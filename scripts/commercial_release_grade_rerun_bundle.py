#!/usr/bin/env python3
"""Preview per-gate release-grade receipt rerun bundles without writing receipts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from commercial_release_grade_receipt_plan import REQUIRED_GATE_IDS, build_plan


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_release_grade_rerun_bundle_v1"
BUNDLE_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RERUN_BUNDLE.json"
RECEIPTS_PATH = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(path: Path) -> dict[str, Any]:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def receipt_write_preview(*, gate_plan: dict[str, Any], current_head: str) -> dict[str, Any]:
    previous_head = str(gate_plan.get("verified_head") or "")
    missing_commands = list(gate_plan.get("missing_commands") or [])
    before = {
        "verified_head": previous_head,
        "local_receipt_current": bool(gate_plan.get("local_receipt_current")),
        "release_grade_current": bool(gate_plan.get("release_grade_current")),
        "command_count": int(gate_plan.get("command_count") or 0),
        "required_command_count": int(gate_plan.get("required_command_count") or 0),
    }
    would_set = {
        "verified_head": current_head,
        "local_receipt_current": not missing_commands,
        "release_grade_current": False,
        "receipt_state": "local_receipt_rerun_preview_ready" if not missing_commands else "local_receipt_commands_missing",
        "release_grade_update_allowed": False,
        "requires_release_grade_promotion": True,
    }
    diff_preview = [
        {"field": key, "before": before.get(key), "after": value}
        for key, value in would_set.items()
        if before.get(key) != value
    ]
    return {
        "target": "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json",
        "operation": "preview_only_no_write",
        "path": f"phase_gate_receipts[gate_id={gate_plan.get('gate_id')}]",
        "mutates_receipts": False,
        "write_before": before,
        "would_set": would_set,
        "diff_preview": diff_preview,
    }


def build_bundle_item(*, gate_plan: dict[str, Any], current_head: str) -> dict[str, Any]:
    gate_id = str(gate_plan.get("gate_id") or "")
    missing_commands = list(gate_plan.get("missing_commands") or [])
    receipt_head_current = bool(gate_plan.get("receipt_head_current"))
    release_grade_current = bool(gate_plan.get("release_grade_current"))
    blockers = list(gate_plan.get("blockers") or [])
    if missing_commands:
        state = "rerun_required_missing_local_receipts"
    elif not receipt_head_current:
        state = "rerun_required_current_head"
    elif release_grade_current and not blockers:
        state = "release_grade_receipt_current_preview"
    else:
        state = "blocked_by_global_release_invariants"
    return {
        "gate_id": gate_id,
        "bundle_id": f"rerun_{gate_id}",
        "state": state,
        "current_head": current_head,
        "previous_verified_head": str(gate_plan.get("verified_head") or ""),
        "receipt_head_current": receipt_head_current,
        "local_receipt_current": bool(gate_plan.get("local_receipt_current")),
        "release_grade_current": release_grade_current,
        "missing_commands": missing_commands,
        "rerun_commands": list(gate_plan.get("rerun_commands") or []),
        "executes_rerun_commands": False,
        "write_preview": receipt_write_preview(gate_plan=gate_plan, current_head=current_head),
        "blockers": blockers,
    }


def build_bundle(
    *,
    include_external_ci: bool = False,
    require_external_ci: bool = False,
    external_ci_run_id: str | None = None,
    runtime_acceptance_json: str | None = None,
    require_current_runtime: bool = False,
) -> dict[str, Any]:
    spec = read_json(BUNDLE_PATH)
    require(spec.get("contract_id") == CONTRACT_ID, "rerun bundle contract mismatch")
    plan = build_plan(
        include_external_ci=include_external_ci,
        require_external_ci=require_external_ci,
        external_ci_run_id=external_ci_run_id,
        runtime_acceptance_json=runtime_acceptance_json,
        require_current_runtime=require_current_runtime,
    )
    current_head = str(plan.get("current_git_head") or "")
    gate_plans = list(plan.get("phase_gate_receipt_plan") or [])
    require([str(item.get("gate_id")) for item in gate_plans] == REQUIRED_GATE_IDS, "rerun bundle gate coverage mismatch")
    bundles = [build_bundle_item(gate_plan=item, current_head=current_head) for item in gate_plans]

    gates_requiring_rerun = list((plan.get("receipt_summary") or {}).get("gates_requiring_rerun") or [])
    write_preview_count = sum(1 for item in bundles if item.get("write_preview"))
    command_count = sum(len(item.get("rerun_commands") or []) for item in bundles)
    read_only_previews = all((item.get("write_preview") or {}).get("mutates_receipts") is False for item in bundles)
    bundle_checks = {
        "all_gate_rerun_bundles_materialized": len(bundles) == len(REQUIRED_GATE_IDS),
        "all_bundle_write_previews_read_only": read_only_previews,
        "all_gate_receipts_current_head": bool((plan.get("plan_checks") or {}).get("all_gate_receipts_current_head")),
        "exact_head_ci_verified": bool((plan.get("plan_checks") or {}).get("exact_head_ci_verified")),
        "real_runtime_acceptance_verified": bool((plan.get("plan_checks") or {}).get("real_runtime_acceptance_verified")),
        "clean_worktree_verified": bool((plan.get("plan_checks") or {}).get("clean_worktree_verified")),
        "remote_sync_verified": bool((plan.get("plan_checks") or {}).get("remote_sync_verified")),
        "release_complete": bool((plan.get("plan_checks") or {}).get("release_complete")),
        "commercial_handoff_allowed": bool((plan.get("plan_checks") or {}).get("commercial_handoff_allowed")),
        "ready_to_merge": bool((plan.get("plan_checks") or {}).get("ready_to_merge")),
    }
    blockers = list(plan.get("blockers") or [])
    if gates_requiring_rerun:
        blockers.append("receipt_rerun_required")
    if not read_only_previews:
        blockers.append("receipt_write_preview_not_read_only")
    blockers = sorted(dict.fromkeys(blockers))
    bundle_ready = not blockers and all(
        bundle_checks.get(key) is expected
        for key, expected in (spec.get("bundle_requires") or {}).items()
    )

    return {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": "rerun_bundle_ready" if bundle_ready else "blocked_rerun_bundle_preview",
        "ci_safe": True,
        "read_only": True,
        "current_git_head": current_head,
        "source_contracts": list(spec.get("source_contracts") or []),
        "release_grade_receipt_plan": {
            "contract": plan.get("contract"),
            "status": plan.get("status"),
            "blockers": list(plan.get("blockers") or []),
            "plan_checks": dict(plan.get("plan_checks") or {}),
        },
        "bundle_checks": bundle_checks,
        "bundle_requires": dict(spec.get("bundle_requires") or {}),
        "plan_summary": {
            "gate_count": len(gate_plans),
            "gates_requiring_rerun": gates_requiring_rerun,
            "all_gate_receipts_current_head": bundle_checks["all_gate_receipts_current_head"],
            "exact_head_ci_verified": bundle_checks["exact_head_ci_verified"],
            "real_runtime_acceptance_verified": bundle_checks["real_runtime_acceptance_verified"],
            "current_runtime_evidence_supplied": bool((plan.get("plan_checks") or {}).get("current_runtime_evidence_supplied")),
        },
        "bundle_summary": {
            "gate_count": len(REQUIRED_GATE_IDS),
            "bundle_count": len(bundles),
            "bundles_requiring_rerun": len(gates_requiring_rerun),
            "write_preview_count": write_preview_count,
            "mutating_write_count": 0,
            "command_count": command_count,
        },
        "phase_gate_rerun_bundles": bundles,
        "blockers": blockers,
        "required_commands": list(spec.get("required_commands") or []),
        "must_not_use": list(spec.get("must_not_use") or []),
        "safety": {
            "read_only": True,
            "ci_safe": True,
            "network_called": bool(((plan.get("safety") or {}).get("network_called"))),
            "live_execution_performed": False,
            "executes_rerun_commands": False,
            "mutates_receipts": False,
            "allows_handoff_or_merge": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "private_transcripts_omitted": True,
            "billing_call_performed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview commercial release-grade receipt rerun bundles.")
    parser.add_argument("--include-external-ci-evidence", action="store_true", help="Query GitHub Actions for current HEAD exact CI evidence.")
    parser.add_argument("--require-external-ci-evidence", action="store_true", help="Fail unless GitHub Actions verifies current HEAD exact CI evidence.")
    parser.add_argument("--external-ci-run-id", help="Specific GitHub Actions run id to verify as exact-head CI evidence.")
    parser.add_argument("--runtime-acceptance-json", help="Path to local_runtime_acceptance.py JSON output, or '-' for stdin.")
    parser.add_argument("--require-current-runtime-evidence", action="store_true", help="Require operator-supplied runtime acceptance JSON.")
    parser.add_argument("--require-bundle-ready", action="store_true", help="Fail unless every rerun bundle requirement is ready.")
    args = parser.parse_args()

    payload = build_bundle(
        include_external_ci=bool(args.include_external_ci_evidence or args.require_external_ci_evidence),
        require_external_ci=bool(args.require_external_ci_evidence),
        external_ci_run_id=args.external_ci_run_id,
        runtime_acceptance_json=args.runtime_acceptance_json,
        require_current_runtime=bool(args.require_current_runtime_evidence),
    )
    if args.require_bundle_ready:
        require(payload["status"] == "rerun_bundle_ready", f"rerun bundle blockers remain: {payload['blockers']}")
        for key, expected in (payload.get("bundle_requires") or {}).items():
            require((payload.get("bundle_checks") or {}).get(key) is expected, f"bundle requirement not met: {key}")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
