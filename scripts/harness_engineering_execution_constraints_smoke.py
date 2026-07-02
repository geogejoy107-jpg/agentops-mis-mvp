#!/usr/bin/env python3
"""Validate Harness engineering execution constraints and release wiring."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md"
CONTROL_SPEC = ROOT / "docs" / "HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md"
RESEARCH = ROOT / "docs" / "research" / "HARNESS_ENGINEERING_RESEARCH_BRIEF.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_SMOKE = ROOT / "scripts" / "release_evidence_packet_smoke.py"
RELEASE_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"

COMMAND = "python3 scripts/harness_engineering_execution_constraints_smoke.py"

REQUIRED_MARKERS = [
    "Work Packet Contract",
    "Required Gate Chain",
    "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD",
    "Policy Decision Shape",
    "Approval Wall Constraint",
    "Real-Runtime Proof Standard",
    "Async Lane Constraint",
    "UI And CLI Constraint",
    "Product Claims Constraint",
    "summary_only_until_runtime_events_available",
    "local-first harness slice verified",
    "real-runtime dogfood verified for this adapter/run id",
    "Do not claim",
]

PACKET_FIELDS = [
    "packet_id",
    "packet_kind",
    "packet_version",
    "workspace_id",
    "task_id",
    "agent_id",
    "runtime_connector_id",
    "objective_summary",
    "authority_refs",
    "allowed_commands",
    "forbidden_actions",
    "required_gates",
    "evidence_targets",
    "verification_commands",
    "redaction_rules",
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
    "delivery report",
    "audit log",
]

SOURCES = [
    "https://github.com/harness/harness",
    "https://www.harness.io/open-source",
    "https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/",
    "https://openai.com/index/harness-engineering/",
    "https://openai.com/index/unlocking-the-codex-harness/",
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
    re.compile(r"Harness\s+(replaces|owns|becomes)\s+MIS", re.IGNORECASE),
    re.compile(r"universal per-action governance\s+(is\s+)?(done|complete|ready)", re.IGNORECASE),
    re.compile(r"mock adapter-only evidence\s+is\s+product-grade", re.IGNORECASE),
    re.compile(r"raw prompts?.*canonical evidence", re.IGNORECASE),
    re.compile(r"raw responses?.*canonical evidence", re.IGNORECASE),
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
    research = read(RESEARCH)
    ci = read(CI)
    release_smoke = read(RELEASE_SMOKE)
    release_doc = read(RELEASE_DOC)
    joined = "\n".join([spec, control_spec, research, ci, release_smoke, release_doc])

    for path, label in [
        (SPEC, "execution constraints spec"),
        (CONTROL_SPEC, "control-plane spec"),
        (RESEARCH, "Harness research brief"),
    ]:
        require(path.exists(), f"missing {label}: {path.relative_to(ROOT)}", failures)

    for marker in REQUIRED_MARKERS:
        require(marker in spec, f"execution constraints spec missing marker: {marker}", failures)

    for field in PACKET_FIELDS:
        require(f"`{field}`" in spec, f"work packet contract missing field: {field}", failures)

    spec_lower = spec.lower()
    for authority_object in AUTHORITY_OBJECTS:
        require(
            authority_object.lower() in spec_lower,
            f"execution constraints spec missing authority object: {authority_object}",
            failures,
        )

    for source in SOURCES:
        require(source in spec, f"execution constraints spec missing source: {source}", failures)

    require(COMMAND in ci, "CI workflow missing execution constraints smoke", failures)
    require(COMMAND in release_smoke, "release evidence packet missing execution constraints smoke", failures)
    require(COMMAND in release_doc, "release evidence doc missing execution constraints smoke", failures)

    for pattern in FORBIDDEN:
        match = pattern.search(joined)
        require(not match, f"forbidden harness claim found: {match.group(0) if match else pattern.pattern}", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in Harness execution surface: {len(secret_hits)}", failures)

    output = {
        "operation": "harness_engineering_execution_constraints_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "spec": str(SPEC.relative_to(ROOT)),
        "work_packet_fields": PACKET_FIELDS,
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
