#!/usr/bin/env python3
"""Verify live worker daemon starts require explicit confirmation."""
from __future__ import annotations

import json
import os
import subprocess
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    return any(marker in text for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"])


def assert_confirm_gate(adapter: str) -> dict:
    proc = run(["worker", "start", "--adapter", adapter, "--poll-interval", "1", "--max-tasks", "0"])
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
    results = [assert_confirm_gate("hermes"), assert_confirm_gate("openclaw")]
    print(json.dumps({
        "ok": True,
        "results": results,
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
