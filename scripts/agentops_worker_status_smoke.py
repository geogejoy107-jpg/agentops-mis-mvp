#!/usr/bin/env python3
"""Smoke test `agentops worker status` without printing token secrets."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
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


def leaked_secret(text: str) -> bool:
    markers = ["AGENTOPS_API_KEY", "Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"]
    return any(marker in text for marker in markers)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agentops-worker-status-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env.pop("AGENTOPS_API_KEY", None)

        proc = run([str(CLI), "worker", "status"], env=env)
        payload = load_json(proc)
        text = proc.stdout + proc.stderr
        ok = (
            proc.returncode == 0
            and payload.get("provider") == "agentops-worker"
            and payload.get("status") in {"ready", "running", "attention"}
            and isinstance(payload.get("daemons"), list)
            and isinstance(payload.get("workers"), list)
            and isinstance(payload.get("remote_worker_health"), dict)
            and isinstance(payload.get("remote_worker_count"), int)
            and payload.get("remote_worker_health", {}).get("token_omitted") is True
            and not leaked_secret(text)
        )
        print(json.dumps({
            "ok": ok,
            "returncode": proc.returncode,
            "provider": payload.get("provider"),
            "status": payload.get("status"),
            "worker_count": payload.get("worker_count"),
            "running_workers": payload.get("running_workers"),
            "pending_worker_tasks": payload.get("pending_worker_tasks"),
            "stuck_worker_tasks": payload.get("stuck_worker_tasks"),
            "remote_worker_count": payload.get("remote_worker_count"),
            "stale_remote_enrollments": payload.get("stale_remote_enrollments"),
            "active_remote_sessions": payload.get("active_remote_sessions"),
            "daemon_count": len(payload.get("daemons") or []),
            "secret_leaked": leaked_secret(text),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        if not ok:
            print("stdout:", proc.stdout[-1600:], file=sys.stderr)
            print("stderr:", proc.stderr[-1600:], file=sys.stderr)
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
