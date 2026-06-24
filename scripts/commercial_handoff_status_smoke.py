#!/usr/bin/env python3
"""Static smoke for the commercial handoff status surface."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "docs" / "COMMERCIAL_HANDOFF_STATUS.json"
STATUS_DOC = ROOT / "docs" / "COMMERCIAL_HANDOFF_STATUS.md"
STATUS_SCRIPT = ROOT / "scripts" / "commercial_handoff_status.py"
CONTRACT_ID = "commercial_handoff_status_v1"

REQUIRED_STRINGS = {
    "commercial_handoff_status_v1",
    "commercial_release_promotion_preflight_v1",
    "commercial_evidence_receipts_v1",
    "commercial_current_evidence_status_v1",
    "commercial_release_evidence_packet_v1",
    "release_evidence_packet_v1",
    "release_freeze_protocol_v1",
    "merge_readiness_status_v1",
    "gate_enforced_not_release_complete",
    "freeze_active_not_release_complete",
    "blocked_release_evidence_required",
    "commercial_handoff_allowed",
    "release_complete",
    "ready_to_merge",
    "explicit_blockers",
    "required_commands",
    "current_evidence_status",
    "gates_with_local_receipts",
    "gates_with_release_grade_receipts",
    "local_receipts_complete_exact_head_required",
    "phase_gate_statuses",
    "python3 scripts/commercial_evidence_receipts.py",
    "python3 scripts/commercial_evidence_receipts_smoke.py",
    "python3 scripts/commercial_handoff_status.py",
    "python3 scripts/commercial_handoff_status_smoke.py",
    "python3 scripts/commercial_release_promotion_preflight.py",
    "python3 scripts/commercial_release_promotion_preflight_smoke.py",
    "python3 scripts/commercial_release_promotion_preflight.py --require-promotion-ready",
    "python3 scripts/commercial_current_evidence_status.py",
    "python3 scripts/commercial_current_evidence_status_smoke.py",
    "python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture",
    "python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
    "python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    "HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api",
    "--skip-postgres-if-unavailable",
    "mock_only_product_claim",
}

REQUIRED_SOURCES = {
    "docs/COMMERCIAL_HANDOFF_STATUS.json": REQUIRED_STRINGS,
    "docs/COMMERCIAL_HANDOFF_STATUS.md": REQUIRED_STRINGS,
    "scripts/commercial_handoff_status.py": {
        "commercial_handoff_status_v1",
        "commercial_release_promotion_preflight_v1",
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "gates_with_local_receipts",
        "commercial_handoff_allowed",
        "release_complete",
        "ready_to_merge",
        "explicit_blockers",
        "required_commands",
        "current_evidence_status",
        "phase_gate_statuses",
        "--require-handoff-ready",
    },
    "docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json": {
        "commercial_release_promotion_preflight_v1",
        "blocked_release_promotion_required",
        "release_promotion_allowed",
        "release_grade_update_allowed",
    },
    "docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.md": {
        "commercial_release_promotion_preflight_v1",
        "commercial_release_promotion_preflight.py",
        "commercial_release_promotion_preflight_smoke.py",
        "--require-promotion-ready",
    },
    "scripts/commercial_release_promotion_preflight.py": {
        "commercial_release_promotion_preflight_v1",
        "--require-promotion-ready",
        "remote_sync_verified",
        "clean_worktree_verified",
        "exact_head_ci_verified",
    },
    "scripts/commercial_release_promotion_preflight_smoke.py": {
        "commercial_release_promotion_preflight_v1",
        "blocked_release_promotion_required",
        "release_grade_receipts_empty",
    },
    "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json": {
        "python3 scripts/commercial_evidence_receipts.py",
        "python3 scripts/commercial_evidence_receipts_smoke.py",
        "python3 scripts/commercial_handoff_status.py",
        "python3 scripts/commercial_handoff_status_smoke.py",
        "python3 scripts/commercial_current_evidence_status.py",
        "python3 scripts/commercial_current_evidence_status_smoke.py",
    },
    "docs/RELEASE_EVIDENCE_PACKET.json": {
        "evidence_receipts_command",
        "handoff_status_command",
        "current_evidence_status_command",
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "python3 scripts/commercial_evidence_receipts.py",
        "python3 scripts/commercial_evidence_receipts_smoke.py",
        "python3 scripts/commercial_handoff_status.py",
        "python3 scripts/commercial_handoff_status_smoke.py",
    },
    "docs/RELEASE_FREEZE_PROTOCOL.json": {
        "commercial_evidence_receipts_v1",
        "python3 scripts/commercial_evidence_receipts_smoke.py",
        "commercial_current_evidence_status_v1",
        "python3 scripts/commercial_current_evidence_status_smoke.py",
        "commercial_handoff_status_v1",
        "python3 scripts/commercial_handoff_status_smoke.py",
    },
    "docs/MERGE_READINESS_STATUS.json": {
        "commercial_evidence_receipts_v1",
        "python3 scripts/commercial_evidence_receipts_smoke.py",
        "commercial_current_evidence_status_v1",
        "python3 scripts/commercial_current_evidence_status_smoke.py",
        "commercial_handoff_status_v1",
        "python3 scripts/commercial_handoff_status_smoke.py",
    },
    "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json": {
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "phase_gate_evidence_statuses",
        "gates_requiring_current_evidence",
        "gates_with_local_receipts",
        "current_evidence_required",
    },
    "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json": {
        "commercial_evidence_receipts_v1",
        "partial_local_receipts_not_release_complete",
        "gate_1_product_packaging_and_entitlement",
        "gate_2_production_safety_baseline",
        "gate_3_storage_boundary_before_postgres",
        "gate_4_ui_api_parity_before_nextjs",
        "gate_5_byoc_enterprise_deployment",
    },
    "docs/COMMERCIAL_EVIDENCE_RECEIPTS.md": {
        "commercial_evidence_receipts_v1",
        "commercial_evidence_receipts.py",
        "commercial_evidence_receipts_smoke.py",
    },
    "scripts/commercial_evidence_receipts.py": {
        "commercial_evidence_receipts_v1",
        "--require-release-grade",
    },
    "scripts/commercial_evidence_receipts_smoke.py": {
        "commercial_evidence_receipts_v1",
        "release_grade_current",
    },
    "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md": {
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status.py",
        "commercial_current_evidence_status_smoke.py",
    },
    "scripts/commercial_current_evidence_status.py": {
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "phase_gate_evidence_statuses",
        "gates_requiring_current_evidence",
        "local_receipt_current",
    },
    "scripts/commercial_current_evidence_status_smoke.py": {
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "gates_with_local_receipts",
        "current_evidence_required",
    },
    "scripts/commercial_migration_readiness.py": {
        "commercial_handoff_status_surface_exists",
        "commercial_evidence_receipts_surface_exists",
        "commercial_handoff_status_v1",
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "commercial_evidence_receipts_smoke.py",
        "commercial_handoff_status_smoke.py",
    },
}

EXPECTED_GATE_STATUSES = {
    "gate_0_isolated_commercial_track": "ready",
    "gate_1_product_packaging_and_entitlement": "evidence_required",
    "gate_2_production_safety_baseline": "evidence_required",
    "gate_3_storage_boundary_before_postgres": "evidence_required",
    "gate_4_ui_api_parity_before_nextjs": "started",
    "gate_5_byoc_enterprise_deployment": "evidence_required",
}

EXPECTED_LOCAL_RECEIPT_GATES = [
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def run_script(script: Path, *args: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    require(proc.returncode == 0, f"{script.relative_to(ROOT)} failed: {proc.stdout}{proc.stderr}")
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the commercial handoff status surface.")
    parser.add_argument("--require-handoff-ready", action="store_true", help="Fail unless the handoff status is ready.")
    args = parser.parse_args()

    status = read_json(STATUS_PATH)
    require(status.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(status.get("status") == "blocked_release_evidence_required", "handoff status must stay blocked until final evidence lands")
    require(status.get("ci_safe") is True, "handoff status must be CI-safe")
    require(status.get("commercial_handoff_allowed") is False, "handoff must not be allowed yet")
    require(status.get("release_complete") is False, "handoff status must not claim release completion")
    require(status.get("ready_to_merge") is False, "handoff status must not claim merge readiness")

    static_gates = {str(item.get("id")): str(item.get("status")) for item in status.get("phase_gate_statuses") or [] if isinstance(item, dict)}
    require(static_gates == EXPECTED_GATE_STATUSES, f"static gate statuses mismatch: {static_gates}")
    require("release_complete_false_until_all_phase_gates_have_current_evidence" in set(status.get("explicit_blockers") or []), "release blocker missing")
    require("release_promotion_preflight_not_ready" in set(status.get("explicit_blockers") or []), "promotion preflight blocker missing")
    require("python3 scripts/commercial_handoff_status.py" in set(status.get("required_commands") or []), "operator command missing")
    require("python3 scripts/commercial_handoff_status_smoke.py" in set(status.get("required_commands") or []), "smoke command missing")
    require("python3 scripts/commercial_release_promotion_preflight.py" in set(status.get("required_commands") or []), "promotion preflight command missing")
    require("python3 scripts/commercial_release_promotion_preflight_smoke.py" in set(status.get("required_commands") or []), "promotion preflight smoke missing")
    require("python3 scripts/commercial_current_evidence_status.py" in set(status.get("required_commands") or []), "current evidence command missing")
    require("python3 scripts/commercial_current_evidence_status_smoke.py" in set(status.get("required_commands") or []), "current evidence smoke missing")
    require("--skip-postgres-if-unavailable" in set(status.get("must_not_use") or []), "Postgres skip ban missing")
    require("mock_only_product_claim" in set(status.get("must_not_use") or []), "mock-only ban missing")

    for relative, needles in REQUIRED_SOURCES.items():
        text = read_text(ROOT / relative)
        for needle in needles:
            require(needle in text, f"{relative} missing {needle!r}")

    output = run_script(STATUS_SCRIPT)
    payload = json.loads(output)
    require(payload.get("ok") is True, "operator payload must be internally consistent")
    require(payload.get("contract") == CONTRACT_ID, "operator contract mismatch")
    require(payload.get("status") == "blocked_release_evidence_required", "operator status mismatch")
    require(payload.get("commercial_handoff_allowed") is False, "operator handoff state mismatch")
    require(payload.get("release_complete") is False, "operator release state mismatch")
    require(payload.get("ready_to_merge") is False, "operator merge state mismatch")
    gate_statuses = {str(item.get("id")): str(item.get("status")) for item in payload.get("phase_gate_statuses") or [] if isinstance(item, dict)}
    require(gate_statuses == EXPECTED_GATE_STATUSES, f"operator gate statuses mismatch: {gate_statuses}")
    require("gate_5_byoc_enterprise_deployment" in set(payload.get("blocking_gates") or []), "Gate 5 must remain blocking")
    evidence = payload.get("current_evidence_status") or {}
    require(evidence.get("contract") == "commercial_current_evidence_status_v1", "current evidence contract missing from handoff payload")
    require(evidence.get("status") == "current_evidence_required", "current evidence status mismatch")
    require(set(evidence.get("gates_requiring_current_evidence") or []) == set(EXPECTED_LOCAL_RECEIPT_GATES), "current evidence gaps mismatch")
    require(evidence.get("gates_with_local_receipts") == EXPECTED_LOCAL_RECEIPT_GATES, "handoff local receipt summary mismatch")
    require(evidence.get("gates_with_release_grade_receipts") == [], "handoff release-grade receipt summary mismatch")
    require(evidence.get("gates_missing_local_receipts") == [], "handoff local receipt gaps should be empty")
    require(evidence.get("exact_head_ci_verified") is False, "handoff exact-head CI should remain blocked for the current HEAD")
    require(evidence.get("remote_sync_verified") is True, "handoff remote sync should be verified")
    require(evidence.get("clean_worktree_verified") is False, "handoff clean worktree must remain false")

    if args.require_handoff_ready:
        require(payload.get("commercial_handoff_allowed") is True, "commercial handoff is not allowed")
        require(payload.get("release_complete") is True, "release is not complete")
        require(payload.get("ready_to_merge") is True, "merge status is not ready")
        require(not payload.get("blocking_gates"), f"blocking gates remain: {payload.get('blocking_gates')}")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": payload.get("status"),
        "commercial_handoff_allowed": payload.get("commercial_handoff_allowed"),
        "release_complete": payload.get("release_complete"),
        "ready_to_merge": payload.get("ready_to_merge"),
        "blocking_gates": payload.get("blocking_gates"),
        "strict_handoff_required": bool(args.require_handoff_ready),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
