#!/usr/bin/env python3
"""Smoke-test read-only production security readiness API and CLI."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_MARKERS = ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_", "AGENTOPS_API_KEY="]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def http_json(base_url: str) -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + "/api/security/production-readiness", headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def run_cli(base_url: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "security", "production-readiness"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def validate(payload: dict, label: str) -> None:
    require(payload.get("provider") == "agentops-security", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "production_readiness", f"{label} wrong operation: {payload}")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"{label} bad status: {payload.get('status')}")
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    startup = payload.get("startup_security") or {}
    require(startup.get("token_omitted") is True, f"{label} startup token omission missing")
    require(startup.get("status") in {"ready", "attention", "blocked"}, f"{label} bad startup status: {startup}")
    gates = payload.get("gates") or []
    gate_ids = {gate.get("id") for gate in gates if isinstance(gate, dict)}
    for gate_id in {"agent_gateway_auth", "admin_key", "scoped_agent_tokens", "local_dev_boundary"}:
        require(gate_id in gate_ids, f"{label} missing gate {gate_id}: {payload}")
    require(isinstance(payload.get("next_actions"), list) and payload.get("next_actions"), f"{label} next_actions missing")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("token_omitted") is True, f"{label} safety.token_omitted missing")
    require(safety.get("raw_prompt_omitted") is True, f"{label} safety.raw_prompt_omitted missing")
    require("local_dev_no_token" in (payload.get("contract") or ""), f"{label} contract should name local_dev_no_token boundary")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify production security readiness API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        status, payload = http_json(args.base_url)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        outputs.append(raw)
        require(status == 200, f"security readiness API failed: {status} {payload}")
        validate(payload, "api")

        with tempfile.TemporaryDirectory(prefix="agentops-security-readiness-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            proc = run_cli(args.base_url, env)
            outputs.extend([proc.stdout, proc.stderr])
            require(proc.returncode == 0, f"security readiness CLI failed: {proc.stderr or proc.stdout}")
            cli_payload = json.loads(proc.stdout)
            validate(cli_payload, "cli")

        require(not leaked_secret("\n".join(outputs)), "security readiness leaked token-like material")
        print(json.dumps({
            "ok": True,
            "status": payload.get("status"),
            "auth_mode": payload.get("auth_mode"),
            "production_ready": payload.get("production_ready"),
            "production_requested": payload.get("production_requested"),
            "gate_count": len(payload.get("gates") or []),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
