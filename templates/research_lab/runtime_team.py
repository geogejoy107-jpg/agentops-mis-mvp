"""Event-driven Research Agent team over the shared openJiuwen runtime port."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
import re
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from template_runtime.protocols import OpenJiuwenRuntimePort, RuntimeRequest, RuntimeState

from .contracts import ResearchError, canonical_hash
from .trust import CoreReceiptVerifier, require_core_receipt


RESEARCH_AGENT_ROLES = (
    "research_lead",
    "literature_researcher",
    "protocol_planner",
    "experiment_planner",
    "training_operator",
    "failure_diagnoser",
    "metrics_analyst",
    "evidence_reviewer",
    "paper_writer",
    "memory_curator",
)


@dataclass(frozen=True, slots=True)
class TeamStep:
    role: str
    input_event: str
    output_schema: str
    tool_policy: str
    approval_policy: str

    def __post_init__(self) -> None:
        if self.role not in RESEARCH_AGENT_ROLES:
            raise ResearchError("research.invalid_agent_role", "agent role is not registered")


DEFAULT_TEAM = (
    TeamStep("research_lead", "research_lab.project.created", "research-plan/v1", "research_lab.policy.read_only", "none"),
    TeamStep("literature_researcher", "research_lab.plan.approved", "literature-evidence/v1", "research_lab.policy.deep_search", "policy"),
    TeamStep("protocol_planner", "research_lab.literature.verified", "research-protocol/v1", "research_lab.policy.no_external_write", "policy"),
    TeamStep("experiment_planner", "research_lab.protocol.frozen", "trial-matrix/v1", "research_lab.policy.no_external_write", "none"),
    TeamStep("training_operator", "research_lab.trials.queued", "job-attempt/v1", "research_lab.policy.compute", "always"),
    TeamStep("failure_diagnoser", "research_lab.attempt.failed", "failure-diagnosis/v1", "research_lab.policy.diagnostics", "none"),
    TeamStep("metrics_analyst", "research_lab.attempt.completed", "metric-analysis/v1", "research_lab.policy.read_only", "none"),
    TeamStep("evidence_reviewer", "research_lab.metrics.ready", "claim-decision/v1", "research_lab.policy.read_only", "policy"),
    TeamStep("paper_writer", "research_lab.claim.supported", "manuscript-section/v1", "research_lab.policy.no_external_write", "none"),
    TeamStep("memory_curator", "research_lab.receipt.completed", "memory-candidate/v1", "research_lab.policy.memory_candidate", "policy"),
)


class ResearchRuntimeCoordinator:
    def __init__(self, runtime: OpenJiuwenRuntimePort, governance: "ResearchRuntimeGovernancePort") -> None:
        if not isinstance(runtime, OpenJiuwenRuntimePort):
            raise TypeError("runtime must implement OpenJiuwenRuntimePort")
        self.runtime = runtime
        if not isinstance(governance, ResearchRuntimeGovernancePort):
            raise TypeError("governance must implement ResearchRuntimeGovernancePort")
        self.governance = governance

    def health(self) -> Mapping[str, Any]:
        observed = dict(self.runtime.health())
        if observed.get("state") not in {"ready", "degraded", "unavailable"}:
            raise ResearchError("research.runtime_health_invalid", "runtime health must be explicit")
        if observed.get("state") == "ready" and not observed.get("upstream_version"):
            raise ResearchError("research.runtime_false_ready", "ready runtime must report pinned upstream version")
        return observed
    def dispatch(self, request: RuntimeRequest, *, input_event: str) -> Mapping[str, Any]:
        matching = [step for step in DEFAULT_TEAM if step.input_event == input_event]
        if len(matching) != 1:
            raise ResearchError("research.workflow_event_unhandled", "event must map to exactly one team step")
        health = self.health()
        if health["state"] != "ready":
            result = {"state": "unavailable", "reason_code": "openjiuwen_runtime_unavailable", "input_event": input_event, "health": health}
            return {**result, "receipt_hash": canonical_hash(result)}
        receipt = self.runtime.start(request)
        expected_schema = matching[0].output_schema
        if (
            receipt.runtime_request_id != request.runtime_request_id
            or receipt.provider != request.provider
            or receipt.model != request.model
            or receipt.output_schema_version != expected_schema
        ):
            raise ResearchError("research.runtime_receipt_mismatch", "runtime receipt must bind request, provider, model and expected structured output schema")
        if receipt.state in {RuntimeState.COMPLETED, RuntimeState.RUNNING, RuntimeState.WAITING_APPROVAL} and receipt.upstream_version != health["upstream_version"]:
            raise ResearchError("research.runtime_version_drift", "runtime receipt version differs from health pin")
        if not re.fullmatch(r"[0-9a-f]{64}", receipt.receipt_hash):
            raise ResearchError("research.runtime_receipt_invalid", "runtime receipt hash is invalid")
        verification = self.governance.verify_runtime_receipt(request=request, receipt=receipt, role=matching[0].role, expected_output_schema=expected_schema)
        if verification.get("verified") is not True:
            raise ResearchError("research.runtime_receipt_unverified", "MIS Core did not verify the full runtime request/receipt binding")
        domain_receipt = None
        if receipt.state is RuntimeState.COMPLETED:
            if not receipt.output_ref:
                raise ResearchError("research.runtime_output_missing", "completed runtime must return a governed output reference")
            domain_receipt = self.governance.consume_runtime_output(request=request, role=matching[0].role, output_ref=receipt.output_ref, runtime_receipt_hash=receipt.receipt_hash)
            if domain_receipt.get("committed") is not True or not domain_receipt.get("outbox_receipt_hash"):
                raise ResearchError("research.runtime_output_uncommitted", "runtime output must drive an atomic domain write and outbox event")
        return {"state": receipt.state.value, "role": matching[0].role, "runtime_receipt_id": receipt.runtime_receipt_id, "checkpoint_ref": receipt.checkpoint_ref, "event_ids": list(receipt.event_ids), "approval_ids": list(receipt.approval_ids), "cost_usd": receipt.cost_usd, "domain_receipt": domain_receipt, "receipt_hash": receipt.receipt_hash}

    def resume(self, runtime_request_id: str, checkpoint_ref: str, action_hash: str) -> Mapping[str, Any]:
        authorization = self.governance.authorize_runtime_resume(runtime_request_id=runtime_request_id, checkpoint_ref=checkpoint_ref, action_hash=action_hash)
        if authorization.get("decision") != "allow" or authorization.get("executed_once") is not True or not authorization.get("receipt_hash"):
            raise ResearchError("research.runtime_resume_denied", "Core PreparedAction/Approval readback denied runtime resume")
        receipt = self.runtime.resume(runtime_request_id, checkpoint_ref, action_hash)
        if receipt.runtime_request_id != runtime_request_id or receipt.checkpoint_ref != checkpoint_ref:
            raise ResearchError("research.runtime_resume_invalid", "resume receipt does not bind request and checkpoint")
        if receipt.state not in {RuntimeState.RESUMING, RuntimeState.RUNNING, RuntimeState.COMPLETED, RuntimeState.FAILED}:
            raise ResearchError("research.runtime_resume_invalid", "resume returned an invalid state")
        self.governance.verify_resume_receipt(runtime_request_id=runtime_request_id, checkpoint_ref=checkpoint_ref, action_hash=action_hash, receipt=receipt, authorization=authorization)
        if receipt.state is RuntimeState.COMPLETED and not receipt.output_ref:
            raise ResearchError("research.runtime_output_missing", "completed resumed runtime must return a governed output reference")
        return {"state": receipt.state.value, "runtime_receipt_id": receipt.runtime_receipt_id, "authorization_receipt_hash": authorization["receipt_hash"], "receipt_hash": receipt.receipt_hash}


@runtime_checkable
class ResearchRuntimeGovernancePort(Protocol):
    def verify_runtime_receipt(self, *, request: RuntimeRequest, receipt: Any, role: str, expected_output_schema: str) -> Mapping[str, Any]: ...
    def consume_runtime_output(self, *, request: RuntimeRequest, role: str, output_ref: str, runtime_receipt_hash: str) -> Mapping[str, Any]: ...
    def authorize_runtime_resume(self, *, runtime_request_id: str, checkpoint_ref: str, action_hash: str) -> Mapping[str, Any]: ...
    def verify_resume_receipt(self, *, runtime_request_id: str, checkpoint_ref: str, action_hash: str, receipt: Any, authorization: Mapping[str, Any]) -> Mapping[str, Any]: ...


@runtime_checkable
class CoreRuntimeDomainPort(Protocol):
    def verify_runtime_receipt_readback(self, *, request: RuntimeRequest, receipt: Mapping[str, Any], role: str, expected_output_schema: str, request_hash: str) -> Mapping[str, Any]: ...
    def read_runtime_output(self, *, output_ref: str, workspace_id: str, project_id: str, run_id: str) -> Mapping[str, Any]: ...
    def commit_runtime_domain_output_and_event(self, *, request: RuntimeRequest, role: str, output: Mapping[str, Any], runtime_receipt_hash: str, idempotency_key: str) -> Mapping[str, Any]: ...
    def authorize_runtime_resume_once(self, *, runtime_request_id: str, checkpoint_ref: str, action_hash: str) -> Mapping[str, Any]: ...
    def verify_runtime_resume_receipt_readback(self, *, runtime_request_id: str, checkpoint_ref: str, action_hash: str, receipt: Mapping[str, Any], authorization_receipt_hash: str) -> Mapping[str, Any]: ...


class CoreResearchRuntimeGovernance:
    """Concrete MIS Core adapter: governed runtime output atomically drives domain state."""

    def __init__(self, core: CoreRuntimeDomainPort, trust: CoreReceiptVerifier) -> None:
        if not isinstance(core, CoreRuntimeDomainPort):
            raise TypeError("core must implement CoreRuntimeDomainPort")
        self.core = core
        self.trust = trust

    def consume_runtime_output(self, *, request: RuntimeRequest, role: str, output_ref: str, runtime_receipt_hash: str) -> Mapping[str, Any]:
        output = dict(self.core.read_runtime_output(output_ref=output_ref, workspace_id=request.workspace_id, project_id=request.project_id, run_id=request.run_id))
        if output.get("artifact_id") != output_ref or output.get("run_id") != request.run_id or output.get("sha256_verified") is not True or output.get("output_schema") != next(step.output_schema for step in DEFAULT_TEAM if step.role == role):
            raise ResearchError("research.runtime_output_readback_invalid", "runtime output Artifact does not bind Run, role and structured schema")
        key = f"research_lab:runtime-output:{request.runtime_request_id}:{runtime_receipt_hash}"
        receipt = require_core_receipt(self.core.commit_runtime_domain_output_and_event(request=request, role=role, output=output, runtime_receipt_hash=runtime_receipt_hash, idempotency_key=key), trust=self.trust, purpose="research.runtime-output-commit/v1", bindings={"idempotency_key": key, "run_id": request.run_id, "runtime_receipt_hash": runtime_receipt_hash, "output_ref": output_ref, "committed": True})
        if receipt.get("committed") is not True or receipt.get("idempotency_key") != key or receipt.get("run_id") != request.run_id or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("outbox_receipt_hash") or "")):
            raise ResearchError("research.runtime_output_uncommitted", "Core did not atomically commit runtime output and outbox event")
        return receipt

    def authorize_runtime_resume(self, *, runtime_request_id: str, checkpoint_ref: str, action_hash: str) -> Mapping[str, Any]:
        receipt = dict(self.core.authorize_runtime_resume_once(runtime_request_id=runtime_request_id, checkpoint_ref=checkpoint_ref, action_hash=action_hash))
        receipt = require_core_receipt(receipt, trust=self.trust, purpose="research.runtime-resume-authorization/v1", bindings={"runtime_request_id": runtime_request_id, "checkpoint_ref": checkpoint_ref, "action_hash": action_hash, "decision": "allow", "executed_once": True})
        if receipt.get("runtime_request_id") != runtime_request_id or receipt.get("checkpoint_ref") != checkpoint_ref or receipt.get("action_hash") != action_hash:
            raise ResearchError("research.runtime_resume_denied", "Core resume receipt does not bind request, checkpoint and action")
        return receipt
    def verify_resume_receipt(self, *, runtime_request_id: str, checkpoint_ref: str, action_hash: str, receipt: Any, authorization: Mapping[str, Any]) -> Mapping[str, Any]:
        document = asdict(receipt)
        for field in ("state", "error_code"):
            value = document.get(field)
            document[field] = value.value if hasattr(value, "value") else value
        document_hash = canonical_hash(document)
        observed = self.core.verify_runtime_resume_receipt_readback(runtime_request_id=runtime_request_id, checkpoint_ref=checkpoint_ref, action_hash=action_hash, receipt=document, authorization_receipt_hash=str(authorization["receipt_hash"]))
        verified = require_core_receipt(observed, trust=self.trust, purpose="research.runtime-resume-receipt/v1", bindings={"runtime_request_id": runtime_request_id, "checkpoint_ref": checkpoint_ref, "action_hash": action_hash, "runtime_receipt_hash": receipt.receipt_hash, "runtime_receipt_document_hash": document_hash, "authorization_receipt_hash": authorization["receipt_hash"], "state": document["state"], "output_ref": document.get("output_ref"), "verified": True})
        if receipt.state is RuntimeState.COMPLETED and (verified.get("output_committed") is not True or not re.fullmatch(r"[0-9a-f]{64}", str(verified.get("outbox_receipt_hash") or ""))):
            raise ResearchError("research.runtime_output_uncommitted", "completed resumed runtime output must be atomically committed by Core")
        return verified
    def verify_runtime_receipt(self, *, request: RuntimeRequest, receipt: Any, role: str, expected_output_schema: str) -> Mapping[str, Any]:
        request_document = asdict(request)
        request_hash = canonical_hash(request_document)
        receipt_document = asdict(receipt)
        for field in ("state", "error_code"):
            value = receipt_document.get(field)
            receipt_document[field] = value.value if hasattr(value, "value") else value
        receipt_document_hash = canonical_hash(receipt_document)
        observed = require_core_receipt(self.core.verify_runtime_receipt_readback(request=request, receipt=receipt_document, role=role, expected_output_schema=expected_output_schema, request_hash=request_hash), trust=self.trust, purpose="research.runtime-receipt/v1", bindings={"request_hash": request_hash, "runtime_receipt_hash": receipt.receipt_hash, "runtime_receipt_document_hash": receipt_document_hash, "runtime_request_id": request.runtime_request_id, "policy_hash": request.policy_hash, "input_ref": request.input_ref, "provider": request.provider, "model": request.model, "output_schema": expected_output_schema, "verified": True})
        if (
            observed.get("verified") is not True
            or observed.get("request_hash") != request_hash
            or observed.get("runtime_receipt_hash") != receipt.receipt_hash
            or observed.get("runtime_request_id") != request.runtime_request_id
            or observed.get("policy_hash") != request.policy_hash
            or observed.get("input_ref") != request.input_ref
            or observed.get("provider") != request.provider
            or observed.get("model") != request.model
            or observed.get("output_schema") != expected_output_schema
            or not observed.get("audit_id")
        ):
            raise ResearchError("research.runtime_receipt_unverified", "MIS Core runtime receipt attestation is incomplete or mismatched")
        return observed


research_runtime_coordinator = ResearchRuntimeCoordinator
