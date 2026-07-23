#!/usr/bin/env python3
"""Compare selected repo_* write helpers on SQLite and Postgres."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.parity_fixture import snapshot_hash  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port, wait_for_adapter_connect  # noqa: E402


CONTRACT_ID = "postgres_write_helper_parity_v1"
WORKSPACE_A = "ws_pg_write_a"
WORKSPACE_B = "ws_pg_write_b"
AGENT_A = "agt_pg_write_a"
AGENT_B = "agt_pg_write_b"
TASK_A = "tsk_pg_write_a"
TASK_B = "tsk_pg_write_b"
RUN_A = "run_pg_write_a"
TOOL_CALL_A = "tc_pg_write_a"
APPROVAL_A = "ap_pg_write_a"
PREPARED_A = "pact_pg_write_a"
PREPARED_APPROVAL_CONFLICT = "pact_pg_write_approval_conflict"
EVAL_A = "eval_pg_write_a"
ARTIFACT_A = "art_pg_write_a"
MEMORY_A = "mem_pg_write_a"
RUNTIME_EVENT_A = "rte_pg_write_a"
AUDIT_A = "aud_pg_write_a"
AUDIT_CHAIN_A = "aud_pg_write_chain_a"
WORKFLOW_JOB_A = "wfjob_pg_write_a"
PLAN_A = "plan_pg_write_a"
MANIFEST_A = "pem_pg_write_a"
ROLLBACK_TASK = "tsk_pg_write_rollback"


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_WRITE_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_WRITE_PG_REEXEC"] = "1"
        os.execv(str(BUNDLED_PYTHON), [str(BUNDLED_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def unavailable(message: str, *, skip: bool) -> int:
    payload = {
        "ok": bool(skip),
        "skipped": bool(skip),
        "contract": CONTRACT_ID,
        "reason": message,
        "next_action": "Run again with Docker and optional psycopg available; skipped mode is diagnostic only.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if skip else 1


class DeterministicClock:
    def __init__(self):
        self.index = 0
        self.base = dt.datetime(2026, 6, 22, 4, 0, 0, tzinfo=dt.timezone.utc)

    def __call__(self) -> str:
        value = self.base + dt.timedelta(seconds=self.index)
        self.index += 1
        return value.isoformat()


@contextmanager
def deterministic_server_clock():
    original = server.now_iso
    server.now_iso = DeterministicClock()
    try:
        yield
    finally:
        server.now_iso = original


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def normalize(value):
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, tuple):
        return [normalize(item) for item in value]
    return value


def row_dict(row) -> dict:
    return normalize(dict(row))


def seed_reference_rows(conn) -> None:
    now = "2026-06-22T03:59:00+00:00"
    conn.execute(
        "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
        ("usr_founder", "Founder", "founder@example.local", "founder", now),
    )
    for agent_id, workspace_id in [(AGENT_A, WORKSPACE_A), (AGENT_B, WORKSPACE_B)]:
        conn.execute(
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""",
            {
                "agent_id": agent_id,
                "name": f"Postgres Write {workspace_id}",
                "role": "operator",
                "description": "Write-helper parity agent.",
                "runtime_type": "mock",
                "model_provider": "mock",
                "model_name": "mock-model",
                "status": "idle",
                "permission_level": "standard",
                "allowed_tools": "[]",
                "budget_limit_usd": 0,
                "owner_user_id": "usr_founder",
                "created_at": now,
                "updated_at": now,
            },
        )
    conn.execute(
        """INSERT INTO runtime_connectors(runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,require_confirm_run,trust_status,trust_note,trust_updated_at,last_health_at,last_error,created_at,updated_at)
        VALUES(:runtime_connector_id,:provider,:connector_type,:profile_name,:base_url,:binary_path,:status,:allow_real_run,:require_confirm_run,:trust_status,:trust_note,:trust_updated_at,:last_health_at,:last_error,:created_at,:updated_at)""",
        {
            "runtime_connector_id": "rtc_pg_write",
            "provider": "agent-gateway",
            "connector_type": "mock",
            "profile_name": "write-helper parity",
            "base_url": None,
            "binary_path": None,
            "status": "healthy",
            "allow_real_run": 0,
            "require_confirm_run": 1,
            "trust_status": "trusted",
            "trust_note": "Temporary write-helper parity connector.",
            "trust_updated_at": now,
            "last_health_at": now,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
    )


def run_write_helpers(conn) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    with deterministic_server_clock():
        now = server.now_iso()
        task_b = {
            "task_id": TASK_B,
            "workspace_id": WORKSPACE_B,
            "title": "Postgres write helper task B",
            "description": "Cross-workspace control row.",
            "requester_id": "usr_founder",
            "owner_agent_id": AGENT_B,
            "collaborator_agent_ids": "[]",
            "status": "planned",
            "priority": "medium",
            "due_date": None,
            "acceptance_criteria": "Must remain outside workspace A snapshot.",
            "risk_level": "low",
            "budget_limit_usd": 0,
            "created_at": now,
            "updated_at": now,
        }
        _before, outcomes["repo_upsert_task_b"] = server.repo_upsert_task(conn, dict(task_b))

        task_a = {
            "task_id": TASK_A,
            "workspace_id": WORKSPACE_A,
            "title": "Postgres write helper task A",
            "description": "Created through repo_upsert_task.",
            "requester_id": "usr_founder",
            "owner_agent_id": AGENT_A,
            "collaborator_agent_ids": "[]",
            "status": "planned",
            "priority": "medium",
            "due_date": None,
            "acceptance_criteria": "Postgres write helpers must match SQLite.",
            "risk_level": "low",
            "budget_limit_usd": 1.0,
            "created_at": now,
            "updated_at": now,
        }
        before, outcomes["repo_upsert_task_create"] = server.repo_upsert_task(conn, dict(task_a))
        require(before is None and outcomes["repo_upsert_task_create"] == "created", "task create outcome mismatch")
        task_a["status"] = "running"
        task_a["updated_at"] = server.now_iso()
        before, outcomes["repo_upsert_task_update"] = server.repo_upsert_task(conn, dict(task_a))
        require(before and outcomes["repo_upsert_task_update"] == "updated", "task update outcome mismatch")

        run_a = {
            "run_id": RUN_A,
            "workspace_id": WORKSPACE_A,
            "task_id": TASK_A,
            "agent_id": AGENT_A,
            "runtime_type": "mock",
            "status": "running",
            "started_at": now,
            "ended_at": None,
            "duration_ms": None,
            "input_summary": "Write-helper parity run.",
            "output_summary": None,
            "model_provider": "mock",
            "model_name": "mock-model",
            "input_tokens": 1,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "cost_usd": 0,
            "error_type": None,
            "error_message": None,
            "trace_id": "trace_pg_write_a",
            "parent_run_id": None,
            "delegation_id": "del_pg_write_a",
            "approval_required": 0,
            "created_at": now,
        }
        before, outcomes["repo_upsert_run_create"] = server.repo_upsert_run(conn, dict(run_a))
        require(before is None and outcomes["repo_upsert_run_create"] == "created", "run create outcome mismatch")
        run_a.update({"status": "completed", "ended_at": server.now_iso(), "duration_ms": 7, "output_summary": "Write-helper parity run completed."})
        before, outcomes["repo_upsert_run_update"] = server.repo_upsert_run(conn, dict(run_a))
        require(before and outcomes["repo_upsert_run_update"] == "updated", "run update outcome mismatch")

        tool_a = {
            "tool_call_id": TOOL_CALL_A,
            "run_id": RUN_A,
            "agent_id": AGENT_A,
            "tool_name": "storage.postgres_write_helper",
            "tool_version": "v1",
            "tool_category": "database",
            "normalized_args_json": dumps({"raw_omitted": True, "workspace_id": WORKSPACE_A}),
            "target_resource": "postgres://write-helper",
            "risk_level": "low",
            "status": "waiting_approval",
            "result_summary": "Write-helper tool call.",
            "side_effect_id": None,
            "started_at": now,
            "ended_at": now,
            "created_at": now,
        }
        before, outcomes["repo_upsert_tool_call_create"] = server.repo_upsert_tool_call(conn, dict(tool_a))
        require(before is None and outcomes["repo_upsert_tool_call_create"] == "created", "tool create outcome mismatch")
        tool_a["result_summary"] = "Write-helper tool call updated."
        before, outcomes["repo_upsert_tool_call_update"] = server.repo_upsert_tool_call(conn, dict(tool_a))
        require(before and outcomes["repo_upsert_tool_call_update"] == "updated", "tool update outcome mismatch")
        _before, after, outcomes["repo_update_tool_call_status"] = server.repo_update_tool_call_status(conn, TOOL_CALL_A, "completed")
        require(after and after["status"] == "completed", "tool status update mismatch")

        runtime_event = {
            "runtime_event_id": RUNTIME_EVENT_A,
            "runtime_connector_id": "rtc_pg_write",
            "event_type": "storage.postgres_write_helper",
            "status": "completed",
            "run_id": RUN_A,
            "task_id": TASK_A,
            "agent_id": AGENT_A,
            "model_name": "mock-model",
            "latency_ms": 1,
            "prompt_hash": "prompt_hash_pg_write",
            "input_summary": "Write-helper runtime event.",
            "output_summary": "Write-helper runtime event stored.",
            "error_message": None,
            "raw_payload_hash": "payload_hash_pg_write",
            "created_at": now,
        }
        server.repo_insert_runtime_event(conn, dict(runtime_event))
        outcomes["repo_insert_runtime_event"] = "created"

        audit_row = {
            "audit_id": AUDIT_A,
            "actor_type": "system",
            "actor_id": "postgres-write-helper-smoke",
            "action": "storage.postgres_write_helper",
            "entity_type": "tasks",
            "entity_id": TASK_A,
            "before_hash": None,
            "after_hash": server.stable_hash({"task_id": TASK_A, "status": "completed"}),
            "created_at": now,
        }
        server.repo_insert_audit_log(conn, dict(audit_row), {"workspace_id": WORKSPACE_A, "raw_omitted": True})
        chained_audit_row = {
            "audit_id": AUDIT_CHAIN_A,
            "actor_type": "system",
            "actor_id": "postgres-write-helper-smoke",
            "action": "storage.postgres_write_helper_chain",
            "entity_type": "runs",
            "entity_id": RUN_A,
            "before_hash": server.stable_hash({"run_id": RUN_A, "status": "running"}),
            "after_hash": server.stable_hash({"run_id": RUN_A, "status": "completed"}),
            "created_at": server.now_iso(),
        }
        server.repo_insert_audit_log(conn, dict(chained_audit_row), {"workspace_id": WORKSPACE_A, "previous_expected": AUDIT_A})
        outcomes["repo_insert_audit_log"] = "created_chained"

        approval_a = {
            "approval_id": APPROVAL_A,
            "approval_kind": "prepared_action",
            "task_id": TASK_A,
            "run_id": RUN_A,
            "tool_call_id": TOOL_CALL_A,
            "requested_by_agent_id": AGENT_A,
            "approver_user_id": "usr_founder",
            "decision": "pending",
            "reason": "Write-helper approval.",
            "expires_at": server.now_iso(),
            "created_at": now,
            "decided_at": None,
        }
        before, outcomes["repo_upsert_approval_create"] = server.repo_upsert_approval(conn, dict(approval_a))
        require(before is None and outcomes["repo_upsert_approval_create"] == "created", "approval create outcome mismatch")

        prepared_a = {
            "prepared_action_id": PREPARED_A,
            "workspace_id": WORKSPACE_A,
            "task_id": TASK_A,
            "run_id": RUN_A,
            "tool_call_id": TOOL_CALL_A,
            "approval_id": APPROVAL_A,
            "requested_by_agent_id": AGENT_A,
            "action_type": "external_write_exact_resume",
            "provider": "postgres-write-helper",
            "target_resource": "external://postgres-write-helper/a",
            "normalized_args_json": dumps({"document_hash": "doc_hash_pg_write", "raw_omitted": True}),
            "args_hash": None,
            "snapshot_ref": "snapshot://postgres-write-helper/a",
            "snapshot_hash": "snapshot_hash_pg_write",
            "status": "waiting_approval",
            "result_json": "{}",
            "created_at": now,
            "updated_at": now,
            "approved_at": None,
            "consumed_at": None,
        }
        before, outcomes["repo_upsert_prepared_action_create"] = server.repo_upsert_prepared_action(conn, dict(prepared_a))
        require(before is None and outcomes["repo_upsert_prepared_action_create"] == "created", "prepared create outcome mismatch")
        _before, after, outcomes["repo_update_approval_decision"] = server.repo_update_approval_decision(
            conn,
            APPROVAL_A,
            "approved",
            "Write-helper approval decided.",
            decided_at=server.now_iso(),
        )
        require(after and after["decision"] == "approved", "approval decision update mismatch")
        approval_conflict = dict(prepared_a)
        approval_conflict["prepared_action_id"] = PREPARED_APPROVAL_CONFLICT
        try:
            server.repo_upsert_prepared_action(conn, approval_conflict)
        except server.PreparedActionImmutableConflict as exc:
            outcomes["repo_upsert_prepared_action_approval_conflict"] = str(exc)
        require(
            outcomes.get("repo_upsert_prepared_action_approval_conflict") == "prepared_action_approval_binding_conflict",
            "prepared approval reuse was not rejected",
        )
        prepared_a["snapshot_hash"] = "snapshot_hash_pg_write_updated"
        prepared_a["updated_at"] = server.now_iso()
        try:
            server.repo_upsert_prepared_action(conn, dict(prepared_a))
        except server.PreparedActionImmutableConflict as exc:
            outcomes["repo_upsert_prepared_action_immutable_conflict"] = str(exc)
        require(
            outcomes.get("repo_upsert_prepared_action_immutable_conflict") == "prepared_action_immutable_binding_conflict",
            "prepared immutable binding update was not rejected",
        )
        _before, after, outcomes["repo_update_prepared_action_approved"] = server.repo_update_prepared_action_status(conn, PREPARED_A, "approved")
        require(after and after["status"] == "approved", "prepared approve update mismatch")
        _before, after, outcomes["repo_update_prepared_action_consumed"] = server.repo_update_prepared_action_status(
            conn,
            PREPARED_A,
            "consumed",
            result_json={"provider_object_id": "external_pg_write", "raw_omitted": True},
        )
        require(after and after["status"] == "consumed", "prepared consume update mismatch")

        evaluation_a = {
            "evaluation_id": EVAL_A,
            "task_id": TASK_A,
            "run_id": RUN_A,
            "agent_id": AGENT_A,
            "evaluator_type": "rule",
            "score": 0.8,
            "pass_fail": "pass",
            "rubric_json": dumps({"postgres_write_helper": True}),
            "notes": "Write-helper evaluation.",
            "created_at": now,
        }
        before, outcomes["repo_upsert_evaluation_create"] = server.repo_upsert_evaluation(conn, dict(evaluation_a))
        require(before is None and outcomes["repo_upsert_evaluation_create"] == "created", "evaluation create outcome mismatch")
        evaluation_a.update({"score": 0.93, "notes": "Write-helper evaluation updated."})
        before, outcomes["repo_upsert_evaluation_update"] = server.repo_upsert_evaluation(conn, dict(evaluation_a))
        require(before and outcomes["repo_upsert_evaluation_update"] == "updated", "evaluation update outcome mismatch")

        artifact_a = {
            "artifact_id": ARTIFACT_A,
            "task_id": TASK_A,
            "run_id": RUN_A,
            "artifact_type": "markdown",
            "title": "Postgres Write Helper Artifact",
            "uri": "artifact://postgres-write-helper/a",
            "summary": "Write-helper artifact.",
            "created_at": now,
        }
        before, outcomes["repo_upsert_artifact_create"] = server.repo_upsert_artifact(conn, dict(artifact_a))
        require(before is None and outcomes["repo_upsert_artifact_create"] == "created", "artifact create outcome mismatch")
        artifact_a["summary"] = "Write-helper artifact updated."
        before, outcomes["repo_upsert_artifact_update"] = server.repo_upsert_artifact(conn, dict(artifact_a))
        require(before and outcomes["repo_upsert_artifact_update"] == "updated", "artifact update outcome mismatch")

        memory_a = {
            "memory_id": MEMORY_A,
            "workspace_id": WORKSPACE_A,
            "scope": "task",
            "memory_type": "artifact_summary",
            "canonical_text": "Write-helper memory.",
            "source_type": "run_log",
            "source_ref": RUN_A,
            "project_id": "proj_pg_write",
            "task_id": TASK_A,
            "agent_id": AGENT_A,
            "confidence": 0.77,
            "review_status": "candidate",
            "owner_user_id": "usr_founder",
            "ttl_review_due_at": server.now_iso(),
            "supersedes_memory_id": None,
            "access_tags": dumps(["postgres-write-helper"]),
            "created_at": now,
            "updated_at": now,
        }
        before, outcomes["repo_upsert_memory_candidate_create"] = server.repo_upsert_memory_candidate(conn, dict(memory_a))
        require(before is None and outcomes["repo_upsert_memory_candidate_create"] == "created", "memory create outcome mismatch")
        memory_a.update({"canonical_text": "Write-helper memory updated.", "confidence": 0.91, "updated_at": server.now_iso()})
        before, outcomes["repo_upsert_memory_candidate_update"] = server.repo_upsert_memory_candidate(conn, dict(memory_a))
        require(before and outcomes["repo_upsert_memory_candidate_update"] == "updated", "memory update outcome mismatch")
        _before, after, outcomes["repo_update_memory_review_status"] = server.repo_update_memory_review_status(
            conn,
            MEMORY_A,
            "approved",
            updated_at=server.now_iso(),
        )
        require(after and after["review_status"] == "approved", "memory review update mismatch")

        workflow_job_a = {
            "job_id": WORKFLOW_JOB_A,
            "workspace_id": WORKSPACE_A,
            "workflow_type": "customer_worker_task",
            "status": "queued",
            "template_id": None,
            "adapter": "mock",
            "confirm_run": 0,
            "title": "Write-helper workflow job",
            "input_summary": "No raw prompt stored.",
            "request_hash": "request_hash_pg_write",
            "result_json": "{}",
            "result_task_id": TASK_A,
            "result_run_id": RUN_A,
            "result_artifact_id": ARTIFACT_A,
            "error_message": None,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "updated_at": now,
        }
        before, outcomes["repo_upsert_workflow_job_create"] = server.repo_upsert_workflow_job(conn, dict(workflow_job_a))
        require(before is None and outcomes["repo_upsert_workflow_job_create"] == "created", "workflow create outcome mismatch")
        _before, after, outcomes["repo_update_workflow_job"] = server.repo_update_workflow_job(
            conn,
            WORKFLOW_JOB_A,
            {"status": "completed", "completed_at": server.now_iso(), "updated_at": server.now_iso(), "result_json": dumps({"ok": True})},
        )
        require(after and after["status"] == "completed", "workflow update mismatch")

        plan_a = {
            "plan_id": PLAN_A,
            "workspace_id": WORKSPACE_A,
            "task_id": TASK_A,
            "run_id": RUN_A,
            "agent_id": AGENT_A,
            "task_understanding": "Postgres write helper parity plan.",
            "referenced_specs_json": dumps(["docs/STORAGE_BOUNDARY_MAP.md", "docs/POSTGRES_PARITY_CONTRACT.md"]),
            "referenced_memories_json": dumps([MEMORY_A]),
            "referenced_bases_json": dumps(["base_local_tasks"]),
            "proposed_files_to_change_json": dumps(["scripts/storage_postgres_write_helper_parity_smoke.py"]),
            "risk_level": "medium",
            "approval_required": 0,
            "execution_steps_json": dumps(["write", "compare", "record"]),
            "verification_plan": "Run Postgres write helper parity smoke.",
            "rollback_plan": "Drop temporary databases.",
            "status": "submitted",
            "created_at": now,
            "updated_at": now,
        }
        before, outcomes["repo_upsert_agent_plan_create"] = server.repo_upsert_agent_plan(conn, dict(plan_a))
        require(before is None and outcomes["repo_upsert_agent_plan_create"] == "created", "plan create outcome mismatch")
        plan_a.update({"verification_plan": "Run Postgres write helper parity smoke and compare hashes.", "updated_at": server.now_iso()})
        before, outcomes["repo_upsert_agent_plan_update"] = server.repo_upsert_agent_plan(conn, dict(plan_a))
        require(before and outcomes["repo_upsert_agent_plan_update"] == "updated", "plan update outcome mismatch")

        manifest_a = {
            "manifest_id": MANIFEST_A,
            "workspace_id": WORKSPACE_A,
            "plan_id": PLAN_A,
            "task_id": TASK_A,
            "run_id": RUN_A,
            "agent_id": AGENT_A,
            "mismatch_policy": "block",
            "expected_steps_json": dumps(["write", "compare", "record"]),
            "tool_call_ids_json": dumps([TOOL_CALL_A]),
            "evaluation_ids_json": dumps([EVAL_A]),
            "artifact_ids_json": dumps([ARTIFACT_A]),
            "audit_ids_json": dumps([AUDIT_A]),
            "status": "submitted",
            "verification_json": "{}",
            "created_at": now,
            "updated_at": now,
        }
        before, outcomes["repo_upsert_plan_evidence_manifest_create"] = server.repo_upsert_plan_evidence_manifest(conn, dict(manifest_a))
        require(before is None and outcomes["repo_upsert_plan_evidence_manifest_create"] == "created", "manifest create outcome mismatch")
        verification = server.verify_plan_evidence_manifest_row(conn, conn.execute("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", (MANIFEST_A,)).fetchone())
        require(verification["status"] == "verified", f"manifest verification failed: {verification}")
        _before, after, outcomes["repo_update_plan_evidence_manifest"] = server.repo_update_plan_evidence_manifest(
            conn,
            MANIFEST_A,
            {"status": verification["status"], "verification_json": dumps(verification), "updated_at": server.now_iso()},
        )
        require(after and after["status"] == "verified", "manifest update mismatch")
    return outcomes


def verify_postgres_approval_kind_required(conn) -> bool:
    row = {
        "approval_id": "ap_pg_write_missing_kind",
        "task_id": TASK_A,
        "run_id": RUN_A,
        "tool_call_id": None,
        "requested_by_agent_id": AGENT_A,
        "approver_user_id": "usr_founder",
        "decision": "pending",
        "reason": "Missing approval kind must fail before Postgres SQL.",
        "expires_at": None,
        "created_at": "2026-06-22T04:00:00+00:00",
        "decided_at": None,
    }
    try:
        server.repo_upsert_approval(conn, row)
    except server.ApprovalImmutableConflict as exc:
        require(str(exc) == "approval_kind_required", f"unexpected approval kind error: {exc}")
        return True
    raise AssertionError("Postgres approval helper inferred a missing approval_kind")


SNAPSHOT_QUERIES = {
    "users": ("SELECT user_id,email,role FROM users WHERE user_id='usr_founder' ORDER BY user_id", None),
    "tasks": ("SELECT task_id,workspace_id,title,status,budget_limit_usd,updated_at FROM tasks WHERE task_id IN (?,?) ORDER BY task_id", [TASK_A, TASK_B]),
    "runs": ("SELECT run_id,workspace_id,task_id,agent_id,status,duration_ms,output_summary FROM runs WHERE run_id=? ORDER BY run_id", [RUN_A]),
    "tool_calls": ("SELECT tool_call_id,run_id,agent_id,status,result_summary FROM tool_calls WHERE tool_call_id=? ORDER BY tool_call_id", [TOOL_CALL_A]),
    "runtime_events": ("SELECT runtime_event_id,runtime_connector_id,event_type,status,run_id,task_id,agent_id,raw_payload_hash FROM runtime_events WHERE runtime_event_id=? ORDER BY runtime_event_id", [RUNTIME_EVENT_A]),
    "audit_logs": ("SELECT audit_id,action,entity_type,entity_id,metadata_json,tamper_chain_hash FROM audit_logs WHERE audit_id IN (?,?) ORDER BY audit_id", [AUDIT_A, AUDIT_CHAIN_A]),
    "approvals": ("SELECT approval_id,decision,reason,decided_at FROM approvals WHERE approval_id=? ORDER BY approval_id", [APPROVAL_A]),
    "prepared_actions": ("SELECT prepared_action_id,workspace_id,status,args_hash,snapshot_hash,result_json,approved_at,consumed_at FROM prepared_actions WHERE prepared_action_id=? ORDER BY prepared_action_id", [PREPARED_A]),
    "evaluations": ("SELECT evaluation_id,score,pass_fail,notes FROM evaluations WHERE evaluation_id=? ORDER BY evaluation_id", [EVAL_A]),
    "artifacts": ("SELECT artifact_id,artifact_type,title,uri,summary FROM artifacts WHERE artifact_id=? ORDER BY artifact_id", [ARTIFACT_A]),
    "memories": ("SELECT memory_id,workspace_id,canonical_text,confidence,review_status,updated_at FROM memories WHERE memory_id=? ORDER BY memory_id", [MEMORY_A]),
    "workflow_jobs": ("SELECT job_id,workspace_id,status,result_json,completed_at,updated_at FROM workflow_jobs WHERE job_id=? ORDER BY job_id", [WORKFLOW_JOB_A]),
    "agent_plans": ("SELECT plan_id,workspace_id,task_id,run_id,agent_id,status,verification_plan,updated_at FROM agent_plans WHERE plan_id=? ORDER BY plan_id", [PLAN_A]),
    "plan_evidence_manifests": ("SELECT manifest_id,workspace_id,plan_id,run_id,status,verification_json,updated_at FROM plan_evidence_manifests WHERE manifest_id=? ORDER BY manifest_id", [MANIFEST_A]),
    "workspace_a_prepared_ids": ("SELECT prepared_action_id FROM prepared_actions WHERE workspace_id=? ORDER BY prepared_action_id", [WORKSPACE_A]),
    "cross_workspace_task_exclusion": ("SELECT task_id FROM tasks WHERE workspace_id=? AND task_id=? ORDER BY task_id", [WORKSPACE_A, TASK_B]),
}


def snapshot(conn) -> dict[str, Any]:
    data = {}
    for name, (sql, params) in SNAPSHOT_QUERIES.items():
        rows = conn.execute(sql, params or []).fetchall()
        data[name] = [row_dict(row) for row in rows]
    return normalize(data)


def run_rollback_sentinel(conn) -> str:
    now = "2026-06-22T04:30:00+00:00"
    task = {
        "task_id": ROLLBACK_TASK,
        "workspace_id": WORKSPACE_A,
        "title": "Rollback sentinel task",
        "description": "This row must not survive rollback.",
        "requester_id": "usr_founder",
        "owner_agent_id": AGENT_A,
        "collaborator_agent_ids": "[]",
        "status": "planned",
        "priority": "medium",
        "due_date": None,
        "acceptance_criteria": "Rollback must remove this task.",
        "risk_level": "low",
        "budget_limit_usd": 0,
        "created_at": now,
        "updated_at": now,
    }
    _before, outcome = server.repo_upsert_task(conn, dict(task))
    require(outcome == "created", "rollback sentinel create failed")
    conn.rollback()
    row = conn.execute("SELECT task_id FROM tasks WHERE task_id=?", (ROLLBACK_TASK,)).fetchone()
    require(not row, "rollback sentinel survived rollback")
    return "rolled_back"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_postgres_legacy_prepared_action_migration(conn) -> dict:
    status_constraints = conn.execute(
        """SELECT con.conname, pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid=con.conrelid
        WHERE rel.oid=to_regclass('prepared_actions')
          AND con.contype='c'
        ORDER BY con.conname"""
    ).fetchall()
    for row in status_constraints:
        if "status" not in str(row["definition"] or "").lower():
            continue
        name = str(row["conname"]).replace('"', '""')
        conn.execute(f'ALTER TABLE prepared_actions DROP CONSTRAINT "{name}"')
    conn.execute(
        """ALTER TABLE prepared_actions
        ADD CONSTRAINT prepared_actions_status_legacy_check
        CHECK(status IN ('prepared','waiting_approval','approved','rejected','consumed','expired','canceled'))"""
    )
    conn.execute("DROP INDEX IF EXISTS idx_prepared_actions_approval_unique")
    conn.commit()

    first = server.ensure_postgres_prepared_action_lifecycle_schema(conn)
    conn.commit()
    second = server.ensure_postgres_prepared_action_lifecycle_schema(conn)
    conn.commit()
    migrated = conn.execute(
        """SELECT pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid=con.conrelid
        WHERE rel.oid=to_regclass('prepared_actions')
          AND con.contype='c'
          AND pg_get_constraintdef(con.oid) LIKE '%status%'"""
    ).fetchall()
    unique_index = conn.execute(
        """SELECT 1
        FROM pg_indexes
        WHERE tablename='prepared_actions'
          AND indexname='idx_prepared_actions_approval_unique'"""
    ).fetchone()
    definitions = [str(row["definition"] or "").lower() for row in migrated]
    require(first.get("check_migrated") is True, f"legacy Postgres CHECK was not migrated: {first}")
    require(second.get("check_migrated") is False, f"Postgres lifecycle migration was not idempotent: {second}")
    require(definitions and all("executing" in item and "failed" in item for item in definitions), f"Postgres lifecycle CHECK is incomplete: {definitions}")
    require(bool(unique_index), "Postgres approval unique index was not recreated after lifecycle migration")
    return {
        "legacy_check_migrated": True,
        "idempotent": True,
        "approval_index_ensured": True,
    }


def verify_postgres_stale_prepared_action_reconciliation(conn, dsn: str) -> dict:
    old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()

    def insert_stale(action_id: str) -> None:
        conn.execute(
            """INSERT INTO prepared_actions(
            prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,requested_by_agent_id,
            action_type,provider,target_resource,normalized_args_json,args_hash,snapshot_ref,snapshot_hash,status,
            result_json,created_at,updated_at,approved_at,consumed_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                action_id, WORKSPACE_A, TASK_A, RUN_A, TOOL_CALL_A, None, AGENT_A,
                "postgres.stale_reconciliation", "postgres-smoke", "postgres://stale-reconciliation",
                "{}", server.prepared_action_args_hash("{}"), None, "stale_snapshot", "executing",
                "{}", old, old, old, None,
            ),
        )

    runtime_events_before = conn.execute("SELECT COUNT(*) AS count FROM runtime_events").fetchone()["count"]
    read_action_id = "pact_pg_stale_read_side"
    insert_stale(read_action_id)
    conn.commit()
    rows = server.repo_list_workspace_prepared_actions(conn, WORKSPACE_A)
    read_failed = next((row for row in rows if row["prepared_action_id"] == read_action_id), None)
    read_result = json.loads(read_failed["result_json"] or "{}") if read_failed else {}
    require(
        read_failed
        and read_failed["status"] == "failed"
        and read_result.get("outcome") == "unknown"
        and read_result.get("automatic_retry_performed") is False,
        f"Postgres read-side stale reconciliation failed: {read_result}",
    )
    conn.commit()

    startup_action_id = "pact_pg_stale_startup"
    insert_stale(startup_action_id)
    conn.commit()
    original_backend = server.STORAGE_BACKEND
    startup_env = {
        "AGENTOPS_STORAGE_BACKEND": "postgres",
        "AGENTOPS_POSTGRES_DSN": dsn,
        "AGENTOPS_ENABLE_POSTGRES_STORAGE": "1",
        "AGENTOPS_POSTGRES_READ_ONLY_HTTP": "1",
        "AGENTOPS_EDITION": "enterprise_byoc",
    }
    original_env = {key: os.environ.get(key) for key in startup_env}
    try:
        server.STORAGE_BACKEND = "postgres"
        os.environ.update(startup_env)
        startup = server.run_prepared_action_startup_lifecycle()
    finally:
        server.STORAGE_BACKEND = original_backend
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    startup_failed = conn.execute(
        "SELECT status,result_json FROM prepared_actions WHERE prepared_action_id=?",
        (startup_action_id,),
    ).fetchone()
    startup_result = json.loads(startup_failed["result_json"] or "{}") if startup_failed else {}
    runtime_events_after = conn.execute("SELECT COUNT(*) AS count FROM runtime_events").fetchone()["count"]
    require(
        startup.get("stale_executing_reconciled") == 1
        and startup_failed
        and startup_failed["status"] == "failed"
        and startup_result.get("outcome") == "unknown"
        and startup_result.get("automatic_retry_performed") is False,
        f"Postgres startup stale reconciliation failed: {startup} {startup_result}",
    )
    require(runtime_events_after == runtime_events_before, "Postgres stale reconciliation emitted provider runtime events")
    return {
        "read_side_failed_outcome_unknown": True,
        "startup_failed_outcome_unknown": True,
        "automatic_provider_retry_performed": False,
    }


def run_sqlite() -> tuple[dict[str, str], dict[str, Any]]:
    handle = tempfile.NamedTemporaryFile(prefix="agentops-write-helper-sqlite-", delete=False)
    db_path = handle.name
    handle.close()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(server.SCHEMA_SQL)
            server.ensure_schema_migrations(conn)
            seed_reference_rows(conn)
            outcomes = run_write_helpers(conn)
            conn.commit()
            rollback_sentinel = run_rollback_sentinel(conn)
            return outcomes, snapshot(conn)
        finally:
            conn.close()
    finally:
        Path(db_path).unlink(missing_ok=True)


def run_postgres(*, image: str, skip: bool, install_driver: bool) -> tuple[int | None, dict[str, Any] | None]:
    early = container_smoke.docker_available(skip)
    if early is not None:
        return early, None
    early = container_smoke.ensure_image(image, skip)
    if early is not None:
        return early, None

    with tempfile.TemporaryDirectory(prefix="agentops-write-helper-pg-") as temp_dir:
        driver_ok, driver_status = ensure_psycopg(Path(temp_dir), install=install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=skip), None

        container = f"agentops-pg-write-helper-{container_smoke.secrets.token_hex(6)}"
        pg_auth = container_smoke.secrets.token_urlsafe(18)
        started = container_smoke.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                container,
                "-p",
                "127.0.0.1::5432",
                "-e",
                "POSTGRES_USER=agentops",
                "-e",
                "POSTGRES_DB=agentops",
                "-e",
                f"POSTGRES_PASSWORD={pg_auth}",
                image,
            ],
            timeout=60,
        )
        if started.returncode != 0:
            detail = (started.stderr or started.stdout or "docker run failed").strip().replace(pg_auth, "[REDACTED]")
            return unavailable(f"Postgres container failed to start: {detail}", skip=skip), None

        adapter: PostgresAdapter | None = None
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=skip), None
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = wait_for_adapter_connect(dsn)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            lifecycle_migration = verify_postgres_legacy_prepared_action_migration(adapter)
            seed_reference_rows(adapter)
            approval_kind_required = verify_postgres_approval_kind_required(adapter)
            outcomes = run_write_helpers(adapter)
            adapter.commit()
            rollback_sentinel = run_rollback_sentinel(adapter)
            postgres_snapshot = snapshot(adapter)
            stale_reconciliation = verify_postgres_stale_prepared_action_reconciliation(adapter, dsn)
            return None, {
                "driver_status": driver_status,
                "outcomes": outcomes,
                "snapshot": postgres_snapshot,
                "rollback_sentinel": rollback_sentinel,
                "lifecycle_migration": lifecycle_migration,
                "stale_reconciliation": stale_reconciliation,
                "approval_kind_required": approval_kind_required,
            }
        except (AssertionError, PostgresAdapterUnavailable, RuntimeError, ValueError, KeyError) as exc:
            if adapter is not None:
                adapter.rollback()
            return unavailable(str(exc).replace(pg_auth, "[REDACTED]"), skip=skip), None
        finally:
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SQLite/Postgres repo_* write helper parity smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE, help="Postgres Docker image to use.")
    parser.add_argument("--skip-if-unavailable", action="store_true", help="Return success with skipped=true when Docker or psycopg is unavailable.")
    parser.add_argument("--no-install-driver", action="store_true", help="Do not install psycopg into a temporary target when missing.")
    args = parser.parse_args()

    reexec_self_with_bundled_python_if_needed()

    sqlite_outcomes, sqlite_snapshot = run_sqlite()
    early, postgres_result = run_postgres(image=args.image, skip=args.skip_if_unavailable, install_driver=not args.no_install_driver)
    if early is not None:
        return early
    assert postgres_result is not None
    postgres_outcomes = postgres_result["outcomes"]
    postgres_snapshot = postgres_result["snapshot"]
    rollback_sentinel = postgres_result["rollback_sentinel"]
    sqlite_digest = snapshot_hash({"outcomes": sqlite_outcomes, "rollback_sentinel": "rolled_back", "snapshot": sqlite_snapshot})
    postgres_digest = snapshot_hash({"outcomes": postgres_outcomes, "rollback_sentinel": rollback_sentinel, "snapshot": postgres_snapshot})
    failures: list[str] = []
    if sqlite_outcomes != postgres_outcomes:
        failures.append("sqlite_postgres_write_outcome_mismatch")
    if sqlite_snapshot != postgres_snapshot:
        failures.append("sqlite_postgres_write_snapshot_mismatch")
    if sqlite_digest != postgres_digest:
        failures.append("sqlite_postgres_write_hash_mismatch")
    output = {
        "ok": not failures,
        "skipped": False,
        "contract": CONTRACT_ID,
        "image": args.image,
        "driver_status": postgres_result["driver_status"],
        "helper_count": len(sqlite_outcomes),
        "helpers": sorted(sqlite_outcomes.keys()),
        "snapshot_sections": list(sqlite_snapshot.keys()),
        "rollback_sentinel": rollback_sentinel,
        "postgres_legacy_lifecycle_migration": postgres_result["lifecycle_migration"],
        "postgres_stale_reconciliation": postgres_result["stale_reconciliation"],
        "postgres_approval_kind_required": postgres_result["approval_kind_required"],
        "sqlite_write_helper_hash": sqlite_digest,
        "postgres_write_helper_hash": postgres_digest,
        "free_local_dependencies": [],
        "fallback_performed": False,
        "writes_enabled_for_http": False,
        "failures": failures,
        "next_proof": "Route a small, explicit Postgres write adapter path only after write helpers and fail-closed guards stay green.",
    }
    if failures:
        output["sqlite_outcomes"] = sqlite_outcomes
        output["postgres_outcomes"] = postgres_outcomes
        output["sqlite_snapshot"] = sqlite_snapshot
        output["postgres_snapshot"] = postgres_snapshot
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
