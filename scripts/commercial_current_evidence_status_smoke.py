#!/usr/bin/env python3
"""Static smoke for the commercial current evidence status surface."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "docs" / "COMMERCIAL_CURRENT_EVIDENCE_STATUS.json"
STATUS_DOC = ROOT / "docs" / "COMMERCIAL_CURRENT_EVIDENCE_STATUS.md"
STATUS_SCRIPT = ROOT / "scripts" / "commercial_current_evidence_status.py"
CONTRACT_ID = "commercial_current_evidence_status_v1"

REQUIRED_GATE_IDS = {
    "gate_0_isolated_commercial_track",
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
}

REQUIRED_STRINGS = {
    "commercial_current_evidence_status_v1",
    "commercial_handoff_status_v1",
    "commercial_release_evidence_packet_v1",
    "release_evidence_packet_v1",
    "release_freeze_protocol_v1",
    "merge_readiness_status_v1",
    "current_evidence_required",
    "phase_gate_evidence_statuses",
    "gates_requiring_current_evidence",
    "evidence_current",
    "required_commands",
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
    "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json": REQUIRED_STRINGS,
    "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md": REQUIRED_STRINGS,
    "scripts/commercial_current_evidence_status.py": {
        "commercial_current_evidence_status_v1",
        "phase_gate_evidence_statuses",
        "gates_requiring_current_evidence",
        "--require-current-evidence",
    },
    "docs/COMMERCIAL_HANDOFF_STATUS.json": {
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status.py",
        "commercial_current_evidence_status_smoke.py",
    },
    "scripts/commercial_handoff_status.py": {
        "commercial_current_evidence_status_v1",
        "current_evidence_status",
    },
    "scripts/commercial_handoff_status_smoke.py": {
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status_smoke.py",
    },
    "docs/RELEASE_EVIDENCE_PACKET.json": {
        "current_evidence_status_command",
        "commercial_current_evidence_status_v1",
    },
    "docs/RELEASE_FREEZE_PROTOCOL.json": {
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status_smoke.py",
    },
    "docs/MERGE_READINESS_STATUS.json": {
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status_smoke.py",
    },
    "scripts/commercial_migration_readiness.py": {
        "commercial_current_evidence_status_surface_exists",
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status_smoke.py",
    },
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def run_status_script(*args: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(STATUS_SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    require(proc.returncode == 0, f"commercial current evidence status failed: {proc.stdout}{proc.stderr}")
    return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify commercial current evidence status.")
    parser.add_argument("--require-current-evidence", action="store_true", help="Fail unless every phase gate has current evidence.")
    args = parser.parse_args()

    status = read_json(STATUS_PATH)
    require(status.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(status.get("status") == "current_evidence_required", "status must remain current_evidence_required")
    require(status.get("ci_safe") is True, "current evidence status must be CI-safe")
    require(status.get("release_complete") is False, "current evidence status must not claim release completion")
    require(status.get("commercial_handoff_allowed") is False, "current evidence status must not allow handoff")
    require(status.get("ready_to_merge") is False, "current evidence status must not claim merge readiness")
    policy = status.get("evidence_policy") or {}
    require(policy.get("does_not_execute_heavy_or_live_commands") is True, "default command must stay CI-safe")
    require(policy.get("real_runtime_claims_require_live_hermes_openclaw") is True, "real runtime policy missing")
    require(policy.get("postgres_handoff_requires_no_skip") is True, "Postgres no-skip policy missing")

    gates = {str(gate.get("id")): gate for gate in status.get("phase_gate_evidence_statuses") or [] if isinstance(gate, dict)}
    require(set(gates) == REQUIRED_GATE_IDS, f"gate ids mismatch: {sorted(gates)}")
    require(gates["gate_0_isolated_commercial_track"].get("evidence_current") is True, "Gate 0 should be static-current")
    for gate_id in REQUIRED_GATE_IDS - {"gate_0_isolated_commercial_track"}:
        require(gates[gate_id].get("evidence_current") is False, f"{gate_id} must still require current evidence")
    gate5 = gates["gate_5_byoc_enterprise_deployment"]
    require(gate5.get("real_runtime_required") is True or "real_runtime" in set(gate5.get("evidence_classes") or []), "Gate 5 must require real runtime evidence")
    require("mock_only_product_claim" in set(gate5.get("must_not_use") or []), "Gate 5 mock-only ban missing")

    summary = status.get("evidence_summary") or {}
    require(summary.get("gate_count") == 6, "summary gate count mismatch")
    require(summary.get("ready_gate_count") == 1, "summary ready gate count mismatch")
    require("gate_5_byoc_enterprise_deployment" in set(summary.get("gates_requiring_current_evidence") or []), "Gate 5 gap missing")
    require(summary.get("heavy_evidence_not_executed_by_default") is True, "heavy evidence default policy missing")
    require(summary.get("postgres_required") is True, "Postgres requirement missing")
    require(summary.get("browser_required") is True, "browser requirement missing")
    require(summary.get("real_runtime_required") is True, "real runtime requirement missing")

    for relative, needles in REQUIRED_SOURCES.items():
        text = read_text(ROOT / relative)
        for needle in needles:
            require(needle in text, f"{relative} missing {needle!r}")

    output = run_status_script()
    payload = json.loads(output)
    require(payload.get("ok") is True, "operator payload must be internally consistent")
    require(payload.get("contract") == CONTRACT_ID, "operator contract mismatch")
    require(payload.get("status") == "current_evidence_required", "operator status mismatch")
    require(payload.get("release_complete") is False, "operator must not claim release complete")
    require(payload.get("commercial_handoff_allowed") is False, "operator must not allow handoff")
    require(payload.get("ready_to_merge") is False, "operator must not claim merge ready")
    runtime_gaps = set((payload.get("evidence_summary") or {}).get("gates_requiring_current_evidence") or [])
    require("gate_5_byoc_enterprise_deployment" in runtime_gaps, "operator Gate 5 gap missing")

    if args.require_current_evidence:
        require(not runtime_gaps, f"current evidence gaps remain: {sorted(runtime_gaps)}")
        require(payload.get("release_complete") is True, "release is not complete")
        require(payload.get("commercial_handoff_allowed") is True, "commercial handoff is not allowed")
        require(payload.get("ready_to_merge") is True, "merge status is not ready")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": payload.get("status"),
        "gates_requiring_current_evidence": sorted(runtime_gaps),
        "strict_current_evidence_required": bool(args.require_current_evidence),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
