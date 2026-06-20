#!/usr/bin/env python3
"""Verify worker fleet status summarizes remote workers without leaking tokens."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "agentops_mis.db"
CLI = ROOT / "scripts" / "agentops"


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def run_cli(base_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "worker", "status"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    markers = ["AGENTOPS_API_KEY", "Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"]
    return any(marker in text for marker in markers)


def safe_ref(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def age_token_heartbeat(token_id: str, seconds_ago: int) -> str:
    aged_at = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE agent_gateway_tokens SET last_heartbeat_at=?, last_used_at=? WHERE token_id=?",
            (aged_at, aged_at, token_id),
        )
    return aged_at


def find_remote_worker(payload: dict, agent_id: str) -> dict:
    for item in ((payload.get("remote_worker_health") or {}).get("remote_workers") or []):
        if item.get("agent_id") == agent_id:
            return item
    raise AssertionError(f"remote worker {agent_id} not present in worker status")


def worker_status_payload(base_url: str) -> dict:
    proc = run_cli(base_url)
    require(proc.returncode == 0, f"agentops worker status failed: {proc.stderr or proc.stdout}")
    require(not leaked_secret(proc.stdout + proc.stderr), "agentops worker status leaked token-like content")
    return json.loads(proc.stdout)


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_remote_fleet_{stamp}"
    create_status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "agent_id": agent_id,
        "name": "Remote Fleet Status Smoke",
        "runtime_type": "mock",
        "workspace_id": "local-demo",
        "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
        "ttl_days": 1,
        "heartbeat_timeout_sec": 30,
    })
    require(create_status == 201, f"enrollment create failed: {create_status} {created}")
    token = created.get("token")
    token_id = created.get("token_id")
    require(token and token_id, "create did not return one-time token and token_id")
    try:
        never_seen = worker_status_payload(base_url)
        never_worker = find_remote_worker(never_seen, agent_id)
        require(never_worker.get("heartbeat_state") == "never_seen", f"expected never_seen, got {never_worker}")
        require(never_worker.get("token_id_omitted") is True and not never_worker.get("token_id"), f"token id should be omitted: {never_worker}")

        heartbeat_status, heartbeat = http_json("POST", base_url, "/api/agent-gateway/heartbeat", {
            "status": "idle",
            "summary": "remote fleet status smoke heartbeat",
        }, token=token)
        require(heartbeat_status == 200, f"heartbeat failed: {heartbeat_status} {heartbeat}")

        session_status, session = http_json("POST", base_url, "/api/agent-gateway/session/create", {
            "ttl_sec": 900,
            "scopes": ["agents:heartbeat", "tasks:read"],
        }, token=token)
        require(session_status == 201 and session.get("session_token"), f"session create failed: {session_status} {session}")

        fresh = worker_status_payload(base_url)
        fresh_worker = find_remote_worker(fresh, agent_id)
        require(fresh_worker.get("heartbeat_state") == "fresh", f"expected fresh, got {fresh_worker}")
        require(int(fresh_worker.get("active_session_count") or 0) >= 1, f"active session count missing: {fresh_worker}")
        require((fresh.get("remote_worker_health") or {}).get("active_sessions", 0) >= 1, f"active sessions missing: {fresh}")

        aged_at = age_token_heartbeat(token_id, seconds_ago=120)
        stale = worker_status_payload(base_url)
        stale_worker = find_remote_worker(stale, agent_id)
        require(stale_worker.get("heartbeat_state") == "stale", f"expected stale after aging heartbeat to {aged_at}, got {stale_worker}")
        require(stale.get("stale_remote_enrollments", 0) >= 1, f"stale count missing: {stale}")
        return {
            "agent_id": agent_id,
            "token_ref": safe_ref(token_id),
            "states": ["never_seen", "fresh", "stale"],
            "aged_at": aged_at,
            "active_sessions": (fresh.get("remote_worker_health") or {}).get("active_sessions"),
            "token_omitted": True,
        }
    finally:
        if token_id:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify remote worker fleet appears in worker status.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--stamp", default=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"))
    args = parser.parse_args()
    try:
        result = smoke(args.base_url, args.stamp)
        print(json.dumps({"ok": True, "base_url": args.base_url, "result": result}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "db_path": str(DB_PATH)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
