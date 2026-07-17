#!/usr/bin/env python3
"""Shared helper for smoke tests that need an isolated MIS server."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def prepare_minimal_sqlite_db(path: Path) -> None:
    sys.path.insert(0, str(ROOT))
    import server  # noqa: PLC0415

    with sqlite3.connect(path) as conn:
        conn.executescript(server.SCHEMA_SQL)
        conn.commit()


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout_sec: int = 25) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=1)
            raise RuntimeError(f"server exited early: rc={proc.returncode} stdout={out} stderr={err}")
        try:
            req = urllib.request.Request(base_url.rstrip("/") + "/api/local/readiness", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


@contextmanager
def isolated_server(prefix: str):
    proc: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops.db"
        runtime_dir = tmp_path / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        prepare_minimal_sqlite_db(db_path)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_RUNTIME_DIR"] = str(runtime_dir)
        env["AGENTOPS_DEPLOYMENT_MODE"] = "local"
        env["AGENTOPS_STORAGE_BACKEND"] = "sqlite"
        env.pop("AGENTOPS_API_KEY", None)
        env.pop("AGENTOPS_ADMIN_KEY", None)
        env.pop("AGENTOPS_WORKSPACE_ADMIN_KEYS_JSON", None)
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            wait_ready(base_url, proc)
            yield {"base_url": base_url, "db_path": str(db_path), "runtime_dir": str(runtime_dir)}
        finally:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
