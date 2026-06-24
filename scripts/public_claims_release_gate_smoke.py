#!/usr/bin/env python3
"""Verify public release claims match tested local-MVP behavior."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAIMS_DOC = ROOT / "docs" / "PUBLIC_CLAIMS_AND_LIMITATIONS.md"
FILES = {
    "claims": CLAIMS_DOC,
    "checklist": ROOT / "docs" / "V1_5_MERGE_READINESS_CHECKLIST.md",
    "project_spec": ROOT / "PROJECT_SPEC.md",
    "readme": ROOT / "README.md",
    "demo_script": ROOT / "docs" / "DEMO_VIDEO_SCRIPT.md",
    "presentation": ROOT / "docs" / "PRESENTATION_BRIEF.md",
    "release_provenance": ROOT / "docs" / "RELEASE_PROVENANCE.md",
    "third_party_notices": ROOT / "docs" / "THIRD_PARTY_NOTICES.md",
    "project_memory_state": ROOT / "docs" / "PROJECT_MEMORY_CURRENT_STATE.md",
}
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]
DISALLOWED_UNQUALIFIED_CLAIMS = [
    "hosted SaaS is ready",
    "production-ready multi-tenant",
    "commercially ready",
    "commercial ready",
    "billing is live",
    "Dify live sync is available",
    "Notion bidirectional sync is available",
    "generic approval resumes tool actions",
    "Star-Office art is commercial-ready",
    "stores raw prompts",
    "stores raw model responses",
    "stores credentials",
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def contains_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def has_phrase(text: str, phrase: str) -> bool:
    return " ".join(phrase.lower().split()) in " ".join(text.lower().split())


def main() -> int:
    failures: list[str] = []
    docs: dict[str, str] = {}
    for label, path in FILES.items():
        require(path.exists(), f"missing public-claims evidence file: {path.relative_to(ROOT)}", failures)
        docs[label] = read(path) if path.exists() else ""

    claims = docs.get("claims", "")
    required_claim_doc_phrases = [
        "local-first AI workforce/MIS control plane",
        "local MVP / NOT_READY",
        "Hosted SaaS, billing, production multi-tenant fleet management, marketplace",
        "Hermes/OpenClaw live execution is protected/manual",
        "Dify, Notion and other external connectors are adapter or prepared-action paths",
        "Star-Office-UI and other pixel-office references are reference-only",
        "does not store raw credentials, private prompts, raw model responses",
        "Do not claim",
    ]
    for phrase in required_claim_doc_phrases:
        require(has_phrase(claims, phrase), f"public claims doc missing phrase: {phrase}", failures)

    checklist = docs.get("checklist", "")
    require(
        "- [x] Known limitations and public-claims checklist." in checklist
        and "scripts/public_claims_release_gate_smoke.py" in checklist,
        "merge readiness checklist does not close public-claims gate with this smoke",
        failures,
    )
    require(
        "Current status: `NOT_READY`" in checklist or "Current status: `READY_TO_MERGE`" in checklist,
        "checklist must stay NOT_READY until exact RC evidence advances it, then may state READY_TO_MERGE",
        failures,
    )

    project_spec = docs.get("project_spec", "")
    require("MIS must not store raw secrets" in project_spec, "PROJECT_SPEC missing no-raw-storage boundary", failures)
    require("exact tool-action resume" in project_spec and "prepared-action context" in project_spec, "PROJECT_SPEC missing approval semantics qualifier", failures)

    readme = docs.get("readme", "")
    require("默认不调用外部 API" in readme, "README missing default no-external-API qualifier", failures)
    require("不提交 `agentops_mis.db`、credentials、真实 prompts、私聊正文或完整 transcripts" in readme, "README missing repo hygiene claim boundary", failures)

    demo_script = docs.get("demo_script", "")
    require("Do not claim Dify live sync or Notion bidirectional sync" in demo_script, "demo script missing connector claim limit", failures)
    require("Do not claim hosted SaaS, billing or production multi-tenant fleet management" in demo_script, "demo script missing hosted/billing/fleet claim limit", failures)
    require("local MVP for classroom demonstration" in demo_script, "demo script missing local MVP qualifier", failures)

    presentation = docs.get("presentation", "")
    require("Commercial direction:" in presentation and "Future marketplace" in presentation, "presentation must frame commercial material as future direction", failures)

    release_provenance = docs.get("release_provenance", "")
    third_party = docs.get("third_party_notices", "")
    require("commercial-build exclusions" in release_provenance, "release provenance missing commercial exclusion framing", failures)
    require("commercial/public distribution is blocked" in release_provenance.lower(), "release provenance missing commercial/public block", failures)
    require("legal advice" in third_party and "final legal review" in third_party, "third-party notices missing legal-review qualifier", failures)

    project_memory = docs.get("project_memory_state", "")
    require("Still do not claim hosted/commercial readiness" in project_memory, "project memory state missing hosted/commercial readiness limit", failures)

    public_bundle = "\n".join(docs.values())
    for phrase in DISALLOWED_UNQUALIFIED_CLAIMS:
        require(phrase.lower() not in public_bundle.lower(), f"found disallowed unqualified claim: {phrase}", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(public_bundle)]
    require(not secret_hits, f"public-claims evidence leaked token-like material: {secret_hits}", failures)

    output = {
        "ok": not failures,
        "operation": "public_claims_release_gate",
        "documents": [str(path.relative_to(ROOT)) for path in FILES.values()],
        "allowed_claims": [
            "local-first AI workforce/MIS control plane",
            "local MVP / NOT_READY until exact RC evidence advances it, then READY_TO_MERGE as a release-candidate state",
            "protected/manual live Hermes/OpenClaw evidence only",
        ],
        "disallowed_unqualified_claims_checked": len(DISALLOWED_UNQUALIFIED_CLAIMS),
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
