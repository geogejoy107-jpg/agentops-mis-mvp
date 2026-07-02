#!/usr/bin/env python3
"""Emit and guard the commercial rerun bundle preview packet."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "COMMERCIAL_EVIDENCE_PACKET_INDEX.md"
RELEASE_PACKET = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_RERUN_BUNDLE_PREVIEW_ACCEPTANCE.md"

COMMAND = "python3 scripts/commercial_rerun_bundle_preview_smoke.py"

SOURCE_DOCS = [
    INDEX,
    RELEASE_PACKET,
    CI_WORKFLOW,
    ACCEPTANCE,
]

RERUN_COMMANDS = [
    {
        "id": "commercial_evidence_packet_index",
        "command": "python3 scripts/commercial_evidence_packet_index_smoke.py",
        "purpose": "Validate the commercial evidence packet inventory and clean-room boundaries.",
    },
    {
        "id": "commercial_current_evidence_status",
        "command": "python3 scripts/commercial_current_evidence_status_smoke.py",
        "purpose": "Read current-source commercial evidence status without DB, server or live runtime.",
    },
    {
        "id": "commercial_handoff_status",
        "command": "python3 scripts/commercial_handoff_status_smoke.py",
        "purpose": "Show clean-room lane and packet status for the next operator handoff.",
    },
    {
        "id": "commercial_promotion_preflight",
        "command": "python3 scripts/commercial_promotion_preflight_smoke.py",
        "purpose": "Check branch, CI and safety gates before promotion review.",
    },
    {
        "id": "commercial_promotion_packet",
        "command": "python3 scripts/commercial_promotion_packet_smoke.py",
        "purpose": "Bundle current-source promotion evidence references.",
    },
    {
        "id": "commercial_receipt_plan",
        "command": "python3 scripts/commercial_receipt_plan_smoke.py",
        "purpose": "Define review receipts required before risky commercial actions.",
    },
    {
        "id": "commercial_receipt_recording",
        "command": "python3 scripts/commercial_receipt_recording_smoke.py",
        "purpose": "Preview receipt records and hashes without ledger mutation or execution.",
    },
    {
        "id": "commercial_rerun_bundle_preview",
        "command": COMMAND,
        "purpose": "List this reproducible command bundle without running live systems.",
    },
    {
        "id": "release_branch_control",
        "command": "python3 scripts/release_branch_control_smoke.py",
        "purpose": "Confirm branch and upstream posture for local reproduction.",
    },
    {
        "id": "release_evidence_packet",
        "command": "python3 scripts/release_evidence_packet_smoke.py",
        "purpose": "Confirm the release command manifest includes the commercial packet chain.",
    },
    {
        "id": "secret_scan",
        "command": "python3 scripts/secret_scan_smoke.py",
        "purpose": "Reject committed secret-like material before sharing the bundle.",
    },
    {
        "id": "diff_check",
        "command": "git diff --check",
        "purpose": "Check whitespace diff hygiene.",
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


def validate_sources(texts: dict[Path, str], failures: list[str]) -> None:
    for path in SOURCE_DOCS:
        require(path.exists(), f"missing source: {path.relative_to(ROOT)}", failures)

    index_text = texts.get(INDEX, "")
    release_text = texts.get(RELEASE_PACKET, "")
    ci_text = texts.get(CI_WORKFLOW, "")
    acceptance_text = texts.get(ACCEPTANCE, "")

    require("Rerun Bundle Preview" in index_text, "index missing Rerun Bundle Preview row", failures)
    require("commercial_rerun_bundle_preview_smoke.py" in index_text, "index missing rerun bundle command", failures)
    require("generator smoke added" in index_text, "index must mark rerun bundle as generator-smoke guarded", failures)
    require(COMMAND in release_text, "release packet doc missing rerun bundle command", failures)
    require(COMMAND in ci_text, "CI workflow missing rerun bundle command", failures)
    require(COMMAND in acceptance_text, "rerun bundle acceptance missing verification command", failures)
    require("reproduce the commercial evidence packet chain" in acceptance_text, "acceptance missing reproducibility purpose", failures)

    for item in RERUN_COMMANDS:
        command = item["command"]
        require(command in release_text or command == "git diff --check", f"release packet missing rerun command: {command}", failures)
        require("python3 " not in command or command in ci_text or command == "python3 scripts/release_branch_control_smoke.py", f"CI missing rerun command: {command}", failures)

    joined = "\n".join(texts.values())
    for claim in unsafe_claim_hits(joined):
        require(False, f"unsafe positive commercial claim found: {claim}", failures)
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in rerun bundle sources: {secret_hits}", failures)
    require(not re.search(r"\b[0-9a-f]{40}\b", acceptance_text), "acceptance doc must not pin stale SHA", failures)


def main() -> int:
    failures: list[str] = []
    texts = {path: read(path) for path in SOURCE_DOCS}
    validate_sources(texts, failures)

    output: dict[str, Any] = {
        "operation": "commercial_rerun_bundle_preview_smoke",
        "ok": not failures,
        "evidence_class": "commercial_rerun_bundle_preview",
        "head": {
            "sha": git_text(["rev-parse", "HEAD"]),
            "branch": maybe_git_text(["branch", "--show-current"]) or "DETACHED",
            "upstream_sync": upstream_sync(),
            "working_tree_entries": len(status_entries()),
        },
        "bundle": {
            "mode": "preview_only",
            "purpose": "reproduce the commercial evidence packet chain on another machine",
            "command_count": len(RERUN_COMMANDS),
            "commands": RERUN_COMMANDS,
        },
        "source_docs": [str(path.relative_to(ROOT)) for path in SOURCE_DOCS],
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
            "server_started": False,
            "ledger_mutated": False,
            "db_read": False,
            "env_dumped": False,
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
