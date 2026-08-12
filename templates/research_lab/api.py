"""Typed domain API controller registered by Template SDK under shared auth."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any, Callable, Protocol, runtime_checkable

from .contracts import CoreRefs, ExperimentStage, ResearchError, ResearchProtocol, canonical_hash
from .service import ResearchService


API_VERSION = "template-platform-api/v1"
ROUTE_PREFIX = "/api/v1/templates/research_lab"
RESOURCE_KINDS = {
    "projects": "research_project", "experiments": "experiment", "trials": "trial",
    "attempts": "job_attempt", "metrics": "metric_snapshot", "claims": "research_claim",
    "manuscripts": "manuscript", "literature": "literature_evidence", "checkpoints": "checkpoint",
    "compute-targets": "compute_target", "budgets": "research_contract", "receipts": "research_receipt",
}


@runtime_checkable
class ResearchOperationsPort(Protocol):
    def execute(self, *, operation: str, body: Mapping[str, Any], refs: CoreRefs) -> Mapping[str, Any]: ...
    def query(self, *, resource: str, refs: CoreRefs) -> Mapping[str, Any]: ...


ACTION_PERMISSIONS = {
    "attempts/start": "research_lab.permission.compute.local", "attempts/execute": "research_lab.permission.compute.remote",
    "attempts/cancel": "research_lab.permission.compute.remote", "attempts/reconcile": "research_lab.permission.compute.remote",
    "claims/decide": "research_lab.permission.claim.review", "evidence/invalidate": "research_lab.permission.claim.review",
    "literature/search": "research_lab.permission.experiment.write", "budgets/evaluate": "research_lab.permission.experiment.write",
    "runtime/dispatch": "research_lab.permission.experiment.write", "runtime/resume": "research_lab.permission.compute.remote",
    "memory/candidate": "research_lab.permission.experiment.write", "migration/dry-run": "research_lab.permission.read",
    "migration/apply": "research_lab.permission.compute.remote", "migration/restore": "research_lab.permission.compute.remote",
    "exports/bdci": "research_lab.permission.claim.review",
}
READ_OPERATIONS = {"attempts/logs", "approvals", "memory", "runtime/health", "settings"}


def _error_status(code: str) -> int:
    if code.endswith(("not_found", "_missing")):
        return 404
    if any(part in code for part in ("forbidden", "denied", "not_authorized")):
        return 403
    if any(part in code for part in ("concurrent", "conflict", "immutable", "mismatch", "replay")):
        return 409
    if any(part in code for part in ("unavailable", "degraded")):
        return 503
    return 422


class ResearchAPI:
    def __init__(self, service: ResearchService, authorize: Callable[[str, CoreRefs], None], health_provider: Callable[[], Mapping[str, Any]], operations: ResearchOperationsPort | None = None) -> None:
        self.service = service
        self.authorize = authorize
        self.health_provider = health_provider
        self.operations = operations

    def create_experiment(self, body: Mapping[str, Any], refs: CoreRefs) -> tuple[int, Mapping[str, Any]]:
        self.authorize("research_lab.permission.experiment.write", refs)
        try:
            protocol = ResearchProtocol(
                protocol_id=str(body["protocol_id"]),
                version=int(body["protocol_version"]),
                research_question=str(body["research_question"]),
                hypothesis=str(body["hypothesis"]),
                stage=ExperimentStage(str(body["stage"])),
                code_commit=str(body["code_commit"]),
                dataset_version=str(body["dataset_version"]),
                environment_lock_hash=str(body["environment_lock_hash"]),
                primary_metric=str(body["primary_metric"]),
                seeds=tuple(body["seeds"]),
                configuration=dict(body.get("configuration") or {}),
            )
            result = self.service.create_experiment(refs=refs, research_project_id=str(body["research_project_id"]), question_id=str(body["research_question_id"]), protocol=protocol, idempotency_key=str(body["idempotency_key"]))
            return 201, {"api_version": API_VERSION, "data": result}
        except (KeyError, TypeError, ValueError, ResearchError) as exc:
            code = exc.code if isinstance(exc, ResearchError) else "research.invalid_request"
            return _error_status(code), {"api_version": API_VERSION, "error": {"code": code, "message": str(exc)}}

    def list_records(self, *, kind: str, refs: CoreRefs) -> tuple[int, Mapping[str, Any]]:
        self.authorize("research_lab.permission.read", refs)
        allowed = set(RESOURCE_KINDS.values())
        if kind not in allowed:
            return 400, {"api_version": API_VERSION, "error": {"code": "research.invalid_record_kind"}}
        return 200, {"api_version": API_VERSION, "data": list(self.service.repository.list(kind=kind, workspace_id=refs.workspace_id, project_id=refs.project_id))}

    def health(self, refs: CoreRefs) -> tuple[int, Mapping[str, Any]]:
        self.authorize("research_lab.permission.read", refs)
        observed = dict(self.health_provider())
        state = observed.get("state")
        if state not in {"ready", "degraded", "unavailable"}:
            raise ResearchError("research.health_invalid", "health provider returned an invalid state")
        return 200, {"api_version": API_VERSION, "template": "research_lab", "version": "1.0.0", "state": state, "authority": "mis_core", "diagnostics": observed}

    def dispatch(self, *, method: str, path: str, body: Mapping[str, Any], refs: CoreRefs) -> tuple[int, Mapping[str, Any]]:
        """Concrete AppShell route adapter; shared HTTP auth supplies ``CoreRefs``."""
        if not path.startswith(ROUTE_PREFIX + "/"):
            return 404, {"api_version": API_VERSION, "error": {"code": "research.route_not_found"}}
        resource = path.removeprefix(ROUTE_PREFIX + "/").strip("/")
        if method == "GET" and resource == "health":
            return self.health(refs)
        if method == "GET" and resource in RESOURCE_KINDS:
            return self.list_records(kind=RESOURCE_KINDS[resource], refs=refs)
        parts = resource.split("/")
        if method == "GET" and len(parts) == 2 and parts[0] in {"experiments", "attempts"}:
            self.authorize("research_lab.permission.read", refs)
            kind = RESOURCE_KINDS[parts[0]]
            value = self.service.repository.get(kind=kind, record_id=parts[1], workspace_id=refs.workspace_id, project_id=refs.project_id)
            if value is None:
                return 404, {"api_version": API_VERSION, "error": {"code": "research.not_found"}}
            return 200, {"api_version": API_VERSION, "data": value}
        if method == "GET" and len(parts) == 3 and parts[0] == "experiments" and parts[2] in {"trials", "metrics"}:
            self.authorize("research_lab.permission.read", refs)
            kind = "trial" if parts[2] == "trials" else "metric_snapshot"
            values = self.service.repository.list(kind=kind, workspace_id=refs.workspace_id, project_id=refs.project_id, filters={"experiment_id": parts[1]})
            return 200, {"api_version": API_VERSION, "data": list(values)}
        if method == "GET" and len(parts) == 3 and parts[0] == "attempts" and parts[2] in {"logs", "checkpoints"}:
            self.authorize("research_lab.permission.read", refs)
            if parts[2] == "checkpoints":
                values = self.service.repository.list(kind="checkpoint", workspace_id=refs.workspace_id, project_id=refs.project_id, filters={"job_attempt_id": parts[1]})
                return 200, {"api_version": API_VERSION, "data": list(values)}
            if self.operations is None:
                return 503, {"api_version": API_VERSION, "error": {"code": "research.operation_unavailable"}}
            return 200, {"api_version": API_VERSION, "data": self.operations.query(resource=f"attempts/{parts[1]}/logs", refs=refs)}
        if method == "GET" and resource in READ_OPERATIONS:
            self.authorize("research_lab.permission.read", refs)
            if self.operations is None:
                return 503, {"api_version": API_VERSION, "error": {"code": "research.operation_unavailable"}}
            return 200, {"api_version": API_VERSION, "data": self.operations.query(resource=resource, refs=refs)}
        if method == "POST" and resource == "experiments":
            return self.create_experiment(body, refs)
        if method == "POST" and resource == "projects":
            self.authorize("research_lab.permission.experiment.write", refs)
            try:
                value = self.service.create_project(refs=refs, name=str(body["name"]), research_contract=dict(body.get("research_contract") or {}), idempotency_key=str(body["idempotency_key"]))
                return 201, {"api_version": API_VERSION, "data": value}
            except (KeyError, TypeError, ValueError, ResearchError) as exc:
                code = exc.code if isinstance(exc, ResearchError) else "research.invalid_request"
                return _error_status(code), {"api_version": API_VERSION, "error": {"code": code, "message": str(exc)}}
        if method == "POST" and resource in ACTION_PERMISSIONS:
            if self.operations is None:
                return 503, {"api_version": API_VERSION, "error": {"code": "research.operation_unavailable"}}
            self.authorize(ACTION_PERMISSIONS[resource], refs)
            try:
                value = self.operations.execute(operation=resource, body=body, refs=refs)
                supplied_hash = str(value.get("receipt_hash") or "")
                unsigned = {key: child for key, child in value.items() if key != "receipt_hash"}
                if not re.fullmatch(r"[0-9a-f]{64}", supplied_hash) or supplied_hash != canonical_hash(unsigned):
                    raise ResearchError("research.operation_receipt_missing", "governed operation requires a receipt")
                return 200, {"api_version": API_VERSION, "data": value}
            except (KeyError, TypeError, ValueError, ResearchError) as exc:
                code = exc.code if isinstance(exc, ResearchError) else "research.invalid_request"
                return _error_status(code), {"api_version": API_VERSION, "error": {"code": code, "message": str(exc)}}
        return 405, {"api_version": API_VERSION, "error": {"code": "research.route_method_not_allowed"}}


def route_contracts() -> tuple[Mapping[str, Any], ...]:
    reads = tuple({"method": "GET", "path": f"{ROUTE_PREFIX}/{resource}", "handler": "ResearchAPI.dispatch", "permission": "research_lab.permission.read"} for resource in (*RESOURCE_KINDS, "health", *sorted(READ_OPERATIONS)))
    details = tuple({"method": "GET", "path": f"{ROUTE_PREFIX}/{resource}", "handler": "ResearchAPI.dispatch", "permission": "research_lab.permission.read"} for resource in ("experiments/{experiment_id}", "experiments/{experiment_id}/trials", "attempts/{attempt_id}", "attempts/{attempt_id}/logs", "experiments/{experiment_id}/metrics", "attempts/{attempt_id}/checkpoints"))
    writes = tuple({"method": "POST", "path": f"{ROUTE_PREFIX}/{resource}", "handler": "ResearchAPI.dispatch", "permission": "research_lab.permission.experiment.write"} for resource in ("projects", "experiments"))
    actions = tuple({"method": "POST", "path": f"{ROUTE_PREFIX}/{resource}", "handler": "ResearchAPI.dispatch", "permission": permission} for resource, permission in ACTION_PERMISSIONS.items())
    return (*reads, *details, *writes, *actions)
