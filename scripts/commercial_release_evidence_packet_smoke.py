#!/usr/bin/env python3
"""Static smoke for the commercial release evidence packet."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKET_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_EVIDENCE_PACKET.json"
PACKET_DOC = ROOT / "docs" / "COMMERCIAL_RELEASE_EVIDENCE_PACKET.md"
CONTRACT_ID = "commercial_release_evidence_packet_v1"

REQUIRED_GATE_IDS = {
    "gate_0_isolated_commercial_track",
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
}

REQUIRED_HANDOFF_COMMANDS = {
    "python3 scripts/commercial_handoff_status.py",
    "python3 scripts/commercial_handoff_status_smoke.py",
    "python3 scripts/commercial_evidence_receipts.py",
    "python3 scripts/commercial_evidence_receipts_smoke.py",
    "python3 scripts/commercial_current_evidence_status.py",
    "python3 scripts/commercial_current_evidence_status_smoke.py",
    "python3 scripts/release_evidence_packet_smoke.py",
    "python3 scripts/commercial_release_evidence_packet_smoke.py",
    "python3 scripts/release_freeze_protocol_smoke.py",
    "python3 scripts/merge_readiness_status_smoke.py",
    "python3 scripts/commercial_migration_readiness.py",
    "python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    "python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture",
    "python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
    "HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api",
}

GATE5_REQUIRED_COMMANDS = {
    "python3 scripts/audit_retention_policy_smoke.py",
    "python3 scripts/audit_retention_controls_smoke.py --configured-fixture",
    "python3 scripts/deployment_readiness_smoke.py --configured-retention-fixture --configured-enterprise-fixture",
    "python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture",
    "python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
    "python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    "HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api",
}

GATE5_REQUIRED_CONTRACTS = {
    "audit_retention_policy_v1",
    "audit_retention_controls_v1",
    "deployment_readiness_v1",
    "enterprise_byoc_controls_v1",
    "deployment_readiness_postgres_runtime_write_fixture_v1",
    "nextjs_deployment_postgres_runtime_write_fixture_v1",
    "byoc_deployment_acceptance_v1",
    "postgres_http_runtime_prepared_action_write_v1",
    "postgres_http_runtime_approval_decision_write_v1",
    "real_hermes_openclaw_acceptance",
}

REQUIRED_SOURCES = {
    "docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md": [
        "release_evidence_packet_v1",
        "commercial_release_evidence_packet_v1",
        "commercial_evidence_receipts_v1",
        "commercial_handoff_status_v1",
        "commercial_current_evidence_status_v1",
        "release_evidence_packet_smoke.py",
        "commercial_release_evidence_packet_smoke.py",
        "commercial_evidence_receipts_smoke.py",
        "commercial_handoff_status_smoke.py",
        "commercial_current_evidence_status_smoke.py",
        "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
        "deployment_readiness_smoke.py --postgres-write-fixture",
        "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
        "local_runtime_acceptance.py --live-openclaw --live-hermes",
    ],
    "docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md": [
        "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
        "deployment_readiness_smoke.py --postgres-write-fixture",
    ],
    "docs/POSTGRES_PARITY_CONTRACT.md": [
        "deployment_readiness_postgres_runtime_write_fixture_v1",
        "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    ],
    "docs/UI_API_PARITY_MATRIX.json": [
        "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
        "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    ],
    "ui/next-app/README.md": [
        "deployment_readiness_smoke.py --postgres-write-fixture",
        "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
    ],
    "scripts/byoc_deployment_acceptance_smoke.py": [
        "--postgres-readiness-fixture",
        "deployment_readiness_postgres_runtime_write_fixture_v1",
        "postgres_read_only_backend",
        "postgres_counts_unchanged",
    ],
    "scripts/deployment_readiness_smoke.py": [
        "--postgres-write-fixture",
        "deployment_readiness_postgres_runtime_write_fixture_v1",
        "non_allowlisted_write_error",
    ],
    "scripts/nextjs_playwright_snapshot_smoke.py": [
        "--postgres-write-fixture",
        "nextjs_deployment_postgres_runtime_write_fixture_v1",
        "runtime_write_gate",
    ],
    "scripts/local_runtime_acceptance.py": [
        "--live-openclaw",
        "--live-hermes",
        "prepared_action_status",
    ],
    "docs/RELEASE_EVIDENCE_PACKET.json": [
        "release_evidence_packet_v1",
        "commercial_release_evidence_packet_v1",
        "commercial_evidence_receipts_v1",
        "commercial_handoff_status_v1",
        "commercial_current_evidence_status_v1",
        "commercial_evidence_receipts.py",
        "commercial_evidence_receipts_smoke.py",
        "commercial_handoff_status.py",
        "commercial_handoff_status_smoke.py",
        "commercial_current_evidence_status.py",
        "commercial_current_evidence_status_smoke.py",
        "release_freeze_protocol_smoke.py",
        "merge_readiness_status_smoke.py",
        "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
        "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
        "local_runtime_acceptance.py --live-openclaw --live-hermes",
    ],
    "docs/RELEASE_EVIDENCE_PACKET.md": [
        "release_evidence_packet_v1",
        "commercial_release_evidence_packet_v1",
        "commercial_evidence_receipts_v1",
        "commercial_evidence_receipts.py",
        "commercial_evidence_receipts_smoke.py",
        "commercial_handoff_status.py",
        "commercial_handoff_status_smoke.py",
        "commercial_current_evidence_status.py",
        "commercial_current_evidence_status_smoke.py",
        "release_freeze_protocol_smoke.py",
        "merge_readiness_status_smoke.py",
        "mock-only",
    ],
    "docs/RELEASE_FREEZE_PROTOCOL.json": [
        "release_freeze_protocol_v1",
        "commercial_evidence_receipts_v1",
        "commercial_evidence_receipts_smoke.py",
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status_smoke.py",
        "commercial_handoff_status_v1",
        "commercial_handoff_status_smoke.py",
        "commercial_current_evidence_status_smoke.py",
        "freeze_active_not_release_complete",
        "commercial_release_evidence_packet_v1",
        "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
        "mock_only_product_claim",
        "sqlite_fallback_as_postgres_proof",
    ],
    "docs/RELEASE_FREEZE_PROTOCOL.md": [
        "release_freeze_protocol_v1",
        "freeze_active_not_release_complete",
        "commercial_handoff_status_smoke.py",
        "release_freeze_protocol_smoke.py",
    ],
    "docs/MERGE_READINESS_STATUS.json": [
        "merge_readiness_status_v1",
        "commercial_evidence_receipts_v1",
        "commercial_evidence_receipts_smoke.py",
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status_smoke.py",
        "commercial_handoff_status_v1",
        "commercial_handoff_status_smoke.py",
        "commercial_current_evidence_status_smoke.py",
        "blocked_release_evidence_required",
        "commercial_release_evidence_packet_v1",
        "release_freeze_protocol_v1",
        "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    ],
    "docs/MERGE_READINESS_STATUS.md": [
        "merge_readiness_status_v1",
        "blocked_release_evidence_required",
        "commercial_handoff_status_smoke.py",
        "merge_readiness_status_smoke.py",
    ],
    "docs/COMMERCIAL_HANDOFF_STATUS.json": [
        "commercial_handoff_status_v1",
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "commercial_release_evidence_packet_v1",
        "release_evidence_packet_v1",
        "release_freeze_protocol_v1",
        "merge_readiness_status_v1",
        "blocked_release_evidence_required",
        "phase_gate_statuses",
        "current_evidence_status",
        "gates_with_local_receipts",
        "explicit_blockers",
        "required_commands",
    ],
    "docs/COMMERCIAL_HANDOFF_STATUS.md": [
        "commercial_handoff_status_v1",
        "commercial_handoff_status.py",
        "commercial_handoff_status_smoke.py",
        "commercial_current_evidence_status_v1",
        "blocked_release_evidence_required",
    ],
    "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json": [
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "commercial_handoff_status_v1",
        "commercial_release_evidence_packet_v1",
        "release_evidence_packet_v1",
        "release_freeze_protocol_v1",
        "merge_readiness_status_v1",
        "current_evidence_required",
        "phase_gate_evidence_statuses",
        "gates_requiring_current_evidence",
        "gates_with_local_receipts",
        "required_commands",
    ],
    "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json": [
        "commercial_evidence_receipts_v1",
        "partial_local_receipts_not_release_complete",
        "local_receipts_complete_exact_head_required",
        "gate_5_byoc_enterprise_deployment",
    ],
    "docs/COMMERCIAL_EVIDENCE_RECEIPTS.md": [
        "commercial_evidence_receipts_v1",
        "commercial_evidence_receipts.py",
        "commercial_evidence_receipts_smoke.py",
        "release-grade",
    ],
    "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md": [
        "commercial_current_evidence_status_v1",
        "commercial_evidence_receipts_v1",
        "commercial_evidence_receipts.py",
        "commercial_evidence_receipts_smoke.py",
        "commercial_current_evidence_status.py",
        "commercial_current_evidence_status_smoke.py",
        "current_evidence_required",
    ],
    "scripts/commercial_handoff_status.py": [
        "commercial_handoff_status_v1",
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "commercial_handoff_allowed",
        "current_evidence_status",
        "gates_with_local_receipts",
        "phase_gate_statuses",
        "explicit_blockers",
        "required_commands",
    ],
    "scripts/commercial_handoff_status_smoke.py": [
        "commercial_handoff_status_v1",
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "commercial_evidence_receipts_smoke.py",
        "commercial_current_evidence_status_smoke.py",
        "commercial_release_evidence_packet_v1",
        "release_freeze_protocol_v1",
        "merge_readiness_status_v1",
    ],
    "scripts/commercial_current_evidence_status.py": [
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "phase_gate_evidence_statuses",
        "gates_requiring_current_evidence",
        "local_receipt_current",
        "--require-current-evidence",
    ],
    "scripts/commercial_current_evidence_status_smoke.py": [
        "commercial_evidence_receipts_v1",
        "commercial_current_evidence_status_v1",
        "gates_with_local_receipts",
        "current_evidence_required",
        "commercial_release_evidence_packet_v1",
    ],
    "scripts/commercial_evidence_receipts.py": [
        "commercial_evidence_receipts_v1",
        "--require-release-grade",
        "local_receipt_current",
    ],
    "scripts/commercial_evidence_receipts_smoke.py": [
        "commercial_evidence_receipts_v1",
        "release_grade_current",
        "gate_5_byoc_enterprise_deployment",
    ],
    "scripts/release_evidence_packet_smoke.py": [
        "release_evidence_packet_v1",
        "commercial_release_evidence_packet_v1",
        "commercial_evidence_receipts",
        "commercial_handoff_status",
        "commercial_current_evidence_status",
        "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    ],
    "scripts/release_freeze_protocol_smoke.py": [
        "release_freeze_protocol_v1",
        "commercial_evidence_receipts_v1",
        "commercial_evidence_receipts_smoke.py",
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status_smoke.py",
        "commercial_handoff_status_v1",
        "commercial_handoff_status_smoke.py",
        "freeze_active_not_release_complete",
        "release_evidence_packet_smoke.py",
    ],
    "scripts/merge_readiness_status_smoke.py": [
        "merge_readiness_status_v1",
        "commercial_evidence_receipts_v1",
        "commercial_evidence_receipts_smoke.py",
        "commercial_current_evidence_status_v1",
        "commercial_current_evidence_status_smoke.py",
        "commercial_handoff_status_v1",
        "commercial_handoff_status_smoke.py",
        "blocked_release_evidence_required",
        "release_freeze_protocol_smoke.py",
    ],
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def commands_for(gate: dict[str, Any]) -> set[str]:
    return {str(item) for item in gate.get("required_commands") or []}


def contracts_for(gate: dict[str, Any]) -> set[str]:
    return {str(item) for item in gate.get("required_contracts") or []}


def main() -> int:
    packet = read_json(PACKET_PATH)
    require(packet.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(packet.get("status") == "gate_enforced_not_release_complete", "packet must not claim release completion")
    scope = packet.get("scope") or {}
    require(scope.get("release_complete") is False, "commercial packet must remain completion-honest")
    require(scope.get("branch") == "codex/commercial-migration-closed-loop", "packet branch is wrong")

    policy = packet.get("policy") or {}
    require(policy.get("agent_gateway_cli_api_mcp_durable") is True, "Agent Gateway contract must remain durable")
    require(policy.get("python_sqlite_vite_remain_canonical_until_parity") is True, "Python/SQLite/Vite canonical policy missing")
    require(policy.get("nextjs_replaces_routes_only_after_explicit_retirement") is True, "Next.js route-retirement guard missing")
    require(policy.get("postgres_requires_storage_boundary_and_byoc_evidence") is True, "Postgres BYOC evidence policy missing")
    require(policy.get("live_runtime_product_claims_require_real_hermes_openclaw") is True, "real runtime evidence policy missing")
    require(policy.get("mock_evidence_is_ci_or_offline_only") is True, "mock evidence policy missing")
    require(policy.get("verification_command") == "python3 scripts/commercial_release_evidence_packet_smoke.py", "verification command mismatch")
    forbidden = set(policy.get("forbidden_committed_material") or [])
    require(
        {"secrets", "local_databases", "generated_artifacts", "raw_prompts", "raw_responses", "private_transcripts", "token_values"} <= forbidden,
        "forbidden material policy is incomplete",
    )

    gates = {str(gate.get("id")): gate for gate in packet.get("phase_gate_evidence") or [] if isinstance(gate, dict)}
    require(REQUIRED_GATE_IDS == set(gates), f"phase gates mismatch: {sorted(gates)}")
    for gate_id, gate in gates.items():
        require(commands_for(gate), f"{gate_id} must list evidence commands")
        require(contracts_for(gate), f"{gate_id} must list evidence contracts")

    gate5 = gates["gate_5_byoc_enterprise_deployment"]
    require(gate5.get("status") == "evidence_required", "Gate 5 must require evidence")
    require(GATE5_REQUIRED_COMMANDS <= commands_for(gate5), f"Gate 5 missing commands: {sorted(GATE5_REQUIRED_COMMANDS - commands_for(gate5))}")
    require(GATE5_REQUIRED_CONTRACTS <= contracts_for(gate5), f"Gate 5 missing contracts: {sorted(GATE5_REQUIRED_CONTRACTS - contracts_for(gate5))}")
    gate5_commands = "\n".join(commands_for(gate5))
    require("--skip-postgres-if-unavailable" not in gate5_commands, "release handoff must not allow skipped Postgres proof")
    require("--live-openclaw" in gate5_commands and "--live-hermes" in gate5_commands, "Gate 5 must require real Hermes/OpenClaw acceptance")
    require("HERMES_ALLOW_REAL_RUN=true" in gate5_commands, "real Hermes acceptance must be explicit")
    require("mock_only_product_claim" in set(gate5.get("must_not_use") or []), "Gate 5 must reject mock-only product claims")

    handoff_commands = {str(item) for item in packet.get("handoff_required_commands") or []}
    require(REQUIRED_HANDOFF_COMMANDS <= handoff_commands, f"handoff commands missing: {sorted(REQUIRED_HANDOFF_COMMANDS - handoff_commands)}")
    require(not any("--skip-postgres-if-unavailable" in item for item in handoff_commands), "handoff commands must not skip Postgres")

    output_policy = packet.get("sensitive_output_policy") or {}
    require(output_policy.get("raw_prompts_allowed") is False, "raw prompts must be forbidden")
    require(output_policy.get("raw_responses_allowed") is False, "raw responses must be forbidden")
    require(output_policy.get("token_values_allowed") is False, "token values must be forbidden")
    require(output_policy.get("private_transcripts_allowed") is False, "private transcripts must be forbidden")
    require(output_policy.get("hash_or_ref_only") is True, "hash/ref-only policy missing")

    packet_doc = read_text(PACKET_DOC)
    require(CONTRACT_ID in packet_doc, "human packet doc must name the contract")
    require("mock evidence is CI/offline fallback only" in packet_doc, "human packet doc must constrain mock evidence")
    require("byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture" in packet_doc, "human packet doc must require BYOC Postgres handoff")
    require("local_runtime_acceptance.py --live-openclaw --live-hermes" in packet_doc, "human packet doc must require real runtime acceptance")

    readiness = read_text(ROOT / "scripts" / "commercial_migration_readiness.py")
    require(CONTRACT_ID in readiness, "commercial readiness must require this packet")
    require("commercial_release_evidence_packet_smoke.py" in readiness, "commercial readiness must list packet smoke")
    closed_loop = read_text(ROOT / "docs" / "COMMERCIAL_MIGRATION_CLOSED_LOOP.md")
    require(CONTRACT_ID in closed_loop, "closed-loop doc must reference this packet")
    require("commercial_release_evidence_packet_smoke.py" in closed_loop, "closed-loop doc must list packet smoke")

    for relative, needles in REQUIRED_SOURCES.items():
        text = read_text(ROOT / relative)
        for needle in needles:
            require(needle in text, f"{relative} missing {needle!r}")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "gate_count": len(gates),
        "gate_5_commands": sorted(GATE5_REQUIRED_COMMANDS),
        "release_complete": False,
        "real_runtime_required": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
