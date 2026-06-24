#!/usr/bin/env python3
"""Smoke test Agent Gateway enrollment token rotation without printing secrets."""

from __future__ import annotations

import argparse
import hashlib
import os
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
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


def safe_ref(prefix: str, raw: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", raw or "").strip("_").lower()
    if slug and len(slug) <= 64:
        return f"{prefix}_{slug}"[-12:]
    return f"{prefix}_{hashlib.sha256((raw or '').encode('utf-8')).hexdigest()[:16]}"[-12:]


def find_enrollment(enrollments: list[dict], token_id: str) -> dict:
    token_ref = safe_ref("token_ref", token_id)
    for item in enrollments:
        if item.get("token_ref") == token_ref:
            return item
    raise AssertionError(f"token ref not found in enrollment list: {token_ref}")


def api_rotation_smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_rotate_api_smoke_{stamp}"
    create_status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "agent_id": agent_id,
        "name": "Rotate API Smoke",
        "runtime_type": "mock",
        "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    require(create_status == 201, f"create failed: {create_status} {created}")
    require(created.get("token"), "create did not return one-time token")

    rotate_status, rotated = http_json("POST", base_url, "/api/agent-gateway/enrollment/rotate", {
        "token_id": created["token_id"],
        "ttl_days": 2,
    })
    require(rotate_status == 201, f"rotate failed: {rotate_status} {rotated}")
    require(rotated.get("token"), "rotate did not return one-time token")
    require(rotated.get("rotated_from_token_id") == created["token_id"], "rotate response did not link old token")

    list_status, listed = http_json("GET", base_url, "/api/agent-gateway/enrollments")
    require(list_status == 200, f"list failed: {list_status} {listed}")
    old = find_enrollment(listed.get("enrollments", []), created["token_id"])
    new = find_enrollment(listed.get("enrollments", []), rotated["token_id"])
    require(old.get("status") == "revoked", f"old token was not revoked: {old}")
    require(new.get("status") == "active", f"new token is not active: {new}")
    serialized_list = json.dumps(listed, ensure_ascii=False)
    require(created["token_id"] not in serialized_list and rotated["token_id"] not in serialized_list, f"enrollment list leaked raw token ids: {listed}")
    require(old.get("token_id_omitted") is True and new.get("token_id_omitted") is True, f"enrollment list missing omission proof: {listed}")

    revoke_status, revoked = http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"agent_id": agent_id})
    require(revoke_status == 200, f"cleanup revoke failed: {revoke_status} {revoked}")

    return {
        "agent_id": agent_id,
        "old_token_ref": safe_ref("token_ref", created["token_id"]),
        "new_token_ref": safe_ref("token_ref", rotated["token_id"]),
        "old_status_after_rotate": old.get("status"),
        "new_status_after_rotate": new.get("status"),
        "token_omitted": True,
        "cleanup_revoked": revoked.get("revoked"),
    }


def cli_rotation_smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_rotate_cli_smoke_{stamp}"
    create_status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "agent_id": agent_id,
        "name": "Rotate CLI Smoke",
        "runtime_type": "mock",
        "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
        "ttl_days": 1,
    })
    require(create_status == 201, f"CLI create failed: {create_status} {created}")

    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    raw = subprocess.check_output(
        ["./scripts/agentops", "enrollment", "rotate", "--token-id", created["token_id"], "--ttl-days", "2"],
        cwd=".",
        env=env,
        text=True,
    )
    rotated = json.loads(raw)
    require(rotated.get("rotated") is True, f"CLI rotate did not report rotated=true: {rotated}")
    require(rotated.get("rotated_from_token_id") == created["token_id"], "CLI rotate response did not link old token")
    require(rotated.get("token"), "CLI rotate did not return one-time token")

    revoke_status, revoked = http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"agent_id": agent_id})
    require(revoke_status == 200, f"CLI cleanup revoke failed: {revoke_status} {revoked}")

    return {
        "agent_id": agent_id,
        "old_token_ref": safe_ref("token_ref", created["token_id"]),
        "new_token_ref": safe_ref("token_ref", rotated["token_id"]),
        "rotated": True,
        "token_omitted": True,
        "cleanup_revoked": revoked.get("revoked"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Agent Gateway enrollment token rotation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    result = {
        "ok": True,
        "base_url": args.base_url,
        "api": api_rotation_smoke(args.base_url, stamp),
        "cli": cli_rotation_smoke(args.base_url, stamp),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
