#!/usr/bin/env python3
"""Verify production mode fails closed without admin/API credentials."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


SECRET_MARKERS = ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_", "AGENTOPS_API_KEY="]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def request_json(method: str, base_url: str, path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"error": exc.reason, "raw": raw}
        return exc.code, body


def assert_unauthorized(label: str, status: int, payload: dict) -> None:
    require(status == 401, f"{label} should be 401 in production mode without credentials: {status} {payload}")
    require(payload.get("error") == "unauthorized", f"{label} wrong error payload: {payload}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify production auth fail-closed behavior.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--admin-key", default=os.environ.get("AGENTOPS_ADMIN_KEY", ""))
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        status, readiness = request_json("GET", args.base_url, "/api/security/production-readiness")
        outputs.append(json.dumps(readiness, ensure_ascii=False, sort_keys=True))
        require(status == 200, f"readiness failed: {status} {readiness}")
        require(readiness.get("production_requested") is True, f"server is not in production-requested mode: {readiness}")
        require(readiness.get("status") == "blocked", f"production readiness should be blocked without API/admin keys: {readiness}")
        require(readiness.get("production_ready") is False, f"production_ready should be false: {readiness}")
        require(readiness.get("auth_mode") == "unauthorized", f"auth mode should report unauthorized: {readiness}")

        checks = [
            ("GET enrollments", "GET", "/api/agent-gateway/enrollments", None),
            ("GET sessions", "GET", "/api/agent-gateway/sessions", None),
            ("POST enrollment create", "POST", "/api/agent-gateway/enrollment/create", {
                "agent_id": "agt_prod_fail_closed",
                "name": "Production Fail Closed",
                "runtime_type": "mock",
                "workspace_id": "local-demo",
                "scopes": ["tasks:read"],
            }),
            ("POST enrollment revoke", "POST", "/api/agent-gateway/enrollment/revoke", {"agent_id": "agt_prod_fail_closed"}),
            ("POST session revoke", "POST", "/api/agent-gateway/session/revoke", {"agent_id": "agt_prod_fail_closed"}),
            ("GET task pull", "GET", "/api/agent-gateway/tasks/pull", None),
            ("POST task create", "POST", "/api/agent-gateway/tasks", {
                "title": "Production unauthorized task",
                "owner_agent_id": "agt_prod_fail_closed",
                "acceptance_criteria": "Should not be created.",
            }),
        ]
        for label, method, path, payload in checks:
            item_status, item_payload = request_json(method, args.base_url, path, payload)
            outputs.append(json.dumps(item_payload, ensure_ascii=False, sort_keys=True))
            assert_unauthorized(label, item_status, item_payload)

        admin_list_status = None
        if args.admin_key:
            admin_list_status, admin_payload = request_json(
                "GET",
                args.base_url,
                "/api/agent-gateway/enrollments",
                headers={"X-AgentOps-Admin-Key": args.admin_key},
            )
            outputs.append(json.dumps(admin_payload, ensure_ascii=False, sort_keys=True))
            require(admin_list_status == 200, f"admin-key enrollment list should pass: {admin_list_status} {admin_payload}")
            require(admin_payload.get("valid_scopes"), f"admin-key list should include valid scopes: {admin_payload}")

        require(not leaked_secret("\n".join(outputs)), "production auth smoke leaked token-like material")
        print(json.dumps({
            "ok": True,
            "production_requested": readiness.get("production_requested"),
            "readiness_status": readiness.get("status"),
            "auth_mode": readiness.get("auth_mode"),
            "unauthorized_checks": len(checks),
            "admin_key_list_status": admin_list_status,
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
