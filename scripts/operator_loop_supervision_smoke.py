#!/usr/bin/env python3
"""Smoke-test the read-only Hermes/OpenClaw loop supervision API and CLI."""

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
SERVER = ROOT / "server.py"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_-]{12,}"),
    re.compile(r"agtsess_[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ntn_[A-Za-z0-9_-]{16,}"),
    re.compile(r"AGENTOPS_API_KEY\s*=", re.IGNORECASE),
]
LEDGER_TABLES = [
    "tasks",
    "runs",
    "tool_calls",
    "runtime_events",
    "evaluations",
    "audit_logs",
    "artifacts",
    "approvals",
    "memories",
    "agent_plans",
    "plan_evidence_manifests",
    "workflow_jobs",
    "agent_gateway_tokens",
    "agent_gateway_sessions",
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"})
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
            status, payload = http_json(base_url, "/api/local/readiness")
            if status == 200 and payload.get("operation") == "local_readiness":
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        counts: dict[str, int] = {}
        for table in LEDGER_TABLES:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return counts
    finally:
        conn.close()


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def run_cli(args: list[str], base_url: str, outputs: list[str]) -> dict:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    proc = subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    outputs.extend([proc.stdout, proc.stderr])
    if proc.returncode != 0:
        raise RuntimeError(f"agentops {' '.join(args)} failed: {proc.stderr or proc.stdout}")
    return json.loads(proc.stdout or "{}")


def create_plan_quality_attention_fixture(base_url: str, outputs: list[str]) -> dict:
    stamp = str(int(time.time() * 1000000))
    agent_id = f"agt_loop_quality_{stamp}"
    task_id = f"tsk_loop_quality_{stamp}"
    run_cli(["agent", "register", "--id", agent_id, "--name", "Loop Quality Agent", "--role", "Builder", "--runtime", "mock"], base_url, outputs)
    run_cli([
        "task", "create",
        "--task-id", task_id,
        "--title", "Loop supervision plan quality fixture",
        "--description", "Create a hard-verifying but quality-attention Agent Plan for loop supervision.",
        "--owner-agent-id", agent_id,
        "--requester-id", "usr_founder",
        "--acceptance", "Loop supervision must surface plan quality attention without hard-blocking run_start.",
        "--risk", "low",
    ], base_url, outputs)
    plan_payload = run_cli([
        "agent-plan", "create",
        "--agent-id", agent_id,
        "--task-id", task_id,
        "--task-understanding", "Build loop-supervision quality fixture with sparse method steps.",
        "--referenced-specs", "PROJECT_SPEC.md,AGENT_WORKFLOW.md",
        "--referenced-memories", "knowledge/shared/common_failures.md",
        "--referenced-bases", "base_local_tasks",
        "--proposed-files-to-change", "server.py,scripts/operator_loop_supervision_smoke.py",
        "--risk", "low",
        "--execution-steps", "READ,PLAN,RETRIEVE,EXECUTE",
        "--verification-plan", "Run operator_loop_supervision_smoke.py and inspect Agent Plan quality audit readback.",
        "--rollback-plan", "Stop before bounded/live execution if plan quality attention cannot be inspected.",
    ], base_url, outputs)
    plan_id = (plan_payload.get("agent_plan") or {}).get("plan_id")
    if not plan_id:
        raise RuntimeError(f"plan missing: {plan_payload}")
    verified = run_cli(["agent-plan", "verify", "--plan-id", str(plan_id)], base_url, outputs)
    quality = (verified.get("verification") or {}).get("quality") or {}
    if quality.get("status") != "attention":
        raise RuntimeError(f"fixture plan should have quality attention: {quality}")
    run_payload = run_cli([
        "run", "start",
        "--task-id", task_id,
        "--agent-id", agent_id,
        "--plan-id", str(plan_id),
        "--input-summary", "Loop supervision plan quality attention fixture.",
    ], base_url, outputs)
    run_id = (run_payload.get("run") or {}).get("run_id")
    if not run_id:
        raise RuntimeError(f"run missing: {run_payload}")
    tool = run_cli(["toolcall", "record", "--run-id", str(run_id), "--agent-id", agent_id, "--tool", "loop.quality.fixture", "--category", "custom", "--risk", "low", "--status", "completed", "--summary", "Fixture tool call completed."], base_url, outputs)
    evaluation = run_cli(["eval", "submit", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--gate", "operator_loop_supervision_plan_quality", "--score", "1", "--pass", "--notes", "Fixture evaluation passed."], base_url, outputs)
    artifact = run_cli(["artifact", "record", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--type", "loop_supervision_plan_quality_fixture", "--title", "Loop supervision quality fixture", "--summary", "Safe fixture artifact summary.", "--uri", f"run://{run_id}"], base_url, outputs)
    run_cli(["run", "heartbeat", "--run-id", str(run_id), "--status", "completed", "--summary", "Loop supervision quality fixture completed.", "--duration-ms", "1000"], base_url, outputs)
    manifest = run_cli([
        "plan-evidence", "create",
        "--plan-id", str(plan_id),
        "--run-id", str(run_id),
        "--agent-id", agent_id,
        "--tool-call-ids", str((tool.get("tool_call") or {}).get("tool_call_id") or ""),
        "--evaluation-ids", str((evaluation.get("evaluation") or {}).get("evaluation_id") or ""),
        "--artifact-ids", str((artifact.get("artifact") or {}).get("artifact_id") or ""),
    ], base_url, outputs)
    if (manifest.get("verification") or {}).get("pass") is not True:
        raise RuntimeError(f"manifest failed: {manifest}")
    memory = run_cli(["memory", "propose", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--scope", "task", "--type", "artifact_summary", "--text", "Loop supervision quality fixture completed with reviewed evidence."], base_url, outputs)
    memory_id = (memory.get("memory") or {}).get("memory_id")
    if memory_id:
        run_cli(["memory", "approve", "--memory-id", str(memory_id)], base_url, outputs)
    return {"agent_id": agent_id, "task_id": task_id, "run_id": run_id, "plan_id": plan_id, "quality": quality}


def require_adapter_command(value: object, adapter: str, label: str, failures: list[str]) -> None:
    text = str(value or "")
    require(
        f"--adapter {adapter}" in text or f"--require-adapter {adapter}" in text,
        f"{label} missing {adapter} adapter binding: {text}",
        failures,
    )
    for other in {"hermes", "openclaw", "mock"} - {adapter}:
        require(f"--adapter {other}" not in text, f"{label} leaked {other} adapter: {text}", failures)
        require(f"--require-adapter {other}" not in text, f"{label} leaked {other} live-readiness adapter: {text}", failures)


def validate(payload: dict, failures: list[str], *, expect_quality_attention: bool = False, expect_service_primary: bool = False) -> None:
    require(payload.get("operation") == "operator_loop_supervision", f"wrong operation: {payload}", failures)
    require(payload.get("provider") == "agentops-operator", f"wrong provider: {payload}", failures)
    require(payload.get("status") in {"ready_to_confirm", "record_first", "preview_only", "blocked", "attention"}, f"bad status: {payload.get('status')}", failures)
    require(payload.get("token_omitted") is True, "top-level token omission missing", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"read-only proof missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"ledger mutation proof missing: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"live execution proof missing: {safety}", failures)
    require(safety.get("server_executes_shell") is False, f"server shell proof missing: {safety}", failures)
    require(safety.get("raw_prompt_omitted") is True, f"raw prompt omission proof missing: {safety}", failures)
    require(safety.get("raw_response_omitted") is True, f"raw response omission proof missing: {safety}", failures)
    require(safety.get("raw_content_omitted") is True, f"raw content omission proof missing: {safety}", failures)
    summary = payload.get("summary") or {}
    require(summary.get("items") == 2, f"expected Hermes/OpenClaw items: {summary}", failures)
    require(summary.get("can_confirm_all") is True, f"bounded confirm should be structurally ready: {summary}", failures)
    require(summary.get("agent_plan_quality_status") in {"pass", "attention", "not_applicable"}, f"plan quality summary missing: {summary}", failures)
    require(summary.get("agent_plan_quality_attention") is not None, f"plan quality attention count missing: {summary}", failures)
    require(summary.get("agent_plan_quality_blocked") is not None, f"plan quality blocked count missing: {summary}", failures)
    if expect_quality_attention:
        require(summary.get("agent_plan_quality_status") == "attention", f"plan quality summary should be attention: {summary}", failures)
        require(int(summary.get("agent_plan_quality_attention") or 0) >= 1, f"plan quality attention count should be positive: {summary}", failures)
    work_packets = payload.get("work_packets") or []
    require(len(work_packets) == 2, f"top-level work packets missing: {work_packets}", failures)
    require(summary.get("research_lab_packets") == 2, f"top-level research lab packet summary missing: {summary}", failures)
    require(len(summary.get("research_lab_packet_hashes") or []) == 2, f"top-level research lab packet hashes missing: {summary}", failures)
    require(len(payload.get("research_lab_packets") or []) == 2, f"top-level research lab packets missing: {payload.get('research_lab_packets')}", failures)
    handoff_summary = payload.get("handoff_summary") or {}
    require(handoff_summary.get("ready_for_handoff") is True, f"handoff source should be ready: {handoff_summary}", failures)
    items = payload.get("items") or []
    adapters = {item.get("adapter") for item in items}
    require({"hermes", "openclaw"}.issubset(adapters), f"missing Hermes/OpenClaw supervision items: {adapters}", failures)
    for item in items:
        adapter = item.get("adapter")
        require(item.get("operation") == "operator_loop_supervision_item", f"{adapter} wrong item operation: {item}", failures)
        require(item.get("status") in {"ready_to_confirm", "record_first", "preview_only", "blocked", "attention"}, f"{adapter} bad item status: {item}", failures)
        require(item.get("can_preview_loop") is True, f"{adapter} preview gate missing: {item}", failures)
        require(item.get("can_confirm_bounded_loop") is True, f"{adapter} confirm gate missing: {item}", failures)
        require(item.get("should_record_before_execute") in {True, False}, f"{adapter} record decision missing: {item}", failures)
        work_packet = item.get("agent_work_packet") or {}
        require(work_packet.get("operation") == "operator_loop_supervision_agent_work_packet", f"{adapter} work packet missing: {work_packet}", failures)
        require(work_packet.get("schema_version") == "agent_work_packet_v1", f"{adapter} work packet schema missing: {work_packet}", failures)
        require(work_packet.get("adapter") == adapter, f"{adapter} work packet adapter mismatch: {work_packet}", failures)
        require(work_packet.get("packet_hash"), f"{adapter} work packet hash missing: {work_packet}", failures)
        primary_next = work_packet.get("primary_next_action") or {}
        require(primary_next.get("id"), f"{adapter} work packet primary action id missing: {primary_next}", failures)
        require(primary_next.get("phase") in {"READ", "PLAN", "RETRIEVE", "COMPARE", "PREFLIGHT", "EXECUTE", "VERIFY", "RECORD"}, f"{adapter} work packet primary action phase missing: {primary_next}", failures)
        require(primary_next.get("command"), f"{adapter} work packet primary action command missing: {primary_next}", failures)
        require(primary_next.get("confirm_required") in {True, False}, f"{adapter} work packet primary confirm flag missing: {primary_next}", failures)
        require(primary_next.get("receipt_required") in {True, False}, f"{adapter} work packet primary receipt flag missing: {primary_next}", failures)
        require(primary_next.get("safe_to_auto_continue") in {True, False}, f"{adapter} work packet safe-to-auto flag missing: {primary_next}", failures)
        require(primary_next.get("requires_human_before_effect") in {True, False}, f"{adapter} work packet human gate flag missing: {primary_next}", failures)
        if primary_next.get("requires_human_before_effect") is True:
            require(primary_next.get("safe_to_auto_continue") is False, f"{adapter} human-gated primary action must not auto-continue: {primary_next}", failures)
        require(primary_next.get("verify_command"), f"{adapter} work packet primary verify command missing: {primary_next}", failures)
        require(work_packet.get("loop_protocol") == ["READ", "PLAN", "RETRIEVE", "COMPARE", "PREFLIGHT", "EXECUTE", "VERIFY", "RECORD"], f"{adapter} loop protocol missing: {work_packet}", failures)
        work_phase_commands = work_packet.get("phase_commands") or {}
        require({"read", "plan", "retrieve", "compare", "preflight", "execute", "verify", "record"}.issubset(work_phase_commands), f"{adapter} work phase commands missing: {work_phase_commands}", failures)
        require_adapter_command(work_phase_commands.get("preflight"), adapter, f"{adapter} work packet preflight", failures)
        require_adapter_command(work_phase_commands.get("execute"), adapter, f"{adapter} work packet execute", failures)
        require("--confirm-loop" in str(work_phase_commands.get("execute") or ""), f"{adapter} work packet execute must stay confirm-gated: {work_phase_commands}", failures)
        command_lanes = work_packet.get("command_lanes") or {}
        require(any(f"--adapter {adapter}" in str(command) for command in command_lanes.get("safe_read") or []), f"{adapter} work packet safe lane missing adapter command: {command_lanes}", failures)
        require(any("--confirm-run" in str(command) or "--confirm-loop" in str(command) for command in command_lanes.get("confirm_required") or []), f"{adapter} work packet confirm lane missing: {command_lanes}", failures)
        receipts = work_packet.get("receipts") or {}
        require((receipts.get("service_control") or {}).get("required") is True, f"{adapter} work packet service receipt missing: {receipts}", failures)
        require((receipts.get("control_readback") or {}).get("required") is True, f"{adapter} work packet readback missing: {receipts}", failures)
        require((receipts.get("run_start_admission") or {}).get("control_readback_required") is True, f"{adapter} work packet run_start receipt missing: {receipts}", failures)
        evidence_contract = work_packet.get("evidence_contract") or {}
        require(evidence_contract.get("agent_plan_required") is True, f"{adapter} work packet Agent Plan contract missing: {evidence_contract}", failures)
        require(evidence_contract.get("agent_plan_quality_audit_required") is True, f"{adapter} work packet Agent Plan quality audit contract missing: {evidence_contract}", failures)
        contract_quality = evidence_contract.get("agent_plan_quality") or {}
        require(contract_quality.get("status") in {"pass", "attention", "not_applicable"}, f"{adapter} work packet quality status missing: {contract_quality}", failures)
        require(contract_quality.get("hard_run_start_gate") is False, f"{adapter} quality audit must not be hard run_start gate: {contract_quality}", failures)
        require(str(contract_quality.get("command") or "").startswith("agentops operator evidence-report"), f"{adapter} quality audit command missing: {contract_quality}", failures)
        if expect_quality_attention:
            require(contract_quality.get("status") == "attention", f"{adapter} work packet quality should be attention: {contract_quality}", failures)
            require(int(contract_quality.get("attention") or 0) >= 1, f"{adapter} work packet quality attention count missing: {contract_quality}", failures)
        contract_service = evidence_contract.get("service_managed_loop") or {}
        require(evidence_contract.get("service_managed_loop_required") is True, f"{adapter} work packet service-managed contract missing: {evidence_contract}", failures)
        require(contract_service.get("status") in {"pass", "attention"}, f"{adapter} work packet service closure status missing: {contract_service}", failures)
        require(contract_service.get("hard_run_start_gate") is False, f"{adapter} service closure should not be hard run_start gate: {contract_service}", failures)
        require(contract_service.get("server_executes_shell") is False, f"{adapter} service closure shell proof missing: {contract_service}", failures)
        require(contract_service.get("receipt_verified") in {True, False}, f"{adapter} service closure receipt state missing: {contract_service}", failures)
        require(contract_service.get("control_readback_attached") in {True, False}, f"{adapter} service closure readback state missing: {contract_service}", failures)
        if contract_service.get("required") is True:
            require(contract_service.get("step") in {"record_service_control_receipt", "record_control_readback", "confirm_service_control_load"}, f"{adapter} service closure step missing: {contract_service}", failures)
            require(contract_service.get("phase") in {"RECORD", "PREFLIGHT"}, f"{adapter} service closure phase missing: {contract_service}", failures)
            require_adapter_command(contract_service.get("command"), adapter, f"{adapter} service closure command", failures)
        require(evidence_contract.get("knowledge_retrieval_required") is True, f"{adapter} work packet retrieval contract missing: {evidence_contract}", failures)
        research_lab_packet = work_packet.get("research_lab_packet") or {}
        require(research_lab_packet.get("operation") == "operator_research_lab_packet", f"{adapter} embedded Research Lab packet missing: {research_lab_packet}", failures)
        require(research_lab_packet.get("schema_version") == "research_lab_agent_work_packet_v1", f"{adapter} embedded Research Lab packet schema missing: {research_lab_packet}", failures)
        require(research_lab_packet.get("adapter") == adapter, f"{adapter} embedded Research Lab adapter mismatch: {research_lab_packet}", failures)
        require(research_lab_packet.get("status") == "ready", f"{adapter} embedded Research Lab packet not ready: {research_lab_packet}", failures)
        require(research_lab_packet.get("packet_hash"), f"{adapter} embedded Research Lab packet hash missing: {research_lab_packet}", failures)
        research_lab_safety = research_lab_packet.get("safety") or {}
        require(research_lab_safety.get("read_only") is True, f"{adapter} embedded Research Lab read-only proof missing: {research_lab_safety}", failures)
        require(research_lab_safety.get("ledger_mutated") is False, f"{adapter} embedded Research Lab ledger proof missing: {research_lab_safety}", failures)
        require(research_lab_safety.get("server_executes_shell") is False, f"{adapter} embedded Research Lab server-shell proof missing: {research_lab_safety}", failures)
        require(research_lab_safety.get("ssh_command_executed") is False, f"{adapter} embedded Research Lab SSH proof missing: {research_lab_safety}", failures)
        require(research_lab_safety.get("network_probe_performed") is False, f"{adapter} embedded Research Lab network proof missing: {research_lab_safety}", failures)
        research_lab_contract = evidence_contract.get("research_lab_packet") or {}
        require(evidence_contract.get("research_lab_packet_required") is True, f"{adapter} Research Lab packet contract missing: {evidence_contract}", failures)
        require(research_lab_contract.get("status") == "pass", f"{adapter} Research Lab packet contract not passing: {research_lab_contract}", failures)
        require(research_lab_contract.get("packet_hash") == research_lab_packet.get("packet_hash"), f"{adapter} Research Lab contract hash mismatch: {research_lab_contract}", failures)
        require("agentops operator research-lab-packet" in str(research_lab_contract.get("read_command") or ""), f"{adapter} Research Lab read command missing: {research_lab_contract}", failures)
        require("validate-spec --spec examples/ssh_experiment.json" in str(research_lab_contract.get("verify_command") or ""), f"{adapter} Research Lab verify command missing: {research_lab_contract}", failures)
        require(research_lab_contract.get("local_spec_validation_requires_approval") is False, f"{adapter} Research Lab local approval boundary wrong: {research_lab_contract}", failures)
        require(research_lab_contract.get("real_ssh_execution_requires_approval") is True, f"{adapter} Research Lab SSH approval boundary wrong: {research_lab_contract}", failures)
        require(research_lab_contract.get("server_executes_shell") is False, f"{adapter} Research Lab contract shell proof missing: {research_lab_contract}", failures)
        require(evidence_contract.get("audit_ledger_required") is True, f"{adapter} work packet audit contract missing: {evidence_contract}", failures)
        work_safety = work_packet.get("safety") or {}
        require(work_safety.get("read_only") is True, f"{adapter} work packet read-only safety missing: {work_safety}", failures)
        require(work_safety.get("server_executes_shell") is False, f"{adapter} work packet shell safety missing: {work_safety}", failures)
        require(work_safety.get("live_execution_performed") is False, f"{adapter} work packet live safety missing: {work_safety}", failures)
        item_safety = item.get("safety") or {}
        require(item_safety.get("read_only") is True, f"{adapter} read-only safety missing: {item_safety}", failures)
        require(item_safety.get("ledger_mutated") is False, f"{adapter} ledger safety missing: {item_safety}", failures)
        require(item_safety.get("server_executes_shell") is False, f"{adapter} shell safety missing: {item_safety}", failures)
        gate_ids = {gate.get("id") for gate in (item.get("gates") or [])}
        require({"handoff_ready", "current_code", "method_gates", "preview_loop", "local_deployment", "bounded_confirm", "plan_quality", "service_managed_loop", "record_pressure", "server_shell_boundary", "research_lab_packet"}.issubset(gate_ids), f"{adapter} gates missing: {gate_ids}", failures)
        quality_gate = next((gate for gate in (item.get("gates") or []) if gate.get("id") == "plan_quality"), {})
        require(quality_gate.get("status") in {"pass", "attention"}, f"{adapter} quality gate status missing: {quality_gate}", failures)
        require(quality_gate.get("hard_run_start_gate") is False, f"{adapter} quality gate should not hard-block run_start: {quality_gate}", failures)
        require(str(quality_gate.get("command") or "").startswith("agentops operator evidence-report"), f"{adapter} quality gate command missing: {quality_gate}", failures)
        if expect_quality_attention:
            require(quality_gate.get("status") == "attention", f"{adapter} quality gate should be attention: {quality_gate}", failures)
            require(item.get("can_confirm_bounded_loop") is True, f"{adapter} quality attention should not change structural confirm readiness: {item}", failures)
        service_gate = next((gate for gate in (item.get("gates") or []) if gate.get("id") == "service_managed_loop"), {})
        require(service_gate.get("status") in {"pass", "attention"}, f"{adapter} service gate status missing: {service_gate}", failures)
        require(service_gate.get("hard_run_start_gate") is False, f"{adapter} service gate should not hard-block run_start: {service_gate}", failures)
        if service_gate.get("status") == "attention":
            require(service_gate.get("step") in {"record_service_control_receipt", "record_control_readback", "confirm_service_control_load"}, f"{adapter} service gate step missing: {service_gate}", failures)
            require_adapter_command(service_gate.get("command"), adapter, f"{adapter} service gate command", failures)
        research_lab_gate = next((gate for gate in (item.get("gates") or []) if gate.get("id") == "research_lab_packet"), {})
        require(research_lab_gate.get("status") == "pass", f"{adapter} Research Lab gate should pass: {research_lab_gate}", failures)
        require("agentops operator research-lab-packet" in str(research_lab_gate.get("command") or ""), f"{adapter} Research Lab gate command missing: {research_lab_gate}", failures)
        require(research_lab_gate.get("packet_hash") == research_lab_packet.get("packet_hash"), f"{adapter} Research Lab gate hash mismatch: {research_lab_gate}", failures)
        service_closure = item.get("service_closure") or {}
        require(service_closure.get("status") in {"pass", "attention"}, f"{adapter} service closure missing: {service_closure}", failures)
        require(service_closure.get("hard_run_start_gate") is False, f"{adapter} service closure should remain non-hard gate: {service_closure}", failures)
        if service_closure.get("required") is True:
            require(service_closure.get("step") in {"record_service_control_receipt", "record_control_readback", "confirm_service_control_load"}, f"{adapter} service closure required step missing: {service_closure}", failures)
            require_adapter_command(service_closure.get("command"), adapter, f"{adapter} service closure required command", failures)
        if expect_service_primary:
            require(service_closure.get("required") is True, f"{adapter} service closure should be required before dispatch: {service_closure}", failures)
            require(item.get("status") == "record_first", f"{adapter} service closure should make item record_first: {item}", failures)
            require(primary_next.get("command") == service_closure.get("command"), f"{adapter} primary action should be service closure: primary={primary_next} service={service_closure}", failures)
            require(primary_next.get("phase") == service_closure.get("phase"), f"{adapter} primary phase should match service closure: primary={primary_next} service={service_closure}", failures)
            require(str(primary_next.get("verify_command") or "").startswith("agentops operator action-receipts"), f"{adapter} service closure should verify through action receipts: {primary_next}", failures)
        local_gate = next((gate for gate in (item.get("gates") or []) if gate.get("id") == "local_deployment"), {})
        require(local_gate.get("ok") is True, f"{adapter} local deployment gate not passing: {local_gate}", failures)
        require(local_gate.get("recommended_adapter") == adapter, f"{adapter} local deployment recommended adapter mismatch: {local_gate}", failures)
        require(local_gate.get("service_managed_adapter") == adapter, f"{adapter} service-managed gate adapter mismatch: {local_gate}", failures)
        commands = item.get("commands") or {}
        require(str(commands.get("handoff") or "").startswith(f"agentops operator agent-loop-handoff --adapter {adapter}"), f"{adapter} handoff command missing: {commands}", failures)
        require(str(commands.get("start_check") or "").startswith(f"agentops operator start-check --adapter {adapter}"), f"{adapter} start-check command missing: {commands}", failures)
        require(str(commands.get("preview_loop") or "").startswith(f"agentops operator loop-driver --adapter {adapter}"), f"{adapter} preview command missing: {commands}", failures)
        require("--confirm-loop" in str(commands.get("confirm_loop") or ""), f"{adapter} confirm-loop command missing: {commands}", failures)
        require_adapter_command(commands.get("preview_loop"), adapter, f"{adapter} preview command", failures)
        require_adapter_command(commands.get("confirm_loop"), adapter, f"{adapter} confirm command", failures)
        require(str(commands.get("record_review") or "").startswith("agentops review queue"), f"{adapter} record command missing: {commands}", failures)
        require(commands.get("recommended_next"), f"{adapter} recommended command missing: {commands}", failures)
        local_deployment = item.get("local_deployment") or {}
        local_run_path = local_deployment.get("local_run_path") or {}
        service_managed = local_deployment.get("service_managed_loop") or {}
        service_commands = service_managed.get("commands") or {}
        managed_execution = local_deployment.get("managed_execution_path") or {}
        managed_commands = managed_execution.get("commands") or {}
        managed_gate_ids = {str(gate.get("id")) for gate in managed_execution.get("gates") or [] if isinstance(gate, dict)}
        require(local_run_path.get("operation") == "local_run_path_compact", f"{adapter} local run path missing: {local_deployment}", failures)
        require(local_run_path.get("recommended_adapter") == adapter, f"{adapter} local run path adapter mismatch: {local_run_path}", failures)
        require((local_run_path.get("safety") or {}).get("server_executes_shell") is False, f"{adapter} local run path shell proof missing: {local_run_path}", failures)
        require(service_managed.get("adapter") == adapter, f"{adapter} service-managed adapter mismatch: {service_managed}", failures)
        require(service_managed.get("receipt_required") is True, f"{adapter} service receipt requirement missing: {service_managed}", failures)
        require(service_managed.get("receipt_verified") in {True, False}, f"{adapter} service receipt verification state missing: {service_managed}", failures)
        require(service_managed.get("control_readback_required") is True, f"{adapter} control readback requirement missing: {service_managed}", failures)
        require(service_managed.get("control_readback_attached") in {True, False}, f"{adapter} control readback state missing: {service_managed}", failures)
        require(service_managed.get("service_active_loop_ready") in {True, False}, f"{adapter} active loop state missing: {service_managed}", failures)
        require(service_managed.get("active_status") in {"loaded", "not_loaded", "unverified"}, f"{adapter} active status missing: {service_managed}", failures)
        require((service_managed.get("safety") or {}).get("server_executes_shell") is False, f"{adapter} service-managed shell proof missing: {service_managed}", failures)
        require(service_managed.get("live_execution_performed") is False, f"{adapter} service-managed live execution proof missing: {service_managed}", failures)
        for key in ["service_check", "service_control_preview", "record_verified_receipt", "record_control_readback"]:
            require_adapter_command(service_commands.get(key), adapter, f"{adapter} service-managed {key}", failures)
        require(managed_execution.get("operation") == "operator_service_managed_execution_path", f"{adapter} managed execution path missing: {managed_execution}", failures)
        require(managed_execution.get("adapter") == adapter, f"{adapter} managed execution adapter mismatch: {managed_execution}", failures)
        require((managed_execution.get("safety") or {}).get("server_executes_shell") is False, f"{adapter} managed execution shell proof missing: {managed_execution}", failures)
        require(managed_execution.get("service_active_loop_ready") in {True, False}, f"{adapter} managed active loop state missing: {managed_execution}", failures)
        require(managed_execution.get("recommended_before_dispatch") in {"record_service_control_receipt_and_readback", "confirm_service_control_load", "dispatch_customer_worker_task"}, f"{adapter} managed recommendation missing: {managed_execution}", failures)
        require({"service_managed_loop_ready", "service_active_loop_ready", "customer_worker_dispatch", "plan_evidence_required", "review_queue_required"}.issubset(managed_gate_ids), f"{adapter} managed execution gates missing: {managed_gate_ids}", failures)
        require(any(str(command).startswith(f"agentops worker preflight --adapter {adapter}") for command in managed_execution.get("first_safe_commands") or []), f"{adapter} managed first-safe preflight missing: {managed_execution}", failures)
        require(any(f"--adapter {adapter}" in str(command) and "--confirm-run" in str(command) for command in managed_execution.get("confirm_required_commands") or []), f"{adapter} managed confirm command missing: {managed_execution}", failures)
        require(any(str(command).startswith("agentops operator evidence-report --run-id") for command in managed_execution.get("verify_commands") or []), f"{adapter} managed evidence verify missing: {managed_execution}", failures)
        require(any(str(command).startswith("agentops review queue") for command in managed_execution.get("verify_commands") or []), f"{adapter} managed review verify missing: {managed_execution}", failures)
        require_adapter_command(managed_commands.get("service_check"), adapter, f"{adapter} managed service_check", failures)
        require_adapter_command(managed_commands.get("service_control_receipt"), adapter, f"{adapter} managed service_control_receipt", failures)
        require_adapter_command(managed_commands.get("service_control_readback"), adapter, f"{adapter} managed service_control_readback", failures)
        require_adapter_command(managed_commands.get("service_control_load_confirm"), adapter, f"{adapter} managed service_control_load_confirm", failures)
        require("--confirm-control" in str(managed_commands.get("service_control_load_confirm") or ""), f"{adapter} managed load confirm-control missing: {managed_execution}", failures)
        require_adapter_command(managed_commands.get("customer_worker_dispatch"), adapter, f"{adapter} managed customer dispatch", failures)
        require(str(managed_commands.get("evidence_report") or "").startswith("agentops operator evidence-report --run-id"), f"{adapter} managed evidence command missing: {managed_execution}", failures)
        require(str(managed_commands.get("review_queue") or "").startswith("agentops review queue"), f"{adapter} managed review command missing: {managed_execution}", failures)
        run_start_admission = item.get("run_start_admission") or {}
        require(run_start_admission.get("operation") == "operator_loop_supervision_run_start_admission", f"{adapter} run_start admission operation missing: {run_start_admission}", failures)
        require(run_start_admission.get("gateway_endpoint") == "POST /api/agent-gateway/runs/start", f"{adapter} gateway endpoint missing: {run_start_admission}", failures)
        require(run_start_admission.get("governed_runtime") is True, f"{adapter} governed runtime missing: {run_start_admission}", failures)
        require(run_start_admission.get("would_allow_run_start") is True, f"{adapter} run_start should be structurally allowed: {run_start_admission}", failures)
        require(run_start_admission.get("would_block_run_start") is False, f"{adapter} run_start block projection drifted: {run_start_admission}", failures)
        require(run_start_admission.get("fail_closed_error") == "run_start_loop_supervision_blocked", f"{adapter} fail-closed error missing: {run_start_admission}", failures)
        require(run_start_admission.get("no_run_created_on_block") is True, f"{adapter} no-run-on-block proof missing: {run_start_admission}", failures)
        require(run_start_admission.get("agent_plan_required") is True, f"{adapter} Agent Plan precondition missing: {run_start_admission}", failures)
        require(run_start_admission.get("supervision_hash_state") == "bound_by_agent_gateway_run_start", f"{adapter} hash binding state missing: {run_start_admission}", failures)
        receipt_projection = run_start_admission.get("receipt_projection") or {}
        require(receipt_projection.get("source") == f"operator_loop_supervision.run_start_gate:{adapter}", f"{adapter} receipt projection source missing: {receipt_projection}", failures)
        require(receipt_projection.get("action_id") == f"run_start_supervision:{adapter}", f"{adapter} receipt projection action id missing: {receipt_projection}", failures)
        require(receipt_projection.get("action_signature"), f"{adapter} receipt projection action signature missing: {receipt_projection}", failures)
        require(str(receipt_projection.get("action_command") or "").startswith(f"agentops operator loop-supervision --adapter {adapter}"), f"{adapter} receipt projection action command missing: {receipt_projection}", failures)
        require(str(receipt_projection.get("verify_command") or "").startswith("agentops operator loop-audit"), f"{adapter} receipt projection verify command missing: {receipt_projection}", failures)
        require(receipt_projection.get("control_readback_required") is True, f"{adapter} receipt projection control readback missing: {receipt_projection}", failures)
        require(receipt_projection.get("control_readback_source") == f"operator_loop_supervision.run_start_gate:{adapter}.control_readback", f"{adapter} receipt projection control readback source missing: {receipt_projection}", failures)
        require(receipt_projection.get("token_omitted") is True, f"{adapter} receipt projection token omission missing: {receipt_projection}", failures)
        run_start_safety = run_start_admission.get("safety") or {}
        require(run_start_safety.get("read_only") is True, f"{adapter} run_start admission read-only proof missing: {run_start_safety}", failures)
        require(run_start_safety.get("ledger_mutated") is False, f"{adapter} run_start admission ledger proof missing: {run_start_safety}", failures)
        require(run_start_safety.get("live_execution_performed") is False, f"{adapter} run_start admission live proof missing: {run_start_safety}", failures)
        require(run_start_safety.get("server_executes_shell") is False, f"{adapter} run_start admission shell proof missing: {run_start_safety}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-loop-supervision-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops.db"
        log_path = tmp_path / "server.log"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_DEPLOYMENT_MODE"] = "local"
        proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=log_path.open("w"),
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            pre_before = db_counts(db_path)
            pre_status, pre_payload = http_json(base_url, "/api/operator/loop-supervision?limit=5")
            outputs.append(json.dumps(pre_payload, ensure_ascii=False))
            require(pre_status == 200, f"pre-fixture HTTP loop-supervision status {pre_status}: {pre_payload}", failures)
            validate(pre_payload, failures, expect_service_primary=True)
            pre_after = db_counts(db_path)
            require(pre_before == pre_after, f"pre-fixture loop-supervision mutated ledger: before={pre_before} after={pre_after}", failures)
            fixture = create_plan_quality_attention_fixture(base_url, outputs)
            require(bool(fixture.get("run_id") and fixture.get("plan_id")), f"quality fixture missing ids: {fixture}", failures)
            fixture_task_id = str(fixture.get("task_id") or "")
            before = db_counts(db_path)
            http_status, http_payload = http_json(base_url, f"/api/operator/loop-supervision?limit=5&task_id={fixture_task_id}")
            outputs.append(json.dumps(http_payload, ensure_ascii=False))
            require(http_status == 200, f"HTTP loop-supervision status {http_status}: {http_payload}", failures)
            validate(http_payload, failures, expect_quality_attention=True)
            cli_env = env.copy()
            cli_env["AGENTOPS_BASE_URL"] = base_url
            result = subprocess.run(
                [str(CLI), "operator", "loop-supervision", "--limit", "5", "--task-id", fixture_task_id],
                cwd=ROOT,
                env=cli_env,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            outputs.extend([result.stdout, result.stderr])
            require(result.returncode == 0, f"loop-supervision CLI failed: {result.stderr or result.stdout}", failures)
            cli_payload = json.loads(result.stdout or "{}")
            validate(cli_payload, failures, expect_quality_attention=True)
            require(cli_payload.get("summary") == http_payload.get("summary"), f"CLI/HTTP summary drift: cli={cli_payload.get('summary')} http={http_payload.get('summary')}", failures)
            packet_result = subprocess.run(
                [str(CLI), "operator", "loop-supervision", "--limit", "5", "--task-id", fixture_task_id, "--work-packet"],
                cwd=ROOT,
                env=cli_env,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            outputs.extend([packet_result.stdout, packet_result.stderr])
            require(packet_result.returncode == 0, f"loop-supervision --work-packet failed: {packet_result.stderr or packet_result.stdout}", failures)
            packet_payload = json.loads(packet_result.stdout or "{}")
            require(packet_payload.get("operation") == "operator_loop_work_packet_bundle", f"work packet bundle operation mismatch: {packet_payload}", failures)
            require(packet_payload.get("schema_version") == "agent_work_packet_bundle_v1", f"work packet bundle schema mismatch: {packet_payload}", failures)
            packet_summary = packet_payload.get("summary") or {}
            packet_items = packet_payload.get("work_packets") or []
            require(packet_summary.get("work_packets") == 2, f"work packet bundle summary missing: {packet_summary}", failures)
            require(packet_summary.get("research_lab_packets") == 2, f"work packet bundle Research Lab summary missing: {packet_summary}", failures)
            require(len(packet_summary.get("research_lab_packet_hashes") or []) == 2, f"work packet bundle Research Lab hashes missing: {packet_summary}", failures)
            require(len(packet_items) == 2, f"work packet bundle items missing: {packet_payload}", failures)
            require(len(packet_payload.get("research_lab_packets") or []) == 2, f"work packet bundle Research Lab packets missing: {packet_payload}", failures)
            require({"hermes", "openclaw"}.issubset({item.get("adapter") for item in packet_items}), f"work packet bundle adapters missing: {packet_items}", failures)
            require(all((item.get("safety") or {}).get("server_executes_shell") is False for item in packet_items), f"work packet bundle shell safety missing: {packet_items}", failures)
            require(all((item.get("safety") or {}).get("live_execution_performed") is False for item in packet_items), f"work packet bundle live safety missing: {packet_items}", failures)
            require(all(item.get("packet_hash") for item in packet_items), f"work packet bundle hashes missing: {packet_items}", failures)
            require(all((item.get("primary_next_action") or {}).get("command") for item in packet_items), f"work packet bundle primary actions missing: {packet_items}", failures)
            require(all(((item.get("evidence_contract") or {}).get("agent_plan_quality") or {}).get("status") == "attention" for item in packet_items), f"work packet bundle quality attention missing: {packet_items}", failures)
            require(all((item.get("evidence_contract") or {}).get("service_managed_loop_required") is True for item in packet_items), f"work packet bundle service contract missing: {packet_items}", failures)
            require(all(((item.get("evidence_contract") or {}).get("service_managed_loop") or {}).get("status") in {"pass", "attention"} for item in packet_items), f"work packet bundle service closure missing: {packet_items}", failures)
            require(all(((item.get("evidence_contract") or {}).get("service_managed_loop") or {}).get("hard_run_start_gate") is False for item in packet_items), f"work packet bundle service hard gate drift: {packet_items}", failures)
            require(all((item.get("research_lab_packet") or {}).get("operation") == "operator_research_lab_packet" for item in packet_items), f"work packet bundle embedded Research Lab packet missing: {packet_items}", failures)
            require(all(((item.get("research_lab_packet") or {}).get("safety") or {}).get("server_executes_shell") is False for item in packet_items), f"work packet bundle Research Lab shell proof missing: {packet_items}", failures)
            require(all(((item.get("evidence_contract") or {}).get("research_lab_packet") or {}).get("status") == "pass" for item in packet_items), f"work packet bundle Research Lab contract missing: {packet_items}", failures)
            after = db_counts(db_path)
            require(before == after, f"loop-supervision mutated ledger: before={before} after={after}", failures)
            require(not leaked("\n".join(outputs)), "loop-supervision leaked token-like material", failures)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_loop_supervision_smoke",
        "failures": failures,
        "secret_leaked": leaked("\n".join(outputs)),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or leaked("\n".join(outputs)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
