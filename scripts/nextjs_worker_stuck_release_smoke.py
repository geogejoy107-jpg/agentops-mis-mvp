#!/usr/bin/env python3
"""Verify Next.js can release stuck worker tasks without exposing force release."""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_worker_stuck_release_v1"

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    free_port,
    leaked_secret,
    require,
    restore_next_env,
    run,
    start_process,
    wait_http,
)


def http_json_status(method: str, url: str, payload: dict[str, Any] | None = None, token: str | None = None) -> tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def post_form_no_redirect(url: str, payload: dict[str, str]) -> tuple[int, str]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=90) as response:
            return int(response.status), response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        if exc.code in {302, 303, 307, 308}:
            return int(exc.code), exc.headers.get("Location", "")
        raise


def old_iso(seconds: int = 3600) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds)).isoformat()


def make_stale(db_path: str, task_id: str, run_id: str) -> None:
    stale_at = old_iso()
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE tasks SET updated_at=? WHERE task_id=?", (stale_at, task_id))
        conn.execute("UPDATE runs SET started_at=?, created_at=? WHERE run_id=?", (stale_at, stale_at, run_id))
        conn.commit()


def create_running_worker_task(api_base: str, db_path: str, suffix: str) -> tuple[str, str, str]:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")
    agent_id = f"agt_worker_next_release_{stamp}_{suffix}"
    task_id = f"tsk_worker_next_release_{stamp}_{suffix}"
    status, created = http_json_status(
        "POST",
        f"{api_base}/api/agent-gateway/enrollment/create",
        {
            "agent_id": agent_id,
            "name": "Next Worker Release Smoke",
            "runtime_type": "mock",
            "workspace_id": "local-demo",
            "scopes": ["agents:heartbeat", "tasks:read", "tasks:claim", "runs:write", "audit:write"],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        },
    )
    require(status == 201, f"enrollment create failed: {status} {created}")
    token = str(created.get("token") or "")
    require(token, f"missing enrollment token: {created}")

    status, task = http_json_status(
        "POST",
        f"{api_base}/api/tasks",
        {
            "task_id": task_id,
            "workspace_id": "local-demo",
            "title": "next stuck worker release smoke task",
            "description": "Verify Next can release a stale running worker task.",
            "owner_agent_id": agent_id,
            "status": "planned",
            "priority": "high",
            "risk_level": "low",
            "acceptance_criteria": "Stale running task should be visible and releasable.",
        },
    )
    require(status == 201, f"task create failed: {status} {task}")

    status, claim = http_json_status("POST", f"{api_base}/api/agent-gateway/tasks/{task_id}/claim", {"runtime_type": "mock"}, token=token)
    require(status == 200, f"claim failed: {status} {claim}")
    status, started = http_json_status("POST", f"{api_base}/api/agent-gateway/runs/start", {"task_id": task_id, "runtime_type": "mock"}, token=token)
    require(status in {200, 201}, f"run start failed: {status} {started}")
    run_id = str((started.get("run") or {}).get("run_id") or "")
    require(run_id, f"missing run id: {started}")
    make_stale(db_path, task_id, run_id)
    return task_id, run_id, agent_id


def verify_released(next_base: str, task_id: str, run_id: str) -> dict[str, Any]:
    status, detail = http_json_status("GET", f"{next_base}/api/mis/tasks/{task_id}")
    require(status == 200, f"task readback failed: {status} {detail}")
    task = detail.get("task") or {}
    runs = detail.get("runs") or []
    released_run = next((run for run in runs if run.get("run_id") == run_id), {})
    require(task.get("status") == "planned" and not task.get("owner_agent_id"), f"task was not returned to queue: {task}")
    require(released_run.get("status") == "blocked" and released_run.get("error_type") == "WorkerTaskReleased", f"run was not blocked: {released_run}")
    return {"task": task, "run": released_run}


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Next.js stuck release smoke"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-worker-release-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset_env["AGENTOPS_BASE_URL"] = api_base
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_env["AGENTOPS_BASE_URL"] = api_base
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/agents")

            proxy_task_id, proxy_run_id, _proxy_agent_id = create_running_worker_task(api_base, db_path, "proxy")
            stuck_status, stuck_payload = http_json_status("GET", f"{next_base}/api/mis/workers/stuck-tasks?threshold_sec=30&limit=10")
            require(stuck_status == 200, f"Next stuck task read failed: {stuck_status} {stuck_payload}")
            stuck_ids = {item.get("task_id") for item in stuck_payload.get("stuck_tasks", [])}
            require(proxy_task_id in stuck_ids, f"Next stuck list missing task: {stuck_payload}")

            force_status, force_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workers/tasks/release",
                {"task_id": proxy_task_id, "force": True, "reason": "force should be blocked by Next"},
            )
            require(force_status == 403, f"force release was not blocked by Next proxy: {force_status} {force_payload}")
            require(force_payload.get("error") == "force_release_not_allowed_next_parity", f"wrong force-release error: {force_payload}")

            release_status, release_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workers/tasks/release",
                {"task_id": proxy_task_id, "reason": "Next proxy released stuck worker task"},
            )
            require(release_status == 200 and release_payload.get("released") is True, f"Next proxy release failed: {release_status} {release_payload}")
            require(proxy_run_id in release_payload.get("released_runs", []), f"Next proxy release did not block run: {release_payload}")
            proxy_readback = verify_released(next_base, proxy_task_id, proxy_run_id)

            form_task_id, form_run_id, _form_agent_id = create_running_worker_task(api_base, db_path, "form")
            form_status, form_location = post_form_no_redirect(f"{next_base}/workspace/agents/release-task", {"task_id": form_task_id})
            require(form_status == 303, f"form release did not redirect with 303: {form_status} {form_location}")
            form_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_location).query)
            require(form_query.get("release_status") == ["released"], f"form release did not report released: {form_location}")
            require(form_query.get("task_id") == [form_task_id], f"form release returned wrong task id: {form_location}")
            form_readback = verify_released(next_base, form_task_id, form_run_id)

            transcript = json.dumps([stuck_payload, force_payload, release_payload, proxy_readback, form_location, form_readback], ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript), "Next worker stuck release leaked token-like material")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "stuck_route": "/api/mis/workers/stuck-tasks",
                "release_route": "/api/mis/workers/tasks/release",
                "form_route": "/workspace/agents/release-task",
                "stuck_status": stuck_status,
                "force_status": force_status,
                "force_error": "force_release_not_allowed_next_parity",
                "proxy_release_status": release_status,
                "proxy_task_id": proxy_task_id,
                "proxy_run_id": proxy_run_id,
                "form_status": form_status,
                "form_task_id": form_task_id,
                "form_run_id": form_run_id,
                "secret_leaked": False,
                "token_omitted": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()


if __name__ == "__main__":
    raise SystemExit(main())
