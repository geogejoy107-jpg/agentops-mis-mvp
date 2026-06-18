#!/usr/bin/env python3
"""Verify short-lived Agent Gateway sessions inherit scope and expire."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
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
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
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


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_session_smoke_{stamp}"
    task_id = f"tsk_session_smoke_{stamp}"
    token_id = None
    try:
        status, enrollment = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
            "agent_id": agent_id,
            "name": "Session Smoke Agent",
            "runtime_type": "mock",
            "workspace_id": "local-demo",
            "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        })
        require(status == 201, f"enrollment create failed: {status} {enrollment}")
        enrollment_token = enrollment.get("token")
        token_id = enrollment.get("token_id")
        require(enrollment_token and token_id, f"missing enrollment token: {enrollment}")

        status, session = http_json("POST", base_url, "/api/agent-gateway/session/create", {
            "ttl_sec": 1,
            "scopes": ["agents:heartbeat", "tasks:read"],
        }, token=enrollment_token)
        require(status == 201, f"session create failed: {status} {session}")
        session_token = session.get("session_token")
        session_id = session.get("session_id")
        require(session_token and session_id, f"missing session token: {session}")
        require("audit:write" not in session.get("scopes", []), f"session scopes were not narrowed: {session}")

        status, task = http_json("POST", base_url, "/api/tasks", {
            "task_id": task_id,
            "workspace_id": "local-demo",
            "title": "session smoke task",
            "description": "Verify short-lived Agent Gateway session can pull tasks.",
            "owner_agent_id": agent_id,
            "status": "planned",
            "priority": "medium",
            "risk_level": "low",
        })
        require(status == 201, f"task create failed: {status} {task}")

        status, gateway_status = http_json("GET", base_url, "/api/agent-gateway/status", token=session_token)
        require(status == 200, f"session status failed: {status} {gateway_status}")
        require((gateway_status.get("auth") or {}).get("mode") == "agent_session", f"wrong auth mode: {gateway_status}")

        status, heartbeat = http_json("POST", base_url, "/api/agent-gateway/heartbeat", {
            "status": "idle",
            "summary": "session smoke heartbeat",
        }, token=session_token)
        require(status == 200, f"session heartbeat failed: {status} {heartbeat}")

        status, pulled = http_json("GET", base_url, "/api/agent-gateway/tasks/pull", token=session_token, query={"status": "planned", "limit": 10})
        require(status == 200, f"session pull failed: {status} {pulled}")
        pulled_ids = {item.get("task_id") for item in pulled.get("tasks", [])}
        require(task_id in pulled_ids, f"session did not pull owned task: {pulled_ids}")

        status, nested = http_json("POST", base_url, "/api/agent-gateway/session/create", {"ttl_sec": 30}, token=session_token)
        require(status == 401, f"session should not mint another session: {status} {nested}")

        time.sleep(2)
        status, expired = http_json("POST", base_url, "/api/agent-gateway/heartbeat", {
            "status": "idle",
            "summary": "expired session heartbeat",
        }, token=session_token)
        require(status == 401, f"expired session should be rejected: {status} {expired}")
        require("expired" in json.dumps(expired).lower(), f"expired session message missing: {expired}")

        return {
            "agent_id": agent_id,
            "task_id": task_id,
            "token_id": token_id,
            "session_id": session_id,
            "session_scopes": session.get("scopes", []),
            "auth_mode": (gateway_status.get("auth") or {}).get("mode"),
            "expired_status": expired.get("error"),
            "token_omitted": True,
        }
    finally:
        if token_id:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Agent Gateway short-lived session behavior.")
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
