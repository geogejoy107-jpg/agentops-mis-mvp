#!/usr/bin/env python3
"""Offline smoke for Agent Plan quality/rubric projections."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_core.agent_plans import (  # noqa: E402
    AGENT_PLAN_QUALITY_VERSION,
    build_agent_plan_verification,
    compute_agent_plan_hash,
)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def plan_row(**overrides) -> dict:
    row = {
        "workspace_id": "local-demo",
        "task_id": "tsk_quality_smoke",
        "run_id": None,
        "agent_id": "agt_quality_smoke",
        "task_understanding": "Operator-only source marker: QUALITY-SMOKE-SOURCE-MARKER.",
        "referenced_specs_json": json.dumps(["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"]),
        "referenced_memories_json": json.dumps(["knowledge/shared/common_failures.md"]),
        "referenced_bases_json": json.dumps(["base_local_tasks"]),
        "proposed_files_to_change_json": json.dumps(["server.py", "agentops_mis_core/agent_plans.py"]),
        "risk_level": "high",
        "approval_required": 1,
        "execution_steps_json": json.dumps(["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"]),
        "verification_plan": "Run agent_plan_quality_smoke.py and operator_evidence_report_smoke.py before promotion.",
        "rollback_plan": "Reject the plan or stop before run_start if quality, verification or approval evidence fails.",
        "plan_version": 1,
        "plan_hash": None,
    }
    row.update(overrides)
    row["plan_hash"] = row.get("plan_hash") or compute_agent_plan_hash(row)
    return row


def verify(row: dict, *, hard_checks_pass: bool = True) -> dict:
    spec_authority = {
        "ok": True,
        "readable": [{"ref": "PROJECT_SPEC.md"}, {"ref": "AGENT_WORKFLOW.md"}],
        "missing": [],
        "unsafe": [],
    }
    memory_authority = {
        "ok": True,
        "approved": [{"memory_id": "mem_quality"}],
        "non_authoritative": [],
        "missing": [],
        "knowledge_context": [{"ref": "knowledge/shared/common_failures.md"}],
    }
    base_authority = {
        "ok": True,
        "table_bases": [{"base_id": "base_local_tasks"}],
        "file_bases": [],
        "virtual_bases": [],
    }
    file_scope = {
        "ok": True,
        "scoped": [{"ref": "server.py"}, {"ref": "agentops_mis_core/agent_plans.py"}],
        "unsafe": [],
    }
    if not hard_checks_pass:
        memory_authority["ok"] = False
        memory_authority["approved"] = []
        memory_authority["missing"] = ["mem_missing"]
    return build_agent_plan_verification(
        row,
        spec_authority=spec_authority,
        memory_authority=memory_authority,
        base_authority=base_authority,
        file_scope=file_scope,
    )


def main() -> int:
    failures: list[str] = []
    ready_verification = verify(plan_row())
    quality = ready_verification.get("quality") or {}
    require(ready_verification.get("pass") is True, f"ready plan should hard-verify: {ready_verification}", failures)
    require(quality.get("version") == AGENT_PLAN_QUALITY_VERSION, f"quality version missing: {quality}", failures)
    require(quality.get("status") == "ready", f"full method plan should be ready quality: {quality}", failures)
    require(int(quality.get("score") or 0) >= 95, f"full method score too low: {quality}", failures)
    require((quality.get("method_block") or {}).get("missing_steps") == [], f"method block should be complete: {quality}", failures)
    require(quality.get("raw_plan_body_omitted") is True, f"raw plan omission missing: {quality}", failures)
    require(quality.get("raw_prompt_omitted") is True, f"raw prompt omission missing: {quality}", failures)
    require(quality.get("raw_response_omitted") is True, f"raw response omission missing: {quality}", failures)
    require(quality.get("token_omitted") is True, f"token omission missing: {quality}", failures)

    sparse = plan_row(
        execution_steps_json=json.dumps(["READ", "PLAN", "EXECUTE"]),
        verification_plan="Run tests.",
        rollback_plan="Stop.",
    )
    sparse_quality = verify(sparse).get("quality") or {}
    require(sparse_quality.get("status") in {"attention", "blocked"}, f"sparse plan should need attention: {sparse_quality}", failures)
    require("COMPARE" in ((sparse_quality.get("method_block") or {}).get("missing_steps") or []), f"missing COMPARE not surfaced: {sparse_quality}", failures)
    require("VERIFY" in ((sparse_quality.get("method_block") or {}).get("missing_steps") or []), f"missing VERIFY not surfaced: {sparse_quality}", failures)

    unsafe_governance = plan_row(risk_level="critical", approval_required=0)
    unsafe_quality = verify(unsafe_governance).get("quality") or {}
    require(unsafe_quality.get("status") != "ready", f"critical plan without approval must not be ready: {unsafe_quality}", failures)
    require("governance_posture" in (unsafe_quality.get("failed_rubric_ids") or []), f"governance failure not surfaced: {unsafe_quality}", failures)

    failed_authority_quality = verify(plan_row(), hard_checks_pass=False).get("quality") or {}
    require(failed_authority_quality.get("status") != "ready", f"failed hard checks must affect quality: {failed_authority_quality}", failures)
    require("authority_diversity" in (failed_authority_quality.get("failed_rubric_ids") or []), f"authority failure not surfaced: {failed_authority_quality}", failures)

    projection_blob = json.dumps(
        {
            "ready": quality,
            "sparse": sparse_quality,
            "unsafe": unsafe_quality,
            "failed_authority": failed_authority_quality,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    require("QUALITY-SMOKE-SOURCE-MARKER" not in projection_blob, "quality projection leaked task_understanding source marker", failures)
    require("task_understanding" not in projection_blob, "quality projection leaked source field names", failures)

    output = {
        "ok": not failures,
        "ready_score": quality.get("score"),
        "sparse_status": sparse_quality.get("status"),
        "unsafe_governance_status": unsafe_quality.get("status"),
        "failed_authority_status": failed_authority_quality.get("status"),
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
