"""Research v0-to-v1 migration through the shared migration transaction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
import re
from typing import Any, Protocol, runtime_checkable

from template_runtime.protocols import InstallationIdentity, LifecycleCommand, LifecycleReceipt, TemplateMigrationPort

from .contracts import ResearchError, canonical_hash, require_sha256
from .migration_journal import MigrationRestartJournal
from .trust import CoreTrustStore, require_core_receipt


LEGACY_SCHEMA = "research_lab_mis_evidence_v1"
TARGET_SCHEMA = "research-lab-domain/v1"


def migration_checksum() -> str:
    return canonical_hash({"from": LEGACY_SCHEMA, "to": TARGET_SCHEMA, "mapping": "experiment_trial_attempt_metric_artifact"})


def dry_run_legacy(records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    errors: list[Mapping[str, Any]] = []
    counts: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records):
        kind = str(record.get("kind") or "")
        record_id = str(record.get("id") or "")
        if kind not in {"experiment", "trial", "attempt", "metric", "artifact"}:
            errors.append({"index": index, "code": "unsupported_kind", "kind": kind})
        if not record_id:
            errors.append({"index": index, "code": "missing_id"})
        identity = (kind, record_id)
        if identity in seen:
            errors.append({"index": index, "code": "duplicate_identity", "identity": list(identity)})
        seen.add(identity)
        counts[kind] = counts.get(kind, 0) + 1
    result = {"from_schema": LEGACY_SCHEMA, "to_schema": TARGET_SCHEMA, "record_count": len(records), "counts": counts, "valid": not errors, "errors": errors, "migration_checksum": migration_checksum(), "data_loss": False}
    return {**result, "dry_run_hash": canonical_hash(result)}


def transform_legacy(record: Mapping[str, Any], *, workspace_id: str, project_id: str, task_id: str, run_id: str) -> Mapping[str, Any]:
    kind = str(record.get("kind") or "")
    mapping = {
        "experiment": "experiment",
        "trial": "trial",
        "attempt": "job_attempt",
        "metric": "metric_snapshot",
        "artifact": "research_artifact",
    }
    if kind not in mapping or not record.get("id"):
        raise ResearchError("research.migration_invalid_record", "legacy record cannot be mapped")
    source_hash = canonical_hash(dict(record))
    return {
        "namespace": "research_lab",
        "kind": mapping[kind],
        "record_id": str(record["id"]),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "task_id": task_id,
        "run_id": run_id,
        "schema_version": TARGET_SCHEMA,
        "legacy_source_hash": source_hash,
        "legacy_read_only": True,
        "value": dict(record.get("value") or {}),
    }


def verify_migration(source: Sequence[Mapping[str, Any]], migrated: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    source_ids = sorted((str(item.get("kind")), str(item.get("id"))) for item in source)
    reverse_kind = {"job_attempt": "attempt", "metric_snapshot": "metric", "research_artifact": "artifact", "experiment": "experiment", "trial": "trial"}
    target_ids = sorted((reverse_kind.get(str(item.get("kind")), "unknown"), str(item.get("record_id"))) for item in migrated)
    source_by_identity = {(str(item.get("kind")), str(item.get("id"))): item for item in source}
    content_verified = True
    for item in migrated:
        source_kind = reverse_kind.get(str(item.get("kind")), "unknown")
        original = source_by_identity.get((source_kind, str(item.get("record_id"))))
        if original is None or item.get("legacy_source_hash") != canonical_hash(dict(original)) or item.get("value") != dict(original.get("value") or {}):
            content_verified = False
            break
    result = {"verified": source_ids == target_ids and content_verified, "content_verified": content_verified, "source_count": len(source), "target_count": len(migrated), "source_identity_hash": canonical_hash(source_ids), "target_identity_hash": canonical_hash(target_ids), "historical_readable": all(item.get("legacy_read_only") is True for item in migrated)}
    return {**result, "readback_hash": canonical_hash(result)}


def rollback_plan(*, backup_receipt_id: str, backup_sha256: str) -> Mapping[str, Any]:
    if not backup_receipt_id:
        raise ResearchError("research.rollback_backup_invalid", "verified shared backup receipt is required")
    require_sha256(backup_sha256, "backup_sha256")
    plan = {"operation": "restore_shared_backup", "backup_receipt_id": backup_receipt_id, "backup_sha256": backup_sha256, "delete_v1_records": False, "archive_v1_records": True, "requires_approval": True, "readback_required": True}
    return {**plan, "action_hash": canonical_hash(plan)}


@runtime_checkable
class CoreMigrationTransactionPort(Protocol):
    """C0-owned transactional implementation; C1 never creates migration authority."""
    def load_legacy_records(self, identity: InstallationIdentity) -> Sequence[Mapping[str, Any]]: ...
    def create_backup(self, identity: InstallationIdentity) -> Mapping[str, Any]: ...
    def create_backup_once(self, *, identity: InstallationIdentity, request_hash: str) -> Mapping[str, Any]: ...
    def find_migration_by_request_hash(self, *, identity: InstallationIdentity, request_hash: str) -> Mapping[str, Any] | None: ...
    def authorize_migration(self, *, command: LifecycleCommand, migration_ids: Sequence[str], request_hash: str) -> Mapping[str, Any]: ...
    def apply_domain_migration_once(self, *, command: LifecycleCommand, migration_ids: Sequence[str], transformed: Sequence[Mapping[str, Any]], backup_receipt_id: str, backup_sha256: str, request_hash: str) -> Mapping[str, Any]: ...
    def readback_domain_migration(self, *, identity: InstallationIdentity, migration_ids: Sequence[str]) -> Mapping[str, Any]: ...
    def restore_backup_once(self, *, command: LifecycleCommand, backup_receipt_id: str, mode: str, request_hash: str) -> Mapping[str, Any]: ...
    def get_lifecycle_receipt(self, *, transaction_id: str, readback_hash: str) -> LifecycleReceipt: ...
    def attest_lifecycle_receipt(self, *, transaction_id: str, readback_hash: str, lifecycle_receipt_hash: str) -> Mapping[str, Any]: ...


class ResearchMigrationAdapter:
    """Complete frozen TemplateMigrationPort adapter with Core-owned atomicity."""
    migration_id = "research_lab.migration.0_1_0_to_1_0_0"

    def __init__(self, core: CoreMigrationTransactionPort, trust: CoreTrustStore, journal: MigrationRestartJournal | None = None) -> None:
        if not isinstance(core, CoreMigrationTransactionPort):
            raise TypeError("core must implement CoreMigrationTransactionPort")
        self.core = core
        self.trust = trust
        self.journal = journal

    @staticmethod
    def _identity(command: LifecycleCommand) -> InstallationIdentity:
        return InstallationIdentity(command.workspace_id, command.template_id)

    def dry_run(self, identity: InstallationIdentity, target_version: str) -> Mapping[str, Any]:
        if identity.template_id != "research_lab" or target_version != "1.0.0":
            raise ResearchError("research.migration_target_invalid", "migration target must be research_lab/1.0.0")
        return dry_run_legacy(self.core.load_legacy_records(identity))

    def backup(self, identity: InstallationIdentity) -> Mapping[str, Any]:
        receipt = require_core_receipt(self.core.create_backup(identity), trust=self.trust, purpose="research.migration-backup/v1", bindings={"verified": True, "workspace_id": identity.workspace_id, "template_id": identity.template_id})
        require_sha256(str(receipt.get("backup_sha256") or ""), "backup_sha256")
        if not receipt.get("backup_receipt_id"):
            raise ResearchError("research.migration_backup_invalid", "Core backup receipt must be verified")
        return receipt
    def apply_once(self, command: LifecycleCommand, migration_ids: Sequence[str]) -> Mapping[str, Any]:
        if tuple(migration_ids) != (self.migration_id,) or command.template_id != "research_lab" or command.target_version != "1.0.0":
            raise ResearchError("research.migration_set_invalid", "exact Research migration set is required")
        identity = self._identity(command)
        source = tuple(self.core.load_legacy_records(identity))
        preview = dry_run_legacy(source)
        if not preview["valid"]:
            raise ResearchError("research.migration_dry_run_failed", "migration dry-run must pass before apply")
        base_request = {"command": {field: getattr(command, field) for field in command.__dataclass_fields__}, "migration_ids": list(migration_ids), "source_hash": canonical_hash(source), "dry_run_hash": preview["dry_run_hash"]}
        request_hash = canonical_hash(base_request)
        journaled = self.journal.read(request_hash) if self.journal else None
        prior = self.core.find_migration_by_request_hash(identity=identity, request_hash=request_hash)
        if prior is not None:
            prior = require_core_receipt(prior, trust=self.trust, purpose="research.migration-apply/v1", bindings={"committed": True, "request_hash": request_hash, "workspace_id": identity.workspace_id, "template_id": identity.template_id})
            if not prior.get("transaction_id"):
                raise ResearchError("research.migration_replay_invalid", "persisted migration replay receipt is incomplete")
            if self.journal and journaled and journaled.get("backup"):
                journaled_apply = self.journal.record_apply_once(request_hash, prior)
                if journaled_apply.get("receipt_hash") != prior["receipt_hash"]:
                    raise ResearchError("research.migration_journal_conflict", "journaled apply receipt conflicts with Core authority")
            return prior
        if journaled and journaled.get("apply"):
            raise ResearchError("research.migration_journal_conflict", "journal records apply but Core authoritative readback is missing")
        backup = require_core_receipt(self.core.create_backup_once(identity=identity, request_hash=request_hash), trust=self.trust, purpose="research.migration-backup-once/v1", bindings={"verified": True, "request_hash": request_hash, "workspace_id": identity.workspace_id, "template_id": identity.template_id})
        if not backup.get("backup_receipt_id"):
            raise ResearchError("research.migration_backup_invalid", "persisted Core backup receipt is invalid")
        require_sha256(str(backup.get("backup_sha256") or ""), "backup_sha256")
        if self.journal:
            journaled_backup = self.journal.record_backup_once(request_hash, backup)
            journaled_backup = require_core_receipt(journaled_backup, trust=self.trust, purpose="research.migration-backup-once/v1", bindings={"verified": True, "request_hash": request_hash, "workspace_id": identity.workspace_id, "template_id": identity.template_id})
            if journaled_backup["receipt_hash"] != backup["receipt_hash"]:
                raise ResearchError("research.migration_journal_conflict", "journaled backup receipt conflicts with Core authority")
        authorization = require_core_receipt(self.core.authorize_migration(command=command, migration_ids=migration_ids, request_hash=request_hash), trust=self.trust, purpose="research.migration-authorization/v1", bindings={"decision": "allow", "executed_once": True, "request_hash": request_hash, "backup_receipt_id": backup["backup_receipt_id"], "workspace_id": identity.workspace_id, "template_id": identity.template_id})
        if authorization.get("decision") != "allow":
            raise ResearchError("research.migration_not_authorized", "Core PreparedAction/Approval denied migration")
        transformed = tuple(transform_legacy(item, workspace_id=command.workspace_id, project_id=str(authorization.get("project_id") or ""), task_id=str(authorization.get("task_id") or ""), run_id=str(authorization.get("run_id") or "")) for item in source)
        applied = require_core_receipt(self.core.apply_domain_migration_once(command=command, migration_ids=migration_ids, transformed=transformed, backup_receipt_id=str(backup["backup_receipt_id"]), backup_sha256=str(backup["backup_sha256"]), request_hash=request_hash), trust=self.trust, purpose="research.migration-apply/v1", bindings={"committed": True, "request_hash": request_hash, "backup_receipt_id": backup["backup_receipt_id"], "workspace_id": identity.workspace_id, "template_id": identity.template_id})
        if not applied.get("transaction_id"):
            raise ResearchError("research.migration_apply_failed", "Core migration transaction did not commit")
        if self.journal:
            journaled_apply = self.journal.record_apply_once(request_hash, applied)
            if journaled_apply.get("receipt_hash") != applied["receipt_hash"]:
                raise ResearchError("research.migration_journal_conflict", "journaled apply receipt conflicts with Core authority")
        return {**applied, "request_hash": request_hash, "backup_receipt_id": backup["backup_receipt_id"], "backup_sha256": backup["backup_sha256"], "authorization_receipt_hash": authorization["receipt_hash"]}

    def readback(self, identity: InstallationIdentity, migration_ids: Sequence[str]) -> Mapping[str, Any]:
        observed = require_core_receipt(self.core.readback_domain_migration(identity=identity, migration_ids=migration_ids), trust=self.trust, purpose="research.migration-readback/v1", bindings={"verified": True, "workspace_id": identity.workspace_id, "template_id": identity.template_id})
        if not re.fullmatch(r"[0-9a-f]{64}", str(observed.get("readback_hash") or "")):
            raise ResearchError("research.migration_readback_failed", "Core migration readback failed")
        return observed

    def _restore(self, command: LifecycleCommand, backup_receipt_id: str, mode: str) -> Mapping[str, Any]:
        request_hash = canonical_hash({"command": {field: getattr(command, field) for field in command.__dataclass_fields__}, "backup_receipt_id": backup_receipt_id, "mode": mode})
        observed = require_core_receipt(self.core.restore_backup_once(command=command, backup_receipt_id=backup_receipt_id, mode=mode, request_hash=request_hash), trust=self.trust, purpose="research.migration-restore/v1", bindings={"request_hash": request_hash, "backup_receipt_id": backup_receipt_id, "restored": True, "workspace_id": command.workspace_id, "template_id": command.template_id})
        if not re.fullmatch(r"[0-9a-f]{64}", str(observed.get("readback_hash") or "")):
            raise ResearchError("research.migration_restore_failed", "Core backup restore/readback failed")
        return observed

    def rollback(self, command: LifecycleCommand, backup_receipt_id: str) -> Mapping[str, Any]:
        return self._restore(command, backup_receipt_id, "rollback")

    def restore(self, command: LifecycleCommand, backup_receipt_id: str) -> Mapping[str, Any]:
        return self._restore(command, backup_receipt_id, "restore")

    def receipt(self, transaction_id: str, readback_hash: str) -> LifecycleReceipt:
        require_sha256(readback_hash, "readback_hash")
        receipt = self.core.get_lifecycle_receipt(transaction_id=transaction_id, readback_hash=readback_hash)
        if receipt.transaction_id != transaction_id or receipt.readback_hash != readback_hash or receipt.template_id != "research_lab":
            raise ResearchError("research.migration_receipt_invalid", "Core LifecycleReceipt does not bind migration readback")
        document_hash = canonical_hash(asdict(receipt))
        require_core_receipt(self.core.attest_lifecycle_receipt(transaction_id=transaction_id, readback_hash=readback_hash, lifecycle_receipt_hash=document_hash), trust=self.trust, purpose="research.migration-lifecycle-receipt/v1", bindings={"transaction_id": transaction_id, "readback_hash": readback_hash, "lifecycle_receipt_hash": document_hash, "template_id": "research_lab", "verified": True})
        return receipt
