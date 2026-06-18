#!/usr/bin/env python3
"""Verify Agent Gateway enrollment heartbeat health states without printing secrets."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "agentops_mis.db"


def http_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def find_enrollment(enrollments: list[dict], token_id: str) -> dict:
    for item in enrollments:
        if item.get("token_id") == token_id:
            return item
    raise AssertionError(f"token not found in enrollment list: {token_id}")


def get_enrollment(base_url: str, token_id: str) -> dict:
    status, payload = http_json("GET", base_url, "/api/agent-gateway/enrollments")
    require(status == 200, f"list failed: {status} {payload}")
    return find_enrollment(payload.get("enrollments", []), token_id)


def age_token_heartbeat(token_id: str, seconds_ago: int) -> str:
    aged_at = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE agent_gateway_tokens SET last_heartbeat_at=?, last_used_at=? WHERE token_id=?",
            (aged_at, aged_at, token_id),
        )
    return aged_at


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_enroll_health_smoke_{stamp}"
    create_status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "agent_id": agent_id,
        "name": "Enrollment Health Smoke",
        "runtime_type": "mock",
        "workspace_id": "local-demo",
        "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
        "ttl_days": 1,
        "heartbeat_timeout_sec": 30,
    })
    require(create_status == 201, f"create failed: {create_status} {created}")
    token = created.get("token")
    token_id = created.get("token_id")
    require(token and token_id, "create did not return one-time token and token_id")

    never_seen = get_enrollment(base_url, token_id)
    require(never_seen.get("heartbeat_state") == "never_seen", f"expected never_seen, got {never_seen}")

    heartbeat_status, heartbeat = http_json("POST", base_url, "/api/agent-gateway/heartbeat", {
        "status": "idle",
        "summary": "Enrollment health smoke heartbeat.",
    }, token=token)
    require(heartbeat_status == 200, f"heartbeat failed: {heartbeat_status} {heartbeat}")

    fresh = get_enrollment(base_url, token_id)
    require(fresh.get("heartbeat_state") == "fresh", f"expected fresh, got {fresh}")
    require(fresh.get("last_heartbeat_at"), "fresh enrollment is missing last_heartbeat_at")

    aged_at = age_token_heartbeat(token_id, seconds_ago=120)
    stale = get_enrollment(base_url, token_id)
    require(stale.get("heartbeat_state") == "stale", f"expected stale after aging heartbeat to {aged_at}, got {stale}")

    revoke_status, revoked = http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
    require(revoke_status == 200, f"revoke failed: {revoke_status} {revoked}")

    revoked_row = get_enrollment(base_url, token_id)
    require(revoked_row.get("status") == "revoked", f"expected revoked status, got {revoked_row}")
    require(revoked_row.get("heartbeat_state") == "revoked", f"revoked token should not show live heartbeat state: {revoked_row}")

    return {
        "agent_id": agent_id,
        "token_id": token_id,
        "states": ["never_seen", "fresh", "stale", "revoked"],
        "last_heartbeat_aged_at": aged_at,
        "token_omitted": True,
        "cleanup_revoked": revoked.get("revoked"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Agent Gateway enrollment heartbeat states.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    result = {
        "ok": True,
        "base_url": args.base_url,
        "db_path": str(DB_PATH),
        "smoke": smoke(args.base_url, stamp),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
