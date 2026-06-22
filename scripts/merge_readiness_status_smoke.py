#!/usr/bin/env python3
"""Report and guard the v1.5 merge-readiness state.

Default mode is intentionally CI-safe: it validates checklist structure and
explicit blocker state without requiring the current in-progress CI run to have
already completed. Use --require-ready-to-merge only for a final local
release/merge candidate.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "docs" / "V1_5_MERGE_READINESS_CHECKLIST.md"
ALLOWED_STATES = {"NOT_READY", "READY_FOR_RC", "RC_FAILED", "RC_PASSED", "READY_TO_MERGE", "MERGED"}
READY_STATES = {"READY_FOR_RC", "RC_PASSED", "READY_TO_MERGE", "MERGED"}


def run(args: list[str], *, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)


def git_text(args: list[str]) -> str:
    proc = run(["git", *args])
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "git command failed").strip())
    return (proc.stdout or "").strip()


def maybe_git_text(args: list[str]) -> str | None:
    proc = run(["git", *args])
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip()


def current_branch() -> str:
    return maybe_git_text(["branch", "--show-current"]) or os.environ.get("GITHUB_REF_NAME") or "DETACHED"


def upstream_sync() -> dict[str, int | None]:
    upstream = maybe_git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if not upstream:
        return {"ahead": None, "behind": None}
    counts = maybe_git_text(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
    if not counts:
        return {"ahead": None, "behind": None}
    behind_text, ahead_text = counts.split()
    return {"ahead": int(ahead_text), "behind": int(behind_text)}


def git_status_entries() -> list[str]:
    raw = maybe_git_text(["status", "--porcelain"]) or ""
    return [line for line in raw.splitlines() if line.strip()]


def ci_from_env(head_sha: str) -> dict[str, Any] | None:
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return None
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    github_sha = os.environ.get("GITHUB_SHA", "")
    if not repo or not run_id:
        return None
    return {
        "source": "github_actions_env",
        "status": "in_progress",
        "conclusion": None,
        "url": f"{server_url.rstrip('/')}/{repo}/actions/runs/{run_id}",
        "head_sha": github_sha,
        "head_matches": github_sha == head_sha,
    }


def ci_from_gh(head_sha: str, branch: str) -> dict[str, Any]:
    gh = shutil.which("gh")
    if not gh:
        return {"source": "gh_unavailable", "status": "not_available", "conclusion": None, "head_matches": False}
    proc = run(
        [
            gh,
            "run",
            "list",
            "--branch",
            branch,
            "--limit",
            "20",
            "--json",
            "status,conclusion,url,headSha,workflowName,createdAt,name",
        ],
        timeout=15,
    )
    if proc.returncode != 0:
        return {"source": "gh_error", "status": "not_available", "conclusion": None, "head_matches": False}
    try:
        runs = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {"source": "gh_parse_error", "status": "not_available", "conclusion": None, "head_matches": False}
    exact = [item for item in runs if item.get("headSha") == head_sha]
    if not exact:
        return {"source": "gh_run_list", "status": "not_found_for_head", "conclusion": None, "head_matches": False}
    selected = exact[0]
    return {
        "source": "gh_run_list",
        "status": selected.get("status") or "unknown",
        "conclusion": selected.get("conclusion") or None,
        "url": selected.get("url"),
        "head_sha": selected.get("headSha"),
        "head_matches": True,
        "workflow": selected.get("workflowName") or selected.get("name"),
        "created_at": selected.get("createdAt"),
    }


def ci_status(head_sha: str, branch: str) -> dict[str, Any]:
    return ci_from_env(head_sha) or ci_from_gh(head_sha, branch)


def current_status_from_header(text: str) -> str:
    match = re.search(r"Current status:\s*`([^`]+)`", text)
    return match.group(1).strip() if match else "UNKNOWN"


def current_state_from_final_section(text: str) -> str:
    match = re.search(r"Current state:\s*```text\s*([A-Z_]+)\s*```", text, re.MULTILINE)
    return match.group(1).strip() if match else "UNKNOWN"


def unchecked_items(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("- [ ]") or stripped.startswith("[ ]"):
            label = stripped.replace("- [ ]", "", 1).replace("[ ]", "", 1).strip()
            items.append({"line": line_no, "label": label})
    return items


def final_required_items(text: str) -> list[str]:
    match = re.search(r"`READY_TO_MERGE` requires:\s*```text\s*(.*?)\s*```", text, re.DOTALL)
    if not match:
        return []
    items: list[str] = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        item = re.match(r"^\[(?: |x|X)\]\s*(.+)$", stripped)
        if item:
            items.append(item.group(1).strip())
    return items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-ready-to-merge", action="store_true", help="Fail unless checklist and exact HEAD satisfy READY_TO_MERGE conditions.")
    parser.add_argument("--require-clean", action="store_true", help="Fail if the working tree is dirty.")
    parser.add_argument("--require-green-ci", action="store_true", help="Fail unless current HEAD has completed successful CI evidence.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    text = CHECKLIST.read_text(encoding="utf-8") if CHECKLIST.exists() else ""
    head_sha = git_text(["rev-parse", "HEAD"])
    branch = current_branch()
    header_status = current_status_from_header(text)
    final_state = current_state_from_final_section(text)
    unchecked = unchecked_items(text)
    required = final_required_items(text)
    status_entries = git_status_entries()
    upstream = upstream_sync()
    ci = ci_status(head_sha, branch)
    green_ci = ci.get("head_matches") is True and ci.get("status") == "completed" and ci.get("conclusion") == "success"

    if not CHECKLIST.exists():
        failures.append("missing docs/V1_5_MERGE_READINESS_CHECKLIST.md")
    if header_status not in ALLOWED_STATES:
        failures.append(f"invalid checklist header status: {header_status}")
    if final_state not in ALLOWED_STATES:
        failures.append(f"invalid checklist final state: {final_state}")
    if header_status != final_state:
        failures.append(f"header status and final state disagree: {header_status} != {final_state}")
    if header_status in READY_STATES and unchecked:
        failures.append(f"ready-like status cannot have unchecked checklist items: {len(unchecked)}")
    if header_status == "NOT_READY" and not unchecked:
        failures.append("NOT_READY checklist should expose at least one unchecked blocker")
    if not required:
        failures.append("READY_TO_MERGE required-condition block is missing")
    if ci.get("head_matches") is False and ci.get("head_sha"):
        failures.append(f"CI head does not match current HEAD: {ci}")
    if args.require_clean:
        if status_entries:
            failures.append(f"working tree is not clean: {len(status_entries)} entries")
    if args.require_green_ci:
        if not green_ci:
            failures.append(f"current HEAD lacks completed successful CI evidence: {ci}")
    if args.require_ready_to_merge:
        if header_status != "READY_TO_MERGE":
            failures.append(f"expected READY_TO_MERGE, got {header_status}")
        if unchecked:
            failures.append(f"unchecked checklist items remain: {len(unchecked)}")
        if upstream.get("ahead") != 0 or upstream.get("behind") != 0:
            failures.append(f"upstream is not synchronized: {upstream}")
        if not green_ci:
            failures.append(f"current HEAD lacks green CI: {ci}")
        if status_entries:
            failures.append(f"working tree is not clean: {status_entries}")

    output = {
        "ok": not failures,
        "operation": "merge_readiness_status_smoke",
        "release_state": {
            "header_status": header_status,
            "final_state": final_state,
            "allowed_states": sorted(ALLOWED_STATES),
            "ready_to_merge": header_status == "READY_TO_MERGE" and not unchecked and green_ci and not status_entries,
        },
        "branch": branch,
        "head_sha": head_sha,
        "upstream_sync": upstream,
        "working_tree_entries": len(status_entries),
        "ci": ci,
        "blockers": {
            "unchecked_count": len(unchecked),
            "unchecked_items": unchecked[:20],
            "final_required_conditions": required,
        },
        "strict": {
            "require_ready_to_merge": args.require_ready_to_merge,
            "require_clean": args.require_clean,
            "require_green_ci": args.require_green_ci,
        },
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
