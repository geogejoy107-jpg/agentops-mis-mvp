#!/usr/bin/env python3
"""Verify stuck worker task detection and operator release."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def old_iso(seconds: int = 3600) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds)).isoformat()


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None, query: dict | None = None) -> tuple[int, dict]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
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


def make_stale(task_id: str, run_id: str) -> None:
    stale_at = old_iso()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE tasks SET updated_at=? WHERE task_id=?", (stale_at, task_id))
        conn.execute("UPDATE runs SET started_at=?, created_at=? WHERE run_id=?", (stale_at, stale_at, run_id))
        conn.commit()


def create_verified_plan(base_url: str, agent_id: str, task_id: str) -> str:
    status, plan = http_json("POST", base_url, "/api/agent-gateway/agent-plans", {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "task_id": task_id,
        "task_understanding": "Start the worker task only after a verified plan is recorded.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["scripts/worker_stuck_recovery_smoke.py"],
        "risk_level": "low",
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "VERIFY"],
        "verification_plan": "Run worker_stuck_recovery_smoke.py.",
        "rollback_plan": "Release the task if plan-bound run_start fails.",
        "status": "submitted",
    })
    require(status == 201, f"plan create failed: {status} {plan}")
    plan_id = (plan.get("agent_plan") or {}).get("plan_id")
    require(bool(plan_id), f"plan id missing: {plan}")
    status, verified = http_json("GET", base_url, f"/api/agent-gateway/agent-plans/{plan_id}/verify")
    require(status == 200 and (verified.get("verification") or {}).get("pass") is True, f"plan verify failed: {status} {verified}")
    return str(plan_id)


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_worker_stuck_{stamp}"
    task_id = f"tsk_worker_stuck_{stamp}"
    token_id = None
    try:
        status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
            "agent_id": agent_id,
            "name": "Worker Stuck Recovery Smoke",
            "runtime_type": "mock",
            "workspace_id": "local-demo",
            "scopes": ["agents:heartbeat", "tasks:read", "tasks:claim", "runs:write", "audit:write"],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        })
        require(status == 201, f"enrollment create failed: {status} {created}")
        token = created["token"]
        token_id = created["token_id"]

        status, task = http_json("POST", base_url, "/api/tasks", {
            "task_id": task_id,
            "workspace_id": "local-demo",
            "title": "worker stuck recovery smoke task",
            "description": "Verify operator can release a stale running worker task.",
            "owner_agent_id": agent_id,
            "status": "planned",
            "priority": "high",
            "risk_level": "low",
            "acceptance_criteria": "Stale running task should be visible and releasable.",
        })
        require(status == 201, f"task create failed: {status} {task}")

        status, claim = http_json("POST", base_url, f"/api/agent-gateway/tasks/{task_id}/claim", {"runtime_type": "mock"}, token=token)
        require(status == 200, f"claim failed: {status} {claim}")
        plan_id = create_verified_plan(base_url, agent_id, task_id)
        status, start = http_json("POST", base_url, "/api/agent-gateway/runs/start", {"task_id": task_id, "runtime_type": "mock", "agent_plan_id": plan_id}, token=token)
        require(status in {200, 201}, f"run start failed: {status} {start}")
        run_id = (start.get("run") or {}).get("run_id")
        require(run_id, f"missing run id: {start}")

        make_stale(task_id, run_id)

        status, stuck = http_json("GET", base_url, "/api/workers/stuck-tasks", query={"threshold_sec": 30})
        require(status == 200, f"stuck list failed: {status} {stuck}")
        stuck_ids = {item.get("task_id") for item in stuck.get("stuck_tasks", [])}
        require(task_id in stuck_ids, f"stuck task missing: {stuck_ids}")

        status, released = http_json("POST", base_url, "/api/workers/tasks/release", {
            "task_id": task_id,
            "reason": "stuck recovery smoke",
        })
        require(status == 200 and released.get("released") is True, f"release failed: {status} {released}")
        require(run_id in released.get("released_runs", []), f"running run was not released: {released}")

        status, detail = http_json("GET", base_url, f"/api/tasks/{task_id}")
        require(status == 200, f"task detail failed: {status} {detail}")
        task_after = detail.get("task") or {}
        runs = detail.get("runs") or []
        released_run = next((run for run in runs if run.get("run_id") == run_id), {})
        require(task_after.get("status") == "planned" and not task_after.get("owner_agent_id"), f"task was not returned to queue: {task_after}")
        require(released_run.get("status") == "blocked" and released_run.get("error_type") == "WorkerTaskReleased", f"run was not blocked: {released_run}")

        return {
            "agent_id": agent_id,
            "task_id": task_id,
            "run_id": run_id,
            "released_runs": released.get("released_runs", []),
            "task_status_after": task_after.get("status"),
            "run_status_after": released_run.get("status"),
            "token_omitted": True,
        }
    finally:
        if token_id:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify stuck worker task recovery.")
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
