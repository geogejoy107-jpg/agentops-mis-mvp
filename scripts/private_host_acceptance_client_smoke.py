#!/usr/bin/env python3
"""Verify the real-runtime acceptance client can use Private Host human auth."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import customer_worker_real_runtime_acceptance as acceptance
import v1_5_live_product_readiness_smoke as readiness


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    failures: list[str] = []
    evidence: dict[str, object] = {}
    fixture_values = {
        "machine": "fixture-private-host-machine-key",
        "admin": "fixture-private-host-admin-key",
        "setup": "fixture-private-host-setup-code",
        "password": "fixture-private-host-password",
    }
    with tempfile.TemporaryDirectory(prefix="agentops-private-client-") as temporary:
        temp = Path(temporary)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "AGENTOPS_DB_PATH": str(temp / "agentops_mis.db"),
            "AGENTOPS_SKIP_SEED_EXPORTS": "1",
            "AGENTOPS_DEPLOYMENT_MODE": "private_host",
            "AGENTOPS_HUMAN_AUTH_REQUIRED": "true",
            "AGENTOPS_COOKIE_SECURE": "false",
            "AGENTOPS_API_KEY": fixture_values["machine"],
            "AGENTOPS_ADMIN_KEY": fixture_values["admin"],
            "AGENTOPS_OWNER_SETUP_CODE": fixture_values["setup"],
            "AGENTOPS_ALLOWED_ORIGINS": base_url,
            "AGENTOPS_ACCEPTANCE_PASSWORD": fixture_values["password"],
        }
        process = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        old_password = os.environ.get("AGENTOPS_ACCEPTANCE_PASSWORD")
        old_setup = os.environ.get("AGENTOPS_OWNER_SETUP_CODE")
        os.environ["AGENTOPS_ACCEPTANCE_PASSWORD"] = fixture_values["password"]
        os.environ["AGENTOPS_OWNER_SETUP_CODE"] = fixture_values["setup"]
        try:
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(base_url + "/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("private Host fixture did not become ready")

            args = argparse.Namespace(
                base_url=base_url,
                request_timeout=10,
                origin=base_url,
                username="acceptance-owner",
                password_env="AGENTOPS_ACCEPTANCE_PASSWORD",
                setup_code_env="AGENTOPS_OWNER_SETUP_CODE",
            )
            opener, csrf_token, origin = acceptance.authenticate_human_session(args)
            read_status, tasks = acceptance.http_json(
                "GET", base_url, "/api/tasks", None, 10, opener=opener
            )
            write_status, task = acceptance.http_json(
                "POST",
                base_url,
                "/api/tasks",
                {"title": "Private Host acceptance client smoke", "description": "Bounded auth proof."},
                10,
                opener=opener,
                headers={"Origin": origin, "X-AgentOps-CSRF": csrf_token},
            )
            evidence = {
                "owner_session_created": bool(csrf_token),
                "authenticated_read": read_status == 200 and isinstance(tasks, list),
                "csrf_write": write_status in {200, 201} and bool(task.get("task_id")),
                "authenticated_readiness": False,
                "machine_token_used_for_browser": False,
                "real_runtime_called": False,
            }
            readiness_args = argparse.Namespace(
                base_url=base_url,
                timeout=10,
                origin=base_url,
                username="acceptance-owner",
                password_env="AGENTOPS_ACCEPTANCE_PASSWORD",
            )
            readiness_opener = readiness.authenticated_human_opener(readiness_args)
            readiness_status, readiness_payload = readiness.http_get_json(
                base_url, "/api/local/readiness", 10, opener=readiness_opener
            )
            evidence["authenticated_readiness"] = (
                readiness_status == 200 and readiness_payload.get("operation") == "local_readiness"
            )
            if not all((evidence["owner_session_created"], evidence["authenticated_read"], evidence["csrf_write"], evidence["authenticated_readiness"])):
                failures.append(f"Private Host acceptance client auth failed: {evidence}")
        except (OSError, RuntimeError, ValueError) as exc:
            failures.append(f"acceptance client exception: {type(exc).__name__}: {str(exc)[:180]}")
        finally:
            if old_password is None:
                os.environ.pop("AGENTOPS_ACCEPTANCE_PASSWORD", None)
            else:
                os.environ["AGENTOPS_ACCEPTANCE_PASSWORD"] = old_password
            if old_setup is None:
                os.environ.pop("AGENTOPS_OWNER_SETUP_CODE", None)
            else:
                os.environ["AGENTOPS_OWNER_SETUP_CODE"] = old_setup
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)
        combined = (stdout or "") + (stderr or "")
        if any(value in combined for value in fixture_values.values()):
            failures.append("Private Host acceptance client or server log exposed fixture credentials")

    print(json.dumps({
        "ok": not failures,
        "operation": "private_host_acceptance_client_smoke",
        "temporary_database": True,
        "credential_values_omitted": True,
        "evidence": evidence,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
