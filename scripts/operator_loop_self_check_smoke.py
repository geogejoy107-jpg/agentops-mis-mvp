#!/usr/bin/env python3
"""Verify the read-only operator loop self-check API and CLI."""

from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
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


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _ = http_json(base_url, "/api/operator/loop-self-check?limit=1")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def run_cli(base_url: str, args: list[str], env: dict) -> subprocess.CompletedProcess[str]:
    cli_env = env.copy()
    cli_env["AGENTOPS_BASE_URL"] = base_url
    cli_env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    cli_env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run([str(CLI), *args], cwd=ROOT, env=cli_env, capture_output=True, text=True, timeout=90, check=False)


def load_json(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def db_fingerprint(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        result = {}
        for table in ["audit_logs", "runtime_events", "operator_action_evaluations", "tasks", "runs", "memories", "approvals"]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return result
    finally:
        conn.close()


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def seed_verified_receipt(base_url: str, outputs: list[str], failures: list[str]) -> None:
    status, action_plan = http_json(base_url, "/api/operator/action-plan?limit=30")
    outputs.append(json.dumps(action_plan, ensure_ascii=False))
    require(status == 200, f"action-plan status mismatch: {status} {action_plan}", failures)
    action = next((
        item for item in action_plan.get("actions") or []
        if item.get("command") and item.get("action_signature") and item.get("receipt_required") is True
    ), {})
    require(bool(action), f"receipt seed action missing: {action_plan.get('actions')}", failures)
    if not action:
        return
    payload = {
        "action_command": str(action.get("command") or "agentops operator action-plan --limit 20"),
        "verify_command": str(action.get("verify_command") or "agentops operator loop-self-check --limit 20"),
        "action_id": str(action.get("action_id") or "smoke:loop-self-check"),
        "action_signature": str(action.get("action_signature") or ""),
        "source": "smoke.operator_loop_self_check",
        "status": "verified",
        "result_summary": "Smoke verified receipt should be visible in loop self-check audit gate.",
    }
    status, receipt = http_json(base_url, "/api/operator/action-receipts", method="POST", payload=payload)
    outputs.append(json.dumps(receipt, ensure_ascii=False))
    require(status == 201, f"receipt POST status mismatch: {status} {receipt}", failures)
    require((receipt.get("evaluation") or {}).get("pass_fail") == "pass", f"receipt evaluation should pass: {receipt}", failures)


def validate_payload(payload: dict, label: str, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-operator", f"{label} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "operator_loop_self_check", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"{label} status wrong: {payload}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing: {payload}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} ledger mutation flag wrong: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} live execution flag wrong: {safety}", failures)
    require(safety.get("server_shell_execution") is False, f"{label} server shell flag wrong: {safety}", failures)
    gates = payload.get("gates") or {}
    for gate_id in ["policy_contract", "advance_boundary", "receipt_coverage", "receipt_evaluations", "audit_ledger", "handoff_health"]:
        require(gate_id in gates, f"{label} missing gate {gate_id}: {gates}", failures)
    policy_gate = gates.get("policy_contract") or {}
    require(policy_gate.get("status") == "pass", f"{label} policy gate should pass: {policy_gate}", failures)
    require(policy_gate.get("policy_id") == "advance_loop_local_bounded_v1", f"{label} policy id missing: {policy_gate}", failures)
    require(policy_gate.get("denied_memory_approval") is True, f"{label} deny memory approval proof missing: {policy_gate}", failures)
    advance_gate = gates.get("advance_boundary") or {}
    require(advance_gate.get("local_cli_only") is True, f"{label} local CLI boundary missing: {advance_gate}", failures)
    audit_gate = gates.get("audit_ledger") or {}
    require(audit_gate.get("status") in {"pass", "attention"}, f"{label} audit gate status wrong: {audit_gate}", failures)
    require(int(audit_gate.get("receipt_audit_rows") or 0) >= 1, f"{label} receipt audit count missing: {audit_gate}", failures)
    require(int(audit_gate.get("evaluation_audit_rows") or 0) >= 1, f"{label} evaluation audit count missing: {audit_gate}", failures)
    require(audit_gate.get("tamper_chain_present") is True, f"{label} tamper chain proof missing: {audit_gate}", failures)
    decisions = payload.get("policy_decisions") or []
    denied = next((item for item in decisions if item.get("id") == "deny_memory_approval"), {})
    require(((denied.get("decision") or {}).get("allowed") is False), f"{label} denied decision missing: {decisions}", failures)
    handoff_snapshot = payload.get("handoff_snapshot") or {}
    require((handoff_snapshot.get("loop_health") or {}).get("operation") == "operator_loop_health", f"{label} loop health snapshot missing: {handoff_snapshot}", failures)
    require(isinstance(payload.get("next_actions") or [], list), f"{label} next actions missing: {payload}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-loop-self-check-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_CONFIG"] = str(tmpdir / "config.json")
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
            seed_verified_receipt(base_url, outputs, failures)
            before = db_fingerprint(db_path)
            status, api_payload = http_json(base_url, "/api/operator/loop-self-check?limit=12")
            outputs.append(json.dumps(api_payload, ensure_ascii=False))
            require(status == 200, f"self-check API status mismatch: {status} {api_payload}", failures)
            validate_payload(api_payload, "api", failures)
            cli_proc = run_cli(base_url, ["operator", "loop-self-check", "--limit", "12"], env)
            outputs.extend([cli_proc.stdout, cli_proc.stderr])
            cli_payload = load_json(cli_proc.stdout)
            require(cli_proc.returncode == 0, f"self-check CLI failed: {cli_proc.stderr or cli_proc.stdout}", failures)
            validate_payload(cli_payload, "cli", failures)
            after = db_fingerprint(db_path)
            require(before == after, f"loop self-check mutated DB: {before} -> {after}", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])
    secret_leaked = leaked("\n".join(outputs))
    require(not secret_leaked, "loop self-check leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_loop_self_check_smoke",
        "secret_leaked": secret_leaked,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
