"""Concrete Research API operations adapter over C0-owned governed use cases."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any, Protocol, runtime_checkable

from .contracts import CoreRefs, ResearchError, canonical_hash
from .trust import CoreReceiptVerifier, reject_untrusted_payload, require_core_receipt


@runtime_checkable
class GovernedResearchOperationsPort(Protocol):
    def query_research(self, *, resource: str, refs: CoreRefs) -> Mapping[str, Any]: ...
    def execute_research_once(self, *, operation: str, request: Mapping[str, Any], refs: CoreRefs, request_hash: str) -> Mapping[str, Any]: ...


READ_RESOURCES = frozenset({"attempts/logs", "approvals", "memory", "runtime/health", "settings"})
WRITE_OPERATIONS = frozenset({
    "attempts/start", "attempts/execute", "attempts/cancel", "attempts/reconcile",
    "claims/decide", "evidence/invalidate", "literature/search", "budgets/evaluate",
    "runtime/dispatch", "runtime/resume", "memory/candidate", "migration/dry-run",
    "migration/apply", "migration/restore", "exports/bdci",
})


class ResearchOperationsAdapter:
    """Fail-closed bridge used by ResearchAPI; C0 injects its real Core use cases."""

    def __init__(self, core: GovernedResearchOperationsPort, trust: CoreReceiptVerifier) -> None:
        if not isinstance(core, GovernedResearchOperationsPort):
            raise TypeError("core must implement GovernedResearchOperationsPort")
        self.core = core
        self.trust = trust

    def query(self, *, resource: str, refs: CoreRefs) -> Mapping[str, Any]:
        if resource not in READ_RESOURCES and not re.fullmatch(r"attempts/[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}/logs", resource):
            raise ResearchError("research.operation_invalid", "Research read operation is not registered")
        observed = dict(self.core.query_research(resource=resource, refs=refs))
        if observed.get("resource") != resource or observed.get("workspace_id") != refs.workspace_id or observed.get("project_id") != refs.project_id:
            raise ResearchError("research.operation_readback_mismatch", "Research readback does not bind Core scope")
        return observed

    def execute(self, *, operation: str, body: Mapping[str, Any], refs: CoreRefs) -> Mapping[str, Any]:
        if operation not in WRITE_OPERATIONS:
            raise ResearchError("research.operation_invalid", "Research write operation is not registered")
        if not str(body.get("idempotency_key") or ""):
            raise ResearchError("research.idempotency_key_missing", "governed operation requires an idempotency key")
        reject_untrusted_payload(body, path=f"operation.{operation}")
        request = {"operation": operation, "body": dict(body), "workspace_id": refs.workspace_id, "project_id": refs.project_id, "task_id": refs.task_id, "plan_id": refs.plan_id, "run_id": refs.run_id, "actor_id": refs.actor_id}
        request_hash = canonical_hash(request)
        receipt = dict(self.core.execute_research_once(operation=operation, request=request, refs=refs, request_hash=request_hash))
        return require_core_receipt(receipt, trust=self.trust, purpose="research.operation-execute/v1", bindings={"request_hash": request_hash, "operation": operation, "run_id": refs.run_id, "committed": True})
