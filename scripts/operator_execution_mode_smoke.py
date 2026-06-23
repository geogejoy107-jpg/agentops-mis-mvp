#!/usr/bin/env python3
"""Verify operator execution-mode is read-only, scoped, and available by CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from operator_runtime_doctor_smoke import (
    CLI,
    ROOT,
    create_enrollment,
    db_fingerprint,
    free_port,
    http_json,
    leaked_secret,
    load_json,
    require,
    wait_ready,
)


def validate_payload(payload: dict, label: str, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-operator", f"{label} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "operator_execution_mode", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("adapter") in {"mock", "hermes", "openclaw"}, f"{label} adapter mismatch: {payload}", failures)
    require(payload.get("mode") in {"dry_run_or_mock", "live_confirmation_required", "live_confirmed", "adapter_route_blocked"}, f"{label} mode mismatch: {payload}", failures)
    summary = payload.get("summary") or {}
    require("confirm_run_wall" in summary, f"{label} missing confirm_run_wall summary: {payload}", failures)
    require("prepared_action_wall" in summary, f"{label} missing prepared_action_wall summary: {payload}", failures)
    require("pending_approvals" in summary, f"{label} missing pending approvals count: {payload}", failures)
    require("active_workflow_jobs" in summary, f"{label} missing active workflow jobs count: {payload}", failures)
    route = payload.get("selected_route") or {}
    require(route.get("token_omitted") is True, f"{label} route should omit tokens: {route}", failures)
    gates = {item.get("id"): item for item in payload.get("gates") or []}
    for gate_id in ["selected_adapter_route", "confirm_run_wall", "prepared_action_wall", "approval_waiting", "async_jobs"]:
        require(gate_id in gates, f"{label} missing gate {gate_id}: {gates}", failures)
    require("live_acceptance_freshness" in gates, f"{label} missing live acceptance gate: {gates}", failures)
    commands = payload.get("commands") or {}
    require("agentops operator execution-mode" in commands.get("execution_mode", ""), f"{label} missing CLI command: {commands}", failures)
    sources = payload.get("sources") or {}
    live = sources.get("live_acceptance_readiness") or {}
    require(live.get("operation") == "live_acceptance_readiness", f"{label} live acceptance source missing: {sources}", failures)
    require((live.get("safety") or {}).get("read_only") is True, f"{label} live acceptance source not read-only: {live}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} should be read-only: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} should not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} should not execute live runtime: {safety}", failures)
    require(safety.get("server_executes_shell") is False, f"{label} should not execute shell: {safety}", failures)
    require(safety.get("token_omitted") is True, f"{label} should omit token: {safety}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-execution-mode-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_BASE_URL"] = base_url
        env.pop("AGENTOPS_API_KEY", None)
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            workspace_id = "ws_execution_mode"
            _token_id, token = create_enrollment(base_url, workspace_id, "agt_execution_mode", ["tasks:read", "agents:heartbeat"])
            before = db_fingerprint(db_path)
            for path, label in [
                ("/api/operator/execution-mode?adapter=mock", "api_mock"),
                ("/api/operator/execution-mode?adapter=hermes", "api_hermes_unconfirmed"),
                ("/api/operator/execution-mode?adapter=hermes&confirm_run=true", "api_hermes_confirmed"),
            ]:
                status, payload = http_json(base_url, path)
                outputs.append(json.dumps(payload, ensure_ascii=False))
                require(status == 200, f"{label} status mismatch: {status} {payload}", failures)
                validate_payload(payload, label, failures)
            status, scoped_payload = http_json(
                base_url,
                "/api/operator/execution-mode?adapter=openclaw",
                headers={"Authorization": f"Bearer {token}", "X-AgentOps-Workspace-Id": workspace_id},
            )
            outputs.append(json.dumps(scoped_payload, ensure_ascii=False))
            require(status == 200, f"scoped status mismatch: {status} {scoped_payload}", failures)
            validate_payload(scoped_payload, "scoped_api", failures)
            require(scoped_payload.get("workspace_id") == workspace_id, f"scoped workspace mismatch: {scoped_payload}", failures)
            status, forbidden = http_json(
                base_url,
                "/api/operator/execution-mode?adapter=openclaw",
                headers={"Authorization": f"Bearer {token}", "X-AgentOps-Workspace-Id": "other-workspace"},
            )
            outputs.append(json.dumps(forbidden, ensure_ascii=False))
            require(status == 403, f"cross-workspace token should be forbidden: {status} {forbidden}", failures)
            cli_proc = subprocess.run(
                [str(CLI), "--base-url", base_url, "operator", "execution-mode", "--adapter", "hermes", "--confirm-run"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            outputs.extend([cli_proc.stdout, cli_proc.stderr])
            require(cli_proc.returncode == 0, f"CLI execution-mode failed: {cli_proc.stderr or cli_proc.stdout}", failures)
            cli_payload = load_json(cli_proc.stdout)
            validate_payload(cli_payload, "cli", failures)
            live_status, live_payload = http_json(base_url, "/api/operator/live-acceptance?freshness_hours=72&limit=4")
            outputs.append(json.dumps(live_payload, ensure_ascii=False))
            require(live_status == 200, f"live acceptance status mismatch: {live_status} {live_payload}", failures)
            require(live_payload.get("operation") == "live_acceptance_readiness", f"live acceptance operation mismatch: {live_payload}", failures)
            require((live_payload.get("safety") or {}).get("read_only") is True, f"live acceptance must be read-only: {live_payload}", failures)
            live_cli_proc = subprocess.run(
                [str(CLI), "--base-url", base_url, "operator", "live-acceptance", "--freshness-hours", "72", "--limit", "4"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            outputs.extend([live_cli_proc.stdout, live_cli_proc.stderr])
            require(live_cli_proc.returncode == 0, f"CLI live-acceptance failed: {live_cli_proc.stderr or live_cli_proc.stdout}", failures)
            live_cli_payload = load_json(live_cli_proc.stdout)
            require(live_cli_payload.get("operation") == "live_acceptance_readiness", f"CLI live acceptance operation mismatch: {live_cli_payload}", failures)
            require((live_cli_payload.get("safety") or {}).get("read_only") is True, f"CLI live acceptance must be read-only: {live_cli_payload}", failures)
            after = db_fingerprint(db_path)
            require(before == after, f"execution-mode mutated ledger: before={before} after={after}", failures)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    combined = "\n".join(outputs)
    require(not leaked_secret(combined), "execution-mode output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_execution_mode_smoke",
        "failures": failures,
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
