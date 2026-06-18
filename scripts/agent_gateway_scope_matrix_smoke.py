#!/usr/bin/env python3
"""Verify Agent Gateway scoped-token RBAC returns 403 for missing scopes."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def http_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict | None = None,
    token: str | None = None,
    query: dict | None = None,
) -> tuple[int, dict]:
    url = base_url.rstrip("/") + path
    if query:
        encoded = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
        url += "?" + encoded
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def create_enrollment(base_url: str, agent_id: str, name: str, scopes: list[str]) -> dict:
    status, payload = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "agent_id": agent_id,
        "name": name,
        "runtime_type": "mock",
        "workspace_id": "local-demo",
        "scopes": scopes,
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    require(status == 201, f"enrollment create failed: {status} {payload}")
    require(payload.get("token") and payload.get("token_id"), f"enrollment missing token: {payload}")
    return payload


def expect_forbidden(label: str, status: int, payload: dict) -> str:
    require(status == 403, f"{label} should return 403: {status} {payload}")
    require(payload.get("error") == "forbidden", f"{label} should return forbidden body: {payload}")
    return payload.get("message", "")


def smoke(base_url: str, stamp: str) -> dict:
    observer_agent = f"agt_scope_observer_{stamp}"
    worker_agent = f"agt_scope_worker_{stamp}"
    task_id = f"tsk_scope_matrix_{stamp}"
    observer_token_id = None
    worker_token_id = None
    try:
        observer = create_enrollment(base_url, observer_agent, "Scope Matrix Observer", ["agents:heartbeat", "tasks:read", "audit:write"])
        worker = create_enrollment(base_url, worker_agent, "Scope Matrix Worker", ["agents:heartbeat", "tasks:read", "tasks:claim", "runs:write", "toolcalls:write", "artifacts:write", "evaluations:submit", "audit:write"])
        observer_token = observer["token"]
        worker_token = worker["token"]
        observer_token_id = observer["token_id"]
        worker_token_id = worker["token_id"]

        status, task = http_json("POST", base_url, "/api/tasks", {
            "task_id": task_id,
            "workspace_id": "local-demo",
            "title": "scope matrix smoke task",
            "description": "Verify observer token cannot mutate task/run/tool/artifact state.",
            "owner_agent_id": worker_agent,
            "collaborator_agent_ids": [observer_agent],
            "status": "planned",
            "priority": "high",
            "risk_level": "low",
            "acceptance_criteria": "Scope matrix must enforce read/write boundaries.",
        })
        require(status == 201, f"task create failed: {status} {task}")

        status, heartbeat = http_json("POST", base_url, "/api/agent-gateway/heartbeat", {"status": "idle", "summary": "observer online"}, token=observer_token)
        require(status == 200, f"observer heartbeat failed: {status} {heartbeat}")

        status, pulled = http_json("GET", base_url, "/api/agent-gateway/tasks/pull", token=observer_token, query={"status": "planned", "limit": 10})
        require(status == 200, f"observer pull failed: {status} {pulled}")
        pulled_ids = {item.get("task_id") for item in pulled.get("tasks", [])}
        require(task_id in pulled_ids, f"observer did not see collaborator task: {pulled_ids}")

        status, audit = http_json("POST", base_url, "/api/agent-gateway/audit", {
            "action": "scope_matrix.observer_checked",
            "entity_type": "tasks",
            "entity_id": task_id,
            "metadata": {"token_omitted": True},
        }, token=observer_token)
        require(status == 201, f"observer audit failed: {status} {audit}")

        forbidden = {}
        status, body = http_json("POST", base_url, f"/api/agent-gateway/tasks/{task_id}/claim", {"runtime_type": "mock"}, token=observer_token)
        forbidden["claim"] = expect_forbidden("claim", status, body)

        status, body = http_json("POST", base_url, "/api/agent-gateway/runs/start", {"task_id": task_id, "runtime_type": "mock"}, token=observer_token)
        forbidden["run_start"] = expect_forbidden("run_start", status, body)

        status, body = http_json("POST", base_url, "/api/agent-gateway/tool-calls", {"run_id": "run_scope_matrix_fake", "tool_name": "scope.matrix"}, token=observer_token)
        forbidden["tool_call"] = expect_forbidden("tool_call", status, body)

        status, body = http_json("POST", base_url, "/api/agent-gateway/artifacts", {"run_id": "run_scope_matrix_fake", "title": "blocked artifact", "summary": "blocked"}, token=observer_token)
        forbidden["artifact"] = expect_forbidden("artifact", status, body)

        status, claimed = http_json("POST", base_url, f"/api/agent-gateway/tasks/{task_id}/claim", {"runtime_type": "mock"}, token=worker_token)
        require(status == 200, f"worker claim failed: {status} {claimed}")
        status, started = http_json("POST", base_url, "/api/agent-gateway/runs/start", {"task_id": task_id, "runtime_type": "mock"}, token=worker_token)
        require(status in {200, 201}, f"worker run start failed: {status} {started}")
        run_id = (started.get("run") or {}).get("run_id")
        require(run_id, f"worker run id missing: {started}")

        return {
            "observer_agent": observer_agent,
            "worker_agent": worker_agent,
            "task_id": task_id,
            "run_id": run_id,
            "observer_allowed": ["agents:heartbeat", "tasks:read", "audit:write"],
            "observer_forbidden": sorted(forbidden),
            "observer_token_id": observer_token_id,
            "worker_token_id": worker_token_id,
            "token_omitted": True,
        }
    finally:
        for token_id in [observer_token_id, worker_token_id]:
            if token_id:
                http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Agent Gateway scope enforcement matrix.")
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
