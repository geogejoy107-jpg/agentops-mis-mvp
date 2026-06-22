#!/usr/bin/env python3
"""
Verify approval decisions preserve context and update linked ledger rows.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def http_json(method: str, base_url: str, path: str, payload: dict | None = None):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=180) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def require(condition: bool, message: str, failures: list[str]):
    if not condition:
        failures.append(message)


def run_project(base_url: str) -> dict:
    payload = http_json("POST", base_url, "/api/workflows/kb-bot-project", {})
    approval_ids = payload.get("approval_ids") or []
    if not approval_ids:
        raise RuntimeError(f"workflow did not create approval: {payload}")
    approval_id = approval_ids[0]
    approval = http_json("GET", base_url, f"/api/agent-gateway/approvals/{approval_id}")["approval"]
    return {"workflow": payload, "approval": approval}


def verify_decision(base_url: str, decision: str, failures: list[str]) -> dict:
    created = run_project(base_url)
    before = created["approval"]
    run_before = http_json("GET", base_url, f"/api/runs/{before['run_id']}")["run"]
    decided = http_json("POST", base_url, f"/api/approvals/{before['approval_id']}/{decision}", {})
    run_detail = http_json("GET", base_url, f"/api/runs/{before['run_id']}")
    task_detail = http_json("GET", base_url, f"/api/tasks/{before['task_id']}")
    tool = next((item for item in run_detail.get("tool_calls", []) if item.get("tool_call_id") == before["tool_call_id"]), {})

    expected_decision = "approved" if decision == "approve" else "rejected"
    require(decided.get("decision") == expected_decision, f"{decision}: approval decision mismatch", failures)
    require(decided.get("reason") == before.get("reason"), f"{decision}: approval reason was overwritten", failures)
    if decision == "approve":
        require(tool.get("status") == "completed", "approve: tool call should be completed", failures)
        require(run_detail["run"].get("approval_required") in (False, 0), "approve: run approval_required should be cleared", failures)
        require(run_detail["run"].get("output_summary") == run_before.get("output_summary"), "approve: completed run output summary should not be replaced by mock completion", failures)
    else:
        require(tool.get("status") == "blocked", "reject: tool call should be blocked", failures)
        require(run_detail["run"].get("status") == "blocked", "reject: run should be blocked", failures)
        require(task_detail["task"].get("status") == "blocked", "reject: task should be blocked", failures)
    return {
        "approval_id": before["approval_id"],
        "run_id": before["run_id"],
        "task_id": before["task_id"],
        "tool_call_id": before["tool_call_id"],
        "decision": decided.get("decision"),
        "tool_status": tool.get("status"),
        "run_status": run_detail["run"].get("status"),
        "task_status": task_detail["task"].get("status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify approval decision side effects.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    failures: list[str] = []
    approved = verify_decision(args.base_url, "approve", failures)
    rejected = verify_decision(args.base_url, "reject", failures)
    output = {"ok": not failures, "approved": approved, "rejected": rejected, "failures": failures}
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
