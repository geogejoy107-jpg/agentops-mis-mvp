#!/usr/bin/env python3
"""Verify high-risk Agent Gateway tool calls cannot bypass the Approval Wall."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


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


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test high-risk tool-call prepared-action gate.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    stamp = time.strftime("%Y%m%d%H%M%S")
    agent_id = "agt_research"
    task_id = f"tsk_high_risk_gate_{stamp}"
    failures: list[str] = []
    outputs: list[str] = []

    status, task_payload = http_json(args.base_url, "/api/tasks", {
        "task_id": task_id,
        "workspace_id": "local-demo",
        "title": f"High-risk tool-call gate smoke {stamp}",
        "description": "Verify high-risk side effects require a prepared action.",
        "owner_agent_id": agent_id,
        "risk_level": "high",
        "acceptance_criteria": "Direct completed high-risk tool calls must be rejected; prepared actions must be accepted.",
    })
    outputs.append(json.dumps(task_payload, ensure_ascii=False))
    require(status in {200, 201}, f"task create failed: {status} {task_payload}", failures)

    status, run_payload = http_json(args.base_url, "/api/mock-runs/start", {"task_id": task_id, "agent_id": agent_id})
    outputs.append(json.dumps(run_payload, ensure_ascii=False))
    require(status == 201, f"mock run start failed: {status} {run_payload}", failures)
    run_id = (run_payload.get("run") or {}).get("run_id") or run_payload.get("run_id")
    require(bool(run_id), f"run_id missing: {run_payload}", failures)

    direct_payload = {
        "workspace_id": "local-demo",
        "run_id": run_id,
        "agent_id": agent_id,
        "tool_name": "openai.file_search.upload",
        "tool_category": "custom",
        "risk_level": "critical",
        "status": "completed",
        "target_resource": "openai://file-search/vector-store",
        "side_effect_id": f"mock-upload-{stamp}",
        "args": {"raw_document_storage": "not_in_mis", "summary_only": True},
        "result_summary": "This direct high-risk side effect should be rejected.",
    }
    status, blocked = http_json(args.base_url, "/api/agent-gateway/tool-calls", direct_payload)
    outputs.append(json.dumps(blocked, ensure_ascii=False))
    require(status == 428, f"direct high-risk completed tool call should require prepared action: {status} {blocked}", failures)
    require(blocked.get("error") == "high_risk_prepared_action_required", f"wrong direct rejection: {blocked}", failures)
    require("prepare_action=true" in (blocked.get("message") or "") or "prepare_action=true" in (blocked.get("next_action") or ""), f"missing prepared-action guidance: {blocked}", failures)

    status, prepared = http_json(args.base_url, "/api/agent-gateway/tool-calls", {
        **direct_payload,
        "tool_call_id": f"tc_high_risk_gate_{stamp}",
        "status": "waiting_approval",
        "side_effect_id": None,
        "result_summary": "Prepared external upload plan only; no file was uploaded.",
        "prepare_action": True,
        "action_type": "openai.file_search.upload",
        "checkpoint": {
            "run_id": run_id,
            "checkpoint": "after_toolcall_record_before_external_upload",
        },
        "idempotency_key": f"high-risk-gate-{stamp}",
        "approval_reason": "High-risk external knowledge upload requires exact prepared-action approval and resume.",
    })
    outputs.append(json.dumps(prepared, ensure_ascii=False))
    require(status in {200, 201}, f"prepared high-risk tool call failed: {status} {prepared}", failures)
    wall = prepared.get("approval_wall") or {}
    prepared_action = wall.get("prepared_action") or {}
    approval = wall.get("approval") or {}
    require(prepared_action.get("status") == "prepared", f"prepared action missing/prepared status wrong: {prepared}", failures)
    require(bool(prepared_action.get("action_hash")), f"prepared action missing action_hash: {prepared}", failures)
    require(approval.get("decision") == "pending", f"approval should be pending: {prepared}", failures)
    require("prepared-action resume" in (prepared.get("next_action") or ""), f"missing resume next action: {prepared}", failures)

    status, run_detail = http_json(args.base_url, f"/api/runs/{run_id}", method="GET")
    outputs.append(json.dumps(run_detail, ensure_ascii=False))
    require(status == 200, f"run detail failed: {status} {run_detail}", failures)
    run = run_detail.get("run") or {}
    require(run.get("approval_required") in {1, True}, f"run should require approval after prepared high-risk gate: {run}", failures)
    require(run.get("status") == "waiting_approval", f"run should wait for approval: {run}", failures)

    require(not contains_secret("\n".join(outputs)), "high-risk gate smoke output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "high_risk_toolcall_prepared_action_gate",
        "run_id": run_id,
        "blocked_error": blocked.get("error"),
        "prepared_action_id": prepared_action.get("action_id"),
        "approval_id": approval.get("approval_id"),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
