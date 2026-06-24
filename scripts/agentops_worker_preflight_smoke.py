#!/usr/bin/env python3
"""Smoke test the operator-facing `agentops worker preflight` command."""
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


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    return any(marker in text for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"])


def main() -> int:
    mock = run(["worker", "preflight", "--adapter", "mock"])
    mock_payload = load_json(mock)
    require(mock.returncode == 0, f"mock preflight failed: {mock.stderr or mock.stdout}")
    require(mock_payload.get("provider") == "agentops-worker", f"unexpected provider: {mock_payload}")
    require(mock_payload.get("ok") is True, f"mock preflight was not ready: {mock_payload}")
    require(mock_payload.get("live_execution_performed") is False, "mock preflight reported live execution")
    require((mock_payload.get("adapter_preflight") or {}).get("live_execution_performed") is False, "adapter preflight executed live work")
    require(mock_payload.get("token_omitted") is True, "token omission marker missing")

    hermes = run(["worker", "preflight", "--adapter", "hermes", "--timeout", "1"])
    hermes_payload = load_json(hermes)
    require(hermes.returncode == 0, f"hermes preflight command failed: {hermes.stderr or hermes.stdout}")
    require((hermes_payload.get("adapter_preflight") or {}).get("adapter") == "hermes", f"wrong hermes adapter payload: {hermes_payload}")
    require((hermes_payload.get("adapter_preflight") or {}).get("live_execution_performed") is False, "hermes preflight executed live work")

    combined = "\n".join([mock.stdout, mock.stderr, hermes.stdout, hermes.stderr])
    require(not secret_leaked(combined), "preflight output leaked a secret-like token")
    print(json.dumps({
        "ok": True,
        "mock_ready": mock_payload.get("ok") is True,
        "hermes_preflight_returned": True,
        "live_execution_performed": False,
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
