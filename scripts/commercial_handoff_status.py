#!/usr/bin/env python3
"""CI-safe commercial handoff status aggregator.

The command only reads local release packet JSON files. A successful default
exit means the status surface is internally consistent, not that commercial
handoff is allowed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_handoff_status_v1"
STATUS_PATH = ROOT / "docs" / "COMMERCIAL_HANDOFF_STATUS.json"

SOURCE_SPECS = [
    {
        "path": "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json",
        "contract_id": "commercial_release_evidence_packet_v1",
        "expected_status": "gate_enforced_not_release_complete",
    },
    {
        "path": "docs/RELEASE_EVIDENCE_PACKET.json",
        "contract_id": "release_evidence_packet_v1",
        "expected_status": "delegates_to_commercial_release_evidence_packet",
    },
    {
        "path": "docs/RELEASE_FREEZE_PROTOCOL.json",
        "contract_id": "release_freeze_protocol_v1",
        "expected_status": "freeze_active_not_release_complete",
    },
    {
        "path": "docs/MERGE_READINESS_STATUS.json",
        "contract_id": "merge_readiness_status_v1",
        "expected_status": "blocked_release_evidence_required",
    },
    {
        "path": "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json",
        "contract_id": "commercial_evidence_receipts_v1",
        "expected_status": "partial_local_receipts_not_release_complete",
    },
    {
        "path": "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json",
        "contract_id": "commercial_current_evidence_status_v1",
        "expected_status": "current_evidence_required",
    },
    {
        "path": "docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json",
        "contract_id": "commercial_release_promotion_preflight_v1",
        "expected_status": "blocked_release_promotion_required",
    },
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    require(path.exists(), f"missing file: {relative_path}")
    return json.loads(path.read_text(encoding="utf-8"))


def append_unique(items: list[str], value: str | None) -> None:
    if value and value not in items:
        items.append(value)


def extend_unique(items: list[str], values: list[Any] | tuple[Any, ...] | set[Any]) -> None:
    for value in values:
        append_unique(items, str(value))


def source_payloads() -> list[dict[str, Any]]:
    sources = []
    for spec in SOURCE_SPECS:
        payload = read_json(spec["path"])
        require(payload.get("contract_id") == spec["contract_id"], f"{spec['path']} contract mismatch")
        require(payload.get("status") == spec["expected_status"], f"{spec['path']} status mismatch")
        sources.append({
            "path": spec["path"],
            "contract_id": payload.get("contract_id"),
            "status": payload.get("status"),
        })
    return sources


def build_payload() -> dict[str, Any]:
    static_status = read_json("docs/COMMERCIAL_HANDOFF_STATUS.json")
    require(static_status.get("contract_id") == CONTRACT_ID, "handoff status contract mismatch")

    commercial = read_json("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json")
    release = read_json("docs/RELEASE_EVIDENCE_PACKET.json")
    freeze = read_json("docs/RELEASE_FREEZE_PROTOCOL.json")
    merge = read_json("docs/MERGE_READINESS_STATUS.json")
    current_evidence = read_json("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json")

    sources = source_payloads()
    phase_gate_statuses = [
        {
            "id": str(gate.get("id")),
            "status": str(gate.get("status")),
        }
        for gate in commercial.get("phase_gate_evidence") or []
        if isinstance(gate, dict)
    ]
    blocking_gates = [
        gate["id"]
        for gate in phase_gate_statuses
        if gate["status"] != "ready"
    ]

    required_commands = [
        "python3 scripts/commercial_handoff_status.py",
        "python3 scripts/commercial_handoff_status_smoke.py",
        "python3 scripts/commercial_release_promotion_preflight.py",
        "python3 scripts/commercial_release_promotion_preflight_smoke.py",
        "python3 scripts/commercial_evidence_receipts.py",
        "python3 scripts/commercial_evidence_receipts_smoke.py",
        "python3 scripts/commercial_current_evidence_status.py",
        "python3 scripts/commercial_current_evidence_status_smoke.py",
    ]
    extend_unique(required_commands, commercial.get("handoff_required_commands") or [])
    append_unique(required_commands, release.get("verification_command"))
    append_unique(required_commands, release.get("commercial_verification_command"))
    append_unique(required_commands, release.get("freeze_verification_command"))
    append_unique(required_commands, release.get("merge_readiness_command"))
    append_unique(required_commands, release.get("handoff_status_command"))
    append_unique(required_commands, release.get("handoff_status_verification_command"))
    append_unique(required_commands, release.get("current_evidence_status_command"))
    append_unique(required_commands, release.get("current_evidence_status_verification_command"))
    extend_unique(required_commands, freeze.get("required_freeze_commands") or [])
    extend_unique(required_commands, merge.get("required_before_ready") or [])

    required_contracts = [CONTRACT_ID, "commercial_evidence_receipts_v1", "commercial_current_evidence_status_v1"]
    for spec in SOURCE_SPECS:
        append_unique(required_contracts, spec["contract_id"])
    extend_unique(required_contracts, release.get("gate_5_required_contracts") or [])
    extend_unique(required_contracts, freeze.get("required_contracts") or [])
    extend_unique(required_contracts, merge.get("required_contracts") or [])

    must_not_use = []
    extend_unique(must_not_use, static_status.get("must_not_use") or [])
    extend_unique(must_not_use, release.get("must_not_use") or [])
    extend_unique(must_not_use, freeze.get("must_not_use") or [])
    for gate in commercial.get("phase_gate_evidence") or []:
        if isinstance(gate, dict):
            extend_unique(must_not_use, gate.get("must_not_use") or [])

    release_complete = bool(release.get("release_complete")) and bool((commercial.get("scope") or {}).get("release_complete"))
    commercial_handoff_allowed = bool(freeze.get("commercial_handoff_allowed")) and bool(merge.get("commercial_handoff_allowed"))
    ready_to_merge = bool(merge.get("ready_to_merge"))

    payload = {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": "blocked_release_evidence_required",
        "ci_safe": True,
        "commercial_handoff_allowed": commercial_handoff_allowed,
        "release_complete": release_complete,
        "ready_to_merge": ready_to_merge,
        "sources": sources,
        "phase_gate_statuses": phase_gate_statuses,
        "blocking_gates": blocking_gates,
        "current_evidence_status": {
            "contract": current_evidence.get("contract_id"),
            "status": current_evidence.get("status"),
            "gates_requiring_current_evidence": (current_evidence.get("evidence_summary") or {}).get("gates_requiring_current_evidence") or [],
            "heavy_evidence_not_executed_by_default": (current_evidence.get("evidence_summary") or {}).get("heavy_evidence_not_executed_by_default"),
            "gates_with_local_receipts": (current_evidence.get("evidence_summary") or {}).get("gates_with_local_receipts") or [],
            "gates_with_release_grade_receipts": (current_evidence.get("evidence_summary") or {}).get("gates_with_release_grade_receipts") or [],
            "gates_missing_local_receipts": (current_evidence.get("evidence_summary") or {}).get("gates_missing_local_receipts") or [],
            "local_receipt_command_counts": (current_evidence.get("evidence_summary") or {}).get("local_receipt_command_counts") or {},
            "exact_head_ci_verified": (current_evidence.get("evidence_summary") or {}).get("exact_head_ci_verified"),
            "remote_sync_verified": (current_evidence.get("evidence_summary") or {}).get("remote_sync_verified"),
            "clean_worktree_verified": (current_evidence.get("evidence_summary") or {}).get("clean_worktree_verified"),
        },
        "explicit_blockers": list(merge.get("explicit_blockers") or []),
        "required_commands": required_commands,
        "required_contracts": required_contracts,
        "must_not_use": must_not_use,
    }

    require(static_status.get("status") == payload["status"], "static handoff status mismatch")
    require(static_status.get("commercial_handoff_allowed") is commercial_handoff_allowed, "static commercial handoff state mismatch")
    require(static_status.get("release_complete") is release_complete, "static release-complete state mismatch")
    require(static_status.get("ready_to_merge") is ready_to_merge, "static ready-to-merge state mismatch")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Print CI-safe commercial handoff status.")
    parser.add_argument("--require-handoff-ready", action="store_true", help="Fail unless commercial handoff is explicitly allowed.")
    args = parser.parse_args()

    payload = build_payload()
    if args.require_handoff_ready:
        require(payload["commercial_handoff_allowed"] is True, "commercial handoff is not allowed")
        require(payload["release_complete"] is True, "release is not complete")
        require(payload["ready_to_merge"] is True, "merge status is not ready")
        require(not payload["blocking_gates"], f"blocking gates remain: {payload['blocking_gates']}")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
