#!/usr/bin/env python3
"""Promote current Gate 1-5 evidence into release-grade receipts transactionally."""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import io
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_release_grade_promotion_v1"
PAYLOAD_CONTRACT_ID = "commercial_release_grade_promotion_payload_v1"
RECEIPTS_CONTRACT_ID = "commercial_evidence_receipts_v1"
CI_CONTRACT_ID = "commercial_exact_head_ci_evidence_v1"
CI_RECEIPT_CONTRACT_ID = "commercial_migration_ci_receipt_v1"
CI_WORKFLOW_NAME = "Commercial Migration CI"
CI_WORKFLOW_ID = 301537454
CI_WORKFLOW_PATH = ".github/workflows/commercial-migration-ci.yml"
CI_WORKFLOW_EVENT = "push"
CI_ARTIFACT_NAME = "commercial-migration-ci-receipt"
GITHUB_REPOSITORY = "geogejoy107-jpg/agentops-mis-mvp"
GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_REQUIRE_HTTPS = True
GITHUB_API_VERSION = "2022-11-28"
GITHUB_CA_FILE_CANDIDATES = (
    "/private/etc/ssl/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/ssl/cert.pem",
)
GITHUB_ARTIFACT_REDIRECT_HOST_SUFFIXES = (
    ".blob.core.windows.net",
    ".githubusercontent.com",
    ".actions.githubusercontent.com",
)
MAX_GITHUB_JSON_BYTES = 4 * 1024 * 1024
MAX_GITHUB_ARTIFACT_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_GITHUB_ARTIFACT_FILE_BYTES = 4 * 1024 * 1024
FIXED_RUNTIME_BASE_URL = "http://127.0.0.1:8787"
GIT_EXECUTABLE_CANDIDATES = ("/usr/bin/git",)
RECEIPTS_BASENAME = "COMMERCIAL_EVIDENCE_RECEIPTS.json"
RECEIPTS_RELATIVE_PATH = Path("docs") / RECEIPTS_BASENAME
RELEASE_PACKET_CONTRACT_ID = "commercial_release_evidence_packet_v1"
RECORDING_TRANSACTION_OPERATION = "explicit_confirm_receipt_recording_transaction"
DEFAULT_MAX_EVIDENCE_AGE_SECONDS = 24 * 60 * 60
MAX_FUTURE_SKEW_SECONDS = 5 * 60
RUNTIME_ACCEPTANCE_TIMEOUT_SECONDS = 1500
DIRECTORY_FSYNC = os.fsync
RUNTIME_ENVIRONMENT_TEST_KEYS: tuple[str, ...] = ()

REQUIRED_CI_JOBS = [
    "Commercial core gates",
    "Storage and Postgres parity",
    "UI parity and build evidence",
    "Independent Postgres and BYOC evidence",
    "Assemble immutable commercial CI receipt",
]
REQUIRED_CI_SCOPES = {
    "gate_3_storage_boundary_before_postgres",
    "gate_5_byoc_enterprise_deployment_ci",
}
CI_RECEIPT_KEYS = {
    "contract_id",
    "generated_at",
    "subject_sha",
    "builder_sha",
    "github_run",
    "required_scopes",
    "scope_receipts",
    "missing_scopes",
    "invalid_scopes",
    "job_results",
    "failing_jobs",
    "scope_evidence_complete",
    "ci_run_complete",
    "failures",
    "raw_output_stored",
    "credentials_stored",
    "release_complete",
    "commercial_handoff_allowed",
    "ready_to_merge",
}
CI_RECEIPT_GITHUB_RUN_KEYS = {"run_id", "run_attempt", "workflow"}
CI_RECEIPT_SCOPE_KEYS = {"gate_id", "receipt_sha256", "scope_evidence_complete"}
CI_RECEIPT_JOB_NAMES = set(REQUIRED_CI_JOBS[:-1])
REQUIRED_GATE_IDS = [
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
]
REQUIRED_RUNTIME_CHECKS = {
    "Agent Gateway CLI smoke": "agent_gateway_run_id",
    "POST /api/integrations/openclaw/probe live": "openclaw_run_id",
    "POST /api/integrations/hermes/run-task live": "hermes_run_id",
}
FIXED_RUNTIME_ARGUMENTS = [
    "--base-url",
    FIXED_RUNTIME_BASE_URL,
    "--live-openclaw",
    "--live-hermes",
    "--require-hermes-api",
    "--openclaw-timeout",
    "300",
    "--hermes-timeout",
    "600",
    "--request-timeout",
    "720",
]

PAYLOAD_KEYS = {
    "contract",
    "contract_id",
    "created_at",
    "current_git_head",
    "exact_head_ci_evidence",
    "real_runtime_acceptance",
    "phase_gate_receipts",
}
GATE_PAYLOAD_KEYS = {
    "gate_id",
    "local_receipt_current",
    "verified_head",
    "verified_at",
    "commands",
}
RUNTIME_PAYLOAD_KEYS = {
    "contract",
    "source",
    "checked",
    "current_session",
    "verified_head",
    "verified_at",
    "live_openclaw",
    "live_hermes",
    "require_hermes_api",
    "agent_gateway_run_id",
    "openclaw_run_id",
    "hermes_run_id",
    "raw_prompt_omitted",
    "raw_response_omitted",
    "private_transcripts_omitted",
    "token_values_omitted",
    "real_runtime_acceptance_verified",
}
GATE_ALLOWED_UPDATE_FIELDS = {
    "release_grade_current",
    "receipt_state",
    "evidence_level",
    "release_blockers",
    "release_grade_verified_head",
    "release_grade_verified_at",
    "release_grade_promotion_id",
    "release_grade_evidence",
}
SUMMARY_ALLOWED_UPDATE_FIELDS = {
    "gates_with_release_grade_receipts",
    "gate_5_release_grade_current",
    "exact_head_ci_verified",
    "remote_sync_verified",
    "clean_worktree_verified",
    "clean_source_head_verified",
    "canonical_receipt_transaction_dirty",
    "release_grade_verified_head",
    "release_grade_verified_at",
    "release_grade_promotion_id",
}
PROMOTION_EVIDENCE_ALLOWED_UPDATE_FIELDS = {
    "state",
    "verified_head",
    "verified_at",
    "branch",
    "remote_sync_verified",
    "clean_worktree_verified",
    "clean_source_head_verified",
    "canonical_receipt_transaction_dirty",
    "recording_transaction_id",
    "recording_receipt_sha256",
    "head_receipt_sha256",
    "exact_head_ci",
    "real_runtime_acceptance",
    "release_grade_blockers",
    "promotion_transaction_id",
    "promotion_payload_sha256",
}
CRITICAL_HEAD_PATHS = (
    "scripts/commercial_release_grade_promotion",
    "scripts/commercial_release_grade_promotion.py",
    "scripts/local_runtime_acceptance.py",
    "scripts/agentops",
    "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json",
)
FORBIDDEN_RECEIPT_FIELDS = {
    "release_complete",
    "commercial_handoff_allowed",
    "ready_to_merge",
    "status",
    "local_receipt_current",
    "commands",
}
OMISSION_FIELD_NAMES = {
    "raw_prompt_omitted",
    "raw_response_omitted",
    "private_transcripts_omitted",
    "token_omitted",
    "token_values_omitted",
    "raw_output_stored",
    "credentials_stored",
}
SECRET_VALUE_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9])(?:sk|gh[pousr])[-_][A-Za-z0-9_-]{16,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{12,}", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
]


class PromotionRejected(RuntimeError):
    """A fail-closed promotion rejection carrying only a bounded error code."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise PromotionRejected(code)


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "json_object_required")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_recording_payload(path_value: str) -> dict[str, Any]:
    if path_value == "-":
        payload = json.loads(sys.stdin.read())
        require(isinstance(payload, dict), "promotion_payload_not_object")
        return payload
    return read_json(Path(path_value))


def has_forbidden_payload_text(raw: str) -> bool:
    lowered = raw.lower()
    return any(marker in lowered for marker in [
        '"raw_prompt"',
        '"raw_prompts"',
        '"raw_response"',
        '"raw_responses"',
        '"private_transcript"',
        '"private_transcripts"',
        '"token_value"',
        '"token_values"',
        "openai_api_key",
        "anthropic_api_key",
        "notion_token",
        "dify_api_key",
    ])


def normalize_runtime_evidence(
    runtime: dict[str, Any],
    *,
    source: str,
    verified_head: str | None = None,
    current_session: bool = False,
) -> dict[str, Any]:
    normalized = {
        "source": source,
        "checked": True,
        "current_session": bool(current_session),
        "verified_head": verified_head or runtime.get("verified_head"),
        "live_openclaw": bool(runtime.get("live_openclaw")),
        "live_hermes": bool(runtime.get("live_hermes")),
        "require_hermes_api": bool(runtime.get("require_hermes_api")),
        "agent_gateway_run_id": str(runtime.get("agent_gateway_run_id") or ""),
        "openclaw_run_id": str(runtime.get("openclaw_run_id") or ""),
        "hermes_run_id": str(runtime.get("hermes_run_id") or ""),
        "raw_prompt_omitted": runtime.get("raw_prompt_omitted") is True,
        "raw_response_omitted": runtime.get("raw_response_omitted") is True,
        "private_transcripts_omitted": runtime.get("private_transcripts_omitted", True) is True,
        "token_values_omitted": runtime.get("token_values_omitted") is True,
    }
    normalized["real_runtime_acceptance_verified"] = bool(
        normalized["live_openclaw"]
        and normalized["live_hermes"]
        and normalized["require_hermes_api"]
        and normalized["agent_gateway_run_id"].startswith("run_gw_")
        and normalized["openclaw_run_id"].startswith("run_api_integrations_openclaw_probe_")
        and normalized["hermes_run_id"].startswith("run_api_integrations_hermes_run_task_")
        and normalized["raw_prompt_omitted"]
        and normalized["raw_response_omitted"]
        and normalized["private_transcripts_omitted"]
        and normalized["token_values_omitted"]
    )
    return normalized


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_time(value: Any, code: str) -> datetime:
    require(isinstance(value, str) and bool(value.strip()), code)
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise PromotionRejected(code) from exc
    require(parsed.tzinfo is not None, code)
    return parsed.astimezone(timezone.utc)


def require_current_time(value: Any, *, now: datetime, max_age_seconds: int, code: str) -> datetime:
    parsed = parse_time(value, code)
    age = (now - parsed).total_seconds()
    require(age >= -MAX_FUTURE_SKEW_SECONDS, f"{code}_future")
    require(age <= max_age_seconds, f"{code}_stale")
    return parsed


def normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def reject_sensitive_payload(value: Any, *, key: str = "") -> None:
    normalized = normalized_key(key)
    if key and key not in OMISSION_FIELD_NAMES:
        sensitive_key = (
            "rawprompt" in normalized
            or "rawresponse" in normalized
            or "transcript" in normalized
            or "token" in normalized
            or "apikey" in normalized
            or "credential" in normalized
            or "secret" in normalized
        )
        require(not sensitive_key, "sensitive_payload_field_rejected")
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            reject_sensitive_payload(child_value, key=str(child_key))
    elif isinstance(value, list):
        for child in value:
            reject_sensitive_payload(child, key=key)
    elif isinstance(value, str):
        require(not any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS), "sensitive_payload_value_rejected")


def trusted_executable(candidates: tuple[str, ...], error_code: str) -> str:
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_absolute():
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return str(resolved)
    raise PromotionRejected(error_code)


def require_trusted_running_python() -> str:
    try:
        executable = Path(sys.executable).resolve(strict=True)
        metadata = executable.stat()
    except OSError as exc:
        raise PromotionRejected("trusted_python_executable_unavailable") from exc
    require(metadata.st_uid == 0, "trusted_python_owner_invalid")
    require(metadata.st_mode & 0o022 == 0, "trusted_python_permissions_invalid")
    return str(executable)


def sanitized_environment(
    *,
    strip_git: bool = False,
    strip_gh_routing: bool = False,
    strip_python: bool = False,
) -> dict[str, str]:
    environment = dict(os.environ)
    for key in list(environment):
        upper = key.upper()
        if strip_git and upper.startswith("GIT_"):
            environment.pop(key, None)
        elif strip_python and upper.startswith("PYTHON"):
            environment.pop(key, None)
    if strip_gh_routing:
        for key in ("GH_HOST", "GH_REPO", "GH_CONFIG_DIR"):
            environment.pop(key, None)
        environment["GH_PROMPT_DISABLED"] = "1"
    if strip_git:
        environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def fixed_runtime_environment() -> dict[str, str]:
    environment = {
        "PATH": "/usr/bin:/bin",
        "HERMES_ALLOW_REAL_RUN": "true",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }
    for key in ("HOME", "LANG", "LC_ALL", "TZ"):
        value = os.environ.get(key)
        if value:
            environment[key] = value
    for key in RUNTIME_ENVIRONMENT_TEST_KEYS:
        value = os.environ.get(key)
        if value is not None:
            environment[key] = value
    return environment


def git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        [trusted_executable(GIT_EXECUTABLE_CANDIDATES, "trusted_git_executable_unavailable"), "--no-replace-objects", *args],
        cwd=repo_root,
        env=sanitized_environment(strip_git=True),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    require(proc.returncode == 0, "git_state_unavailable")
    return proc.stdout.strip()


def git_bytes(repo_root: Path, *args: str) -> bytes:
    proc = subprocess.run(
        [trusted_executable(GIT_EXECUTABLE_CANDIDATES, "trusted_git_executable_unavailable"), "--no-replace-objects", *args],
        cwd=repo_root,
        env=sanitized_environment(strip_git=True),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    require(proc.returncode == 0, "git_state_unavailable")
    return proc.stdout


def require_no_git_object_overrides(repo_root: Path) -> None:
    require(not git(repo_root, "for-each-ref", "--format=%(refname)", "refs/replace/"), "git_replace_refs_present")
    common_dir = Path(git(repo_root, "rev-parse", "--git-common-dir"))
    if not common_dir.is_absolute():
        common_dir = repo_root / common_dir
    grafts_path = common_dir.resolve() / "info" / "grafts"
    try:
        grafts_present = grafts_path.is_file() and grafts_path.stat().st_size > 0
    except OSError as exc:
        raise PromotionRejected("git_grafts_state_unavailable") from exc
    require(not grafts_present, "git_grafts_present")


def tracked_head_bytes(repo_root: Path, relative_path: str) -> bytes:
    tracked = git(repo_root, "ls-files", "--error-unmatch", relative_path)
    require(tracked == relative_path, "critical_head_path_not_tracked")
    return git_bytes(repo_root, "show", f"HEAD:{relative_path}")


def verify_critical_head_bytes(repo_root: Path) -> dict[str, str]:
    relative_paths = list(CRITICAL_HEAD_PATHS)
    cli_paths = [
        item
        for item in git(repo_root, "ls-tree", "-r", "--name-only", "HEAD", "--", "agentops_mis_cli").splitlines()
        if item
    ]
    require(bool(cli_paths), "agentops_cli_head_paths_missing")
    relative_paths.extend(cli_paths)
    verified: dict[str, str] = {}
    for relative_path in relative_paths:
        path = repo_root / relative_path
        require(path.is_file() and not path.is_symlink(), "critical_head_path_invalid")
        raw = path.read_bytes()
        require(raw == tracked_head_bytes(repo_root, relative_path), "critical_head_bytes_mismatch")
        verified[relative_path] = hashlib.sha256(raw).hexdigest()
    return verified


@contextmanager
def promotion_transaction_lock(repo_root: Path, receipts_path: Path):
    lock_key = hashlib.sha256(
        f"{repo_root.resolve()}\0{receipts_path.resolve()}".encode("utf-8")
    ).hexdigest()[:24]
    common_dir_raw = git(repo_root, "rev-parse", "--git-common-dir")
    common_dir = Path(common_dir_raw)
    if not common_dir.is_absolute():
        common_dir = repo_root / common_dir
    common_dir = common_dir.resolve()
    require(common_dir.is_dir() and not common_dir.is_symlink(), "promotion_transaction_lock_directory_invalid")
    lock_path = common_dir / f"agentops-commercial-promotion-{lock_key}.lock"
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise PromotionRejected("promotion_transaction_lock_unavailable") from exc
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        descriptor_metadata = os.fstat(descriptor)
        path_metadata = os.stat(lock_path, follow_symlinks=False)
        require(
            descriptor_metadata.st_nlink == 1
            and descriptor_metadata.st_dev == path_metadata.st_dev
            and descriptor_metadata.st_ino == path_metadata.st_ino,
            "promotion_transaction_lock_identity_invalid",
        )
        yield
    except OSError as exc:
        raise PromotionRejected("promotion_transaction_lock_unavailable") from exc
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def github_repository_slug(value: str) -> str:
    raw = value.strip()
    if raw.startswith("git@github.com:"):
        raw = raw.split(":", 1)[1]
    elif "github.com/" in raw:
        raw = raw.split("github.com/", 1)[1]
    return raw.removesuffix(".git").strip("/")


def git_state(repo_root: Path, *, permitted_dirty_path: Path | None = None) -> dict[str, Any]:
    head = git(repo_root, "rev-parse", "HEAD")
    branch = git(repo_root, "branch", "--show-current")
    require(bool(branch), "detached_head_not_promotable")
    origin = git(repo_root, "remote", "get-url", "origin")
    require(github_repository_slug(origin) == GITHUB_REPOSITORY, "repository_identity_mismatch")
    status_lines = [
        line
        for line in git_bytes(
            repo_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).decode("utf-8").splitlines()
        if line
    ]
    permitted_relative = None
    if permitted_dirty_path is not None:
        try:
            permitted_relative = str(permitted_dirty_path.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            permitted_relative = None

    def porcelain_path(line: str) -> str:
        path = line[3:] if len(line) > 3 else ""
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        return path.strip('"')

    dirty_entries = [(line[:2], porcelain_path(line)) for line in status_lines]
    dirty_paths = [path for _status, path in dirty_entries]
    permitted_statuses = {" M", "M ", "MM", "??"}
    unexpected_dirty = [
        path
        for status, path in dirty_entries
        if not permitted_relative
        or path != permitted_relative
        or status not in permitted_statuses
    ]
    require(not unexpected_dirty, "worktree_not_clean")
    upstream = git(repo_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    expected_upstream = f"origin/{branch}"
    require(upstream == expected_upstream, "upstream_not_origin_branch")
    upstream_head = git(repo_root, "rev-parse", "@{u}")
    ahead_behind = git(repo_root, "rev-list", "--left-right", "--count", "@{u}...HEAD").split()
    require(len(ahead_behind) == 2 and all(value.isdigit() for value in ahead_behind), "remote_sync_unavailable")
    behind, ahead = (int(ahead_behind[0]), int(ahead_behind[1]))
    require(ahead == 0 and behind == 0 and upstream_head == head, "remote_sync_not_verified")
    return {
        "head": head,
        "short_head": git(repo_root, "rev-parse", "--short", "HEAD"),
        "branch": branch,
        "upstream": upstream,
        "upstream_head": upstream_head,
        "ahead": ahead,
        "behind": behind,
        "worktree_clean": not status_lines,
        "promotion_input_only_dirty": bool(status_lines) and not unexpected_dirty,
        "dirty_paths": dirty_paths,
        "remote_sync_verified": True,
        "repository_identity_verified": True,
    }


def head_matches(candidate: Any, full_head: str) -> bool:
    value = str(candidate or "")
    return value == full_head or (len(value) >= 7 and full_head.startswith(value))


def validate_ci_evidence(ci: dict[str, Any], *, current_head: str) -> dict[str, Any]:
    require(isinstance(ci, dict), "exact_head_ci_evidence_missing")
    require((ci.get("contract") or ci.get("contract_id")) == CI_CONTRACT_ID, "exact_head_ci_contract_mismatch")
    require(ci.get("status") == "exact_head_ci_verified", "exact_head_ci_not_verified")
    require(ci.get("exact_head_ci_verified") is True, "exact_head_ci_not_verified")
    require(ci.get("head") == current_head, "exact_head_ci_head_mismatch")

    github = ci.get("github_evidence") or {}
    require(isinstance(github, dict), "exact_head_ci_github_evidence_missing")
    require(github.get("provider") == "github_actions", "exact_head_ci_provider_mismatch")
    require(github.get("workflow") == CI_WORKFLOW_NAME, "exact_head_ci_workflow_mismatch")
    require(github.get("workflow_matches_expected") is True, "exact_head_ci_workflow_mismatch")
    require(github.get("head") == current_head and github.get("head_matches_current") is True, "exact_head_ci_head_mismatch")
    require(github.get("status") == "completed" and github.get("conclusion") == "success", "exact_head_ci_not_successful")
    require(github.get("required_jobs_success") is True, "exact_head_ci_jobs_not_verified")
    run_id = str(github.get("run_id") or "")
    require(bool(run_id), "exact_head_ci_run_id_missing")

    jobs = [item for item in github.get("required_jobs") or [] if isinstance(item, dict)]
    jobs_by_name = {str(item.get("name")): item for item in jobs}
    require(len(jobs_by_name) == len(jobs), "exact_head_ci_job_duplicate")
    require(set(jobs_by_name) == set(REQUIRED_CI_JOBS), "exact_head_ci_job_coverage_mismatch")
    require(
        all(
            jobs_by_name[name].get("status") == "completed"
            and str(jobs_by_name[name].get("conclusion")).lower() == "success"
            for name in REQUIRED_CI_JOBS
        ),
        "exact_head_ci_jobs_not_verified",
    )

    aggregate = github.get("aggregate_receipt") or {}
    require(aggregate.get("verified") is True, "exact_head_ci_aggregate_receipt_not_verified")
    require(aggregate.get("contract_id") == CI_RECEIPT_CONTRACT_ID, "exact_head_ci_aggregate_contract_mismatch")
    require(aggregate.get("subject_sha") == current_head, "exact_head_ci_aggregate_head_mismatch")
    require(str(aggregate.get("run_id") or "") == run_id, "exact_head_ci_aggregate_run_mismatch")
    aggregate_hash = str(aggregate.get("sha256") or "")
    require(bool(re.fullmatch(r"[0-9a-f]{64}", aggregate_hash)), "exact_head_ci_aggregate_hash_invalid")
    require(aggregate.get("raw_output_stored") is False, "exact_head_ci_raw_output_policy_invalid")
    require(not aggregate.get("failures"), "exact_head_ci_aggregate_receipt_not_verified")
    require(not aggregate.get("error"), "exact_head_ci_aggregate_receipt_not_verified")
    return {
        "contract": CI_CONTRACT_ID,
        "provider": "github_actions",
        "workflow": CI_WORKFLOW_NAME,
        "run_id": run_id,
        "head": current_head,
        "status": "success",
        "required_jobs": [
            {
                "name": name,
                "job_id": jobs_by_name[name].get("job_id"),
                "status": "success",
            }
            for name in REQUIRED_CI_JOBS
        ],
        "aggregate_receipt_contract": CI_RECEIPT_CONTRACT_ID,
        "aggregate_receipt_sha256": aggregate_hash,
        "raw_output_stored": False,
    }


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_api_token() -> str:
    values = {
        value.strip()
        for name in ("GITHUB_TOKEN", "GH_TOKEN")
        for value in [os.environ.get(name, "")]
        if value.strip()
    }
    require(len(values) == 1, "github_api_token_required")
    token = next(iter(values))
    require("\n" not in token and "\r" not in token and len(token) >= 20, "github_api_token_invalid")
    return token


def trusted_github_ca_file() -> str:
    for candidate in GITHUB_CA_FILE_CANDIDATES:
        try:
            resolved = Path(candidate).resolve(strict=True)
            metadata = resolved.stat()
        except OSError:
            continue
        if resolved.is_file() and metadata.st_uid == 0 and metadata.st_mode & 0o022 == 0:
            return str(resolved)
    raise PromotionRejected("trusted_github_ca_file_unavailable")


def github_api_base_parts():
    parsed = urlsplit(GITHUB_API_BASE_URL)
    require(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment, "github_api_base_invalid")
    if GITHUB_API_REQUIRE_HTTPS:
        require(parsed.scheme == "https", "github_api_base_invalid")
        require(parsed.hostname == "api.github.com", "github_api_base_invalid")
        require(parsed.port in (None, 443), "github_api_base_invalid")
    else:
        require(parsed.scheme in {"http", "https"} and bool(parsed.hostname), "github_api_base_invalid")
    return parsed


def github_opener(*, no_redirect: bool):
    parsed = github_api_base_parts()
    handlers = [ProxyHandler({})]
    if parsed.scheme == "https":
        context = ssl.create_default_context(cafile=trusted_github_ca_file())
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        handlers.append(HTTPSHandler(context=context))
    if no_redirect:
        handlers.append(NoRedirectHandler())
    return build_opener(*handlers)


def read_bounded_response(response, *, limit: int, code: str) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            require(int(content_length) <= limit, code)
        except ValueError as exc:
            raise PromotionRejected(code) from exc
    raw = response.read(limit + 1)
    require(len(raw) <= limit, code)
    return raw


def github_api_request(path: str, *, timeout: int, error_code: str, no_redirect: bool = False):
    require(path.startswith("/") and ".." not in path, "github_api_path_invalid")
    token = github_api_token()
    request = Request(
        GITHUB_API_BASE_URL.rstrip("/") + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "agentops-commercial-release-promotion/1",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        },
        method="GET",
    )
    try:
        return github_opener(no_redirect=no_redirect).open(request, timeout=timeout)
    except HTTPError as exc:
        if no_redirect and exc.code in {301, 302, 303, 307, 308}:
            return exc
        raise PromotionRejected(error_code) from exc
    except (OSError, URLError, ValueError) as exc:
        raise PromotionRejected(error_code) from exc


def github_api_json(path: str, *, timeout: int, error_code: str) -> dict[str, Any]:
    response = github_api_request(path, timeout=timeout, error_code=error_code, no_redirect=True)
    try:
        require(getattr(response, "code", None) == 200, error_code)
        raw = read_bounded_response(response, limit=MAX_GITHUB_JSON_BYTES, code=error_code)
    finally:
        response.close()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PromotionRejected(error_code) from exc
    require(isinstance(payload, dict), error_code)
    return payload


def validate_artifact_redirect_url(value: str) -> str:
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and not parsed.username and not parsed.password, "independent_ci_artifact_redirect_invalid")
    require(parsed.port in (None, 443) and bool(parsed.hostname), "independent_ci_artifact_redirect_invalid")
    hostname = str(parsed.hostname).lower()
    require(
        hostname in {"github.com", "objects.githubusercontent.com"}
        or any(hostname.endswith(suffix) for suffix in GITHUB_ARTIFACT_REDIRECT_HOST_SUFFIXES),
        "independent_ci_artifact_redirect_invalid",
    )
    return value


def download_ci_artifact(artifact_id: str) -> bytes:
    response = github_api_request(
        f"/repos/{GITHUB_REPOSITORY}/actions/artifacts/{artifact_id}/zip",
        timeout=90,
        error_code="independent_ci_artifact_download_failed",
        no_redirect=True,
    )
    try:
        if getattr(response, "code", None) in {301, 302, 303, 307, 308}:
            location = validate_artifact_redirect_url(str(response.headers.get("Location") or ""))
            for _redirect_count in range(4):
                request = Request(location, headers={"User-Agent": "agentops-commercial-release-promotion/1"}, method="GET")
                try:
                    redirected = github_opener(no_redirect=True).open(request, timeout=90)
                except HTTPError as exc:
                    if exc.code in {301, 302, 303, 307, 308}:
                        redirected = exc
                    else:
                        raise PromotionRejected("independent_ci_artifact_download_failed") from exc
                except (OSError, URLError, ValueError) as exc:
                    raise PromotionRejected("independent_ci_artifact_download_failed") from exc
                try:
                    if getattr(redirected, "code", None) in {301, 302, 303, 307, 308}:
                        location = validate_artifact_redirect_url(str(redirected.headers.get("Location") or ""))
                        continue
                    require(getattr(redirected, "code", None) == 200, "independent_ci_artifact_download_failed")
                    validate_artifact_redirect_url(str(redirected.geturl()))
                    return read_bounded_response(
                        redirected,
                        limit=MAX_GITHUB_ARTIFACT_ARCHIVE_BYTES,
                        code="independent_ci_artifact_archive_too_large",
                    )
                finally:
                    redirected.close()
            raise PromotionRejected("independent_ci_artifact_redirect_limit_exceeded")
        require(getattr(response, "code", None) == 200, "independent_ci_artifact_download_failed")
        return read_bounded_response(
            response,
            limit=MAX_GITHUB_ARTIFACT_ARCHIVE_BYTES,
            code="independent_ci_artifact_archive_too_large",
        )
    finally:
        response.close()


def extract_ci_receipt(archive_raw: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_raw), "r") as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            require(len(members) == 1, "independent_ci_artifact_file_count_invalid")
            member = members[0]
            require(member.filename == "commercial-migration-ci-receipt.json", "independent_ci_artifact_file_invalid")
            require(member.file_size <= MAX_GITHUB_ARTIFACT_FILE_BYTES, "independent_ci_artifact_file_too_large")
            mode = (member.external_attr >> 16) & 0o170000
            require(mode not in {0o120000, 0o060000}, "independent_ci_artifact_file_invalid")
            raw = archive.read(member)
    except PromotionRejected:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise PromotionRejected("independent_ci_artifact_zip_invalid") from exc
    require(len(raw) <= MAX_GITHUB_ARTIFACT_FILE_BYTES, "independent_ci_artifact_file_too_large")
    return raw


def parse_json_object(raw: str, code: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PromotionRejected(code) from exc
    require(isinstance(payload, dict), code)
    return payload


def independently_verify_remote_branch(repo_root: Path, *, branch: str, current_head: str) -> dict[str, Any]:
    encoded_branch = quote(branch, safe="")
    payload = github_api_json(
        f"/repos/{GITHUB_REPOSITORY}/git/ref/heads/{encoded_branch}",
        timeout=60,
        error_code="independent_remote_branch_query_failed",
    )
    require(payload.get("ref") == f"refs/heads/{branch}", "independent_remote_branch_ref_mismatch")
    target = payload.get("object") or {}
    require(isinstance(target, dict), "independent_remote_branch_target_missing")
    require(target.get("type") == "commit", "independent_remote_branch_target_invalid")
    require(target.get("sha") == current_head, "independent_remote_branch_head_mismatch")
    return {
        "provider": "github_api",
        "repository": GITHUB_REPOSITORY,
        "branch": branch,
        "ref": payload.get("ref"),
        "head": target.get("sha"),
        "verified": True,
    }


def validate_downloaded_ci_receipt(
    receipt: dict[str, Any],
    *,
    current_head: str,
    run_id: str,
    run_attempt: str,
) -> None:
    require(set(receipt) == CI_RECEIPT_KEYS, "independent_ci_receipt_schema_invalid")
    require(receipt.get("contract_id") == CI_RECEIPT_CONTRACT_ID, "independent_ci_receipt_contract_mismatch")
    require(isinstance(receipt.get("generated_at"), str) and bool(receipt.get("generated_at")), "independent_ci_receipt_generated_at_invalid")
    require(receipt.get("subject_sha") == current_head, "independent_ci_receipt_subject_mismatch")
    require(receipt.get("builder_sha") == current_head, "independent_ci_receipt_builder_mismatch")
    github_run = receipt.get("github_run") or {}
    require(isinstance(github_run, dict) and set(github_run) == CI_RECEIPT_GITHUB_RUN_KEYS, "independent_ci_receipt_github_run_schema_invalid")
    require(str(github_run.get("run_id") or "") == run_id, "independent_ci_receipt_run_mismatch")
    require(str(github_run.get("run_attempt") or "") == run_attempt, "independent_ci_receipt_run_attempt_mismatch")
    require(github_run.get("workflow") == CI_WORKFLOW_NAME, "independent_ci_receipt_workflow_mismatch")
    for field in ("required_scopes", "scope_receipts", "missing_scopes", "invalid_scopes", "failing_jobs", "failures"):
        require(isinstance(receipt.get(field), list), f"independent_ci_receipt_{field}_schema_invalid")
    required_scopes = receipt["required_scopes"]
    require(all(isinstance(item, str) for item in required_scopes), "independent_ci_receipt_required_scopes_schema_invalid")
    require(set(required_scopes) == REQUIRED_CI_SCOPES, "independent_ci_receipt_scope_mismatch")
    require(len(required_scopes) == len(REQUIRED_CI_SCOPES), "independent_ci_receipt_scope_mismatch")
    scope_receipts = receipt["scope_receipts"]
    require(
        all(isinstance(item, dict) and set(item) == CI_RECEIPT_SCOPE_KEYS for item in scope_receipts),
        "independent_ci_receipt_scope_schema_invalid",
    )
    require({str(item.get("gate_id") or "") for item in scope_receipts} == REQUIRED_CI_SCOPES, "independent_ci_receipt_scope_mismatch")
    require(len(scope_receipts) == len(REQUIRED_CI_SCOPES), "independent_ci_receipt_scope_mismatch")
    require(all(item.get("scope_evidence_complete") is True for item in scope_receipts), "independent_ci_receipt_scope_incomplete")
    require(
        all(bool(re.fullmatch(r"[0-9a-f]{64}", str(item.get("receipt_sha256") or ""))) for item in scope_receipts),
        "independent_ci_scope_hash_invalid",
    )
    require(receipt.get("scope_evidence_complete") is True, "independent_ci_receipt_scope_incomplete")
    require(receipt.get("ci_run_complete") is True, "independent_ci_receipt_incomplete")
    require(not receipt["missing_scopes"], "independent_ci_receipt_scope_incomplete")
    require(not receipt["invalid_scopes"], "independent_ci_receipt_scope_incomplete")
    require(not receipt["failing_jobs"], "independent_ci_receipt_jobs_failed")
    job_results = receipt.get("job_results") or {}
    require(isinstance(job_results, dict) and bool(job_results), "independent_ci_receipt_job_results_missing")
    require(set(job_results) == CI_RECEIPT_JOB_NAMES, "independent_ci_receipt_job_results_schema_invalid")
    require(all(result == "success" for result in job_results.values()), "independent_ci_receipt_jobs_failed")
    require(not receipt["failures"], "independent_ci_receipt_incomplete")
    require(receipt.get("raw_output_stored") is False, "independent_ci_receipt_raw_output_policy_invalid")
    require(receipt.get("credentials_stored") is False, "independent_ci_receipt_credential_policy_invalid")
    require(receipt.get("release_complete") is False, "independent_ci_receipt_self_promotion_invalid")
    require(receipt.get("commercial_handoff_allowed") is False, "independent_ci_receipt_self_promotion_invalid")
    require(receipt.get("ready_to_merge") is False, "independent_ci_receipt_self_promotion_invalid")


def independently_verify_ci(
    *,
    repo_root: Path,
    current_head: str,
    branch: str,
    payload_ci: dict[str, Any],
) -> dict[str, Any]:
    claim = validate_ci_evidence(payload_ci, current_head=current_head)
    run_id = str(claim.get("run_id") or "")
    require(bool(re.fullmatch(r"[0-9]+", run_id)), "exact_head_ci_run_id_invalid")
    github_api_token()
    remote_branch = independently_verify_remote_branch(
        repo_root,
        branch=branch,
        current_head=current_head,
    )
    workflow_payload = github_api_json(
        f"/repos/{GITHUB_REPOSITORY}/actions/workflows/{CI_WORKFLOW_ID}",
        timeout=60,
        error_code="independent_ci_workflow_query_failed",
    )
    require(workflow_payload.get("id") == CI_WORKFLOW_ID, "independent_ci_workflow_id_mismatch")
    require(workflow_payload.get("name") == CI_WORKFLOW_NAME, "independent_ci_workflow_mismatch")
    require(workflow_payload.get("path") == CI_WORKFLOW_PATH, "independent_ci_workflow_path_mismatch")
    require(workflow_payload.get("state") == "active", "independent_ci_workflow_inactive")
    run_payload = github_api_json(
        f"/repos/{GITHUB_REPOSITORY}/actions/runs/{run_id}",
        timeout=60,
        error_code="independent_ci_run_query_failed",
    )
    require(str(run_payload.get("id") or "") == run_id, "independent_ci_run_id_mismatch")
    require(run_payload.get("head_sha") == current_head, "independent_ci_head_mismatch")
    require(run_payload.get("workflow_id") == CI_WORKFLOW_ID, "independent_ci_workflow_id_mismatch")
    require(run_payload.get("path") == CI_WORKFLOW_PATH, "independent_ci_workflow_path_mismatch")
    require(run_payload.get("event") == CI_WORKFLOW_EVENT, "independent_ci_event_mismatch")
    require(run_payload.get("head_branch") == branch, "independent_ci_branch_mismatch")
    require((run_payload.get("head_repository") or {}).get("full_name") == GITHUB_REPOSITORY, "independent_ci_head_repository_mismatch")
    require((run_payload.get("repository") or {}).get("full_name") == GITHUB_REPOSITORY, "independent_ci_repository_mismatch")
    run_attempt = str(run_payload.get("run_attempt") or "")
    require(bool(re.fullmatch(r"[1-9][0-9]*", run_attempt)), "independent_ci_run_attempt_invalid")
    workflow_name = run_payload.get("name")
    require(workflow_name == CI_WORKFLOW_NAME, "independent_ci_workflow_mismatch")
    require(run_payload.get("status") == "completed", "independent_ci_run_not_completed")
    require(run_payload.get("conclusion") == "success", "independent_ci_run_not_successful")
    jobs_payload = github_api_json(
        f"/repos/{GITHUB_REPOSITORY}/actions/runs/{run_id}/attempts/{run_attempt}/jobs?per_page=100",
        timeout=60,
        error_code="independent_ci_jobs_query_failed",
    )
    actual_jobs = [item for item in jobs_payload.get("jobs") or [] if isinstance(item, dict)]
    actual_jobs_by_name = {str(item.get("name") or ""): item for item in actual_jobs}
    require(len(actual_jobs_by_name) == len(actual_jobs), "independent_ci_job_duplicate")
    require(set(REQUIRED_CI_JOBS).issubset(actual_jobs_by_name), "independent_ci_job_coverage_mismatch")
    require(
        all(
            actual_jobs_by_name[name].get("status") == "completed"
            and str(actual_jobs_by_name[name].get("conclusion") or "").lower() == "success"
            for name in REQUIRED_CI_JOBS
        ),
        "independent_ci_jobs_not_successful",
    )
    claimed_jobs = {str(item.get("name") or ""): item for item in claim.get("required_jobs") or []}
    for name in REQUIRED_CI_JOBS:
        claimed_job_id = str(claimed_jobs[name].get("job_id") or "")
        actual_job_id = str(actual_jobs_by_name[name].get("id") or "")
        require(bool(claimed_job_id) and claimed_job_id == actual_job_id, "payload_ci_job_reference_mismatch")

    artifacts_payload = github_api_json(
        f"/repos/{GITHUB_REPOSITORY}/actions/runs/{run_id}/artifacts?name={quote(CI_ARTIFACT_NAME, safe='')}&per_page=100",
        timeout=60,
        error_code="independent_ci_artifact_query_failed",
    )
    artifacts = [
        item
        for item in artifacts_payload.get("artifacts") or []
        if isinstance(item, dict) and item.get("name") == CI_ARTIFACT_NAME
    ]
    require(len(artifacts) == 1, "independent_ci_artifact_count_invalid")
    artifact_metadata = artifacts[0]
    require(artifact_metadata.get("expired") is False, "independent_ci_artifact_expired")
    artifact_workflow_run = artifact_metadata.get("workflow_run") or {}
    require(str(artifact_workflow_run.get("id") or "") == run_id, "independent_ci_artifact_run_mismatch")
    artifact_id = str(artifact_metadata.get("id") or "")
    require(bool(re.fullmatch(r"[0-9]+", artifact_id)), "independent_ci_artifact_id_invalid")
    archive_raw = download_ci_artifact(artifact_id)
    raw = extract_ci_receipt(archive_raw)
    artifact_hash = hashlib.sha256(raw).hexdigest()
    try:
        artifact = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PromotionRejected("independent_ci_artifact_json_invalid") from exc
    require(isinstance(artifact, dict), "independent_ci_artifact_json_invalid")
    reject_sensitive_payload(artifact)
    require(
        not has_forbidden_payload_text(raw.decode("utf-8")),
        "independent_ci_artifact_contains_forbidden_material",
    )
    validate_downloaded_ci_receipt(
        artifact,
        current_head=current_head,
        run_id=run_id,
        run_attempt=run_attempt,
    )

    require(artifact_hash == claim.get("aggregate_receipt_sha256"), "payload_ci_artifact_hash_mismatch")
    return {
        "contract": CI_CONTRACT_ID,
        "provider": "github_actions",
        "workflow": CI_WORKFLOW_NAME,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "head": current_head,
        "status": "success",
        "required_jobs": [
            {
                "name": name,
                "job_id": actual_jobs_by_name[name].get("id"),
                "status": "success",
            }
            for name in REQUIRED_CI_JOBS
        ],
        "aggregate_receipt_contract": CI_RECEIPT_CONTRACT_ID,
        "aggregate_receipt_sha256": artifact_hash,
        "remote_branch": remote_branch,
        "workflow_id": CI_WORKFLOW_ID,
        "workflow_path": CI_WORKFLOW_PATH,
        "event": CI_WORKFLOW_EVENT,
        "raw_output_stored": False,
        "credentials_stored": False,
        "independently_verified_via_github_api": True,
    }


def validate_runtime_evidence(
    runtime: dict[str, Any],
    *,
    current_head: str,
    now: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    require(isinstance(runtime, dict), "real_runtime_evidence_missing")
    require(set(runtime).issubset(RUNTIME_PAYLOAD_KEYS), "real_runtime_payload_keys_invalid")
    require(runtime.get("current_session") is True, "real_runtime_evidence_not_current")
    require(runtime.get("verified_head") == current_head, "real_runtime_head_mismatch")
    verified_at = require_current_time(
        runtime.get("verified_at"),
        now=now,
        max_age_seconds=max_age_seconds,
        code="real_runtime_verified_at_invalid",
    )
    for field in [
        "raw_prompt_omitted",
        "raw_response_omitted",
        "private_transcripts_omitted",
        "token_values_omitted",
    ]:
        require(runtime.get(field) is True, "real_runtime_sensitive_omission_missing")
    require(not has_forbidden_payload_text(canonical_json(runtime)), "real_runtime_payload_contains_forbidden_material")
    normalized = normalize_runtime_evidence(
        runtime,
        source=str(runtime.get("source") or "operator_supplied_promotion_payload"),
        verified_head=current_head,
        current_session=True,
    )
    require(normalized.get("real_runtime_acceptance_verified") is True, "real_runtime_acceptance_not_verified")
    normalized["verified_at"] = verified_at.replace(microsecond=0).isoformat()
    normalized["real_runtime_acceptance_verified"] = True
    normalized["independent_reexecution_verified"] = False
    return normalized


def run_fixed_runtime_acceptance(
    *,
    repo_root: Path,
    payload_runtime: dict[str, Any],
) -> dict[str, Any]:
    script_path = repo_root / "scripts" / "local_runtime_acceptance.py"
    require(script_path.exists(), "runtime_acceptance_script_missing")
    require(script_path.is_file() and not script_path.is_symlink(), "runtime_acceptance_script_invalid")
    relative_script = str(script_path.relative_to(repo_root))
    tracked = git(repo_root, "ls-files", "--error-unmatch", relative_script)
    require(tracked == relative_script, "runtime_acceptance_script_not_tracked")
    require(
        script_path.read_bytes() == git_bytes(repo_root, "show", f"HEAD:{relative_script}"),
        "runtime_acceptance_script_head_mismatch",
    )
    command = [sys.executable, "-I", "-B", "-S", str(script_path), *FIXED_RUNTIME_ARGUMENTS]
    environment = fixed_runtime_environment()
    try:
        proc = subprocess.run(
            command,
            cwd=repo_root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=RUNTIME_ACCEPTANCE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise PromotionRejected("fixed_runtime_acceptance_execution_failed") from exc
    require(proc.returncode == 0, "fixed_runtime_acceptance_failed")
    runtime_output = parse_json_object(proc.stdout, "fixed_runtime_acceptance_json_invalid")
    reject_sensitive_payload(runtime_output)
    require(not has_forbidden_payload_text(proc.stdout), "fixed_runtime_acceptance_contains_forbidden_material")
    require(runtime_output.get("ok") is True, "fixed_runtime_acceptance_not_verified")
    require(runtime_output.get("live_openclaw") is True, "fixed_runtime_openclaw_not_live")
    require(runtime_output.get("live_hermes") is True, "fixed_runtime_hermes_not_live")
    require(runtime_output.get("require_hermes_api") is True, "fixed_runtime_hermes_api_not_required")
    checks = [item for item in runtime_output.get("checks") or [] if isinstance(item, dict)]
    checks_by_name = {str(item.get("name") or ""): item for item in checks}
    require(len(checks_by_name) == len(checks), "fixed_runtime_check_duplicate")
    actual_ids: dict[str, str] = {}
    for check_name, field in REQUIRED_RUNTIME_CHECKS.items():
        item = checks_by_name.get(check_name) or {}
        require(item.get("ok") is True, "fixed_runtime_required_check_failed")
        detail = item.get("detail") or {}
        require(isinstance(detail, dict), "fixed_runtime_required_check_detail_missing")
        run_id = str(detail.get("run_id") or "")
        actual_ids[field] = run_id
    require(actual_ids["agent_gateway_run_id"].startswith("run_gw_"), "fixed_runtime_agent_gateway_run_id_invalid")
    require(
        actual_ids["openclaw_run_id"].startswith("run_api_integrations_openclaw_probe_"),
        "fixed_runtime_openclaw_run_id_invalid",
    )
    require(
        actual_ids["hermes_run_id"].startswith("run_api_integrations_hermes_run_task_"),
        "fixed_runtime_hermes_run_id_invalid",
    )
    for check_name in [
        "POST /api/integrations/openclaw/probe live",
        "POST /api/integrations/hermes/run-task live",
    ]:
        detail = (checks_by_name[check_name].get("detail") or {})
        require(detail.get("ok") is True, "fixed_runtime_provider_check_not_ok")
        require(detail.get("dry_run") is False, "fixed_runtime_provider_check_not_live")
        require(detail.get("provider_call_performed") is True, "fixed_runtime_provider_call_not_performed")
        require(detail.get("raw_prompt_omitted") is True, "fixed_runtime_raw_prompt_omission_missing")
        require(detail.get("raw_response_omitted") is True, "fixed_runtime_raw_response_omission_missing")
        require(detail.get("token_omitted") is True, "fixed_runtime_token_omission_missing")
    operator_ids = {
        field: str(payload_runtime.get(field) or "")
        for field in REQUIRED_RUNTIME_CHECKS.values()
    }
    require(
        all(actual_ids[field] != operator_ids[field] for field in actual_ids),
        "fixed_runtime_reexecution_not_distinct",
    )
    verified_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    runtime = normalize_runtime_evidence(
        {
            "live_openclaw": True,
            "live_hermes": True,
            "require_hermes_api": True,
            **actual_ids,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "private_transcripts_omitted": True,
            "token_values_omitted": True,
        },
        source="fixed_repo_local_runtime_acceptance_reexecution",
        verified_head=str(payload_runtime.get("verified_head") or ""),
        current_session=True,
    )
    require(runtime.get("real_runtime_acceptance_verified") is True, "fixed_runtime_acceptance_not_verified")
    runtime.update({
        "verified_at": verified_at,
        "independent_reexecution_verified": True,
        "operator_reference_sha256": sha256_json(operator_ids),
        "operator_run_ids_distinct": True,
        "fixed_command_arguments": list(FIXED_RUNTIME_ARGUMENTS),
        "fixed_command_sha256": hashlib.sha256(
            "\0".join(["python3", "-I", "-B", "-S", "scripts/local_runtime_acceptance.py", *FIXED_RUNTIME_ARGUMENTS]).encode("utf-8")
        ).hexdigest(),
        "python_isolated_mode": True,
        "hermes_allow_real_run": True,
        "fixed_base_url": FIXED_RUNTIME_BASE_URL,
    })
    return runtime


def command_signature(command: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": str(command.get("command") or ""),
        "status": str(command.get("status") or ""),
        "contract": str(command.get("contract") or ""),
        "skipped": command.get("skipped") is True,
    }


def validate_gate_payloads(
    gate_payloads: Any,
    *,
    receipt_map: dict[str, dict[str, Any]],
    required_commands: dict[str, list[str]],
    current_head: str,
    now: datetime,
    max_age_seconds: int,
) -> dict[str, dict[str, Any]]:
    require(isinstance(gate_payloads, list), "phase_gate_payloads_missing")
    require(all(isinstance(item, dict) for item in gate_payloads), "phase_gate_payload_invalid")
    require(all(set(item).issubset(GATE_PAYLOAD_KEYS) for item in gate_payloads), "phase_gate_payload_keys_invalid")
    payload_map = {str(item.get("gate_id") or ""): item for item in gate_payloads}
    require(len(payload_map) == len(gate_payloads), "phase_gate_payload_duplicate")
    require(set(payload_map) == set(REQUIRED_GATE_IDS), "phase_gate_payload_coverage_mismatch")

    validated: dict[str, dict[str, Any]] = {}
    for gate_id in REQUIRED_GATE_IDS:
        supplied = payload_map[gate_id]
        receipt = receipt_map.get(gate_id)
        require(isinstance(receipt, dict), "receipt_gate_coverage_mismatch")
        require(supplied.get("local_receipt_current") is True, "local_receipt_not_current")
        require(receipt.get("local_receipt_current") is True, "local_receipt_not_current")
        require(head_matches(supplied.get("verified_head"), current_head), "local_receipt_head_mismatch")
        require(head_matches(receipt.get("verified_head"), current_head), "local_receipt_head_mismatch")
        supplied_at = require_current_time(
            supplied.get("verified_at"),
            now=now,
            max_age_seconds=max_age_seconds,
            code="local_receipt_verified_at_invalid",
        )
        receipt_at = require_current_time(
            receipt.get("verified_at"),
            now=now,
            max_age_seconds=max_age_seconds,
            code="local_receipt_verified_at_invalid",
        )
        require(supplied_at == receipt_at, "local_receipt_time_mismatch")

        supplied_commands = supplied.get("commands") or []
        receipt_commands = receipt.get("commands") or []
        require(bool(supplied_commands) and all(isinstance(item, dict) for item in supplied_commands), "local_receipt_commands_missing")
        require(bool(receipt_commands) and all(isinstance(item, dict) for item in receipt_commands), "local_receipt_commands_missing")
        supplied_signatures = [command_signature(item) for item in supplied_commands]
        receipt_signatures = [command_signature(item) for item in receipt_commands]
        require(supplied_signatures == receipt_signatures, "local_receipt_command_evidence_mismatch")
        require(len({item["command"] for item in supplied_signatures}) == len(supplied_signatures), "local_receipt_command_duplicate")
        for command in supplied_signatures:
            require(bool(command["command"]), "local_receipt_command_missing")
            require(command["status"] == "passed", "local_receipt_command_not_passed")
            require(bool(command["contract"]), "local_receipt_command_contract_missing")
            require(command["skipped"] is False, "local_receipt_command_skipped")
        supplied_command_names = {item["command"] for item in supplied_signatures}
        require(
            set(required_commands[gate_id]).issubset(supplied_command_names),
            "local_receipt_required_command_missing",
        )
        validated[gate_id] = {
            "verified_head": str(receipt.get("verified_head")),
            "verified_at": receipt_at.replace(microsecond=0).isoformat(),
            "command_count": len(receipt_signatures),
            "command_evidence_sha256": sha256_json(receipt_signatures),
        }
    return validated


def required_commands_by_gate(repo_root: Path) -> dict[str, list[str]]:
    packet_path = repo_root / "docs" / "COMMERCIAL_RELEASE_EVIDENCE_PACKET.json"
    packet = read_json(packet_path)
    require(packet.get("contract_id") == RELEASE_PACKET_CONTRACT_ID, "release_packet_contract_mismatch")
    required = {
        str(item.get("id") or ""): [str(command) for command in item.get("required_commands") or []]
        for item in packet.get("phase_gate_evidence") or []
        if isinstance(item, dict) and str(item.get("id") or "") in REQUIRED_GATE_IDS
    }
    require(set(required) == set(REQUIRED_GATE_IDS), "release_packet_gate_coverage_mismatch")
    require(all(required[gate_id] for gate_id in REQUIRED_GATE_IDS), "release_packet_required_commands_missing")
    return required


def validate_receipts(receipts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    require(receipts.get("contract_id") == RECEIPTS_CONTRACT_ID, "receipts_contract_mismatch")
    require(receipts.get("release_complete") is False, "receipts_release_state_not_fail_closed")
    require(receipts.get("commercial_handoff_allowed") is False, "receipts_release_state_not_fail_closed")
    require(receipts.get("ready_to_merge") is False, "receipts_release_state_not_fail_closed")
    phase_receipts = receipts.get("phase_gate_receipts") or []
    require(all(isinstance(item, dict) for item in phase_receipts), "receipt_gate_invalid")
    receipt_map = {str(item.get("gate_id") or ""): item for item in phase_receipts}
    require(len(receipt_map) == len(phase_receipts), "receipt_gate_duplicate")
    require(set(receipt_map) == set(REQUIRED_GATE_IDS), "receipt_gate_coverage_mismatch")
    summary = receipts.get("receipt_summary") or {}
    require(summary.get("gates_with_local_receipts") == REQUIRED_GATE_IDS, "local_receipt_summary_mismatch")
    require(summary.get("gates_missing_local_receipts") == [], "local_receipt_summary_mismatch")
    command_counts = summary.get("local_receipt_command_counts") or {}
    for gate_id in REQUIRED_GATE_IDS:
        require(command_counts.get(gate_id) == len(receipt_map[gate_id].get("commands") or []), "local_receipt_command_count_mismatch")
    return receipt_map


def validate_recording_receipt_against_head(
    *,
    repo_root: Path,
    receipts_path: Path,
    receipts: dict[str, Any],
    current_head: str,
    now: datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    relative_path = str(receipts_path.relative_to(repo_root))
    head_raw = tracked_head_bytes(repo_root, relative_path)
    try:
        head_receipts = json.loads(head_raw)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PromotionRejected("head_receipts_json_invalid") from exc
    require(isinstance(head_receipts, dict), "head_receipts_json_invalid")
    require(head_receipts.get("contract_id") == RECEIPTS_CONTRACT_ID, "head_receipts_contract_mismatch")

    baseline_transactions = [
        item for item in head_receipts.get("receipt_recording_transactions") or [] if isinstance(item, dict)
    ]
    current_transactions = [
        item for item in receipts.get("receipt_recording_transactions") or [] if isinstance(item, dict)
    ]
    require(
        len(current_transactions) == len(baseline_transactions) + 1
        and current_transactions[:-1] == baseline_transactions,
        "recording_transaction_lineage_invalid",
    )
    transaction = current_transactions[-1]
    expected_transaction_id = f"tx_receipt_recording_{current_head[:12]}"
    recorded_at = require_current_time(
        transaction.get("recorded_at"),
        now=now,
        max_age_seconds=max_age_seconds,
        code="recording_transaction_recorded_at_invalid",
    ).replace(microsecond=0).isoformat()
    expected_transaction = {
        "transaction_id": expected_transaction_id,
        "recorded_at": recorded_at,
        "operation": RECORDING_TRANSACTION_OPERATION,
        "selected_gate_ids": list(REQUIRED_GATE_IDS),
        "current_git_head": current_head,
        "exact_head_ci_verified": True,
        "real_runtime_acceptance_verified": True,
        "current_runtime_evidence_supplied": True,
        "writes_release_grade_receipts": False,
        "allows_handoff_or_merge": False,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "token_values_omitted": True,
    }
    require(transaction == expected_transaction, "recording_transaction_evidence_invalid")

    expected = copy.deepcopy(head_receipts)
    expected_map = {
        str(item.get("gate_id") or ""): item
        for item in expected.get("phase_gate_receipts") or []
        if isinstance(item, dict)
    }
    require(set(expected_map) == set(REQUIRED_GATE_IDS), "head_receipt_gate_coverage_mismatch")
    for gate_id in REQUIRED_GATE_IDS:
        expected_map[gate_id].update({
            "verified_head": current_head,
            "verified_at": recorded_at,
            "local_receipt_current": True,
            "release_grade_current": False,
            "receipt_state": "local_receipt_recording_preview_ready",
            "evidence_level": "local_current_not_release_grade",
            "release_grade_update_allowed": False,
            "recording_transaction_id": expected_transaction_id,
        })
    expected["receipt_recording_transactions"] = [*baseline_transactions, expected_transaction]
    expected["release_complete"] = False
    expected["commercial_handoff_allowed"] = False
    expected["ready_to_merge"] = False
    expected_summary = expected.setdefault("receipt_summary", {})
    expected_summary.update({
        "gates_with_local_receipts": list(REQUIRED_GATE_IDS),
        "gates_with_release_grade_receipts": [],
        "gates_missing_local_receipts": [],
        "gate_5_release_grade_current": False,
    })
    require(
        canonical_json(receipts) == canonical_json(expected),
        "recording_receipt_derivation_mismatch",
    )
    return {
        "transaction_id": expected_transaction_id,
        "recorded_at": recorded_at,
        "head_receipt_sha256": hashlib.sha256(head_raw).hexdigest(),
        "recording_receipt_sha256": sha256_json(receipts),
        "head_baseline_verified": True,
        "recording_derivation_verified": True,
    }


def allowed_change_paths(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    paths: list[str] = []

    def walk(left: Any, right: Any, prefix: str) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                walk(left.get(key), right.get(key), f"{prefix}/{key}")
            return
        if isinstance(left, list) and isinstance(right, list):
            for index in range(max(len(left), len(right))):
                left_value = left[index] if index < len(left) else None
                right_value = right[index] if index < len(right) else None
                walk(left_value, right_value, f"{prefix}/{index}")
            return
        if left != right:
            paths.append(prefix)

    walk(before, after, "")
    return paths


def validate_change_whitelist(paths: list[str]) -> None:
    for path in paths:
        parts = [part for part in path.split("/") if part]
        require(bool(parts), "promotion_change_path_invalid")
        require(not any(part in FORBIDDEN_RECEIPT_FIELDS for part in parts), "promotion_forbidden_receipt_field")
        if parts[0] == "phase_gate_receipts":
            require(len(parts) >= 3 and parts[1].isdigit(), "promotion_change_path_invalid")
            require(parts[2] in GATE_ALLOWED_UPDATE_FIELDS, "promotion_change_path_not_allowed")
        elif parts[0] == "receipt_summary":
            require(len(parts) >= 2 and parts[1] in SUMMARY_ALLOWED_UPDATE_FIELDS, "promotion_change_path_not_allowed")
        elif parts[0] == "promotion_evidence":
            require(len(parts) >= 2 and parts[1] in PROMOTION_EVIDENCE_ALLOWED_UPDATE_FIELDS, "promotion_change_path_not_allowed")
        else:
            require(False, "promotion_change_path_not_allowed")


def build_promoted_receipts(
    *,
    receipts: dict[str, Any],
    receipt_map: dict[str, dict[str, Any]],
    gate_evidence: dict[str, dict[str, Any]],
    ci_reference: dict[str, Any],
    runtime_reference: dict[str, Any],
    git_snapshot: dict[str, Any],
    payload_hash: str,
    promoted_at: str,
    recording_reference: dict[str, Any],
) -> tuple[dict[str, Any], str, list[str]]:
    transaction_seed = {
        "contract": CONTRACT_ID,
        "head": git_snapshot["head"],
        "payload_sha256": payload_hash,
        "receipts_contract": receipts.get("contract_id"),
    }
    transaction_id = f"promotion_{sha256_json(transaction_seed)[:24]}"
    promoted = copy.deepcopy(receipts)
    promoted_map = {
        str(item.get("gate_id")): item
        for item in promoted.get("phase_gate_receipts") or []
        if isinstance(item, dict)
    }
    runtime_safe_ref = {
        key: runtime_reference.get(key)
        for key in [
            "source",
            "verified_head",
            "verified_at",
            "live_openclaw",
            "live_hermes",
            "require_hermes_api",
            "agent_gateway_run_id",
            "openclaw_run_id",
            "hermes_run_id",
            "raw_prompt_omitted",
            "raw_response_omitted",
            "private_transcripts_omitted",
            "token_values_omitted",
            "real_runtime_acceptance_verified",
            "independent_reexecution_verified",
            "independently_verified_at",
            "fixed_command_arguments",
            "fixed_command_sha256",
            "python_isolated_mode",
            "hermes_allow_real_run",
            "fixed_base_url",
            "operator_reference_sha256",
            "operator_run_ids_distinct",
        ]
    }
    for gate_id in REQUIRED_GATE_IDS:
        receipt = promoted_map[gate_id]
        receipt.update({
            "release_grade_current": True,
            "receipt_state": "release_grade_receipt_current",
            "evidence_level": "release_grade_exact_head_ci_and_real_runtime",
            "release_blockers": [
                "release_completion_requires_separate_transaction",
                "commercial_handoff_requires_separate_transaction",
                "merge_readiness_requires_separate_transaction",
            ],
            "release_grade_verified_head": git_snapshot["head"],
            "release_grade_verified_at": promoted_at,
            "release_grade_promotion_id": transaction_id,
            "release_grade_evidence": {
                "contract": CONTRACT_ID,
                "promotion_payload_sha256": payload_hash,
                "exact_head_ci": ci_reference,
                "real_runtime_acceptance": runtime_safe_ref,
                "local_receipt": gate_evidence[gate_id],
            },
        })

    summary = promoted.setdefault("receipt_summary", {})
    summary.update({
        "gates_with_release_grade_receipts": list(REQUIRED_GATE_IDS),
        "gate_5_release_grade_current": True,
        "exact_head_ci_verified": True,
        "remote_sync_verified": True,
        "clean_worktree_verified": False,
        "clean_source_head_verified": True,
        "canonical_receipt_transaction_dirty": True,
        "release_grade_verified_head": git_snapshot["head"],
        "release_grade_verified_at": promoted_at,
        "release_grade_promotion_id": transaction_id,
    })
    promoted["promotion_evidence"] = {
        **dict(promoted.get("promotion_evidence") or {}),
        "state": "exact_head_ci_and_real_runtime_verified_release_grade_blocked",
        "verified_head": git_snapshot["short_head"],
        "verified_at": promoted_at,
        "branch": git_snapshot["branch"],
        "remote_sync_verified": True,
        "clean_worktree_verified": False,
        "clean_source_head_verified": True,
        "canonical_receipt_transaction_dirty": True,
        "recording_transaction_id": recording_reference["transaction_id"],
        "recording_receipt_sha256": recording_reference["recording_receipt_sha256"],
        "head_receipt_sha256": recording_reference["head_receipt_sha256"],
        "exact_head_ci": ci_reference,
        "real_runtime_acceptance": runtime_safe_ref,
        "release_grade_blockers": [
            "release_complete_false",
            "commercial_handoff_not_allowed",
            "ready_to_merge_false",
        ],
        "promotion_transaction_id": transaction_id,
        "promotion_payload_sha256": payload_hash,
    }

    changes = allowed_change_paths(receipts, promoted)
    validate_change_whitelist(changes)
    for gate_id in REQUIRED_GATE_IDS:
        original = receipt_map[gate_id]
        updated = promoted_map[gate_id]
        require(original.get("local_receipt_current") == updated.get("local_receipt_current"), "promotion_local_receipt_mutation_forbidden")
        require(original.get("commands") == updated.get("commands"), "promotion_command_mutation_forbidden")
    for field in ["release_complete", "commercial_handoff_allowed", "ready_to_merge", "status"]:
        require(promoted.get(field) == receipts.get(field), "promotion_release_authority_mutation_forbidden")
    return promoted, transaction_id, changes


def atomic_write_json(path: Path, payload: dict[str, Any], *, expected_input_sha256: str) -> bool:
    require(path.exists(), "receipts_path_missing")
    require(path.is_file() and not path.is_symlink(), "receipts_path_not_regular_file")
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777
    descriptor, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        os.close(descriptor)
        write_json(tmp_path, payload)
        os.chmod(tmp_path, mode)
        with tmp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY)
        replaced = False
        directory_fsync_verified = False
        try:
            require(sha256_json(read_json(path)) == expected_input_sha256, "receipts_changed_during_transaction")
            os.replace(tmp_path, path)
            replaced = True
            try:
                DIRECTORY_FSYNC(directory_fd)
                directory_fsync_verified = True
            except OSError:
                directory_fsync_verified = False
        finally:
            try:
                os.close(directory_fd)
            except OSError:
                if not replaced:
                    raise
                directory_fsync_verified = False
        return directory_fsync_verified
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def prepare_promotion(
    *,
    payload: dict[str, Any],
    receipts_path: Path,
    max_evidence_age_seconds: int,
) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, Any]]:
    require(max_evidence_age_seconds > 0, "max_evidence_age_invalid")
    require(isinstance(payload, dict), "promotion_payload_not_object")
    reject_sensitive_payload(payload)
    require(set(payload).issubset(PAYLOAD_KEYS), "promotion_payload_keys_invalid")
    require((payload.get("contract") or payload.get("contract_id")) == PAYLOAD_CONTRACT_ID, "promotion_payload_contract_mismatch")
    require("exact_head_ci_evidence" in payload, "exact_head_ci_evidence_missing")
    require("real_runtime_acceptance" in payload, "real_runtime_evidence_missing")
    require("phase_gate_receipts" in payload, "phase_gate_payloads_missing")

    repo_root = ROOT.resolve()
    receipts_path = receipts_path.expanduser()
    require(repo_root.is_dir(), "repo_root_missing")
    require(receipts_path.exists(), "receipts_path_missing")
    require(receipts_path.is_file() and not receipts_path.is_symlink(), "receipts_path_not_regular_file")
    receipts_path = receipts_path.resolve()
    require(receipts_path.name == RECEIPTS_BASENAME, "receipts_path_name_invalid")
    require(receipts_path == repo_root / RECEIPTS_RELATIVE_PATH, "receipts_path_not_canonical")
    require_no_git_object_overrides(repo_root)
    git_snapshot = git_state(repo_root, permitted_dirty_path=receipts_path)
    require(payload.get("current_git_head") == git_snapshot["head"], "promotion_payload_head_mismatch")
    critical_head_hashes = verify_critical_head_bytes(repo_root)

    now = datetime.now(timezone.utc)
    created_at = require_current_time(
        payload.get("created_at"),
        now=now,
        max_age_seconds=max_evidence_age_seconds,
        code="promotion_payload_created_at_invalid",
    ).replace(microsecond=0).isoformat()
    receipts = read_json(receipts_path)
    input_receipts_hash = sha256_json(receipts)
    recording_reference = validate_recording_receipt_against_head(
        repo_root=repo_root,
        receipts_path=receipts_path,
        receipts=receipts,
        current_head=git_snapshot["head"],
        now=now,
        max_age_seconds=max_evidence_age_seconds,
    )
    receipt_map = validate_receipts(receipts)
    payload_ci = payload.get("exact_head_ci_evidence") or {}
    ci_reference = independently_verify_ci(
        repo_root=repo_root,
        current_head=git_snapshot["head"],
        branch=git_snapshot["branch"],
        payload_ci=payload_ci,
    )
    payload_runtime_reference = validate_runtime_evidence(
        payload.get("real_runtime_acceptance") or {},
        current_head=git_snapshot["head"],
        now=now,
        max_age_seconds=max_evidence_age_seconds,
    )
    gate_evidence = validate_gate_payloads(
        payload.get("phase_gate_receipts"),
        receipt_map=receipt_map,
        required_commands=required_commands_by_gate(repo_root),
        current_head=git_snapshot["head"],
        now=now,
        max_age_seconds=max_evidence_age_seconds,
    )
    payload_hash = sha256_json(payload)
    promoted, transaction_id, changes = build_promoted_receipts(
        receipts=receipts,
        receipt_map=receipt_map,
        gate_evidence=gate_evidence,
        ci_reference=ci_reference,
        runtime_reference=payload_runtime_reference,
        git_snapshot=git_snapshot,
        payload_hash=payload_hash,
        promoted_at=created_at,
        recording_reference=recording_reference,
    )
    result = {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": "promotion_preview_ready",
        "transaction_id": transaction_id,
        "promotion_payload_sha256": payload_hash,
        "target": str(receipts_path),
        "current_git_head": git_snapshot["head"],
        "branch": git_snapshot["branch"],
        "preview_by_default": True,
        "requires_confirmation": True,
        "confirm_flag": "--confirm-promotion",
        "confirmation_supplied": False,
        "applied": False,
        "changed": False,
        "idempotent": canonical_json(receipts) == canonical_json(promoted),
        "would_change_paths": changes,
        "would_change_count": len(changes),
        "selected_gate_ids": list(REQUIRED_GATE_IDS),
        "checks": {
            "current_head_verified": True,
            "exact_head_ci_verified": True,
            "exact_head_ci_independently_verified_via_github_api": True,
            "payload_runtime_reference_valid": True,
            "real_runtime_acceptance_independently_verified": False,
            "current_runtime_evidence_verified": False,
            "confirm_runtime_reexecution_required": True,
            "clean_worktree_verified": git_snapshot.get("worktree_clean") is True,
            "clean_source_head_verified": True,
            "recording_receipt_derivation_verified": True,
            "promotion_input_only_dirty": git_snapshot.get("promotion_input_only_dirty") is True,
            "critical_head_bytes_verified": True,
            "repository_identity_verified": True,
            "remote_sync_verified": True,
            "all_gate_local_receipts_current": True,
            "all_gate_commands_current_and_passed": True,
            "sensitive_payload_scan_passed": True,
            "change_whitelist_verified": True,
        },
        "safety": {
            "operator_payload_required": True,
            "preview_only": True,
            "live_runtime_executed": False,
            "receipts_written": False,
            "atomic_replace": False,
            "release_complete_unchanged": True,
            "commercial_handoff_allowed_unchanged": True,
            "ready_to_merge_unchanged": True,
            "payload_omission_policy_valid": True,
            "runtime_raw_prompt_omission_independently_verified": False,
            "runtime_raw_response_omission_independently_verified": False,
            "runtime_private_transcript_omission_independently_verified": False,
            "runtime_token_omission_independently_verified": False,
        },
    }
    context = {
        "repo_root": repo_root,
        "receipts": receipts,
        "receipt_map": receipt_map,
        "gate_evidence": gate_evidence,
        "ci_reference": ci_reference,
        "payload_ci": payload_ci,
        "payload_runtime_reference": payload_runtime_reference,
        "git_snapshot": git_snapshot,
        "payload_hash": payload_hash,
        "promoted_at": created_at,
        "recording_reference": recording_reference,
        "critical_head_hashes": critical_head_hashes,
    }
    return result, promoted, input_receipts_hash, context


def _run_promotion_locked(
    *,
    payload: dict[str, Any],
    receipts_path: Path,
    max_evidence_age_seconds: int = DEFAULT_MAX_EVIDENCE_AGE_SECONDS,
    confirm_promotion: bool = False,
) -> dict[str, Any]:
    result, promoted, input_receipts_hash, context = prepare_promotion(
        payload=payload,
        receipts_path=receipts_path,
        max_evidence_age_seconds=max_evidence_age_seconds,
    )
    if not confirm_promotion:
        return result
    runtime_reference = run_fixed_runtime_acceptance(
        repo_root=context["repo_root"],
        payload_runtime=context["payload_runtime_reference"],
    )
    post_runtime_git = git_state(
        context["repo_root"],
        permitted_dirty_path=receipts_path.expanduser().resolve(),
    )
    require(post_runtime_git["head"] == context["git_snapshot"]["head"], "git_head_changed_during_runtime_acceptance")
    post_runtime_ci = independently_verify_ci(
        repo_root=context["repo_root"],
        current_head=post_runtime_git["head"],
        branch=post_runtime_git["branch"],
        payload_ci=context["payload_ci"],
    )
    require(
        canonical_json(post_runtime_ci) == canonical_json(context["ci_reference"]),
        "independent_ci_changed_during_runtime_acceptance",
    )
    existing_summary = context["receipts"].get("receipt_summary") or {}
    if existing_summary.get("release_grade_promotion_id") == result.get("transaction_id"):
        final_promoted_at = str(existing_summary.get("release_grade_verified_at") or "")
        require(bool(final_promoted_at), "existing_promotion_timestamp_missing")
    else:
        final_promoted_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    runtime_reference["independently_verified_at"] = final_promoted_at
    promoted, transaction_id, changes = build_promoted_receipts(
        receipts=context["receipts"],
        receipt_map=context["receipt_map"],
        gate_evidence=context["gate_evidence"],
        ci_reference=post_runtime_ci,
        runtime_reference=runtime_reference,
        git_snapshot=post_runtime_git,
        payload_hash=context["payload_hash"],
        promoted_at=final_promoted_at,
        recording_reference=context["recording_reference"],
    )
    require(transaction_id == result.get("transaction_id"), "promotion_transaction_id_changed")
    result["would_change_paths"] = changes
    result["would_change_count"] = len(changes)
    current = read_json(receipts_path.expanduser().resolve())
    require(sha256_json(current) == input_receipts_hash, "receipts_changed_during_transaction")
    changed = canonical_json(current) != canonical_json(promoted)
    directory_fsync_verified = True
    if changed:
        directory_fsync_verified = atomic_write_json(
            receipts_path.expanduser().resolve(),
            promoted,
            expected_input_sha256=input_receipts_hash,
        )
    result.update({
        "status": "promotion_applied" if changed else "promotion_already_applied",
        "confirmation_supplied": True,
        "applied": True,
        "changed": changed,
        "idempotent": not changed,
    })
    if changed and not directory_fsync_verified:
        result["ok"] = False
        result["status"] = "promotion_applied_durability_unverified"
        result["warnings"] = ["receipt_replaced_but_directory_fsync_not_verified"]
    result["checks"].update({
        "real_runtime_acceptance_independently_verified": True,
        "current_runtime_evidence_verified": True,
        "confirm_runtime_reexecution_required": False,
        "runtime_reexecution_distinct_from_operator_reference": True,
        "exact_head_ci_reverified_after_runtime": True,
    })
    result["safety"].update({
        "preview_only": False,
        "live_runtime_executed": True,
        "runtime_raw_prompt_omission_independently_verified": True,
        "runtime_raw_response_omission_independently_verified": True,
        "runtime_private_transcript_omission_independently_verified": True,
        "runtime_token_omission_independently_verified": True,
        "receipts_written": changed,
        "atomic_replace": changed,
        "directory_fsync_verified": directory_fsync_verified if changed else True,
    })
    return result


def run_promotion(
    *,
    payload: dict[str, Any],
    receipts_path: Path,
    max_evidence_age_seconds: int = DEFAULT_MAX_EVIDENCE_AGE_SECONDS,
    confirm_promotion: bool = False,
) -> dict[str, Any]:
    repo_root = ROOT.resolve()
    canonical_receipts_path = receipts_path.expanduser().resolve()
    require(canonical_receipts_path.exists(), "receipts_path_missing")
    require(
        canonical_receipts_path.is_file() and not canonical_receipts_path.is_symlink(),
        "receipts_path_not_regular_file",
    )
    pre_lock_receipts_sha256 = hashlib.sha256(canonical_receipts_path.read_bytes()).hexdigest()
    with promotion_transaction_lock(repo_root, canonical_receipts_path):
        require(
            hashlib.sha256(canonical_receipts_path.read_bytes()).hexdigest() == pre_lock_receipts_sha256,
            "receipts_changed_before_transaction_lock",
        )
        result = _run_promotion_locked(
            payload=payload,
            receipts_path=canonical_receipts_path,
            max_evidence_age_seconds=max_evidence_age_seconds,
            confirm_promotion=confirm_promotion,
        )
    result.setdefault("checks", {})["cross_process_transaction_lock"] = True
    return result


def main() -> int:
    if sys.flags.isolated != 1 or not sys.dont_write_bytecode or sys.flags.no_site != 1:
        print(json.dumps({
            "ok": False,
            "contract": CONTRACT_ID,
            "status": "promotion_rejected",
            "error_code": "isolated_launcher_required",
            "applied": False,
            "safety": {"receipts_written": False, "raw_payload_echoed": False},
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    try:
        require_trusted_running_python()
    except PromotionRejected as exc:
        print(json.dumps({
            "ok": False,
            "contract": CONTRACT_ID,
            "status": "promotion_rejected",
            "error_code": str(exc),
            "applied": False,
            "safety": {"receipts_written": False, "raw_payload_echoed": False},
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    parser = argparse.ArgumentParser(description="Promote Gate 1-5 release-grade receipts from an operator-supplied evidence payload.")
    parser.add_argument("--promotion-payload-json", required=True, help="Operator-supplied promotion payload path, or '-' for stdin.")
    parser.add_argument("--receipts-path", required=True, help=f"Specific {RECEIPTS_BASENAME} path to preview or update.")
    parser.add_argument(
        "--max-evidence-age-seconds",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_AGE_SECONDS,
        help="Maximum age for the payload, runtime evidence, and Gate 1-5 local receipts.",
    )
    parser.add_argument("--confirm-promotion", action="store_true", help="Atomically update --receipts-path. Default is preview only.")
    args = parser.parse_args()

    try:
        payload = load_recording_payload(args.promotion_payload_json)
        result = run_promotion(
            payload=payload,
            receipts_path=Path(args.receipts_path),
            max_evidence_age_seconds=args.max_evidence_age_seconds,
            confirm_promotion=bool(args.confirm_promotion),
        )
    except (PromotionRejected, AssertionError, json.JSONDecodeError, OSError, UnicodeError) as exc:
        code = str(exc) if isinstance(exc, PromotionRejected) else "promotion_input_rejected"
        print(json.dumps({
            "ok": False,
            "contract": CONTRACT_ID,
            "status": "promotion_rejected",
            "error_code": code,
            "applied": False,
            "safety": {
                "receipts_written": False,
                "raw_payload_echoed": False,
            },
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") is True else 3


if __name__ == "__main__":
    raise SystemExit(main())
