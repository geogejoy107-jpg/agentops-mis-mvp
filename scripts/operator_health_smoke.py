#!/usr/bin/env python3
"""Verify aggregate operator health is read-only, scoped, and redacted."""

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


def http_json(base_url: str, path: str, *, method: str = "GET", payload: dict | None = None, headers: dict[str, str] | None = None) -> tuple[int, dict]:
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
            status, _ = http_json(base_url, "/api/operator/health?limit=1")
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
    require(payload.get("operation") == "operator_health", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") in {"blocked", "attention", "ready", "unknown"}, f"{label} status wrong: {payload}", failures)
    require(isinstance(payload.get("score"), int), f"{label} score missing: {payload}", failures)
    require(0 <= int(payload.get("score") or 0) <= 100, f"{label} score out of range: {payload}", failures)
    require(isinstance(payload.get("components") or [], list), f"{label} components missing: {payload}", failures)
    component_ids = {item.get("id") for item in payload.get("components") or []}
    for required_id in ["loop_health", "local_readiness", "security_readiness", "worker_fleet", "review_queue", "operator_action_plan"]:
        require(required_id in component_ids, f"{label} missing component {required_id}: {component_ids}", failures)
    require(isinstance(payload.get("risks") or [], list), f"{label} risks missing: {payload}", failures)
    for risk in payload.get("risks") or []:
        require(risk.get("action_command"), f"{label} risk action command missing: {risk}", failures)
        require(risk.get("verify_command") == "agentops operator health --limit 20" or str(risk.get("verify_command") or "").startswith("agentops operator health --loop-id "), f"{label} risk verify command wrong: {risk}", failures)
        require(risk.get("receipt_record_command"), f"{label} risk receipt record command missing: {risk}", failures)
        require(risk.get("receipt_verify_record_command"), f"{label} risk verify receipt command missing: {risk}", failures)
        require(risk.get("action_signature"), f"{label} risk signature missing: {risk}", failures)
        require(risk.get("receipt_required") is True, f"{label} risk receipt flag missing: {risk}", failures)
    require(isinstance(payload.get("next_actions") or [], list), f"{label} next actions missing: {payload}", failures)
    sources = payload.get("sources") or {}
    for key in ["handoff", "local_readiness", "security_readiness", "worker_status", "review_queue"]:
        require(key in sources, f"{label} source {key} missing: {sources}", failures)
    auth = payload.get("auth") or {}
    require(auth.get("mode") in {"local_dev_no_token", "global_api_key", "agent_token", "agent_session"}, f"{label} auth mode wrong: {auth}", failures)
    require(auth.get("required_scope") == "tasks:read", f"{label} auth required scope wrong: {auth}", failures)
    require(auth.get("token_omitted") is True, f"{label} auth token omission missing: {auth}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} mutated ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} executed live work: {safety}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing: {payload}", failures)


def create_enrollment(base_url: str, workspace_id: str, agent_id: str, scopes: list[str]) -> tuple[str, str]:
    status, payload = http_json(
        base_url,
        "/api/agent-gateway/enrollment/create",
        method="POST",
        payload={
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "name": f"Operator Health {agent_id}",
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
    with tempfile.TemporaryDirectory(prefix="agentops-operator-health-") as tmp:
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
            status, api_payload = http_json(base_url, "/api/operator/health?limit=8")
            outputs.append(json.dumps(api_payload, ensure_ascii=False))
            require(status == 200, f"API status mismatch: {status} {api_payload}", failures)
            validate_payload(api_payload, "api", failures)
            status, invalid_limit_payload = http_json(base_url, "/api/operator/health?limit=nope")
            outputs.append(json.dumps(invalid_limit_payload, ensure_ascii=False))
            require(status == 200, f"invalid limit should not fail: {status} {invalid_limit_payload}", failures)
            validate_payload(invalid_limit_payload, "invalid_limit_api", failures)
            status, invalid_token_payload = http_json(base_url, "/api/operator/health", headers={"Authorization": "Bearer no-such-token"})
            outputs.append(json.dumps(invalid_token_payload, ensure_ascii=False))
            require(status == 401, f"invalid token should be rejected: {status} {invalid_token_payload}", failures)
            require(invalid_token_payload.get("error") == "unauthorized", f"invalid token error mismatch: {invalid_token_payload}", failures)

            workspace_id = "ws_operator_health"
            agent_id = "agt_operator_health"
            _token_id, token = create_enrollment(base_url, workspace_id, agent_id, ["tasks:read", "agents:heartbeat"])
            status, scoped_payload = http_json(
                base_url,
                "/api/operator/health?limit=4",
                headers={"Authorization": f"Bearer {token}", "X-AgentOps-Workspace-Id": workspace_id},
            )
            outputs.append(json.dumps(scoped_payload, ensure_ascii=False))
            require(status == 200, f"scoped token health failed: {status} {scoped_payload}", failures)
            validate_payload(scoped_payload, "scoped_api", failures)
            scoped_auth = scoped_payload.get("auth") or {}
            require(scoped_auth.get("mode") == "agent_token", f"scoped auth mode mismatch: {scoped_auth}", failures)
            require(scoped_auth.get("workspace_id") == workspace_id, f"scoped workspace mismatch: {scoped_auth}", failures)

            cli_proc = subprocess.run(
                [str(CLI), "operator", "health", "--limit", "8"],
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

            after = db_fingerprint(db_path)
            for table in ["tasks", "runs", "memories", "approvals", "agent_plans", "plan_evidence_manifests"]:
                require(before.get(table) == after.get(table), f"operator health changed read-only table {table}: {before} -> {after}", failures)
            require(not leaked_secret("\n".join(outputs)), "operator health output leaked token-like material", failures)
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
        "operation": "operator_health_smoke",
        "failures": failures,
        "secret_leaked": leaked_secret("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
