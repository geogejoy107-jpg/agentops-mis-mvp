#!/usr/bin/env python3
"""Smoke test CLI worker daemon start/status/logs/stop controls."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    return any(marker in text for marker in ["AGENTOPS_API_KEY", "Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"])


def main() -> int:
    started_by_smoke = False
    try:
        before = load_json(run(["worker", "status"]))
        mock_before = next((item for item in before.get("daemons", []) if item.get("adapter") == "mock"), {})
        was_running = bool(mock_before.get("running"))

        start = run(["worker", "start", "--adapter", "mock", "--poll-interval", "1", "--max-tasks", "0", "--max-errors", "2"])
        start_payload = load_json(start)
        require(start.returncode == 0, f"start failed: {start.stderr or start.stdout}")
        require(start_payload.get("provider") == "agentops-worker", f"unexpected start payload: {start_payload}")
        started_by_smoke = not bool(start_payload.get("already_running")) and not was_running

        time.sleep(0.5)
        status = run(["worker", "status"])
        status_payload = load_json(status)
        require(status.returncode == 0, f"status failed: {status.stderr or status.stdout}")
        mock_status = next((item for item in status_payload.get("daemons", []) if item.get("adapter") == "mock"), {})
        require(bool(mock_status.get("running")) or bool(start_payload.get("already_running")), f"mock daemon not visible: {status_payload}")

        logs = run(["worker", "logs", "--adapter", "mock"])
        logs_payload = load_json(logs)
        require(logs.returncode == 0, f"logs failed: {logs.stderr or logs.stdout}")
        require((logs_payload.get("daemon") or {}).get("adapter") == "mock", f"logs adapter mismatch: {logs_payload}")

        stop_payload = {}
        if started_by_smoke:
            stop = run(["worker", "stop", "--adapter", "mock"])
            stop_payload = load_json(stop)
            require(stop.returncode == 0, f"stop failed: {stop.stderr or stop.stdout}")
            require(stop_payload.get("provider") == "agentops-worker", f"unexpected stop payload: {stop_payload}")

        combined = "\n".join([start.stdout, start.stderr, status.stdout, status.stderr, logs.stdout, logs.stderr, json.dumps(stop_payload)])
        require(not secret_leaked(combined), "CLI daemon controls leaked a secret-like token")
        print(json.dumps({
            "ok": True,
            "start_already_running": bool(start_payload.get("already_running")),
            "started_by_smoke": started_by_smoke,
            "status_running": bool(mock_status.get("running")),
            "logs_present": bool((logs_payload.get("daemon") or {}).get("log_tail") is not None),
            "stopped_by_smoke": bool(started_by_smoke),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        if started_by_smoke:
            run(["worker", "stop", "--adapter", "mock"])
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
