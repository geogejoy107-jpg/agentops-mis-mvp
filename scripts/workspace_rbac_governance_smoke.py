#!/usr/bin/env python3
"""Verify human/admin read APIs respect workspace boundaries."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


SECRET_MARKERS = [
    "Authorization" + ":",
    "Bearer" + " ",
    "agt" + "ok_",
    "agt" + "sess_",
    "nt" + "n_",
    "AGENTOPS_API_KEY=",
]
OPENAI_KEY_RE = re.compile(r"s" + r"k-[A-Za-z0-9_-]{20,}")


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS) or bool(OPENAI_KEY_RE.search(text))


def http_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict | None = None,
    workspace_id: str | None = None,
    query: dict | None = None,
) -> tuple[int, object]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if workspace_id:
        headers["X-AgentOps-Workspace-Id"] = workspace_id
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body


def ids_from_rows(rows: object, key: str) -> set[str]:
    if isinstance(rows, list):
        return {str(row.get(key)) for row in rows if isinstance(row, dict) and row.get(key)}
    return set()


def create_task(base_url: str, workspace_id: str, task_id: str, agent_id: str, title: str) -> None:
    status, payload = http_json("POST", base_url, "/api/tasks", {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "title": title,
        "description": f"Workspace governance smoke task for {workspace_id}.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Human/admin APIs must not leak this task across workspaces.",
    }, workspace_id=workspace_id)
    require(status == 201, f"task create failed for {workspace_id}: {status} {payload}")


def start_mock_run(base_url: str, workspace_id: str, task_id: str, agent_id: str) -> str:
    status, payload = http_json("POST", base_url, "/api/mock-runs/start", {
        "task_id": task_id,
        "agent_id": agent_id,
    }, workspace_id=workspace_id)
    require(status == 201, f"mock run failed for {workspace_id}: {status} {payload}")
    run_id = payload.get("run_id") if isinstance(payload, dict) else None
    require(bool(run_id), f"mock run did not return run_id: {payload}")
    return str(run_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify human/admin workspace governance.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    stamp = now_stamp()
    workspace_a = f"ws_gov_a_{stamp}"
    workspace_b = f"ws_gov_b_{stamp}"
    agent_id = "agt_builder"
    task_a = f"tsk_gov_a_{stamp}"
    task_b = f"tsk_gov_b_{stamp}"
    outputs: list[str] = []
    try:
        create_task(args.base_url, workspace_a, task_a, agent_id, "workspace A governance smoke")
        create_task(args.base_url, workspace_b, task_b, agent_id, "workspace B governance smoke")
        run_a = start_mock_run(args.base_url, workspace_a, task_a, agent_id)
        run_b = start_mock_run(args.base_url, workspace_b, task_b, agent_id)

        list_checks = [
            ("tasks", "/api/tasks", "task_id", task_a, task_b),
            ("runs", "/api/runs", "run_id", run_a, run_b),
            ("runs_export", "/api/runs/export", "run_id", run_a, run_b),
            ("tool_calls", "/api/tool-calls", "run_id", run_a, run_b),
            ("approvals", "/api/approvals", "task_id", task_a, task_b),
            ("evaluations", "/api/evaluations", "task_id", task_a, task_b),
            ("artifacts", "/api/artifacts", "task_id", task_a, task_b),
        ]
        list_results = {}
        for label, path, key, expected_id, forbidden_id in list_checks:
            status, payload = http_json("GET", args.base_url, path, workspace_id=workspace_a)
            outputs.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            require(status == 200, f"{label} list failed: {status} {payload}")
            ids = ids_from_rows(payload, key)
            require(expected_id in ids or label in {"approvals", "evaluations", "artifacts"}, f"{label} missing workspace A id {expected_id}: {ids}")
            require(forbidden_id not in ids, f"{label} leaked workspace B id {forbidden_id}: {ids}")
            list_results[label] = len(ids)

        detail_checks = [
            ("task_detail", f"/api/tasks/{task_b}"),
            ("run_detail", f"/api/runs/{run_b}"),
        ]
        for label, path in detail_checks:
            status, payload = http_json("GET", args.base_url, path, workspace_id=workspace_a)
            outputs.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            require(status == 404, f"{label} should hide workspace B object from workspace A: {status} {payload}")

        status, audit_payload = http_json("GET", args.base_url, "/api/audit", workspace_id=workspace_a)
        outputs.append(json.dumps(audit_payload, ensure_ascii=False, sort_keys=True))
        require(status == 200, f"audit list failed: {status} {audit_payload}")
        audit_text = json.dumps(audit_payload, ensure_ascii=False, sort_keys=True)
        require(task_a in audit_text or run_a in audit_text, "workspace A audit evidence missing")
        require(task_b not in audit_text and run_b not in audit_text, "workspace B audit evidence leaked into workspace A audit")

        require(not leaked_secret("\n".join(outputs)), "workspace governance smoke leaked token-like material")
        print(json.dumps({
            "ok": True,
            "workspace_a": workspace_a,
            "workspace_b": workspace_b,
            "task_a": task_a,
            "task_b": task_b,
            "run_a": run_a,
            "run_b": run_b,
            "list_results": list_results,
            "detail_cross_workspace_hidden": True,
            "audit_cross_workspace_hidden": True,
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
