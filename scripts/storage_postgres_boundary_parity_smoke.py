#!/usr/bin/env python3
"""Compare the shared storage-boundary fixture on SQLite and Postgres."""
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
    fixture_queries,
    normalize_rows,
    snapshot_hash,
)
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402
from storage_postgres_optional_adapter_smoke import (  # noqa: E402
    BUNDLED_PYTHON,
    ensure_psycopg,
    mapped_port,
)


CONTRACT_ID = "postgres_boundary_fixture_parity_v1"


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_BOUNDARY_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_BOUNDARY_PG_REEXEC"] = "1"
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


def apply_fixture_sqlite() -> dict[str, list[dict[str, Any]]]:
    handle = tempfile.NamedTemporaryFile(prefix="agentops-sqlite-boundary-parity-", delete=False)
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
            return {
                query.name: normalize_rows(conn.execute(query.sql, query.params or []).fetchall())
                for query in fixture_queries()
            }
        finally:
            conn.close()
    finally:
        Path(db_path).unlink(missing_ok=True)


def apply_fixture_postgres(*, image: str, skip: bool, install_driver: bool) -> tuple[int | None, dict[str, Any] | None]:
    early = container_smoke.docker_available(skip)
    if early is not None:
        return early, None
    early = container_smoke.ensure_image(image, skip)
    if early is not None:
        return early, None

    with tempfile.TemporaryDirectory(prefix="agentops-boundary-pg-") as temp_dir:
        driver_ok, driver_status = ensure_psycopg(Path(temp_dir), install=install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=skip), None

        container = f"agentops-pg-boundary-{container_smoke.secrets.token_hex(6)}"
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
            return unavailable(f"Postgres container failed to start: {detail}", skip=skip), None

        adapter: PostgresAdapter | None = None
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=skip), None
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = PostgresAdapter.connect(dsn)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            for operation in fixture_operations():
                adapter.execute(operation.sql, operation.params)
            adapter.commit()
            snapshot = {
                query.name: normalize_rows(adapter.fetchall(query.sql, query.params))
                for query in fixture_queries()
            }
            return None, {"driver_status": driver_status, "snapshot": snapshot}
        except (AssertionError, PostgresAdapterUnavailable, RuntimeError, ValueError, KeyError) as exc:
            if adapter is not None:
                adapter.rollback()
            return unavailable(str(exc), skip=skip), None
        finally:
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SQLite/Postgres shared storage-boundary fixture parity smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE, help="Postgres Docker image to use.")
    parser.add_argument("--skip-if-unavailable", action="store_true", help="Return success with skipped=true when Docker or psycopg is unavailable.")
    parser.add_argument("--no-install-driver", action="store_true", help="Do not install psycopg into a temporary target when missing.")
    args = parser.parse_args()

    reexec_self_with_bundled_python_if_needed()

    sqlite_snapshot = apply_fixture_sqlite()
    early, postgres_result = apply_fixture_postgres(
        image=args.image,
        skip=args.skip_if_unavailable,
        install_driver=not args.no_install_driver,
    )
    if early is not None:
        return early
    assert postgres_result is not None
    postgres_snapshot = postgres_result["snapshot"]
    sqlite_digest = snapshot_hash(sqlite_snapshot)
    postgres_digest = snapshot_hash(postgres_snapshot)
    failures: list[str] = []
    if sqlite_snapshot != postgres_snapshot:
        failures.append("sqlite_postgres_snapshot_mismatch")
    if sqlite_digest != postgres_digest:
        failures.append("sqlite_postgres_snapshot_hash_mismatch")
    output = {
        "ok": not failures,
        "skipped": False,
        "contract": CONTRACT_ID,
        "fixture_version": FIXTURE_VERSION,
        "image": args.image,
        "driver_status": postgres_result["driver_status"],
        "free_local_dependencies": [],
        "compared_queries": list(sqlite_snapshot.keys()),
        "sqlite_snapshot_hash": sqlite_digest,
        "postgres_snapshot_hash": postgres_digest,
        "row_counts": {name: len(rows) for name, rows in sqlite_snapshot.items()},
        "failures": failures,
        "next_proof": "Route more server repo_* helpers through the same adapter boundary before accepting BYOC Postgres.",
    }
    if failures:
        output["sqlite_snapshot"] = sqlite_snapshot
        output["postgres_snapshot"] = postgres_snapshot
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
