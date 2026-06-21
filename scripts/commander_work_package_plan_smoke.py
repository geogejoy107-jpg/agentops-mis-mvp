#!/usr/bin/env python3
"""Smoke-test Commander work-package planning through API and CLI."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
DEFAULT_DB = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
BASE_URL = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        BASE_URL.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
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


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env["AGENTOPS_BASE_URL"] = BASE_URL
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def db_counts(db_path: Path, project_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        like_project = f"%Commander project: {project_id}%"
        return {
            "tasks": int(conn.execute("SELECT COUNT(*) FROM tasks WHERE description LIKE ?", (like_project,)).fetchone()[0] or 0),
            "runtime_events": int(conn.execute("SELECT COUNT(*) FROM runtime_events WHERE event_type='commander.work_package_plan'").fetchone()[0] or 0),
            "audit_logs": int(conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='commander.work_package_plan_create'").fetchone()[0] or 0),
        }
    finally:
        conn.close()


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    suffix = stamp()
    project_id = f"proj_commander_plan_smoke_{suffix}"
    plan_id = f"cmdplan_smoke_{suffix}"
    goal = "Use AgentOps MIS to coordinate a customer AI-team project, split lanes, and prepare worker execution evidence."
    transcripts: list[str] = []
    failures: list[str] = []
    before = db_counts(DEFAULT_DB, project_id) if DEFAULT_DB.exists() else None
    try:
        status, preview = http_json("POST", "/api/commander/work-packages/plan", {
            "project_id": project_id,
            "plan_id": plan_id,
            "goal": goal,
            "max_packages": 4,
        })
        transcripts.append(json.dumps(preview, ensure_ascii=False))
        require(status == 200, f"preview failed: {status} {preview}")
        require(preview.get("status") == "preview", f"preview status wrong: {preview}")
        require(preview.get("created") is False, f"preview created tasks: {preview}")
        require(preview.get("safety", {}).get("ledger_mutated") is False, f"preview safety wrong: {preview}")
        if before is not None:
            after_preview = db_counts(DEFAULT_DB, project_id)
            require(before == after_preview, f"preview mutated database: before={before} after={after_preview}")

        cli_preview = run_cli([
            "commander",
            "plan",
            "--project-id",
            project_id,
            "--plan-id",
            plan_id,
            "--goal",
            goal,
            "--max-packages",
            "4",
        ])
        transcripts.extend([cli_preview.stdout, cli_preview.stderr])
        cli_preview_payload = load_json(cli_preview)
        require(cli_preview.returncode == 0, f"CLI preview failed: {cli_preview.stderr or cli_preview.stdout}")
        require(cli_preview_payload.get("status") == "preview", f"CLI preview status wrong: {cli_preview_payload}")

        cli_create = run_cli([
            "commander",
            "plan",
            "--project-id",
            project_id,
            "--plan-id",
            plan_id,
            "--goal",
            goal,
            "--max-packages",
            "4",
            "--confirm-create",
        ])
        transcripts.extend([cli_create.stdout, cli_create.stderr])
        create_payload = load_json(cli_create)
        require(cli_create.returncode == 0, f"CLI create failed: {cli_create.stderr or cli_create.stdout}")
        require(create_payload.get("status") == "created", f"create status wrong: {create_payload}")
        require(create_payload.get("created_count") == 4, f"wrong created count: {create_payload}")
        require(create_payload.get("live_execution_performed") is False, "planner executed live work")
        require(create_payload.get("token_omitted") is True, "token omission proof missing")
        task_ids = create_payload.get("created_task_ids") or []
        require(len(task_ids) == 4, f"wrong task ids: {create_payload}")

        for task_id in task_ids:
            detail_status, detail = http_json("GET", f"/api/tasks/{task_id}")
            require(detail_status == 200, f"task detail failed for {task_id}: {detail_status} {detail}")
            task = detail.get("task") or {}
            require(task.get("status") == "planned", f"task not planned: {task}")
            require(task.get("description", "").find(project_id) >= 0, f"task lacks project provenance: {task}")
            require(task.get("owner_agent_id"), f"task missing owner: {task}")

        after_create = db_counts(DEFAULT_DB, project_id) if DEFAULT_DB.exists() else None
        if after_create is not None:
            require(after_create["tasks"] >= 4, f"created tasks not found by provenance: {after_create}")
            require(after_create["runtime_events"] >= (before or {}).get("runtime_events", 0) + 1, f"commander runtime event missing: {after_create}")
            require(after_create["audit_logs"] >= (before or {}).get("audit_logs", 0) + 1, f"commander audit log missing: {after_create}")

        require(not leaked_secret("\n".join(transcripts)), "planner output leaked token-like material")
    except Exception as exc:
        failures.append(str(exc))

    result = {
        "ok": not failures,
        "project_id": project_id,
        "plan_id": plan_id,
        "created_count": 0 if failures else 4,
        "db_counts_before": before,
        "db_counts_after": db_counts(DEFAULT_DB, project_id) if DEFAULT_DB.exists() else None,
        "secret_leaked": leaked_secret("\n".join(transcripts)),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
