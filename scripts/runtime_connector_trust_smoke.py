#!/usr/bin/env python3
"""Verify runtime connector trust policy blocks live customer worker execution."""
from __future__ import annotations

import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def http_json(method: str, base_url: str, path: str, payload: dict | None = None):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def set_trust(base_url: str, connector_id: str, status: str, note: str) -> tuple[int, dict]:
    return http_json("POST", base_url, f"/api/runtime-connectors/{connector_id}/trust", {
        "trust_status": status,
        "trust_note": note,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify runtime connector trust policy.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--connector-id", default="rtc_openclaw_local")
    args = parser.parse_args()
    failures: list[str] = []
    blocked_result: dict = {}
    restore_status = None

    try:
        status, blocked = set_trust(args.base_url, args.connector_id, "blocked", "Smoke test blocks live OpenClaw execution.")
        require(status == 200, f"block trust status mismatch: {status} {blocked}", failures)
        require((blocked.get("connector") or {}).get("trust_status") == "blocked", f"connector not blocked: {blocked}", failures)

        status, blocked_result = http_json("POST", args.base_url, "/api/workflows/customer-worker-task", {
            "adapter": "openclaw",
            "confirm_run": True,
            "title": "Runtime trust smoke should block OpenClaw live execution",
            "description": "This task must not execute while the OpenClaw runtime connector is blocked.",
            "acceptance_criteria": "The workflow returns runtime_connector_trust_blocked and no live adapter execution occurs.",
            "priority": "high",
            "risk_level": "medium",
        })
        require(status == 409, f"blocked live workflow should return 409: {status} {blocked_result}", failures)
        require(blocked_result.get("reason") == "runtime_connector_trust_blocked", f"wrong block reason: {blocked_result}", failures)
        require(blocked_result.get("trust_status") == "blocked", f"missing blocked trust status: {blocked_result}", failures)
        require(not blocked_result.get("run_id"), f"blocked workflow should not create a live run: {blocked_result}", failures)
    finally:
        restore_status, restored = set_trust(args.base_url, args.connector_id, "trusted", "Smoke test restored runtime connector trust.")
        if restore_status != 200:
            failures.append(f"failed to restore trust: {restore_status} {restored}")

    serialized = json.dumps({"blocked_result": blocked_result}, ensure_ascii=False)
    require("agtok_" not in serialized and "agtsess_" not in serialized and "sk-" not in serialized and "ntn_" not in serialized, "trust smoke output leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "connector_id": args.connector_id,
        "blocked_task_id": blocked_result.get("task_id"),
        "blocked_reason": blocked_result.get("reason"),
        "restore_status": restore_status,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
