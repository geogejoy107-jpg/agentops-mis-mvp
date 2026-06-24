"""Read-only Research Lab work packet projection for local agents.

This module intentionally performs only filesystem reads against the checked-in
incubator files. It does not execute the Research Lab CLI, open SSH
connections, inspect credentials, mutate the MIS ledger, or call the network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


METHOD = "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD"
SCHEMA_VERSION = "research_lab_agent_work_packet_v1"
ADAPTERS = {"mock", "hermes", "openclaw", "codex"}

DOC_PATHS = [
    "README.md",
    "docs/AGENT_PLAN.md",
    "docs/EXPERIMENT_PROTOCOL.md",
    "docs/SSH_EXECUTOR.md",
    "docs/SOURCE_COMPLETENESS.md",
    "docs/ASYNC_EXECUTION.md",
    "docs/OPEN_SOURCE_ABSORPTION.md",
]

EXAMPLE_PATHS = [
    "examples/confirmatory_experiment.json",
    "examples/ssh_experiment.json",
    "examples/servers.example.json",
]


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _safe_adapter(adapter: str | None) -> str:
    normalized = str(adapter or "hermes").strip().lower()
    return normalized if normalized in ADAPTERS else "hermes"


def _file_metadata(path: Path, root: Path) -> dict:
    rel = path.relative_to(root).as_posix()
    if not path.exists() or not path.is_file():
        return {
            "path": rel,
            "exists": False,
            "size_bytes": 0,
            "sha256": "",
            "raw_content_omitted": True,
            "token_omitted": True,
        }
    data = path.read_bytes()
    return {
        "path": rel,
        "exists": True,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "raw_content_omitted": True,
        "token_omitted": True,
    }


def _read_json(path: Path) -> dict:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _matrix_trial_count(matrix: dict) -> int:
    if not isinstance(matrix, dict) or not matrix:
        return 1
    total = 1
    for values in matrix.values():
        if isinstance(values, list):
            total *= max(len(values), 1)
        else:
            total *= 1
    return total


def _spec_summary(path: Path, lab_root: Path) -> dict:
    meta = _file_metadata(path, lab_root)
    payload = _read_json(path)
    executor_config = payload.get("executor_config") if isinstance(payload.get("executor_config"), dict) else {}
    integrity = payload.get("integrity") if isinstance(payload.get("integrity"), dict) else {}
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    protocol = payload.get("protocol") if isinstance(payload.get("protocol"), dict) else {}
    command = payload.get("command") if isinstance(payload.get("command"), list) else []
    command_hash = hashlib.sha256(json.dumps(command, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest() if command else ""
    protocol_hash = hashlib.sha256(json.dumps(protocol, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest() if protocol else ""
    provenance_hash = hashlib.sha256(json.dumps(provenance, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest() if provenance else ""
    return {
        **meta,
        "kind": "experiment_spec",
        "name": payload.get("name") or "",
        "stage": payload.get("stage") or "",
        "executor": payload.get("executor") or "",
        "profile": executor_config.get("profile") or "",
        "trial_count": _matrix_trial_count(payload.get("matrix") if isinstance(payload.get("matrix"), dict) else {}),
        "max_concurrency": payload.get("max_concurrency"),
        "timeout_seconds": payload.get("timeout_seconds"),
        "minimum_completed_trials": integrity.get("minimum_completed_trials"),
        "minimum_distinct_seeds": integrity.get("minimum_distinct_seeds"),
        "strict_actuals": integrity.get("strict_actuals"),
        "require_provenance": integrity.get("require_provenance"),
        "command_hash": command_hash,
        "protocol_hash": protocol_hash,
        "provenance_hash": provenance_hash,
        "raw_command_omitted": True,
        "raw_protocol_omitted": True,
        "raw_provenance_omitted": True,
        "token_omitted": True,
    }


def _server_registry_summary(path: Path, lab_root: Path, requested_profile: str = "") -> dict:
    meta = _file_metadata(path, lab_root)
    payload = _read_json(path)
    profiles = payload.get("profiles") if isinstance(payload.get("profiles"), list) else []
    public_profiles = []
    for item in profiles:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if requested_profile and name != requested_profile:
            continue
        public_profiles.append({
            "name": name,
            "host_ref": hashlib.sha256(str(item.get("host") or "").encode("utf-8")).hexdigest()[:16] if item.get("host") else "",
            "port": item.get("port"),
            "user_ref": hashlib.sha256(str(item.get("user") or "").encode("utf-8")).hexdigest()[:16] if item.get("user") else "",
            "remote_root_ref": hashlib.sha256(str(item.get("remote_root") or "").encode("utf-8")).hexdigest()[:16] if item.get("remote_root") else "",
            "python": item.get("python") or "",
            "host_key_policy": item.get("host_key_policy") or "",
            "max_parallel_jobs": item.get("max_parallel_jobs"),
            "max_stage_bytes": item.get("max_stage_bytes"),
            "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
            "identity_file_omitted": True,
            "known_hosts_file_omitted": True,
            "raw_host_omitted": True,
            "raw_user_omitted": True,
            "token_omitted": True,
        })
    return {
        **meta,
        "kind": "server_registry",
        "profile_count": len(profiles),
        "selected_profile_count": len(public_profiles),
        "profiles": public_profiles,
        "raw_credentials_omitted": True,
        "raw_hosts_omitted": True,
        "token_omitted": True,
    }


def _status_from_files(items: list[dict]) -> str:
    missing = [item for item in items if not item.get("exists")]
    if missing:
        return "blocked"
    return "ready"


def build_research_lab_packet(repo_root: Path, *, adapter: str = "hermes", limit: int = 8, profile: str = "") -> dict:
    repo_root = Path(repo_root).resolve()
    adapter = _safe_adapter(adapter)
    limit = _bounded_int(limit, 8, 1, 20)
    requested_profile = str(profile or "").strip()
    lab_root = repo_root / "incubator" / "research-lab"
    docs = [_file_metadata(lab_root / path, lab_root) for path in DOC_PATHS[:limit]]
    examples = []
    for rel in EXAMPLE_PATHS:
        path = lab_root / rel
        if rel.endswith("servers.example.json"):
            examples.append(_server_registry_summary(path, lab_root, requested_profile))
        else:
            examples.append(_spec_summary(path, lab_root))
    all_files = docs + examples + [_file_metadata(lab_root / "pyproject.toml", lab_root)]
    status = _status_from_files(all_files)
    packet_hash = hashlib.sha256(
        json.dumps(
            {
                "adapter": adapter,
                "docs": [{k: item.get(k) for k in ("path", "sha256", "exists")} for item in docs],
                "examples": [{k: item.get(k) for k in ("path", "sha256", "exists")} for item in examples],
                "schema_version": SCHEMA_VERSION,
            },
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    base_cmd = "cd incubator/research-lab && python3 -m research_lab"
    phase_commands = {
        "READ": "agentops operator research-lab-packet --adapter {adapter} --limit {limit}".format(adapter=adapter, limit=limit),
        "PLAN": "agentops agent-plan create --agent-id <agent_id> --task-id <task_id> --referenced-specs PROJECT_SPEC.md,incubator/research-lab/docs/AGENT_PLAN.md --referenced-bases incubator/research-lab --execution-steps READ,PLAN,RETRIEVE,COMPARE,EXECUTE,VERIFY,RECORD",
        "RETRIEVE": "agentops knowledge search --query 'Research Lab Method Block SSH executor validation evidence' --limit 8",
        "COMPARE": f"{base_cmd} inventory",
        "EXECUTE": f"{base_cmd} validate-spec --spec examples/confirmatory_experiment.json",
        "VERIFY": f"{base_cmd} validate-spec --spec examples/ssh_experiment.json --servers examples/servers.example.json",
        "RECORD": "agentops plan-evidence create --agent-plan-id <agent_plan_id> --evidence-kind research_lab_packet --summary 'Research Lab packet consumed; validation evidence recorded without raw output or credentials'",
    }
    command_lanes = [
        {
            "phase": "READ",
            "command": phase_commands["READ"],
            "purpose": "Load the copy-only Research Lab packet from MIS.",
            "server_executes_shell": False,
        },
        {
            "phase": "COMPARE",
            "command": phase_commands["COMPARE"],
            "purpose": "Inspect incubator inventory locally; MIS backend does not run this command.",
            "server_executes_shell": False,
        },
        {
            "phase": "EXECUTE",
            "command": phase_commands["EXECUTE"],
            "purpose": "Validate the local confirmatory example spec.",
            "server_executes_shell": False,
        },
        {
            "phase": "VERIFY",
            "command": phase_commands["VERIFY"],
            "purpose": "Validate the SSH example against redacted server-profile metadata.",
            "server_executes_shell": False,
        },
        {
            "phase": "VERIFY",
            "command": f"{base_cmd} server-list --servers examples/servers.example.json",
            "purpose": "List safe server profile metadata; does not connect to SSH.",
            "server_executes_shell": False,
        },
        {
            "phase": "VERIFY",
            "command": f"{base_cmd} server-probe --servers examples/servers.example.json --profile {requested_profile or 'lab-gpu-01'}",
            "purpose": "Prepared local probe command; real network/SSH probing is operator-run and approval-bound.",
            "server_executes_shell": False,
            "approval_required_for_real_network_probe": True,
        },
        {
            "phase": "VERIFY",
            "command": "python3 scripts/operator_research_lab_packet_smoke.py",
            "purpose": "Verify API/CLI packet safety and reproducible local validation.",
            "server_executes_shell": False,
        },
    ]
    agent_plan_draft = {
        "task_understanding": "Use AgentOps MIS to coordinate a Research Lab task for Hermes/OpenClaw/Codex with a read-only packet, local spec validation, explicit approval boundaries for real SSH/GPU execution, and ledger evidence after verification.",
        "referenced_specs": [
            "PROJECT_SPEC.md",
            "AGENT_WORKFLOW.md",
            "BASE_INDEX.md",
            "incubator/research-lab/README.md",
            "incubator/research-lab/docs/AGENT_PLAN.md",
            "incubator/research-lab/docs/EXPERIMENT_PROTOCOL.md",
            "incubator/research-lab/docs/SSH_EXECUTOR.md",
        ],
        "referenced_memories": [
            "knowledge/shared/architecture_rules.md",
            "knowledge/shared/security_rules.md",
            "knowledge/shared/runtime_rules.md",
        ],
        "referenced_bases": [
            "incubator/research-lab",
            "docs/research/OPEN_SOURCE_BASE_INDEX_V1_1.md",
            "agentops_mis.db",
        ],
        "proposed_files_to_change": ["<declare_before_execution>"],
        "risk_level": "medium",
        "approval_required": True,
        "approval_reason": "Real SSH/GPU/network execution, credential use, remote writes, or external publication require human-approved prepared actions. Local spec validation is read-only.",
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "verification_plan": "Run Research Lab validate-spec for local and SSH examples, run the packet smoke, then record plan evidence without raw prompts, responses, credentials, or full transcripts.",
        "rollback_plan": "Stop before external writes or SSH execution; revert only scoped file changes and mark any failed evidence as remediation work.",
    }
    return {
        "provider": "agentops-operator",
        "operation": "operator_research_lab_packet",
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "method": METHOD,
        "adapter": adapter,
        "packet_hash": packet_hash,
        "research_lab": {
            "root": "incubator/research-lab",
            "exists": lab_root.exists() and lab_root.is_dir(),
            "docs": docs,
            "examples": examples,
            "profile_filter": requested_profile,
            "raw_content_omitted": True,
            "token_omitted": True,
        },
        "agent_plan_draft": agent_plan_draft,
        "phase_commands": phase_commands,
        "command_lanes": command_lanes,
        "approval_boundary": {
            "local_spec_validation_requires_approval": False,
            "server_list_requires_approval": False,
            "real_ssh_execution_requires_approval": True,
            "network_probe_requires_approval": True,
            "credential_use_requires_approval": True,
            "external_publication_requires_approval": True,
        },
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "ssh_command_executed": False,
            "network_probe_performed": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "raw_content_omitted": True,
            "credentials_omitted": True,
            "token_omitted": True,
        },
        "next_actions": [
            phase_commands["READ"],
            phase_commands["PLAN"],
            phase_commands["EXECUTE"],
            phase_commands["VERIFY"],
            "python3 scripts/operator_research_lab_packet_smoke.py",
        ],
        "token_omitted": True,
        "live_execution_performed": False,
    }
