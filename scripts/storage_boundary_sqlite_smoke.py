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
    job_a = "wfjob_storage_a"
    job_b = "wfjob_storage_b"

    try:
        server.init_schema()
        with server.db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
                ("usr_founder", "Founder", "founder@example.local", "founder", server.now_iso()),
            )
            server.ensure_gateway_agent(conn, agent_a, runtime_type="mock")
            server.ensure_gateway_agent(conn, agent_b, runtime_type="mock")
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
                conn.execute(
                    """INSERT INTO workflow_jobs(job_id,workspace_id,workflow_type,status,template_id,adapter,confirm_run,title,input_summary,request_hash,result_json,result_task_id,result_run_id,result_artifact_id,error_message,created_at,started_at,completed_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        job_id,
                        workspace_id,
                        "customer_worker_task",
                        "queued",
                        None,
                        "mock",
                        0,
                        f"Storage boundary workflow job {workspace_id}",
                        "Synthetic workflow job for storage-boundary smoke. Raw prompt omitted.",
                        f"hash_{job_id}",
                        "{}",
                        task_id,
                        run_id,
                        artifact_id,
                        None,
                        old,
                        None,
                        None,
                        old,
                    ),
                )
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

            memory_id_a = memory_a["memory"]["memory_id"]
            memory_id_b = memory_b["memory"]["memory_id"]
            org_memory_id_a = org_memory_a["memory"]["memory_id"]
            memory_ids = ids(server.repo_list_workspace_memories(conn, workspace_a), "memory_id")
            require(memory_id_a in memory_ids and org_memory_id_a in memory_ids, f"memory helper missed workspace A rows: {memory_ids}")
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
            require(artifact_id_a in artifact_ids and artifact_id_b not in artifact_ids, f"artifact helper leaked workspace rows: {artifact_ids}")

            audit_rows = server.repo_list_workspace_audit(conn, workspace_a)
            audit_text = json.dumps([dict(row) for row in audit_rows], ensure_ascii=False, sort_keys=True)
            require(task_a in audit_text or run_a in audit_text, "audit helper missed workspace A task/run evidence")
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
            ],
            "workspace_a": workspace_a,
            "workspace_b": workspace_b,
            "run_a": run_a,
            "run_b": run_b,
            "workflow_job_a": job_a,
            "workflow_job_b": job_b,
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
