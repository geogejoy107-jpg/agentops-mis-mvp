#!/usr/bin/env python3
"""Verify live worker daemon starts require explicit confirmation."""
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
CLI = ROOT / "scripts" / "agentops"
SERVER = ROOT / "server.py"


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(base_url + "/api/agent-gateway/status", timeout=1) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    return False


def start_server(db_path: Path, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    return subprocess.Popen(
        [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run(args: list[str], base_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env["AGENTOPS_BASE_URL"] = base_url
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    return any(marker in text for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"])


def assert_confirm_gate(adapter: str, base_url: str) -> dict:
    proc = run(["worker", "start", "--adapter", adapter, "--poll-interval", "1", "--max-tasks", "0"], base_url)
    combined = "\n".join([proc.stdout, proc.stderr])
    require(proc.returncode != 0, f"{adapter} start without --confirm-run unexpectedly succeeded: {combined}")
    require("confirm_run" in combined or "confirm" in combined.lower(), f"{adapter} failure did not mention confirmation: {combined}")
    require(not secret_leaked(combined), f"{adapter} confirm gate leaked a secret-like token")
    return {
        "adapter": adapter,
        "blocked": True,
        "returncode": proc.returncode,
    }


def main() -> int:
    port = choose_port()
    base_url = f"http://127.0.0.1:{port}"
    server: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="agentops-worker-live-confirm-") as tmp:
        try:
            server = start_server(Path(tmp) / "agentops_worker_live_confirm.db", port)
            require(wait_ready(base_url, server), "isolated server did not become ready")
            results = [assert_confirm_gate("hermes", base_url), assert_confirm_gate("openclaw", base_url)]
        finally:
            if server:
                server.terminate()
                try:
                    server.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.communicate(timeout=5)
    print(json.dumps({
        "ok": True,
        "results": results,
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
