#!/usr/bin/env python3
"""Verify memory review/export and session admin views respect workspace boundaries."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from smoke_isolated_server import isolated_server


SECRET_PATTERNS = [
    re.compile("Authorization" + ":", re.IGNORECASE),
    re.compile("Bearer" + r"\s+[A-Za-z0-9._~+/=-]+"),
    re.compile("s" + r"k-[A-Za-z0-9_-]{20,}"),
    re.compile("nt" + r"n_[A-Za-z0-9_]+"),
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    forbidden_fields = ('"token":', '"session_token":', '"token_hash":', '"session_hash":')
    return any(field in text for field in forbidden_fields) or any(pattern.search(text) for pattern in SECRET_PATTERNS)


def http_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict | None = None,
    token: str | None = None,
    workspace_id: str | None = None,
    query: dict | None = None,
) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if workspace_id:
        headers["X-AgentOps-Workspace-Id"] = workspace_id
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body, raw


def create_enrollment(base_url: str, workspace_id: str, agent_id: str) -> tuple[str, str]:
    status, payload, _raw = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "name": f"Governance {agent_id}",
        "runtime_type": "mock",
        "scopes": ["tasks:read", "memories:propose", "agents:heartbeat"],
        "ttl_days": 1,
    })
    require(status == 201, f"enrollment create failed: {status} {payload}")
    token_id = payload.get("token_id")
    token = payload.get("token")
    require(bool(token_id and token), f"enrollment did not return token: {payload}")
    return str(token_id), str(token)


def create_task(base_url: str, workspace_id: str, agent_id: str, task_id: str) -> None:
    status, payload, _raw = http_json("POST", base_url, "/api/tasks", {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "title": f"memory governance {workspace_id}",
        "description": "Workspace memory governance smoke task.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "medium",
        "risk_level": "low",
    }, workspace_id=workspace_id)
    require(status == 201, f"task create failed: {status} {payload}")


def propose_memory(base_url: str, workspace_id: str, agent_id: str, token: str, marker: str, task_id: str | None = None) -> str:
    payload = {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "scope": "task" if task_id else "org",
        "memory_type": "artifact_summary",
        "canonical_text": f"Workspace memory/session governance marker {marker}.",
        "source_ref": f"workspace_memory_session_governance:{marker}",
        "access_tags": ["workspace-governance", workspace_id],
        "confidence": 0.86,
    }
    if task_id:
        payload["task_id"] = task_id
    status, body, _raw = http_json("POST", base_url, "/api/agent-gateway/memories/propose", payload, token=token, workspace_id=workspace_id)
    require(status in {200, 201}, f"memory propose failed: {status} {body}")
    memory_id = (body.get("memory") or {}).get("memory_id")
    require(bool(memory_id), f"memory_id missing: {body}")
    return str(memory_id)


def create_session(base_url: str, token: str, workspace_id: str) -> str:
    status, payload, _raw = http_json("POST", base_url, "/api/agent-gateway/session/create", {
        "ttl_sec": 120,
        "scopes": ["tasks:read"],
    }, token=token, workspace_id=workspace_id)
    require(status == 201, f"session create failed: {status} {payload}")
    session_id = payload.get("session_id")
    require(bool(session_id and payload.get("session_token")), f"session missing one-time token: {payload}")
    return str(session_id)


def ids_from_rows(rows: object, key: str) -> set[str]:
    if not isinstance(rows, list):
        return set()
    return {str(row.get(key)) for row in rows if isinstance(row, dict) and row.get(key)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify workspace memory and session governance.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--isolated-fixture", action="store_true", help="Start a temporary local server and SQLite database for this smoke.")
    args = parser.parse_args()
    if args.isolated_fixture:
        with isolated_server("agentops-workspace-memory-session-") as fixture:
            return run_smoke(fixture["base_url"], isolated_fixture=True)
    return run_smoke(args.base_url, isolated_fixture=False)


def run_smoke(base_url: str, isolated_fixture: bool = False) -> int:

    stamp = now_stamp()
    workspace_a = f"ws_mem_a_{stamp}"
    workspace_b = f"ws_mem_b_{stamp}"
    agent_a = f"agt_mem_a_{stamp}"
    agent_b = f"agt_mem_b_{stamp}"
    task_a = f"tsk_mem_a_{stamp}"
    task_b = f"tsk_mem_b_{stamp}"
    safe_outputs: list[str] = []
    token_ids: list[str] = []

    try:
        token_id_a, token_a = create_enrollment(base_url, workspace_a, agent_a)
        token_id_b, token_b = create_enrollment(base_url, workspace_b, agent_b)
        token_ids.extend([token_id_a, token_id_b])
        session_a = create_session(base_url, token_a, workspace_a)
        session_b = create_session(base_url, token_b, workspace_b)

        create_task(base_url, workspace_a, agent_a, task_a)
        create_task(base_url, workspace_b, agent_b, task_b)
        memory_a = propose_memory(base_url, workspace_a, agent_a, token_a, f"A {stamp}", task_a)
        memory_b = propose_memory(base_url, workspace_b, agent_b, token_b, f"B {stamp}", task_b)
        org_memory_a = propose_memory(base_url, workspace_a, agent_a, token_a, f"ORG A {stamp}")
        org_memory_b = propose_memory(base_url, workspace_b, agent_b, token_b, f"ORG B {stamp}")

        for label, path in [("memories", "/api/memories"), ("memories_export", "/api/memories/export")]:
            status, payload, raw = http_json("GET", base_url, path, workspace_id=workspace_a)
            safe_outputs.append(raw)
            require(status == 200, f"{label} failed: {status} {payload}")
            ids = ids_from_rows(payload, "memory_id")
            require(memory_a in ids and org_memory_a in ids, f"{label} missing workspace A memories: {ids}")
            require(memory_b not in ids and org_memory_b not in ids, f"{label} leaked workspace B memories: {ids}")

        status, hidden, raw = http_json("POST", base_url, f"/api/memories/{memory_b}/approve", {}, workspace_id=workspace_a)
        safe_outputs.append(raw)
        require(status == 404, f"workspace A should not approve workspace B memory: {status} {hidden}")

        status, approved, raw = http_json("POST", base_url, f"/api/memories/{memory_a}/approve", {}, workspace_id=workspace_a)
        safe_outputs.append(raw)
        require(status == 200 and approved.get("review_status") == "approved", f"workspace A memory approve failed: {status} {approved}")
        require(approved.get("workspace_id") == workspace_a, f"approved memory lost workspace: {approved}")

        status, enrollments, raw = http_json("GET", base_url, "/api/agent-gateway/enrollments", workspace_id=workspace_a)
        safe_outputs.append(raw)
        require(status == 200, f"enrollment list failed: {status} {enrollments}")
        enrollment_ids = ids_from_rows(enrollments.get("enrollments"), "token_id")
        require(token_id_a in enrollment_ids and token_id_b not in enrollment_ids, f"enrollment workspace filter failed: {enrollment_ids}")
        require("token_hash" not in raw and '"token":' not in raw, "enrollment admin list leaked token material")

        status, sessions, raw = http_json("GET", base_url, "/api/agent-gateway/sessions", workspace_id=workspace_a)
        safe_outputs.append(raw)
        require(status == 200, f"session list failed: {status} {sessions}")
        session_ids = ids_from_rows(sessions.get("sessions"), "session_id")
        require(session_a in session_ids and session_b not in session_ids, f"session workspace filter failed: {session_ids}")
        require("session_hash" not in raw and "session_token" not in raw, "session admin list leaked secret material")

        require(not secret_leaked("\n".join(safe_outputs)), "workspace memory/session governance leaked token-like material")
        print(json.dumps({
            "ok": True,
            "base_url": base_url,
            "isolated_fixture": isolated_fixture,
            "workspace_a": workspace_a,
            "workspace_b": workspace_b,
            "visible_memories": [memory_a, org_memory_a],
            "hidden_memories": [memory_b, org_memory_b],
            "visible_sessions": 1 if session_a else 0,
            "hidden_sessions": 1 if session_b else 0,
            "visible_enrollments": 1 if token_id_a else 0,
            "hidden_enrollments": 1 if token_id_b else 0,
            "session_ids_omitted": True,
            "enrollment_token_ids_omitted": True,
            "cross_workspace_review_hidden": True,
            "secret_leaked": False,
            "token_omitted": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        for token_id in token_ids:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        raise
