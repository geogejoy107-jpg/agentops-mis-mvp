#!/usr/bin/env python3
"""Smoke-test the read-only commercial config status API and CLI."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(url: str) -> dict:
    with urlopen(url, timeout=3) as res:
        return json.loads(res.read().decode("utf-8"))


def wait_ready(base_url: str, proc: subprocess.Popen, failures: list[str]) -> bool:
    deadline = time.time() + 12
    while time.time() < deadline:
        if proc.poll() is not None:
            failures.append(f"server exited early with rc={proc.returncode}")
            return False
        try:
            payload = http_json(base_url + "/api/commercial/config-status")
            return payload.get("operation") == "commercial_config_status"
        except (OSError, URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.2)
    failures.append("server did not expose commercial config status before timeout")
    return False


def validate_payload(label: str, payload: dict, failures: list[str]) -> None:
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    entitlements = payload.get("entitlements") if isinstance(payload.get("entitlements"), dict) else {}
    retention = payload.get("retention") if isinstance(payload.get("retention"), dict) else {}
    sources = payload.get("sources") if isinstance(payload.get("sources"), dict) else {}
    require(payload.get("operation") == "commercial_config_status", f"{label}: operation mismatch", failures)
    require(payload.get("status") == "ready", f"{label}: expected ready status: {payload.get('status')}", failures)
    require(entitlements.get("edition") == "free_local", f"{label}: edition should default free_local", failures)
    require(entitlements.get("billing_provider") == "none", f"{label}: billing provider should be none", failures)
    require(entitlements.get("billing_calls_enabled") is False, f"{label}: billing calls should be disabled", failures)
    require("local_worker_loop" in (entitlements.get("enabled_capabilities") or []), f"{label}: local worker capability missing", failures)
    require("hosted_mode" in (entitlements.get("disabled_capabilities") or []), f"{label}: hosted mode should be disabled", failures)
    require(retention.get("cleanup_approval_required") is True, f"{label}: cleanup approval gate missing", failures)
    require(retention.get("legal_hold_required_before_cleanup") is True, f"{label}: legal hold gate missing", failures)
    require(retention.get("cleanup_execution_enabled") is False, f"{label}: cleanup execution should be disabled", failures)
    require(safety.get("read_only") is True, f"{label}: read_only safety missing", failures)
    require(safety.get("live_execution_performed") is False, f"{label}: live execution marker wrong", failures)
    require(safety.get("billing_call_performed") is False, f"{label}: billing call marker wrong", failures)
    require(safety.get("cleanup_execution_performed") is False, f"{label}: cleanup marker wrong", failures)
    require(safety.get("raw_config_omitted") is True, f"{label}: raw config should be omitted", failures)
    require(safety.get("token_omitted") is True, f"{label}: token omission marker missing", failures)
    require((sources.get("entitlements") or {}).get("source") == "default_example", f"{label}: entitlement source should be default example", failures)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.pop("AGENTOPS_ENTITLEMENTS_PATH", None)
        env.pop("AGENTOPS_RETENTION_CONTROLS_PATH", None)
        env["AGENTOPS_DB_PATH"] = str(Path(tmp) / "agentops_commercial_status.db")
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            if wait_ready(base_url, proc, failures):
                api_payload = http_json(base_url + "/api/commercial/config-status")
                validate_payload("api", api_payload, failures)
                cli = subprocess.run(
                    [
                        "./scripts/agentops",
                        "--base-url",
                        base_url,
                        "commercial",
                        "config-status",
                    ],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=10,
                    check=False,
                )
                require(cli.returncode == 0, f"cli failed rc={cli.returncode} stderr={cli.stderr}", failures)
                if cli.stdout.strip():
                    try:
                        validate_payload("cli", json.loads(cli.stdout), failures)
                    except json.JSONDecodeError as exc:
                        failures.append(f"cli output invalid json: {exc}: {cli.stdout[:500]}")
                else:
                    failures.append("cli output empty")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    output = {
        "ok": not failures,
        "operation": "commercial_config_status_smoke",
        "endpoint": "/api/commercial/config-status",
        "cli": "agentops commercial config-status",
        "safety": {
            "read_only": True,
            "billing_call_performed": False,
            "cleanup_execution_performed": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
