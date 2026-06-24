"""Pure operator loop-control projection helpers."""
from __future__ import annotations

from typing import Any


def operator_loop_control_summary_from_handoff(
    advance_loop: dict[str, Any],
    loop_health: dict[str, Any] | None = None,
    *,
    loop_id: str | None = None,
) -> dict[str, Any]:
    loop_health = loop_health or {}
    selected = advance_loop.get("selected_item") or {}
    summary = advance_loop.get("summary") or {}
    policy = advance_loop.get("policy") or {}
    safety = advance_loop.get("safety") or {}
    selected_status = str(selected.get("gate_status") or summary.get("selected_status") or advance_loop.get("status") or "unknown")
    has_selected = bool(selected)
    if has_selected:
        control_mode = "human_confirm_required"
        next_command = advance_loop.get("confirm_command") or advance_loop.get("preview_command")
        verify_command = selected.get("verify_command")
        receipt_command = selected.get("receipt_verify_record_command")
        step_status = "blocked" if selected_status in {"blocked", "failed", "fail", "error"} else "attention"
        reason = "selected handoff action requires local CLI confirmation, verification, and receipt recording"
    else:
        control_mode = "read_only_copy"
        next_command = advance_loop.get("preview_command") or "agentops operator advance-loop --limit 12"
        verify_command = "agentops operator handoff --limit 12"
        receipt_command = None
        step_status = "ready" if (loop_health.get("status") or advance_loop.get("status")) in {"ready", "pass"} else "attention"
        reason = "no selected bounded action; preview the handoff queue before advancing"
    recommended = {
        "step_id": "handoff_advance_loop",
        "label": selected.get("gate_label") or "Bounded handoff advance",
        "phase": "EXECUTE" if has_selected else "READ",
        "status": step_status,
        "control_mode": control_mode,
        "command": next_command,
        "verify_command": verify_command,
        "receipt_command": receipt_command,
        "reason": reason,
        "mutating": has_selected,
        "confirm_required": has_selected,
        "receipt_required": has_selected,
        "receipt_verified": False,
        "receipt_status": "missing" if has_selected else "not_required",
        "action_signature": selected.get("action_signature"),
        "policy_id": policy.get("policy_id") or summary.get("policy_id"),
        "selected_gate": selected.get("gate_id") or summary.get("selected_gate"),
        "source": selected.get("source") or "operator_handoff.advance_loop",
        "run_id": selected.get("run_id"),
        "token_omitted": True,
    }
    status = "blocked" if step_status == "blocked" else "attention" if has_selected or loop_health.get("status") == "attention" else "ready"
    return {
        "operation": "operator_loop_control_summary",
        "status": status,
        "mode": control_mode,
        "loop_id": loop_id or None,
        "recommended_step": recommended,
        "next_command": next_command,
        "verify_command": verify_command,
        "receipt_command": receipt_command,
        "requires_human": has_selected,
        "requires_receipt": has_selected,
        "server_executes_shell": False,
        "copy_only": True,
        "step_counts": {
            "selected": 1 if has_selected else 0,
            "ready": 0 if has_selected else 1,
            "attention": 1 if has_selected else 0,
            "blocked": 1 if step_status == "blocked" else 0,
        },
        "selected_gate": selected.get("gate_id") or summary.get("selected_gate"),
        "selected_status": selected_status,
        "policy_id": policy.get("policy_id") or summary.get("policy_id"),
        "server_shell_execution": bool(safety.get("server_shell_execution")),
        "token_omitted": True,
    }


def operator_loop_control_gate(
    control_summary: dict[str, Any],
    *,
    source: str = "operator_handoff.control_summary",
) -> dict[str, Any]:
    recommended_step = control_summary.get("recommended_step") or {}
    status = str(control_summary.get("status") or "unknown")
    return {
        "status": "pass" if status == "ready" else status,
        "source": source,
        "mode": control_summary.get("mode"),
        "recommended_step": recommended_step.get("step_id"),
        "recommended_step_status": recommended_step.get("status"),
        "selected_gate": control_summary.get("selected_gate"),
        "selected_status": control_summary.get("selected_status"),
        "next_action": control_summary.get("next_command"),
        "verify_command": control_summary.get("verify_command"),
        "receipt_command": control_summary.get("receipt_command"),
        "requires_human": control_summary.get("requires_human") is True,
        "requires_receipt": control_summary.get("requires_receipt") is True,
        "copy_only": control_summary.get("copy_only") is True,
        "server_executes_shell": control_summary.get("server_executes_shell") is True,
        "server_shell_execution": control_summary.get("server_shell_execution") is True,
        "refresh_cache_required_after_receipt": control_summary.get("requires_receipt") is True,
        "control_readback_source": "agentops operator advance-loop --confirm-advance",
        "token_omitted": True,
    }
