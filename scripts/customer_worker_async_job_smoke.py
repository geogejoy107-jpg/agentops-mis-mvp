#!/usr/bin/env python3
"""Smoke-test async customer worker task submission and polling."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def run_cli(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env.pop("AGENTOPS_AGENT_ID", None)
    env["AGENTOPS_BASE_URL"] = "http://127.0.0.1:8787"
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


def main() -> int:
    suffix = stamp()
    worker_agent_id = f"agt_customer_worker_async_smoke_{suffix}"
    submit = run_cli([
        "workflow",
        "customer-worker-task",
        "--async-job",
        "--adapter",
        "mock",
        "--title",
        "Async customer worker smoke",
        "--description",
        "Submit a customer worker task as a workflow job and verify ledger-backed result.",
        "--acceptance",
        "Job must produce run, artifact and evidence without storing raw secrets.",
        "--worker-agent-id",
        worker_agent_id,
        "--priority",
        "high",
        "--risk",
        "low",
    ])
    submitted = load_json(submit)
    require(submit.returncode == 0, f"submit failed: {submit.stderr or submit.stdout}")
    require(submitted.get("provider") == "agentops-workflow-job", f"wrong provider: {submitted}")
    require(submitted.get("workflow") == "customer_worker_task", f"wrong workflow: {submitted}")
    require(submitted.get("ok") is True, f"submit not ok: {submitted}")
    job_id = submitted.get("job_id")
    require(bool(job_id), f"missing job id: {submitted}")

    poll = run_cli([
        "workflow",
        "job-status",
        "--job-id",
        job_id,
        "--wait",
        "--timeout",
        "60",
        "--poll-interval",
        "0.5",
    ])
    polled = load_json(poll)
    job = polled.get("job") or {}
    result = job.get("result") or {}
    evidence = result.get("evidence") or {}
    require(poll.returncode == 0, f"poll failed: {poll.stderr or poll.stdout}")
    require(job.get("workflow_type") == "customer_worker_task", f"job type mismatch: {job}")
    require(job.get("status") == "completed", f"job not completed: {job}")
    require(result.get("workflow") == "customer_worker_task", f"result workflow mismatch: {result}")
    require(result.get("ok") is True, f"result not ok: {result}")
    require(bool(job.get("result_task_id") or result.get("task_id")), f"missing task id: {job}")
    require(bool(job.get("result_run_id") or result.get("run_id")), f"missing run id: {job}")
    require(bool(job.get("result_artifact_id") or result.get("artifact_id")), f"missing artifact id: {job}")
    require(evidence.get("tool_calls", 0) >= 1, f"missing tool evidence: {evidence}")
    require(evidence.get("evaluations", 0) >= 1, f"missing eval evidence: {evidence}")
    require(evidence.get("audit_logs", 0) >= 1, f"missing audit evidence: {evidence}")
    require(evidence.get("artifacts", 0) >= 1, f"missing artifact evidence: {evidence}")
    require(evidence.get("approvals", 0) >= 1, f"missing approval evidence: {evidence}")
    combined = "\n".join([submit.stdout, submit.stderr, poll.stdout, poll.stderr])
    require(not secret_leaked(combined), "async customer worker output leaked token-like material")
    print(json.dumps({
        "ok": True,
        "job_id": job_id,
        "status": job.get("status"),
        "task_id": job.get("result_task_id") or result.get("task_id"),
        "run_id": job.get("result_run_id") or result.get("run_id"),
        "artifact_id": job.get("result_artifact_id") or result.get("artifact_id"),
        "evidence": evidence,
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
