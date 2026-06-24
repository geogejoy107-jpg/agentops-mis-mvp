#!/usr/bin/env python3
"""CI-safe reader for commercial evidence receipts."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_evidence_receipts_v1"
RECEIPTS_PATH = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
RELEASE_PACKET_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_EVIDENCE_PACKET.json"
REQUIRED_RELEASE_GRADE_GATES = [
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


def git_output(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return (proc.stdout or proc.stderr).strip()


def receipt_commands(receipt: dict[str, Any]) -> list[str]:
    return [str(item.get("command")) for item in receipt.get("commands") or [] if isinstance(item, dict)]


def passed_receipt_commands(receipt: dict[str, Any]) -> set[str]:
    return {
        str(item.get("command"))
        for item in receipt.get("commands") or []
        if isinstance(item, dict) and item.get("status") == "passed"
    }


def required_commands_by_gate() -> dict[str, list[str]]:
    release_packet = read_json(RELEASE_PACKET_PATH)
    require(release_packet.get("contract_id") == "commercial_release_evidence_packet_v1", "commercial release packet contract mismatch")
    return {
        str(gate.get("id")): [str(command) for command in gate.get("required_commands") or []]
        for gate in release_packet.get("phase_gate_evidence") or []
        if isinstance(gate, dict) and str(gate.get("id")) in REQUIRED_RELEASE_GRADE_GATES
    }


def validate_promotion_evidence(receipts: dict[str, Any], current_head: str) -> dict[str, Any]:
    evidence = dict(receipts.get("promotion_evidence") or {})
    summary = dict(receipts.get("receipt_summary") or {})
    exact_head_ci_verified = summary.get("exact_head_ci_verified") is True
    remote_sync_verified = summary.get("remote_sync_verified") is True
    if evidence:
        require(evidence.get("state") in {
            "exact_head_ci_and_real_runtime_verified_release_grade_blocked",
            "latest_exact_head_ci_and_real_runtime_recorded_current_head_requires_ci",
        }, "promotion evidence state mismatch")
        if exact_head_ci_verified:
            require(str(evidence.get("verified_head")) == current_head, "promotion evidence head is not current")
        else:
            require(str(evidence.get("verified_head")), "promotion evidence head missing")
        require(evidence.get("remote_sync_verified") is True, "promotion evidence remote sync missing")
        ci = evidence.get("exact_head_ci") or {}
        require(ci.get("provider") == "github_actions", "promotion evidence CI provider mismatch")
        require(ci.get("workflow") == "Commercial Migration CI", "promotion evidence CI workflow mismatch")
        expected_ci_head = current_head if exact_head_ci_verified else str(evidence.get("verified_head"))
        require(str(ci.get("head")) == expected_ci_head, "promotion evidence CI head mismatch")
        require(str(ci.get("run_id")), "promotion evidence CI run id missing")
        require(ci.get("status") == "success", "promotion evidence CI status mismatch")
        jobs = [job for job in ci.get("jobs") or [] if isinstance(job, dict)]
        require({job.get("name") for job in jobs} == {
            "Commercial core gates",
            "Storage and Postgres parity",
            "UI, deployment, and BYOC evidence",
        }, "promotion evidence CI jobs mismatch")
        require(all(job.get("status") == "success" for job in jobs), "promotion evidence CI jobs must be successful")
        runtime = evidence.get("real_runtime_acceptance") or {}
        require(runtime.get("live_openclaw") is True, "promotion evidence OpenClaw live flag missing")
        require(runtime.get("live_hermes") is True, "promotion evidence Hermes live flag missing")
        require(runtime.get("require_hermes_api") is True, "promotion evidence Hermes API requirement missing")
        require(str(runtime.get("agent_gateway_run_id", "")).startswith("run_gw_"), "promotion evidence Agent Gateway run id missing")
        require(str(runtime.get("openclaw_run_id", "")).startswith("run_api_integrations_openclaw_probe_"), "promotion evidence OpenClaw run id missing")
        require(str(runtime.get("hermes_run_id", "")).startswith("run_api_integrations_hermes_run_task_"), "promotion evidence Hermes run id missing")
        require(runtime.get("raw_prompt_omitted") is True, "promotion evidence raw prompt omission missing")
        require(runtime.get("raw_response_omitted") is True, "promotion evidence raw response omission missing")
        require(runtime.get("token_values_omitted") is True, "promotion evidence token omission missing")
        blockers = set(evidence.get("release_grade_blockers") or [])
        if not exact_head_ci_verified:
            require("exact_head_ci_not_verified" in blockers, "promotion evidence must keep exact-head CI blocker")
        require("clean_worktree_not_verified" in blockers, "promotion evidence must keep clean-worktree blocker")
        require("release_complete_false" in blockers, "promotion evidence must keep release-complete blocker")
    elif exact_head_ci_verified or remote_sync_verified:
        require(False, "promotion evidence missing")
    return evidence


def build_payload() -> dict[str, Any]:
    receipts = read_json(RECEIPTS_PATH)
    require(receipts.get("contract_id") == CONTRACT_ID, "receipt contract mismatch")
    require(receipts.get("status") == "partial_local_receipts_not_release_complete", "receipt status mismatch")
    require(receipts.get("release_complete") is False, "receipts must not claim release completion")
    require(receipts.get("commercial_handoff_allowed") is False, "receipts must not allow handoff")
    require(receipts.get("ready_to_merge") is False, "receipts must not claim merge readiness")

    phase_receipts = [item for item in receipts.get("phase_gate_receipts") or [] if isinstance(item, dict)]
    receipt_map = {str(item.get("gate_id")): item for item in phase_receipts}
    required_by_gate = required_commands_by_gate()
    require(set(required_by_gate) == set(REQUIRED_RELEASE_GRADE_GATES), "release packet gate command coverage mismatch")
    for gate_id, receipt in receipt_map.items():
        require(gate_id in required_by_gate, f"unexpected receipt gate: {gate_id}")
        if receipt.get("local_receipt_current") is True:
            commands = passed_receipt_commands(receipt)
            missing = sorted(set(required_by_gate[gate_id]) - commands)
            require(not missing, f"{gate_id} local receipts missing commands: {missing}")
            failed = [
                item.get("command")
                for item in receipt.get("commands") or []
                if isinstance(item, dict) and item.get("status") != "passed"
            ]
            require(not failed, f"{gate_id} receipts include failed commands: {failed}")

    summary = dict(receipts.get("receipt_summary") or {})
    local_receipt_gates = [gate_id for gate_id, item in receipt_map.items() if item.get("local_receipt_current") is True]
    release_grade_gates = [gate_id for gate_id, item in receipt_map.items() if item.get("release_grade_current") is True]
    require(summary.get("gates_with_local_receipts") == local_receipt_gates, "local receipt summary mismatch")
    require(summary.get("gates_with_release_grade_receipts") == release_grade_gates, "release-grade receipt summary mismatch")
    missing_local = [gate_id for gate_id in REQUIRED_RELEASE_GRADE_GATES if gate_id not in local_receipt_gates]
    require(summary.get("gates_missing_local_receipts") == missing_local, "missing local receipt summary mismatch")
    current_head = git_output("rev-parse", "--short", "HEAD")
    if release_grade_gates:
        require(summary.get("exact_head_ci_verified") is True, "release-grade receipts require exact-head CI")
        require(summary.get("remote_sync_verified") is True, "release-grade receipts require remote sync")
        require(summary.get("clean_worktree_verified") is True, "release-grade receipts require clean worktree")
        for gate_id in release_grade_gates:
            receipt = receipt_map[gate_id]
            require(str(receipt.get("verified_head")) == current_head, f"{gate_id} receipt head is not current")
    promotion_evidence = validate_promotion_evidence(receipts, current_head)

    payload = {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": receipts.get("status"),
        "ci_safe": True,
        "current_git_head": current_head,
        "working_tree_clean": not bool(git_output("status", "--short")),
        "release_complete": False,
        "commercial_handoff_allowed": False,
        "ready_to_merge": False,
        "receipt_summary": summary,
        "promotion_evidence": promotion_evidence,
        "phase_gate_receipts": phase_receipts,
        "must_not_use": receipts.get("must_not_use") or [],
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Print commercial evidence receipts.")
    parser.add_argument("--require-release-grade", action="store_true", help="Fail unless receipts are release-grade for every required gate.")
    args = parser.parse_args()

    payload = build_payload()
    if args.require_release_grade:
        summary = payload["receipt_summary"]
        require(summary.get("gates_with_release_grade_receipts") == REQUIRED_RELEASE_GRADE_GATES, "release-grade receipts are incomplete")
        require(summary.get("exact_head_ci_verified") is True, "exact-head CI is not verified")
        require(summary.get("remote_sync_verified") is True, "remote sync is not verified")
        require(summary.get("clean_worktree_verified") is True, "clean worktree is not verified")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
