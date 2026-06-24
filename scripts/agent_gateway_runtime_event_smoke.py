#!/usr/bin/env python3
"""Verify scoped Agent Gateway runtime-event ingestion and redaction."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def token_like_leaked(text: str, raw_token: str, raw_secret: str) -> bool:
    scrubbed = text.replace(raw_token, "<raw-token>")
    bearer_value = re.search(r"Bearer\s+(?!\[REDACTED\])[\w._~+/=-]+", scrubbed, re.IGNORECASE)
    return raw_secret in scrubbed or bool(bearer_value) or any(marker in scrubbed for marker in ["agtok_", "agtsess_", "ntn_"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Agent Gateway runtime event ingestion.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    stamp = os.environ.get("AGENTOPS_TEST_STAMP") or str(os.getpid())
    workspace_id = f"ws_runtime_event_{stamp}"
    agent_id = f"agt_runtime_event_{stamp}"
    raw_secret = "sk-runtime-event-raw-secret-1234567890"
    failures: list[str] = []

    status, enrollment = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/create", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "name": "Runtime Event Smoke Agent",
        "runtime_type": "hermes",
        "scopes": [
            "agents:heartbeat",
            "agent_plans:read",
            "agent_plans:write",
            "tasks:create",
            "tasks:read",
            "tasks:claim",
            "runs:write",
            "runtime_events:write",
            "audit:write",
        ],
    })
    require(status == 201 and enrollment.get("token"), f"enrollment failed: {status} {enrollment}", failures)
    token = enrollment.get("token") or ""

    status, task = http_json("POST", args.base_url, "/api/agent-gateway/tasks", {
        "workspace_id": workspace_id,
        "title": "Record scoped runtime internal event",
        "description": "Runtime can emit a summary/hash-only internal tool event into MIS.",
        "acceptance_criteria": "Run detail shows runtime_events without raw payload leakage.",
        "risk_level": "medium",
    }, token=token)
    task_id = task.get("task_id")
    require(status == 201 and task_id, f"task create failed: {status} {task}", failures)

    status, _claim = http_json("POST", args.base_url, f"/api/agent-gateway/tasks/{task_id}/claim", {
        "workspace_id": workspace_id,
        "runtime_type": "hermes",
    }, token=token)
    require(status == 200, f"claim failed: {status} {_claim}", failures)

    plan_body = {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "task_understanding": "Record a redacted runtime event emitted by an external runtime.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["runtime-event-ingestion-smoke"],
        "risk_level": "medium",
        "execution_steps": ["READ", "PLAN", "EXECUTE", "VERIFY", "RECORD"],
        "verification_plan": "Read run detail and confirm runtime_events contains the ingested event.",
        "rollback_plan": "Delete the smoke task/run from the isolated test database.",
        "status": "submitted",
    }
    status, plan = http_json("POST", args.base_url, "/api/agent-gateway/agent-plans", plan_body, token=token)
    plan_id = (plan.get("agent_plan") or {}).get("plan_id")
    require(status == 201 and plan_id, f"plan create failed: {status} {plan}", failures)

    status, verified = http_json("GET", args.base_url, f"/api/agent-gateway/agent-plans/{plan_id}/verify", token=token)
    require(status == 200 and (verified.get("verification") or {}).get("pass") is True, f"plan verify failed: {status} {verified}", failures)

    status, run_start = http_json("POST", args.base_url, "/api/agent-gateway/runs/start", {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "runtime_type": "hermes",
        "input_summary": "Start run for runtime-event ingestion smoke.",
        "agent_plan_id": plan_id,
    }, token=token)
    run_id = (run_start.get("run") or {}).get("run_id")
    require(status == 201 and run_id, f"run start failed: {status} {run_start}", failures)

    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = args.base_url
    env["AGENTOPS_WORKSPACE_ID"] = workspace_id
    env["AGENTOPS_AGENT_ID"] = agent_id
    env["AGENTOPS_API_KEY"] = token
    proc = subprocess.run(
        [
            str(CLI),
            "runtime-event",
            "record",
            "--run-id",
            run_id or "",
            "--adapter",
            "hermes",
            "--event-type",
            "runtime.tool_event",
            "--status",
            "completed",
            "--input-summary",
            f"internal shell probe Authorization: Bearer {raw_secret}",
            "--output-summary",
            f"runtime internal event completed with secret {raw_secret}",
            "--latency-ms",
            "42",
            "--payload-json",
            json.dumps({"raw": raw_secret, "tool": "shell"}, ensure_ascii=False),
            "--metadata-json",
            json.dumps({"source": "smoke", "raw": raw_secret}, ensure_ascii=False),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    require(proc.returncode == 0, f"CLI runtime event failed: {proc.stderr or proc.stdout}", failures)
    event_payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    event = event_payload.get("runtime_event") or {}
    runtime_event_id = event.get("runtime_event_id")
    gateway_scope = event_payload.get("gateway_scope") or {}
    require(event_payload.get("operation") == "runtime_event_record", f"wrong operation: {event_payload}", failures)
    require(bool(runtime_event_id), f"runtime event id missing: {event_payload}", failures)
    require(event.get("raw_payload_hash"), f"runtime event payload hash missing: {event_payload}", failures)
    require(gateway_scope.get("scope_service") == "agent_gateway_scope_v1", f"runtime event missing scope service proof: {gateway_scope}", failures)
    require(gateway_scope.get("required_scope") == "runtime_events:write", f"runtime event wrong required scope: {gateway_scope}", failures)
    require(gateway_scope.get("bound_visibility_enforced") is True, f"runtime event missing bound visibility proof: {gateway_scope}", failures)
    require(raw_secret not in json.dumps(event_payload, ensure_ascii=False), f"runtime event response leaked raw secret: {event_payload}", failures)

    status, run_detail = http_json("GET", args.base_url, f"/api/agent-gateway/runs/{run_id}", token=token)
    require(status == 200, f"run detail failed: {status} {run_detail}", failures)
    runtime_events = run_detail.get("runtime_events") or []
    matched = next((item for item in runtime_events if item.get("runtime_event_id") == runtime_event_id), None)
    require(matched is not None, f"run detail missing runtime event: {run_detail}", failures)
    require(matched and matched.get("raw_payload_hash"), f"runtime event readback missing hash: {matched}", failures)
    require(matched and raw_secret not in json.dumps(matched, ensure_ascii=False), f"runtime event readback leaked raw secret: {matched}", failures)

    status, audit_page = http_json("GET", args.base_url, "/api/audit?limit=80")
    require(status == 200, f"audit list failed: {status} {audit_page}", failures)
    audit_logs = audit_page if isinstance(audit_page, list) else audit_page.get("audit_logs") or audit_page.get("items") or []
    audit_match = next(
        (
            item
            for item in audit_logs
            if item.get("action") == "agent_gateway.runtime_event_record"
            and item.get("entity_id") == runtime_event_id
        ),
        None,
    )
    require(audit_match is not None, f"runtime event audit evidence missing: {audit_page}", failures)

    serialized = "\n".join([proc.stdout, proc.stderr, json.dumps(run_detail, ensure_ascii=False), json.dumps(audit_match or {}, ensure_ascii=False)])
    require(not token_like_leaked(serialized, token, raw_secret), "runtime event smoke leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "run_id": run_id,
        "runtime_event_id": runtime_event_id,
        "runtime_event_count": len(runtime_events),
        "secret_leaked": False,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
