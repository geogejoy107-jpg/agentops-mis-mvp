"""Concurrency, resource inventory, retry and budget policy gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import ExperimentStage, ResearchError, canonical_hash


@dataclass(frozen=True, slots=True)
class ResearchBudget:
    gpu_hours: float
    token_budget: int
    model_cost_usd: float
    max_concurrency: int
    max_retries: int
    timeout_seconds: int
    approval_gpu_hour_threshold: float
    approval_cost_threshold_usd: float

    def __post_init__(self) -> None:
        numeric = (self.gpu_hours, self.model_cost_usd, self.approval_gpu_hour_threshold, self.approval_cost_threshold_usd)
        if any(isinstance(value, bool) or value < 0 for value in numeric):
            raise ResearchError("research.invalid_budget", "budget values must be non-negative")
        if min(self.token_budget, self.max_concurrency, self.timeout_seconds) < 1 or self.max_retries < 0:
            raise ResearchError("research.invalid_budget", "token/concurrency/timeout must be positive and retries non-negative")


class BudgetGate:
    @staticmethod
    def evaluate(*, budget: ResearchBudget, consumed: Mapping[str, float], request: Mapping[str, float], stage: str) -> Mapping[str, Any]:
        try:
            ExperimentStage(stage)
        except ValueError as exc:
            raise ResearchError("research.invalid_stage", "unknown experiment stage") from exc
        projected_gpu = float(consumed.get("gpu_hours", 0)) + float(request.get("gpu_hours", 0))
        projected_tokens = int(consumed.get("tokens", 0)) + int(request.get("tokens", 0))
        projected_cost = float(consumed.get("cost_usd", 0)) + float(request.get("cost_usd", 0))
        blockers = []
        approvals = []
        if projected_gpu > budget.gpu_hours:
            blockers.append("gpu_hour_budget_exceeded")
        if projected_tokens > budget.token_budget:
            blockers.append("token_budget_exceeded")
        if projected_cost > budget.model_cost_usd:
            blockers.append("model_cost_budget_exceeded")
        if float(request.get("gpu_hours", 0)) >= budget.approval_gpu_hour_threshold:
            approvals.append("gpu_hour_threshold")
        if float(request.get("cost_usd", 0)) >= budget.approval_cost_threshold_usd:
            approvals.append("model_cost_threshold")
        result = {"allowed": not blockers, "approval_required": bool(approvals), "blockers": blockers, "approval_reasons": approvals, "projected": {"gpu_hours": projected_gpu, "tokens": projected_tokens, "cost_usd": projected_cost}}
        return {**result, "policy_receipt_hash": canonical_hash(result)}

    @staticmethod
    def prune(metric_history: list[float], *, direction: str, threshold: float, minimum_observations: int) -> Mapping[str, Any]:
        if direction not in {"maximize", "minimize"} or minimum_observations < 1:
            raise ResearchError("research.invalid_prune_policy", "prune policy is invalid")
        enough = len(metric_history) >= minimum_observations
        latest = metric_history[-1] if metric_history else None
        prune = enough and latest is not None and (latest < threshold if direction == "maximize" else latest > threshold)
        result = {"prune": prune, "reason": "threshold_not_met" if prune else "continue", "observations": len(metric_history)}
        return {**result, "receipt_hash": canonical_hash(result)}
