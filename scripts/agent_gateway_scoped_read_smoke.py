#!/usr/bin/env python3
"""Verify Agent Gateway readback endpoints enforce scoped workspace visibility."""
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
) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if workspace_header:
        headers["X-AgentOps-Workspace-Id"] = workspace_header
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require_scope_service(payload: dict, label: str) -> None:
    scope = payload.get("gateway_scope") or {}
    require(scope.get("scope_service") == "agent_gateway_scope_v1", f"{label} missing unified scope service: {scope}")
    require(scope.get("bound_visibility_enforced") is True, f"{label} missing bound visibility proof: {scope}")


def create_verified_plan(base_url: str, token: str, workspace: str, agent_id: str, task_id: str, output_chunks: list[str]) -> str:
    status, plan, raw = http_json("POST", base_url, "/api/agent-gateway/agent-plans", {
        "workspace_id": workspace,
        "agent_id": agent_id,
        "task_id": task_id,
        "task_understanding": "Verify scoped read smoke can create a plan-bound run.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["scripts/agent_gateway_scoped_read_smoke.py"],
        "risk_level": "low",
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "VERIFY"],
        "verification_plan": "Run scoped read smoke.",
        "rollback_plan": "Keep task running if plan-bound run_start fails.",
        "status": "submitted",
    }, token=token, workspace_header=workspace)
    output_chunks.append(raw)
    require(status == 201, f"plan create failed: {status} {plan}")
    plan_id = (plan.get("agent_plan") or {}).get("plan_id")
    require(bool(plan_id), f"plan id missing: {plan}")
    status, verified, raw = http_json("GET", base_url, f"/api/agent-gateway/agent-plans/{plan_id}/verify", token=token, workspace_header=workspace)
    output_chunks.append(raw)
    require(status == 200 and (verified.get("verification") or {}).get("pass") is True, f"plan verify failed: {status} {verified}")
    return plan_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Agent Gateway scoped readback endpoints.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    base_url = args.base_url
    stamp = now_stamp()
    agent_id = f"agt_scoped_read_{stamp}"
    workspace_a = f"ws_read_a_{stamp}"
    workspace_b = f"ws_read_b_{stamp}"
    task_a = f"tsk_scoped_read_a_{stamp}"
    task_b = f"tsk_scoped_read_b_{stamp}"
    token_id = None
    token = None
    output_chunks: list[str] = []
    try:
        status, created, raw = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
            "workspace_id": workspace_a,
            "agent_id": agent_id,
            "name": "Scoped Read Smoke",
            "runtime_type": "mock",
            "scopes": ["agents:heartbeat", "tasks:read", "tasks:claim", "agent_plans:read", "agent_plans:write", "runs:write", "toolcalls:write", "artifacts:write", "evaluations:submit", "audit:write"],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        })
        require(status == 201, f"enrollment create failed: {status} {created}")
        token = created["token"]
        token_id = created["token_id"]

        for workspace, task_id, title in [
            (workspace_a, task_a, "scoped read workspace A task"),
            (workspace_b, task_b, "scoped read workspace B task"),
        ]:
            status, body, raw = http_json("POST", base_url, "/api/tasks", {
                "task_id": task_id,
                "workspace_id": workspace,
                "title": title,
                "description": "Scoped read smoke fixture.",
                "owner_agent_id": agent_id,
                "status": "planned",
                "priority": "high",
                "risk_level": "low",
                "acceptance_criteria": "Scoped read endpoints must not cross workspace boundaries.",
            })
            output_chunks.append(raw)
            require(status == 201, f"task create failed for {task_id}: {status} {body}")

        status, task_ok, raw = http_json("GET", base_url, f"/api/agent-gateway/tasks/{task_a}", token=token, workspace_header=workspace_a)
        output_chunks.append(raw)
        require(status == 200, f"task A scoped get failed: {status} {task_ok}")
        require((task_ok.get("task") or {}).get("task_id") == task_a, f"task A payload mismatch: {task_ok}")
        require_scope_service(task_ok, "task get")

        status, task_forbidden, raw = http_json("GET", base_url, f"/api/agent-gateway/tasks/{task_b}", token=token, workspace_header=workspace_a)
        output_chunks.append(raw)
        require(status == 403, f"task B scoped get should fail: {status} {task_forbidden}")

        status, task_list, raw = http_json("GET", base_url, "/api/agent-gateway/tasks", token=token, workspace_header=workspace_a, query={"limit": 50})
        output_chunks.append(raw)
        listed_task_ids = {item.get("task_id") for item in task_list.get("tasks") or []}
        require(status == 200, f"scoped task list failed: {status} {task_list}")
        require(task_a in listed_task_ids, f"task A missing from scoped list: {listed_task_ids}")
        require(task_b not in listed_task_ids, f"task B leaked into scoped list: {listed_task_ids}")
        require_scope_service(task_list, "task list")

        status, claim, raw = http_json("POST", base_url, f"/api/agent-gateway/tasks/{task_a}/claim", {"runtime_type": "mock"}, token=token, workspace_header=workspace_a)
        output_chunks.append(raw)
        require(status == 200, f"claim A failed: {status} {claim}")

        plan_id = create_verified_plan(base_url, token, workspace_a, agent_id, task_a, output_chunks)
        status, started, raw = http_json("POST", base_url, "/api/agent-gateway/runs/start", {"task_id": task_a, "runtime_type": "mock", "agent_plan_id": plan_id}, token=token, workspace_header=workspace_a)
        output_chunks.append(raw)
        require(status in {200, 201}, f"run start failed: {status} {started}")
        run_id = (started.get("run") or {}).get("run_id")
        require(run_id, f"run id missing: {started}")

        status, tool, raw = http_json("POST", base_url, "/api/agent-gateway/tool-calls", {
            "run_id": run_id,
            "tool_name": "scoped_read.fixture",
            "status": "completed",
            "result_summary": "Scoped read fixture tool call.",
        }, token=token, workspace_header=workspace_a)
        output_chunks.append(raw)
        require(status in {200, 201}, f"tool record failed: {status} {tool}")

        status, artifact, raw = http_json("POST", base_url, "/api/agent-gateway/artifacts", {
            "run_id": run_id,
            "task_id": task_a,
            "artifact_type": "scoped_read_fixture",
            "title": "Scoped read fixture artifact",
            "summary": "Safe artifact summary for scoped read smoke.",
            "uri": f"run://{run_id}",
        }, token=token, workspace_header=workspace_a)
        output_chunks.append(raw)
        require(status in {200, 201}, f"artifact record failed: {status} {artifact}")
        artifact_id = (artifact.get("artifact") or {}).get("artifact_id")
        require(artifact_id, f"artifact id missing: {artifact}")

        status, heartbeat, raw = http_json("POST", base_url, f"/api/agent-gateway/runs/{run_id}/heartbeat", {
            "status": "completed",
            "output_summary": "Scoped read smoke completed.",
        }, token=token, workspace_header=workspace_a)
        output_chunks.append(raw)
        require(status == 200, f"run heartbeat failed: {status} {heartbeat}")

        status, run_get, raw = http_json("GET", base_url, f"/api/agent-gateway/runs/{run_id}", token=token, workspace_header=workspace_a)
        output_chunks.append(raw)
        require(status == 200, f"scoped run get failed: {status} {run_get}")
        require((run_get.get("run") or {}).get("run_id") == run_id, f"run get mismatch: {run_get}")
        require(len(run_get.get("tool_calls") or []) >= 1, f"run get missing tool evidence: {run_get}")
        require(len(run_get.get("artifacts") or []) >= 1, f"run get missing artifact evidence: {run_get}")
        require_scope_service(run_get, "run get")

        status, run_list, raw = http_json("GET", base_url, "/api/agent-gateway/runs", token=token, workspace_header=workspace_a, query={"task_id": task_a, "limit": 10})
        output_chunks.append(raw)
        listed_run_ids = {item.get("run_id") for item in run_list.get("runs") or []}
        require(status == 200, f"scoped run list failed: {status} {run_list}")
        require(run_id in listed_run_ids, f"run missing from scoped list: {run_list}")
        require_scope_service(run_list, "run list")

        status, artifact_list, raw = http_json("GET", base_url, "/api/agent-gateway/artifacts", token=token, workspace_header=workspace_a, query={"run_id": run_id, "limit": 10})
        output_chunks.append(raw)
        listed_artifact_ids = {item.get("artifact_id") for item in artifact_list.get("artifacts") or []}
        require(status == 200, f"scoped artifact list failed: {status} {artifact_list}")
        require(artifact_id in listed_artifact_ids, f"artifact missing from scoped list: {artifact_list}")
        require_scope_service(artifact_list, "artifact list")

        status, graph, raw = http_json("GET", base_url, f"/api/agent-gateway/runs/{run_id}/graph", token=token, workspace_header=workspace_a)
        output_chunks.append(raw)
        require(status == 200, f"scoped run graph failed: {status} {graph}")
        require_scope_service(graph, "run graph")

        require(not secret_leaked("\n".join(output_chunks)), "scoped read smoke leaked token-like material")
        print(json.dumps({
            "ok": True,
            "agent_id": agent_id,
            "workspace_a": workspace_a,
            "workspace_b": workspace_b,
            "task_a": task_a,
            "task_b_forbidden": True,
            "run_id": run_id,
            "artifact_id": artifact_id,
            "token_omitted": True,
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        if token_id:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
