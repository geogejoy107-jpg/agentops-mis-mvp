#!/usr/bin/env python3
"""Verify enrollment policy preview is read-only and matches CLI/API expectations."""
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


def http_json(base_url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/agent-gateway/enrollment/policy-preview",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
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


def run_cli(base_url: str, scopes: str, runtime: str = "mock") -> tuple[int, dict, str]:
    proc = subprocess.run(
        [str(CLI), "--base-url", base_url, "enrollment", "policy-preview", "--runtime", runtime, "--scopes", scopes],
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
    parser = argparse.ArgumentParser(description="Smoke test Agent Gateway enrollment policy preview.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    failures: list[str] = []
    try:
        status, worker = http_json(args.base_url, {
            "runtime_type": "openclaw",
            "workspace_id": "local-demo",
            "scopes": ["agents:heartbeat", "tasks:read", "tasks:claim", "runs:write", "toolcalls:write", "evaluations:submit", "audit:write"],
        })
        require(status == 200, f"worker preview failed: {status} {worker}")
        require(worker.get("policy") == "worker", f"worker policy mismatch: {worker}")
        require(worker.get("approval_recommended") is True, f"worker should recommend approval: {worker}")
        require(worker.get("recommended_path") == "request_approval", f"worker path mismatch: {worker}")
        require(worker.get("safety", {}).get("read_only") is True, f"worker preview not read-only: {worker}")
        require(worker.get("safety", {}).get("ledger_mutated") is False, f"worker preview mutated ledger: {worker}")

        status, observer = http_json(args.base_url, {
            "runtime_type": "mock",
            "workspace_id": "local-demo",
            "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
        })
        require(status == 200, f"observer preview failed: {status} {observer}")
        require(observer.get("policy") == "observer", f"observer policy mismatch: {observer}")
        require(observer.get("risk_level") == "low", f"observer risk mismatch: {observer}")
        require(observer.get("approval_recommended") is False, f"observer should not require approval: {observer}")

        status, invalid = http_json(args.base_url, {
            "runtime_type": "mock",
            "workspace_id": "local-demo",
            "scopes": ["agents:heartbeat", "tasks:read", "root:all"],
        })
        require(status == 200, f"invalid preview failed: {status} {invalid}")
        require(invalid.get("status") == "blocked", f"invalid scopes should block: {invalid}")
        require("root:all" in invalid.get("invalid_scopes", []), f"invalid scope missing: {invalid}")

        cli_code, cli_payload, cli_text = run_cli(args.base_url, "agents:heartbeat,tasks:read,audit:write")
        require(cli_code == 0, f"CLI preview failed: {cli_code} {cli_payload}")
        require(cli_payload.get("operation") == "enrollment_policy_preview", f"CLI operation mismatch: {cli_payload}")
        require(cli_payload.get("token_omitted") is True, f"CLI preview token omission missing: {cli_payload}")
        require(not leaked_secret(cli_text), "CLI preview leaked secret-like content")
    except AssertionError as exc:
        failures.append(str(exc))

    print(json.dumps({
        "ok": not failures,
        "base_url": args.base_url,
        "failure_count": len(failures),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
