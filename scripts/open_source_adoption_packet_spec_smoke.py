#!/usr/bin/env python3
"""Validate the open-source adoption packet spec and release wiring."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "OPEN_SOURCE_ADOPTION_PACKET_SPEC.md"
BOUNDARY = ROOT / "docs" / "OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md"
GOVERNANCE = ROOT / "docs" / "OPEN_SOURCE_MAINLINE_GOVERNANCE_SPEC.md"
HARNESS = ROOT / "docs" / "HARNESS_STYLE_AGENTOPS_OPERATING_SPEC.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_SMOKE = ROOT / "scripts" / "release_evidence_packet_smoke.py"
RELEASE_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"

COMMAND = "python3 scripts/open_source_adoption_packet_spec_smoke.py"

REQUIRED_FIELDS = [
    "packet_id",
    "packet_version",
    "source_name",
    "source_url_or_branch",
    "source_kind",
    "license_summary",
    "owner_lane",
    "mis_authority_objects_touched",
    "intake_lane",
    "allowed_operations",
    "forbidden_operations",
    "raw_data_omissions",
    "runtime_requirements",
    "verification_commands",
    "product_claim_limit",
    "merge_decision",
    "rollback_plan",
    "evidence_refs",
]

REQUIRED_LANES = [
    "research_packet",
    "incubator",
    "adapter",
    "read_model",
    "first_party_migration",
    "reject",
]

REQUIRED_MARKERS = [
    "Harness-Informed Constraints",
    "Merge Gates",
    "Rejection Conditions",
    "Browser UI is for humans",
    "agents use CLI/API/MCP packets",
    "MIS ledger remains the source of truth",
    "raw external state is not canonical",
    "mock-only evidence",
]

OMISSION_MARKERS = [
    "raw prompts",
    "raw responses",
    "credentials",
    "private messages",
    "full transcripts",
    "local DBs",
    "generated exports",
    "customer raw documents",
    "tokens",
]

SECRET_PATTERNS = [
    re.compile(r"Authorization:\s*(Bearer|Basic|Token)\s+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9_]+"),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    spec = read(SPEC)
    ci = read(CI)
    release_smoke = read(RELEASE_SMOKE)
    release_doc = read(RELEASE_DOC)
    related = "\n".join([read(BOUNDARY), read(GOVERNANCE), read(HARNESS)])

    for path, label in [
        (SPEC, "open-source adoption packet spec"),
        (BOUNDARY, "open-source adoption boundary spec"),
        (GOVERNANCE, "open-source mainline governance spec"),
        (HARNESS, "Harness-style operating spec"),
    ]:
        require(path.exists(), f"missing {label}: {path.relative_to(ROOT)}", failures)

    for field in REQUIRED_FIELDS:
        require(f"`{field}`" in spec or f'"{field}"' in spec, f"packet field missing: {field}", failures)

    for lane in REQUIRED_LANES:
        require(f"`{lane}`" in spec or f'"{lane}"' in spec, f"intake lane missing: {lane}", failures)

    for marker in REQUIRED_MARKERS:
        require(marker in spec, f"required marker missing: {marker}", failures)

    spec_lower = spec.lower()
    for marker in OMISSION_MARKERS:
        require(marker.lower() in spec_lower, f"raw-data omission missing: {marker}", failures)

    require("adoption packet" in related.lower(), "related governance docs do not mention adoption packet", failures)
    require(COMMAND in ci, "CI workflow missing open-source adoption packet spec smoke", failures)
    require(COMMAND in release_smoke, "release evidence smoke missing open-source adoption packet spec smoke", failures)
    require(COMMAND in release_doc, "release evidence doc missing open-source adoption packet spec smoke", failures)

    joined = "\n".join([spec, ci, release_smoke, release_doc])
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in adoption packet surface: {len(secret_hits)}", failures)

    output = {
        "operation": "open_source_adoption_packet_spec_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "spec": str(SPEC.relative_to(ROOT)),
        "fields": REQUIRED_FIELDS,
        "intake_lanes": REQUIRED_LANES,
        "required_command": COMMAND,
        "safety": {
            "read_only": True,
            "db_read": False,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
