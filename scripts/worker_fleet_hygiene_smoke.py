#!/usr/bin/env python3
"""Verify read-only and confirmed cleanup paths for worker fleet hygiene."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "agentops_mis.db"


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


def make_stale(task_id: str, run_id: str, token_id: str) -> None:
    stale_at = old_iso()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE tasks SET updated_at=? WHERE task_id=?", (stale_at, task_id))
        conn.execute("UPDATE runs SET started_at=?, created_at=? WHERE run_id=?", (stale_at, stale_at, run_id))
        conn.execute("UPDATE agent_gateway_tokens SET created_at=?, last_used_at=NULL, last_heartbeat_at=NULL WHERE token_id=?", (stale_at, token_id))
        conn.commit()


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_worker_fleet_hygiene_{stamp}"
    task_id = f"tsk_fleet_hygiene_{stamp}"
    token_id = None
    try:
        status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
            "agent_id": agent_id,
            "name": "Fleet Hygiene Smoke",
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
            "title": "fleet hygiene smoke task",
            "description": "Verify fleet hygiene can plan and apply recovery safely.",
            "owner_agent_id": agent_id,
            "status": "planned",
            "priority": "high",
            "risk_level": "low",
            "acceptance_criteria": "Hygiene should release this stale task and revoke the never-seen enrollment.",
        })
        require(status == 201, f"task create failed: {status} {task}")

        status, claim = http_json("POST", base_url, f"/api/agent-gateway/tasks/{task_id}/claim", {"runtime_type": "mock"}, token=token)
        require(status == 200, f"claim failed: {status} {claim}")
        status, start = http_json("POST", base_url, "/api/agent-gateway/runs/start", {"task_id": task_id, "runtime_type": "mock"}, token=token)
        require(status in {200, 201}, f"run start failed: {status} {start}")
        run_id = (start.get("run") or {}).get("run_id")
        require(run_id, f"missing run id: {start}")

        make_stale(task_id, run_id, token_id)

        query = {"threshold_sec": 30, "enrollment_age_sec": 0, "limit": 20}
        status, plan = http_json("GET", base_url, "/api/workers/fleet/hygiene", query=query)
        require(status == 200, f"hygiene plan failed: {status} {plan}")
        require(plan.get("safety", {}).get("read_only") is True, f"plan should be read-only: {plan}")
        require(task_id in {item.get("task_id") for item in plan.get("stuck_tasks", [])}, f"stuck task missing from hygiene plan: {plan}")
        require(token_id in {item.get("token_id") for item in plan.get("stale_never_seen_enrollments", [])}, f"stale enrollment missing from hygiene plan: {plan}")

        status, rejected = http_json("POST", base_url, "/api/workers/fleet/hygiene", {**query, "apply": True})
        require(status == 409 and rejected.get("error") == "confirm_cleanup_required", f"cleanup should require confirmation: {status} {rejected}")

        status, applied = http_json("POST", base_url, "/api/workers/fleet/hygiene", {**query, "apply": True, "confirm_cleanup": True})
        require(status in {200, 207}, f"hygiene apply failed: {status} {applied}")
        released_ids = {item.get("task_id") for item in applied.get("released_tasks", [])}
        revoked_ids = {item.get("token_id") for item in applied.get("revoked_enrollments", [])}
        require(task_id in released_ids, f"task was not released by hygiene: {applied}")
        require(token_id in revoked_ids, f"enrollment was not revoked by hygiene: {applied}")

        status, detail = http_json("GET", base_url, f"/api/tasks/{task_id}")
        require(status == 200, f"task detail failed: {status} {detail}")
        task_after = detail.get("task") or {}
        runs = detail.get("runs") or []
        released_run = next((run for run in runs if run.get("run_id") == run_id), {})
        require(task_after.get("status") == "planned" and not task_after.get("owner_agent_id"), f"task was not returned to queue: {task_after}")
        require(released_run.get("status") == "blocked", f"run was not blocked: {released_run}")

        return {
            "agent_id": agent_id,
            "task_id": task_id,
            "run_id": run_id,
            "token_id": token_id,
            "planned_stuck_tasks": plan.get("summary", {}).get("stuck_tasks"),
            "planned_stale_enrollments": plan.get("summary", {}).get("stale_never_seen_enrollments"),
            "released_tasks": len(applied.get("released_tasks", [])),
            "revoked_enrollments": len(applied.get("revoked_enrollments", [])),
            "token_omitted": True,
        }
    finally:
        if token_id:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify worker fleet hygiene plan/apply.")
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
