#!/usr/bin/env python3
"""Verify private-host human sessions remain separate from Agent Gateway auth."""
from __future__ import annotations

import http.cookiejar
import json
import os
import socket
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


def request_json(opener, url: str, *, method="GET", body=None, headers=None) -> tuple[int, dict, dict]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(url, data=payload, method=method, headers=request_headers)
    try:
        with opener.open(request, timeout=3) as response:
            raw = response.read()
            return response.status, dict(response.headers), json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, dict(exc.headers), json.loads(raw.decode("utf-8"))


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-human-auth-") as tmp:
        tmp_path = Path(tmp)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(
            {
                "AGENTOPS_DB_PATH": str(tmp_path / "agentops_mis.db"),
                "AGENTOPS_SKIP_SEED_EXPORTS": "1",
                "AGENTOPS_DEPLOYMENT_MODE": "private_host",
                "AGENTOPS_HUMAN_AUTH_REQUIRED": "true",
                "AGENTOPS_COOKIE_SECURE": "false",
                "AGENTOPS_API_KEY": "fixture-machine-key",
                "AGENTOPS_ADMIN_KEY": "fixture-admin-key",
                "AGENTOPS_OWNER_SETUP_CODE": "fixture-owner-setup-code",
                "AGENTOPS_ALLOWED_ORIGINS": base_url,
                "HERMES_ALLOW_REAL_RUN": "false",
            }
        )
        process = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        cookie_jar = http.cookiejar.CookieJar()
        browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        anonymous = urllib.request.build_opener()
        evidence: dict[str, object] = {}
        try:
            deadline = time.time() + 30
            while time.time() < deadline:
                if process.poll() is not None:
                    break
                try:
                    status, _headers, health = request_json(anonymous, base_url + "/health")
                    if status == 200:
                        evidence["health"] = health
                        break
                except (OSError, ValueError, urllib.error.URLError):
                    time.sleep(0.2)
            if "health" not in evidence:
                failures.append("private host did not become ready")

            status, _headers, payload = request_json(anonymous, base_url + "/api/tasks")
            evidence["anonymous_read"] = {"status": status, "error": payload.get("error")}
            if status != 401 or payload.get("error") != "human_auth_required":
                failures.append("anonymous human API read did not fail closed")

            status, _headers, payload = request_json(anonymous, base_url + "/api/agent-gateway/status")
            evidence["anonymous_gateway"] = {"status": status, "error": payload.get("error")}
            if status != 401:
                failures.append("Agent Gateway did not retain independent machine authentication")
            status, _headers, payload = request_json(
                anonymous,
                base_url + "/api/agent-gateway/status",
                headers={"Authorization": "Bearer fixture-machine-key"},
            )
            if status != 200 or payload.get("provider") != "agent_gateway":
                failures.append("machine API key did not authenticate Agent Gateway")
            status, _headers, payload = request_json(anonymous, base_url + "/api/operator/loop-supervision")
            if status != 401 or payload.get("error") != "human_auth_required":
                failures.append("anonymous operator supervision read did not require human auth")
            status, _headers, payload = request_json(
                anonymous,
                base_url + "/api/operator/loop-supervision?adapter=hermes&limit=2",
                headers={"Authorization": "Bearer fixture-machine-key"},
            )
            evidence["machine_scoped_supervision"] = {
                "status": status,
                "operation": payload.get("operation"),
                "token_omitted": payload.get("token_omitted"),
            }
            if status != 200 or payload.get("operation") != "operator_loop_supervision":
                failures.append("scoped machine credential could not read loop supervision")

            status, _headers, payload = request_json(browser, base_url + "/api/human-auth/status")
            evidence["bootstrap_status"] = payload
            if status != 200 or not payload.get("required") or not payload.get("bootstrap_required"):
                failures.append("human auth did not report owner bootstrap requirement")

            status, _headers, payload = request_json(
                browser,
                base_url + "/api/human-auth/bootstrap",
                method="POST",
                body={"setup_code": "wrong-fixture", "username": "owner", "password": "fixture-password-value"},
                headers={"Origin": base_url},
            )
            if status != 401 or payload.get("error") != "invalid_setup_code":
                failures.append("invalid owner setup code was not rejected")

            status, response_headers, payload = request_json(
                browser,
                base_url + "/api/human-auth/bootstrap",
                method="POST",
                body={
                    "setup_code": "fixture-owner-setup-code",
                    "username": "owner",
                    "display_name": "Local Owner",
                    "password": "fixture-password-value",
                },
                headers={"Origin": base_url},
            )
            csrf_token = str(payload.get("csrf_token") or "")
            set_cookie = response_headers.get("Set-Cookie", "")
            evidence["bootstrap"] = {
                "status": status,
                "role": (payload.get("user") or {}).get("role"),
                "http_only": "HttpOnly" in set_cookie,
                "same_site_strict": "SameSite=Strict" in set_cookie,
                "token_omitted": payload.get("token_omitted"),
            }
            if status != 201 or not csrf_token or "HttpOnly" not in set_cookie or "SameSite=Strict" not in set_cookie:
                failures.append("owner bootstrap did not create the expected secure browser session")

            status, _headers, payload = request_json(
                browser,
                base_url + "/api/human-auth/login",
                method="POST",
                body={"username": "owner", "password": "fixture-password-value"},
                headers={"Origin": "https://untrusted.invalid"},
            )
            evidence["wrong_origin"] = {"status": status, "error": payload.get("error")}
            if status != 403 or payload.get("error") != "origin_validation_failed":
                failures.append("untrusted browser Origin was not rejected")

            status, _headers, payload = request_json(browser, base_url + "/api/agent-gateway/status")
            evidence["human_cookie_gateway"] = {"status": status, "error": payload.get("error")}
            if status != 401:
                failures.append("human browser session was incorrectly accepted as a machine credential")

            status, _headers, payload = request_json(browser, base_url + "/api/tasks")
            if status != 200 or not isinstance(payload, list):
                failures.append("authenticated owner could not read human workspace API")
            status, _headers, payload = request_json(browser, base_url + "/api/operator/health")
            evidence["operator_read"] = {"status": status, "provider": payload.get("provider")}
            if status != 200:
                failures.append("authenticated owner could not read operator workspace API")

            task_body = {"title": "Human session fixture task", "description": "Bounded smoke evidence."}
            status, _headers, payload = request_json(browser, base_url + "/api/tasks", method="POST", body=task_body, headers={"Origin": base_url})
            if status != 403 or payload.get("error") != "csrf_validation_failed":
                failures.append("state-changing human request did not require CSRF")
            status, _headers, payload = request_json(
                browser,
                base_url + "/api/tasks",
                method="POST",
                body=task_body,
                headers={"X-AgentOps-CSRF": csrf_token, "Origin": base_url},
            )
            evidence["csrf_write"] = {"status": status, "task_id_present": bool(payload.get("task_id"))}
            if status not in {200, 201} or not payload.get("task_id"):
                failures.append("valid human session plus CSRF could not create a task")

            status, _headers, payload = request_json(
                browser,
                base_url + "/api/human-auth/logout",
                method="POST",
                body={},
                headers={"X-AgentOps-CSRF": csrf_token, "Origin": base_url},
            )
            if status != 200 or payload.get("authenticated") is not False:
                failures.append("human logout did not revoke the session")
            status, _headers, payload = request_json(browser, base_url + "/api/tasks")
            evidence["post_logout_read"] = {"status": status, "error": payload.get("error")}
            if status != 401:
                failures.append("revoked human session retained workspace access")
        finally:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)

        combined = (stdout or "") + (stderr or "")
        forbidden = ("fixture-machine-key", "fixture-admin-key", "fixture-owner-setup-code", "fixture-password-value")
        if any(value in combined for value in forbidden):
            failures.append("private host output exposed fixture credential material")

    print(
        json.dumps(
            {
                "ok": not failures,
                "operation": "human_browser_auth_smoke",
                "human_and_machine_credentials_separate": True,
                "real_runtime_called": False,
                "temporary_database": True,
                "credential_values_omitted": True,
                "evidence": evidence,
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
