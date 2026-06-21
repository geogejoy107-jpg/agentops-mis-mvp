#!/usr/bin/env python3
"""Verify collaborator visibility uses exact membership, not substring LIKE."""

from __future__ import annotations

import datetime as dt
import json
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
    workspace: str | None = None,
    query: dict | None = None,
) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if workspace:
        headers["X-AgentOps-Workspace-Id"] = workspace
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


def create_enrollment(base_url: str, workspace: str, agent_id: str, scopes: list[str]) -> tuple[str, str]:
    status, created, _raw = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "workspace_id": workspace,
        "agent_id": agent_id,
        "name": f"Exact Scope {agent_id}",
        "runtime_type": "mock",
        "scopes": scopes,
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    require(status == 201, f"enrollment create failed for {agent_id}: {status} {created}")
    return created["token"], created["token_id"]


def create_verified_plan(base_url: str, workspace: str, token: str, agent_id: str, task_id: str, outputs: list[str]) -> str:
    status, plan, raw = http_json("POST", base_url, "/api/agent-gateway/agent-plans", {
        "workspace_id": workspace,
        "agent_id": agent_id,
        "task_id": task_id,
        "task_understanding": "Verify exact collaborator membership for prefix-collision agent ids.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/security_rules.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["server.py", "scripts/collaborator_exact_scope_smoke.py"],
        "risk_level": "low",
        "execution_steps": ["READ", "PLAN", "VERIFY"],
        "verification_plan": "Run collaborator_exact_scope_smoke.py.",
        "rollback_plan": "Revert collaborator visibility SQL helper changes.",
        "status": "submitted",
    }, token=token, workspace=workspace)
    outputs.append(raw)
    require(status == 201, f"plan create failed: {status} {plan}")
    plan_id = (plan.get("agent_plan") or {}).get("plan_id")
    require(bool(plan_id), f"plan id missing: {plan}")
    status, verified, raw = http_json("GET", base_url, f"/api/agent-gateway/agent-plans/{plan_id}/verify", token=token, workspace=workspace)
    outputs.append(raw)
    require(status == 200 and (verified.get("verification") or {}).get("pass") is True, f"plan verify failed: {status} {verified}")
    return str(plan_id)


def ids(rows: list[dict], key: str) -> set[str]:
    return {str(item.get(key)) for item in rows if item.get(key)}


def assert_list_visibility(base_url: str, workspace: str, token: str, path: str, collection: str, key: str, expected_id: str, should_see: bool, outputs: list[str]) -> None:
    status, payload, raw = http_json("GET", base_url, path, token=token, workspace=workspace, query={"limit": 50})
    outputs.append(raw)
    require(status == 200, f"{path} list failed: {status} {payload}")
    visible = expected_id in ids(payload.get(collection) or [], key)
    require(visible is should_see, f"{path} visibility for {expected_id} expected {should_see}, got {visible}: {payload}")


def main(argv: list[str] | None = None) -> int:
    base_url = (argv or sys.argv[1:] or ["http://127.0.0.1:8787"])[0]
    stamp = now_stamp()
    workspace = f"ws_exact_scope_{stamp}"
    prefix_agent = f"agt_exact_{stamp}"
    exact_collaborator = f"{prefix_agent}_extra"
    owner_agent = f"{prefix_agent}_owner"
    task_id = f"tsk_exact_scope_{stamp}"
    output_chunks: list[str] = []
    token_ids: list[str] = []

    scopes = [
        "agents:heartbeat",
        "tasks:read",
        "agent_plans:read",
        "agent_plans:write",
        "runs:write",
        "toolcalls:write",
        "artifacts:write",
        "approvals:request",
        "memories:propose",
        "evaluations:submit",
        "audit:write",
    ]

    try:
        prefix_token, prefix_token_id = create_enrollment(base_url, workspace, prefix_agent, scopes)
        collaborator_token, collaborator_token_id = create_enrollment(base_url, workspace, exact_collaborator, scopes)
        _owner_token, owner_token_id = create_enrollment(base_url, workspace, owner_agent, ["agents:heartbeat", "tasks:read", "audit:write"])
        token_ids.extend([prefix_token_id, collaborator_token_id, owner_token_id])

        status, task, raw = http_json("POST", base_url, "/api/tasks", {
            "task_id": task_id,
            "workspace_id": workspace,
            "title": "Exact collaborator prefix-collision smoke",
            "description": "Agent id prefix must not grant collaborator access by substring match.",
            "owner_agent_id": owner_agent,
            "collaborator_agent_ids": [exact_collaborator],
            "status": "planned",
            "priority": "high",
            "risk_level": "low",
            "acceptance_criteria": "Only the exact collaborator can read task-linked rows.",
        })
        output_chunks.append(raw)
        require(status == 201, f"task create failed: {status} {task}")

        for token, should_see in [(prefix_token, False), (collaborator_token, True)]:
            status, pulled, raw = http_json("GET", base_url, "/api/agent-gateway/tasks/pull", token=token, workspace=workspace, query={"status": "planned", "limit": 50, "task_id": task_id})
            output_chunks.append(raw)
            require(status == 200, f"task pull failed: {status} {pulled}")
            visible = task_id in ids(pulled.get("tasks") or [], "task_id")
            require(visible is should_see, f"task pull visibility expected {should_see}, got {visible}: {pulled}")
            assert_list_visibility(base_url, workspace, token, "/api/agent-gateway/tasks", "tasks", "task_id", task_id, should_see, output_chunks)

        plan_id = create_verified_plan(base_url, workspace, collaborator_token, exact_collaborator, task_id, output_chunks)
        status, started, raw = http_json("POST", base_url, "/api/agent-gateway/runs/start", {
            "task_id": task_id,
            "runtime_type": "mock",
            "agent_plan_id": plan_id,
        }, token=collaborator_token, workspace=workspace)
        output_chunks.append(raw)
        require(status in {200, 201}, f"run start failed: {status} {started}")
        run_id = (started.get("run") or {}).get("run_id")
        require(bool(run_id), f"run id missing: {started}")

        status, tool, raw = http_json("POST", base_url, "/api/agent-gateway/tool-calls", {
            "run_id": run_id,
            "tool_name": "exact_scope.fixture",
            "status": "completed",
            "result_summary": "Exact collaborator scope fixture.",
        }, token=collaborator_token, workspace=workspace)
        output_chunks.append(raw)
        require(status in {200, 201}, f"tool record failed: {status} {tool}")

        status, artifact, raw = http_json("POST", base_url, "/api/agent-gateway/artifacts", {
            "run_id": run_id,
            "task_id": task_id,
            "artifact_type": "exact_scope_fixture",
            "title": "Exact collaborator fixture artifact",
            "summary": "Artifact tied to a task whose collaborator id has a prefix-collision neighbor.",
            "uri": f"run://{run_id}",
        }, token=collaborator_token, workspace=workspace)
        output_chunks.append(raw)
        require(status in {200, 201}, f"artifact record failed: {status} {artifact}")
        artifact_id = (artifact.get("artifact") or {}).get("artifact_id")
        require(bool(artifact_id), f"artifact id missing: {artifact}")

        status, approval, raw = http_json("POST", base_url, "/api/agent-gateway/approvals/request", {
            "run_id": run_id,
            "reason": "Exact collaborator scope fixture approval.",
        }, token=collaborator_token, workspace=workspace)
        output_chunks.append(raw)
        require(status in {200, 201}, f"approval request failed: {status} {approval}")
        approval_id = (approval.get("approval") or {}).get("approval_id")
        require(bool(approval_id), f"approval id missing: {approval}")

        status, memory, raw = http_json("POST", base_url, "/api/agent-gateway/memories/propose", {
            "task_id": task_id,
            "run_id": run_id,
            "agent_id": exact_collaborator,
            "memory_type": "artifact_summary",
            "scope": "task",
            "canonical_text": "Exact collaborator membership smoke memory candidate.",
        }, token=collaborator_token, workspace=workspace)
        output_chunks.append(raw)
        require(status in {200, 201}, f"memory propose failed: {status} {memory}")
        memory_id = (memory.get("memory") or {}).get("memory_id")
        require(bool(memory_id), f"memory id missing: {memory}")

        status, heartbeat, raw = http_json("POST", base_url, f"/api/agent-gateway/runs/{run_id}/heartbeat", {
            "status": "completed",
            "output_summary": "Exact collaborator visibility smoke completed.",
        }, token=collaborator_token, workspace=workspace)
        output_chunks.append(raw)
        require(status == 200, f"run heartbeat failed: {status} {heartbeat}")

        for token, should_see in [(prefix_token, False), (collaborator_token, True)]:
            assert_list_visibility(base_url, workspace, token, "/api/agent-gateway/runs", "runs", "run_id", run_id, should_see, output_chunks)
            assert_list_visibility(base_url, workspace, token, "/api/agent-gateway/artifacts", "artifacts", "artifact_id", artifact_id, should_see, output_chunks)
            assert_list_visibility(base_url, workspace, token, "/api/agent-gateway/approvals", "approvals", "approval_id", approval_id, should_see, output_chunks)
            assert_list_visibility(base_url, workspace, token, "/api/agent-gateway/memories", "memories", "memory_id", memory_id, should_see, output_chunks)

        require(not secret_leaked("\n".join(output_chunks)), "collaborator exact scope smoke leaked token-like material")
        print(json.dumps({
            "ok": True,
            "workspace_id": workspace,
            "prefix_agent": prefix_agent,
            "exact_collaborator": exact_collaborator,
            "owner_agent": owner_agent,
            "task_id": task_id,
            "run_id": run_id,
            "artifact_id": artifact_id,
            "approval_id": approval_id,
            "memory_id": memory_id,
            "prefix_collision_blocked": True,
            "exact_collaborator_allowed": True,
            "token_omitted": True,
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        for token_id in token_ids:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
