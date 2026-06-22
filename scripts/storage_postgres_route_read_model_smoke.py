#!/usr/bin/env python3
"""Compare route-shaped read models on SQLite and Postgres.

This is still a storage-boundary smoke, not a second HTTP server. It mirrors the
read shapes used by the current Python routes so a future Postgres-backed server
adapter has a locked response contract to match.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.parity_fixture import (  # noqa: E402
    FIXTURE_VERSION,
    fixture_operations,
    normalize_rows,
    snapshot_hash,
)
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402


CONTRACT_ID = "postgres_route_read_model_parity_v1"
WORKSPACE_A = "ws_parity_a"
TASK_A = "tsk_parity_a"
TASK_B = "tsk_parity_b"
RUN_A = "run_parity_a"
JOB_A = "wfjob_parity_a"


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_ROUTE_MODEL_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_ROUTE_MODEL_PG_REEXEC"] = "1"
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


class Store:
    def __init__(self, sqlite_conn: sqlite3.Connection | None = None, postgres_adapter: PostgresAdapter | None = None):
        self.sqlite_conn = sqlite_conn
        self.postgres_adapter = postgres_adapter

    def fetchall(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        if self.sqlite_conn is not None:
            return normalize_rows(self.sqlite_conn.execute(sql, params or []).fetchall())
        assert self.postgres_adapter is not None
        return normalize_rows(self.postgres_adapter.fetchall(sql, params or []))

    def fetchone(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> dict[str, Any] | None:
        rows = self.fetchall(sql, params)
        return rows[0] if rows else None


def route_read_model_snapshot(store: Store) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    payloads["GET /api/tasks"] = store.fetchall(
        "SELECT * FROM tasks WHERE COALESCE(workspace_id,'local-demo')=? ORDER BY created_at DESC",
        [WORKSPACE_A],
    )
    task = store.fetchone(
        "SELECT * FROM tasks WHERE task_id=? AND COALESCE(workspace_id,'local-demo')=?",
        [TASK_A, WORKSPACE_A],
    )
    payloads["GET /api/tasks/:task_id"] = {
        "task": task,
        "runs": store.fetchall("SELECT * FROM runs WHERE task_id=? ORDER BY created_at DESC", [TASK_A]),
        "approvals": store.fetchall("SELECT * FROM approvals WHERE task_id=? ORDER BY created_at DESC", [TASK_A]),
        "evaluations": store.fetchall("SELECT * FROM evaluations WHERE task_id=? ORDER BY created_at DESC", [TASK_A]),
        "memories": store.fetchall("SELECT * FROM memories WHERE task_id=? ORDER BY created_at DESC", [TASK_A]),
        "artifacts": store.fetchall("SELECT * FROM artifacts WHERE task_id=? ORDER BY created_at DESC", [TASK_A]),
    }
    payloads["GET /api/tasks/:other_workspace_task"] = server.workspace_hidden("task", TASK_B)
    payloads["GET /api/runs"] = store.fetchall(
        "SELECT * FROM runs WHERE COALESCE(workspace_id,'local-demo')=? ORDER BY created_at DESC",
        [WORKSPACE_A],
    )
    run = store.fetchone(
        "SELECT * FROM runs WHERE run_id=? AND COALESCE(workspace_id,'local-demo')=?",
        [RUN_A, WORKSPACE_A],
    )
    payloads["GET /api/runs/:run_id"] = {
        "run": run,
        "tool_calls": store.fetchall("SELECT * FROM tool_calls WHERE run_id=? ORDER BY created_at", [RUN_A]),
        "approvals": store.fetchall("SELECT * FROM approvals WHERE run_id=? ORDER BY created_at", [RUN_A]),
        "evaluations": store.fetchall("SELECT * FROM evaluations WHERE run_id=? ORDER BY created_at", [RUN_A]),
        "artifacts": store.fetchall("SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at", [RUN_A]),
    }
    payloads["GET /api/runs/:run_id/graph"] = {
        "run": run,
        "parent": None,
        "children": store.fetchall("SELECT * FROM runs WHERE parent_run_id=? ORDER BY created_at", [RUN_A]),
        "siblings_by_delegation": [],
    }
    payloads["GET /api/tool-calls"] = store.fetchall(
        """SELECT tc.* FROM tool_calls tc
        JOIN runs r ON r.run_id=tc.run_id
        WHERE COALESCE(r.workspace_id,'local-demo')=?
        ORDER BY tc.created_at DESC""",
        [WORKSPACE_A],
    )
    payloads["GET /api/approvals"] = store.fetchall(
        """SELECT ap.* FROM approvals ap
        LEFT JOIN tasks t ON t.task_id=ap.task_id
        LEFT JOIN runs r ON r.run_id=ap.run_id
        WHERE COALESCE(t.workspace_id,r.workspace_id,'local-demo')=?
        ORDER BY ap.created_at DESC""",
        [WORKSPACE_A],
    )
    payloads["GET /api/memories"] = store.fetchall(
        "SELECT * FROM memories WHERE COALESCE(workspace_id,'local-demo')=? ORDER BY created_at DESC",
        [WORKSPACE_A],
    )
    payloads["GET /api/evaluations"] = store.fetchall(
        """SELECT ev.* FROM evaluations ev
        LEFT JOIN tasks t ON t.task_id=ev.task_id
        LEFT JOIN runs r ON r.run_id=ev.run_id
        WHERE COALESCE(t.workspace_id,r.workspace_id,'local-demo')=?
        ORDER BY ev.created_at DESC""",
        [WORKSPACE_A],
    )
    payloads["GET /api/artifacts"] = store.fetchall(
        """SELECT art.* FROM artifacts art
        LEFT JOIN tasks t ON t.task_id=art.task_id
        LEFT JOIN runs r ON r.run_id=art.run_id
        WHERE COALESCE(t.workspace_id,r.workspace_id,'local-demo')=?
        ORDER BY art.created_at DESC""",
        [WORKSPACE_A],
    )
    payloads["GET /api/audit"] = store.fetchall(
        """SELECT a.* FROM audit_logs a
        WHERE
          (a.entity_type='tasks' AND EXISTS (
            SELECT 1 FROM tasks t WHERE t.task_id=a.entity_id AND COALESCE(t.workspace_id,'local-demo')=?
          ))
          OR (a.entity_type='runs' AND EXISTS (
            SELECT 1 FROM runs r WHERE r.run_id=a.entity_id AND COALESCE(r.workspace_id,'local-demo')=?
          ))
          OR (a.entity_type='workflow_jobs' AND EXISTS (
            SELECT 1 FROM workflow_jobs j WHERE j.job_id=a.entity_id AND COALESCE(j.workspace_id,'local-demo')=?
          ))
          OR a.metadata_json LIKE ?
        ORDER BY a.created_at DESC LIMIT ?""",
        [WORKSPACE_A, WORKSPACE_A, WORKSPACE_A, f'%"workspace_id": "{WORKSPACE_A}"%', 200],
    )
    job_rows = store.fetchall(
        "SELECT * FROM workflow_jobs WHERE COALESCE(workspace_id,'local-demo')=? ORDER BY created_at DESC LIMIT ?",
        [WORKSPACE_A, 50],
    )
    payloads["GET /api/workflows/jobs"] = {
        "jobs": [server.workflow_job_public(row) for row in job_rows],
        "workspace_id": WORKSPACE_A,
        "token_omitted": True,
    }
    job = store.fetchone(
        "SELECT * FROM workflow_jobs WHERE job_id=? AND COALESCE(workspace_id,'local-demo')=?",
        [JOB_A, WORKSPACE_A],
    )
    payloads["GET /api/workflows/jobs/:job_id"] = {
        "job": server.workflow_job_public(job),
        "workspace_id": WORKSPACE_A,
        "token_omitted": True,
    }
    return payloads


def sqlite_snapshot() -> dict[str, Any]:
    handle = tempfile.NamedTemporaryFile(prefix="agentops-sqlite-route-model-", delete=False)
    db_path = handle.name
    handle.close()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(server.SCHEMA_SQL)
            server.ensure_schema_migrations(conn)
            for operation in fixture_operations():
                conn.execute(operation.sql, operation.params or [])
            conn.commit()
            return route_read_model_snapshot(Store(sqlite_conn=conn))
        finally:
            conn.close()
    finally:
        Path(db_path).unlink(missing_ok=True)


def postgres_snapshot(*, image: str, skip: bool, install_driver: bool) -> tuple[int | None, dict[str, Any] | None, str | None]:
    early = container_smoke.docker_available(skip)
    if early is not None:
        return early, None, None
    early = container_smoke.ensure_image(image, skip)
    if early is not None:
        return early, None, None

    with tempfile.TemporaryDirectory(prefix="agentops-route-model-pg-") as temp_dir:
        driver_ok, driver_status = ensure_psycopg(Path(temp_dir), install=install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=skip), None, None

        container = f"agentops-pg-route-model-{container_smoke.secrets.token_hex(6)}"
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
                image,
            ],
            timeout=60,
        )
        if started.returncode != 0:
            detail = (started.stderr or started.stdout or "docker run failed").strip()
            return unavailable(f"Postgres container failed to start: {detail}", skip=skip), None, None

        adapter: PostgresAdapter | None = None
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=skip), None, None
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = PostgresAdapter.connect(dsn)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            for operation in fixture_operations():
                adapter.execute(operation.sql, operation.params)
            adapter.commit()
            return None, route_read_model_snapshot(Store(postgres_adapter=adapter)), driver_status
        except (AssertionError, PostgresAdapterUnavailable, RuntimeError, ValueError, KeyError) as exc:
            if adapter is not None:
                adapter.rollback()
            return unavailable(str(exc), skip=skip), None, None
        finally:
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SQLite/Postgres route read-model parity smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE, help="Postgres Docker image to use.")
    parser.add_argument("--skip-if-unavailable", action="store_true", help="Return success with skipped=true when Docker or psycopg is unavailable.")
    parser.add_argument("--no-install-driver", action="store_true", help="Do not install psycopg into a temporary target when missing.")
    args = parser.parse_args()

    reexec_self_with_bundled_python_if_needed()

    sqlite_payload = sqlite_snapshot()
    early, postgres_payload, driver_status = postgres_snapshot(
        image=args.image,
        skip=args.skip_if_unavailable,
        install_driver=not args.no_install_driver,
    )
    if early is not None:
        return early
    assert postgres_payload is not None
    sqlite_digest = snapshot_hash(sqlite_payload)
    postgres_digest = snapshot_hash(postgres_payload)
    failures: list[str] = []
    if sqlite_payload != postgres_payload:
        failures.append("sqlite_postgres_route_read_model_mismatch")
    if sqlite_digest != postgres_digest:
        failures.append("sqlite_postgres_route_read_model_hash_mismatch")
    output = {
        "ok": not failures,
        "skipped": False,
        "contract": CONTRACT_ID,
        "fixture_version": FIXTURE_VERSION,
        "image": args.image,
        "driver_status": driver_status,
        "free_local_dependencies": [],
        "route_count": len(sqlite_payload),
        "routes": list(sqlite_payload.keys()),
        "sqlite_read_model_hash": sqlite_digest,
        "postgres_read_model_hash": postgres_digest,
        "token_omitted": True,
        "failures": failures,
        "next_proof": "Run selected HTTP/CLI requests against a Postgres-backed adapter once the server can switch storage backends.",
    }
    if failures:
        output["sqlite_payload"] = sqlite_payload
        output["postgres_payload"] = postgres_payload
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
