#!/usr/bin/env python3
"""Verify task creation returns a clear 400 when owner agent is missing."""

from __future__ import annotations

import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def post_json(base_url: str, path: str, payload: dict):
    req = Request(base_url.rstrip("/") + path, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=30) as res:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify owner-agent validation for task creation.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    missing_agent = "agt_missing_owner_validation_smoke"
    status, payload = post_json(args.base_url, "/api/tasks", {
        "task_id": "tsk_missing_owner_validation_smoke",
        "title": "Missing owner validation smoke",
        "description": "This task should not be created because the owner agent is missing.",
        "owner_agent_id": missing_agent,
        "status": "planned",
    })
    failures = []
    if status != 400:
        failures.append(f"expected 400, got {status}: {payload}")
    if payload.get("error") != "owner_agent_not_found":
        failures.append(f"unexpected error payload: {payload}")
    if payload.get("owner_agent_id") != missing_agent:
        failures.append(f"missing owner_agent_id echo: {payload}")
    serialized = json.dumps(payload, ensure_ascii=False)
    if "agtok_" in serialized or "sk-" in serialized or "ntn_" in serialized:
        failures.append("validation payload leaked token-like material")
    output = {
        "ok": not failures,
        "status": status,
        "error": payload.get("error"),
        "owner_agent_id": payload.get("owner_agent_id"),
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
