#!/usr/bin/env python3
"""Emit and guard the commercial receipt recording packet."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from github_ci_evidence import ci_status as shared_ci_status


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "COMMERCIAL_EVIDENCE_PACKET_INDEX.md"
RELEASE_PACKET = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
APPROVAL_BOUNDARY = ROOT / "docs" / "APPROVAL_SEMANTICS_BOUNDARY.md"
RECEIPT_PLAN_ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_RECEIPT_PLAN_ACCEPTANCE.md"
RECEIPT_RECORDING_ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_RECEIPT_RECORDING_ACCEPTANCE.md"
OPERATOR_RECEIPTS = ROOT / "agentops_mis_core" / "operator_receipts.py"
ACTION_RECEIPT_SMOKE = ROOT / "scripts" / "operator_action_receipt_smoke.py"
ACTION_RECEIPT_CLI_SMOKE = ROOT / "scripts" / "operator_action_receipt_cli_record_smoke.py"

SOURCE_DOCS = [
    INDEX,
    RELEASE_PACKET,
    CI_WORKFLOW,
    APPROVAL_BOUNDARY,
    RECEIPT_PLAN_ACCEPTANCE,
    RECEIPT_RECORDING_ACCEPTANCE,
    OPERATOR_RECEIPTS,
    ACTION_RECEIPT_SMOKE,
    ACTION_RECEIPT_CLI_SMOKE,
]
SECRET_SCAN_SOURCES = [
    INDEX,
    RELEASE_PACKET,
    RECEIPT_PLAN_ACCEPTANCE,
    RECEIPT_RECORDING_ACCEPTANCE,
]

COMMAND = "python3 scripts/commercial_receipt_recording_smoke.py"
RECEIPT_PLAN_COMMAND = "python3 scripts/commercial_receipt_plan_smoke.py"

RISK_CATEGORIES = [
    {
        "risk_category": "billing_provider_call",
        "target_resource": "commercial_config.billing_provider",
        "operator_review": "billing provider calls remain blocked until a prepared action is approved",
    },
    {
        "risk_category": "destructive_cleanup",
        "target_resource": "retention_policy.destructive_cleanup",
        "operator_review": "cleanup execution remains blocked until a prepared action is approved",
    },
    {
        "risk_category": "hosted_customer_data_migration",
        "target_resource": "hosted_workspace.customer_data",
        "operator_review": "hosted customer migration remains blocked until a prepared action is approved",
    },
    {
        "risk_category": "postgres_storage_cutover",
        "target_resource": "storage.postgres_cutover",
        "operator_review": "Postgres cutover remains blocked until a prepared action is approved",
    },
    {
        "risk_category": "live_external_side_effect",
        "target_resource": "external_connector.live_side_effect",
        "operator_review": "live external side effects remain blocked until a prepared action is approved",
    },
]

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9_]+"),
    re.compile(r"AGENTOPS_(API|ADMIN)_KEY=", re.IGNORECASE),
]

UNSAFE_POSITIVE_CLAIMS = [
    "hosted SaaS ready",
    "billing ready",
    "cleanup execution enabled",
    "commercial-ready",
    "Postgres required for local MVP",
    "live runtime execution performed",
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


def status_entries() -> list[str]:
    raw = maybe_git_text(["status", "--porcelain"]) or ""
    return [line for line in raw.splitlines() if line.strip()]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def stable_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def receipt_requests() -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for item in RISK_CATEGORIES:
        risk = item["risk_category"]
        normalized_action = {
            "risk_category": risk,
            "target_resource": item["target_resource"],
            "policy_version": "commercial_receipt_recording_v1",
            "checkpoint": f"commercial_review_before_{risk}",
            "idempotency_key": f"commercial_receipt:{risk}:v1",
            "execution_allowed": False,
            "operator_review": item["operator_review"],
        }
        action_hash = stable_hash(normalized_action)
        review_payload = {
            "reviewer_role": "admin_owner_or_human_approver",
            "source": "commercial_receipt_recording.preview",
            "action_hash": action_hash,
            "status": "review_required",
            "result_summary": f"Review receipt request prepared for {risk}; risky action remains blocked.",
        }
        requests.append(
            {
                "receipt_id": f"commercial_receipt_preview_{risk}",
                "source": "commercial_receipt_recording.preview",
                "status": "review_required",
                "reviewer_role": "admin_owner_or_human_approver",
                "action_id": f"commercial:{risk}",
                "action_signature": f"commercial_receipt_recording_v1:{risk}",
                "target_resource": item["target_resource"],
                "normalized_action_arguments": normalized_action,
                "action_hash": action_hash,
                "review_hash": stable_hash(review_payload),
                "verify_command": COMMAND,
                "recording_mode": "preview_only",
                "recorded_to_ledger": False,
                "execution_allowed": False,
                "token_omitted": True,
            }
        )
    return requests


def unsafe_claim_hits(text: str) -> list[str]:
    hits: list[str] = []
    negative_markers = ("no ", "not ", "never ", "without ", "must not ", "do not ", "unclaimed")
    for line in text.splitlines():
        lowered = line.lower()
        for claim in UNSAFE_POSITIVE_CLAIMS:
            claim_lower = claim.lower()
            if claim_lower not in lowered:
                continue
            claim_index = lowered.find(claim_lower)
            prefix = lowered[max(0, claim_index - 40) : claim_index]
            if any(marker in prefix for marker in negative_markers):
                continue
            hits.append(claim)
    return sorted(set(hits))


def has_hardcoded_sha(text: str) -> bool:
    return bool(re.search(r"\b[0-9a-f]{40}\b", text))


def validate_sources(texts: dict[Path, str], failures: list[str]) -> None:
    for path in SOURCE_DOCS:
        require(path.exists(), f"missing source: {path.relative_to(ROOT)}", failures)

    index_text = texts.get(INDEX, "")
    release_text = texts.get(RELEASE_PACKET, "")
    ci_text = texts.get(CI_WORKFLOW, "")
    approval_text = texts.get(APPROVAL_BOUNDARY, "")
    plan_text = texts.get(RECEIPT_PLAN_ACCEPTANCE, "")
    acceptance_text = texts.get(RECEIPT_RECORDING_ACCEPTANCE, "")
    receipt_core_text = texts.get(OPERATOR_RECEIPTS, "")
    receipt_smoke_text = texts.get(ACTION_RECEIPT_SMOKE, "")
    receipt_cli_text = texts.get(ACTION_RECEIPT_CLI_SMOKE, "")

    require("Receipt Recording" in index_text, "index missing Receipt Recording row", failures)
    require("generator smoke added" in index_text, "index must mark receipt recording as generator-smoke guarded", failures)
    require(COMMAND in index_text, "index missing receipt recording command", failures)
    require("commercial_rerun_bundle_preview_smoke.py" in index_text, "index must advance next generator to rerun bundle preview", failures)
    require(COMMAND in release_text, "release packet doc missing receipt recording command", failures)
    require(COMMAND in ci_text, "CI workflow missing receipt recording command", failures)
    require(COMMAND in acceptance_text, "receipt recording acceptance missing verification command", failures)
    require(RECEIPT_PLAN_COMMAND in plan_text, "receipt plan acceptance missing prerequisite plan command", failures)

    for phrase in [
        "prepared_actions",
        "immutable `action_hash`",
        "idempotency key",
        "checkpoint",
        "human/admin reviewer",
    ]:
        require(phrase in approval_text, f"approval semantics boundary missing phrase: {phrase}", failures)

    for phrase in [
        "operator_action_receipt_public",
        "action_hash",
        "verify_hash",
        "token_omitted",
    ]:
        require(phrase in receipt_core_text, f"operator receipt helper missing phrase: {phrase}", failures)

    for phrase in [
        "operator.action_queue_receipt",
        "runtime_events",
        "operator_action_evaluations",
        "live_execution_performed",
    ]:
        require(phrase in receipt_smoke_text, f"operator receipt smoke missing phrase: {phrase}", failures)

    for phrase in [
        "operator_action_receipt_cli_preview",
        "--confirm-record",
        "ledger_mutated",
    ]:
        require(phrase in receipt_cli_text, f"operator receipt CLI smoke missing phrase: {phrase}", failures)

    joined = "\n".join(texts.get(path, "") for path in SECRET_SCAN_SOURCES)
    for claim in unsafe_claim_hits(joined):
        require(False, f"unsafe positive commercial claim found: {claim}", failures)
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in receipt recording docs: {len(secret_hits)}", failures)

    generated_docs = [INDEX, RECEIPT_RECORDING_ACCEPTANCE]
    hardcoded = [path.name for path in generated_docs if has_hardcoded_sha(texts.get(path, ""))]
    require(not hardcoded, f"hard-coded SHA found in receipt recording docs: {hardcoded}", failures)


def validate_receipts(requests: list[dict[str, Any]], failures: list[str]) -> None:
    require(len(requests) == len(RISK_CATEGORIES), "receipt request count mismatch", failures)
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    for request in requests:
        seen_ids.add(str(request.get("receipt_id") or ""))
        seen_hashes.add(str(request.get("action_hash") or ""))
        normalized = request.get("normalized_action_arguments") or {}
        for field in [
            "risk_category",
            "target_resource",
            "policy_version",
            "checkpoint",
            "idempotency_key",
            "execution_allowed",
        ]:
            require(field in normalized, f"normalized action missing {field}: {request}", failures)
        require(request.get("reviewer_role") == "admin_owner_or_human_approver", f"wrong reviewer role: {request}", failures)
        require(request.get("recording_mode") == "preview_only", f"wrong recording mode: {request}", failures)
        require(request.get("recorded_to_ledger") is False, f"receipt must not be ledger-recorded: {request}", failures)
        require(request.get("execution_allowed") is False, f"receipt must not allow execution: {request}", failures)
        require(normalized.get("execution_allowed") is False, f"normalized action must block execution: {normalized}", failures)
        require(bool(request.get("action_hash")), f"action_hash missing: {request}", failures)
        require(bool(request.get("review_hash")), f"review_hash missing: {request}", failures)
        require(request.get("token_omitted") is True, f"token omission missing: {request}", failures)
    require(len(seen_ids) == len(requests), "receipt IDs must be unique", failures)
    require(len(seen_hashes) == len(requests), "action hashes must be unique", failures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-current-ci",
        action="store_true",
        help="Fail unless the current branch has clean exact-head green CI.",
    )
    args = parser.parse_args()

    failures: list[str] = []
    texts = {path: read(path) for path in SOURCE_DOCS}
    validate_sources(texts, failures)
    requests = receipt_requests()
    validate_receipts(requests, failures)

    head_sha = git_text(["rev-parse", "HEAD"])
    branch = current_branch()
    sync = upstream_sync()
    dirty_count = len(status_entries())
    ci = shared_ci_status(ROOT, head_sha, branch, required_before_ready=True)
    ci_ready = (
        dirty_count == 0
        and sync.get("behind") in (0, None)
        and ci.get("head_matches") is True
        and ci.get("status") == "completed"
        and ci.get("conclusion") == "success"
    )
    if args.require_current_ci and not ci_ready:
        failures.append("current_head_green_ci_required")

    output: dict[str, Any] = {
        "operation": "commercial_receipt_recording_smoke",
        "ok": not failures,
        "evidence_class": "commercial_receipt_recording",
        "head": {
            "sha": head_sha,
            "branch": branch,
            "upstream_sync": sync,
            "working_tree_entries": dirty_count,
        },
        "ci": ci,
        "current_head_ci_ready": ci_ready,
        "receipt_recording_ready": not failures,
        "recording_transaction": {
            "mode": "preview_only",
            "recording_request_count": len(requests),
            "recorded_to_ledger": False,
            "requires_operator_confirmation": True,
            "execution_allowed_by_this_packet": False,
            "source": "commercial_receipt_recording.preview",
        },
        "receipt_requests": requests,
        "commercial_limits": {
            "hosted_ready": False,
            "billing_ready": False,
            "cleanup_execution_enabled": False,
            "postgres_required_for_local_mvp": False,
            "live_runtime_execution_performed": False,
            "direct_pr22_merge_allowed": False,
        },
        "source_docs": [str(path.relative_to(ROOT)) for path in SOURCE_DOCS],
        "next_recommended_generator": "commercial_rerun_bundle_preview_smoke.py",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "db_read": False,
            "env_dumped": False,
            "receipt_recorded": False,
            "billing_call_performed": False,
            "cleanup_execution_performed": False,
            "hosted_migration_performed": False,
            "postgres_cutover_performed": False,
            "live_execution_performed": False,
            "pr22_contents_read": False,
            "raw_logs_omitted": True,
            "raw_prompts_omitted": True,
            "raw_responses_omitted": True,
            "token_omitted": True,
        },
        "failure_count": len(failures),
        "failures": failures,
    }

    rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    output_secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(rendered)]
    if output_secret_hits:
        output["ok"] = False
        output["failure_count"] += 1
        output["failures"].append(f"secret-like marker found in output: {len(output_secret_hits)}")
        rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    return 1 if output["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
