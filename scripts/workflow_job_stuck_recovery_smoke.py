#!/usr/bin/env python3
"""Verify stale workflow job detection and operator mark-failed recovery."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CLI = ROOT / "scripts" / "agentops"
DB_PATH = Path(os.environ.get("AGENTOPS_DB_PATH", ROOT / "agentops_mis.db"))


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def run_cli(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env.pop("AGENTOPS_AGENT_ID", None)
    env["AGENTOPS_BASE_URL"] = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    return bool(re.search(r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,})", text))


def insert_stale_job(job_id: str) -> None:
    os.environ.setdefault("AGENTOPS_DB_PATH", str(DB_PATH))
    import server  # noqa: PLC0415

    stale_at = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
    row = {
        "job_id": job_id,
        "workspace_id": "local-demo",
        "workflow_type": "customer_worker_task",
        "status": "running",
        "template_id": None,
        "adapter": "mock",
        "confirm_run": 0,
        "title": "Workflow job stuck recovery smoke",
        "input_summary": "Synthetic stale workflow job for recovery smoke. No raw prompt or credential stored.",
        "request_hash": "smoke_request_hash",
        "result_json": "{}",
        "result_task_id": None,
        "result_run_id": None,
        "result_artifact_id": None,
        "error_message": None,
        "created_at": stale_at,
        "started_at": stale_at,
        "completed_at": None,
        "updated_at": stale_at,
    }
    server.init_schema()
    with server.db() as conn:
        server.repo_upsert_workflow_job(conn, row)
        conn.commit()


def main() -> int:
    job_id = f"wfjob_stuck_smoke_{stamp()}"
    insert_stale_job(job_id)

    listed = run_cli(["workflow", "stuck-jobs", "--threshold-sec", "30", "--limit", "20"])
    listed_payload = load_json(listed)
    require(listed.returncode == 0, f"stuck-jobs failed: {listed.stderr or listed.stdout}")
    stuck_jobs = listed_payload.get("stuck_jobs") or []
    stuck_ids = {item.get("job_id") for item in stuck_jobs}
    require(job_id in stuck_ids, f"stale workflow job missing: {stuck_ids}")

    marked = run_cli([
        "workflow",
        "job-mark-failed",
        "--job-id",
        job_id,
        "--reason",
        "workflow job stuck recovery smoke",
    ])
    marked_payload = load_json(marked)
    job = marked_payload.get("job") or {}
    require(marked.returncode == 0, f"job-mark-failed failed: {marked.stderr or marked.stdout}")
    require(marked_payload.get("ok") is True, f"mark failed not ok: {marked_payload}")
    require(marked_payload.get("marked_failed") is True, f"mark flag missing: {marked_payload}")
    require(job.get("status") == "failed", f"job status mismatch: {job}")
    require(job.get("error_message") == "workflow job stuck recovery smoke", f"job reason mismatch: {job}")

    relisted = run_cli(["workflow", "stuck-jobs", "--threshold-sec", "30", "--limit", "20"])
    relisted_payload = load_json(relisted)
    remaining_ids = {item.get("job_id") for item in (relisted_payload.get("stuck_jobs") or [])}
    require(job_id not in remaining_ids, f"marked job still appears stuck: {remaining_ids}")

    combined = "\n".join([listed.stdout, listed.stderr, marked.stdout, marked.stderr, relisted.stdout, relisted.stderr])
    require(not secret_leaked(combined), "workflow stuck recovery output leaked token-like material")
    print(json.dumps({
        "ok": True,
        "job_id": job_id,
        "listed": True,
        "marked_failed": True,
        "final_status": job.get("status"),
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
