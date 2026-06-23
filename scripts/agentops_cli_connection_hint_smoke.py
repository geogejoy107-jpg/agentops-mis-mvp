#!/usr/bin/env python3
"""Verify AgentOps CLI explains stale base-url sources on connection failure."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ProbeHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        if self.path == "/api/local/readiness":
            payload = {
                "operation": "local_readiness",
                "status": "attention",
                "running_instance": {
                    "current": True,
                    "status": "current",
                    "git_head_short": "probehead",
                    "server_started_after_source_mtime": True,
                },
                "token_omitted": True,
            }
        elif self.path == "/api/agent-gateway/status":
            payload = {
                "provider": "agent_gateway",
                "status": "ready",
                "auth": {"mode": "local_dev_no_token", "authenticated": False},
                "token_omitted": True,
            }
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-cli-connection-hint-") as tmp:
        probe_port = free_port()
        probe_url = f"http://127.0.0.1:{probe_port}"
        probe_server = ThreadingHTTPServer(("127.0.0.1", probe_port), ProbeHandler)
        probe_thread = threading.Thread(target=probe_server.serve_forever, daemon=True)
        probe_thread.start()
        config_path = Path(tmp) / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "base_url": "http://127.0.0.1:18787",
                    "workspace_id": "local-demo",
                    "agent_id": "agt_connection_hint_smoke",
                    "api_key": "fake_token_should_not_print",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(config_path)
        env["AGENTOPS_LOCAL_DEMO_DEFAULT_URL"] = probe_url
        env.pop("AGENTOPS_BASE_URL", None)
        proc = subprocess.run(
            [sys.executable, "-m", "agentops_mis_cli.agentops", "status"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        combined = f"{proc.stdout}\n{proc.stderr}"
        require(proc.returncode == 1, f"status should fail against stale base URL: rc={proc.returncode} {combined}", failures)
        require("Cannot reach http://127.0.0.1:18787/api/agent-gateway/status" in combined, f"missing unreachable URL: {combined}", failures)
        require("base_url_source=config" in combined, f"missing base_url source hint: {combined}", failures)
        require(f"config_path={config_path}" in combined, f"missing config path hint: {combined}", failures)
        require(f"local_demo_default={probe_url}" in combined, f"missing local demo default hint: {combined}", failures)
        require("local_demo_probe=ready" in combined, f"missing ready local demo probe hint: {combined}", failures)
        require("local_demo_current_code=current" in combined, f"missing current-code local demo hint: {combined}", failures)
        require(f"AGENTOPS_BASE_URL={probe_url} agentops status" in combined, f"missing env override repair hint: {combined}", failures)
        require(f"agentops login --base-url {probe_url}" in combined, f"missing saved-config repair hint: {combined}", failures)
        require("fake_token_should_not_print" not in combined, "connection hint leaked raw token", failures)
        doctor = subprocess.run(
            [sys.executable, "-m", "agentops_mis_cli.agentops", "doctor"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        try:
            doctor_payload = json.loads(doctor.stdout)
        except json.JSONDecodeError:
            doctor_payload = {}
        doctor_probe = doctor_payload.get("local_demo_probe") or {}
        require(doctor.returncode == 0, f"doctor should stay diagnostic in local mode: rc={doctor.returncode} stderr={doctor.stderr}", failures)
        require(doctor_payload.get("ok") is False, f"doctor should report stale configured target as not ok: {doctor_payload}", failures)
        require(doctor_probe.get("ready") is True and doctor_probe.get("base_url") == probe_url, f"doctor local default probe missing: {doctor_payload}", failures)
        require(doctor_probe.get("current_code_ok") is True and doctor_probe.get("current_code_status") == "current", f"doctor current-code probe missing: {doctor_payload}", failures)
        require(any("local demo default is ready" in str(item) for item in (doctor_payload.get("setup_hints") or [])), f"doctor repair hint missing: {doctor_payload}", failures)
        require("fake_token_should_not_print" not in doctor.stdout and "fake_token_should_not_print" not in doctor.stderr, "doctor leaked raw token", failures)
        probe_server.shutdown()
        probe_server.server_close()

    print(
        json.dumps(
            {
                "ok": not failures,
                "operation": "agentops_cli_connection_hint_smoke",
                "checked": [
                    "stale config base_url",
                    "base_url_source hint",
                    "local demo default hint",
                    "local demo readiness probe",
                    "local demo current-code probe",
                    "saved config repair hint",
                    "doctor stale-config probe",
                    "token omission",
                ],
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
