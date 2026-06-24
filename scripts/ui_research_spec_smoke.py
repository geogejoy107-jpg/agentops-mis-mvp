#!/usr/bin/env python3
"""Validate the UI v2 research and Gemini handoff docs."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = {
    "spec": ROOT / "docs" / "design" / "AGENTOPS_MIS_UI_UX_SPEC_V2.md",
    "handoff": ROOT / "docs" / "design" / "GEMINI_UI_IMPLEMENTATION_HANDOFF.md",
    "benchmark": ROOT / "docs" / "design" / "UI_BENCHMARK_RESEARCH_2026.md",
}

REQUIRED_TERMS = {
    "spec": [
        "local-first control plane",
        "Pixel Office remains",
        "New canonical routes",
        "Legacy routes remain",
        "Use live audit API",
        "Implementation sequence",
        "Operator can reach pending approvals",
        "Demo tells a coherent story",
    ],
    "handoff": [
        "Do not rewrite the backend",
        "Do not weaken security",
        "Pixel Office is not the authority system",
        "Test and validation commands",
        "First execution prompt for Gemini",
        "Do not implement against main",
        "Preserve all existing routes and behavior",
        "Stop conditions",
    ],
    "benchmark": [
        "Linear",
        "Vercel",
        "LangSmith",
        "Langfuse",
        "Arize Phoenix",
        "Braintrust",
        "GitHub pull request review",
        "Cloudflare Access policies",
        "Notion database views",
        "Dify Knowledge",
        "GitHub Primer",
        "No silent automation",
    ],
}

FORBIDDEN_PATTERNS = [
    ("live_run_default_enabled", re.compile(r"HERMES_ALLOW_REAL_RUN\s*=\s*true")),
    ("notion_token_literal", re.compile(r"\bntn_[A-Za-z0-9._~+/=-]{8,}\b")),
    ("openai_key_literal", re.compile(r"\bsk-[A-Za-z0-9._~+/=-]{20,}\b")),
    ("generated_node_modules", re.compile(r"\bnode_modules/")),
    ("generated_dist", re.compile(r"\bdist/")),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    evidence: dict[str, object] = {"docs": {}, "required_terms": {}, "forbidden_terms": []}

    for key, path in DOCS.items():
        require(path.exists(), f"missing {path.relative_to(ROOT)}", failures)
        if not path.exists():
            continue

        text = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(ROOT))
        evidence["docs"][key] = {
            "path": relative,
            "line_count": len(text.splitlines()),
            "bytes": len(text.encode("utf-8")),
        }

        matched_terms = [term for term in REQUIRED_TERMS[key] if term in text]
        missing_terms = [term for term in REQUIRED_TERMS[key] if term not in text]
        evidence["required_terms"][key] = matched_terms
        for term in missing_terms:
            failures.append(f"{relative} missing required term: {term}")

        lowered = text.lower()
        require("governance" in lowered or "approval" in lowered, f"{relative} missing governance language", failures)
        require("audit" in lowered, f"{relative} missing audit language", failures)
        require("raw prompts" in lowered or "raw secrets" in lowered or "secrets" in lowered, f"{relative} missing raw secret/prompt boundary", failures)

        for name, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                evidence["forbidden_terms"].append({"path": relative, "pattern": name})
                failures.append(f"{relative} contains forbidden pattern: {name}")

    spec = DOCS["spec"].read_text(encoding="utf-8") if DOCS["spec"].exists() else ""
    handoff = DOCS["handoff"].read_text(encoding="utf-8") if DOCS["handoff"].exists() else ""
    benchmark = DOCS["benchmark"].read_text(encoding="utf-8") if DOCS["benchmark"].exists() else ""

    require("/pixel-office" in spec, "spec must preserve Pixel Office route", failures)
    require("/govern/audit" in spec, "spec must include Audit Explorer route", failures)
    require("Do not modify backend execution, auth, approval or worker semantics" in handoff, "handoff must protect backend execution/auth/approval semantics", failures)
    require("Stop conditions" in handoff, "handoff must include stop conditions", failures)
    require("What not to copy" in benchmark, "benchmark must include adaptation boundaries", failures)

    result = {
        "ok": not failures,
        "operation": "ui_research_spec_smoke",
        "failures": failures,
        "evidence": evidence,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
