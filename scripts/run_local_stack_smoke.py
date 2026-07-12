#!/usr/bin/env python3
"""Verify the one-command local stack starts backend plus a safe worker."""
from __future__ import annotations

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
STACK = ROOT / "scripts" / "run_local_stack.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-local-stack-") as tmp:
        tmp_path = Path(tmp)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update(
            {
                "AGENTOPS_DB_PATH": str(tmp_path / "agentops_mis.db"),
                "AGENTOPS_CONFIG": str(tmp_path / "config.json"),
                "AGENTOPS_WORKER_STATE_PATH": str(tmp_path / "worker-state.json"),
                "AGENTOPS_SKIP_SEED_EXPORTS": "1",
                "HERMES_ALLOW_REAL_RUN": "false",
            }
        )
        process = subprocess.Popen(
            [
                sys.executable,
                str(STACK),
                "--backend-port",
                str(port),
                "--no-ui",
                "--worker",
                "mock",
                "--worker-poll-interval",
                "0.2",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        gateway = {}
        workers = {}
        try:
            deadline = time.time() + 30
            while time.time() < deadline:
                if process.poll() is not None:
                    break
                try:
                    gateway = get_json(base_url + "/api/agent-gateway/status")
                    workers = get_json(base_url + "/api/workers/status")
                    registered = [item for item in workers.get("workers", []) if item.get("agent_id") == "agt_worker_local_stack_mock"]
                    if gateway.get("provider") == "agent_gateway" and registered:
                        break
                except (OSError, ValueError, urllib.error.URLError):
                    pass
                time.sleep(0.25)
            else:
                failures.append("local stack did not become ready with a registered mock worker")
            if process.poll() is not None:
                failures.append(f"local stack exited early with code {process.returncode}")
            if gateway.get("provider") != "agent_gateway":
                failures.append("Agent Gateway status was not reachable")
            if not any(item.get("agent_id") == "agt_worker_local_stack_mock" for item in workers.get("workers", [])):
                failures.append("safe mock worker was not registered")
            if (tmp_path / "config.json").exists():
                failures.append("stack mutated CLI config without --configure-cli")
        finally:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate(timeout=5)

        combined = (stdout or "") + (stderr or "")
        if any(marker in combined for marker in ("Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_")):
            failures.append("stack output contained token-like material")

    blocked = subprocess.run(
        [sys.executable, str(STACK), "--no-ui", "--worker", "hermes"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if blocked.returncode == 0 or "--confirm-live-workers" not in ((blocked.stdout or "") + (blocked.stderr or "")):
        failures.append("Hermes worker did not fail closed without explicit live confirmation")

    print(
        json.dumps(
            {
                "ok": not failures,
                "operation": "run_local_stack_smoke",
                "backend_started": gateway.get("provider") == "agent_gateway",
                "mock_worker_registered": any(item.get("agent_id") == "agt_worker_local_stack_mock" for item in workers.get("workers", [])),
                "live_worker_confirmation_required": blocked.returncode != 0,
                "real_runtime_called": False,
                "user_config_mutated": False,
                "token_omitted": True,
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
