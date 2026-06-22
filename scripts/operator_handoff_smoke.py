#!/usr/bin/env python3
"""Verify operator handoff is read-only, redacted, and contains loop work order state."""

from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(
    base_url: str,
    path: str,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict]:
    req_headers = {"Content-Type": "application/json"}
    req_headers.update(headers or {})
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers=req_headers, method=method)
    try:
        with urlopen(req, timeout=45) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _ = http_json(base_url, "/api/operator/handoff?limit=1")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_fingerprint(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        result = {}
        for table in ["audit_logs", "runtime_events", "tasks", "runs", "memories", "approvals", "agent_plans", "plan_evidence_manifests"]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return result
    finally:
        conn.close()


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def validate_payload(payload: dict, label: str, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-operator", f"{label} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "operator_handoff", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") in {"blocked", "attention", "ready", "unknown"}, f"{label} status wrong: {payload}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing: {payload}", failures)
    auth = payload.get("auth") or {}
    require(auth.get("mode") in {"local_dev_no_token", "global_api_key", "agent_token", "agent_session"}, f"{label} auth mode missing: {auth}", failures)
    require(auth.get("required_scope") == "tasks:read", f"{label} auth required scope wrong: {auth}", failures)
    require(auth.get("token_omitted") is True, f"{label} auth token omission missing: {auth}", failures)
    loop_health = payload.get("loop_health") or {}
    require(loop_health.get("operation") == "operator_loop_health", f"{label} loop_health operation missing: {loop_health}", failures)
    require(loop_health.get("status") in {"blocked", "attention", "ready", "unknown"}, f"{label} loop_health status wrong: {loop_health}", failures)
    require(isinstance(loop_health.get("score"), int), f"{label} loop_health score missing: {loop_health}", failures)
    require(0 <= int(loop_health.get("score") or 0) <= 100, f"{label} loop_health score out of range: {loop_health}", failures)
    require(isinstance(loop_health.get("gates") or {}, dict), f"{label} loop_health gates missing: {loop_health}", failures)
    require(isinstance(loop_health.get("risks") or [], list), f"{label} loop_health risks missing: {loop_health}", failures)
    require(loop_health.get("token_omitted") is True, f"{label} loop_health token omission missing: {loop_health}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} should not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} should not execute live work: {safety}", failures)
    summary = payload.get("summary") or {}
    for key in [
        "loop_package_items",
        "operator_actions",
        "receipt_required",
        "receipt_verified",
        "receipt_missing",
        "receipt_stale",
        "receipt_evaluation_required",
        "receipt_evaluated",
        "receipt_evaluation_fail",
        "receipt_evaluation_missing",
        "receipt_failure_memory_candidates",
        "receipt_failure_memory_failed_receipts",
        "receipt_failure_memory_existing_candidates",
        "receipt_failure_memory_work_items",
        "advance_loop_work_items",
    ]:
        require(isinstance(summary.get(key), int), f"{label} summary.{key} missing: {summary}", failures)
    loop_health_gates = loop_health.get("gates") or {}
    receipt_eval_gate = loop_health_gates.get("receipt_evaluations") or {}
    require(receipt_eval_gate.get("status") in {"pass", "attention", "blocked"}, f"{label} receipt evaluation gate missing: {receipt_eval_gate}", failures)
    for key in ["required", "evaluated", "failed", "missing", "coverage_percent"]:
        require(isinstance(receipt_eval_gate.get(key), int), f"{label} receipt evaluation gate {key} missing: {receipt_eval_gate}", failures)
    receipt_failure_gate = loop_health_gates.get("receipt_failure_memory") or {}
    require(receipt_failure_gate.get("status") in {"pass", "attention"}, f"{label} receipt failure memory gate missing: {receipt_failure_gate}", failures)
    for key in ["candidates", "failed_receipts", "existing_candidates", "work_items"]:
        require(isinstance(receipt_failure_gate.get(key), int), f"{label} receipt failure memory gate {key} missing: {receipt_failure_gate}", failures)
    remediation_workflow_gate = loop_health_gates.get("evidence_remediation_workflow") or {}
    require(
        remediation_workflow_gate.get("status") in {"pass", "attention", "blocked"},
        f"{label} evidence remediation workflow gate missing: {remediation_workflow_gate}",
        failures,
    )
    for key in [
        "items",
        "steps",
        "ready_steps",
        "blocked_steps",
        "receipt_required",
        "receipt_verified",
        "receipt_missing",
    ]:
        require(
            isinstance(remediation_workflow_gate.get(key), int),
            f"{label} evidence remediation workflow gate {key} missing: {remediation_workflow_gate}",
            failures,
        )
    score_parts = loop_health.get("score_parts") or {}
    require(isinstance(score_parts.get("receipt_evaluations"), int), f"{label} receipt evaluation score part missing: {score_parts}", failures)
    work_order = payload.get("work_order") or {}
    require(work_order.get("method") == "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD", f"{label} method missing: {work_order}", failures)
    require(isinstance(work_order.get("commands") or [], list), f"{label} commands missing: {work_order}", failures)
    action_package = work_order.get("action_package") or {}
    require(action_package.get("operation") == "loop_action_package", f"{label} action_package missing: {action_package}", failures)
    evidence_work_order = work_order.get("evidence_report") or {}
    require(evidence_work_order.get("operation") == "operator_evidence_report_work_order", f"{label} evidence report work order missing: {evidence_work_order}", failures)
    require(evidence_work_order.get("status") in {"ready", "attention", "blocked", "unavailable", "unknown"}, f"{label} evidence report status wrong: {evidence_work_order}", failures)
    require(isinstance(evidence_work_order.get("action_signature"), str), f"{label} evidence report action signature missing: {evidence_work_order}", failures)
    require(isinstance((evidence_work_order.get("summary") or {}).get("runs"), int), f"{label} evidence report summary missing: {evidence_work_order}", failures)
    require(isinstance(evidence_work_order.get("runs") or [], list), f"{label} evidence report runs missing: {evidence_work_order}", failures)
    require(isinstance(evidence_work_order.get("next_actions") or [], list), f"{label} evidence report next_actions missing: {evidence_work_order}", failures)
    evidence_safety = evidence_work_order.get("safety") or {}
    evidence_receipt_state = evidence_work_order.get("receipt_state") or {}
    require(evidence_receipt_state.get("status") in {"missing", "recorded", "verified", "failed", "skipped"}, f"{label} evidence report receipt state missing: {evidence_receipt_state}", failures)
    require(evidence_receipt_state.get("action_signature") == evidence_work_order.get("action_signature"), f"{label} evidence report receipt signature mismatch: {evidence_receipt_state}", failures)
    require(evidence_safety.get("read_only") is True, f"{label} evidence report work order should be read-only: {evidence_safety}", failures)
    require(evidence_safety.get("ledger_mutated") is False, f"{label} evidence report work order should not mutate ledger: {evidence_safety}", failures)
    require(evidence_work_order.get("token_omitted") is True, f"{label} evidence report token omission missing: {evidence_work_order}", failures)
    remediation_chain = evidence_work_order.get("remediation_chain") or {}
    require(remediation_chain.get("operation") == "evidence_remediation_chain", f"{label} evidence remediation chain missing: {remediation_chain}", failures)
    require(remediation_chain.get("status") in {"attention", "empty"}, f"{label} evidence remediation chain status wrong: {remediation_chain}", failures)
    require(isinstance((remediation_chain.get("summary") or {}).get("items"), int), f"{label} evidence remediation chain summary missing: {remediation_chain}", failures)
    require(isinstance((remediation_chain.get("summary") or {}).get("workflow_steps"), int), f"{label} evidence remediation workflow summary missing: {remediation_chain}", failures)
    require(isinstance((remediation_chain.get("summary") or {}).get("workflow_ready_steps"), int), f"{label} evidence remediation ready step summary missing: {remediation_chain}", failures)
    require(isinstance((remediation_chain.get("summary") or {}).get("workflow_blocked_steps"), int), f"{label} evidence remediation blocked step summary missing: {remediation_chain}", failures)
    require(isinstance((remediation_chain.get("summary") or {}).get("workflow_receipt_required"), int), f"{label} evidence remediation receipt-required summary missing: {remediation_chain}", failures)
    require(isinstance((remediation_chain.get("summary") or {}).get("workflow_receipt_verified"), int), f"{label} evidence remediation receipt-verified summary missing: {remediation_chain}", failures)
    require(isinstance((remediation_chain.get("summary") or {}).get("workflow_receipt_missing"), int), f"{label} evidence remediation receipt-missing summary missing: {remediation_chain}", failures)
    require(isinstance(remediation_chain.get("items") or [], list), f"{label} evidence remediation chain items missing: {remediation_chain}", failures)
    require(isinstance(remediation_chain.get("next_actions") or [], list), f"{label} evidence remediation chain next_actions missing: {remediation_chain}", failures)
    chain_safety = remediation_chain.get("safety") or {}
    require(chain_safety.get("read_only") is True, f"{label} evidence remediation chain should be read-only: {chain_safety}", failures)
    require(chain_safety.get("explicit_mutating_commands_are_not_auto_run") is True, f"{label} remediation chain mutating boundary missing: {chain_safety}", failures)
    for item in remediation_chain.get("items") or []:
        require(item.get("operation") == "evidence_remediation_work_item", f"{label} remediation item operation wrong: {item}", failures)
        require(str(item.get("action_id") or "").startswith("evidence_remediation:"), f"{label} remediation action_id missing: {item}", failures)
        require(isinstance(item.get("action_signature"), str), f"{label} remediation action_signature missing: {item}", failures)
        require(item.get("receipt_source") == "handoff.evidence_remediation", f"{label} remediation receipt source missing: {item}", failures)
        require((item.get("receipt_state") or {}).get("action_signature") == item.get("action_signature"), f"{label} remediation receipt signature mismatch: {item}", failures)
        require(str(item.get("preview_command") or "").startswith("agentops operator remediate-evidence-gap --run-id "), f"{label} remediation preview command missing: {item}", failures)
        require(str(item.get("dispatch_command") or "").startswith("agentops commander dispatch-package --task-id "), f"{label} remediation dispatch command missing: {item}", failures)
        require(str(item.get("verify_command") or "").startswith("agentops operator evidence-report --run-id "), f"{label} remediation verify command missing: {item}", failures)
        require(str(item.get("receipt_record_command") or "").startswith("agentops operator record-action-receipt "), f"{label} remediation receipt command missing: {item}", failures)
        require(str(item.get("receipt_verify_record_command") or "").endswith("--status verified --confirm-record"), f"{label} remediation verify receipt command missing: {item}", failures)
        workflow_steps = item.get("workflow_steps") or []
        require(isinstance(workflow_steps, list) and len(workflow_steps) >= 6, f"{label} remediation workflow steps missing: {item}", failures)
        step_ids = {str(step.get("id") or "") for step in workflow_steps}
        for step_id in ["preview", "create_task", "dispatch_package", "plan_evidence", "synthesize", "close_gap"]:
            require(step_id in step_ids, f"{label} remediation workflow step {step_id} missing: {workflow_steps}", failures)
        next_step = item.get("next_workflow_step") or {}
        require(not next_step or next_step.get("id") in step_ids, f"{label} remediation next workflow step invalid: {item}", failures)
        for step in workflow_steps:
            require(step.get("status") in {"ready", "blocked", "attention", "pending", "completed", "not_applicable"}, f"{label} remediation step status wrong: {step}", failures)
            require(isinstance(step.get("mutating"), bool), f"{label} remediation step mutating flag missing: {step}", failures)
            require(isinstance(step.get("confirm_required"), bool), f"{label} remediation step confirm flag missing: {step}", failures)
            require(isinstance(step.get("auto_advance_allowed"), bool), f"{label} remediation step auto-advance flag missing: {step}", failures)
            if step.get("status") == "ready":
                require(isinstance(step.get("ready_reason"), str) and step.get("ready_reason"), f"{label} remediation ready step reason missing: {step}", failures)
                require(step.get("next_safe_command_kind") == "action", f"{label} remediation ready step next command kind wrong: {step}", failures)
                require(isinstance(step.get("next_safe_command"), str) and step.get("next_safe_command"), f"{label} remediation ready step next command missing: {step}", failures)
            if step.get("status") == "blocked":
                require(isinstance(step.get("blocked_reason"), str) and step.get("blocked_reason"), f"{label} remediation blocked step reason missing: {step}", failures)
                if step.get("id") != "preview":
                    require(isinstance(step.get("prerequisite_step"), str) and step.get("prerequisite_step"), f"{label} remediation blocked step prerequisite missing: {step}", failures)
            if step.get("command"):
                receipt_state = step.get("receipt_state") or {}
                require(str(step.get("action_id") or "").startswith("evidence_remediation:"), f"{label} remediation step action_id missing: {step}", failures)
                require(isinstance(step.get("action_signature"), str), f"{label} remediation step action_signature missing: {step}", failures)
                require(receipt_state.get("required") is True, f"{label} remediation step receipt required missing: {step}", failures)
                require(receipt_state.get("action_signature") == step.get("action_signature"), f"{label} remediation step receipt signature mismatch: {step}", failures)
                require(str(step.get("receipt_record_command") or "").startswith("agentops operator record-action-receipt "), f"{label} remediation step receipt record command missing: {step}", failures)
                require(str(step.get("receipt_verify_record_command") or "").endswith("--status verified --confirm-record"), f"{label} remediation step verify receipt command missing: {step}", failures)
                require(str(step.get("receipt_next_command") or "").startswith("agentops operator record-action-receipt "), f"{label} remediation step receipt next command missing: {step}", failures)
            if step.get("id") == "preview":
                require(step.get("auto_advance_allowed") is True, f"{label} remediation preview should be auto-advanceable: {step}", failures)
                require(step.get("mutating") is False, f"{label} remediation preview must be read-only: {step}", failures)
                require((step.get("receipt_state") or {}).get("source") == "handoff.evidence_remediation", f"{label} remediation preview receipt source mismatch: {step}", failures)
            if step.get("mutating"):
                require(step.get("auto_advance_allowed") is False, f"{label} mutating remediation step must not auto-advance: {step}", failures)
                require(step.get("receipt_required_before_mutation") is True, f"{label} mutating remediation step should require prior receipt: {step}", failures)
        require((item.get("safety") or {}).get("preview_read_only") is True, f"{label} remediation preview safety missing: {item}", failures)
        require((item.get("safety") or {}).get("mutating_steps_are_explicit") is True, f"{label} remediation mutating step boundary missing: {item}", failures)
        require((item.get("safety") or {}).get("server_executes_shell") is False, f"{label} remediation server shell boundary missing: {item}", failures)
    advance_loop = work_order.get("advance_loop") or {}
    require(advance_loop.get("operation") == "advance_loop_work_order", f"{label} advance loop work order missing: {advance_loop}", failures)
    require(advance_loop.get("status") in {"attention", "empty"}, f"{label} advance loop status wrong: {advance_loop}", failures)
    require("advance-loop" in str(advance_loop.get("preview_command") or ""), f"{label} advance loop preview command missing: {advance_loop}", failures)
    require("--confirm-advance" in str(advance_loop.get("confirm_command") or ""), f"{label} advance loop confirm command missing: {advance_loop}", failures)
    advance_policy = advance_loop.get("policy") or {}
    require(advance_policy.get("policy_id") == "advance_loop_local_bounded_v1", f"{label} advance loop policy id missing: {advance_policy}", failures)
    require(advance_policy.get("server_executes_shell") is False, f"{label} advance loop policy should keep shell local: {advance_policy}", failures)
    require((advance_loop.get("summary") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"{label} advance loop summary policy id missing: {advance_loop}", failures)
    advance_safety = advance_loop.get("safety") or {}
    selected = advance_loop.get("selected_item") or {}
    if selected.get("gate_id") == "evidence_report":
        require(selected.get("action_signature") == evidence_work_order.get("action_signature"), f"{label} selected evidence action signature mismatch: {selected}", failures)
    require(advance_safety.get("read_only") is True, f"{label} advance loop handoff should be read-only: {advance_safety}", failures)
    require(advance_safety.get("server_shell_execution") is False, f"{label} advance loop should not execute shell from server: {advance_safety}", failures)
    require(advance_loop.get("token_omitted") is True, f"{label} advance loop token omission missing: {advance_loop}", failures)
    control_summary = payload.get("control_summary") or {}
    control_step = control_summary.get("recommended_step") or {}
    require(control_summary.get("operation") == "operator_loop_control_summary", f"{label} loop control summary missing: {control_summary}", failures)
    require(control_summary.get("status") in {"ready", "attention", "blocked"}, f"{label} loop control status wrong: {control_summary}", failures)
    require(control_summary.get("copy_only") is True, f"{label} loop control copy-only proof missing: {control_summary}", failures)
    require(control_summary.get("server_executes_shell") is False, f"{label} loop control server shell boundary missing: {control_summary}", failures)
    require(control_step.get("step_id") == "handoff_advance_loop", f"{label} loop control recommended step wrong: {control_step}", failures)
    require(str(control_summary.get("next_command") or "").startswith("agentops operator advance-loop"), f"{label} loop control next command missing: {control_summary}", failures)
    require((control_step.get("control_mode") or control_summary.get("mode")) in {"read_only_copy", "human_confirm_required"}, f"{label} loop control mode wrong: {control_summary}", failures)
    require(control_summary.get("token_omitted") is True and control_step.get("token_omitted") is True, f"{label} loop control token omission missing: {control_summary}", failures)
    receipt_failure_work_order = work_order.get("receipt_failure_memory") or {}
    require(receipt_failure_work_order.get("operation") == "receipt_failure_memory_work_order", f"{label} receipt failure memory work order missing: {receipt_failure_work_order}", failures)
    require(receipt_failure_work_order.get("status") in {"attention", "empty"}, f"{label} receipt failure memory work order status wrong: {receipt_failure_work_order}", failures)
    require(isinstance((receipt_failure_work_order.get("summary") or {}).get("items"), int), f"{label} receipt failure memory work order summary missing: {receipt_failure_work_order}", failures)
    require(isinstance(receipt_failure_work_order.get("items") or [], list), f"{label} receipt failure memory work order items missing: {receipt_failure_work_order}", failures)
    require(isinstance(receipt_failure_work_order.get("next_actions") or [], list), f"{label} receipt failure memory work order next_actions missing: {receipt_failure_work_order}", failures)
    receipt_failure_work_safety = receipt_failure_work_order.get("safety") or {}
    require(receipt_failure_work_safety.get("read_only") is True, f"{label} receipt failure memory work order should be read-only: {receipt_failure_work_safety}", failures)
    require(receipt_failure_work_safety.get("ledger_mutated") is False, f"{label} receipt failure memory work order should not mutate ledger: {receipt_failure_work_safety}", failures)
    require(receipt_failure_work_safety.get("create_requires_confirm") is True, f"{label} receipt failure memory work order confirm gate missing: {receipt_failure_work_safety}", failures)
    require(receipt_failure_work_order.get("token_omitted") is True, f"{label} receipt failure memory work order token omission missing: {receipt_failure_work_order}", failures)
    for item in receipt_failure_work_order.get("items") or []:
        require(item.get("operation") == "receipt_failure_memory_item", f"{label} receipt failure memory item operation wrong: {item}", failures)
        require("propose-receipt-failure-memory" in str(item.get("preview_command") or ""), f"{label} receipt failure memory preview command missing: {item}", failures)
        require("--confirm-create" in str(item.get("create_command") or ""), f"{label} receipt failure memory create command missing confirm: {item}", failures)
        require(str(item.get("review_command") or "").startswith("agentops review queue"), f"{label} receipt failure memory review command missing: {item}", failures)
        require((item.get("safety") or {}).get("preview_read_only") is True, f"{label} receipt failure memory item preview safety missing: {item}", failures)
        require((item.get("safety") or {}).get("create_requires_confirm") is True, f"{label} receipt failure memory item confirm safety missing: {item}", failures)
        require(item.get("token_omitted") is True, f"{label} receipt failure memory item token omission missing: {item}", failures)
    receipt_state = payload.get("receipt_state") or {}
    require(isinstance((receipt_state.get("coverage") or {}).get("required"), int), f"{label} receipt coverage missing: {receipt_state}", failures)
    require(isinstance(receipt_state.get("recent") or [], list), f"{label} recent receipts missing: {receipt_state}", failures)
    failure_memory_state = receipt_state.get("failure_memory") or {}
    require((failure_memory_state.get("work_order") or {}).get("operation") == "receipt_failure_memory_work_order", f"{label} receipt_state failure memory work order missing: {failure_memory_state}", failures)
    review_state = payload.get("review_state") or {}
    require(isinstance(review_state.get("loop_record") or {}, dict), f"{label} review loop_record missing: {review_state}", failures)
    sources = payload.get("sources") or {}
    require("loop_audit" in sources and "action_plan" in sources and "evidence_report" in sources, f"{label} sources missing: {sources}", failures)
    evidence_source = sources.get("evidence_report") or {}
    require(isinstance((evidence_source.get("summary") or {}).get("runs"), int), f"{label} evidence report source summary missing: {evidence_source}", failures)
    require("read-only" in (payload.get("contract") or ""), f"{label} contract missing: {payload}", failures)


def seed_repeated_failed_receipts(base_url: str, outputs: list[str], failures: list[str]) -> str:
    status, action_plan = http_json(base_url, "/api/operator/action-plan?limit=30")
    outputs.append(json.dumps(action_plan, ensure_ascii=False))
    require(status == 200, f"seed action-plan status mismatch: {status} {action_plan}", failures)
    seed_action = next((
        item for item in action_plan.get("actions") or []
        if item.get("command") and item.get("action_signature") and item.get("receipt_required") is True
    ), {})
    require(bool(seed_action), f"seed action for failed receipts missing: {action_plan.get('actions')}", failures)
    if not seed_action:
        return ""
    payload = {
        "action_command": str(seed_action.get("command") or "agentops worker status"),
        "verify_command": str(seed_action.get("verify_command") or "agentops operator action-plan --limit 20"),
        "action_id": str(seed_action.get("action_id") or "smoke:handoff-failed-action"),
        "action_signature": str(seed_action.get("action_signature") or ""),
        "source": "smoke.operator_handoff.failed",
        "status": "failed",
        "result_summary": "Smoke failed receipt should appear as a handoff memory work item.",
    }
    action_hash = ""
    for index in range(2):
        repeated_payload = dict(payload)
        repeated_payload["source"] = f"smoke.operator_handoff.failed.{index}"
        status, receipt = http_json(base_url, "/api/operator/action-receipts", method="POST", payload=repeated_payload)
        outputs.append(json.dumps(receipt, ensure_ascii=False))
        require(status == 201, f"failed receipt POST status mismatch: {status} {receipt}", failures)
        item = receipt.get("receipt") or {}
        evaluation = receipt.get("evaluation") or {}
        action_hash = action_hash or str(item.get("action_hash") or "")
        require(evaluation.get("pass_fail") == "fail", f"seed failed receipt should fail evaluation: {evaluation}", failures)
    return action_hash


def validate_receipt_failure_work_item(payload: dict, expected_action_hash: str, label: str, failures: list[str]) -> None:
    work_order = ((payload.get("work_order") or {}).get("receipt_failure_memory") or {})
    items = work_order.get("items") or []
    item = next((row for row in items if row.get("action_hash") == expected_action_hash), {})
    require(bool(item), f"{label} expected receipt failure work item missing for {expected_action_hash}: {work_order}", failures)
    if not item:
        return
    require(int(item.get("failures") or 0) >= 2, f"{label} receipt failure work item count wrong: {item}", failures)
    require("propose-receipt-failure-memory" in str(item.get("preview_command") or ""), f"{label} preview command wrong: {item}", failures)
    require("--confirm-create" in str(item.get("create_command") or ""), f"{label} create command lacks confirm: {item}", failures)
    require(str(item.get("review_command") or "").startswith("agentops review queue"), f"{label} review command wrong: {item}", failures)
    commands = (payload.get("work_order") or {}).get("commands") or []
    require(item.get("preview_command") in commands, f"{label} preview command not promoted to handoff commands: {commands}", failures)


def create_enrollment(base_url: str, workspace_id: str, agent_id: str, scopes: list[str]) -> tuple[str, str]:
    status, payload = http_json(
        base_url,
        "/api/agent-gateway/enrollment/create",
        method="POST",
        payload={
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "name": f"Handoff Scope {agent_id}",
            "runtime_type": "mock",
            "scopes": scopes,
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        },
    )
    if status != 201 or not payload.get("token_id") or not payload.get("token"):
        raise RuntimeError(f"enrollment create failed: {status} {payload}")
    return str(payload["token_id"]), str(payload["token"])


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-operator-handoff-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_BASE_URL"] = base_url
        env.pop("AGENTOPS_API_KEY", None)
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            failed_action_hash = seed_repeated_failed_receipts(base_url, outputs, failures)
            before = db_fingerprint(db_path)
            status, api_payload = http_json(base_url, "/api/operator/handoff?limit=8")
            outputs.append(json.dumps(api_payload, ensure_ascii=False))
            require(status == 200, f"API status mismatch: {status} {api_payload}", failures)
            validate_payload(api_payload, "api", failures)
            validate_receipt_failure_work_item(api_payload, failed_action_hash, "api", failures)
            invalid_limit_status, invalid_limit_payload = http_json(base_url, "/api/operator/handoff?limit=not-an-int")
            outputs.append(json.dumps(invalid_limit_payload, ensure_ascii=False))
            require(invalid_limit_status == 200, f"invalid limit should not 500: {invalid_limit_status} {invalid_limit_payload}", failures)
            validate_payload(invalid_limit_payload, "invalid_limit_api", failures)
            validate_receipt_failure_work_item(invalid_limit_payload, failed_action_hash, "invalid_limit_api", failures)
            invalid_token_status, invalid_token_payload = http_json(
                base_url,
                "/api/operator/handoff?limit=8",
                headers={"Authorization": "Bearer not-a-real-token"},
            )
            outputs.append(json.dumps(invalid_token_payload, ensure_ascii=False))
            require(invalid_token_status == 401, f"invalid token should be rejected: {invalid_token_status} {invalid_token_payload}", failures)
            require(invalid_token_payload.get("error") == "unauthorized", f"invalid token error mismatch: {invalid_token_payload}", failures)

            workspace_a = "ws_handoff_scope_a"
            workspace_b = "ws_handoff_scope_b"
            agent_id = "agt_handoff_scope"
            _token_id, token = create_enrollment(base_url, workspace_a, agent_id, ["tasks:read", "agents:heartbeat"])
            scoped_headers = {
                "Authorization": f"Bearer {token}",
                "X-AgentOps-Workspace-Id": workspace_a,
            }
            status, scoped_payload = http_json(base_url, "/api/operator/handoff?limit=4", headers=scoped_headers)
            outputs.append(json.dumps(scoped_payload, ensure_ascii=False))
            require(status == 200, f"scoped token handoff failed: {status} {scoped_payload}", failures)
            validate_payload(scoped_payload, "scoped_api", failures)
            scoped_auth = scoped_payload.get("auth") or {}
            require(scoped_auth.get("mode") == "agent_token", f"scoped auth mode mismatch: {scoped_auth}", failures)
            require(scoped_auth.get("scoped") is True, f"scoped auth flag missing: {scoped_auth}", failures)
            require(scoped_auth.get("workspace_id") == workspace_a, f"scoped workspace mismatch: {scoped_auth}", failures)
            require(scoped_auth.get("agent_id") == agent_id, f"scoped agent mismatch: {scoped_auth}", failures)

            status, forbidden_payload = http_json(
                base_url,
                "/api/operator/handoff?limit=4",
                headers={"Authorization": f"Bearer {token}", "X-AgentOps-Workspace-Id": workspace_b},
            )
            outputs.append(json.dumps(forbidden_payload, ensure_ascii=False))
            require(status == 403, f"cross-workspace handoff should fail: {status} {forbidden_payload}", failures)
            require(forbidden_payload.get("error") == "forbidden", f"cross-workspace error mismatch: {forbidden_payload}", failures)

            _limited_token_id, limited_token = create_enrollment(base_url, workspace_a, "agt_handoff_limited", ["agents:heartbeat"])
            status, limited_payload = http_json(
                base_url,
                "/api/operator/handoff?limit=4",
                headers={"Authorization": f"Bearer {limited_token}", "X-AgentOps-Workspace-Id": workspace_a},
            )
            outputs.append(json.dumps(limited_payload, ensure_ascii=False))
            require(status == 403, f"missing-scope handoff should fail: {status} {limited_payload}", failures)
            require(limited_payload.get("error") == "forbidden", f"missing-scope error mismatch: {limited_payload}", failures)

            cli_proc = subprocess.run(
                [str(CLI), "operator", "handoff", "--limit", "8"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            outputs.extend([cli_proc.stdout, cli_proc.stderr])
            cli_payload = load_json(cli_proc.stdout)
            require(cli_proc.returncode == 0, f"CLI failed: {cli_proc.returncode} {cli_proc.stderr}", failures)
            validate_payload(cli_payload, "cli", failures)
            validate_receipt_failure_work_item(cli_payload, failed_action_hash, "cli", failures)
            scoped_env = env.copy()
            scoped_env["AGENTOPS_API_KEY"] = token
            scoped_env["AGENTOPS_WORKSPACE_ID"] = workspace_a
            scoped_env["AGENTOPS_AGENT_ID"] = agent_id
            scoped_cli_proc = subprocess.run(
                [str(CLI), "operator", "handoff", "--limit", "4"],
                cwd=ROOT,
                env=scoped_env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            outputs.extend([scoped_cli_proc.stdout, scoped_cli_proc.stderr])
            scoped_cli_payload = load_json(scoped_cli_proc.stdout)
            require(scoped_cli_proc.returncode == 0, f"scoped CLI failed: {scoped_cli_proc.returncode} {scoped_cli_proc.stderr}", failures)
            validate_payload(scoped_cli_payload, "scoped_cli", failures)
            scoped_cli_auth = scoped_cli_payload.get("auth") or {}
            require(scoped_cli_auth.get("scoped") is True, f"scoped CLI auth missing: {scoped_cli_auth}", failures)
            require(scoped_cli_auth.get("workspace_id") == workspace_a, f"scoped CLI workspace mismatch: {scoped_cli_auth}", failures)
            after = db_fingerprint(db_path)
            for table in ["tasks", "runs", "memories", "approvals", "agent_plans", "plan_evidence_manifests"]:
                require(before.get(table) == after.get(table), f"handoff changed read-only table {table}: {before} -> {after}", failures)
            require(after.get("audit_logs", 0) >= before.get("audit_logs", 0), f"audit count regressed: {before} -> {after}", failures)
            require(not leaked_secret("\n".join(outputs)), "handoff output leaked token-like material", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])
    result = {
        "ok": not failures,
        "operation": "operator_handoff_smoke",
        "failures": failures,
        "secret_leaked": leaked_secret("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
