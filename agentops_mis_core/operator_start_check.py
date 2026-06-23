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
            "token_omitted": step.get("token_omitted", True) is not False,
        })
    service_step = next((step for step in compact_steps if step.get("step_id") == "preview_worker_service_control"), None)
    commands = [
        str(step.get("command") or "").strip()
        for step in compact_steps
        if str(step.get("command") or "").strip()
    ]
    summary = local.get("summary") if isinstance(local.get("summary"), dict) else {}
    return {
        "operation": "local_run_path_compact",
        "source_operation": local.get("operation") or "local_readiness",
        "status": local.get("status"),
        "recommended_adapter": summary.get("recommended_adapter"),
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
            "local_run_path_steps": len(local_run_path.get("steps") or []),
            "local_run_path_recommended_adapter": local_run_path.get("recommended_adapter"),
            "service_control_preview": bool(local_run_path.get("service_control_preview")),
        },
        "next_command": control.get("next_command") or recommended.get("command"),
        "verify_command": control.get("verify_command") or recommended.get("verify_command"),
        "receipt_command": control.get("receipt_command") or recommended.get("receipt_command"),
        "adapter_preflight_command": adapter_command,
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
    live_ready = not live_required or bool(live_product.get("product_readiness_proof"))
    preview_allowed = not blocked_gates
    confirm_loop_allowed = preview_allowed and (loop_driver.get("safety") or {}).get("server_executes_shell") is False
    live_dispatch_allowed = adapter == "mock" or (live_ready and adapter_state.get("requires_confirm_run") is True)

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
            "service_control_preview": bool(local_path.get("service_control_preview")),
            "runtime_doctor_status": doctor.get("status"),
            "adapter_readiness": adapter_state.get("readiness"),
            "live_product_readiness": None if not live_required else live_ready,
        },
        "commands": {
            "start_check": f"agentops operator start-check --adapter {adapter} --limit 8",
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
