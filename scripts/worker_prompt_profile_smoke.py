#!/usr/bin/env python3
"""Verify worker prompt profiles are classified and ledger-visible without raw prompt storage."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_cli.worker import build_task_prompt_bundle  # noqa: E402

WORKER = ROOT / "agentops_mis_cli" / "worker.py"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{12,}"),
    re.compile(r"ntn_[A-Za-z0-9]{12,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    cases = [
        (
            "coding",
            {
                "title": "Improve Pixel Office React UI",
                "description": "Change TSX code, patch the repo, and list verification commands.",
                "acceptance_criteria": "Build passes and patch evidence is recorded.",
                "risk_level": "medium",
            },
            "local_coding_project_summary",
        ),
        (
            "knowledge",
            {
                "title": "Build an AI knowledge-base Q&A bot",
                "description": "Prepare source documents for retrieval and File Search style evaluation.",
                "acceptance_criteria": "Return retrieval design and evaluation questions.",
                "risk_level": "medium",
            },
            "knowledge_base_delivery_summary",
        ),
        (
            "review",
            {
                "title": "Audit customer delivery evidence",
                "description": "Review quality gates and missing approval evidence.",
                "acceptance_criteria": "Return pass/fail gate assessment.",
                "risk_level": "high",
            },
            "review_quality_gate_summary",
        ),
        (
            "general",
            {
                "title": "Plan a customer onboarding task",
                "description": "Summarize the work and next actions.",
                "acceptance_criteria": "Return concise delivery notes.",
                "risk_level": "low",
            },
            "general_customer_delivery_summary",
        ),
    ]

    profile_ids: dict[str, str] = {}
    prompt_hash_markers = 0
    combined_prompt = ""
    for label, task, expected in cases:
        prompt, profile = build_task_prompt_bundle(task, adapter="hermes")
        profile_ids[label] = profile.get("profile_id") or ""
        combined_prompt += "\n" + prompt
        require(profile.get("profile_id") == expected, f"{label} profile mismatch: {profile}", failures)
        require(profile.get("version") == "worker_prompt_profiles_v1", f"{label} profile version mismatch: {profile}", failures)
        require(bool(profile.get("profile_hash")), f"{label} missing profile hash: {profile}", failures)
        require(profile.get("raw_prompt_omitted") is True, f"{label} raw prompt omission missing: {profile}", failures)
        require("profile_hash=" in prompt and "output_contract=" in prompt, f"{label} prompt missing profile contract: {prompt}", failures)
        require("raw profile prompt body omitted" in prompt, f"{label} prompt missing raw omission boundary", failures)
        prompt_hash_markers += prompt.count("profile_hash=")

    worker_source = WORKER.read_text(encoding="utf-8")
    source_markers = [
        "PROMPT_PROFILE_VERSION",
        "select_task_prompt_profile",
        "build_task_prompt_bundle",
        "prompt_profile_id",
        "prompt_profile_version",
        "prompt_profile_hash",
        "\"prompt_profile\"",
        "agent_worker.external_write_prepared_action_required",
        "raw_prompt_omitted",
        "raw_response_omitted",
        "token_omitted",
    ]
    for marker in source_markers:
        require(marker in worker_source, f"worker source missing marker: {marker}", failures)
    require(worker_source.count('"prompt_profile_id": result.prompt_profile_id') >= 3, "tool/eval/audit profile metadata not wired from AdapterResult", failures)
    require(worker_source.count('"prompt_profile_id": prompt_profile.get("profile_id")') >= 2, "external-write prepared-action profile metadata missing", failures)
    require(prompt_hash_markers == len(cases), f"profile hash should appear once per generated prompt: {prompt_hash_markers}", failures)
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(worker_source + combined_prompt)]
    require(not secret_hits, f"secret-like pattern found in worker prompt profile path: {secret_hits}", failures)

    output = {
        "operation": "worker_prompt_profile_smoke",
        "ok": not failures,
        "profile_ids": profile_ids,
        "profile_count": len(set(profile_ids.values())),
        "source_markers_checked": len(source_markers),
        "failures": failures,
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
