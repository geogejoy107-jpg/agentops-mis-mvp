#!/usr/bin/env python3
"""Verify open-source references cannot drift into MIS authority ownership.

This is a static release gate. It does not ban open-source tools; it keeps the
documented boundary explicit: external projects may accelerate tooling and
runtime adapters, while AgentOps MIS remains authoritative for plans, ledger
objects, approvals, memory governance, delivery and audit.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_DOC = ROOT / "docs" / "OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_EVIDENCE = ROOT / "scripts" / "release_evidence_packet_smoke.py"

SECRET_PATTERNS = [
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
]

AUTHORITY_OBJECTS = [
    "workspaces",
    "agents",
    "tasks",
    "runs",
    "tool calls",
    "approvals",
    "prepared actions",
    "artifacts",
    "evaluations",
    "memories",
    "audit logs",
    "delivery reports",
]

REFERENCE_BOUNDARIES = [
    ("GitHub Spec Kit", "The canonical Agent Plan engine"),
    ("LangGraph interrupt/checkpoint", "The approval ledger or delivery gate"),
    ("CrewAI / LangGraph / JiuwenSwarm", "Workspace, run, approval or audit authority"),
    ("Aider Repo Map", "Workspace/agent memory authority"),
    ("Mem0 / Zep / Letta", "Automatic memory authority"),
]

BANNED_AUTHORITY_CLAIMS = [
    re.compile(r"Spec Kit\s+(owns|is|becomes)\s+.*Agent Plan", re.IGNORECASE),
    re.compile(r"LangGraph\s+(owns|is|becomes)\s+.*approval", re.IGNORECASE),
    re.compile(r"CrewAI\s+(owns|is|becomes)\s+.*audit", re.IGNORECASE),
    re.compile(r"external framework\s+(owns|is|becomes)\s+.*source of truth", re.IGNORECASE),
]

SCAN_FILES = [
    "README.md",
    "PROJECT_SPEC.md",
    "AGENT_WORKFLOW.md",
    "docs/project/PROJECT_STATE.md",
    "docs/project/BACKLOG.md",
    "docs/V1_5_AGENT_GATEWAY_HARDENING_OBJECTIVE.md",
    "docs/V1_5_EIGHT_PRODUCT_CLOSURE_SPEC.md",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    doc = read(BOUNDARY_DOC)
    doc_lower = doc.lower()
    doc_compact = re.sub(r"\s+", " ", doc.replace(">", ""))
    ci = read(CI_WORKFLOW)
    release = read(RELEASE_EVIDENCE)

    for authority_object in AUTHORITY_OBJECTS:
        require(
            authority_object in doc_lower,
            f"authority object missing from open-source boundary doc: {authority_object}",
            failures,
        )

    for reference, banned_role in REFERENCE_BOUNDARIES:
        require(reference in doc, f"reference missing from boundary table: {reference}", failures)
        require(banned_role in doc, f"forbidden authority role missing for {reference}: {banned_role}", failures)

    required_phrases = [
        "business objects must remain first-party AgentOps MIS code",
        "must not delegate the MIS authority model",
        "External runtimes and frameworks can execute or observe work",
        "raw external state does not become canonical",
    ]
    for phrase in required_phrases:
        require(phrase in doc_compact, f"boundary doctrine missing phrase: {phrase}", failures)

    command = "python3 scripts/open_source_adoption_boundary_smoke.py"
    require(command in ci, "CI workflow missing open-source adoption boundary smoke", failures)
    require(command in release, "release evidence packet missing open-source adoption boundary smoke", failures)

    scanned: list[str] = []
    banned_hits: list[dict[str, str]] = []
    for rel_path in SCAN_FILES:
        path = ROOT / rel_path
        require(path.exists(), f"authority-claim scan target missing: {rel_path}", failures)
        if not path.exists():
            continue
        text = read(path)
        scanned.append(rel_path)
        for pattern in BANNED_AUTHORITY_CLAIMS:
            match = pattern.search(text)
            if match:
                banned_hits.append({"file": rel_path, "claim": match.group(0)})
    require(not banned_hits, f"banned external-authority claims found: {banned_hits}", failures)

    output = {
        "operation": "open_source_adoption_boundary_smoke",
        "ok": not failures,
        "authority_objects": AUTHORITY_OBJECTS,
        "reference_boundaries": [
            {"reference": reference, "forbidden_role": forbidden_role}
            for reference, forbidden_role in REFERENCE_BOUNDARIES
        ],
        "scanned_files": scanned,
        "failures": failures,
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    require(not any(pattern.search(rendered) for pattern in SECRET_PATTERNS), "output leaked token-like material", failures)
    if failures:
        output["ok"] = False
        output["failures"] = failures
        rendered = json.dumps(output, ensure_ascii=False, indent=2)
    print(rendered)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
