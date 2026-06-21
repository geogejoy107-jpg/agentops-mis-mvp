#!/usr/bin/env python3
"""Verify scoped Agent Gateway approval/memory list readback."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
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


def run_cli(base_url: str, token: str, workspace_id: str, agent_id: str, args: list[str]) -> tuple[int, dict, str]:
    with tempfile.TemporaryDirectory(prefix="agentops-reviewable-lists-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_BASE_URL"] = base_url.rstrip("/")
        env["AGENTOPS_API_KEY"] = token
        env["AGENTOPS_WORKSPACE_ID"] = workspace_id
        env["AGENTOPS_AGENT_ID"] = agent_id
        proc = subprocess.run(
            [str(CLI), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {}
    return proc.returncode, payload, proc.stdout + proc.stderr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def create_enrollment(base_url: str, admin_key: str | None, agent_id: str, workspace_id: str, scopes: list[str]) -> tuple[str, str]:
    status, payload, _raw = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "name": f"Reviewable Lists {agent_id}",
        "runtime_type": "mock",
        "scopes": scopes,
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    }, admin_key=admin_key)
    require(status == 201, f"enrollment create failed for {agent_id}: {status} {payload}")
    require(bool(payload.get("token_id") and payload.get("token")), f"token missing for {agent_id}: {payload}")
    return str(payload["token_id"]), str(payload["token"])


def create_task(base_url: str, workspace_id: str, agent_id: str, task_id: str) -> None:
    status, payload, _raw = http_json("POST", base_url, "/api/tasks", {
        "task_id": task_id,
        "workspace_id": workspace_id,
        "title": f"Scoped reviewable list fixture {task_id}",
        "description": "Fixture for approval/memory scoped list smoke.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Scoped approval and memory lists must not cross workspace boundaries.",
    })
    require(status in {200, 201}, f"task create failed for {task_id}: {status} {payload}")


def start_run(base_url: str, token: str, workspace_id: str, agent_id: str, task_id: str) -> str:
    status, plan, _raw = http_json("POST", base_url, "/api/agent-gateway/agent-plans", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "task_understanding": "Verify scoped reviewable list run is authorized by an Agent Plan.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["scripts/agent_gateway_reviewable_lists_smoke.py"],
        "risk_level": "low",
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "VERIFY"],
        "verification_plan": "Run scoped reviewable list smoke.",
        "rollback_plan": "Keep task planned if run_start fails.",
        "status": "submitted",
    }, token=token, workspace_header=workspace_id)
    require(status == 201, f"plan create failed for {task_id}: {status} {plan}")
    plan_id = (plan.get("agent_plan") or {}).get("plan_id")
    require(bool(plan_id), f"plan_id missing for {task_id}: {plan}")
    status, verified, _raw = http_json("GET", base_url, f"/api/agent-gateway/agent-plans/{plan_id}/verify", token=token, workspace_header=workspace_id)
    require(status == 200 and (verified.get("verification") or {}).get("pass") is True, f"plan verify failed for {task_id}: {status} {verified}")
    status, payload, _raw = http_json("POST", base_url, "/api/agent-gateway/runs/start", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "agent_plan_id": plan_id,
        "runtime_type": "mock",
        "input_summary": f"Scoped list run for {task_id}",
    }, token=token, workspace_header=workspace_id)
    require(status in {200, 201}, f"run start failed for {task_id}: {status} {payload}")
    run_id = (payload.get("run") or {}).get("run_id")
    require(bool(run_id), f"run_id missing for {task_id}: {payload}")
    return str(run_id)


def request_approval(base_url: str, token: str, workspace_id: str, agent_id: str, run_id: str, marker: str) -> tuple[str, str]:
    status, payload, raw = http_json("POST", base_url, "/api/agent-gateway/approvals/request", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "run_id": run_id,
        "reason": f"Scoped approval marker {marker}.",
    }, token=token, workspace_header=workspace_id)
    require(status == 201, f"approval request failed for {run_id}: {status} {payload}")
    approval_id = (payload.get("approval") or {}).get("approval_id")
    require(bool(approval_id), f"approval_id missing for {run_id}: {payload}")
    return str(approval_id), raw


def propose_memory(base_url: str, token: str, workspace_id: str, agent_id: str, task_id: str, marker: str) -> tuple[str, str]:
    status, payload, raw = http_json("POST", base_url, "/api/agent-gateway/memories/propose", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "scope": "task",
        "memory_type": "artifact_summary",
        "canonical_text": f"Scoped memory marker {marker}.",
        "source_ref": f"reviewable_lists_smoke:{task_id}",
        "access_tags": ["reviewable-lists-smoke", workspace_id],
        "confidence": 0.83,
    }, token=token, workspace_header=workspace_id)
    require(status in {200, 201}, f"memory propose failed for {task_id}: {status} {payload}")
    memory_id = (payload.get("memory") or {}).get("memory_id")
    require(bool(memory_id), f"memory_id missing for {task_id}: {payload}")
    return str(memory_id), raw


def revoke(base_url: str, admin_key: str | None, token_id: str) -> None:
    http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id}, admin_key=admin_key)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify scoped approval and memory list readback.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--admin-key", default=os.environ.get("AGENTOPS_ADMIN_KEY", ""))
    args = parser.parse_args()

    stamp = now_stamp()
    workspace_a = f"ws_lists_a_{stamp}"
    workspace_b = f"ws_lists_b_{stamp}"
    agent_a = f"agt_lists_a_{stamp}"
    agent_b = f"agt_lists_b_{stamp}"
    agent_limited = f"agt_lists_limited_{stamp}"
    task_a = f"tsk_lists_a_{stamp}"
    task_b = f"tsk_lists_b_{stamp}"
    marker_a = f"A {stamp}"
    marker_b = f"B {stamp}"
    admin_key = args.admin_key or None
    token_ids: list[str] = []
    outputs: list[str] = []

    try:
        scopes = ["tasks:read", "agent_plans:read", "agent_plans:write", "runs:write", "approvals:request", "memories:propose"]
        token_id_a, token_a = create_enrollment(args.base_url, admin_key, agent_a, workspace_a, scopes)
        token_id_b, token_b = create_enrollment(args.base_url, admin_key, agent_b, workspace_b, scopes)
        token_id_limited, token_limited = create_enrollment(args.base_url, admin_key, agent_limited, workspace_a, ["agents:heartbeat"])
        token_ids.extend([token_id_a, token_id_b, token_id_limited])

        create_task(args.base_url, workspace_a, agent_a, task_a)
        create_task(args.base_url, workspace_b, agent_b, task_b)
        run_a = start_run(args.base_url, token_a, workspace_a, agent_a, task_a)
        run_b = start_run(args.base_url, token_b, workspace_b, agent_b, task_b)
        approval_a, raw = request_approval(args.base_url, token_a, workspace_a, agent_a, run_a, marker_a)
        outputs.append(raw)
        approval_b, raw = request_approval(args.base_url, token_b, workspace_b, agent_b, run_b, marker_b)
        outputs.append(raw)
        memory_a, raw = propose_memory(args.base_url, token_a, workspace_a, agent_a, task_a, marker_a)
        outputs.append(raw)
        memory_b, raw = propose_memory(args.base_url, token_b, workspace_b, agent_b, task_b, marker_b)
        outputs.append(raw)

        status, approvals, raw = http_json(
            "GET",
            args.base_url,
            "/api/agent-gateway/approvals",
            token=token_a,
            workspace_header=workspace_a,
            query={"decision": "pending", "limit": 50},
        )
        outputs.append(raw)
        require(status == 200, f"approval list failed: {status} {approvals}")
        approval_payload = json.dumps(approvals, ensure_ascii=False)
        require(approval_a in approval_payload and marker_a in approval_payload, "workspace A approval missing from scoped list")
        require(approval_b not in approval_payload and marker_b not in approval_payload and task_b not in approval_payload, "workspace B approval leaked into scoped list")
        require((approvals.get("gateway_scope") or {}).get("bound_visibility_enforced") is True, f"approval scope missing: {approvals}")

        status, memories, raw = http_json(
            "GET",
            args.base_url,
            "/api/agent-gateway/memories",
            token=token_a,
            workspace_header=workspace_a,
            query={"status": "candidate", "limit": 50},
        )
        outputs.append(raw)
        memory_payload = json.dumps(memories, ensure_ascii=False)
        require(status == 200, f"memory list failed: {status} {memories}")
        require(memory_a in memory_payload and marker_a in memory_payload, "workspace A memory missing from scoped list")
        require(memory_b not in memory_payload and marker_b not in memory_payload and task_b not in memory_payload, "workspace B memory leaked into scoped list")
        require((memories.get("gateway_scope") or {}).get("bound_visibility_enforced") is True, f"memory scope missing: {memories}")

        for path in ["/api/agent-gateway/approvals", "/api/agent-gateway/memories"]:
            status, forbidden, raw = http_json("GET", args.base_url, path, token=token_limited, workspace_header=workspace_a, query={"limit": 5})
            outputs.append(raw)
            require(status == 403, f"limited token should be forbidden for {path}: {status} {forbidden}")
            require("tasks:read" in (forbidden.get("message") or ""), f"forbidden message should mention tasks:read: {forbidden}")

        approval_rc, approval_cli, raw = run_cli(args.base_url, token_a, workspace_a, agent_a, ["approval", "list", "--decision", "pending", "--limit", "50"])
        outputs.append(raw)
        require(approval_rc == 0, f"approval CLI failed: {approval_cli} {raw}")
        approval_cli_payload = json.dumps(approval_cli, ensure_ascii=False)
        require(approval_a in approval_cli_payload and marker_a in approval_cli_payload, "workspace A approval missing from CLI list")
        require(approval_b not in approval_cli_payload and marker_b not in approval_cli_payload and task_b not in approval_cli_payload, "workspace B approval leaked into CLI list")
        require(((approval_cli.get("gateway_scope") or {}).get("required_scope")) == "tasks:read", f"approval CLI scope missing: {approval_cli}")

        memory_rc, memory_cli, raw = run_cli(args.base_url, token_a, workspace_a, agent_a, ["memory", "list", "--status", "candidate", "--limit", "50"])
        outputs.append(raw)
        require(memory_rc == 0, f"memory CLI failed: {memory_cli} {raw}")
        memory_cli_payload = json.dumps(memory_cli, ensure_ascii=False)
        require(memory_a in memory_cli_payload and marker_a in memory_cli_payload, "workspace A memory missing from CLI list")
        require(memory_b not in memory_cli_payload and marker_b not in memory_cli_payload and task_b not in memory_cli_payload, "workspace B memory leaked into CLI list")
        require(((memory_cli.get("gateway_scope") or {}).get("required_scope")) == "tasks:read", f"memory CLI scope missing: {memory_cli}")

        require(not secret_leaked("\n".join(outputs)), "scoped reviewable list output leaked token-like material")
        print(json.dumps({
            "ok": True,
            "workspace_a": workspace_a,
            "workspace_b": workspace_b,
            "visible_approval_id": approval_a,
            "hidden_approval_id": approval_b,
            "visible_memory_id": memory_a,
            "hidden_memory_id": memory_b,
            "limited_token_forbidden": True,
            "cli_checked": True,
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
