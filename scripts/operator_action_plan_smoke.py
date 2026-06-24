#!/usr/bin/env python3
"""Verify the read-only operator action-plan API and CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
DEFAULT_DB = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = Request(base_url.rstrip("/") + path, headers={"Content-Type": "application/json"}, method="GET")
    try:
        with urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def run_cli(base_url: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def db_fingerprint(db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        result = {}
        for table, timestamp_col in [
            ("approvals", "created_at"),
            ("memories", "updated_at"),
            ("artifacts", "created_at"),
            ("tasks", "updated_at"),
            ("runs", "created_at"),
            ("tool_calls", "created_at"),
            ("evaluations", "created_at"),
            ("evaluation_case_candidates", "updated_at"),
            ("evaluation_case_runs", "created_at"),
            ("agent_plans", "updated_at"),
            ("plan_evidence_manifests", "updated_at"),
            ("audit_logs", "created_at"),
            ("runtime_events", "created_at"),
        ]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                continue
            row = conn.execute(f"SELECT COUNT(*) AS count, COALESCE(MAX({timestamp_col}), '') AS max_ts FROM {table}").fetchone()
            result[table] = {"count": int(row["count"] or 0), "max_ts": row["max_ts"] or ""}
        return result
    finally:
        conn.close()


def validate_plan(payload: dict, label: str, failures: list[str], limit: int) -> None:
    require(payload.get("provider") == "agentops-operator", f"{label} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "action_plan", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") in {"blocked", "attention", "ready"}, f"{label} bad status: {payload}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} must not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} must not run live work: {safety}", failures)
    require(safety.get("raw_prompt_omitted") is True, f"{label} raw prompt omission missing", failures)
    require(safety.get("raw_response_omitted") is True, f"{label} raw response omission missing", failures)
    summary = payload.get("summary") or {}
    for key in [
        "actions",
        "blocked",
        "attention",
        "ready",
        "review_items_total",
        "failed_evaluation_case_runs",
        "waiting_deliveries",
        "needs_attention_deliveries",
        "stuck_worker_tasks",
        "stuck_workflow_jobs",
        "remediation_packages",
        "remediation_ready_for_review",
        "remediation_pending_reviews",
        "remediation_promoted_deliveries",
        "evidence_gap_runs",
        "missing_plan_runs",
        "missing_plan_evidence_manifests",
        "unverified_plan_evidence_manifests",
        "remediated_evidence_gap_runs",
        "blocked_evidence_gap_runs",
        "evidence_synthesis_ready_runs",
        "evidence_synthesis_pending_runs",
        "evidence_synthesis_promoted_runs",
        "evidence_gap_closure_ready_runs",
        "closed_evidence_gap_runs",
        "waived_evidence_gap_runs",
        "task_intake_checked",
        "task_intake_ready",
        "task_intake_blocked",
        "task_intake_attention",
        "task_intake_missing_agent_plan",
        "dispatch_evidence_proofs",
        "dispatch_evidence_ready",
        "dispatch_evidence_waiting_approval",
        "dispatch_evidence_verified_manifests",
        "operator_health_risks",
        "operator_health_blocked",
        "operator_health_attention",
        "local_service_control_actions",
        "local_service_control_receipt_missing",
        "local_service_control_readback_missing",
        "workflow_job_recovery_actions",
        "workflow_job_recovery_stuck_jobs",
        "workflow_job_recovery_retryable_failed_jobs",
        "workflow_job_recovery_receipt_missing",
        "workflow_job_recovery_receipt_verified",
        "evidence_remediation_workflow_actions",
        "evidence_remediation_workflow_mutating",
        "evidence_remediation_workflow_confirm_required",
        "evidence_remediation_workflow_receipt_missing",
        "evidence_remediation_workflow_receipt_verified",
        "action_receipts",
        "action_receipts_recorded",
        "action_receipts_verified",
        "action_receipts_failed",
        "action_receipts_evaluated",
        "action_receipts_evaluation_pass",
        "action_receipts_evaluation_fail",
        "receipt_failure_memory_candidates",
        "receipt_failure_memory_failed_receipts",
        "receipt_failure_memory_existing_candidates",
        "receipt_required_actions",
        "receipt_verified_actions",
        "receipt_missing_actions",
        "receipt_missing_verified_actions",
        "receipt_stale_actions",
        "receipt_evaluation_required_actions",
        "receipt_evaluated_actions",
        "receipt_evaluation_pass_actions",
        "receipt_evaluation_fail_actions",
        "receipt_evaluation_missing_actions",
        "receipt_evaluation_coverage_percent",
        "receipt_coverage_percent",
        "receipt_lookup_window",
    ]:
        require(isinstance(summary.get(key), int), f"{label} summary.{key} missing: {summary}", failures)
    receipt_coverage = payload.get("receipt_coverage") or {}
    require(receipt_coverage.get("required") == summary.get("receipt_required_actions"), f"{label} receipt coverage required mismatch: {receipt_coverage} {summary}", failures)
    require(receipt_coverage.get("verified") == summary.get("receipt_verified_actions"), f"{label} receipt coverage verified mismatch: {receipt_coverage} {summary}", failures)
    require(receipt_coverage.get("stale") == summary.get("receipt_stale_actions"), f"{label} receipt coverage stale mismatch: {receipt_coverage} {summary}", failures)
    require(receipt_coverage.get("missing") == summary.get("receipt_missing_actions"), f"{label} receipt coverage missing mismatch: {receipt_coverage} {summary}", failures)
    require(receipt_coverage.get("coverage_percent") == summary.get("receipt_coverage_percent"), f"{label} receipt coverage percent mismatch: {receipt_coverage} {summary}", failures)
    require(receipt_coverage.get("status") in {"ready", "attention"}, f"{label} receipt coverage status wrong: {receipt_coverage}", failures)
    require(receipt_coverage.get("evaluation_required") == summary.get("receipt_evaluation_required_actions"), f"{label} receipt eval required mismatch: {receipt_coverage} {summary}", failures)
    require(receipt_coverage.get("evaluated") == summary.get("receipt_evaluated_actions"), f"{label} receipt eval evaluated mismatch: {receipt_coverage} {summary}", failures)
    require(receipt_coverage.get("evaluation_fail") == summary.get("receipt_evaluation_fail_actions"), f"{label} receipt eval fail mismatch: {receipt_coverage} {summary}", failures)
    require(receipt_coverage.get("evaluation_coverage_percent") == summary.get("receipt_evaluation_coverage_percent"), f"{label} receipt eval coverage mismatch: {receipt_coverage} {summary}", failures)
    require(receipt_coverage.get("evaluation_status") in {"ready", "attention", "blocked"}, f"{label} receipt eval status wrong: {receipt_coverage}", failures)
    require(isinstance(summary.get("recommended_adapter"), str), f"{label} recommended_adapter missing: {summary}", failures)
    actions = payload.get("actions")
    require(isinstance(actions, list), f"{label} actions missing", failures)
    if not isinstance(actions, list):
        actions = []
    require(len(actions) <= limit, f"{label} ignored limit: {len(actions)} > {limit}", failures)
    require(bool(payload.get("top_commands")), f"{label} top_commands missing", failures)
    require(isinstance(payload.get("source_status"), dict), f"{label} source_status missing", failures)
    require("remediation_loop" in (payload.get("source_status") or {}), f"{label} remediation source status missing: {payload.get('source_status')}", failures)
    require("execution_evidence" in (payload.get("source_status") or {}), f"{label} execution evidence source status missing: {payload.get('source_status')}", failures)
    require("task_intake" in (payload.get("source_status") or {}), f"{label} task intake source status missing: {payload.get('source_status')}", failures)
    require("dispatch_evidence" in (payload.get("source_status") or {}), f"{label} dispatch evidence source status missing: {payload.get('source_status')}", failures)
    require("operator_health" in (payload.get("source_status") or {}), f"{label} operator health source status missing: {payload.get('source_status')}", failures)
    require("local_service_control" in (payload.get("source_status") or {}), f"{label} local service-control source status missing: {payload.get('source_status')}", failures)
    require("workflow_job_recovery" in (payload.get("source_status") or {}), f"{label} workflow job recovery source status missing: {payload.get('source_status')}", failures)
    require("evidence_remediation_workflow" in (payload.get("source_status") or {}), f"{label} evidence remediation workflow source status missing: {payload.get('source_status')}", failures)
    require("action_receipts" in (payload.get("source_status") or {}), f"{label} action receipts source status missing: {payload.get('source_status')}", failures)
    require("receipt_failure_memory" in (payload.get("source_status") or {}), f"{label} receipt failure memory source status missing: {payload.get('source_status')}", failures)
    evidence_source = payload.get("execution_evidence") or {}
    require(evidence_source.get("operation") == "execution_evidence_gaps", f"{label} execution evidence payload missing: {evidence_source}", failures)
    evidence_summary = evidence_source.get("summary") or {}
    dispatch_source = payload.get("dispatch_evidence") or {}
    require(dispatch_source.get("operation") == "dispatch_evidence_lane", f"{label} dispatch evidence payload missing: {dispatch_source}", failures)
    receipt_source = payload.get("action_receipts") or {}
    require(receipt_source.get("operation") == "operator_action_receipts", f"{label} action receipts payload missing: {receipt_source}", failures)
    receipt_failure_memory = payload.get("receipt_failure_memory") or {}
    require(receipt_failure_memory.get("operation") == "receipt_failure_memory_lane", f"{label} receipt failure memory payload missing: {receipt_failure_memory}", failures)
    operator_health_source = payload.get("operator_health") or {}
    require(operator_health_source.get("status") in {"blocked", "attention", "ready"}, f"{label} operator health source missing: {operator_health_source}", failures)
    operator_health_summary = operator_health_source.get("summary") or {}
    for key in ["components", "risks", "ready", "blocked", "attention", "review_items_total"]:
        require(isinstance(operator_health_summary.get(key), int), f"{label} operator health summary.{key} missing: {operator_health_summary}", failures)
    require(operator_health_summary.get("local_ui_write_guard_status") in {"pass", "warn", "fail", "unknown"}, f"{label} operator health write guard status missing: {operator_health_summary}", failures)
    operator_health_components = operator_health_source.get("components") or []
    require(any(item.get("id") == "local_ui_write_guard" for item in operator_health_components), f"{label} operator health missing local write guard component: {operator_health_components}", failures)
    operator_health_safety = operator_health_source.get("safety") or {}
    require(operator_health_safety.get("read_only") is True, f"{label} operator health read_only missing: {operator_health_safety}", failures)
    require(operator_health_safety.get("ledger_mutated") is False, f"{label} operator health must not mutate ledger: {operator_health_safety}", failures)
    workflow_recovery_source = payload.get("workflow_job_recovery") or {}
    require(workflow_recovery_source.get("operation") == "workflow_job_recovery", f"{label} workflow recovery source missing: {workflow_recovery_source}", failures)
    require(workflow_recovery_source.get("status") in {"blocked", "attention", "ready"}, f"{label} workflow recovery source status wrong: {workflow_recovery_source}", failures)
    workflow_recovery_summary = workflow_recovery_source.get("summary") or {}
    for key in ["actions", "stuck_jobs", "retryable_failed_jobs", "blocked", "attention", "receipt_missing", "receipt_verified"]:
        require(isinstance(workflow_recovery_summary.get(key), int), f"{label} workflow recovery summary.{key} missing: {workflow_recovery_summary}", failures)
    workflow_recovery_safety = workflow_recovery_source.get("safety") or {}
    require(workflow_recovery_safety.get("read_only") is True, f"{label} workflow recovery read_only missing: {workflow_recovery_safety}", failures)
    require(workflow_recovery_safety.get("ledger_mutated") is False, f"{label} workflow recovery must not mutate ledger: {workflow_recovery_safety}", failures)
    require(workflow_recovery_safety.get("live_execution_performed") is False, f"{label} workflow recovery must not run live work: {workflow_recovery_safety}", failures)
    remediation_workflow_source = payload.get("evidence_remediation_workflow") or {}
    require(remediation_workflow_source.get("status") in {"ready", "attention"}, f"{label} remediation workflow source missing: {remediation_workflow_source}", failures)
    remediation_workflow_summary = remediation_workflow_source.get("summary") or {}
    for key in ["actions", "mutating", "confirm_required", "receipt_missing", "receipt_verified"]:
        require(isinstance(remediation_workflow_summary.get(key), int), f"{label} remediation workflow summary.{key} missing: {remediation_workflow_summary}", failures)
    remediation_workflow_safety = remediation_workflow_source.get("safety") or {}
    require(remediation_workflow_safety.get("read_only") is True, f"{label} remediation workflow source read_only missing: {remediation_workflow_safety}", failures)
    require(remediation_workflow_safety.get("ledger_mutated") is False, f"{label} remediation workflow source must not mutate ledger: {remediation_workflow_safety}", failures)
    receipt_summary = receipt_source.get("summary") or {}
    for key in ["receipts", "recorded", "verified", "failed", "skipped", "evaluated", "evaluation_pass", "evaluation_fail"]:
        require(isinstance(receipt_summary.get(key), int), f"{label} action receipts summary.{key} missing: {receipt_summary}", failures)
    receipt_safety = receipt_source.get("safety") or {}
    require(receipt_safety.get("read_only") is True, f"{label} action receipts read_only missing: {receipt_safety}", failures)
    require(receipt_safety.get("ledger_mutated") is False, f"{label} action receipts must not mutate ledger: {receipt_safety}", failures)
    require(isinstance(evidence_summary.get("gap_runs"), int), f"{label} execution evidence gap count missing: {evidence_summary}", failures)
    for key in [
        "synthesis_ready_runs",
        "synthesis_pending_runs",
        "synthesis_promoted_runs",
        "closure_ready_runs",
        "closed_gap_runs",
        "waived_gap_runs",
    ]:
        require(isinstance(evidence_summary.get(key), int), f"{label} execution evidence {key} missing: {evidence_summary}", failures)
    evidence_safety = evidence_source.get("safety") or {}
    require(evidence_safety.get("read_only") is True, f"{label} execution evidence read_only missing: {evidence_safety}", failures)
    require(evidence_safety.get("ledger_mutated") is False, f"{label} execution evidence must not mutate ledger: {evidence_safety}", failures)
    intake_source = payload.get("task_intake") or {}
    require(intake_source.get("operation") == "task_intake_checklist", f"{label} task intake payload missing: {intake_source}", failures)
    intake_summary = intake_source.get("summary") or {}
    for key in [
        "tasks_checked",
        "ready_for_intake",
        "blocked_for_intake",
        "attention_for_intake",
        "missing_agent_plan",
        "missing_knowledge_retrieval",
        "missing_base_reference",
        "risk_gate_blocked",
    ]:
        require(isinstance(intake_summary.get(key), int), f"{label} task intake {key} missing: {intake_summary}", failures)
    intake_safety = intake_source.get("safety") or {}
    require(intake_safety.get("read_only") is True, f"{label} task intake read_only missing: {intake_safety}", failures)
    require(intake_safety.get("ledger_mutated") is False, f"{label} task intake must not mutate ledger: {intake_safety}", failures)
    for item in intake_source.get("items") or []:
        require(bool(item.get("task_id")), f"{label} task intake item task_id missing: {item}", failures)
        require(item.get("severity") in {"blocked", "attention", "ready"}, f"{label} task intake severity wrong: {item}", failures)
        require(isinstance(item.get("gates"), list), f"{label} task intake gates missing: {item}", failures)
        for gate in item.get("gates") or []:
            require(bool(gate.get("id")), f"{label} task intake gate id missing: {gate}", failures)
            require(isinstance(gate.get("ok"), bool), f"{label} task intake gate ok missing: {gate}", failures)
    for action in actions or []:
        require(bool(action.get("action_id")), f"{label} action_id missing: {action}", failures)
        require(action.get("severity") in {"blocked", "attention", "ready", "info"}, f"{label} bad severity: {action}", failures)
        require(isinstance(action.get("priority"), int), f"{label} priority missing: {action}", failures)
        require(isinstance(action.get("base_priority"), int), f"{label} base_priority missing: {action}", failures)
        require(isinstance(action.get("receipt_priority_boost"), int), f"{label} receipt_priority_boost missing: {action}", failures)
        require(action.get("priority") == action.get("base_priority") + action.get("receipt_priority_boost"), f"{label} receipt priority math wrong: {action}", failures)
        require(bool(action.get("title")), f"{label} title missing: {action}", failures)
        require(bool(action.get("command")), f"{label} command missing: {action}", failures)
        require(bool(action.get("action_signature")), f"{label} action_signature missing: {action}", failures)
        require(isinstance(action.get("receipt_required"), bool), f"{label} receipt_required missing: {action}", failures)
        if action.get("source") in {"receipt_coverage", "receipt_evaluation"}:
            require(action.get("receipt_required") is False, f"{label} receipt coverage action should not require its own receipt: {action}", failures)
            require(action.get("lane") == action.get("source"), f"{label} receipt meta lane wrong: {action}", failures)
            require(action.get("verify_command") == "agentops operator loop-audit --limit 20", f"{label} receipt meta verify command wrong: {action}", failures)
        else:
            require(action.get("receipt_required") is True, f"{label} ordinary action should require receipt: {action}", failures)
        require(action.get("receipt_status") in {"missing", "recorded", "verified", "failed", "skipped", "stale"}, f"{label} bad receipt_status: {action}", failures)
        require(action.get("receipt_match") in {"missing", "current", "stale"}, f"{label} bad receipt_match: {action}", failures)
        require(isinstance(action.get("receipt_current"), bool), f"{label} receipt_current missing: {action}", failures)
        require(isinstance(action.get("receipt_verified"), bool), f"{label} receipt_verified missing: {action}", failures)
        if action.get("receipt_required"):
            record_command = action.get("receipt_record_command") or ""
            record_confirm_command = action.get("receipt_record_confirm_command") or ""
            verify_record_command = action.get("receipt_verify_record_command") or ""
            require(record_command.startswith("agentops operator record-action-receipt "), f"{label} receipt_record_command missing: {action}", failures)
            require("--action-command" in record_command, f"{label} receipt_record_command lacks action command: {action}", failures)
            require("--confirm-record" not in record_command, f"{label} preview receipt command should not confirm: {record_command}", failures)
            require(record_confirm_command.startswith("agentops operator record-action-receipt "), f"{label} receipt_record_confirm_command missing: {action}", failures)
            require("--confirm-record" in record_confirm_command, f"{label} receipt_record_confirm_command lacks confirmation: {record_confirm_command}", failures)
            require("--status recorded" in record_confirm_command, f"{label} receipt record confirm status wrong: {record_confirm_command}", failures)
            require(verify_record_command.startswith("agentops operator record-action-receipt "), f"{label} receipt_verify_record_command missing: {action}", failures)
            require("--confirm-record" in verify_record_command, f"{label} receipt_verify_record_command lacks confirmation: {verify_record_command}", failures)
            require("--status verified" in verify_record_command, f"{label} receipt verify record status wrong: {verify_record_command}", failures)
        receipt_state = action.get("receipt_state") or {}
        require(receipt_state.get("status") == action.get("receipt_status"), f"{label} receipt_state mismatch: {action}", failures)
        require(receipt_state.get("match") == action.get("receipt_match"), f"{label} receipt_state match mismatch: {action}", failures)
        require(receipt_state.get("current") == action.get("receipt_current"), f"{label} receipt_state current mismatch: {action}", failures)
        require(receipt_state.get("verified") == action.get("receipt_verified"), f"{label} receipt_state verified mismatch: {action}", failures)
        if action.get("receipt_required"):
            require(receipt_state.get("record_command") == action.get("receipt_record_command"), f"{label} receipt_state record command mismatch: {action}", failures)
            require(receipt_state.get("record_confirm_command") == action.get("receipt_record_confirm_command"), f"{label} receipt_state confirm command mismatch: {action}", failures)
            require(receipt_state.get("verify_record_command") == action.get("receipt_verify_record_command"), f"{label} receipt_state verify command mismatch: {action}", failures)
        if action.get("receipt_verified"):
            require(bool(action.get("receipt_id")), f"{label} verified receipt_id missing: {action}", failures)
            require(bool(action.get("receipt_hash")), f"{label} verified receipt_hash missing: {action}", failures)
        require(
            not str(action.get("command") or "").startswith("agentops approval approve --approval-id"),
            f"{label} action should inspect approval before approve: {action}",
            failures,
        )
        if action.get("source") == "execution_evidence_gaps":
            command = str(action.get("command") or "")
            require(
                command.startswith("agentops operator remediate-evidence-gap --run-id ")
                or command.startswith("agentops commander dispatch-package --task-id ")
                or command.startswith("agentops commander synthesize --project-id ")
                or command.startswith("agentops commander promote-synthesis --artifact-id ")
                or command.startswith("agentops operator close-evidence-gap --run-id ")
                or command.startswith("agentops approval inspect --approval-id ")
                or command.startswith("agentops workflow delivery-board")
                or command.startswith("agentops task get --task-id ")
                or command.startswith("agentops run get --run-id ")
                or command.startswith("agentops commander inbox"),
                f"{label} execution evidence action should preview remediation package: {action}",
                failures,
            )
            if command.startswith("agentops operator remediate-evidence-gap --run-id "):
                evidence = action.get("evidence") or {}
                run_id = str(evidence.get("run_id") or "").strip()
                require(bool(run_id), f"{label} remediation action run_id missing: {action}", failures)
                require(action.get("action_id") == f"evidence_remediation:{run_id}", f"{label} remediation action_id should match handoff chain: {action}", failures)
                require((action.get("verify_command") or "") == f"agentops operator evidence-report --run-id {run_id} --limit 1", f"{label} remediation verify command should read evidence report: {action}", failures)
                require((action.get("evidence") or {}).get("handoff_remediation_chain") is True, f"{label} remediation chain evidence marker missing: {action}", failures)
                require((action.get("evidence") or {}).get("handoff_remediation_source") == "handoff.evidence_remediation", f"{label} remediation source marker missing: {action}", failures)
                require("--source handoff.evidence_remediation" in (action.get("receipt_record_command") or ""), f"{label} remediation receipt source missing: {action}", failures)
                require("--source handoff.evidence_remediation" in (action.get("receipt_verify_record_command") or ""), f"{label} remediation verify receipt source missing: {action}", failures)
                require("Evidence remediation preview reviewed for run" in (action.get("receipt_verify_record_command") or ""), f"{label} remediation receipt summary missing: {action}", failures)
        if str(action.get("source") or "").startswith("evidence_remediation_workflow:"):
            evidence = action.get("evidence") or {}
            command = str(action.get("command") or "")
            step_id = str(evidence.get("workflow_step_id") or "")
            run_id = str(evidence.get("run_id") or "").strip()
            require(bool(step_id), f"{label} workflow action step id missing: {action}", failures)
            require(bool(run_id), f"{label} workflow action run id missing: {action}", failures)
            require(action.get("action_id") == (f"evidence_remediation:{run_id}" if step_id == "preview" else f"evidence_remediation:{run_id}:{step_id}"), f"{label} workflow action id mismatch: {action}", failures)
            require(evidence.get("handoff_remediation_chain") is True, f"{label} workflow handoff marker missing: {action}", failures)
            require(str(evidence.get("handoff_remediation_source") or "").startswith("handoff.evidence_remediation"), f"{label} workflow handoff source missing: {action}", failures)
            require(evidence.get("next_safe_command_kind") == "action", f"{label} workflow next command kind missing: {action}", failures)
            require(isinstance(evidence.get("mutating"), bool), f"{label} workflow mutating flag missing: {action}", failures)
            require(isinstance(evidence.get("confirm_required"), bool), f"{label} workflow confirm flag missing: {action}", failures)
            require("--source handoff.evidence_remediation" in (action.get("receipt_record_command") or ""), f"{label} workflow receipt source missing: {action}", failures)
            require("--source handoff.evidence_remediation" in (action.get("receipt_verify_record_command") or ""), f"{label} workflow verify receipt source missing: {action}", failures)
            require(
                command.startswith("agentops operator remediate-evidence-gap --run-id ")
                or command.startswith("agentops commander dispatch-package --task-id ")
                or command.startswith("agentops plan-evidence ")
                or command.startswith("agentops commander synthesize --project-id ")
                or command.startswith("agentops commander promote-synthesis --artifact-id ")
                or command.startswith("agentops operator close-evidence-gap --run-id ")
                or command.startswith("agentops approval inspect --approval-id "),
                f"{label} workflow action command outside allowed remediation stages: {action}",
                failures,
            )
        if action.get("source") == "task_intake_checklist":
            command = str(action.get("command") or "")
            require(
                command.startswith("agentops knowledge search ")
                or command.startswith("agentops operator intake-auto-plan --task-id ")
                or command.startswith("agentops agent-plan verify --plan-id ")
                or command.startswith("agentops agent-plan get --plan-id ")
                or command.startswith("agentops task pull --agent-id "),
                f"{label} task intake action should stay in read/plan/pull commands: {action}",
                failures,
            )
        if action.get("lane") == "operator_health" or str(action.get("source") or "").startswith("operator_health:"):
            require(str(action.get("command") or "").startswith("agentops "), f"{label} operator health action must be a CLI command: {action}", failures)
            require(action.get("verify_command") == "agentops operator health --limit 20", f"{label} operator health action verify command wrong: {action}", failures)
            require(str(action.get("source") or "").startswith("operator_health:"), f"{label} operator health source wrong: {action}", failures)
            require(action.get("receipt_required") is True, f"{label} operator health action must require receipt: {action}", failures)
        if action.get("lane") == "workflow_job_recovery" or str(action.get("source") or "").startswith("workflow_job_recovery:"):
            command = str(action.get("command") or "")
            verify_command = str(action.get("verify_command") or "")
            require(str(action.get("source") or "").startswith("workflow_job_recovery:"), f"{label} workflow recovery source wrong: {action}", failures)
            require(action.get("receipt_required") is True, f"{label} workflow recovery action must require receipt: {action}", failures)
            require("--source operator.workflow_job_recovery" in (action.get("receipt_record_command") or ""), f"{label} workflow recovery receipt source missing: {action}", failures)
            require("--source operator.workflow_job_recovery" in (action.get("receipt_verify_record_command") or ""), f"{label} workflow recovery verify receipt source missing: {action}", failures)
            require(
                command.startswith("agentops workflow recover-job --job-id "),
                f"{label} workflow recovery command outside allowed set: {action}",
                failures,
            )
            if "--mode mark-failed" in command:
                require(verify_command.startswith("agentops workflow job-status --job-id "), f"{label} workflow mark-failed verify command wrong: {action}", failures)
                evidence = action.get("evidence") or {}
                require(evidence.get("mode") == "mark-failed", f"{label} workflow recover mode missing: {action}", failures)
                require(evidence.get("confirm_required") is True, f"{label} workflow recover confirm missing: {action}", failures)
                require(str(evidence.get("preview_command") or "").startswith("agentops workflow recover-job --job-id "), f"{label} workflow recover preview missing: {action}", failures)
            if "--mode retry" in command:
                require(verify_command == "agentops workflow jobs --status queued,running,completed,failed --limit 20", f"{label} workflow retry verify command wrong: {action}", failures)
                require(bool((action.get("evidence") or {}).get("task_id")), f"{label} workflow retry task id missing: {action}", failures)
        if action.get("lane") == "local_service_control":
            evidence = action.get("evidence") or {}
            require(action.get("source") == "local_readiness.service_control_preview", f"{label} service-control source wrong: {action}", failures)
            require("service-control" in str(action.get("command") or ""), f"{label} service-control command missing: {action}", failures)
            require("service-check" in str(action.get("verify_command") or ""), f"{label} service-control verify command missing: {action}", failures)
            require(evidence.get("step_id") == "preview_worker_service_control", f"{label} service-control step evidence missing: {action}", failures)
            require(evidence.get("service_control_preview") is True, f"{label} service-control preview evidence missing: {action}", failures)
            require(evidence.get("control_readback_required") is True, f"{label} service-control readback requirement missing: {action}", failures)
            require(evidence.get("copy_only") is True, f"{label} service-control copy-only proof missing: {action}", failures)
            require(evidence.get("server_executes_shell") is False, f"{label} service-control server shell proof missing: {action}", failures)
            require(evidence.get("live_execution_performed") is False, f"{label} service-control live execution proof missing: {action}", failures)
            require("--source local_readiness.service_control_preview" in (action.get("receipt_record_command") or ""), f"{label} service-control receipt source missing: {action}", failures)
            require("--source local_readiness.service_control_preview" in (action.get("receipt_verify_record_command") or ""), f"{label} service-control verify receipt source missing: {action}", failures)
        require(bool(action.get("source")), f"{label} source missing: {action}", failures)
    for command in payload.get("top_commands") or []:
        require(
            not str(command or "").startswith("agentops approval approve --approval-id"),
            f"{label} top command should inspect approval before approve: {command}",
            failures,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify operator action plan API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--skip-cli", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    outputs: list[str] = []
    db_path = Path(args.db_path)
    before = db_fingerprint(db_path)

    status, payload = http_json(args.base_url, f"/api/operator/action-plan?limit={args.limit}")
    require(status == 200, f"API status mismatch: {status} {payload}", failures)
    validate_plan(payload, "api", failures, args.limit)
    outputs.append(json.dumps(payload, ensure_ascii=False))

    cli_payload: dict = {}
    if not args.skip_cli:
        with tempfile.TemporaryDirectory(prefix="agentops-operator-plan-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            proc = run_cli(args.base_url, ["operator", "action-plan", "--limit", str(args.limit)], env)
            outputs.extend([proc.stdout, proc.stderr])
            cli_payload = load_json(proc)
            require(proc.returncode == 0, f"CLI failed: {proc.stderr or proc.stdout}", failures)
            validate_plan(cli_payload, "cli", failures, args.limit)
            intake_proc = run_cli(args.base_url, ["operator", "intake-checklist", "--limit", str(args.limit)], env)
            outputs.extend([intake_proc.stdout, intake_proc.stderr])
            intake_payload = load_json(intake_proc)
            require(intake_proc.returncode == 0, f"intake-checklist CLI failed: {intake_proc.stderr or intake_proc.stdout}", failures)
            require(intake_payload.get("operation") == "task_intake_checklist", f"intake-checklist operation mismatch: {intake_payload}", failures)
            intake_safety = intake_payload.get("safety") or {}
            require(intake_safety.get("read_only") is True, f"intake-checklist CLI read_only missing: {intake_safety}", failures)
            require(intake_safety.get("ledger_mutated") is False, f"intake-checklist CLI mutated ledger: {intake_safety}", failures)
            gap_run_id = next(
                (item.get("run_id") for item in ((payload.get("execution_evidence") or {}).get("gaps") or []) if item.get("run_id")),
                None,
            )
            if gap_run_id:
                close_proc = run_cli(
                    args.base_url,
                    [
                        "operator",
                        "close-evidence-gap",
                        "--run-id",
                        str(gap_run_id),
                        "--decision",
                        "waived",
                        "--note",
                        "smoke preview only",
                    ],
                    env,
                )
                outputs.extend([close_proc.stdout, close_proc.stderr])
                close_payload = load_json(close_proc)
                require(close_proc.returncode == 0, f"close-gap preview CLI failed: {close_proc.stderr or close_proc.stdout}", failures)
                require(close_payload.get("operation") == "execution_evidence_gap_decision", f"close-gap preview operation mismatch: {close_payload}", failures)
                close_safety = close_payload.get("safety") or {}
                require(close_safety.get("read_only") is True, f"close-gap preview should be read-only: {close_safety}", failures)
                require(close_safety.get("ledger_mutated") is False, f"close-gap preview mutated ledger: {close_safety}", failures)

    after = db_fingerprint(db_path)
    db_unchanged = bool(before is not None and after is not None and before == after)
    if before is not None and after is not None:
        require(db_unchanged, "operator action plan changed database fingerprint", failures)
    secret_leaked = leaked_secret("\n".join(outputs))
    require(not secret_leaked, "operator action plan leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "api_status": payload.get("status"),
        "summary": payload.get("summary"),
        "top_commands": payload.get("top_commands", [])[:3],
        "cli_checked": not args.skip_cli,
        "cli_status": cli_payload.get("status"),
        "db_fingerprint_checked": before is not None and after is not None,
        "db_fingerprint_unchanged": db_unchanged,
        "secret_leaked": secret_leaked,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    if failures:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:3000])
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
