#!/usr/bin/env python3
"""Verify operator handoff is read-only, redacted, and contains loop work order state."""

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


def http_json(
    base_url: str,
    path: str,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    payload: dict | None = None,
) -> tuple[int, dict]:
    req_headers = {"Content-Type": "application/json"}
    req_headers.update(headers or {})
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers=req_headers, method=method)
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
            status, _ = http_json(base_url, "/api/operator/handoff?limit=1")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_fingerprint(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        result = {}
        for table in ["audit_logs", "runtime_events", "tasks", "runs", "memories", "approvals", "agent_plans", "plan_evidence_manifests"]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return result
    finally:
        conn.close()


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def validate_payload(payload: dict, label: str, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-operator", f"{label} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "operator_handoff", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") in {"blocked", "attention", "ready", "unknown"}, f"{label} status wrong: {payload}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing: {payload}", failures)
    auth = payload.get("auth") or {}
    require(auth.get("mode") in {"local_dev_no_token", "global_api_key", "agent_token", "agent_session"}, f"{label} auth mode missing: {auth}", failures)
    require(auth.get("required_scope") == "tasks:read", f"{label} auth required scope wrong: {auth}", failures)
    require(auth.get("token_omitted") is True, f"{label} auth token omission missing: {auth}", failures)
    loop_health = payload.get("loop_health") or {}
    require(loop_health.get("operation") == "operator_loop_health", f"{label} loop_health operation missing: {loop_health}", failures)
    require(loop_health.get("status") in {"blocked", "attention", "ready", "unknown"}, f"{label} loop_health status wrong: {loop_health}", failures)
    require(isinstance(loop_health.get("score"), int), f"{label} loop_health score missing: {loop_health}", failures)
    require(0 <= int(loop_health.get("score") or 0) <= 100, f"{label} loop_health score out of range: {loop_health}", failures)
    require(isinstance(loop_health.get("gates") or {}, dict), f"{label} loop_health gates missing: {loop_health}", failures)
    require(isinstance(loop_health.get("risks") or [], list), f"{label} loop_health risks missing: {loop_health}", failures)
    require(loop_health.get("token_omitted") is True, f"{label} loop_health token omission missing: {loop_health}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} should not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} should not execute live work: {safety}", failures)
    summary = payload.get("summary") or {}
    for key in ["loop_package_items", "operator_actions", "receipt_required", "receipt_verified", "receipt_missing", "receipt_stale"]:
        require(isinstance(summary.get(key), int), f"{label} summary.{key} missing: {summary}", failures)
    work_order = payload.get("work_order") or {}
    require(work_order.get("method") == "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD", f"{label} method missing: {work_order}", failures)
    require(isinstance(work_order.get("commands") or [], list), f"{label} commands missing: {work_order}", failures)
    action_package = work_order.get("action_package") or {}
    require(action_package.get("operation") == "loop_action_package", f"{label} action_package missing: {action_package}", failures)
    receipt_state = payload.get("receipt_state") or {}
    require(isinstance((receipt_state.get("coverage") or {}).get("required"), int), f"{label} receipt coverage missing: {receipt_state}", failures)
    require(isinstance(receipt_state.get("recent") or [], list), f"{label} recent receipts missing: {receipt_state}", failures)
    review_state = payload.get("review_state") or {}
    require(isinstance(review_state.get("loop_record") or {}, dict), f"{label} review loop_record missing: {review_state}", failures)
    sources = payload.get("sources") or {}
    require("loop_audit" in sources and "action_plan" in sources, f"{label} sources missing: {sources}", failures)
    require("read-only" in (payload.get("contract") or ""), f"{label} contract missing: {payload}", failures)


def create_enrollment(base_url: str, workspace_id: str, agent_id: str, scopes: list[str]) -> tuple[str, str]:
    status, payload = http_json(
        base_url,
        "/api/agent-gateway/enrollment/create",
        method="POST",
        payload={
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "name": f"Handoff Scope {agent_id}",
            "runtime_type": "mock",
            "scopes": scopes,
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        },
    )
    if status != 201 or not payload.get("token_id") or not payload.get("token"):
        raise RuntimeError(f"enrollment create failed: {status} {payload}")
    return str(payload["token_id"]), str(payload["token"])


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-operator-handoff-") as tmp:
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
            before = db_fingerprint(db_path)
            status, api_payload = http_json(base_url, "/api/operator/handoff?limit=8")
            outputs.append(json.dumps(api_payload, ensure_ascii=False))
            require(status == 200, f"API status mismatch: {status} {api_payload}", failures)
            validate_payload(api_payload, "api", failures)
            invalid_limit_status, invalid_limit_payload = http_json(base_url, "/api/operator/handoff?limit=not-an-int")
            outputs.append(json.dumps(invalid_limit_payload, ensure_ascii=False))
            require(invalid_limit_status == 200, f"invalid limit should not 500: {invalid_limit_status} {invalid_limit_payload}", failures)
            validate_payload(invalid_limit_payload, "invalid_limit_api", failures)
            invalid_token_status, invalid_token_payload = http_json(
                base_url,
                "/api/operator/handoff?limit=8",
                headers={"Authorization": "Bearer not-a-real-token"},
            )
            outputs.append(json.dumps(invalid_token_payload, ensure_ascii=False))
            require(invalid_token_status == 401, f"invalid token should be rejected: {invalid_token_status} {invalid_token_payload}", failures)
            require(invalid_token_payload.get("error") == "unauthorized", f"invalid token error mismatch: {invalid_token_payload}", failures)

            workspace_a = "ws_handoff_scope_a"
            workspace_b = "ws_handoff_scope_b"
            agent_id = "agt_handoff_scope"
            _token_id, token = create_enrollment(base_url, workspace_a, agent_id, ["tasks:read", "agents:heartbeat"])
            scoped_headers = {
                "Authorization": f"Bearer {token}",
                "X-AgentOps-Workspace-Id": workspace_a,
            }
            status, scoped_payload = http_json(base_url, "/api/operator/handoff?limit=4", headers=scoped_headers)
            outputs.append(json.dumps(scoped_payload, ensure_ascii=False))
            require(status == 200, f"scoped token handoff failed: {status} {scoped_payload}", failures)
            validate_payload(scoped_payload, "scoped_api", failures)
            scoped_auth = scoped_payload.get("auth") or {}
            require(scoped_auth.get("mode") == "agent_token", f"scoped auth mode mismatch: {scoped_auth}", failures)
            require(scoped_auth.get("scoped") is True, f"scoped auth flag missing: {scoped_auth}", failures)
            require(scoped_auth.get("workspace_id") == workspace_a, f"scoped workspace mismatch: {scoped_auth}", failures)
            require(scoped_auth.get("agent_id") == agent_id, f"scoped agent mismatch: {scoped_auth}", failures)

            status, forbidden_payload = http_json(
                base_url,
                "/api/operator/handoff?limit=4",
                headers={"Authorization": f"Bearer {token}", "X-AgentOps-Workspace-Id": workspace_b},
            )
            outputs.append(json.dumps(forbidden_payload, ensure_ascii=False))
            require(status == 403, f"cross-workspace handoff should fail: {status} {forbidden_payload}", failures)
            require(forbidden_payload.get("error") == "forbidden", f"cross-workspace error mismatch: {forbidden_payload}", failures)

            _limited_token_id, limited_token = create_enrollment(base_url, workspace_a, "agt_handoff_limited", ["agents:heartbeat"])
            status, limited_payload = http_json(
                base_url,
                "/api/operator/handoff?limit=4",
                headers={"Authorization": f"Bearer {limited_token}", "X-AgentOps-Workspace-Id": workspace_a},
            )
            outputs.append(json.dumps(limited_payload, ensure_ascii=False))
            require(status == 403, f"missing-scope handoff should fail: {status} {limited_payload}", failures)
            require(limited_payload.get("error") == "forbidden", f"missing-scope error mismatch: {limited_payload}", failures)

            cli_proc = subprocess.run(
                [str(CLI), "operator", "handoff", "--limit", "8"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            outputs.extend([cli_proc.stdout, cli_proc.stderr])
            cli_payload = load_json(cli_proc.stdout)
            require(cli_proc.returncode == 0, f"CLI failed: {cli_proc.returncode} {cli_proc.stderr}", failures)
            validate_payload(cli_payload, "cli", failures)
            scoped_env = env.copy()
            scoped_env["AGENTOPS_API_KEY"] = token
            scoped_env["AGENTOPS_WORKSPACE_ID"] = workspace_a
            scoped_env["AGENTOPS_AGENT_ID"] = agent_id
            scoped_cli_proc = subprocess.run(
                [str(CLI), "operator", "handoff", "--limit", "4"],
                cwd=ROOT,
                env=scoped_env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            outputs.extend([scoped_cli_proc.stdout, scoped_cli_proc.stderr])
            scoped_cli_payload = load_json(scoped_cli_proc.stdout)
            require(scoped_cli_proc.returncode == 0, f"scoped CLI failed: {scoped_cli_proc.returncode} {scoped_cli_proc.stderr}", failures)
            validate_payload(scoped_cli_payload, "scoped_cli", failures)
            scoped_cli_auth = scoped_cli_payload.get("auth") or {}
            require(scoped_cli_auth.get("scoped") is True, f"scoped CLI auth missing: {scoped_cli_auth}", failures)
            require(scoped_cli_auth.get("workspace_id") == workspace_a, f"scoped CLI workspace mismatch: {scoped_cli_auth}", failures)
            after = db_fingerprint(db_path)
            for table in ["tasks", "runs", "memories", "approvals", "agent_plans", "plan_evidence_manifests"]:
                require(before.get(table) == after.get(table), f"handoff changed read-only table {table}: {before} -> {after}", failures)
            require(after.get("audit_logs", 0) >= before.get("audit_logs", 0), f"audit count regressed: {before} -> {after}", failures)
            require(not leaked_secret("\n".join(outputs)), "handoff output leaked token-like material", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])
    result = {
        "ok": not failures,
        "operation": "operator_handoff_smoke",
        "failures": failures,
        "secret_leaked": leaked_secret("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
