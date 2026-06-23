#!/usr/bin/env python3
"""Verify local end-to-end readiness API and CLI output."""
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
        [str(CLI), "--base-url", base_url, "local", "readiness"],
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


def validate(payload: dict) -> None:
    require(payload.get("provider") == "agentops-local", f"wrong provider: {payload}")
    require(payload.get("operation") == "local_readiness", f"wrong operation: {payload}")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"bad status: {payload}")
    require(payload.get("live_execution_performed") is False, "readiness must not execute live work")
    require(payload.get("token_omitted") is True, "token omission proof missing")
    gates = payload.get("gates") or []
    gate_ids = {gate.get("id") for gate in gates}
    for gate_id in {"agent_gateway", "worker_fleet", "production_security", "adapter_route", "knowledge_memory", "evidence_chain", "commander_synthesis_loop", "runbook"}:
        require(gate_id in gate_ids, f"missing gate {gate_id}: {payload}")
    require("live_acceptance_freshness" in gate_ids, f"missing live acceptance gate: {payload}")
    evidence = payload.get("evidence") or {}
    for key in ["tasks", "runs", "tool_calls", "evaluations", "audit_logs", "artifacts", "memories", "approvals", "closed_loop_runs"]:
        require(isinstance(evidence.get(key), int), f"missing evidence count {key}: {evidence}")
    for key in ["commander_synthesis_artifacts", "commander_synthesis_pending_reviews", "commander_synthesis_promoted_memories", "commander_synthesis_promoted_deliveries"]:
        require(isinstance(evidence.get(key), int), f"missing synthesis evidence count {key}: {evidence}")
    for key in ["live_acceptance_fresh_adapters", "live_acceptance_latest_failed_adapters", "live_acceptance_missing_adapters"]:
        require(isinstance(evidence.get(key), int), f"missing live acceptance evidence count {key}: {evidence}")
    live = payload.get("live_acceptance_readiness") or {}
    require(live.get("operation") == "live_acceptance_readiness", f"live acceptance readiness missing: {live}")
    require(live.get("live_execution_performed") is False, f"live acceptance readback must be read-only: {live}")
    require((live.get("safety") or {}).get("read_only") is True, f"live acceptance safety missing: {live}")
    adapters = live.get("adapters") or {}
    for adapter in ["hermes", "openclaw"]:
        require(adapter in adapters, f"live acceptance missing adapter {adapter}: {live}")
        require(adapters[adapter].get("token_omitted") is True, f"live acceptance adapter token omission missing: {adapters[adapter]}")
    lifecycle = payload.get("commander_synthesis_lifecycle") or {}
    require(lifecycle.get("status") in {"empty", "created", "review_pending", "promotion_available", "promoted"}, f"bad synthesis lifecycle: {lifecycle}")
    require((lifecycle.get("safety") or {}).get("read_only") is True, f"synthesis lifecycle must be read-only: {lifecycle}")
    require(isinstance(payload.get("next_actions"), list), "next_actions must be a list")
    require(payload.get("contract") and "single local" in payload.get("contract"), "local contract missing")
    security = payload.get("security_production_readiness") or {}
    require(security.get("operation") == "production_readiness", f"security readiness missing: {security}")
    require(security.get("token_omitted") is True, "security readiness token omission proof missing")
    require(security.get("live_execution_performed") is False, "security readiness must not execute live work")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify AgentOps MIS local readiness closure.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    try:
        status_code, api_payload = http_json(args.base_url, "/api/local/readiness")
        require(status_code == 200, f"local readiness API failed: {status_code} {api_payload}")
        validate(api_payload)

        proc = run_cli(args.base_url)
        require(proc.returncode == 0, f"CLI local readiness failed: {proc.stderr or proc.stdout}")
        require(not leaked_secret(proc.stdout + proc.stderr), "CLI local readiness leaked token-like material")
        cli_payload = json.loads(proc.stdout)
        validate(cli_payload)

        result = {
            "ok": True,
            "api_status": api_payload.get("status"),
            "cli_status": cli_payload.get("status"),
            "gate_count": len(api_payload.get("gates") or []),
            "closed_loop_runs": (api_payload.get("evidence") or {}).get("closed_loop_runs"),
            "recommended_adapter": (api_payload.get("adapter_readiness") or {}).get("recommended_adapter"),
            "secret_leaked": False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
