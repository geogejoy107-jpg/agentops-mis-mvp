#!/usr/bin/env python3
"""Run selected AgentOps CLI writes against a Postgres-backed server adapter."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
import storage_postgres_http_write_task_smoke as http_write  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402
from storage_postgres_http_read_parity_smoke import (  # noqa: E402
    connect_postgres_when_ready,
    free_port,
    start_server,
    wait_json,
)
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402


CONTRACT_ID = "postgres_cli_write_parity_v1"
CLI_TASK_ID = "tsk_pg_cli_gateway_write"
CLI_READ_ONLY_TASK_ID = "tsk_pg_cli_gateway_read_only_blocked"
CLI_MISSING_SCOPE_TASK_ID = "tsk_pg_cli_gateway_missing_scope"
CLI_ARTIFACT_ID = "art_pg_cli_gateway_write"
CLI_MANIFEST_ID = "pem_pg_cli_gateway_write"
CLI_AUDIT_ACTION = "agent_gateway.postgres_cli_audit_write"


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_CLI_WRITE_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_CLI_WRITE_PG_REEXEC"] = "1"
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


def redact_many(value: str, secrets: list[str]) -> str:
    redacted = value or ""
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def run_cli(args: list[str], env: dict[str, str], *, secrets: list[str], expect_ok: bool = True) -> tuple[int, dict | None, str]:
    result = subprocess.run(
        [sys.executable, "-m", "agentops_mis_cli", *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    stdout = redact_many(result.stdout, secrets)
    stderr = redact_many(result.stderr, secrets)
    if expect_ok and result.returncode != 0:
        raise RuntimeError(f"CLI failed: args={args} rc={result.returncode} stdout={stdout} stderr={stderr}")
    if not expect_ok and result.returncode == 0:
        raise RuntimeError(f"CLI unexpectedly succeeded: args={args} stdout={stdout}")
    payload = None
    if stdout.strip():
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CLI returned non-JSON: args={args} stdout={stdout} stderr={stderr}") from exc
    return result.returncode, payload, stderr


def cli_env(base_url: str, temp_root: Path, pythonpath: str, *, token: str, agent_id: str, workspace_id: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": pythonpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "AGENTOPS_BASE_URL": base_url,
            "AGENTOPS_WORKSPACE_ID": workspace_id,
            "AGENTOPS_AGENT_ID": agent_id,
            "AGENTOPS_API_KEY": token,
            "AGENTOPS_CONFIG": str(temp_root / f"agentops-cli-{agent_id}.json"),
            "AGENTOPS_REQUEST_TIMEOUT": "10",
        }
    )
    env.pop("AGENTOPS_DB_PATH", None)
    return env


def token_like_leaked(payloads: dict, stderr_values: list[str], *, secrets: list[str]) -> bool:
    haystack = dumps(payloads) + "\n" + "\n".join(stderr_values)
    for secret in secrets:
        if secret and secret in haystack:
            return True
    forbidden = ["agtok_", "agtsess_", "sk-", "ntn_", "BEGIN PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY"]
    return any(marker in haystack for marker in forbidden)


def stderr_mentions(stderr: str, *, status: int, reason: str) -> bool:
    return str(status) in stderr and reason in stderr


def row_id(payload: dict | None, key: str, id_key: str) -> str | None:
    if not payload:
        return None
    row = payload.get(key)
    if isinstance(row, dict):
        return row.get(id_key)
    return None


def assert_status(failures: list[str], name: str, payload: dict | None, key: str, field: str, expected) -> None:
    row = (payload or {}).get(key) or {}
    if row.get(field) != expected:
        failures.append(f"{name}_mismatch:{payload}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Postgres-backed server CLI write parity smoke.")
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

    with tempfile.TemporaryDirectory(prefix="agentops-cli-pg-write-") as temp_dir:
        temp_root = Path(temp_dir)
        driver_ok, driver_status = ensure_psycopg(temp_root, install=not args.no_install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=args.skip_if_unavailable)

        pythonpath_parts = [str(ROOT)]
        package_target = temp_root / "python-packages"
        if package_target.exists():
            pythonpath_parts.insert(0, str(package_target))
        if os.environ.get("PYTHONPATH"):
            pythonpath_parts.append(os.environ["PYTHONPATH"])
        pythonpath = os.pathsep.join(pythonpath_parts)

        container = f"agentops-pg-cli-write-{container_smoke.secrets.token_hex(6)}"
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
            detail = redact_many((started.stderr or started.stdout or "docker run failed").strip(), [pg_auth])
            return unavailable(f"Postgres container failed to start: {detail}", skip=args.skip_if_unavailable)

        adapter: PostgresAdapter | None = None
        proc: subprocess.Popen[str] | None = None
        gateway_token = "pg_cli_gateway_token_" + container_smoke.secrets.token_urlsafe(24)
        gateway_observer_token = "pg_cli_observer_token_" + container_smoke.secrets.token_urlsafe(18)
        gateway_completion_token = "pg_cli_completion_token_" + container_smoke.secrets.token_urlsafe(18)
        secrets = [pg_auth, gateway_token, gateway_observer_token, gateway_completion_token]
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=args.skip_if_unavailable)
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = connect_postgres_when_ready(dsn, secret=pg_auth)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            http_write.seed_reference_rows(adapter)
            http_write.seed_gateway_token(
                adapter,
                token_id="tok_pg_cli_gateway_write",
                raw_token=gateway_token,
                agent_id=http_write.GATEWAY_AGENT_ID,
                workspace_id=http_write.GATEWAY_WORKSPACE_ID,
                scopes=[
                    "agents:heartbeat",
                    "tasks:create",
                    "tasks:read",
                    "tasks:claim",
                    "runs:write",
                    "toolcalls:write",
                    "artifacts:write",
                    "evaluations:submit",
                    "agent_plans:read",
                    "agent_plans:write",
                    "plan_evidence:read",
                    "plan_evidence:write",
                    "memories:propose",
                    "approvals:request",
                    "audit:write",
                ],
            )
            http_write.seed_gateway_token(
                adapter,
                token_id="tok_pg_cli_gateway_observer",
                raw_token=gateway_observer_token,
                agent_id=http_write.GATEWAY_OBSERVER_AGENT_ID,
                workspace_id=http_write.GATEWAY_WORKSPACE_ID,
                scopes=["tasks:read"],
            )
            http_write.seed_gateway_token(
                adapter,
                token_id="tok_pg_cli_gateway_completion",
                raw_token=gateway_completion_token,
                agent_id=http_write.GATEWAY_COMPLETION_AGENT_ID,
                workspace_id=http_write.GATEWAY_WORKSPACE_ID,
                scopes=["runs:write"],
            )
            adapter.close()
            adapter = None

            read_only_port = free_port()
            proc = start_server(http_write.server_env(dsn, pythonpath, write_enabled=False), read_only_port)
            read_only_base = f"http://127.0.0.1:{read_only_port}"
            read_only_status_code, read_only_backend = wait_json(f"{read_only_base}/api/storage/backend-status", proc, secret=pg_auth)
            read_only_env = cli_env(
                read_only_base,
                temp_root,
                pythonpath,
                token=gateway_token,
                agent_id=http_write.GATEWAY_AGENT_ID,
                workspace_id=http_write.GATEWAY_WORKSPACE_ID,
            )
            _ro_rc, _ro_payload, read_only_stderr = run_cli(
                [
                    "task",
                    "create",
                    "--task-id",
                    CLI_READ_ONLY_TASK_ID,
                    "--title",
                    "Read-only CLI task write must fail",
                    "--description",
                    "Postgres read-only mode must block agent-facing CLI writes.",
                    "--owner-agent-id",
                    http_write.GATEWAY_AGENT_ID,
                    "--status",
                    "planned",
                    "--risk",
                    "low",
                ],
                read_only_env,
                secrets=secrets,
                expect_ok=False,
            )
            http_write.stop_server(proc)
            proc = None

            write_port = free_port()
            proc = start_server(http_write.server_env(dsn, pythonpath, write_enabled=True), write_port)
            write_base = f"http://127.0.0.1:{write_port}"
            write_status_code, write_backend = wait_json(f"{write_base}/api/storage/backend-status", proc, secret=pg_auth)
            main_env = cli_env(
                write_base,
                temp_root,
                pythonpath,
                token=gateway_token,
                agent_id=http_write.GATEWAY_AGENT_ID,
                workspace_id=http_write.GATEWAY_WORKSPACE_ID,
            )
            observer_env = cli_env(
                write_base,
                temp_root,
                pythonpath,
                token=gateway_observer_token,
                agent_id=http_write.GATEWAY_OBSERVER_AGENT_ID,
                workspace_id=http_write.GATEWAY_WORKSPACE_ID,
            )
            completion_env = cli_env(
                write_base,
                temp_root,
                pythonpath,
                token=gateway_completion_token,
                agent_id=http_write.GATEWAY_COMPLETION_AGENT_ID,
                workspace_id=http_write.GATEWAY_WORKSPACE_ID,
            )

            payloads: dict[str, dict] = {}
            stderr_values = [read_only_stderr]

            _rc, payload, stderr = run_cli(
                [
                    "task",
                    "create",
                    "--task-id",
                    CLI_MISSING_SCOPE_TASK_ID,
                    "--title",
                    "Missing scope CLI task write must fail",
                    "--description",
                    "Observer token must not create tasks in Postgres write mode.",
                    "--owner-agent-id",
                    http_write.GATEWAY_OBSERVER_AGENT_ID,
                    "--status",
                    "planned",
                    "--risk",
                    "low",
                ],
                observer_env,
                secrets=secrets,
                expect_ok=False,
            )
            stderr_values.append(stderr)
            missing_scope_stderr = stderr

            _rc, payload, stderr = run_cli(["knowledge", "index"], main_env, secrets=secrets, expect_ok=False)
            stderr_values.append(stderr)
            non_allowlisted_stderr = stderr

            cli_commands: list[str] = []

            def run_named(name: str, cli_args: list[str], env: dict[str, str] = main_env) -> dict:
                _rc2, payload2, stderr2 = run_cli(cli_args, env, secrets=secrets)
                payloads[name] = server.json_safe(payload2 or {})
                stderr_values.append(stderr2)
                cli_commands.append(name)
                return payload2 or {}

            heartbeat_payload = run_named(
                "agent_heartbeat",
                [
                    "agent",
                    "heartbeat",
                    "--status",
                    "running",
                    "--summary",
                    "Postgres CLI Gateway agent heartbeat write proof.",
                    "--runtime",
                    "mock",
                ],
            )
            task_payload = run_named(
                "task_create",
                [
                    "task",
                    "create",
                    "--task-id",
                    CLI_TASK_ID,
                    "--title",
                    "Postgres CLI Gateway task write",
                    "--description",
                    "Created through the AgentOps CLI against a Postgres write server.",
                    "--owner-agent-id",
                    http_write.GATEWAY_AGENT_ID,
                    "--status",
                    "planned",
                    "--priority",
                    "high",
                    "--risk",
                    "low",
                    "--acceptance",
                    "CLI writes must persist task, run, evidence, approval, memory, and audit rows in Postgres.",
                    "--budget",
                    "2.0",
                ],
            )
            claim_payload = run_named("task_claim", ["task", "claim", "--task-id", CLI_TASK_ID, "--runtime", "mock"])
            run_start_payload = run_named(
                "run_start",
                [
                    "run",
                    "start",
                    "--task-id",
                    CLI_TASK_ID,
                    "--runtime",
                    "mock",
                    "--input-summary",
                    "Postgres Agent Gateway CLI run start write proof.",
                ],
            )
            run_id = row_id(run_start_payload, "run", "run_id")
            if not run_id:
                raise RuntimeError(f"CLI run start did not return run_id: {run_start_payload}")
            run_heartbeat_payload = run_named(
                "run_heartbeat",
                [
                    "run",
                    "heartbeat",
                    "--run-id",
                    run_id,
                    "--status",
                    "running",
                    "--summary",
                    "Postgres CLI Gateway run heartbeat write proof.",
                    "--duration-ms",
                    "1234",
                    "--output-tokens",
                    "11",
                    "--cost",
                    "0.01",
                ],
            )
            tool_payload = run_named(
                "toolcall_record",
                [
                    "toolcall",
                    "record",
                    "--run-id",
                    run_id,
                    "--tool",
                    "postgres.cli_gateway_tool",
                    "--category",
                    "custom",
                    "--risk",
                    "low",
                    "--status",
                    "completed",
                    "--target",
                    f"run://{run_id}",
                    "--args-json",
                    dumps({"raw_omitted": True, "contract": "postgres_cli_gateway_evidence_write_v1"}),
                    "--summary",
                    "Postgres CLI Gateway tool-call evidence write proof.",
                ],
            )
            tool_call_id = row_id(tool_payload, "tool_call", "tool_call_id")
            if not tool_call_id:
                raise RuntimeError(f"CLI toolcall record did not return tool_call_id: {tool_payload}")
            eval_payload = run_named(
                "evaluation_submit",
                [
                    "eval",
                    "submit",
                    "--run-id",
                    run_id,
                    "--task-id",
                    CLI_TASK_ID,
                    "--gate",
                    "postgres_cli_gateway_write",
                    "--score",
                    "1.0",
                    "--pass",
                    "--evaluator-type",
                    "rule",
                    "--rubric-json",
                    dumps({"gate": "postgres_cli_gateway_write"}),
                    "--notes",
                    "Postgres CLI Gateway evaluation evidence write proof.",
                ],
            )
            evaluation_id = row_id(eval_payload, "evaluation", "evaluation_id")
            if not evaluation_id:
                raise RuntimeError(f"CLI eval submit did not return evaluation_id: {eval_payload}")
            artifact_payload = run_named(
                "artifact_record",
                [
                    "artifact",
                    "record",
                    "--run-id",
                    run_id,
                    "--task-id",
                    CLI_TASK_ID,
                    "--artifact-id",
                    CLI_ARTIFACT_ID,
                    "--type",
                    "postgres_cli_evidence",
                    "--title",
                    "Postgres CLI Gateway evidence artifact",
                    "--uri",
                    f"run://{run_id}",
                    "--summary",
                    "Postgres CLI Gateway artifact evidence write proof.",
                    "--content-hash",
                    "pg_cli_gateway_evidence_hash",
                ],
            )
            plan_payload = run_named(
                "agent_plan_create",
                [
                    "agent-plan",
                    "create",
                    "--task-id",
                    CLI_TASK_ID,
                    "--run-id",
                    run_id,
                    "--task-understanding",
                    "Bind the Postgres CLI Gateway execution to a verifiable READ/PLAN/EXECUTE/VERIFY/RECORD chain.",
                    "--referenced-specs",
                    "docs/AGENT_GATEWAY_CLI_SPEC.md,docs/POSTGRES_PARITY_CONTRACT.md",
                    "--referenced-memories",
                    "project-memory:postgres-cli-write-proof",
                    "--referenced-bases",
                    "agent_gateway_ledger,postgres_storage_boundary",
                    "--proposed-files-to-change",
                    "scripts/storage_postgres_cli_write_parity_smoke.py",
                    "--risk",
                    "low",
                    "--execution-steps-json",
                    dumps(["READ", "PLAN", "EXECUTE", "VERIFY", "RECORD"]),
                    "--verification-plan",
                    "Verify CLI-written task, run, tool, evaluation, artifact, audit, Agent Plan, and plan-evidence rows in Postgres.",
                    "--rollback-plan",
                    "Remove CLI write parity from readiness if verification fails.",
                    "--status",
                    "submitted",
                ],
            )
            plan_id = row_id(plan_payload, "agent_plan", "plan_id")
            if not plan_id:
                raise RuntimeError(f"CLI agent-plan create did not return plan_id: {plan_payload}")
            manifest_payload = run_named(
                "plan_evidence_create",
                [
                    "plan-evidence",
                    "create",
                    "--manifest-id",
                    CLI_MANIFEST_ID,
                    "--plan-id",
                    plan_id,
                    "--task-id",
                    CLI_TASK_ID,
                    "--run-id",
                    run_id,
                    "--mismatch-policy",
                    "block",
                    "--expected-steps-json",
                    dumps(["READ", "PLAN", "EXECUTE", "VERIFY", "RECORD"]),
                    "--tool-call-ids",
                    tool_call_id,
                    "--evaluation-ids",
                    evaluation_id,
                    "--artifact-ids",
                    CLI_ARTIFACT_ID,
                ],
            )
            memory_payload = run_named(
                "memory_propose",
                [
                    "memory",
                    "propose",
                    "--task-id",
                    CLI_TASK_ID,
                    "--run-id",
                    run_id,
                    "--scope",
                    "project",
                    "--type",
                    "agent_lesson",
                    "--text",
                    "Postgres CLI Gateway memory candidate write proof with raw prompt omitted.",
                    "--source-ref",
                    run_id,
                    "--access-tags",
                    "agent-gateway,postgres-cli-write-proof",
                    "--confidence",
                    "0.88",
                ],
            )
            memory_id = row_id(memory_payload, "memory", "memory_id")
            audit_payload = run_named(
                "audit_emit",
                [
                    "audit",
                    "emit",
                    "--action",
                    CLI_AUDIT_ACTION,
                    "--entity-type",
                    "runs",
                    "--entity-id",
                    run_id,
                    "--task-id",
                    CLI_TASK_ID,
                    "--run-id",
                    run_id,
                    "--metadata-json",
                    dumps({"contract": "postgres_cli_gateway_audit_write_v1", "raw_omitted": True}),
                ],
            )
            approval_payload = run_named(
                "approval_request",
                [
                    "approval",
                    "request",
                    "--task-id",
                    CLI_TASK_ID,
                    "--run-id",
                    run_id,
                    "--tool-call-id",
                    tool_call_id,
                    "--reason",
                    "Postgres CLI Gateway approval request write proof.",
                    "--approver",
                    "usr_founder",
                ],
            )
            approval_id = row_id(approval_payload, "approval", "approval_id")
            completion_payload = run_named(
                "run_completion_heartbeat",
                [
                    "run",
                    "heartbeat",
                    "--run-id",
                    http_write.GATEWAY_COMPLETION_RUN_ID,
                    "--status",
                    "completed",
                    "--summary",
                    "Postgres CLI Gateway run completion heartbeat proof.",
                    "--duration-ms",
                    "4567",
                    "--output-tokens",
                    "31",
                    "--cost",
                    "0.021",
                ],
                completion_env,
            )

            http_write.stop_server(proc)
            proc = None

            adapter = connect_postgres_when_ready(dsn, secret=pg_auth)
            task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [CLI_TASK_ID])
            read_only_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [CLI_READ_ONLY_TASK_ID])
            missing_scope_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [CLI_MISSING_SCOPE_TASK_ID])
            run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [run_id])
            tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [tool_call_id])
            eval_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [evaluation_id])
            artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [CLI_ARTIFACT_ID])
            plan_row = adapter.fetchone("SELECT * FROM agent_plans WHERE plan_id=?", [plan_id])
            manifest_row = adapter.fetchone("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", [CLI_MANIFEST_ID])
            memory_row = adapter.fetchone("SELECT * FROM memories WHERE memory_id=?", [memory_id])
            approval_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [approval_id])
            audit_row = adapter.fetchone("SELECT * FROM audit_logs WHERE action=?", [CLI_AUDIT_ACTION])
            completion_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [http_write.GATEWAY_COMPLETION_RUN_ID])
            completion_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [http_write.GATEWAY_COMPLETION_TASK_ID])
            completion_agent_row = adapter.fetchone("SELECT * FROM agents WHERE agent_id=?", [http_write.GATEWAY_COMPLETION_AGENT_ID])
            token_row = adapter.fetchone("SELECT last_used_at,last_heartbeat_at FROM agent_gateway_tokens WHERE token_id=?", ["tok_pg_cli_gateway_write"])
            cli_run_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=?", [run_id])["c"]
            cli_run_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_id=?", [run_id])["c"]
            completion_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [http_write.GATEWAY_COMPLETION_RUN_ID, "run.heartbeat"])["c"]
            completion_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=? AND action=?", ["runs", http_write.GATEWAY_COMPLETION_RUN_ID, "agent_gateway.run_heartbeat"])["c"]

            failures: list[str] = []
            if read_only_status_code != 200 or read_only_backend.get("mode") != "read_only_http" or read_only_backend.get("writes_allowed") is not False:
                failures.append(f"read_only_backend_mismatch:{read_only_backend}")
            if not stderr_mentions(read_only_stderr, status=503, reason="postgres_read_only_backend"):
                failures.append(f"cli_read_only_write_block_missing_reason:{read_only_stderr}")
            if write_status_code != 200 or write_backend.get("mode") != "experimental_write_http" or write_backend.get("writes_allowed") is not True:
                failures.append(f"write_backend_mismatch:{write_backend}")
            if not stderr_mentions(missing_scope_stderr, status=403, reason="forbidden"):
                failures.append(f"cli_missing_scope_missing_reason:{missing_scope_stderr}")
            if not stderr_mentions(non_allowlisted_stderr, status=503, reason="postgres_read_only_backend"):
                failures.append(f"cli_non_allowlisted_write_missing_reason:{non_allowlisted_stderr}")
            if read_only_task_row:
                failures.append(f"cli_read_only_write_created_task:{read_only_task_row}")
            if missing_scope_task_row:
                failures.append(f"cli_missing_scope_created_task:{missing_scope_task_row}")

            if heartbeat_payload.get("status") != "running" or heartbeat_payload.get("agent_id") != http_write.GATEWAY_AGENT_ID:
                failures.append(f"agent_heartbeat_mismatch:{heartbeat_payload}")
            assert_status(failures, "task_create", task_payload, "task", "task_id", CLI_TASK_ID)
            assert_status(failures, "task_claim", claim_payload, "task", "status", "running")
            assert_status(failures, "run_start", run_start_payload, "run", "status", "running")
            assert_status(failures, "run_heartbeat", run_heartbeat_payload, "run", "status", "running")
            assert_status(failures, "toolcall_record", tool_payload, "tool_call", "status", "completed")
            assert_status(failures, "evaluation_submit", eval_payload, "evaluation", "pass_fail", "pass")
            assert_status(failures, "artifact_record", artifact_payload, "artifact", "artifact_id", CLI_ARTIFACT_ID)
            assert_status(failures, "agent_plan_create", plan_payload, "agent_plan", "status", "submitted")
            assert_status(failures, "plan_evidence_create", manifest_payload, "manifest", "status", "verified")
            if ((manifest_payload.get("verification") or {}).get("pass") is not True):
                failures.append(f"cli_plan_evidence_verification_failed:{manifest_payload}")
            assert_status(failures, "memory_propose", memory_payload, "memory", "review_status", "candidate")
            if not audit_payload.get("emitted"):
                failures.append(f"cli_audit_emit_mismatch:{audit_payload}")
            assert_status(failures, "approval_request", approval_payload, "approval", "decision", "pending")
            assert_status(failures, "run_completion_heartbeat", completion_payload, "run", "status", "completed")

            if not task_row or task_row.get("status") != "waiting_approval" or task_row.get("owner_agent_id") != http_write.GATEWAY_AGENT_ID:
                failures.append(f"postgres_cli_task_row_mismatch:{task_row}")
            if not run_row or run_row.get("status") != "waiting_approval" or run_row.get("task_id") != CLI_TASK_ID:
                failures.append(f"postgres_cli_run_row_mismatch:{run_row}")
            if not tool_row or tool_row.get("run_id") != run_id or tool_row.get("agent_id") != http_write.GATEWAY_AGENT_ID:
                failures.append(f"postgres_cli_tool_row_mismatch:{tool_row}")
            if not eval_row or eval_row.get("run_id") != run_id or eval_row.get("pass_fail") != "pass":
                failures.append(f"postgres_cli_evaluation_row_mismatch:{eval_row}")
            if not artifact_row or artifact_row.get("run_id") != run_id:
                failures.append(f"postgres_cli_artifact_row_mismatch:{artifact_row}")
            if not plan_row or plan_row.get("run_id") != run_id or plan_row.get("agent_id") != http_write.GATEWAY_AGENT_ID:
                failures.append(f"postgres_cli_plan_row_mismatch:{plan_row}")
            if not manifest_row or manifest_row.get("status") != "verified" or manifest_row.get("run_id") != run_id:
                failures.append(f"postgres_cli_manifest_row_mismatch:{manifest_row}")
            if not memory_row or memory_row.get("review_status") != "candidate" or memory_row.get("source_ref") != run_id or memory_row.get("task_id") != CLI_TASK_ID:
                failures.append(f"postgres_cli_memory_row_mismatch:{memory_row}")
            if not approval_row or approval_row.get("decision") != "pending" or approval_row.get("run_id") != run_id:
                failures.append(f"postgres_cli_approval_row_mismatch:{approval_row}")
            if not audit_row or audit_row.get("entity_id") != run_id:
                failures.append(f"postgres_cli_audit_row_mismatch:{audit_row}")
            if not completion_run_row or completion_run_row.get("status") != "completed" or completion_run_row.get("ended_at") is None or int(completion_run_row.get("duration_ms") or 0) != 4567:
                failures.append(f"postgres_cli_completion_run_row_mismatch:{completion_run_row}")
            if not completion_task_row or completion_task_row.get("status") != "completed":
                failures.append(f"postgres_cli_completion_task_row_mismatch:{completion_task_row}")
            if not completion_agent_row or completion_agent_row.get("status") != "idle":
                failures.append(f"postgres_cli_completion_agent_row_mismatch:{completion_agent_row}")
            if not token_row or not token_row.get("last_used_at") or not token_row.get("last_heartbeat_at"):
                failures.append(f"postgres_cli_token_usage_mismatch:{token_row}")
            if int(cli_run_runtime_event_count or 0) < 8:
                failures.append(f"postgres_cli_run_runtime_events_too_low:{cli_run_runtime_event_count}")
            if int(cli_run_audit_count or 0) < 2:
                failures.append(f"postgres_cli_run_audit_events_too_low:{cli_run_audit_count}")
            if int(completion_runtime_event_count or 0) < 1:
                failures.append("postgres_cli_completion_runtime_event_missing")
            if int(completion_audit_count or 0) < 1:
                failures.append("postgres_cli_completion_audit_missing")
            if token_like_leaked(payloads, stderr_values, secrets=secrets):
                failures.append("postgres_cli_write_raw_token_leaked")

            output = {
                "ok": not failures,
                "skipped": False,
                "contract": CONTRACT_ID,
                "contracts": [
                    CONTRACT_ID,
                    "postgres_cli_gateway_task_write_v1",
                    "postgres_cli_gateway_execution_start_write_v1",
                    "postgres_cli_gateway_heartbeat_write_v1",
                    "postgres_cli_gateway_run_heartbeat_write_v1",
                    "postgres_cli_gateway_run_completion_heartbeat_write_v1",
                    "postgres_cli_gateway_evidence_write_v1",
                    "postgres_cli_gateway_plan_evidence_write_v1",
                    "postgres_cli_gateway_memory_write_v1",
                    "postgres_cli_gateway_approval_write_v1",
                    "postgres_cli_gateway_audit_write_v1",
                ],
                "image": args.image,
                "driver_status": driver_status,
                "read_only_backend_mode": read_only_backend.get("mode"),
                "read_only_write_block_checked": True,
                "write_backend_mode": write_backend.get("mode"),
                "cli_write_command_count": len(cli_commands),
                "cli_block_command_count": 3,
                "cli_commands": cli_commands,
                "cli_read_only_task_status": "blocked",
                "cli_missing_scope_status": "blocked",
                "cli_non_allowlisted_write_status": "blocked",
                "gateway_task_id": CLI_TASK_ID,
                "gateway_run_id": run_id,
                "gateway_tool_call_id": tool_call_id,
                "gateway_evaluation_id": evaluation_id,
                "gateway_artifact_id": CLI_ARTIFACT_ID,
                "gateway_plan_id": plan_id,
                "gateway_manifest_id": CLI_MANIFEST_ID,
                "gateway_manifest_status": manifest_row.get("status") if manifest_row else None,
                "gateway_memory_id": memory_id,
                "gateway_approval_id": approval_id,
                "gateway_completion_run_id": http_write.GATEWAY_COMPLETION_RUN_ID,
                "gateway_completion_run_status": completion_run_row.get("status") if completion_run_row else None,
                "gateway_completion_task_status": completion_task_row.get("status") if completion_task_row else None,
                "gateway_completion_agent_status": completion_agent_row.get("status") if completion_agent_row else None,
                "gateway_completion_run_ended": bool(completion_run_row and completion_run_row.get("ended_at")),
                "gateway_token_last_heartbeat": bool(token_row and token_row.get("last_heartbeat_at")),
                "gateway_token_last_used": bool(token_row and token_row.get("last_used_at")),
                "gateway_run_runtime_event_count": int(cli_run_runtime_event_count or 0),
                "gateway_run_audit_count": int(cli_run_audit_count or 0),
                "gateway_run_completion_heartbeat_runtime_event_count": int(completion_runtime_event_count or 0),
                "gateway_run_completion_heartbeat_audit_count": int(completion_audit_count or 0),
                "fallback_performed": False,
                "free_local_dependencies": [],
                "token_omitted": True,
                "failures": failures,
                "next_proof": "Widen Agent Gateway CLI write coverage only after each CLI command has Postgres-backed row and guard evidence.",
            }
            if failures:
                output["payloads"] = payloads
                output["read_only_stderr"] = read_only_stderr
                output["missing_scope_stderr"] = missing_scope_stderr
                output["non_allowlisted_stderr"] = non_allowlisted_stderr
            print(json.dumps(server.json_safe(output), ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not failures else 1
        except (AssertionError, PostgresAdapterUnavailable, RuntimeError, ValueError, KeyError) as exc:
            if adapter is not None:
                adapter.rollback()
            return unavailable(redact_many(str(exc), secrets), skip=args.skip_if_unavailable)
        finally:
            if proc is not None:
                http_write.stop_server(proc)
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
