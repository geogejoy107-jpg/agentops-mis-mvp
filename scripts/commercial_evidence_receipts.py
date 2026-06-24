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


def build_payload() -> dict[str, Any]:
    receipts = read_json(RECEIPTS_PATH)
    require(receipts.get("contract_id") == CONTRACT_ID, "receipt contract mismatch")
    require(receipts.get("status") == "partial_local_receipts_not_release_complete", "receipt status mismatch")
    require(receipts.get("release_complete") is False, "receipts must not claim release completion")
    require(receipts.get("commercial_handoff_allowed") is False, "receipts must not allow handoff")
    require(receipts.get("ready_to_merge") is False, "receipts must not claim merge readiness")

    phase_receipts = [item for item in receipts.get("phase_gate_receipts") or [] if isinstance(item, dict)]
    receipt_map = {str(item.get("gate_id")): item for item in phase_receipts}
    gate5 = receipt_map.get("gate_5_byoc_enterprise_deployment") or {}
    gate5_commands = receipt_commands(gate5)
    all_gate5_passed = all(str(item.get("status")) == "passed" for item in gate5.get("commands") or [] if isinstance(item, dict))
    require(all_gate5_passed, "Gate 5 receipts must all be passed")
    require("HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api" in gate5_commands, "Gate 5 real runtime receipt missing")
    require("python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture" in gate5_commands, "Gate 5 BYOC receipt missing")
    require("python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture" in gate5_commands, "Gate 5 Next Postgres receipt missing")
    require("python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture" in gate5_commands, "Gate 5 backend Postgres receipt missing")

    summary = dict(receipts.get("receipt_summary") or {})
    local_receipt_gates = [gate_id for gate_id, item in receipt_map.items() if item.get("local_receipt_current") is True]
    release_grade_gates = [gate_id for gate_id, item in receipt_map.items() if item.get("release_grade_current") is True]
    require(summary.get("gates_with_local_receipts") == local_receipt_gates, "local receipt summary mismatch")
    require(summary.get("gates_with_release_grade_receipts") == release_grade_gates, "release-grade receipt summary mismatch")
    require(summary.get("gate_5_release_grade_current") is False, "Gate 5 must not be release-grade current yet")
    current_head = git_output("rev-parse", "--short", "HEAD")
    if release_grade_gates:
        require(summary.get("exact_head_ci_verified") is True, "release-grade receipts require exact-head CI")
        require(summary.get("remote_sync_verified") is True, "release-grade receipts require remote sync")
        require(summary.get("clean_worktree_verified") is True, "release-grade receipts require clean worktree")
        for gate_id in release_grade_gates:
            receipt = receipt_map[gate_id]
            require(str(receipt.get("verified_head")) == current_head, f"{gate_id} receipt head is not current")

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
        require(summary.get("gates_with_release_grade_receipts") == [
            "gate_1_product_packaging_and_entitlement",
            "gate_2_production_safety_baseline",
            "gate_3_storage_boundary_before_postgres",
            "gate_4_ui_api_parity_before_nextjs",
            "gate_5_byoc_enterprise_deployment",
        ], "release-grade receipts are incomplete")
        require(summary.get("exact_head_ci_verified") is True, "exact-head CI is not verified")
        require(summary.get("remote_sync_verified") is True, "remote sync is not verified")
        require(summary.get("clean_worktree_verified") is True, "clean worktree is not verified")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
