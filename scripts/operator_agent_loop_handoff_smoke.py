#!/usr/bin/env python3
"""Smoke-test the compact Hermes/OpenClaw/Codex agent-loop handoff CLI."""

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
SERVER = ROOT / "server.py"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_-]{12,}"),
    re.compile(r"agtsess_[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ntn_[A-Za-z0-9_-]{16,}"),
    re.compile(r"AGENTOPS_API_KEY\s*=", re.IGNORECASE),
]
LEDGER_TABLES = [
    "tasks",
    "runs",
    "tool_calls",
    "runtime_events",
    "evaluations",
    "audit_logs",
    "artifacts",
    "approvals",
    "memories",
    "agent_plans",
    "plan_evidence_manifests",
    "workflow_jobs",
    "agent_gateway_tokens",
    "agent_gateway_sessions",
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"})
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
            status, payload = http_json(base_url, "/api/local/readiness")
            if status == 200 and payload.get("operation") == "local_readiness":
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        counts: dict[str, int] = {}
        for table in LEDGER_TABLES:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return counts
    finally:
        conn.close()


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def validate(payload: dict, failures: list[str]) -> None:
    require(payload.get("operation") == "operator_agent_loop_handoff", f"wrong operation: {payload}", failures)
    require(payload.get("provider") == "agentops-operator", f"wrong provider: {payload}", failures)
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"bad status: {payload.get('status')}", failures)
    require(payload.get("token_omitted") is True, "top-level token omission missing", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"read-only proof missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"ledger mutation proof missing: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"live execution proof missing: {safety}", failures)
    require(safety.get("server_executes_shell") is False, f"server shell proof missing: {safety}", failures)
    require(safety.get("raw_prompt_omitted") is True, f"raw prompt omission proof missing: {safety}", failures)
    require(safety.get("raw_response_omitted") is True, f"raw response omission proof missing: {safety}", failures)
    require(safety.get("raw_content_omitted") is True, f"raw content omission proof missing: {safety}", failures)
    current_code = payload.get("current_code") or {}
    require(current_code.get("ok") is True, f"current code should pass on isolated server: {current_code}", failures)
    require("--require-current-code" in str(current_code.get("strict_command") or ""), f"strict current-code command missing: {current_code}", failures)
    summary = payload.get("summary") or {}
    require(summary.get("ready_for_handoff") is True, f"handoff should be structurally ready: {summary}", failures)
    consumers = payload.get("consumers") or []
    adapters = {item.get("adapter") for item in consumers}
    require({"hermes", "openclaw"}.issubset(adapters), f"missing Hermes/OpenClaw consumers: {adapters}", failures)
    for item in consumers:
        adapter = item.get("adapter")
        require(item.get("operation") == "agent_loop_handoff_consumer", f"{adapter} wrong operation: {item}", failures)
        require(item.get("ready_for_handoff") is True, f"{adapter} should be structurally handoff-ready: {item}", failures)
        require((item.get("safety") or {}).get("server_executes_shell") is False, f"{adapter} server shell proof missing: {item}", failures)
        require((item.get("safety") or {}).get("live_execution_performed") is False, f"{adapter} live proof missing: {item}", failures)
        start = item.get("start_check") or {}
        require(start.get("can_preview_loop") is True, f"{adapter} preview loop gate missing: {start}", failures)
        require(start.get("server_executes_shell") is False, f"{adapter} start-check server shell proof missing: {start}", failures)
        method = item.get("method") or {}
        require({"read", "plan", "retrieve", "compare", "preflight", "execute", "verify", "record"}.issubset(set(method.get("phase_commands") or {})), f"{adapter} phase commands missing: {method}", failures)
        gate_ids = set(method.get("method_gate_ids") or [])
        require({"read_start_check", "read_current_code", "plan_agent_plan", "retrieve_knowledge", "compare_base_reference", "preflight_adapter", "execute_bounded_loop", "verify_loop", "record_memory_candidate"}.issubset(gate_ids), f"{adapter} method gates missing: {gate_ids}", failures)
        commands = item.get("commands") or {}
        require(str(commands.get("agent_loop_handoff") or "").startswith(f"agentops operator agent-loop-handoff --adapter {adapter}"), f"{adapter} handoff command missing: {commands}", failures)
        require(str(commands.get("start_check") or "").startswith(f"agentops operator start-check --adapter {adapter}"), f"{adapter} start-check command missing: {commands}", failures)
        require(str(commands.get("launch_brief") or "").startswith(f"agentops operator loop-launch-packet --brief --adapter {adapter}"), f"{adapter} launch brief command missing: {commands}", failures)
        require("--confirm-loop" in str(commands.get("loop_driver_confirm") or ""), f"{adapter} confirm-loop command missing: {commands}", failures)
        live = item.get("live_product_readiness") or {}
        require(live.get("command") == f"agentops operator live-product-readiness --require-adapter {adapter}", f"{adapter} live readiness command missing: {live}", failures)
    codex = payload.get("codex_consumer") or {}
    require(codex.get("operation") == "agent_loop_handoff_codex_consumer", f"Codex consumer missing: {codex}", failures)
    require(codex.get("uses_same_packets") is True, f"Codex must use same packets: {codex}", failures)
    require((codex.get("safety") or {}).get("server_executes_shell") is False, f"Codex server shell proof missing: {codex}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-agent-loop-handoff-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops.db"
        log_path = tmp_path / "server.log"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_DEPLOYMENT_MODE"] = "local"
        proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=log_path.open("w"),
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            before = db_counts(db_path)
            http_status, http_payload = http_json(base_url, "/api/operator/agent-loop-handoff?limit=5")
            outputs.append(json.dumps(http_payload, ensure_ascii=False))
            require(http_status == 200, f"HTTP agent-loop-handoff status {http_status}: {http_payload}", failures)
            validate(http_payload, failures)
            cli_env = env.copy()
            cli_env["AGENTOPS_BASE_URL"] = base_url
            result = subprocess.run(
                [str(CLI), "operator", "agent-loop-handoff", "--limit", "5"],
                cwd=ROOT,
                env=cli_env,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            outputs.extend([result.stdout, result.stderr])
            require(result.returncode == 0, f"agent-loop-handoff failed: {result.stderr or result.stdout}", failures)
            payload = json.loads(result.stdout or "{}")
            validate(payload, failures)
            require(payload.get("summary") == http_payload.get("summary"), f"CLI/HTTP summary drift: cli={payload.get('summary')} http={http_payload.get('summary')}", failures)
            require(payload.get("adapters") == http_payload.get("adapters"), f"CLI/HTTP adapter drift: cli={payload.get('adapters')} http={http_payload.get('adapters')}", failures)
            after = db_counts(db_path)
            require(before == after, f"agent-loop-handoff mutated ledger: before={before} after={after}", failures)
            require(not leaked("\n".join(outputs)), "agent-loop-handoff leaked token-like material", failures)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_agent_loop_handoff_smoke",
        "failures": failures,
        "secret_leaked": leaked("\n".join(outputs)),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or leaked("\n".join(outputs)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
