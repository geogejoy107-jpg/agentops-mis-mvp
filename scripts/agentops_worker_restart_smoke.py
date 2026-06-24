#!/usr/bin/env python3
"""Verify local worker daemon restart controls and live confirm gate."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def run_cli(base_url: str, args: list[str]) -> tuple[int, dict, str]:
    proc = subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        payload = {}
    return proc.returncode, payload, proc.stdout + proc.stderr


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in ["agtok_", "agtsess_", "Authorization:", "Bearer ", "sk-", "ntn_"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test worker daemon restart controls.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    failures: list[str] = []
    try:
        status, gate = http_json("POST", args.base_url, "/api/workers/local/restart", {"adapter": "hermes"})
        require(status == 400, f"Hermes restart without confirm should fail closed: {status} {gate}")
        require("confirm_run" in (gate.get("error") or ""), f"confirm gate message missing: {gate}")

        run_cli(args.base_url, ["worker", "stop", "--adapter", "mock"])
        code, payload, text = run_cli(args.base_url, [
            "worker",
            "restart",
            "--adapter",
            "mock",
            "--poll-interval",
            "2",
            "--max-tasks",
            "0",
        ])
        require(code == 0, f"mock restart CLI failed: {code} {payload}")
        require(payload.get("provider") == "agentops-worker", f"wrong provider: {payload}")
        require(payload.get("ok") is True, f"restart not ok: {payload}")
        require((payload.get("daemon") or {}).get("running") is True, f"daemon not running after restart: {payload}")
        require((payload.get("daemon") or {}).get("adapter") == "mock", f"wrong daemon adapter: {payload}")
        require(payload.get("token_omitted") is True, f"token omission missing: {payload}")
        require(payload.get("live_execution_performed") is False, f"restart should not perform live execution: {payload}")
        require(not leaked_secret(text), "restart output leaked secret-like content")
    except AssertionError as exc:
        failures.append(str(exc))
    finally:
        run_cli(args.base_url, ["worker", "stop", "--adapter", "mock"])

    print(json.dumps({
        "ok": not failures,
        "base_url": args.base_url,
        "failure_count": len(failures),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
