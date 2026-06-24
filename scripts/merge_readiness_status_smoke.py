#!/usr/bin/env python3
"""Merge-readiness gate for the commercial migration branch."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "docs" / "MERGE_READINESS_STATUS.json"
STATUS_DOC = ROOT / "docs" / "MERGE_READINESS_STATUS.md"
FREEZE_SMOKE = ROOT / "scripts" / "release_freeze_protocol_smoke.py"
COMMERCIAL_PACKET = ROOT / "docs" / "COMMERCIAL_RELEASE_EVIDENCE_PACKET.json"
CONTRACT_ID = "merge_readiness_status_v1"

EXPECTED_GATE_STATUSES = {
    "gate_0_isolated_commercial_track": "ready",
    "gate_1_product_packaging_and_entitlement": "evidence_required",
    "gate_2_production_safety_baseline": "evidence_required",
    "gate_3_storage_boundary_before_postgres": "evidence_required",
    "gate_4_ui_api_parity_before_nextjs": "started",
    "gate_5_byoc_enterprise_deployment": "evidence_required",
}

REQUIRED_COMMANDS = {
    "python3 scripts/commercial_release_promotion_preflight.py",
    "python3 scripts/commercial_release_promotion_preflight_smoke.py",
    "python3 scripts/commercial_release_promotion_preflight.py --require-promotion-ready",
    "python3 scripts/commercial_evidence_receipts_smoke.py",
    "python3 scripts/commercial_current_evidence_status_smoke.py",
    "python3 scripts/commercial_handoff_status_smoke.py",
    "python3 scripts/release_evidence_packet_smoke.py",
    "python3 scripts/commercial_release_evidence_packet_smoke.py",
    "python3 scripts/release_freeze_protocol_smoke.py",
    "python3 scripts/commercial_migration_readiness.py",
    "python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture",
    "python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
    "python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    "HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api",
}

REQUIRED_CONTRACTS = {
    "commercial_release_promotion_preflight_v1",
    "commercial_evidence_receipts_v1",
    "commercial_current_evidence_status_v1",
    "commercial_handoff_status_v1",
    "release_evidence_packet_v1",
    "release_freeze_protocol_v1",
    "commercial_release_evidence_packet_v1",
    "deployment_readiness_postgres_runtime_write_fixture_v1",
    "nextjs_deployment_postgres_runtime_write_fixture_v1",
    "byoc_deployment_acceptance_v1",
    "real_hermes_openclaw_acceptance",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def git_status_short() -> str:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return proc.stdout.strip() or proc.stderr.strip()


def run_freeze_smoke() -> None:
    proc = subprocess.run(
        [sys.executable, str(FREEZE_SMOKE)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    require(proc.returncode == 0, f"release freeze smoke failed: {proc.stdout}{proc.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify commercial migration merge readiness status.")
    parser.add_argument("--require-ready-to-merge", action="store_true", help="Fail unless the status is READY_TO_MERGE and the worktree is clean.")
    args = parser.parse_args()

    status = read_json(STATUS_PATH)
    require(status.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(status.get("verification_command") == "python3 scripts/merge_readiness_status_smoke.py", "verification command mismatch")
    require(status.get("branch") == "codex/commercial-migration-closed-loop", "branch mismatch")
    require(status.get("source_packet") == "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "source packet reference mismatch")
    require(status.get("source_contract_id") == "commercial_release_evidence_packet_v1", "source contract mismatch")
    require(status.get("release_evidence_packet") == "docs/RELEASE_EVIDENCE_PACKET.json", "release packet reference mismatch")
    require(status.get("release_freeze_protocol") == "docs/RELEASE_FREEZE_PROTOCOL.json", "freeze protocol reference mismatch")
    require(status.get("release_freeze_contract_id") == "release_freeze_protocol_v1", "freeze contract mismatch")
    require(status.get("commercial_release_evidence_packet") == "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "commercial packet reference mismatch")
    require(REQUIRED_COMMANDS <= set(status.get("required_before_ready") or []), "merge readiness misses required commands")
    require(REQUIRED_CONTRACTS <= set(status.get("required_contracts") or []), "merge readiness misses required contracts")
    require(status.get("status") == "blocked_release_evidence_required", "this branch must remain explicit until all final evidence is current")
    require(status.get("ready_to_merge") is False, "ready_to_merge must remain false until final audit")
    require(status.get("merge_allowed") is False, "merge_allowed must remain false until final audit")
    require(status.get("commercial_handoff_allowed") is False, "commercial_handoff_allowed must remain false until final audit")
    require(status.get("release_complete") is False, "release_complete must remain false until final audit")
    blockers = set(status.get("explicit_blockers") or [])
    require("release_promotion_preflight_not_ready" in blockers, "promotion preflight blocker missing")
    require("release_complete_false_until_all_phase_gates_have_current_evidence" in blockers, "release-complete blocker missing")
    require("release_grade_receipts_empty" in blockers, "release-grade receipt blocker missing")
    require("exact_head_ci_not_verified" in blockers, "exact-head CI blocker missing")
    require("clean_worktree_not_verified" in blockers, "clean worktree blocker missing")
    require("exact_head_ci_not_checked_in_this_worktree" not in blockers, "exact-head CI blocker should be cleared")
    require("remote_sync_not_checked_in_this_worktree" not in blockers, "remote-sync blocker should be cleared")

    ready_requires = status.get("ready_requires") or {}
    for key in [
        "release_complete",
        "clean_worktree",
        "upstream_synced",
        "exact_head_ci_green",
        "release_promotion_preflight_ready",
        "gate_5_byoc_postgres_handoff_verified",
        "real_hermes_openclaw_acceptance_verified",
    ]:
        require(ready_requires.get(key) is True, f"ready requirement missing: {key}")

    doc = read_text(STATUS_DOC)
    require(CONTRACT_ID in doc, "merge readiness doc must name the contract")
    require("Current status: `blocked_release_evidence_required`" in doc, "merge readiness doc must state blocked status")
    for command in REQUIRED_COMMANDS:
        require(command in doc, f"merge readiness doc missing command: {command}")

    run_freeze_smoke()
    commercial = read_json(COMMERCIAL_PACKET)
    gates = {
        str(gate.get("id")): str(gate.get("status"))
        for gate in commercial.get("phase_gate_evidence") or []
        if isinstance(gate, dict)
    }
    require(gates == EXPECTED_GATE_STATUSES, f"commercial gate statuses changed: {gates}")

    worktree_clean = not bool(git_status_short())
    if args.require_ready_to_merge:
        require(status.get("status") == "READY_TO_MERGE" and status.get("ready_to_merge") is True, "merge status is not READY_TO_MERGE")
        require(worktree_clean, "working tree is not clean")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": status.get("status"),
        "ready_to_merge": status.get("ready_to_merge"),
        "explicit_blockers": sorted(blockers),
        "strict_ready_required": bool(args.require_ready_to_merge),
        "working_tree_clean": worktree_clean,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
