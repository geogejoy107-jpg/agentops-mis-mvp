#!/usr/bin/env python3
"""CI-safe current evidence coverage for commercial handoff gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_current_evidence_status_v1"
STATUS_PATH = ROOT / "docs" / "COMMERCIAL_CURRENT_EVIDENCE_STATUS.json"

SOURCE_SPECS = [
    ("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "commercial_release_evidence_packet_v1", "gate_enforced_not_release_complete"),
    ("docs/RELEASE_EVIDENCE_PACKET.json", "release_evidence_packet_v1", "delegates_to_commercial_release_evidence_packet"),
    ("docs/RELEASE_FREEZE_PROTOCOL.json", "release_freeze_protocol_v1", "freeze_active_not_release_complete"),
    ("docs/MERGE_READINESS_STATUS.json", "merge_readiness_status_v1", "blocked_release_evidence_required"),
]

GATE_EVIDENCE_CLASSES = {
    "gate_0_isolated_commercial_track": ["static", "git"],
    "gate_1_product_packaging_and_entitlement": ["entitlement", "fail_closed", "isolated_fixture"],
    "gate_2_production_safety_baseline": ["production_security", "workspace_isolation", "rbac", "session_governance", "isolated_fixture"],
    "gate_3_storage_boundary_before_postgres": ["storage_boundary", "postgres", "http_parity", "cli_parity", "write_parity"],
    "gate_4_ui_api_parity_before_nextjs": ["ui_api_parity", "browser_snapshot", "vite_build", "nextjs_build"],
    "gate_5_byoc_enterprise_deployment": ["audit_retention", "enterprise_byoc", "postgres", "browser_snapshot", "real_runtime"],
}


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


def command_classes(gate_id: str, commands: list[str]) -> list[str]:
    if gate_id in GATE_EVIDENCE_CLASSES:
        return list(GATE_EVIDENCE_CLASSES[gate_id])
    classes: list[str] = []
    joined = "\n".join(commands)
    if "entitlement" in joined or "enrollment" in joined:
        append_unique(classes, "entitlement")
    if "production" in joined or "workspace" in joined or "scope_matrix" in joined:
        append_unique(classes, "production_security")
    if "storage_" in joined or "postgres" in joined:
        append_unique(classes, "postgres")
    if "playwright" in joined or "nextjs" in joined or "vite" in joined or "npm run build" in joined:
        append_unique(classes, "browser_or_ui")
    if "HERMES_ALLOW_REAL_RUN=true" in joined or "--live-openclaw" in joined or "--live-hermes" in joined:
        append_unique(classes, "real_runtime")
    if "git " in joined or "git diff" in joined:
        append_unique(classes, "git")
    if not classes:
        append_unique(classes, "static")
    return classes


def source_payloads() -> list[dict[str, Any]]:
    sources = []
    for path, contract_id, expected_status in SOURCE_SPECS:
        payload = read_json(path)
        require(payload.get("contract_id") == contract_id, f"{path} contract mismatch")
        require(payload.get("status") == expected_status, f"{path} status mismatch")
        sources.append({"path": path, "contract_id": contract_id, "status": expected_status})
    return sources


def build_payload() -> dict[str, Any]:
    static_status = read_json("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json")
    require(static_status.get("contract_id") == CONTRACT_ID, "current evidence status contract mismatch")

    commercial = read_json("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json")
    release = read_json("docs/RELEASE_EVIDENCE_PACKET.json")
    freeze = read_json("docs/RELEASE_FREEZE_PROTOCOL.json")
    merge = read_json("docs/MERGE_READINESS_STATUS.json")

    source_packets = source_payloads()
    gates: list[dict[str, Any]] = []
    for gate in commercial.get("phase_gate_evidence") or []:
        if not isinstance(gate, dict):
            continue
        gate_id = str(gate.get("id"))
        packet_status = str(gate.get("status"))
        commands = [str(command) for command in gate.get("required_commands") or []]
        evidence_current = packet_status == "ready"
        evidence_state = "static_contract_current" if evidence_current else "current_evidence_required"
        item = {
            "id": gate_id,
            "packet_status": packet_status,
            "evidence_current": evidence_current,
            "evidence_state": evidence_state,
            "required_commands": commands,
            "required_contracts": [str(contract) for contract in gate.get("required_contracts") or []],
            "evidence_classes": command_classes(gate_id, commands),
            "postgres_required": any("postgres" in command for command in commands),
            "browser_required": any("playwright" in command or "npm run build" in command for command in commands),
            "real_runtime_required": any("--live-openclaw" in command or "--live-hermes" in command for command in commands),
            "must_not_use": [str(item) for item in gate.get("must_not_use") or []],
        }
        gates.append(item)

    gates_requiring_current_evidence = [gate["id"] for gate in gates if not gate["evidence_current"]]
    required_commands = [
        "python3 scripts/commercial_current_evidence_status.py",
        "python3 scripts/commercial_current_evidence_status_smoke.py",
    ]
    extend_unique(required_commands, commercial.get("handoff_required_commands") or [])
    append_unique(required_commands, release.get("current_evidence_status_command"))
    append_unique(required_commands, release.get("current_evidence_status_verification_command"))
    extend_unique(required_commands, freeze.get("required_freeze_commands") or [])
    extend_unique(required_commands, merge.get("required_before_ready") or [])

    required_contracts = [CONTRACT_ID]
    for _, contract_id, _ in SOURCE_SPECS:
        append_unique(required_contracts, contract_id)
    extend_unique(required_contracts, release.get("gate_5_required_contracts") or [])
    extend_unique(required_contracts, freeze.get("required_contracts") or [])
    extend_unique(required_contracts, merge.get("required_contracts") or [])

    must_not_use = []
    extend_unique(must_not_use, static_status.get("must_not_use") or [])
    extend_unique(must_not_use, release.get("must_not_use") or [])
    extend_unique(must_not_use, freeze.get("must_not_use") or [])
    for gate in gates:
        extend_unique(must_not_use, gate.get("must_not_use") or [])

    release_complete = bool(release.get("release_complete")) and bool((commercial.get("scope") or {}).get("release_complete"))
    commercial_handoff_allowed = bool(freeze.get("commercial_handoff_allowed")) and bool(merge.get("commercial_handoff_allowed"))
    ready_to_merge = bool(merge.get("ready_to_merge"))

    summary = {
        "gate_count": len(gates),
        "ready_gate_count": len([gate for gate in gates if gate["evidence_current"]]),
        "gates_requiring_current_evidence": gates_requiring_current_evidence,
        "postgres_required": any(gate["postgres_required"] for gate in gates),
        "browser_required": any(gate["browser_required"] for gate in gates),
        "real_runtime_required": any(gate["real_runtime_required"] for gate in gates),
        "heavy_evidence_not_executed_by_default": True,
    }

    payload = {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": "current_evidence_required",
        "ci_safe": True,
        "release_complete": release_complete,
        "commercial_handoff_allowed": commercial_handoff_allowed,
        "ready_to_merge": ready_to_merge,
        "source_packets": source_packets,
        "evidence_policy": static_status.get("evidence_policy") or {},
        "evidence_summary": summary,
        "phase_gate_evidence_statuses": gates,
        "explicit_blockers": list(merge.get("explicit_blockers") or []),
        "required_commands": required_commands,
        "required_contracts": required_contracts,
        "must_not_use": must_not_use,
    }

    require(static_status.get("status") == payload["status"], "static current evidence status mismatch")
    require(static_status.get("release_complete") is release_complete, "static release-complete state mismatch")
    require(static_status.get("commercial_handoff_allowed") is commercial_handoff_allowed, "static handoff state mismatch")
    require(static_status.get("ready_to_merge") is ready_to_merge, "static merge state mismatch")
    require((static_status.get("evidence_summary") or {}).get("gates_requiring_current_evidence") == gates_requiring_current_evidence, "static evidence gap list mismatch")
    static_gates = {
        str(gate.get("id")): gate
        for gate in static_status.get("phase_gate_evidence_statuses") or []
        if isinstance(gate, dict)
    }
    require(set(static_gates) == {gate["id"] for gate in gates}, "static/runtime gate id mismatch")
    list_keys = {"required_commands", "evidence_classes", "must_not_use"}
    for gate in gates:
        static_gate = static_gates[gate["id"]]
        for key in ["packet_status", "evidence_current", "evidence_state", "required_commands", "evidence_classes", "must_not_use"]:
            static_value = static_gate.get(key, [] if key in list_keys else None)
            runtime_value = gate.get(key, [] if key in list_keys else None)
            require(static_value == runtime_value, f"static/runtime mismatch for {gate['id']} {key}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Print CI-safe commercial current evidence status.")
    parser.add_argument("--require-current-evidence", action="store_true", help="Fail unless every commercial phase gate has current evidence.")
    args = parser.parse_args()

    payload = build_payload()
    if args.require_current_evidence:
        gaps = payload["evidence_summary"]["gates_requiring_current_evidence"]
        require(not gaps, f"current evidence gaps remain: {gaps}")
        require(payload["release_complete"] is True, "release is not complete")
        require(payload["commercial_handoff_allowed"] is True, "commercial handoff is not allowed")
        require(payload["ready_to_merge"] is True, "merge status is not ready")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
