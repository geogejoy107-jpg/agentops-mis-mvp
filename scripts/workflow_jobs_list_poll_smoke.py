#!/usr/bin/env python3
"""Verify async workflow jobs can be listed, filtered, and polled from the CLI."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_RE = re.compile(r"(Authorization:|Bearer\s+[A-Za-z0-9._~+/=-]+|agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{20,}|ntn_[A-Za-z0-9_-]{8,})")


def run_cli(base_url: str, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
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
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def job_ids(payload: dict) -> set[str]:
    return {str(item.get("job_id")) for item in payload.get("jobs") or [] if item.get("job_id")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test workflow job list and poll CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    failures: list[str] = []
    outputs: list[str] = []

    submit = run_cli(args.base_url, [
        "workflow",
        "run-template",
        "--template-id",
        "tpl_customer_ui_review",
        "--adapter",
        "mock",
        "--async-job",
    ])
    submit_payload = load_json(submit)
    outputs.append(submit.stdout + submit.stderr)
    job_id = submit_payload.get("job_id") or (submit_payload.get("job") or {}).get("job_id")
    require(submit.returncode == 0, f"async submit failed: {submit.stderr or submit.stdout}", failures)
    require(bool(job_id), f"missing job id: {submit_payload}", failures)
    require(submit_payload.get("provider") == "agentops-workflow-job", f"wrong submit provider: {submit_payload}", failures)

    listed = run_cli(args.base_url, ["workflow", "jobs", "--status", "queued,running,completed", "--limit", "50"])
    listed_payload = load_json(listed)
    outputs.append(listed.stdout + listed.stderr)
    require(listed.returncode == 0, f"workflow jobs failed: {listed.stderr or listed.stdout}", failures)
    require(listed_payload.get("operation") == "workflow_jobs_list", f"wrong list operation: {listed_payload}", failures)
    require(listed_payload.get("read_only") is True, f"list should be read-only: {listed_payload}", failures)
    require(job_id in job_ids(listed_payload), f"submitted job missing from list: {listed_payload}", failures)
    require((listed_payload.get("summary") or {}).get("active_jobs", 0) >= 0, f"summary missing active jobs: {listed_payload}", failures)
    require("agentops workflow job-status --job-id <job_id> --wait" in (listed_payload.get("next_actions") or []), f"next action missing: {listed_payload}", failures)

    polled = run_cli(args.base_url, [
        "workflow",
        "job-status",
        "--job-id",
        str(job_id or "missing"),
        "--wait",
        "--timeout",
        "60",
        "--poll-interval",
        "0.5",
    ])
    polled_payload = load_json(polled)
    outputs.append(polled.stdout + polled.stderr)
    job = polled_payload.get("job") or {}
    require(polled.returncode == 0, f"job-status wait failed: {polled.stderr or polled.stdout}", failures)
    require(job.get("status") == "completed", f"job did not complete: {polled_payload}", failures)
    require(polled_payload.get("done") is True and polled_payload.get("waited") is True, f"poll flags missing: {polled_payload}", failures)
    require(bool(job.get("result_run_id") or (job.get("result") or {}).get("run_id")), f"missing result run id: {polled_payload}", failures)

    completed = run_cli(args.base_url, ["workflow", "jobs", "--status", "completed", "--workflow-type", "customer_task_template", "--limit", "50"])
    completed_payload = load_json(completed)
    outputs.append(completed.stdout + completed.stderr)
    require(completed.returncode == 0, f"completed jobs list failed: {completed.stderr or completed.stdout}", failures)
    require(job_id in job_ids(completed_payload), f"completed job missing from filtered list: {completed_payload}", failures)
    require((completed_payload.get("filters") or {}).get("status") == ["completed"], f"status filter readback missing: {completed_payload}", failures)

    combined = "\n".join(outputs)
    require(not SECRET_RE.search(combined), "workflow jobs list/poll output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "job_id": job_id,
        "listed_count": listed_payload.get("count"),
        "final_status": job.get("status"),
        "result_run_id": job.get("result_run_id") or (job.get("result") or {}).get("run_id"),
        "secret_leaked": False,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
