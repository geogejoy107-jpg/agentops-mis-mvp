#!/usr/bin/env python3
"""Validate the Harness-style AgentOps operating spec and release wiring."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "HARNESS_STYLE_AGENTOPS_OPERATING_SPEC.md"
CONTROL_SPEC = ROOT / "docs" / "HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md"
EXECUTION_SPEC = ROOT / "docs" / "HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_SMOKE = ROOT / "scripts" / "release_evidence_packet_smoke.py"
RELEASE_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"

COMMAND = "python3 scripts/harness_style_agentops_operating_spec_smoke.py"

REQUIRED_MARKERS = [
    "Harness-Style AgentOps Operating Spec",
    "Fresh Harness Research Notes",
    "AgentOps MIS Interpretation",
    "Solo Local Company Mode",
    "Dogfood Engineering Mode",
    "Remote Worker Mode",
    "Async Commander Constraints",
    "Work Packet Constraints",
    "Real Runtime Constraints",
    "UI Constraints",
    "Scorecard For Product Slices",
    "Open-Source And Harness Boundary",
    "Next Implementation Slices",
    "mock_or_ci_fallback_only",
    "Pixel Office can be a useful operating map, but it remains a visual read model",
]

SOURCE_MARKERS = [
    "https://developer.harness.io/docs/platform/harness-ai/harness-agents/",
    "https://developer.harness.io/docs/platform/harness-ai/harness-mcp-server/",
    "https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/",
    "https://developer.harness.io/docs/internal-developer-portal/overview",
    "https://developer.harness.io/docs/internal-developer-portal/scorecards/scorecard/",
    "https://www.harness.io/blog/introducing-autonomous-worker-agents",
]

LANE_FIELDS = [
    "lane_id",
    "objective",
    "owner",
    "runtime",
    "phase",
    "task_id",
    "run_id",
    "packet_hash",
    "blocked_reason",
    "next_command",
    "verification_command",
    "evidence_refs",
    "claim_limit",
]

AUTHORITY_OBJECTS = [
    "workspace",
    "agent",
    "task",
    "Agent Plan",
    "run",
    "tool call",
    "prepared action",
    "approval",
    "runtime event",
    "evaluation",
    "memory candidate",
    "artifact",
    "report",
    "audit",
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

FORBIDDEN = [
    re.compile(r"Harness\s+(replaces|owns|becomes)\s+the\s+MIS", re.IGNORECASE),
    re.compile(r"Pixel Office\s+.*second\s+task\s+ledger", re.IGNORECASE),
    re.compile(r"raw prompts?\s+(may|can|should|must)\s+.*committed", re.IGNORECASE),
    re.compile(r"raw responses?\s+(may|can|should|must)\s+.*committed", re.IGNORECASE),
    re.compile(r"mock evidence\s+is\s+real AI work", re.IGNORECASE),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    spec = read(SPEC)
    control_spec = read(CONTROL_SPEC)
    execution_spec = read(EXECUTION_SPEC)
    ci = read(CI)
    release_smoke = read(RELEASE_SMOKE)
    release_doc = read(RELEASE_DOC)
    joined = "\n".join([spec, control_spec, execution_spec, ci, release_smoke, release_doc])

    for path, label in [
        (SPEC, "Harness-style operating spec"),
        (CONTROL_SPEC, "Harness control-plane spec"),
        (EXECUTION_SPEC, "Harness execution constraints spec"),
    ]:
        require(path.exists(), f"missing {label}: {path.relative_to(ROOT)}", failures)

    for marker in REQUIRED_MARKERS:
        require(marker in spec, f"operating spec missing marker: {marker}", failures)

    for marker in SOURCE_MARKERS:
        require(marker in spec, f"operating spec missing source marker: {marker}", failures)

    for field in LANE_FIELDS:
        require(f"`{field}`" in spec, f"async lane field missing: {field}", failures)

    spec_lower = spec.lower()
    for authority_object in AUTHORITY_OBJECTS:
        require(
            authority_object.lower() in spec_lower,
            f"operating spec missing authority object: {authority_object}",
            failures,
        )

    require(COMMAND in ci, "CI workflow missing Harness-style operating spec smoke", failures)
    require(COMMAND in release_smoke, "release evidence smoke missing Harness-style operating spec smoke", failures)
    require(COMMAND in release_doc, "release evidence doc missing Harness-style operating spec smoke", failures)

    for pattern in FORBIDDEN:
        match = pattern.search(joined)
        require(not match, f"forbidden operating-spec claim found: {match.group(0) if match else pattern.pattern}", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in operating spec surface: {len(secret_hits)}", failures)

    output = {
        "operation": "harness_style_agentops_operating_spec_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "spec": str(SPEC.relative_to(ROOT)),
        "lane_fields": LANE_FIELDS,
        "authority_objects": AUTHORITY_OBJECTS,
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
