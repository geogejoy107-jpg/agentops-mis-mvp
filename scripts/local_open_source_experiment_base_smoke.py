#!/usr/bin/env python3
"""Verify the local open-source experiment base remains wired together.

This is a static/read-only smoke. It does not call live runtimes, does not
refresh the SQLite knowledge index, and does not write ledger rows.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_FILES = [
    "docs/LOCAL_OPEN_SOURCE_EXPERIMENT_BASE_SPEC.md",
    "docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md",
    "docs/OPEN_SOURCE_UI_REFERENCE_ATLAS.md",
    "docs/RESEARCH_REFERENCES.md",
    "docs/RESEARCH_TO_PRODUCT_TRACEABILITY.md",
    "docs/THIRD_PARTY_NOTICES.md",
    "docs/RELEASE_PROVENANCE.md",
    "docs/AGENT_WORK_METHOD_BLOCK.md",
    "knowledge/shared/architecture_rules.md",
    "knowledge/shared/security_rules.md",
    "knowledge/shared/common_failures.md",
    "knowledge/bases/openclaw/BASE_SPEC.md",
    "knowledge/bases/hermes/BASE_SPEC.md",
    "knowledge/bases/star-office-ui/BASE_SPEC.md",
    "knowledge/runbooks/agent_work_method_runbook.md",
    "scripts/openclaw_v1_experiment.py",
    "scripts/hermes_openclaw_loop.py",
    "scripts/open_source_adoption_boundary_smoke.py",
    "scripts/knowledge_retrieval_quality_smoke.py",
    "scripts/evaluation_case_candidate_smoke.py",
]


SOURCE_FRAGMENTS = {
    "server.py": [
        "CREATE TABLE IF NOT EXISTS evaluation_case_candidates",
        "CREATE TABLE IF NOT EXISTS evaluation_case_runs",
        "def propose_evaluation_case_candidate",
        "def run_evaluation_cases",
        "def list_evaluation_case_candidates",
        "def list_evaluation_case_runs",
        "/api/knowledge/search",
        "/api/agent-gateway/knowledge/evidence-packet",
    ],
    "agentops_mis_cli/agentops.py": [
        "def cmd_knowledge_search",
        "def cmd_knowledge_evidence_packet",
        "def cmd_eval_propose_case",
        "def cmd_eval_run_cases",
        "def cmd_eval_case_runs",
        "def cmd_eval_remediate_case_run",
        "agentops local readiness --require-current-code",
    ],
    "docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md": [
        "Tooling, protocols, retrieval, CI, and security scanning can borrow heavily",
        "MIS authority ledger",
        "Reference-Only Methods",
        "First-Party MIS Modules",
    ],
    "docs/LOCAL_OPEN_SOURCE_EXPERIMENT_BASE_SPEC.md": [
        "Reference Atlas",
        "Evaluation Case Loop",
        "Runtime Experiment Lane",
        "No hosted SaaS claims",
        "No Dify/Notion live sync",
    ],
    ".github/workflows/ci.yml": [
        "python3 scripts/local_open_source_experiment_base_smoke.py",
        "python3 scripts/open_source_adoption_boundary_smoke.py",
    ],
    "README.md": [
        "Local Open Source Experiment Base",
        "scripts/local_open_source_experiment_base_smoke.py",
    ],
}


FORBIDDEN_TRACKED_HINTS = [
    "node_modules/",
    "dist/",
    ".env",
    "agentops_mis.db",
    ".agentops_runtime/",
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []
    evidence: dict[str, object] = {}

    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        failures.append(f"missing required local base files: {missing}")
    evidence["required_files_checked"] = len(REQUIRED_FILES)
    evidence["missing_required_files"] = missing

    fragment_results: dict[str, dict[str, object]] = {}
    for path, fragments in SOURCE_FRAGMENTS.items():
        target = ROOT / path
        if not target.exists():
            fragment_results[path] = {"ok": False, "missing_file": True, "missing_fragments": fragments}
            failures.append(f"missing source file for fragment check: {path}")
            continue
        text = read(path)
        missing_fragments = [fragment for fragment in fragments if fragment not in text]
        fragment_results[path] = {
            "ok": not missing_fragments,
            "missing_file": False,
            "missing_fragments": missing_fragments,
        }
        if missing_fragments:
            failures.append(f"{path} missing fragments: {missing_fragments}")
    evidence["fragment_results"] = fragment_results

    knowledge_files = sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "knowledge").rglob("*.md")
        if path.is_file()
    )
    if len(knowledge_files) < 10:
        failures.append(f"expected at least 10 Markdown knowledge files, found {len(knowledge_files)}")
    evidence["knowledge_markdown_files"] = len(knowledge_files)
    evidence["knowledge_base_examples"] = knowledge_files[:12]

    tracked_text = "\n".join(path for path in REQUIRED_FILES)
    forbidden_hits = [hint for hint in FORBIDDEN_TRACKED_HINTS if hint in tracked_text]
    if forbidden_hits:
        failures.append(f"local experiment base points at forbidden runtime/generated paths: {forbidden_hits}")
    evidence["forbidden_runtime_path_hits"] = forbidden_hits

    payload = {
        "ok": not failures,
        "operation": "local_open_source_experiment_base_smoke",
        "contract": "Open-source references and experiments stay local, evidence-backed, and subordinate to first-party MIS authority objects.",
        "evidence": evidence,
        "recommended_next": [
            "Use agentops knowledge evidence-packet before experiment implementation.",
            "Use agentops eval propose-case for reusable experiment learnings.",
            "Use Agent Plan and plan-evidence manifests before product-affecting changes.",
        ],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
