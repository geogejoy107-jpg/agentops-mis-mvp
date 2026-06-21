#!/usr/bin/env python3
"""Smoke-test Agent Gateway workspace isolation without printing token secrets."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def http_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict | None = None,
    token: str | None = None,
    workspace_header: str | None = None,
    query: dict | None = None,
    timeout: int = 30,
) -> tuple[int, dict]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    headers = {"Content-Type": "application/json"}
    if workspace_header:
        headers["X-AgentOps-Workspace-Id"] = workspace_header
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def create_task(base_url: str, task_id: str, workspace_id: str, agent_id: str, title: str) -> None:
    status, body = http_json("POST", base_url, "/api/tasks", {
        "task_id": task_id,
        "workspace_id": workspace_id,
        "title": title,
        "description": f"Workspace isolation smoke task for {workspace_id}.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Only the matching workspace token may access this task.",
    })
    require(status == 201, f"task create failed for {task_id}: {status} {body}")


def create_verified_plan(base_url: str, workspace_id: str, agent_id: str, task_id: str, token: str) -> str:
    status, plan = http_json("POST", base_url, "/api/agent-gateway/agent-plans", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "task_understanding": "Verify workspace isolation with a plan-bound run.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["scripts/workspace_isolation_smoke.py"],
        "risk_level": "low",
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "VERIFY"],
        "verification_plan": "Run workspace_isolation_smoke.py.",
        "rollback_plan": "Keep the task planned if plan-bound run_start fails.",
        "status": "submitted",
    }, token=token, workspace_header=workspace_id)
    require(status == 201, f"plan create failed for {task_id}: {status} {plan}")
    plan_id = (plan.get("agent_plan") or {}).get("plan_id")
    require(bool(plan_id), f"plan id missing for {task_id}: {plan}")
    status, verified = http_json("GET", base_url, f"/api/agent-gateway/agent-plans/{plan_id}/verify", token=token, workspace_header=workspace_id)
    require(status == 200 and (verified.get("verification") or {}).get("pass") is True, f"plan verify failed for {task_id}: {status} {verified}")
    return str(plan_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Agent Gateway token workspace isolation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args(argv)

    stamp = now_stamp()
    agent_id = f"agt_workspace_iso_smoke_{stamp}"
    workspace_a = f"ws_iso_a_{stamp}"
    workspace_b = f"ws_iso_b_{stamp}"
    task_a = f"tsk_workspace_iso_a_{stamp}"
    task_b = f"tsk_workspace_iso_b_{stamp}"
    token_id = None
    token_b_id = None
    token = None
    token_b = None
    result = {
        "ok": False,
        "agent_id": agent_id,
        "workspace_a": workspace_a,
        "workspace_b": workspace_b,
        "task_a": task_a,
        "task_b": task_b,
        "token_omitted": True,
    }

    try:
        status, created = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/create", {
            "workspace_id": workspace_a,
            "agent_id": agent_id,
            "name": "Workspace Isolation Smoke",
            "runtime_type": "mock",
            "scopes": ["agents:heartbeat", "tasks:read", "tasks:claim", "agent_plans:read", "agent_plans:write", "runs:write", "toolcalls:write", "evaluations:submit", "audit:write"],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        })
        require(status == 201, f"enrollment create failed: {status} {created}")
        token = created["token"]
        token_id = created["token_id"]
        result["token_id"] = token_id

        status, created_b = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/create", {
            "workspace_id": workspace_b,
            "agent_id": agent_id,
            "name": "Workspace Isolation Smoke B",
            "runtime_type": "mock",
            "scopes": ["agents:heartbeat", "tasks:read", "tasks:claim", "agent_plans:read", "agent_plans:write", "runs:write", "toolcalls:write", "artifacts:write", "approvals:request", "evaluations:submit", "audit:write"],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        })
        require(status == 201, f"workspace B enrollment create failed: {status} {created_b}")
        token_b = created_b["token"]
        token_b_id = created_b["token_id"]
        result["token_b_id"] = token_b_id

        create_task(args.base_url, task_a, workspace_a, agent_id, "workspace A isolation smoke")
        create_task(args.base_url, task_b, workspace_b, agent_id, "workspace B isolation smoke")

        status, pulled = http_json(
            "GET",
            args.base_url,
            "/api/agent-gateway/tasks/pull",
            token=token,
            workspace_header=workspace_a,
            query={"status": "planned", "limit": 20},
        )
        require(status == 200, f"pull failed: {status} {pulled}")
        task_ids = {item.get("task_id") for item in pulled.get("tasks", [])}
        require(task_a in task_ids, f"workspace A task missing from pull: {task_ids}")
        require(task_b not in task_ids, f"workspace B task leaked into pull: {task_ids}")

        status, header_spoof = http_json(
            "GET",
            args.base_url,
            "/api/agent-gateway/tasks/pull",
            token=token,
            workspace_header=workspace_b,
            query={"status": "planned", "limit": 20},
        )
        require(status == 403, f"header spoof should fail: {status} {header_spoof}")

        status, query_spoof = http_json(
            "GET",
            args.base_url,
            "/api/agent-gateway/tasks/pull",
            token=token,
            workspace_header=workspace_a,
            query={"workspace_id": workspace_b, "status": "planned", "limit": 20},
        )
        require(status == 403, f"query spoof should fail: {status} {query_spoof}")

        status, claim_b = http_json(
            "POST",
            args.base_url,
            f"/api/agent-gateway/tasks/{task_b}/claim",
            payload={"workspace_id": workspace_a, "runtime_type": "mock"},
            token=token,
            workspace_header=workspace_a,
        )
        require(status == 403, f"cross-workspace claim should fail: {status} {claim_b}")

        status, start_b = http_json(
            "POST",
            args.base_url,
            "/api/agent-gateway/runs/start",
            payload={"workspace_id": workspace_a, "task_id": task_b, "runtime_type": "mock"},
            token=token,
            workspace_header=workspace_a,
        )
        require(status == 403, f"cross-workspace run start should fail: {status} {start_b}")

        status, claim_b_owner = http_json(
            "POST",
            args.base_url,
            f"/api/agent-gateway/tasks/{task_b}/claim",
            payload={"workspace_id": workspace_b, "runtime_type": "mock"},
            token=token_b,
            workspace_header=workspace_b,
        )
        require(status == 200, f"workspace B owner claim failed: {status} {claim_b_owner}")

        plan_b = create_verified_plan(args.base_url, workspace_b, agent_id, task_b, token_b)
        status, start_b_owner = http_json(
            "POST",
            args.base_url,
            "/api/agent-gateway/runs/start",
            payload={"workspace_id": workspace_b, "task_id": task_b, "runtime_type": "mock", "agent_plan_id": plan_b},
            token=token_b,
            workspace_header=workspace_b,
        )
        require(status in {200, 201}, f"workspace B owner run start failed: {status} {start_b_owner}")
        run_b_id = (start_b_owner.get("run") or {}).get("run_id")
        require(bool(run_b_id), f"workspace B run_id missing: {start_b_owner}")

        cross_write_checks = {}
        cross_write_payloads = [
            ("run_heartbeat", "POST", f"/api/agent-gateway/runs/{run_b_id}/heartbeat", {"workspace_id": workspace_a, "status": "completed", "output_summary": "should be blocked"}),
            ("tool_call", "POST", "/api/agent-gateway/tool-calls", {"workspace_id": workspace_a, "run_id": run_b_id, "tool_name": "workspace.isolation.blocked"}),
            ("artifact", "POST", "/api/agent-gateway/artifacts", {"workspace_id": workspace_a, "run_id": run_b_id, "title": "blocked artifact", "summary": "should be blocked"}),
            ("approval", "POST", "/api/agent-gateway/approvals/request", {"workspace_id": workspace_a, "run_id": run_b_id, "reason": "should be blocked"}),
            ("evaluation", "POST", "/api/agent-gateway/evaluations/submit", {"workspace_id": workspace_a, "run_id": run_b_id, "score": 1.0}),
            ("audit", "POST", "/api/agent-gateway/audit", {"workspace_id": workspace_a, "run_id": run_b_id, "action": "workspace.isolation.blocked"}),
        ]
        for label, method, path, payload in cross_write_payloads:
            status, blocked = http_json(
                method,
                args.base_url,
                path,
                payload=payload,
                token=token,
                workspace_header=workspace_a,
            )
            require(status == 403, f"cross-workspace {label} should fail: {status} {blocked}")
            cross_write_checks[label] = blocked.get("error")

        status, claim_a = http_json(
            "POST",
            args.base_url,
            f"/api/agent-gateway/tasks/{task_a}/claim",
            payload={"workspace_id": workspace_a, "runtime_type": "mock"},
            token=token,
            workspace_header=workspace_a,
        )
        require(status == 200, f"workspace A claim failed: {status} {claim_a}")

        plan_a = create_verified_plan(args.base_url, workspace_a, agent_id, task_a, token)
        status, start_a = http_json(
            "POST",
            args.base_url,
            "/api/agent-gateway/runs/start",
            payload={"workspace_id": workspace_a, "task_id": task_a, "runtime_type": "mock", "agent_plan_id": plan_a},
            token=token,
            workspace_header=workspace_a,
        )
        require(status in {200, 201}, f"workspace A run start failed: {status} {start_a}")
        run_id = (start_a.get("run") or {}).get("run_id")
        require(bool(run_id), f"run_id missing from start response: {start_a}")

        status, heartbeat = http_json(
            "POST",
            args.base_url,
            f"/api/agent-gateway/runs/{run_id}/heartbeat",
            payload={"workspace_id": workspace_a, "status": "completed", "output_summary": "Workspace isolation smoke completed."},
            token=token,
            workspace_header=workspace_a,
        )
        require(status == 200, f"workspace A heartbeat failed: {status} {heartbeat}")

        result.update({
            "ok": True,
            "run_id": run_id,
            "pull_count": pulled.get("count"),
            "header_spoof_status": header_spoof.get("error"),
            "query_spoof_status": query_spoof.get("error"),
            "cross_claim_status": claim_b.get("error"),
            "cross_start_status": start_b.get("error"),
            "cross_write_statuses": cross_write_checks,
            "run_b": run_b_id,
        })
        return 0
    except Exception as exc:
        result["error"] = str(exc)
        return 1
    finally:
        if token_id:
            status, revoked = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
            result["revocation"] = {"status": status, "revoked": revoked.get("revoked") if isinstance(revoked, dict) else None}
        if token_b_id:
            status, revoked = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_b_id})
            result["revocation_b"] = {"status": status, "revoked": revoked.get("revoked") if isinstance(revoked, dict) else None}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
