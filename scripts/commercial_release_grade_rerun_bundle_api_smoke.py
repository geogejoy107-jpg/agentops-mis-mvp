#!/usr/bin/env python3
"""Smoke the read-only commercial release-grade rerun bundle API projection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


RECEIPTS_JSON = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
CONTRACT_ID = "commercial_release_grade_rerun_bundle_v1"
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
    payload = server.commercial_release_grade_rerun_bundle_status({}, {})
    after_hash = file_hash(RECEIPTS_JSON)
    require(before_hash == after_hash, "rerun bundle API must not mutate receipts")
    require(payload.get("contract_id") == CONTRACT_ID, "API contract mismatch")
    require(payload.get("operation") == "commercial_release_grade_rerun_bundle", "API operation mismatch")
    require(payload.get("read_only") is True and payload.get("ci_safe") is True, "API must be read-only/CI-safe")
    require((payload.get("safety") or {}).get("network_called") is False, "default API must not call network")
    require((payload.get("safety") or {}).get("live_execution_performed") is False, "API must not run live evidence")
    require((payload.get("safety") or {}).get("mutates_receipts") is False, "API must not mutate receipts")
    require((payload.get("safety") or {}).get("executes_rerun_commands") is False, "API must not execute rerun commands")
    summary = payload.get("bundle_summary") or {}
    require(summary.get("bundle_count") == len(REQUIRED_GATE_IDS), "API bundle count mismatch")
    require(summary.get("write_preview_count") == len(REQUIRED_GATE_IDS), "API write preview count mismatch")
    require(summary.get("mutating_write_count") == 0, "API must report zero mutating writes")
    bundles = payload.get("phase_gate_rerun_bundles") or []
    require([item.get("gate_id") for item in bundles] == REQUIRED_GATE_IDS, "API gate coverage mismatch")
    for item in bundles:
        require(item.get("rerun_commands"), f"{item.get('gate_id')} rerun commands missing")
        require(item.get("executes_rerun_commands") is False, f"{item.get('gate_id')} must not execute commands")
        require((item.get("write_preview") or {}).get("mutates_receipts") is False, f"{item.get('gate_id')} preview must be read-only")
    require("receipt_rerun_required" in set(payload.get("blockers") or []), "API must surface receipt rerun blocker")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": payload.get("status"),
        "gate_count": len(bundles),
        "network_called": (payload.get("safety") or {}).get("network_called"),
        "receipts_mutated": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
