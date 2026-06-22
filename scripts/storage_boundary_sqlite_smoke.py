#!/usr/bin/env python3
"""Verify the first SQLite storage-boundary helpers preserve workspace behavior."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import datetime as dt
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def ids(rows, key: str) -> set[str]:
    return {str(row[key]) for row in rows if row[key]}


def main() -> int:
    owned_db = "AGENTOPS_DB_PATH" not in os.environ
    db_path = ""
    if owned_db:
        handle = tempfile.NamedTemporaryFile(prefix="agentops-storage-boundary-", delete=False)
        db_path = handle.name
        handle.close()
        os.environ["AGENTOPS_DB_PATH"] = db_path

    import server  # noqa: PLC0415

    workspace_a = "ws_storage_a"
    workspace_b = "ws_storage_b"
    agent_a = "agt_storage_a"
    agent_b = "agt_storage_b"
    task_a = "tsk_storage_a"
    task_b = "tsk_storage_b"
    write_task = "tsk_storage_write"
    write_run = "run_storage_write"
    write_tool_call = "tc_storage_write"
    write_runtime_event = "rte_storage_write"
    write_audit = "aud_storage_write"
    write_plan = "plan_storage_write"
    write_manifest = "pem_storage_write"
    write_approval = "ap_storage_write"
    write_eval = "eval_storage_write"
    write_artifact = "art_storage_write"
    write_memory = "mem_storage_write"
    job_a = "wfjob_storage_a"
    job_b = "wfjob_storage_b"
    token_id_a = ""
    token_id_b = ""
    session_id_a = ""
    session_id_b = ""

    try:
        server.init_schema()
        with server.db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
                ("usr_founder", "Founder", "founder@example.local", "founder", server.now_iso()),
            )
            server.ensure_gateway_agent(conn, agent_a, runtime_type="mock")
            server.ensure_gateway_agent(conn, agent_b, runtime_type="mock")
            enrollment_a, status = server.agent_gateway_create_enrollment(conn, {
                "workspace_id": workspace_a,
                "agent_id": agent_a,
                "name": "Storage Boundary Agent A",
                "runtime_type": "mock",
                "scopes": ["tasks:read", "agents:heartbeat"],
                "ttl_days": 1,
            })
            require(status == 201, f"enrollment A create failed: {status} {enrollment_a}")
            enrollment_b, status = server.agent_gateway_create_enrollment(conn, {
                "workspace_id": workspace_b,
                "agent_id": agent_b,
                "name": "Storage Boundary Agent B",
                "runtime_type": "mock",
                "scopes": ["tasks:read", "agents:heartbeat"],
                "ttl_days": 1,
            })
            require(status == 201, f"enrollment B create failed: {status} {enrollment_b}")
            token_id_a = enrollment_a["token_id"]
            token_id_b = enrollment_b["token_id"]
            session_a, status = server.agent_gateway_create_session(conn, {
                "Authorization": f"Bearer {enrollment_a['token']}",
                "X-AgentOps-Workspace-Id": workspace_a,
            }, {"ttl_sec": 120, "scopes": ["tasks:read"]})
            require(status == 201, f"session A create failed: {status} {session_a}")
            session_b, status = server.agent_gateway_create_session(conn, {
                "Authorization": f"Bearer {enrollment_b['token']}",
                "X-AgentOps-Workspace-Id": workspace_b,
            }, {"ttl_sec": 120, "scopes": ["tasks:read"]})
            require(status == 201, f"session B create failed: {status} {session_b}")
            session_id_a = session_a["session_id"]
            session_id_b = session_b["session_id"]
            for workspace_id, agent_id, task_id in [
                (workspace_a, agent_a, task_a),
                (workspace_b, agent_b, task_b),
            ]:
                payload, status = server.create_task_api(conn, {
                    "workspace_id": workspace_id,
                    "task_id": task_id,
                    "title": f"Storage boundary {workspace_id}",
                    "description": "Storage boundary helper smoke task.",
                    "requester_id": "usr_founder",
                    "owner_agent_id": agent_id,
                    "status": "planned",
                    "priority": "medium",
                    "risk_level": "low",
                })
                require(status == 201, f"task create failed: {status} {payload}")
            run_a = server.start_mock_run(conn, {"task_id": task_a, "agent_id": agent_a})["run_id"]
            run_b = server.start_mock_run(conn, {"task_id": task_b, "agent_id": agent_b})["run_id"]
            approval_a, status = server.agent_gateway_request_approval(conn, {
                "workspace_id": workspace_a,
                "agent_id": agent_a,
                "run_id": run_a,
                "reason": "Storage boundary approval A.",
            })
            require(status == 201, f"approval A request failed: {status} {approval_a}")
            approval_b, status = server.agent_gateway_request_approval(conn, {
                "workspace_id": workspace_b,
                "agent_id": agent_b,
                "run_id": run_b,
                "reason": "Storage boundary approval B.",
            })
            require(status == 201, f"approval B request failed: {status} {approval_b}")
            evaluation_a, status = server.agent_gateway_eval_submit(conn, {
                "workspace_id": workspace_a,
                "agent_id": agent_a,
                "run_id": run_a,
                "score": 0.91,
                "pass_fail": "pass",
                "notes": "Storage boundary evaluation A.",
            })
            require(status == 201, f"evaluation A submit failed: {status} {evaluation_a}")
            evaluation_b, status = server.agent_gateway_eval_submit(conn, {
                "workspace_id": workspace_b,
                "agent_id": agent_b,
                "run_id": run_b,
                "score": 0.92,
                "pass_fail": "pass",
                "notes": "Storage boundary evaluation B.",
            })
            require(status == 201, f"evaluation B submit failed: {status} {evaluation_b}")
            artifact_a, status = server.agent_gateway_record_artifact(conn, {
                "workspace_id": workspace_a,
                "agent_id": agent_a,
                "run_id": run_a,
                "artifact_type": "report",
                "title": "Storage Boundary Artifact A",
                "summary": "Storage boundary artifact A.",
                "content_hash": "hash_storage_a",
            })
            require(status == 201, f"artifact A record failed: {status} {artifact_a}")
            artifact_b, status = server.agent_gateway_record_artifact(conn, {
                "workspace_id": workspace_b,
                "agent_id": agent_b,
                "run_id": run_b,
                "artifact_type": "report",
                "title": "Storage Boundary Artifact B",
                "summary": "Storage boundary artifact B.",
                "content_hash": "hash_storage_b",
            })
            require(status == 201, f"artifact B record failed: {status} {artifact_b}")
            memory_a, status = server.agent_gateway_memory_propose(conn, {
                "workspace_id": workspace_a,
                "agent_id": agent_a,
                "task_id": task_a,
                "scope": "task",
                "memory_type": "artifact_summary",
                "canonical_text": "Storage boundary memory A.",
            })
            require(status == 201, f"memory A propose failed: {status} {memory_a}")
            memory_b, status = server.agent_gateway_memory_propose(conn, {
                "workspace_id": workspace_b,
                "agent_id": agent_b,
                "task_id": task_b,
                "scope": "task",
                "memory_type": "artifact_summary",
                "canonical_text": "Storage boundary memory B.",
            })
            require(status == 201, f"memory B propose failed: {status} {memory_b}")
            org_memory_a, status = server.agent_gateway_memory_propose(conn, {
                "workspace_id": workspace_a,
                "agent_id": agent_a,
                "scope": "org",
                "memory_type": "policy",
                "canonical_text": "Storage boundary org memory A.",
            })
            require(status == 201, f"org memory propose failed: {status} {org_memory_a}")
            old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=120)).isoformat()
            for workspace_id, agent_id, task_id, run_id, artifact_id, job_id in [
                (workspace_a, agent_a, task_a, run_a, artifact_a["artifact"]["artifact_id"], job_a),
                (workspace_b, agent_b, task_b, run_b, artifact_b["artifact"]["artifact_id"], job_b),
            ]:
                before_job, job_outcome = server.repo_upsert_workflow_job(conn, {
                    "job_id": job_id,
                    "workspace_id": workspace_id,
                    "workflow_type": "customer_worker_task",
                    "status": "queued",
                    "template_id": None,
                    "adapter": "mock",
                    "confirm_run": 0,
                    "title": f"Storage boundary workflow job {workspace_id}",
                    "input_summary": "Synthetic workflow job for storage-boundary smoke. Raw prompt omitted.",
                    "request_hash": f"hash_{job_id}",
                    "result_json": "{}",
                    "result_task_id": task_id,
                    "result_run_id": run_id,
                    "result_artifact_id": artifact_id,
                    "error_message": None,
                    "created_at": old,
                    "started_at": None,
                    "completed_at": None,
                    "updated_at": old,
                })
                require(before_job is None and job_outcome == "created", f"workflow job write helper create failed: {job_id} {job_outcome}")
            conn.commit()

            task_ids = ids(server.repo_list_workspace_tasks(conn, workspace_a), "task_id")
            require(task_a in task_ids and task_b not in task_ids, f"task helper leaked workspace rows: {task_ids}")
            require(server.repo_get_workspace_task(conn, workspace_a, task_a), "task helper missed workspace A task")
            require(not server.repo_get_workspace_task(conn, workspace_a, task_b), "task helper exposed workspace B task")

            run_ids = ids(server.repo_list_workspace_runs(conn, workspace_a), "run_id")
            require(run_a in run_ids and run_b not in run_ids, f"run helper leaked workspace rows: {run_ids}")
            require(ids(server.repo_list_workspace_runs(conn, workspace_a, task_id=task_a), "run_id") == {run_a}, "run helper task filter failed")
            require(ids(server.repo_list_workspace_runs(conn, workspace_a, agent_id=agent_a), "run_id") == {run_a}, "run helper agent filter failed")
            require(server.repo_get_workspace_run(conn, workspace_a, run_a), "run helper missed workspace A run")
            require(not server.repo_get_workspace_run(conn, workspace_a, run_b), "run helper exposed workspace B run")

            task_a_status = server.repo_get_workspace_task(conn, workspace_a, task_a)["status"]
            gateway_pull_ids = ids(server.repo_pull_agent_gateway_tasks(conn, workspace_a, agent_a, [task_a_status], 20), "task_id")
            require(task_a in gateway_pull_ids and task_b not in gateway_pull_ids, f"gateway task pull helper leaked workspace rows: {gateway_pull_ids}")
            gateway_task_ids = ids(server.repo_list_agent_gateway_tasks(conn, workspace_a, agent_id=agent_a, bound_visibility=True, limit=20), "task_id")
            require(task_a in gateway_task_ids and task_b not in gateway_task_ids, f"gateway task list helper leaked workspace rows: {gateway_task_ids}")
            require(server.repo_get_agent_gateway_task(conn, workspace_a, task_a), "gateway task helper missed workspace A task")
            require(not server.repo_get_agent_gateway_task(conn, workspace_a, task_b), "gateway task helper exposed workspace B task")

            gateway_run_ids = ids(server.repo_list_agent_gateway_runs(conn, workspace_a, agent_id=agent_a, bound_visibility=True, limit=20), "run_id")
            require(run_a in gateway_run_ids and run_b not in gateway_run_ids, f"gateway run list helper leaked workspace rows: {gateway_run_ids}")
            require(server.repo_get_agent_gateway_run(conn, workspace_a, run_a), "gateway run helper missed workspace A run")
            require(not server.repo_get_agent_gateway_run(conn, workspace_a, run_b), "gateway run helper exposed workspace B run")

            write_now = server.now_iso()
            write_task_row = {
                "task_id": write_task,
                "workspace_id": workspace_a,
                "title": "Storage write boundary task",
                "description": "Created through repo_upsert_task.",
                "requester_id": "usr_founder",
                "owner_agent_id": agent_a,
                "collaborator_agent_ids": "[]",
                "status": "planned",
                "priority": "medium",
                "due_date": None,
                "acceptance_criteria": "Write helper smoke must create and update task rows.",
                "risk_level": "low",
                "budget_limit_usd": 1.0,
                "created_at": write_now,
                "updated_at": write_now,
            }
            before_task, task_outcome = server.repo_upsert_task(conn, dict(write_task_row))
            require(before_task is None and task_outcome == "created", f"task write helper create failed: {task_outcome}")
            write_task_row["status"] = "running"
            write_task_row["updated_at"] = server.now_iso()
            before_task, task_outcome = server.repo_upsert_task(conn, dict(write_task_row))
            require(before_task and task_outcome == "updated", f"task write helper update failed: {task_outcome}")
            require(server.repo_get_workspace_task(conn, workspace_a, write_task)["status"] == "running", "task write helper did not persist update")

            write_run_row = {
                "run_id": write_run,
                "workspace_id": workspace_a,
                "task_id": write_task,
                "agent_id": agent_a,
                "runtime_type": "mock",
                "status": "running",
                "started_at": write_now,
                "ended_at": None,
                "duration_ms": None,
                "input_summary": "Storage write boundary run.",
                "output_summary": None,
                "model_provider": "mock-provider",
                "model_name": "mock-model",
                "input_tokens": 1,
                "output_tokens": 0,
                "reasoning_tokens": 0,
                "cost_usd": 0,
                "error_type": None,
                "error_message": None,
                "trace_id": "trace_storage_write",
                "parent_run_id": None,
                "delegation_id": "del_storage_write",
                "approval_required": 0,
                "created_at": write_now,
            }
            before_run, run_outcome = server.repo_upsert_run(conn, dict(write_run_row))
            require(before_run is None and run_outcome == "created", f"run write helper create failed: {run_outcome}")
            write_run_row["status"] = "completed"
            write_run_row["ended_at"] = server.now_iso()
            write_run_row["duration_ms"] = 1
            write_run_row["output_summary"] = "Storage write boundary run completed."
            before_run, run_outcome = server.repo_upsert_run(conn, dict(write_run_row))
            require(before_run and run_outcome == "updated", f"run write helper update failed: {run_outcome}")
            require(server.repo_get_workspace_run(conn, workspace_a, write_run)["status"] == "completed", "run write helper did not persist update")

            write_tool_call_row = {
                "tool_call_id": write_tool_call,
                "run_id": write_run,
                "agent_id": agent_a,
                "tool_name": "storage.boundary",
                "tool_version": "v1",
                "tool_category": "custom",
                "normalized_args_json": json.dumps({"raw_omitted": True}, ensure_ascii=False),
                "target_resource": "local://storage-boundary",
                "risk_level": "low",
                "status": "completed",
                "result_summary": "Storage write boundary tool call.",
                "side_effect_id": None,
                "started_at": write_now,
                "ended_at": write_now,
                "created_at": write_now,
            }
            before_tool, tool_outcome = server.repo_upsert_tool_call(conn, dict(write_tool_call_row))
            require(before_tool is None and tool_outcome == "created", f"tool call write helper create failed: {tool_outcome}")
            write_tool_call_row["result_summary"] = "Storage write boundary tool call updated."
            before_tool, tool_outcome = server.repo_upsert_tool_call(conn, dict(write_tool_call_row))
            require(before_tool and tool_outcome == "updated", f"tool call write helper update failed: {tool_outcome}")
            write_run_detail = server.repo_run_detail(conn, server.repo_get_workspace_run(conn, workspace_a, write_run))
            require(
                any(row["tool_call_id"] == write_tool_call and row["result_summary"].endswith("updated.") for row in write_run_detail["tool_calls"]),
                "tool call write helper row not visible in run detail",
            )

            runtime_event_row = {
                "runtime_event_id": write_runtime_event,
                "runtime_connector_id": "rtc_agent_gateway_local",
                "event_type": "storage.boundary",
                "status": "completed",
                "run_id": write_run,
                "task_id": write_task,
                "agent_id": agent_a,
                "model_name": "storage-boundary",
                "latency_ms": 1,
                "prompt_hash": "prompt_hash_storage_boundary",
                "input_summary": "Storage boundary runtime event.",
                "output_summary": "Storage boundary runtime event stored.",
                "error_message": None,
                "raw_payload_hash": "payload_hash_storage_boundary",
                "created_at": write_now,
            }
            server.repo_insert_runtime_event(conn, dict(runtime_event_row))
            runtime_event_count = conn.execute(
                "SELECT COUNT(*) c FROM runtime_events WHERE runtime_event_id=? AND run_id=? AND task_id=?",
                (write_runtime_event, write_run, write_task),
            ).fetchone()["c"]
            require(runtime_event_count == 1, "runtime event write helper did not persist row")

            server.repo_insert_audit_log(conn, {
                "audit_id": write_audit,
                "actor_type": "system",
                "actor_id": "storage-boundary-smoke",
                "action": "storage_boundary.audit_append",
                "entity_type": "tasks",
                "entity_id": write_task,
                "before_hash": None,
                "after_hash": server.stable_hash({"task_id": write_task, "status": "completed"}),
                "created_at": write_now,
            }, {"workspace_id": workspace_a, "raw_omitted": True})
            write_audit_row = conn.execute("SELECT * FROM audit_logs WHERE audit_id=?", (write_audit,)).fetchone()
            require(write_audit_row and write_audit_row["tamper_chain_hash"], "audit write helper did not persist tamper-chain row")

            write_approval_row = {
                "approval_id": write_approval,
                "task_id": write_task,
                "run_id": write_run,
                "tool_call_id": None,
                "requested_by_agent_id": agent_a,
                "approver_user_id": "usr_founder",
                "decision": "pending",
                "reason": "Storage write boundary approval.",
                "expires_at": server.now_iso(),
                "created_at": write_now,
                "decided_at": None,
            }
            before_approval, approval_outcome = server.repo_upsert_approval(conn, dict(write_approval_row))
            require(before_approval is None and approval_outcome == "created", f"approval write helper create failed: {approval_outcome}")
            write_approval_row["decision"] = "approved"
            write_approval_row["decided_at"] = server.now_iso()
            before_approval, approval_outcome = server.repo_upsert_approval(conn, dict(write_approval_row))
            require(before_approval and approval_outcome == "updated", f"approval write helper update failed: {approval_outcome}")
            approval_ids_after_write = ids(server.repo_list_workspace_approvals(conn, workspace_a), "approval_id")
            require(write_approval in approval_ids_after_write, f"approval write helper row not visible in workspace list: {approval_ids_after_write}")

            write_eval_row = {
                "evaluation_id": write_eval,
                "task_id": write_task,
                "run_id": write_run,
                "agent_id": agent_a,
                "evaluator_type": "rule",
                "score": 0.8,
                "pass_fail": "pass",
                "rubric_json": json.dumps({"storage_boundary": True}, ensure_ascii=False),
                "notes": "Storage write boundary evaluation.",
                "created_at": write_now,
            }
            before_eval, eval_outcome = server.repo_upsert_evaluation(conn, dict(write_eval_row))
            require(before_eval is None and eval_outcome == "created", f"evaluation write helper create failed: {eval_outcome}")
            write_eval_row["score"] = 0.93
            write_eval_row["notes"] = "Storage write boundary evaluation updated."
            before_eval, eval_outcome = server.repo_upsert_evaluation(conn, dict(write_eval_row))
            require(before_eval and eval_outcome == "updated", f"evaluation write helper update failed: {eval_outcome}")
            evaluation_ids_after_write = ids(server.repo_list_workspace_evaluations(conn, workspace_a), "evaluation_id")
            require(write_eval in evaluation_ids_after_write, f"evaluation write helper row not visible in workspace list: {evaluation_ids_after_write}")

            write_artifact_row = {
                "artifact_id": write_artifact,
                "task_id": write_task,
                "run_id": write_run,
                "artifact_type": "markdown",
                "title": "Storage Write Boundary Artifact",
                "uri": "artifact://storage/write",
                "summary": "Storage write boundary artifact.",
                "created_at": write_now,
            }
            before_artifact, artifact_outcome = server.repo_upsert_artifact(conn, dict(write_artifact_row))
            require(before_artifact is None and artifact_outcome == "created", f"artifact write helper create failed: {artifact_outcome}")
            write_artifact_row["summary"] = "Storage write boundary artifact updated."
            before_artifact, artifact_outcome = server.repo_upsert_artifact(conn, dict(write_artifact_row))
            require(before_artifact and artifact_outcome == "updated", f"artifact write helper update failed: {artifact_outcome}")
            artifact_ids_after_write = ids(server.repo_list_workspace_artifacts(conn, workspace_a), "artifact_id")
            require(write_artifact in artifact_ids_after_write, f"artifact write helper row not visible in workspace list: {artifact_ids_after_write}")

            write_memory_row = {
                "memory_id": write_memory,
                "workspace_id": workspace_a,
                "scope": "task",
                "memory_type": "artifact_summary",
                "canonical_text": "Storage write boundary memory.",
                "source_type": "run_log",
                "source_ref": write_run,
                "project_id": "proj_mvp",
                "task_id": write_task,
                "agent_id": agent_a,
                "confidence": 0.77,
                "review_status": "candidate",
                "owner_user_id": "usr_founder",
                "ttl_review_due_at": server.now_iso(),
                "supersedes_memory_id": None,
                "access_tags": json.dumps(["storage-boundary"], ensure_ascii=False),
                "created_at": write_now,
                "updated_at": write_now,
            }
            before_memory, memory_outcome = server.repo_upsert_memory_candidate(conn, dict(write_memory_row))
            require(before_memory is None and memory_outcome == "created", f"memory write helper create failed: {memory_outcome}")
            write_memory_row["canonical_text"] = "Storage write boundary memory updated."
            write_memory_row["confidence"] = 0.91
            write_memory_row["updated_at"] = server.now_iso()
            before_memory, memory_outcome = server.repo_upsert_memory_candidate(conn, dict(write_memory_row))
            require(before_memory and memory_outcome == "updated", f"memory write helper update failed: {memory_outcome}")
            require(server.repo_get_workspace_memory(conn, workspace_a, write_memory)["confidence"] == 0.91, "memory write helper did not persist update")

            write_plan_row = {
                "plan_id": write_plan,
                "workspace_id": workspace_a,
                "task_id": write_task,
                "run_id": write_run,
                "agent_id": agent_a,
                "task_understanding": "Storage boundary plan covers repo write helper evidence.",
                "referenced_specs_json": json.dumps(["docs/STORAGE_BOUNDARY_MAP.md"], ensure_ascii=False),
                "referenced_memories_json": json.dumps([write_memory], ensure_ascii=False),
                "referenced_bases_json": json.dumps(["base_local_tasks"], ensure_ascii=False),
                "proposed_files_to_change_json": json.dumps(["server.py", "scripts/storage_boundary_sqlite_smoke.py"], ensure_ascii=False),
                "risk_level": "medium",
                "approval_required": 0,
                "execution_steps_json": json.dumps(["create", "record", "verify"], ensure_ascii=False),
                "verification_plan": "Run storage boundary smoke.",
                "rollback_plan": "Revert storage-boundary helper changes.",
                "status": "submitted",
                "created_at": write_now,
                "updated_at": write_now,
            }
            before_plan, plan_outcome = server.repo_upsert_agent_plan(conn, dict(write_plan_row))
            require(before_plan is None and plan_outcome == "created", f"agent plan write helper create failed: {plan_outcome}")
            write_plan_row["verification_plan"] = "Run storage boundary smoke and plan evidence verification."
            write_plan_row["updated_at"] = server.now_iso()
            before_plan, plan_outcome = server.repo_upsert_agent_plan(conn, dict(write_plan_row))
            require(before_plan and plan_outcome == "updated", f"agent plan write helper update failed: {plan_outcome}")
            plan_row = conn.execute("SELECT * FROM agent_plans WHERE plan_id=?", (write_plan,)).fetchone()
            require(server.verify_agent_plan_row(plan_row)["pass"] is True, "agent plan write helper did not persist a verifiable plan")

            write_manifest_row = {
                "manifest_id": write_manifest,
                "workspace_id": workspace_a,
                "plan_id": write_plan,
                "task_id": write_task,
                "run_id": write_run,
                "agent_id": agent_a,
                "mismatch_policy": "block",
                "expected_steps_json": json.dumps(["create", "record", "verify"], ensure_ascii=False),
                "tool_call_ids_json": json.dumps([write_tool_call], ensure_ascii=False),
                "evaluation_ids_json": json.dumps([write_eval], ensure_ascii=False),
                "artifact_ids_json": json.dumps([write_artifact], ensure_ascii=False),
                "audit_ids_json": json.dumps([write_audit], ensure_ascii=False),
                "status": "submitted",
                "verification_json": "{}",
                "created_at": write_now,
                "updated_at": write_now,
            }
            before_manifest, manifest_outcome = server.repo_upsert_plan_evidence_manifest(conn, dict(write_manifest_row))
            require(before_manifest is None and manifest_outcome == "created", f"plan evidence write helper create failed: {manifest_outcome}")
            manifest_row = conn.execute("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", (write_manifest,)).fetchone()
            manifest_verification = server.verify_plan_evidence_manifest_row(conn, manifest_row)
            require(manifest_verification["status"] == "verified", f"plan evidence verification failed: {manifest_verification}")
            _before_manifest, after_manifest, manifest_update = server.repo_update_plan_evidence_manifest(conn, write_manifest, {
                "status": manifest_verification["status"],
                "verification_json": json.dumps(manifest_verification, ensure_ascii=False),
                "updated_at": server.now_iso(),
            })
            require(after_manifest and manifest_update == "updated" and after_manifest["status"] == "verified", f"plan evidence update helper failed: {manifest_update}")

            memory_id_a = memory_a["memory"]["memory_id"]
            memory_id_b = memory_b["memory"]["memory_id"]
            org_memory_id_a = org_memory_a["memory"]["memory_id"]
            memory_ids = ids(server.repo_list_workspace_memories(conn, workspace_a), "memory_id")
            require(memory_id_a in memory_ids and org_memory_id_a in memory_ids and write_memory in memory_ids, f"memory helper missed workspace A rows: {memory_ids}")
            require(memory_id_b not in memory_ids, f"memory helper leaked workspace B rows: {memory_ids}")
            require(server.repo_get_workspace_memory(conn, workspace_a, memory_id_a), "memory helper missed workspace A memory")
            require(not server.repo_get_workspace_memory(conn, workspace_a, memory_id_b), "memory helper exposed workspace B memory")

            approval_id_a = approval_a["approval"]["approval_id"]
            approval_id_b = approval_b["approval"]["approval_id"]
            approval_ids = ids(server.repo_list_workspace_approvals(conn, workspace_a), "approval_id")
            require(approval_id_a in approval_ids and approval_id_b not in approval_ids, f"approval helper leaked workspace rows: {approval_ids}")

            evaluation_id_a = evaluation_a["evaluation"]["evaluation_id"]
            evaluation_id_b = evaluation_b["evaluation"]["evaluation_id"]
            evaluation_ids = ids(server.repo_list_workspace_evaluations(conn, workspace_a), "evaluation_id")
            require(evaluation_id_a in evaluation_ids and evaluation_id_b not in evaluation_ids, f"evaluation helper leaked workspace rows: {evaluation_ids}")

            artifact_id_a = artifact_a["artifact"]["artifact_id"]
            artifact_id_b = artifact_b["artifact"]["artifact_id"]
            artifact_ids = ids(server.repo_list_workspace_artifacts(conn, workspace_a), "artifact_id")
            require(artifact_id_a in artifact_ids and write_artifact in artifact_ids and artifact_id_b not in artifact_ids, f"artifact helper leaked workspace rows: {artifact_ids}")
            gateway_artifact_ids = ids(server.repo_list_agent_gateway_artifacts(conn, workspace_a, agent_id=agent_a, bound_visibility=True, limit=20), "artifact_id")
            require(artifact_id_a in gateway_artifact_ids and artifact_id_b not in gateway_artifact_ids, f"gateway artifact helper leaked workspace rows: {gateway_artifact_ids}")
            gateway_approval_ids = ids(server.repo_list_agent_gateway_approvals(conn, workspace_a, agent_id=agent_a, bound_visibility=True, decisions=["pending"], limit=20), "approval_id")
            require(approval_id_a in gateway_approval_ids and approval_id_b not in gateway_approval_ids, f"gateway approval helper leaked workspace rows: {gateway_approval_ids}")
            gateway_memory_ids = ids(server.repo_list_agent_gateway_memories(conn, workspace_a, agent_id=agent_a, bound_visibility=True, statuses=["candidate"], limit=20), "memory_id")
            require(memory_id_a in gateway_memory_ids and memory_id_b not in gateway_memory_ids, f"gateway memory helper leaked workspace rows: {gateway_memory_ids}")

            audit_rows = server.repo_list_workspace_audit(conn, workspace_a)
            audit_text = json.dumps([dict(row) for row in audit_rows], ensure_ascii=False, sort_keys=True)
            require(task_a in audit_text or run_a in audit_text, "audit helper missed workspace A task/run evidence")
            require(write_audit in audit_text, "audit helper missed direct repo_insert_audit_log evidence")
            require(artifact_id_a in audit_text, "audit helper missed workspace A metadata evidence")
            require(task_b not in audit_text and run_b not in audit_text and artifact_id_b not in audit_text, "audit helper leaked workspace B evidence")

            workflow_job_ids = ids(server.repo_list_workspace_workflow_jobs(conn, workspace_a), "job_id")
            require(job_a in workflow_job_ids and job_b not in workflow_job_ids, f"workflow job helper leaked workspace rows: {workflow_job_ids}")
            require(server.repo_get_workspace_workflow_job(conn, workspace_a, job_a), "workflow job helper missed workspace A job")
            require(not server.repo_get_workspace_workflow_job(conn, workspace_a, job_b), "workflow job helper exposed workspace B job")
            stuck_ids = {row["job_id"] for row in server.repo_list_workspace_stuck_workflow_jobs(conn, workspace_a, threshold_sec=30, limit=20)}
            require(job_a in stuck_ids and job_b not in stuck_ids, f"stuck workflow helper leaked workspace rows: {stuck_ids}")
            wrong_workspace_payload, wrong_workspace_status = server.mark_workflow_job_failed(conn, job_b, {
                "workspace_id": workspace_a,
                "reason": "Cross-workspace mark failed should not mutate.",
            })
            require(wrong_workspace_status == 404, f"cross-workspace mark-failed should be 404: {wrong_workspace_payload}")
            marked_payload, marked_status = server.mark_workflow_job_failed(conn, job_a, {
                "workspace_id": workspace_a,
                "reason": "Storage boundary mark failed.",
            })
            require(marked_status == 200 and marked_payload.get("marked_failed") is True, f"workspace mark-failed failed: {marked_status} {marked_payload}")
            remaining_stuck_ids = {row["job_id"] for row in server.repo_list_workspace_stuck_workflow_jobs(conn, workspace_a, threshold_sec=30, limit=20)}
            require(job_a not in remaining_stuck_ids and job_b not in remaining_stuck_ids, f"marked/cross workflow job still leaked as stuck: {remaining_stuck_ids}")

            enrollment_ids = ids(server.repo_list_gateway_enrollments(conn, workspace_a), "token_id")
            require(token_id_a in enrollment_ids and token_id_b not in enrollment_ids, f"gateway enrollment helper leaked workspace rows: {enrollment_ids}")
            enrollment_rows = [dict(row) for row in server.repo_list_gateway_enrollments(conn, workspace_a)]
            require(all("token_hash" not in row for row in enrollment_rows), f"gateway enrollment helper exposed token_hash: {enrollment_rows}")
            session_ids = ids(server.repo_list_gateway_sessions(conn, workspace_a), "session_id")
            require(session_id_a in session_ids and session_id_b not in session_ids, f"gateway session helper leaked workspace rows: {session_ids}")
            session_rows = [dict(row) for row in server.repo_list_gateway_sessions(conn, workspace_a)]
            require(all("session_hash" not in row for row in session_rows), f"gateway session helper exposed session_hash: {session_rows}")

        print(json.dumps({
            "ok": True,
            "db_path": "isolated_tmp" if owned_db else os.environ.get("AGENTOPS_DB_PATH"),
            "helpers": [
                "repo_list_workspace_tasks",
                "repo_get_workspace_task",
                "repo_list_workspace_runs",
                "repo_get_workspace_run",
                "repo_list_workspace_memories",
                "repo_get_workspace_memory",
                "repo_list_workspace_approvals",
                "repo_list_workspace_evaluations",
                "repo_list_workspace_artifacts",
                "repo_list_workspace_audit",
                "repo_list_workspace_workflow_jobs",
                "repo_get_workspace_workflow_job",
                "repo_list_workspace_stuck_workflow_jobs",
                "repo_upsert_workflow_job",
                "repo_update_workflow_job",
                "repo_upsert_agent_plan",
                "repo_upsert_plan_evidence_manifest",
                "repo_update_plan_evidence_manifest",
                "repo_list_gateway_enrollments",
                "repo_list_gateway_sessions",
                "repo_pull_agent_gateway_tasks",
                "repo_list_agent_gateway_tasks",
                "repo_get_agent_gateway_task",
                "repo_list_agent_gateway_runs",
                "repo_get_agent_gateway_run",
                "repo_list_agent_gateway_artifacts",
                "repo_list_agent_gateway_approvals",
                "repo_list_agent_gateway_memories",
                "repo_upsert_task",
                "repo_upsert_run",
                "repo_upsert_tool_call",
                "repo_insert_runtime_event",
                "repo_insert_audit_log",
                "repo_upsert_approval",
                "repo_upsert_evaluation",
                "repo_upsert_artifact",
                "repo_upsert_memory_candidate",
            ],
            "workspace_a": workspace_a,
            "workspace_b": workspace_b,
            "run_a": run_a,
            "run_b": run_b,
            "workflow_job_a": job_a,
            "workflow_job_b": job_b,
            "write_task": write_task,
            "write_run": write_run,
            "write_tool_call": write_tool_call,
            "write_runtime_event": write_runtime_event,
            "write_audit": write_audit,
            "write_agent_plan": write_plan,
            "write_plan_evidence_manifest": write_manifest,
            "write_approval": write_approval,
            "write_evaluation": write_eval,
            "write_artifact": write_artifact,
            "write_memory": write_memory,
            "gateway_enrollment_a": token_id_a,
            "gateway_session_a": session_id_a,
            "token_omitted": True,
            "raw_prompt_omitted": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        if owned_db and db_path:
            try:
                os.unlink(db_path)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
