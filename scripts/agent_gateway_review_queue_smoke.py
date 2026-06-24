#!/usr/bin/env python3
"""Verify Agent Gateway review queue scope and workspace visibility."""
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


SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict | None = None,
    token: str | None = None,
    workspace_header: str | None = None,
    query: dict | None = None,
    admin_key: str | None = None,
) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if admin_key:
        headers["X-AgentOps-Admin-Key"] = admin_key
    if workspace_header:
        headers["X-AgentOps-Workspace-Id"] = workspace_header
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body, raw


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def create_enrollment(base_url: str, admin_key: str | None, agent_id: str, workspace_id: str, scopes: list[str]) -> tuple[str, str]:
    status, payload, _raw = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "name": f"Review Queue {agent_id}",
        "runtime_type": "mock",
        "scopes": scopes,
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    }, admin_key=admin_key)
    require(status == 201, f"enrollment create failed for {agent_id}: {status} {payload}")
    token = payload.get("token")
    token_id = payload.get("token_id")
    require(bool(token and token_id), f"enrollment token missing for {agent_id}: {payload}")
    return str(token_id), str(token)


def create_task(base_url: str, workspace_id: str, agent_id: str, task_id: str, title: str) -> str:
    status, payload, raw = http_json("POST", base_url, "/api/tasks", {
        "task_id": task_id,
        "workspace_id": workspace_id,
        "title": title,
        "description": "Scoped review queue smoke fixture.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Review queue must not cross token workspace boundaries.",
    })
    require(status in {200, 201}, f"task create failed for {task_id}: {status} {payload}")
    return raw


def propose_memory(
    base_url: str,
    token: str,
    workspace_id: str,
    agent_id: str,
    task_id: str,
    text: str,
) -> tuple[str, str]:
    status, payload, raw = http_json("POST", base_url, "/api/agent-gateway/memories/propose", {
        "agent_id": agent_id,
        "workspace_id": workspace_id,
        "task_id": task_id,
        "scope": "task",
        "memory_type": "artifact_summary",
        "canonical_text": text,
        "source_ref": f"review_queue_smoke:{task_id}",
        "access_tags": ["review-queue-smoke", workspace_id],
        "confidence": 0.82,
    }, token=token, workspace_header=workspace_id)
    require(status in {200, 201}, f"memory propose failed for {task_id}: {status} {payload}")
    memory_id = (payload.get("memory") or {}).get("memory_id")
    require(bool(memory_id), f"memory id missing for {task_id}: {payload}")
    return str(memory_id), raw


def revoke(base_url: str, admin_key: str | None, token_id: str) -> None:
    http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id}, admin_key=admin_key)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify scoped Agent Gateway review queue.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--admin-key", default=os.environ.get("AGENTOPS_ADMIN_KEY", ""))
    args = parser.parse_args()

    stamp = now_stamp()
    workspace_a = f"ws_review_a_{stamp}"
    workspace_b = f"ws_review_b_{stamp}"
    agent_a = f"agt_review_a_{stamp}"
    agent_b = f"agt_review_b_{stamp}"
    agent_limited = f"agt_review_limited_{stamp}"
    task_a = f"tsk_review_a_{stamp}"
    task_b = f"tsk_review_b_{stamp}"
    text_a = f"Scoped review queue visible candidate A {stamp}."
    text_b = f"Scoped review queue hidden candidate B {stamp}."
    hidden_noise_count = 60
    admin_key = args.admin_key or None
    token_ids: list[str] = []
    outputs: list[str] = []

    try:
        scopes = ["tasks:read", "memories:propose"]
        token_id_a, token_a = create_enrollment(args.base_url, admin_key, agent_a, workspace_a, scopes)
        token_id_b, token_b = create_enrollment(args.base_url, admin_key, agent_b, workspace_b, scopes)
        token_id_limited, token_limited = create_enrollment(args.base_url, admin_key, agent_limited, workspace_a, ["agents:heartbeat"])
        token_ids.extend([token_id_a, token_id_b, token_id_limited])

        outputs.append(create_task(args.base_url, workspace_a, agent_a, task_a, "Scoped review queue A task"))
        outputs.append(create_task(args.base_url, workspace_b, agent_b, task_b, "Scoped review queue B task"))
        memory_a, raw = propose_memory(args.base_url, token_a, workspace_a, agent_a, task_a, text_a)
        outputs.append(raw)
        memory_b, raw = propose_memory(args.base_url, token_b, workspace_b, agent_b, task_b, text_b)
        outputs.append(raw)
        for index in range(hidden_noise_count):
            _memory_noise, raw = propose_memory(
                args.base_url,
                token_b,
                workspace_b,
                agent_b,
                task_b,
                f"Scoped review queue hidden noise {index:02d} {stamp}.",
            )
            if index in {0, hidden_noise_count - 1}:
                outputs.append(raw)

        status, queue, raw = http_json(
            "GET",
            args.base_url,
            "/api/agent-gateway/review/queue",
            token=token_a,
            workspace_header=workspace_a,
            query={"limit": 1},
        )
        outputs.append(raw)
        require(status == 200, f"scoped review queue failed: {status} {queue}")
        require(queue.get("provider") == "agentops-review", f"provider mismatch: {queue}")
        require(queue.get("operation") == "human_review_queue", f"operation mismatch: {queue}")
        gateway_scope = queue.get("gateway_scope") or {}
        require(gateway_scope.get("required_scope") == "tasks:read", f"scope mismatch: {gateway_scope}")
        require(gateway_scope.get("scope_service") == "agent_gateway_scope_v1", f"unified scope service missing: {gateway_scope}")
        require(gateway_scope.get("bound_visibility_enforced") is True, f"bound visibility missing: {gateway_scope}")
        require(gateway_scope.get("scope_before_limit") is True, f"scope-before-limit proof missing: {gateway_scope}")
        require(gateway_scope.get("scoped_totals_before_limit") is True, f"scoped totals proof missing: {gateway_scope}")
        require(gateway_scope.get("workspace_id") == workspace_a, f"workspace mismatch: {gateway_scope}")
        require(gateway_scope.get("agent_id") == agent_a, f"agent mismatch: {gateway_scope}")
        require(queue.get("token_omitted") is True, "token omission missing")

        serialized_queue = json.dumps(queue, ensure_ascii=False)
        require(memory_a in serialized_queue and text_a in serialized_queue, "workspace A memory candidate missing from scoped queue")
        require(memory_b not in serialized_queue and text_b not in serialized_queue and task_b not in serialized_queue, "workspace B review item leaked into scoped queue")
        require(len(queue.get("review_items") or []) <= 1, "review queue ignored limit")
        summary = queue.get("summary") or {}
        require(summary.get("scope_before_limit") is True, f"summary scope-before-limit proof missing: {summary}")
        require(int(summary.get("memory_candidates") or 0) == 1, f"scoped memory total distorted by hidden global noise: {summary}")
        require(int(summary.get("returned_items") or 0) == 1, f"scoped returned item count wrong: {summary}")

        status, forbidden, raw = http_json(
            "GET",
            args.base_url,
            "/api/agent-gateway/review/queue",
            token=token_limited,
            workspace_header=workspace_a,
            query={"limit": 5},
        )
        outputs.append(raw)
        require(status == 403, f"limited token should be forbidden: {status} {forbidden}")
        require("tasks:read" in (forbidden.get("message") or ""), f"forbidden message should mention tasks:read: {forbidden}")
        require(not secret_leaked("\n".join(outputs)), "review queue smoke leaked token-like material")

        print(json.dumps({
            "ok": True,
            "workspace_a": workspace_a,
            "workspace_b": workspace_b,
            "visible_memory_id": memory_a,
            "hidden_memory_id": memory_b,
            "hidden_noise_count": hidden_noise_count,
            "limited_token_forbidden": True,
            "gateway_scope": gateway_scope,
            "secret_leaked": False,
            "token_omitted": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        for token_id in token_ids:
            revoke(args.base_url, admin_key, token_id)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
