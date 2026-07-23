"""Shared storage-boundary parity fixture.

The fixture is deliberately standard-library only so both Free Local SQLite and
optional Postgres/BYOC smokes can import it without changing runtime
dependencies.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


FIXTURE_VERSION = "storage_boundary_shared_fixture_v1"


@dataclass(frozen=True)
class StorageOperation:
    name: str
    sql: str
    params: Mapping[str, Any] | Sequence[Any] | None = None


@dataclass(frozen=True)
class StorageQuery:
    name: str
    sql: str
    params: Mapping[str, Any] | Sequence[Any] | None = None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def fixture_operations() -> list[StorageOperation]:
    now = "2026-06-22T03:00:00+00:00"
    later = "2026-06-22T03:01:00+00:00"
    rows: list[StorageOperation] = [
        StorageOperation(
            "insert_user",
            "INSERT INTO users(user_id,name,email,role,created_at) VALUES(:user_id,:name,:email,:role,:created_at)",
            {
                "user_id": "usr_parity_founder",
                "name": "Parity Founder",
                "email": "parity@example.local",
                "role": "founder",
                "created_at": now,
            },
        ),
        StorageOperation(
            "insert_agent_a",
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""",
            {
                "agent_id": "agt_parity_a",
                "name": "Parity Agent A",
                "role": "operator",
                "description": "Shared fixture agent A.",
                "runtime_type": "mock",
                "model_provider": "mock",
                "model_name": "mock-model",
                "status": "idle",
                "permission_level": "standard",
                "allowed_tools": "[]",
                "budget_limit_usd": 0,
                "owner_user_id": "usr_parity_founder",
                "created_at": now,
                "updated_at": now,
            },
        ),
        StorageOperation(
            "insert_agent_b",
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""",
            {
                "agent_id": "agt_parity_b",
                "name": "Parity Agent B",
                "role": "operator",
                "description": "Shared fixture agent B.",
                "runtime_type": "mock",
                "model_provider": "mock",
                "model_name": "mock-model",
                "status": "idle",
                "permission_level": "standard",
                "allowed_tools": "[]",
                "budget_limit_usd": 0,
                "owner_user_id": "usr_parity_founder",
                "created_at": now,
                "updated_at": now,
            },
        ),
    ]
    for workspace, agent, task in [
        ("ws_parity_a", "agt_parity_a", "tsk_parity_a"),
        ("ws_parity_b", "agt_parity_b", "tsk_parity_b"),
    ]:
        rows.append(
            StorageOperation(
                f"insert_task_{workspace}",
                """INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
                VALUES(:task_id,:workspace_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)""",
                {
                    "task_id": task,
                    "workspace_id": workspace,
                    "title": f"Parity task {workspace}",
                    "description": "Shared storage-boundary fixture task.",
                    "requester_id": "usr_parity_founder",
                    "owner_agent_id": agent,
                    "collaborator_agent_ids": "[]",
                    "status": "planned",
                    "priority": "medium",
                    "due_date": None,
                    "acceptance_criteria": "SQLite and Postgres snapshots must match.",
                    "risk_level": "low",
                    "budget_limit_usd": 0,
                    "created_at": now,
                    "updated_at": now,
                },
            )
        )
    rows.extend(
        [
            StorageOperation(
                "update_task_a",
                """UPDATE tasks SET status=:status, updated_at=:updated_at, title=:title, description=:description,
                requester_id=:requester_id, owner_agent_id=:owner_agent_id, collaborator_agent_ids=:collaborator_agent_ids,
                priority=:priority, due_date=:due_date, acceptance_criteria=:acceptance_criteria,
                risk_level=:risk_level, budget_limit_usd=:budget_limit_usd, workspace_id=:workspace_id
                WHERE task_id=:task_id""",
                {
                    "task_id": "tsk_parity_a",
                    "workspace_id": "ws_parity_a",
                    "title": "Parity task ws_parity_a",
                    "description": "Shared storage-boundary fixture task.",
                    "requester_id": "usr_parity_founder",
                    "owner_agent_id": "agt_parity_a",
                    "collaborator_agent_ids": "[]",
                    "status": "running",
                    "priority": "medium",
                    "due_date": None,
                    "acceptance_criteria": "SQLite and Postgres snapshots must match.",
                    "risk_level": "low",
                    "budget_limit_usd": 0,
                    "updated_at": later,
                },
            ),
            StorageOperation(
                "insert_run_a",
                """INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
                VALUES(:run_id,:workspace_id,:task_id,:agent_id,:runtime_type,:status,:started_at,:ended_at,:duration_ms,:input_summary,:output_summary,:model_provider,:model_name,:input_tokens,:output_tokens,:reasoning_tokens,:cost_usd,:error_type,:error_message,:trace_id,:parent_run_id,:delegation_id,:approval_required,:created_at)""",
                {
                    "run_id": "run_parity_a",
                    "workspace_id": "ws_parity_a",
                    "task_id": "tsk_parity_a",
                    "agent_id": "agt_parity_a",
                    "runtime_type": "mock",
                    "status": "completed",
                    "started_at": now,
                    "ended_at": later,
                    "duration_ms": 11,
                    "input_summary": "Shared fixture input summary.",
                    "output_summary": "Shared fixture output summary.",
                    "model_provider": "mock",
                    "model_name": "mock-model",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "reasoning_tokens": 0,
                    "cost_usd": 0,
                    "error_type": None,
                    "error_message": None,
                    "trace_id": "trace_parity_a",
                    "parent_run_id": None,
                    "delegation_id": None,
                    "approval_required": 0,
                    "created_at": now,
                },
            ),
            StorageOperation(
                "insert_run_b",
                """INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
                VALUES(:run_id,:workspace_id,:task_id,:agent_id,:runtime_type,:status,:started_at,:ended_at,:duration_ms,:input_summary,:output_summary,:model_provider,:model_name,:input_tokens,:output_tokens,:reasoning_tokens,:cost_usd,:error_type,:error_message,:trace_id,:parent_run_id,:delegation_id,:approval_required,:created_at)""",
                {
                    "run_id": "run_parity_b",
                    "workspace_id": "ws_parity_b",
                    "task_id": "tsk_parity_b",
                    "agent_id": "agt_parity_b",
                    "runtime_type": "mock",
                    "status": "completed",
                    "started_at": now,
                    "ended_at": later,
                    "duration_ms": 13,
                    "input_summary": "Shared fixture input summary B.",
                    "output_summary": "Shared fixture output summary B.",
                    "model_provider": "mock",
                    "model_name": "mock-model",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "reasoning_tokens": 0,
                    "cost_usd": 0,
                    "error_type": None,
                    "error_message": None,
                    "trace_id": "trace_parity_b",
                    "parent_run_id": None,
                    "delegation_id": None,
                    "approval_required": 0,
                    "created_at": now,
                },
            ),
            StorageOperation(
                "insert_tool_call",
                """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
                VALUES(:tool_call_id,:run_id,:agent_id,:tool_name,:tool_version,:tool_category,:normalized_args_json,:target_resource,:risk_level,:status,:result_summary,:side_effect_id,:started_at,:ended_at,:created_at)""",
                {
                    "tool_call_id": "tc_parity_a",
                    "run_id": "run_parity_a",
                    "agent_id": "agt_parity_a",
                    "tool_name": "shared_fixture_tool",
                    "tool_version": "v1",
                    "tool_category": "database",
                    "normalized_args_json": _json({"workspace_id": "ws_parity_a"}),
                    "target_resource": "postgres://parity",
                    "risk_level": "high",
                    "status": "waiting_approval",
                    "result_summary": "Prepared action pending.",
                    "side_effect_id": None,
                    "started_at": now,
                    "ended_at": None,
                    "created_at": now,
                },
            ),
            StorageOperation(
                "insert_approval",
                """INSERT INTO approvals(approval_id,approval_kind,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,decision,reason,expires_at,created_at,decided_at)
                VALUES(:approval_id,'tool_execution',:task_id,:run_id,:tool_call_id,:requested_by_agent_id,:approver_user_id,:decision,:reason,:expires_at,:created_at,:decided_at)""",
                {
                    "approval_id": "ap_parity_a",
                    "task_id": "tsk_parity_a",
                    "run_id": "run_parity_a",
                    "tool_call_id": "tc_parity_a",
                    "requested_by_agent_id": "agt_parity_a",
                    "approver_user_id": None,
                    "decision": "pending",
                    "reason": "Shared parity approval.",
                    "expires_at": None,
                    "created_at": now,
                    "decided_at": None,
                },
            ),
            StorageOperation(
                "insert_prepared_action",
                """INSERT INTO prepared_actions(prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,requested_by_agent_id,action_type,provider,target_resource,normalized_args_json,args_hash,snapshot_ref,snapshot_hash,status,result_json,created_at,updated_at,approved_at,consumed_at)
                VALUES(:prepared_action_id,:workspace_id,:task_id,:run_id,:tool_call_id,:approval_id,:requested_by_agent_id,:action_type,:provider,:target_resource,:normalized_args_json,:args_hash,:snapshot_ref,:snapshot_hash,:status,:result_json,:created_at,:updated_at,:approved_at,:consumed_at)""",
                {
                    "prepared_action_id": "pact_parity_a",
                    "workspace_id": "ws_parity_a",
                    "task_id": "tsk_parity_a",
                    "run_id": "run_parity_a",
                    "tool_call_id": "tc_parity_a",
                    "approval_id": "ap_parity_a",
                    "requested_by_agent_id": "agt_parity_a",
                    "action_type": "runtime.external_write",
                    "provider": "shared-fixture",
                    "target_resource": "postgres://parity",
                    "normalized_args_json": _json({"workspace_id": "ws_parity_a"}),
                    "args_hash": "args_hash_parity_a",
                    "snapshot_ref": "snapshot://parity/a",
                    "snapshot_hash": "snapshot_hash_parity_a",
                    "status": "waiting_approval",
                    "result_json": "{}",
                    "created_at": now,
                    "updated_at": now,
                    "approved_at": None,
                    "consumed_at": None,
                },
            ),
            StorageOperation(
                "consume_prepared_action",
                """UPDATE prepared_actions SET status=:status, result_json=:result_json, updated_at=:updated_at,
                approved_at=:approved_at, consumed_at=:consumed_at WHERE prepared_action_id=:prepared_action_id""",
                {
                    "prepared_action_id": "pact_parity_a",
                    "status": "consumed",
                    "result_json": _json({"provider_result_id": "shared-fixture-result"}),
                    "updated_at": later,
                    "approved_at": later,
                    "consumed_at": later,
                },
            ),
            StorageOperation(
                "insert_evaluation",
                """INSERT INTO evaluations(evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at)
                VALUES(:evaluation_id,:task_id,:run_id,:agent_id,:evaluator_type,:score,:pass_fail,:rubric_json,:notes,:created_at)""",
                {
                    "evaluation_id": "eval_parity_a",
                    "task_id": "tsk_parity_a",
                    "run_id": "run_parity_a",
                    "agent_id": "agt_parity_a",
                    "evaluator_type": "rule",
                    "score": 1.0,
                    "pass_fail": "pass",
                    "rubric_json": _json({"shared_fixture": True}),
                    "notes": "Shared fixture evaluation.",
                    "created_at": now,
                },
            ),
            StorageOperation(
                "insert_artifact",
                """INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,uri,summary,created_at)
                VALUES(:artifact_id,:task_id,:run_id,:artifact_type,:title,:uri,:summary,:created_at)""",
                {
                    "artifact_id": "art_parity_a",
                    "task_id": "tsk_parity_a",
                    "run_id": "run_parity_a",
                    "artifact_type": "report",
                    "title": "Shared Fixture Artifact",
                    "uri": None,
                    "summary": "Shared fixture artifact summary.",
                    "created_at": now,
                },
            ),
            StorageOperation(
                "insert_memory",
                """INSERT INTO memories(memory_id,workspace_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
                VALUES(:memory_id,:workspace_id,:scope,:memory_type,:canonical_text,:source_type,:source_ref,:project_id,:task_id,:agent_id,:confidence,:review_status,:owner_user_id,:ttl_review_due_at,:supersedes_memory_id,:access_tags,:created_at,:updated_at)""",
                {
                    "memory_id": "mem_parity_a",
                    "workspace_id": "ws_parity_a",
                    "scope": "task",
                    "memory_type": "artifact_summary",
                    "canonical_text": "Shared fixture memory candidate.",
                    "source_type": "run_log",
                    "source_ref": "run_parity_a",
                    "project_id": "proj_parity",
                    "task_id": "tsk_parity_a",
                    "agent_id": "agt_parity_a",
                    "confidence": 0.91,
                    "review_status": "approved",
                    "owner_user_id": "usr_parity_founder",
                    "ttl_review_due_at": None,
                    "supersedes_memory_id": None,
                    "access_tags": _json(["shared", "parity"]),
                    "created_at": now,
                    "updated_at": later,
                },
            ),
            StorageOperation(
                "insert_workflow_job",
                """INSERT INTO workflow_jobs(job_id,workspace_id,workflow_type,status,template_id,adapter,confirm_run,title,input_summary,request_hash,result_json,result_task_id,result_run_id,result_artifact_id,error_message,created_at,started_at,completed_at,updated_at)
                VALUES(:job_id,:workspace_id,:workflow_type,:status,:template_id,:adapter,:confirm_run,:title,:input_summary,:request_hash,:result_json,:result_task_id,:result_run_id,:result_artifact_id,:error_message,:created_at,:started_at,:completed_at,:updated_at)""",
                {
                    "job_id": "wfjob_parity_a",
                    "workspace_id": "ws_parity_a",
                    "workflow_type": "customer_worker_task",
                    "status": "queued",
                    "template_id": None,
                    "adapter": "mock",
                    "confirm_run": 0,
                    "title": "Shared fixture workflow job",
                    "input_summary": "No raw prompt stored.",
                    "request_hash": "request_hash_parity",
                    "result_json": "{}",
                    "result_task_id": "tsk_parity_a",
                    "result_run_id": "run_parity_a",
                    "result_artifact_id": "art_parity_a",
                    "error_message": None,
                    "created_at": now,
                    "started_at": None,
                    "completed_at": None,
                    "updated_at": now,
                },
            ),
            StorageOperation(
                "insert_agent_plan",
                """INSERT INTO agent_plans(plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,referenced_specs_json,referenced_memories_json,referenced_bases_json,proposed_files_to_change_json,risk_level,approval_required,execution_steps_json,verification_plan,rollback_plan,status,created_at,updated_at)
                VALUES(:plan_id,:workspace_id,:task_id,:run_id,:agent_id,:task_understanding,:referenced_specs_json,:referenced_memories_json,:referenced_bases_json,:proposed_files_to_change_json,:risk_level,:approval_required,:execution_steps_json,:verification_plan,:rollback_plan,:status,:created_at,:updated_at)""",
                {
                    "plan_id": "plan_parity_a",
                    "workspace_id": "ws_parity_a",
                    "task_id": "tsk_parity_a",
                    "run_id": "run_parity_a",
                    "agent_id": "agt_parity_a",
                    "task_understanding": "Prove shared storage parity fixture.",
                    "referenced_specs_json": _json(["docs/POSTGRES_PARITY_CONTRACT.md"]),
                    "referenced_memories_json": "[]",
                    "referenced_bases_json": "[]",
                    "proposed_files_to_change_json": _json(["agentops_mis_storage/parity_fixture.py"]),
                    "risk_level": "low",
                    "approval_required": 0,
                    "execution_steps_json": _json(["insert", "query", "compare"]),
                    "verification_plan": "Run SQLite/Postgres parity smoke.",
                    "rollback_plan": "Drop temporary databases.",
                    "status": "submitted",
                    "created_at": now,
                    "updated_at": later,
                },
            ),
            StorageOperation(
                "insert_plan_evidence",
                """INSERT INTO plan_evidence_manifests(manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,expected_steps_json,tool_call_ids_json,evaluation_ids_json,artifact_ids_json,audit_ids_json,status,verification_json,created_at,updated_at)
                VALUES(:manifest_id,:workspace_id,:plan_id,:task_id,:run_id,:agent_id,:mismatch_policy,:expected_steps_json,:tool_call_ids_json,:evaluation_ids_json,:artifact_ids_json,:audit_ids_json,:status,:verification_json,:created_at,:updated_at)""",
                {
                    "manifest_id": "pem_parity_a",
                    "workspace_id": "ws_parity_a",
                    "plan_id": "plan_parity_a",
                    "task_id": "tsk_parity_a",
                    "run_id": "run_parity_a",
                    "agent_id": "agt_parity_a",
                    "mismatch_policy": "block",
                    "expected_steps_json": _json(["insert", "query", "compare"]),
                    "tool_call_ids_json": _json(["tc_parity_a"]),
                    "evaluation_ids_json": _json(["eval_parity_a"]),
                    "artifact_ids_json": _json(["art_parity_a"]),
                    "audit_ids_json": "[]",
                    "status": "verified",
                    "verification_json": _json({"shared_fixture": True}),
                    "created_at": now,
                    "updated_at": later,
                },
            ),
            StorageOperation(
                "insert_audit",
                """INSERT INTO audit_logs(audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at)
                VALUES(:audit_id,:actor_type,:actor_id,:action,:entity_type,:entity_id,:before_hash,:after_hash,:metadata_json,:tamper_chain_hash,:created_at)""",
                {
                    "audit_id": "aud_parity_a",
                    "actor_type": "system",
                    "actor_id": "storage-parity-fixture",
                    "action": "storage.parity_fixture",
                    "entity_type": "tasks",
                    "entity_id": "tsk_parity_a",
                    "before_hash": None,
                    "after_hash": "after_hash_parity",
                    "metadata_json": _json({"workspace_id": "ws_parity_a"}),
                    "tamper_chain_hash": "chain_hash_parity",
                    "created_at": later,
                },
            ),
        ]
    )
    return rows


def fixture_queries() -> list[StorageQuery]:
    return [
        StorageQuery("workspace_a_tasks", "SELECT task_id,workspace_id,status FROM tasks WHERE workspace_id=? ORDER BY task_id", ["ws_parity_a"]),
        StorageQuery("workspace_a_runs", "SELECT run_id,workspace_id,status FROM runs WHERE workspace_id=? ORDER BY run_id", ["ws_parity_a"]),
        StorageQuery("workspace_a_prepared", "SELECT prepared_action_id,workspace_id,status,result_json FROM prepared_actions WHERE workspace_id=? ORDER BY prepared_action_id", ["ws_parity_a"]),
        StorageQuery("workspace_a_memory", "SELECT memory_id,workspace_id,review_status FROM memories WHERE workspace_id=? ORDER BY memory_id", ["ws_parity_a"]),
        StorageQuery("workspace_a_evaluations", "SELECT evaluation_id,pass_fail,score FROM evaluations WHERE run_id=? ORDER BY evaluation_id", ["run_parity_a"]),
        StorageQuery("workspace_a_artifacts", "SELECT artifact_id,artifact_type,title FROM artifacts WHERE run_id=? ORDER BY artifact_id", ["run_parity_a"]),
        StorageQuery("workspace_a_workflow_jobs", "SELECT job_id,workspace_id,status FROM workflow_jobs WHERE workspace_id=? ORDER BY job_id", ["ws_parity_a"]),
        StorageQuery("workspace_a_plan_evidence", "SELECT manifest_id,workspace_id,status FROM plan_evidence_manifests WHERE workspace_id=? ORDER BY manifest_id", ["ws_parity_a"]),
        StorageQuery("workspace_a_audit", "SELECT audit_id,actor_type,action,entity_id FROM audit_logs WHERE entity_id=? ORDER BY audit_id", ["tsk_parity_a"]),
        StorageQuery("cross_workspace_task_exclusion", "SELECT task_id FROM tasks WHERE workspace_id=? AND task_id=?", ["ws_parity_a", "tsk_parity_b"]),
        StorageQuery("literal_question_mark", "SELECT '?' AS literal_value, task_id FROM tasks WHERE task_id=?", ["tsk_parity_a"]),
    ]


def normalize_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = {}
        for key, value in dict(row).items():
            if isinstance(value, float) and value.is_integer():
                item[key] = int(value)
            else:
                item[key] = value
        normalized.append(item)
    return normalized


def snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
