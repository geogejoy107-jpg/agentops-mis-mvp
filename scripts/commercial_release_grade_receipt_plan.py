#!/usr/bin/env python3
"""Preview release-grade receipt promotion actions without mutating receipts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from commercial_release_promotion_packet import build_packet


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_release_grade_receipt_plan_v1"
PLAN_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RECEIPT_PLAN.json"
RECEIPTS_PATH = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
RELEASE_PACKET_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_EVIDENCE_PACKET.json"
REQUIRED_GATE_IDS = [
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(path: Path) -> dict[str, Any]:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def gate_required_commands() -> dict[str, list[str]]:
    release_packet = read_json(RELEASE_PACKET_PATH)
    require(release_packet.get("contract_id") == "commercial_release_evidence_packet_v1", "release packet contract mismatch")
    return {
        str(gate.get("id")): [str(command) for command in gate.get("required_commands") or []]
        for gate in release_packet.get("phase_gate_evidence") or []
        if isinstance(gate, dict) and str(gate.get("id")) in REQUIRED_GATE_IDS
    }


def passed_commands(receipt: dict[str, Any]) -> set[str]:
    return {
        str(item.get("command"))
        for item in receipt.get("commands") or []
        if isinstance(item, dict) and item.get("status") == "passed"
    }


def gate_plan(
    *,
    gate_id: str,
    receipt: dict[str, Any],
    required_commands: list[str],
    current_head: str,
    global_blockers: list[str],
) -> dict[str, Any]:
    passed = passed_commands(receipt)
    missing_commands = [command for command in required_commands if command not in passed]
    verified_head = str(receipt.get("verified_head") or "")
    local_receipt_current = bool(receipt.get("local_receipt_current") is True and not missing_commands)
    release_grade_current = bool(receipt.get("release_grade_current") is True)
    current_head_receipt = bool(verified_head == current_head)
    blockers: list[str] = []
    if not local_receipt_current:
        blockers.append("local_receipts_incomplete")
    if missing_commands:
        blockers.append("local_receipt_commands_missing")
    if not current_head_receipt:
        blockers.append("receipt_head_not_current")
    if not release_grade_current:
        blockers.append("release_grade_receipt_not_promoted")
    blockers.extend(global_blockers)
    blockers = sorted(dict.fromkeys(blockers))

    if release_grade_current and current_head_receipt and not blockers:
        state = "release_grade_current"
    elif missing_commands:
        state = "rerun_missing_local_receipts"
    elif not current_head_receipt:
        state = "rerun_local_receipts_for_current_head"
    else:
        state = "blocked_by_global_release_invariants"

    return {
        "gate_id": gate_id,
        "promotion_state": state,
        "eligible_for_release_grade_update": False,
        "local_receipt_current": local_receipt_current,
        "release_grade_current": release_grade_current,
        "receipt_head_current": current_head_receipt,
        "verified_head": verified_head,
        "current_head": current_head,
        "command_count": len(passed),
        "required_command_count": len(required_commands),
        "missing_commands": missing_commands,
        "rerun_commands": required_commands,
        "blockers": blockers,
    }


def build_plan(
    *,
    include_external_ci: bool = False,
    require_external_ci: bool = False,
    external_ci_run_id: str | None = None,
    runtime_acceptance_json: str | None = None,
    require_current_runtime: bool = False,
) -> dict[str, Any]:
    spec = read_json(PLAN_PATH)
    require(spec.get("contract_id") == CONTRACT_ID, "receipt plan contract mismatch")
    receipts = read_json(RECEIPTS_PATH)
    require(receipts.get("contract_id") == "commercial_evidence_receipts_v1", "receipt contract mismatch")
    packet = build_packet(
        include_external_ci=include_external_ci,
        require_external_ci=require_external_ci,
        external_ci_run_id=external_ci_run_id,
        runtime_acceptance_json=runtime_acceptance_json,
        require_current_runtime=require_current_runtime,
    )
    current_head = str(packet.get("current_git_head") or "")
    receipt_map = {
        str(item.get("gate_id")): item
        for item in receipts.get("phase_gate_receipts") or []
        if isinstance(item, dict)
    }
    commands_by_gate = gate_required_commands()
    require(set(commands_by_gate) == set(REQUIRED_GATE_IDS), "release packet gate command coverage mismatch")

    packet_checks = dict(packet.get("packet_checks") or {})
    global_blockers = list(packet.get("blockers") or [])
    plans = [
        gate_plan(
            gate_id=gate_id,
            receipt=receipt_map.get(gate_id) or {},
            required_commands=commands_by_gate[gate_id],
            current_head=current_head,
            global_blockers=global_blockers,
        )
        for gate_id in REQUIRED_GATE_IDS
    ]
    gates_current_head = [item["gate_id"] for item in plans if item["receipt_head_current"]]
    gates_requiring_rerun = [item["gate_id"] for item in plans if not item["receipt_head_current"] or item["missing_commands"]]
    release_grade_gates = [item["gate_id"] for item in plans if item["release_grade_current"]]
    all_gate_receipts_current_head = len(gates_current_head) == len(REQUIRED_GATE_IDS)
    plan_checks = {
        "all_local_receipts_complete": bool(packet_checks.get("all_local_receipts_complete")),
        "all_gate_receipts_current_head": all_gate_receipts_current_head,
        "exact_head_ci_verified": bool(packet_checks.get("exact_head_ci_verified")),
        "real_runtime_acceptance_verified": bool(packet_checks.get("real_runtime_acceptance_verified")),
        "current_runtime_evidence_supplied": bool(packet_checks.get("current_runtime_evidence_supplied")),
        "clean_worktree_verified": bool(packet_checks.get("clean_worktree_verified")),
        "remote_sync_verified": bool(packet_checks.get("remote_sync_verified")),
        "release_complete": bool(packet_checks.get("release_complete")),
        "commercial_handoff_allowed": bool(packet_checks.get("commercial_handoff_allowed")),
        "ready_to_merge": bool(packet_checks.get("ready_to_merge")),
    }
    plan_blockers = list(global_blockers)
    if not all_gate_receipts_current_head:
        plan_blockers.append("gate_receipts_not_current_head")
    if release_grade_gates != REQUIRED_GATE_IDS:
        plan_blockers.append("release_grade_receipts_not_promoted")
    plan_blockers = sorted(dict.fromkeys(plan_blockers))
    plan_ready = not plan_blockers

    return {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": "receipt_promotion_plan_ready" if plan_ready else "blocked_receipt_promotion_preview",
        "ci_safe": True,
        "read_only": True,
        "current_git_head": current_head,
        "source_contracts": list(spec.get("source_contracts") or []),
        "promotion_packet": {
            "contract": packet.get("contract"),
            "status": packet.get("status"),
            "blockers": list(packet.get("blockers") or []),
            "packet_checks": packet_checks,
        },
        "plan_checks": plan_checks,
        "plan_requires": dict(spec.get("plan_requires") or {}),
        "receipt_summary": {
            "gates_with_local_receipts": list((receipts.get("receipt_summary") or {}).get("gates_with_local_receipts") or []),
            "gates_with_release_grade_receipts": list((receipts.get("receipt_summary") or {}).get("gates_with_release_grade_receipts") or []),
            "gates_current_head": gates_current_head,
            "gates_requiring_rerun": gates_requiring_rerun,
            "release_grade_gates": release_grade_gates,
        },
        "phase_gate_receipt_plan": plans,
        "blockers": plan_blockers,
        "required_commands": list(spec.get("required_commands") or []),
        "must_not_use": list(spec.get("must_not_use") or []),
        "safety": {
            "read_only": True,
            "ci_safe": True,
            "network_called": bool((packet.get("safety") or {}).get("network_called")),
            "live_execution_performed": False,
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
    parser = argparse.ArgumentParser(description="Preview commercial release-grade receipt promotion actions.")
    parser.add_argument("--include-external-ci-evidence", action="store_true", help="Query GitHub Actions for current HEAD exact CI evidence.")
    parser.add_argument("--require-external-ci-evidence", action="store_true", help="Fail unless GitHub Actions verifies current HEAD exact CI evidence.")
    parser.add_argument("--external-ci-run-id", help="Specific GitHub Actions run id to verify as exact-head CI evidence.")
    parser.add_argument("--runtime-acceptance-json", help="Path to local_runtime_acceptance.py JSON output, or '-' for stdin.")
    parser.add_argument("--require-current-runtime-evidence", action="store_true", help="Require operator-supplied runtime acceptance JSON.")
    parser.add_argument("--require-plan-ready", action="store_true", help="Fail unless every receipt promotion plan requirement is ready.")
    args = parser.parse_args()

    payload = build_plan(
        include_external_ci=bool(args.include_external_ci_evidence or args.require_external_ci_evidence),
        require_external_ci=bool(args.require_external_ci_evidence),
        external_ci_run_id=args.external_ci_run_id,
        runtime_acceptance_json=args.runtime_acceptance_json,
        require_current_runtime=bool(args.require_current_runtime_evidence),
    )
    if args.require_plan_ready:
        require(payload["status"] == "receipt_promotion_plan_ready", f"receipt promotion blockers remain: {payload['blockers']}")
        for key, expected in (payload.get("plan_requires") or {}).items():
            require((payload.get("plan_checks") or {}).get(key) is expected, f"plan requirement not met: {key}")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
