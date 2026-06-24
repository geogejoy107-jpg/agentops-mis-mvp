#!/usr/bin/env python3
"""Verify storage backend selection is explicit and fail-closed."""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


CONTRACT_ID = "storage_backend_selection_fail_closed_v1"


def run_server_reset(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "server.py", "--reset"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_sqlite_server(env: dict[str, str], port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def wait_json(url: str, proc: subprocess.Popen[str], timeout_sec: int = 20) -> dict:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=1)
            raise RuntimeError(f"server exited early: rc={proc.returncode} stdout={out} stderr={err}")
        try:
            with urlopen(url, timeout=2) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"server did not return JSON before timeout: {last_error}")


def prepare_minimal_sqlite_db(path: Path) -> None:
    import server  # noqa: PLC0415

    conn = sqlite3.connect(path)
    try:
        conn.executescript(server.SCHEMA_SQL)
        conn.execute(
            "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
            ("usr_storage_smoke", "Storage Smoke", "storage-smoke@example.local", "admin", "2026-06-22T00:00:00+00:00"),
        )
        conn.execute(
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "agt_storage_smoke",
                "Storage Smoke Agent",
                "operator",
                "Prevents server seed/export drift during backend selection smoke.",
                "mock",
                "mock",
                "mock-model",
                "idle",
                "standard",
                "[]",
                0,
                "usr_storage_smoke",
                "2026-06-22T00:00:00+00:00",
                "2026-06-22T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    import server  # noqa: PLC0415

    failures: list[str] = []
    default_status = server.storage_backend_status(None)
    if default_status.get("status") != "active" or default_status.get("active_backend") != "sqlite":
        failures.append(f"default_sqlite_not_active:{default_status}")
    if default_status.get("fallback_performed") is not False:
        failures.append("default_sqlite_fallback_flag_not_false")
    default_runtime_gate = default_status.get("runtime_write_gate") or {}
    if default_runtime_gate.get("status") != "not_selected":
        failures.append(f"default_runtime_write_gate_status:{default_runtime_gate}")
    if "postgres_http_runtime_prepared_action_write_v1" not in set(default_runtime_gate.get("contracts") or []):
        failures.append("default_runtime_prepared_action_contract_missing")
    if "postgres_http_runtime_approval_decision_write_v1" not in set(default_runtime_gate.get("contracts") or []):
        failures.append("default_runtime_approval_decision_contract_missing")
    if default_runtime_gate.get("exact_resume_required") is not True:
        failures.append("default_runtime_exact_resume_proof_missing")
    if default_runtime_gate.get("approval_decision") != "row_gated_prepared_action_only":
        failures.append("default_runtime_approval_row_gate_missing")
    if default_runtime_gate.get("non_fixed_runtime_writes") != "blocked":
        failures.append("default_runtime_non_fixed_block_missing")
    if default_runtime_gate.get("live_execution_performed") is not False:
        failures.append("default_runtime_live_execution_flag_not_false")

    with tempfile.TemporaryDirectory(prefix="agentops-storage-backend-") as temp_dir:
        db_path = Path(temp_dir) / "should_not_exist.db"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_STORAGE_BACKEND"] = "postgres"
        env.pop("AGENTOPS_EDITION", None)
        env.pop("AGENTOPS_POSTGRES_DSN", None)
        env.pop("DATABASE_URL", None)
        env.pop("AGENTOPS_ENABLE_POSTGRES_STORAGE", None)
        blocked = run_server_reset(env)
        if blocked.returncode != 2:
            failures.append(f"postgres_without_entitlement_returncode={blocked.returncode}")
        if db_path.exists():
            failures.append("postgres_block_created_sqlite_db")
        if "entitlement_required" not in blocked.stderr:
            failures.append("postgres_without_entitlement_missing_reason")

        env["AGENTOPS_EDITION"] = "enterprise_byoc"
        missing_dsn = run_server_reset(env)
        if missing_dsn.returncode != 2:
            failures.append(f"postgres_without_dsn_returncode={missing_dsn.returncode}")
        if "missing_postgres_dsn" not in missing_dsn.stderr:
            failures.append("postgres_without_dsn_missing_reason")

        env["AGENTOPS_POSTGRES_DSN"] = "postgresql://agentops:example@127.0.0.1:15432/agentops"
        no_flag = run_server_reset(env)
        if no_flag.returncode != 2:
            failures.append(f"postgres_without_enable_flag_returncode={no_flag.returncode}")
        if "postgres_storage_flag_required" not in no_flag.stderr:
            failures.append("postgres_without_enable_flag_missing_reason")
        if db_path.exists():
            failures.append("blocked_postgres_selection_created_sqlite_db")

        env["AGENTOPS_ENABLE_POSTGRES_STORAGE"] = "1"
        no_read_only_http = run_server_reset(env)
        if no_read_only_http.returncode != 2:
            failures.append(f"postgres_without_read_only_http_flag_returncode={no_read_only_http.returncode}")
        if "postgres_read_only_http_flag_required" not in no_read_only_http.stderr:
            failures.append("postgres_without_read_only_http_flag_missing_reason")
        if db_path.exists():
            failures.append("blocked_postgres_read_only_selection_created_sqlite_db")

        sqlite_env = os.environ.copy()
        sqlite_env["AGENTOPS_DB_PATH"] = str(Path(temp_dir) / "sqlite-active.db")
        sqlite_env.pop("AGENTOPS_STORAGE_BACKEND", None)
        prepare_minimal_sqlite_db(Path(sqlite_env["AGENTOPS_DB_PATH"]))
        port = free_port()
        proc = start_sqlite_server(sqlite_env, port)
        try:
            api_status = wait_json(f"http://127.0.0.1:{port}/api/storage/backend-status", proc)
            if api_status.get("status") != "active" or api_status.get("active_backend") != "sqlite":
                failures.append(f"http_sqlite_backend_status_mismatch:{api_status}")
            if api_status.get("fallback_performed") is not False:
                failures.append("http_sqlite_fallback_flag_not_false")
        finally:
            proc.terminate()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)

    output = {
        "ok": not failures,
        "contract": CONTRACT_ID,
        "default_backend": default_status.get("active_backend"),
        "postgres_selection": "fail_closed",
        "fallback_performed": False,
        "token_omitted": True,
        "failures": failures,
        "next_proof": "Run selected HTTP/CLI requests against a temporary Postgres backend, then widen routed helper coverage.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
