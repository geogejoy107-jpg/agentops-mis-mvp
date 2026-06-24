#!/usr/bin/env python3
"""Verify scoped Agent Gateway task creation for remote agents."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
BASE_URL = "http://127.0.0.1:8787"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json(method: str, path: str, payload: dict | None = None, token: str | None = None, timeout: int = 60) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach MIS server: {exc.reason}") from exc


def run_cli(args: list[str], *, token: str, agent_id: str, workspace_id: str = "local-demo") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_API_KEY"] = token
    env["AGENTOPS_AGENT_ID"] = agent_id
    env["AGENTOPS_WORKSPACE_ID"] = workspace_id
    env["AGENTOPS_BASE_URL"] = BASE_URL
    env["AGENTOPS_CONFIG"] = str(ROOT / ".agentops_runtime" / "scope-smoke-config.json")
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def create_token(agent_id: str, scopes: list[str], workspace_id: str = "local-demo") -> tuple[str, str]:
    status, payload = http_json("POST", "/api/agent-gateway/enrollment/create", {
        "agent_id": agent_id,
        "workspace_id": workspace_id,
        "name": f"Task Create Scope Smoke {agent_id}",
        "role": "Remote Agent Gateway Smoke",
        "runtime_type": "mock",
        "scopes": scopes,
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    if status != 201:
        raise AssertionError(f"token create failed: {status} {payload}")
    return payload["token_id"], payload["token"]


def revoke(token_id: str) -> dict:
    _status, payload = http_json("POST", "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
    return payload


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str, raw_tokens: list[str]) -> bool:
    credential_pattern = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,})")
    return any(marker in text for marker in ["Authorization:", "Bearer "]) or bool(credential_pattern.search(text)) or any(token and token in text for token in raw_tokens)


def main() -> int:
    suffix = stamp()
    agent_id = f"agt_gateway_task_create_scope_{suffix}"
    other_agent_id = f"agt_gateway_task_create_other_{suffix}"
    task_id = f"tsk_gateway_task_create_scope_{suffix}"
    token_ids: list[str] = []
    raw_tokens: list[str] = []
    transcripts: list[str] = []
    try:
        allowed_token_id, allowed_token = create_token(agent_id, [
            "agents:write",
            "agents:heartbeat",
            "tasks:create",
            "tasks:read",
            "tasks:claim",
            "runs:write",
            "toolcalls:write",
            "evaluations:submit",
            "audit:write",
        ])
        token_ids.append(allowed_token_id)
        raw_tokens.append(allowed_token)
        no_create_token_id, no_create_token = create_token(f"{agent_id}_observer", ["agents:heartbeat", "tasks:read", "audit:write"])
        token_ids.append(no_create_token_id)
        raw_tokens.append(no_create_token)

        ok_proc = run_cli([
            "task",
            "create",
            "--task-id",
            task_id,
            "--title",
            "Scoped gateway task-create smoke",
            "--description",
            "A remote agent creates its own task through Agent Gateway.",
            "--owner-agent-id",
            agent_id,
            "--acceptance",
            "Task must be created under the bound agent and workspace.",
            "--priority",
            "high",
            "--risk",
            "low",
        ], token=allowed_token, agent_id=agent_id)
        transcripts.extend([ok_proc.stdout, ok_proc.stderr])
        ok_payload = load_json(ok_proc)
        task = ok_payload.get("task") or {}
        require(ok_proc.returncode == 0, f"allowed task create failed: {ok_proc.stderr or ok_proc.stdout}")
        require(ok_payload.get("operation") == "task_create", f"wrong operation: {ok_payload}")
        require(ok_payload.get("task_id") == task_id, f"wrong task id: {ok_payload}")
        require(task.get("owner_agent_id") == agent_id, f"task owner not bound to token agent: {task}")
        require(task.get("workspace_id") == "local-demo", f"task workspace not bound: {task}")

        missing_scope = run_cli([
            "task",
            "create",
            "--title",
            "This should be forbidden",
            "--owner-agent-id",
            f"{agent_id}_observer",
        ], token=no_create_token, agent_id=f"{agent_id}_observer")
        transcripts.extend([missing_scope.stdout, missing_scope.stderr])
        require(missing_scope.returncode != 0, "task create without tasks:create scope unexpectedly succeeded")
        require("tasks:create" in missing_scope.stderr, f"missing-scope error did not name scope: {missing_scope.stderr}")

        other_agent = run_cli([
            "task",
            "create",
            "--title",
            "This should not assign to another agent",
            "--owner-agent-id",
            other_agent_id,
        ], token=allowed_token, agent_id=agent_id)
        transcripts.extend([other_agent.stdout, other_agent.stderr])
        require(other_agent.returncode != 0, "bound token assigned task to another agent")
        require("forbidden" in other_agent.stderr.lower(), f"wrong other-agent error: {other_agent.stderr}")

        other_workspace = run_cli([
            "task",
            "create",
            "--title",
            "This should not cross workspace",
            "--owner-agent-id",
            agent_id,
        ], token=allowed_token, agent_id=agent_id, workspace_id="other-workspace")
        transcripts.extend([other_workspace.stdout, other_workspace.stderr])
        require(other_workspace.returncode != 0, "bound token created task in another workspace")
        require("workspace" in other_workspace.stderr.lower(), f"wrong workspace error: {other_workspace.stderr}")

        require(not secret_leaked("\n".join(transcripts), raw_tokens), "raw token leaked in CLI output")
        print(json.dumps({
            "ok": True,
            "agent_id": agent_id,
            "task_id": task_id,
            "allowed_token_id": allowed_token_id,
            "missing_scope_rejected": True,
            "other_agent_rejected": True,
            "other_workspace_rejected": True,
            "token_omitted": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        for token_id in token_ids:
            revoke(token_id)


if __name__ == "__main__":
    raise SystemExit(main())
