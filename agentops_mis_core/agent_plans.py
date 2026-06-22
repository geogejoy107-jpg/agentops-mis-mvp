"""Pure Agent Plan response helpers."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_json_list_field(row: Any, field: str) -> list:
    try:
        value = row[field]
    except Exception:
        value = "[]"
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        parsed = []
    return parsed if isinstance(parsed, list) else []


def row_field(row: Any | None, field: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[field]
    except Exception:
        return row.get(field, default) if hasattr(row, "get") else default


def agent_plan_contract(row: Any) -> dict[str, Any]:
    return {
        "workspace_id": row_field(row, "workspace_id"),
        "task_id": row_field(row, "task_id"),
        "run_id": row_field(row, "run_id"),
        "agent_id": row_field(row, "agent_id"),
        "task_understanding": row_field(row, "task_understanding") or "",
        "referenced_specs": load_json_list_field(row, "referenced_specs_json"),
        "referenced_memories": load_json_list_field(row, "referenced_memories_json"),
        "referenced_bases": load_json_list_field(row, "referenced_bases_json"),
        "proposed_files_to_change": load_json_list_field(row, "proposed_files_to_change_json"),
        "risk_level": row_field(row, "risk_level"),
        "approval_required": bool(row_field(row, "approval_required")),
        "execution_steps": load_json_list_field(row, "execution_steps_json"),
        "verification_plan": row_field(row, "verification_plan") or "",
        "rollback_plan": row_field(row, "rollback_plan") or "",
        "plan_version": int(row_field(row, "plan_version", 1) or 1),
    }


def compute_agent_plan_hash(row: Any) -> str:
    return _stable_hash(agent_plan_contract(row))


def agent_plan_verification_hash(plan_id: str, verification: dict[str, Any]) -> str:
    return _stable_hash({
        "plan_id": plan_id,
        "plan_hash": verification.get("plan_hash"),
        "pass": verification.get("pass"),
        "failed_checks": [check.get("id") for check in verification.get("failed_checks") or []],
        "summary": verification.get("summary") or {},
    })


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
