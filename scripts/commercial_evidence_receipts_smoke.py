#!/usr/bin/env python3
"""Static smoke for commercial evidence receipts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECEIPTS_PATH = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
RECEIPTS_DOC = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.md"
RECEIPTS_SCRIPT = ROOT / "scripts" / "commercial_evidence_receipts.py"
RELEASE_PACKET_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_EVIDENCE_PACKET.json"
CONTRACT_ID = "commercial_evidence_receipts_v1"

REQUIRED_RECEIPT_GATE_IDS = [
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
]

REQUIRED_JSON_STRINGS = {
    "commercial_evidence_receipts_v1",
    "partial_local_receipts_not_release_complete",
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
    "local_receipts_complete_exact_head_required",
    "release_grade_current",
    "exact_head_ci_verified",
    "remote_sync_verified",
    "clean_worktree_verified",
    "run_gw_",
    "run_api_integrations_openclaw_probe_",
    "run_api_integrations_hermes_run_task_",
    "--skip-postgres-if-unavailable",
    "mock_only_product_claim",
}

REQUIRED_DOC_STRINGS = {
    "commercial_evidence_receipts_v1",
    "partial_local_receipts_not_release_complete",
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
    "local_receipts_complete_exact_head_required",
    "release-grade",
    "exact_head_ci_verified=false",
    "remote_sync_verified=false",
    "clean_worktree_verified=false",
    "--require-release-grade",
    "mock_only_product_claim",
}

REQUIRED_SCRIPT_STRINGS = {
    "commercial_evidence_receipts_v1",
    "partial_local_receipts_not_release_complete",
    "local_receipt_current",
    "release_grade_current",
    "exact_head_ci_verified",
    "remote_sync_verified",
    "clean_worktree_verified",
    "--require-release-grade",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def run_receipts(*args: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(RECEIPTS_SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    require(proc.returncode == 0, f"commercial evidence receipts failed: {proc.stdout}{proc.stderr}")
    return proc.stdout


def required_commands_by_gate() -> dict[str, set[str]]:
    release = read_json(RELEASE_PACKET_PATH)
    require(release.get("contract_id") == "commercial_release_evidence_packet_v1", "release packet contract mismatch")
    commands = {
        str(gate.get("id")): {str(command) for command in gate.get("required_commands") or []}
        for gate in release.get("phase_gate_evidence") or []
        if isinstance(gate, dict) and str(gate.get("id")) in REQUIRED_RECEIPT_GATE_IDS
    }
    require(set(commands) == set(REQUIRED_RECEIPT_GATE_IDS), "release packet receipt gate coverage mismatch")
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify commercial evidence receipts.")
    parser.add_argument("--require-release-grade", action="store_true", help="Fail unless receipts are release-grade.")
    args = parser.parse_args()

    receipts = read_json(RECEIPTS_PATH)
    required_commands = required_commands_by_gate()
    require(receipts.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(receipts.get("status") == "partial_local_receipts_not_release_complete", "receipt status mismatch")
    require(receipts.get("ci_safe") is True, "receipts must be CI-safe")
    require(receipts.get("release_complete") is False, "receipts must not claim release completion")
    require(receipts.get("commercial_handoff_allowed") is False, "receipts must not allow commercial handoff")
    require(receipts.get("ready_to_merge") is False, "receipts must not claim merge readiness")

    summary = receipts.get("receipt_summary") or {}
    require(summary.get("gates_with_local_receipts") == REQUIRED_RECEIPT_GATE_IDS, "local receipt gate summary mismatch")
    require(summary.get("gates_with_release_grade_receipts") == [], "release-grade receipts must be empty")
    require(summary.get("gates_missing_local_receipts") == [], "local receipt gaps should be empty")
    require(summary.get("gate_5_local_receipt_commands") == 7, "Gate 5 command count mismatch")
    require(summary.get("exact_head_ci_verified") is False, "exact-head CI must remain false")
    require(summary.get("remote_sync_verified") is False, "remote sync must remain false")
    require(summary.get("clean_worktree_verified") is False, "clean worktree must remain false")

    receipt_map = {
        str(item.get("gate_id")): item
        for item in receipts.get("phase_gate_receipts") or []
        if isinstance(item, dict)
    }
    require(set(receipt_map) == set(REQUIRED_RECEIPT_GATE_IDS), f"receipt gate ids mismatch: {sorted(receipt_map)}")
    for gate_id in REQUIRED_RECEIPT_GATE_IDS:
        receipt = receipt_map[gate_id]
        require(receipt.get("local_receipt_current") is True, f"{gate_id} local receipt must be current")
        require(receipt.get("release_grade_current") is False, f"{gate_id} must not be release-grade current")
        commands = {str(item.get("command")) for item in receipt.get("commands") or [] if isinstance(item, dict)}
        require(required_commands[gate_id] == commands, f"{gate_id} command receipts mismatch: {sorted(required_commands[gate_id] - commands)}")
        for command in receipt.get("commands") or []:
            require(command.get("status") == "passed", f"{gate_id} command did not pass: {command}")

    for relative, needles in {
        "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json": REQUIRED_JSON_STRINGS,
        "docs/COMMERCIAL_EVIDENCE_RECEIPTS.md": REQUIRED_DOC_STRINGS,
        "scripts/commercial_evidence_receipts.py": REQUIRED_SCRIPT_STRINGS,
    }.items():
        text = read_text(ROOT / relative)
        for needle in needles:
            require(needle in text, f"{relative} missing {needle!r}")

    doc = read_text(RECEIPTS_DOC)
    for gate_id, commands in required_commands.items():
        require(gate_id in doc, f"receipt doc missing {gate_id}")
        for command in commands:
            require(command in doc, f"receipt doc missing {command}")

    output = run_receipts()
    payload = json.loads(output)
    require(payload.get("ok") is True, "receipt payload must be internally consistent")
    require(payload.get("contract") == CONTRACT_ID, "receipt payload contract mismatch")
    require(payload.get("release_complete") is False, "receipt payload must not claim release completion")
    require(payload.get("commercial_handoff_allowed") is False, "receipt payload must not allow handoff")

    if args.require_release_grade:
        release_grade = set((payload.get("receipt_summary") or {}).get("gates_with_release_grade_receipts") or [])
        require("gate_5_byoc_enterprise_deployment" in release_grade, "Gate 5 is not release-grade current")
        require((payload.get("receipt_summary") or {}).get("exact_head_ci_verified") is True, "exact-head CI is not verified")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": payload.get("status"),
        "local_receipt_gates": payload.get("receipt_summary", {}).get("gates_with_local_receipts"),
        "release_grade_gates": payload.get("receipt_summary", {}).get("gates_with_release_grade_receipts"),
        "strict_release_grade_required": bool(args.require_release_grade),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
