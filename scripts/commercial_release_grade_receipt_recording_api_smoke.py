#!/usr/bin/env python3
"""Smoke the read-only commercial release-grade receipt recording API projection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


RECEIPTS_JSON = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
CONTRACT_ID = "commercial_release_grade_receipt_recording_v1"
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


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    before_hash = file_hash(RECEIPTS_JSON)
    payload = server.commercial_release_grade_receipt_recording_status({}, {})
    after_hash = file_hash(RECEIPTS_JSON)
    require(before_hash == after_hash, "receipt recording API must not mutate receipts")
    require(payload.get("contract_id") == CONTRACT_ID, "API contract mismatch")
    require(payload.get("operation") == "commercial_release_grade_receipt_recording", "API operation mismatch")
    require(payload.get("read_only") is True and payload.get("ci_safe") is True, "API must be read-only/CI-safe")
    safety = payload.get("safety") or {}
    require(safety.get("network_called") is False, "default API must not call network")
    require(safety.get("live_execution_performed") is False, "API must not run live evidence")
    require(safety.get("mutates_receipts") is False, "API must not mutate receipts")
    require(safety.get("writes_release_grade_receipts") is False, "API must not write release-grade receipts")
    require(safety.get("executes_rerun_commands") is False, "API must not execute rerun commands")
    summary = payload.get("recording_summary") or {}
    require(summary.get("recording_request_count") == len(REQUIRED_GATE_IDS), "API recording request count mismatch")
    require(summary.get("mutating_write_count") == 0, "API must report zero mutating writes")
    requests = payload.get("phase_gate_recording_requests") or []
    require([item.get("gate_id") for item in requests] == REQUIRED_GATE_IDS, "API gate coverage mismatch")
    for item in requests:
        require(item.get("operation") == "preview_only_json_patch", f"{item.get('gate_id')} operation mismatch")
        require(item.get("mutates_receipts") is False, f"{item.get('gate_id')} must be read-only")
        require(item.get("writes_release_grade_receipt") is False, f"{item.get('gate_id')} must not write release-grade receipt")
        require(item.get("requires_operator_confirmation") is True, f"{item.get('gate_id')} must require operator confirmation")
        require(item.get("json_patch_preview"), f"{item.get('gate_id')} patch preview missing")
    require("operator_confirmation_required" in set(payload.get("blockers") or []), "API must surface operator confirmation blocker")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": payload.get("status"),
        "gate_count": len(requests),
        "network_called": safety.get("network_called"),
        "receipts_mutated": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
