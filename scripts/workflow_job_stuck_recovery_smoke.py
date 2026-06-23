#!/usr/bin/env python3
"""Verify stale workflow job detection and operator mark-failed recovery."""
from __future__ import annotations

import datetime as dt
import argparse
import json
import os
import re
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
DEFAULT_DB_PATH = ROOT / "agentops_mis.db"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def run_cli(base_url: str, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env.pop("AGENTOPS_AGENT_ID", None)
    env["AGENTOPS_BASE_URL"] = base_url
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


def insert_stale_job(db_path: Path, job_id: str) -> None:
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
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO workflow_jobs(job_id,workspace_id,workflow_type,status,template_id,adapter,confirm_run,title,input_summary,request_hash,result_json,result_task_id,result_run_id,result_artifact_id,error_message,created_at,started_at,completed_at,updated_at)
            VALUES(:job_id,:workspace_id,:workflow_type,:status,:template_id,:adapter,:confirm_run,:title,:input_summary,:request_hash,:result_json,:result_task_id,:result_run_id,:result_artifact_id,:error_message,:created_at,:started_at,:completed_at,:updated_at)""",
            row,
        )
        conn.commit()


def job_status(base_url: str, job_id: str) -> dict:
    proc = run_cli(base_url, ["workflow", "job-status", "--job-id", job_id])
    payload = load_json(proc)
    require(proc.returncode == 0, f"job-status failed: {proc.stderr or proc.stdout}")
    return payload.get("job") or {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test stale workflow job recovery.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=os.environ.get("AGENTOPS_DB_PATH", str(DEFAULT_DB_PATH)))
    args = parser.parse_args()
    db_path = Path(args.db_path)
    job_id = f"wfjob_stuck_smoke_{stamp()}"
    insert_stale_job(db_path, job_id)

    listed = run_cli(args.base_url, ["workflow", "stuck-jobs", "--threshold-sec", "30", "--limit", "20"])
    listed_payload = load_json(listed)
    require(listed.returncode == 0, f"stuck-jobs failed: {listed.stderr or listed.stdout}")
    stuck_jobs = listed_payload.get("stuck_jobs") or []
    stuck_ids = {item.get("job_id") for item in stuck_jobs}
    require(job_id in stuck_ids, f"stale workflow job missing: {stuck_ids}")

    action_plan = run_cli(args.base_url, ["operator", "action-plan", "--limit", "20"])
    action_plan_payload = load_json(action_plan)
    require(action_plan.returncode == 0, f"operator action-plan failed: {action_plan.stderr or action_plan.stdout}")
    workflow_recovery = action_plan_payload.get("workflow_job_recovery") or {}
    workflow_summary = workflow_recovery.get("summary") or {}
    require(workflow_recovery.get("operation") == "workflow_job_recovery", f"workflow recovery source missing: {workflow_recovery}")
    require(workflow_summary.get("stuck_jobs", 0) >= 1, f"workflow recovery stuck count missing: {workflow_summary}")
    recovery_actions = [
        item for item in (action_plan_payload.get("actions") or [])
        if item.get("lane") == "workflow_job_recovery"
    ]
    mark_action = next(
        (
            item for item in recovery_actions
            if job_id in str(item.get("command") or "")
            and str(item.get("command") or "").startswith("agentops workflow job-mark-failed --job-id ")
        ),
        None,
    )
    require(mark_action is not None, f"workflow recovery mark-failed action missing: {recovery_actions}")
    require(mark_action.get("verify_command") == f"agentops workflow job-status --job-id {job_id}", f"workflow recovery verify command mismatch: {mark_action}")
    require("--source operator.workflow_job_recovery" in (mark_action.get("receipt_record_command") or ""), f"workflow recovery receipt source missing: {mark_action}")
    require("--status verified" in (mark_action.get("receipt_verify_record_command") or ""), f"workflow recovery verify receipt command missing: {mark_action}")

    recover_preview = run_cli(args.base_url, [
        "workflow",
        "recover-job",
        "--job-id",
        job_id,
        "--mode",
        "mark-failed",
        "--reason",
        "workflow job stuck recovery smoke",
    ])
    recover_preview_payload = load_json(recover_preview)
    require(recover_preview.returncode == 0, f"recover-job preview failed: {recover_preview.stderr or recover_preview.stdout}")
    require(recover_preview_payload.get("dry_run") is True, f"recover-job preview should be dry-run: {recover_preview_payload}")
    preview_action_command = str(recover_preview_payload.get("action_command") or "")
    require(preview_action_command.startswith("agentops workflow job-mark-failed --job-id "), f"recover-job action command missing: {recover_preview_payload}")
    require(job_id in preview_action_command, f"recover-job action command does not target job: {recover_preview_payload}")
    require(recover_preview_payload.get("verify_command") == mark_action.get("verify_command"), f"recover-job verify command mismatch: {recover_preview_payload}")
    require((recover_preview_payload.get("safety") or {}).get("ledger_mutated") is False, f"recover-job preview mutated ledger: {recover_preview_payload}")

    marked = run_cli(args.base_url, [
        "workflow",
        "recover-job",
        "--job-id",
        job_id,
        "--mode",
        "mark-failed",
        "--reason",
        "workflow job stuck recovery smoke",
        "--confirm-recover",
        "--record-receipt",
    ])
    marked_payload = load_json(marked)
    recovery = marked_payload.get("recovery") or {}
    job = recovery.get("job") or {}
    require(marked.returncode == 0, f"recover-job confirm failed: {marked.stderr or marked.stdout}")
    require(marked_payload.get("ok") is True, f"mark failed not ok: {marked_payload}")
    require(recovery.get("marked_failed") is True, f"mark flag missing: {marked_payload}")
    require((marked_payload.get("safety") or {}).get("ledger_mutated") is True, f"recover-job confirm should mutate ledger: {marked_payload}")
    require((marked_payload.get("receipt") or {}).get("status") == "verified", f"recover-job receipt missing: {marked_payload}")
    require(job.get("status") == "failed", f"job status mismatch: {job}")
    require(job.get("error_message") == "workflow job stuck recovery smoke", f"job reason mismatch: {job}")

    relisted = run_cli(args.base_url, ["workflow", "stuck-jobs", "--threshold-sec", "30", "--limit", "20"])
    relisted_payload = load_json(relisted)
    remaining_ids = {item.get("job_id") for item in (relisted_payload.get("stuck_jobs") or [])}
    require(job_id not in remaining_ids, f"marked job still appears stuck: {remaining_ids}")

    recover_job_id = f"wfjob_recover_smoke_{stamp()}"
    insert_stale_job(db_path, recover_job_id)
    preview = run_cli(args.base_url, [
        "workflow",
        "recover-job",
        "--job-id",
        recover_job_id,
        "--mode",
        "mark-failed",
        "--reason",
        "workflow recover-job preview smoke",
    ])
    preview_payload = load_json(preview)
    require(preview.returncode == 0, f"recover-job preview failed: {preview.stderr or preview.stdout}")
    require(preview_payload.get("operation") == "workflow_job_recover", f"recover preview operation mismatch: {preview_payload}")
    require(preview_payload.get("ok") is True, f"recover preview should be ok: {preview_payload}")
    require(preview_payload.get("dry_run") is True, f"recover preview should be dry-run: {preview_payload}")
    require(preview_payload.get("safety", {}).get("ledger_mutated") is False, f"recover preview mutated ledger: {preview_payload}")
    require(preview_payload.get("action_command", "").startswith("agentops workflow job-mark-failed --job-id "), f"recover preview action missing: {preview_payload}")
    preview_job = job_status(args.base_url, recover_job_id)
    require(preview_job.get("status") == "running", f"recover preview changed job status: {preview_job}")

    recovered = run_cli(args.base_url, [
        "workflow",
        "recover-job",
        "--job-id",
        recover_job_id,
        "--mode",
        "mark-failed",
        "--reason",
        "workflow recover-job confirmed smoke",
        "--confirm-recover",
        "--record-receipt",
    ])
    recovered_payload = load_json(recovered)
    recovered_job = (recovered_payload.get("recovery") or {}).get("job") or {}
    recovered_receipt = recovered_payload.get("receipt") or {}
    require(recovered.returncode == 0, f"recover-job confirmed failed: {recovered.stderr or recovered.stdout}")
    require(recovered_payload.get("ok") is True, f"recover confirmed not ok: {recovered_payload}")
    require(recovered_payload.get("dry_run") is False, f"recover confirmed should not be dry-run: {recovered_payload}")
    require(recovered_job.get("status") == "failed", f"recover confirmed job status mismatch: {recovered_payload}")
    require(recovered_receipt.get("status") == "verified", f"recover receipt missing/invalid: {recovered_payload}")
    require(recovered_receipt.get("source") == "operator.workflow_job_recovery", f"recover receipt source mismatch: {recovered_payload}")
    require(recovered_payload.get("safety", {}).get("ledger_mutated") is True, f"recover confirmed ledger flag missing: {recovered_payload}")

    combined = "\n".join([
        listed.stdout,
        listed.stderr,
        action_plan.stdout,
        action_plan.stderr,
        recover_preview.stdout,
        recover_preview.stderr,
        marked.stdout,
        marked.stderr,
        relisted.stdout,
        relisted.stderr,
        preview.stdout,
        preview.stderr,
        recovered.stdout,
        recovered.stderr,
    ])
    require(not secret_leaked(combined), "workflow stuck recovery output leaked token-like material")
    print(json.dumps({
        "ok": True,
        "job_id": job_id,
        "recover_job_id": recover_job_id,
        "listed": True,
        "marked_failed": True,
        "recover_preview_dry_run": True,
        "recover_receipt_status": recovered_receipt.get("status"),
        "final_status": job.get("status"),
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
