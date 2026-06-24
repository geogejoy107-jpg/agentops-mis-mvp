#!/usr/bin/env python3
"""Verify worker adapter retry and non-retry safety behavior."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def create_task(base_url: str, agent_id: str, task_id: str, title: str) -> None:
    status, payload = http_json("POST", base_url, "/api/tasks", {
        "task_id": task_id,
        "workspace_id": "local-demo",
        "title": title,
        "description": "Verify adapter retry metadata enters the MIS ledger without raw prompt or token leakage.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "medium",
        "risk_level": "low",
        "acceptance_criteria": "Worker must record attempt_count, max_attempts, retry_history, and final status.",
    })
    require(status == 201, f"task create failed: {status} {payload}")


def run_worker(base_url: str, agent_id: str, token: str, args: list[str], expected_returncode: int) -> dict:
    env = os.environ.copy()
    env.update({
        "AGENTOPS_BASE_URL": base_url,
        "AGENTOPS_WORKSPACE_ID": "local-demo",
        "AGENTOPS_AGENT_ID": agent_id,
        "AGENTOPS_API_KEY": token,
    })
    cmd = [sys.executable, "scripts/agent_worker.py", *args]
    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180, check=False)
    require(proc.returncode == expected_returncode, f"worker returncode {proc.returncode}, expected {expected_returncode}: {proc.stderr or proc.stdout}")
    require(token not in proc.stdout and token not in proc.stderr, "worker output leaked raw token")
    try:
        return json.loads(proc.stdout or "{}")
    except Exception as exc:
        raise AssertionError(f"worker output was not JSON: {proc.stdout}") from exc


def tool_args(tool_call: dict) -> dict:
    raw = tool_call.get("normalized_args_json") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def run_detail(base_url: str, run_id: str) -> dict:
    status, detail = http_json("GET", base_url, f"/api/runs/{run_id}")
    require(status == 200, f"run detail failed: {status} {detail}")
    return detail


def verify_worker_runtime_event(detail: dict, adapter: str, expected_status: str) -> str:
    runtime_events = detail.get("runtime_events") or []
    matched = next(
        (
            item
            for item in runtime_events
            if item.get("event_type") == "agent_worker.adapter_execution_summary"
            and item.get("status") == expected_status
            and item.get("prompt_hash")
            and item.get("raw_payload_hash")
        ),
        None,
    )
    require(matched is not None, f"{adapter} missing worker runtime summary event: {runtime_events}")
    require((matched.get("input_summary") or "").find(f"adapter={adapter}") >= 0, f"{adapter} runtime event input summary mismatch: {matched}")
    serialized = json.dumps(matched, ensure_ascii=False)
    require("sk-" not in serialized and "raw prompt" not in serialized.lower(), f"{adapter} runtime event leaked unsafe content: {matched}")
    return matched["runtime_event_id"]


def verify_operator_runtime_summary(base_url: str, run_id: str, runtime_event_id: str, adapter: str) -> None:
    status, report = http_json("GET", base_url, f"/api/operator/evidence-report?run_id={run_id}&limit=5")
    require(status == 200, f"{adapter} operator evidence report failed: {status} {report}")
    item = next((entry for entry in report.get("runs") or [] if entry.get("run_id") == run_id), None)
    require(item is not None, f"{adapter} operator report missing run: {report}")
    runtime_summary = item.get("worker_runtime_summary") or {}
    require(runtime_summary.get("status") == "ready", f"{adapter} operator runtime summary not ready: {runtime_summary}")
    require(runtime_event_id in (runtime_summary.get("event_ids") or []), f"{adapter} operator runtime event id missing: {runtime_summary}")
    require(runtime_summary.get("raw_prompt_omitted") is True, f"{adapter} operator runtime summary missing raw prompt omission: {runtime_summary}")
    checks = {check.get("id"): check for check in item.get("checks") or []}
    require((checks.get("worker_runtime_summary") or {}).get("ok") is True, f"{adapter} worker runtime summary check missing: {checks}")
    summary = report.get("summary") or {}
    require(int(summary.get("worker_runtime_summary_ready") or 0) >= 1, f"{adapter} report summary missing runtime summary count: {summary}")
    require(int(summary.get("worker_runtime_summary_missing") or 0) == 0, f"{adapter} report summary should not flag missing runtime summary: {summary}")


def verify_retry_success(base_url: str, worker_result: dict) -> dict:
    result = (worker_result.get("results") or [{}])[0]
    run_id = result.get("run_id")
    require(run_id and result.get("ok") is True, f"retry success worker result invalid: {worker_result}")
    require(result.get("attempt_count") == 2, f"worker output did not report two attempts: {worker_result}")
    require(result.get("plan_id"), f"retry success missing agent plan: {worker_result}")
    require(result.get("plan_evidence_manifest_id"), f"retry success missing plan evidence manifest: {worker_result}")
    require(result.get("plan_evidence_pass") is True, f"retry success plan evidence did not pass: {worker_result}")
    detail = run_detail(base_url, run_id)
    run = detail.get("run") or {}
    tool_calls = detail.get("tool_calls") or []
    evaluations = detail.get("evaluations") or []
    require(run.get("status") == "completed", f"retry success run not completed: {run}")
    runtime_event_id = verify_worker_runtime_event(detail, "mock", "completed")
    verify_operator_runtime_summary(base_url, run_id, runtime_event_id, "mock")
    tool = next((item for item in tool_calls if item.get("tool_name") == "agent_worker.mock"), {})
    args = tool_args(tool)
    require(tool.get("status") == "completed", f"retry success tool call not completed: {tool_calls}")
    require(args.get("attempt_count") == 2 and args.get("max_attempts") == 2, f"retry args missing attempt metadata: {args}")
    require(args.get("worker_runtime_event_id") == runtime_event_id, f"retry args missing runtime event id: {args}")
    require(args.get("worker_runtime_event_summary_recorded") is True, f"retry args missing runtime summary flag: {args}")
    history = args.get("retry_history") or []
    require(len(history) == 2 and history[0].get("retryable") is True and history[1].get("ok") is True, f"retry history invalid: {history}")
    require(any(((ev.get("rubric_json") or ev.get("rubric") or "")).find("attempt_count") >= 0 for ev in evaluations), f"evaluation rubric missing attempt metadata: {evaluations}")
    return {
        "run_id": run_id,
        "attempt_count": args.get("attempt_count"),
        "worker_runtime_event_id": runtime_event_id,
        "retry_history": history,
        "plan_id": result.get("plan_id"),
        "plan_evidence_manifest_id": result.get("plan_evidence_manifest_id"),
    }


def verify_non_retry_failure(base_url: str, worker_result: dict) -> dict:
    result = (worker_result.get("results") or [{}])[0]
    run_id = result.get("run_id")
    require(run_id and result.get("ok") is False, f"non-retry worker result invalid: {worker_result}")
    require(result.get("attempt_count") == 1 and result.get("error_type") == "ConfirmRunRequired", f"confirm gate should not retry: {worker_result}")
    require(result.get("plan_id"), f"non-retry failure missing agent plan: {worker_result}")
    require(result.get("plan_evidence_manifest_id"), f"non-retry failure missing plan evidence manifest: {worker_result}")
    require(result.get("plan_evidence_pass") is not True, f"non-retry failure should not have passing plan evidence: {worker_result}")
    detail = run_detail(base_url, run_id)
    run = detail.get("run") or {}
    tool_calls = detail.get("tool_calls") or []
    require(run.get("status") == "failed", f"non-retry run should fail: {run}")
    runtime_event_id = verify_worker_runtime_event(detail, "hermes", "failed")
    verify_operator_runtime_summary(base_url, run_id, runtime_event_id, "hermes")
    tool = next((item for item in tool_calls if item.get("tool_name") == "agent_worker.hermes"), {})
    args = tool_args(tool)
    require(tool.get("status") == "failed", f"non-retry tool call should fail: {tool_calls}")
    require(tool.get("risk_level") == "medium", f"Hermes runtime tool call should use capability risk floor, not low: {tool}")
    require(args.get("attempt_count") == 1 and args.get("max_attempts") == 3, f"non-retry args missing attempt metadata: {args}")
    require(args.get("observation_level") == "ledger_summary_only", f"Hermes observation level missing from tool args: {args}")
    require(args.get("risk_floor") == "medium" and args.get("effective_risk_level") == "medium", f"Hermes risk floor missing from tool args: {args}")
    require(args.get("commercial_readiness") == "restricted_until_runtime_tool_events", f"Hermes commercial restriction missing from tool args: {args}")
    require(args.get("requires_prepared_action_for_external_write") is True, f"Hermes prepared-action requirement missing from tool args: {args}")
    require(args.get("worker_runtime_event_id") == runtime_event_id, f"Hermes tool args missing runtime event id: {args}")
    require(args.get("worker_runtime_event_summary_recorded") is True, f"Hermes runtime summary flag missing: {args}")
    require(args.get("runtime_internal_tools_remain_opaque") is True, f"Hermes opacity proof missing: {args}")
    history = args.get("retry_history") or []
    require(len(history) == 1 and history[0].get("retryable") is False, f"non-retry history invalid: {history}")
    return {
        "run_id": run_id,
        "attempt_count": args.get("attempt_count"),
        "worker_runtime_event_id": runtime_event_id,
        "error_type": result.get("error_type"),
        "plan_id": result.get("plan_id"),
        "plan_evidence_manifest_id": result.get("plan_evidence_manifest_id"),
        "plan_evidence_pass": result.get("plan_evidence_pass"),
    }


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_adapter_retry_{stamp}"
    token_id = None
    try:
        status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
            "agent_id": agent_id,
            "name": "Worker Adapter Retry Smoke",
            "runtime_type": "mock",
            "workspace_id": "local-demo",
            "scopes": [
                "agents:write",
                "agents:heartbeat",
                "knowledge:read",
                "knowledge:write",
                "agent_plans:read",
                "agent_plans:write",
                "plan_evidence:read",
                "plan_evidence:write",
                "tasks:read",
                "tasks:claim",
                "runs:write",
                "runtime_events:write",
                "toolcalls:write",
                "artifacts:write",
                "memories:propose",
                "evaluations:submit",
                "audit:write",
            ],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        })
        require(status == 201, f"enrollment create failed: {status} {created}")
        token = created.get("token")
        token_id = created.get("token_id")
        require(token and token_id, f"created enrollment missing one-time token: {created}")

        retry_task_id = f"tsk_adapter_retry_{stamp}_success"
        create_task(base_url, agent_id, retry_task_id, "adapter retry transient success smoke")
        retry_worker = run_worker(base_url, agent_id, token, [
            "--once",
            "--no-enforce-intake",
            "--adapter",
            "mock",
            "--task-id",
            retry_task_id,
            "--adapter-max-attempts",
            "2",
            "--adapter-retry-delay-sec",
            "0",
            "--mock-failures-before-success",
            "1",
        ], 0)
        retry_result = verify_retry_success(base_url, retry_worker)

        gate_task_id = f"tsk_adapter_retry_{stamp}_confirm_gate"
        create_task(base_url, agent_id, gate_task_id, "adapter retry confirm gate smoke")
        gate_worker = run_worker(base_url, agent_id, token, [
            "--once",
            "--no-enforce-intake",
            "--adapter",
            "hermes",
            "--task-id",
            gate_task_id,
            "--adapter-max-attempts",
            "3",
            "--adapter-retry-delay-sec",
            "0",
        ], 1)
        gate_result = verify_non_retry_failure(base_url, gate_worker)

        return {
            "agent_id": agent_id,
            "retry_task_id": retry_task_id,
            "retry_run_id": retry_result["run_id"],
            "retry_attempt_count": retry_result["attempt_count"],
            "retry_plan_id": retry_result["plan_id"],
            "retry_plan_evidence_manifest_id": retry_result["plan_evidence_manifest_id"],
            "retry_worker_runtime_event_id": retry_result["worker_runtime_event_id"],
            "confirm_gate_task_id": gate_task_id,
            "confirm_gate_run_id": gate_result["run_id"],
            "confirm_gate_attempt_count": gate_result["attempt_count"],
            "confirm_gate_error_type": gate_result["error_type"],
            "confirm_gate_plan_id": gate_result["plan_id"],
            "confirm_gate_plan_evidence_manifest_id": gate_result["plan_evidence_manifest_id"],
            "confirm_gate_plan_evidence_pass": gate_result["plan_evidence_pass"],
            "confirm_gate_worker_runtime_event_id": gate_result["worker_runtime_event_id"],
            "token_omitted": True,
        }
    finally:
        if token_id:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify adapter retry behavior.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args(argv)
    result = {"ok": True, "base_url": args.base_url, "smoke": smoke(args.base_url, now_stamp())}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
