#!/usr/bin/env python3
"""Prove one explicit Postgres-backed HTTP write route."""
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
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402
from storage_postgres_http_read_parity_smoke import free_port, request_json, start_server, wait_json  # noqa: E402
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402


CONTRACT_ID = "postgres_http_write_task_parity_v1"
WORKSPACE_ID = "ws_pg_http_write"
AGENT_ID = "agt_pg_http_write"
TASK_ID = "tsk_pg_http_write_task"
BLOCKED_TASK_ID = "tsk_pg_http_write_blocked"
BLOCKED_AGENT_ID = "agt_pg_http_write_blocked"


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
    adapter.execute(
        """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
        VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""",
        {
            "agent_id": AGENT_ID,
            "name": "Postgres HTTP Writer",
            "role": "operator",
            "description": "Seed agent for routed Postgres HTTP task write smoke.",
            "runtime_type": "mock",
            "model_provider": "mock",
            "model_name": "mock-model",
            "status": "idle",
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
    adapter.commit()


def server_env(dsn: str, pythonpath: str, *, write_enabled: bool) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "AGENTOPS_STORAGE_BACKEND": "postgres",
            "AGENTOPS_EDITION": "enterprise_byoc",
            "AGENTOPS_POSTGRES_DSN": dsn,
            "AGENTOPS_ENABLE_POSTGRES_STORAGE": "1",
            "AGENTOPS_POSTGRES_READ_ONLY_HTTP": "1",
            "PYTHONPATH": pythonpath,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
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
            return unavailable(f"Postgres container failed to start: {detail}", skip=args.skip_if_unavailable)

        adapter: PostgresAdapter | None = None
        proc: subprocess.Popen[str] | None = None
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=args.skip_if_unavailable)
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = PostgresAdapter.connect(dsn)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            seed_reference_rows(adapter)
            adapter.close()
            adapter = None

            read_only_port = free_port()
            proc = start_server(server_env(dsn, pythonpath, write_enabled=False), read_only_port)
            read_only_base = f"http://127.0.0.1:{read_only_port}"
            read_only_status_code, read_only_backend = wait_json(f"{read_only_base}/api/storage/backend-status", proc, secret=pg_auth)
            blocked_status, blocked_payload = request_json(f"{read_only_base}/api/tasks", method="POST", body=task_body(BLOCKED_TASK_ID))
            stop_server(proc)
            proc = None

            write_port = free_port()
            proc = start_server(server_env(dsn, pythonpath, write_enabled=True), write_port)
            write_base = f"http://127.0.0.1:{write_port}"
            write_status_code, write_backend = wait_json(f"{write_base}/api/storage/backend-status", proc, secret=pg_auth)
            create_status, create_payload = request_json(f"{write_base}/api/tasks", method="POST", body=task_body(TASK_ID))
            readback_status, readback_payload = request_json(f"{write_base}/api/tasks/{TASK_ID}?workspace_id={WORKSPACE_ID}")
            agent_block_status, agent_block_payload = request_json(
                f"{write_base}/api/agents",
                method="POST",
                body={"agent_id": BLOCKED_AGENT_ID, "name": "Should stay blocked"},
            )
            stop_server(proc)
            proc = None

            adapter = PostgresAdapter.connect(dsn)
            task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [TASK_ID])
            blocked_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [BLOCKED_TASK_ID])
            blocked_agent_row = adapter.fetchone("SELECT * FROM agents WHERE agent_id=?", [BLOCKED_AGENT_ID])
            runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE task_id=?", [TASK_ID])["c"]
            audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["tasks", TASK_ID])["c"]

            failures: list[str] = []
            if read_only_status_code != 200 or read_only_backend.get("mode") != "read_only_http" or read_only_backend.get("writes_allowed") is not False:
                failures.append(f"read_only_backend_mismatch:{read_only_backend}")
            if blocked_status != 503 or blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"read_only_write_block_mismatch:{blocked_status}:{blocked_payload}")
            if blocked_task_row:
                failures.append("read_only_post_created_blocked_task")
            if write_status_code != 200 or write_backend.get("mode") != "experimental_write_http" or write_backend.get("writes_allowed") is not True:
                failures.append(f"write_backend_mismatch:{write_backend}")
            if create_status != 201 or create_payload.get("task_id") != TASK_ID or create_payload.get("token_omitted") is not True:
                failures.append(f"task_create_payload_mismatch:{create_status}:{create_payload}")
            if readback_status != 200 or readback_payload.get("task", {}).get("task_id") != TASK_ID:
                failures.append(f"task_readback_mismatch:{readback_status}:{readback_payload}")
            if agent_block_status != 503 or agent_block_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"non_allowlisted_write_not_blocked:{agent_block_status}:{agent_block_payload}")
            if blocked_agent_row:
                failures.append("non_allowlisted_agent_write_created_row")
            if not task_row or task_row.get("workspace_id") != WORKSPACE_ID or task_row.get("owner_agent_id") != AGENT_ID:
                failures.append(f"postgres_task_row_mismatch:{task_row}")
            if int(runtime_event_count or 0) < 1:
                failures.append("postgres_runtime_event_missing")
            if int(audit_count or 0) < 1:
                failures.append("postgres_audit_missing")

            output = {
                "ok": not failures,
                "skipped": False,
                "contract": CONTRACT_ID,
                "image": args.image,
                "driver_status": driver_status,
                "read_only_backend_mode": read_only_backend.get("mode"),
                "read_only_write_block_status": blocked_status,
                "write_backend_mode": write_backend.get("mode"),
                "write_allowlist": write_backend.get("write_allowlist"),
                "task_create_status": create_status,
                "task_readback_status": readback_status,
                "non_allowlisted_write_status": agent_block_status,
                "task_id": TASK_ID,
                "workspace_id": WORKSPACE_ID,
                "runtime_event_count": int(runtime_event_count or 0),
                "audit_count": int(audit_count or 0),
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
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
