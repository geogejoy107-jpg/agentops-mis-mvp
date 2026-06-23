#!/usr/bin/env python3
"""Smoke-test the read-only operator start-check CLI aggregate."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_-]{12,}"),
    re.compile(r"agtsess_[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ntn_[A-Za-z0-9_-]{16,}"),
    re.compile(r"AGENTOPS_API_KEY\s*=", re.IGNORECASE),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def run_start_check(base_url: str, adapter: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "operator", "start-check", "--adapter", adapter, "--limit", "4"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def http_json(base_url: str, path: str, query: dict[str, str] | None = None) -> tuple[int, dict]:
    suffix = f"?{urlencode(query or {})}" if query else ""
    req = Request(base_url.rstrip("/") + path + suffix, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=45) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def validate(payload: dict, adapter: str) -> None:
    require(payload.get("provider") == "agentops-operator", f"wrong provider: {payload}")
    require(payload.get("operation") == "operator_start_check", f"wrong operation: {payload}")
    require(payload.get("adapter") == adapter, f"wrong adapter: {payload.get('adapter')}")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"bad status: {payload.get('status')}")
    require(payload.get("token_omitted") is True, "token omission proof missing")
    require(payload.get("live_execution_performed") is False, "start-check must not execute live work")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"safety.read_only missing: {safety}")
    require(safety.get("ledger_mutated") is False, f"safety.ledger_mutated must be false: {safety}")
    require(safety.get("server_executes_shell") is False, f"server shell must be false: {safety}")
    require(safety.get("token_omitted") is True, f"safety token proof missing: {safety}")
    gates = payload.get("gates") or []
    gate_ids = {gate.get("id") for gate in gates}
    for gate_id in {
        "local_readiness",
        "worker_connection_policy",
        "adapter_preflight",
        "runtime_doctor",
        "loop_launch_brief",
        "local_run_path",
        "agent_plan_boundary",
        "live_product_readiness",
    }:
        require(gate_id in gate_ids, f"missing start-check gate {gate_id}: {gate_ids}")
    for gate in gates:
        require(gate.get("token_omitted") is True, f"gate token proof missing: {gate}")
    worker_policy = payload.get("worker_connection_policy") or {}
    require(worker_policy.get("schema") == "agentops-worker-connection-policy-v1", f"worker policy schema missing: {worker_policy}")
    worker_policy_safety = worker_policy.get("safety") if isinstance(worker_policy.get("safety"), dict) else {}
    worker_policy_token_omitted = worker_policy.get("token_omitted") if "token_omitted" in worker_policy else worker_policy_safety.get("token_omitted", True)
    worker_policy_server_shell = worker_policy.get("server_executes_shell") if "server_executes_shell" in worker_policy else worker_policy_safety.get("server_executes_shell")
    require(worker_policy_token_omitted is not False, f"worker policy token proof missing: {worker_policy}")
    require(worker_policy_server_shell is False, f"worker policy must be copy-only: {worker_policy}")
    local_run_path = payload.get("local_run_path") or {}
    steps = local_run_path.get("steps") or []
    require(len(steps) >= 8, f"local run path too short: {local_run_path}")
    require((local_run_path.get("safety") or {}).get("server_executes_shell") is False, f"local run path safety missing: {local_run_path}")
    launch_brief = payload.get("launch_brief") or {}
    require(launch_brief.get("operation") == "operator_loop_launch_brief", f"launch brief missing: {launch_brief}")
    require((launch_brief.get("safety") or {}).get("read_only") is True, f"launch brief read-only proof missing: {launch_brief}")
    next_commands = payload.get("next_commands") or []
    require(any("operator loop-launch-packet" in command for command in next_commands), f"launch command missing: {next_commands}")
    if adapter in {"hermes", "openclaw"}:
        summary = payload.get("summary") or {}
        require(summary.get("requires_confirm_run") is True, f"live adapter confirm proof missing: {summary}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify operator start-check CLI aggregate.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], action="append", default=None)
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="agentops-start-check-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            checked = []
            for adapter in (args.adapter or ["mock"]):
                api_status, api_payload = http_json(args.base_url, "/api/operator/start-check", {"adapter": adapter, "limit": "4"})
                outputs.append(json.dumps(api_payload, ensure_ascii=False))
                require(api_status == 200, f"operator start-check API failed for {adapter}: {api_status} {api_payload}")
                validate(api_payload, adapter)
                proc = run_start_check(args.base_url, adapter, env)
                outputs.extend([proc.stdout, proc.stderr])
                require(proc.returncode == 0, f"operator start-check failed for {adapter}: {proc.stderr or proc.stdout}")
                payload = json.loads(proc.stdout)
                validate(payload, adapter)
                require(payload.get("operation") == api_payload.get("operation"), f"CLI/API operation mismatch for {adapter}")
                require(payload.get("adapter") == api_payload.get("adapter"), f"CLI/API adapter mismatch for {adapter}")
                checked.append({"adapter": adapter, "api_status": api_payload.get("status"), "cli_status": payload.get("status")})
        require(not leaked_secret("\n".join(outputs)), "operator start-check leaked token-like material")
        print(json.dumps({
            "ok": True,
            "operation": "operator_start_check_smoke",
            "checked": checked,
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
