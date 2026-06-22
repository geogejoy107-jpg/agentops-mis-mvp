#!/usr/bin/env python3
"""Verify prepared action -> action hash -> approval -> exact-once resume."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_MARKERS = ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_", "AGENTOPS_API_KEY="]


def http_json(base_url: str, path: str, payload: dict | None = None, method: str | None = None) -> tuple[int, dict]:
    raw = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=raw,
        headers={"Content-Type": "application/json"},
        method=method or ("POST" if payload is not None else "GET"),
    )
    try:
        with urlopen(req, timeout=60) as res:
            body = res.read().decode("utf-8")
            return res.status, json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"raw": body}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def run_cli(base_url: str, args: list[str]) -> tuple[int, dict, str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    proc = subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout) if proc.stdout else {}
    except json.JSONDecodeError:
        payload = {}
    return proc.returncode, payload, proc.stdout + proc.stderr


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def contains_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the prepared-action approval wall.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    stamp = time.strftime("%Y%m%d%H%M%S")
    agent_id = "agt_research"
    failures: list[str] = []
    outputs: list[str] = []

    task_id = f"tsk_prepared_action_{stamp}"
    status, task_payload = http_json(args.base_url, "/api/tasks", {
        "task_id": task_id,
        "workspace_id": "local-demo",
        "title": f"Prepared action approval wall smoke {stamp}",
        "description": "Verify exact prepared-action resume semantics.",
        "owner_agent_id": agent_id,
        "risk_level": "high",
        "acceptance_criteria": "Approve a prepared action, resume it once, and reject replay.",
    })
    outputs.append(json.dumps(task_payload, ensure_ascii=False))
    require(status in {200, 201}, f"task create failed: {status} {task_payload}", failures)

    status, run_payload = http_json(args.base_url, "/api/mock-runs/start", {"task_id": task_id, "agent_id": agent_id})
    outputs.append(json.dumps(run_payload, ensure_ascii=False))
    require(status == 201, f"mock run start failed: {status} {run_payload}", failures)
    run_id = run_payload.get("run", {}).get("run_id") or run_payload.get("run_id")
    require(bool(run_id), f"run_id missing: {run_payload}", failures)

    blocked_status, blocked_payload = http_json(args.base_url, "/api/agent-gateway/tool-calls", {
        "workspace_id": "local-demo",
        "run_id": run_id,
        "agent_id": agent_id,
        "tool_name": "external.publish",
        "tool_category": "custom",
        "risk_level": "critical",
        "status": "waiting_approval",
        "target_resource": "mock://customer/delivery",
        "args": {"operation": "publish", "target": "mock://customer/delivery", "raw_payload_stored": False},
        "result_summary": "This high-risk publish should be blocked without prepare_action.",
    })
    outputs.append(json.dumps(blocked_payload, ensure_ascii=False))
    require(blocked_status == 428, f"unprepared high-risk external tool should require prepared action: {blocked_status} {blocked_payload}", failures)
    require(blocked_payload.get("error") == "high_risk_prepared_action_required", f"wrong unprepared tool error: {blocked_payload}", failures)

    returncode, tool_payload, raw = run_cli(args.base_url, [
        "toolcall", "record",
        "--run-id", run_id,
        "--agent-id", agent_id,
        "--tool", "external.publish",
        "--category", "custom",
        "--risk", "critical",
        "--status", "waiting_approval",
        "--target", "mock://customer/delivery",
        "--args-json", '{"operation":"publish","target":"mock://customer/delivery","raw_payload_stored":false}',
        "--summary", "Prepared publish action is waiting for human approval.",
        "--prepare-action",
        "--checkpoint-json", f'{{"run_id":"{run_id}","checkpoint":"before_external_publish"}}',
        "--idempotency-key", f"prepared-action-smoke-{stamp}",
        "--approval-reason", "Smoke prepared action requires exact approval before external publish.",
    ])
    outputs.append(raw)
    require(returncode == 0, f"toolcall prepared-action CLI failed: {raw}", failures)
    tool_call_id = (tool_payload.get("tool_call") or {}).get("tool_call_id")
    require(bool(tool_call_id), f"tool_call_id missing: {tool_payload}", failures)
    prepare_payload = tool_payload.get("approval_wall") or {}
    prepared_action = prepare_payload.get("prepared_action") or {}
    approval = prepare_payload.get("approval") or {}
    action_id = prepared_action.get("action_id")
    approval_id = approval.get("approval_id")
    action_hash = prepared_action.get("action_hash")
    require(bool(action_id and approval_id and action_hash), f"prepared action fields missing: {prepare_payload}", failures)
    require(prepared_action.get("status") == "prepared", f"prepared action not prepared: {prepared_action}", failures)
    require(approval.get("decision") == "pending", f"approval not pending: {approval}", failures)
    require("approval prepared-action resume" in (tool_payload.get("next_action") or ""), f"toolcall did not return prepared-action next action: {tool_payload}", failures)

    returncode, inspect_payload, raw = run_cli(args.base_url, ["approval", "inspect", "--approval-id", approval_id])
    outputs.append(raw)
    require(returncode == 0, f"approval inspect failed: {raw}", failures)
    require((inspect_payload.get("prepared_action_gate") or {}).get("hash_match") is True, f"inspect hash mismatch: {inspect_payload}", failures)

    returncode, approve_payload, raw = run_cli(args.base_url, ["approval", "approve", "--approval-id", approval_id])
    outputs.append(raw)
    require(returncode == 0, f"approval approve failed: {raw}", failures)
    require(approve_payload.get("resume_required") is True, f"approve should require resume: {approve_payload}", failures)
    require((approve_payload.get("prepared_action") or {}).get("status") == "approved", f"prepared action not approved: {approve_payload}", failures)

    side_effect_id = f"mock-side-effect-{stamp}"
    returncode, resume_payload, raw = run_cli(args.base_url, [
        "approval", "prepared-action", "resume",
        "--action-id", action_id,
        "--agent-id", agent_id,
        "--provider-side-effect-id", side_effect_id,
        "--result-summary", "Mock provider publish side effect recorded after exact approval.",
    ])
    outputs.append(raw)
    require(returncode == 0, f"prepared action resume failed: {raw}", failures)
    resumed = resume_payload.get("prepared_action") or {}
    require(resume_payload.get("execute_once") is True, f"execute_once missing: {resume_payload}", failures)
    require(resumed.get("status") == "consumed", f"prepared action not consumed: {resume_payload}", failures)
    require(resumed.get("provider_side_effect_id") == side_effect_id, f"side effect id mismatch: {resume_payload}", failures)
    require((resume_payload.get("hash_verification") or {}).get("match") is True, f"resume hash verification missing: {resume_payload}", failures)

    replay_status, replay_payload = http_json(args.base_url, f"/api/agent-gateway/prepared-actions/{action_id}/resume", {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "provider_side_effect_id": f"mock-side-effect-replay-{stamp}",
    })
    outputs.append(json.dumps(replay_payload, ensure_ascii=False))
    require(replay_status == 409, f"replay should fail with 409: {replay_status} {replay_payload}", failures)
    require(replay_payload.get("error") == "prepared_action_already_consumed", f"replay error mismatch: {replay_payload}", failures)

    status, run_detail = http_json(args.base_url, f"/api/runs/{run_id}")
    outputs.append(json.dumps(run_detail, ensure_ascii=False))
    require(status == 200, f"run detail failed: {status} {run_detail}", failures)
    run_after = run_detail.get("run") or {}
    require(run_after.get("approval_required") in {0, False}, f"run approval_required should be cleared after resume: {run_after}", failures)
    require(run_after.get("status") != "waiting_approval", f"run should leave waiting_approval after resume: {run_after}", failures)

    status, prepared_get = http_json(args.base_url, f"/api/agent-gateway/prepared-actions/{action_id}")
    outputs.append(json.dumps(prepared_get, ensure_ascii=False))
    require(status == 200, f"prepared action get failed: {status} {prepared_get}", failures)
    require((prepared_get.get("hash_verification") or {}).get("match") is True, f"final hash verification mismatch: {prepared_get}", failures)

    leaked = contains_secret("\n".join(outputs))
    require(not leaked, "prepared action approval wall output leaked token-like material", failures)
    result = {
        "ok": not failures,
        "failures": failures,
        "task_id": task_id,
        "run_id": run_id,
        "tool_call_id": tool_call_id,
        "approval_id": approval_id,
        "prepared_action_id": action_id,
        "action_hash_prefix": str(action_hash or "")[:16],
        "side_effect_id": side_effect_id,
        "replay_status": replay_status,
        "secret_leaked": leaked,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
