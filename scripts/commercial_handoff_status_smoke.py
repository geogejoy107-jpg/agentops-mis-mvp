#!/usr/bin/env python3
"""Emit and guard the commercial handoff status packet."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from github_ci_evidence import ci_status as shared_ci_status


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "COMMERCIAL_EVIDENCE_PACKET_INDEX.md"
BREAKDOWN = ROOT / "docs" / "COMMERCIAL_MIGRATION_CLEAN_ROOM_BREAKDOWN.md"
RELEASE_PACKET = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
INDEX_ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_EVIDENCE_PACKET_INDEX_ACCEPTANCE.md"
CURRENT_ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_CURRENT_EVIDENCE_STATUS_ACCEPTANCE.md"
HANDOFF_ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_HANDOFF_STATUS_ACCEPTANCE.md"

SOURCE_DOCS = [
    INDEX,
    BREAKDOWN,
    RELEASE_PACKET,
    CI_WORKFLOW,
    INDEX_ACCEPTANCE,
    CURRENT_ACCEPTANCE,
    HANDOFF_ACCEPTANCE,
]
COMMAND = "python3 scripts/commercial_handoff_status_smoke.py"

EXPECTED_LANES = [
    "Commercial Read Models",
    "Workspace And RBAC Scope",
    "Storage Boundary",
    "Commercial Evidence Packets",
    "UI Route Retirement And Parity",
    "Deployment And BYOC Readiness",
]

PACKET_STATUS = {
    "Current Evidence Status": "generator_smoke_added",
    "Release Evidence Packet": "existing_generator",
    "Commercial Handoff Status": "generator_smoke_added",
    "Promotion Preflight": "generator_smoke_added",
    "Promotion Packet": "generator_smoke_added",
    "Receipt Plan": "generator_smoke_added",
    "Receipt Recording": "generator_smoke_added",
    "Rerun Bundle Preview": "generator_smoke_added",
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
    breakdown_text = texts.get(BREAKDOWN, "")
    release_text = texts.get(RELEASE_PACKET, "")
    ci_text = texts.get(CI_WORKFLOW, "")
    handoff_text = texts.get(HANDOFF_ACCEPTANCE, "")

    require("Commercial Handoff Status" in index_text, "index missing Commercial Handoff Status row", failures)
    require("generator smoke added" in index_text, "index must mark handoff status as generator-smoke guarded", failures)
    require(COMMAND in index_text, "index missing handoff command", failures)
    require(COMMAND in release_text, "release packet doc missing handoff command", failures)
    require(COMMAND in ci_text, "CI workflow missing handoff command", failures)
    require("read-only handoff packet" in handoff_text, "handoff acceptance missing read-only packet boundary", failures)

    for lane in EXPECTED_LANES:
        require(f"Lane {EXPECTED_LANES.index(lane) + 1}: {lane}" in breakdown_text, f"missing clean-room lane: {lane}", failures)
    require("Do not merge PR #22 directly." in breakdown_text, "PR #22 direct-merge block missing", failures)
    require("Start with Lane 1 or Lane 4." in breakdown_text, "recommended starting lane missing", failures)

    for packet, status in PACKET_STATUS.items():
        require(packet in index_text, f"missing packet row: {packet}", failures)
        require(status != "generator_smoke_added" or "generator smoke added" in index_text, f"missing generator status for packet: {packet}", failures)

    joined = "\n".join(texts.values())
    for claim in unsafe_claim_hits(joined):
        require(False, f"unsafe positive commercial claim found: {claim}", failures)
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in handoff sources: {secret_hits}", failures)

    generated_docs = [INDEX, HANDOFF_ACCEPTANCE]
    hardcoded = [path.name for path in generated_docs if has_hardcoded_sha(texts.get(path, ""))]
    require(not hardcoded, f"hard-coded SHA found in commercial handoff docs: {hardcoded}", failures)


def lane_status() -> list[dict[str, str]]:
    return [
        {
            "lane": "Lane 1",
            "name": "Commercial Read Models",
            "status": "partially_started",
            "evidence": "commercial config status and current-evidence status readbacks exist; no billing or cleanup.",
        },
        {
            "lane": "Lane 4",
            "name": "Commercial Evidence Packets",
            "status": "active",
            "evidence": "packet index, current evidence status and handoff status are generator-smoke guarded.",
        },
        {
            "lane": "Lane 2",
            "name": "Workspace And RBAC Scope",
            "status": "queued",
            "evidence": "requires separate workspace/RBAC scope slice.",
        },
        {
            "lane": "Lane 3",
            "name": "Storage Boundary",
            "status": "queued",
            "evidence": "requires separate storage helper parity slice.",
        },
        {
            "lane": "Lane 5",
            "name": "UI Route Retirement And Parity",
            "status": "queued",
            "evidence": "requires separate route inventory and parity slice.",
        },
        {
            "lane": "Lane 6",
            "name": "Deployment And BYOC Readiness",
            "status": "queued",
            "evidence": "requires separate local/customer deployment slice; hosted readiness stays unclaimed.",
        },
    ]


def main() -> int:
    failures: list[str] = []
    texts = {path: read(path) for path in SOURCE_DOCS}
    validate_sources(texts, failures)

    head_sha = git_text(["rev-parse", "HEAD"])
    branch = current_branch()
    ci = shared_ci_status(ROOT, head_sha, branch, required_before_ready=True)
    packets = [
        {"packet": packet, "status": status, "source": "docs/COMMERCIAL_EVIDENCE_PACKET_INDEX.md"}
        for packet, status in PACKET_STATUS.items()
    ]

    output: dict[str, Any] = {
        "operation": "commercial_handoff_status_smoke",
        "ok": not failures,
        "evidence_class": "commercial_handoff_status",
        "handoff_class": "commercial_handoff_status",
        "head": {
            "sha": head_sha,
            "branch": branch,
            "upstream_sync": upstream_sync(),
            "working_tree_entries": len(status_entries()),
        },
        "ci": ci,
        "source_docs": [str(path.relative_to(ROOT)) for path in SOURCE_DOCS],
        "clean_room_lanes": lane_status(),
        "packet_status": packets,
        "next_recommended_generator": "operator_confirmed_receipt_recording",
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
            "pr22_contents_read": False,
            "billing_call_performed": False,
            "cleanup_execution_performed": False,
            "live_execution_performed": False,
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
