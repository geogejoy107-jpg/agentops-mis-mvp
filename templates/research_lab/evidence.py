"""Scientific evidence graph, integrity propagation, and Claim Gate."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contracts import ClaimStatus, ExperimentStage, ResearchError, require_sha256


REQUIRED_NUMERIC_EVIDENCE = frozenset(
    {
        "protocol_hash",
        "code_commit",
        "dataset_version",
        "environment_lock_hash",
        "seed",
        "run_id",
        "job_attempt_id",
        "metric_artifact_id",
        "figure_table_artifact_id",
        "evaluation_id",
        "reviewer_id",
        "claim_id",
        "claim_statement_hash",
        "metric_name",
        "metric_direction",
        "evaluation_support_strength",
    }
)


@dataclass(frozen=True, slots=True)
class ClaimDecision:
    status: ClaimStatus
    eligible: bool
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "evidence_ids": list(self.evidence_ids),
        }


def evaluate_claim(
    *,
    stage: str,
    evidence: Sequence[Mapping[str, Any]],
    minimum_seeds: int = 2,
    baseline_required: bool = True,
) -> ClaimDecision:
    reasons: list[str] = []
    try:
        experiment_stage = ExperimentStage(stage)
    except ValueError:
        experiment_stage = ExperimentStage.SMOKE
        reasons.append("unknown_experiment_stage")
    if not experiment_stage.claim_eligible:
        reasons.append("stage_not_claim_eligible")
    if not evidence:
        reasons.append("evidence_missing")
    valid: list[Mapping[str, Any]] = []
    seeds: set[int] = set()
    role_seeds: dict[str, set[int]] = defaultdict(set)
    protocols: set[str] = set()
    evidence_ids: list[str] = []
    for index, item in enumerate(evidence):
        missing = sorted(REQUIRED_NUMERIC_EVIDENCE - item.keys())
        if missing:
            reasons.append(f"evidence_{index}_missing:" + ",".join(missing))
            continue
        try:
            require_sha256(str(item["protocol_hash"]), "protocol_hash")
            require_sha256(str(item["environment_lock_hash"]), "environment_lock_hash")
        except ResearchError:
            reasons.append(f"evidence_{index}_invalid_hash")
            continue
        if item.get("artifact_integrity") != "verified":
            reasons.append(f"evidence_{index}_artifact_unverified")
            continue
        if item.get("evaluation_status") != "passed":
            reasons.append(f"evidence_{index}_evaluation_not_passed")
            continue
        if item.get("evaluation_support_strength") not in {"strong", "replicated"}:
            reasons.append(f"evidence_{index}_support_strength_insufficient")
            continue
        try:
            require_sha256(str(item["claim_statement_hash"]), "claim_statement_hash")
        except ResearchError:
            reasons.append(f"evidence_{index}_claim_binding_invalid")
            continue
        if item.get("metric_direction") not in {"maximize", "minimize"} or not str(item.get("metric_name") or "").strip():
            reasons.append(f"evidence_{index}_metric_binding_invalid")
            continue
        if item.get("run_status") != "completed":
            reasons.append(f"evidence_{index}_run_not_completed")
            continue
        if item.get("stale") is True or item.get("invalidated") is True:
            reasons.append(f"evidence_{index}_stale_or_invalidated")
            continue
        seed = item.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int):
            reasons.append(f"evidence_{index}_invalid_seed")
            continue
        if not re.fullmatch(r"[0-9a-f]{40}", str(item.get("code_commit") or "")):
            reasons.append(f"evidence_{index}_invalid_code_commit")
            continue
        if not str(item.get("dataset_version") or "").strip():
            reasons.append(f"evidence_{index}_dataset_version_missing")
            continue
        seeds.add(seed)
        role = str(item.get("role") or "")
        role_seeds[role].add(seed)
        protocols.add(str(item["protocol_hash"]))
        evidence_ids.append(str(item.get("evidence_id") or item["metric_artifact_id"]))
        valid.append(item)
    if len(seeds) < minimum_seeds:
        reasons.append("insufficient_distinct_seeds")
    if len(protocols) > 1:
        reasons.append("cross_protocol_evidence")
    if baseline_required and not any(item.get("role") == "baseline" for item in valid):
        reasons.append("baseline_gap")
    if not any(item.get("role") == "candidate" for item in valid):
        reasons.append("candidate_evidence_missing")
    for role in ("baseline", "candidate"):
        if role_seeds[role] and len(role_seeds[role]) < minimum_seeds:
            reasons.append(f"insufficient_{role}_seeds")
    if reasons:
        severe = any(
            reason.startswith(("evidence_", "cross_protocol", "baseline_gap", "stage_"))
            for reason in reasons
        )
        return ClaimDecision(
            status=ClaimStatus.REJECTED if severe else ClaimStatus.WEAK,
            eligible=False,
            reasons=tuple(dict.fromkeys(reasons)),
            evidence_ids=tuple(evidence_ids),
        )
    return ClaimDecision(
        status=ClaimStatus.SUPPORTED,
        eligible=True,
        reasons=(),
        evidence_ids=tuple(evidence_ids),
    )


class EvidenceGraph:
    """Acyclic reference graph used for stale/invalidated propagation."""

    def __init__(self, edges: Sequence[tuple[str, str]]) -> None:
        self._children: dict[str, set[str]] = defaultdict(set)
        self._parents: dict[str, set[str]] = defaultdict(set)
        for source, target in edges:
            if source == target:
                raise ResearchError("research.evidence_cycle", "self-referential evidence is forbidden")
            self._children[source].add(target)
            self._parents[target].add(source)
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        nodes = set(self._children) | set(self._parents)
        indegree = {node: len(self._parents[node]) for node in nodes}
        ready = deque(sorted(node for node, degree in indegree.items() if degree == 0))
        visited = 0
        while ready:
            node = ready.popleft()
            visited += 1
            for child in sorted(self._children[node]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if visited != len(nodes):
            raise ResearchError("research.evidence_cycle", "evidence graph must be acyclic")

    def invalidate_from(self, evidence_id: str) -> tuple[str, ...]:
        affected: set[str] = set()
        queue = deque([evidence_id])
        while queue:
            current = queue.popleft()
            if current in affected:
                continue
            affected.add(current)
            queue.extend(sorted(self._children[current]))
        return tuple(sorted(affected))
