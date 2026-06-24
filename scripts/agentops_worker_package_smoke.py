#!/usr/bin/env python3
"""Smoke-test pip source installation of the AgentOps worker command."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]


class SmokeGateway(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        SmokeGateway.requests.append({"method": "GET", "path": self.path})
        if self.path.startswith("/api/agent-gateway/status"):
            self._send(200, {
                "auth": {
                    "mode": "local_dev",
                    "agent_id": "agt_worker_package_smoke",
                    "workspace_id": "local-demo",
                    "scopes": [],
                    "token_omitted": True,
                }
            })
            return
        if self.path.startswith("/api/agent-gateway/tasks/pull"):
            self._send(200, {"tasks": []})
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length") or "0"))
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        SmokeGateway.requests.append({"method": "POST", "path": self.path, "payload": payload})
        if self.path == "/api/agent-gateway/register":
            self._send(200, {"ok": True, "agent": payload})
            return
        if self.path == "/api/agent-gateway/heartbeat":
            self._send(200, {"ok": True})
            return
        self._send(404, {"error": "not_found"})


def run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), SmokeGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    with tempfile.TemporaryDirectory(prefix="agentops-worker-install-") as tmp:
        tmp_path = Path(tmp)
        venv_path = tmp_path / "venv"
        state_path = tmp_path / "worker.state.json"
        env = os.environ.copy()
        env.pop("AGENTOPS_API_KEY", None)
        env["AGENTOPS_WORKER_RUNTIME_DIR"] = str(tmp_path / "runtime")

        uv = shutil.which("uv")
        create_cmd = [uv, "venv", str(venv_path)] if uv else [sys.executable, "-m", "venv", str(venv_path)]
        create = run(create_cmd, cwd=ROOT, env=env)
        if create.returncode != 0:
            print(create.stderr or create.stdout, file=sys.stderr)
            return 1

        bin_dir = venv_path / ("Scripts" if os.name == "nt" else "bin")
        python = bin_dir / "python"
        worker = bin_dir / "agentops-worker"

        install_cmd = [uv, "pip", "install", "--python", str(python), str(ROOT)] if uv else [str(python), "-m", "pip", "install", str(ROOT)]
        install = run(install_cmd, cwd=tmp_path, env=env)
        help_run = run([str(worker), "--help"], cwd=tmp_path, env=env)
        once_run = run(
            [
                str(worker),
                "--once",
                "--adapter",
                "mock",
                "--base-url",
                base_url,
                "--workspace-id",
                "local-demo",
                "--agent-id",
                "agt_worker_package_smoke",
                "--status",
                "no_such_status_for_install_smoke",
                "--state-path",
                str(state_path),
            ],
            cwd=tmp_path,
            env=env,
        )
        preflight_run = run(
            [
                str(worker),
                "preflight",
                "--adapter",
                "mock",
                "--base-url",
                base_url,
                "--workspace-id",
                "local-demo",
                "--agent-id",
                "agt_worker_package_smoke",
            ],
            cwd=tmp_path,
            env=env,
        )
        launchd_run = run(
            [
                str(worker),
                "service-template",
                "--manager",
                "launchd",
                "--adapter",
                "mock",
                "--agent-id",
                "agt_worker_package_smoke",
                "--base-url",
                base_url,
            ],
            cwd=tmp_path,
            env=env,
        )
        systemd_run = run(
            [
                str(worker),
                "service-template",
                "--manager",
                "systemd",
                "--adapter",
                "mock",
                "--agent-id",
                "agt_worker_package_smoke",
                "--base-url",
                base_url,
            ],
            cwd=tmp_path,
            env=env,
        )

        once_payload = {}
        try:
            once_payload = json.loads(once_run.stdout) if once_run.stdout.strip() else {}
        except json.JSONDecodeError:
            pass

        state_payload = {}
        if state_path.exists():
            try:
                state_payload = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        preflight_payload = {}
        try:
            preflight_payload = json.loads(preflight_run.stdout) if preflight_run.stdout.strip() else {}
        except json.JSONDecodeError:
            pass

        ok = (
            install.returncode == 0
            and help_run.returncode == 0
            and "Run an AgentOps MIS worker loop" in help_run.stdout
            and preflight_run.returncode == 0
            and preflight_payload.get("ok") is True
            and preflight_payload.get("live_execution_performed") is False
            and preflight_payload.get("token_omitted") is True
            and once_run.returncode == 0
            and once_payload.get("ok") is True
            and once_payload.get("processed") == 0
            and once_payload.get("session", {}).get("token_omitted") is True
            and state_payload.get("agent_id") == "agt_worker_package_smoke"
            and state_payload.get("status") in {"completed", "stopped"}
            and any(item.get("path") == "/api/agent-gateway/register" for item in SmokeGateway.requests)
            and any(str(item.get("path")).startswith("/api/agent-gateway/tasks/pull") for item in SmokeGateway.requests)
            and any(item.get("path") == "/api/agent-gateway/heartbeat" for item in SmokeGateway.requests)
            and launchd_run.returncode == 0
            and "KeepAlive" in launchd_run.stdout
            and "agentops-worker" in launchd_run.stdout
            and "paste one-time token here" in launchd_run.stdout
            and systemd_run.returncode == 0
            and "Restart=always" in systemd_run.stdout
            and "agentops-worker" in systemd_run.stdout
            and "paste one-time token here" in systemd_run.stdout
        )
        print(json.dumps({
            "ok": ok,
            "install_returncode": install.returncode,
            "help_returncode": help_run.returncode,
            "preflight_returncode": preflight_run.returncode,
            "once_returncode": once_run.returncode,
            "launchd_template_returncode": launchd_run.returncode,
            "systemd_template_returncode": systemd_run.returncode,
            "command": str(worker),
            "state_path": str(state_path),
            "state_written": state_path.exists(),
            "processed": once_payload.get("processed"),
            "gateway_request_count": len(SmokeGateway.requests),
            "token_omitted": once_payload.get("session", {}).get("token_omitted"),
            "venv_tool": "uv" if uv else "venv",
        }, ensure_ascii=False, indent=2, sort_keys=True))
        if not ok:
            print("install stderr:", install.stderr[-1200:], file=sys.stderr)
            print("help stderr:", help_run.stderr[-1200:], file=sys.stderr)
            print("preflight stdout:", preflight_run.stdout[-1200:], file=sys.stderr)
            print("preflight stderr:", preflight_run.stderr[-1200:], file=sys.stderr)
            print("once stdout:", once_run.stdout[-1200:], file=sys.stderr)
            print("once stderr:", once_run.stderr[-1200:], file=sys.stderr)
            print("launchd stderr:", launchd_run.stderr[-1200:], file=sys.stderr)
            print("systemd stderr:", systemd_run.stderr[-1200:], file=sys.stderr)
        server.shutdown()
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
