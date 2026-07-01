#!/usr/bin/env python3
"""Verify Agent Gateway run_start consumes work-packet decisions before run creation."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SMOKE_DB_DIR = tempfile.TemporaryDirectory(prefix="agentops-run-start-work-decision-")
os.environ["AGENTOPS_DB_PATH"] = str(Path(SMOKE_DB_DIR.name) / "agentops.db")
os.environ.setdefault("AGENTOPS_SKIP_SEED_EXPORTS", "1")

import server  # noqa: E402


TOKEN_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+(?!\[REDACTED\])[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"agtok_[A-Za-z0-9_-]{16,}"),
    re.compile(r"agtsess_[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9_-]{8,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in TOKEN_PATTERNS)


def require_gate_safety(gate: dict, label: str, failures: list[str]) -> None:
    safety = gate.get("safety") or {}
    require(gate.get("token_omitted") is True, f"{label} token omission missing: {gate}", failures)
    require(gate.get("live_execution_performed") is False, f"{label} live execution proof missing: {gate}", failures)
    require(gate.get("server_executes_shell") is False, f"{label} shell proof missing: {gate}", failures)
    require(safety.get("read_only") is True, f"{label} read-only proof missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} ledger mutation proof missing: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} safety live proof missing: {safety}", failures)
    require(safety.get("server_executes_shell") is False, f"{label} safety shell proof missing: {safety}", failures)
    require(safety.get("raw_prompt_omitted") is True, f"{label} raw prompt omission missing: {safety}", failures)
    require(safety.get("raw_response_omitted") is True, f"{label} raw response omission missing: {safety}", failures)
    require(safety.get("raw_content_omitted") is True, f"{label} raw content omission missing: {safety}", failures)
    require(safety.get("token_omitted") is True, f"{label} safety token omission missing: {safety}", failures)


def fake_supervision(adapter: str = "hermes", *, decision_blocked: bool = False) -> dict:
    packet_status = "blocked" if decision_blocked else "record_first"
    action_blockers = ["smoke_packet_blocked"] if decision_blocked else []
    command = "agentops operator service-closure --fast --confirm-record" if not decision_blocked else ""
    packet = {
        "operation": "agent_work_packet",
        "adapter": adapter,
        "packet_hash": f"pkt_smoke_{adapter}_{packet_status}",
        "status": packet_status,
        "recommended_next": command,
        "primary_next_action": {
            "phase": "RECORD" if not decision_blocked else "EXECUTE",
            "command": command,
            "blockers": action_blockers,
            "confirm_required": False,
            "safe_to_auto_continue": False,
            "receipt_required": not decision_blocked,
            "token_omitted": True,
        },
        "blockers": action_blockers,
        "attention": ["record_before_execute"] if not decision_blocked else [],
        "evidence_contract": {
            "service_managed_loop": {
                "required": not decision_blocked,
                "status": "attention" if not decision_blocked else "not_applicable",
            },
            "token_omitted": True,
        },
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "copy_only": True,
            "token_omitted": True,
        },
        "token_omitted": True,
    }
    return {
        "provider": "agentops-operator",
        "operation": "operator_loop_supervision",
        "status": "record_first",
        "workspace_id": "local-demo",
        "adapters": [adapter],
        "summary": {
            "items": 1,
            "current_code_ok": True,
            "can_confirm_all": True,
            "record_required": not decision_blocked,
        },
        "items": [
            {
                "operation": "operator_loop_supervision_item",
                "adapter": adapter,
                "status": "record_first",
                "can_preview_loop": True,
                "can_confirm_bounded_loop": True,
                "should_record_before_execute": not decision_blocked,
                "ready_for_live_dispatch": True,
                "blockers": [],
                "attention": ["record_before_execute"] if not decision_blocked else [],
                "review_pressure": {"token_omitted": True},
                "agent_work_packet": packet,
                "gates": [
                    {"id": "bounded_confirm", "ok": True, "status": "pass", "confirm_required": True, "token_omitted": True},
                    {"id": "server_shell_boundary", "ok": True, "status": "pass", "server_executes_shell": False, "token_omitted": True},
                ],
                "commands": {
                    "recommended_next": command or "agentops operator loop-supervision --decision",
                    "preview_loop": f"agentops operator loop-driver --adapter {adapter} --max-steps 3",
                    "confirm_loop": f"agentops operator loop-driver --adapter {adapter} --max-steps 3 --confirm-loop",
                    "record_review": "agentops review queue --limit 20",
                },
                "next_commands": {
                    "safe_read_commands": [f"agentops operator start-check --adapter {adapter} --limit 8"],
                    "preview_commands": [f"agentops operator loop-driver --adapter {adapter} --max-steps 3"],
                    "confirm_required_commands": [f"agentops operator loop-driver --adapter {adapter} --max-steps 3 --confirm-loop"],
                    "recommended_next": command or "agentops operator loop-supervision --decision",
                    "token_omitted": True,
                },
                "safety": {
                    "read_only": True,
                    "ledger_mutated": False,
                    "live_execution_performed": False,
                    "server_executes_shell": False,
                    "token_omitted": True,
                },
                "token_omitted": True,
            }
        ],
        "work_packets": [packet],
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


def create_task_and_plan(conn, *, task_id: str, agent_id: str, runtime_type: str) -> str:
    server.ensure_gateway_agent(conn, agent_id, name=f"{runtime_type.title()} Decision Smoke", role="Decision Gate Smoke", runtime_type=runtime_type)
    now = server.now_iso()
    server.upsert_task(conn, {
        "task_id": task_id,
        "workspace_id": "local-demo",
        "title": f"{runtime_type} run-start work-packet decision smoke",
        "description": "Verify run_start consumes agent_work_packet_decision_v1 before live runtime run creation.",
        "requester_id": "usr_founder",
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": "[]",
        "status": "planned",
        "priority": "medium",
        "due_date": None,
        "acceptance_criteria": "No live run is created unless the work-packet decision gate passes.",
        "risk_level": "low",
        "budget_limit_usd": 1.0,
        "created_at": now,
        "updated_at": now,
    }, "run-start-work-packet-decision-smoke")
    payload, status = server.agent_gateway_create_agent_plan(conn, {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "task_id": task_id,
        "task_understanding": "Use loop supervision and work-packet decision before run_start.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["server.py"],
        "risk_level": "low",
        "approval_required": False,
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "verification_plan": "Run run_start_work_packet_decision_gate_smoke.py.",
        "rollback_plan": "Leave the task planned if work-packet decision blocks run_start.",
        "status": "submitted",
    })
    if status != 201:
        raise RuntimeError(f"agent plan create failed: {status} {payload}")
    plan_id = payload["agent_plan"]["plan_id"]
    verify, verify_status = server.verify_agent_plan(conn, plan_id)
    if verify_status != 200 or (verify.get("verification") or {}).get("pass") is not True:
        raise RuntimeError(f"agent plan verify failed: {verify_status} {verify}")
    return plan_id


def run_start(conn, *, task_id: str, agent_id: str, plan_id: str, runtime_type: str) -> tuple[dict, int]:
    return server.agent_gateway_start_run(conn, {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "task_id": task_id,
        "agent_plan_id": plan_id,
        "runtime_type": runtime_type,
        "input_summary": f"{runtime_type} run_start work-packet decision smoke.",
    })


def main() -> int:
    server.seed(reset=True)
    failures: list[str] = []
    outputs: list[str] = []
    original_operator_loop_supervision = server.operator_loop_supervision
    call_count = {"value": 0}
    try:
        with server.db() as conn:
            blocked_task = "tsk_run_start_decision_blocked"
            blocked_agent = "agt_run_start_decision_blocked"
            blocked_plan = create_task_and_plan(conn, task_id=blocked_task, agent_id=blocked_agent, runtime_type="hermes")

            def blocked_supervision(conn_arg, headers, qs=None, auth_ctx=None):
                call_count["value"] += 1
                return fake_supervision("hermes", decision_blocked=True)

            server.operator_loop_supervision = blocked_supervision
            blocked_payload, blocked_status = run_start(conn, task_id=blocked_task, agent_id=blocked_agent, plan_id=blocked_plan, runtime_type="hermes")
            outputs.append(json.dumps(blocked_payload, ensure_ascii=False))
            blocked_run_count = conn.execute("SELECT COUNT(*) c FROM runs WHERE task_id=?", (blocked_task,)).fetchone()["c"]
            blocked_audit_count = conn.execute(
                "SELECT COUNT(*) c FROM audit_logs WHERE entity_id=? AND action='agent_gateway.run_start_work_packet_decision_blocked'",
                (blocked_task,),
            ).fetchone()["c"]
            blocked_gate = blocked_payload.get("work_packet_decision_gate") or {}
            require(blocked_status == 428, f"Hermes blocked decision should reject run_start: {blocked_status} {blocked_payload}", failures)
            require(blocked_payload.get("error") == "run_start_work_packet_decision_blocked", f"wrong block error: {blocked_payload}", failures)
            require(blocked_payload.get("live_execution_performed") is False, f"blocked path must not execute live runtime: {blocked_payload}", failures)
            require(blocked_gate.get("operation") == "agent_gateway_run_start_work_packet_decision_gate", f"missing blocked decision gate: {blocked_payload}", failures)
            require(blocked_gate.get("ok") is False and blocked_gate.get("decision_kind") == "blocked", f"blocked decision not surfaced: {blocked_gate}", failures)
            require(bool(blocked_gate.get("decision_hash")), f"blocked gate missing decision_hash: {blocked_gate}", failures)
            require_gate_safety(blocked_gate, "blocked decision gate", failures)
            require(blocked_run_count == 0, f"blocked decision created a run for {blocked_task}", failures)
            require(blocked_audit_count >= 1, "blocked decision audit missing", failures)

            ready_task = "tsk_run_start_decision_ready"
            ready_agent = "agt_run_start_decision_ready"
            ready_plan = create_task_and_plan(conn, task_id=ready_task, agent_id=ready_agent, runtime_type="openclaw")

            def ready_supervision(conn_arg, headers, qs=None, auth_ctx=None):
                call_count["value"] += 1
                return fake_supervision("openclaw", decision_blocked=False)

            server.operator_loop_supervision = ready_supervision
            ready_payload, ready_status = run_start(conn, task_id=ready_task, agent_id=ready_agent, plan_id=ready_plan, runtime_type="openclaw")
            outputs.append(json.dumps(ready_payload, ensure_ascii=False))
            ready_gate = ready_payload.get("work_packet_decision_gate") or {}
            require(ready_status == 201, f"OpenClaw ready decision should allow run_start: {ready_status} {ready_payload}", failures)
            require(ready_gate.get("ok") is True and ready_gate.get("decision_kind") == "service_closure_first", f"ready decision gate should be attached: {ready_gate}", failures)
            require(bool(ready_gate.get("decision_hash")), f"ready gate missing decision_hash: {ready_gate}", failures)
            require_gate_safety(ready_gate, "ready decision gate", failures)
            require((ready_payload.get("agent_plan") or {}).get("work_packet_decision_hash") == ready_gate.get("decision_hash"), f"run_start response missing decision hash: {ready_payload}", failures)

            mock_task = "tsk_run_start_decision_mock"
            mock_agent = "agt_run_start_decision_mock"
            mock_plan = create_task_and_plan(conn, task_id=mock_task, agent_id=mock_agent, runtime_type="mock")

            def fail_if_mock_calls_supervision(conn_arg, headers, qs=None, auth_ctx=None):
                raise AssertionError("mock run_start should not read work-packet decisions")

            server.operator_loop_supervision = fail_if_mock_calls_supervision
            mock_payload, mock_status = run_start(conn, task_id=mock_task, agent_id=mock_agent, plan_id=mock_plan, runtime_type="mock")
            outputs.append(json.dumps(mock_payload, ensure_ascii=False))
            require(mock_status == 201, f"mock run_start should stay unaffected: {mock_status} {mock_payload}", failures)
            require("work_packet_decision_gate" not in mock_payload, f"mock response should not include decision gate: {mock_payload}", failures)
    finally:
        server.operator_loop_supervision = original_operator_loop_supervision
    serialized = "\n".join(outputs)
    require(not leaked(serialized), "run_start work-packet decision smoke leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "run_start_work_packet_decision_gate_smoke",
        "blocked_rejected": True,
        "ready_allowed": True,
        "mock_unaffected": True,
        "operator_loop_supervision_calls": call_count["value"],
        "secret_leaked": leaked(serialized),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
