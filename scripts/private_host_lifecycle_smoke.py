#!/usr/bin/env python3
"""Verify the repo-local `agentops host` lifecycle with isolated state."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
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
            }
            if not evidence["init"]["config_private"] or not evidence["init"]["secrets_private"]:
                failures.append("host config or secrets permissions were not private")
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

            _code, preview, preview_output = run_host(env, "tailscale-preview")
            evidence["tailscale_preview"] = {
                "preview_only": preview.get("preview_only"),
                "automatic_execution": preview.get("automatic_execution"),
                "public_funnel_enabled": preview.get("public_funnel_enabled"),
            }
            if preview.get("preview_only") is not True or preview.get("automatic_execution") is not False or preview.get("public_funnel_enabled") is not False:
                failures.append("Tailscale path was not preview-only and Funnel-disabled")
            if any(value and value in preview_output for value in secret_values):
                failures.append("Tailscale preview output exposed stored secret material")
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
