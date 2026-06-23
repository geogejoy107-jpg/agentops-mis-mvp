#!/usr/bin/env python3
"""Verify enrollment responses include safe remote-agent launch steps."""

from __future__ import annotations

import argparse
import json
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


def assert_safe_launch_steps(payload: dict, expected_adapter: str) -> dict:
    token = payload.get("token")
    steps = payload.get("next_steps") or {}
    require(token, "response did not include one-time token")
    require(steps, "response did not include next_steps")
    text = json.dumps(steps, ensure_ascii=False)
    command_text = json.dumps({key: value for key, value in steps.items() if key != "notes"}, ensure_ascii=False)
    require(token not in text, "raw token leaked into next_steps")
    require("<paste one-time token here>" in text, "next_steps should use a token placeholder")
    require("agentops status" in text, "next_steps missing agentops status")
    require("agentops-worker preflight" in text, "next_steps missing worker preflight command")
    require("agentops session create" in text, "next_steps missing short-lived session command")
    require("python3 -m pip install ." in text, "next_steps missing package install command")
    require("agentops-worker" in text, "next_steps missing installable worker launch command")
    require("service-template --manager launchd" in text, "next_steps missing launchd service template command")
    require("service-template --manager systemd" in text, "next_steps missing systemd service template command")
    require("service-install --manager launchd" in text, "next_steps missing launchd service install command")
    require("service-install --manager systemd" in text, "next_steps missing systemd service install command")
    require("service-check --manager launchd" in text, "next_steps missing launchd service check command")
    require("service-check --manager systemd" in text, "next_steps missing systemd service check command")
    for manager in ("launchd", "systemd"):
        for action in ("load", "unload", "restart"):
            require(
                f"service-control --manager {manager} --action {action}" in text,
                f"next_steps missing {manager} service-control {action} preview command",
            )
    require("--confirm-control" not in command_text, "next_steps must not default to mutating service-control commands")
    require("scripts/agent_worker.py" in text, "next_steps missing repo fallback worker command")
    require("--use-session" in text, "worker launch command should mint a short-lived session")
    for flag in (
        "--session-refresh-margin-sec 60",
        "--idle-backoff-max 30",
        "--error-backoff-max 30",
        "--backoff-factor 2",
        "--adapter-max-attempts 1",
        "--adapter-retry-delay-sec 1",
        "--continue-on-error",
        "--max-errors 5",
    ):
        require(flag in text, f"next_steps missing explicit remote loop policy flag {flag}: {steps}")
    require(steps.get("adapter") == expected_adapter, f"next_steps adapter mismatch: {steps}")
    if expected_adapter in {"hermes", "openclaw"}:
        require("--confirm-run" in text, f"{expected_adapter} launch commands must include --confirm-run: {steps}")
    else:
        require("--confirm-run" not in text, f"{expected_adapter} launch commands should not include --confirm-run: {steps}")
    require(steps.get("token_omitted") is True, "next_steps should explicitly mark token_omitted")
    return {
        "token_id": payload.get("token_id"),
        "agent_id": payload.get("agent_id"),
        "workspace_id": payload.get("workspace_id"),
        "adapter": steps.get("adapter"),
        "token_omitted": True,
    }


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_launch_steps_smoke_{stamp}"
    create_status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "agent_id": agent_id,
        "name": "Launch Steps Smoke",
        "runtime_type": "hermes",
        "workspace_id": "local-demo",
        "base_url": "http://127.0.0.1:8787",
        "scopes": ["agents:heartbeat", "tasks:read", "tasks:claim", "runs:write", "toolcalls:write", "evaluations:submit", "audit:write"],
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    require(create_status == 201, f"create failed: {create_status} {created}")
    created_steps = assert_safe_launch_steps(created, "hermes")

    rotate_status, rotated = http_json("POST", base_url, "/api/agent-gateway/enrollment/rotate", {"token_id": created["token_id"], "ttl_days": 1})
    require(rotate_status == 201, f"rotate failed: {rotate_status} {rotated}")
    rotated_steps = assert_safe_launch_steps(rotated, "hermes")

    revoke_status, revoked = http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"agent_id": agent_id})
    require(revoke_status == 200, f"cleanup revoke failed: {revoke_status} {revoked}")

    return {
        "created": created_steps,
        "rotated": rotated_steps,
        "cleanup_revoked": revoked.get("revoked"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify enrollment launch-step response safety.")
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
