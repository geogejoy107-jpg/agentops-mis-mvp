#!/usr/bin/env python3
"""Validate the Harness engineering product constraints spec."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "HARNESS_ENGINEERING_PRODUCT_CONSTRAINTS_SPEC.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_SMOKE = ROOT / "scripts" / "release_evidence_packet_smoke.py"
RELEASE_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"

COMMAND = "python3 scripts/harness_engineering_product_constraints_smoke.py"

REQUIRED_MARKERS = [
    "Harness Worker Agents",
    "Harness Policy As Code overview",
    "Harness Open Source repository",
    "Adaptive Auto-Harness paper",
    "AgentOps MIS is a local-first human-AI work harness and authority ledger",
    "Agent Interface Constraint",
    "Work Packet Constraint",
    "Policy Decision Constraint",
    "Approval Wall Constraint",
    "Real Runtime Constraint",
    "Open-Source Base Constraint",
    "Async Commander Constraint",
    "Product Slice Acceptance",
    "Immediate Implementation Queue",
    "source of truth remains",
    "Mock and fixture evidence is CI/offline fallback only",
    "Agents must not scrape Pixel Office",
    "A generic approval row is not enough",
]

AUTHORITY_OBJECTS = [
    "workspace",
    "agent",
    "task",
    "Agent Plan",
    "run",
    "tool call",
    "runtime event",
    "prepared action",
    "approval",
    "evaluation",
    "artifact",
    "memory candidate",
    "report",
    "audit log",
]

SOURCE_URLS = [
    "https://developer.harness.io/docs/platform/harness-ai/harness-agents/",
    "https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/",
    "https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-quickstart/",
    "https://github.com/harness/harness",
    "https://arxiv.org/abs/2606.01770",
]

FORBIDDEN_PATTERNS = [
    re.compile(r"Harness\s+(replaces|owns|becomes)\s+AgentOps MIS", re.IGNORECASE),
    re.compile(r"browser UI is for agents", re.IGNORECASE),
    re.compile(r"raw prompt.*stored", re.IGNORECASE),
    re.compile(r"raw response.*stored", re.IGNORECASE),
    re.compile(r"mock.*product-readiness", re.IGNORECASE),
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
    joined = "\n".join([spec, ci, release_smoke, release_doc])

    require(SPEC.exists(), f"missing spec: {SPEC.relative_to(ROOT)}", failures)

    for marker in REQUIRED_MARKERS:
        require(marker in spec, f"spec missing marker: {marker}", failures)

    for authority_object in AUTHORITY_OBJECTS:
        require(authority_object in spec, f"spec missing authority object: {authority_object}", failures)

    for url in SOURCE_URLS:
        require(url in spec, f"spec missing source URL: {url}", failures)

    require(COMMAND in ci, "CI workflow missing product constraints smoke", failures)
    require(COMMAND in release_smoke, "release evidence packet missing product constraints smoke", failures)
    require(COMMAND in release_doc, "release evidence doc missing product constraints smoke", failures)

    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(joined)
        require(not match, f"forbidden product claim found: {match.group(0) if match else pattern.pattern}", failures)

    output = {
        "ok": not failures,
        "operation": "harness_engineering_product_constraints_smoke",
        "spec": str(SPEC.relative_to(ROOT)),
        "sources_checked": len(SOURCE_URLS),
        "authority_objects_checked": len(AUTHORITY_OBJECTS),
        "failures": failures,
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "token_omitted": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
