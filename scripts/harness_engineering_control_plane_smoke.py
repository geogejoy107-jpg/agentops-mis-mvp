#!/usr/bin/env python3
"""Validate the Harness engineering control-plane spec and release wiring."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md"
EXECUTION_SPEC = ROOT / "docs" / "HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md"
RESEARCH = ROOT / "docs" / "research" / "HARNESS_ENGINEERING_RESEARCH_BRIEF.md"
BOUNDARY = ROOT / "docs" / "OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_SMOKE = ROOT / "scripts" / "release_evidence_packet_smoke.py"
RELEASE_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"

COMMAND = "python3 scripts/harness_engineering_control_plane_smoke.py"
EXECUTION_COMMAND = "python3 scripts/harness_engineering_execution_constraints_smoke.py"

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

REQUIRED_MARKERS = [
    "AgentOps MIS is a human-AI work delivery control plane",
    "First-party AgentOps MIS authority remains",
    "Agents Need A Harness, Not Raw Access",
    "Repository Knowledge Is Product Infrastructure",
    "Policy Decisions Must Be First-Class",
    "Work Delivery Graph Is A Read Model",
    "Async Commander Mode Is Product Behavior",
    "READ",
    "PLAN",
    "RETRIEVE",
    "COMPARE",
    "EXECUTE",
    "VERIFY",
    "RECORD",
    "Approval Wall Requirements",
    "Runtime Adapter Requirements",
    "Execution Constraints Layer",
    "docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md",
    "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD",
    "Bind `agent_work_packet_decision_v1` into `runs/start`",
    "Do not vendor Harness Open Source into AgentOps MIS",
    "Do not claim universal per-action governance",
]

AUTHORITY_OBJECTS = [
    "workspace",
    "agent",
    "task",
    "agent plan",
    "run",
    "tool call",
    "prepared action",
    "approval",
    "runtime event",
    "evaluation",
    "memory candidate",
    "artifact",
    "delivery report",
    "audit log",
]

SOURCE_MARKERS = [
    "https://github.com/harness/harness",
    "https://www.harness.io/open-source",
    "https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/",
    "https://openai.com/index/harness-engineering/",
]

FORBIDDEN_CLAIMS = [
    re.compile(r"Harness\s+(replaces|owns|becomes)\s+MIS", re.IGNORECASE),
    re.compile(r"OPA\s+(replaces|owns|becomes)\s+.*Approval", re.IGNORECASE),
    re.compile(r"raw prompts?.*committed", re.IGNORECASE),
    re.compile(r"raw responses?.*committed", re.IGNORECASE),
    re.compile(r"universal per-action governance.*complete", re.IGNORECASE),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    spec = read(SPEC)
    execution_spec = read(EXECUTION_SPEC)
    research = read(RESEARCH)
    boundary = read(BOUNDARY)
    ci = read(CI)
    release_smoke = read(RELEASE_SMOKE)
    release_doc = read(RELEASE_DOC)
    joined = "\n".join([spec, execution_spec, research, boundary, ci, release_doc])

    for path, label in [
        (SPEC, "control-plane spec"),
        (EXECUTION_SPEC, "execution constraints spec"),
        (RESEARCH, "Harness research brief"),
        (BOUNDARY, "open-source boundary spec"),
    ]:
        require(path.exists(), f"missing {label}: {path.relative_to(ROOT)}", failures)

    for marker in REQUIRED_MARKERS:
        require(marker in spec, f"control-plane spec missing marker: {marker}", failures)

    spec_lower = spec.lower()
    for authority_object in AUTHORITY_OBJECTS:
        require(
            authority_object in spec_lower,
            f"control-plane spec missing authority object: {authority_object}",
            failures,
        )

    for marker in SOURCE_MARKERS:
        require(marker in spec, f"control-plane spec missing source: {marker}", failures)
        require(marker in research, f"research brief missing source: {marker}", failures)

    require(COMMAND in ci, "CI workflow missing Harness control-plane smoke", failures)
    require(COMMAND in release_smoke, "release evidence packet missing Harness control-plane smoke", failures)
    require(COMMAND in release_doc, "release evidence doc missing Harness control-plane smoke", failures)
    require(EXECUTION_COMMAND in ci, "CI workflow missing Harness execution constraints smoke", failures)
    require(EXECUTION_COMMAND in release_smoke, "release evidence packet missing Harness execution constraints smoke", failures)
    require(EXECUTION_COMMAND in release_doc, "release evidence doc missing Harness execution constraints smoke", failures)

    for pattern in FORBIDDEN_CLAIMS:
        match = pattern.search(joined)
        require(not match, f"forbidden Harness/MIS authority claim found: {match.group(0) if match else pattern.pattern}", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in harness spec surface: {len(secret_hits)}", failures)

    output = {
        "operation": "harness_engineering_control_plane_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "docs": [
            str(SPEC.relative_to(ROOT)),
            str(EXECUTION_SPEC.relative_to(ROOT)),
            str(RESEARCH.relative_to(ROOT)),
            str(BOUNDARY.relative_to(ROOT)),
        ],
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
