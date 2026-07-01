#!/usr/bin/env python3
"""Validate open-source mainline governance and Harness research docs."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "OPEN_SOURCE_MAINLINE_GOVERNANCE_SPEC.md"
HARNESS_BRIEF = ROOT / "docs" / "research" / "HARNESS_ENGINEERING_RESEARCH_BRIEF.md"

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


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    failures: list[str] = []
    spec = read(SPEC)
    brief = read(HARNESS_BRIEF)

    require(SPEC.exists(), "missing open-source mainline governance spec", failures)
    require(HARNESS_BRIEF.exists(), "missing Harness engineering research brief", failures)

    spec_markers = [
        "P0: Local Open-Source And Runtime Base",
        "P1: Product Hardening",
        "P2: Future Commercial / Hosted Stack",
        "Commercial Isolation Rule",
        "Prefer rebuild over direct merge for old experiment branches",
        "real Hermes/OpenClaw",
        "commercial_lane: future/reference",
        "hosted_ready: false",
        "billing_ready: false",
        "postgres_required_for_local_mvp: false",
        "Current Queue After This Spec",
        "codex/osbi-v1-1-mainline",
        "PR #11 UI v2",
        "PR #23 Spatial Research District art",
    ]
    for marker in spec_markers:
        require(marker in spec, f"governance spec missing marker: {marker}", failures)

    harness_markers = [
        "Harness Open Source",
        "Policy As Code",
        "Software Delivery Knowledge Graph",
        "Raw API Access Is Not Enough For Agents",
        "work packets",
        "Approval Wall",
        "Do not replace MIS",
        "https://github.com/harness/harness",
        "https://www.harness.io/open-source",
        "https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/",
    ]
    for marker in harness_markers:
        require(marker in brief, f"Harness research brief missing marker: {marker}", failures)

    forbidden_positive_claims = [
        "hosted_ready: true",
        "billing_ready: true",
        "postgres_required_for_local_mvp: true",
        "commercial_lane: current_local_mvp",
        "Replace MIS with Harness",
        "Harness replaces MIS",
    ]
    joined = f"{spec}\n{brief}"
    for marker in forbidden_positive_claims:
        require(marker not in joined, f"unsafe local-MVP/commercial claim found: {marker}", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in governance docs: {len(secret_hits)}", failures)

    output = {
        "operation": "open_source_mainline_governance_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "docs": [
            str(SPEC.relative_to(ROOT)),
            str(HARNESS_BRIEF.relative_to(ROOT)),
        ],
        "mainline_priority": [
            "P0 local open-source/runtime base",
            "P1 product hardening",
            "P2 future commercial/hosted stack only when explicitly authorized",
        ],
        "harness_implications": [
            "typed work-delivery graph over MIS ledgers",
            "agents consume work packets, not raw UI/API guesses",
            "policy gates before side effects",
            "MIS authority remains first-party",
        ],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "db_read": False,
            "live_execution_performed": False,
            "commercial_runtime_enabled": False,
            "token_omitted": True,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
