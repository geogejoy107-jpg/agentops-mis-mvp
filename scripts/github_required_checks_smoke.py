#!/usr/bin/env python3
"""Verify GitHub branch protection requires the release CI checks before merge.

This smoke is read-only. It reads branch protection for the target branch and
verifies that the deterministic backend and UI build jobs are required status
checks with strict up-to-date enforcement enabled.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import argparse
import urllib.error
import urllib.request
from typing import Any


DEFAULT_REPO = "geogejoy107-jpg/agentops-mis-mvp"
DEFAULT_BRANCH = "main"
REQUIRED_CONTEXTS = {"Backend deterministic smokes", "UI build"}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def gh_token() -> str | None:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    gh = shutil.which("gh")
    if not gh:
        return None
    proc = subprocess.run([gh, "auth", "token"], capture_output=True, text=True, timeout=10, check=False)
    token = (proc.stdout or "").strip()
    return token or None


def fetch_protection(repo: str, branch: str, token: str | None) -> tuple[int, dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/branches/{branch}/protection"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "agentops-mis-required-checks-smoke",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        return exc.code, payload


def protection_checks(payload: dict[str, Any]) -> set[str]:
    status = payload.get("required_status_checks") or {}
    contexts = set(status.get("contexts") or [])
    for item in status.get("checks") or []:
        context = item.get("context")
        if context:
            contexts.add(context)
    return contexts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-ci-permission-limited",
        action="store_true",
        help="Report a GitHub Actions branch-protection permission limit without failing. Do not use for final RC verification.",
    )
    args = parser.parse_args()
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO).strip() or DEFAULT_REPO
    branch = os.environ.get("AGENTOPS_REQUIRED_CHECKS_BRANCH", DEFAULT_BRANCH).strip() or DEFAULT_BRANCH
    expected = {
        item.strip()
        for item in os.environ.get("AGENTOPS_REQUIRED_CHECKS", ",".join(sorted(REQUIRED_CONTEXTS))).split(",")
        if item.strip()
    }
    token = gh_token()
    failures: list[str] = []

    require(bool(token), "GitHub token is required to read branch protection", failures)
    status, payload = fetch_protection(repo, branch, token)
    ci_permission_limited = (
        status == 403
        and args.allow_ci_permission_limited
        and os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
        and "Resource not accessible by integration" in str(payload.get("message") or "")
    )
    require(
        status == 200 or ci_permission_limited,
        f"branch protection read failed for {repo}:{branch}: status={status} message={payload.get('message')}",
        failures,
    )

    required_status_checks = payload.get("required_status_checks") or {}
    contexts = protection_checks(payload)
    missing = sorted(expected - contexts)
    if not ci_permission_limited:
        require(required_status_checks.get("strict") is True, "required status checks must require branches to be up to date before merge", failures)
        require(not missing, f"missing required status checks: {missing}", failures)
        require((payload.get("allow_force_pushes") or {}).get("enabled") is False, "force pushes must be disabled for the protected branch", failures)
        require((payload.get("allow_deletions") or {}).get("enabled") is False, "branch deletions must be disabled for the protected branch", failures)

    output = {
        "ok": not failures,
        "operation": "github_required_checks_smoke",
        "repo": repo,
        "branch": branch,
        "required_contexts": sorted(expected),
        "observed_contexts": sorted(contexts),
        "strict": required_status_checks.get("strict"),
        "branch_protected": status == 200,
        "verification_mode": "ci_permission_limited" if ci_permission_limited else "live_branch_protection_read",
        "permission_limited": ci_permission_limited,
        "permission_note": "GitHub Actions token cannot read branch protection; run locally with gh auth for live verification." if ci_permission_limited else None,
        "safety": {
            "read_only": True,
            "github_settings_mutated": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
