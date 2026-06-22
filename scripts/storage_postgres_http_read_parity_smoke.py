#!/usr/bin/env python3
"""Run selected HTTP GET routes against a Postgres-backed server adapter."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.parity_fixture import FIXTURE_VERSION, fixture_operations, snapshot_hash  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402
from storage_postgres_route_read_model_smoke import (  # noqa: E402
    JOB_A,
    RUN_A,
    TASK_A,
    TASK_B,
    WORKSPACE_A,
    Store,
    route_read_model_snapshot,
)


CONTRACT_ID = "postgres_http_read_parity_v1"

HTTP_ROUTES = [
    ("GET /api/tasks", f"/api/tasks?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/tasks/:task_id", f"/api/tasks/{TASK_A}?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/tasks/:other_workspace_task", f"/api/tasks/{TASK_B}?{urlencode({'workspace_id': WORKSPACE_A})}", 404),
    ("GET /api/runs", f"/api/runs?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/runs/:run_id", f"/api/runs/{RUN_A}?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/runs/:run_id/graph", f"/api/runs/{RUN_A}/graph?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/tool-calls", f"/api/tool-calls?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/approvals", f"/api/approvals?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/memories", f"/api/memories?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/evaluations", f"/api/evaluations?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/artifacts", f"/api/artifacts?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/audit", f"/api/audit?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/workflows/jobs", f"/api/workflows/jobs?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
    ("GET /api/workflows/jobs/:job_id", f"/api/workflows/jobs/{JOB_A}?{urlencode({'workspace_id': WORKSPACE_A})}", 200),
]


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_HTTP_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_HTTP_PG_REEXEC"] = "1"
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


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def redact(value: str, secret: str) -> str:
    if not value:
        return value
    return value.replace(secret, "[REDACTED]")


def connect_postgres_when_ready(dsn: str, *, secret: str, timeout_sec: int = 30) -> PostgresAdapter:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        try:
            return PostgresAdapter.connect(dsn)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(redact(f"postgres host connection did not become ready before timeout: {last_error}", secret))


def wait_json(url: str, proc: subprocess.Popen[str], *, secret: str, timeout_sec: int = 30) -> tuple[int, dict]:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=1)
            detail = f"server exited early rc={proc.returncode} stdout={out} stderr={err}"
            raise RuntimeError(redact(detail, secret))
        try:
            return request_json(url)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(redact(f"server did not return JSON before timeout: {last_error}", secret))


def request_json(url: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=5) as res:
            return int(res.status), json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def start_server(env: dict[str, str], port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def postgres_http_snapshot(base_url: str) -> tuple[dict, list[str]]:
    failures: list[str] = []
    payloads: dict = {}
    for key, route, expected_status in HTTP_ROUTES:
        status, payload = request_json(f"{base_url}{route}")
        if status != expected_status:
            failures.append(f"{key}_status_{status}_expected_{expected_status}")
        payloads[key] = payload
    return payloads, failures


def canonical_numeric_payload(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: canonical_numeric_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [canonical_numeric_payload(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Postgres-backed server HTTP read parity smoke.")
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

    with tempfile.TemporaryDirectory(prefix="agentops-http-pg-") as temp_dir:
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

        container = f"agentops-pg-http-read-{container_smoke.secrets.token_hex(6)}"
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
            return unavailable(redact((started.stderr or started.stdout or "docker run failed").strip(), pg_auth), skip=args.skip_if_unavailable)

        adapter: PostgresAdapter | None = None
        proc: subprocess.Popen[str] | None = None
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=args.skip_if_unavailable)
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = connect_postgres_when_ready(dsn, secret=pg_auth)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            for operation in fixture_operations():
                adapter.execute(operation.sql, operation.params)
            adapter.commit()
            expected_payload = server.json_safe(route_read_model_snapshot(Store(postgres_adapter=adapter)))
            adapter.close()
            adapter = None

            http_port = free_port()
            env = os.environ.copy()
            env.update(
                {
                    "AGENTOPS_STORAGE_BACKEND": "postgres",
                    "AGENTOPS_EDITION": "enterprise_byoc",
                    "AGENTOPS_POSTGRES_DSN": dsn,
                    "AGENTOPS_ENABLE_POSTGRES_STORAGE": "1",
                    "AGENTOPS_POSTGRES_READ_ONLY_HTTP": "1",
                    "PYTHONPATH": os.pathsep.join(pythonpath_parts),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            env.pop("AGENTOPS_DB_PATH", None)
            proc = start_server(env, http_port)
            base_url = f"http://127.0.0.1:{http_port}"
            status_code, backend_status = wait_json(f"{base_url}/api/storage/backend-status", proc, secret=pg_auth)
            failures: list[str] = []
            if status_code != 200:
                failures.append(f"backend_status_http_{status_code}")
            if backend_status.get("status") != "active" or backend_status.get("active_backend") != "postgres":
                failures.append(f"postgres_backend_not_active:{backend_status}")
            if backend_status.get("fallback_performed") is not False:
                failures.append("postgres_backend_fallback_flag_not_false")
            if backend_status.get("mode") != "read_only_http":
                failures.append(f"postgres_backend_mode_mismatch:{backend_status.get('mode')}")

            actual_payload, route_failures = postgres_http_snapshot(base_url)
            failures.extend(route_failures)
            actual_payload = server.json_safe(actual_payload)
            if actual_payload != expected_payload:
                failures.append("postgres_http_payload_mismatch")
            actual_hash = snapshot_hash(canonical_numeric_payload(actual_payload))
            expected_hash = snapshot_hash(canonical_numeric_payload(expected_payload))
            if actual_hash != expected_hash:
                failures.append("postgres_http_payload_hash_mismatch")

            post_status, post_payload = request_json(
                f"{base_url}/api/tasks",
                method="POST",
                body={"task_id": "tsk_postgres_write_should_block", "title": "Should not write"},
            )
            if post_status != 503:
                failures.append(f"postgres_write_block_status_{post_status}")
            if post_payload.get("error") != "postgres_read_only_backend" or post_payload.get("writes_allowed") is not False:
                failures.append(f"postgres_write_block_payload_mismatch:{post_payload}")

            adapter = connect_postgres_when_ready(dsn, secret=pg_auth)
            leaked_write = adapter.fetchone("SELECT task_id FROM tasks WHERE task_id=?", ["tsk_postgres_write_should_block"])
            if leaked_write:
                failures.append("postgres_read_only_post_created_task")

            output = {
                "ok": not failures,
                "skipped": False,
                "contract": CONTRACT_ID,
                "fixture_version": FIXTURE_VERSION,
                "image": args.image,
                "driver_status": driver_status,
                "route_count": len(HTTP_ROUTES),
                "routes": [key for key, _route, _status in HTTP_ROUTES],
                "postgres_http_read_model_hash": actual_hash,
                "expected_read_model_hash": expected_hash,
                "write_block_status": post_status,
                "backend_mode": backend_status.get("mode"),
                "fallback_performed": False,
                "free_local_dependencies": [],
                "token_omitted": True,
                "failures": failures,
                "next_proof": "Widen Postgres-backed server route coverage or add CLI parity once more write helpers are adapter-safe.",
            }
            if failures:
                output["expected_payload"] = expected_payload
                output["actual_payload"] = actual_payload
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not failures else 1
        except (AssertionError, PostgresAdapterUnavailable, RuntimeError, ValueError, KeyError) as exc:
            if adapter is not None:
                adapter.rollback()
            return unavailable(redact(str(exc), pg_auth), skip=args.skip_if_unavailable)
        finally:
            if proc is not None:
                proc.terminate()
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate(timeout=5)
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
