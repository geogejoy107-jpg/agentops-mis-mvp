"""Immutable Research Lab domain contracts and state machines."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class ResearchError(ValueError):
    """Stable fail-closed domain error with a machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ExperimentStage(str, Enum):
    SMOKE = "smoke"
    REPRODUCTION = "reproduction"
    PILOT = "pilot"
    SEARCH = "search"
    CONFIRMATORY = "confirmatory"
    ABLATION = "ablation"
    ROBUSTNESS = "robustness"
    COMPLETED = "completed"

    @property
    def claim_eligible(self) -> bool:
        return self in {
            self.REPRODUCTION,
            self.CONFIRMATORY,
            self.ABLATION,
            self.ROBUSTNESS,
            self.COMPLETED,
        }


class TrialState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INVALIDATED = "invalidated"
    BLOCKED = "blocked"


class JobAttemptState(str, Enum):
    PREPARED = "prepared"
    SUBMITTED = "submitted"
    RUNNING = "running"
    DISCONNECTED = "disconnected"
    PREEMPTED = "preempted"
    RECONCILING = "reconciling"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    REMOTE_UNKNOWN = "remote_unknown"


class ClaimStatus(str, Enum):
    DRAFT = "draft"
    SUPPORTED = "supported"
    WEAK = "weak"
    CONFLICTED = "conflicted"
    INVALIDATED = "invalidated"
    REJECTED = "rejected"


TRIAL_TRANSITIONS: Mapping[TrialState, frozenset[TrialState]] = {
    TrialState.QUEUED: frozenset({TrialState.RUNNING, TrialState.CANCELLED, TrialState.BLOCKED}),
    TrialState.RUNNING: frozenset({TrialState.PAUSED, TrialState.COMPLETED, TrialState.FAILED, TrialState.CANCELLED, TrialState.BLOCKED}),
    TrialState.PAUSED: frozenset({TrialState.RUNNING, TrialState.CANCELLED, TrialState.INVALIDATED}),
    TrialState.COMPLETED: frozenset({TrialState.INVALIDATED}),
    TrialState.FAILED: frozenset({TrialState.RUNNING, TrialState.INVALIDATED}),
    TrialState.CANCELLED: frozenset(),
    TrialState.INVALIDATED: frozenset(),
    TrialState.BLOCKED: frozenset({TrialState.QUEUED, TrialState.CANCELLED, TrialState.INVALIDATED}),
}

ATTEMPT_TRANSITIONS: Mapping[JobAttemptState, frozenset[JobAttemptState]] = {
    JobAttemptState.PREPARED: frozenset({JobAttemptState.SUBMITTED, JobAttemptState.CANCELLED}),
    JobAttemptState.SUBMITTED: frozenset({JobAttemptState.RUNNING, JobAttemptState.FAILED, JobAttemptState.CANCELLED, JobAttemptState.REMOTE_UNKNOWN}),
    JobAttemptState.RUNNING: frozenset({JobAttemptState.DISCONNECTED, JobAttemptState.PREEMPTED, JobAttemptState.COMPLETED, JobAttemptState.FAILED, JobAttemptState.TIMED_OUT, JobAttemptState.CANCELLED}),
    JobAttemptState.DISCONNECTED: frozenset({JobAttemptState.RECONCILING, JobAttemptState.REMOTE_UNKNOWN}),
    JobAttemptState.PREEMPTED: frozenset({JobAttemptState.RECONCILING, JobAttemptState.CANCELLED}),
    JobAttemptState.RECONCILING: frozenset({JobAttemptState.RUNNING, JobAttemptState.COMPLETED, JobAttemptState.FAILED, JobAttemptState.REMOTE_UNKNOWN}),
    JobAttemptState.COMPLETED: frozenset(),
    JobAttemptState.FAILED: frozenset(),
    JobAttemptState.TIMED_OUT: frozenset(),
    JobAttemptState.CANCELLED: frozenset(),
    JobAttemptState.REMOTE_UNKNOWN: frozenset({JobAttemptState.RECONCILING, JobAttemptState.CANCELLED}),
}

_MACHINE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_id(value: str, field: str) -> str:
    if not isinstance(value, str) or not _MACHINE_ID.fullmatch(value):
        raise ResearchError("research.invalid_id", f"{field} must be a safe Core/domain id")
    return value


def require_sha256(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ResearchError("research.invalid_hash", f"{field} must be lowercase sha256")
    return value


def transition_trial(current: str, target: str) -> TrialState:
    try:
        source, destination = TrialState(current), TrialState(target)
    except ValueError as exc:
        raise ResearchError("research.invalid_trial_state", "unknown trial state") from exc
    if destination not in TRIAL_TRANSITIONS[source]:
        raise ResearchError("research.invalid_trial_transition", f"invalid trial transition {source.value}->{destination.value}")
    return destination


def transition_attempt(current: str, target: str) -> JobAttemptState:
    try:
        source, destination = JobAttemptState(current), JobAttemptState(target)
    except ValueError as exc:
        raise ResearchError("research.invalid_attempt_state", "unknown attempt state") from exc
    if destination not in ATTEMPT_TRANSITIONS[source]:
        raise ResearchError("research.invalid_attempt_transition", f"invalid attempt transition {source.value}->{destination.value}")
    return destination


@dataclass(frozen=True, slots=True)
class CoreRefs:
    workspace_id: str
    project_id: str
    task_id: str
    plan_id: str
    run_id: str
    actor_id: str

    def __post_init__(self) -> None:
        for field, value in asdict(self).items():
            require_id(value, field)


@dataclass(frozen=True, slots=True)
class ResearchProtocol:
    protocol_id: str
    version: int
    research_question: str
    hypothesis: str
    stage: ExperimentStage
    code_commit: str
    dataset_version: str
    environment_lock_hash: str
    primary_metric: str
    seeds: tuple[int, ...]
    configuration: Mapping[str, Any]
    previous_protocol_hash: str | None = None

    def __post_init__(self) -> None:
        from .trust import reject_untrusted_payload
        require_id(self.protocol_id, "protocol_id")
        if self.version < 1:
            raise ResearchError("research.invalid_protocol", "protocol version must be >= 1")
        if not self.research_question.strip() or not self.hypothesis.strip() or not self.primary_metric.strip():
            raise ResearchError("research.invalid_protocol", "question, hypothesis and primary metric are required")
        if not re.fullmatch(r"[0-9a-f]{40}", self.code_commit):
            raise ResearchError("research.invalid_protocol", "code_commit must be an exact 40-character git SHA")
        require_sha256(self.environment_lock_hash, "environment_lock_hash")
        if not self.dataset_version.strip():
            raise ResearchError("research.invalid_protocol", "dataset_version is required")
        if not self.seeds or len(set(self.seeds)) != len(self.seeds) or any(isinstance(seed, bool) or not isinstance(seed, int) for seed in self.seeds):
            raise ResearchError("research.invalid_protocol", "seeds must be a non-empty unique integer tuple")
        if not isinstance(self.configuration, Mapping):
            raise ResearchError("research.invalid_protocol", "configuration must be an object")
        reject_untrusted_payload(self.configuration, path="protocol.configuration")
        if self.previous_protocol_hash is not None:
            require_sha256(self.previous_protocol_hash, "previous_protocol_hash")

    @property
    def document(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "version": self.version,
            "research_question": self.research_question,
            "hypothesis": self.hypothesis,
            "stage": self.stage.value,
            "code_commit": self.code_commit,
            "dataset_version": self.dataset_version,
            "environment_lock_hash": self.environment_lock_hash,
            "primary_metric": self.primary_metric,
            "seeds": list(self.seeds),
            "configuration": dict(self.configuration),
            "previous_protocol_hash": self.previous_protocol_hash,
        }

    @property
    def protocol_hash(self) -> str:
        return canonical_hash(self.document)


def verify_protocol_immutable(stored: Mapping[str, Any], proposed: ResearchProtocol) -> None:
    stored_hash = stored.get("protocol_hash")
    if stored_hash != proposed.protocol_hash:
        raise ResearchError("research.protocol_immutable", "a frozen protocol cannot be mutated; create a new version")


def validate_comparable_protocols(protocols: Sequence[Mapping[str, Any]]) -> None:
    if not protocols:
        raise ResearchError("research.comparison_empty", "comparison requires protocols")
    fields = ("dataset_version", "environment_lock_hash", "primary_metric")
    expected = {field: protocols[0].get(field) for field in fields}
    for protocol in protocols[1:]:
        drift = [field for field in fields if protocol.get(field) != expected[field]]
        if drift:
            raise ResearchError("research.cross_protocol_incomparable", "incomparable protocol fields: " + ", ".join(drift))


def evaluate_protocol_deviation(
    *, expected: Mapping[str, Any], actual: Mapping[str, Any], allowed_fields: Sequence[str] = ()
) -> Mapping[str, Any]:
    """Diff frozen execution conditions without hiding unobserved actuals."""
    missing = sorted(key for key in expected if key not in actual)
    changed = {
        key: {"expected": expected[key], "actual": actual.get(key)}
        for key in expected
        if key in actual and expected[key] != actual[key]
    }
    unexpected = sorted(key for key in actual if key not in expected)
    unresolved = sorted(key for key in changed if key not in set(allowed_fields))
    result = {
        "status": "matched" if not missing and not unresolved else "deviated",
        "missing_actual_fields": missing,
        "changed": changed,
        "unexpected_actual_fields": unexpected,
        "allowed_changed_fields": sorted(key for key in changed if key in set(allowed_fields)),
        "unresolved_fields": unresolved,
    }
    return {**result, "deviation_hash": canonical_hash(result)}
