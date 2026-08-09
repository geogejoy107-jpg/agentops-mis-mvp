"""Dependency-free, fail-closed Template Platform v1 contract validation.

The module owns shared shape and namespace rules only. Templates may declare
domain objects, workflows, agents and tools, but they must reference MIS Core
authority objects rather than creating a second task/run/approval/audit ledger.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Callable

MANIFEST_SCHEMA_VERSION = "template-manifest/v1"
SHARED_API_VERSION = "template-platform-api/v1"
EVENT_SCHEMA_VERSION = "template-event/v1"
RUNTIME_CONTRACT_VERSION = "openjiuwen-runtime/v1"
MIGRATION_CONTRACT_VERSION = "template-migration/v1"
PROFILE_CONTRACT_VERSION = "product-profile/v1"

CORE_AUTHORITY_OBJECTS = frozenset(
    {
        "Workspace",
        "Project",
        "Agent",
        "Task",
        "Plan",
        "Run",
        "ToolCall",
        "PreparedAction",
        "Approval",
        "Artifact",
        "Evaluation",
        "MemoryReview",
        "Audit",
        "Evidence",
        "ProjectDelta",
        "Identity",
        "Permission",
    }
)
CORE_AUTHORITY_IDS = frozenset(
    {
        "mis_core.workspace",
        "mis_core.project",
        "mis_core.agent",
        "mis_core.task",
        "mis_core.plan",
        "mis_core.run",
        "mis_core.tool_call",
        "mis_core.prepared_action",
        "mis_core.approval",
        "mis_core.artifact",
        "mis_core.evaluation",
        "mis_core.memory_review",
        "mis_core.audit",
        "mis_core.evidence",
        "mis_core.project_delta",
        "mis_core.identity",
        "mis_core.permission",
    }
)
CORE_AUTHORITY_ID_BY_NORMALIZED_NAME = {
    "workspace": "mis_core.workspace",
    "project": "mis_core.project",
    "agent": "mis_core.agent",
    "task": "mis_core.task",
    "plan": "mis_core.plan",
    "run": "mis_core.run",
    "toolcall": "mis_core.tool_call",
    "preparedaction": "mis_core.prepared_action",
    "approval": "mis_core.approval",
    "artifact": "mis_core.artifact",
    "evaluation": "mis_core.evaluation",
    "memoryreview": "mis_core.memory_review",
    "audit": "mis_core.audit",
    "evidence": "mis_core.evidence",
    "projectdelta": "mis_core.project_delta",
    "identity": "mis_core.identity",
    "permission": "mis_core.permission",
}

TEMPLATE_LIFECYCLE_TRANSITIONS: dict[str, frozenset[str]] = {
    "discovered": frozenset({"validated", "archived"}),
    "validated": frozenset({"install_preview", "archived"}),
    "install_preview": frozenset({"pending_approval"}),
    "pending_approval": frozenset(
        {"installing", "install_rejected", "install_approval_expired"}
    ),
    "install_rejected": frozenset({"install_preview", "archived"}),
    "install_approval_expired": frozenset({"install_preview", "archived"}),
    "installing": frozenset({"install_readback", "install_failed"}),
    "install_readback": frozenset({"install_receipt_pending", "install_failed"}),
    "install_receipt_pending": frozenset({"installed", "install_failed"}),
    "install_failed": frozenset({"install_preview", "archived"}),
    "installed": frozenset({"activation_preview", "uninstall_preview"}),
    "activation_preview": frozenset({"pending_activation_approval"}),
    "pending_activation_approval": frozenset(
        {"activating", "activation_rejected", "activation_approval_expired"}
    ),
    "activation_rejected": frozenset({"installed", "disabled"}),
    "activation_approval_expired": frozenset({"activation_preview", "installed", "disabled"}),
    "activating": frozenset({"activation_readback", "activation_failed"}),
    "activation_readback": frozenset(
        {"activation_receipt_pending", "activation_failed"}
    ),
    "activation_receipt_pending": frozenset({"active", "activation_failed"}),
    "activation_failed": frozenset({"activation_preview", "uninstall_preview"}),
    "active": frozenset({"disable_preview", "upgrade_preview", "uninstall_preview"}),
    "disable_preview": frozenset({"pending_disable_approval"}),
    "pending_disable_approval": frozenset(
        {"disabling", "disable_rejected", "disable_approval_expired"}
    ),
    "disable_rejected": frozenset({"active"}),
    "disable_approval_expired": frozenset({"disable_preview", "active"}),
    "disabling": frozenset({"disable_readback", "disable_failed"}),
    "disable_readback": frozenset({"disable_receipt_pending", "disable_failed"}),
    "disable_receipt_pending": frozenset({"disabled", "disable_failed"}),
    "disable_failed": frozenset({"disable_preview", "active"}),
    "disabled": frozenset({"activation_preview", "upgrade_preview", "uninstall_preview"}),
    "upgrade_preview": frozenset({"pending_upgrade_approval"}),
    "pending_upgrade_approval": frozenset(
        {"migrating", "upgrade_rejected", "upgrade_approval_expired"}
    ),
    "upgrade_rejected": frozenset({"active", "disabled"}),
    "upgrade_approval_expired": frozenset({"active", "disabled"}),
    "migrating": frozenset({"migration_readback", "upgrade_failed"}),
    "migration_readback": frozenset({"migration_receipt_pending", "upgrade_failed"}),
    "migration_receipt_pending": frozenset({"upgrading", "upgrade_failed"}),
    "upgrading": frozenset({"upgrade_readback", "upgrade_failed"}),
    "upgrade_readback": frozenset({"upgrade_receipt_pending", "upgrade_failed"}),
    "upgrade_receipt_pending": frozenset({"active", "disabled", "upgrade_failed"}),
    "upgrade_failed": frozenset({"rollback_preview"}),
    "rollback_preview": frozenset({"pending_rollback_approval"}),
    "pending_rollback_approval": frozenset(
        {"rolling_back", "rollback_rejected", "rollback_approval_expired"}
    ),
    "rollback_rejected": frozenset({"disabled"}),
    "rollback_approval_expired": frozenset({"rollback_preview", "disabled"}),
    "rolling_back": frozenset({"rollback_readback", "rollback_failed"}),
    "rollback_readback": frozenset({"rollback_receipt_pending", "rollback_failed"}),
    "rollback_receipt_pending": frozenset({"active", "disabled", "rollback_failed"}),
    "rollback_failed": frozenset({"rollback_preview", "disabled"}),
    "uninstall_preview": frozenset({"pending_uninstall_approval"}),
    "pending_uninstall_approval": frozenset(
        {"uninstalling", "uninstall_rejected", "uninstall_approval_expired"}
    ),
    "uninstall_rejected": frozenset({"active", "disabled"}),
    "uninstall_approval_expired": frozenset({"active", "disabled"}),
    "uninstalling": frozenset({"uninstall_readback", "uninstall_failed"}),
    "uninstall_readback": frozenset(
        {"uninstall_receipt_pending", "uninstall_failed"}
    ),
    "uninstall_receipt_pending": frozenset({"uninstalled", "uninstall_failed"}),
    "uninstall_failed": frozenset({"uninstall_preview", "disabled"}),
    "uninstalled": frozenset({"archived"}),
    "archived": frozenset(),
}

_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ENTRYPOINT_RE = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*)*(?::[a-z][a-z0-9_]*)?$"
)
_VERSION_CONSTRAINT_RE = re.compile(
    r"^(?:(?:\^|~|==|>=|<=|>|<)?(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\."
    r"(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?)(?:,(?:(?:==|>=|<=|>|<)"
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?))*$"
)
_MACHINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_EVIDENCE_REF_RE = re.compile(
    r"^(?:artifact|evaluation|audit|evidence|run):[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
)
_REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "id",
        "name",
        "version",
        "category",
        "description",
        "publisher",
        "license",
        "min_mis_version",
        "runtime_dependencies",
        "capabilities",
        "domain_objects",
        "workflows",
        "agents",
        "skills",
        "tools",
        "policies",
        "evaluators",
        "memory",
        "ui_extensions",
        "reports",
        "fixtures",
        "migrations",
        "permissions",
        "api_routes",
        "cli_commands",
        "testing_hooks",
        "exports",
        "upgrade_policy",
        "uninstall_policy",
        "provenance",
        "integrity",
    }
)
_LIST_FIELDS = frozenset(
    {
        "runtime_dependencies",
        "capabilities",
        "domain_objects",
        "workflows",
        "agents",
        "skills",
        "tools",
        "policies",
        "evaluators",
        "ui_extensions",
        "reports",
        "fixtures",
        "migrations",
        "permissions",
        "api_routes",
        "cli_commands",
        "testing_hooks",
        "exports",
    }
)
_APPROVAL_TO_EXECUTION = frozenset(
    {
        ("pending_approval", "installing"),
        ("pending_activation_approval", "activating"),
        ("pending_disable_approval", "disabling"),
        ("pending_upgrade_approval", "migrating"),
        ("pending_rollback_approval", "rolling_back"),
        ("pending_uninstall_approval", "uninstalling"),
    }
)
_EXECUTION_TO_READBACK = frozenset(
    {
        ("installing", "install_readback"),
        ("activating", "activation_readback"),
        ("disabling", "disable_readback"),
        ("migrating", "migration_readback"),
        ("upgrading", "upgrade_readback"),
        ("rolling_back", "rollback_readback"),
        ("uninstalling", "uninstall_readback"),
    }
)
_READBACK_TO_RECEIPT = frozenset(
    {
        ("install_readback", "install_receipt_pending"),
        ("activation_readback", "activation_receipt_pending"),
        ("disable_readback", "disable_receipt_pending"),
        ("migration_readback", "migration_receipt_pending"),
        ("upgrade_readback", "upgrade_receipt_pending"),
        ("rollback_readback", "rollback_receipt_pending"),
        ("uninstall_readback", "uninstall_receipt_pending"),
    }
)
_RECEIPT_TO_SUCCESS = frozenset(
    {
        ("install_receipt_pending", "installed"),
        ("activation_receipt_pending", "active"),
        ("disable_receipt_pending", "disabled"),
        ("migration_receipt_pending", "upgrading"),
        ("upgrade_receipt_pending", "active"),
        ("upgrade_receipt_pending", "disabled"),
        ("rollback_receipt_pending", "active"),
        ("rollback_receipt_pending", "disabled"),
        ("uninstall_receipt_pending", "uninstalled"),
    }
)
_RESTORE_TO_STABLE = frozenset(
    {
        ("activation_rejected", "installed"),
        ("activation_rejected", "disabled"),
        ("activation_approval_expired", "installed"),
        ("activation_approval_expired", "disabled"),
        ("disable_rejected", "active"),
        ("disable_approval_expired", "active"),
        ("disable_failed", "active"),
        ("upgrade_rejected", "active"),
        ("upgrade_rejected", "disabled"),
        ("upgrade_approval_expired", "active"),
        ("upgrade_approval_expired", "disabled"),
        ("rollback_rejected", "disabled"),
        ("rollback_approval_expired", "disabled"),
        ("rollback_failed", "disabled"),
        ("uninstall_rejected", "active"),
        ("uninstall_rejected", "disabled"),
        ("uninstall_approval_expired", "active"),
        ("uninstall_approval_expired", "disabled"),
        ("uninstall_failed", "disabled"),
    }
)
_VERSIONED_RECEIPT_TO_STABLE = frozenset(
    {
        ("upgrade_receipt_pending", "active"),
        ("upgrade_receipt_pending", "disabled"),
        ("rollback_receipt_pending", "active"),
        ("rollback_receipt_pending", "disabled"),
    }
)


class ContractViolation(ValueError):
    """Raised when an untrusted manifest, profile, or event violates v1."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def manifest_content_sha256(manifest: Mapping[str, Any]) -> str:
    """Hash the signed manifest payload without its integrity envelope."""
    if not isinstance(manifest, Mapping):
        raise ContractViolation(("manifest must be an object",))
    return canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "integrity"}
    )


def normalize_template_id(value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise ContractViolation(("id must match ^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$",))
    return value


def validate_lifecycle_transition(
    current: str, target: str, evidence: Mapping[str, Any] | None = None
) -> None:
    """Validate state edge plus the evidence required for privileged success."""
    errors: list[str] = []
    if current not in TEMPLATE_LIFECYCLE_TRANSITIONS:
        errors.append(f"unknown lifecycle state {current}")
    elif target not in TEMPLATE_LIFECYCLE_TRANSITIONS[current]:
        errors.append(f"invalid lifecycle transition {current}->{target}")
    proof = evidence if isinstance(evidence, Mapping) else {}
    if (current, target) in _APPROVAL_TO_EXECUTION:
        for field in ("approval_id", "action_hash"):
            if not isinstance(proof.get(field), str) or not proof.get(field):
                errors.append(f"{field} required for {current}->{target}")
        if proof.get("approval_status") != "approved":
            errors.append(f"approved approval_status required for {current}->{target}")
        if isinstance(proof.get("action_hash"), str) and not _SHA256_RE.fullmatch(
            proof["action_hash"]
        ):
            errors.append(f"action_hash must be lowercase sha256 for {current}->{target}")
    if (current, target) in _EXECUTION_TO_READBACK:
        if not isinstance(proof.get("transaction_id"), str) or not proof.get(
            "transaction_id"
        ):
            errors.append(f"transaction_id required for {current}->{target}")
    if (current, target) in _READBACK_TO_RECEIPT:
        if not isinstance(proof.get("readback_hash"), str) or not _SHA256_RE.fullmatch(
            proof.get("readback_hash", "")
        ):
            errors.append(f"readback_hash required for {current}->{target}")
    if (current, target) in _RECEIPT_TO_SUCCESS:
        for field in ("receipt_id", "receipt_hash"):
            value = proof.get(field)
            if not isinstance(value, str) or not value:
                errors.append(f"{field} required for {current}->{target}")
        if isinstance(proof.get("receipt_hash"), str) and not _SHA256_RE.fullmatch(
            proof["receipt_hash"]
        ):
            errors.append(f"receipt_hash must be lowercase sha256 for {current}->{target}")
    if (current, target) in _RESTORE_TO_STABLE | _VERSIONED_RECEIPT_TO_STABLE:
        if proof.get("previous_state") != target:
            errors.append(f"previous_state={target} required for {current}->{target}")
        if not isinstance(
            proof.get("state_snapshot_hash"), str
        ) or not _SHA256_RE.fullmatch(proof.get("state_snapshot_hash", "")):
            errors.append(f"state_snapshot_hash required for {current}->{target}")
        if (current, target) in _RESTORE_TO_STABLE:
            for field in ("receipt_id", "receipt_hash"):
                value = proof.get(field)
                if not isinstance(value, str) or not value:
                    errors.append(f"{field} required for {current}->{target}")
            if isinstance(proof.get("receipt_hash"), str) and not _SHA256_RE.fullmatch(
                proof["receipt_hash"]
            ):
                errors.append(
                    f"receipt_hash must be lowercase sha256 for {current}->{target}"
                )
    if errors:
        raise ContractViolation(errors)


def _plain_mapping(value: Any, field: str, errors: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{field} must be an object")
        return {}
    return value


def _plain_list(value: Any, field: str, errors: list[str]) -> Sequence[Any]:
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return ()
    return value


def _strict_rfc3339(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
        value,
    ):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_namespaced_items(
    items: Sequence[Any], template_id: str, field: str, errors: list[str]
) -> None:
    seen: set[str] = set()
    required_prefix = f"{template_id}."
    item_id_re = re.compile(
        rf"^{re.escape(template_id)}\.[a-z0-9][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*)*$"
    )
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            errors.append(f"{field}[{index}] must be an object")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id_re.fullmatch(item_id):
            errors.append(
                f"{field}[{index}].id must be a safe namespace under {required_prefix}"
            )
            continue
        if item_id in seen:
            errors.append(f"{field} contains duplicate id {item_id}")
        seen.add(item_id)
        allowed = {
            "id",
            "version",
            "contract_version",
            "entrypoint",
            "description",
            "configuration",
            "metadata",
        }
        required = {"id", "version", "contract_version", "entrypoint"}
        if field == "tools":
            allowed |= {"risk", "side_effect", "approval"}
            required |= {"risk", "side_effect", "approval"}
        elif field == "migrations":
            allowed |= {"from_version", "to_version", "checksum", "reversible"}
            required |= {"from_version", "to_version", "checksum", "reversible"}
        elif field == "permissions":
            allowed |= {"action", "scope", "risk", "default"}
            required |= {"action", "scope", "risk", "default"}
        elif field == "ui_extensions":
            allowed |= {"route", "nav_label", "permission"}
            required |= {"route", "nav_label", "permission"}
        unknown = sorted(item.keys() - allowed)
        if unknown:
            errors.append(f"{field}[{index}] has unknown fields: " + ", ".join(unknown))
        missing = sorted(required - item.keys())
        if missing:
            errors.append(f"{field}[{index}] missing fields: " + ", ".join(missing))
        if not isinstance(item.get("version"), str) or not _SEMVER_RE.fullmatch(
            item.get("version", "")
        ):
            errors.append(f"{field}[{index}].version must be semantic version")
        if not isinstance(item.get("contract_version"), str) or not item.get(
            "contract_version"
        ):
            errors.append(f"{field}[{index}].contract_version is required")
        if not isinstance(item.get("entrypoint"), str) or not _ENTRYPOINT_RE.fullmatch(
            item.get("entrypoint", "")
        ):
            errors.append(f"{field}[{index}].entrypoint is invalid")
        for object_field in ("configuration", "metadata"):
            if object_field in item and not isinstance(item.get(object_field), Mapping):
                errors.append(f"{field}[{index}].{object_field} must be an object")
        if field in {"tools", "permissions"}:
            if item.get("risk") not in {"low", "medium", "high", "critical"}:
                errors.append(f"{field}[{index}].risk is invalid")
        if field == "tools":
            if item.get("side_effect") not in {"none", "internal_write", "external_write"}:
                errors.append(f"tools[{index}].side_effect is invalid")
            if item.get("approval") not in {"never", "policy", "always"}:
                errors.append(f"tools[{index}].approval is invalid")
            if item.get("side_effect") == "external_write" and item.get(
                "approval"
            ) != "always":
                errors.append(
                    f"tools[{index}] external_write requires approval=always"
                )
            if item.get("risk") == "critical" and item.get("approval") != "always":
                errors.append(f"tools[{index}] critical risk requires approval=always")
            if item.get("risk") == "high" and item.get("approval") not in {
                "policy",
                "always",
            }:
                errors.append(
                    f"tools[{index}] high risk requires approval=policy or always"
                )
        if field == "permissions":
            if item.get("scope") not in {"workspace", "template", "project", "run"}:
                errors.append(f"permissions[{index}].scope is invalid")
            if item.get("default") not in {"allow", "ask", "deny"}:
                errors.append(f"permissions[{index}].default is invalid")
            if not isinstance(item.get("action"), str) or not re.fullmatch(
                rf"{re.escape(template_id)}\.[a-z0-9][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*)*",
                item.get("action", ""),
            ):
                errors.append(
                    f"permissions[{index}].action must be namespaced by template_id"
                )
            elif not re.fullmatch(
                rf"{re.escape(template_id)}\.permission\.[a-z0-9][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*)*",
                item["action"],
            ):
                errors.append(
                    f"permissions[{index}].action must use {template_id}.permission.*"
                )
            if item.get("risk") in {"high", "critical"} and item.get(
                "default"
            ) != "deny":
                errors.append(
                    f"permissions[{index}] high or critical risk requires default=deny"
                )
            if item.get("risk") == "medium" and item.get("default") == "allow":
                errors.append(
                    f"permissions[{index}] medium risk cannot default=allow"
                )
        if field == "migrations":
            for version_field in ("from_version", "to_version"):
                if not isinstance(item.get(version_field), str) or not _SEMVER_RE.fullmatch(
                    item.get(version_field, "")
                ):
                    errors.append(
                        f"migrations[{index}].{version_field} must be semantic version"
                    )
            if not isinstance(item.get("checksum"), str) or not _SHA256_RE.fullmatch(
                item.get("checksum", "")
            ):
                errors.append(f"migrations[{index}].checksum must be sha256")
            if not isinstance(item.get("reversible"), bool):
                errors.append(f"migrations[{index}].reversible must be boolean")
        if field == "ui_extensions":
            route = item.get("route")
            if not isinstance(route, str) or not re.fullmatch(
                rf"/solutions/{re.escape(template_id)}/[a-z0-9_-]+(?:/[a-z0-9_-]+)*",
                route,
            ):
                errors.append(
                    f"ui_extensions[{index}].route must stay under /solutions/{template_id}/"
                )
            for required_string in ("nav_label", "permission"):
                if not isinstance(item.get(required_string), str) or not item.get(
                    required_string
                ):
                    errors.append(
                        f"ui_extensions[{index}].{required_string} is required"
                    )


def validate_template_manifest(
    manifest: Mapping[str, Any],
    *,
    signature_verifier: Callable[
        [Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]
    ]
    | None = None,
) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        raise ContractViolation(("manifest must be an object",))
    data = dict(manifest)
    errors: list[str] = []
    missing = sorted(_REQUIRED_MANIFEST_FIELDS - data.keys())
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))
    unknown = sorted(data.keys() - _REQUIRED_MANIFEST_FIELDS)
    if unknown:
        errors.append("unknown top-level fields: " + ", ".join(unknown))

    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(f"schema_version must be {MANIFEST_SCHEMA_VERSION}")
    template_id = data.get("id")
    if not isinstance(template_id, str) or not _ID_RE.fullmatch(template_id):
        errors.append("id has invalid normalized form")
        template_id = "invalid"
    for field in ("name", "category", "description", "publisher", "license"):
        if not isinstance(data.get(field), str) or not data.get(field, "").strip():
            errors.append(f"{field} must be a non-empty string")
    for field in ("version", "min_mis_version"):
        if not isinstance(data.get(field), str) or not _SEMVER_RE.fullmatch(data[field]):
            errors.append(f"{field} must be semantic version")

    for field in _LIST_FIELDS:
        _plain_list(data.get(field), field, errors)
    for field in ("memory", "upgrade_policy", "uninstall_policy"):
        _plain_mapping(data.get(field), field, errors)

    memory = _plain_mapping(data.get("memory"), "memory", errors)
    memory_required = {
        "candidate_only": True,
        "source_refs_required": True,
        "shared_memory": "deny_by_default",
        "conflict_policy": "stale_or_superseded",
    }
    unknown_memory = sorted(memory.keys() - memory_required.keys())
    if unknown_memory:
        errors.append("memory has unknown fields: " + ", ".join(unknown_memory))
    for field, expected in memory_required.items():
        if memory.get(field) != expected:
            errors.append(f"memory.{field} must be {expected!r}")

    upgrade_policy = _plain_mapping(data.get("upgrade_policy"), "upgrade_policy", errors)
    upgrade_required = {
        "preview_required": True,
        "approval_required": True,
        "backup_required": True,
        "rollback_required": True,
        "readback_required": True,
        "receipt_required": True,
    }
    unknown_upgrade = sorted(
        upgrade_policy.keys() - (upgrade_required.keys() | {"compatibility"})
    )
    if unknown_upgrade:
        errors.append("upgrade_policy has unknown fields: " + ", ".join(unknown_upgrade))
    for field, expected in upgrade_required.items():
        if upgrade_policy.get(field) != expected:
            errors.append(f"upgrade_policy.{field} must be true")
    if upgrade_policy.get("compatibility") not in {"semver", "explicit_matrix"}:
        errors.append("upgrade_policy.compatibility is invalid")

    uninstall_policy = _plain_mapping(
        data.get("uninstall_policy"), "uninstall_policy", errors
    )
    uninstall_required = {
        "preview_required": True,
        "approval_required": True,
        "readback_required": True,
        "receipt_required": True,
        "archive_history": True,
    }
    unknown_uninstall = sorted(
        uninstall_policy.keys() - (uninstall_required.keys() | {"data_policy"})
    )
    if unknown_uninstall:
        errors.append(
            "uninstall_policy has unknown fields: " + ", ".join(unknown_uninstall)
        )
    for field, expected in uninstall_required.items():
        if uninstall_policy.get(field) != expected:
            errors.append(f"uninstall_policy.{field} must be true")
    if uninstall_policy.get("data_policy") not in {
        "archive",
        "delete_with_separate_approval",
    }:
        errors.append("uninstall_policy.data_policy is invalid")

    domain_objects = _plain_list(data.get("domain_objects"), "domain_objects", errors)
    domain_ids: set[str] = set()
    for index, item in enumerate(domain_objects):
        if not isinstance(item, Mapping):
            errors.append(f"domain_objects[{index}] must be an object")
            continue
        authority = item.get("authority")
        name = item.get("name")
        if authority not in {"template_domain", "mis_core_reference"}:
            errors.append(
                f"domain_objects[{index}].authority must be template_domain or mis_core_reference"
            )
            continue
        allowed_domain_fields = (
            {"id", "name", "authority", "schema"}
            if authority == "template_domain"
            else {"name", "authority", "core_authority_id"}
        )
        unknown_domain_fields = sorted(item.keys() - allowed_domain_fields)
        if unknown_domain_fields:
            errors.append(
                f"domain_objects[{index}] has unknown fields: "
                + ", ".join(unknown_domain_fields)
            )
        if not isinstance(name, str) or not name.strip():
            errors.append(f"domain_objects[{index}].name must be non-empty")
        if authority == "template_domain":
            domain_id = item.get("id")
            expected = re.compile(
                rf"^{re.escape(template_id)}\.domain\.[a-z0-9][a-z0-9_]*$"
            )
            if not isinstance(domain_id, str) or not expected.fullmatch(domain_id):
                errors.append(
                    f"domain_objects[{index}].id must be under {template_id}.domain."
                )
            elif domain_id in domain_ids:
                errors.append(f"domain_objects contains duplicate id {domain_id}")
            else:
                domain_ids.add(domain_id)
            if "schema" in item and not isinstance(item.get("schema"), Mapping):
                errors.append(f"domain_objects[{index}].schema must be an object")
        if authority == "mis_core_reference" and item.get(
            "core_authority_id"
        ) not in CORE_AUTHORITY_IDS:
            errors.append(
                f"domain_objects[{index}].core_authority_id must reference MIS Core"
            )
        normalized_name = re.sub(r"[^a-z0-9]", "", str(name).lower())
        if (
            normalized_name in CORE_AUTHORITY_ID_BY_NORMALIZED_NAME
            and authority != "mis_core_reference"
        ):
            errors.append(
                f"domain_objects[{index}] duplicates MIS Core authority {name}"
            )
        if authority == "mis_core_reference" and (
            normalized_name not in CORE_AUTHORITY_ID_BY_NORMALIZED_NAME
            or CORE_AUTHORITY_ID_BY_NORMALIZED_NAME[normalized_name]
            != item.get("core_authority_id")
        ):
            errors.append(f"domain_objects[{index}] Core name/id reference mismatch")

    dependencies = _plain_list(
        data.get("runtime_dependencies"), "runtime_dependencies", errors
    )
    dependency_ids: set[str] = set()
    for index, item in enumerate(dependencies):
        if not isinstance(item, Mapping):
            errors.append(f"runtime_dependencies[{index}] must be an object")
            continue
        unknown_dependency_fields = sorted(
            item.keys() - {"id", "kind", "version", "optional"}
        )
        if unknown_dependency_fields:
            errors.append(
                f"runtime_dependencies[{index}] has unknown fields: "
                + ", ".join(unknown_dependency_fields)
            )
        dependency_id = item.get("id")
        if not isinstance(dependency_id, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_.-]*", dependency_id
        ):
            errors.append(f"runtime_dependencies[{index}].id is invalid")
        elif dependency_id in dependency_ids:
            errors.append(f"runtime_dependencies contains duplicate id {dependency_id}")
        else:
            dependency_ids.add(dependency_id)
        if item.get("kind") not in {"python", "runtime", "template", "service"}:
            errors.append(f"runtime_dependencies[{index}].kind is invalid")
        if not isinstance(item.get("version"), str) or not _VERSION_CONSTRAINT_RE.fullmatch(
            item.get("version", "")
        ):
            errors.append(
                f"runtime_dependencies[{index}].version must be a bounded semantic constraint"
            )
        if "optional" in item and not isinstance(item.get("optional"), bool):
            errors.append(f"runtime_dependencies[{index}].optional must be boolean")

    capabilities = _plain_list(data.get("capabilities"), "capabilities", errors)
    if any(
        not isinstance(item, str)
        or not re.fullmatch(r"[a-z][a-z0-9_.-]*", item)
        for item in capabilities
    ):
        errors.append("capabilities entries must be normalized strings")
    if all(isinstance(item, str) for item in capabilities):
        if len(capabilities) != len(set(capabilities)):
            errors.append("capabilities entries must be unique")

    for field in (
        "workflows",
        "agents",
        "skills",
        "tools",
        "policies",
        "evaluators",
        "ui_extensions",
        "reports",
        "fixtures",
        "migrations",
        "permissions",
        "api_routes",
        "cli_commands",
        "testing_hooks",
        "exports",
    ):
        _validate_namespaced_items(
            _plain_list(data.get(field), field, errors), template_id, field, errors
        )

    permission_actions = {
        item.get("action")
        for item in data.get("permissions", [])
        if isinstance(item, Mapping) and isinstance(item.get("action"), str)
    }
    for index, extension in enumerate(data.get("ui_extensions", [])):
        if isinstance(extension, Mapping) and extension.get(
            "permission"
        ) not in permission_actions:
            errors.append(
                f"ui_extensions[{index}].permission must reference a declared permission action"
            )

    provenance = _plain_mapping(data.get("provenance"), "provenance", errors)
    unknown_provenance = sorted(
        provenance.keys() - {"source_repository", "source_commit", "built_at"}
    )
    if unknown_provenance:
        errors.append("provenance has unknown fields: " + ", ".join(unknown_provenance))
    for field in ("source_repository", "source_commit", "built_at"):
        if not isinstance(provenance.get(field), str) or not provenance.get(field):
            errors.append(f"provenance.{field} must be non-empty")
    source_commit = provenance.get("source_commit")
    if isinstance(source_commit, str) and not _COMMIT_RE.fullmatch(source_commit):
        errors.append("provenance.source_commit must be lowercase 40-character git sha")
    built_at = provenance.get("built_at")
    if isinstance(built_at, str) and not _strict_rfc3339(built_at):
        errors.append("provenance.built_at must be RFC3339 with timezone")

    integrity = _plain_mapping(data.get("integrity"), "integrity", errors)
    unknown_integrity = sorted(
        integrity.keys() - {"algorithm", "content_sha256", "signature"}
    )
    if unknown_integrity:
        errors.append("integrity has unknown fields: " + ", ".join(unknown_integrity))
    if integrity.get("algorithm") != "sha256":
        errors.append("integrity.algorithm must be sha256")
    content_sha = integrity.get("content_sha256")
    if not isinstance(content_sha, str) or not _SHA256_RE.fullmatch(content_sha):
        errors.append("integrity.content_sha256 must be lowercase sha256")
    elif content_sha != manifest_content_sha256(data):
        errors.append("integrity.content_sha256 does not match canonical manifest payload")
    signature = _plain_mapping(integrity.get("signature"), "integrity.signature", errors)
    unknown_signature = sorted(
        signature.keys() - {"status", "algorithm", "key_id", "value"}
    )
    if unknown_signature:
        errors.append(
            "integrity.signature has unknown fields: " + ", ".join(unknown_signature)
        )
    if signature.get("status") not in {"verified", "unsigned_candidate"}:
        errors.append("integrity.signature.status must be verified or unsigned_candidate")
    if signature.get("status") == "verified":
        for field in ("algorithm", "key_id", "value"):
            if not isinstance(signature.get(field), str) or not signature.get(field):
                errors.append(f"integrity.signature.{field} required when verified")
        if signature.get("algorithm") not in {"ed25519", "sigstore"}:
            errors.append("verified signature algorithm is not allowlisted")
        if signature_verifier is None:
            errors.append("verified signature requires a trusted signature verifier")
        elif not errors:
            try:
                signed_payload = {
                    key: value for key, value in data.items() if key != "integrity"
                }
                verification = signature_verifier(signed_payload, signature)
                required_verification = {
                    "verified": True,
                    "algorithm": signature.get("algorithm"),
                    "key_id": signature.get("key_id"),
                    "payload_sha256": content_sha,
                    "revocation_checked": True,
                }
                if not isinstance(verification, Mapping) or any(
                    verification.get(field) != expected
                    for field, expected in required_verification.items()
                ):
                    errors.append("trusted signature verification failed")
                elif not isinstance(
                    verification.get("trust_store_hash"), str
                ) or not _SHA256_RE.fullmatch(verification["trust_store_hash"]):
                    errors.append("trusted signature verification missing trust_store_hash")
                elif not isinstance(verification.get("receipt_id"), str) or not verification.get(
                    "receipt_id"
                ):
                    errors.append("trusted signature verification missing receipt_id")
                elif not isinstance(
                    verification.get("receipt_hash"), str
                ) or not _SHA256_RE.fullmatch(verification["receipt_hash"]):
                    errors.append("trusted signature verification missing receipt_hash")
            except Exception:
                errors.append("trusted signature verification failed")

    if errors:
        raise ContractViolation(errors)
    return data


def validate_event_envelope(event: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise ContractViolation(("event must be an object",))
    required = {
        "event_id",
        "event_type",
        "schema_version",
        "workspace_id",
        "project_id",
        "template_id",
        "profile_id",
        "task_id",
        "run_id",
        "actor",
        "occurred_at",
        "idempotency_key",
        "correlation_id",
        "sequence",
        "payload",
        "evidence_refs",
    }
    errors: list[str] = []
    missing = sorted(required - event.keys())
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))
    unknown = sorted(event.keys() - required)
    if unknown:
        errors.append("unknown event fields: " + ", ".join(unknown))
    if event.get("schema_version") != EVENT_SCHEMA_VERSION:
        errors.append(f"schema_version must be {EVENT_SCHEMA_VERSION}")
    template_id = event.get("template_id")
    event_type = event.get("event_type")
    if not isinstance(template_id, str) or not _ID_RE.fullmatch(template_id):
        errors.append("template_id has invalid normalized form")
    elif (
        not isinstance(event_type, str)
        or not re.fullmatch(
            rf"{re.escape(template_id)}\.[a-z0-9][a-z0-9_]*(?:\.[a-z0-9][a-z0-9_]*)*",
            event_type,
        )
    ):
        errors.append("event_type must be namespaced by template_id")
    if (
        isinstance(event.get("sequence"), bool)
        or not isinstance(event.get("sequence"), int)
        or event.get("sequence", 0) < 0
    ):
        errors.append("sequence must be a non-negative integer")
    actor = _plain_mapping(event.get("actor"), "actor", errors)
    if actor.keys() - {"type", "id"}:
        errors.append("actor has unknown fields")
    if actor.get("type") not in {"user", "agent", "system", "runtime"}:
        errors.append("actor.type is invalid")
    if not isinstance(actor.get("id"), str) or not _MACHINE_ID_RE.fullmatch(
        actor.get("id", "")
    ):
        errors.append("actor.id must be a safe machine id")
    _plain_mapping(event.get("payload"), "payload", errors)
    evidence_refs = _plain_list(event.get("evidence_refs"), "evidence_refs", errors)
    for field in ("event_id", "workspace_id", "idempotency_key", "correlation_id"):
        if not isinstance(event.get(field), str) or not _MACHINE_ID_RE.fullmatch(
            event.get(field, "")
        ):
            errors.append(f"{field} must be a safe machine id")
    occurred_at = event.get("occurred_at")
    if not _strict_rfc3339(occurred_at):
        errors.append("occurred_at must be RFC3339 with timezone")
    for field in ("project_id", "profile_id", "task_id", "run_id"):
        value = event.get(field)
        if value is not None and (
            not isinstance(value, str) or not _MACHINE_ID_RE.fullmatch(value)
        ):
            errors.append(f"{field} must be null or a safe machine id")
    if any(
        not isinstance(ref, str) or not _EVIDENCE_REF_RE.fullmatch(ref)
        for ref in evidence_refs
    ):
        errors.append("evidence_refs entries must bind Core evidence authority")
    if errors:
        raise ContractViolation(errors)
    return dict(event)


def validate_product_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(profile, Mapping):
        raise ContractViolation(("profile must be an object",))
    required = {
        "schema_version",
        "id",
        "template_id",
        "name",
        "version",
        "description",
        "configuration",
        "budgets",
        "policies",
        "evaluators",
        "submission",
    }
    errors: list[str] = []
    missing = sorted(required - profile.keys())
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))
    unknown = sorted(profile.keys() - required)
    if unknown:
        errors.append("unknown profile fields: " + ", ".join(unknown))
    if profile.get("schema_version") != PROFILE_CONTRACT_VERSION:
        errors.append(f"schema_version must be {PROFILE_CONTRACT_VERSION}")
    template_id = profile.get("template_id")
    profile_id = profile.get("id")
    if not isinstance(template_id, str) or not _ID_RE.fullmatch(template_id):
        errors.append("template_id has invalid normalized form")
    if (
        not isinstance(profile_id, str)
        or not _ID_RE.fullmatch(profile_id)
        or not isinstance(template_id, str)
    ):
        errors.append("id has invalid normalized form")
    if not isinstance(profile.get("version"), str) or not _SEMVER_RE.fullmatch(
        profile.get("version", "")
    ):
        errors.append("version must be semantic version")
    for field in ("configuration", "budgets", "submission"):
        _plain_mapping(profile.get(field), field, errors)
    for field in ("policies", "evaluators"):
        _validate_namespaced_items(
            _plain_list(profile.get(field), field, errors),
            template_id if isinstance(template_id, str) else "invalid",
            field,
            errors,
        )
    for field in ("name", "description"):
        if not isinstance(profile.get(field), str) or not profile.get(field, "").strip():
            errors.append(f"{field} must be a non-empty string")
    if errors:
        raise ContractViolation(errors)
    return dict(profile)
