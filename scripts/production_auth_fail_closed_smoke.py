#!/usr/bin/env python3
"""Verify production mode fails closed without admin/API credentials."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SECRET_MARKERS = ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_", "AGENTOPS_API_KEY="]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def db_dump_hash(path: str | None) -> str | None:
    if not path:
        return None
    db_path = Path(path).expanduser().resolve()
    if not db_path.exists():
        return None
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        dumped = "\n".join(conn.iterdump())
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


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


def start_production_fail_closed_server(db_path: Path, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_DEPLOYMENT_MODE"] = "production"
    env.pop("AGENTOPS_API_KEY", None)
    env.pop("AGENTOPS_ADMIN_KEY", None)
    env.pop("AGENTOPS_REQUIRE_PRODUCTION_SECURITY", None)
    return subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout_sec: int = 25) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=1)
            raise RuntimeError(f"server exited early: rc={proc.returncode} stdout={out} stderr={err}")
        try:
            status, payload = request_json("GET", base_url, "/api/security/production-readiness")
            if status == 200 and payload.get("provider") == "agentops-security":
                return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def request_json(method: str, base_url: str, path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"error": exc.reason, "raw": raw}
        return exc.code, body


def assert_unauthorized(label: str, status: int, payload: dict) -> None:
    require(status == 401, f"{label} should be 401 in production mode without credentials: {status} {payload}")
    require(payload.get("error") == "unauthorized", f"{label} wrong error payload: {payload}")


def run_fail_closed_checks(base_url: str, admin_key: str = "") -> dict:
    outputs: list[str] = []
    status, readiness = request_json("GET", base_url, "/api/security/production-readiness")
    outputs.append(json.dumps(readiness, ensure_ascii=False, sort_keys=True))
    require(status == 200, f"readiness failed: {status} {readiness}")
    require(readiness.get("production_requested") is True, f"server is not in production-requested mode: {readiness}")
    require(readiness.get("status") == "blocked", f"production readiness should be blocked without API/admin keys: {readiness}")
    require(readiness.get("production_ready") is False, f"production_ready should be false: {readiness}")
    require(readiness.get("auth_mode") == "unauthorized", f"auth mode should report unauthorized: {readiness}")

    checks = [
        ("GET enrollments", "GET", "/api/agent-gateway/enrollments", None),
        ("GET sessions", "GET", "/api/agent-gateway/sessions", None),
        ("POST enrollment create", "POST", "/api/agent-gateway/enrollment/create", {
            "agent_id": "agt_prod_fail_closed",
            "name": "Production Fail Closed",
            "runtime_type": "mock",
            "workspace_id": "local-demo",
            "scopes": ["tasks:read"],
        }),
        ("POST enrollment revoke", "POST", "/api/agent-gateway/enrollment/revoke", {"agent_id": "agt_prod_fail_closed"}),
        ("POST session revoke", "POST", "/api/agent-gateway/session/revoke", {"agent_id": "agt_prod_fail_closed"}),
        ("GET task pull", "GET", "/api/agent-gateway/tasks/pull", None),
        ("POST task create", "POST", "/api/agent-gateway/tasks", {
            "title": "Production unauthorized task",
            "owner_agent_id": "agt_prod_fail_closed",
            "acceptance_criteria": "Should not be created.",
        }),
    ]
    for label, method, path, payload in checks:
        item_status, item_payload = request_json(method, base_url, path, payload)
        outputs.append(json.dumps(item_payload, ensure_ascii=False, sort_keys=True))
        assert_unauthorized(label, item_status, item_payload)

    admin_list_status = None
    if admin_key:
        admin_list_status, admin_payload = request_json(
            "GET",
            base_url,
            "/api/agent-gateway/enrollments",
            headers={"X-AgentOps-Admin-Key": admin_key},
        )
        outputs.append(json.dumps(admin_payload, ensure_ascii=False, sort_keys=True))
        require(admin_list_status == 200, f"admin-key enrollment list should pass: {admin_list_status} {admin_payload}")
        require(admin_payload.get("valid_scopes"), f"admin-key list should include valid scopes: {admin_payload}")

    return {
        "outputs": outputs,
        "production_requested": readiness.get("production_requested"),
        "readiness_status": readiness.get("status"),
        "auth_mode": readiness.get("auth_mode"),
        "unauthorized_checks": len(checks),
        "admin_key_list_status": admin_list_status,
    }


def run_configured_production_fixture() -> dict:
    proc: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="agentops-production-auth-fail-closed-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops.db"
        prepare_minimal_sqlite_db(db_path)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        proc = start_production_fail_closed_server(db_path, port)
        try:
            wait_ready(base_url, proc)
            before_hash = db_dump_hash(str(db_path))
            result = run_fail_closed_checks(base_url)
            after_hash = db_dump_hash(str(db_path))
            require(before_hash == after_hash, "configured production fail-closed checks mutated the SQLite ledger")
            require(not leaked_secret("\n".join(result["outputs"])), "configured production auth smoke leaked token-like material")
            return {
                "readiness_status": result["readiness_status"],
                "auth_mode": result["auth_mode"],
                "unauthorized_checks": result["unauthorized_checks"],
                "read_only_hash_checked": True,
            }
        finally:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify production auth fail-closed behavior.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--admin-key", default=os.environ.get("AGENTOPS_ADMIN_KEY", ""))
    parser.add_argument("--configured-production-fixture", action="store_true", help="Start an isolated production-mode server without API/admin keys and verify fail-closed auth.")
    args = parser.parse_args()
    try:
        result = run_fail_closed_checks(args.base_url, args.admin_key) if not args.configured_production_fixture else {}
        configured = run_configured_production_fixture() if args.configured_production_fixture else None
        require(not leaked_secret("\n".join(result.get("outputs") or [])), "production auth smoke leaked token-like material")
        print(json.dumps({
            "ok": True,
            "production_requested": result.get("production_requested"),
            "readiness_status": result.get("readiness_status"),
            "auth_mode": result.get("auth_mode"),
            "unauthorized_checks": result.get("unauthorized_checks"),
            "admin_key_list_status": result.get("admin_key_list_status"),
            "configured_production_fixture": configured,
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
