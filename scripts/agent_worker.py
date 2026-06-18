#!/usr/bin/env python3
"""
Local AgentOps MIS worker daemon.

This is the v1.5 bridge from "Agent Gateway protocol works" to "an agent can
actually pull a MIS task, execute it through a local adapter, and write evidence
back." It intentionally uses the HTTP Agent Gateway API instead of direct
SQLite writes so the same shape can later run on another machine.

The worker never stores full prompts, raw responses, credentials, transcripts,
or private messages. Tool evidence uses short summaries and hashes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_WORKSPACE_ID = "local-demo"
DEFAULT_AGENT_ID = "agt_worker_local"
DEFAULT_HERMES_GATEWAY_URL = "http://127.0.0.1:8642"
DEFAULT_HERMES_MODEL = "hermes-agent"
DEFAULT_OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_RUNTIME_DIR = ROOT / ".agentops_runtime" / "workers"


SHOULD_STOP = False


def handle_stop_signal(_signum, _frame):
    global SHOULD_STOP
    SHOULD_STOP = True


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_iso_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception:
        return None


def stable_hash(value) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def redact_text(value, limit: int = 200) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    secrets = [
        "sk-",
        "ntn_",
        "Bearer ",
        "Authorization:",
        "api_key",
        "password",
        "token",
    ]
    for marker in secrets:
        if marker.lower() in text.lower():
            text = text.replace(marker, f"{marker[:2]}[REDACTED]")
    return text[:limit]


def json_dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def safe_error(exc: Exception | str) -> dict:
    return {
        "error_type": exc.__class__.__name__ if isinstance(exc, Exception) else "WorkerError",
        "error_message": redact_text(str(exc), 260),
    }


class WorkerState:
    def __init__(self, args):
        if args.state_path:
            self.path = Path(args.state_path)
        else:
            self.path = DEFAULT_RUNTIME_DIR / f"{args.adapter}.state.json"
        self.enabled = bool(args.write_state or args.state_path)
        self.data = {
            "adapter": args.adapter,
            "agent_id": args.agent_id,
            "workspace_id": args.workspace_id,
            "base_url": args.base_url,
            "status": "starting",
            "processed": 0,
            "iterations": 0,
            "total_errors": 0,
            "consecutive_errors": 0,
            "consecutive_idle": 0,
            "max_errors": args.max_errors,
            "continue_on_error": bool(args.continue_on_error),
            "backoff_factor": args.backoff_factor,
            "idle_backoff_max": args.idle_backoff_max,
            "error_backoff_max": args.error_backoff_max,
            "last_sleep_sec": 0,
            "next_sleep_sec": 0,
            "session_refresh_count": 0,
            "adapter_max_attempts": args.adapter_max_attempts,
            "started_at": now_iso(),
            "updated_at": now_iso(),
            "last_heartbeat_at": None,
            "last_result": None,
            "last_error": None,
        }
        self.write()

    def update(self, **kwargs):
        self.data.update(kwargs)
        self.data["updated_at"] = now_iso()
        self.write()

    def record_result(self, result: dict):
        if result.get("processed"):
            self.data["processed"] = int(self.data.get("processed") or 0) + 1
            self.data["consecutive_idle"] = 0
        else:
            self.data["consecutive_idle"] = int(self.data.get("consecutive_idle") or 0) + 1
        self.data["iterations"] = int(self.data.get("iterations") or 0) + 1
        self.data["consecutive_errors"] = 0
        self.data["last_error"] = None
        self.update(
            status="idle" if not result.get("processed") else "completed" if result.get("ok", True) else "failed",
            last_result=result,
            last_task_id=result.get("task_id"),
            last_run_id=result.get("run_id"),
            last_heartbeat_at=now_iso(),
        )

    def record_error(self, exc: Exception | str):
        error = safe_error(exc)
        self.data["iterations"] = int(self.data.get("iterations") or 0) + 1
        self.data["total_errors"] = int(self.data.get("total_errors") or 0) + 1
        self.data["consecutive_errors"] = int(self.data.get("consecutive_errors") or 0) + 1
        self.update(status="error", last_error=error, last_result=None, last_heartbeat_at=now_iso())
        return error

    def stop(self, status: str = "stopped"):
        self.update(status=status, stopped_at=now_iso())

    def write(self):
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass


class AgentOpsClient:
    def __init__(self, base_url: str, workspace_id: str, agent_id: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.workspace_id = workspace_id
        self.agent_id = agent_id
        self.api_key = api_key

    def request(self, method: str, path: str, payload: dict | None = None, query: dict | None = None, timeout: int = 180):
        url = self.base_url + path
        if query:
            url += "?" + urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
        headers = {
            "Content-Type": "application/json",
            "X-AgentOps-Workspace-Id": self.workspace_id,
            "X-AgentOps-Agent-Id": self.agent_id,
        }
        if self.api_key:
            headers["X-AgentOps-Api-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as res:
                raw = res.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc

    def get(self, path: str, query: dict | None = None):
        return self.request("GET", path, query=query)

    def post(self, path: str, payload: dict, timeout: int = 180):
        return self.request("POST", path, payload=payload, timeout=timeout)


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def mint_worker_session(client: AgentOpsClient, args, parent_api_key: str | None = None) -> dict:
    if parent_api_key:
        client.api_key = parent_api_key
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "ttl_sec": args.session_ttl_sec,
    }
    requested_scopes = split_csv(args.session_scopes)
    if requested_scopes:
        payload["scopes"] = requested_scopes
    session = client.post("/api/agent-gateway/session/create", payload, timeout=30)
    token = session.get("session_token")
    if not token:
        raise RuntimeError("session create did not return a one-time session token")
    client.api_key = token
    return {
        "session_id": session.get("session_id"),
        "expires_at": session.get("expires_at"),
        "ttl_sec": session.get("ttl_sec"),
        "scopes": session.get("scopes") or [],
        "token_omitted": True,
    }


def session_seconds_remaining(session_info: dict | None) -> float:
    expires = parse_iso_datetime((session_info or {}).get("expires_at"))
    if not expires:
        return 0.0
    return (expires - dt.datetime.now(dt.timezone.utc)).total_seconds()


def session_needs_refresh(session_info: dict | None, refresh_margin_sec: float) -> bool:
    if not session_info:
        return True
    return session_seconds_remaining(session_info) <= max(float(refresh_margin_sec or 0), 0.0)


def ensure_worker_session(client: AgentOpsClient, args, state: WorkerState, parent_api_key: str, session_info: dict | None, session_history: list[dict]) -> dict:
    if not session_needs_refresh(session_info, args.session_refresh_margin_sec):
        return session_info or {}
    state.update(status="refreshing_session" if session_info else "minting_session")
    next_session = mint_worker_session(client, args, parent_api_key=parent_api_key)
    session_history.append(next_session)
    refresh_count = max(len(session_history) - 1, 0)
    state.update(
        status="session_ready",
        session_id=next_session.get("session_id"),
        session_expires_at=next_session.get("expires_at"),
        session_refresh_count=refresh_count,
    )
    return next_session


@dataclass
class AdapterResult:
    ok: bool
    output_summary: str
    prompt_hash: str
    raw_payload_hash: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    duration_ms: int = 0
    output_tokens: int = 0
    target_resource: str | None = None
    retryable: bool = False
    attempt_count: int = 1
    max_attempts: int = 1
    retry_history: list[dict] | None = None


def build_task_prompt(task: dict) -> str:
    title = redact_text(task.get("title"), 180)
    description = redact_text(task.get("description"), 900)
    acceptance = redact_text(task.get("acceptance_criteria"), 500)
    risk = redact_text(task.get("risk_level") or "medium", 40)
    return (
        "你是 AgentOps MIS 的本地 AI worker。请根据下面的任务摘要给出可交付结果。\n"
        "约束：不要请求外部凭证；不要输出隐藏推理；如果任务信息不足，给出可执行的下一步和缺口。"
        "请用中文，返回 3-6 条要点。\n\n"
        f"任务标题：{title}\n"
        f"任务风险：{risk}\n"
        f"任务描述：{description}\n"
        f"验收标准：{acceptance}\n"
    )


def execute_mock(task: dict, attempt: int = 1, fail_before_success: int = 0) -> AdapterResult:
    prompt = build_task_prompt(task)
    if fail_before_success and attempt <= fail_before_success:
        return AdapterResult(
            ok=False,
            output_summary=f"Mock worker simulated transient adapter failure on attempt {attempt}.",
            prompt_hash=stable_hash(prompt),
            raw_payload_hash=stable_hash({"adapter": "mock", "task_id": task.get("task_id"), "attempt": attempt, "simulated": True}),
            error_type="MockTransientFailure",
            error_message=f"Simulated transient adapter failure before success, attempt {attempt}.",
            target_resource="local://agentops/mock-worker",
            retryable=True,
        )
    summary = f"Mock worker completed task '{redact_text(task.get('title'), 80)}' and produced a safe local execution summary."
    return AdapterResult(
        ok=True,
        output_summary=summary,
        prompt_hash=stable_hash(prompt),
        raw_payload_hash=stable_hash({"adapter": "mock", "task_id": task.get("task_id"), "summary": summary}),
        target_resource="local://agentops/mock-worker",
    )


def execute_hermes(task: dict, gateway_url: str, model: str, confirm_run: bool) -> AdapterResult:
    prompt = build_task_prompt(task)
    if not confirm_run:
        return AdapterResult(
            ok=False,
            output_summary="Hermes adapter dry-run: pass --confirm-run to execute.",
            prompt_hash=stable_hash(prompt),
            error_type="ConfirmRunRequired",
            error_message="Hermes live execution requires --confirm-run.",
            target_resource=gateway_url.rstrip() + "/v1/chat/completions",
            retryable=False,
        )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }
    started = time.time()
    try:
        req = Request(
            gateway_url.rstrip("/") + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=180) as res:
            response = json.loads(res.read().decode("utf-8"))
        visible = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        usage = response.get("usage") or {}
        return AdapterResult(
            ok=bool(visible),
            output_summary=redact_text(visible, 200) if visible else "Hermes returned an empty response.",
            prompt_hash=stable_hash(prompt),
            raw_payload_hash=stable_hash(response),
            error_type=None if visible else "HermesEmptyResponse",
            error_message=None if visible else "Hermes returned no visible content.",
            duration_ms=int((time.time() - started) * 1000),
            output_tokens=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
            target_resource=gateway_url.rstrip("/") + "/v1/chat/completions",
            retryable=not bool(visible),
        )
    except Exception as exc:
        return AdapterResult(
            ok=False,
            output_summary="Hermes adapter execution failed.",
            prompt_hash=stable_hash(prompt),
            error_type="HermesExecutionFailed",
            error_message=redact_text(str(exc), 200),
            duration_ms=int((time.time() - started) * 1000),
            target_resource=gateway_url.rstrip("/") + "/v1/chat/completions",
            retryable=True,
        )


def execute_openclaw(task: dict, binary_path: str, agent_name: str, timeout: int, confirm_run: bool) -> AdapterResult:
    prompt = build_task_prompt(task)
    if not confirm_run:
        return AdapterResult(
            ok=False,
            output_summary="OpenClaw adapter dry-run: pass --confirm-run to execute.",
            prompt_hash=stable_hash(prompt),
            error_type="ConfirmRunRequired",
            error_message="OpenClaw live execution requires --confirm-run.",
            target_resource=f"local://openclaw/{agent_name}",
            retryable=False,
        )
    started = time.time()
    try:
        proc = subprocess.run(
            [binary_path, "agent", "--agent", agent_name, "-m", prompt, "--timeout", str(timeout), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout + 30,
            check=False,
        )
        payload = json.loads(proc.stdout) if proc.stdout else {}
        meta = (payload.get("result") or {}).get("meta") or {}
        visible = meta.get("finalAssistantVisibleText") or (((payload.get("result") or {}).get("payloads") or [{}])[0].get("text"))
        visible = (visible or "").strip()
        ok = proc.returncode == 0 and bool(visible)
        return AdapterResult(
            ok=ok,
            output_summary=redact_text(visible, 200) if ok else "OpenClaw adapter execution failed.",
            prompt_hash=stable_hash(prompt),
            raw_payload_hash=stable_hash(payload or {"stderr": proc.stderr, "returncode": proc.returncode}),
            error_type=None if ok else "OpenClawExecutionFailed",
            error_message=None if ok else redact_text(proc.stderr or visible or f"exit={proc.returncode}", 200),
            duration_ms=int(meta.get("durationMs") or ((time.time() - started) * 1000)),
            target_resource=f"local://openclaw/{agent_name}",
            retryable=not ok,
        )
    except Exception as exc:
        return AdapterResult(
            ok=False,
            output_summary="OpenClaw adapter execution failed.",
            prompt_hash=stable_hash(prompt),
            error_type="OpenClawExecutionFailed",
            error_message=redact_text(str(exc), 200),
            duration_ms=int((time.time() - started) * 1000),
            target_resource=f"local://openclaw/{agent_name}",
            retryable=True,
        )


def execute_adapter_once(task: dict, args, attempt: int) -> AdapterResult:
    if args.adapter == "mock":
        return execute_mock(task, attempt=attempt, fail_before_success=args.mock_failures_before_success)
    if args.adapter == "hermes":
        return execute_hermes(task, args.hermes_gateway_url, args.hermes_model, args.confirm_run)
    if args.adapter == "openclaw":
        return execute_openclaw(task, args.openclaw_bin, args.openclaw_agent, args.openclaw_timeout, args.confirm_run)
    raise RuntimeError(f"unknown adapter: {args.adapter}")


def execute_adapter_with_retries(task: dict, args) -> AdapterResult:
    max_attempts = min(max(int(args.adapter_max_attempts or 1), 1), 5)
    retry_delay = max(float(args.adapter_retry_delay_sec or 0), 0.0)
    history = []
    result = None
    for attempt in range(1, max_attempts + 1):
        result = execute_adapter_once(task, args, attempt)
        history.append({
            "attempt": attempt,
            "ok": result.ok,
            "error_type": result.error_type,
            "retryable": result.retryable,
            "summary": redact_text(result.output_summary, 120),
        })
        if result.ok:
            break
        if not result.retryable or attempt >= max_attempts:
            break
        if retry_delay:
            time.sleep(retry_delay)
    if result is None:
        raise RuntimeError("adapter execution produced no result")
    result.attempt_count = len(history)
    result.max_attempts = max_attempts
    result.retry_history = history
    if result.attempt_count > 1:
        result.output_summary = f"{result.output_summary} Adapter attempts: {result.attempt_count}/{max_attempts}."
    return result


def risk_allowed(task: dict, allow_high_risk: bool) -> bool:
    return allow_high_risk or (task.get("risk_level") or "medium") in {"low", "medium"}


def emit_jsonl(args, payload: dict):
    if args.jsonl_log:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def safe_worker_heartbeat(client: AgentOpsClient, args, status: str, summary: str):
    try:
        client.post("/api/agent-gateway/heartbeat", {
            "workspace_id": client.workspace_id,
            "agent_id": client.agent_id,
            "status": status,
            "summary": redact_text(summary, 200),
            "runtime_type": args.adapter,
        }, timeout=20)
    except Exception:
        pass


def backoff_sleep(base_interval: float, cap: float, streak: int, factor: float) -> float:
    base = max(float(base_interval or 0), 0.0)
    if base <= 0:
        return 0.0
    capped = max(float(cap or base), base)
    multiplier = max(float(factor or 1.0), 1.0) ** max(int(streak or 1) - 1, 0)
    return min(base * multiplier, capped)


def register_worker(client: AgentOpsClient, adapter: str):
    return client.post("/api/agent-gateway/register", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "name": "Local Agent Worker",
        "role": f"Local {adapter} Adapter Worker",
        "runtime_type": "hermes" if adapter == "hermes" else "openclaw" if adapter == "openclaw" else "mock",
        "model_provider": adapter,
        "model_name": adapter,
        "permission_level": "standard",
        "allowed_tools": ["agent_gateway.task", f"{adapter}.execute", "agent_gateway.audit"],
        "budget_limit_usd": 5.0,
        "description": "Repo-local v1.5 worker daemon.",
    })


def process_one_task(client: AgentOpsClient, args) -> dict:
    pulled = client.get("/api/agent-gateway/tasks/pull", {
        "agent_id": client.agent_id,
        "workspace_id": client.workspace_id,
        "limit": 1,
        "status": args.status,
    })
    tasks = pulled.get("tasks") or []
    if not tasks:
        client.post("/api/agent-gateway/heartbeat", {
            "workspace_id": client.workspace_id,
            "agent_id": client.agent_id,
            "status": "idle",
            "summary": "Worker found no eligible task.",
            "runtime_type": args.adapter,
        })
        return {"processed": False, "reason": "no_task"}

    task = tasks[0]
    task_id = task["task_id"]
    if not risk_allowed(task, args.allow_high_risk):
        return {"processed": False, "task_id": task_id, "reason": "risk_not_allowed", "risk_level": task.get("risk_level")}

    client.post(f"/api/agent-gateway/tasks/{task_id}/claim", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "runtime_type": args.adapter,
    })
    run_payload = client.post("/api/agent-gateway/runs/start", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "task_id": task_id,
        "runtime_type": args.adapter,
        "input_summary": f"Worker adapter={args.adapter} task={redact_text(task.get('title'), 120)}",
        "delegation_id": f"worker:{args.adapter}:{task_id}",
    })
    run = run_payload["run"]
    run_id = run["run_id"]

    result = execute_adapter_with_retries(task, args)

    tool_status = "completed" if result.ok else "failed"
    client.post("/api/agent-gateway/tool-calls", {
        "workspace_id": client.workspace_id,
        "run_id": run_id,
        "agent_id": client.agent_id,
        "tool_name": f"agent_worker.{args.adapter}",
        "tool_category": "custom",
        "risk_level": "low",
        "status": tool_status,
        "target_resource": result.target_resource,
        "args": {
            "task_id": task_id,
            "adapter": args.adapter,
            "prompt_hash": result.prompt_hash,
            "attempt_count": result.attempt_count,
            "max_attempts": result.max_attempts,
            "retry_history": result.retry_history or [],
            "raw_omitted": True,
        },
        "result_summary": result.output_summary,
    })
    final_status = "completed" if result.ok else "failed"
    client.post(f"/api/agent-gateway/runs/{run_id}/heartbeat", {
        "workspace_id": client.workspace_id,
        "status": final_status,
        "output_summary": result.output_summary,
        "duration_ms": result.duration_ms,
        "output_tokens": result.output_tokens,
        "cost_usd": 0.0,
        "error_type": result.error_type,
        "error_message": result.error_message,
    })
    client.post("/api/agent-gateway/evaluations/submit", {
        "workspace_id": client.workspace_id,
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": client.agent_id,
        "evaluator_type": "rule",
        "score": 1.0 if result.ok else 0.0,
        "pass_fail": "pass" if result.ok else "fail",
        "rubric": {
            "gate": "worker_adapter_loop",
            "adapter": args.adapter,
            "requires_completed_run": True,
            "raw_prompt_response_omitted": True,
            "attempt_count": result.attempt_count,
            "max_attempts": result.max_attempts,
        },
        "notes": "Worker adapter loop completed." if result.ok else f"Worker adapter loop failed: {result.error_type}",
    })
    if result.ok:
        client.post("/api/agent-gateway/memories/propose", {
            "workspace_id": client.workspace_id,
            "agent_id": client.agent_id,
            "task_id": task_id,
            "run_id": run_id,
            "scope": "workspace",
            "memory_type": "artifact_summary",
            "canonical_text": f"Worker {client.agent_id} completed task '{redact_text(task.get('title'), 80)}' via {args.adapter}.",
            "source_ref": run_id,
            "access_tags": ["worker-loop", args.adapter, "review"],
            "confidence": 0.72,
        })
    client.post("/api/agent-gateway/audit", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "action": "agent_worker.task_processed",
        "entity_type": "runs",
        "entity_id": run_id,
        "task_id": task_id,
        "run_id": run_id,
        "metadata": {
            "adapter": args.adapter,
            "ok": result.ok,
            "prompt_hash": result.prompt_hash,
            "raw_payload_hash": result.raw_payload_hash,
            "attempt_count": result.attempt_count,
            "max_attempts": result.max_attempts,
            "retryable_final": result.retryable,
        },
    })
    client.post("/api/agent-gateway/heartbeat", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "status": "idle" if result.ok else "error",
        "summary": result.output_summary,
        "runtime_type": args.adapter,
    })
    return {
        "processed": True,
        "task_id": task_id,
        "run_id": run_id,
        "adapter": args.adapter,
        "ok": result.ok,
        "attempt_count": result.attempt_count,
        "output_summary": result.output_summary,
        "error_type": result.error_type,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local AgentOps MIS worker loop.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--api-key", default=os.environ.get("AGENTOPS_API_KEY", ""))
    parser.add_argument("--use-session", action="store_true", help="Mint a short-lived Agent Gateway session before running the worker.")
    parser.add_argument("--session-ttl-sec", type=int, default=int(os.environ.get("AGENTOPS_SESSION_TTL_SEC", "900")), help="Session TTL when --use-session is set.")
    parser.add_argument("--session-refresh-margin-sec", type=float, default=float(os.environ.get("AGENTOPS_SESSION_REFRESH_MARGIN_SEC", "60")), help="Refresh the short-lived session when it has this many seconds or less remaining.")
    parser.add_argument("--session-scopes", default=os.environ.get("AGENTOPS_SESSION_SCOPES", ""), help="Optional comma-separated subset for the worker session. Defaults to parent token scopes.")
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--status", action="append", default=["planned"], help="Task status to pull. Repeatable.")
    parser.add_argument("--once", action="store_true", help="Process at most one task and exit.")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--idle-backoff-max", type=float, default=30.0, help="Maximum sleep seconds after consecutive no-task polls.")
    parser.add_argument("--error-backoff-max", type=float, default=30.0, help="Maximum sleep seconds after consecutive worker errors.")
    parser.add_argument("--backoff-factor", type=float, default=2.0, help="Exponential backoff factor for idle/error loops.")
    parser.add_argument("--max-tasks", type=int, default=1, help="Maximum tasks to process before exit. Use 0 for no limit.")
    parser.add_argument("--confirm-run", action="store_true", help="Allow live runtime adapter execution.")
    parser.add_argument("--allow-high-risk", action="store_true", help="Allow high/critical risk tasks.")
    parser.add_argument("--adapter-max-attempts", type=int, default=int(os.environ.get("AGENTOPS_ADAPTER_MAX_ATTEMPTS", "1")), help="Maximum adapter execution attempts for retryable failures.")
    parser.add_argument("--adapter-retry-delay-sec", type=float, default=float(os.environ.get("AGENTOPS_ADAPTER_RETRY_DELAY_SEC", "1")), help="Delay between retryable adapter attempts.")
    parser.add_argument("--mock-failures-before-success", type=int, default=int(os.environ.get("AGENTOPS_MOCK_FAILURES_BEFORE_SUCCESS", "0")), help="Local test hook: make the mock adapter fail this many retryable attempts before succeeding.")
    parser.add_argument("--hermes-gateway-url", default=os.environ.get("HERMES_GATEWAY_URL", DEFAULT_HERMES_GATEWAY_URL))
    parser.add_argument("--hermes-model", default=os.environ.get("HERMES_MODEL", DEFAULT_HERMES_MODEL))
    parser.add_argument("--openclaw-bin", default=os.environ.get("OPENCLAW_BIN", DEFAULT_OPENCLAW_BIN))
    parser.add_argument("--openclaw-agent", default=os.environ.get("OPENCLAW_AGENT", "main"))
    parser.add_argument("--openclaw-timeout", type=int, default=int(os.environ.get("OPENCLAW_TIMEOUT", "180")))
    parser.add_argument("--continue-on-error", action="store_true", help="Keep polling after a loop/API/adapter error.")
    parser.add_argument("--max-errors", type=int, default=5, help="Stop after this many consecutive errors when continuing.")
    parser.add_argument("--state-path", default=os.environ.get("AGENTOPS_WORKER_STATE_PATH", ""))
    parser.add_argument("--write-state", action="store_true", help="Write local worker state under .agentops_runtime/workers.")
    parser.add_argument("--jsonl-log", action="store_true", help="Emit one JSON log line per loop iteration.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)
    client = AgentOpsClient(args.base_url, args.workspace_id, args.agent_id, args.api_key)
    state = WorkerState(args)
    processed = 0
    results = []
    registered = False
    fatal_failure = False
    session_info = None
    session_history = []
    parent_api_key = args.api_key
    if args.use_session:
        try:
            session_info = ensure_worker_session(client, args, state, parent_api_key, session_info, session_history)
        except Exception as exc:
            error = state.record_error(exc)
            state.stop("failed_session_create")
            print(json_dumps({"ok": False, "processed": 0, "results": [{**error, "processed": False, "ok": False}], "state": state.data, "session": {"token_omitted": True}, "sessions": session_history}))
            return 1
    while True:
        if SHOULD_STOP:
            break
        try:
            if args.use_session:
                session_info = ensure_worker_session(client, args, state, parent_api_key, session_info, session_history)
            if not registered:
                state.update(status="registering")
                register_worker(client, args.adapter)
                registered = True
            state.update(status="polling")
            result = process_one_task(client, args)
            results.append(result)
            state.record_result(result)
            emit_jsonl(args, {"event": "worker.iteration", "ok": True, "result": result, "state": state.data})
            if result.get("processed"):
                processed += 1
            if args.once:
                break
            if args.max_tasks and processed >= args.max_tasks:
                break
            if result.get("processed"):
                sleep_sec = max(args.poll_interval, 0.0)
                sleep_reason = "post_task"
            else:
                sleep_sec = backoff_sleep(args.poll_interval, args.idle_backoff_max, int(state.data.get("consecutive_idle") or 1), args.backoff_factor)
                sleep_reason = "idle_backoff"
            state.update(status="sleeping", last_sleep_sec=sleep_sec, next_sleep_sec=sleep_sec, last_sleep_reason=sleep_reason)
            time.sleep(sleep_sec)
        except Exception as exc:
            error = state.record_error(exc)
            result = {"processed": False, "ok": False, **error}
            results.append(result)
            safe_worker_heartbeat(client, args, "error", error["error_message"])
            emit_jsonl(args, {"event": "worker.error", "ok": False, "error": error, "state": state.data})
            if args.once or not args.continue_on_error:
                fatal_failure = True
                state.stop("failed")
                break
            if int(state.data.get("consecutive_errors") or 0) >= max(int(args.max_errors or 1), 1):
                fatal_failure = True
                state.stop("failed_max_errors")
                break
            sleep_sec = backoff_sleep(args.poll_interval, args.error_backoff_max, int(state.data.get("consecutive_errors") or 1), args.backoff_factor)
            state.update(status="sleeping_after_error", last_sleep_sec=sleep_sec, next_sleep_sec=sleep_sec, last_sleep_reason="error_backoff")
            time.sleep(sleep_sec)
    final_ok = (
        not fatal_failure
        and all(item.get("ok", True) for item in results if item.get("processed"))
        and not any(item.get("ok") is False for item in results if args.once)
    )
    final_status = "stopped" if SHOULD_STOP else "completed" if final_ok else "failed"
    state.stop(final_status)
    print(json_dumps({"ok": final_ok, "processed": processed, "results": results, "state": state.data, "session": session_info or {"token_omitted": True}, "sessions": session_history}))
    return 0 if final_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
