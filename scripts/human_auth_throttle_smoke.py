#!/usr/bin/env python3
"""Verify source-independent Human Login/Pairing throttling."""
from __future__ import annotations

import http.cookiejar
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


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def browser() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def request_json(opener, url: str, base_url: str, body: dict) -> tuple[int, dict, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Origin": base_url},
    )
    try:
        with opener.open(request, timeout=5) as response:
            return response.status, dict(response.headers), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.loads(exc.read().decode("utf-8"))


def main() -> int:
    failures: list[str] = []
    evidence: dict[str, object] = {}
    raw_values = [
        "fixture-owner-password",
        "wrong-fixture-password",
        "fixture-owner",
        "unknown-pairing-secret-",
    ]
    with tempfile.TemporaryDirectory(prefix="agentops-human-throttle-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({
            "AGENTOPS_DB_PATH": str(db_path),
            "AGENTOPS_SKIP_SEED_EXPORTS": "1",
            "AGENTOPS_DEPLOYMENT_MODE": "private_host",
            "AGENTOPS_HUMAN_AUTH_REQUIRED": "true",
            "AGENTOPS_COOKIE_SECURE": "false",
            "AGENTOPS_OWNER_SETUP_CODE": "fixture-owner-setup",
            "AGENTOPS_ALLOWED_ORIGINS": base_url,
            "AGENTOPS_API_KEY": "fixture-machine-key",
            "AGENTOPS_ADMIN_KEY": "fixture-admin-key",
            "HERMES_ALLOW_REAL_RUN": "false",
        })
        process = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        owner = browser()
        anonymous = urllib.request.build_opener()
        process_output = ""
        try:
            deadline = time.time() + 30
            ready = False
            while time.time() < deadline and process.poll() is None:
                try:
                    with urllib.request.urlopen(base_url + "/health", timeout=2) as response:
                        ready = response.status == 200
                    if ready:
                        break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.2)
            if not ready:
                failures.append("temporary Host did not become ready")
            else:
                status, _headers, payload = request_json(
                    owner,
                    base_url + "/api/human-auth/bootstrap",
                    base_url,
                    {
                        "setup_code": "fixture-owner-setup",
                        "username": "fixture-owner",
                        "display_name": "Fixture Owner",
                        "password": "fixture-owner-password",
                    },
                )
                if status != 201 or payload.get("user", {}).get("role") != "owner":
                    failures.append("owner bootstrap failed")

                for _index in range(7):
                    status, _headers, payload = request_json(
                        owner,
                        base_url + "/api/human-auth/login",
                        base_url,
                        {"username": "fixture-owner", "password": "wrong-fixture-password"},
                    )
                    if status != 401 or payload.get("error") != "invalid_credentials":
                        failures.append("login subject was throttled before its configured threshold")
                        break
                status, _headers, payload = request_json(
                    owner,
                    base_url + "/api/human-auth/login",
                    base_url,
                    {"username": "fixture-owner", "password": "fixture-owner-password"},
                )
                evidence["subject_reset_on_success"] = {"status": status, "authenticated": payload.get("authenticated")}
                if status != 200 or not payload.get("authenticated"):
                    failures.append("successful login did not clear the subject throttle bucket")

                final_login = None
                for _index in range(8):
                    final_login = request_json(
                        owner,
                        base_url + "/api/human-auth/login",
                        base_url,
                        {"username": "fixture-owner", "password": "wrong-fixture-password"},
                    )
                status, headers, payload = final_login
                retry_after = int(headers.get("Retry-After") or 0)
                evidence["login_subject_block"] = {
                    "status": status,
                    "error": payload.get("error"),
                    "retry_after_header": retry_after > 0,
                    "source_identity_omitted": payload.get("source_identity_omitted"),
                }
                if status != 429 or payload.get("error") != "too_many_attempts" or retry_after <= 0:
                    failures.append("login subject threshold did not return bounded 429/Retry-After")

                status, _headers, payload = request_json(
                    owner,
                    base_url + "/api/human-auth/login",
                    base_url,
                    {"username": "fixture-owner", "password": "fixture-owner-password"},
                )
                evidence["correct_password_during_block"] = {"status": status, "error": payload.get("error")}
                if status != 429 or payload.get("error") != "too_many_attempts":
                    failures.append("a correct password bypassed the active throttle block")

                final_pairing = None
                for index in range(60):
                    final_pairing = request_json(
                        anonymous,
                        base_url + "/api/human-auth/pair",
                        base_url,
                        {
                            "pairing_secret": f"unknown-pairing-secret-{index}",
                            "username": "fixture-member",
                            "password": "fixture-member-password",
                        },
                    )
                status, headers, payload = final_pairing
                evidence["pairing_global_block"] = {
                    "status": status,
                    "error": payload.get("error"),
                    "retry_after_header": int(headers.get("Retry-After") or 0) > 0,
                    "rotated_subjects": 60,
                }
                if status != 429 or payload.get("error") != "too_many_attempts":
                    failures.append("rotating unknown pairing secrets bypassed the endpoint-global bucket")
        finally:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
            process_output = (stdout or "") + (stderr or "")

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            columns = {row[1] for row in conn.execute("PRAGMA table_info(human_auth_throttle_buckets)").fetchall()}
            bucket_rows = [dict(row) for row in conn.execute(
                "SELECT bucket_key,scope,window_started_at,attempt_count,blocked_until,updated_at FROM human_auth_throttle_buckets"
            ).fetchall()]
            throttle_audits = [dict(row) for row in conn.execute(
                "SELECT action,metadata_json FROM audit_logs WHERE action IN ('human_auth.login_throttled','human_auth.pairing_throttled')"
            ).fetchall()]

        serialized = json.dumps({"buckets": bucket_rows, "audits": throttle_audits}, ensure_ascii=False)
        forbidden_columns = {"ip", "ip_address", "user_agent", "username", "pairing_secret"}
        evidence["persistence"] = {
            "bucket_rows": len(bucket_rows),
            "throttle_audit_rows": len(throttle_audits),
            "raw_identity_columns_absent": not bool(columns & forbidden_columns),
            "bucket_keys_hashed": bool(bucket_rows) and all(str(row["bucket_key"]).startswith("hatb_") for row in bucket_rows),
        }
        if columns & forbidden_columns:
            failures.append("throttle schema stores source identity fields")
        if bucket_rows and not all(str(row["bucket_key"]).startswith("hatb_") for row in bucket_rows):
            failures.append("throttle persistence contains a non-hashed bucket key")
        if any(value in serialized or value in process_output for value in raw_values):
            failures.append("throttle persistence, audit, or process output contains raw authentication input")
        actions = {row["action"] for row in throttle_audits}
        if not {"human_auth.login_throttled", "human_auth.pairing_throttled"}.issubset(actions):
            failures.append("bounded throttle audit actions are incomplete")

    print(json.dumps({
        "operation": "human_auth_throttle_smoke",
        "ok": not failures,
        "failures": failures,
        "evidence": evidence,
        "policy": {
            "source_independent": True,
            "login_subject_limit": 8,
            "login_global_limit": 100,
            "pairing_subject_limit": 8,
            "pairing_global_limit": 60,
            "window_seconds": 300,
            "block_seconds": 300,
        },
        "safety": {
            "temporary_database": True,
            "real_runtime_called": False,
            "ip_or_user_agent_stored": False,
            "raw_auth_input_omitted": True,
        },
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
