#!/usr/bin/env python3
"""Verify shared/production mode protects browser/local write APIs."""

from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, method: str, path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    req = Request(base_url.rstrip("/") + path, data=data, headers=req_headers, method=method)
    try:
        with urlopen(req, timeout=45) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def wait_ready(base_url: str, proc: subprocess.Popen[str], admin_key: str) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _payload = http_json(base_url, "GET", "/api/security/production-readiness", headers={"X-AgentOps-Admin-Key": admin_key})
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def count_rows(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
    finally:
        conn.close()


def leaked(text: str, secrets: list[str]) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS) or any(secret and secret in text for secret in secrets)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    admin_key = "local_admin_guard_key"
    gateway_key = "local_gateway_guard_key"
    with tempfile.TemporaryDirectory(prefix="agentops-shared-write-guard-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_CONFIG"] = str(tmpdir / "config.json")
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_DEPLOYMENT_MODE"] = "production"
        env["AGENTOPS_API_KEY"] = gateway_key
        env["AGENTOPS_ADMIN_KEY"] = admin_key
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc, admin_key)
            before_tasks = count_rows(db_path, "tasks")
            status, blocked_task = http_json(base_url, "POST", "/api/tasks", {"title": "Blocked production UI write"})
            outputs.append(json.dumps(blocked_task, ensure_ascii=False))
            require(status == 401, f"unauthenticated local task write should be 401: {status} {blocked_task}", failures)
            require(blocked_task.get("error") == "local_ui_write_admin_auth_required", f"wrong blocked error: {blocked_task}", failures)
            require(count_rows(db_path, "tasks") == before_tasks, "blocked local task write changed task count", failures)

            status, created_task = http_json(
                base_url,
                "POST",
                "/api/tasks",
                {"task_id": "tsk_shared_guard_admin", "title": "Authorized production UI write", "owner_agent_id": "agt_research"},
                headers={"X-AgentOps-Admin-Key": admin_key},
            )
            outputs.append(json.dumps(created_task, ensure_ascii=False))
            require(status == 201, f"admin local task write should succeed: {status} {created_task}", failures)
            require(created_task.get("task_id") == "tsk_shared_guard_admin", f"wrong admin task payload: {created_task}", failures)

            status, blocked_patch = http_json(
                base_url,
                "PATCH",
                "/api/tasks/tsk_shared_guard_admin/status",
                {"status": "completed"},
            )
            outputs.append(json.dumps(blocked_patch, ensure_ascii=False))
            require(status == 401, f"unauthenticated local patch should be 401: {status} {blocked_patch}", failures)

            status, patched = http_json(
                base_url,
                "PATCH",
                "/api/tasks/tsk_shared_guard_admin/status",
                {"status": "completed"},
                headers={"X-AgentOps-Admin-Key": admin_key},
            )
            outputs.append(json.dumps(patched, ensure_ascii=False))
            require(status == 200, f"admin local patch should succeed: {status} {patched}", failures)
            require(patched.get("status") == "completed", f"wrong patched payload: {patched}", failures)

            status, gateway_task = http_json(
                base_url,
                "POST",
                "/api/agent-gateway/tasks",
                {"task_id": "tsk_shared_guard_gateway", "title": "Gateway write remains scoped", "owner_agent_id": "agt_research"},
                headers={"Authorization": f"Bearer {gateway_key}", "X-AgentOps-Agent-Id": "agt_research"},
            )
            outputs.append(json.dumps(gateway_task, ensure_ascii=False))
            require(status == 201, f"gateway task write should still succeed: {status} {gateway_task}", failures)
            require(gateway_task.get("task_id") == "tsk_shared_guard_gateway", f"wrong gateway task payload: {gateway_task}", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])
    secret_leaked = leaked("\n".join(outputs), [admin_key, gateway_key])
    require(not secret_leaked, "shared-mode local write guard leaked secret-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "shared_mode_local_write_guard_smoke",
        "secret_leaked": secret_leaked,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
