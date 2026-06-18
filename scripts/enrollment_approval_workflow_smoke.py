#!/usr/bin/env python3
"""Verify enrollment request -> approval -> token issue workflow."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
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


def smoke(base_url: str, run_stamp: str) -> dict:
    agent_id = f"agt_enroll_approval_{run_stamp}"
    token_id = None
    status, requested = http_json("POST", base_url, "/api/agent-gateway/enrollment/request", {
        "agent_id": agent_id,
        "name": "Approved Remote Worker",
        "role": "Remote AI Digital Employee",
        "runtime_type": "mock",
        "workspace_id": "local-demo",
        "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
        "reason": "Smoke test remote enrollment approval workflow.",
    })
    require(status == 201, f"request failed: {status} {requested}")
    require("token" not in requested and "token_id" not in requested, f"request leaked token data: {requested}")
    request = requested.get("request") or {}
    approval = requested.get("approval") or {}
    request_id = request.get("request_id")
    approval_id = approval.get("approval_id")
    task_id = request.get("task_id")
    run_id = request.get("run_id")
    require(request_id and approval_id and task_id and run_id, f"request missing ids: {requested}")

    status, premature = http_json("POST", base_url, "/api/agent-gateway/enrollment/issue-approved", {"approval_id": approval_id})
    require(status == 409, f"premature issue should require approval: {status} {premature}")

    status, approved = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
    require(status == 200, f"approval failed: {status} {approved}")
    require(approved.get("decision") == "approved", f"approval decision missing: {approved}")

    status, issued = http_json("POST", base_url, "/api/agent-gateway/enrollment/issue-approved", {
        "approval_id": approval_id,
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    require(status == 201, f"issue approved failed: {status} {issued}")
    token = issued.get("token")
    token_id = issued.get("token_id")
    require(token and token_id, f"issued response missing one-time token: {issued}")
    require(issued.get("issued_from_request_id") == request_id, f"issued request id mismatch: {issued}")

    status, heartbeat = http_json("POST", base_url, "/api/agent-gateway/heartbeat", {
        "status": "idle",
        "summary": "approved enrollment token online",
    }, token=token)
    require(status == 200, f"issued token heartbeat failed: {status} {heartbeat}")

    return {
        "agent_id": agent_id,
        "request_id": request_id,
        "approval_id": approval_id,
        "task_id": task_id,
        "run_id": run_id,
        "token_id": token_id,
        "premature_issue_status": premature.get("error"),
        "heartbeat_status": heartbeat.get("status"),
        "token_omitted": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify enrollment approval workflow.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args(argv)
    result = {"ok": False, "base_url": args.base_url}
    token_id = None
    try:
        result["smoke"] = smoke(args.base_url, stamp())
        token_id = (result["smoke"] or {}).get("token_id")
        result["ok"] = True
        return 0
    except Exception as exc:
        result["error"] = str(exc)
        return 1
    finally:
        if token_id:
            status, revoked = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
            result["cleanup"] = {"status": status, "revoked": revoked.get("revoked")}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
