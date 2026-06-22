#!/usr/bin/env python3
"""Verify live customer-worker writes use prepared-action exact resume."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    markers = ["AGENTOPS_API_KEY", "Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"]
    return any(marker in text for marker in markers)


def approve(conn, approval_id: str) -> tuple[dict, int]:
    before, after, outcome = server.repo_update_approval_decision(conn, approval_id, "approved")
    if outcome == "missing" or not after:
        return {"error": "not found"}, 404
    prepared_action = conn.execute(
        "SELECT * FROM prepared_actions WHERE approval_id=? ORDER BY created_at DESC LIMIT 1",
        (approval_id,),
    ).fetchone()
    if prepared_action:
        server.repo_update_prepared_action_status(conn, prepared_action["prepared_action_id"], "approved")
        conn.execute("UPDATE runs SET approval_required=0 WHERE run_id=?", (prepared_action["run_id"],))
        server.audit(
            conn,
            "user",
            "usr_founder",
            "prepared_action.approved",
            "prepared_actions",
            prepared_action["prepared_action_id"],
            dict(prepared_action),
            {"status": "approved"},
            {"approval_id": approval_id},
        )
    server.audit(conn, "user", "usr_founder", "approval.approved", "approvals", approval_id, dict(before) if before else None, dict(after), {})
    conn.commit()
    return dict(after), 200


def fake_worker_result(conn, body: dict, calls: list[dict]) -> dict:
    calls.append({"adapter": body.get("adapter"), "async_job": bool(body.get("async_job"))})
    adapter = body.get("adapter") or "openclaw"
    agent_id = body.get("agent_id") or body.get("worker_agent_id") or f"agt_fake_{adapter}_customer_worker"
    task_id = body.get("task_id") or server.stable_id("tsk_fake_customer_worker", adapter, str(len(calls)))
    run_id = server.stable_id("run_fake_customer_worker", task_id, str(len(calls)))
    now = server.now_iso()
    server.ensure_gateway_agent(conn, agent_id, name=f"Fake {adapter} Customer Worker", role="Customer Task Worker", runtime_type=adapter)
    server.repo_upsert_task(conn, {
        "task_id": task_id,
        "workspace_id": "local-demo",
        "title": f"Fake customer worker {adapter}",
        "description": "Fake customer worker task for prepared-action smoke.",
        "requester_id": "usr_customer_demo",
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": "[]",
        "status": "completed",
        "priority": "high",
        "due_date": None,
        "acceptance_criteria": "Fake worker evidence is complete.",
        "risk_level": "medium",
        "budget_limit_usd": 1.0,
        "created_at": now,
        "updated_at": now,
    })
    row = {
        "run_id": run_id,
        "workspace_id": "local-demo",
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": adapter,
        "status": "completed",
        "started_at": now,
        "ended_at": now,
        "duration_ms": 123,
        "input_summary": "Fake customer worker prepared-action smoke.",
        "output_summary": "Fake customer worker completed.",
        "model_provider": adapter,
        "model_name": f"{adapter}-fake",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.0,
        "error_type": None,
        "error_message": None,
        "trace_id": None,
        "parent_run_id": None,
        "delegation_id": f"customer-worker:{adapter}",
        "approval_required": 0,
        "created_at": now,
    }
    server.repo_upsert_run(conn, row)
    server.repo_upsert_tool_call(conn, {
        "tool_call_id": server.stable_id("tc_fake_customer_worker", run_id),
        "run_id": run_id,
        "agent_id": agent_id,
        "tool_name": "fake.customer_worker",
        "tool_version": "v1",
        "tool_category": "custom",
        "normalized_args_json": json.dumps({"adapter": adapter, "raw_request_omitted": True}, sort_keys=True),
        "target_resource": "fake://customer-worker",
        "risk_level": "low",
        "status": "completed",
        "result_summary": "Fake worker completed.",
        "side_effect_id": "fake-worker-side-effect",
        "started_at": now,
        "ended_at": now,
        "created_at": now,
    })
    server.repo_upsert_evaluation(conn, server.quality_gate_for_run(row))
    server.runtime_event(conn, "rtc_agent_gateway_local", "fake_customer_worker.completed", "completed", run_id=run_id, task_id=task_id, agent_id=agent_id, output_summary="Fake worker completed.")
    server.audit(conn, "system", "fake-worker", "fake.customer_worker.completed", "runs", run_id, None, {"status": "completed"}, {"raw_output_omitted": True})
    conn.commit()
    return {
        "provider": "agentops-worker",
        "dry_run": False,
        "ok": True,
        "adapter": adapter,
        "agent_id": agent_id,
        "task_id": task_id,
        "duration_ms": 123,
        "worker_result": {
            "ok": True,
            "results": [{
                "processed": True,
                "task_id": task_id,
                "run_id": run_id,
                "output_summary": "Fake customer worker completed.",
            }],
        },
        "error": None,
    }


def exercise_sync(conn, calls: list[dict], failures: list[str]) -> dict:
    path_body = {
        "adapter": "openclaw",
        "confirm_run": True,
        "title": "Prepared customer worker sync smoke",
        "description": "This live worker request must prepare before executing.",
        "acceptance_criteria": "Resume exactly once after approval.",
        "worker_agent_id": "agt_prepared_customer_worker_sync",
        "priority": "high",
        "risk_level": "medium",
    }
    prepare, prepare_status = server.run_customer_worker_task_workflow(conn, dict(path_body))
    require(prepare_status == 202, f"sync prepare should be 202: {prepare_status} {prepare}", failures)
    require(prepare.get("provider_call_performed") is False, f"sync prepare called provider: {prepare}", failures)
    require(calls == [], f"sync provider called before approval: {calls}", failures)
    premature, premature_status = server.run_customer_worker_task_workflow(conn, {**path_body, "prepared_action_id": prepare.get("prepared_action_id"), "request_hash": prepare.get("request_hash")})
    require(premature_status == 428 and premature.get("error") == "approval_required", f"sync premature should require approval: {premature_status} {premature}", failures)
    require(calls == [], "sync provider called during premature resume", failures)
    approved, approved_status = approve(conn, prepare["approval_id"])
    require(approved_status == 200 and approved.get("decision") == "approved", f"sync approval failed: {approved_status} {approved}", failures)
    mismatch, mismatch_status = server.run_customer_worker_task_workflow(conn, {**path_body, "title": "Changed title", "prepared_action_id": prepare.get("prepared_action_id"), "request_hash": prepare.get("request_hash")})
    require(mismatch_status == 409 and mismatch.get("error") == "prepared_action_request_hash_mismatch", f"sync mismatch should block: {mismatch_status} {mismatch}", failures)
    require(calls == [], "sync provider called during mismatch", failures)
    resumed, resumed_status = server.run_customer_worker_task_workflow(conn, {**path_body, "prepared_action_id": prepare.get("prepared_action_id"), "request_hash": prepare.get("request_hash")})
    require(resumed_status == 201 and resumed.get("ok") is True, f"sync resume failed: {resumed_status} {resumed}", failures)
    require(resumed.get("prepared_action_status") == "consumed", f"sync action not consumed: {resumed}", failures)
    require(len(calls) == 1, f"sync provider should be called once: {calls}", failures)
    replay, replay_status = server.run_customer_worker_task_workflow(conn, {**path_body, "prepared_action_id": prepare.get("prepared_action_id"), "request_hash": prepare.get("request_hash")})
    require(replay_status == 409 and replay.get("error") == "prepared_action_already_consumed", f"sync replay should block: {replay_status} {replay}", failures)
    require(len(calls) == 1, "sync provider called during replay", failures)
    return resumed


def exercise_async(conn, calls: list[dict], failures: list[str]) -> dict:
    body = {
        "adapter": "hermes",
        "confirm_run": True,
        "title": "Prepared customer worker async smoke",
        "description": "This async live worker request must prepare before queueing.",
        "acceptance_criteria": "Queue exactly once after approval.",
        "worker_agent_id": "agt_prepared_customer_worker_async",
        "priority": "high",
        "risk_level": "medium",
    }
    prepare, prepare_status = server.submit_customer_worker_task_job(conn, dict(body))
    require(prepare_status == 202 and prepare.get("requires_approval") is True, f"async prepare should be 202: {prepare_status} {prepare}", failures)
    require(prepare.get("provider_call_performed") is False, f"async prepare called provider: {prepare}", failures)
    require(len(calls) == 1, f"async prepare should not add provider calls: {calls}", failures)
    premature, premature_status = server.submit_customer_worker_task_job(conn, {**body, "prepared_action_id": prepare.get("prepared_action_id"), "request_hash": prepare.get("request_hash")})
    require(premature_status == 428 and premature.get("error") == "approval_required", f"async premature should require approval: {premature_status} {premature}", failures)
    approved, approved_status = approve(conn, prepare["approval_id"])
    require(approved_status == 200 and approved.get("decision") == "approved", f"async approval failed: {approved_status} {approved}", failures)
    resumed, resumed_status = server.submit_customer_worker_task_job(conn, {**body, "prepared_action_id": prepare.get("prepared_action_id"), "request_hash": prepare.get("request_hash")})
    require(resumed_status == 202 and resumed.get("ok") is True, f"async resume should queue once: {resumed_status} {resumed}", failures)
    require(resumed.get("prepared_action_status") == "consumed", f"async action not consumed: {resumed}", failures)
    require(len(calls) == 1, f"async resume should queue without synchronous worker call: {calls}", failures)
    replay, replay_status = server.submit_customer_worker_task_job(conn, {**body, "prepared_action_id": prepare.get("prepared_action_id"), "request_hash": prepare.get("request_hash")})
    require(replay_status == 409 and replay.get("error") == "prepared_action_already_consumed", f"async replay should block: {replay_status} {replay}", failures)
    return resumed


def main() -> int:
    failures: list[str] = []
    calls: list[dict] = []
    original_db_path = server.DB_PATH
    original_dispatch = server.dispatch_local_worker_once
    original_readiness = server.worker_adapter_readiness
    original_thread = server.threading.Thread
    with tempfile.TemporaryDirectory(prefix="agentops-customer-worker-prepared-action-") as tmp:
        server.DB_PATH = Path(tmp) / "agentops.sqlite"

        class ImmediateThread:
            def __init__(self, target=None, args=(), kwargs=None, daemon=None):
                self.target = target
                self.args = args
                self.kwargs = kwargs or {}
                self.daemon = daemon

            def start(self):
                return None

        try:
            server.init_schema()
            server.worker_adapter_readiness = lambda conn: {
                "status": "ready",
                "adapters": {
                    "openclaw": {"readiness": "ready", "recommended_action": "ok"},
                    "hermes": {"readiness": "ready", "recommended_action": "ok"},
                },
            }
            server.dispatch_local_worker_once = lambda conn, body: fake_worker_result(conn, body, calls)
            server.threading.Thread = ImmediateThread
            with server.db() as conn:
                server.refresh_runtime_connectors(conn)
                conn.execute("UPDATE runtime_connectors SET trust_status='trusted', trust_note=NULL WHERE provider IN ('openclaw','hermes')")
                sync_result = exercise_sync(conn, calls, failures)
                async_result = exercise_async(conn, calls, failures)
                prepared_count = conn.execute("SELECT COUNT(*) c FROM prepared_actions WHERE provider='agentops-worker'").fetchone()["c"]
                consumed_count = conn.execute("SELECT COUNT(*) c FROM prepared_actions WHERE provider='agentops-worker' AND status='consumed'").fetchone()["c"]
                require(prepared_count == 2 and consumed_count == 2, f"prepared actions not consumed: prepared={prepared_count} consumed={consumed_count}", failures)
            serialized = json.dumps({"sync": sync_result, "async": async_result}, ensure_ascii=False)
            require(not leaked_secret(serialized), "prepared customer worker payload leaked token-like material", failures)
            print(json.dumps({
                "ok": not failures,
                "failures": failures,
                "provider_call_count": len(calls),
                "sync_prepared_action": sync_result.get("prepared_action_id"),
                "async_prepared_action": async_result.get("prepared_action_id"),
                "sync_run_id": sync_result.get("run_id"),
                "async_job_id": async_result.get("job_id"),
                "raw_request_omitted": True,
                "raw_result_omitted": True,
                "token_omitted": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not failures else 1
        finally:
            server.DB_PATH = original_db_path
            server.dispatch_local_worker_once = original_dispatch
            server.worker_adapter_readiness = original_readiness
            server.threading.Thread = original_thread


if __name__ == "__main__":
    raise SystemExit(main())
