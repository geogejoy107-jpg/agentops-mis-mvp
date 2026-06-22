"""Pure Agent Plan response helpers."""
from __future__ import annotations

from typing import Any


def build_agent_plan_approval_anchor_required_response(*, plan_id: Any = None) -> dict[str, Any]:
    payload = {
        "error": "agent_plan_approval_anchor_required",
        "message": "Approval-required Agent Plans must be attached to a task or run so the approval ledger has task/run anchors.",
        "token_omitted": True,
    }
    if plan_id is not None:
        payload["plan_id"] = plan_id
    return payload


def build_agent_plan_status_transition_required_response(*, requested_status: Any) -> dict[str, Any]:
    return {
        "error": "plan_status_transition_required",
        "message": "Agent-created plans may only start as draft or submitted. Human/admin approval must be a separate transition.",
        "requested_status": requested_status,
        "allowed_create_statuses": ["draft", "submitted"],
        "token_omitted": True,
    }


def build_agent_plan_bound_approval_forbidden_response(*, auth_ctx: dict[str, Any]) -> dict[str, Any]:
    context = auth_ctx or {}
    return {
        "error": "agent_plan_human_approval_required",
        "message": "Bound Agent Gateway tokens and sessions cannot approve or reject Agent Plans.",
        "auth_mode": context.get("mode"),
        "agent_id": context.get("agent_id"),
        "token_omitted": True,
    }


def build_agent_plan_approval_decision_response(*, approval: Any, agent_plan_decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval": dict(approval) if approval is not None else None,
        "agent_plan": agent_plan_decision["agent_plan"],
        "verification": agent_plan_decision["verification"],
        "verification_result_hash": agent_plan_decision["verification_result_hash"],
        "token_omitted": True,
    }
