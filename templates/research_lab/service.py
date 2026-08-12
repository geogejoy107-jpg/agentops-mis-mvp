"""Research Lab application service over MIS Core-backed repositories."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any, Callable

from .contracts import (
    CoreRefs,
    JobAttemptState,
    ResearchError,
    ResearchProtocol,
    TrialState,
    canonical_hash,
    require_sha256,
    transition_attempt,
    transition_trial,
    verify_protocol_immutable,
)
from .evidence import ClaimDecision, EvidenceGraph, evaluate_claim
from .repository import ResearchRepository
from .trust import reject_untrusted_payload


class ResearchService:
    """Transactional use cases; MIS Core supplies persistence and audit receipts."""

    def __init__(self, repository: ResearchRepository, *, now: Callable[[], str]) -> None:
        self.repository = repository
        self._now = now

    @staticmethod
    def _id(prefix: str, value: Mapping[str, Any]) -> str:
        return f"{prefix}_{canonical_hash(value)[:20]}"

    def create_project(self, *, refs: CoreRefs, name: str, research_contract: Mapping[str, Any], idempotency_key: str) -> Mapping[str, Any]:
        if not name.strip() or not isinstance(research_contract, Mapping):
            raise ResearchError("research.invalid_project", "name and research contract are required")
        reject_untrusted_payload(research_contract, path="research_contract")
        project_id = self._id("rsp", {"core_project": refs.project_id, "name": name})
        record = {
            "research_project_id": project_id,
            "name": name.strip(),
            "research_contract": dict(research_contract),
            "status": "active",
            "created_at": self._now(),
            "idempotency_key": idempotency_key,
        }
        return self.repository.put_many(refs=refs, operations=({"kind": "research_project", "record_id": project_id, "value": record},), events=({"event_type": "project.created", "event_id": self._id("evt", {"op": "project", "key": idempotency_key}), "idempotency_key": idempotency_key, "sequence": 0, "payload": {"research_project_id": project_id, "record_hash": canonical_hash(record)}, "occurred_at": self._now()},))[0]

    def record_domain_object(
        self,
        *,
        refs: CoreRefs,
        kind: str,
        record_id: str,
        value: Mapping[str, Any],
        idempotency_key: str,
        expected_version: int | None = None,
    ) -> Mapping[str, Any]:
        """Persist non-authority scientific objects with strict kind allowlist."""
        kinds = {
            "research_contract",
            "research_question",
            "literature_evidence",
            "compute_target",
            "checkpoint",
            "research_artifact",
        }
        if kind not in kinds:
            raise ResearchError("research.invalid_record_kind", "domain object kind is not registered")
        data = dict(value)
        reject_untrusted_payload(data, path=kind)
        if kind in {"checkpoint", "research_artifact"}:
            require_sha256(str(data.get("sha256") or ""), "sha256")
        if kind in {"checkpoint", "research_artifact"}:
            core_artifact_id = str(data.get("artifact_id") or "")
            core_artifact = self.repository.require_core(authority="artifact", record_id=core_artifact_id, refs=refs)
            if core_artifact.get("sha256") != data["sha256"] or core_artifact.get("sha256_verified") is not True:
                raise ResearchError("research.artifact_core_readback_invalid", "Research Artifact metadata must wrap a verified MIS Core Artifact")
        if kind == "checkpoint":
            required = {"protocol_hash", "code_commit", "step", "container_receipt_hash", "compatibility"}
            if required - data.keys() or not re.fullmatch(r"[0-9a-f]{40}", str(data.get("code_commit") or "")):
                raise ResearchError("research.checkpoint_readback_invalid", "Checkpoint requires Protocol, commit, container validation and compatibility readback")
            require_sha256(str(data.get("protocol_hash") or ""), "protocol_hash")
            require_sha256(str(data.get("container_receipt_hash") or ""), "container_receipt_hash")
            if isinstance(data.get("step"), bool) or not isinstance(data.get("step"), int) or int(data["step"]) < 0 or not isinstance(data.get("compatibility"), Mapping):
                raise ResearchError("research.checkpoint_readback_invalid", "Checkpoint step and compatibility are invalid")
        if kind == "compute_target" and data.get("state") not in {"ready", "degraded", "unavailable", "disabled"}:
            raise ResearchError("research.compute_target_state_invalid", "compute target state must be explicit")
        if kind == "literature_evidence":
            if data.get("verification_status") not in {"verified", "conflicted", "unavailable"}:
                raise ResearchError("research.literature_status_invalid", "literature verification status must be explicit")
            if data.get("verification_status") == "verified":
                source_artifact_id = str(data.get("source_artifact_id") or "")
                source = self.repository.require_core(authority="artifact", record_id=source_artifact_id, refs=refs)
                require_sha256(str(data.get("verification_receipt_hash") or ""), "verification_receipt_hash")
                if source.get("sha256_verified") is not True or source.get("run_id") != refs.run_id or not (data.get("doi") or data.get("arxiv_id")):
                    raise ResearchError("research.literature_core_readback_invalid", "verified literature must bind an identifier and verified MIS Core source Artifact")
        data.update({"idempotency_key": idempotency_key, "updated_at": self._now()})
        return self.repository.put(kind=kind, record_id=record_id, refs=refs, value=data, expected_version=expected_version)

    def freeze_protocol(self, *, refs: CoreRefs, experiment_id: str, protocol: ResearchProtocol, idempotency_key: str) -> Mapping[str, Any]:
        existing = self.repository.get(kind="protocol", record_id=protocol.protocol_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        value = {**protocol.document, "experiment_id": experiment_id, "protocol_hash": protocol.protocol_hash, "frozen": True, "frozen_at": self._now(), "idempotency_key": idempotency_key}
        if existing is not None:
            verify_protocol_immutable(existing, protocol)
            return existing
        return self.repository.put_many(refs=refs, operations=({"kind": "protocol", "record_id": protocol.protocol_id, "value": value},), events=({"event_type": "protocol.frozen", "event_id": self._id("evt", {"op": "protocol", "key": idempotency_key}), "idempotency_key": idempotency_key, "sequence": 0, "payload": {"protocol_id": protocol.protocol_id, "experiment_id": experiment_id, "protocol_hash": protocol.protocol_hash}, "occurred_at": self._now()},))[0]

    def create_experiment(self, *, refs: CoreRefs, research_project_id: str, question_id: str, protocol: ResearchProtocol, idempotency_key: str) -> Mapping[str, Any]:
        self.repository.require(kind="research_project", record_id=research_project_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        self.repository.require(kind="research_question", record_id=question_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        experiment_id = self._id("exp", {"project": research_project_id, "protocol": protocol.protocol_hash})
        value = {
            "experiment_id": experiment_id,
            "research_project_id": research_project_id,
            "research_question_id": question_id,
            "protocol_id": protocol.protocol_id,
            "protocol_hash": protocol.protocol_hash,
            "stage": protocol.stage.value,
            "status": "planned",
            "created_at": self._now(),
            "idempotency_key": idempotency_key,
        }
        existing = self.repository.get(kind="protocol", record_id=protocol.protocol_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        if existing is not None:
            verify_protocol_immutable(existing, protocol)
            operations = ({"kind": "experiment", "record_id": experiment_id, "value": value},)
            events = ()
        else:
            protocol_key = f"{idempotency_key}:protocol"
            protocol_value = {**protocol.document, "experiment_id": experiment_id, "protocol_hash": protocol.protocol_hash, "frozen": True, "frozen_at": self._now(), "idempotency_key": protocol_key}
            operations = ({"kind": "experiment", "record_id": experiment_id, "value": value}, {"kind": "protocol", "record_id": protocol.protocol_id, "value": protocol_value})
            events = ({"event_type": "protocol.frozen", "event_id": self._id("evt", {"op": "protocol", "key": protocol_key}), "idempotency_key": protocol_key, "sequence": 0, "payload": {"protocol_id": protocol.protocol_id, "experiment_id": experiment_id, "protocol_hash": protocol.protocol_hash}, "occurred_at": self._now()},)
        return self.repository.put_many(refs=refs, operations=operations, events=events)[0]

    def create_trials(self, *, refs: CoreRefs, experiment_id: str, protocol: ResearchProtocol, matrix: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
        if not matrix:
            raise ResearchError("research.empty_trial_matrix", "at least one trial is required")
        experiment = self.repository.require(kind="experiment", record_id=experiment_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        frozen = self.repository.require(kind="protocol", record_id=protocol.protocol_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        verify_protocol_immutable(frozen, protocol)
        if experiment.get("protocol_hash") != protocol.protocol_hash or frozen.get("experiment_id") != experiment_id:
            raise ResearchError("research.trial_protocol_mismatch", "Trial matrix must bind the Experiment's frozen Protocol")
        operations: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        for parameters in matrix:
            seed = parameters.get("seed")
            if seed not in protocol.seeds:
                raise ResearchError("research.seed_outside_protocol", "trial seed is not frozen in protocol")
            trial_id = self._id("trl", {"experiment": experiment_id, "parameters": dict(parameters)})
            if trial_id in seen:
                raise ResearchError("research.duplicate_trial", "duplicate scientific condition")
            seen.add(trial_id)
            value = {"trial_id": trial_id, "experiment_id": experiment_id, "protocol_id": protocol.protocol_id, "protocol_hash": protocol.protocol_hash, "seed": seed, "parameters": dict(parameters), "state": TrialState.QUEUED.value, "attempt_count": 0, "created_at": self._now()}
            operations.append({"kind": "trial", "record_id": trial_id, "value": value})
        return tuple(self.repository.put_many(refs=refs, operations=operations))

    def transition_trial(self, *, refs: CoreRefs, trial_id: str, target: str, expected_version: int, reason: str | None = None) -> Mapping[str, Any]:
        current = self.repository.require(kind="trial", record_id=trial_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        state = transition_trial(str(current["state"]), target)
        value = {**dict(current), "state": state.value, "updated_at": self._now()}
        value["idempotency_key"] = self.repository.idempotency_key(
            "trial_transition", {"trial_id": trial_id, "target": state.value, "version": expected_version}
        )
        if reason:
            value["state_reason"] = reason
        return self.repository.put(kind="trial", record_id=trial_id, refs=refs, value=value, expected_version=expected_version)

    def start_job_attempt(self, *, refs: CoreRefs, trial_id: str, executor: str, compute_target_id: str, idempotency_key: str) -> Mapping[str, Any]:
        trial = self.repository.require(kind="trial", record_id=trial_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        if trial["state"] not in {TrialState.QUEUED.value, TrialState.RUNNING.value, TrialState.FAILED.value}:
            raise ResearchError("research.trial_not_runnable", "trial is not in a runnable state")
        prior = self.repository.list(
            kind="job_attempt", workspace_id=refs.workspace_id, project_id=refs.project_id, filters={"trial_id": trial_id}
        )
        replay = next((item for item in prior if item.get("idempotency_key") == idempotency_key), None)
        if replay is not None:
            return replay
        if any(item.get("state") in {"prepared", "submitted", "running", "disconnected", "reconciling", "remote_unknown"} for item in prior):
            raise ResearchError("research.concurrent_attempt", "trial already has a non-terminal attempt")
        attempt_number = len(prior) + 1
        admission = self.repository.admit_attempt(refs=refs, executor=executor, compute_target_id=compute_target_id, trial_id=trial_id, attempt_number=attempt_number)
        attempt_id = self._id("att", {"trial": trial_id, "attempt": attempt_number, "key": idempotency_key})
        value = {
            "job_attempt_id": attempt_id,
            "trial_id": trial_id,
            "experiment_id": trial["experiment_id"],
            "protocol_id": trial["protocol_id"],
            "protocol_hash": trial["protocol_hash"],
            "attempt_number": attempt_number,
            "executor": executor,
            "compute_target_id": compute_target_id,
            "state": JobAttemptState.PREPARED.value,
            "heartbeat_at": None,
            "checkpoint_id": None,
            "created_at": self._now(),
            "idempotency_key": idempotency_key,
            "admission_receipt_hash": admission["receipt_hash"],
        }
        trial_version = int(trial.get("version", 0))
        reserved_trial = {
            **dict(trial),
            "state": TrialState.RUNNING.value,
            "active_attempt_id": attempt_id,
            "attempt_count": attempt_number,
            "updated_at": self._now(),
            "idempotency_key": self.repository.idempotency_key(
                "reserve_attempt", {"trial_id": trial_id, "attempt_id": attempt_id}
            ),
        }
        try:
            receipts = self.repository.put_many(
                refs=refs,
                operations=(
                    {"kind": "trial", "record_id": trial_id, "expected_version": trial_version, "value": reserved_trial},
                    {"kind": "job_attempt", "record_id": attempt_id, "expected_version": None, "value": value},
                ),
            )
        except ValueError as exc:
            raise ResearchError("research.concurrent_attempt", "trial attempt reservation conflicted") from exc
        return receipts[1]

    def transition_attempt(self, *, refs: CoreRefs, attempt_id: str, target: str, expected_version: int, receipt: Mapping[str, Any]) -> Mapping[str, Any]:
        current = self.repository.require(kind="job_attempt", record_id=attempt_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        state = transition_attempt(str(current["state"]), target)
        if state is not JobAttemptState.PREPARED:
            expected_operations = {
                JobAttemptState.SUBMITTED: {"submit", "resume"},
                JobAttemptState.RUNNING: {"status", "reconcile"},
                JobAttemptState.DISCONNECTED: {"status"},
                JobAttemptState.PREEMPTED: {"status", "reconcile"},
                JobAttemptState.RECONCILING: {"reconcile"},
                JobAttemptState.COMPLETED: {"collect", "status", "reconcile"},
                JobAttemptState.FAILED: {"status", "collect", "reconcile"},
                JobAttemptState.TIMED_OUT: {"status", "reconcile"},
                JobAttemptState.CANCELLED: {"cancel"},
                JobAttemptState.REMOTE_UNKNOWN: {"status", "reconcile"},
            }[state]
            if receipt.get("operation") not in expected_operations:
                raise ResearchError("research.execution_receipt_mismatch", "executor receipt does not bind Attempt, executor, request and Core admission")
            receipt = self.repository.verify_core_receipt(receipt, purpose="research.execution-receipt/v1", bindings={"attempt_id": attempt_id, "executor": current.get("executor"), "state": state.value, "admission_receipt_hash": current.get("admission_receipt_hash"), "workspace_id": refs.workspace_id, "project_id": refs.project_id, "run_id": refs.run_id})
            if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("request_hash") or "")) or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("authorization_receipt_hash") or "")):
                raise ResearchError("research.execution_receipt_mismatch", "executor receipt does not bind request and authorization")
        value = {**dict(current), "state": state.value, "executor_receipt": dict(receipt), "updated_at": self._now()}
        value["idempotency_key"] = self.repository.idempotency_key(
            "attempt_transition",
            {"attempt_id": attempt_id, "target": state.value, "version": expected_version, "receipt_hash": receipt.get("receipt_hash")},
        )
        if state is JobAttemptState.RUNNING:
            value["heartbeat_at"] = self._now()
        if state in {JobAttemptState.COMPLETED, JobAttemptState.FAILED, JobAttemptState.TIMED_OUT, JobAttemptState.CANCELLED}:
            trial_id = str(current["trial_id"])
            trial = self.repository.require(kind="trial", record_id=trial_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
            trial_state = {
                JobAttemptState.COMPLETED: TrialState.COMPLETED,
                JobAttemptState.FAILED: TrialState.FAILED,
                JobAttemptState.TIMED_OUT: TrialState.FAILED,
                JobAttemptState.CANCELLED: TrialState.CANCELLED,
            }[state]
            cleared_trial = {
                **dict(trial),
                "state": trial_state.value,
                "active_attempt_id": None,
                "updated_at": self._now(),
                "idempotency_key": self.repository.idempotency_key(
                    "attempt_terminal_trial",
                    {"trial_id": trial_id, "attempt_id": attempt_id, "attempt_state": state.value},
                ),
            }
            receipts = self.repository.put_many(
                refs=refs,
                operations=(
                    {"kind": "job_attempt", "record_id": attempt_id, "expected_version": expected_version, "value": value},
                    {"kind": "trial", "record_id": trial_id, "expected_version": int(trial["version"]), "value": cleared_trial},
                ),
            )
            return receipts[0]
        return self.repository.put(kind="job_attempt", record_id=attempt_id, refs=refs, value=value, expected_version=expected_version)

    def record_metric(self, *, refs: CoreRefs, attempt_id: str, name: str, value: float, step: int, artifact_id: str, artifact_sha256: str) -> Mapping[str, Any]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or step < 0:
            raise ResearchError("research.invalid_metric", "metric must be numeric and step non-negative")
        require_sha256(artifact_sha256, "artifact_sha256")
        self.repository.require(kind="job_attempt", record_id=attempt_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
        artifact = self.repository.require_core(authority="artifact", record_id=artifact_id, refs=refs)
        if artifact.get("run_id") != refs.run_id or artifact.get("sha256") != artifact_sha256 or artifact.get("sha256_verified") is not True:
            raise ResearchError("research.metric_artifact_unverified", "metric Artifact must read back from MIS Core with matching verified sha256")
        metric_id = self._id("met", {"attempt": attempt_id, "name": name, "step": step})
        record = {"metric_snapshot_id": metric_id, "job_attempt_id": attempt_id, "name": name, "value": float(value), "step": step, "artifact_id": artifact_id, "artifact_sha256": artifact_sha256, "recorded_at": self._now()}
        return self.repository.put(kind="metric_snapshot", record_id=metric_id, refs=refs, value=record)

    def decide_claim(self, *, refs: CoreRefs, claim_id: str, statement: str, stage: str, evidence: Sequence[Mapping[str, Any]], reviewer_id: str, expected_version: int | None = None) -> tuple[Mapping[str, Any], ClaimDecision]:
        if not statement.strip():
            raise ResearchError("research.claim_statement_missing", "Claim statement is required")
        if reviewer_id == refs.actor_id:
            raise ResearchError("research.self_review_forbidden", "Claim reviewer must be independent from the acting agent")
        reviewer = self.repository.require_core(authority="identity", record_id=reviewer_id, refs=refs)
        permission_id = str(reviewer.get("claim_review_permission_id") or "")
        permission = self.repository.require_core(authority="permission", record_id=permission_id, refs=refs)
        if permission.get("action") != "research_lab.permission.claim.review" or permission.get("decision") != "allow":
            raise ResearchError("research.claim_review_forbidden", "MIS Core reviewer permission readback denied")
        verified_evidence = []
        statement_hash = canonical_hash({"statement": statement.strip()})
        frozen_stage: str | None = None
        for item in evidence:
            observed = dict(item)
            run = self.repository.require_core(authority="run", record_id=str(item.get("run_id") or ""), refs=refs)
            if item.get("run_id") != refs.run_id or run.get("run_id") != refs.run_id or run.get("status") != "completed" or run.get("plan_id") != refs.plan_id or run.get("task_id") != refs.task_id:
                raise ResearchError("research.claim_run_mismatch", "Claim evidence Run must be the completed current MIS Run")
            attempt_id = str(item.get("job_attempt_id") or "")
            attempt = self.repository.require(kind="job_attempt", record_id=attempt_id, workspace_id=refs.workspace_id, project_id=refs.project_id)
            trial = self.repository.require(kind="trial", record_id=str(attempt.get("trial_id") or ""), workspace_id=refs.workspace_id, project_id=refs.project_id)
            protocol = self.repository.require(kind="protocol", record_id=str(trial.get("protocol_id") or attempt.get("protocol_id") or ""), workspace_id=refs.workspace_id, project_id=refs.project_id)
            protocol_stage = str(protocol.get("stage") or "")
            if frozen_stage is None:
                frozen_stage = protocol_stage
            if protocol_stage != frozen_stage or stage != protocol_stage:
                raise ResearchError("research.claim_stage_mismatch", "Claim stage must be derived from one frozen Protocol")
            if (
                attempt.get("run_id") != refs.run_id
                or attempt.get("state") != JobAttemptState.COMPLETED.value
                or trial.get("trial_id") != attempt.get("trial_id")
                or trial.get("state") != TrialState.COMPLETED.value
                or trial.get("protocol_hash") != protocol.get("protocol_hash")
                or item.get("protocol_hash") != protocol.get("protocol_hash")
                or item.get("code_commit") != protocol.get("code_commit")
                or item.get("dataset_version") != protocol.get("dataset_version")
                or item.get("environment_lock_hash") != protocol.get("environment_lock_hash")
                or item.get("seed") != trial.get("seed")
                or item.get("role") != trial.get("parameters", {}).get("role")
            ):
                raise ResearchError("research.claim_protocol_binding_mismatch", "Claim evidence must bind a completed Trial/JobAttempt and its frozen Protocol")
            metric = self.repository.require_core(authority="artifact", record_id=str(item.get("metric_artifact_id") or ""), refs=refs)
            figure = self.repository.require_core(authority="artifact", record_id=str(item.get("figure_table_artifact_id") or ""), refs=refs)
            evaluation = self.repository.require_core(authority="evaluation", record_id=str(item.get("evaluation_id") or ""), refs=refs)
            if (
                metric.get("run_id") != refs.run_id
                or figure.get("run_id") != refs.run_id
                or metric.get("job_attempt_id") != attempt_id
                or figure.get("job_attempt_id") != attempt_id
                or evaluation.get("run_id") != refs.run_id
                or evaluation.get("job_attempt_id") != attempt_id
                or evaluation.get("metric_artifact_id") != item.get("metric_artifact_id")
                or evaluation.get("figure_table_artifact_id") != item.get("figure_table_artifact_id")
                or evaluation.get("reviewer_id") != reviewer_id
                or evaluation.get("claim_id") != claim_id
                or evaluation.get("claim_statement_hash") != statement_hash
                or evaluation.get("protocol_hash") != protocol.get("protocol_hash")
                or evaluation.get("metric_name") != protocol.get("primary_metric")
                or evaluation.get("metric_direction") != protocol.get("configuration", {}).get("metric_direction")
                or evaluation.get("supports_claim") is not True
                or evaluation.get("support_strength") not in {"strong", "replicated"}
            ):
                raise ResearchError("research.claim_evidence_binding_mismatch", "Artifact and Evaluation readback must bind Claim, Protocol, metric direction, Run, JobAttempt and reviewer")
            observed.update({"claim_id": claim_id, "claim_statement_hash": statement_hash, "stage": protocol_stage, "metric_name": evaluation.get("metric_name"), "metric_direction": evaluation.get("metric_direction"), "run_status": run.get("status"), "artifact_integrity": "verified" if metric.get("sha256_verified") and figure.get("sha256_verified") else "unverified", "evaluation_status": evaluation.get("status"), "evaluation_support_strength": evaluation.get("support_strength"), "reviewer_id": reviewer_id})
            verified_evidence.append(observed)
        if frozen_stage is None:
            raise ResearchError("research.claim_evidence_missing", "Claim requires evidence from a frozen Protocol")
        decision = evaluate_claim(stage=frozen_stage, evidence=verified_evidence)
        reviewed_at = self._now()
        evidence_records = []
        evidence_ids = []
        for index, item in enumerate(verified_evidence):
            evidence_id = self._id("cev", {"claim_id": claim_id, "index": index, "evidence": item})
            evidence_ids.append(evidence_id)
            evidence_records.append({"kind": "claim_evidence", "record_id": evidence_id, "value": {**dict(item), "claim_evidence_id": evidence_id, "research_claim_id": claim_id, "status": "active", "reviewed_at": reviewed_at, "idempotency_key": self.repository.idempotency_key("claim_evidence", {"claim_id": claim_id, "evidence_id": evidence_id})}})
        value = {"research_claim_id": claim_id, "statement": statement.strip(), "statement_hash": statement_hash, "protocol_hash": verified_evidence[0]["protocol_hash"], "stage": frozen_stage, "status": decision.status.value, "decision": decision.to_dict(), "claim_evidence_ids": evidence_ids, "reviewer_id": reviewer_id, "reviewed_at": reviewed_at, "idempotency_key": self.repository.idempotency_key("claim_decision", {"claim_id": claim_id, "statement_hash": statement_hash, "evidence_ids": evidence_ids})}
        receipts = self.repository.put_many(refs=refs, operations=({"kind": "research_claim", "record_id": claim_id, "expected_version": expected_version, "value": value}, *evidence_records))
        return receipts[0], decision

    def invalidate_evidence(self, *, refs: CoreRefs, root_evidence_id: str, edges: Sequence[tuple[str, str]], reason: str) -> tuple[str, ...]:
        affected = EvidenceGraph(edges).invalidate_from(root_evidence_id)
        operations = []
        for evidence_id in affected:
            matches = [(kind, value) for kind in ("claim_evidence", "research_claim", "manuscript") if (value := self.repository.get(kind=kind, record_id=evidence_id, workspace_id=refs.workspace_id, project_id=refs.project_id)) is not None]
            if len(matches) != 1:
                raise ResearchError("research.evidence_node_unresolved", "affected evidence node must resolve to exactly one registered domain kind")
            kind, current = matches[0]
            operations.append({"kind": kind, "record_id": evidence_id, "expected_version": int(current["version"]), "value": {**dict(current), "status": "invalidated", "invalidated": True, "invalidation_reason": reason, "invalidated_at": self._now()}})
        self.repository.put_many(refs=refs, operations=operations)
        return affected

    def validate_core_evidence_chain(self, *, refs: CoreRefs, artifact_ids: Sequence[str], evaluation_ids: Sequence[str]) -> Mapping[str, Any]:
        plan = self.repository.require_core(authority="plan", record_id=refs.plan_id, refs=refs)
        run = self.repository.require_core(authority="run", record_id=refs.run_id, refs=refs)
        if run.get("plan_id") != refs.plan_id or run.get("task_id") != refs.task_id:
            raise ResearchError("research.core_evidence_chain_mismatch", "MIS Run does not bind the declared Task and Plan")
        artifacts = [self.repository.require_core(authority="artifact", record_id=item, refs=refs) for item in artifact_ids]
        evaluations = [self.repository.require_core(authority="evaluation", record_id=item, refs=refs) for item in evaluation_ids]
        if any(item.get("run_id") != refs.run_id or not item.get("sha256_verified") for item in artifacts):
            raise ResearchError("research.core_evidence_chain_mismatch", "MIS Artifact readback is not bound and verified")
        if any(item.get("run_id") != refs.run_id or item.get("status") != "passed" for item in evaluations):
            raise ResearchError("research.core_evidence_chain_mismatch", "MIS Evaluation readback is not bound and passed")
        value = {"task_id": refs.task_id, "plan_id": refs.plan_id, "run_id": refs.run_id, "plan_status": plan.get("status"), "run_status": run.get("status"), "artifact_ids": list(artifact_ids), "evaluation_ids": list(evaluation_ids), "verified": True}
        return {**value, "evidence_chain_hash": canonical_hash(value)}
