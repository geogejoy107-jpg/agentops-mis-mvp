"""Pure operator start-check projection helpers."""
from __future__ import annotations

import shlex
from typing import Any


def _safe_text(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    text = " ".join(text.split())
    return text[:limit]


def operator_start_check_gate(
    gate_id: str,
    *,
    label: str,
    ok: bool,
    status: str | None = None,
    detail: str | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "label": label,
        "ok": bool(ok),
        "status": status or ("pass" if ok else "attention"),
        "detail": detail,
        "next_action": command,
        "token_omitted": True,
    }


def compact_start_check_loop_driver_entry(
    review: dict[str, Any],
    *,
    adapter: str,
    limit: int,
    loop_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    command_parts = [
        "agentops", "operator", "loop-driver",
        "--adapter", adapter,
        "--max-steps", "3",
        "--limit", str(limit),
    ]
    if loop_id:
        command_parts.extend(["--loop-id", loop_id])
    if task_id:
        command_parts.extend(["--task-id", task_id])
    if agent_id:
        command_parts.extend(["--agent-id", agent_id])
    preview_command = " ".join(shlex.quote(str(part)) for part in command_parts)
    confirm_command = " ".join(shlex.quote(str(part)) for part in [*command_parts, "--confirm-loop"])
    review_command = "agentops review queue --limit 20"
    review_summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
    review_items = review.get("review_items") if isinstance(review.get("review_items"), list) else []
    compact_items: list[dict[str, Any]] = []
    for item in review_items[: min(limit, 5)]:
        if not isinstance(item, dict):
            continue
        item_type = item.get("item_type")
        compact_items.append({
            "item_id": item.get("item_id"),
            "item_type": item_type,
            "kind": item.get("kind"),
            "status": item.get("status"),
            "priority": item.get("priority"),
            "task_id": item.get("task_id"),
            "run_id": item.get("run_id"),
            "approval_id": item.get("approval_id") or (item.get("item_id") if item_type == "approval" else None),
            "memory_id": item.get("memory_id") or (item.get("item_id") if item_type == "memory_candidate" else None),
            "next_action": _safe_text(item.get("next_action") or item.get("cli_action") or "", 500),
            "summary_omitted": True,
            "raw_content_omitted": True,
            "token_omitted": True,
        })
    pending_approvals = int(review_summary.get("pending_approvals") or 0)
    memory_candidates = int(review_summary.get("memory_candidates") or 0)
    review_items_total = int(review_summary.get("review_items_total") or len(review_items))
    review_status = "attention" if review_items_total or pending_approvals or memory_candidates else "ready"
    return {
        "operation": "operator_start_check_loop_driver_entry",
        "status": review_status,
        "adapter": adapter,
        "loop_id": loop_id or None,
        "task_id": task_id or None,
        "agent_id": agent_id or None,
        "commands": {
            "preview": preview_command,
            "confirm_loop": confirm_command,
            "review_queue": review_command,
            "verify": "agentops operator action-receipts --limit 20",
        },
        "review_snapshot": {
            "operation": "loop_driver_record_review_snapshot",
            "source_operation": review.get("operation"),
            "status": review_status,
            "summary": {
                "review_items_total": review_items_total,
                "returned_items": int(review_summary.get("returned_items") or len(review_items)),
                "pending_approvals": pending_approvals,
                "memory_candidates": memory_candidates,
                "retrieved_pending_approvals": int(review_summary.get("retrieved_pending_approvals") or 0),
                "retrieved_memory_candidates": int(review_summary.get("retrieved_memory_candidates") or 0),
            },
            "items": compact_items,
            "review_command": review_command,
            "summary_omitted": True,
            "raw_content_omitted": True,
            "token_omitted": True,
            "safety": {
                "read_only": True,
                "ledger_mutated": False,
                "live_execution_performed": False,
                "server_executes_shell": False,
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "raw_content_omitted": True,
                "token_omitted": True,
            },
        },
        "contract": "copy-only loop-driver entry for Hermes/OpenClaw/Codex start-check; preview is read-only, confirm-loop runs only bounded advance-loop steps from the local CLI, and review state is compact/redacted",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "raw_content_omitted": True,
            "token_omitted": True,
        },
        "token_omitted": True,
    }


def operator_agent_loop_packet(
    *,
    adapter: str,
    max_steps: int,
    acceptance_gate: dict[str, Any],
    adapter_readiness: dict[str, Any],
    launch_brief: dict[str, Any],
    review_snapshot: dict[str, Any],
    confirm_loop: bool,
    stop_reason: str | None = None,
    steps_advanced: int = 0,
) -> dict[str, Any]:
    acceptance_decision = acceptance_gate.get("decision") if isinstance(acceptance_gate.get("decision"), dict) else {}
    acceptance_commands = acceptance_gate.get("commands") if isinstance(acceptance_gate.get("commands"), dict) else {}
    acceptance_safety = acceptance_gate.get("safety") if isinstance(acceptance_gate.get("safety"), dict) else {}
    readiness_commands = adapter_readiness.get("commands") if isinstance(adapter_readiness.get("commands"), dict) else {}
    launch_commands = launch_brief.get("commands") if isinstance(launch_brief.get("commands"), dict) else {}
    launch_summary = launch_brief.get("summary") if isinstance(launch_brief.get("summary"), dict) else {}
    launch_local_path = launch_brief.get("local_run_path") if isinstance(launch_brief.get("local_run_path"), dict) else {}
    current_code_gate = launch_local_path.get("current_code_gate") if isinstance(launch_local_path.get("current_code_gate"), dict) else {}
    current_code_command = (
        acceptance_commands.get("current_code_check")
        or current_code_gate.get("strict_command")
        or current_code_gate.get("command")
        or "agentops local readiness --require-current-code"
    )
    current_code_ok = acceptance_decision.get("current_code_ok") is True and current_code_gate.get("ok") is True
    review_summary = review_snapshot.get("summary") if isinstance(review_snapshot.get("summary"), dict) else {}
    can_confirm = (
        current_code_ok
        and acceptance_decision.get("can_confirm_bounded_loop") is True
        and acceptance_safety.get("server_executes_shell") is False
    )
    review_attention = bool(
        int(review_summary.get("review_items_total") or 0)
        or int(review_summary.get("pending_approvals") or 0)
        or int(review_summary.get("memory_candidates") or 0)
    )
    if not can_confirm:
        current_phase = "blocked"
    elif confirm_loop:
        current_phase = "record" if steps_advanced else "execute"
    else:
        current_phase = "preview"
    confirm_command = (
        acceptance_commands.get("loop_driver_confirm")
        or "agentops operator loop-driver --confirm-loop --max-steps "
        f"{max_steps} --adapter {adapter}"
    )
    preview_command = (
        acceptance_commands.get("loop_driver_preview")
        or f"agentops operator loop-driver --adapter {adapter} --max-steps {max_steps}"
    )
    verify_command = launch_brief.get("verify_command") or "agentops operator loop-control --limit 8"
    receipt_command = launch_brief.get("receipt_command") or "agentops operator action-receipts --limit 20"
    phases = [
        {
            "phase": "read",
            "status": "ready",
            "command": acceptance_commands.get("start_check") or f"agentops operator start-check --adapter {adapter} --limit 8",
            "gate_id": "start_check",
            "description": "read start-check acceptance packet before local loop work",
            "token_omitted": True,
        },
        {
            "phase": "read",
            "status": "ready" if current_code_ok else "blocked",
            "command": current_code_command,
            "gate_id": "current_code_check",
            "description": "fail closed when the connected MIS process is older than the current checkout",
            "token_omitted": True,
        },
        {
            "phase": "plan",
            "status": "ready",
            "command": launch_commands.get("agent_plan_create") or "agentops agent-plan create --help",
            "gate_id": "agent_plan",
            "description": "create or inspect task-bound Agent Plan before live work",
            "token_omitted": True,
        },
        {
            "phase": "retrieve",
            "status": "ready",
            "command": launch_commands.get("knowledge_search") or "agentops knowledge search --query '<task terms>'",
            "gate_id": "knowledge_search",
            "description": "retrieve project knowledge and repo context",
            "token_omitted": True,
        },
        {
            "phase": "compare",
            "status": "ready",
            "command": launch_commands.get("repo_map") or "agentops commander repo-map --query '<task terms>'",
            "gate_id": "base_reference",
            "description": "compare proposed files against repo map and base references",
            "token_omitted": True,
        },
        {
            "phase": "preflight",
            "status": adapter_readiness.get("status") or adapter_readiness.get("readiness") or "unknown",
            "command": readiness_commands.get("adapter_preflight") or f"agentops worker preflight --adapter {adapter}",
            "gate_id": "adapter_preflight",
            "description": "check adapter readiness before any live dispatch",
            "token_omitted": True,
        },
        {
            "phase": "execute",
            "status": "ready" if can_confirm else "blocked",
            "command": confirm_command,
            "gate_id": "bounded_loop_confirm",
            "description": "run bounded local advance-loop steps only after acceptance gate passes",
            "confirm_required": True,
            "token_omitted": True,
        },
        {
            "phase": "verify",
            "status": "ready",
            "command": verify_command,
            "gate_id": "loop_verify",
            "description": "verify loop-control state after bounded execution",
            "token_omitted": True,
        },
        {
            "phase": "record",
            "status": "attention" if review_attention else "ready",
            "command": review_snapshot.get("review_command") or "agentops review queue --limit 20",
            "gate_id": "record_review",
            "description": "review pending RECORD items without approving or storing raw content",
            "token_omitted": True,
        },
    ]
    phase_commands = {
        str(phase["phase"]): phase.get("command")
        for phase in phases
        if phase.get("phase") and phase.get("command")
    }
    method_gates = [
        {
            "id": "read_start_check",
            "phase": "read",
            "required": True,
            "status": "ready",
            "command": acceptance_commands.get("start_check") or f"agentops operator start-check --adapter {adapter} --limit 8",
            "proof": "operator start-check acceptance packet is the first read before local loop work",
            "token_omitted": True,
        },
        {
            "id": "read_current_code",
            "phase": "read",
            "required": True,
            "status": "ready" if current_code_ok else "blocked",
            "command": current_code_command,
            "proof": "Hermes/OpenClaw/Codex must verify the local MIS process matches current backend source before planning or dispatch",
            "token_omitted": True,
        },
        {
            "id": "plan_agent_plan",
            "phase": "plan",
            "required": acceptance_decision.get("agent_plan_required") is not False,
            "status": "required" if acceptance_decision.get("agent_plan_required") is not False else "optional",
            "command": phase_commands.get("plan"),
            "proof": "Agent Plan must be created and verified before run start",
            "token_omitted": True,
        },
        {
            "id": "retrieve_knowledge",
            "phase": "retrieve",
            "required": acceptance_decision.get("knowledge_search_required") is not False,
            "status": "required" if acceptance_decision.get("knowledge_search_required") is not False else "optional",
            "command": phase_commands.get("retrieve"),
            "proof": "knowledge search and referenced memories must ground the task",
            "token_omitted": True,
        },
        {
            "id": "compare_base_reference",
            "phase": "compare",
            "required": acceptance_decision.get("base_compare_required") is not False,
            "status": "required" if acceptance_decision.get("base_compare_required") is not False else "optional",
            "command": phase_commands.get("compare"),
            "proof": "repo-map/base comparison must happen before execution",
            "token_omitted": True,
        },
        {
            "id": "preflight_adapter",
            "phase": "preflight",
            "required": True,
            "status": adapter_readiness.get("status") or adapter_readiness.get("readiness") or "unknown",
            "command": phase_commands.get("preflight"),
            "proof": "adapter readiness is checked without live dispatch",
            "token_omitted": True,
        },
        {
            "id": "execute_bounded_loop",
            "phase": "execute",
            "required": True,
            "status": "ready" if can_confirm else "blocked",
            "command": phase_commands.get("execute"),
            "confirm_required": True,
            "proof": "bounded loop confirmation is allowed only when start-check acceptance passes and server_executes_shell=false",
            "token_omitted": True,
        },
        {
            "id": "verify_loop",
            "phase": "verify",
            "required": True,
            "status": "ready",
            "command": phase_commands.get("verify"),
            "proof": "loop-control/action-receipt verification must be read back after bounded execution",
            "token_omitted": True,
        },
        {
            "id": "record_memory_candidate",
            "phase": "record",
            "required": acceptance_decision.get("receipt_required") is not False,
            "status": "attention" if review_attention else "ready",
            "command": phase_commands.get("record"),
            "proof": "RECORD closes through review queue and memory candidates remain reviewable before becoming authority",
            "token_omitted": True,
        },
    ]
    return {
        "operation": "operator_loop_driver_agent_loop_packet",
        "adapter": adapter,
        "current_phase": current_phase,
        "ready_to_confirm_loop": can_confirm,
        "max_steps": max_steps,
        "steps_advanced": int(steps_advanced or 0),
        "stop_reason": stop_reason,
        "phases": phases,
        "phase_commands": phase_commands,
        "method_gates": method_gates,
        "commands": {
            "start_check": acceptance_commands.get("start_check") or f"agentops operator start-check --adapter {adapter} --limit 8",
            "current_code_check": current_code_command,
            "agent_plan_create": phase_commands.get("plan"),
            "knowledge_search": phase_commands.get("retrieve"),
            "base_reference": phase_commands.get("compare"),
            "preview_loop": preview_command,
            "confirm_loop": confirm_command if can_confirm else None,
            "adapter_preflight": readiness_commands.get("adapter_preflight") or f"agentops worker preflight --adapter {adapter}",
            "verify_loop": verify_command,
            "receipt_readback": receipt_command,
            "loop_audit": "agentops operator loop-audit --limit 20",
            "review_queue": review_snapshot.get("review_command") or "agentops review queue --limit 20",
        },
        "gates": {
            "acceptance": acceptance_gate.get("status"),
            "adapter_readiness": adapter_readiness.get("status") or adapter_readiness.get("readiness"),
            "launch_brief": launch_brief.get("status"),
            "current_code": "ready" if current_code_ok else "blocked",
            "record_review": review_snapshot.get("status"),
            "control_status": launch_summary.get("control_status"),
            "server_executes_shell": acceptance_safety.get("server_executes_shell") is True,
        },
        "contract": "machine-readable READ/PLAN/RETRIEVE/COMPARE/PREFLIGHT/EXECUTE/VERIFY/RECORD loop packet for Hermes/OpenClaw/Codex; commands are copy-only and live dispatch still requires explicit confirm-run/prepared-action gates",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "raw_content_omitted": True,
            "token_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }


def compact_runtime_current_code_gate(local: dict[str, Any]) -> dict[str, Any]:
    runtime = local.get("running_instance") if isinstance(local.get("running_instance"), dict) else {}
    readiness_gates = local.get("gates") if isinstance(local.get("gates"), list) else []
    source_gate = next(
        (gate for gate in readiness_gates if isinstance(gate, dict) and gate.get("id") == "running_instance_freshness"),
        {},
    )
    git_head = str(runtime.get("git_head_sha") or "")
    command = _safe_text(source_gate.get("next_action") or "agentops local readiness --require-current-code", 700)
    strict_command = command
    if git_head and "--expect-head-sha" not in strict_command:
        strict_command = f"{strict_command} --expect-head-sha {shlex.quote(git_head)}"
    has_runtime_signal = bool(runtime or source_gate)
    current = (
        source_gate.get("ok") is True
        or runtime.get("current") is True
        or runtime.get("status") == "current"
    ) if has_runtime_signal else False
    status = runtime.get("status") or source_gate.get("status") or ("current" if current else "unknown")
    return {
        "operation": "local_current_code_gate",
        "id": "running_instance_freshness",
        "ok": bool(current),
        "current": bool(current),
        "status": status,
        "gate_status": source_gate.get("status") or status,
        "server_started_after_source_mtime": runtime.get("server_started_after_source_mtime"),
        "git_head_sha": git_head,
        "git_head_short": runtime.get("git_head_short") or (git_head[:12] if git_head else ""),
        "git_branch": runtime.get("git_branch"),
        "git_dirty_entries": int(runtime.get("git_dirty_entries") or 0),
        "latest_source_path": runtime.get("latest_source_path"),
        "command": command,
        "strict_command": strict_command,
        "next_action": command,
        "contract": "read-only preflight gate for local agents; fail closed if the connected MIS process is stale or reports a different git HEAD",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "token_omitted": True,
        },
        "token_omitted": True,
    }


def compact_start_check_local_run_path(local: dict[str, Any]) -> dict[str, Any]:
    steps = local.get("local_run_path") if isinstance(local.get("local_run_path"), list) else []
    compact_steps: list[dict[str, Any]] = []
    for step in steps[:8]:
        if not isinstance(step, dict):
            continue
        compact_steps.append({
            "step_id": step.get("step_id"),
            "phase": step.get("phase"),
            "status": step.get("status"),
            "adapter": step.get("adapter"),
            "command": step.get("command"),
            "verify_command": step.get("verify_command"),
            "confirm_required": bool(step.get("confirm_required")),
            "writes_ledger": bool(step.get("writes_ledger")),
            "live_execution": bool(step.get("live_execution")),
            "service_control_preview": bool(step.get("service_control_preview")),
            "copy_only": step.get("copy_only", True) is not False,
            "server_executes_shell": bool(step.get("server_executes_shell")),
            "receipt_required": bool(step.get("receipt_required")),
            "control_readback_required": bool(step.get("control_readback_required")),
            "receipt_command": step.get("receipt_command"),
            "receipt_record_command": step.get("receipt_record_command"),
            "receipt_verify_record_command": step.get("receipt_verify_record_command"),
            "receipt_state": step.get("receipt_state") if isinstance(step.get("receipt_state"), dict) else None,
            "action_signature": step.get("action_signature"),
            "source": step.get("source"),
            "token_omitted": step.get("token_omitted", True) is not False,
        })
    service_step = next((step for step in compact_steps if step.get("step_id") == "preview_worker_service_control"), None)
    current_code_gate = compact_runtime_current_code_gate(local)
    commands = [str(current_code_gate.get("strict_command") or current_code_gate.get("command") or "").strip()]
    commands.extend([
        str(step.get("command") or "").strip()
        for step in compact_steps
        if str(step.get("command") or "").strip()
    ])
    commands = [command for command in dict.fromkeys(commands) if command]
    summary = local.get("summary") if isinstance(local.get("summary"), dict) else {}
    return {
        "operation": "local_run_path_compact",
        "source_operation": local.get("operation") or "local_readiness",
        "status": local.get("status"),
        "recommended_adapter": summary.get("recommended_adapter"),
        "current_code_gate": current_code_gate,
        "steps": compact_steps,
        "commands": commands,
        "service_control_preview": service_step,
        "contract": "copy-only local boot/readiness/worker/service/dispatch/verify path; commands are for the operator or agent shell to copy, not for server-side shell execution",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "token_omitted": True,
        },
        "token_omitted": True,
    }


def compact_start_check_launch_brief(
    packet: dict[str, Any],
    *,
    adapter: str,
    local_run_path: dict[str, Any],
) -> dict[str, Any]:
    summary = packet.get("summary") if isinstance(packet.get("summary"), dict) else {}
    control = packet.get("control_summary") if isinstance(packet.get("control_summary"), dict) else {}
    recommended = control.get("recommended_step") if isinstance(control.get("recommended_step"), dict) else {}
    safety = packet.get("safety") if isinstance(packet.get("safety"), dict) else {}
    audit = packet.get("audit_contract") if isinstance(packet.get("audit_contract"), dict) else {}
    evaluation = packet.get("evaluation_contract") if isinstance(packet.get("evaluation_contract"), dict) else {}
    agent_plan_draft = packet.get("agent_plan_draft") if isinstance(packet.get("agent_plan_draft"), dict) else {}
    chain = packet.get("execution_chain") if isinstance(packet.get("execution_chain"), list) else []
    compact_chain: list[dict[str, Any]] = []
    for item in chain[:8]:
        if not isinstance(item, dict):
            continue
        compact_chain.append({
            "step_id": item.get("step_id"),
            "phase": item.get("phase"),
            "label": item.get("label"),
            "status": item.get("step_status"),
            "next_safe_command": item.get("next_safe_command") or item.get("command"),
            "verify_command": item.get("verify_command"),
            "receipt_command": item.get("receipt_command"),
            "confirm_required": bool(item.get("confirm_required")),
            "receipt_required": bool(item.get("receipt_required")),
            "source": item.get("source"),
            "token_omitted": item.get("token_omitted", True) is not False,
        })
    adapter_command = f"agentops worker preflight --adapter {adapter}"
    current_code_gate = local_run_path.get("current_code_gate") if isinstance(local_run_path.get("current_code_gate"), dict) else {}
    current_code_command = current_code_gate.get("strict_command") or current_code_gate.get("command") or "agentops local readiness --require-current-code"
    live_run_command = (
        "agentops workflow run-task "
        f"--adapter {adapter} "
        "--confirm-run "
        f"--worker-agent-id <{adapter}_agent_id> "
        "--title '<task title>' "
        "--description '<task description>'"
    ) if adapter in {"hermes", "openclaw"} else (
        "agentops workflow run-task "
        "--adapter mock "
        "--worker-agent-id <mock_agent_id> "
        "--title '<task title>' "
        "--description '<task description>'"
    )
    readback_commands = [
        "agentops task get --task-id <task_id>",
        "agentops run get --run-id <run_id>",
        "agentops plan-evidence list --run-id <run_id>",
        "agentops operator loop-audit --limit 20",
        "agentops operator action-receipts --limit 20",
    ]
    return {
        "operation": "operator_loop_launch_brief",
        "source_operation": packet.get("operation", "operator_loop_launch_packet"),
        "status": packet.get("status", "unknown"),
        "workspace_id": packet.get("workspace_id"),
        "task_id": packet.get("task_id"),
        "agent_id": packet.get("agent_id"),
        "adapter": adapter,
        "method": packet.get("method"),
        "summary": {
            "handoff_mode": summary.get("handoff_mode"),
            "control_status": control.get("status") or summary.get("control_status"),
            "control_mode": control.get("mode") or summary.get("control_mode"),
            "recommended_step": recommended.get("step_id") or summary.get("recommended_step"),
            "recommended_label": recommended.get("label"),
            "requires_human": bool(control.get("requires_human")),
            "requires_receipt": bool(control.get("requires_receipt")),
            "execution_chain_steps": len(chain),
            "blocking_steps": control.get("blocking_steps") or [],
            "attention_steps": control.get("attention_steps") or [],
            "required_ledgers": evaluation.get("required_ledgers") or [],
            "agent_plan_risk": agent_plan_draft.get("risk_level"),
            "agent_plan_approval_required": bool(agent_plan_draft.get("approval_required")),
            "local_readiness_status": local_run_path.get("status"),
            "current_code_status": current_code_gate.get("status"),
            "current_code_ok": current_code_gate.get("ok"),
            "local_run_path_steps": len(local_run_path.get("steps") or []),
            "local_run_path_recommended_adapter": local_run_path.get("recommended_adapter"),
            "service_control_preview": bool(local_run_path.get("service_control_preview")),
        },
        "next_command": control.get("next_command") or recommended.get("command"),
        "verify_command": control.get("verify_command") or recommended.get("verify_command"),
        "receipt_command": control.get("receipt_command") or recommended.get("receipt_command"),
        "adapter_preflight_command": adapter_command,
        "current_code_check_command": current_code_command,
        "live_run_command": live_run_command,
        "readback_commands": readback_commands,
        "runtime_doctor_command": "agentops operator runtime-doctor --limit 8",
        "local_run_path": local_run_path,
        "execution_chain": compact_chain,
        "policy": {
            "policy_id": control.get("policy_id") or (audit.get("bounded_runner") or {}).get("policy_id"),
            "server_executes_shell": bool(control.get("server_executes_shell") or (audit.get("bounded_runner") or {}).get("server_executes_shell")),
            "live_execution_requires_confirm_run": adapter in {"hermes", "openclaw"},
            "external_writes_require_prepared_action": adapter in {"hermes", "openclaw"},
            "copy_only": control.get("copy_only", True) is not False,
        },
        "safety": {
            "read_only": bool(safety.get("read_only", True)),
            "ledger_mutated": bool(safety.get("ledger_mutated")),
            "live_execution_performed": bool(safety.get("live_execution_performed")),
            "server_executes_shell": False,
            "raw_prompt_omitted": bool(safety.get("raw_prompt_omitted", True)),
            "raw_response_omitted": bool(safety.get("raw_response_omitted", True)),
            "token_omitted": bool(safety.get("token_omitted", True)),
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }


def operator_start_check_acceptance_packet(
    *,
    status: str,
    adapter: str,
    workspace_id: str,
    task_id: str | None = None,
    agent_id: str | None = None,
    gates: list[dict[str, Any]] | None = None,
    worker_connection_policy: dict[str, Any] | None = None,
    adapter_readiness: dict[str, Any] | None = None,
    runtime_doctor: dict[str, Any] | None = None,
    launch_brief: dict[str, Any] | None = None,
    loop_driver_entry: dict[str, Any] | None = None,
    local_run_path: dict[str, Any] | None = None,
    live_product_readiness: dict[str, Any] | None = None,
    next_commands: list[str] | None = None,
) -> dict[str, Any]:
    gate_items = gates or []
    launch = launch_brief or {}
    loop_driver = loop_driver_entry or {}
    local_path = local_run_path or {}
    local_current_code_gate = local_path.get("current_code_gate") if isinstance(local_path.get("current_code_gate"), dict) else {}
    worker_policy = worker_connection_policy or {}
    adapter_state = adapter_readiness or {}
    doctor = runtime_doctor or {}
    live_product = live_product_readiness or {}
    commands = [str(command or "").strip() for command in (next_commands or []) if str(command or "").strip()]
    blocked_gates = [gate for gate in gate_items if gate.get("status") == "blocked"]
    attention_gates = [gate for gate in gate_items if gate.get("status") == "attention" or gate.get("ok") is False]
    loop_commands = loop_driver.get("commands") if isinstance(loop_driver.get("commands"), dict) else {}
    launch_summary = launch.get("summary") if isinstance(launch.get("summary"), dict) else {}
    review_snapshot = loop_driver.get("review_snapshot") if isinstance(loop_driver.get("review_snapshot"), dict) else {}
    review_summary = review_snapshot.get("summary") if isinstance(review_snapshot.get("summary"), dict) else {}
    local_steps = local_path.get("steps") if isinstance(local_path.get("steps"), list) else []
    required_ledgers = launch_summary.get("required_ledgers") if isinstance(launch_summary.get("required_ledgers"), list) else []
    receipt_required = (
        bool(launch_summary.get("requires_receipt", False))
        or "operator_action_receipts" in required_ledgers
        or "operator_action_evaluations" in required_ledgers
    )
    live_required = adapter in {"hermes", "openclaw"}
    current_code_ok = local_current_code_gate.get("ok") is True
    live_ready = not live_required or bool(live_product.get("product_readiness_proof"))
    preview_allowed = not blocked_gates
    confirm_loop_allowed = current_code_ok and preview_allowed and (loop_driver.get("safety") or {}).get("server_executes_shell") is False
    live_dispatch_allowed = current_code_ok and (adapter == "mock" or (live_ready and adapter_state.get("requires_confirm_run") is True))

    def command_for(needle: str, fallback: str | None = None) -> str | None:
        for command in commands:
            if needle in command:
                return command
        return fallback

    return {
        "operation": "operator_local_loop_acceptance_packet",
        "status": status,
        "adapter": adapter,
        "workspace_id": workspace_id,
        "task_id": task_id or None,
        "agent_id": agent_id or None,
        "audience": ["codex", "hermes", "openclaw"],
        "decision": {
            "can_preview_loop": preview_allowed,
            "can_confirm_bounded_loop": confirm_loop_allowed,
            "live_dispatch_allowed": live_dispatch_allowed,
            "live_dispatch_requires_confirm_run": live_required,
            "human_review_required": bool(review_summary.get("review_items_total") or review_summary.get("pending_approvals")),
            "memory_review_required": "memory_review" in required_ledgers,
            "current_code_required": True,
            "current_code_ok": current_code_ok,
            "agent_plan_required": True,
            "knowledge_search_required": True,
            "base_compare_required": True,
            "receipt_required": receipt_required,
        },
        "summary": {
            "blocked_gates": [gate.get("id") for gate in blocked_gates],
            "attention_gates": [gate.get("id") for gate in attention_gates],
            "review_items_total": int(review_summary.get("review_items_total") or 0),
            "pending_approvals": int(review_summary.get("pending_approvals") or 0),
            "memory_candidates": int(review_summary.get("memory_candidates") or 0),
            "required_ledgers": required_ledgers,
            "local_run_path_steps": len(local_steps),
            "current_code_status": local_current_code_gate.get("status"),
            "current_code_ok": current_code_ok,
            "service_control_preview": bool(local_path.get("service_control_preview")),
            "runtime_doctor_status": doctor.get("status"),
            "adapter_readiness": adapter_state.get("readiness"),
            "live_product_readiness": None if not live_required else live_ready,
        },
        "commands": {
            "start_check": f"agentops operator start-check --adapter {adapter} --limit 8",
            "current_code_check": command_for("require-current-code", local_current_code_gate.get("strict_command") or local_current_code_gate.get("command") or "agentops local readiness --require-current-code"),
            "local_readiness": command_for("local readiness", "agentops local readiness"),
            "worker_readiness": command_for("worker readiness", "agentops worker readiness"),
            "adapter_preflight": command_for("worker preflight", f"agentops worker preflight --adapter {adapter}"),
            "runtime_doctor": command_for("operator runtime-doctor", "agentops operator runtime-doctor --limit 8"),
            "loop_launch_brief": command_for("operator loop-launch-packet", f"agentops operator loop-launch-packet --brief --adapter {adapter} --limit 8"),
            "loop_driver_preview": loop_commands.get("preview") or command_for("operator loop-driver"),
            "loop_driver_confirm": loop_commands.get("confirm_loop"),
            "review_queue": loop_commands.get("review_queue") or command_for("review queue", "agentops review queue --limit 20"),
            "execution_mode_preview": f"agentops operator execution-mode --adapter {adapter}",
            "execution_mode_confirm": f"agentops operator execution-mode --adapter {adapter} --confirm-run" if live_required else None,
            "live_product_readiness": f"agentops operator live-product-readiness --require-adapter {adapter}" if live_required else None,
            "live_dispatch_template": launch.get("live_run_command") if live_required else None,
            "receipt_readback": command_for("operator action-receipts", "agentops operator action-receipts --limit 20"),
        },
        "gate_readback": [
            {
                "id": gate.get("id"),
                "status": gate.get("status"),
                "ok": bool(gate.get("ok")),
                "next_action": _safe_text(gate.get("next_action") or "", 500),
                "token_omitted": True,
            }
            for gate in gate_items
        ],
        "sources": {
            "worker_connection_policy": {
                "status": worker_policy.get("status") or worker_policy.get("mode") or worker_policy.get("schema"),
                "server_executes_shell": worker_policy.get("server_executes_shell"),
                "token_omitted": True,
            },
            "adapter_readiness": adapter_state,
            "runtime_doctor": {
                "status": doctor.get("status"),
                "token_omitted": True,
            },
            "launch_brief": {
                "status": launch.get("status"),
                "operation": launch.get("operation"),
                "token_omitted": True,
            },
            "loop_driver_entry": {
                "status": loop_driver.get("status"),
                "operation": loop_driver.get("operation"),
                "token_omitted": True,
            },
            "local_run_path": {
                "status": local_path.get("status"),
                "operation": local_path.get("operation"),
                "current_code_gate": local_current_code_gate,
                "token_omitted": True,
            },
        },
        "contract": "single read-only acceptance packet for local Hermes/OpenClaw/Codex loop intake; it is copy-only and does not start runtimes, confirm live dispatch, approve reviews, write memories, mutate ledgers, or execute shell on the server",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "raw_content_omitted": True,
            "token_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }


def operator_local_loop_admission_packet(
    *,
    status: str,
    adapter: str,
    workspace_id: str,
    acceptance_packet: dict[str, Any],
    agent_loop_packet: dict[str, Any],
    local_run_path: dict[str, Any],
    adapter_readiness: dict[str, Any],
    loop_driver_entry: dict[str, Any],
    task_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Build the single local loop admission readback for agent callers."""
    decision = acceptance_packet.get("decision") if isinstance(acceptance_packet.get("decision"), dict) else {}
    acceptance_commands = acceptance_packet.get("commands") if isinstance(acceptance_packet.get("commands"), dict) else {}
    agent_commands = agent_loop_packet.get("commands") if isinstance(agent_loop_packet.get("commands"), dict) else {}
    phase_commands = agent_loop_packet.get("phase_commands") if isinstance(agent_loop_packet.get("phase_commands"), dict) else {}
    method_gates = agent_loop_packet.get("method_gates") if isinstance(agent_loop_packet.get("method_gates"), list) else []
    method_gate_ids = [str(gate.get("id")) for gate in method_gates if isinstance(gate, dict) and gate.get("id")]
    local_steps = local_run_path.get("steps") if isinstance(local_run_path.get("steps"), list) else []
    service_step = local_run_path.get("service_control_preview") if isinstance(local_run_path.get("service_control_preview"), dict) else {}
    current_code_gate = local_run_path.get("current_code_gate") if isinstance(local_run_path.get("current_code_gate"), dict) else {}
    current_code_command = (
        acceptance_commands.get("current_code_check")
        or current_code_gate.get("strict_command")
        or current_code_gate.get("command")
        or "agentops local readiness --require-current-code"
    )
    loop_commands = loop_driver_entry.get("commands") if isinstance(loop_driver_entry.get("commands"), dict) else {}

    def step_by_id(step_id: str) -> dict[str, Any]:
        for step in local_steps:
            if isinstance(step, dict) and step.get("step_id") == step_id:
                return step
        return {}

    start_worker_step = step_by_id("start_selected_worker")
    dispatch_step = step_by_id("dispatch_customer_task")
    verify_step = step_by_id("verify_ledger_evidence")
    acceptance_step = step_by_id("prove_live_product_readiness")
    blocked_gates = (acceptance_packet.get("summary") or {}).get("blocked_gates") if isinstance(acceptance_packet.get("summary"), dict) else []
    attention_gates = (acceptance_packet.get("summary") or {}).get("attention_gates") if isinstance(acceptance_packet.get("summary"), dict) else []
    can_preview = decision.get("can_preview_loop") is True
    can_confirm_loop = decision.get("can_confirm_bounded_loop") is True
    live_required = adapter in {"hermes", "openclaw"}
    start_worker_matches_adapter = not start_worker_step or start_worker_step.get("adapter") in {None, adapter}
    service_matches_adapter = not service_step or service_step.get("adapter") in {None, adapter}
    dispatch_matches_adapter = not dispatch_step or dispatch_step.get("adapter") in {None, adapter}
    start_worker_command = start_worker_step.get("command") if start_worker_matches_adapter else None
    start_worker_verify = start_worker_step.get("verify_command") or "agentops worker status"
    service_command = service_step.get("command") if service_matches_adapter else None
    service_verify = service_step.get("verify_command") if service_matches_adapter else None
    dispatch_command = dispatch_step.get("command") if dispatch_matches_adapter else None
    dispatch_verify = dispatch_step.get("verify_command") if dispatch_matches_adapter else None
    if live_required:
        start_worker_command = start_worker_command or f"agentops worker start --adapter {adapter} --confirm-run --poll-interval 5 --max-tasks 0"
        service_command = service_command or f"agentops worker service-control --manager launchd --action restart --adapter {adapter} --agent-id agt_worker_daemon_{adapter}"
        service_verify = service_verify or f"agentops worker service-check --manager launchd --adapter {adapter} --agent-id agt_worker_daemon_{adapter}"
        dispatch_command = acceptance_commands.get("live_dispatch_template") or (
            "agentops workflow run-task "
            f"--adapter {adapter} "
            "--confirm-run "
            f"--worker-agent-id <{adapter}_agent_id> "
            "--title '<task title>' "
            "--description '<task description>'"
        )
        dispatch_verify = dispatch_verify or f"agentops operator live-product-readiness --require-adapter {adapter}"
    else:
        start_worker_command = start_worker_command or f"agentops worker start --adapter {adapter} --poll-interval 5 --max-tasks 0"
        service_command = service_command or f"agentops worker service-control --manager launchd --action restart --adapter {adapter} --agent-id agt_worker_daemon_{adapter}"
        service_verify = service_verify or f"agentops worker service-check --manager launchd --adapter {adapter} --agent-id agt_worker_daemon_{adapter}"
        dispatch_command = dispatch_command or acceptance_commands.get("live_dispatch_template") or (
            "agentops workflow run-task "
            f"--adapter {adapter} "
            f"--worker-agent-id <{adapter}_agent_id> "
            "--title '<task title>' "
            "--description '<task description>'"
        )
        dispatch_verify = dispatch_verify or "agentops run list --limit 5"
    first_safe_commands = [
        acceptance_commands.get("start_check"),
        current_code_command,
        agent_commands.get("agent_plan_create"),
        agent_commands.get("knowledge_search"),
        agent_commands.get("base_reference"),
        acceptance_commands.get("adapter_preflight"),
        acceptance_commands.get("runtime_doctor"),
        loop_commands.get("preview") or agent_commands.get("preview_loop"),
        service_verify,
        acceptance_commands.get("receipt_readback"),
    ]
    confirm_commands = [
        loop_commands.get("confirm_loop") if can_confirm_loop else None,
        start_worker_command,
        service_command,
        dispatch_command,
        acceptance_step.get("command"),
    ]
    return {
        "operation": "operator_local_loop_admission_packet",
        "status": status,
        "adapter": adapter,
        "workspace_id": workspace_id,
        "task_id": task_id or None,
        "agent_id": agent_id or None,
        "admission": {
            "can_preview_loop": can_preview,
            "can_confirm_bounded_loop": can_confirm_loop,
            "current_code_ok": current_code_gate.get("ok") is True,
            "current_code_status": current_code_gate.get("status"),
            "can_start_worker": bool(start_worker_command) and (not live_required or "--confirm-run" in str(start_worker_command)),
            "can_preview_service_control": bool(service_command) and service_step.get("service_control_preview") is True,
            "live_dispatch_allowed": decision.get("live_dispatch_allowed") is True,
            "live_dispatch_requires_confirm_run": bool(live_required),
            "method_gate_count": len(method_gate_ids),
            "blocked_gates": blocked_gates if isinstance(blocked_gates, list) else [],
            "attention_gates": attention_gates if isinstance(attention_gates, list) else [],
        },
        "required_method_gates": method_gate_ids,
        "phase_commands": {
            str(key): value
            for key, value in phase_commands.items()
            if str(key) in {"read", "plan", "retrieve", "compare", "preflight", "execute", "verify", "record"}
        },
        "local_deployment": {
            "current_code_gate": current_code_gate,
            "worker_start": {
                "command": start_worker_command,
                "verify_command": start_worker_verify,
                "confirm_required": bool(start_worker_step.get("confirm_required")) or live_required,
                "live_execution": bool(start_worker_step.get("live_execution")) or live_required,
                "server_executes_shell": False if live_required else bool(start_worker_step.get("server_executes_shell")),
                "token_omitted": True,
            },
            "service_control_preview": {
                "command": service_command,
                "verify_command": service_verify,
                "confirm_required": bool(service_step.get("confirm_required")) if service_matches_adapter and service_step else bool(live_required),
                "preview_only": True if live_required else bool(service_step.get("service_control_preview")) if service_step else False,
                "live_execution": False,
                "server_executes_shell": False,
                "token_omitted": True,
            },
            "customer_worker_dispatch": {
                "command": dispatch_command,
                "verify_command": dispatch_verify,
                "confirm_required": bool(dispatch_step.get("confirm_required")) or live_required,
                "writes_ledger": bool(dispatch_step.get("writes_ledger")) or live_required,
                "live_execution": bool(dispatch_step.get("live_execution")) or live_required,
                "requires_confirm_run_flag": live_required,
                "token_omitted": True,
            },
            "ledger_verify": {
                "command": verify_step.get("command") or agent_commands.get("verify_loop"),
                "verify_command": verify_step.get("verify_command") or agent_commands.get("receipt_readback"),
                "token_omitted": True,
            },
        },
        "commands": {
            "read_start_check": acceptance_commands.get("start_check"),
            "current_code_check": current_code_command,
            "preview_loop": loop_commands.get("preview") or agent_commands.get("preview_loop"),
            "confirm_loop": loop_commands.get("confirm_loop") if can_confirm_loop else None,
            "worker_start": start_worker_command,
            "service_check": service_verify,
            "service_control_preview": service_command,
            "customer_worker_dispatch": dispatch_command,
            "live_acceptance": acceptance_step.get("command") or acceptance_commands.get("live_product_readiness"),
            "receipt_readback": acceptance_commands.get("receipt_readback") or agent_commands.get("receipt_readback"),
            "review_queue": acceptance_commands.get("review_queue") or agent_commands.get("review_queue"),
        },
        "first_safe_commands": [command for command in (_safe_text(item, 700) for item in first_safe_commands) if command],
        "confirm_required_commands": [command for command in (_safe_text(item, 700) for item in confirm_commands) if command],
        "sources": {
            "acceptance_packet": acceptance_packet.get("operation"),
            "agent_loop_packet": agent_loop_packet.get("operation"),
            "local_run_path": local_run_path.get("operation"),
            "adapter_readiness": adapter_readiness.get("readiness"),
            "loop_driver_entry": loop_driver_entry.get("operation"),
            "token_omitted": True,
        },
        "contract": "single copy-only local loop admission packet for Hermes/OpenClaw/Codex; it combines method gates, local deployment previews, worker start, service-control preview, dispatch template, and ledger verification without executing shell or live work on the server",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "raw_content_omitted": True,
            "token_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }
