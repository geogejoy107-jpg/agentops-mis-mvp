#!/usr/bin/env python3
"""External exact-head CI evidence reader for commercial release promotion."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_exact_head_ci_evidence_v1"
WORKFLOW_NAME = "Commercial Migration CI"
REQUIRED_JOB_NAMES = [
    "Commercial core gates",
    "Storage and Postgres parity",
    "UI, deployment, and BYOC evidence",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def git_output(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return (proc.stdout or proc.stderr).strip()


def gh_json(args: list[str]) -> tuple[Any | None, str | None]:
    proc = subprocess.run(
        ["gh", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"failed to decode gh JSON: {exc}"


def current_branch() -> str:
    branch = git_output("branch", "--show-current")
    return branch or os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME") or ""


def load_run(run_id: str, repo: str | None) -> tuple[dict[str, Any] | None, str | None]:
    args = ["run", "view", str(run_id), "--json", "databaseId,headSha,status,conclusion,url,jobs,name,workflowName"]
    if repo:
        args.extend(["--repo", repo])
    data, error = gh_json(args)
    if error:
        return None, error
    require(isinstance(data, dict), "gh run view returned non-object JSON")
    return data, None


def find_successful_run(head_sha: str, branch: str, repo: str | None) -> tuple[dict[str, Any] | None, str | None]:
    args = [
        "run",
        "list",
        "--workflow",
        WORKFLOW_NAME,
        "--limit",
        "30",
        "--json",
        "databaseId,headSha,status,conclusion,url,createdAt,displayTitle",
    ]
    if branch:
        args.extend(["--branch", branch])
    if repo:
        args.extend(["--repo", repo])
    runs, error = gh_json(args)
    if error:
        return None, error
    require(isinstance(runs, list), "gh run list returned non-list JSON")
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("headSha") != head_sha:
            continue
        if run.get("status") == "completed" and run.get("conclusion") == "success":
            return load_run(str(run.get("databaseId")), repo)
    return None, f"no successful completed {WORKFLOW_NAME!r} run found for head {head_sha[:7]}"


def successful_required_jobs(run: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], list[str]]:
    jobs = [job for job in run.get("jobs") or [] if isinstance(job, dict)]
    job_map = {str(job.get("name")): job for job in jobs}
    missing = [name for name in REQUIRED_JOB_NAMES if name not in job_map]
    failed = [
        name
        for name in REQUIRED_JOB_NAMES
        if name in job_map and str(job_map[name].get("conclusion")).lower() != "success"
    ]
    selected = [
        {
            "name": name,
            "status": job_map.get(name, {}).get("status"),
            "conclusion": job_map.get(name, {}).get("conclusion"),
            "job_id": job_map.get(name, {}).get("databaseId"),
            "url": job_map.get(name, {}).get("url"),
        }
        for name in REQUIRED_JOB_NAMES
        if name in job_map
    ]
    return not missing and not failed, selected, missing + failed


def build_payload(from_gh: bool, require_current_head: bool, run_id: str | None, repo: str | None) -> dict[str, Any]:
    head = git_output("rev-parse", "HEAD")
    branch = current_branch()
    payload: dict[str, Any] = {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": "external_ci_check_not_requested",
        "ci_safe": True,
        "external_check_requested": bool(from_gh),
        "workflow": WORKFLOW_NAME,
        "branch": branch,
        "head": head,
        "exact_head_ci_verified": False,
        "required_jobs": REQUIRED_JOB_NAMES,
        "github_evidence": None,
        "must_not_use": [
            "manual_receipt_promotion_without_ci",
            "local_only_release_grade_claim",
            "in_progress_ci_as_exact_head_proof",
            "raw_prompts",
            "raw_responses",
            "private_transcripts",
            "token_values",
        ],
    }
    if not from_gh:
        if require_current_head:
            require(False, "external GitHub CI check was not requested")
        return payload

    run, error = load_run(run_id, repo) if run_id else find_successful_run(head, branch, repo)
    if error:
        payload["status"] = "exact_head_ci_not_verified"
        payload["github_error"] = error
        if require_current_head:
            require(False, error)
        return payload
    require(run is not None, "exact-head CI run lookup returned no run")
    jobs_ok, jobs, job_gaps = successful_required_jobs(run)
    head_matches = run.get("headSha") == head
    workflow_name = run.get("workflowName") or run.get("name")
    workflow_matches = workflow_name == WORKFLOW_NAME
    run_success = run.get("status") == "completed" and run.get("conclusion") == "success"
    verified = bool(head_matches and workflow_matches and run_success and jobs_ok)
    payload.update({
        "status": "exact_head_ci_verified" if verified else "exact_head_ci_not_verified",
        "exact_head_ci_verified": verified,
        "github_evidence": {
            "provider": "github_actions",
            "workflow": WORKFLOW_NAME,
            "workflow_name": workflow_name,
            "workflow_matches_expected": workflow_matches,
            "run_id": str(run.get("databaseId")),
            "url": run.get("url"),
            "head": run.get("headSha"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "head_matches_current": head_matches,
            "required_jobs_success": jobs_ok,
            "required_jobs": jobs,
            "job_gaps": job_gaps,
        },
    })
    if require_current_head:
        require(verified, f"exact-head CI is not verified for {head[:7]}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Read external exact-head CI evidence for commercial release promotion.")
    parser.add_argument("--from-gh", action="store_true", help="Query GitHub Actions through gh CLI.")
    parser.add_argument("--require-current-head", action="store_true", help="Fail unless current HEAD has a successful complete CI run.")
    parser.add_argument("--run-id", help="Specific GitHub Actions run id to verify.")
    parser.add_argument("--repo", help="GitHub repository in owner/name form; defaults to gh current repo.")
    args = parser.parse_args()

    payload = build_payload(
        from_gh=bool(args.from_gh),
        require_current_head=bool(args.require_current_head),
        run_id=args.run_id,
        repo=args.repo,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
