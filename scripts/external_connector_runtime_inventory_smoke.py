#!/usr/bin/env python3
"""Guard the high-risk external connector/runtime prepared-action inventory.

This is a read-only meta-gate: it does not call providers. It verifies that
every known high-risk external connector/runtime write path has source markers,
a dedicated prepared-action smoke, checklist evidence, and release/CI backing
for this inventory gate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_SCRIPT = ROOT / "scripts" / "release_evidence_packet_smoke.py"
RELEASE_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"
CHECKLIST = ROOT / "docs" / "V1_5_MERGE_READINESS_CHECKLIST.md"
OBJECTIVE = ROOT / "docs" / "V1_5_AGENT_GATEWAY_HARDENING_OBJECTIVE.md"

SOURCE_FILES = {
    "server.py": ROOT / "server.py",
    "agentops_mis_core/approval_wall.py": ROOT / "agentops_mis_core" / "approval_wall.py",
    "agentops_mis_cli/worker.py": ROOT / "agentops_mis_cli" / "worker.py",
}

INVENTORY: list[dict[str, Any]] = [
    {
        "id": "approval_wall_exact_resume",
        "description": "Approval Wall creates, approves, resumes and consumes exact prepared actions.",
        "guard_script": "scripts/prepared_action_approval_wall_smoke.py",
        "source_markers": {
            "server.py": [
                "agent_gateway_prepare_action",
                "prepared_action_already_consumed",
                "approval_wall.prepared_action_resumed",
            ],
        },
    },
    {
        "id": "agent_gateway_high_risk_tool_call",
        "description": "Agent Gateway blocks high-risk external side-effect tool calls unless they prepare first.",
        "guard_script": "scripts/high_risk_toolcall_prepared_action_gate_smoke.py",
        "source_markers": {
            "server.py": [
                "tool_call.prepared_action_required",
                "build_high_risk_toolcall_prepared_action_required_response",
                "openai.file_search.upload",
            ],
            "agentops_mis_core/approval_wall.py": [
                "high_risk_prepared_action_required",
            ],
        },
    },
    {
        "id": "agent_gateway_generic_external_side_effect",
        "description": "Generic external side-effect detection escalates risk and requires prepared actions.",
        "guard_script": "scripts/generic_external_side_effect_gate_smoke.py",
        "source_markers": {
            "server.py": [
                "tool_call_has_external_side_effect_intent",
                "EXTERNAL_SIDE_EFFECT_KEYWORDS",
                "EXTERNAL_SIDE_EFFECT_SCHEMES",
            ],
        },
    },
    {
        "id": "customer_worker_external_write",
        "description": "Customer task handoff to Hermes/OpenClaw pauses when task text implies external writes.",
        "guard_script": "scripts/customer_worker_external_write_gate_smoke.py",
        "source_markers": {
            "server.py": [
                "customer_worker_external_write_intent",
                "workflow.customer_worker_task.external_write_prepared_action_required",
                "external_write_prepared_action_required",
            ],
        },
    },
    {
        "id": "direct_worker_external_write",
        "description": "Direct worker/local dispatch external-write intent pauses before opaque runtime execution.",
        "guard_script": "scripts/worker_external_write_preflight_gate_smoke.py",
        "source_markers": {
            "agentops_mis_cli/worker.py": [
                "worker_external_write_intent",
                "agent_worker.external_write_prepared_action_required",
                "external_write_prepared_action_required",
            ],
        },
    },
    {
        "id": "dify_live_upload",
        "description": "Dify live knowledge upload requires exact prepared-action approval before provider write.",
        "guard_script": "scripts/dify_upload_prepared_action_gate_smoke.py",
        "source_markers": {
            "server.py": [
                "dify.knowledge.upload",
                "dify.upload_text.prepared_action_required",
                "dify_prepared_action_required",
            ],
        },
    },
    {
        "id": "notion_live_export",
        "description": "Notion live report export requires exact prepared-action approval before provider write.",
        "guard_script": "scripts/notion_export_prepared_action_gate_smoke.py",
        "source_markers": {
            "server.py": [
                "notion.report.export",
                "notion.export.prepared_action_required",
                "notion_prepared_action_required",
            ],
        },
    },
    {
        "id": "fixed_runtime_probes",
        "description": "OpenClaw, Hermes and Agnes fixed live probes prepare before runtime execution.",
        "guard_script": "scripts/runtime_probe_prepared_action_gate_smoke.py",
        "source_markers": {
            "server.py": [
                "runtime.fixed_probe",
                "runtime.fixed_probe.prepared_action_required",
                "runtime_probe_prepared_action_required",
            ],
        },
    },
    {
        "id": "runtime_connector_trust_gate",
        "description": "Runtime connector trust policy can block live Hermes/OpenClaw execution before adapter invocation.",
        "guard_script": "scripts/runtime_connector_trust_smoke.py",
        "source_markers": {
            "server.py": [
                "runtime_connector_trust",
                "runtime_connector_trust_blocked",
                "workflow.customer_worker_task.trust_blocked",
            ],
        },
    },
]

RISK_MARKERS = {
    "dify.knowledge.upload",
    "notion.report.export",
    "runtime.fixed_probe",
    "openai.file_search.upload",
    "tool_call.prepared_action_required",
    "high_risk_prepared_action_required",
    "external_write_prepared_action_required",
    "runtime_probe_prepared_action_required",
    "dify_prepared_action_required",
    "notion_prepared_action_required",
    "runtime_connector_trust_blocked",
    "agent_worker.external_write_prepared_action_required",
    "workflow.customer_worker_task.external_write_prepared_action_required",
}

THIS_COMMAND = "python3 scripts/external_connector_runtime_inventory_smoke.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def marker_owners() -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for entry in INVENTORY:
        for markers in entry["source_markers"].values():
            for marker in markers:
                owners.setdefault(marker, []).append(entry["id"])
    return owners


def main() -> int:
    failures: list[str] = []
    source_texts = {name: read(path) for name, path in SOURCE_FILES.items()}
    ci_text = read(CI)
    release_script_text = read(RELEASE_SCRIPT)
    release_doc_text = read(RELEASE_DOC)
    checklist_text = read(CHECKLIST)
    objective_text = read(OBJECTIVE)
    owners = marker_owners()

    for path in [CI, RELEASE_SCRIPT, RELEASE_DOC, CHECKLIST, OBJECTIVE, *SOURCE_FILES.values()]:
        require(path.exists(), f"missing required file: {path.relative_to(ROOT)}", failures)

    covered_paths: list[str] = []
    for entry in INVENTORY:
        guard_script = entry["guard_script"]
        guard_path = ROOT / guard_script
        require(guard_path.exists(), f"{entry['id']} missing guard script: {guard_script}", failures)
        require(guard_script in checklist_text, f"{entry['id']} guard missing from merge checklist: {guard_script}", failures)
        require(guard_script in objective_text, f"{entry['id']} guard missing from hardening objective: {guard_script}", failures)

        for source_name, markers in entry["source_markers"].items():
            source = source_texts.get(source_name, "")
            for marker in markers:
                require(marker in source, f"{entry['id']} marker missing from {source_name}: {marker}", failures)
        covered_paths.append(entry["id"])

    require(THIS_COMMAND in ci_text, "inventory gate is not wired into CI", failures)
    require(THIS_COMMAND in release_script_text, "inventory gate is not listed in release evidence command manifest", failures)
    require(THIS_COMMAND in release_doc_text, "inventory gate is not listed in release evidence documentation", failures)
    require(THIS_COMMAND in checklist_text, "inventory gate is not referenced in merge readiness checklist", failures)
    require(THIS_COMMAND in objective_text, "inventory gate is not referenced in hardening objective", failures)
    require(
        "- [x] All high-risk external connector/runtime tool paths use prepared actions" in checklist_text,
        "high-risk connector/runtime inventory checklist item is not closed",
        failures,
    )

    unaccounted_markers: list[dict[str, str]] = []
    for marker in sorted(RISK_MARKERS):
        marker_found = any(marker in text for text in source_texts.values())
        if marker_found and marker not in owners:
            unaccounted_markers.append({"marker": marker, "reason": "marker has no inventory owner"})
    require(not unaccounted_markers, f"unaccounted high-risk markers: {unaccounted_markers}", failures)

    output = {
        "ok": not failures,
        "operation": "external_connector_runtime_inventory_smoke",
        "inventory_count": len(INVENTORY),
        "covered_paths": covered_paths,
        "guard_scripts": [entry["guard_script"] for entry in INVENTORY],
        "ci_backed": THIS_COMMAND in ci_text,
        "release_packet_backed": THIS_COMMAND in release_script_text and THIS_COMMAND in release_doc_text,
        "unaccounted_markers": unaccounted_markers,
        "safety": {
            "read_only": True,
            "provider_calls_performed": False,
            "ledger_mutated": False,
            "raw_payload_omitted": True,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
