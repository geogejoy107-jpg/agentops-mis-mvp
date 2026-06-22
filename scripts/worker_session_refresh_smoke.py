#!/usr/bin/env python3
"""Verify a long-running worker refreshes short-lived Agent Gateway sessions."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def create_task(base_url: str, agent_id: str, task_id: str, index: int) -> None:
    status, payload = http_json("POST", base_url, "/api/tasks", {
        "task_id": task_id,
        "workspace_id": "local-demo",
        "title": f"session refresh worker smoke task {index}",
        "description": "Verify a remote worker can rotate short-lived sessions while staying in the same loop.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "medium",
        "risk_level": "low",
        "acceptance_criteria": "Worker must complete the task with run/tool/evaluation ledger evidence.",
    })
    require(status == 201, f"task create failed: {status} {payload}")


def run_worker(base_url: str, agent_id: str, token: str) -> dict:
    env = os.environ.copy()
    env.update({
        "AGENTOPS_BASE_URL": base_url,
        "AGENTOPS_WORKSPACE_ID": "local-demo",
        "AGENTOPS_AGENT_ID": agent_id,
        "AGENTOPS_API_KEY": token,
    })
    cmd = [
        sys.executable,
        "scripts/agent_worker.py",
        "--adapter",
        "mock",
        "--max-tasks",
        "2",
        "--poll-interval",
        "0.1",
        "--use-session",
        "--session-ttl-sec",
        "2",
        "--session-refresh-margin-sec",
        "3600",
        "--no-enforce-intake",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180, check=False)
    require(proc.returncode == 0, f"worker failed: {proc.stderr or proc.stdout}")
    require(token not in proc.stdout and token not in proc.stderr, "worker output leaked raw enrollment token")
    try:
        return json.loads(proc.stdout or "{}")
    except Exception as exc:
        raise AssertionError(f"worker output was not JSON: {proc.stdout}") from exc


def verify_run(base_url: str, run_id: str) -> None:
    status, detail = http_json("GET", base_url, f"/api/runs/{run_id}")
    require(status == 200, f"run detail failed: {status} {detail}")
    run = detail.get("run") or {}
    tool_calls = detail.get("tool_calls") or []
    evaluations = detail.get("evaluations") or []
    require(run.get("status") == "completed", f"run not completed: {run}")
    require(any(item.get("tool_name") == "agent_worker.mock" and item.get("status") == "completed" for item in tool_calls), f"missing completed worker tool call: {tool_calls}")
    require(any(item.get("pass_fail") == "pass" for item in evaluations), f"missing pass evaluation: {evaluations}")


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_session_refresh_worker_{stamp}"
    token_id = None
    token = None
    try:
        status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
            "agent_id": agent_id,
            "name": "Worker Session Refresh Smoke",
            "runtime_type": "mock",
            "workspace_id": "local-demo",
            "scopes": [
                "agents:write",
                "agents:heartbeat",
                "knowledge:read",
                "agent_plans:read",
                "agent_plans:write",
                "plan_evidence:read",
                "plan_evidence:write",
                "tasks:create",
                "tasks:read",
                "tasks:claim",
                "runs:write",
                "toolcalls:write",
                "artifacts:write",
                "memories:propose",
                "evaluations:submit",
                "audit:write",
            ],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        })
        require(status == 201, f"enrollment create failed: {status} {created}")
        token = created.get("token")
        token_id = created.get("token_id")
        require(token and token_id, f"created enrollment missing one-time token: {created}")

        task_ids = [f"tsk_session_refresh_{stamp}_{idx}" for idx in (1, 2)]
        for idx, task_id in enumerate(task_ids, start=1):
            create_task(base_url, agent_id, task_id, idx)

        worker = run_worker(base_url, agent_id, token)
        require(worker.get("processed") == 2, f"worker did not process both tasks: {worker}")
        sessions = worker.get("sessions") or []
        session_ids = [item.get("session_id") for item in sessions if item.get("session_id")]
        require(len(set(session_ids)) >= 2, f"worker did not refresh session in loop: {worker}")
        require(worker.get("state", {}).get("session_refresh_count", 0) >= 1, f"refresh count missing: {worker}")

        run_ids = [item.get("run_id") for item in worker.get("results", []) if item.get("run_id")]
        require(len(run_ids) == 2, f"missing processed run ids: {worker}")
        for run_id in run_ids:
            verify_run(base_url, run_id)

        status, sessions_payload = http_json("GET", base_url, "/api/agent-gateway/sessions")
        require(status == 200, f"session list failed: {status} {sessions_payload}")
        serialized = json.dumps(sessions_payload, ensure_ascii=False)
        require("session_hash" not in serialized and token not in serialized, "session listing leaked secret material")

        return {
            "agent_id": agent_id,
            "task_ids": task_ids,
            "run_ids": run_ids,
            "token_id": token_id,
            "session_ids": session_ids,
            "session_refresh_count": worker.get("state", {}).get("session_refresh_count"),
            "token_omitted": True,
        }
    finally:
        if token_id:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify short-lived worker session refresh.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args(argv)
    result = {"ok": True, "base_url": args.base_url, "smoke": smoke(args.base_url, now_stamp())}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
