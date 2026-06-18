#!/usr/bin/env python3
"""Smoke test `agentops status` without printing token secrets."""

from __future__ import annotations

import argparse
import json
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


def run_agentops(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["./scripts/agentops", *args], cwd=".", text=True, capture_output=True, check=False)


def parse_stdout_json(proc: subprocess.CompletedProcess[str]) -> dict:
    require(proc.returncode == 0, f"command failed: rc={proc.returncode} stderr={proc.stderr}")
    return json.loads(proc.stdout)


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_status_cli_smoke_{stamp}"
    create_status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "agent_id": agent_id,
        "name": "Status CLI Smoke",
        "runtime_type": "mock",
        "workspace_id": "local-demo",
        "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    require(create_status == 201, f"create failed: {create_status} {created}")
    token = created.get("token")
    token_id = created.get("token_id")
    require(token and token_id, "create did not return one-time token and token_id")

    first = run_agentops(["status", "--base-url", base_url, "--api-key", token])
    require(token not in first.stdout, "status stdout leaked raw token")
    require(token not in first.stderr, "status stderr leaked raw token")
    first_payload = parse_stdout_json(first)
    auth = first_payload.get("auth", {})
    require(auth.get("mode") == "agent_token", f"expected agent_token mode: {first_payload}")
    require(auth.get("agent_id") == agent_id, f"wrong agent binding: {first_payload}")
    require(auth.get("workspace_id") == "local-demo", f"wrong workspace binding: {first_payload}")
    require(auth.get("token_id") == token_id, f"wrong token id: {first_payload}")
    require(auth.get("heartbeat_state") == "never_seen", f"expected never_seen: {first_payload}")
    require("agents:heartbeat" in auth.get("scopes", []), f"missing scope in status: {first_payload}")

    prefix_args = run_agentops(["--base-url", base_url, "--api-key", token, "status"])
    require(token not in prefix_args.stdout, "prefix-args status stdout leaked raw token")
    require(token not in prefix_args.stderr, "prefix-args status stderr leaked raw token")
    prefix_payload = parse_stdout_json(prefix_args)
    require(prefix_payload.get("auth", {}).get("mode") == "agent_token", f"prefix global args were not honored: {prefix_payload}")

    heartbeat = run_agentops(["--base-url", base_url, "--api-key", token, "agent", "heartbeat", "--id", agent_id, "--status", "idle", "--summary", "Status smoke heartbeat."])
    require(heartbeat.returncode == 0, f"heartbeat failed: {heartbeat.stderr}")
    require(token not in heartbeat.stdout, "heartbeat stdout leaked raw token")
    require(token not in heartbeat.stderr, "heartbeat stderr leaked raw token")

    second = run_agentops(["status", "--base-url", base_url, "--api-key", token])
    second_payload = parse_stdout_json(second)
    require(second_payload.get("auth", {}).get("heartbeat_state") == "fresh", f"expected fresh after heartbeat: {second_payload}")

    revoke_status, revoked = http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
    require(revoke_status == 200, f"revoke failed: {revoke_status} {revoked}")

    revoked_status = run_agentops(["status", "--base-url", base_url, "--api-key", token])
    require(revoked_status.returncode != 0, "revoked token status unexpectedly succeeded")
    require(token not in revoked_status.stdout, "revoked status stdout leaked raw token")
    require(token not in revoked_status.stderr, "revoked status stderr leaked raw token")

    return {
        "agent_id": agent_id,
        "token_id": token_id,
        "initial_mode": auth.get("mode"),
        "initial_heartbeat_state": auth.get("heartbeat_state"),
        "prefix_global_args_supported": True,
        "post_heartbeat_state": second_payload.get("auth", {}).get("heartbeat_state"),
        "revoked_status_rejected": True,
        "token_omitted": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify agentops status command.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    result = {"ok": True, "base_url": args.base_url, "smoke": smoke(args.base_url, stamp)}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
