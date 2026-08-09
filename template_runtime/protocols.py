"""Frozen port contracts for Template Platform v1 implementations.

These protocols do not create another authority layer. Implementations persist
through MIS Core repositories and emit Core Run, Approval, Artifact, Evaluation
and Audit references in every receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


class TemplateErrorCode(str, Enum):
    INVALID_MANIFEST = "template.invalid_manifest"
    INCOMPATIBLE_VERSION = "template.incompatible_version"
    DEPENDENCY_UNAVAILABLE = "template.dependency_unavailable"
    ALREADY_INSTALLED = "template.already_installed"
    NOT_INSTALLED = "template.not_installed"
    INVALID_STATE = "template.invalid_state"
    APPROVAL_REQUIRED = "template.approval_required"
    APPROVAL_INVALID = "template.approval_invalid"
    ACTION_HASH_MISMATCH = "template.action_hash_mismatch"
    IDEMPOTENCY_CONFLICT = "template.idempotency_conflict"
    PERMISSION_DENIED = "template.permission_denied"
    CROSS_TEMPLATE_SCOPE = "template.cross_template_scope"
    MIGRATION_FAILED = "template.migration_failed"
    READBACK_FAILED = "template.readback_failed"
    RECEIPT_INVALID = "template.receipt_invalid"
    RUNTIME_UNAVAILABLE = "template.runtime_unavailable"
    RUNTIME_DEGRADED = "template.runtime_degraded"
    OUTBOX_DELIVERY_FAILED = "template.outbox_delivery_failed"


class ToolRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class RuntimeState(str, Enum):
    PREPARED = "prepared"
    STARTING = "starting"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    INTERRUPTING = "interrupting"
    INTERRUPTED = "interrupted"
    RESUMING = "resuming"
    RECONCILING = "reconciling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class RegistryIdentity:
    publisher: str
    template_id: str
    version: str


@dataclass(frozen=True, slots=True)
class InstallationIdentity:
    workspace_id: str
    template_id: str


@dataclass(frozen=True, slots=True)
class LifecycleCommand:
    operation: str
    workspace_id: str
    template_id: str
    target_version: str | None
    idempotency_key: str
    action_hash: str
    actor_id: str
    approval_id: str | None
    correlation_id: str


@dataclass(frozen=True, slots=True)
class LifecycleReadback:
    workspace_id: str
    template_id: str
    state: str
    active_version: str | None
    readback_hash: str
    migration_ids: tuple[str, ...]
    observed_at: str


@dataclass(frozen=True, slots=True)
class LifecycleReceipt:
    receipt_id: str
    operation: str
    workspace_id: str
    template_id: str
    previous_state: str
    final_state: str
    action_hash: str
    idempotency_key: str
    transaction_id: str
    readback_hash: str
    receipt_hash: str
    approval_id: str | None
    run_id: str
    audit_id: str
    artifact_ids: tuple[str, ...]
    occurred_at: str


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    outbox_id: str
    workspace_id: str
    template_id: str
    event_id: str
    event_type: str
    schema_version: str
    idempotency_key: str
    correlation_id: str
    sequence: int
    payload_hash: str
    status: str
    attempts: int
    next_attempt_at: str | None


@dataclass(frozen=True, slots=True)
class RuntimeRequest:
    runtime_request_id: str
    workspace_id: str
    project_id: str
    template_id: str
    profile_id: str | None
    run_id: str
    agent_id: str
    team_id: str | None
    provider: str
    model: str
    policy_hash: str
    idempotency_key: str
    checkpoint_ref: str | None
    input_ref: str


@dataclass(frozen=True, slots=True)
class RuntimeReceipt:
    runtime_receipt_id: str
    runtime_request_id: str
    state: RuntimeState
    provider: str
    model: str
    upstream_version: str
    output_schema_version: str
    output_ref: str | None
    checkpoint_ref: str | None
    event_ids: tuple[str, ...]
    tool_call_ids: tuple[str, ...]
    approval_ids: tuple[str, ...]
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float
    latency_ms: int
    receipt_hash: str
    error_code: TemplateErrorCode | None


@runtime_checkable
class TemplateRegistryPort(Protocol):
    def discover(self, package_uri: str) -> RegistryIdentity: ...

    def validate(self, identity: RegistryIdentity) -> Mapping[str, Any]: ...

    def resolve(
        self, template_id: str, version_constraint: str, mis_version: str
    ) -> RegistryIdentity: ...

    def get_installation(self, identity: InstallationIdentity) -> Mapping[str, Any]: ...


@runtime_checkable
class TemplateLifecyclePort(Protocol):
    def preview(self, command: LifecycleCommand) -> Mapping[str, Any]: ...

    def execute_once(self, command: LifecycleCommand) -> LifecycleReceipt: ...

    def readback(self, identity: InstallationIdentity) -> LifecycleReadback: ...

    def reconcile(self, identity: InstallationIdentity) -> LifecycleReadback: ...


@runtime_checkable
class TransactionalOutboxPort(Protocol):
    def append_in_transaction(self, event: Mapping[str, Any]) -> OutboxRecord: ...

    def claim(self, consumer_id: str, limit: int) -> Sequence[OutboxRecord]: ...

    def acknowledge(self, outbox_id: str, delivery_receipt_hash: str) -> None: ...

    def fail(self, outbox_id: str, error_code: str, retryable: bool) -> None: ...

    def replay(self, outbox_id: str, idempotency_key: str) -> OutboxRecord: ...

    def dead_letter(self, outbox_id: str, reason: str) -> None: ...


@runtime_checkable
class TemplateMigrationPort(Protocol):
    def dry_run(
        self, identity: InstallationIdentity, target_version: str
    ) -> Mapping[str, Any]: ...

    def backup(self, identity: InstallationIdentity) -> Mapping[str, Any]: ...

    def apply_once(
        self, command: LifecycleCommand, migration_ids: Sequence[str]
    ) -> Mapping[str, Any]: ...

    def readback(
        self, identity: InstallationIdentity, migration_ids: Sequence[str]
    ) -> Mapping[str, Any]: ...

    def rollback(
        self, command: LifecycleCommand, backup_receipt_id: str
    ) -> Mapping[str, Any]: ...

    def restore(
        self, command: LifecycleCommand, backup_receipt_id: str
    ) -> Mapping[str, Any]: ...

    def receipt(self, transaction_id: str, readback_hash: str) -> LifecycleReceipt: ...


@runtime_checkable
class OpenJiuwenRuntimePort(Protocol):
    def health(self) -> Mapping[str, Any]: ...

    def start(self, request: RuntimeRequest) -> RuntimeReceipt: ...

    def interrupt(self, runtime_request_id: str, reason: str) -> RuntimeReceipt: ...

    def resume(
        self, runtime_request_id: str, checkpoint_ref: str, action_hash: str
    ) -> RuntimeReceipt: ...

    def cancel(self, runtime_request_id: str, action_hash: str) -> RuntimeReceipt: ...

    def reconcile(self, runtime_request_id: str) -> RuntimeReceipt: ...


@runtime_checkable
class TemplateSDKPort(Protocol):
    def register_domain_repository(self, declaration: Mapping[str, Any]) -> None: ...

    def register_workflow(self, declaration: Mapping[str, Any]) -> None: ...

    def register_agent_team(self, declaration: Mapping[str, Any]) -> None: ...

    def register_skill(self, declaration: Mapping[str, Any]) -> None: ...

    def register_tool(self, declaration: Mapping[str, Any]) -> None: ...

    def register_policy(self, declaration: Mapping[str, Any]) -> None: ...

    def register_evaluator(self, declaration: Mapping[str, Any]) -> None: ...

    def register_memory_policy(self, declaration: Mapping[str, Any]) -> None: ...

    def register_ui_extension(self, declaration: Mapping[str, Any]) -> None: ...

    def register_report(self, declaration: Mapping[str, Any]) -> None: ...

    def register_api_route(self, declaration: Mapping[str, Any]) -> None: ...

    def register_cli_command(self, declaration: Mapping[str, Any]) -> None: ...

    def register_fixture(self, declaration: Mapping[str, Any]) -> None: ...

    def register_testing_hook(self, declaration: Mapping[str, Any]) -> None: ...

    def register_exporter(self, declaration: Mapping[str, Any]) -> None: ...
