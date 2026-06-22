"""Pure Agent Plan response helpers."""
from __future__ import annotations

from typing import Any


def build_agent_plan_approval_decision_response(*, approval: Any, agent_plan_decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval": dict(approval) if approval is not None else None,
        "agent_plan": agent_plan_decision["agent_plan"],
        "verification": agent_plan_decision["verification"],
        "verification_result_hash": agent_plan_decision["verification_result_hash"],
        "token_omitted": True,
    }
