#!/usr/bin/env python3
"""Verify the repo-local `agentops host` lifecycle with isolated state."""
from __future__ import annotations

import json
import http.cookiejar
import os
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_host(env: dict, *args: str, expected=(0,)) -> tuple[int, dict, str]:
    process = subprocess.run(
        [sys.executable, "-m", "agentops_mis_cli.cli", "host", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    try:
        payload = json.loads(process.stdout)
    except ValueError:
        payload = {}
    if process.returncode not in expected:
        raise RuntimeError(f"host {' '.join(args)} exited {process.returncode}: {process.stderr[-300:]}")
    return process.returncode, payload, (process.stdout or "") + (process.stderr or "")


def request_json(opener, url: str, *, method="GET", body=None, headers=None) -> tuple[int, dict, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with opener.open(request, timeout=5) as response:
            return response.status, dict(response.headers), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.loads(exc.read().decode("utf-8"))


def main() -> int:
    failures: list[str] = []
    evidence: dict[str, object] = {}
    with tempfile.TemporaryDirectory(prefix="agentops-host-lifecycle-") as tmp:
        tmp_path = Path(tmp)
        host_home = tmp_path / "host"
        ui_dist = tmp_path / "ui"
        ui_dist.mkdir()
        (ui_dist / "index.html").write_text("<!doctype html><div id='root'>HOST_FIXTURE</div>\n", encoding="utf-8")
        env = os.environ.copy()
        env["AGENTOPS_HOST_HOME"] = str(host_home)
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        tailscale_log = tmp_path / "tailscale-commands.log"
        fake_tailscale = fake_bin / "tailscale"
        fake_tailscale.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = status ]; then\n"
            "  printf '%s\\n' '{\"BackendState\":\"Running\",\"Self\":{\"DNSName\":\"agentops-host.example.ts.net.\"}}'\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"$1\" = serve ] && [ \"$2\" = status ]; then\n"
            "  if [ \"${AGENTOPS_TEST_TAILSCALE_SERVE_CONFLICT:-}\" = 1 ]; then\n"
            "    printf '%s\\n' '{\"TCP\":{\"443\":{\"HTTPS\":true}},\"Web\":{\"agentops-host.example.ts.net:443\":{\"Handlers\":{\"/\":{\"Proxy\":\"http://127.0.0.1:18789\"}}}}}'\n"
            "  else\n"
            "    printf '%s\\n' '{\"TCP\":{},\"Web\":{}}'\n"
            "  fi\n"
            "  exit 0\n"
            "fi\n"
            f"printf '%s\\n' \"$*\" >> {tailscale_log}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_tailscale.chmod(0o700)
        env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
        port = free_port()
        secret_values: list[str] = []
        try:
            _code, initialized, init_output = run_host(
                env,
                "init",
                "--port",
                str(port),
                "--ui-dist",
                str(ui_dist),
            )
            setup_code = str(initialized.get("owner_setup_code") or "")
            if not initialized.get("ok") or not setup_code:
                failures.append("host init did not return the one-time Owner setup code")
            config_path = Path(str(initialized.get("config_path") or ""))
            secrets_path = Path(str(initialized.get("secrets_path") or ""))
            secret_file = json.loads(secrets_path.read_text(encoding="utf-8")) if secrets_path.is_file() else {}
            secret_values = [str(value) for value in secret_file.values()]
            evidence["init"] = {
                "ok": initialized.get("ok"),
                "config_private": config_path.is_file() and (config_path.stat().st_mode & 0o077) == 0,
                "secrets_private": secrets_path.is_file() and (secrets_path.stat().st_mode & 0o077) == 0,
                "setup_code_visible_once": initialized.get("owner_setup_code_visible_once"),
                "loopback_cookie_secure": json.loads(config_path.read_text(encoding="utf-8")).get("cookie_secure"),
            }
            if not evidence["init"]["config_private"] or not evidence["init"]["secrets_private"]:
                failures.append("host config or secrets permissions were not private")
            if evidence["init"]["loopback_cookie_secure"] is not False:
                failures.append("loopback Host incorrectly required a Secure-only browser cookie")
            _code, repeated, repeated_output = run_host(env, "init", expected=(2,))
            if repeated.get("error") != "already_initialized" or any(value and value in repeated_output for value in secret_values):
                failures.append("repeated init did not fail closed without reprinting secrets")

            _code, started, start_output = run_host(env, "start", "--no-workers")
            evidence["start"] = {
                "ok": started.get("ok"),
                "health": (started.get("health") or {}).get("status"),
                "network_publication": started.get("network_publication"),
                "workers": started.get("workers"),
            }
            if not started.get("ok") or started.get("network_publication") != "disabled":
                failures.append("host did not start privately with network publication disabled")
            if any(value and value in start_output for value in secret_values):
                failures.append("host start output exposed stored secret material")

            _code, status, status_output = run_host(env, "status")
            evidence["status"] = {"ok": status.get("ok"), "running": status.get("running"), "health": (status.get("health") or {}).get("status")}
            if not status.get("running") or not status.get("ok"):
                failures.append("host status did not report the managed process ready")
            if any(value and value in status_output for value in secret_values):
                failures.append("host status output exposed stored secret material")

            base_url = f"http://127.0.0.1:{port}"
            browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            auth_status, auth_headers, auth_payload = request_json(
                browser,
                base_url + "/api/human-auth/bootstrap",
                method="POST",
                body={
                    "setup_code": setup_code,
                    "username": "host-owner",
                    "display_name": "Host Owner",
                    "password": "host-lifecycle-fixture-password",
                },
                headers={"Origin": base_url},
            )
            task_status, _task_headers, task_payload = request_json(browser, base_url + "/api/tasks")
            set_cookie = auth_headers.get("Set-Cookie", "")
            evidence["local_human_login"] = {
                "bootstrap_status": auth_status,
                "role": (auth_payload.get("user") or {}).get("role"),
                "http_only": "HttpOnly" in set_cookie,
                "secure_cookie": "Secure" in set_cookie,
                "authenticated_task_read": task_status == 200 and isinstance(task_payload, list),
            }
            if (
                auth_status != 201
                or "HttpOnly" not in set_cookie
                or "Secure" in set_cookie
                or task_status != 200
                or not isinstance(task_payload, list)
            ):
                failures.append("loopback Host Owner session did not persist over local HTTP")

            _code, preview, preview_output = run_host(env, "tailscale-preview")
            evidence["tailscale_preview"] = {
                "preview_only": preview.get("preview_only"),
                "automatic_execution": preview.get("automatic_execution"),
                "public_funnel_enabled": preview.get("public_funnel_enabled"),
                "installation_source": (preview.get("tailscale") or {}).get("installation_source"),
            }
            if (
                preview.get("preview_only") is not True
                or preview.get("automatic_execution") is not False
                or preview.get("public_funnel_enabled") is not False
                or (preview.get("tailscale") or {}).get("installation_source") != "path"
            ):
                failures.append("Tailscale path was not preview-only and Funnel-disabled")
            if any(value and value in preview_output for value in secret_values):
                failures.append("Tailscale preview output exposed stored secret material")

            _code, unconfirmed_apply, _output = run_host(env, "tailscale-apply", expected=(2,))
            if unconfirmed_apply.get("error") != "confirmation_required" or tailscale_log.exists():
                failures.append("unconfirmed Tailscale apply did not remain side-effect free")
            env["AGENTOPS_TEST_TAILSCALE_SERVE_CONFLICT"] = "1"
            _code, conflict_apply, _output = run_host(env, "tailscale-apply", "--confirm", expected=(2,))
            if conflict_apply.get("error") != "tailscale_serve_conflict" or tailscale_log.exists():
                failures.append("existing Tailscale Serve target was not protected from replacement")
            env.pop("AGENTOPS_TEST_TAILSCALE_SERVE_CONFLICT", None)
            _code, applied, apply_output = run_host(env, "tailscale-apply", "--confirm")
            config_after_apply = json.loads(config_path.read_text(encoding="utf-8"))
            evidence["tailscale_apply"] = {
                "ok": applied.get("ok"),
                "network_publication": config_after_apply.get("network_publication"),
                "trusted_origin_added": "https://agentops-host.example.ts.net" in (config_after_apply.get("allowed_origins") or []),
                "restart_required": applied.get("restart_required"),
                "secure_cookie_enabled": config_after_apply.get("cookie_secure"),
            }
            command_log = tailscale_log.read_text(encoding="utf-8") if tailscale_log.exists() else ""
            if "serve --bg" not in command_log or config_after_apply.get("network_publication") != "tailscale_serve" or config_after_apply.get("cookie_secure") is not True:
                failures.append("confirmed Tailscale apply did not persist Serve and trusted-Origin state")
            if any(value and value in apply_output for value in secret_values):
                failures.append("Tailscale apply output exposed stored secret material")

            _code, unconfirmed_revoke, _output = run_host(env, "tailscale-revoke", expected=(2,))
            if unconfirmed_revoke.get("error") != "confirmation_required":
                failures.append("unconfirmed Tailscale revoke did not fail closed")
            env["AGENTOPS_TEST_TAILSCALE_SERVE_CONFLICT"] = "1"
            _code, conflict_revoke, _output = run_host(env, "tailscale-revoke", "--confirm", expected=(2,))
            if conflict_revoke.get("error") != "tailscale_serve_not_exclusively_owned":
                failures.append("Tailscale revoke did not protect another Serve target")
            env.pop("AGENTOPS_TEST_TAILSCALE_SERVE_CONFLICT", None)
            _code, revoked, revoke_output = run_host(env, "tailscale-revoke", "--confirm")
            config_after_revoke = json.loads(config_path.read_text(encoding="utf-8"))
            evidence["tailscale_revoke"] = {
                "ok": revoked.get("ok"),
                "network_publication": config_after_revoke.get("network_publication"),
                "private_origin_removed": "https://agentops-host.example.ts.net" not in (config_after_revoke.get("allowed_origins") or []),
                "restart_required": revoked.get("restart_required"),
                "secure_cookie_disabled": config_after_revoke.get("cookie_secure") is False,
            }
            command_log = tailscale_log.read_text(encoding="utf-8") if tailscale_log.exists() else ""
            if "serve reset" not in command_log or config_after_revoke.get("network_publication") != "disabled" or config_after_revoke.get("cookie_secure") is not False:
                failures.append("confirmed Tailscale revoke did not reset Serve and trusted-Origin state")
            if any(value and value in revoke_output for value in secret_values):
                failures.append("Tailscale revoke output exposed stored secret material")
        except (OSError, ValueError, RuntimeError) as exc:
            failures.append(f"lifecycle exception: {type(exc).__name__}: {str(exc)[:180]}")
        finally:
            try:
                _code, stopped, _output = run_host(env, "stop")
                evidence["stop"] = {"ok": stopped.get("ok"), "status": stopped.get("status")}
                if not stopped.get("ok"):
                    failures.append("host stop did not complete")
            except Exception as exc:
                failures.append(f"host cleanup failed: {type(exc).__name__}")

    print(
        json.dumps(
            {
                "ok": not failures,
                "operation": "private_host_lifecycle_smoke",
                "temporary_host_home": True,
                "network_publication_performed": False,
                "real_runtime_called": False,
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
