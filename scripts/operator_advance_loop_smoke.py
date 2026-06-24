#!/usr/bin/env python3
"""Verify the bounded CLI loop runner advances one safe action and records a receipt."""

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
import urllib.request
import uuid
from pathlib import Path


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


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(text: str) -> dict:
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/dashboard/metrics", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.3)
    raise RuntimeError(f"server did not become ready: {last_error}")


def start_server(db_path: Path, port: int, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
        cwd=ROOT,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._agentops_log_fh = log_fh  # type: ignore[attr-defined]
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=8)
    log_fh = getattr(proc, "_agentops_log_fh", None)
    if log_fh:
        log_fh.close()


def run_cli(args: list[str], base_url: str, outputs: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env.pop("AGENTOPS_API_KEY", None)
    env.pop("AGENTOPS_AGENT_ID", None)
    proc = subprocess.run([str(CLI), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def db_counts(db_path: Path, loop_id: str) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        memories = conn.execute(
            "SELECT review_status, COUNT(*) AS c FROM memories WHERE source_ref=? AND memory_type='loop_record' GROUP BY review_status",
            (f"loop://{loop_id}",),
        ).fetchall()
        receipts = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt' AND metadata_json LIKE ?",
            (f"%advance_loop:record%",),
        ).fetchone()
        evaluations = conn.execute(
            "SELECT COUNT(*) AS c FROM operator_action_evaluations",
        ).fetchone()
    return {
        "memories": {row["review_status"]: int(row["c"] or 0) for row in memories},
        "advance_receipts": int(receipts["c"] if receipts else 0),
        "evaluations": int(evaluations["c"] if evaluations else 0),
    }


def advance_receipt_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt' AND metadata_json LIKE ?",
            ("%advance_loop:%",),
        ).fetchone()
    return int(row[0] if row else 0)


def receipt_count_for_source(db_path: Path, source: str) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt' AND metadata_json LIKE ?",
            (f"%{source}%",),
        ).fetchone()
    return int(row[0] if row else 0)


def research_consumption_counts(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        receipt_row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt' AND metadata_json LIKE ?",
            ("%operator.research_lab_consumption:%",),
        ).fetchone()
        audit_row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.research_lab_consumption'",
        ).fetchone()
        memory_row = conn.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE source_ref LIKE 'research_lab_packet://%'",
        ).fetchone()
    return {
        "receipts": int(receipt_row[0] if receipt_row else 0),
        "audits": int(audit_row[0] if audit_row else 0),
        "memories": int(memory_row[0] if memory_row else 0),
    }


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    loop_id = f"loop_advance_{uuid.uuid4().hex[:10]}"
    with tempfile.TemporaryDirectory(prefix="agentops-advance-loop-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            policy = run_cli(["operator", "advance-loop-policy"], base_url, outputs)
            policy_payload = load_json(policy.stdout)
            policy_summary = policy_payload.get("policy") or {}
            require(policy.returncode == 0, f"advance policy CLI failed: {policy.stderr or policy.stdout}", failures)
            require(policy_payload.get("operation") == "operator_advance_loop_policy", f"advance policy operation mismatch: {policy_payload}", failures)
            require(policy_summary.get("policy_id") == "advance_loop_local_bounded_v1", f"advance policy id missing: {policy_payload}", failures)
            require((policy_payload.get("safety") or {}).get("read_only") is True, f"advance policy should be read-only: {policy_payload}", failures)
            allowed_read_commands = set(policy_summary.get("allowed_read_commands") or [])
            special_rules = " ".join(policy_summary.get("special_rules") or [])
            require("operator runtime-doctor" in allowed_read_commands, f"advance policy should allow runtime-doctor read: {policy_summary}", failures)
            require("operator execution-mode" in allowed_read_commands, f"advance policy should allow execution-mode read: {policy_summary}", failures)
            require("operator loop-supervision" in allowed_read_commands, f"advance policy should allow loop-supervision verify read: {policy_summary}", failures)
            require("research-lab-consumption" in special_rules, f"advance policy should document research consumption writeback rule: {policy_summary}", failures)

            research_before = research_consumption_counts(db_path)
            research_preview = run_cli(["operator", "advance-loop", "--source", "research_lab_consumption", "--limit", "10"], base_url, outputs)
            research_preview_payload = load_json(research_preview.stdout)
            research_after_preview = research_consumption_counts(db_path)
            require(research_preview.returncode == 0, f"research source advance preview failed: {research_preview.stderr or research_preview.stdout}", failures)
            require(research_preview_payload.get("status") == "preview", f"research source advance should preview: {research_preview_payload}", failures)
            research_preview_item = research_preview_payload.get("preview") or {}
            require(research_preview_item.get("gate_id") == "research_lab_consumption", f"research source advance should select research gate: {research_preview_payload}", failures)
            require("operator research-lab-consumption" in str(research_preview_item.get("action_command") or ""), f"research source action command missing: {research_preview_payload}", failures)
            require("--confirm-record" in str(research_preview_item.get("action_command") or ""), f"research source action must be confirm-record gated: {research_preview_payload}", failures)
            require(((research_preview_item.get("action_policy") or {}).get("allowed") is True), f"research source action should be allowlisted: {research_preview_payload}", failures)
            require(((research_preview_item.get("verify_policy") or {}).get("allowed") is True), f"research source verify should be allowlisted: {research_preview_payload}", failures)
            require(research_after_preview == research_before, f"research source preview mutated db: {research_before} -> {research_after_preview}", failures)

            research_confirm = run_cli(["operator", "advance-loop", "--source", "research_lab_consumption", "--limit", "10", "--confirm-advance"], base_url, outputs, timeout=180)
            research_confirm_payload = load_json(research_confirm.stdout)
            research_after_confirm = research_consumption_counts(db_path)
            require(research_confirm.returncode == 0, f"research source advance confirm failed: {research_confirm.stderr or research_confirm.stdout}", failures)
            require(research_confirm_payload.get("advanced") is True, f"research source advance should execute: {research_confirm_payload}", failures)
            require((research_confirm_payload.get("preview") or {}).get("gate_id") == "research_lab_consumption", f"research confirm selected wrong gate: {research_confirm_payload}", failures)
            require((research_confirm_payload.get("action_result") or {}).get("ok") is True, f"research confirm action failed: {research_confirm_payload}", failures)
            require((research_confirm_payload.get("verify_result") or {}).get("ok") is True, f"research confirm verify failed: {research_confirm_payload}", failures)
            require(((research_confirm_payload.get("receipt") or {}).get("receipt") or {}).get("source", "").startswith("research_lab_consumption:"), f"research advance receipt source mismatch: {research_confirm_payload}", failures)
            require((research_confirm_payload.get("safety") or {}).get("ledger_mutated") is True, f"research confirm should mutate governance ledger: {research_confirm_payload}", failures)
            require((research_confirm_payload.get("safety") or {}).get("live_execution_performed") is False, f"research confirm must not run live adapters: {research_confirm_payload}", failures)
            require(research_after_confirm["receipts"] >= research_before["receipts"] + 1, f"research consumption receipt missing: {research_before} -> {research_after_confirm}", failures)
            require(research_after_confirm["audits"] >= research_before["audits"] + 1, f"research consumption audit missing: {research_before} -> {research_after_confirm}", failures)
            require(research_after_confirm["memories"] >= research_before["memories"] + 1, f"research consumption memory missing: {research_before} -> {research_after_confirm}", failures)
            research_readback = run_cli(["operator", "command-center", "--limit", "10"], base_url, outputs)
            research_readback_payload = load_json(research_readback.stdout)
            research_summary = ((research_readback_payload.get("research_lab_consumption") or {}).get("summary") or {})
            require(int(research_summary.get("consumed") or 0) >= 1, f"command-center should read back consumed research packet: {research_readback_payload}", failures)
            require(int(research_summary.get("missing") or 0) >= 1, f"one unadvanced research adapter should remain visible: {research_readback_payload}", failures)

            missing_source = run_cli(["operator", "advance-loop", "--source", "definitely_missing_source", "--limit", "10"], base_url, outputs)
            missing_source_payload = load_json(missing_source.stdout)
            require(missing_source.returncode == 0, f"missing-source advance should fail closed without CLI error: {missing_source.stderr or missing_source.stdout}", failures)
            require(missing_source_payload.get("status") == "empty", f"missing-source advance should be empty: {missing_source_payload}", failures)
            require(missing_source_payload.get("advanced") is False, f"missing-source advance must not execute fallback: {missing_source_payload}", failures)
            require("fall back" in str(missing_source_payload.get("message") or ""), f"missing-source message should explain no fallback: {missing_source_payload}", failures)

            global_preview = run_cli(["operator", "advance-loop", "--limit", "10"], base_url, outputs)
            global_preview_payload = load_json(global_preview.stdout)
            require(global_preview.returncode == 0, f"global advance preview failed: {global_preview.stderr or global_preview.stdout}", failures)
            require(global_preview_payload.get("status") == "preview", f"global advance should preview: {global_preview_payload}", failures)
            require((global_preview_payload.get("preview") or {}).get("gate_id") == "evidence_report", f"global advance should prioritize evidence report: {global_preview_payload}", failures)
            require(((global_preview_payload.get("preview") or {}).get("action_policy") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"global evidence preview policy missing: {global_preview_payload}", failures)
            global_before_receipts = advance_receipt_count(db_path)
            global_advanced = run_cli(["operator", "advance-loop", "--limit", "10", "--confirm-advance"], base_url, outputs)
            global_advanced_payload = load_json(global_advanced.stdout)
            global_after_receipts = advance_receipt_count(db_path)
            require(global_advanced.returncode == 0, f"global advance confirm failed: {global_advanced.stderr or global_advanced.stdout}", failures)
            require((global_advanced_payload.get("preview") or {}).get("gate_id") == "evidence_report", f"global advance confirmed wrong gate: {global_advanced_payload}", failures)
            require(global_advanced_payload.get("advanced") is True, f"global advance should execute evidence report: {global_advanced_payload}", failures)
            require((global_advanced_payload.get("action_result") or {}).get("ok") is True, f"global evidence action failed: {global_advanced_payload}", failures)
            require((global_advanced_payload.get("verify_result") or {}).get("ok") is True, f"global evidence verify failed: {global_advanced_payload}", failures)
            global_control = global_advanced_payload.get("control_readback") or {}
            global_before_control = global_control.get("before") or {}
            global_after_control = global_control.get("after") or {}
            global_after_self_check = global_control.get("after_self_check") or {}
            global_readback_receipt = ((global_advanced_payload.get("control_readback_receipt") or {}).get("readback") or {})
            require(global_control.get("refresh_cache_requested") is True, f"global advance should request control refresh: {global_advanced_payload}", failures)
            require(global_control.get("cache_bypassed") is True, f"global advance should bypass read-model cache after receipt: {global_advanced_payload}", failures)
            require(global_before_control.get("selected_gate") == "evidence_report", f"global advance before control should target evidence report: {global_control}", failures)
            require(global_after_control.get("selected_gate") != "evidence_report", f"global advance after control should move past verified evidence report: {global_control}", failures)
            require(global_after_self_check.get("operation") == "operator_loop_control_summary", f"global advance self-check control missing: {global_control}", failures)
            require((global_readback_receipt.get("control_readback") or {}).get("cache_bypassed") is True, f"global control readback receipt missing cache proof: {global_advanced_payload}", failures)
            require(((global_readback_receipt.get("control_readback") or {}).get("before") or {}).get("selected_gate") == "evidence_report", f"global persisted control readback before mismatch: {global_advanced_payload}", failures)
            require(global_after_receipts >= global_before_receipts + 1, f"global evidence advance receipt missing: {global_before_receipts} -> {global_after_receipts}", failures)
            global_second_preview = run_cli(["operator", "advance-loop", "--limit", "10"], base_url, outputs)
            global_second_payload = load_json(global_second_preview.stdout)
            require(global_second_preview.returncode == 0, f"global second preview failed: {global_second_preview.stderr or global_second_preview.stdout}", failures)
            require((global_second_payload.get("preview") or {}).get("gate_id") != "evidence_report", f"verified evidence work order should not be selected again: {global_second_payload}", failures)
            require((global_second_payload.get("preview") or {}).get("gate_id") == "evidence_remediation", f"global second preview should continue with evidence remediation: {global_second_payload}", failures)
            require(str((global_second_payload.get("preview") or {}).get("action_command") or "").startswith("agentops operator remediate-evidence-gap --run-id "), f"remediation preview command missing: {global_second_payload}", failures)
            require(((global_second_payload.get("preview") or {}).get("action_policy") or {}).get("allowed") is True, f"remediation preview should be allowlisted: {global_second_payload}", failures)
            remediation_command_center = run_cli(["operator", "command-center", "--limit", "10"], base_url, outputs)
            remediation_command_center_payload = load_json(remediation_command_center.stdout)
            remediation_lane = remediation_command_center_payload.get("evidence_remediation") or {}
            remediation_lane_summary = remediation_lane.get("summary") or {}
            remediation_actions = [
                item for item in remediation_command_center_payload.get("next_actions") or []
                if str(item.get("source") or "").startswith("evidence_remediation:")
            ]
            require(remediation_command_center.returncode == 0, f"remediation command-center readback failed: {remediation_command_center.stderr or remediation_command_center.stdout}", failures)
            require(int(remediation_lane_summary.get("items") or 0) >= 1, f"command-center remediation lane missing items: {remediation_command_center_payload}", failures)
            require(remediation_actions, f"command-center remediation next action missing: {remediation_command_center_payload}", failures)
            require("advance-loop --source evidence_remediation" in str(((remediation_actions[0].get("evidence") or {}).get("advance_command")) or ""), f"command-center remediation advance source missing: {remediation_command_center_payload}", failures)
            remediation_source_preview = run_cli(["operator", "advance-loop", "--source", "evidence_remediation", "--limit", "10"], base_url, outputs)
            remediation_source_payload = load_json(remediation_source_preview.stdout)
            require(remediation_source_preview.returncode == 0, f"remediation source preview failed: {remediation_source_preview.stderr or remediation_source_preview.stdout}", failures)
            require((remediation_source_payload.get("preview") or {}).get("gate_id") == "evidence_remediation", f"remediation source preview wrong gate: {remediation_source_payload}", failures)
            require(((remediation_source_payload.get("preview") or {}).get("action_policy") or {}).get("allowed") is True, f"remediation source preview should be allowlisted: {remediation_source_payload}", failures)
            remediation_before_receipts = receipt_count_for_source(db_path, "handoff.evidence_remediation")
            remediation_advanced = run_cli(["operator", "advance-loop", "--source", "evidence_remediation", "--limit", "10", "--confirm-advance"], base_url, outputs)
            remediation_advanced_payload = load_json(remediation_advanced.stdout)
            remediation_after_receipts = receipt_count_for_source(db_path, "handoff.evidence_remediation")
            require(remediation_advanced.returncode == 0, f"remediation advance confirm failed: {remediation_advanced.stderr or remediation_advanced.stdout}", failures)
            require((remediation_advanced_payload.get("preview") or {}).get("gate_id") == "evidence_remediation", f"remediation advance confirmed wrong gate: {remediation_advanced_payload}", failures)
            require((remediation_advanced_payload.get("action_result") or {}).get("ok") is True, f"remediation preview action failed: {remediation_advanced_payload}", failures)
            require((remediation_advanced_payload.get("verify_result") or {}).get("ok") is True, f"remediation preview verify failed: {remediation_advanced_payload}", failures)
            require(((remediation_advanced_payload.get("receipt") or {}).get("receipt") or {}).get("source") == "handoff.evidence_remediation", f"remediation receipt should preserve handoff source: {remediation_advanced_payload}", failures)
            require(remediation_after_receipts >= remediation_before_receipts + 1, f"remediation advance receipt missing: {remediation_before_receipts} -> {remediation_after_receipts}", failures)
            remediation_workflow_readback = run_cli(["operator", "command-center", "--limit", "20"], base_url, outputs)
            remediation_workflow_payload = load_json(remediation_workflow_readback.stdout)
            remediation_workflow = remediation_workflow_payload.get("evidence_remediation_workflow") or {}
            remediation_workflow_summary = remediation_workflow.get("summary") or {}
            remediation_workflow_items = remediation_workflow.get("items") or []
            remediation_workflow_actions = [
                item for item in remediation_workflow_payload.get("next_actions") or []
                if str(item.get("source") or "").startswith("evidence_remediation_workflow:")
            ]
            first_workflow_item = remediation_workflow_items[0] if remediation_workflow_items else {}
            first_workflow_action = remediation_workflow_actions[0] if remediation_workflow_actions else {}
            require(remediation_workflow_readback.returncode == 0, f"remediation workflow readback failed: {remediation_workflow_readback.stderr or remediation_workflow_readback.stdout}", failures)
            require(remediation_workflow.get("operation") == "operator_command_center_evidence_remediation_workflow", f"remediation workflow lane missing: {remediation_workflow_payload}", failures)
            require((remediation_workflow.get("safety") or {}).get("read_only") is True, f"remediation workflow lane should be read-only: {remediation_workflow}", failures)
            require((remediation_workflow.get("safety") or {}).get("bounded_advance_auto_runs") is False, f"remediation workflow must not be auto-run by bounded advance: {remediation_workflow}", failures)
            require(int(remediation_workflow_summary.get("items") or 0) >= 1, f"verified remediation preview should expose workflow steps: {remediation_workflow_payload}", failures)
            require(int(remediation_workflow_summary.get("confirm_required") or 0) >= 1, f"workflow steps should preserve explicit confirmation boundary: {remediation_workflow_payload}", failures)
            require(remediation_workflow_actions, f"workflow next action missing after verified preview: {remediation_workflow_payload}", failures)
            require(first_workflow_item.get("step_id") in {"create_task", "dispatch_package", "plan_evidence", "synthesize", "close_gap"}, f"unexpected workflow step id: {first_workflow_item}", failures)
            require(first_workflow_item.get("preview_receipt_verified") is True, f"workflow item should prove preview receipt first: {first_workflow_item}", failures)
            require(str(first_workflow_item.get("receipt_source") or "").startswith("handoff.evidence_remediation"), f"workflow item receipt source missing: {first_workflow_item}", failures)
            require(first_workflow_item.get("server_executes_shell") is False, f"workflow item shell proof missing: {first_workflow_item}", failures)
            require(first_workflow_item.get("live_execution_performed") is False, f"workflow item live proof missing: {first_workflow_item}", failures)
            require((first_workflow_action.get("evidence") or {}).get("preview_receipt_verified") is True, f"workflow action preview receipt proof missing: {first_workflow_action}", failures)
            require((first_workflow_action.get("evidence") or {}).get("bounded_advance_auto_runs") is False, f"workflow action bounded auto-run proof missing: {first_workflow_action}", failures)
            require(first_workflow_action.get("control_readback_required") is False, f"workflow action should require explicit operator action, not bounded readback: {first_workflow_action}", failures)
            handoff_after_global = run_cli(["operator", "handoff", "--limit", "10"], base_url, outputs)
            handoff_after_payload = load_json(handoff_after_global.stdout)
            evidence_work_order = ((handoff_after_payload.get("work_order") or {}).get("evidence_report") or {})
            evidence_receipt_state = evidence_work_order.get("receipt_state") or {}
            require(evidence_receipt_state.get("verified") is True, f"handoff should expose verified evidence receipt state: {handoff_after_payload}", failures)
            remediation_items = (((evidence_work_order.get("remediation_chain") or {}).get("items")) or [])
            require(any((item.get("receipt_state") or {}).get("verified") is True for item in remediation_items), f"handoff should expose verified remediation receipt state: {handoff_after_payload}", failures)

            workflow = run_cli([
                "workflow",
                "hermes-openclaw-loop",
                "--topic",
                "Advance one safe RECORD action through the bounded operator runner.",
                "--loop-id",
                loop_id,
                "--rounds",
                "1",
                "--request-timeout",
                "5",
            ], base_url, outputs)
            workflow_payload = load_json(workflow.stdout)
            require(workflow.returncode == 0 and workflow_payload.get("ok") is True, f"loop workflow failed: {workflow.stderr or workflow.stdout}", failures)

            before = db_counts(db_path, loop_id)
            first_audit = run_cli(["operator", "loop-audit", "--loop-id", loop_id, "--limit", "10"], base_url, outputs)
            first_payload = load_json(first_audit.stdout)
            record_step = next((step for step in first_payload.get("steps") or [] if step.get("id") == "record"), {})
            require(first_payload.get("status") == "attention", f"loop should require RECORD before advance: {first_payload}", failures)
            require(record_step.get("status") == "attention", f"record gate should need attention: {record_step}", failures)

            preview = run_cli(["operator", "advance-loop", "--loop-id", loop_id, "--limit", "10"], base_url, outputs)
            preview_payload = load_json(preview.stdout)
            after_preview = db_counts(db_path, loop_id)
            require(preview.returncode == 0, f"advance preview failed: {preview.stderr or preview.stdout}", failures)
            require(preview_payload.get("status") == "preview", f"advance should default to preview: {preview_payload}", failures)
            require((preview_payload.get("preview") or {}).get("gate_id") == "record", f"advance should select record gate: {preview_payload}", failures)
            require((preview_payload.get("policy") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"advance preview policy id missing: {preview_payload}", failures)
            require(((preview_payload.get("preview") or {}).get("action_policy") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"advance action policy id missing: {preview_payload}", failures)
            require(after_preview == before, f"advance preview mutated db: {before} -> {after_preview}", failures)

            advanced = run_cli(["operator", "advance-loop", "--loop-id", loop_id, "--limit", "10", "--confirm-advance"], base_url, outputs)
            advanced_payload = load_json(advanced.stdout)
            after_advance = db_counts(db_path, loop_id)
            require(advanced.returncode == 0, f"advance confirm CLI failed: {advanced.stderr or advanced.stdout}", failures)
            require(advanced_payload.get("operation") == "operator_advance_loop", f"advance operation mismatch: {advanced_payload}", failures)
            require(advanced_payload.get("advanced") is True, f"advance did not execute: {advanced_payload}", failures)
            require(advanced_payload.get("status") == "advanced", f"advance should finish verified: {advanced_payload}", failures)
            require((advanced_payload.get("preview") or {}).get("gate_id") == "record", f"advanced wrong gate: {advanced_payload}", failures)
            require((advanced_payload.get("policy") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"advanced policy id missing: {advanced_payload}", failures)
            require((advanced_payload.get("action_result") or {}).get("ok") is True, f"advance action failed: {advanced_payload}", failures)
            require((advanced_payload.get("verify_result") or {}).get("ok") is True, f"advance verify failed: {advanced_payload}", failures)
            loop_control = advanced_payload.get("control_readback") or {}
            loop_readback_receipt = ((advanced_payload.get("control_readback_receipt") or {}).get("readback") or {})
            require((loop_control.get("before") or {}).get("selected_gate") == "record", f"loop advance before control should target record: {advanced_payload}", failures)
            require(loop_control.get("refresh_cache_requested") is True, f"loop advance should request control refresh: {advanced_payload}", failures)
            require(loop_control.get("cache_bypassed") is True, f"loop advance should bypass read-model cache after receipt: {advanced_payload}", failures)
            require((loop_control.get("after") or {}).get("operation") == "operator_loop_control_summary", f"loop advance after handoff control missing: {advanced_payload}", failures)
            require((loop_control.get("after_self_check") or {}).get("operation") == "operator_loop_control_summary", f"loop advance after self-check control missing: {advanced_payload}", failures)
            require(((loop_readback_receipt.get("control_readback") or {}).get("before") or {}).get("selected_gate") == "record", f"loop persisted control readback before mismatch: {advanced_payload}", failures)
            receipts_after_advance = run_cli(["operator", "action-receipts", "--limit", "20"], base_url, outputs)
            receipts_payload = load_json(receipts_after_advance.stdout)
            receipts_summary = receipts_payload.get("summary") or {}
            persisted_readbacks = [
                receipt.get("control_readback") or {}
                for receipt in receipts_payload.get("receipts") or []
                if (receipt.get("control_readback") or {}).get("before")
            ]
            require(any((item.get("before") or {}).get("selected_gate") == "record" and item.get("cache_bypassed") is True for item in persisted_readbacks), f"action receipts should expose persisted loop control readback: {receipts_payload}", failures)
            require(int(receipts_summary.get("control_readback_required") or 0) >= 3, f"action receipt summary should require control readbacks for advance receipts: {receipts_payload}", failures)
            require(int(receipts_summary.get("control_readback_attached") or 0) >= int(receipts_summary.get("control_readback_required") or 0), f"action receipt summary should attach all required control readbacks: {receipts_payload}", failures)
            require(int(receipts_summary.get("control_readback_missing") or 0) == 0, f"action receipt summary should not miss control readbacks: {receipts_payload}", failures)
            require(receipts_summary.get("control_readback_status") == "ready", f"action receipt summary control readback status should be ready: {receipts_payload}", failures)
            handoff_with_readbacks = run_cli(["operator", "handoff", "--loop-id", loop_id, "--limit", "10"], base_url, outputs)
            handoff_with_readbacks_payload = load_json(handoff_with_readbacks.stdout)
            control_readback_gate = ((((handoff_with_readbacks_payload.get("loop_health") or {}).get("gates") or {}).get("control_readbacks")) or {})
            require(control_readback_gate.get("status") == "pass", f"handoff health should expose passing control readback gate: {handoff_with_readbacks_payload}", failures)
            require(int(control_readback_gate.get("attached") or 0) >= int(control_readback_gate.get("required") or 0), f"handoff control readback gate should prove coverage: {handoff_with_readbacks_payload}", failures)
            require((advanced_payload.get("safety") or {}).get("ledger_mutated") is True, f"advance should record receipt: {advanced_payload}", failures)
            require((advanced_payload.get("safety") or {}).get("live_execution_performed") is False, f"advance must not run live work: {advanced_payload}", failures)
            require(after_advance["memories"].get("candidate", 0) == 1, f"advance should propose one loop memory candidate: {after_advance}", failures)
            require(after_advance["memories"].get("approved", 0) == 0, f"advance must not approve memory: {after_advance}", failures)
            require(after_advance["advance_receipts"] >= before["advance_receipts"] + 1, f"advance receipt missing: {before} -> {after_advance}", failures)
            require(after_advance["evaluations"] >= before["evaluations"] + 1, f"advance receipt evaluation missing: {before} -> {after_advance}", failures)

            review = run_cli(["review", "queue", "--limit", "20"], base_url, outputs)
            review_payload = load_json(review.stdout)
            require(review.returncode == 0, f"review queue failed: {review.stderr or review.stdout}", failures)
            require(any(item.get("item_type") == "memory_candidate" and item.get("kind") == "loop_record" for item in review_payload.get("review_items") or []), f"loop memory candidate missing from review queue: {review_payload}", failures)

            unsafe_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops memory approve --memory-id mem_x', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([unsafe_policy.stdout, unsafe_policy.stderr])
            unsafe_payload = load_json(unsafe_policy.stdout)
            require(unsafe_payload.get("allowed") is False, f"unsafe memory approve should be rejected: {unsafe_payload}", failures)
            evidence_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator evidence-report --limit 8', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([evidence_policy.stdout, evidence_policy.stderr])
            evidence_policy_payload = load_json(evidence_policy.stdout)
            require(evidence_policy_payload.get("allowed") is True, f"evidence report should be allowlisted as read-only action: {evidence_policy_payload}", failures)
            runtime_doctor_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator runtime-doctor --limit 8', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([runtime_doctor_policy.stdout, runtime_doctor_policy.stderr])
            runtime_doctor_policy_payload = load_json(runtime_doctor_policy.stdout)
            require(runtime_doctor_policy_payload.get("allowed") is True, f"runtime-doctor should be allowlisted as read-only action: {runtime_doctor_policy_payload}", failures)
            execution_mode_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator execution-mode --adapter hermes', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([execution_mode_policy.stdout, execution_mode_policy.stderr])
            execution_mode_policy_payload = load_json(execution_mode_policy.stdout)
            require(execution_mode_policy_payload.get("allowed") is True, f"execution-mode should be allowlisted as read-only action: {execution_mode_policy_payload}", failures)
            execution_mode_confirm_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator execution-mode --adapter hermes --confirm-run', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([execution_mode_confirm_policy.stdout, execution_mode_confirm_policy.stderr])
            execution_mode_confirm_policy_payload = load_json(execution_mode_confirm_policy.stdout)
            require(execution_mode_confirm_policy_payload.get("allowed") is False, f"execution-mode --confirm-run should still be denied: {execution_mode_confirm_policy_payload}", failures)
            research_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator research-lab-consumption --adapter hermes --packet-hash abc --confirm-record', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([research_policy.stdout, research_policy.stderr])
            research_policy_payload = load_json(research_policy.stdout)
            require(research_policy_payload.get("allowed") is True, f"research-lab-consumption confirm-record should be allowlisted: {research_policy_payload}", failures)
            research_preview_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator research-lab-consumption --adapter hermes --packet-hash abc', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([research_preview_policy.stdout, research_preview_policy.stderr])
            research_preview_policy_payload = load_json(research_preview_policy.stdout)
            require(research_preview_policy_payload.get("allowed") is False, f"research-lab-consumption without confirm-record should be denied for advance: {research_preview_policy_payload}", failures)
            loop_supervision_verify_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator loop-supervision --adapter hermes --limit 8 --work-packet', phase='verify')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([loop_supervision_verify_policy.stdout, loop_supervision_verify_policy.stderr])
            loop_supervision_verify_payload = load_json(loop_supervision_verify_policy.stdout)
            require(loop_supervision_verify_payload.get("allowed") is True, f"loop-supervision verify should be allowlisted: {loop_supervision_verify_payload}", failures)
            remediation_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator remediate-evidence-gap --run-id run_seed_28', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([remediation_policy.stdout, remediation_policy.stderr])
            remediation_policy_payload = load_json(remediation_policy.stdout)
            require(remediation_policy_payload.get("allowed") is True, f"remediation preview should be allowlisted as read-only action: {remediation_policy_payload}", failures)
            remediation_confirm_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator remediate-evidence-gap --run-id run_seed_28 --confirm-create', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([remediation_confirm_policy.stdout, remediation_confirm_policy.stderr])
            remediation_confirm_payload = load_json(remediation_confirm_policy.stdout)
            require(remediation_confirm_payload.get("allowed") is False, f"remediation confirm-create must stay denied: {remediation_confirm_payload}", failures)
            intake_auto_plan_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator intake-auto-plan --task-id tsk_demo --agent-id agt_demo --adapter openclaw --confirm-plan', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([intake_auto_plan_policy.stdout, intake_auto_plan_policy.stderr])
            intake_auto_plan_payload = load_json(intake_auto_plan_policy.stdout)
            require(intake_auto_plan_payload.get("allowed") is True, f"intake auto-plan confirm-plan should be allowlisted: {intake_auto_plan_payload}", failures)
            intake_auto_plan_preview_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator intake-auto-plan --task-id tsk_demo --agent-id agt_demo --adapter openclaw', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([intake_auto_plan_preview_policy.stdout, intake_auto_plan_preview_policy.stderr])
            intake_auto_plan_preview_payload = load_json(intake_auto_plan_preview_policy.stdout)
            require(intake_auto_plan_preview_payload.get("allowed") is False, f"intake auto-plan without confirm-plan should be denied: {intake_auto_plan_preview_payload}", failures)
            intake_auto_plan_high_risk_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator intake-auto-plan --task-id tsk_demo --agent-id agt_demo --adapter openclaw --confirm-plan --allow-high-risk', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([intake_auto_plan_high_risk_policy.stdout, intake_auto_plan_high_risk_policy.stderr])
            intake_auto_plan_high_risk_payload = load_json(intake_auto_plan_high_risk_policy.stdout)
            require(intake_auto_plan_high_risk_payload.get("allowed") is False, f"intake auto-plan high-risk bypass should be denied: {intake_auto_plan_high_risk_payload}", failures)
        finally:
            stop_server(server)
    secret_leaked = leaked("\n".join(outputs))
    require(not secret_leaked, "advance-loop output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_advance_loop_smoke",
        "loop_id": loop_id,
        "secret_leaked": secret_leaked,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
