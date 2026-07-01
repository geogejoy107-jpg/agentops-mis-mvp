#!/usr/bin/env python3
"""Emit and guard the commercial receipt plan packet."""
from __future__ import annotations

import argparse
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
FREEZE_PROTOCOL = ROOT / "docs" / "RELEASE_FREEZE_PROTOCOL.md"
PROMOTION_PACKET_ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_PROMOTION_PACKET_ACCEPTANCE.md"
RECEIPT_PLAN_ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_RECEIPT_PLAN_ACCEPTANCE.md"

SOURCE_DOCS = [
    INDEX,
    RELEASE_PACKET,
    CI_WORKFLOW,
    APPROVAL_BOUNDARY,
    FREEZE_PROTOCOL,
    PROMOTION_PACKET_ACCEPTANCE,
    RECEIPT_PLAN_ACCEPTANCE,
]
COMMAND = "python3 scripts/commercial_receipt_plan_smoke.py"
PROMOTION_PACKET_COMMAND = "python3 scripts/commercial_promotion_packet_smoke.py"

CANONICAL_GATES = {
    "promotion_packet": PROMOTION_PACKET_COMMAND,
    "approval_semantics_boundary": "python3 scripts/approval_semantics_boundary_smoke.py",
    "prepared_action_wall": "python3 scripts/prepared_action_approval_wall_smoke.py --base-url \"$AGENTOPS_BASE_URL\"",
    "release_freeze": "python3 scripts/release_freeze_protocol_smoke.py",
    "release_evidence": "python3 scripts/release_evidence_packet_smoke.py",
    "secret_scan": "python3 scripts/secret_scan_smoke.py",
}

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
    freeze_text = texts.get(FREEZE_PROTOCOL, "")
    acceptance_text = texts.get(RECEIPT_PLAN_ACCEPTANCE, "")

    require("Receipt Plan" in index_text, "index missing Receipt Plan row", failures)
    require("generator smoke added" in index_text, "index must mark receipt plan as generator-smoke guarded", failures)
    require(COMMAND in index_text, "index missing receipt plan command", failures)
    require(COMMAND in release_text, "release packet doc missing receipt plan command", failures)
    require(COMMAND in ci_text, "CI workflow missing receipt plan command", failures)
    require(COMMAND in acceptance_text, "receipt plan acceptance missing verification command", failures)
    require("commercial_receipt_recording_smoke.py" in index_text, "index must advance next generator to receipt recording", failures)

    for gate_name, gate_command in CANONICAL_GATES.items():
        require(gate_command in release_text, f"release packet missing canonical gate: {gate_name}", failures)

    for phrase in [
        "prepared_actions",
        "immutable `action_hash`",
        "idempotency key",
        "checkpoint",
        "Execution evidence",
    ]:
        require(phrase in approval_text, f"approval semantics boundary missing phrase: {phrase}", failures)
    require("ACTIVE_HARDENING_FREEZE" in freeze_text, "release freeze state missing", failures)
    require("Public/commercial readiness claims" in freeze_text, "release freeze commercial claim guard missing", failures)

    joined = "\n".join(texts.values())
    for claim in unsafe_claim_hits(joined):
        require(False, f"unsafe positive commercial claim found: {claim}", failures)
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in receipt plan sources: {secret_hits}", failures)

    generated_docs = [INDEX, RECEIPT_PLAN_ACCEPTANCE]
    hardcoded = [path.name for path in generated_docs if has_hardcoded_sha(texts.get(path, ""))]
    require(not hardcoded, f"hard-coded SHA found in receipt plan docs: {hardcoded}", failures)


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
        "operation": "commercial_receipt_plan_smoke",
        "ok": not failures,
        "evidence_class": "commercial_receipt_plan",
        "head": {
            "sha": head_sha,
            "branch": branch,
            "upstream_sync": sync,
            "working_tree_entries": dirty_count,
        },
        "ci": ci,
        "receipt_plan_ready": not failures,
        "current_head_ci_ready": ci_ready,
        "source_docs": [str(path.relative_to(ROOT)) for path in SOURCE_DOCS],
        "review_receipt_requirements": {
            "reviewer_role": "admin_owner_or_human_approver",
            "required_before": [
                "billing_provider_call",
                "destructive_cleanup",
                "hosted_customer_data_migration",
                "postgres_storage_cutover",
                "live_external_side_effect",
            ],
            "prepared_action_fields": [
                "normalized_action_arguments",
                "target_resource",
                "policy_version",
                "checkpoint",
                "idempotency_key",
                "immutable_action_hash",
            ],
            "generic_ledger_approval_is_not_exact_resume": True,
            "execution_allowed_by_this_packet": False,
        },
        "canonical_commands": CANONICAL_GATES,
        "next_recommended_generator": "commercial_receipt_recording_smoke.py",
        "commercial_limits": {
            "hosted_ready": False,
            "billing_ready": False,
            "cleanup_execution_enabled": False,
            "postgres_required_for_local_mvp": False,
            "live_runtime_execution_performed": False,
            "direct_pr22_merge_allowed": False,
        },
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "db_read": False,
            "env_dumped": False,
            "billing_call_performed": False,
            "cleanup_execution_performed": False,
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
        output["failures"].append(f"secret-like marker found in output: {output_secret_hits}")
        rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    return 1 if output["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
