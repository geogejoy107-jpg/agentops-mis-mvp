#!/usr/bin/env python3
"""Prove one explicit Postgres-backed HTTP write route."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402
from storage_postgres_http_read_parity_smoke import (  # noqa: E402
    connect_postgres_when_ready,
    free_port,
    request_json,
    start_server,
    wait_json,
)
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402


CONTRACT_ID = "postgres_http_write_task_parity_v1"
WORKSPACE_ID = "ws_pg_http_write"
AGENT_ID = "agt_pg_http_write"
TASK_ID = "tsk_pg_http_write_task"
BLOCKED_TASK_ID = "tsk_pg_http_write_blocked"
BLOCKED_AGENT_ID = "agt_pg_http_write_blocked"
GATEWAY_WORKSPACE_ID = "ws_pg_gateway_write"
GATEWAY_TOKEN_ID = "tok_pg_gateway_write"
GATEWAY_AGENT_ID = "agt_pg_gateway_write"
GATEWAY_OBSERVER_AGENT_ID = "agt_pg_gateway_observer"
GATEWAY_OTHER_AGENT_ID = "agt_pg_gateway_other"
GATEWAY_INTRUDER_AGENT_ID = "agt_pg_gateway_intruder"
GATEWAY_COMPLETION_AGENT_ID = "agt_pg_gateway_completion"
GATEWAY_TASK_ID = "tsk_pg_gateway_write_task"
GATEWAY_RUN_ID = "run_pg_gateway_write_start"
GATEWAY_COMPLETION_TASK_ID = "tsk_pg_gateway_completion_heartbeat"
GATEWAY_COMPLETION_RUN_ID = "run_pg_gateway_completion_heartbeat"
GATEWAY_TOOL_CALL_ID = "tc_pg_gateway_write_evidence"
GATEWAY_EVALUATION_ID = "eval_pg_gateway_write_evidence"
GATEWAY_ARTIFACT_ID = "art_pg_gateway_write_evidence"
GATEWAY_PLAN_ID = "plan_pg_gateway_write"
GATEWAY_MANIFEST_ID = "pem_pg_gateway_write"
GATEWAY_MEMORY_ID = "mem_pg_gateway_write"
GATEWAY_MEMORY_MISMATCH_ID = "mem_pg_gateway_mismatch"
GATEWAY_APPROVED_MEMORY_ID = "mem_pg_gateway_approved_existing"
GATEWAY_CROSS_WORKSPACE_MEMORY_ID = "mem_pg_gateway_cross_workspace_existing"
GATEWAY_OTHER_AGENT_MEMORY_ID = "mem_pg_gateway_other_agent_existing"
GATEWAY_APPROVAL_ID = "ap_pg_gateway_write"
GATEWAY_READ_ONLY_APPROVAL_ID = "ap_pg_gateway_read_only_blocked"
GATEWAY_NO_TOKEN_APPROVAL_ID = "ap_pg_gateway_no_token"
GATEWAY_APPROVAL_MISMATCH_ID = "ap_pg_gateway_mismatch"
GATEWAY_APPROVED_APPROVAL_ID = "ap_pg_gateway_approved_existing"
GATEWAY_APPROVED_APPROVAL_TASK_ID = "tsk_pg_gateway_approved_approval_existing"
GATEWAY_APPROVED_APPROVAL_RUN_ID = "run_pg_gateway_approved_approval_existing"
GATEWAY_APPROVED_APPROVAL_TOOL_ID = "tc_pg_gateway_approved_approval_existing"
GATEWAY_OTHER_RUN_TOOL_ID = "tc_pg_gateway_other_run_existing"
GATEWAY_AUDIT_ACTION = "agent_gateway.postgres_audit_write"
GATEWAY_READ_ONLY_AUDIT_ACTION = "agent_gateway.postgres_audit_read_only_blocked"
GATEWAY_READ_ONLY_TASK_ID = "tsk_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_CLAIM_TASK_ID = "tsk_pg_gateway_read_only_claim_blocked"
GATEWAY_READ_ONLY_RUN_ID = "run_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_TOOL_CALL_ID = "tc_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_ARTIFACT_ID = "art_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_PLAN_ID = "plan_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_MANIFEST_ID = "pem_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_MEMORY_ID = "mem_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_HEARTBEAT_AGENT_ID = "agt_pg_gateway_read_only_heartbeat_blocked"
GATEWAY_READ_ONLY_RUN_HEARTBEAT_ID = "run_pg_gateway_read_only_heartbeat_blocked"
GATEWAY_MISSING_SCOPE_TASK_ID = "tsk_pg_gateway_missing_scope"
GATEWAY_CROSS_WORKSPACE_TASK_ID = "tsk_pg_gateway_cross_workspace"
GATEWAY_CROSS_WORKSPACE_PLAN_ID = "plan_pg_gateway_cross_workspace"
GATEWAY_HEADER_WORKSPACE_TASK_ID = "tsk_pg_gateway_header_workspace"
GATEWAY_OTHER_AGENT_TASK_ID = "tsk_pg_gateway_other_agent"
GATEWAY_NO_TOKEN_TASK_ID = "tsk_pg_gateway_no_token"
GATEWAY_NO_TOKEN_PLAN_ID = "plan_pg_gateway_no_token"
GATEWAY_NO_TOKEN_MEMORY_ID = "mem_pg_gateway_no_token"
GATEWAY_MISMATCH_MANIFEST_ID = "pem_pg_gateway_mismatch"
GATEWAY_AUDIT_MISMATCH_TASK_ID = "tsk_pg_gateway_audit_wrong_task"
GATEWAY_TERMINAL_HEARTBEAT_TASK_ID = "tsk_pg_gateway_terminal_heartbeat"
GATEWAY_TERMINAL_HEARTBEAT_RUN_ID = "run_pg_gateway_terminal_heartbeat"
SMOKE_API_KEY = "postgres_write_smoke_required_api_key"
GATEWAY_ADMIN_KEY = "postgres_gateway_write_admin_key_2026"
RUNTIME_WORKSPACE_ID = "ws_pg_runtime_prepared_action"
RUNTIME_ADMIN_KEY = "postgres_runtime_write_admin_key_2026"
RUNTIME_OPENCLAW_TASK_ID = "tsk_pg_runtime_openclaw_probe"
RUNTIME_OPENCLAW_RUN_ID = "run_pg_runtime_openclaw_probe"
RUNTIME_OPENCLAW_TOOL_ID = "tc_pg_runtime_openclaw_probe"
RUNTIME_OPENCLAW_APPROVAL_ID = "ap_pg_runtime_openclaw_probe"
RUNTIME_OPENCLAW_PREPARED_ACTION_ID = "pact_pg_runtime_openclaw_probe"
RUNTIME_HERMES_TASK_ID = "tsk_pg_runtime_hermes_run_task"
RUNTIME_HERMES_RUN_ID = "run_pg_runtime_hermes_run_task"
RUNTIME_HERMES_TOOL_ID = "tc_pg_runtime_hermes_run_task"
RUNTIME_HERMES_APPROVAL_ID = "ap_pg_runtime_hermes_run_task"
RUNTIME_HERMES_PREPARED_ACTION_ID = "pact_pg_runtime_hermes_run_task"
RUNTIME_READ_ONLY_APPROVAL_ID = "ap_pg_runtime_read_only_blocked"


class FakeHermesHandler(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, fmt, *args):  # noqa: D401
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        messages = payload.get("messages") or []
        prompt = ((messages[0] if messages else {}).get("content") or "").strip()
        self.__class__.calls.append({
            "path": self.path,
            "model": payload.get("model"),
            "prompt_present": bool(prompt),
        })
        time.sleep(0.35)
        body = json.dumps({
            "id": "fake-postgres-hermes-run-task",
            "choices": [{"message": {"content": "HERMES_DEFAULT_RUN_OK"}}],
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_HTTP_WRITE_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_HTTP_WRITE_PG_REEXEC"] = "1"
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


def redact(value: str, secret: str) -> str:
    return (value or "").replace(secret, "[REDACTED]")


def seed_reference_rows(adapter: PostgresAdapter) -> None:
    now = "2026-06-22T05:00:00+00:00"
    adapter.execute(
        "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
        ("usr_founder", "Founder", "founder@example.local", "founder", now),
    )
    adapter.execute(
        "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
        ("usr_customer_demo", "Customer Demo", "customer@example.local", "customer", now),
    )
    for agent_id, name in [
        (AGENT_ID, "Postgres HTTP Writer"),
        (GATEWAY_AGENT_ID, "Postgres Gateway Writer"),
        (GATEWAY_OBSERVER_AGENT_ID, "Postgres Gateway Observer"),
        (GATEWAY_OTHER_AGENT_ID, "Postgres Gateway Other Agent"),
        (GATEWAY_INTRUDER_AGENT_ID, "Postgres Gateway Intruder Agent"),
        (GATEWAY_COMPLETION_AGENT_ID, "Postgres Gateway Completion Agent"),
    ]:
        adapter.execute(
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""",
            {
                "agent_id": agent_id,
                "name": name,
                "role": "operator",
                "description": "Seed agent for routed Postgres HTTP task write smoke.",
                "runtime_type": "mock",
                "model_provider": "mock",
                "model_name": "mock-model",
                "status": "running" if agent_id == GATEWAY_COMPLETION_AGENT_ID else "idle",
                "permission_level": "standard",
                "allowed_tools": "[]",
                "budget_limit_usd": 0,
                "owner_user_id": "usr_founder",
                "created_at": now,
                "updated_at": now,
            },
        )
    adapter.execute(
        """INSERT INTO runtime_connectors(runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,require_confirm_run,trust_status,trust_note,trust_updated_at,last_health_at,last_error,created_at,updated_at)
        VALUES(:runtime_connector_id,:provider,:connector_type,:profile_name,:base_url,:binary_path,:status,:allow_real_run,:require_confirm_run,:trust_status,:trust_note,:trust_updated_at,:last_health_at,:last_error,:created_at,:updated_at)""",
        {
            "runtime_connector_id": "rtc_agent_gateway_local",
            "provider": "agent-gateway",
            "connector_type": "local_cli_api_mcp",
            "profile_name": "postgres-http-write-smoke",
            "base_url": "http://127.0.0.1:8787/api/agent-gateway",
            "binary_path": None,
            "status": "available",
            "allow_real_run": 0,
            "require_confirm_run": 1,
            "trust_status": "trusted",
            "trust_note": "Seeded for Postgres HTTP write smoke.",
            "trust_updated_at": now,
            "last_health_at": now,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    for memory_id, workspace_id, agent_id, review_status in [
        (GATEWAY_APPROVED_MEMORY_ID, GATEWAY_WORKSPACE_ID, GATEWAY_AGENT_ID, "approved"),
        (GATEWAY_CROSS_WORKSPACE_MEMORY_ID, "other-workspace", GATEWAY_AGENT_ID, "candidate"),
        (GATEWAY_OTHER_AGENT_MEMORY_ID, GATEWAY_WORKSPACE_ID, GATEWAY_OTHER_AGENT_ID, "candidate"),
    ]:
        adapter.execute(
            """INSERT INTO memories(memory_id,workspace_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
            VALUES(:memory_id,:workspace_id,:scope,:memory_type,:canonical_text,:source_type,:source_ref,:project_id,:task_id,:agent_id,:confidence,:review_status,:owner_user_id,:ttl_review_due_at,:supersedes_memory_id,:access_tags,:created_at,:updated_at)""",
            {
                "memory_id": memory_id,
                "workspace_id": workspace_id,
                "scope": "project",
                "memory_type": "agent_lesson",
                "canonical_text": f"Seeded {review_status} memory must not be overwritten by propose scope.",
                "source_type": "manual",
                "source_ref": "seeded-postgres-write-smoke",
                "project_id": "proj_mvp",
                "task_id": None,
                "agent_id": agent_id,
                "confidence": 0.9,
                "review_status": review_status,
                "owner_user_id": "usr_founder",
                "ttl_review_due_at": "2026-07-23T05:00:00+00:00",
                "supersedes_memory_id": None,
                "access_tags": json.dumps(["agent-gateway", "seeded"], ensure_ascii=False),
                "created_at": now,
                "updated_at": now,
            },
        )
    adapter.execute(
        """INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
        VALUES(:task_id,:workspace_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)""",
        {
            "task_id": GATEWAY_APPROVED_APPROVAL_TASK_ID,
            "workspace_id": GATEWAY_WORKSPACE_ID,
            "title": "Seeded approved approval overwrite guard",
            "description": "Existing approved approval must not be reset by approval request scope.",
            "requester_id": "usr_customer_demo",
            "owner_agent_id": GATEWAY_AGENT_ID,
            "collaborator_agent_ids": "[]",
            "status": "waiting_approval",
            "priority": "high",
            "due_date": None,
            "acceptance_criteria": "Existing approval remains approved.",
            "risk_level": "high",
            "budget_limit_usd": 1.0,
            "created_at": now,
            "updated_at": now,
        },
    )
    adapter.execute(
        """INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
        VALUES(:run_id,:workspace_id,:task_id,:agent_id,:runtime_type,:status,:started_at,:ended_at,:duration_ms,:input_summary,:output_summary,:model_provider,:model_name,:input_tokens,:output_tokens,:reasoning_tokens,:cost_usd,:error_type,:error_message,:trace_id,:parent_run_id,:delegation_id,:approval_required,:created_at)""",
        {
            "run_id": GATEWAY_APPROVED_APPROVAL_RUN_ID,
            "workspace_id": GATEWAY_WORKSPACE_ID,
            "task_id": GATEWAY_APPROVED_APPROVAL_TASK_ID,
            "agent_id": GATEWAY_AGENT_ID,
            "runtime_type": "mock",
            "status": "waiting_approval",
            "started_at": now,
            "ended_at": None,
            "duration_ms": None,
            "input_summary": "Seeded run for approval overwrite guard.",
            "output_summary": None,
            "model_provider": "mock",
            "model_name": "mock-model",
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "cost_usd": 0,
            "error_type": None,
            "error_message": None,
            "trace_id": "trace_pg_gateway_approved_approval",
            "parent_run_id": None,
            "delegation_id": None,
            "approval_required": 1,
            "created_at": now,
        },
    )
    for tool_call_id, run_id in [
        (GATEWAY_APPROVED_APPROVAL_TOOL_ID, GATEWAY_APPROVED_APPROVAL_RUN_ID),
        (GATEWAY_OTHER_RUN_TOOL_ID, GATEWAY_APPROVED_APPROVAL_RUN_ID),
    ]:
        adapter.execute(
            """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
            VALUES(:tool_call_id,:run_id,:agent_id,:tool_name,:tool_version,:tool_category,:normalized_args_json,:target_resource,:risk_level,:status,:result_summary,:side_effect_id,:started_at,:ended_at,:created_at)""",
            {
                "tool_call_id": tool_call_id,
                "run_id": run_id,
                "agent_id": GATEWAY_AGENT_ID,
                "tool_name": "postgres.gateway_approval_seed",
                "tool_version": "v1",
                "tool_category": "custom",
                "normalized_args_json": json.dumps({"raw_omitted": True}, ensure_ascii=False),
                "target_resource": None,
                "risk_level": "high",
                "status": "waiting_approval",
                "result_summary": "Seeded approval guard tool call.",
                "side_effect_id": None,
                "started_at": now,
                "ended_at": None,
                "created_at": now,
            },
        )
    adapter.execute(
        """INSERT INTO approvals(approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,decision,reason,expires_at,created_at,decided_at)
        VALUES(:approval_id,:task_id,:run_id,:tool_call_id,:requested_by_agent_id,:approver_user_id,:decision,:reason,:expires_at,:created_at,:decided_at)""",
        {
            "approval_id": GATEWAY_APPROVED_APPROVAL_ID,
            "task_id": GATEWAY_APPROVED_APPROVAL_TASK_ID,
            "run_id": GATEWAY_APPROVED_APPROVAL_RUN_ID,
            "tool_call_id": GATEWAY_APPROVED_APPROVAL_TOOL_ID,
            "requested_by_agent_id": GATEWAY_AGENT_ID,
            "approver_user_id": "usr_founder",
            "decision": "approved",
            "reason": "Seeded approved approval must remain immutable to request scope.",
            "expires_at": "2026-06-24T05:00:00+00:00",
            "created_at": now,
            "decided_at": now,
        },
    )
    adapter.execute(
        """INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
        VALUES(:task_id,:workspace_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)""",
        {
            "task_id": GATEWAY_TERMINAL_HEARTBEAT_TASK_ID,
            "workspace_id": GATEWAY_WORKSPACE_ID,
            "title": "Seeded terminal heartbeat guard task",
            "description": "Terminal run heartbeat must not revive this completed run.",
            "requester_id": "usr_customer_demo",
            "owner_agent_id": GATEWAY_AGENT_ID,
            "collaborator_agent_ids": "[]",
            "status": "completed",
            "priority": "high",
            "due_date": None,
            "acceptance_criteria": "Completed runs stay terminal under heartbeat.",
            "risk_level": "low",
            "budget_limit_usd": 1.0,
            "created_at": now,
            "updated_at": now,
        },
    )
    adapter.execute(
        """INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
        VALUES(:run_id,:workspace_id,:task_id,:agent_id,:runtime_type,:status,:started_at,:ended_at,:duration_ms,:input_summary,:output_summary,:model_provider,:model_name,:input_tokens,:output_tokens,:reasoning_tokens,:cost_usd,:error_type,:error_message,:trace_id,:parent_run_id,:delegation_id,:approval_required,:created_at)""",
        {
            "run_id": GATEWAY_TERMINAL_HEARTBEAT_RUN_ID,
            "workspace_id": GATEWAY_WORKSPACE_ID,
            "task_id": GATEWAY_TERMINAL_HEARTBEAT_TASK_ID,
            "agent_id": GATEWAY_AGENT_ID,
            "runtime_type": "mock",
            "status": "completed",
            "started_at": now,
            "ended_at": now,
            "duration_ms": 1200,
            "input_summary": "Seeded terminal run heartbeat guard.",
            "output_summary": "Already completed and immutable to heartbeat revival.",
            "model_provider": "mock",
            "model_name": "mock-model",
            "input_tokens": 0,
            "output_tokens": 3,
            "reasoning_tokens": 0,
            "cost_usd": 0,
            "error_type": None,
            "error_message": None,
            "trace_id": "trace_pg_gateway_terminal_heartbeat",
            "parent_run_id": None,
            "delegation_id": None,
            "approval_required": 0,
            "created_at": now,
        },
    )
    adapter.execute(
        """INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
        VALUES(:task_id,:workspace_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)""",
        {
            "task_id": GATEWAY_COMPLETION_TASK_ID,
            "workspace_id": GATEWAY_WORKSPACE_ID,
            "title": "Seeded run heartbeat completion task",
            "description": "Run heartbeat completion must close this running run and task.",
            "requester_id": "usr_customer_demo",
            "owner_agent_id": GATEWAY_COMPLETION_AGENT_ID,
            "collaborator_agent_ids": "[]",
            "status": "running",
            "priority": "high",
            "due_date": None,
            "acceptance_criteria": "Completion heartbeat sets run/task completed and agent idle.",
            "risk_level": "low",
            "budget_limit_usd": 1.0,
            "created_at": now,
            "updated_at": now,
        },
    )
    adapter.execute(
        """INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
        VALUES(:run_id,:workspace_id,:task_id,:agent_id,:runtime_type,:status,:started_at,:ended_at,:duration_ms,:input_summary,:output_summary,:model_provider,:model_name,:input_tokens,:output_tokens,:reasoning_tokens,:cost_usd,:error_type,:error_message,:trace_id,:parent_run_id,:delegation_id,:approval_required,:created_at)""",
        {
            "run_id": GATEWAY_COMPLETION_RUN_ID,
            "workspace_id": GATEWAY_WORKSPACE_ID,
            "task_id": GATEWAY_COMPLETION_TASK_ID,
            "agent_id": GATEWAY_COMPLETION_AGENT_ID,
            "runtime_type": "mock",
            "status": "running",
            "started_at": now,
            "ended_at": None,
            "duration_ms": None,
            "input_summary": "Seeded running run for heartbeat completion.",
            "output_summary": None,
            "model_provider": "mock",
            "model_name": "mock-model",
            "input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0,
            "cost_usd": 0,
            "error_type": None,
            "error_message": None,
            "trace_id": "trace_pg_gateway_completion_heartbeat",
            "parent_run_id": None,
            "delegation_id": None,
            "approval_required": 0,
            "created_at": now,
        },
    )
    adapter.commit()


def seed_gateway_token(adapter: PostgresAdapter, *, token_id: str, raw_token: str, agent_id: str, workspace_id: str, scopes: list[str]) -> None:
    now = "2026-06-22T05:01:00+00:00"
    adapter.execute(
        """INSERT INTO agent_gateway_tokens(token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at)
        VALUES(:token_id,:token_hash,:workspace_id,:agent_id,:scopes_json,:status,:label,:heartbeat_timeout_sec,:created_at,:expires_at,:revoked_at,:last_used_at,:last_heartbeat_at)""",
        {
            "token_id": token_id,
            "token_hash": server.token_hash(raw_token),
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "scopes_json": json.dumps(scopes, ensure_ascii=False),
            "status": "active",
            "label": "Postgres HTTP Gateway write smoke",
            "heartbeat_timeout_sec": 60,
            "created_at": now,
            "expires_at": "2026-07-23T05:01:00+00:00",
            "revoked_at": None,
            "last_used_at": None,
            "last_heartbeat_at": None,
        },
    )
    adapter.commit()


def write_fake_openclaw(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path
log_path = Path(os.environ["OPENCLAW_FAKE_LOG"])
with log_path.open("a", encoding="utf-8") as handle:
    handle.write("called\\n")
time.sleep(0.35)
print(json.dumps({
    "runId": "fake-postgres-openclaw-probe",
    "result": {
        "meta": {
            "finalAssistantVisibleText": "OPENCLAW_MIS_PROBE_OK",
            "durationMs": 42,
            "agentMeta": {
                "provider": "openclaw-fake",
                "model": "openclaw-fake-model",
                "usage": {"input": 1, "output": 1}
            }
        },
        "payloads": [{"text": "OPENCLAW_MIS_PROBE_OK"}]
    }
}))
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def openclaw_call_count(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    return len([line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()])


def start_fake_hermes(port: int) -> ThreadingHTTPServer:
    FakeHermesHandler.calls = []
    fake = ThreadingHTTPServer(("127.0.0.1", port), FakeHermesHandler)
    thread = threading.Thread(target=fake.serve_forever, daemon=True)
    thread.start()
    return fake


def stop_fake_hermes(fake: ThreadingHTTPServer | None) -> None:
    if fake is None:
        return
    fake.shutdown()
    fake.server_close()


def server_env(dsn: str, pythonpath: str, *, write_enabled: bool, extra_env: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "AGENTOPS_STORAGE_BACKEND": "postgres",
            "AGENTOPS_EDITION": "enterprise_byoc",
            "AGENTOPS_POSTGRES_DSN": dsn,
            "AGENTOPS_ENABLE_POSTGRES_STORAGE": "1",
            "AGENTOPS_POSTGRES_READ_ONLY_HTTP": "1",
            "AGENTOPS_API_KEY": SMOKE_API_KEY,
            "AGENTOPS_WORKSPACE_ADMIN_KEYS_JSON": json.dumps(
                {
                    GATEWAY_WORKSPACE_ID: GATEWAY_ADMIN_KEY,
                    RUNTIME_WORKSPACE_ID: RUNTIME_ADMIN_KEY,
                },
                sort_keys=True,
            ),
            "PYTHONPATH": pythonpath,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    env.update(extra_env or {})
    if write_enabled:
        env["AGENTOPS_POSTGRES_WRITE_HTTP"] = "1"
    else:
        env.pop("AGENTOPS_POSTGRES_WRITE_HTTP", None)
    env.pop("AGENTOPS_DB_PATH", None)
    return env


def stop_server(proc: subprocess.Popen[str] | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=5)


def task_body(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "workspace_id": WORKSPACE_ID,
        "title": "Postgres routed HTTP task write",
        "description": "Created only through the explicit Postgres HTTP write allowlist.",
        "requester_id": "usr_customer_demo",
        "owner_agent_id": AGENT_ID,
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Task, runtime event, and audit rows persist in Postgres.",
        "budget_limit_usd": 1.5,
    }


def gateway_task_body(task_id: str, *, workspace_id: str | None = None, owner_agent_id: str | None = None) -> dict:
    body = {
        "task_id": task_id,
        "title": "Postgres routed Agent Gateway task write",
        "description": "Created through scoped Agent Gateway token on Postgres.",
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Gateway task, runtime event, and audit rows persist in Postgres.",
        "budget_limit_usd": 2.0,
    }
    if workspace_id is not None:
        body["workspace_id"] = workspace_id
    if owner_agent_id is not None:
        body["owner_agent_id"] = owner_agent_id
    return body


def gateway_agent_plan_body(plan_id: str, *, run_id: str = GATEWAY_RUN_ID) -> dict:
    return {
        "plan_id": plan_id,
        "run_id": run_id,
        "task_understanding": "Bind the Postgres Gateway execution to a verifiable READ/PLAN/EXECUTE/VERIFY/RECORD chain.",
        "referenced_specs": ["docs/AGENT_GATEWAY_CLI_SPEC.md", "docs/POSTGRES_PARITY_CONTRACT.md"],
        "referenced_memories": ["project-memory:postgres-gateway-evidence-write"],
        "referenced_bases": ["agent_gateway_ledger", "postgres_storage_boundary"],
        "proposed_files_to_change": ["server.py", "scripts/storage_postgres_http_write_task_smoke.py"],
        "risk_level": "low",
        "approval_required": False,
        "execution_steps": ["READ", "PLAN", "EXECUTE", "VERIFY", "RECORD"],
        "verification_plan": "Verify task, run, tool, evaluation, artifact, audit, Agent Plan, and plan-evidence rows in Postgres.",
        "rollback_plan": "Remove the two plan routes from the Postgres allowlist if verification fails.",
        "status": "submitted",
    }


def gateway_plan_evidence_body(manifest_id: str, *, plan_id: str = GATEWAY_PLAN_ID, run_id: str = GATEWAY_RUN_ID) -> dict:
    return {
        "manifest_id": manifest_id,
        "plan_id": plan_id,
        "run_id": run_id,
        "mismatch_policy": "block",
        "expected_steps": ["READ", "PLAN", "EXECUTE", "VERIFY", "RECORD"],
        "tool_call_ids": [GATEWAY_TOOL_CALL_ID],
        "evaluation_ids": [GATEWAY_EVALUATION_ID],
        "artifact_ids": [GATEWAY_ARTIFACT_ID],
        "verify_now": True,
    }


def gateway_approval_body(
    approval_id: str,
    *,
    run_id: str = GATEWAY_RUN_ID,
    task_id: str = GATEWAY_TASK_ID,
    tool_call_id: str | None = GATEWAY_TOOL_CALL_ID,
    reason: str = "Postgres Gateway approval request write proof.",
) -> dict:
    body = {
        "approval_id": approval_id,
        "run_id": run_id,
        "task_id": task_id,
        "reason": reason,
    }
    if tool_call_id is not None:
        body["tool_call_id"] = tool_call_id
    return body


def gateway_audit_body(action: str = GATEWAY_AUDIT_ACTION, *, task_id: str = GATEWAY_TASK_ID, run_id: str = GATEWAY_RUN_ID) -> dict:
    return {
        "run_id": run_id,
        "task_id": task_id,
        "entity_type": "runs",
        "entity_id": run_id,
        "action": action,
        "after": {"status": "postgres_gateway_audit_recorded", "raw_omitted": True},
        "metadata": {
            "contract": "postgres_http_gateway_audit_write_v1",
            "raw_omitted": True,
        },
    }


def gateway_memory_body(memory_id: str, *, task_id: str = GATEWAY_TASK_ID, run_id: str = GATEWAY_RUN_ID) -> dict:
    return {
        "memory_id": memory_id,
        "run_id": run_id,
        "task_id": task_id,
        "scope": "project",
        "memory_type": "agent_lesson",
        "canonical_text": "Postgres Gateway memory candidate write proof with raw prompt omitted.",
        "source_type": "run_log",
        "source_ref": run_id,
        "confidence": 0.88,
        "access_tags": ["agent-gateway", "postgres-write-proof"],
    }


def request_json_with_token(url: str, *, token: str, method: str = "POST", body: dict | None = None, extra_headers: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra_headers or {})
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=5) as res:
            return int(res.status), json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def request_json_with_admin(
    url: str,
    *,
    workspace_id: str,
    admin_key: str,
    body: dict | None = None,
) -> tuple[int, dict]:
    return request_json_with_token(
        url,
        token=admin_key,
        body=body,
        extra_headers={"X-AgentOps-Workspace-Id": workspace_id},
    )


def concurrent_admin_requests(
    base_urls: list[str],
    *,
    path: str,
    workspace_id: str,
    admin_key: str,
    body: dict,
) -> list[tuple[int, dict]]:
    barrier = threading.Barrier(len(base_urls))

    def send(base_url: str) -> tuple[int, dict]:
        barrier.wait(timeout=5)
        return request_json_with_admin(
            f"{base_url}{path}",
            workspace_id=workspace_id,
            admin_key=admin_key,
            body=dict(body),
        )

    with ThreadPoolExecutor(max_workers=len(base_urls)) as executor:
        return list(executor.map(send, base_urls))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Postgres-backed HTTP task write smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE, help="Postgres Docker image to use.")
    parser.add_argument("--skip-if-unavailable", action="store_true", help="Return success with skipped=true when Docker or psycopg is unavailable.")
    parser.add_argument("--no-install-driver", action="store_true", help="Do not install psycopg into a temporary target when missing.")
    args = parser.parse_args()

    reexec_self_with_bundled_python_if_needed()

    early = container_smoke.docker_available(args.skip_if_unavailable)
    if early is not None:
        return early
    early = container_smoke.ensure_image(args.image, args.skip_if_unavailable)
    if early is not None:
        return early

    with tempfile.TemporaryDirectory(prefix="agentops-http-pg-write-") as temp_dir:
        temp_root = Path(temp_dir)
        driver_ok, driver_status = ensure_psycopg(temp_root, install=not args.no_install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=args.skip_if_unavailable)

        fake_hermes_port = free_port()
        fake_hermes = start_fake_hermes(fake_hermes_port)
        fake_openclaw = temp_root / "openclaw"
        fake_openclaw_log = temp_root / "openclaw.log"
        fake_openclaw_home = temp_root / "openclaw-home"
        fake_openclaw_home.mkdir(parents=True, exist_ok=True)
        write_fake_openclaw(fake_openclaw)
        runtime_env = {
            "HERMES_GATEWAY_URL": f"http://127.0.0.1:{fake_hermes_port}",
            "HERMES_ALLOW_REAL_RUN": "true",
            "HERMES_REQUIRE_CONFIRM_RUN": "true",
            "OPENCLAW_BIN": str(fake_openclaw),
            "OPENCLAW_HOME": str(fake_openclaw_home),
            "OPENCLAW_FAKE_LOG": str(fake_openclaw_log),
        }

        pythonpath_parts = [str(ROOT)]
        package_target = temp_root / "python-packages"
        if package_target.exists():
            pythonpath_parts.insert(0, str(package_target))
        if os.environ.get("PYTHONPATH"):
            pythonpath_parts.append(os.environ["PYTHONPATH"])
        pythonpath = os.pathsep.join(pythonpath_parts)

        container = f"agentops-pg-http-write-{container_smoke.secrets.token_hex(6)}"
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
                args.image,
            ],
            timeout=60,
        )
        if started.returncode != 0:
            detail = redact((started.stderr or started.stdout or "docker run failed").strip(), pg_auth)
            stop_fake_hermes(fake_hermes)
            return unavailable(f"Postgres container failed to start: {detail}", skip=args.skip_if_unavailable)

        adapter: PostgresAdapter | None = None
        proc: subprocess.Popen[str] | None = None
        peer_proc: subprocess.Popen[str] | None = None
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=args.skip_if_unavailable)
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = connect_postgres_when_ready(dsn, secret=pg_auth)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            seed_reference_rows(adapter)
            gateway_token = "agtok_pg_" + container_smoke.secrets.token_urlsafe(24)
            gateway_observer_token = "agtok_pg_observer_" + container_smoke.secrets.token_urlsafe(18)
            gateway_intruder_token = "agtok_pg_intruder_" + container_smoke.secrets.token_urlsafe(18)
            gateway_completion_token = "agtok_pg_completion_" + container_smoke.secrets.token_urlsafe(18)
            seed_gateway_token(
                adapter,
                token_id=GATEWAY_TOKEN_ID,
                raw_token=gateway_token,
                agent_id=GATEWAY_AGENT_ID,
                workspace_id=GATEWAY_WORKSPACE_ID,
                scopes=[
                    "tasks:create",
                    "tasks:read",
                    "tasks:claim",
                    "agents:heartbeat",
                    "runs:write",
                    "toolcalls:write",
                    "artifacts:write",
                    "evaluations:submit",
                    "agent_plans:write",
                    "plan_evidence:write",
                    "memories:propose",
                    "approvals:request",
                    "audit:write",
                ],
            )
            seed_gateway_token(
                adapter,
                token_id="agtok_pg_gateway_observer",
                raw_token=gateway_observer_token,
                agent_id=GATEWAY_OBSERVER_AGENT_ID,
                workspace_id=GATEWAY_WORKSPACE_ID,
                scopes=["tasks:read"],
            )
            seed_gateway_token(
                adapter,
                token_id="tok_pg_gateway_intruder",
                raw_token=gateway_intruder_token,
                agent_id=GATEWAY_INTRUDER_AGENT_ID,
                workspace_id=GATEWAY_WORKSPACE_ID,
                scopes=[
                    "tasks:read",
                    "tasks:claim",
                    "agents:heartbeat",
                    "runs:write",
                    "toolcalls:write",
                    "artifacts:write",
                    "evaluations:submit",
                    "agent_plans:write",
                    "plan_evidence:write",
                    "memories:propose",
                    "approvals:request",
                    "audit:write",
                ],
            )
            seed_gateway_token(
                adapter,
                token_id="tok_pg_gateway_completion",
                raw_token=gateway_completion_token,
                agent_id=GATEWAY_COMPLETION_AGENT_ID,
                workspace_id=GATEWAY_WORKSPACE_ID,
                scopes=["runs:write"],
            )
            adapter.close()
            adapter = None

            read_only_port = free_port()
            proc = start_server(server_env(dsn, pythonpath, write_enabled=False, extra_env=runtime_env), read_only_port)
            read_only_base = f"http://127.0.0.1:{read_only_port}"
            read_only_status_code, read_only_backend = wait_json(f"{read_only_base}/api/storage/backend-status", proc, secret=pg_auth)
            blocked_status, blocked_payload = request_json(f"{read_only_base}/api/tasks", method="POST", body=task_body(BLOCKED_TASK_ID))
            gateway_blocked_status, gateway_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_READ_ONLY_TASK_ID, owner_agent_id=GATEWAY_AGENT_ID),
            )
            gateway_claim_blocked_status, gateway_claim_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/tasks/{GATEWAY_READ_ONLY_CLAIM_TASK_ID}/claim",
                token=gateway_token,
                body={"runtime_type": "mock"},
            )
            gateway_run_start_blocked_status, gateway_run_start_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/runs/start",
                token=gateway_token,
                body={
                    "run_id": GATEWAY_READ_ONLY_RUN_ID,
                    "task_id": GATEWAY_READ_ONLY_CLAIM_TASK_ID,
                    "runtime_type": "mock",
                },
            )
            gateway_tool_blocked_status, gateway_tool_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/tool-calls",
                token=gateway_token,
                body={
                    "tool_call_id": GATEWAY_READ_ONLY_TOOL_CALL_ID,
                    "run_id": GATEWAY_READ_ONLY_RUN_ID,
                    "tool_name": "postgres.read_only_blocked_tool",
                    "tool_category": "custom",
                    "status": "completed",
                },
            )
            gateway_eval_blocked_status, gateway_eval_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/evaluations/submit",
                token=gateway_token,
                body={
                    "evaluation_id": f"{GATEWAY_EVALUATION_ID}_read_only",
                    "run_id": GATEWAY_READ_ONLY_RUN_ID,
                    "score": 1.0,
                    "pass_fail": "pass",
                },
            )
            gateway_artifact_blocked_status, gateway_artifact_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/artifacts",
                token=gateway_token,
                body={
                    "artifact_id": GATEWAY_READ_ONLY_ARTIFACT_ID,
                    "run_id": GATEWAY_READ_ONLY_RUN_ID,
                    "title": "Read-only blocked artifact",
                    "summary": "This artifact must not persist in read-only Postgres mode.",
                },
            )
            gateway_plan_blocked_status, gateway_plan_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/agent-plans",
                token=gateway_token,
                body=gateway_agent_plan_body(GATEWAY_READ_ONLY_PLAN_ID, run_id=GATEWAY_READ_ONLY_RUN_ID),
            )
            gateway_manifest_blocked_status, gateway_manifest_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/plan-evidence-manifests",
                token=gateway_token,
                body=gateway_plan_evidence_body(
                    GATEWAY_READ_ONLY_MANIFEST_ID,
                    plan_id=GATEWAY_READ_ONLY_PLAN_ID,
                    run_id=GATEWAY_READ_ONLY_RUN_ID,
                ),
            )
            gateway_memory_blocked_status, gateway_memory_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/memories/propose",
                token=gateway_token,
                body=gateway_memory_body(
                    GATEWAY_READ_ONLY_MEMORY_ID,
                    run_id=GATEWAY_READ_ONLY_RUN_ID,
                    task_id=GATEWAY_READ_ONLY_CLAIM_TASK_ID,
                ),
            )
            gateway_approval_blocked_status, gateway_approval_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/approvals/request",
                token=gateway_token,
                body=gateway_approval_body(
                    GATEWAY_READ_ONLY_APPROVAL_ID,
                    run_id=GATEWAY_READ_ONLY_RUN_ID,
                    task_id=GATEWAY_READ_ONLY_CLAIM_TASK_ID,
                    tool_call_id=GATEWAY_READ_ONLY_TOOL_CALL_ID,
                ),
            )
            gateway_heartbeat_blocked_status, gateway_heartbeat_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/heartbeat",
                token=gateway_token,
                body={
                    "agent_id": GATEWAY_READ_ONLY_HEARTBEAT_AGENT_ID,
                    "status": "running",
                    "summary": "This heartbeat must not persist in read-only Postgres mode.",
                },
            )
            gateway_run_heartbeat_blocked_status, gateway_run_heartbeat_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/runs/{GATEWAY_READ_ONLY_RUN_HEARTBEAT_ID}/heartbeat",
                token=gateway_token,
                body={
                    "task_id": GATEWAY_READ_ONLY_CLAIM_TASK_ID,
                    "status": "running",
                    "output_summary": "This run heartbeat must not persist in read-only Postgres mode.",
                },
            )
            gateway_audit_blocked_status, gateway_audit_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/audit",
                token=gateway_token,
                body=gateway_audit_body(GATEWAY_READ_ONLY_AUDIT_ACTION, run_id=GATEWAY_READ_ONLY_RUN_ID, task_id=GATEWAY_READ_ONLY_CLAIM_TASK_ID),
            )
            runtime_openclaw_read_only_status, runtime_openclaw_read_only_payload = request_json_with_admin(
                f"{read_only_base}/api/integrations/openclaw/probe",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={"confirm_run": True, "task_id": RUNTIME_OPENCLAW_TASK_ID, "workspace_id": RUNTIME_WORKSPACE_ID},
            )
            runtime_hermes_read_only_status, runtime_hermes_read_only_payload = request_json_with_admin(
                f"{read_only_base}/api/integrations/hermes/run-task",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={"confirm_run": True, "task_id": RUNTIME_HERMES_TASK_ID, "workspace_id": RUNTIME_WORKSPACE_ID},
            )
            runtime_approval_read_only_status, runtime_approval_read_only_payload = request_json_with_admin(
                f"{read_only_base}/api/approvals/{RUNTIME_READ_ONLY_APPROVAL_ID}/approve",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={},
            )
            stop_server(proc)
            proc = None

            write_port = free_port()
            proc = start_server(server_env(dsn, pythonpath, write_enabled=True, extra_env=runtime_env), write_port)
            write_base = f"http://127.0.0.1:{write_port}"
            write_status_code, write_backend = wait_json(f"{write_base}/api/storage/backend-status", proc, secret=pg_auth)
            peer_port = free_port()
            peer_proc = start_server(server_env(dsn, pythonpath, write_enabled=True, extra_env=runtime_env), peer_port)
            peer_base = f"http://127.0.0.1:{peer_port}"
            peer_status_code, peer_backend = wait_json(f"{peer_base}/api/storage/backend-status", peer_proc, secret=pg_auth)
            create_status, create_payload = request_json(f"{write_base}/api/tasks", method="POST", body=task_body(TASK_ID))
            readback_status, readback_payload = request_json(f"{write_base}/api/tasks/{TASK_ID}?workspace_id={WORKSPACE_ID}")
            gateway_missing_heartbeat_scope_status, gateway_missing_heartbeat_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/heartbeat",
                token=gateway_observer_token,
                body={"status": "running", "summary": "Missing agents:heartbeat scope must be rejected."},
            )
            gateway_heartbeat_cross_workspace_status, gateway_heartbeat_cross_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/heartbeat",
                token=gateway_token,
                body={"workspace_id": "other-workspace", "status": "running"},
            )
            gateway_heartbeat_header_workspace_status, gateway_heartbeat_header_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/heartbeat",
                token=gateway_token,
                body={"status": "running"},
                extra_headers={"X-AgentOps-Workspace-Id": "other-workspace"},
            )
            gateway_heartbeat_other_agent_status, gateway_heartbeat_other_agent_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/heartbeat",
                token=gateway_token,
                body={"agent_id": GATEWAY_OTHER_AGENT_ID, "status": "running"},
            )
            gateway_heartbeat_intruder_status, gateway_heartbeat_intruder_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/heartbeat",
                token=gateway_intruder_token,
                body={"agent_id": GATEWAY_AGENT_ID, "status": "running"},
            )
            gateway_heartbeat_no_token_status, gateway_heartbeat_no_token_payload = request_json(
                f"{write_base}/api/agent-gateway/heartbeat",
                method="POST",
                body={"agent_id": GATEWAY_AGENT_ID, "status": "running"},
            )
            gateway_heartbeat_write_status, gateway_heartbeat_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/heartbeat",
                token=gateway_token,
                body={
                    "status": "running",
                    "runtime_type": "mock",
                    "summary": "Postgres Gateway agent heartbeat write proof.",
                },
            )
            gateway_missing_scope_status, gateway_missing_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_observer_token,
                body=gateway_task_body(GATEWAY_MISSING_SCOPE_TASK_ID, owner_agent_id=GATEWAY_OBSERVER_AGENT_ID),
            )
            gateway_cross_workspace_status, gateway_cross_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_CROSS_WORKSPACE_TASK_ID, workspace_id="other-workspace", owner_agent_id=GATEWAY_AGENT_ID),
            )
            gateway_header_workspace_status, gateway_header_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_HEADER_WORKSPACE_TASK_ID, owner_agent_id=GATEWAY_AGENT_ID),
                extra_headers={"X-AgentOps-Workspace-Id": "other-workspace"},
            )
            gateway_other_agent_status, gateway_other_agent_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_OTHER_AGENT_TASK_ID, owner_agent_id=GATEWAY_OTHER_AGENT_ID),
            )
            gateway_no_token_status, gateway_no_token_payload = request_json(
                f"{write_base}/api/agent-gateway/tasks",
                method="POST",
                body=gateway_task_body(GATEWAY_NO_TOKEN_TASK_ID, owner_agent_id=GATEWAY_AGENT_ID),
            )
            gateway_create_status, gateway_create_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_TASK_ID, owner_agent_id=GATEWAY_AGENT_ID),
            )
            gateway_missing_claim_scope_status, gateway_missing_claim_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks/{GATEWAY_TASK_ID}/claim",
                token=gateway_observer_token,
                body={"runtime_type": "mock"},
            )
            gateway_claim_status, gateway_claim_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks/{GATEWAY_TASK_ID}/claim",
                token=gateway_token,
                body={"runtime_type": "mock"},
            )
            gateway_missing_run_scope_status, gateway_missing_run_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/start",
                token=gateway_observer_token,
                body={
                    "run_id": f"{GATEWAY_RUN_ID}_missing_scope",
                    "task_id": GATEWAY_TASK_ID,
                    "runtime_type": "mock",
                },
            )
            gateway_run_start_status, gateway_run_start_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/start",
                token=gateway_token,
                body={
                    "run_id": GATEWAY_RUN_ID,
                    "task_id": GATEWAY_TASK_ID,
                    "runtime_type": "mock",
                    "input_summary": "Postgres Agent Gateway run start write proof.",
                },
            )
            gateway_missing_run_heartbeat_scope_status, gateway_missing_run_heartbeat_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/{GATEWAY_RUN_ID}/heartbeat",
                token=gateway_observer_token,
                body={
                    "task_id": GATEWAY_TASK_ID,
                    "status": "running",
                    "output_summary": "Missing runs:write scope must be rejected.",
                },
            )
            gateway_run_heartbeat_no_token_status, gateway_run_heartbeat_no_token_payload = request_json(
                f"{write_base}/api/agent-gateway/runs/{GATEWAY_RUN_ID}/heartbeat",
                method="POST",
                body={
                    "task_id": GATEWAY_TASK_ID,
                    "agent_id": GATEWAY_AGENT_ID,
                    "status": "running",
                    "output_summary": "No token run heartbeat must be rejected.",
                },
            )
            gateway_run_heartbeat_cross_workspace_status, gateway_run_heartbeat_cross_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/{GATEWAY_RUN_ID}/heartbeat",
                token=gateway_token,
                body={
                    "workspace_id": "other-workspace",
                    "task_id": GATEWAY_TASK_ID,
                    "status": "running",
                    "output_summary": "Cross-workspace run heartbeat must be rejected.",
                },
            )
            gateway_run_heartbeat_header_workspace_status, gateway_run_heartbeat_header_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/{GATEWAY_RUN_ID}/heartbeat",
                token=gateway_token,
                body={
                    "task_id": GATEWAY_TASK_ID,
                    "status": "running",
                    "output_summary": "Cross-workspace header run heartbeat must be rejected.",
                },
                extra_headers={"X-AgentOps-Workspace-Id": "other-workspace"},
            )
            gateway_run_heartbeat_task_mismatch_status, gateway_run_heartbeat_task_mismatch_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/{GATEWAY_RUN_ID}/heartbeat",
                token=gateway_token,
                body={
                    "task_id": GATEWAY_AUDIT_MISMATCH_TASK_ID,
                    "status": "running",
                    "output_summary": "Task mismatch must be rejected.",
                },
            )
            gateway_run_heartbeat_intruder_status, gateway_run_heartbeat_intruder_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/{GATEWAY_RUN_ID}/heartbeat",
                token=gateway_intruder_token,
                body={
                    "task_id": GATEWAY_TASK_ID,
                    "status": "running",
                    "output_summary": "Intruder run heartbeat must be rejected.",
                },
            )
            gateway_run_heartbeat_terminal_revival_status, gateway_run_heartbeat_terminal_revival_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/{GATEWAY_TERMINAL_HEARTBEAT_RUN_ID}/heartbeat",
                token=gateway_token,
                body={
                    "task_id": GATEWAY_TERMINAL_HEARTBEAT_TASK_ID,
                    "status": "running",
                    "output_summary": "Terminal run must not be revived by heartbeat.",
                },
            )
            gateway_run_heartbeat_write_status, gateway_run_heartbeat_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/{GATEWAY_RUN_ID}/heartbeat",
                token=gateway_token,
                body={
                    "task_id": GATEWAY_TASK_ID,
                    "status": "running",
                    "duration_ms": 2345,
                    "output_tokens": 17,
                    "cost_usd": 0.0123,
                    "output_summary": "Postgres Gateway run heartbeat write proof.",
                },
            )
            gateway_run_completion_heartbeat_status, gateway_run_completion_heartbeat_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/{GATEWAY_COMPLETION_RUN_ID}/heartbeat",
                token=gateway_completion_token,
                body={
                    "task_id": GATEWAY_COMPLETION_TASK_ID,
                    "status": "completed",
                    "duration_ms": 3456,
                    "output_tokens": 29,
                    "cost_usd": 0.019,
                    "output_summary": "Postgres Gateway run completion heartbeat proof.",
                },
            )
            gateway_intruder_claim_status, gateway_intruder_claim_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks/{GATEWAY_TASK_ID}/claim",
                token=gateway_intruder_token,
                body={"runtime_type": "mock"},
            )
            gateway_intruder_run_status, gateway_intruder_run_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/start",
                token=gateway_intruder_token,
                body={
                    "run_id": f"{GATEWAY_RUN_ID}_intruder",
                    "task_id": GATEWAY_TASK_ID,
                    "runtime_type": "mock",
                },
            )
            gateway_missing_tool_scope_status, gateway_missing_tool_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tool-calls",
                token=gateway_observer_token,
                body={
                    "tool_call_id": f"{GATEWAY_TOOL_CALL_ID}_missing_scope",
                    "run_id": GATEWAY_RUN_ID,
                    "tool_name": "postgres.gateway_missing_tool_scope",
                    "tool_category": "custom",
                    "status": "completed",
                },
            )
            gateway_tool_write_status, gateway_tool_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tool-calls",
                token=gateway_token,
                body={
                    "tool_call_id": GATEWAY_TOOL_CALL_ID,
                    "run_id": GATEWAY_RUN_ID,
                    "tool_name": "postgres.gateway_evidence_tool",
                    "tool_category": "custom",
                    "risk_level": "low",
                    "status": "completed",
                    "args": {"raw_omitted": True, "contract": "postgres_http_gateway_evidence_write_v1"},
                    "result_summary": "Postgres Gateway tool-call evidence write proof.",
                },
            )
            gateway_missing_eval_scope_status, gateway_missing_eval_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/evaluations/submit",
                token=gateway_observer_token,
                body={
                    "evaluation_id": f"{GATEWAY_EVALUATION_ID}_missing_scope",
                    "run_id": GATEWAY_RUN_ID,
                    "score": 1.0,
                    "pass_fail": "pass",
                },
            )
            gateway_eval_write_status, gateway_eval_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/evaluations/submit",
                token=gateway_token,
                body={
                    "evaluation_id": GATEWAY_EVALUATION_ID,
                    "run_id": GATEWAY_RUN_ID,
                    "task_id": GATEWAY_TASK_ID,
                    "evaluator_type": "rule",
                    "score": 1.0,
                    "pass_fail": "pass",
                    "rubric": {"gate": "postgres_gateway_evidence_write"},
                    "notes": "Postgres Gateway evaluation evidence write proof.",
                },
            )
            gateway_missing_artifact_scope_status, gateway_missing_artifact_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/artifacts",
                token=gateway_observer_token,
                body={
                    "artifact_id": f"{GATEWAY_ARTIFACT_ID}_missing_scope",
                    "run_id": GATEWAY_RUN_ID,
                    "title": "Missing artifact scope",
                    "summary": "This artifact must not persist without artifacts:write.",
                },
            )
            gateway_artifact_write_status, gateway_artifact_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/artifacts",
                token=gateway_token,
                body={
                    "artifact_id": GATEWAY_ARTIFACT_ID,
                    "run_id": GATEWAY_RUN_ID,
                    "artifact_type": "postgres_gateway_evidence",
                    "title": "Postgres Gateway evidence artifact",
                    "uri": f"run://{GATEWAY_RUN_ID}",
                    "summary": "Postgres Gateway artifact evidence write proof.",
                    "content_hash": "pg_gateway_evidence_hash",
                },
            )
            gateway_missing_plan_scope_status, gateway_missing_plan_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/agent-plans",
                token=gateway_observer_token,
                body=gateway_agent_plan_body(f"{GATEWAY_PLAN_ID}_missing_scope"),
            )
            gateway_plan_cross_workspace_body = gateway_agent_plan_body(GATEWAY_CROSS_WORKSPACE_PLAN_ID)
            gateway_plan_cross_workspace_body["workspace_id"] = "other-workspace"
            gateway_plan_cross_workspace_status, gateway_plan_cross_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/agent-plans",
                token=gateway_token,
                body=gateway_plan_cross_workspace_body,
            )
            gateway_plan_no_token_status, gateway_plan_no_token_payload = request_json(
                f"{write_base}/api/agent-gateway/agent-plans",
                method="POST",
                body=gateway_agent_plan_body(GATEWAY_NO_TOKEN_PLAN_ID),
            )
            gateway_plan_write_status, gateway_plan_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/agent-plans",
                token=gateway_token,
                body=gateway_agent_plan_body(GATEWAY_PLAN_ID),
            )
            gateway_manifest_mismatch_body = gateway_plan_evidence_body(GATEWAY_MISMATCH_MANIFEST_ID)
            gateway_manifest_mismatch_body["task_id"] = "tsk_pg_gateway_wrong_task"
            gateway_manifest_mismatch_status, gateway_manifest_mismatch_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/plan-evidence-manifests",
                token=gateway_token,
                body=gateway_manifest_mismatch_body,
            )
            gateway_missing_manifest_scope_status, gateway_missing_manifest_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/plan-evidence-manifests",
                token=gateway_observer_token,
                body=gateway_plan_evidence_body(f"{GATEWAY_MANIFEST_ID}_missing_scope"),
            )
            gateway_manifest_write_status, gateway_manifest_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/plan-evidence-manifests",
                token=gateway_token,
                body=gateway_plan_evidence_body(GATEWAY_MANIFEST_ID),
            )
            gateway_missing_memory_scope_status, gateway_missing_memory_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/memories/propose",
                token=gateway_observer_token,
                body=gateway_memory_body(f"{GATEWAY_MEMORY_ID}_missing_scope"),
            )
            gateway_memory_cross_workspace_body = gateway_memory_body(f"{GATEWAY_MEMORY_ID}_cross_workspace")
            gateway_memory_cross_workspace_body["workspace_id"] = "other-workspace"
            gateway_memory_cross_workspace_status, gateway_memory_cross_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/memories/propose",
                token=gateway_token,
                body=gateway_memory_cross_workspace_body,
            )
            gateway_memory_header_workspace_status, gateway_memory_header_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/memories/propose",
                token=gateway_token,
                body=gateway_memory_body(f"{GATEWAY_MEMORY_ID}_header_workspace"),
                extra_headers={"X-AgentOps-Workspace-Id": "other-workspace"},
            )
            gateway_memory_no_token_status, gateway_memory_no_token_payload = request_json(
                f"{write_base}/api/agent-gateway/memories/propose",
                method="POST",
                body=gateway_memory_body(GATEWAY_NO_TOKEN_MEMORY_ID),
            )
            gateway_memory_mismatch_status, gateway_memory_mismatch_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/memories/propose",
                token=gateway_token,
                body=gateway_memory_body(GATEWAY_MEMORY_MISMATCH_ID, task_id=GATEWAY_AUDIT_MISMATCH_TASK_ID),
            )
            gateway_memory_approved_overwrite_status, gateway_memory_approved_overwrite_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/memories/propose",
                token=gateway_token,
                body=gateway_memory_body(GATEWAY_APPROVED_MEMORY_ID),
            )
            gateway_memory_existing_cross_workspace_status, gateway_memory_existing_cross_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/memories/propose",
                token=gateway_token,
                body=gateway_memory_body(GATEWAY_CROSS_WORKSPACE_MEMORY_ID),
            )
            gateway_memory_other_agent_overwrite_status, gateway_memory_other_agent_overwrite_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/memories/propose",
                token=gateway_token,
                body=gateway_memory_body(GATEWAY_OTHER_AGENT_MEMORY_ID),
            )
            gateway_memory_write_status, gateway_memory_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/memories/propose",
                token=gateway_token,
                body=gateway_memory_body(GATEWAY_MEMORY_ID),
            )
            gateway_missing_approval_scope_status, gateway_missing_approval_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_observer_token,
                body=gateway_approval_body(f"{GATEWAY_APPROVAL_ID}_missing_scope"),
            )
            gateway_approval_cross_workspace_body = gateway_approval_body(f"{GATEWAY_APPROVAL_ID}_cross_workspace")
            gateway_approval_cross_workspace_body["workspace_id"] = "other-workspace"
            gateway_approval_cross_workspace_status, gateway_approval_cross_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_token,
                body=gateway_approval_cross_workspace_body,
            )
            gateway_approval_header_workspace_status, gateway_approval_header_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_token,
                body=gateway_approval_body(f"{GATEWAY_APPROVAL_ID}_header_workspace"),
                extra_headers={"X-AgentOps-Workspace-Id": "other-workspace"},
            )
            gateway_approval_no_token_status, gateway_approval_no_token_payload = request_json(
                f"{write_base}/api/agent-gateway/approvals/request",
                method="POST",
                body=gateway_approval_body(GATEWAY_NO_TOKEN_APPROVAL_ID),
            )
            gateway_approval_mismatch_status, gateway_approval_mismatch_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_token,
                body=gateway_approval_body(GATEWAY_APPROVAL_MISMATCH_ID, task_id=GATEWAY_AUDIT_MISMATCH_TASK_ID),
            )
            gateway_approval_tool_mismatch_status, gateway_approval_tool_mismatch_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_token,
                body=gateway_approval_body(f"{GATEWAY_APPROVAL_ID}_tool_mismatch", tool_call_id=GATEWAY_OTHER_RUN_TOOL_ID),
            )
            gateway_approval_approved_overwrite_status, gateway_approval_approved_overwrite_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_token,
                body=gateway_approval_body(
                    GATEWAY_APPROVED_APPROVAL_ID,
                    run_id=GATEWAY_APPROVED_APPROVAL_RUN_ID,
                    task_id=GATEWAY_APPROVED_APPROVAL_TASK_ID,
                    tool_call_id=GATEWAY_APPROVED_APPROVAL_TOOL_ID,
                ),
            )
            gateway_approval_other_agent_status, gateway_approval_other_agent_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_token,
                body={
                    **gateway_approval_body(f"{GATEWAY_APPROVAL_ID}_other_agent"),
                    "requested_by_agent_id": GATEWAY_OTHER_AGENT_ID,
                },
            )
            gateway_approval_write_status, gateway_approval_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_token,
                body=gateway_approval_body(GATEWAY_APPROVAL_ID),
            )
            runtime_non_prepared_approval_status, runtime_non_prepared_approval_payload = request_json_with_admin(
                f"{write_base}/api/approvals/{GATEWAY_APPROVAL_ID}/approve",
                workspace_id=GATEWAY_WORKSPACE_ID,
                admin_key=GATEWAY_ADMIN_KEY,
                body={},
            )
            gateway_missing_audit_scope_status, gateway_missing_audit_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/audit",
                token=gateway_observer_token,
                body=gateway_audit_body(f"{GATEWAY_AUDIT_ACTION}.missing_scope"),
            )
            gateway_audit_cross_workspace_body = gateway_audit_body(f"{GATEWAY_AUDIT_ACTION}.cross_workspace")
            gateway_audit_cross_workspace_body["workspace_id"] = "other-workspace"
            gateway_audit_cross_workspace_status, gateway_audit_cross_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/audit",
                token=gateway_token,
                body=gateway_audit_cross_workspace_body,
            )
            gateway_audit_no_token_status, gateway_audit_no_token_payload = request_json(
                f"{write_base}/api/agent-gateway/audit",
                method="POST",
                body=gateway_audit_body(f"{GATEWAY_AUDIT_ACTION}.no_token"),
            )
            gateway_audit_mismatch_status, gateway_audit_mismatch_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/audit",
                token=gateway_token,
                body=gateway_audit_body(f"{GATEWAY_AUDIT_ACTION}.mismatch", task_id=GATEWAY_AUDIT_MISMATCH_TASK_ID),
            )
            gateway_audit_write_status, gateway_audit_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/audit",
                token=gateway_token,
                body=gateway_audit_body(),
            )
            gateway_intruder_tool_status, gateway_intruder_tool_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tool-calls",
                token=gateway_intruder_token,
                body={
                    "tool_call_id": f"{GATEWAY_TOOL_CALL_ID}_intruder",
                    "run_id": GATEWAY_RUN_ID,
                    "tool_name": "postgres.gateway_intruder_tool",
                    "tool_category": "custom",
                    "status": "completed",
                },
            )
            gateway_intruder_eval_status, gateway_intruder_eval_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/evaluations/submit",
                token=gateway_intruder_token,
                body={
                    "evaluation_id": f"{GATEWAY_EVALUATION_ID}_intruder",
                    "run_id": GATEWAY_RUN_ID,
                    "score": 1.0,
                    "pass_fail": "pass",
                },
            )
            gateway_intruder_artifact_status, gateway_intruder_artifact_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/artifacts",
                token=gateway_intruder_token,
                body={
                    "artifact_id": f"{GATEWAY_ARTIFACT_ID}_intruder",
                    "run_id": GATEWAY_RUN_ID,
                    "title": "Intruder artifact",
                    "summary": "This artifact must not persist for another agent's run.",
                },
            )
            gateway_intruder_plan_status, gateway_intruder_plan_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/agent-plans",
                token=gateway_intruder_token,
                body=gateway_agent_plan_body(f"{GATEWAY_PLAN_ID}_intruder"),
            )
            gateway_intruder_manifest_status, gateway_intruder_manifest_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/plan-evidence-manifests",
                token=gateway_intruder_token,
                body=gateway_plan_evidence_body(f"{GATEWAY_MANIFEST_ID}_intruder"),
            )
            gateway_intruder_memory_status, gateway_intruder_memory_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/memories/propose",
                token=gateway_intruder_token,
                body=gateway_memory_body(f"{GATEWAY_MEMORY_ID}_intruder"),
            )
            gateway_intruder_approval_status, gateway_intruder_approval_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_intruder_token,
                body=gateway_approval_body(f"{GATEWAY_APPROVAL_ID}_intruder"),
            )
            gateway_intruder_audit_status, gateway_intruder_audit_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/audit",
                token=gateway_intruder_token,
                body=gateway_audit_body(f"{GATEWAY_AUDIT_ACTION}.intruder"),
            )
            gateway_intruder_audit_no_run_status, gateway_intruder_audit_no_run_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/audit",
                token=gateway_intruder_token,
                body={
                    "entity_type": "runs",
                    "entity_id": GATEWAY_RUN_ID,
                    "action": f"{GATEWAY_AUDIT_ACTION}.intruder_no_run",
                    "metadata": {"contract": "postgres_http_gateway_audit_write_v1", "raw_omitted": True},
                },
            )
            gateway_readback_status, gateway_readback_payload = request_json(f"{write_base}/api/tasks/{GATEWAY_TASK_ID}?workspace_id={GATEWAY_WORKSPACE_ID}")
            gateway_run_readback_status, gateway_run_readback_payload = request_json(f"{write_base}/api/runs/{GATEWAY_RUN_ID}?workspace_id={GATEWAY_WORKSPACE_ID}")
            agent_block_status, agent_block_payload = request_json(
                f"{write_base}/api/agents",
                method="POST",
                body={"agent_id": BLOCKED_AGENT_ID, "name": "Should stay blocked"},
            )
            gateway_knowledge_block_status, gateway_knowledge_block_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/knowledge/index",
                token=gateway_token,
                body={"rebuild": False},
            )
            runtime_openclaw_prepare_status, runtime_openclaw_prepare_payload = request_json_with_admin(
                f"{write_base}/api/integrations/openclaw/probe",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "workspace_id": RUNTIME_WORKSPACE_ID,
                },
            )
            runtime_openclaw_prepared_action_id = runtime_openclaw_prepare_payload.get("prepared_action_id") or RUNTIME_OPENCLAW_PREPARED_ACTION_ID
            runtime_openclaw_task_id = runtime_openclaw_prepare_payload.get("task_id")
            runtime_openclaw_run_id = runtime_openclaw_prepare_payload.get("run_id")
            runtime_openclaw_tool_id = runtime_openclaw_prepare_payload.get("tool_call_id")
            runtime_openclaw_approval_id = runtime_openclaw_prepare_payload.get("approval_id")
            runtime_openclaw_prompt_hash = runtime_openclaw_prepare_payload.get("prompt_hash")
            runtime_openclaw_premature_status, runtime_openclaw_premature_payload = request_json_with_admin(
                f"{write_base}/api/integrations/openclaw/probe",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_openclaw_prepared_action_id,
                    "prompt_hash": runtime_openclaw_prompt_hash,
                },
            )
            runtime_openclaw_approve_status, runtime_openclaw_approve_payload = request_json_with_admin(
                f"{write_base}/api/approvals/{runtime_openclaw_approval_id}/approve",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={},
            )
            runtime_openclaw_mismatch_status, runtime_openclaw_mismatch_payload = request_json_with_admin(
                f"{write_base}/api/integrations/openclaw/probe",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_openclaw_prepared_action_id,
                    "prompt_hash": "bad-prompt-hash",
                },
            )
            runtime_openclaw_cross_workspace_status, runtime_openclaw_cross_workspace_payload = request_json_with_admin(
                f"{peer_base}/api/integrations/openclaw/probe",
                workspace_id=GATEWAY_WORKSPACE_ID,
                admin_key=GATEWAY_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_openclaw_prepared_action_id,
                    "prompt_hash": runtime_openclaw_prompt_hash,
                },
            )
            runtime_openclaw_race_results = concurrent_admin_requests(
                [write_base, peer_base],
                path="/api/integrations/openclaw/probe",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_openclaw_prepared_action_id,
                    "prompt_hash": runtime_openclaw_prompt_hash,
                },
            )
            runtime_openclaw_resume_status, runtime_openclaw_resume_payload = next(
                ((status, payload) for status, payload in runtime_openclaw_race_results if status == 201),
                (None, {}),
            )
            runtime_openclaw_concurrent_status, runtime_openclaw_concurrent_payload = next(
                ((status, payload) for status, payload in runtime_openclaw_race_results if status != 201),
                (None, {}),
            )
            runtime_openclaw_replay_status, runtime_openclaw_replay_payload = request_json_with_admin(
                f"{write_base}/api/integrations/openclaw/probe",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_openclaw_prepared_action_id,
                    "prompt_hash": runtime_openclaw_prompt_hash,
                },
            )
            runtime_hermes_prepare_status, runtime_hermes_prepare_payload = request_json_with_admin(
                f"{write_base}/api/integrations/hermes/run-task",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "workspace_id": RUNTIME_WORKSPACE_ID,
                },
            )
            runtime_hermes_prepared_action_id = runtime_hermes_prepare_payload.get("prepared_action_id") or RUNTIME_HERMES_PREPARED_ACTION_ID
            runtime_hermes_task_id = runtime_hermes_prepare_payload.get("task_id")
            runtime_hermes_run_id = runtime_hermes_prepare_payload.get("run_id")
            runtime_hermes_tool_id = runtime_hermes_prepare_payload.get("tool_call_id")
            runtime_hermes_approval_id = runtime_hermes_prepare_payload.get("approval_id")
            runtime_hermes_prompt_hash = runtime_hermes_prepare_payload.get("prompt_hash")
            runtime_hermes_premature_status, runtime_hermes_premature_payload = request_json_with_admin(
                f"{write_base}/api/integrations/hermes/run-task",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_hermes_prepared_action_id,
                    "prompt_hash": runtime_hermes_prompt_hash,
                },
            )
            runtime_hermes_approve_status, runtime_hermes_approve_payload = request_json_with_admin(
                f"{write_base}/api/approvals/{runtime_hermes_approval_id}/approve",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={},
            )
            runtime_hermes_mismatch_status, runtime_hermes_mismatch_payload = request_json_with_admin(
                f"{write_base}/api/integrations/hermes/run-task",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_hermes_prepared_action_id,
                    "prompt_hash": "bad-prompt-hash",
                },
            )
            runtime_hermes_cross_workspace_status, runtime_hermes_cross_workspace_payload = request_json_with_admin(
                f"{peer_base}/api/integrations/hermes/run-task",
                workspace_id=GATEWAY_WORKSPACE_ID,
                admin_key=GATEWAY_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_hermes_prepared_action_id,
                    "prompt_hash": runtime_hermes_prompt_hash,
                },
            )
            runtime_hermes_race_results = concurrent_admin_requests(
                [write_base, peer_base],
                path="/api/integrations/hermes/run-task",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_hermes_prepared_action_id,
                    "prompt_hash": runtime_hermes_prompt_hash,
                },
            )
            runtime_hermes_resume_status, runtime_hermes_resume_payload = next(
                ((status, payload) for status, payload in runtime_hermes_race_results if status == 201),
                (None, {}),
            )
            runtime_hermes_concurrent_status, runtime_hermes_concurrent_payload = next(
                ((status, payload) for status, payload in runtime_hermes_race_results if status != 201),
                (None, {}),
            )
            runtime_hermes_replay_status, runtime_hermes_replay_payload = request_json_with_admin(
                f"{write_base}/api/integrations/hermes/run-task",
                workspace_id=RUNTIME_WORKSPACE_ID,
                admin_key=RUNTIME_ADMIN_KEY,
                body={
                    "confirm_run": True,
                    "prepared_action_id": runtime_hermes_prepared_action_id,
                    "prompt_hash": runtime_hermes_prompt_hash,
                },
            )
            stop_server(proc)
            proc = None
            stop_server(peer_proc)
            peer_proc = None

            adapter = connect_postgres_when_ready(dsn, secret=pg_auth)
            task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [TASK_ID])
            blocked_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [BLOCKED_TASK_ID])
            gateway_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_TASK_ID])
            gateway_read_only_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_READ_ONLY_TASK_ID])
            gateway_read_only_claim_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_READ_ONLY_CLAIM_TASK_ID])
            gateway_read_only_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [GATEWAY_READ_ONLY_RUN_ID])
            gateway_read_only_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [GATEWAY_READ_ONLY_TOOL_CALL_ID])
            gateway_read_only_eval_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [f"{GATEWAY_EVALUATION_ID}_read_only"])
            gateway_read_only_artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [GATEWAY_READ_ONLY_ARTIFACT_ID])
            gateway_read_only_plan_row = adapter.fetchone("SELECT * FROM agent_plans WHERE plan_id=?", [GATEWAY_READ_ONLY_PLAN_ID])
            gateway_read_only_manifest_row = adapter.fetchone("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", [GATEWAY_READ_ONLY_MANIFEST_ID])
            gateway_read_only_memory_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [GATEWAY_READ_ONLY_MEMORY_ID])
            gateway_read_only_approval_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [GATEWAY_READ_ONLY_APPROVAL_ID])
            gateway_read_only_heartbeat_agent_row = adapter.fetchone("SELECT * FROM agents WHERE agent_id=?", [GATEWAY_READ_ONLY_HEARTBEAT_AGENT_ID])
            gateway_read_only_audit_row = adapter.fetchone("SELECT * FROM audit_logs WHERE action=?", [GATEWAY_READ_ONLY_AUDIT_ACTION])
            gateway_missing_scope_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_MISSING_SCOPE_TASK_ID])
            gateway_cross_workspace_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_CROSS_WORKSPACE_TASK_ID])
            gateway_header_workspace_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_HEADER_WORKSPACE_TASK_ID])
            gateway_other_agent_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_OTHER_AGENT_TASK_ID])
            gateway_no_token_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_NO_TOKEN_TASK_ID])
            gateway_cross_workspace_plan_row = adapter.fetchone("SELECT * FROM agent_plans WHERE plan_id=?", [GATEWAY_CROSS_WORKSPACE_PLAN_ID])
            gateway_no_token_plan_row = adapter.fetchone("SELECT * FROM agent_plans WHERE plan_id=?", [GATEWAY_NO_TOKEN_PLAN_ID])
            blocked_agent_row = adapter.fetchone("SELECT * FROM agents WHERE agent_id=?", [BLOCKED_AGENT_ID])
            gateway_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [GATEWAY_RUN_ID])
            gateway_heartbeat_agent_row = adapter.fetchone("SELECT * FROM agents WHERE agent_id=?", [GATEWAY_AGENT_ID])
            gateway_terminal_heartbeat_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [GATEWAY_TERMINAL_HEARTBEAT_RUN_ID])
            gateway_completion_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [GATEWAY_COMPLETION_RUN_ID])
            gateway_completion_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_COMPLETION_TASK_ID])
            gateway_completion_agent_row = adapter.fetchone("SELECT * FROM agents WHERE agent_id=?", [GATEWAY_COMPLETION_AGENT_ID])
            gateway_missing_run_scope_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [f"{GATEWAY_RUN_ID}_missing_scope"])
            gateway_intruder_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [f"{GATEWAY_RUN_ID}_intruder"])
            gateway_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [GATEWAY_TOOL_CALL_ID])
            gateway_eval_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [GATEWAY_EVALUATION_ID])
            gateway_artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [GATEWAY_ARTIFACT_ID])
            gateway_plan_row = adapter.fetchone("SELECT * FROM agent_plans WHERE plan_id=?", [GATEWAY_PLAN_ID])
            gateway_manifest_row = adapter.fetchone("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", [GATEWAY_MANIFEST_ID])
            gateway_audit_row = adapter.fetchone("SELECT * FROM audit_logs WHERE action=?", [GATEWAY_AUDIT_ACTION])
            gateway_missing_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [f"{GATEWAY_TOOL_CALL_ID}_missing_scope"])
            gateway_missing_eval_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [f"{GATEWAY_EVALUATION_ID}_missing_scope"])
            gateway_missing_artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [f"{GATEWAY_ARTIFACT_ID}_missing_scope"])
            gateway_missing_plan_row = adapter.fetchone("SELECT * FROM agent_plans WHERE plan_id=?", [f"{GATEWAY_PLAN_ID}_missing_scope"])
            gateway_missing_manifest_row = adapter.fetchone("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", [f"{GATEWAY_MANIFEST_ID}_missing_scope"])
            gateway_missing_audit_scope_row = adapter.fetchone("SELECT * FROM audit_logs WHERE action=?", [f"{GATEWAY_AUDIT_ACTION}.missing_scope"])
            gateway_mismatch_manifest_row = adapter.fetchone("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", [GATEWAY_MISMATCH_MANIFEST_ID])
            gateway_memory_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [GATEWAY_MEMORY_ID])
            gateway_missing_memory_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [f"{GATEWAY_MEMORY_ID}_missing_scope"])
            gateway_memory_cross_workspace_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [f"{GATEWAY_MEMORY_ID}_cross_workspace"])
            gateway_memory_header_workspace_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [f"{GATEWAY_MEMORY_ID}_header_workspace"])
            gateway_memory_no_token_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [GATEWAY_NO_TOKEN_MEMORY_ID])
            gateway_memory_mismatch_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [GATEWAY_MEMORY_MISMATCH_ID])
            gateway_approved_memory_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [GATEWAY_APPROVED_MEMORY_ID])
            gateway_cross_workspace_memory_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [GATEWAY_CROSS_WORKSPACE_MEMORY_ID])
            gateway_other_agent_memory_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [GATEWAY_OTHER_AGENT_MEMORY_ID])
            gateway_approval_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [GATEWAY_APPROVAL_ID])
            gateway_missing_approval_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [f"{GATEWAY_APPROVAL_ID}_missing_scope"])
            gateway_approval_cross_workspace_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [f"{GATEWAY_APPROVAL_ID}_cross_workspace"])
            gateway_approval_header_workspace_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [f"{GATEWAY_APPROVAL_ID}_header_workspace"])
            gateway_approval_no_token_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [GATEWAY_NO_TOKEN_APPROVAL_ID])
            gateway_approval_mismatch_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [GATEWAY_APPROVAL_MISMATCH_ID])
            gateway_approval_tool_mismatch_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [f"{GATEWAY_APPROVAL_ID}_tool_mismatch"])
            gateway_approved_approval_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [GATEWAY_APPROVED_APPROVAL_ID])
            gateway_approval_other_agent_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [f"{GATEWAY_APPROVAL_ID}_other_agent"])
            gateway_intruder_approval_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [f"{GATEWAY_APPROVAL_ID}_intruder"])
            gateway_audit_cross_workspace_row = adapter.fetchone("SELECT * FROM audit_logs WHERE action=?", [f"{GATEWAY_AUDIT_ACTION}.cross_workspace"])
            gateway_audit_no_token_row = adapter.fetchone("SELECT * FROM audit_logs WHERE action=?", [f"{GATEWAY_AUDIT_ACTION}.no_token"])
            gateway_audit_mismatch_row = adapter.fetchone("SELECT * FROM audit_logs WHERE action=?", [f"{GATEWAY_AUDIT_ACTION}.mismatch"])
            gateway_intruder_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [f"{GATEWAY_TOOL_CALL_ID}_intruder"])
            gateway_intruder_eval_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [f"{GATEWAY_EVALUATION_ID}_intruder"])
            gateway_intruder_artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [f"{GATEWAY_ARTIFACT_ID}_intruder"])
            gateway_intruder_plan_row = adapter.fetchone("SELECT * FROM agent_plans WHERE plan_id=?", [f"{GATEWAY_PLAN_ID}_intruder"])
            gateway_intruder_manifest_row = adapter.fetchone("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", [f"{GATEWAY_MANIFEST_ID}_intruder"])
            gateway_intruder_memory_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [f"{GATEWAY_MEMORY_ID}_intruder"])
            gateway_intruder_audit_row = adapter.fetchone("SELECT * FROM audit_logs WHERE action=?", [f"{GATEWAY_AUDIT_ACTION}.intruder"])
            gateway_intruder_audit_no_run_row = adapter.fetchone("SELECT * FROM audit_logs WHERE action=?", [f"{GATEWAY_AUDIT_ACTION}.intruder_no_run"])
            runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE task_id=?", [TASK_ID])["c"]
            audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["tasks", TASK_ID])["c"]
            gateway_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE task_id=?", [GATEWAY_TASK_ID])["c"]
            gateway_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["tasks", GATEWAY_TASK_ID])["c"]
            gateway_run_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=?", [GATEWAY_RUN_ID])["c"]
            gateway_run_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["runs", GATEWAY_RUN_ID])["c"]
            gateway_heartbeat_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE agent_id=? AND event_type=?", [GATEWAY_AGENT_ID, "agent.heartbeat"])["c"]
            gateway_heartbeat_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=? AND action=?", ["agents", GATEWAY_AGENT_ID, "agent_gateway.heartbeat"])["c"]
            gateway_run_heartbeat_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "run.heartbeat"])["c"]
            gateway_run_heartbeat_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=? AND action=?", ["runs", GATEWAY_RUN_ID, "agent_gateway.run_heartbeat"])["c"]
            gateway_run_completion_heartbeat_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_COMPLETION_RUN_ID, "run.heartbeat"])["c"]
            gateway_run_completion_heartbeat_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=? AND action=?", ["runs", GATEWAY_COMPLETION_RUN_ID, "agent_gateway.run_heartbeat"])["c"]
            gateway_tool_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "tool_call.record"])["c"]
            gateway_eval_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "evaluation.submit"])["c"]
            gateway_artifact_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "artifact.record"])["c"]
            gateway_artifact_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["artifacts", GATEWAY_ARTIFACT_ID])["c"]
            gateway_plan_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "agent_plan.create"])["c"]
            gateway_plan_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["agent_plans", GATEWAY_PLAN_ID])["c"]
            gateway_manifest_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "plan_evidence_manifest.create"])["c"]
            gateway_manifest_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["plan_evidence_manifests", GATEWAY_MANIFEST_ID])["c"]
            gateway_memory_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE task_id=? AND event_type=?", [GATEWAY_TASK_ID, "memory.propose"])["c"]
            gateway_memory_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["memories", GATEWAY_MEMORY_ID])["c"]
            gateway_approval_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "approval.request"])["c"]
            gateway_approval_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["approvals", GATEWAY_APPROVAL_ID])["c"]
            gateway_approval_run_wait_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=? AND action=?", ["runs", GATEWAY_RUN_ID, "agent_gateway.run_waiting_approval"])["c"]
            gateway_approval_task_wait_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=? AND action=?", ["tasks", GATEWAY_TASK_ID, "agent_gateway.task_waiting_approval"])["c"]
            gateway_audit_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "audit.emit"])["c"]
            gateway_token_last_used = adapter.fetchone("SELECT last_used_at,last_heartbeat_at FROM agent_gateway_tokens WHERE token_id=?", [GATEWAY_TOKEN_ID])
            runtime_openclaw_action_row = adapter.fetchone("SELECT * FROM prepared_actions WHERE prepared_action_id=?", [runtime_openclaw_prepared_action_id])
            runtime_openclaw_approval_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [runtime_openclaw_approval_id])
            runtime_openclaw_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [runtime_openclaw_run_id])
            runtime_openclaw_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [runtime_openclaw_task_id])
            runtime_openclaw_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [runtime_openclaw_tool_id])
            runtime_openclaw_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=?", [runtime_openclaw_run_id])["c"]
            runtime_openclaw_run_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["runs", runtime_openclaw_run_id])["c"]
            runtime_openclaw_action_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["prepared_actions", runtime_openclaw_prepared_action_id])["c"]
            runtime_openclaw_claim_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=? AND action=?", ["prepared_actions", runtime_openclaw_prepared_action_id, "runtime.openclaw_probe.execution_claimed"])["c"]
            runtime_hermes_action_row = adapter.fetchone("SELECT * FROM prepared_actions WHERE prepared_action_id=?", [runtime_hermes_prepared_action_id])
            runtime_hermes_approval_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [runtime_hermes_approval_id])
            runtime_hermes_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [runtime_hermes_run_id])
            runtime_hermes_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [runtime_hermes_task_id])
            runtime_hermes_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [runtime_hermes_tool_id])
            runtime_hermes_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=?", [runtime_hermes_run_id])["c"]
            runtime_hermes_run_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["runs", runtime_hermes_run_id])["c"]
            runtime_hermes_action_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["prepared_actions", runtime_hermes_prepared_action_id])["c"]
            runtime_hermes_claim_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=? AND action=?", ["prepared_actions", runtime_hermes_prepared_action_id, "runtime.run_task.execution_claimed"])["c"]
            runtime_openclaw_provider_call_count = openclaw_call_count(fake_openclaw_log)
            runtime_hermes_provider_call_count = len(FakeHermesHandler.calls)

            failures: list[str] = []
            if read_only_status_code != 200 or read_only_backend.get("mode") != "read_only_http" or read_only_backend.get("writes_allowed") is not False:
                failures.append(f"read_only_backend_mismatch:{read_only_backend}")
            if blocked_status != 503 or blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"read_only_write_block_mismatch:{blocked_status}:{blocked_payload}")
            if gateway_blocked_status != 503 or gateway_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_write_block_mismatch:{gateway_blocked_status}:{gateway_blocked_payload}")
            if gateway_claim_blocked_status != 503 or gateway_claim_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_claim_block_mismatch:{gateway_claim_blocked_status}:{gateway_claim_blocked_payload}")
            if gateway_run_start_blocked_status != 503 or gateway_run_start_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_run_start_block_mismatch:{gateway_run_start_blocked_status}:{gateway_run_start_blocked_payload}")
            if gateway_tool_blocked_status != 503 or gateway_tool_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_tool_block_mismatch:{gateway_tool_blocked_status}:{gateway_tool_blocked_payload}")
            if gateway_eval_blocked_status != 503 or gateway_eval_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_eval_block_mismatch:{gateway_eval_blocked_status}:{gateway_eval_blocked_payload}")
            if gateway_artifact_blocked_status != 503 or gateway_artifact_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_artifact_block_mismatch:{gateway_artifact_blocked_status}:{gateway_artifact_blocked_payload}")
            if gateway_plan_blocked_status != 503 or gateway_plan_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_plan_block_mismatch:{gateway_plan_blocked_status}:{gateway_plan_blocked_payload}")
            if gateway_manifest_blocked_status != 503 or gateway_manifest_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_manifest_block_mismatch:{gateway_manifest_blocked_status}:{gateway_manifest_blocked_payload}")
            if gateway_memory_blocked_status != 503 or gateway_memory_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_memory_block_mismatch:{gateway_memory_blocked_status}:{gateway_memory_blocked_payload}")
            if gateway_approval_blocked_status != 503 or gateway_approval_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_approval_block_mismatch:{gateway_approval_blocked_status}:{gateway_approval_blocked_payload}")
            if gateway_heartbeat_blocked_status != 503 or gateway_heartbeat_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_heartbeat_block_mismatch:{gateway_heartbeat_blocked_status}:{gateway_heartbeat_blocked_payload}")
            if gateway_run_heartbeat_blocked_status != 503 or gateway_run_heartbeat_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_run_heartbeat_block_mismatch:{gateway_run_heartbeat_blocked_status}:{gateway_run_heartbeat_blocked_payload}")
            if gateway_audit_blocked_status != 503 or gateway_audit_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_audit_block_mismatch:{gateway_audit_blocked_status}:{gateway_audit_blocked_payload}")
            if runtime_openclaw_read_only_status != 503 or runtime_openclaw_read_only_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"runtime_openclaw_read_only_not_blocked:{runtime_openclaw_read_only_status}:{runtime_openclaw_read_only_payload}")
            if runtime_hermes_read_only_status != 503 or runtime_hermes_read_only_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"runtime_hermes_read_only_not_blocked:{runtime_hermes_read_only_status}:{runtime_hermes_read_only_payload}")
            if runtime_approval_read_only_status != 503 or runtime_approval_read_only_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"runtime_approval_read_only_not_blocked:{runtime_approval_read_only_status}:{runtime_approval_read_only_payload}")
            if blocked_task_row:
                failures.append("read_only_post_created_blocked_task")
            if gateway_read_only_task_row:
                failures.append("read_only_post_created_blocked_gateway_task")
            if gateway_read_only_claim_task_row:
                failures.append("read_only_claim_created_or_mutated_gateway_task")
            if gateway_read_only_run_row:
                failures.append("read_only_run_start_created_gateway_run")
            if gateway_read_only_tool_row or gateway_read_only_eval_row or gateway_read_only_artifact_row:
                failures.append("read_only_evidence_write_created_row")
            if gateway_read_only_plan_row or gateway_read_only_manifest_row:
                failures.append("read_only_plan_write_created_row")
            if gateway_read_only_memory_row:
                failures.append("read_only_memory_write_created_row")
            if gateway_read_only_approval_row:
                failures.append("read_only_approval_write_created_row")
            if gateway_read_only_heartbeat_agent_row:
                failures.append("read_only_heartbeat_created_agent_row")
            if gateway_read_only_audit_row:
                failures.append("read_only_audit_write_created_row")
            if write_status_code != 200 or write_backend.get("mode") != "experimental_write_http" or write_backend.get("writes_allowed") is not True:
                failures.append(f"write_backend_mismatch:{write_backend}")
            if peer_status_code != 200 or peer_backend.get("mode") != "experimental_write_http" or peer_backend.get("writes_allowed") is not True:
                failures.append(f"peer_write_backend_mismatch:{peer_backend}")
            read_only_runtime_gate = read_only_backend.get("runtime_write_gate") or {}
            if read_only_runtime_gate.get("status") != "read_only" or read_only_runtime_gate.get("allowlisted_routes"):
                failures.append(f"read_only_runtime_write_gate_mismatch:{read_only_runtime_gate}")
            write_runtime_gate = write_backend.get("runtime_write_gate") or {}
            write_runtime_contracts = set(write_runtime_gate.get("contracts") or []) | set(write_backend.get("contracts") or [])
            expected_runtime_contracts = {
                "postgres_http_runtime_prepared_action_write_v1",
                "postgres_http_runtime_approval_decision_write_v1",
            }
            if write_runtime_gate.get("status") != "active" or not expected_runtime_contracts.issubset(write_runtime_contracts):
                failures.append(f"write_runtime_gate_contract_mismatch:{write_runtime_gate}")
            expected_runtime_routes = {
                "POST /api/integrations/openclaw/probe",
                "POST /api/integrations/hermes/run-task",
                "POST /api/approvals/:approval_id/approve",
            }
            runtime_routes = {
                f"{route.get('method')} {route.get('path')}"
                for route in write_runtime_gate.get("allowlisted_routes") or []
                if isinstance(route, dict)
            }
            if runtime_routes != expected_runtime_routes:
                failures.append(f"write_runtime_gate_routes_mismatch:{sorted(runtime_routes)}")
            if write_runtime_gate.get("approval_decision") != "row_gated_prepared_action_only" or write_runtime_gate.get("non_fixed_runtime_writes") != "blocked":
                failures.append(f"write_runtime_gate_safety_mismatch:{write_runtime_gate}")
            if write_runtime_gate.get("exact_resume_required") is not True or write_runtime_gate.get("live_execution_performed") is not False:
                failures.append(f"write_runtime_gate_resume_or_live_mismatch:{write_runtime_gate}")
            if create_status != 201 or create_payload.get("task_id") != TASK_ID or create_payload.get("token_omitted") is not True:
                failures.append(f"task_create_payload_mismatch:{create_status}:{create_payload}")
            if readback_status != 200 or readback_payload.get("task", {}).get("task_id") != TASK_ID:
                failures.append(f"task_readback_mismatch:{readback_status}:{readback_payload}")
            if gateway_missing_heartbeat_scope_status != 403 or "agents:heartbeat" not in json.dumps(gateway_missing_heartbeat_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_heartbeat_scope_mismatch:{gateway_missing_heartbeat_scope_status}:{gateway_missing_heartbeat_scope_payload}")
            if gateway_heartbeat_cross_workspace_status != 403 or "workspace" not in json.dumps(gateway_heartbeat_cross_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_heartbeat_cross_workspace_mismatch:{gateway_heartbeat_cross_workspace_status}:{gateway_heartbeat_cross_workspace_payload}")
            if gateway_heartbeat_header_workspace_status != 403 or "workspace" not in json.dumps(gateway_heartbeat_header_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_heartbeat_header_workspace_mismatch:{gateway_heartbeat_header_workspace_status}:{gateway_heartbeat_header_workspace_payload}")
            if gateway_heartbeat_other_agent_status != 403 or "another agent" not in json.dumps(gateway_heartbeat_other_agent_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_heartbeat_other_agent_mismatch:{gateway_heartbeat_other_agent_status}:{gateway_heartbeat_other_agent_payload}")
            if gateway_heartbeat_intruder_status != 403 or "another agent" not in json.dumps(gateway_heartbeat_intruder_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_heartbeat_intruder_mismatch:{gateway_heartbeat_intruder_status}:{gateway_heartbeat_intruder_payload}")
            if gateway_heartbeat_no_token_status != 401 or "token" not in json.dumps(gateway_heartbeat_no_token_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_heartbeat_no_token_mismatch:{gateway_heartbeat_no_token_status}:{gateway_heartbeat_no_token_payload}")
            if gateway_heartbeat_write_status != 200 or gateway_heartbeat_write_payload.get("agent_id") != GATEWAY_AGENT_ID or gateway_heartbeat_write_payload.get("status") != "running":
                failures.append(f"gateway_heartbeat_write_mismatch:{gateway_heartbeat_write_status}:{gateway_heartbeat_write_payload}")
            if gateway_missing_scope_status != 403 or "tasks:create" not in json.dumps(gateway_missing_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_scope_mismatch:{gateway_missing_scope_status}:{gateway_missing_scope_payload}")
            if gateway_cross_workspace_status != 403 or "workspace" not in json.dumps(gateway_cross_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_cross_workspace_mismatch:{gateway_cross_workspace_status}:{gateway_cross_workspace_payload}")
            if gateway_header_workspace_status != 403 or "workspace" not in json.dumps(gateway_header_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_header_workspace_mismatch:{gateway_header_workspace_status}:{gateway_header_workspace_payload}")
            if gateway_other_agent_status != 403 or "another agent" not in json.dumps(gateway_other_agent_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_other_agent_mismatch:{gateway_other_agent_status}:{gateway_other_agent_payload}")
            if gateway_no_token_status != 401 or "token" not in json.dumps(gateway_no_token_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_no_token_mismatch:{gateway_no_token_status}:{gateway_no_token_payload}")
            if gateway_create_status != 201 or gateway_create_payload.get("task_id") != GATEWAY_TASK_ID or gateway_create_payload.get("token_omitted") is not True:
                failures.append(f"gateway_task_create_payload_mismatch:{gateway_create_status}:{gateway_create_payload}")
            gateway_task = gateway_create_payload.get("task") or {}
            if gateway_task.get("workspace_id") != GATEWAY_WORKSPACE_ID or gateway_task.get("owner_agent_id") != GATEWAY_AGENT_ID:
                failures.append(f"gateway_task_binding_mismatch:{gateway_task}")
            if gateway_missing_claim_scope_status != 403 or "tasks:claim" not in json.dumps(gateway_missing_claim_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_claim_scope_mismatch:{gateway_missing_claim_scope_status}:{gateway_missing_claim_scope_payload}")
            if gateway_claim_status != 200 or gateway_claim_payload.get("claimed_by") != GATEWAY_AGENT_ID:
                failures.append(f"gateway_claim_payload_mismatch:{gateway_claim_status}:{gateway_claim_payload}")
            if gateway_missing_run_scope_status != 403 or "runs:write" not in json.dumps(gateway_missing_run_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_run_scope_mismatch:{gateway_missing_run_scope_status}:{gateway_missing_run_scope_payload}")
            gateway_run = gateway_run_start_payload.get("run") or {}
            if gateway_run_start_status != 201 or gateway_run.get("run_id") != GATEWAY_RUN_ID or gateway_run.get("workspace_id") != GATEWAY_WORKSPACE_ID:
                failures.append(f"gateway_run_start_payload_mismatch:{gateway_run_start_status}:{gateway_run_start_payload}")
            if gateway_missing_run_heartbeat_scope_status != 403 or "runs:write" not in json.dumps(gateway_missing_run_heartbeat_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_run_heartbeat_scope_mismatch:{gateway_missing_run_heartbeat_scope_status}:{gateway_missing_run_heartbeat_scope_payload}")
            if gateway_run_heartbeat_no_token_status != 401 or "token" not in json.dumps(gateway_run_heartbeat_no_token_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_run_heartbeat_no_token_mismatch:{gateway_run_heartbeat_no_token_status}:{gateway_run_heartbeat_no_token_payload}")
            if gateway_run_heartbeat_cross_workspace_status != 403 or "workspace" not in json.dumps(gateway_run_heartbeat_cross_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_run_heartbeat_cross_workspace_mismatch:{gateway_run_heartbeat_cross_workspace_status}:{gateway_run_heartbeat_cross_workspace_payload}")
            if gateway_run_heartbeat_header_workspace_status != 403 or "workspace" not in json.dumps(gateway_run_heartbeat_header_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_run_heartbeat_header_workspace_mismatch:{gateway_run_heartbeat_header_workspace_status}:{gateway_run_heartbeat_header_workspace_payload}")
            if gateway_run_heartbeat_task_mismatch_status != 403 or "task_id" not in json.dumps(gateway_run_heartbeat_task_mismatch_payload, ensure_ascii=False):
                failures.append(f"gateway_run_heartbeat_task_mismatch_not_blocked:{gateway_run_heartbeat_task_mismatch_status}:{gateway_run_heartbeat_task_mismatch_payload}")
            if gateway_run_heartbeat_intruder_status != 403 or "another agent" not in json.dumps(gateway_run_heartbeat_intruder_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_run_heartbeat_intruder_mismatch:{gateway_run_heartbeat_intruder_status}:{gateway_run_heartbeat_intruder_payload}")
            if gateway_run_heartbeat_terminal_revival_status != 409 or "terminal" not in json.dumps(gateway_run_heartbeat_terminal_revival_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_run_heartbeat_terminal_revival_not_blocked:{gateway_run_heartbeat_terminal_revival_status}:{gateway_run_heartbeat_terminal_revival_payload}")
            gateway_run_heartbeat = gateway_run_heartbeat_write_payload.get("run") or {}
            if gateway_run_heartbeat_write_status != 200 or gateway_run_heartbeat.get("run_id") != GATEWAY_RUN_ID or gateway_run_heartbeat.get("status") != "running" or gateway_run_heartbeat.get("output_summary") != "Postgres Gateway run heartbeat write proof.":
                failures.append(f"gateway_run_heartbeat_write_mismatch:{gateway_run_heartbeat_write_status}:{gateway_run_heartbeat_write_payload}")
            gateway_run_completion_heartbeat = gateway_run_completion_heartbeat_payload.get("run") or {}
            if gateway_run_completion_heartbeat_status != 200 or gateway_run_completion_heartbeat.get("run_id") != GATEWAY_COMPLETION_RUN_ID or gateway_run_completion_heartbeat.get("status") != "completed" or gateway_run_completion_heartbeat.get("output_summary") != "Postgres Gateway run completion heartbeat proof.":
                failures.append(f"gateway_run_completion_heartbeat_mismatch:{gateway_run_completion_heartbeat_status}:{gateway_run_completion_heartbeat_payload}")
            if gateway_intruder_claim_status != 403 or "another agent" not in json.dumps(gateway_intruder_claim_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_claim_mismatch:{gateway_intruder_claim_status}:{gateway_intruder_claim_payload}")
            if gateway_intruder_run_status != 403 or "another agent" not in json.dumps(gateway_intruder_run_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_run_mismatch:{gateway_intruder_run_status}:{gateway_intruder_run_payload}")
            if gateway_missing_tool_scope_status != 403 or "toolcalls:write" not in json.dumps(gateway_missing_tool_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_tool_scope_mismatch:{gateway_missing_tool_scope_status}:{gateway_missing_tool_scope_payload}")
            if gateway_tool_write_status != 201 or (gateway_tool_write_payload.get("tool_call") or {}).get("tool_call_id") != GATEWAY_TOOL_CALL_ID:
                failures.append(f"gateway_tool_write_mismatch:{gateway_tool_write_status}:{gateway_tool_write_payload}")
            if gateway_missing_eval_scope_status != 403 or "evaluations:submit" not in json.dumps(gateway_missing_eval_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_eval_scope_mismatch:{gateway_missing_eval_scope_status}:{gateway_missing_eval_scope_payload}")
            if gateway_eval_write_status != 201 or (gateway_eval_write_payload.get("evaluation") or {}).get("evaluation_id") != GATEWAY_EVALUATION_ID:
                failures.append(f"gateway_eval_write_mismatch:{gateway_eval_write_status}:{gateway_eval_write_payload}")
            if gateway_missing_artifact_scope_status != 403 or "artifacts:write" not in json.dumps(gateway_missing_artifact_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_artifact_scope_mismatch:{gateway_missing_artifact_scope_status}:{gateway_missing_artifact_scope_payload}")
            if gateway_artifact_write_status != 201 or (gateway_artifact_write_payload.get("artifact") or {}).get("artifact_id") != GATEWAY_ARTIFACT_ID:
                failures.append(f"gateway_artifact_write_mismatch:{gateway_artifact_write_status}:{gateway_artifact_write_payload}")
            if gateway_missing_plan_scope_status != 403 or "agent_plans:write" not in json.dumps(gateway_missing_plan_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_plan_scope_mismatch:{gateway_missing_plan_scope_status}:{gateway_missing_plan_scope_payload}")
            if gateway_plan_cross_workspace_status != 403 or "workspace" not in json.dumps(gateway_plan_cross_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_plan_cross_workspace_mismatch:{gateway_plan_cross_workspace_status}:{gateway_plan_cross_workspace_payload}")
            if gateway_plan_no_token_status != 401 or "token" not in json.dumps(gateway_plan_no_token_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_plan_no_token_mismatch:{gateway_plan_no_token_status}:{gateway_plan_no_token_payload}")
            if gateway_plan_write_status != 201 or (gateway_plan_write_payload.get("agent_plan") or {}).get("plan_id") != GATEWAY_PLAN_ID:
                failures.append(f"gateway_plan_write_mismatch:{gateway_plan_write_status}:{gateway_plan_write_payload}")
            if gateway_manifest_mismatch_status != 403 or "task_id" not in json.dumps(gateway_manifest_mismatch_payload, ensure_ascii=False):
                failures.append(f"gateway_manifest_mismatch_not_blocked:{gateway_manifest_mismatch_status}:{gateway_manifest_mismatch_payload}")
            if gateway_missing_manifest_scope_status != 403 or "plan_evidence:write" not in json.dumps(gateway_missing_manifest_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_manifest_scope_mismatch:{gateway_missing_manifest_scope_status}:{gateway_missing_manifest_scope_payload}")
            gateway_manifest = gateway_manifest_write_payload.get("manifest") or {}
            gateway_manifest_verification = gateway_manifest_write_payload.get("verification") or {}
            if gateway_manifest_write_status != 201 or gateway_manifest.get("manifest_id") != GATEWAY_MANIFEST_ID or gateway_manifest_verification.get("pass") is not True:
                failures.append(f"gateway_manifest_write_mismatch:{gateway_manifest_write_status}:{gateway_manifest_write_payload}")
            if gateway_missing_memory_scope_status != 403 or "memories:propose" not in json.dumps(gateway_missing_memory_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_memory_scope_mismatch:{gateway_missing_memory_scope_status}:{gateway_missing_memory_scope_payload}")
            if gateway_memory_cross_workspace_status != 403 or "workspace" not in json.dumps(gateway_memory_cross_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_memory_cross_workspace_mismatch:{gateway_memory_cross_workspace_status}:{gateway_memory_cross_workspace_payload}")
            if gateway_memory_header_workspace_status != 403 or "workspace" not in json.dumps(gateway_memory_header_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_memory_header_workspace_mismatch:{gateway_memory_header_workspace_status}:{gateway_memory_header_workspace_payload}")
            if gateway_memory_no_token_status != 401 or "token" not in json.dumps(gateway_memory_no_token_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_memory_no_token_mismatch:{gateway_memory_no_token_status}:{gateway_memory_no_token_payload}")
            if gateway_memory_mismatch_status != 403 or "task_id" not in json.dumps(gateway_memory_mismatch_payload, ensure_ascii=False):
                failures.append(f"gateway_memory_mismatch_not_blocked:{gateway_memory_mismatch_status}:{gateway_memory_mismatch_payload}")
            if gateway_memory_approved_overwrite_status != 403 or "candidate" not in json.dumps(gateway_memory_approved_overwrite_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_memory_approved_overwrite_not_blocked:{gateway_memory_approved_overwrite_status}:{gateway_memory_approved_overwrite_payload}")
            if gateway_memory_existing_cross_workspace_status != 403 or "workspace" not in json.dumps(gateway_memory_existing_cross_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_memory_existing_cross_workspace_not_blocked:{gateway_memory_existing_cross_workspace_status}:{gateway_memory_existing_cross_workspace_payload}")
            if gateway_memory_other_agent_overwrite_status != 403 or "another agent" not in json.dumps(gateway_memory_other_agent_overwrite_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_memory_other_agent_overwrite_not_blocked:{gateway_memory_other_agent_overwrite_status}:{gateway_memory_other_agent_overwrite_payload}")
            if gateway_memory_write_status != 201 or (gateway_memory_write_payload.get("memory") or {}).get("memory_id") != GATEWAY_MEMORY_ID:
                failures.append(f"gateway_memory_write_mismatch:{gateway_memory_write_status}:{gateway_memory_write_payload}")
            if gateway_missing_approval_scope_status != 403 or "approvals:request" not in json.dumps(gateway_missing_approval_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_approval_scope_mismatch:{gateway_missing_approval_scope_status}:{gateway_missing_approval_scope_payload}")
            if gateway_approval_cross_workspace_status != 403 or "workspace" not in json.dumps(gateway_approval_cross_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_approval_cross_workspace_mismatch:{gateway_approval_cross_workspace_status}:{gateway_approval_cross_workspace_payload}")
            if gateway_approval_header_workspace_status != 403 or "workspace" not in json.dumps(gateway_approval_header_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_approval_header_workspace_mismatch:{gateway_approval_header_workspace_status}:{gateway_approval_header_workspace_payload}")
            if gateway_approval_no_token_status != 401 or "token" not in json.dumps(gateway_approval_no_token_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_approval_no_token_mismatch:{gateway_approval_no_token_status}:{gateway_approval_no_token_payload}")
            if gateway_approval_mismatch_status != 403 or "task_id" not in json.dumps(gateway_approval_mismatch_payload, ensure_ascii=False):
                failures.append(f"gateway_approval_mismatch_not_blocked:{gateway_approval_mismatch_status}:{gateway_approval_mismatch_payload}")
            if gateway_approval_tool_mismatch_status != 403 or "tool_call_id" not in json.dumps(gateway_approval_tool_mismatch_payload, ensure_ascii=False):
                failures.append(f"gateway_approval_tool_mismatch_not_blocked:{gateway_approval_tool_mismatch_status}:{gateway_approval_tool_mismatch_payload}")
            if gateway_approval_approved_overwrite_status != 403 or "pending" not in json.dumps(gateway_approval_approved_overwrite_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_approval_approved_overwrite_not_blocked:{gateway_approval_approved_overwrite_status}:{gateway_approval_approved_overwrite_payload}")
            if gateway_approval_other_agent_status != 403 or "another agent" not in json.dumps(gateway_approval_other_agent_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_approval_other_agent_mismatch:{gateway_approval_other_agent_status}:{gateway_approval_other_agent_payload}")
            if gateway_approval_write_status != 201 or (gateway_approval_write_payload.get("approval") or {}).get("approval_id") != GATEWAY_APPROVAL_ID:
                failures.append(f"gateway_approval_write_mismatch:{gateway_approval_write_status}:{gateway_approval_write_payload}")
            if gateway_missing_audit_scope_status != 403 or "audit:write" not in json.dumps(gateway_missing_audit_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_audit_scope_mismatch:{gateway_missing_audit_scope_status}:{gateway_missing_audit_scope_payload}")
            if gateway_audit_cross_workspace_status != 403 or "workspace" not in json.dumps(gateway_audit_cross_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_audit_cross_workspace_mismatch:{gateway_audit_cross_workspace_status}:{gateway_audit_cross_workspace_payload}")
            if gateway_audit_no_token_status != 401 or "token" not in json.dumps(gateway_audit_no_token_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_audit_no_token_mismatch:{gateway_audit_no_token_status}:{gateway_audit_no_token_payload}")
            if gateway_audit_mismatch_status != 403 or "task_id" not in json.dumps(gateway_audit_mismatch_payload, ensure_ascii=False):
                failures.append(f"gateway_audit_mismatch_not_blocked:{gateway_audit_mismatch_status}:{gateway_audit_mismatch_payload}")
            if gateway_audit_write_status != 201 or gateway_audit_write_payload.get("emitted") is not True or gateway_audit_write_payload.get("token_omitted") is not True:
                failures.append(f"gateway_audit_write_mismatch:{gateway_audit_write_status}:{gateway_audit_write_payload}")
            if gateway_intruder_tool_status != 403 or "another agent" not in json.dumps(gateway_intruder_tool_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_tool_mismatch:{gateway_intruder_tool_status}:{gateway_intruder_tool_payload}")
            if gateway_intruder_eval_status != 403 or "another agent" not in json.dumps(gateway_intruder_eval_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_eval_mismatch:{gateway_intruder_eval_status}:{gateway_intruder_eval_payload}")
            if gateway_intruder_artifact_status != 403 or "another agent" not in json.dumps(gateway_intruder_artifact_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_artifact_mismatch:{gateway_intruder_artifact_status}:{gateway_intruder_artifact_payload}")
            if gateway_intruder_plan_status != 403 or "another agent" not in json.dumps(gateway_intruder_plan_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_plan_mismatch:{gateway_intruder_plan_status}:{gateway_intruder_plan_payload}")
            if gateway_intruder_manifest_status != 403 or "another agent" not in json.dumps(gateway_intruder_manifest_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_manifest_mismatch:{gateway_intruder_manifest_status}:{gateway_intruder_manifest_payload}")
            if gateway_intruder_memory_status != 403 or "another agent" not in json.dumps(gateway_intruder_memory_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_memory_mismatch:{gateway_intruder_memory_status}:{gateway_intruder_memory_payload}")
            if gateway_intruder_approval_status != 403 or "another agent" not in json.dumps(gateway_intruder_approval_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_approval_mismatch:{gateway_intruder_approval_status}:{gateway_intruder_approval_payload}")
            if gateway_intruder_audit_status != 403 or "another agent" not in json.dumps(gateway_intruder_audit_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_audit_mismatch:{gateway_intruder_audit_status}:{gateway_intruder_audit_payload}")
            if gateway_intruder_audit_no_run_status != 403 or "another agent" not in json.dumps(gateway_intruder_audit_no_run_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_audit_no_run_mismatch:{gateway_intruder_audit_no_run_status}:{gateway_intruder_audit_no_run_payload}")
            if gateway_readback_status != 200 or gateway_readback_payload.get("task", {}).get("task_id") != GATEWAY_TASK_ID:
                failures.append(f"gateway_task_readback_mismatch:{gateway_readback_status}:{gateway_readback_payload}")
            if gateway_run_readback_status != 200 or gateway_run_readback_payload.get("run", {}).get("run_id") != GATEWAY_RUN_ID:
                failures.append(f"gateway_run_readback_mismatch:{gateway_run_readback_status}:{gateway_run_readback_payload}")
            if agent_block_status != 503 or agent_block_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"non_allowlisted_write_not_blocked:{agent_block_status}:{agent_block_payload}")
            if gateway_knowledge_block_status != 503 or gateway_knowledge_block_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_non_allowlisted_write_not_blocked:{gateway_knowledge_block_status}:{gateway_knowledge_block_payload}")
            if runtime_non_prepared_approval_status != 503 or runtime_non_prepared_approval_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"runtime_non_prepared_approval_not_blocked:{runtime_non_prepared_approval_status}:{runtime_non_prepared_approval_payload}")
            if runtime_openclaw_prepare_status != 202 or not runtime_openclaw_prepare_payload.get("prepared_action_id") or runtime_openclaw_prepare_payload.get("provider_call_performed") is not False or runtime_openclaw_prepare_payload.get("raw_prompt_omitted") is not True:
                failures.append(f"runtime_openclaw_prepare_mismatch:{runtime_openclaw_prepare_status}:{runtime_openclaw_prepare_payload}")
            if runtime_openclaw_premature_status != 428 or runtime_openclaw_premature_payload.get("error") != "approval_required":
                failures.append(f"runtime_openclaw_premature_not_blocked:{runtime_openclaw_premature_status}:{runtime_openclaw_premature_payload}")
            if runtime_openclaw_approve_status != 200 or runtime_openclaw_approve_payload.get("decision") != "approved":
                failures.append(f"runtime_openclaw_approve_mismatch:{runtime_openclaw_approve_status}:{runtime_openclaw_approve_payload}")
            if runtime_openclaw_mismatch_status != 409 or runtime_openclaw_mismatch_payload.get("error") != "prepared_action_prompt_hash_mismatch":
                failures.append(f"runtime_openclaw_hash_mismatch_not_blocked:{runtime_openclaw_mismatch_status}:{runtime_openclaw_mismatch_payload}")
            if runtime_openclaw_cross_workspace_status != 404 or runtime_openclaw_cross_workspace_payload.get("error") != "prepared_action_not_found":
                failures.append(f"runtime_openclaw_cross_workspace_not_hidden:{runtime_openclaw_cross_workspace_status}:{runtime_openclaw_cross_workspace_payload}")
            if runtime_openclaw_resume_status != 201 or runtime_openclaw_resume_payload.get("ok") is not True or runtime_openclaw_resume_payload.get("created") is not True or runtime_openclaw_resume_payload.get("prepared_action_status") != "consumed" or runtime_openclaw_resume_payload.get("provider_call_performed") is not True:
                failures.append(f"runtime_openclaw_resume_mismatch:{runtime_openclaw_resume_status}:{runtime_openclaw_resume_payload}")
            if runtime_openclaw_concurrent_status != 409 or runtime_openclaw_concurrent_payload.get("error") not in {"prepared_action_execution_in_progress", "prepared_action_already_consumed"}:
                failures.append(f"runtime_openclaw_concurrent_loser_mismatch:{runtime_openclaw_concurrent_status}:{runtime_openclaw_concurrent_payload}")
            if runtime_openclaw_replay_status != 409 or runtime_openclaw_replay_payload.get("error") != "prepared_action_already_consumed":
                failures.append(f"runtime_openclaw_replay_not_blocked:{runtime_openclaw_replay_status}:{runtime_openclaw_replay_payload}")
            if runtime_hermes_prepare_status != 202 or not runtime_hermes_prepare_payload.get("prepared_action_id") or runtime_hermes_prepare_payload.get("provider_call_performed") is not False or runtime_hermes_prepare_payload.get("raw_prompt_omitted") is not True:
                failures.append(f"runtime_hermes_prepare_mismatch:{runtime_hermes_prepare_status}:{runtime_hermes_prepare_payload}")
            if runtime_hermes_premature_status != 428 or runtime_hermes_premature_payload.get("error") != "approval_required":
                failures.append(f"runtime_hermes_premature_not_blocked:{runtime_hermes_premature_status}:{runtime_hermes_premature_payload}")
            if runtime_hermes_approve_status != 200 or runtime_hermes_approve_payload.get("decision") != "approved":
                failures.append(f"runtime_hermes_approve_mismatch:{runtime_hermes_approve_status}:{runtime_hermes_approve_payload}")
            if runtime_hermes_mismatch_status != 409 or runtime_hermes_mismatch_payload.get("error") != "prepared_action_prompt_hash_mismatch":
                failures.append(f"runtime_hermes_hash_mismatch_not_blocked:{runtime_hermes_mismatch_status}:{runtime_hermes_mismatch_payload}")
            if runtime_hermes_cross_workspace_status != 404 or runtime_hermes_cross_workspace_payload.get("error") != "prepared_action_not_found":
                failures.append(f"runtime_hermes_cross_workspace_not_hidden:{runtime_hermes_cross_workspace_status}:{runtime_hermes_cross_workspace_payload}")
            if runtime_hermes_resume_status != 201 or runtime_hermes_resume_payload.get("ok") is not True or runtime_hermes_resume_payload.get("created") is not True or runtime_hermes_resume_payload.get("prepared_action_status") != "consumed" or runtime_hermes_resume_payload.get("provider_call_performed") is not True:
                failures.append(f"runtime_hermes_resume_mismatch:{runtime_hermes_resume_status}:{runtime_hermes_resume_payload}")
            if runtime_hermes_concurrent_status != 409 or runtime_hermes_concurrent_payload.get("error") not in {"prepared_action_execution_in_progress", "prepared_action_already_consumed"}:
                failures.append(f"runtime_hermes_concurrent_loser_mismatch:{runtime_hermes_concurrent_status}:{runtime_hermes_concurrent_payload}")
            if runtime_hermes_replay_status != 409 or runtime_hermes_replay_payload.get("error") != "prepared_action_already_consumed":
                failures.append(f"runtime_hermes_replay_not_blocked:{runtime_hermes_replay_status}:{runtime_hermes_replay_payload}")
            if runtime_openclaw_provider_call_count != 1:
                failures.append(f"runtime_openclaw_provider_call_count_mismatch:{runtime_openclaw_provider_call_count}")
            if runtime_hermes_provider_call_count != 1:
                failures.append(f"runtime_hermes_provider_call_count_mismatch:{runtime_hermes_provider_call_count}")
            if int(runtime_openclaw_claim_audit_count or 0) != 1:
                failures.append(f"runtime_openclaw_claim_audit_count_mismatch:{runtime_openclaw_claim_audit_count}")
            if int(runtime_hermes_claim_audit_count or 0) != 1:
                failures.append(f"runtime_hermes_claim_audit_count_mismatch:{runtime_hermes_claim_audit_count}")
            if blocked_agent_row:
                failures.append("non_allowlisted_agent_write_created_row")
            if not task_row or task_row.get("workspace_id") != WORKSPACE_ID or task_row.get("owner_agent_id") != AGENT_ID:
                failures.append(f"postgres_task_row_mismatch:{task_row}")
            if int(runtime_event_count or 0) < 1:
                failures.append("postgres_runtime_event_missing")
            if int(audit_count or 0) < 1:
                failures.append("postgres_audit_missing")
            if not gateway_task_row or gateway_task_row.get("workspace_id") != GATEWAY_WORKSPACE_ID or gateway_task_row.get("owner_agent_id") != GATEWAY_AGENT_ID:
                failures.append(f"postgres_gateway_task_row_mismatch:{gateway_task_row}")
            if gateway_missing_scope_task_row or gateway_cross_workspace_task_row or gateway_header_workspace_task_row or gateway_other_agent_task_row or gateway_no_token_task_row:
                failures.append("postgres_gateway_rejected_task_created_row")
            if gateway_missing_run_scope_row:
                failures.append("postgres_gateway_missing_scope_run_created_row")
            if gateway_intruder_run_row:
                failures.append("postgres_gateway_intruder_run_created_row")
            if gateway_missing_tool_row or gateway_missing_eval_row or gateway_missing_artifact_row:
                failures.append("postgres_gateway_missing_scope_evidence_created_row")
            if gateway_missing_plan_row or gateway_missing_manifest_row:
                failures.append("postgres_gateway_missing_scope_plan_created_row")
            if gateway_missing_audit_scope_row:
                failures.append("postgres_gateway_missing_scope_audit_created_row")
            if gateway_cross_workspace_plan_row or gateway_no_token_plan_row or gateway_mismatch_manifest_row:
                failures.append("postgres_gateway_rejected_plan_created_row")
            if gateway_missing_memory_row or gateway_memory_cross_workspace_row or gateway_memory_header_workspace_row or gateway_memory_no_token_row or gateway_memory_mismatch_row:
                failures.append("postgres_gateway_rejected_memory_created_row")
            if not gateway_approved_memory_row or gateway_approved_memory_row.get("review_status") != "approved" or gateway_approved_memory_row.get("task_id") is not None:
                failures.append(f"postgres_gateway_approved_memory_overwritten:{gateway_approved_memory_row}")
            if not gateway_cross_workspace_memory_row or gateway_cross_workspace_memory_row.get("workspace_id") != "other-workspace" or gateway_cross_workspace_memory_row.get("task_id") is not None:
                failures.append(f"postgres_gateway_cross_workspace_memory_overwritten:{gateway_cross_workspace_memory_row}")
            if not gateway_other_agent_memory_row or gateway_other_agent_memory_row.get("agent_id") != GATEWAY_OTHER_AGENT_ID or gateway_other_agent_memory_row.get("task_id") is not None:
                failures.append(f"postgres_gateway_other_agent_memory_overwritten:{gateway_other_agent_memory_row}")
            if gateway_missing_approval_row or gateway_approval_cross_workspace_row or gateway_approval_header_workspace_row or gateway_approval_no_token_row or gateway_approval_mismatch_row or gateway_approval_tool_mismatch_row or gateway_approval_other_agent_row:
                failures.append("postgres_gateway_rejected_approval_created_row")
            if not gateway_approved_approval_row or gateway_approved_approval_row.get("decision") != "approved" or gateway_approved_approval_row.get("decided_at") is None:
                failures.append(f"postgres_gateway_approved_approval_overwritten:{gateway_approved_approval_row}")
            if gateway_audit_cross_workspace_row or gateway_audit_no_token_row or gateway_audit_mismatch_row:
                failures.append("postgres_gateway_rejected_audit_created_row")
            if gateway_intruder_tool_row or gateway_intruder_eval_row or gateway_intruder_artifact_row:
                failures.append("postgres_gateway_intruder_evidence_created_row")
            if gateway_intruder_plan_row or gateway_intruder_manifest_row:
                failures.append("postgres_gateway_intruder_plan_created_row")
            if gateway_intruder_memory_row:
                failures.append("postgres_gateway_intruder_memory_created_row")
            if gateway_intruder_approval_row:
                failures.append("postgres_gateway_intruder_approval_created_row")
            if gateway_intruder_audit_row:
                failures.append("postgres_gateway_intruder_audit_created_row")
            if gateway_intruder_audit_no_run_row:
                failures.append("postgres_gateway_intruder_audit_no_run_created_row")
            if not gateway_run_row or gateway_run_row.get("workspace_id") != GATEWAY_WORKSPACE_ID or gateway_run_row.get("task_id") != GATEWAY_TASK_ID or gateway_run_row.get("agent_id") != GATEWAY_AGENT_ID:
                failures.append(f"postgres_gateway_run_row_mismatch:{gateway_run_row}")
            elif gateway_run_row.get("output_summary") != "Postgres Gateway run heartbeat write proof." or int(gateway_run_row.get("duration_ms") or 0) != 2345 or int(gateway_run_row.get("output_tokens") or 0) != 17:
                failures.append(f"postgres_gateway_run_heartbeat_fields_mismatch:{gateway_run_row}")
            if not gateway_heartbeat_agent_row or gateway_heartbeat_agent_row.get("status") != "running":
                failures.append(f"postgres_gateway_heartbeat_agent_row_mismatch:{gateway_heartbeat_agent_row}")
            if not gateway_terminal_heartbeat_run_row or gateway_terminal_heartbeat_run_row.get("status") != "completed" or gateway_terminal_heartbeat_run_row.get("output_summary") != "Already completed and immutable to heartbeat revival.":
                failures.append(f"postgres_gateway_terminal_heartbeat_overwritten:{gateway_terminal_heartbeat_run_row}")
            if not gateway_completion_run_row or gateway_completion_run_row.get("status") != "completed" or gateway_completion_run_row.get("ended_at") is None or gateway_completion_run_row.get("output_summary") != "Postgres Gateway run completion heartbeat proof." or int(gateway_completion_run_row.get("duration_ms") or 0) != 3456 or int(gateway_completion_run_row.get("output_tokens") or 0) != 29:
                failures.append(f"postgres_gateway_completion_run_row_mismatch:{gateway_completion_run_row}")
            if not gateway_completion_task_row or gateway_completion_task_row.get("status") != "completed":
                failures.append(f"postgres_gateway_completion_task_not_completed:{gateway_completion_task_row}")
            if not gateway_completion_agent_row or gateway_completion_agent_row.get("status") != "idle":
                failures.append(f"postgres_gateway_completion_agent_not_idle:{gateway_completion_agent_row}")
            if not gateway_tool_row or gateway_tool_row.get("run_id") != GATEWAY_RUN_ID or gateway_tool_row.get("agent_id") != GATEWAY_AGENT_ID:
                failures.append(f"postgres_gateway_tool_row_mismatch:{gateway_tool_row}")
            if not gateway_eval_row or gateway_eval_row.get("run_id") != GATEWAY_RUN_ID or gateway_eval_row.get("task_id") != GATEWAY_TASK_ID:
                failures.append(f"postgres_gateway_eval_row_mismatch:{gateway_eval_row}")
            if not gateway_artifact_row or gateway_artifact_row.get("run_id") != GATEWAY_RUN_ID or gateway_artifact_row.get("task_id") != GATEWAY_TASK_ID:
                failures.append(f"postgres_gateway_artifact_row_mismatch:{gateway_artifact_row}")
            if not gateway_plan_row or gateway_plan_row.get("run_id") != GATEWAY_RUN_ID or gateway_plan_row.get("task_id") != GATEWAY_TASK_ID or gateway_plan_row.get("agent_id") != GATEWAY_AGENT_ID:
                failures.append(f"postgres_gateway_plan_row_mismatch:{gateway_plan_row}")
            if not gateway_manifest_row or gateway_manifest_row.get("run_id") != GATEWAY_RUN_ID or gateway_manifest_row.get("plan_id") != GATEWAY_PLAN_ID or gateway_manifest_row.get("status") != "verified":
                failures.append(f"postgres_gateway_manifest_row_mismatch:{gateway_manifest_row}")
            if not gateway_memory_row or gateway_memory_row.get("workspace_id") != GATEWAY_WORKSPACE_ID or gateway_memory_row.get("task_id") != GATEWAY_TASK_ID or gateway_memory_row.get("agent_id") != GATEWAY_AGENT_ID or gateway_memory_row.get("review_status") != "candidate":
                failures.append(f"postgres_gateway_memory_row_mismatch:{gateway_memory_row}")
            if not gateway_approval_row or gateway_approval_row.get("run_id") != GATEWAY_RUN_ID or gateway_approval_row.get("task_id") != GATEWAY_TASK_ID or gateway_approval_row.get("tool_call_id") != GATEWAY_TOOL_CALL_ID or gateway_approval_row.get("requested_by_agent_id") != GATEWAY_AGENT_ID or gateway_approval_row.get("decision") != "pending":
                failures.append(f"postgres_gateway_approval_row_mismatch:{gateway_approval_row}")
            audit_metadata = {}
            if gateway_audit_row:
                try:
                    audit_metadata = json.loads(gateway_audit_row.get("metadata_json") or "{}")
                except Exception:
                    audit_metadata = {}
            if not gateway_audit_row or gateway_audit_row.get("actor_id") != GATEWAY_AGENT_ID or gateway_audit_row.get("entity_type") != "runs" or gateway_audit_row.get("entity_id") != GATEWAY_RUN_ID:
                failures.append(f"postgres_gateway_audit_row_mismatch:{gateway_audit_row}")
            if audit_metadata.get("workspace_id") != GATEWAY_WORKSPACE_ID or audit_metadata.get("raw_omitted") is not True or not gateway_audit_row.get("tamper_chain_hash"):
                failures.append(f"postgres_gateway_audit_metadata_mismatch:{audit_metadata}")
            if not gateway_task_row or gateway_task_row.get("status") != "waiting_approval":
                failures.append(f"postgres_gateway_approval_did_not_mark_task_waiting:{gateway_task_row}")
            if not gateway_run_row or gateway_run_row.get("status") != "waiting_approval" or int(gateway_run_row.get("approval_required") or 0) != 1:
                failures.append(f"postgres_gateway_approval_did_not_mark_run_waiting:{gateway_run_row}")
            if int(gateway_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_runtime_event_missing")
            if int(gateway_audit_count or 0) < 1:
                failures.append("postgres_gateway_audit_missing")
            if int(gateway_run_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_run_runtime_event_missing")
            if int(gateway_run_audit_count or 0) < 1:
                failures.append("postgres_gateway_run_audit_missing")
            if int(gateway_heartbeat_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_heartbeat_runtime_event_missing")
            if int(gateway_heartbeat_audit_count or 0) < 1:
                failures.append("postgres_gateway_heartbeat_audit_missing")
            if int(gateway_run_heartbeat_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_run_heartbeat_runtime_event_missing")
            if int(gateway_run_heartbeat_audit_count or 0) < 1:
                failures.append("postgres_gateway_run_heartbeat_audit_missing")
            if int(gateway_run_completion_heartbeat_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_run_completion_heartbeat_runtime_event_missing")
            if int(gateway_run_completion_heartbeat_audit_count or 0) < 1:
                failures.append("postgres_gateway_run_completion_heartbeat_audit_missing")
            if int(gateway_tool_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_tool_runtime_event_missing")
            if int(gateway_eval_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_eval_runtime_event_missing")
            if int(gateway_artifact_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_artifact_runtime_event_missing")
            if int(gateway_artifact_audit_count or 0) < 1:
                failures.append("postgres_gateway_artifact_audit_missing")
            if int(gateway_plan_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_plan_runtime_event_missing")
            if int(gateway_plan_audit_count or 0) < 1:
                failures.append("postgres_gateway_plan_audit_missing")
            if int(gateway_manifest_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_manifest_runtime_event_missing")
            if int(gateway_manifest_audit_count or 0) < 1:
                failures.append("postgres_gateway_manifest_audit_missing")
            if int(gateway_memory_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_memory_runtime_event_missing")
            if int(gateway_memory_audit_count or 0) < 1:
                failures.append("postgres_gateway_memory_audit_missing")
            if int(gateway_approval_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_approval_runtime_event_missing")
            if int(gateway_approval_audit_count or 0) < 1:
                failures.append("postgres_gateway_approval_audit_missing")
            if int(gateway_approval_run_wait_audit_count or 0) < 1:
                failures.append("postgres_gateway_approval_run_wait_audit_missing")
            if int(gateway_approval_task_wait_audit_count or 0) < 1:
                failures.append("postgres_gateway_approval_task_wait_audit_missing")
            if int(gateway_audit_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_audit_runtime_event_missing")
            if not runtime_openclaw_action_row or runtime_openclaw_action_row.get("status") != "consumed" or runtime_openclaw_action_row.get("approved_at") is None or runtime_openclaw_action_row.get("consumed_at") is None or runtime_openclaw_action_row.get("workspace_id") != RUNTIME_WORKSPACE_ID:
                failures.append(f"runtime_openclaw_prepared_action_row_mismatch:{runtime_openclaw_action_row}")
            if not runtime_openclaw_approval_row or runtime_openclaw_approval_row.get("decision") != "approved" or runtime_openclaw_approval_row.get("decided_at") is None:
                failures.append(f"runtime_openclaw_approval_row_mismatch:{runtime_openclaw_approval_row}")
            if not runtime_openclaw_run_row or runtime_openclaw_run_row.get("status") != "completed" or runtime_openclaw_run_row.get("output_summary") != "OpenClaw returned OPENCLAW_MIS_PROBE_OK." or int(runtime_openclaw_run_row.get("approval_required") or 0) != 0:
                failures.append(f"runtime_openclaw_run_row_mismatch:{runtime_openclaw_run_row}")
            if not runtime_openclaw_task_row or runtime_openclaw_task_row.get("status") != "completed":
                failures.append(f"runtime_openclaw_task_row_mismatch:{runtime_openclaw_task_row}")
            if not runtime_openclaw_tool_row or runtime_openclaw_tool_row.get("status") != "completed" or not str(runtime_openclaw_tool_row.get("side_effect_id") or "").startswith("openclaw-response-hash:"):
                failures.append(f"runtime_openclaw_tool_row_mismatch:{runtime_openclaw_tool_row}")
            if int(runtime_openclaw_event_count or 0) < 2:
                failures.append("runtime_openclaw_events_missing")
            if int(runtime_openclaw_run_audit_count or 0) < 1 or int(runtime_openclaw_action_audit_count or 0) < 2:
                failures.append("runtime_openclaw_audit_missing")
            if not runtime_hermes_action_row or runtime_hermes_action_row.get("status") != "consumed" or runtime_hermes_action_row.get("approved_at") is None or runtime_hermes_action_row.get("consumed_at") is None or runtime_hermes_action_row.get("workspace_id") != RUNTIME_WORKSPACE_ID:
                failures.append(f"runtime_hermes_prepared_action_row_mismatch:{runtime_hermes_action_row}")
            if not runtime_hermes_approval_row or runtime_hermes_approval_row.get("decision") != "approved" or runtime_hermes_approval_row.get("decided_at") is None:
                failures.append(f"runtime_hermes_approval_row_mismatch:{runtime_hermes_approval_row}")
            if not runtime_hermes_run_row or runtime_hermes_run_row.get("status") != "completed" or runtime_hermes_run_row.get("output_summary") != "Hermes default gateway returned HERMES_DEFAULT_RUN_OK." or int(runtime_hermes_run_row.get("approval_required") or 0) != 0:
                failures.append(f"runtime_hermes_run_row_mismatch:{runtime_hermes_run_row}")
            if not runtime_hermes_task_row or runtime_hermes_task_row.get("status") != "completed":
                failures.append(f"runtime_hermes_task_row_mismatch:{runtime_hermes_task_row}")
            if not runtime_hermes_tool_row or runtime_hermes_tool_row.get("status") != "completed" or not str(runtime_hermes_tool_row.get("side_effect_id") or "").startswith("hermes-response-hash:"):
                failures.append(f"runtime_hermes_tool_row_mismatch:{runtime_hermes_tool_row}")
            if int(runtime_hermes_event_count or 0) < 2:
                failures.append("runtime_hermes_events_missing")
            if int(runtime_hermes_run_audit_count or 0) < 1 or int(runtime_hermes_action_audit_count or 0) < 2:
                failures.append("runtime_hermes_audit_missing")
            if not (gateway_token_last_used or {}).get("last_used_at"):
                failures.append("postgres_gateway_token_last_used_not_updated")
            if not (gateway_token_last_used or {}).get("last_heartbeat_at"):
                failures.append("postgres_gateway_token_last_heartbeat_not_updated")
            transcript = json.dumps(
                [
                    blocked_payload,
                    gateway_blocked_payload,
                    gateway_claim_blocked_payload,
                    gateway_run_start_blocked_payload,
                    gateway_heartbeat_blocked_payload,
                    gateway_run_heartbeat_blocked_payload,
                    gateway_missing_scope_payload,
                    gateway_missing_heartbeat_scope_payload,
                    gateway_heartbeat_cross_workspace_payload,
                    gateway_heartbeat_header_workspace_payload,
                    gateway_heartbeat_other_agent_payload,
                    gateway_heartbeat_intruder_payload,
                    gateway_heartbeat_no_token_payload,
                    gateway_heartbeat_write_payload,
                    gateway_missing_claim_scope_payload,
                    gateway_missing_run_scope_payload,
                    gateway_tool_blocked_payload,
                    gateway_eval_blocked_payload,
                    gateway_artifact_blocked_payload,
                    gateway_plan_blocked_payload,
                    gateway_manifest_blocked_payload,
                    gateway_memory_blocked_payload,
                    gateway_approval_blocked_payload,
                    gateway_audit_blocked_payload,
                    gateway_cross_workspace_payload,
                    gateway_header_workspace_payload,
                    gateway_other_agent_payload,
                    gateway_no_token_payload,
                    gateway_create_payload,
                    gateway_claim_payload,
                    gateway_run_start_payload,
                    gateway_missing_run_heartbeat_scope_payload,
                    gateway_run_heartbeat_no_token_payload,
                    gateway_run_heartbeat_cross_workspace_payload,
                    gateway_run_heartbeat_header_workspace_payload,
                    gateway_run_heartbeat_task_mismatch_payload,
                    gateway_run_heartbeat_intruder_payload,
                    gateway_run_heartbeat_terminal_revival_payload,
                    gateway_run_heartbeat_write_payload,
                    gateway_run_completion_heartbeat_payload,
                    gateway_missing_tool_scope_payload,
                    gateway_tool_write_payload,
                    gateway_missing_eval_scope_payload,
                    gateway_eval_write_payload,
                    gateway_missing_artifact_scope_payload,
                    gateway_artifact_write_payload,
                    gateway_missing_plan_scope_payload,
                    gateway_plan_cross_workspace_payload,
                    gateway_plan_no_token_payload,
                    gateway_plan_write_payload,
                    gateway_manifest_mismatch_payload,
                    gateway_missing_manifest_scope_payload,
                    gateway_manifest_write_payload,
                    gateway_missing_memory_scope_payload,
                    gateway_memory_cross_workspace_payload,
                    gateway_memory_header_workspace_payload,
                    gateway_memory_no_token_payload,
                    gateway_memory_mismatch_payload,
                    gateway_memory_approved_overwrite_payload,
                    gateway_memory_existing_cross_workspace_payload,
                    gateway_memory_other_agent_overwrite_payload,
                    gateway_memory_write_payload,
                    gateway_missing_approval_scope_payload,
                    gateway_approval_cross_workspace_payload,
                    gateway_approval_header_workspace_payload,
                    gateway_approval_no_token_payload,
                    gateway_approval_mismatch_payload,
                    gateway_approval_tool_mismatch_payload,
                    gateway_approval_approved_overwrite_payload,
                    gateway_approval_other_agent_payload,
                    gateway_approval_write_payload,
                    gateway_missing_audit_scope_payload,
                    gateway_audit_cross_workspace_payload,
                    gateway_audit_no_token_payload,
                    gateway_audit_mismatch_payload,
                    gateway_audit_write_payload,
                    gateway_intruder_claim_payload,
                    gateway_intruder_run_payload,
                    gateway_intruder_tool_payload,
                    gateway_intruder_eval_payload,
                    gateway_intruder_artifact_payload,
                    gateway_intruder_plan_payload,
                    gateway_intruder_manifest_payload,
                    gateway_intruder_memory_payload,
                    gateway_intruder_approval_payload,
                    gateway_intruder_audit_payload,
                    gateway_intruder_audit_no_run_payload,
                    runtime_openclaw_read_only_payload,
                    runtime_hermes_read_only_payload,
                    runtime_approval_read_only_payload,
                    runtime_non_prepared_approval_payload,
                    runtime_openclaw_prepare_payload,
                    runtime_openclaw_premature_payload,
                    runtime_openclaw_approve_payload,
                    runtime_openclaw_mismatch_payload,
                    runtime_openclaw_resume_payload,
                    runtime_openclaw_replay_payload,
                    runtime_hermes_prepare_payload,
                    runtime_hermes_premature_payload,
                    runtime_hermes_approve_payload,
                    runtime_hermes_mismatch_payload,
                    runtime_hermes_resume_payload,
                    runtime_hermes_replay_payload,
                    agent_block_payload,
                    gateway_knowledge_block_payload,
                ],
                ensure_ascii=False,
                sort_keys=True,
            )
            if gateway_token in transcript or gateway_observer_token in transcript or gateway_intruder_token in transcript or gateway_completion_token in transcript:
                failures.append("postgres_gateway_raw_token_leaked")

            output = {
                "ok": not failures,
                "skipped": False,
                "contract": CONTRACT_ID,
                "contracts": [
                    CONTRACT_ID,
                    "postgres_http_gateway_task_write_parity_v1",
                    "postgres_http_gateway_execution_start_write_v1",
                    "postgres_http_gateway_evidence_write_v1",
                    "postgres_http_gateway_plan_evidence_write_v1",
                    "postgres_http_gateway_approval_write_v1",
                    "postgres_http_gateway_audit_write_v1",
                    "postgres_http_gateway_heartbeat_write_v1",
                    "postgres_http_gateway_run_heartbeat_write_v1",
                    "postgres_http_gateway_run_completion_heartbeat_write_v1",
                    "postgres_http_gateway_memory_write_v1",
                    "postgres_http_runtime_prepared_action_write_v1",
                    "postgres_http_runtime_approval_decision_write_v1",
                ],
                "image": args.image,
                "driver_status": driver_status,
                "read_only_backend_mode": read_only_backend.get("mode"),
                "read_only_runtime_write_gate": (read_only_backend.get("runtime_write_gate") or {}).get("status"),
                "read_only_write_block_status": blocked_status,
                "write_backend_mode": write_backend.get("mode"),
                "write_allowlist": write_backend.get("write_allowlist"),
                "write_runtime_write_gate": write_backend.get("runtime_write_gate"),
                "task_create_status": create_status,
                "task_readback_status": readback_status,
                "gateway_read_only_write_block_status": gateway_blocked_status,
                "gateway_read_only_claim_block_status": gateway_claim_blocked_status,
                "gateway_read_only_run_start_block_status": gateway_run_start_blocked_status,
                "gateway_read_only_tool_block_status": gateway_tool_blocked_status,
                "gateway_read_only_eval_block_status": gateway_eval_blocked_status,
                "gateway_read_only_artifact_block_status": gateway_artifact_blocked_status,
                "gateway_read_only_plan_block_status": gateway_plan_blocked_status,
                "gateway_read_only_manifest_block_status": gateway_manifest_blocked_status,
                "gateway_read_only_memory_block_status": gateway_memory_blocked_status,
                "gateway_read_only_approval_block_status": gateway_approval_blocked_status,
                "gateway_read_only_heartbeat_block_status": gateway_heartbeat_blocked_status,
                "gateway_read_only_run_heartbeat_block_status": gateway_run_heartbeat_blocked_status,
                "gateway_read_only_audit_block_status": gateway_audit_blocked_status,
                "runtime_openclaw_read_only_block_status": runtime_openclaw_read_only_status,
                "runtime_hermes_read_only_block_status": runtime_hermes_read_only_status,
                "runtime_approval_read_only_block_status": runtime_approval_read_only_status,
                "gateway_missing_heartbeat_scope_status": gateway_missing_heartbeat_scope_status,
                "gateway_missing_scope_status": gateway_missing_scope_status,
                "gateway_missing_claim_scope_status": gateway_missing_claim_scope_status,
                "gateway_missing_run_scope_status": gateway_missing_run_scope_status,
                "gateway_missing_run_heartbeat_scope_status": gateway_missing_run_heartbeat_scope_status,
                "gateway_missing_tool_scope_status": gateway_missing_tool_scope_status,
                "gateway_missing_eval_scope_status": gateway_missing_eval_scope_status,
                "gateway_missing_artifact_scope_status": gateway_missing_artifact_scope_status,
                "gateway_missing_plan_scope_status": gateway_missing_plan_scope_status,
                "gateway_missing_manifest_scope_status": gateway_missing_manifest_scope_status,
                "gateway_missing_memory_scope_status": gateway_missing_memory_scope_status,
                "gateway_missing_approval_scope_status": gateway_missing_approval_scope_status,
                "gateway_missing_audit_scope_status": gateway_missing_audit_scope_status,
                "gateway_cross_workspace_status": gateway_cross_workspace_status,
                "gateway_plan_cross_workspace_status": gateway_plan_cross_workspace_status,
                "gateway_memory_cross_workspace_status": gateway_memory_cross_workspace_status,
                "gateway_memory_header_workspace_status": gateway_memory_header_workspace_status,
                "gateway_approval_cross_workspace_status": gateway_approval_cross_workspace_status,
                "gateway_approval_header_workspace_status": gateway_approval_header_workspace_status,
                "gateway_audit_cross_workspace_status": gateway_audit_cross_workspace_status,
                "gateway_heartbeat_cross_workspace_status": gateway_heartbeat_cross_workspace_status,
                "gateway_heartbeat_header_workspace_status": gateway_heartbeat_header_workspace_status,
                "gateway_run_heartbeat_cross_workspace_status": gateway_run_heartbeat_cross_workspace_status,
                "gateway_run_heartbeat_header_workspace_status": gateway_run_heartbeat_header_workspace_status,
                "gateway_header_workspace_status": gateway_header_workspace_status,
                "gateway_other_agent_status": gateway_other_agent_status,
                "gateway_heartbeat_other_agent_status": gateway_heartbeat_other_agent_status,
                "gateway_heartbeat_intruder_status": gateway_heartbeat_intruder_status,
                "gateway_no_token_status": gateway_no_token_status,
                "gateway_heartbeat_no_token_status": gateway_heartbeat_no_token_status,
                "gateway_run_heartbeat_no_token_status": gateway_run_heartbeat_no_token_status,
                "gateway_plan_no_token_status": gateway_plan_no_token_status,
                "gateway_memory_no_token_status": gateway_memory_no_token_status,
                "gateway_approval_no_token_status": gateway_approval_no_token_status,
                "gateway_audit_no_token_status": gateway_audit_no_token_status,
                "gateway_task_create_status": gateway_create_status,
                "gateway_claim_status": gateway_claim_status,
                "gateway_run_start_status": gateway_run_start_status,
                "gateway_heartbeat_write_status": gateway_heartbeat_write_status,
                "gateway_run_heartbeat_task_mismatch_status": gateway_run_heartbeat_task_mismatch_status,
                "gateway_run_heartbeat_intruder_status": gateway_run_heartbeat_intruder_status,
                "gateway_run_heartbeat_terminal_revival_status": gateway_run_heartbeat_terminal_revival_status,
                "gateway_run_heartbeat_write_status": gateway_run_heartbeat_write_status,
                "gateway_run_completion_heartbeat_status": gateway_run_completion_heartbeat_status,
                "gateway_tool_write_status": gateway_tool_write_status,
                "gateway_eval_write_status": gateway_eval_write_status,
                "gateway_artifact_write_status": gateway_artifact_write_status,
                "gateway_plan_write_status": gateway_plan_write_status,
                "gateway_manifest_mismatch_status": gateway_manifest_mismatch_status,
                "gateway_manifest_write_status": gateway_manifest_write_status,
                "gateway_memory_mismatch_status": gateway_memory_mismatch_status,
                "gateway_memory_approved_overwrite_status": gateway_memory_approved_overwrite_status,
                "gateway_memory_existing_cross_workspace_status": gateway_memory_existing_cross_workspace_status,
                "gateway_memory_other_agent_overwrite_status": gateway_memory_other_agent_overwrite_status,
                "gateway_memory_write_status": gateway_memory_write_status,
                "gateway_approval_mismatch_status": gateway_approval_mismatch_status,
                "gateway_approval_tool_mismatch_status": gateway_approval_tool_mismatch_status,
                "gateway_approval_approved_overwrite_status": gateway_approval_approved_overwrite_status,
                "gateway_approval_other_agent_status": gateway_approval_other_agent_status,
                "gateway_approval_write_status": gateway_approval_write_status,
                "gateway_audit_mismatch_status": gateway_audit_mismatch_status,
                "gateway_audit_write_status": gateway_audit_write_status,
                "gateway_intruder_claim_status": gateway_intruder_claim_status,
                "gateway_intruder_run_status": gateway_intruder_run_status,
                "gateway_intruder_tool_status": gateway_intruder_tool_status,
                "gateway_intruder_eval_status": gateway_intruder_eval_status,
                "gateway_intruder_artifact_status": gateway_intruder_artifact_status,
                "gateway_intruder_plan_status": gateway_intruder_plan_status,
                "gateway_intruder_manifest_status": gateway_intruder_manifest_status,
                "gateway_intruder_memory_status": gateway_intruder_memory_status,
                "gateway_intruder_approval_status": gateway_intruder_approval_status,
                "gateway_intruder_audit_status": gateway_intruder_audit_status,
                "gateway_intruder_audit_no_run_status": gateway_intruder_audit_no_run_status,
                "gateway_task_readback_status": gateway_readback_status,
                "gateway_run_readback_status": gateway_run_readback_status,
                "non_allowlisted_write_status": agent_block_status,
                "gateway_non_allowlisted_write_status": gateway_knowledge_block_status,
                "runtime_non_prepared_approval_status": runtime_non_prepared_approval_status,
                "runtime_openclaw_prepare_status": runtime_openclaw_prepare_status,
                "runtime_openclaw_premature_status": runtime_openclaw_premature_status,
                "runtime_openclaw_approve_status": runtime_openclaw_approve_status,
                "runtime_openclaw_mismatch_status": runtime_openclaw_mismatch_status,
                "runtime_openclaw_cross_workspace_status": runtime_openclaw_cross_workspace_status,
                "runtime_openclaw_resume_status": runtime_openclaw_resume_status,
                "runtime_openclaw_concurrent_status": runtime_openclaw_concurrent_status,
                "runtime_openclaw_replay_status": runtime_openclaw_replay_status,
                "runtime_hermes_prepare_status": runtime_hermes_prepare_status,
                "runtime_hermes_premature_status": runtime_hermes_premature_status,
                "runtime_hermes_approve_status": runtime_hermes_approve_status,
                "runtime_hermes_mismatch_status": runtime_hermes_mismatch_status,
                "runtime_hermes_cross_workspace_status": runtime_hermes_cross_workspace_status,
                "runtime_hermes_resume_status": runtime_hermes_resume_status,
                "runtime_hermes_concurrent_status": runtime_hermes_concurrent_status,
                "runtime_hermes_replay_status": runtime_hermes_replay_status,
                "task_id": TASK_ID,
                "gateway_task_id": GATEWAY_TASK_ID,
                "gateway_run_id": GATEWAY_RUN_ID,
                "gateway_completion_run_id": GATEWAY_COMPLETION_RUN_ID,
                "gateway_completion_task_id": GATEWAY_COMPLETION_TASK_ID,
                "gateway_completion_agent_id": GATEWAY_COMPLETION_AGENT_ID,
                "gateway_completion_run_status": gateway_completion_run_row.get("status") if gateway_completion_run_row else None,
                "gateway_completion_task_status": gateway_completion_task_row.get("status") if gateway_completion_task_row else None,
                "gateway_completion_agent_status": gateway_completion_agent_row.get("status") if gateway_completion_agent_row else None,
                "gateway_completion_run_ended": bool(gateway_completion_run_row and gateway_completion_run_row.get("ended_at")),
                "gateway_tool_call_id": GATEWAY_TOOL_CALL_ID,
                "gateway_evaluation_id": GATEWAY_EVALUATION_ID,
                "gateway_artifact_id": GATEWAY_ARTIFACT_ID,
                "gateway_plan_id": GATEWAY_PLAN_ID,
                "gateway_manifest_id": GATEWAY_MANIFEST_ID,
                "gateway_memory_id": GATEWAY_MEMORY_ID,
                "gateway_approval_id": GATEWAY_APPROVAL_ID,
                "gateway_manifest_status": gateway_manifest.get("status"),
                "gateway_manifest_verification_pass": bool(gateway_manifest_verification.get("pass")),
                "gateway_audit_action": GATEWAY_AUDIT_ACTION,
                "workspace_id": WORKSPACE_ID,
                "gateway_workspace_id": GATEWAY_WORKSPACE_ID,
                "runtime_workspace_id": RUNTIME_WORKSPACE_ID,
                "runtime_openclaw_prepared_action_id": runtime_openclaw_prepared_action_id,
                "runtime_hermes_prepared_action_id": runtime_hermes_prepared_action_id,
                "runtime_openclaw_provider_call_count": runtime_openclaw_provider_call_count,
                "runtime_hermes_provider_call_count": runtime_hermes_provider_call_count,
                "runtime_openclaw_prepared_action_status": runtime_openclaw_action_row.get("status") if runtime_openclaw_action_row else None,
                "runtime_hermes_prepared_action_status": runtime_hermes_action_row.get("status") if runtime_hermes_action_row else None,
                "runtime_openclaw_run_status": runtime_openclaw_run_row.get("status") if runtime_openclaw_run_row else None,
                "runtime_hermes_run_status": runtime_hermes_run_row.get("status") if runtime_hermes_run_row else None,
                "runtime_event_count": int(runtime_event_count or 0),
                "audit_count": int(audit_count or 0),
                "gateway_runtime_event_count": int(gateway_runtime_event_count or 0),
                "gateway_audit_count": int(gateway_audit_count or 0),
                "gateway_run_runtime_event_count": int(gateway_run_runtime_event_count or 0),
                "gateway_run_audit_count": int(gateway_run_audit_count or 0),
                "gateway_heartbeat_runtime_event_count": int(gateway_heartbeat_runtime_event_count or 0),
                "gateway_heartbeat_audit_count": int(gateway_heartbeat_audit_count or 0),
                "gateway_run_heartbeat_runtime_event_count": int(gateway_run_heartbeat_runtime_event_count or 0),
                "gateway_run_heartbeat_audit_count": int(gateway_run_heartbeat_audit_count or 0),
                "gateway_run_completion_heartbeat_runtime_event_count": int(gateway_run_completion_heartbeat_runtime_event_count or 0),
                "gateway_run_completion_heartbeat_audit_count": int(gateway_run_completion_heartbeat_audit_count or 0),
                "runtime_openclaw_event_count": int(runtime_openclaw_event_count or 0),
                "runtime_openclaw_run_audit_count": int(runtime_openclaw_run_audit_count or 0),
                "runtime_openclaw_action_audit_count": int(runtime_openclaw_action_audit_count or 0),
                "runtime_openclaw_claim_audit_count": int(runtime_openclaw_claim_audit_count or 0),
                "runtime_hermes_event_count": int(runtime_hermes_event_count or 0),
                "runtime_hermes_run_audit_count": int(runtime_hermes_run_audit_count or 0),
                "runtime_hermes_action_audit_count": int(runtime_hermes_action_audit_count or 0),
                "runtime_hermes_claim_audit_count": int(runtime_hermes_claim_audit_count or 0),
                "runtime_cross_process_single_winner": (
                    sorted(status for status, _ in runtime_openclaw_race_results) == [201, 409]
                    and sorted(status for status, _ in runtime_hermes_race_results) == [201, 409]
                    and runtime_openclaw_provider_call_count == 1
                    and runtime_hermes_provider_call_count == 1
                    and int(runtime_openclaw_claim_audit_count or 0) == 1
                    and int(runtime_hermes_claim_audit_count or 0) == 1
                ),
                "gateway_tool_runtime_event_count": int(gateway_tool_runtime_event_count or 0),
                "gateway_eval_runtime_event_count": int(gateway_eval_runtime_event_count or 0),
                "gateway_artifact_runtime_event_count": int(gateway_artifact_runtime_event_count or 0),
                "gateway_artifact_audit_count": int(gateway_artifact_audit_count or 0),
                "gateway_plan_runtime_event_count": int(gateway_plan_runtime_event_count or 0),
                "gateway_plan_audit_count": int(gateway_plan_audit_count or 0),
                "gateway_manifest_runtime_event_count": int(gateway_manifest_runtime_event_count or 0),
                "gateway_manifest_audit_count": int(gateway_manifest_audit_count or 0),
                "gateway_memory_runtime_event_count": int(gateway_memory_runtime_event_count or 0),
                "gateway_memory_audit_count": int(gateway_memory_audit_count or 0),
                "gateway_approval_runtime_event_count": int(gateway_approval_runtime_event_count or 0),
                "gateway_approval_audit_count": int(gateway_approval_audit_count or 0),
                "gateway_approval_run_wait_audit_count": int(gateway_approval_run_wait_audit_count or 0),
                "gateway_approval_task_wait_audit_count": int(gateway_approval_task_wait_audit_count or 0),
                "gateway_audit_runtime_event_count": int(gateway_audit_runtime_event_count or 0),
                "gateway_token_last_used": bool((gateway_token_last_used or {}).get("last_used_at")),
                "gateway_token_last_heartbeat": bool((gateway_token_last_used or {}).get("last_heartbeat_at")),
                "free_local_dependencies": [],
                "fallback_performed": False,
                "token_omitted": True,
                "failures": failures,
                "next_proof": "Widen the routed Postgres write allowlist only after each route has a dedicated HTTP/CLI smoke.",
            }
            print(json.dumps(server.json_safe(output), ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not failures else 1
        except (AssertionError, PostgresAdapterUnavailable, RuntimeError, ValueError, KeyError) as exc:
            if adapter is not None:
                adapter.rollback()
            return unavailable(redact(str(exc), pg_auth), skip=args.skip_if_unavailable)
        finally:
            stop_server(proc)
            stop_server(peer_proc)
            stop_fake_hermes(fake_hermes)
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
