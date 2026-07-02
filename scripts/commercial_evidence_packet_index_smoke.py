#!/usr/bin/env python3
"""Validate the commercial evidence packet index stays safe and actionable."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "COMMERCIAL_EVIDENCE_PACKET_INDEX.md"
ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_EVIDENCE_PACKET_INDEX_ACCEPTANCE.md"

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

PACKETS = [
    "Current Evidence Status",
    "Release Evidence Packet",
    "Commercial Handoff Status",
    "Promotion Preflight",
    "Promotion Packet",
    "Receipt Plan",
    "Receipt Recording",
    "Rerun Bundle Preview",
    "Confirmed Receipt Recording",
    "Prepared Action Receipt Binding",
    "Prepared Action Execution Receipt",
]

FUTURE_SMOKES = [
    "commercial_current_evidence_status_smoke.py",
    "release_evidence_packet_smoke.py",
    "commercial_handoff_status_smoke.py",
    "commercial_promotion_preflight_smoke.py",
    "commercial_promotion_packet_smoke.py",
    "commercial_receipt_plan_smoke.py",
    "commercial_receipt_recording_smoke.py",
    "commercial_rerun_bundle_preview_smoke.py",
    "commercial_confirmed_receipt_recording_smoke.py",
    "commercial_receipt_prepared_action_binding_smoke.py",
    "commercial_prepared_action_execution_receipt_smoke.py",
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    text = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
    acceptance = ACCEPTANCE.read_text(encoding="utf-8") if ACCEPTANCE.exists() else ""

    require(DOC.exists(), "missing docs/COMMERCIAL_EVIDENCE_PACKET_INDEX.md", failures)
    require(ACCEPTANCE.exists(), "missing docs/COMMERCIAL_EVIDENCE_PACKET_INDEX_ACCEPTANCE.md", failures)

    required_markers = {
        "lane": "Lane 4",
        "current_main": "rebuild from current `origin/main`",
        "pr22_reference": "PR #22 status: reference evidence only",
        "first_party_authority": "AgentOps MIS first-party ledgers",
        "no_stale_snapshots": "stale packet snapshots copied from PR #22",
        "exact_head_ci": "Require current-head green CI",
        "safe_storage": "Store hashes, paths, counts, and safe summaries only.",
        "one_generator": "Add one packet generator at a time",
        "next_slice": "commercial_current_evidence_status_smoke.py",
    }
    for label, marker in required_markers.items():
        require(marker in text, f"missing index marker {label}: {marker}", failures)

    forbidden_inputs = [
        "raw logs",
        "raw prompts",
        "raw model responses",
        "private messages or full transcripts",
        "credentials, tokens, `.env`, or secret-bearing config",
        "local SQLite DBs or DB dumps",
        "`node_modules`, `dist`, caches, or generated export snapshots",
    ]
    for marker in forbidden_inputs:
        require(marker in text, f"missing forbidden input marker: {marker}", failures)

    for packet in PACKETS:
        require(packet in text, f"missing packet inventory row: {packet}", failures)
    for smoke in FUTURE_SMOKES:
        require(smoke in text, f"missing packet smoke name: {smoke}", failures)

    unsafe_claims = [
        "hosted SaaS ready",
        "billing ready",
        "cleanup execution enabled",
        "Postgres required for local MVP",
        "commercial-ready",
        "live runtime execution performed",
    ]
    for claim in unsafe_claims:
        require(claim not in text, f"unsafe commercial claim found: {claim}", failures)

    acceptance_markers = [
        "index/gate only",
        "does not implement packet generation",
        "No packet is generated or committed",
        "No live Hermes/OpenClaw execution is required",
    ]
    for marker in acceptance_markers:
        require(marker in acceptance, f"acceptance missing boundary marker: {marker}", failures)

    secret_hits = [
        pattern.pattern
        for pattern in SECRET_PATTERNS
        if pattern.search(text) or pattern.search(acceptance)
    ]
    require(not secret_hits, f"secret-like marker found in packet index docs: {secret_hits}", failures)

    output = {
        "operation": "commercial_evidence_packet_index_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "docs": [
            str(DOC.relative_to(ROOT)),
            str(ACCEPTANCE.relative_to(ROOT)),
        ],
        "packet_count": len(PACKETS),
        "contract": "Lane 4 packet inventory is an index-only clean-room gate; packet generators must be added one at a time from current source.",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "billing_call_performed": False,
            "cleanup_execution_performed": False,
            "live_execution_performed": False,
            "raw_logs_omitted": True,
            "raw_prompts_omitted": True,
            "raw_responses_omitted": True,
            "token_omitted": True,
            "db_omitted": True,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
