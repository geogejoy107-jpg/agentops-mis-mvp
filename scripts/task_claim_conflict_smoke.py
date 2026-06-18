#!/usr/bin/env python3
"""Verify Agent Gateway task claim is atomic enough for multi-worker use."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request


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


def create_token(base_url: str, agent_id: str) -> tuple[str, str]:
    status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "agent_id": agent_id,
        "name": f"Claim Conflict {agent_id}",
        "runtime_type": "mock",
        "workspace_id": "local-demo",
        "scopes": ["agents:heartbeat", "tasks:read", "tasks:claim", "runs:write", "audit:write"],
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    require(status == 201, f"create token failed: {status} {created}")
    return created["token"], created["token_id"]


def smoke(base_url: str, stamp: str) -> dict:
    agent_a = f"agt_claim_a_{stamp}"
    agent_b = f"agt_claim_b_{stamp}"
    task_id = f"tsk_claim_conflict_{stamp}"
    token_ids: list[str] = []
    try:
        token_a, token_id_a = create_token(base_url, agent_a)
        token_b, token_id_b = create_token(base_url, agent_b)
        token_ids.extend([token_id_a, token_id_b])

        status, task = http_json("POST", base_url, "/api/tasks", {
            "task_id": task_id,
            "workspace_id": "local-demo",
            "title": "claim conflict smoke task",
            "description": "Two eligible workers should not both claim or run the same task.",
            "owner_agent_id": None,
            "collaborator_agent_ids": json.dumps([]),
            "status": "planned",
            "priority": "high",
            "risk_level": "low",
            "acceptance_criteria": "Exactly one worker should claim the task; duplicate workers should receive conflict.",
        })
        require(status == 201, f"task create failed: {status} {task}")

        status, pull_a = http_json("GET", base_url, "/api/agent-gateway/tasks/pull?status=planned&limit=10", token=token_a)
        require(status == 200 and task_id in {item.get("task_id") for item in pull_a.get("tasks", [])}, f"agent A did not see pool task: {status} {pull_a}")
        status, pull_b = http_json("GET", base_url, "/api/agent-gateway/tasks/pull?status=planned&limit=10", token=token_b)
        require(status == 200 and task_id in {item.get("task_id") for item in pull_b.get("tasks", [])}, f"agent B did not see pool task: {status} {pull_b}")

        status, claim_a = http_json("POST", base_url, f"/api/agent-gateway/tasks/{task_id}/claim", {"runtime_type": "mock"}, token=token_a)
        require(status == 200, f"first claim failed: {status} {claim_a}")
        require((claim_a.get("task") or {}).get("owner_agent_id") == agent_a, f"first claim owner mismatch: {claim_a}")

        status, claim_a_again = http_json("POST", base_url, f"/api/agent-gateway/tasks/{task_id}/claim", {"runtime_type": "mock"}, token=token_a)
        require(status == 200 and claim_a_again.get("already_claimed") is True, f"same-agent claim should be idempotent: {status} {claim_a_again}")

        status, claim_b = http_json("POST", base_url, f"/api/agent-gateway/tasks/{task_id}/claim", {"runtime_type": "mock"}, token=token_b)
        require(status in {403, 409}, f"second worker claim should be denied or conflict: {status} {claim_b}")

        status, start_b = http_json("POST", base_url, "/api/agent-gateway/runs/start", {"task_id": task_id, "runtime_type": "mock"}, token=token_b)
        require(status in {403, 409}, f"second worker start should be denied or conflict: {status} {start_b}")

        status, start_a = http_json("POST", base_url, "/api/agent-gateway/runs/start", {"task_id": task_id, "runtime_type": "mock"}, token=token_a)
        require(status in {200, 201}, f"claiming worker start failed: {status} {start_a}")

        run = start_a.get("run") or {}
        return {
            "task_id": task_id,
            "claiming_agent": agent_a,
            "blocked_agent": agent_b,
            "run_id": run.get("run_id"),
            "both_agents_saw_pool_task": True,
            "same_agent_idempotent": claim_a_again.get("already_claimed") is True,
            "second_claim_status": claim_b.get("error"),
            "second_start_status": start_b.get("error"),
            "token_omitted": True,
        }
    finally:
        for token_id in token_ids:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify task claim conflict handling.")
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
