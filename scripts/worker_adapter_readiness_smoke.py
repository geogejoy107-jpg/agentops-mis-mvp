#!/usr/bin/env python3
"""Verify worker adapter readiness is available through API and CLI."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def run_cli(base_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "worker", "readiness"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def leaked_secret(text: str) -> bool:
    markers = ["AGENTOPS_API_KEY", "Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"]
    return any(marker in text for marker in markers)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_readiness(payload: dict) -> None:
    require(payload.get("provider") == "agentops-worker", f"wrong provider: {payload}")
    require(payload.get("status") in {"ready", "degraded", "blocked"}, f"bad readiness status: {payload}")
    require(payload.get("live_execution_performed") is False, "readiness must not execute live work")
    require(payload.get("token_omitted") is True, "token omission proof missing")
    adapters = payload.get("adapters") or {}
    for adapter in ("mock", "hermes", "openclaw"):
        item = adapters.get(adapter) or {}
        require(item.get("adapter") == adapter, f"missing adapter {adapter}: {payload}")
        require(item.get("readiness") in {"ready", "review_required", "blocked", "unavailable"}, f"bad {adapter} readiness: {item}")
        require((item.get("checks") or {}).get("live_execution_performed") is False, f"{adapter} readiness executed live work")
        require(item.get("token_omitted") is True, f"{adapter} token omission proof missing")
    summary = payload.get("summary") or {}
    require(summary.get("recommended_adapter") in {"mock", "hermes", "openclaw"}, f"missing recommended adapter: {summary}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify worker adapter readiness.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    try:
        status_code, api_payload = http_json(args.base_url, "/api/workers/adapter-readiness")
        require(status_code == 200, f"adapter readiness API failed: {status_code} {api_payload}")
        validate_readiness(api_payload)

        status_code, worker_status = http_json(args.base_url, "/api/workers/status")
        require(status_code == 200, f"worker status API failed: {status_code} {worker_status}")
        status_summary = worker_status.get("adapter_readiness") or {}
        require(status_summary.get("recommended_adapter") in {"mock", "hermes", "openclaw"}, f"worker status lacks readiness summary: {worker_status}")

        proc = run_cli(args.base_url)
        require(proc.returncode == 0, f"CLI readiness failed: {proc.stderr or proc.stdout}")
        require(not leaked_secret(proc.stdout + proc.stderr), "CLI readiness leaked token-like material")
        cli_payload = json.loads(proc.stdout)
        validate_readiness(cli_payload)

        result = {
            "ok": True,
            "api_status": api_payload.get("status"),
            "recommended_adapter": (api_payload.get("summary") or {}).get("recommended_adapter"),
            "ready_adapters": (api_payload.get("summary") or {}).get("ready_adapters"),
            "live_execution_performed": False,
            "secret_leaked": False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
