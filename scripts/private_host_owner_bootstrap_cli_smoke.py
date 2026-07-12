#!/usr/bin/env python3
"""Verify safe first-Owner bootstrap through the packaged Host CLI contract."""
from __future__ import annotations

import json
import contextlib
import io
import os
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentops_mis_cli import host as host_module


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_host(env: dict, *args: str, expected=(0,), input_text: str | None = None) -> tuple[dict, str]:
    process = subprocess.run(
        [sys.executable, "-m", "agentops_mis_cli.cli", "host", *args],
        cwd=ROOT,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if process.returncode not in expected:
        raise RuntimeError(f"host {' '.join(args)} exited {process.returncode}: {process.stderr[-300:]}")
    return json.loads(process.stdout), (process.stdout or "") + (process.stderr or "")


def request_json(base_url: str, path: str, *, body: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        base_url + path,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method="GET" if body is None else "POST",
        headers={"Content-Type": "application/json", "Origin": base_url},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> int:
    failures: list[str] = []
    evidence: dict[str, object] = {}
    parser = host_module.build_parser()
    bootstrap_parser = next(action for action in parser._actions if getattr(action, "choices", None)).choices["bootstrap-owner"]
    password_argv_option_present = any("--password" in action.option_strings for action in bootstrap_parser._actions)
    forbidden_secret = "fixture-forbidden-argv-secret"
    forbidden_variants = (
        ("--password", forbidden_secret),
        (f"--password={forbidden_secret}",),
        ("--pass", forbidden_secret),
        (f"--password-stdin={forbidden_secret}",),
        ("--password-stdin", forbidden_secret),
        (f"--password={forbidden_secret}", "bootstrap-owner"),
        ("--password-stdin", f"-{forbidden_secret}"),
        (f"--pass=-{forbidden_secret}",),
        ("--password-stdin", "--", forbidden_secret),
    )
    forbidden_results = [
        subprocess.run(
            [sys.executable, "-m", "agentops_mis_cli.cli", "host", "bootstrap-owner", *variant],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        for variant in forbidden_variants
    ]
    forbidden_payloads = [json.loads(result.stdout or "{}") for result in forbidden_results]
    password_argv_rejected_safely = all(
        result.returncode == 2
        and payload.get("error") in {"password_argv_forbidden", "invalid_arguments"}
        and forbidden_secret not in ((result.stdout or "") + (result.stderr or ""))
        for result, payload in zip(forbidden_results, forbidden_payloads)
    )

    captured_requests: list[dict[str, str]] = []

    class CaptureHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", errors="replace")
            captured_requests.append({"path": self.path, "body": raw})
            self.send_response(302 if self.path == "/redirect" else 200)
            self.send_header("Content-Type", "application/json")
            if self.path == "/redirect":
                self.send_header("Location", "/captured")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, _format, *_args):
            return

    capture_server = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    capture_thread = Thread(target=capture_server.serve_forever, daemon=True)
    capture_thread.start()
    capture_base_url = f"http://127.0.0.1:{capture_server.server_port}"
    proxy_fixture_secret = "fixture-proxy-bootstrap-secret"
    try:
        with mock.patch.dict(os.environ, {
            "HTTP_PROXY": capture_base_url,
            "http_proxy": capture_base_url,
            "NO_PROXY": "",
            "no_proxy": "",
        }):
            proxy_status, _proxy_payload = host_module.local_json_request(
                "http://127.0.0.2:9",
                "/api/human-auth/bootstrap",
                method="POST",
                body={"setup_code": proxy_fixture_secret, "password": proxy_fixture_secret},
            )
            proxy_capture_count = len(captured_requests)
            redirect_status, _redirect_payload = host_module.local_json_request(
                capture_base_url,
                "/redirect",
                method="POST",
                body={"setup_code": proxy_fixture_secret, "password": proxy_fixture_secret},
            )
    finally:
        capture_server.shutdown()
        capture_server.server_close()
        capture_thread.join(timeout=5)
    redirect_paths = [item["path"] for item in captured_requests]
    redirected_secret_forwarded = any(item["path"] == "/captured" and proxy_fixture_secret in item["body"] for item in captured_requests)
    mismatch_calls: list[tuple[str, str]] = []

    def mismatch_request(_base_url: str, path: str, *, method: str = "GET", body: dict | None = None):
        mismatch_calls.append((path, method))
        return 200, {"required": True, "bootstrap_required": True}

    mismatch_output = io.StringIO()
    with (
        mock.patch.object(host_module, "require_initialized", return_value=({"host": "127.0.0.1", "port": 8787}, {"owner_setup_code": "fixture-code"})),
        mock.patch.object(host_module, "health", return_value={"reachable": True, "status": "ready"}),
        mock.patch.object(host_module, "local_json_request", side_effect=mismatch_request),
        mock.patch.object(host_module.sys.stdin, "isatty", return_value=True),
        mock.patch.object(host_module.getpass, "getpass", side_effect=["fixture-password-a", "fixture-password-b"]),
        contextlib.redirect_stdout(mismatch_output),
    ):
        mismatch_code = host_module.cmd_bootstrap_owner(SimpleNamespace(confirm=True, username="owner.fixture", display_name="Fixture Owner", password_stdin=False))
    mismatch_payload = json.loads(mismatch_output.getvalue())
    evidence["local_contract"] = {
        "password_argv_option_present": password_argv_option_present,
        "password_argv_variants_rejected_safely": password_argv_rejected_safely,
        "environment_proxy_bypassed": proxy_status == 0 and proxy_capture_count == 0,
        "redirect_rejected": redirect_status == 302 and redirect_paths == ["/redirect"] and not redirected_secret_forwarded,
        "mismatch_code": mismatch_code,
        "mismatch_error": mismatch_payload.get("error"),
        "bootstrap_post_called": any(path == "/api/human-auth/bootstrap" and method == "POST" for path, method in mismatch_calls),
    }
    if (
        password_argv_option_present
        or not evidence["local_contract"]["password_argv_variants_rejected_safely"]
        or not evidence["local_contract"]["environment_proxy_bypassed"]
        or not evidence["local_contract"]["redirect_rejected"]
        or mismatch_code != 2
        or mismatch_payload.get("error") != "password_confirmation_mismatch"
        or evidence["local_contract"]["bootstrap_post_called"]
    ):
        failures.append("local Owner bootstrap password-input contract failed")
    with tempfile.TemporaryDirectory(prefix="agentops-owner-bootstrap-") as temporary:
        root = Path(temporary)
        host_home = root / "host"
        ui_dist = root / "ui"
        ui_dist.mkdir()
        (ui_dist / "index.html").write_text("<!doctype html><div id='root'>OWNER_BOOTSTRAP_FIXTURE</div>\n", encoding="utf-8")
        env = {**os.environ, "AGENTOPS_HOST_HOME": str(host_home)}
        password = "fixture-owner-password-2026"
        setup_code = ""
        try:
            initialized, init_output = run_host(
                env,
                "init",
                "--port",
                str(free_port()),
                "--ui-dist",
                str(ui_dist),
            )
            setup_code = str(initialized.get("owner_setup_code") or "")
            if not setup_code:
                failures.append("Host init did not create the one-time setup code")

            started, start_output = run_host(env, "start", "--no-workers")
            base_url = str(started.get("local_console_url") or "").removesuffix("/workspace")
            before_status, before = request_json(base_url, "/api/human-auth/status")

            preview, preview_output = run_host(
                env,
                "bootstrap-owner",
                "--username",
                "owner.fixture",
                expected=(2,),
            )
            if preview.get("error") != "confirmation_required":
                failures.append("Owner bootstrap was not confirmation gated")

            config_path = host_home / "config.json"
            host_config = json.loads(config_path.read_text(encoding="utf-8"))
            host_config["host"] = "192.0.2.10"
            config_path.write_text(json.dumps(host_config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            unsafe_target, unsafe_output = run_host(
                env,
                "bootstrap-owner",
                "--username",
                "unsafe.target",
                "--password-stdin",
                "--confirm",
                expected=(2,),
            )
            host_config["host"] = "127.0.0.1"
            config_path.write_text(json.dumps(host_config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            non_tty, non_tty_output = run_host(
                env,
                "bootstrap-owner",
                "--username",
                "non.tty",
                "--confirm",
                input_text="",
                expected=(2,),
            )
            empty_password, empty_output = run_host(
                env,
                "bootstrap-owner",
                "--username",
                "empty.password",
                "--password-stdin",
                "--confirm",
                input_text="\n",
                expected=(2,),
            )
            created, created_output = run_host(
                env,
                "bootstrap-owner",
                "--username",
                "owner.fixture",
                "--display-name",
                "Fixture Owner",
                "--password-stdin",
                "--confirm",
                input_text=password + "\n",
            )
            after_status, after = request_json(base_url, "/api/human-auth/status")
            login_status, login = request_json(
                base_url,
                "/api/human-auth/login",
                body={"username": "owner.fixture", "password": password},
            )
            repeated, repeated_output = run_host(
                env,
                "bootstrap-owner",
                "--username",
                "second.owner",
                "--password-stdin",
                "--confirm",
                expected=(2,),
            )
            combined_output = "".join((init_output, start_output, preview_output, unsafe_output, non_tty_output, created_output, repeated_output, empty_output))
            secret_leaked = bool((setup_code and setup_code in "".join((start_output, preview_output, unsafe_output, non_tty_output, created_output, repeated_output, empty_output))) or password in combined_output or password in env.values())
            evidence.update({
                "before": {
                    "status": before_status,
                    "bootstrap_required": before.get("bootstrap_required"),
                },
                "preview": {
                    "confirmation_required": preview.get("error") == "confirmation_required",
                    "password_omitted": preview.get("password_omitted"),
                    "setup_code_omitted": preview.get("setup_code_omitted"),
                },
                "created": {
                    "ok": created.get("ok"),
                    "owner_created": created.get("owner_created"),
                    "role": created.get("role"),
                    "password_omitted": created.get("password_omitted"),
                    "setup_code_omitted": created.get("setup_code_omitted"),
                    "session_cookie_omitted": created.get("session_cookie_omitted"),
                },
                "after": {
                    "status": after_status,
                    "bootstrap_required": after.get("bootstrap_required"),
                    "login_status": login_status,
                    "login_role": (login.get("user") or {}).get("role"),
                },
                "repeat": {
                    "error": repeated.get("error"),
                    "http_status": repeated.get("http_status"),
                },
                "empty_password": {
                    "error": empty_password.get("error"),
                },
                "unsafe_target": {
                    "error": unsafe_target.get("error"),
                    "target_omitted": unsafe_target.get("target_omitted"),
                },
                "non_tty": {
                    "error": non_tty.get("error"),
                },
                "secret_leaked": secret_leaked,
            })
            if before_status != 200 or before.get("bootstrap_required") is not True:
                failures.append("Host did not begin in Owner bootstrap state")
            if (
                created.get("ok") is not True
                or created.get("owner_created") is not True
                or created.get("role") != "owner"
                or created.get("password_omitted") is not True
                or created.get("setup_code_omitted") is not True
                or created.get("session_cookie_omitted") is not True
            ):
                failures.append("confirmed CLI bootstrap did not create a safely reported Owner")
            if after_status != 200 or after.get("bootstrap_required") is not False or login_status != 200 or (login.get("user") or {}).get("role") != "owner":
                failures.append("created Owner could not authenticate or bootstrap remained open")
            if repeated.get("error") != "owner_already_initialized" or repeated.get("http_status") != 409:
                failures.append("repeat Owner bootstrap did not fail closed")
            if empty_password.get("error") != "username_and_password_required":
                failures.append("empty stdin password was not rejected before the API call")
            if unsafe_target.get("error") != "unsafe_bootstrap_target" or unsafe_target.get("target_omitted") is not True:
                failures.append("non-loopback Owner bootstrap target did not fail closed before credential input")
            if non_tty.get("error") != "interactive_terminal_required":
                failures.append("non-interactive Owner bootstrap did not require --password-stdin")
            if secret_leaked:
                failures.append("Owner setup code or password appeared in CLI output")

            concurrent_home = root / "concurrent-host"
            concurrent_env = {**os.environ, "AGENTOPS_HOST_HOME": str(concurrent_home)}
            concurrent_setup_code = ""
            try:
                concurrent_init, concurrent_init_output = run_host(
                    concurrent_env,
                    "init",
                    "--port",
                    str(free_port()),
                    "--ui-dist",
                    str(ui_dist),
                )
                concurrent_setup_code = str(concurrent_init.get("owner_setup_code") or "")
                concurrent_start, concurrent_start_output = run_host(concurrent_env, "start", "--no-workers")
                concurrent_base_url = str(concurrent_start.get("local_console_url") or "").removesuffix("/workspace")
                candidates = (
                    ("owner.alpha", "fixture-concurrent-alpha-2026"),
                    ("owner.beta", "fixture-concurrent-beta-2026"),
                )

                def submit(candidate: tuple[str, str]) -> tuple[int, dict]:
                    username, candidate_password = candidate
                    return request_json(
                        concurrent_base_url,
                        "/api/human-auth/bootstrap",
                        body={
                            "setup_code": concurrent_setup_code,
                            "username": username,
                            "display_name": username,
                            "password": candidate_password,
                        },
                    )

                with ThreadPoolExecutor(max_workers=2) as pool:
                    concurrent_results = list(pool.map(submit, candidates))
                concurrent_logins = [
                    request_json(
                        concurrent_base_url,
                        "/api/human-auth/login",
                        body={"username": username, "password": candidate_password},
                    )[0]
                    for username, candidate_password in candidates
                ]
                concurrent_status, concurrent_auth = request_json(concurrent_base_url, "/api/human-auth/status")
                result_codes = sorted(status for status, _payload in concurrent_results)
                result_errors = sorted(str(payload.get("error") or "") for status, payload in concurrent_results if status != 201)
                concurrent_text = concurrent_start_output + json.dumps(concurrent_results, sort_keys=True)
                concurrent_secret_leaked = any(
                    value and value in concurrent_text
                    for value in (concurrent_setup_code, *(candidate_password for _username, candidate_password in candidates))
                )
                evidence["concurrent"] = {
                    "result_codes": result_codes,
                    "loser_errors": result_errors,
                    "successful_login_count": sum(1 for status in concurrent_logins if status == 200),
                    "bootstrap_required_after": concurrent_auth.get("bootstrap_required"),
                    "init_setup_code_visible_once": bool(concurrent_setup_code and concurrent_setup_code in concurrent_init_output),
                    "secret_leaked": concurrent_secret_leaked,
                }
                if (
                    result_codes != [201, 409]
                    or result_errors != ["owner_already_initialized"]
                    or sum(1 for status in concurrent_logins if status == 200) != 1
                    or concurrent_status != 200
                    or concurrent_auth.get("bootstrap_required") is not False
                    or concurrent_secret_leaked
                ):
                    failures.append("concurrent Owner bootstrap did not create exactly one account safely")
            finally:
                try:
                    concurrent_stopped, _output = run_host(concurrent_env, "stop")
                    evidence["concurrent_host_stopped"] = concurrent_stopped.get("ok")
                except Exception as exc:
                    failures.append(f"Concurrent Host cleanup failed: {type(exc).__name__}")
        except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
            failures.append(f"bootstrap smoke exception: {type(exc).__name__}: {str(exc)[:180]}")
        finally:
            try:
                stopped, _output = run_host(env, "stop")
                evidence["host_stopped"] = stopped.get("ok")
            except Exception as exc:
                failures.append(f"Host cleanup failed: {type(exc).__name__}")

    print(json.dumps({
        "ok": not failures,
        "operation": "private_host_owner_bootstrap_cli_smoke",
        "failures": failures,
        "evidence": evidence,
        "temporary_host_home": True,
        "real_runtime_called": False,
        "init_setup_code_visible_once": True,
        "post_init_credentials_omitted": True,
        "database_persisted": False,
    }, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
