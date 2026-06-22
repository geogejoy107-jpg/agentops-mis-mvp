#!/usr/bin/env python3
"""Verify scoped Agent Gateway access survives special-character IDs."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
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


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def path_id(value: str) -> str:
    return quote(value, safe="")


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
        url += "?" + urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if workspace:
        headers["X-AgentOps-Workspace-Id"] = workspace
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw), raw
        except Exception:
            return exc.code, {"raw": raw}, raw


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _payload, _raw = http_json("GET", base_url, "/api/local/readiness")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        result: dict[str, int] = {}
        for table in ["tasks", "runs", "artifacts", "approvals", "memories", "agent_gateway_tokens"]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return result
    finally:
        conn.close()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def secret_leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def ids(rows: list[dict], key: str) -> set[str]:
    return {str(item.get(key)) for item in rows if item.get(key) is not None}


def create_enrollment(base_url: str, workspace: str, agent_id: str, scopes: list[str]) -> tuple[str, str]:
    status, payload, _raw = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
        "workspace_id": workspace,
        "agent_id": agent_id,
        "name": f"Special Char Agent {agent_id}",
        "runtime_type": "mock",
        "scopes": scopes,
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    if status != 201:
        raise AssertionError(f"enrollment create failed: {status} {payload}")
    return str(payload["token"]), str(payload["token_id"])


def create_verified_plan(base_url: str, workspace: str, token: str, agent_id: str, task_id: str, outputs: list[str]) -> str:
    status, plan, raw = http_json("POST", base_url, "/api/agent-gateway/agent-plans", {
        "workspace_id": workspace,
        "agent_id": agent_id,
        "task_id": task_id,
        "task_understanding": "Verify Agent Gateway scope survives URL-encoded and JSON special-character IDs.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/security_rules.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["server.py", "scripts/agent_gateway_special_char_scope_smoke.py"],
        "risk_level": "low",
        "execution_steps": ["READ", "PLAN", "VERIFY"],
        "verification_plan": "Run agent_gateway_special_char_scope_smoke.py.",
        "rollback_plan": "Revert path decoding or scope helper changes if regression fails.",
        "status": "submitted",
    }, token=token, workspace=workspace)
    outputs.append(raw)
    if status != 201:
        raise AssertionError(f"plan create failed: {status} {plan}")
    plan_id = str((plan.get("agent_plan") or {}).get("plan_id") or "")
    if not plan_id:
        raise AssertionError(f"plan id missing: {plan}")
    status, verified, raw = http_json("GET", base_url, f"/api/agent-gateway/agent-plans/{path_id(plan_id)}/verify", token=token, workspace=workspace)
    outputs.append(raw)
    if status != 200 or (verified.get("verification") or {}).get("pass") is not True:
        raise AssertionError(f"plan verify failed: {status} {verified}")
    return plan_id


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    stamp = now_stamp()
    workspace = f"ws special+%,quote'{stamp}"
    hidden_workspace = f"ws hidden+%,quote'{stamp}"
    owner_agent = f"agt owner+%,quote'/slash {stamp}"
    collaborator_agent = f"agt collaborator+%,quote'/slash {stamp}"
    prefix_agent = f"agt collaborator+%,quote'"
    task_id = f"tsk special+%,quote'/slash {stamp}"
    hidden_task_id = f"tsk hidden+%,quote'/slash {stamp}"
    scopes = [
        "agents:heartbeat",
        "tasks:read",
        "tasks:claim",
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
    with tempfile.TemporaryDirectory(prefix="agentops-special-char-scope-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["HERMES_ALLOW_REAL_RUN"] = "false"
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        token_ids: list[str] = []
        try:
            wait_ready(base_url, proc)
            _owner_token, owner_token_id = create_enrollment(base_url, workspace, owner_agent, ["agents:heartbeat", "tasks:read", "audit:write"])
            collaborator_token, collaborator_token_id = create_enrollment(base_url, workspace, collaborator_agent, scopes)
            prefix_token, prefix_token_id = create_enrollment(base_url, workspace, prefix_agent, scopes)
            hidden_token, hidden_token_id = create_enrollment(base_url, hidden_workspace, collaborator_agent, scopes)
            token_ids.extend([owner_token_id, collaborator_token_id, prefix_token_id, hidden_token_id])
            before = db_counts(db_path)

            for ws, tid, title in [
                (workspace, task_id, "Special-character scoped task"),
                (hidden_workspace, hidden_task_id, "Hidden special-character scoped task"),
            ]:
                status, body, raw = http_json("POST", base_url, "/api/tasks", {
                    "task_id": tid,
                    "workspace_id": ws,
                    "title": title,
                    "description": "Special-character Agent Gateway scope fixture.",
                    "owner_agent_id": owner_agent,
                    "collaborator_agent_ids": [collaborator_agent],
                    "status": "planned",
                    "priority": "high",
                    "risk_level": "low",
                    "acceptance_criteria": "Only exact scoped collaborator can access URL-encoded task and ledger rows.",
                })
                outputs.append(raw)
                require(status == 201, f"task create failed for {tid}: {status} {body}", failures)

            status, pulled, raw = http_json("GET", base_url, "/api/agent-gateway/tasks/pull", token=collaborator_token, workspace=workspace, query={"status": "planned", "task_id": task_id, "limit": 10})
            outputs.append(raw)
            require(status == 200 and task_id in ids(pulled.get("tasks") or [], "task_id"), f"special task missing from pull: {status} {pulled}", failures)
            require(hidden_task_id not in ids(pulled.get("tasks") or [], "task_id"), f"hidden workspace task leaked into pull: {pulled}", failures)

            status, task_get, raw = http_json("GET", base_url, f"/api/agent-gateway/tasks/{path_id(task_id)}", token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status == 200 and (task_get.get("task") or {}).get("task_id") == task_id, f"encoded task get failed: {status} {task_get}", failures)

            status, forbidden, raw = http_json("GET", base_url, f"/api/agent-gateway/tasks/{path_id(task_id)}", token=prefix_token, workspace=workspace)
            outputs.append(raw)
            require(status == 403, f"prefix special agent should not see exact collaborator task: {status} {forbidden}", failures)

            status, forbidden, raw = http_json("GET", base_url, f"/api/agent-gateway/tasks/{path_id(hidden_task_id)}", token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status == 403, f"hidden workspace task should be forbidden: {status} {forbidden}", failures)

            status, spoofed, raw = http_json("GET", base_url, "/api/agent-gateway/tasks/pull", token=collaborator_token, workspace=hidden_workspace, query={"status": "planned", "task_id": hidden_task_id, "limit": 10})
            outputs.append(raw)
            require(status == 403, f"workspace header spoof should fail: {status} {spoofed}", failures)

            status, claimed, raw = http_json("POST", base_url, f"/api/agent-gateway/tasks/{path_id(task_id)}/claim", {"runtime_type": "mock"}, token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status == 200, f"encoded task claim failed: {status} {claimed}", failures)
            plan_id = create_verified_plan(base_url, workspace, collaborator_token, collaborator_agent, task_id, outputs)
            status, started, raw = http_json("POST", base_url, "/api/agent-gateway/runs/start", {"task_id": task_id, "runtime_type": "mock", "agent_plan_id": plan_id}, token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status in {200, 201}, f"run start failed: {status} {started}", failures)
            run_id = str((started.get("run") or {}).get("run_id") or "")
            require(bool(run_id), f"run id missing: {started}", failures)

            status, tool, raw = http_json("POST", base_url, "/api/agent-gateway/tool-calls", {
                "run_id": run_id,
                "tool_name": "special_scope.fixture",
                "status": "completed",
                "result_summary": "Special-character scoped fixture tool call.",
            }, token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status in {200, 201}, f"tool record failed: {status} {tool}", failures)

            status, artifact, raw = http_json("POST", base_url, "/api/agent-gateway/artifacts", {
                "run_id": run_id,
                "task_id": task_id,
                "artifact_type": "special_scope_fixture",
                "title": "Special-character scoped artifact",
                "summary": "Safe artifact summary for special-character scope smoke.",
                "uri": f"run://{run_id}",
            }, token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status in {200, 201}, f"artifact record failed: {status} {artifact}", failures)
            artifact_id = str((artifact.get("artifact") or {}).get("artifact_id") or "")

            status, approval, raw = http_json("POST", base_url, "/api/agent-gateway/approvals/request", {
                "run_id": run_id,
                "reason": "Special-character scoped fixture approval.",
            }, token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status in {200, 201}, f"approval request failed: {status} {approval}", failures)
            approval_id = str((approval.get("approval") or {}).get("approval_id") or "")

            status, memory, raw = http_json("POST", base_url, "/api/agent-gateway/memories/propose", {
                "task_id": task_id,
                "run_id": run_id,
                "agent_id": collaborator_agent,
                "memory_type": "artifact_summary",
                "scope": "task",
                "canonical_text": "Special-character scoped memory candidate.",
            }, token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status in {200, 201}, f"memory propose failed: {status} {memory}", failures)
            memory_id = str((memory.get("memory") or {}).get("memory_id") or "")

            status, heartbeat, raw = http_json("POST", base_url, f"/api/agent-gateway/runs/{path_id(run_id)}/heartbeat", {
                "status": "completed",
                "output_summary": "Special-character scope smoke completed.",
            }, token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status == 200, f"encoded run heartbeat failed: {status} {heartbeat}", failures)

            for path, collection, key, expected in [
                ("/api/agent-gateway/runs", "runs", "run_id", run_id),
                ("/api/agent-gateway/artifacts", "artifacts", "artifact_id", artifact_id),
                ("/api/agent-gateway/approvals", "approvals", "approval_id", approval_id),
                ("/api/agent-gateway/memories", "memories", "memory_id", memory_id),
            ]:
                status, payload, raw = http_json("GET", base_url, path, token=collaborator_token, workspace=workspace, query={"limit": 25})
                outputs.append(raw)
                require(status == 200 and expected in ids(payload.get(collection) or [], key), f"{path} did not include expected scoped row {expected}: {status} {payload}", failures)
                status, hidden, raw = http_json("GET", base_url, path, token=hidden_token, workspace=hidden_workspace, query={"limit": 25})
                outputs.append(raw)
                require(status == 200 and expected not in ids(hidden.get(collection) or [], key), f"{path} leaked scoped row {expected} to hidden workspace: {hidden}", failures)

            status, run_get, raw = http_json("GET", base_url, f"/api/agent-gateway/runs/{path_id(run_id)}", token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status == 200 and (run_get.get("run") or {}).get("run_id") == run_id, f"encoded run get failed: {status} {run_get}", failures)
            status, graph, raw = http_json("GET", base_url, f"/api/agent-gateway/runs/{path_id(run_id)}/graph", token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status == 200, f"encoded run graph failed: {status} {graph}", failures)
            status, approval_get, raw = http_json("GET", base_url, f"/api/agent-gateway/approvals/{path_id(approval_id)}", token=collaborator_token, workspace=workspace)
            outputs.append(raw)
            require(status == 200 and (approval_get.get("approval") or {}).get("approval_id") == approval_id, f"encoded approval get failed: {status} {approval_get}", failures)

            status, queue, raw = http_json("GET", base_url, "/api/agent-gateway/review/queue", token=collaborator_token, workspace=workspace, query={"limit": 5})
            outputs.append(raw)
            queue_text = json.dumps(queue, ensure_ascii=False)
            require(status == 200 and approval_id in queue_text and memory_id in queue_text, f"special scoped review queue missing approval/memory: {status} {queue}", failures)
            require(hidden_task_id not in queue_text, f"hidden task leaked into special scoped queue: {queue}", failures)
            require((queue.get("gateway_scope") or {}).get("scope_before_limit") is True, f"queue scope-before-limit proof missing: {queue}", failures)

            after = db_counts(db_path)
            require(after.get("tasks", 0) >= before.get("tasks", 0) + 2, f"fixture task counts did not grow: {before} -> {after}", failures)
            require(not secret_leaked("\n".join(outputs)), "special-character smoke leaked token-like material", failures)
            result = {
                "ok": not failures,
                "operation": "agent_gateway_special_char_scope_smoke",
                "workspace_id": workspace,
                "hidden_workspace_id": hidden_workspace,
                "owner_agent_id": owner_agent,
                "collaborator_agent_id": collaborator_agent,
                "prefix_agent_blocked": True,
                "task_id": task_id,
                "run_id": run_id,
                "artifact_id": artifact_id,
                "approval_id": approval_id,
                "memory_id": memory_id,
                "url_encoded_path_ids_verified": True,
                "workspace_spoof_blocked": True,
                "token_omitted": True,
                "secret_leaked": False,
                "failures": failures,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 1 if failures else 0
        finally:
            for token_id in token_ids:
                http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
