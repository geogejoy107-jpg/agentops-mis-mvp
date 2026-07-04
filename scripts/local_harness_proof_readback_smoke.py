#!/usr/bin/env python3
"""Verify local task harness proof API/CLI readback is read-only and scoped."""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from operator_runtime_doctor_smoke import CLI, ROOT, free_port, http_json, leaked_secret, load_json, require, wait_ready


LEDGER_TABLES = [
    "tasks",
    "runs",
    "tool_calls",
    "evaluations",
    "runtime_events",
    "audit_logs",
    "artifacts",
    "memories",
    "approvals",
    "plan_evidence_manifests",
]

ACCEPTANCE_DOC = ROOT / "docs" / "LOCAL_HARNESS_PROOF_READBACK_ACCEPTANCE.md"


def iso(hours_delta: float = 0) -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours_delta)).isoformat()


def ledger_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in LEDGER_TABLES}
    finally:
        conn.close()


def seed_harness_attempt(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    adapter: str,
    suffix: str,
    run_status: str = "completed",
    tool_status: str = "completed",
    eval_pass: bool = True,
    include_artifact: bool = True,
    include_memory: bool = True,
    manifest_status: str = "verified",
) -> dict:
    created_at = iso(-0.05)
    ended_at = created_at if run_status != "running" else None
    user_id = "usr_harness_proof"
    agent_id = f"agt_local_task_harness_{adapter}"
    task_id = f"tsk_harness_proof_{adapter}_{suffix}"
    run_id = f"run_harness_proof_{adapter}_{suffix}"
    plan_id = f"plan_harness_proof_{adapter}_{suffix}"
    tool_call_id = f"tc_harness_proof_{adapter}_{suffix}"
    evaluation_id = f"eval_harness_proof_{adapter}_{suffix}"
    artifact_id = f"art_harness_proof_{adapter}_{suffix}"
    audit_id = f"aud_harness_proof_{adapter}_{suffix}"
    memory_id = f"mem_harness_proof_{adapter}_{suffix}"
    manifest_id = f"pem_harness_proof_{adapter}_{suffix}"
    conn.execute(
        """INSERT OR IGNORE INTO users(user_id,name,email,role,created_at)
        VALUES(?,?,?,?,?)""",
        (user_id, "Harness Proof User", "harness-proof@example.local", "operator", created_at),
    )
    conn.execute(
        """INSERT OR IGNORE INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            agent_id,
            f"Local task harness {adapter}",
            "Worker",
            "Fixture worker for local harness proof readback.",
            adapter,
            "local",
            adapter,
            "idle",
            "standard",
            "[]",
            0.0,
            user_id,
            created_at,
            created_at,
        ),
    )
    conn.execute(
        """INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id,
            workspace_id,
            f"{adapter} local task harness proof",
            "Fixture local task harness proof task.",
            user_id,
            agent_id,
            "[]",
            "completed" if run_status == "completed" else run_status,
            "high",
            None,
            "local task harness proof must have run/tool/eval/runtime/audit/artifact/plan evidence.",
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
            "Fixture harness plan.",
            "[]",
            "[]",
            "[]",
            "[]",
            "low",
            0,
            '["execute harness proof"]',
            "Verify readback evidence.",
            "No-op rollback.",
            "approved",
            1,
            f"hash_{plan_id}",
            created_at,
            f"verify_{plan_id}",
            None,
            user_id,
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
            ended_at,
            1000,
            "Fixture local task harness input summary.",
            "Fixture local task harness output summary." if run_status == "completed" else "Fixture failed before completion.",
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
            f"local://{adapter}/harness-proof",
            "low",
            tool_status,
            "Fixture harness tool result.",
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
            "Fixture harness evaluation.",
            created_at,
        ),
    )
    conn.execute(
        """INSERT INTO runtime_events(runtime_event_id,runtime_connector_id,event_type,status,run_id,task_id,agent_id,model_name,latency_ms,prompt_hash,input_summary,output_summary,error_message,raw_payload_hash,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            f"rte_harness_proof_{adapter}_{suffix}",
            f"rtc_{adapter}_local" if adapter != "mock" else "rtc_agent_gateway_mock",
            "local_task_harness.fixture",
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
                "local_task_harness_result",
                "Fixture local task harness result",
                f"run://{run_id}",
                "Fixture harness artifact summary.",
                created_at,
            ),
        )
    if include_memory:
        conn.execute(
            """INSERT INTO memories(memory_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                memory_id,
                "project",
                "artifact_summary",
                "Fixture harness memory candidate.",
                "run_log",
                run_id,
                "proj_harness_proof",
                task_id,
                agent_id,
                0.8,
                "candidate",
                user_id,
                iso(24 * 30),
                None,
                '["fixture"]',
                created_at,
                created_at,
            ),
        )
    conn.execute(
        """INSERT INTO audit_logs(audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            audit_id,
            "system",
            "local-harness-proof-smoke",
            "local_harness_proof.fixture",
            "runs",
            run_id,
            None,
            f"hash_{run_id}",
            json.dumps({"run_id": run_id, "task_id": task_id, "token_omitted": True}, ensure_ascii=False),
            f"chain_{audit_id}",
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
            '["execute harness proof"]',
            json.dumps([tool_call_id], ensure_ascii=False),
            json.dumps([evaluation_id], ensure_ascii=False),
            json.dumps([artifact_id] if include_artifact else [], ensure_ascii=False),
            json.dumps([audit_id], ensure_ascii=False),
            f"hash_{plan_id}",
            f"verify_{manifest_id}",
            manifest_status,
            json.dumps({"ok": manifest_status == "verified"}, ensure_ascii=False),
            created_at,
            created_at,
        ),
    )
    return {"adapter": adapter, "task_id": task_id, "run_id": run_id, "artifact_id": artifact_id, "manifest_id": manifest_id}


def seed_fixture(db_path: Path, workspace_id: str) -> dict:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        seeded = {
            "mock": seed_harness_attempt(conn, workspace_id=workspace_id, adapter="mock", suffix="fresh"),
            "openclaw": seed_harness_attempt(conn, workspace_id=workspace_id, adapter="openclaw", suffix="fresh"),
            "hermes": seed_harness_attempt(
                conn,
                workspace_id=workspace_id,
                adapter="hermes",
                suffix="failed",
                run_status="failed",
                tool_status="failed",
                eval_pass=False,
                include_artifact=False,
                include_memory=False,
                manifest_status="blocked",
            ),
        }
        conn.commit()
        return seeded
    finally:
        conn.close()


def run_cli(base_url: str, env: dict[str, str], *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "operator", "local-harness-proof", *extra],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def validate_payload(payload: dict, failures: list[str]) -> None:
    require(payload.get("operation") == "local_harness_proof_readiness", f"operation mismatch: {payload}", failures)
    require(payload.get("status") == "ready", f"proof should be ready from seeded OpenClaw evidence: {payload}", failures)
    require(payload.get("ok") is True, f"proof ok should be true: {payload}", failures)
    require(payload.get("live_execution_performed") is False, f"readback executed runtime: {payload}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"safety read_only missing: {payload}", failures)
    require(safety.get("ledger_mutated") is False, f"safety ledger_mutated mismatch: {payload}", failures)
    require(safety.get("token_omitted") is True, f"safety token omission missing: {payload}", failures)
    summary = payload.get("summary") or {}
    require(int(summary.get("fresh_real_runtime_adapters") or 0) == 1, f"real runtime summary mismatch: {summary}", failures)
    require(int(summary.get("fresh_mock_fallback") or 0) == 1, f"mock fallback summary mismatch: {summary}", failures)
    adapters = payload.get("adapters") or {}
    mock = adapters.get("mock") or {}
    openclaw = adapters.get("openclaw") or {}
    hermes = adapters.get("hermes") or {}
    require(mock.get("status") == "fresh", f"mock should be fresh fallback: {mock}", failures)
    require(mock.get("evidence_class") == "mock_ci_fallback", f"mock evidence class mismatch: {mock}", failures)
    require(openclaw.get("status") == "fresh", f"OpenClaw should be fresh: {openclaw}", failures)
    require(openclaw.get("evidence_class") == "real_runtime_ledger_readback", f"OpenClaw evidence class mismatch: {openclaw}", failures)
    require(hermes.get("status") == "latest_failed", f"Hermes should expose latest failed: {hermes}", failures)
    latest = openclaw.get("latest_passing") or {}
    evidence = latest.get("evidence") or {}
    for key in ["completed_adapter_tool_calls", "passing_evaluations", "runtime_events", "audit_logs", "artifacts", "verified_plan_evidence_manifests"]:
        require(int(evidence.get(key) or 0) >= 1, f"OpenClaw missing evidence {key}: {evidence}", failures)
    check_ids = {check.get("id") for check in latest.get("checks") or []}
    for check_id in ["run_completed", "adapter_tool_evidence", "evaluation_pass", "runtime_event", "audit_log", "artifact", "plan_evidence"]:
        require(check_id in check_ids, f"OpenClaw missing check {check_id}: {latest}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    workspace_id = "harness-proof-smoke"
    acceptance = ACCEPTANCE_DOC.read_text(encoding="utf-8") if ACCEPTANCE_DOC.exists() else ""
    require(ACCEPTANCE_DOC.exists(), "missing local harness proof acceptance doc", failures)
    for marker in [
        "agentops operator local-harness-proof",
        "GET /api/operator/local-harness-proof",
        "mock_ci_fallback",
        "real_runtime_ledger_readback",
        "python3 scripts/local_harness_proof_readback_smoke.py",
        "live_execution_performed: false",
    ]:
        require(marker in acceptance, f"acceptance doc missing marker: {marker}", failures)
    with tempfile.TemporaryDirectory(prefix="agentops-local-harness-proof-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_BASE_URL"] = base_url
        env["AGENTOPS_WORKSPACE_ID"] = workspace_id
        env.pop("AGENTOPS_API_KEY", None)
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            seed_fixture(db_path, workspace_id)
            before = ledger_counts(db_path)
            status, api_payload = http_json(
                base_url,
                "/api/operator/local-harness-proof?freshness_hours=72&limit=5",
                headers={"X-AgentOps-Workspace-Id": workspace_id},
            )
            outputs.append(json.dumps(api_payload, ensure_ascii=False))
            require(status == 200, f"API status should be 200: {status} {api_payload}", failures)
            validate_payload(api_payload, failures)
            require(ledger_counts(db_path) == before, "API local-harness-proof mutated ledger", failures)

            cli_proc = run_cli(base_url, env, "--freshness-hours", "72", "--limit", "5")
            outputs.extend([cli_proc.stdout, cli_proc.stderr])
            cli_payload = load_json(cli_proc.stdout)
            require(cli_proc.returncode == 0, f"CLI should exit 0: {cli_proc.stdout} {cli_proc.stderr}", failures)
            validate_payload(cli_payload, failures)
            require(ledger_counts(db_path) == before, "CLI local-harness-proof mutated ledger", failures)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    require(not leaked_secret("\n".join(outputs)), "local harness proof output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "local_harness_proof_readback_smoke",
        "failures": failures,
        "workspace_id": workspace_id,
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
