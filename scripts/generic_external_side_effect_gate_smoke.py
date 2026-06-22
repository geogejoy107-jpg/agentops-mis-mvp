#!/usr/bin/env python3
"""Verify generic external side effects cannot bypass prepared actions by using low risk."""

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
    parser = argparse.ArgumentParser(description="Smoke-test generic external side-effect gating.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    stamp = time.strftime("%Y%m%d%H%M%S")
    agent_id = "agt_research"
    task_id = f"tsk_generic_external_gate_{stamp}"
    failures: list[str] = []
    outputs: list[str] = []

    status, task_payload = http_json(args.base_url, "/api/tasks", {
        "task_id": task_id,
        "workspace_id": "local-demo",
        "title": f"Generic external side-effect gate smoke {stamp}",
        "description": "Verify generic external writes cannot be mislabeled as low risk.",
        "owner_agent_id": agent_id,
        "risk_level": "medium",
        "acceptance_criteria": "External publish/upload/write intent must require a prepared action.",
    })
    outputs.append(json.dumps(task_payload, ensure_ascii=False))
    require(status in {200, 201}, f"task create failed: {status} {task_payload}", failures)

    status, run_payload = http_json(args.base_url, "/api/mock-runs/start", {"task_id": task_id, "agent_id": agent_id})
    outputs.append(json.dumps(run_payload, ensure_ascii=False))
    require(status == 201, f"mock run start failed: {status} {run_payload}", failures)
    run_id = (run_payload.get("run") or {}).get("run_id") or run_payload.get("run_id")
    require(bool(run_id), f"run_id missing: {run_payload}", failures)

    status, local_runtime_evidence = http_json(args.base_url, "/api/agent-gateway/tool-calls", {
        "workspace_id": "local-demo",
        "run_id": run_id,
        "agent_id": agent_id,
        "tool_name": "agent_worker.hermes",
        "tool_category": "custom",
        "risk_level": "medium",
        "status": "completed",
        "target_resource": "http://127.0.0.1:8642/v1/chat/completions",
        "args": {
            "adapter": "hermes",
            "observation_level": "ledger_summary_only",
            "requires_prepared_action_for_external_write": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
        },
        "result_summary": "Local Hermes worker execution evidence should not be treated as an external write.",
    })
    outputs.append(json.dumps(local_runtime_evidence, ensure_ascii=False))
    require(status in {200, 201}, f"loopback runtime evidence should not require prepared action: {status} {local_runtime_evidence}", failures)
    require((local_runtime_evidence.get("tool_call") or {}).get("status") == "completed", f"loopback runtime evidence should be completed: {local_runtime_evidence}", failures)

    generic_external = {
        "workspace_id": "local-demo",
        "run_id": run_id,
        "agent_id": agent_id,
        "tool_name": "customer.portal.upload",
        "tool_category": "custom",
        "risk_level": "low",
        "status": "completed",
        "target_resource": "https://customer.example.test/api/upload",
        "side_effect_id": f"external-upload-{stamp}",
        "args": {
            "operation": "upload",
            "target": "https://customer.example.test/api/upload",
            "raw_payload_stored": False,
        },
        "result_summary": "This low-risk external upload label should be rejected.",
    }
    status, blocked = http_json(args.base_url, "/api/agent-gateway/tool-calls", generic_external)
    outputs.append(json.dumps(blocked, ensure_ascii=False))
    require(status == 428, f"generic external side effect should require prepared action: {status} {blocked}", failures)
    require(blocked.get("error") == "high_risk_prepared_action_required", f"wrong generic rejection: {blocked}", failures)
    require(blocked.get("external_side_effect_intent") is True, f"external intent not detected: {blocked}", failures)
    require(blocked.get("risk_level") == "high", f"external write risk should be elevated to high: {blocked}", failures)
    require("prepare_action=true" in (blocked.get("message") or "") or "prepare_action=true" in (blocked.get("next_action") or ""), f"missing prepared-action guidance: {blocked}", failures)

    status, prepared = http_json(args.base_url, "/api/agent-gateway/tool-calls", {
        **generic_external,
        "tool_call_id": f"tc_generic_external_gate_{stamp}",
        "status": "waiting_approval",
        "side_effect_id": None,
        "result_summary": "Prepared external upload plan only; provider upload has not happened.",
        "prepare_action": True,
        "checkpoint": {
            "run_id": run_id,
            "checkpoint": "before_generic_external_upload",
            "raw_payload_stored": False,
        },
        "idempotency_key": f"generic-external-gate-{stamp}",
        "approval_reason": "Generic external upload/write requires exact prepared-action approval before provider execution.",
    })
    outputs.append(json.dumps(prepared, ensure_ascii=False))
    require(status in {200, 201}, f"prepared generic external tool call failed: {status} {prepared}", failures)
    tool = prepared.get("tool_call") or {}
    wall = prepared.get("approval_wall") or {}
    prepared_action = wall.get("prepared_action") or {}
    approval = wall.get("approval") or {}
    require(tool.get("risk_level") == "high", f"prepared tool risk should be elevated to high: {prepared}", failures)
    require(tool.get("status") == "waiting_approval", f"prepared tool should wait approval: {prepared}", failures)
    require(prepared_action.get("status") == "prepared", f"prepared action missing: {prepared}", failures)
    require(bool(prepared_action.get("action_hash")), f"prepared action hash missing: {prepared}", failures)
    require(approval.get("decision") == "pending", f"approval should be pending: {prepared}", failures)

    status, run_detail = http_json(args.base_url, f"/api/runs/{run_id}", method="GET")
    outputs.append(json.dumps(run_detail, ensure_ascii=False))
    require(status == 200, f"run detail failed: {status} {run_detail}", failures)
    run = run_detail.get("run") or {}
    require(run.get("approval_required") in {1, True}, f"run should require approval after generic external gate: {run}", failures)
    require(run.get("status") == "waiting_approval", f"run should wait for approval: {run}", failures)

    require(not contains_secret("\n".join(outputs)), "generic external gate smoke output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "generic_external_side_effect_gate",
        "run_id": run_id,
        "blocked_error": blocked.get("error"),
        "effective_risk": blocked.get("risk_level"),
        "prepared_action_id": prepared_action.get("action_id"),
        "approval_id": approval.get("approval_id"),
        "secret_leaked": contains_secret("\n".join(outputs)),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
