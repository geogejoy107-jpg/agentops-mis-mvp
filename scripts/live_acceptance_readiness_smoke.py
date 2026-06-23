#!/usr/bin/env python3
"""Verify live acceptance readiness classification on isolated ledger fixtures."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def iso(hours_delta: float = 0) -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours_delta)).isoformat()


def seed_identity(conn, workspace_id: str, adapter: str, suffix: str) -> str:
    conn.execute(
        """INSERT OR IGNORE INTO users(user_id,name,email,role,created_at)
        VALUES(?,?,?,?,?)""",
        ("usr_acceptance", "Acceptance Reviewer", "acceptance@example.local", "reviewer", iso()),
    )
    agent_id = f"agt_customer_worker_{adapter}_{suffix}"
    conn.execute(
        """INSERT OR IGNORE INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            agent_id,
            f"{adapter} acceptance worker",
            "Worker",
            "Fixture worker for live acceptance read-model smoke.",
            adapter,
            "local",
            adapter,
            "idle",
            "standard",
            "[]",
            0.0,
            "usr_acceptance",
            iso(),
            iso(),
        ),
    )
    return agent_id


def add_attempt(
    conn,
    *,
    workspace_id: str,
    adapter: str,
    suffix: str,
    hours_delta: float,
    run_status: str,
    tool_status: str,
    eval_pass: bool,
    manifest_status: str,
    include_artifact: bool = True,
) -> dict:
    agent_id = seed_identity(conn, workspace_id, adapter, suffix)
    created_at = iso(hours_delta)
    task_id = f"tsk_{workspace_id}_{adapter}_{suffix}"
    run_id = f"run_{workspace_id}_{adapter}_{suffix}"
    plan_id = f"plan_{workspace_id}_{adapter}_{suffix}"
    manifest_id = f"pem_{workspace_id}_{adapter}_{suffix}"
    tool_call_id = f"tc_{workspace_id}_{adapter}_{suffix}"
    evaluation_id = f"eval_{workspace_id}_{adapter}_{suffix}"
    artifact_id = f"art_{workspace_id}_{adapter}_{suffix}"
    audit_id = f"aud_{workspace_id}_{adapter}_{suffix}"
    memory_id = f"mem_{workspace_id}_{adapter}_{suffix}"
    approval_id = f"ap_{workspace_id}_{adapter}_{suffix}"
    conn.execute(
        """INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id,
            workspace_id,
            f"{adapter} fixture {suffix}",
            "Fixture customer worker task.",
            "usr_acceptance",
            agent_id,
            "[]",
            "waiting_approval" if run_status == "completed" else run_status,
            "high",
            None,
            "Ledger evidence must classify correctly.",
            "low",
            0.0,
            created_at,
            created_at,
        ),
    )
    conn.execute(
        """INSERT INTO agent_plans(plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,referenced_specs_json,referenced_memories_json,referenced_bases_json,proposed_files_to_change_json,risk_level,approval_required,execution_steps_json,verification_plan,rollback_plan,status,plan_version,plan_hash,verified_at,verification_result_hash,approval_id,approved_by_user_id,approved_at,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            plan_id,
            workspace_id,
            task_id,
            None,
            agent_id,
            "Fixture plan.",
            "[]",
            "[]",
            "[]",
            "[]",
            "low",
            0,
            '["execute"]',
            "Verify evidence.",
            "No-op rollback.",
            "approved",
            1,
            f"hash_{plan_id}",
            created_at,
            f"verify_{plan_id}",
            None,
            "usr_acceptance",
            created_at,
            created_at,
            created_at,
        ),
    )
    conn.execute(
        """INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,agent_plan_id,plan_hash,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,
            workspace_id,
            task_id,
            agent_id,
            adapter,
            run_status,
            created_at,
            created_at if run_status != "running" else None,
            1000,
            "Fixture input summary.",
            "Fixture output summary.",
            "local",
            adapter,
            0,
            0,
            0,
            0.0,
            "FixtureFailure" if run_status in {"failed", "blocked"} or tool_status == "failed" else None,
            "Fixture failure." if run_status in {"failed", "blocked"} or tool_status == "failed" else None,
            None,
            None,
            f"worker:{adapter}:{task_id}",
            0,
            plan_id,
            f"hash_{plan_id}",
            created_at,
        ),
    )
    conn.execute(
        """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            tool_call_id,
            run_id,
            agent_id,
            f"agent_worker.{adapter}",
            "v1",
            "custom",
            json.dumps({"adapter": adapter, "raw_prompt_omitted": True, "token_omitted": True}, ensure_ascii=False),
            f"local://{adapter}",
            "low",
            tool_status,
            "Fixture tool result.",
            None,
            created_at,
            created_at if tool_status == "completed" else None,
            created_at,
        ),
    )
    conn.execute(
        """INSERT INTO evaluations(evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            evaluation_id,
            task_id,
            run_id,
            agent_id,
            "rule",
            1.0 if eval_pass else 0.0,
            "pass" if eval_pass else "fail",
            "{}",
            "Fixture evaluation.",
            created_at,
        ),
    )
    conn.execute(
        """INSERT INTO runtime_events(runtime_event_id,runtime_connector_id,event_type,status,run_id,task_id,agent_id,model_name,latency_ms,prompt_hash,input_summary,output_summary,error_message,raw_payload_hash,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"rte_{workspace_id}_{adapter}_{suffix}",
            None,
            "agent_worker.fixture",
            "completed" if eval_pass else "failed",
            run_id,
            task_id,
            agent_id,
            adapter,
            1000,
            "prompt_hash",
            "Fixture input.",
            "Fixture output.",
            None if eval_pass else "Fixture failure.",
            "payload_hash",
            created_at,
        ),
    )
    if include_artifact:
        conn.execute(
            """INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,uri,summary,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (
                artifact_id,
                task_id,
                run_id,
                "customer_worker_result",
                "Fixture customer delivery",
                f"run://{run_id}",
                "Fixture summary.",
                created_at,
            ),
        )
    conn.execute(
        """INSERT INTO memories(memory_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            memory_id,
            "project",
            "artifact_summary",
            "Fixture memory.",
            "run_log",
            run_id,
            "proj_fixture",
            task_id,
            agent_id,
            0.8,
            "candidate",
            "usr_acceptance",
            iso(24 * 30),
            None,
            '["fixture"]',
            created_at,
            created_at,
        ),
    )
    conn.execute(
        """INSERT INTO approvals(approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,decision,reason,expires_at,created_at,decided_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            approval_id,
            task_id,
            run_id,
            None,
            agent_id,
            "usr_acceptance",
            "pending",
            "Fixture delivery approval.",
            iso(48),
            created_at,
            None,
        ),
    )
    conn.execute(
        """INSERT INTO audit_logs(audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            audit_id,
            "system",
            "fixture",
            "fixture.live_acceptance",
            "runs",
            run_id,
            None,
            "after_hash",
            json.dumps({"run_id": run_id, "adapter": adapter}, ensure_ascii=False),
            "chain_hash",
            created_at,
        ),
    )
    conn.execute(
        """INSERT INTO plan_evidence_manifests(manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,expected_steps_json,tool_call_ids_json,evaluation_ids_json,artifact_ids_json,audit_ids_json,plan_hash,verification_result_hash,status,verification_json,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            manifest_id,
            workspace_id,
            plan_id,
            task_id,
            run_id,
            agent_id,
            "block",
            '["execute"]',
            json.dumps([tool_call_id], ensure_ascii=False),
            json.dumps([evaluation_id], ensure_ascii=False),
            json.dumps([artifact_id] if include_artifact else [], ensure_ascii=False),
            json.dumps([audit_id], ensure_ascii=False),
            f"hash_{plan_id}",
            f"verify_{manifest_id}",
            manifest_status,
            json.dumps({"pass": manifest_status == "verified"}, ensure_ascii=False),
            created_at,
            created_at,
        ),
    )
    return {"run_id": run_id, "artifact_id": artifact_id if include_artifact else None, "manifest_id": manifest_id}


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-live-acceptance-readiness-") as tmp:
        os.environ["AGENTOPS_DB_PATH"] = str(Path(tmp) / "agentops_mis.db")
        os.environ["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        import server  # noqa: PLC0415 - DB path must be set before import.

        server.init_schema()
        with server.db() as conn:
            missing = server.live_acceptance_readiness(conn, "ws_missing")
            require(missing.get("summary", {}).get("missing") == 2, f"missing classification failed: {missing}", failures)

            add_attempt(conn, workspace_id="ws_stale", adapter="openclaw", suffix="old_pass", hours_delta=-100, run_status="completed", tool_status="completed", eval_pass=True, manifest_status="verified")
            stale = server.live_acceptance_readiness(conn, "ws_stale", freshness_hours=72)
            require((stale.get("adapters") or {}).get("openclaw", {}).get("status") == "stale", f"stale classification failed: {stale}", failures)

            add_attempt(conn, workspace_id="ws_fresh", adapter="openclaw", suffix="fresh_pass", hours_delta=-1, run_status="completed", tool_status="completed", eval_pass=True, manifest_status="verified")
            add_attempt(conn, workspace_id="ws_fresh", adapter="hermes", suffix="fresh_pass", hours_delta=-1, run_status="completed", tool_status="completed", eval_pass=True, manifest_status="verified")
            fresh = server.live_acceptance_readiness(conn, "ws_fresh", freshness_hours=72)
            require(fresh.get("status") == "ready", f"fresh ready classification failed: {fresh}", failures)
            require((fresh.get("summary") or {}).get("fresh") == 2, f"fresh summary failed: {fresh}", failures)
            require((fresh.get("adapters") or {}).get("openclaw", {}).get("latest_passing", {}).get("artifact_id"), f"fresh artifact id missing: {fresh}", failures)
            require((fresh.get("adapters") or {}).get("hermes", {}).get("latest_passing", {}).get("plan_evidence_manifest_id"), f"fresh manifest id missing: {fresh}", failures)

            add_attempt(conn, workspace_id="ws_latest_failed", adapter="openclaw", suffix="fresh_pass", hours_delta=-1, run_status="completed", tool_status="completed", eval_pass=True, manifest_status="verified")
            add_attempt(conn, workspace_id="ws_latest_failed", adapter="hermes", suffix="old_pass", hours_delta=-10, run_status="completed", tool_status="completed", eval_pass=True, manifest_status="verified")
            add_attempt(conn, workspace_id="ws_latest_failed", adapter="hermes", suffix="new_fail", hours_delta=-0.5, run_status="failed", tool_status="failed", eval_pass=False, manifest_status="blocked")
            failed = server.live_acceptance_readiness(conn, "ws_latest_failed", freshness_hours=72)
            require((failed.get("adapters") or {}).get("hermes", {}).get("status") == "latest_failed", f"latest_failed classification failed: {failed}", failures)

            add_attempt(conn, workspace_id="ws_incomplete", adapter="hermes", suffix="running", hours_delta=-0.2, run_status="running", tool_status="completed", eval_pass=True, manifest_status="verified")
            incomplete = server.live_acceptance_readiness(conn, "ws_incomplete", freshness_hours=72)
            require((incomplete.get("adapters") or {}).get("hermes", {}).get("status") == "latest_incomplete", f"latest_incomplete classification failed: {incomplete}", failures)

            serialized = json.dumps([missing, stale, fresh, failed, incomplete], ensure_ascii=False)
            require("token_omitted" in serialized, "token omission proof missing", failures)
            require("你是 AgentOps MIS 的本地 AI worker" not in serialized, "raw prompt material should not appear", failures)

    print(json.dumps({
        "ok": not failures,
        "operation": "live_acceptance_readiness_smoke",
        "failures": failures,
        "classifications": ["missing", "stale", "fresh", "latest_failed", "latest_incomplete"],
        "safety": {
            "isolated_db": True,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
