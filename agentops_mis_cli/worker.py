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
import html
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agentops_mis_cli.redaction import redact_text


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT if (PACKAGE_ROOT / "server.py").exists() else None
DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_WORKSPACE_ID = "local-demo"
DEFAULT_AGENT_ID = "agt_worker_local"
DEFAULT_HERMES_GATEWAY_URL = "http://127.0.0.1:8642"
DEFAULT_HERMES_MODEL = "hermes-agent"
DEFAULT_OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"


def default_runtime_dir() -> Path:
    configured = os.environ.get("AGENTOPS_WORKER_RUNTIME_DIR")
    if configured:
        return Path(configured).expanduser()
    if REPO_ROOT:
        return REPO_ROOT / ".agentops_runtime" / "workers"
    return Path(os.environ.get("AGENTOPS_HOME", "~/.agentops")).expanduser() / "workers"


def default_worker_cwd() -> Path:
    configured = os.environ.get("AGENTOPS_WORKER_CWD")
    if configured:
        return Path(configured).expanduser()
    return REPO_ROOT or Path.cwd()


DEFAULT_RUNTIME_DIR = default_runtime_dir()
DEFAULT_WORKER_CWD = default_worker_cwd()


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


def execute_hermes(task: dict, gateway_url: str, model: str, timeout: int, confirm_run: bool) -> AdapterResult:
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
        with urlopen(req, timeout=max(int(timeout or 180), 1)) as res:
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
            cwd=DEFAULT_WORKER_CWD,
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
        return execute_hermes(task, args.hermes_gateway_url, args.hermes_model, args.hermes_timeout, args.confirm_run)
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


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def max_risk(*values: str | None) -> str:
    selected = "low"
    for value in values:
        risk = str(value or "low").lower()
        if risk not in RISK_ORDER:
            risk = "low"
        if RISK_ORDER[risk] > RISK_ORDER[selected]:
            selected = risk
    return selected


def adapter_capability_profile(adapter: str) -> dict:
    if adapter == "mock":
        return {
            "observation_level": "structured_ledger",
            "risk_floor": "low",
            "commercial_readiness": "local_demo_ready",
            "requires_prepared_action_for_external_write": False,
        }
    if adapter in {"hermes", "openclaw"}:
        return {
            "observation_level": "ledger_summary_only",
            "risk_floor": "medium",
            "commercial_readiness": "restricted_until_runtime_tool_events",
            "requires_prepared_action_for_external_write": True,
        }
    return {
        "observation_level": "ledger_summary_only",
        "risk_floor": "medium",
        "commercial_readiness": "unknown_runtime",
        "requires_prepared_action_for_external_write": True,
    }


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
        "description": "Installable v1.5 worker daemon.",
    })


def create_worker_agent_plan(client: AgentOpsClient, task: dict, args) -> dict:
    risk = task.get("risk_level") or "medium"
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "task_id": task["task_id"],
        "task_understanding": (
            f"Process task '{redact_text(task.get('title'), 120)}' through the {args.adapter} worker adapter, "
            "write run/tool/evaluation/artifact/audit evidence, then bind the result to this plan."
        ),
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md", "docs/AGENT_WORK_METHOD_BLOCK.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks", "base_local_memory"],
        "proposed_files_to_change": ["agentops-worker-runtime", f"adapter:{args.adapter}"],
        "risk_level": risk,
        "approval_required": risk in {"high", "critical"},
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "verification_plan": "Agent worker must submit tool, evaluation, artifact, audit and plan_evidence_manifest evidence.",
        "rollback_plan": "Mark the run failed/blocked and leave the manifest blocked if execution evidence is incomplete.",
        "status": "submitted",
    }
    return client.post("/api/agent-gateway/agent-plans", payload)


def create_worker_plan_manifest(client: AgentOpsClient, plan_id: str, run_id: str, tool_call_id: str | None, evaluation_id: str | None, artifact_id: str | None) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "plan_id": plan_id,
        "run_id": run_id,
        "mismatch_policy": "block",
        "expected_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "tool_call_ids": [tool_call_id] if tool_call_id else [],
        "evaluation_ids": [evaluation_id] if evaluation_id else [],
        "artifact_ids": [artifact_id] if artifact_id else [],
    }
    return client.post("/api/agent-gateway/plan-evidence-manifests", payload)


def process_one_task(client: AgentOpsClient, args) -> dict:
    pull_query = {
        "agent_id": client.agent_id,
        "workspace_id": client.workspace_id,
        "limit": 1,
        "status": args.status,
        "enforce_intake": "true" if args.enforce_intake else "false",
    }
    if args.task_id:
        pull_query["task_id"] = args.task_id
    pulled = client.get("/api/agent-gateway/tasks/pull", pull_query)
    tasks = pulled.get("tasks") or []
    if not tasks:
        intake = pulled.get("intake") or {}
        if intake.get("blocked"):
            return {
                "processed": False,
                "reason": "intake_blocked",
                "intake": {
                    "blocked": intake.get("blocked", 0),
                    "next_actions": intake.get("next_actions") or [],
                    "blocked_tasks": intake.get("blocked_tasks") or [],
                    "token_omitted": True,
                },
            }
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
    plan_payload = create_worker_agent_plan(client, task, args)
    plan_id = (plan_payload.get("agent_plan") or {}).get("plan_id")
    if not plan_id:
        raise RuntimeError("agent plan create did not return plan_id")
    verified_plan = client.get(f"/api/agent-gateway/agent-plans/{plan_id}/verify")
    if not (verified_plan.get("verification") or {}).get("pass"):
        raise RuntimeError(f"agent plan verification failed before run_start: {json_dumps(verified_plan.get('verification') or {})}")
    run_payload = client.post("/api/agent-gateway/runs/start", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "task_id": task_id,
        "agent_plan_id": plan_id,
        "runtime_type": args.adapter,
        "input_summary": f"Worker adapter={args.adapter} task={redact_text(task.get('title'), 120)}",
        "delegation_id": f"worker:{args.adapter}:{task_id}",
    })
    run = run_payload["run"]
    run_id = run["run_id"]

    result = execute_adapter_with_retries(task, args)
    capability = adapter_capability_profile(args.adapter)
    tool_risk = max_risk(task.get("risk_level"), capability.get("risk_floor"))

    tool_status = "completed" if result.ok else "failed"
    tool_payload = client.post("/api/agent-gateway/tool-calls", {
        "workspace_id": client.workspace_id,
        "run_id": run_id,
        "agent_id": client.agent_id,
        "tool_name": f"agent_worker.{args.adapter}",
        "tool_category": "custom",
        "risk_level": tool_risk,
        "status": tool_status,
        "target_resource": result.target_resource,
        "args": {
            "task_id": task_id,
            "adapter": args.adapter,
            "prompt_hash": result.prompt_hash,
            "attempt_count": result.attempt_count,
            "max_attempts": result.max_attempts,
            "retry_history": result.retry_history or [],
            "observation_level": capability.get("observation_level"),
            "risk_floor": capability.get("risk_floor"),
            "effective_risk_level": tool_risk,
            "commercial_readiness": capability.get("commercial_readiness"),
            "requires_prepared_action_for_external_write": capability.get("requires_prepared_action_for_external_write"),
            "raw_omitted": True,
        },
        "result_summary": result.output_summary,
    })
    tool_call_id = (tool_payload.get("tool_call") or {}).get("tool_call_id")
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
    eval_payload = client.post("/api/agent-gateway/evaluations/submit", {
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
            "observation_level": capability.get("observation_level"),
            "risk_floor": capability.get("risk_floor"),
            "effective_risk_level": tool_risk,
            "commercial_readiness": capability.get("commercial_readiness"),
            "requires_prepared_action_for_external_write": capability.get("requires_prepared_action_for_external_write"),
        },
        "notes": "Worker adapter loop completed." if result.ok else f"Worker adapter loop failed: {result.error_type}",
    })
    evaluation_id = (eval_payload.get("evaluation") or {}).get("evaluation_id")
    artifact_payload = client.post("/api/agent-gateway/artifacts", {
        "workspace_id": client.workspace_id,
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": client.agent_id,
        "artifact_type": "agent_worker_result",
        "title": f"Agent worker result: {redact_text(task.get('title'), 120)}",
        "uri": f"run://{run_id}",
        "summary": result.output_summary,
        "content_hash": stable_hash({
            "run_id": run_id,
            "task_id": task_id,
            "adapter": args.adapter,
            "summary": result.output_summary,
            "ok": result.ok,
        }),
    })
    artifact_id = (artifact_payload.get("artifact") or {}).get("artifact_id")
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
            "observation_level": capability.get("observation_level"),
            "risk_floor": capability.get("risk_floor"),
            "effective_risk_level": tool_risk,
            "commercial_readiness": capability.get("commercial_readiness"),
            "requires_prepared_action_for_external_write": capability.get("requires_prepared_action_for_external_write"),
        },
    })
    manifest_payload = create_worker_plan_manifest(client, plan_id, run_id, tool_call_id, evaluation_id, artifact_id)
    manifest = manifest_payload.get("manifest") or {}
    manifest_verification = manifest_payload.get("verification") or {}
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
        "plan_id": plan_id,
        "plan_evidence_manifest_id": manifest.get("manifest_id"),
        "plan_evidence_status": manifest.get("status"),
        "plan_evidence_pass": manifest_verification.get("pass"),
        "adapter": args.adapter,
        "ok": result.ok,
        "attempt_count": result.attempt_count,
        "output_summary": result.output_summary,
        "error_type": result.error_type,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an AgentOps MIS worker loop.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--api-key", default=os.environ.get("AGENTOPS_API_KEY", ""))
    parser.add_argument("--use-session", action="store_true", help="Mint a short-lived Agent Gateway session before running the worker.")
    parser.add_argument("--session-ttl-sec", type=int, default=int(os.environ.get("AGENTOPS_SESSION_TTL_SEC", "900")), help="Session TTL when --use-session is set.")
    parser.add_argument("--session-refresh-margin-sec", type=float, default=float(os.environ.get("AGENTOPS_SESSION_REFRESH_MARGIN_SEC", "60")), help="Refresh the short-lived session when it has this many seconds or less remaining.")
    parser.add_argument("--session-scopes", default=os.environ.get("AGENTOPS_SESSION_SCOPES", ""), help="Optional comma-separated subset for the worker session. Defaults to parent token scopes.")
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--task-id", default=os.environ.get("AGENTOPS_TASK_ID", ""), help="Optional exact task id to pull and process.")
    parser.add_argument("--status", action="append", default=["planned"], help="Task status to pull. Repeatable.")
    parser.add_argument("--enforce-intake", action=argparse.BooleanOptionalAction, default=True, help="Require Agent Plan / knowledge / base-reference / risk intake gates before pulling tasks.")
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
    parser.add_argument("--hermes-timeout", type=int, default=int(os.environ.get("HERMES_TIMEOUT", "180")))
    parser.add_argument("--openclaw-bin", default=os.environ.get("OPENCLAW_BIN", DEFAULT_OPENCLAW_BIN))
    parser.add_argument("--openclaw-agent", default=os.environ.get("OPENCLAW_AGENT", "main"))
    parser.add_argument("--openclaw-timeout", type=int, default=int(os.environ.get("OPENCLAW_TIMEOUT", "180")))
    parser.add_argument("--continue-on-error", action="store_true", help="Keep polling after a loop/API/adapter error.")
    parser.add_argument("--max-errors", type=int, default=5, help="Stop after this many consecutive errors when continuing.")
    parser.add_argument("--state-path", default=os.environ.get("AGENTOPS_WORKER_STATE_PATH", ""))
    parser.add_argument("--write-state", action="store_true", help="Write local worker state under .agentops_runtime/workers.")
    parser.add_argument("--jsonl-log", action="store_true", help="Emit one JSON log line per loop iteration.")
    return parser


def service_label(agent_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", agent_id or DEFAULT_AGENT_ID).strip("-")
    return f"local.agentops.worker.{safe or 'agent'}"


def build_worker_command(args) -> list[str]:
    command = [
        "agentops-worker",
        "--adapter",
        args.adapter,
        "--use-session",
        "--session-ttl-sec",
        str(args.session_ttl_sec),
        "--session-refresh-margin-sec",
        str(args.session_refresh_margin_sec),
        "--poll-interval",
        str(args.poll_interval),
        "--max-tasks",
        "0",
        "--continue-on-error",
        "--write-state",
        "--jsonl-log",
    ]
    if args.confirm_run:
        command.append("--confirm-run")
    return command


def render_launchd_template(args) -> str:
    label = args.label or service_label(args.agent_id)
    runtime_dir = args.runtime_dir or "~/Library/Application Support/AgentOpsMIS/workers"
    log_path = args.log_path or f"~/Library/Logs/{label}.log"
    env_values = {
        "AGENTOPS_BASE_URL": args.base_url,
        "AGENTOPS_WORKSPACE_ID": args.workspace_id,
        "AGENTOPS_AGENT_ID": args.agent_id,
        "AGENTOPS_API_KEY": args.api_key_placeholder,
        "AGENTOPS_WORKER_RUNTIME_DIR": runtime_dir,
        "AGENTOPS_WORKER_CWD": args.working_directory,
    }
    program_args = ["/usr/bin/env", *build_worker_command(args)]
    arg_items = "\n".join(f"    <string>{html.escape(item)}</string>" for item in program_args)
    env_items = "\n".join(
        f"    <key>{html.escape(key)}</key>\n    <string>{html.escape(str(value))}</string>"
        for key, value in env_values.items()
    )
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key>
  <string>{html.escape(label)}</string>
  <key>ProgramArguments</key>
  <array>
{arg_items}
  </array>
  <key>EnvironmentVariables</key>
  <dict>
{env_items}
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{html.escape(log_path)}</string>
  <key>StandardErrorPath</key>
  <string>{html.escape(log_path)}</string>
</dict>
</plist>
"""


def render_systemd_template(args) -> str:
    label = args.label or service_label(args.agent_id)
    runtime_dir = args.runtime_dir or "%h/.agentops/workers"
    log_path = args.log_path or "%h/.agentops/agentops-worker.log"
    env_values = {
        "AGENTOPS_BASE_URL": args.base_url,
        "AGENTOPS_WORKSPACE_ID": args.workspace_id,
        "AGENTOPS_AGENT_ID": args.agent_id,
        "AGENTOPS_API_KEY": args.api_key_placeholder,
        "AGENTOPS_WORKER_RUNTIME_DIR": runtime_dir,
        "AGENTOPS_WORKER_CWD": args.working_directory,
    }
    env_lines = "\n".join(f"Environment={shlex.quote(f'{key}={value}')}" for key, value in env_values.items())
    command = " ".join(shlex.quote(part) for part in build_worker_command(args))
    return f"""[Unit]
Description=AgentOps MIS Worker ({label})
After=network-online.target

[Service]
Type=simple
{env_lines}
ExecStart=/usr/bin/env {command}
Restart=always
RestartSec=5
StandardOutput=append:{log_path}
StandardError=append:{log_path}

[Install]
WantedBy=default.target
"""


def build_service_template_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a safe launchd/systemd template for agentops-worker.")
    parser.add_argument("--manager", choices=["launchd", "systemd"], required=True)
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--session-ttl-sec", type=int, default=900)
    parser.add_argument("--session-refresh-margin-sec", type=float, default=60)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--label", default="")
    parser.add_argument("--working-directory", default=str(DEFAULT_WORKER_CWD))
    parser.add_argument("--runtime-dir", default="")
    parser.add_argument("--log-path", default="")
    parser.add_argument("--api-key-placeholder", default="<paste one-time token here>")
    return parser


def render_service_template_for_args(args) -> str:
    if args.manager == "launchd":
        return render_launchd_template(args)
    return render_systemd_template(args)


def default_service_path(manager: str, agent_id: str, label: str = "") -> Path:
    safe_agent = re.sub(r"[^A-Za-z0-9_.-]+", "-", agent_id or DEFAULT_AGENT_ID).strip("-") or "agent"
    if manager == "launchd":
        service_name = label or service_label(agent_id)
        return Path("~/Library/LaunchAgents").expanduser() / f"{service_name}.plist"
    return Path("~/.config/systemd/user").expanduser() / f"agentops-worker-{safe_agent}.service"


def service_load_commands(manager: str, path: Path, label: str) -> dict:
    if manager == "launchd":
        domain = f"gui/{os.getuid()}"
        return {
            "load": ["launchctl", "bootstrap", domain, str(path)],
            "unload": ["launchctl", "bootout", domain, str(path)],
            "status": ["launchctl", "print", f"{domain}/{label}"],
        }
    unit = path.name
    return {
        "daemon_reload": ["systemctl", "--user", "daemon-reload"],
        "enable_now": ["systemctl", "--user", "enable", "--now", unit],
        "disable_now": ["systemctl", "--user", "disable", "--now", unit],
        "status": ["systemctl", "--user", "status", unit, "--no-pager"],
    }


def read_service_file(path: Path) -> tuple[bool, str]:
    try:
        return True, path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return False, ""
    except Exception as exc:
        return False, f"READ_ERROR:{redact_text(str(exc), 200)}"


def launchd_status(label: str, timeout: int) -> dict:
    try:
        target = f"gui/{os.getuid()}/{label}"
        proc = subprocess.run(
            ["launchctl", "print", target],
            capture_output=True,
            text=True,
            timeout=max(1, min(timeout, 20)),
            check=False,
        )
        summary = redact_text((proc.stdout or proc.stderr or "").strip(), 600)
        return {
            "checked": True,
            "manager": "launchd",
            "label": label,
            "loaded": proc.returncode == 0,
            "returncode": proc.returncode,
            "summary": summary,
        }
    except Exception as exc:
        return {"checked": True, "manager": "launchd", "label": label, "loaded": False, **safe_error(exc)}


def systemd_status(unit: str, timeout: int) -> dict:
    if not shutil.which("systemctl"):
        return {"checked": True, "manager": "systemd", "unit": unit, "available": False, "loaded": False, "summary": "systemctl is not available."}
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "show", unit, "--property=LoadState,ActiveState,SubState,UnitFileState", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=max(1, min(timeout, 20)),
            check=False,
        )
        fields = {}
        for line in (proc.stdout or "").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key] = value
        return {
            "checked": True,
            "manager": "systemd",
            "unit": unit,
            "available": True,
            "loaded": fields.get("LoadState") == "loaded",
            "active_state": fields.get("ActiveState"),
            "sub_state": fields.get("SubState"),
            "unit_file_state": fields.get("UnitFileState"),
            "returncode": proc.returncode,
            "summary": redact_text(proc.stderr or proc.stdout or "", 600),
        }
    except Exception as exc:
        return {"checked": True, "manager": "systemd", "unit": unit, "available": True, "loaded": False, **safe_error(exc)}


def check_service_installation(args) -> dict:
    label = args.label or service_label(args.agent_id)
    service_path = Path(args.service_path).expanduser() if args.service_path else default_service_path(args.manager, args.agent_id, label)
    exists, content = read_service_file(service_path)
    token_like_detected = bool(re.search(r"(agtok_|agtsess_|sk-|ntn_)", content))
    placeholder_present = args.api_key_placeholder in content if exists else False
    command_has_worker = "agentops-worker" in content
    adapter_present = args.adapter in content
    use_session_present = "--use-session" in content
    confirm_gate_ok = args.adapter == "mock" or "--confirm-run" in content
    if args.manager == "launchd":
        service_status = launchd_status(label, args.timeout)
    else:
        unit = service_path.name
        service_status = systemd_status(unit, args.timeout)
    ok = bool(exists and command_has_worker and adapter_present and use_session_present and confirm_gate_ok and not token_like_detected)
    hints = []
    if not exists:
        hints.append("Render a template with agentops-worker service-template and write it to service_path.")
    if token_like_detected:
        hints.append("Replace raw tokens with a local environment-only secret flow; do not commit service files with real tokens.")
    if args.adapter != "mock" and not confirm_gate_ok:
        hints.append("Hermes/OpenClaw services need --confirm-run only when the operator intentionally allows live execution.")
    if exists and not service_status.get("loaded"):
        hints.append("Service file exists but does not appear loaded; load it manually on the agent machine after review.")
    return {
        "ok": ok,
        "provider": "agentops-worker",
        "command": "agentops-worker service-check",
        "manager": args.manager,
        "label": label,
        "agent_id": args.agent_id,
        "workspace_id": args.workspace_id,
        "adapter": args.adapter,
        "service_path": str(service_path),
        "service_file": {
            "exists": exists,
            "command_has_worker": command_has_worker,
            "adapter_present": adapter_present,
            "use_session_present": use_session_present,
            "confirm_gate_ok": confirm_gate_ok,
            "placeholder_present": placeholder_present,
            "token_like_detected": token_like_detected,
            "raw_content_omitted": True,
        },
        "service_status": service_status,
        "setup_hints": hints,
        "live_execution_performed": False,
        "token_omitted": True,
    }


def build_service_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only check for an agentops-worker launchd/systemd service file.")
    parser.add_argument("--manager", choices=["launchd", "systemd"], required=True)
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--label", default="")
    parser.add_argument("--service-path", default="")
    parser.add_argument("--api-key-placeholder", default="<paste one-time token here>")
    parser.add_argument("--timeout", type=int, default=5)
    return parser


def run_service_check(argv: list[str]) -> int:
    args = build_service_check_parser().parse_args(argv)
    payload = check_service_installation(args)
    print(json_dumps(payload))
    return 0 if payload.get("ok") else 1


def install_service_file(args) -> dict:
    label = args.label or service_label(args.agent_id)
    service_path = Path(args.service_path).expanduser() if args.service_path else default_service_path(args.manager, args.agent_id, label)
    template = render_service_template_for_args(args)
    token_like_detected = bool(re.search(r"(agtok_|agtsess_|sk-|ntn_)", template))
    exists_before = service_path.exists()
    safe_to_write = not token_like_detected and (not exists_before or bool(args.overwrite))
    wrote = False
    write_error = None
    if args.confirm_install and safe_to_write:
        try:
            service_path.parent.mkdir(parents=True, exist_ok=True)
            service_path.write_text(template, encoding="utf-8")
            service_path.chmod(0o600)
            wrote = True
        except Exception as exc:
            write_error = safe_error(exc)
    check_args = argparse.Namespace(
        manager=args.manager,
        workspace_id=args.workspace_id,
        agent_id=args.agent_id,
        adapter=args.adapter,
        label=label,
        service_path=str(service_path),
        api_key_placeholder=args.api_key_placeholder,
        timeout=args.timeout,
    )
    service_check = check_service_installation(check_args) if service_path.exists() else {
        "ok": False,
        "service_file": {
            "exists": False,
            "raw_content_omitted": True,
            "token_like_detected": token_like_detected,
        },
    }
    setup_hints = []
    if not args.confirm_install:
        setup_hints.append("Dry-run only. Re-run with --confirm-install to write the service file.")
    if exists_before and not args.overwrite:
        setup_hints.append("Service file already exists. Pass --overwrite only after reviewing the current file.")
    if token_like_detected:
        setup_hints.append("Refusing to write a service template containing token-like values.")
    if wrote:
        setup_hints.append("Review the service file locally, configure secrets outside git, then load it manually if desired.")
    if write_error:
        setup_hints.append("Service file write failed; inspect permissions on the target directory.")
    ok = bool((not args.confirm_install and not token_like_detected) or (wrote and service_check.get("ok") is True))
    if args.confirm_install and (exists_before and not args.overwrite):
        ok = False
    if write_error:
        ok = False
    return {
        "ok": ok,
        "provider": "agentops-worker",
        "command": "agentops-worker service-install",
        "manager": args.manager,
        "dry_run": not bool(args.confirm_install),
        "confirmed_install": bool(args.confirm_install),
        "wrote": wrote,
        "overwrite": bool(args.overwrite),
        "exists_before": exists_before,
        "agent_id": args.agent_id,
        "workspace_id": args.workspace_id,
        "adapter": args.adapter,
        "service_path": str(service_path),
        "service_file_mode": "0600" if wrote else None,
        "template_hash": stable_hash(template),
        "template_bytes": len(template.encode("utf-8")),
        "service_check": service_check,
        "load_commands": service_load_commands(args.manager, service_path, label),
        "setup_hints": setup_hints,
        "write_error": write_error,
        "live_execution_performed": False,
        "service_loaded": False,
        "raw_content_omitted": True,
        "token_omitted": True,
    }


def build_service_install_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run or write a safe agentops-worker launchd/systemd service file.")
    parser.add_argument("--manager", choices=["launchd", "systemd"], required=True)
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--session-ttl-sec", type=int, default=900)
    parser.add_argument("--session-refresh-margin-sec", type=float, default=60)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--label", default="")
    parser.add_argument("--working-directory", default=str(DEFAULT_WORKER_CWD))
    parser.add_argument("--runtime-dir", default="")
    parser.add_argument("--log-path", default="")
    parser.add_argument("--api-key-placeholder", default="<paste one-time token here>")
    parser.add_argument("--service-path", default="")
    parser.add_argument("--confirm-install", action="store_true", help="Write the service file. Default is dry-run.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing service file after local review.")
    parser.add_argument("--timeout", type=int, default=5)
    return parser


def run_service_install(argv: list[str]) -> int:
    args = build_service_install_parser().parse_args(argv)
    payload = install_service_file(args)
    print(json_dumps(payload))
    return 0 if payload.get("ok") else 1


def render_service_template(argv: list[str]) -> int:
    args = build_service_template_parser().parse_args(argv)
    sys.stdout.write(render_service_template_for_args(args))
    return 0


def preflight_http_json(url: str, timeout: int = 5) -> tuple[bool, int | None, dict]:
    try:
        req = Request(url, headers={"Accept": "application/json"}, method="GET")
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"raw_summary": redact_text(raw, 200)}
            return True, res.status, payload
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {"error": redact_text(str(exc), 200)}
        return False, exc.code, payload
    except Exception as exc:
        return False, None, safe_error(exc)


def check_gateway_preflight(args) -> dict:
    client = AgentOpsClient(args.base_url, args.workspace_id, args.agent_id, args.api_key)
    try:
        status = client.get("/api/agent-gateway/status")
        return {
            "ok": True,
            "mode": ((status.get("auth") or {}).get("mode") or "local"),
            "agent_id": (status.get("auth") or {}).get("agent_id") or args.agent_id,
            "workspace_id": (status.get("auth") or {}).get("workspace_id") or args.workspace_id,
            "scope_count": len((status.get("auth") or {}).get("scopes") or []),
            "token_omitted": True,
        }
    except Exception as exc:
        return {"ok": False, **safe_error(exc), "token_omitted": True}


def check_adapter_preflight(args) -> dict:
    if args.adapter == "mock":
        return {
            "ok": True,
            "adapter": "mock",
            "target_resource": "local://agentops/mock-worker",
            "live_execution_performed": False,
        }
    if args.adapter == "hermes":
        gateway_url = args.hermes_gateway_url.rstrip("/")
        health_ok, health_status, health_payload = preflight_http_json(f"{gateway_url}/health", timeout=args.timeout)
        models_ok, models_status, models_payload = preflight_http_json(f"{gateway_url}/v1/models", timeout=args.timeout)
        return {
            "ok": bool(health_ok or models_ok),
            "adapter": "hermes",
            "target_resource": gateway_url,
            "health": {"ok": health_ok, "status": health_status, "summary": redact_text(health_payload, 200)},
            "models": {"ok": models_ok, "status": models_status, "summary": redact_text(models_payload, 200)},
            "live_execution_performed": False,
        }
    binary = Path(args.openclaw_bin).expanduser()
    exists = binary.exists()
    executable = os.access(binary, os.X_OK) if exists else False
    version_summary = ""
    version_ok = False
    if exists and executable:
        try:
            proc = subprocess.run(
                [str(binary), "--version"],
                cwd=DEFAULT_WORKER_CWD,
                capture_output=True,
                text=True,
                timeout=min(max(int(args.timeout or 5), 1), 20),
                check=False,
            )
            version_ok = proc.returncode == 0
            version_summary = redact_text(proc.stdout or proc.stderr or f"exit={proc.returncode}", 200)
        except Exception as exc:
            version_summary = redact_text(str(exc), 200)
    return {
        "ok": bool(exists and executable),
        "adapter": "openclaw",
        "binary_path": str(binary),
        "binary_exists": exists,
        "binary_executable": executable,
        "version_ok": version_ok,
        "version_summary": version_summary,
        "live_execution_performed": False,
    }


def build_preflight_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a read-only AgentOps worker adapter preflight.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--api-key", default=os.environ.get("AGENTOPS_API_KEY", ""))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--hermes-gateway-url", default=os.environ.get("HERMES_GATEWAY_URL", DEFAULT_HERMES_GATEWAY_URL))
    parser.add_argument("--openclaw-bin", default=os.environ.get("OPENCLAW_BIN", DEFAULT_OPENCLAW_BIN))
    parser.add_argument("--timeout", type=int, default=5)
    return parser


def run_preflight(argv: list[str]) -> int:
    args = build_preflight_parser().parse_args(argv)
    gateway = check_gateway_preflight(args)
    adapter = check_adapter_preflight(args)
    ok = bool(gateway.get("ok") and adapter.get("ok"))
    payload = {
        "ok": ok,
        "provider": "agentops-worker",
        "agent_id": args.agent_id,
        "workspace_id": args.workspace_id,
        "adapter": args.adapter,
        "gateway": gateway,
        "adapter_preflight": adapter,
        "live_execution_performed": False,
        "raw_prompt_response_omitted": True,
        "token_omitted": True,
    }
    print(json_dumps(payload))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["service-template"]:
        return render_service_template(argv[1:])
    if argv[:1] == ["service-install"]:
        return run_service_install(argv[1:])
    if argv[:1] == ["service-check"]:
        return run_service_check(argv[1:])
    if argv[:1] == ["preflight"]:
        return run_preflight(argv[1:])
    args = build_parser().parse_args(argv)
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
