#!/usr/bin/env python3
"""Seed a deterministic, redacted OpenClaw-scale demo ledger.

The generated data is synthetic. It intentionally avoids credentials, real
paths, personal usernames, private prompts, and full transcripts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


AGENTS = 10
TASKS = 50
RUNS = 500
TOOL_CALLS = 800
MEMORIES = 200
AUDITS = 2000


def ts(offset_minutes: int) -> str:
    base = dt.datetime(2026, 6, 13, 8, 0, tzinfo=dt.timezone.utc)
    return (base + dt.timedelta(minutes=offset_minutes)).isoformat()


def reset_demo(conn: sqlite3.Connection) -> None:
    patterns = {
        "evaluations": ("evaluation_id", "eval_demo_%"),
        "approvals": ("approval_id", "ap_demo_%"),
        "tool_calls": ("tool_call_id", "tc_demo_%"),
        "runs": ("run_id", "run_demo_%"),
        "memories": ("memory_id", "mem_demo_%"),
        "tasks": ("task_id", "tsk_demo_%"),
        "agents": ("agent_id", "agt_demo_%"),
        "audit_logs": ("audit_id", "aud_demo_%"),
    }
    for table, (column, pattern) in patterns.items():
        conn.execute(f"DELETE FROM {table} WHERE {column} LIKE ?", (pattern,))


def insert_agents(conn: sqlite3.Connection) -> None:
    roles = [
        "Planner",
        "Researcher",
        "Builder",
        "Evaluator",
        "Ops Monitor",
        "Memory Curator",
        "QA Gatekeeper",
        "Notion Sync",
        "Runtime Probe",
        "Presenter",
    ]
    for i, role in enumerate(roles, start=1):
        now = ts(i)
        row = {
            "agent_id": f"agt_demo_{i:02d}",
            "name": f"Redacted Demo Agent {i:02d}",
            "role": role,
            "description": "Synthetic OpenClaw-style agent for classroom demo.",
            "runtime_type": "openclaw" if i <= 8 else "hermes",
            "model_provider": "redacted-provider",
            "model_name": "redacted-model",
            "status": "idle",
            "permission_level": "standard" if i != 7 else "approval_required",
            "allowed_tools": json.dumps(["browser.search", "notion.preview", "memory.propose"], ensure_ascii=False),
            "budget_limit_usd": 5.0,
            "owner_user_id": "usr_founder",
            "created_at": now,
            "updated_at": now,
        }
        conn.execute(
            """INSERT OR REPLACE INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""",
            row,
        )


def insert_tasks(conn: sqlite3.Connection) -> None:
    statuses = ["completed", "running", "waiting_approval", "failed", "planned"]
    risks = ["low", "medium", "high", "critical"]
    for i in range(1, TASKS + 1):
        now = ts(20 + i)
        row = {
            "task_id": f"tsk_demo_{i:03d}",
            "title": f"Redacted OpenClaw Cron Task {i:03d}",
            "description": "Synthetic task created from redacted cron/job metadata.",
            "requester_id": "usr_founder",
            "owner_agent_id": f"agt_demo_{((i - 1) % AGENTS) + 1:02d}",
            "collaborator_agent_ids": json.dumps([f"agt_demo_{((i + 1) % AGENTS) + 1:02d}"], ensure_ascii=False),
            "status": statuses[i % len(statuses)],
            "priority": ["low", "medium", "high"][i % 3],
            "due_date": None,
            "acceptance_criteria": "Demo task must keep summaries redacted and pass baseline quality gate.",
            "risk_level": risks[i % len(risks)],
            "budget_limit_usd": 2.5,
            "created_at": now,
            "updated_at": now,
        }
        conn.execute(
            """INSERT OR REPLACE INTO tasks(task_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
            VALUES(:task_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)""",
            row,
        )


def run_status(i: int) -> tuple[str, str | None]:
    if i % 17 == 0:
        return "failed", "model_not_found"
    if i % 29 == 0:
        return "failed", "timeout"
    if i % 11 == 0:
        return "blocked", "approval_required"
    return "completed", None


def insert_runs(conn: sqlite3.Connection) -> None:
    for i in range(1, RUNS + 1):
        status, error_type = run_status(i)
        task_idx = ((i - 1) % TASKS) + 1
        agent_idx = ((i - 1) % AGENTS) + 1
        duration_ms = 18_000 + (i % 240) * 1_100
        parent = f"run_demo_{i - 1:04d}" if i % 10 == 0 else None
        started = ts(90 + i)
        row = {
            "run_id": f"run_demo_{i:04d}",
            "task_id": f"tsk_demo_{task_idx:03d}",
            "agent_id": f"agt_demo_{agent_idx:02d}",
            "runtime_type": "openclaw" if agent_idx <= 8 else "hermes",
            "status": status,
            "started_at": started,
            "ended_at": ts(91 + i),
            "duration_ms": duration_ms,
            "input_summary": f"Redacted cron input #{i}; prompt_hash={server.stable_hash(['demo', i])[:12]}",
            "output_summary": f"Redacted result summary #{i}. This is synthetic and under 200 chars.",
            "model_provider": "redacted-provider",
            "model_name": "redacted-model",
            "input_tokens": 600 + (i % 90),
            "output_tokens": 180 + (i % 60),
            "reasoning_tokens": 80 + (i % 40),
            "cost_usd": round(0.006 + (i % 25) * 0.0007, 4),
            "error_type": error_type,
            "error_message": f"Synthetic {error_type} for demo quality gate." if error_type else None,
            "trace_id": f"trace_demo_{i:04d}",
            "parent_run_id": parent,
            "delegation_id": f"demo_delegation_{task_idx:03d}",
            "approval_required": 1 if error_type == "approval_required" or i % 13 == 0 else 0,
            "created_at": started,
        }
        conn.execute(
            """INSERT OR REPLACE INTO runs(run_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
            VALUES(:run_id,:task_id,:agent_id,:runtime_type,:status,:started_at,:ended_at,:duration_ms,:input_summary,:output_summary,:model_provider,:model_name,:input_tokens,:output_tokens,:reasoning_tokens,:cost_usd,:error_type,:error_message,:trace_id,:parent_run_id,:delegation_id,:approval_required,:created_at)""",
            row,
        )
        eval_row = {
            "evaluation_id": f"eval_demo_{i:04d}",
            "task_id": row["task_id"],
            "run_id": row["run_id"],
            "agent_id": row["agent_id"],
            "evaluator_type": "rule",
            "score": 0.91 if status == "completed" else 0.35,
            "pass_fail": "pass" if status == "completed" and duration_ms <= 180_000 else "fail",
            "rubric_json": json.dumps({"baseline_gate": True, "synthetic": True}, ensure_ascii=False),
            "notes": "Synthetic quality gate result for demo scale testing.",
            "created_at": row["created_at"],
        }
        conn.execute(
            """INSERT OR REPLACE INTO evaluations(evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at)
            VALUES(:evaluation_id,:task_id,:run_id,:agent_id,:evaluator_type,:score,:pass_fail,:rubric_json,:notes,:created_at)""",
            eval_row,
        )


def insert_tool_calls(conn: sqlite3.Connection) -> None:
    tools = [
        ("browser.search", "browser", "low"),
        ("notion.preview", "notion", "low"),
        ("memory.propose", "custom", "medium"),
        ("database.write", "database", "high"),
        ("mcp.invoke", "mcp", "high"),
    ]
    for i in range(1, TOOL_CALLS + 1):
        name, category, risk = tools[i % len(tools)]
        run_idx = ((i - 1) % RUNS) + 1
        agent_idx = ((run_idx - 1) % AGENTS) + 1
        row = {
            "tool_call_id": f"tc_demo_{i:04d}",
            "run_id": f"run_demo_{run_idx:04d}",
            "agent_id": f"agt_demo_{agent_idx:02d}",
            "tool_name": name,
            "tool_version": "v1",
            "tool_category": category,
            "normalized_args_json": json.dumps({"redacted": True, "demo_index": i}, ensure_ascii=False),
            "target_resource": f"demo://redacted/resource/{i % 25}",
            "risk_level": risk,
            "status": "approval_required" if risk == "high" and i % 7 == 0 else "completed",
            "result_summary": "Synthetic tool result summary; no raw args or private content.",
            "side_effect_id": None,
            "started_at": ts(700 + i),
            "ended_at": ts(701 + i),
            "created_at": ts(700 + i),
        }
        conn.execute(
            """INSERT OR REPLACE INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
            VALUES(:tool_call_id,:run_id,:agent_id,:tool_name,:tool_version,:tool_category,:normalized_args_json,:target_resource,:risk_level,:status,:result_summary,:side_effect_id,:started_at,:ended_at,:created_at)""",
            row,
        )


def insert_memories(conn: sqlite3.Connection) -> None:
    types = ["failure_case", "sop", "risk", "agent_lesson", "artifact_summary"]
    statuses = ["candidate", "approved", "candidate", "rejected"]
    for i in range(1, MEMORIES + 1):
        task_idx = ((i - 1) % TASKS) + 1
        agent_idx = ((i - 1) % AGENTS) + 1
        row = {
            "memory_id": f"mem_demo_{i:04d}",
            "scope": "project" if i % 3 else "task",
            "memory_type": types[i % len(types)],
            "canonical_text": f"Redacted demo memory #{i}: keep summaries short, hashed, and reviewable.",
            "source_type": "run_log",
            "source_ref": f"run_demo_{((i - 1) % RUNS) + 1:04d}",
            "project_id": "agentops-mis-demo",
            "task_id": f"tsk_demo_{task_idx:03d}",
            "agent_id": f"agt_demo_{agent_idx:02d}",
            "confidence": round(0.55 + (i % 40) / 100, 2),
            "review_status": statuses[i % len(statuses)],
            "owner_user_id": "usr_founder",
            "ttl_review_due_at": None,
            "supersedes_memory_id": None,
            "access_tags": json.dumps(["demo", "redacted"], ensure_ascii=False),
            "created_at": ts(1600 + i),
            "updated_at": ts(1600 + i),
        }
        conn.execute(
            """INSERT OR REPLACE INTO memories(memory_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
            VALUES(:memory_id,:scope,:memory_type,:canonical_text,:source_type,:source_ref,:project_id,:task_id,:agent_id,:confidence,:review_status,:owner_user_id,:ttl_review_due_at,:supersedes_memory_id,:access_tags,:created_at,:updated_at)""",
            row,
        )


def insert_audits(conn: sqlite3.Connection) -> None:
    for i in range(1, AUDITS + 1):
        entity_type = ["agents", "tasks", "runs", "tool_calls", "memories"][i % 5]
        entity_id = {
            "agents": f"agt_demo_{((i - 1) % AGENTS) + 1:02d}",
            "tasks": f"tsk_demo_{((i - 1) % TASKS) + 1:03d}",
            "runs": f"run_demo_{((i - 1) % RUNS) + 1:04d}",
            "tool_calls": f"tc_demo_{((i - 1) % TOOL_CALLS) + 1:04d}",
            "memories": f"mem_demo_{((i - 1) % MEMORIES) + 1:04d}",
        }[entity_type]
        after = {"entity_id": entity_id, "demo_index": i, "redacted": True}
        row = {
            "audit_id": f"aud_demo_{i:04d}",
            "actor_type": "system",
            "actor_id": "demo-seed-redacted",
            "action": f"demo.{entity_type}.upsert",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "before_hash": None,
            "after_hash": server.stable_hash(after),
            "metadata_json": json.dumps({"synthetic": True, "raw_transcript_stored": False}, ensure_ascii=False),
            "tamper_chain_hash": server.stable_hash({"audit": i, "after": after}),
            "created_at": ts(2200 + i),
        }
        conn.execute(
            """INSERT OR REPLACE INTO audit_logs(audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at)
            VALUES(:audit_id,:actor_type,:actor_id,:action,:entity_type,:entity_id,:before_hash,:after_hash,:metadata_json,:tamper_chain_hash,:created_at)""",
            row,
        )


def counts(conn: sqlite3.Connection) -> dict:
    return {
        "agents": conn.execute("SELECT COUNT(*) FROM agents WHERE agent_id LIKE 'agt_demo_%'").fetchone()[0],
        "tasks": conn.execute("SELECT COUNT(*) FROM tasks WHERE task_id LIKE 'tsk_demo_%'").fetchone()[0],
        "runs": conn.execute("SELECT COUNT(*) FROM runs WHERE run_id LIKE 'run_demo_%'").fetchone()[0],
        "tool_calls": conn.execute("SELECT COUNT(*) FROM tool_calls WHERE tool_call_id LIKE 'tc_demo_%'").fetchone()[0],
        "memory_candidates": conn.execute("SELECT COUNT(*) FROM memories WHERE memory_id LIKE 'mem_demo_%'").fetchone()[0],
        "audit_logs": conn.execute("SELECT COUNT(*) FROM audit_logs WHERE audit_id LIKE 'aud_demo_%'").fetchone()[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Remove prior demo_* records before seeding.")
    args = parser.parse_args()

    server.init_schema()
    with server.db() as conn:
        if args.reset:
            reset_demo(conn)
        insert_agents(conn)
        insert_tasks(conn)
        insert_runs(conn)
        insert_tool_calls(conn)
        insert_memories(conn)
        insert_audits(conn)
        conn.commit()
        print(json.dumps({"ok": True, "counts": counts(conn)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
