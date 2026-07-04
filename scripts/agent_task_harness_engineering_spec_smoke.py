#!/usr/bin/env python3
"""Validate the Agent Task Harness engineering spec and release wiring."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "AGENT_TASK_HARNESS_ENGINEERING_SPEC.md"
RESEARCH_ACCEPTANCE = ROOT / "docs" / "AGENT_TASK_HARNESS_RESEARCH_CONSTRAINTS_ACCEPTANCE.md"
LOCAL_ACCEPTANCE = ROOT / "docs" / "LOCAL_TASK_HARNESS_ACCEPTANCE.md"
OPENCLAW_DOGFOOD = ROOT / "docs" / "OPENCLAW_LOCAL_HARNESS_DOGFOOD_2026_07_04.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_SMOKE = ROOT / "scripts" / "release_evidence_packet_smoke.py"
RELEASE_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"

COMMAND = "python3 scripts/agent_task_harness_engineering_spec_smoke.py"

REQUIRED_MARKERS = [
    "Agent Task Harness Engineering Spec",
    "Fresh Research Inputs",
    "Investigation Summary",
    "Harness Objects",
    "Product Constraint Register",
    "Work Packet Minimum",
    "Execution Phases",
    "Real Runtime And Mock Boundary",
    "Trajectory Without Private Thought",
    "Scorecard",
    "Integration With Current AgentOps MIS",
    "OpenClaw/Hermes Product Constraint",
    "Async Commander Constraint",
    "Product Roadmap",
    "Non-Goals",
    "mock_ci_fallback_verified",
    "real_runtime_verified_for_adapter_run_id",
    "summary_only_opaque_runtime",
    "approval_prepared_not_executed",
]

SOURCE_MARKERS = [
    "https://www.promptfoo.dev/docs/guides/evaluate-coding-agents/",
    "https://inspect.aisi.org.uk/",
    "https://github.com/swe-bench/SWE-bench",
    "https://arxiv.org/html/2605.27922v1",
    "https://arize.com/blog/improve-ai-agents-traces-evals-harness/",
    "https://developers.openai.com/api/docs/guides/evals",
    "https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering",
    "https://arxiv.org/html/2605.18747v1",
]

PACKET_FIELDS = [
    "packet_id",
    "packet_kind",
    "packet_version",
    "workspace_id",
    "task_id",
    "agent_id",
    "runtime_adapter",
    "runtime_connector_id",
    "objective_summary",
    "source_refs",
    "allowed_commands",
    "forbidden_actions",
    "required_approvals",
    "required_evidence",
    "verification_commands",
    "redaction_rules",
    "claim_limit",
]

PHASES = [
    "INTAKE",
    "SCOPE",
    "PLAN",
    "RETRIEVE",
    "EXECUTE",
    "OBSERVE",
    "VERIFY",
    "RECORD",
    "REVIEW",
    "REPORT",
]

SCORECARD_FIELDS = [
    "task_completed",
    "tool_trace_present",
    "eval_passed",
    "approval_satisfied",
    "artifact_recorded",
    "cost_latency_bounded",
    "secret_leak_absent",
    "memory_reviewable",
    "claim_limit_clear",
]

CONSTRAINT_MARKERS = [
    "MIS authority",
    "Agent interface",
    "Runtime proof",
    "Mock boundary",
    "Approval wall",
    "Redaction",
    "Reproducibility",
    "Async lanes",
    "External tools",
    "Customer clarity",
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

FORBIDDEN_PATTERNS = [
    re.compile(r"mock evidence (is|counts as|should be treated as) real AI work", re.IGNORECASE),
    re.compile(r"raw prompt/response (is|should be|can be) stored as evidence", re.IGNORECASE),
    re.compile(r"browser UI (is|should be|can be) the agent interface", re.IGNORECASE),
    re.compile(r"all external writes (are|should be|can be) safe without prepared actions", re.IGNORECASE),
    re.compile(r"Do not vendor Promptfoo.*in this slice.*\n.*vendor Promptfoo", re.IGNORECASE | re.DOTALL),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def without_fenced_blocks(text: str) -> str:
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def main() -> int:
    failures: list[str] = []
    spec = read(SPEC)
    spec_without_examples = without_fenced_blocks(spec)
    local_acceptance = read(LOCAL_ACCEPTANCE)
    dogfood = read(OPENCLAW_DOGFOOD)
    ci = read(CI)
    release_smoke = read(RELEASE_SMOKE)
    release_doc = read(RELEASE_DOC)
    joined = "\n".join([spec, local_acceptance, dogfood, ci, release_smoke, release_doc])

    for path, label in [
        (SPEC, "Agent task harness engineering spec"),
        (RESEARCH_ACCEPTANCE, "Agent task harness research constraints acceptance"),
        (LOCAL_ACCEPTANCE, "local task harness acceptance"),
        (OPENCLAW_DOGFOOD, "OpenClaw local harness dogfood"),
    ]:
        require(path.exists(), f"missing {label}: {path.relative_to(ROOT)}", failures)

    research_acceptance = read(RESEARCH_ACCEPTANCE)

    for marker in REQUIRED_MARKERS:
        require(marker in spec, f"spec missing marker: {marker}", failures)

    for marker in SOURCE_MARKERS:
        require(marker in spec, f"spec missing research source: {marker}", failures)

    for field in PACKET_FIELDS:
        require(f"`{field}`" in spec, f"spec missing packet field: {field}", failures)

    for phase in PHASES:
        require(phase in spec, f"spec missing phase: {phase}", failures)

    for field in SCORECARD_FIELDS:
        require(f"`{field}`" in spec, f"spec missing scorecard field: {field}", failures)

    for marker in CONSTRAINT_MARKERS:
        require(marker in spec, f"spec missing product constraint: {marker}", failures)

    require("model-harness pair" in spec, "spec missing model-harness pair investigation lesson", failures)
    require("Store summaries, hashes, ids and safe metadata" in spec, "spec missing redaction storage constraint", failures)
    require("prepared action hash, checkpoint, approval and exact once resume" in spec, "spec missing exact approval-wall constraint", failures)
    require("/api/operator/local-harness-proof" in spec, "spec missing local harness proof API next slice", failures)
    require("python3 scripts/local_task_harness.py --adapter openclaw --confirm-run" in spec, "spec missing confirmed OpenClaw harness command", failures)
    require("live_execution_performed: true" in dogfood, "OpenClaw dogfood doc missing real live evidence marker", failures)
    require("Product-readiness claims" in local_acceptance, "local task harness acceptance missing product-readiness boundary", failures)
    require("Product Translation" in research_acceptance, "research constraints acceptance missing product translation", failures)
    require("Real Hermes/OpenClaw proof needs ledger readback" in research_acceptance, "research constraints acceptance missing real-runtime proof boundary", failures)
    require(
        all(marker in research_acceptance for marker in ["raw prompts", "responses", "credentials", "private messages", "full transcripts", "forbidden"]),
        "research constraints acceptance missing raw-data prohibition",
        failures,
    )

    require(COMMAND in ci, "CI workflow missing Agent task harness spec smoke", failures)
    require(COMMAND in release_smoke, "release evidence smoke missing Agent task harness spec smoke", failures)
    require(COMMAND in release_doc, "release evidence doc missing Agent task harness spec smoke", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in harness spec surface: {len(secret_hits)}", failures)

    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(spec_without_examples)
        require(not match, f"forbidden harness claim found: {match.group(0) if match else pattern.pattern}", failures)

    output = {
        "operation": "agent_task_harness_engineering_spec_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "spec": str(SPEC.relative_to(ROOT)),
        "packet_fields": PACKET_FIELDS,
        "phases": PHASES,
        "scorecard_fields": SCORECARD_FIELDS,
        "constraint_markers": CONSTRAINT_MARKERS,
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
