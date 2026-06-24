#!/usr/bin/env python3
"""Run the first container-backed Postgres parity smoke for Gate 3.

The smoke intentionally avoids adding a Python Postgres driver. It uses Docker
and the `psql` client inside the official Postgres image to prove that the
Postgres DDL generated from `server.SCHEMA_SQL` can create a real database and
preserve representative workspace isolation for the storage-boundary contract.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402


DEFAULT_IMAGE = os.environ.get("AGENTOPS_POSTGRES_IMAGE", "postgres:16-alpine")


def run(args: list[str], *, timeout: int = 60, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def sha256_text(value: str) -> str:
    return contract.sha256_text(value)


def unavailable(message: str, *, skip: bool) -> int:
    payload = {
        "ok": bool(skip),
        "skipped": bool(skip),
        "contract": "postgres_container_parity_v1",
        "reason": message,
        "next_action": "Start Docker or provide a reachable Postgres parity runner, then rerun without --skip-if-unavailable.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if skip else 1


def docker_available(skip: bool) -> int | None:
    try:
        docker = run(["docker", "info", "--format", "{{json .ServerVersion}}"], timeout=15)
    except subprocess.TimeoutExpired as exc:
        return unavailable(f"Docker daemon unavailable: docker info timed out after {exc.timeout} seconds", skip=skip)
    if docker.returncode != 0:
        detail = (docker.stderr or docker.stdout or "docker info failed").strip()
        return unavailable(f"Docker daemon unavailable: {detail}", skip=skip)
    return None


def ensure_image(image: str, skip: bool) -> int | None:
    inspect = run(["docker", "image", "inspect", image], timeout=20)
    if inspect.returncode == 0:
        return None
    pull = run(["docker", "pull", image], timeout=240)
    if pull.returncode != 0:
        detail = (pull.stderr or pull.stdout or f"docker pull {image} failed").strip()
        return unavailable(f"Postgres image unavailable: {detail}", skip=skip)
    return None


def postgres_fixture_sql() -> str:
    now = "2026-06-22T00:00:00+00:00"
    return f"""
BEGIN;

INSERT INTO users(user_id, name, email, role, created_at)
VALUES ('usr_pg_founder', 'Postgres Founder', 'founder+pg@example.local', 'founder', '{now}');

INSERT INTO agents(agent_id, name, role, description, runtime_type, model_provider, model_name, status, permission_level, allowed_tools, budget_limit_usd, owner_user_id, created_at, updated_at)
VALUES
('agt_pg_a', 'Postgres Agent A', 'researcher', 'Container parity agent A', 'mock', 'mock', 'mock-model', 'idle', 'standard', '[]', 0, 'usr_pg_founder', '{now}', '{now}'),
('agt_pg_b', 'Postgres Agent B', 'researcher', 'Container parity agent B', 'mock', 'mock', 'mock-model', 'idle', 'standard', '[]', 0, 'usr_pg_founder', '{now}', '{now}');

INSERT INTO tasks(task_id, workspace_id, title, description, requester_id, owner_agent_id, collaborator_agent_ids, status, priority, due_date, acceptance_criteria, risk_level, budget_limit_usd, created_at, updated_at)
VALUES
('tsk_pg_a', 'ws_pg_a', 'Postgres workspace A task', 'Container smoke task A', 'usr_pg_founder', 'agt_pg_a', '[]', 'planned', 'medium', NULL, 'Prove workspace A remains isolated.', 'low', 0, '{now}', '{now}'),
('tsk_pg_b', 'ws_pg_b', 'Postgres workspace B task', 'Container smoke task B', 'usr_pg_founder', 'agt_pg_b', '[]', 'planned', 'medium', NULL, 'Prove workspace B remains isolated.', 'low', 0, '{now}', '{now}');

INSERT INTO runs(run_id, workspace_id, task_id, agent_id, runtime_type, status, started_at, ended_at, duration_ms, input_summary, output_summary, model_provider, model_name, input_tokens, output_tokens, reasoning_tokens, cost_usd, error_type, error_message, trace_id, parent_run_id, delegation_id, approval_required, created_at)
VALUES
('run_pg_a', 'ws_pg_a', 'tsk_pg_a', 'agt_pg_a', 'mock', 'completed', '{now}', '{now}', 1, 'Postgres parity input A', 'Postgres parity output A', 'mock', 'mock-model', 1, 1, 0, 0, NULL, NULL, 'trace_pg_a', NULL, NULL, 0, '{now}'),
('run_pg_b', 'ws_pg_b', 'tsk_pg_b', 'agt_pg_b', 'mock', 'completed', '{now}', '{now}', 1, 'Postgres parity input B', 'Postgres parity output B', 'mock', 'mock-model', 1, 1, 0, 0, NULL, NULL, 'trace_pg_b', NULL, NULL, 0, '{now}');

INSERT INTO tool_calls(tool_call_id, run_id, agent_id, tool_name, tool_version, tool_category, normalized_args_json, target_resource, risk_level, status, result_summary, side_effect_id, started_at, ended_at, created_at)
VALUES
('tc_pg_a', 'run_pg_a', 'agt_pg_a', 'postgres_parity_probe', 'v1', 'database', '{{}}', 'postgres://local/container', 'high', 'waiting_approval', 'Prepared action awaits approval.', NULL, '{now}', NULL, '{now}'),
('tc_pg_b', 'run_pg_b', 'agt_pg_b', 'postgres_parity_probe', 'v1', 'database', '{{}}', 'postgres://local/container', 'low', 'completed', 'Workspace B completed.', NULL, '{now}', '{now}', '{now}');

INSERT INTO approvals(approval_id, task_id, run_id, tool_call_id, requested_by_agent_id, approver_user_id, decision, reason, expires_at, created_at, decided_at)
VALUES
('ap_pg_a', 'tsk_pg_a', 'run_pg_a', 'tc_pg_a', 'agt_pg_a', NULL, 'pending', 'Container parity prepared action approval.', NULL, '{now}', NULL);

INSERT INTO prepared_actions(prepared_action_id, workspace_id, task_id, run_id, tool_call_id, approval_id, requested_by_agent_id, action_type, provider, target_resource, normalized_args_json, args_hash, snapshot_ref, snapshot_hash, status, result_json, created_at, updated_at, approved_at, consumed_at)
VALUES
('pact_pg_a', 'ws_pg_a', 'tsk_pg_a', 'run_pg_a', 'tc_pg_a', 'ap_pg_a', 'agt_pg_a', 'runtime.external_write', 'postgres-parity', 'postgres://local/container', '{{"workspace_id":"ws_pg_a"}}', 'args_hash_pg_a', 'snapshot://pg/a', 'snapshot_hash_pg_a', 'waiting_approval', '{{}}', '{now}', '{now}', NULL, NULL);

INSERT INTO agent_plans(plan_id, workspace_id, task_id, run_id, agent_id, task_understanding, referenced_specs_json, referenced_memories_json, referenced_bases_json, proposed_files_to_change_json, risk_level, approval_required, execution_steps_json, verification_plan, rollback_plan, status, created_at, updated_at)
VALUES
('plan_pg_a', 'ws_pg_a', 'tsk_pg_a', 'run_pg_a', 'agt_pg_a', 'Prove Postgres parity fixture.', '["docs/POSTGRES_PARITY_CONTRACT.md"]', '[]', '[]', '["scripts/storage_postgres_container_smoke.py"]', 'low', 0, '["create schema","insert fixture","verify isolation"]', 'Run container parity smoke.', 'Drop temporary container.', 'submitted', '{now}', '{now}');

INSERT INTO plan_evidence_manifests(manifest_id, workspace_id, plan_id, task_id, run_id, agent_id, mismatch_policy, expected_steps_json, tool_call_ids_json, evaluation_ids_json, artifact_ids_json, audit_ids_json, status, verification_json, created_at, updated_at)
VALUES
('pem_pg_a', 'ws_pg_a', 'plan_pg_a', 'tsk_pg_a', 'run_pg_a', 'agt_pg_a', 'block', '["create schema","insert fixture","verify isolation"]', '["tc_pg_a"]', '[]', '[]', '[]', 'verified', '{{"container":"postgres","workspace_isolation":true}}', '{now}', '{now}');

COMMIT;

DO $$
DECLARE
    count_value integer;
BEGIN
    SELECT COUNT(*) INTO count_value FROM tasks WHERE workspace_id = 'ws_pg_a';
    IF count_value != 1 THEN
        RAISE EXCEPTION 'expected one workspace A task, got %', count_value;
    END IF;

    SELECT COUNT(*) INTO count_value FROM tasks WHERE workspace_id = 'ws_pg_a' AND task_id = 'tsk_pg_b';
    IF count_value != 0 THEN
        RAISE EXCEPTION 'workspace A task query leaked workspace B task';
    END IF;

    SELECT COUNT(*) INTO count_value
    FROM runs r
    JOIN tasks t ON t.task_id = r.task_id
    WHERE r.workspace_id = 'ws_pg_a' AND t.workspace_id = 'ws_pg_a';
    IF count_value != 1 THEN
        RAISE EXCEPTION 'workspace A run/task join mismatch: %', count_value;
    END IF;

    SELECT COUNT(*) INTO count_value FROM prepared_actions WHERE workspace_id = 'ws_pg_a' AND status = 'waiting_approval';
    IF count_value != 1 THEN
        RAISE EXCEPTION 'prepared-action exact-resume fixture missing: %', count_value;
    END IF;

    SELECT COUNT(*) INTO count_value FROM plan_evidence_manifests WHERE workspace_id = 'ws_pg_a' AND status = 'verified';
    IF count_value != 1 THEN
        RAISE EXCEPTION 'verified plan-evidence fixture missing: %', count_value;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE tablename = 'tasks' AND indexname = 'idx_tasks_workspace') THEN
        RAISE EXCEPTION 'idx_tasks_workspace missing';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE tablename = 'runs' AND indexname = 'idx_runs_workspace') THEN
        RAISE EXCEPTION 'idx_runs_workspace missing';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE tablename = 'prepared_actions' AND indexname = 'idx_prepared_actions_workspace') THEN
        RAISE EXCEPTION 'idx_prepared_actions_workspace missing';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE tablename = 'agent_plans' AND indexname = 'idx_agent_plans_workspace') THEN
        RAISE EXCEPTION 'idx_agent_plans_workspace missing';
    END IF;
END $$;
"""


def docker_exec(container: str, pg_auth: str, psql_args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return run(
        [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={pg_auth}",
            container,
            "psql",
            "-h",
            "127.0.0.1",
            "-U",
            "agentops",
            "-d",
            "agentops",
            "-v",
            "ON_ERROR_STOP=1",
            *psql_args,
        ],
        timeout=timeout,
    )


def wait_for_postgres(container: str, timeout_sec: int = 45) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ready = run(["docker", "exec", container, "pg_isready", "-U", "agentops", "-d", "agentops"], timeout=10)
        if ready.returncode == 0:
            return True
        time.sleep(1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Postgres container storage parity smoke.")
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Postgres Docker image to use.")
    parser.add_argument("--skip-if-unavailable", action="store_true", help="Return success with skipped=true when Docker/image is unavailable.")
    args = parser.parse_args()

    early = docker_available(args.skip_if_unavailable)
    if early is not None:
        return early
    early = ensure_image(args.image, args.skip_if_unavailable)
    if early is not None:
        return early

    container = f"agentops-pg-parity-{secrets.token_hex(6)}"
    pg_auth = secrets.token_urlsafe(18)
    sqlite_sql = server.SCHEMA_SQL
    postgres_sql = contract.postgres_ddl_from_sqlite(sqlite_sql)
    fixture_sql = postgres_fixture_sql()

    started = run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container,
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
        detail = (started.stderr or started.stdout or "docker run failed").strip()
        return unavailable(f"Postgres container failed to start: {detail}", skip=args.skip_if_unavailable)

    try:
        if not wait_for_postgres(container):
            return unavailable("Postgres container did not become ready before timeout.", skip=args.skip_if_unavailable)

        with tempfile.TemporaryDirectory(prefix="agentops-pg-parity-") as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            fixture_path = Path(temp_dir) / "fixture.sql"
            schema_path.write_text(postgres_sql, encoding="utf-8")
            fixture_path.write_text(fixture_sql, encoding="utf-8")

            for local_path, remote_path in [
                (schema_path, "/tmp/agentops_schema.sql"),
                (fixture_path, "/tmp/agentops_fixture.sql"),
            ]:
                copied = run(["docker", "cp", str(local_path), f"{container}:{remote_path}"], timeout=30)
                if copied.returncode != 0:
                    detail = (copied.stderr or copied.stdout or "docker cp failed").strip()
                    raise RuntimeError(detail)

            schema_result = docker_exec(container, pg_auth, ["-f", "/tmp/agentops_schema.sql"], timeout=90)
            if schema_result.returncode != 0:
                raise RuntimeError((schema_result.stderr or schema_result.stdout).strip())

            fixture_result = docker_exec(container, pg_auth, ["-f", "/tmp/agentops_fixture.sql"], timeout=90)
            if fixture_result.returncode != 0:
                raise RuntimeError((fixture_result.stderr or fixture_result.stdout).strip())

            count_result = docker_exec(
                container,
                pg_auth,
                ["-At", "-c", "SELECT COUNT(*) FROM tasks WHERE workspace_id='ws_pg_a';"],
                timeout=30,
            )
            if count_result.returncode != 0:
                raise RuntimeError((count_result.stderr or count_result.stdout).strip())

        output = {
            "ok": True,
            "skipped": False,
            "contract": "postgres_container_parity_v1",
            "image": args.image,
            "sqlite_schema_hash": sha256_text(sqlite_sql),
            "postgres_ddl_hash": sha256_text(postgres_sql),
            "workspace_a_task_count": count_result.stdout.strip(),
            "verified_tables": [
                "tasks",
                "runs",
                "tool_calls",
                "approvals",
                "prepared_actions",
                "agent_plans",
                "plan_evidence_manifests",
            ],
            "verified_indexes": [
                "idx_tasks_workspace",
                "idx_runs_workspace",
                "idx_prepared_actions_workspace",
                "idx_agent_plans_workspace",
            ],
            "next_proof": "Implement a Postgres adapter that runs the full storage-boundary helper fixture against this schema.",
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        payload = {
            "ok": False,
            "skipped": False,
            "contract": "postgres_container_parity_v1",
            "image": args.image,
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    finally:
        run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
