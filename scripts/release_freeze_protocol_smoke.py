#!/usr/bin/env python3
"""Verify the v1.5 release freeze and merge-check protocol.

Default mode is CI-safe: it verifies that the freeze protocol is documented,
that hardening-only scope is explicit, and that the release command chain knows
about this gate. Strict mode is for final RC/merge review and requires a clean
tree, green current-head CI, and remote branch protection or rulesets that
require checks before merge.
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
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
FREEZE_DOC = ROOT / "docs" / "RELEASE_FREEZE_PROTOCOL.md"
CHECKLIST = ROOT / "docs" / "V1_5_MERGE_READINESS_CHECKLIST.md"
PACKET_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_SCRIPT = ROOT / "scripts" / "release_evidence_packet_smoke.py"
THIS_COMMAND = "python3 scripts/release_freeze_protocol_smoke.py"
STRICT_COMMAND = "python3 scripts/release_freeze_protocol_smoke.py --require-clean --require-green-ci --require-remote-checks"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9_]+"),
]

REQUIRED_CI_COMMANDS = [
    "python3 -m py_compile server.py agentops_mis_cli/*.py scripts/*.py",
    "git diff --check",
    "python3 scripts/release_branch_control_smoke.py",
    "python3 scripts/release_freeze_protocol_smoke.py",
    "python3 scripts/release_evidence_packet_smoke.py",
    "python3 scripts/merge_readiness_status_smoke.py",
    "python3 scripts/secret_scan_smoke.py",
    "python3 scripts/public_claims_release_gate_smoke.py",
    "python3 scripts/license_provenance_smoke.py",
    "python3 scripts/migration_rollback_smoke.py",
]


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


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def current_branch() -> str:
    return maybe_git_text(["branch", "--show-current"]) or os.environ.get("GITHUB_REF_NAME") or "DETACHED"


def status_entries() -> list[str]:
    raw = maybe_git_text(["status", "--porcelain"]) or ""
    return [line for line in raw.splitlines() if line.strip()]


def upstream_sync() -> dict[str, int | None]:
    upstream = maybe_git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if not upstream:
        return {"ahead": None, "behind": None}
    counts = maybe_git_text(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
    if not counts:
        return {"ahead": None, "behind": None}
    behind_text, ahead_text = counts.split()
    return {"ahead": int(ahead_text), "behind": int(behind_text)}


def gh_json(args: list[str], *, timeout: int = 15) -> tuple[Any | None, str | None]:
    gh = shutil.which("gh")
    if not gh:
        return None, "gh_unavailable"
    proc = run([gh, *args], timeout=timeout)
    if proc.returncode != 0:
        return None, redact((proc.stderr or proc.stdout or "gh command failed").strip())
    try:
        return json.loads(proc.stdout or "null"), None
    except json.JSONDecodeError:
        return None, "gh_json_parse_error"


def current_ci_status(head_sha: str, branch: str) -> dict[str, Any]:
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        github_sha = os.environ.get("GITHUB_SHA", "")
        if repo and run_id:
            return {
                "source": "github_actions_env",
                "status": "in_progress",
                "conclusion": None,
                "url": f"{server_url.rstrip('/')}/{repo}/actions/runs/{run_id}",
                "head_sha": github_sha,
                "head_matches": github_sha == head_sha,
            }
    data, error = gh_json([
        "run",
        "list",
        "--branch",
        branch,
        "--limit",
        "20",
        "--json",
        "status,conclusion,url,headSha,workflowName,createdAt,name",
    ])
    if error:
        return {"source": "gh_error", "status": "not_available", "conclusion": None, "head_matches": False, "error": error}
    runs = data if isinstance(data, list) else []
    exact = [item for item in runs if item.get("headSha") == head_sha]
    if not exact:
        return {"source": "gh_run_list", "status": "not_found_for_head", "conclusion": None, "head_matches": False, "recent_runs_checked": len(runs)}
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


def repo_name_with_owner() -> tuple[str | None, str | None]:
    data, error = gh_json(["repo", "view", "--json", "nameWithOwner"])
    if error:
        return None, error
    if isinstance(data, dict) and data.get("nameWithOwner"):
        return str(data["nameWithOwner"]), None
    return None, "repo_name_unavailable"


def branch_protection(repo: str, branch: str) -> dict[str, Any]:
    encoded_branch = quote(branch, safe="")
    data, error = gh_json(["api", f"repos/{repo}/branches/{encoded_branch}/protection"])
    if error:
        return {
            "source": "branch_protection_api",
            "enabled": False,
            "requires_status_checks": False,
            "error": error,
        }
    required_status_checks = data.get("required_status_checks") if isinstance(data, dict) else None
    checks = (required_status_checks or {}).get("checks") or []
    contexts = (required_status_checks or {}).get("contexts") or []
    return {
        "source": "branch_protection_api",
        "enabled": True,
        "requires_status_checks": bool(required_status_checks),
        "checks": checks,
        "contexts": contexts,
    }


def rulesets(repo: str) -> dict[str, Any]:
    data, error = gh_json(["api", f"repos/{repo}/rulesets"])
    if error:
        return {"source": "rulesets_api", "available": False, "requires_status_checks": False, "error": error}
    items = data if isinstance(data, list) else []
    required_rules: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("enforcement") == "disabled":
            continue
        rules = item.get("rules") or []
        if any((rule or {}).get("type") in {"required_status_checks", "required_workflows"} for rule in rules):
            required_rules.append(str(item.get("name") or item.get("id") or "unnamed"))
    return {
        "source": "rulesets_api",
        "available": True,
        "ruleset_count": len(items),
        "requires_status_checks": bool(required_rules),
        "required_rulesets": required_rules,
    }


def remote_required_checks() -> dict[str, Any]:
    repo, error = repo_name_with_owner()
    target_branch = os.environ.get("AGENTOPS_REQUIRED_CHECKS_BRANCH", "main").strip() or "main"
    if error or not repo:
        return {
            "repo": repo,
            "branch": target_branch,
            "enabled": False,
            "branch_protection": None,
            "rulesets": None,
            "error": error,
        }
    protection = branch_protection(repo, target_branch)
    rule_status = rulesets(repo)
    enabled = bool(protection.get("requires_status_checks") or rule_status.get("requires_status_checks"))
    return {
        "repo": repo,
        "branch": target_branch,
        "enabled": enabled,
        "branch_protection": protection,
        "rulesets": rule_status,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-clean", action="store_true", help="Fail if the working tree is dirty.")
    parser.add_argument("--require-green-ci", action="store_true", help="Fail unless current HEAD has completed successful CI evidence.")
    parser.add_argument("--require-remote-checks", action="store_true", help="Fail unless branch protection or rulesets require checks before merge.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    freeze_doc = read(FREEZE_DOC)
    checklist = read(CHECKLIST)
    packet_doc = read(PACKET_DOC)
    ci_text = read(CI_WORKFLOW)
    release_script = read(RELEASE_SCRIPT)
    branch = current_branch()
    head_sha = git_text(["rev-parse", "HEAD"])
    status = status_entries()
    upstream = upstream_sync()
    ci = current_ci_status(head_sha, branch)
    green_ci = ci.get("head_matches") is True and ci.get("status") == "completed" and ci.get("conclusion") == "success"
    remote_checks = remote_required_checks()

    require(FREEZE_DOC.exists(), "missing docs/RELEASE_FREEZE_PROTOCOL.md", failures)
    for phrase in [
        "Freeze status: `ACTIVE_HARDENING_FREEZE`",
        "Allowed During Freeze",
        "Forbidden During Freeze",
        "not `READY_TO_MERGE` until remote repository protection",
        STRICT_COMMAND,
        "raw credentials",
    ]:
        require(phrase in freeze_doc, f"freeze protocol missing phrase: {phrase}", failures)
    for command in REQUIRED_CI_COMMANDS:
        require(command in ci_text, f"CI workflow missing required command: {command}", failures)
    require(THIS_COMMAND in release_script, "release evidence manifest missing freeze protocol smoke", failures)
    require(THIS_COMMAND in packet_doc, "release evidence documentation missing freeze protocol smoke", failures)
    require(STRICT_COMMAND in packet_doc, "release evidence documentation missing strict freeze command", failures)
    require("Freeze a release-candidate SHA" in checklist and "scripts/release_freeze_protocol_smoke.py" in checklist, "checklist missing freeze protocol closure", failures)
    require("Pause unrelated feature work during hardening" in checklist and "scripts/release_freeze_protocol_smoke.py" in checklist, "checklist missing hardening freeze closure", failures)
    require("Require checks before merge" in checklist and "scripts/github_required_checks_smoke.py" in checklist, "checklist missing GitHub required-checks evidence", failures)

    if args.require_clean:
        require(not status, f"working tree has local changes: {len(status)} entries", failures)
        require(upstream.get("ahead") == 0 and upstream.get("behind") == 0, f"branch is not synced with upstream: {upstream}", failures)
    if args.require_green_ci:
        require(green_ci, f"current HEAD lacks completed successful CI evidence: {ci}", failures)
    if args.require_remote_checks:
        require(remote_checks.get("enabled") is True, f"remote checks before merge are not enabled: {remote_checks}", failures)

    output = {
        "ok": not failures,
        "operation": "release_freeze_protocol_smoke",
        "branch": branch,
        "head_sha": head_sha,
        "freeze": {
            "status": "ACTIVE_HARDENING_FREEZE" if "ACTIVE_HARDENING_FREEZE" in freeze_doc else "UNKNOWN",
            "baseline_sha_recorded": bool(re.search(r"Baseline reviewed SHA:\s*`[0-9a-f]{40}`", freeze_doc)),
            "authoritative_sha_source": "git rev-parse HEAD",
            "hardening_only_scope_documented": "Allowed During Freeze" in freeze_doc and "Forbidden During Freeze" in freeze_doc,
        },
        "upstream_sync": upstream,
        "working_tree_entries": len(status),
        "ci": ci,
        "remote_required_checks": remote_checks,
        "strict": {
            "require_clean": args.require_clean,
            "require_green_ci": args.require_green_ci,
            "require_remote_checks": args.require_remote_checks,
        },
        "safety": {
            "read_only": True,
            "remote_mutation_performed": False,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    require(not any(pattern.search(serialized) for pattern in SECRET_PATTERNS), "freeze protocol output leaked token-like material", failures)
    if failures and output["ok"]:
        output["ok"] = False
        output["failures"] = failures
        serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    print(serialized)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
