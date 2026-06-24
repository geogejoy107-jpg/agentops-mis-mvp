#!/usr/bin/env python3
"""Smoke-test async customer template workflow jobs through the CLI."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def load_json(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def token_like_leaked(text: str) -> bool:
    return any(marker in text for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "ntn_", "sk-"])


def main() -> int:
    failures: list[str] = []
    submit = run([
        "workflow",
        "run-template",
        "--template-id",
        "tpl_customer_ui_review",
        "--adapter",
        "mock",
        "--async-job",
    ])
    submit_payload = load_json(submit.stdout)
    job_id = submit_payload.get("job_id") or (submit_payload.get("job") or {}).get("job_id")
    require(submit.returncode == 0, f"submit failed: {submit.stderr or submit.stdout}", failures)
    require(submit_payload.get("provider") == "agentops-workflow-job", f"wrong provider: {submit_payload}", failures)
    require(bool(job_id), f"missing job id: {submit_payload}", failures)
    require((submit_payload.get("job") or {}).get("status") in {"queued", "running"}, f"unexpected initial job status: {submit_payload}", failures)
    require(submit_payload.get("raw_request_omitted") is True, f"raw request should be omitted: {submit_payload}", failures)

    status = run([
        "workflow",
        "job-status",
        "--job-id",
        job_id or "missing",
        "--wait",
        "--timeout",
        "45",
        "--poll-interval",
        "0.5",
    ])
    status_payload = load_json(status.stdout)
    job = status_payload.get("job") or {}
    result = job.get("result") or {}
    evidence = result.get("evidence") or {}
    require(status.returncode == 0, f"job status failed: {status.stderr or status.stdout}", failures)
    require(job.get("status") == "completed", f"job did not complete: {status_payload}", failures)
    require(result.get("provider") == "agentops-worker", f"result did not use worker provider: {result}", failures)
    require(result.get("workflow") == "customer_worker_task", f"wrong result workflow: {result}", failures)
    require(result.get("ok") is True, f"result did not complete ok: {result}", failures)
    require(bool(job.get("result_run_id") or result.get("run_id")), f"missing result run id: {status_payload}", failures)
    require(bool(job.get("result_artifact_id") or result.get("artifact_id")), f"missing result artifact id: {status_payload}", failures)
    require(evidence.get("tool_calls", 0) >= 1, f"missing tool evidence: {evidence}", failures)
    require(evidence.get("evaluations", 0) >= 1, f"missing eval evidence: {evidence}", failures)
    require(evidence.get("audit_logs", 0) >= 1, f"missing audit evidence: {evidence}", failures)
    require(evidence.get("artifacts", 0) >= 1, f"missing artifact evidence: {evidence}", failures)
    require(status_payload.get("token_omitted") is True, f"token omission flag missing: {status_payload}", failures)

    combined = "\n".join([submit.stdout, submit.stderr, status.stdout, status.stderr])
    require(not token_like_leaked(combined), "async workflow output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "job_id": job_id,
        "job_status": job.get("status"),
        "run_id": job.get("result_run_id") or result.get("run_id"),
        "artifact_id": job.get("result_artifact_id") or result.get("artifact_id"),
        "evidence": evidence,
        "secret_leaked": False,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
