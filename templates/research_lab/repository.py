"""MIS Core-backed Research repository.

This module never opens SQLite or owns approvals/audits.  Its injected port is
implemented by the shared Template SDK/MIS Core integration in C0.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any, Protocol, runtime_checkable

from template_runtime.contracts import validate_event_envelope

from .contracts import CoreRefs, ResearchError, canonical_hash, require_id
from .trust import CoreTrustStore, require_core_receipt


@runtime_checkable
class ResearchCorePort(Protocol):
    def get_domain_record(self, *, namespace: str, kind: str, record_id: str, workspace_id: str, project_id: str) -> Mapping[str, Any] | None: ...

    def list_domain_records(self, *, namespace: str, kind: str, workspace_id: str, project_id: str, filters: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]: ...

    def assert_core_references(self, *, workspace_id: str, references: Mapping[str, str]) -> None: ...

    def get_core_authority_record(self, *, authority: str, record_id: str, workspace_id: str) -> Mapping[str, Any] | None: ...

    def transact_domain_records_and_events(self, *, namespace: str, workspace_id: str, operations: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]]) -> Mapping[str, Sequence[Mapping[str, Any]]]: ...

    def authorize_research_attempt(self, *, workspace_id: str, project_id: str, task_id: str, run_id: str, executor: str, compute_target_id: str, trial_id: str, attempt_number: int) -> Mapping[str, Any]: ...


class ResearchRepository:
    namespace = "research_lab"

    def __init__(self, core: ResearchCorePort, trust: CoreTrustStore) -> None:
        if not isinstance(core, ResearchCorePort):
            raise TypeError("core must implement ResearchCorePort")
        self._core = core
        self._trust = trust

    def assert_refs(self, refs: CoreRefs) -> None:
        self._core.assert_core_references(
            workspace_id=refs.workspace_id,
            references={
                "project_id": refs.project_id,
                "task_id": refs.task_id,
                "plan_id": refs.plan_id,
                "run_id": refs.run_id,
                "actor_id": refs.actor_id,
            },
        )

    def verify_core_receipt(self, receipt: Mapping[str, Any], *, purpose: str, bindings: Mapping[str, Any]) -> Mapping[str, Any]:
        return require_core_receipt(receipt, trust=self._trust, purpose=purpose, bindings=bindings)

    def admit_attempt(self, *, refs: CoreRefs, executor: str, compute_target_id: str, trial_id: str, attempt_number: int) -> Mapping[str, Any]:
        if executor not in {"local", "ssh", "slurm"}:
            raise ResearchError("research.executor_invalid", "executor must be local, ssh or slurm")
        request = {"workspace_id": refs.workspace_id, "project_id": refs.project_id, "task_id": refs.task_id, "plan_id": refs.plan_id, "run_id": refs.run_id, "executor": executor, "compute_target_id": compute_target_id, "trial_id": trial_id, "attempt_number": attempt_number}
        request_hash = canonical_hash(request)
        receipt = dict(self._core.authorize_research_attempt(workspace_id=refs.workspace_id, project_id=refs.project_id, task_id=refs.task_id, run_id=refs.run_id, executor=executor, compute_target_id=compute_target_id, trial_id=trial_id, attempt_number=attempt_number))
        required = ("target_verified", "budget_allowed", "concurrency_allowed", "retry_allowed", "approval_satisfied")
        receipt = require_core_receipt(receipt, trust=self._trust, purpose="research.attempt-admission/v1", bindings={"request_hash": request_hash, **request})
        if receipt.get("decision") != "allow" or any(receipt.get(field) is not True for field in required):
            raise ResearchError("research.attempt_admission_denied", "Core ComputeTarget, budget, concurrency, retry or approval admission denied")
        return receipt

    def put(self, *, kind: str, record_id: str, refs: CoreRefs, value: Mapping[str, Any], expected_version: int | None = None) -> Mapping[str, Any]:
        return self.put_many(refs=refs, operations=({"kind": kind, "record_id": record_id, "expected_version": expected_version, "value": value},))[0]

    def get(self, *, kind: str, record_id: str, workspace_id: str, project_id: str) -> Mapping[str, Any] | None:
        require_id(record_id, "record_id")
        return self._core.get_domain_record(namespace=self.namespace, kind=kind, record_id=record_id, workspace_id=workspace_id, project_id=project_id)

    def require(self, *, kind: str, record_id: str, workspace_id: str, project_id: str) -> Mapping[str, Any]:
        record = self.get(kind=kind, record_id=record_id, workspace_id=workspace_id, project_id=project_id)
        if record is None:
            raise ResearchError("research.not_found", f"{kind} {record_id} was not found")
        return record

    def list(self, *, kind: str, workspace_id: str, project_id: str, filters: Mapping[str, Any] | None = None) -> Sequence[Mapping[str, Any]]:
        return self._core.list_domain_records(namespace=self.namespace, kind=kind, workspace_id=workspace_id, project_id=project_id, filters=filters or {})

    def require_core(self, *, authority: str, record_id: str, refs: CoreRefs) -> Mapping[str, Any]:
        allowed = {"run", "prepared_action", "approval", "artifact", "evaluation", "evidence", "identity", "permission", "audit", "plan", "task"}
        if authority not in allowed:
            raise ResearchError("research.core_authority_invalid", "Core authority kind is not allowlisted")
        require_id(record_id, f"{authority}_id")
        value = self._core.get_core_authority_record(authority=authority, record_id=record_id, workspace_id=refs.workspace_id)
        if value is None:
            raise ResearchError("research.core_reference_missing", f"MIS Core {authority} readback failed")
        if (
            value.get("workspace_id") != refs.workspace_id
            or value.get("project_id") != refs.project_id
            or value.get(f"{authority}_id", record_id) != record_id
        ):
            raise ResearchError("research.core_reference_mismatch", f"MIS Core {authority} readback mismatched")
        return require_core_receipt(value, trust=self._trust, purpose=f"research.core-authority/{authority}/v1", bindings={"workspace_id": refs.workspace_id, "project_id": refs.project_id, f"{authority}_id": record_id})

    def _event(self, *, event_type: str, event_id: str, refs: CoreRefs, idempotency_key: str, sequence: int, payload: Mapping[str, Any], evidence_refs: Sequence[str] = (), profile_id: str | None = None, occurred_at: str, actor_type: str | None = None) -> Mapping[str, Any]:
        observed_actor_type = actor_type or ("agent" if refs.actor_id.startswith("agt_") else "user")
        if observed_actor_type not in {"user", "agent", "system", "runtime"}:
            raise ResearchError("research.invalid_actor_type", "event actor type is invalid")
        return validate_event_envelope({"event_id": event_id, "event_type": f"research_lab.{event_type}", "schema_version": "template-event/v1", "workspace_id": refs.workspace_id, "project_id": refs.project_id, "template_id": self.namespace, "profile_id": profile_id, "task_id": refs.task_id, "run_id": refs.run_id, "actor": {"type": observed_actor_type, "id": refs.actor_id}, "occurred_at": occurred_at, "idempotency_key": idempotency_key, "correlation_id": refs.run_id, "sequence": sequence, "payload": dict(payload), "evidence_refs": list(evidence_refs)})

    def put_many(self, *, refs: CoreRefs, operations: Sequence[Mapping[str, Any]], events: Sequence[Mapping[str, Any]] = ()) -> Sequence[Mapping[str, Any]]:
        """Commit domain records and their outbox envelopes in one Core transaction."""
        self.assert_refs(refs)
        normalized = []
        for operation in operations:
            record_id = require_id(str(operation.get("record_id") or ""), "record_id")
            value = dict(operation.get("value") or {})
            if value.get("workspace_id") not in {None, refs.workspace_id}:
                raise ResearchError("research.cross_workspace", "record workspace does not match Core references")
            normalized.append(
                {
                    "kind": str(operation["kind"]),
                    "record_id": record_id,
                    "expected_version": operation.get("expected_version"),
                    "value": {**value, "workspace_id": refs.workspace_id, "project_id": refs.project_id, "task_id": refs.task_id, "run_id": refs.run_id},
                }
            )
        event_declarations = [dict(event) for event in events]
        for index, operation in enumerate(normalized):
            record_id = str(operation["record_id"])
            if any(record_id in set(map(str, dict(event.get("payload") or {}).values())) for event in event_declarations):
                continue
            value = dict(operation["value"])
            idempotency_key = str(value.get("idempotency_key") or self.idempotency_key("domain_write", {"kind": operation["kind"], "record_id": record_id, "value": value}))
            occurred_at = str(value.get("updated_at") or value.get("created_at") or value.get("recorded_at") or value.get("reviewed_at") or value.get("frozen_at") or value.get("invalidated_at") or "")
            if not occurred_at:
                raise ResearchError("research.audit_timestamp_missing", "every domain write requires an immutable audit timestamp")
            event_declarations.append({"event_type": "domain.changed", "event_id": f"evt_{canonical_hash({'kind': operation['kind'], 'record_id': record_id, 'idempotency_key': idempotency_key})[:20]}", "idempotency_key": idempotency_key, "sequence": len(event_declarations) + index, "payload": {"kind": operation["kind"], "record_id": record_id, "record_hash": canonical_hash(value)}, "occurred_at": occurred_at})
        normalized_events = [self._event(refs=refs, **event) for event in event_declarations]
        transaction = self._core.transact_domain_records_and_events(namespace=self.namespace, workspace_id=refs.workspace_id, operations=normalized, events=normalized_events)
        receipts = list(transaction.get("records") or ())
        event_receipts = list(transaction.get("events") or ())
        if len(receipts) != len(normalized):
            raise ResearchError("research.transaction_readback_invalid", "Core transaction receipt count mismatch")
        if len(event_receipts) != len(normalized_events):
            raise ResearchError("research.transaction_readback_invalid", "Core outbox transaction receipt mismatch")
        verified_records = []
        for expected, item in zip(normalized, receipts):
            verified = require_core_receipt(item, trust=self._trust, purpose="research.domain-record-commit/v1", bindings={"namespace": self.namespace, "workspace_id": refs.workspace_id, "project_id": refs.project_id, "kind": expected["kind"], "record_id": expected["record_id"], "committed": True, "value_hash": canonical_hash(expected["value"])})
            if not isinstance(verified.get("version"), int) or verified["version"] < 1:
                raise ResearchError("research.transaction_readback_invalid", "Core record transaction version is invalid")
            verified_records.append(dict(verified.get("value") or {}))
            verified_records[-1]["version"] = verified["version"]
        for expected, item in zip(normalized_events, event_receipts):
            verified = require_core_receipt(item, trust=self._trust, purpose="research.outbox-event-commit/v1", bindings={"event_id": expected["event_id"], "event_hash": canonical_hash(expected), "committed": True})
            if verified.get("event_id") != expected["event_id"]:
                raise ResearchError("research.transaction_readback_invalid", "Core outbox transaction receipt is not authoritative or canonical")
        return verified_records

    def emit(self, *, event_type: str, event_id: str, refs: CoreRefs, idempotency_key: str, sequence: int, payload: Mapping[str, Any], evidence_refs: Sequence[str] = (), profile_id: str | None = None, occurred_at: str, actor_type: str | None = None) -> Mapping[str, Any]:
        self.put_many(refs=refs, operations=(), events=({"event_type": event_type, "event_id": event_id, "idempotency_key": idempotency_key, "sequence": sequence, "payload": payload, "evidence_refs": evidence_refs, "profile_id": profile_id, "occurred_at": occurred_at, "actor_type": actor_type},))
        return {"event_id": event_id, "committed": True}

    @staticmethod
    def idempotency_key(operation: str, value: Mapping[str, Any]) -> str:
        return f"research_lab:{operation}:{canonical_hash(value)}"
