#!/usr/bin/env python3
"""Smoke-test the read-only Hermes/OpenClaw loop supervision API and CLI."""

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
    require(payload.get("operation") == "operator_loop_supervision", f"wrong operation: {payload}", failures)
    require(payload.get("provider") == "agentops-operator", f"wrong provider: {payload}", failures)
    require(payload.get("status") in {"ready_to_confirm", "record_first", "preview_only", "blocked", "attention"}, f"bad status: {payload.get('status')}", failures)
    require(payload.get("token_omitted") is True, "top-level token omission missing", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"read-only proof missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"ledger mutation proof missing: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"live execution proof missing: {safety}", failures)
    require(safety.get("server_executes_shell") is False, f"server shell proof missing: {safety}", failures)
    require(safety.get("raw_prompt_omitted") is True, f"raw prompt omission proof missing: {safety}", failures)
    require(safety.get("raw_response_omitted") is True, f"raw response omission proof missing: {safety}", failures)
    require(safety.get("raw_content_omitted") is True, f"raw content omission proof missing: {safety}", failures)
    summary = payload.get("summary") or {}
    require(summary.get("items") == 2, f"expected Hermes/OpenClaw items: {summary}", failures)
    require(summary.get("can_confirm_all") is True, f"bounded confirm should be structurally ready: {summary}", failures)
    handoff_summary = payload.get("handoff_summary") or {}
    require(handoff_summary.get("ready_for_handoff") is True, f"handoff source should be ready: {handoff_summary}", failures)
    items = payload.get("items") or []
    adapters = {item.get("adapter") for item in items}
    require({"hermes", "openclaw"}.issubset(adapters), f"missing Hermes/OpenClaw supervision items: {adapters}", failures)
    for item in items:
        adapter = item.get("adapter")
        require(item.get("operation") == "operator_loop_supervision_item", f"{adapter} wrong item operation: {item}", failures)
        require(item.get("status") in {"ready_to_confirm", "record_first", "preview_only", "blocked", "attention"}, f"{adapter} bad item status: {item}", failures)
        require(item.get("can_preview_loop") is True, f"{adapter} preview gate missing: {item}", failures)
        require(item.get("can_confirm_bounded_loop") is True, f"{adapter} confirm gate missing: {item}", failures)
        require(item.get("should_record_before_execute") in {True, False}, f"{adapter} record decision missing: {item}", failures)
        item_safety = item.get("safety") or {}
        require(item_safety.get("read_only") is True, f"{adapter} read-only safety missing: {item_safety}", failures)
        require(item_safety.get("ledger_mutated") is False, f"{adapter} ledger safety missing: {item_safety}", failures)
        require(item_safety.get("server_executes_shell") is False, f"{adapter} shell safety missing: {item_safety}", failures)
        gate_ids = {gate.get("id") for gate in (item.get("gates") or [])}
        require({"handoff_ready", "current_code", "method_gates", "preview_loop", "bounded_confirm", "record_pressure", "server_shell_boundary"}.issubset(gate_ids), f"{adapter} gates missing: {gate_ids}", failures)
        commands = item.get("commands") or {}
        require(str(commands.get("handoff") or "").startswith(f"agentops operator agent-loop-handoff --adapter {adapter}"), f"{adapter} handoff command missing: {commands}", failures)
        require(str(commands.get("start_check") or "").startswith(f"agentops operator start-check --adapter {adapter}"), f"{adapter} start-check command missing: {commands}", failures)
        require(str(commands.get("preview_loop") or "").startswith(f"agentops operator loop-driver --adapter {adapter}"), f"{adapter} preview command missing: {commands}", failures)
        require("--confirm-loop" in str(commands.get("confirm_loop") or ""), f"{adapter} confirm-loop command missing: {commands}", failures)
        require(str(commands.get("record_review") or "").startswith("agentops review queue"), f"{adapter} record command missing: {commands}", failures)
        require(commands.get("recommended_next"), f"{adapter} recommended command missing: {commands}", failures)
        run_start_admission = item.get("run_start_admission") or {}
        require(run_start_admission.get("operation") == "operator_loop_supervision_run_start_admission", f"{adapter} run_start admission operation missing: {run_start_admission}", failures)
        require(run_start_admission.get("gateway_endpoint") == "POST /api/agent-gateway/runs/start", f"{adapter} gateway endpoint missing: {run_start_admission}", failures)
        require(run_start_admission.get("governed_runtime") is True, f"{adapter} governed runtime missing: {run_start_admission}", failures)
        require(run_start_admission.get("would_allow_run_start") is True, f"{adapter} run_start should be structurally allowed: {run_start_admission}", failures)
        require(run_start_admission.get("would_block_run_start") is False, f"{adapter} run_start block projection drifted: {run_start_admission}", failures)
        require(run_start_admission.get("fail_closed_error") == "run_start_loop_supervision_blocked", f"{adapter} fail-closed error missing: {run_start_admission}", failures)
        require(run_start_admission.get("no_run_created_on_block") is True, f"{adapter} no-run-on-block proof missing: {run_start_admission}", failures)
        require(run_start_admission.get("agent_plan_required") is True, f"{adapter} Agent Plan precondition missing: {run_start_admission}", failures)
        require(run_start_admission.get("supervision_hash_state") == "bound_by_agent_gateway_run_start", f"{adapter} hash binding state missing: {run_start_admission}", failures)
        run_start_safety = run_start_admission.get("safety") or {}
        require(run_start_safety.get("read_only") is True, f"{adapter} run_start admission read-only proof missing: {run_start_safety}", failures)
        require(run_start_safety.get("ledger_mutated") is False, f"{adapter} run_start admission ledger proof missing: {run_start_safety}", failures)
        require(run_start_safety.get("live_execution_performed") is False, f"{adapter} run_start admission live proof missing: {run_start_safety}", failures)
        require(run_start_safety.get("server_executes_shell") is False, f"{adapter} run_start admission shell proof missing: {run_start_safety}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-loop-supervision-") as tmp:
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
            http_status, http_payload = http_json(base_url, "/api/operator/loop-supervision?limit=5")
            outputs.append(json.dumps(http_payload, ensure_ascii=False))
            require(http_status == 200, f"HTTP loop-supervision status {http_status}: {http_payload}", failures)
            validate(http_payload, failures)
            cli_env = env.copy()
            cli_env["AGENTOPS_BASE_URL"] = base_url
            result = subprocess.run(
                [str(CLI), "operator", "loop-supervision", "--limit", "5"],
                cwd=ROOT,
                env=cli_env,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
            outputs.extend([result.stdout, result.stderr])
            require(result.returncode == 0, f"loop-supervision CLI failed: {result.stderr or result.stdout}", failures)
            cli_payload = json.loads(result.stdout or "{}")
            validate(cli_payload, failures)
            require(cli_payload.get("summary") == http_payload.get("summary"), f"CLI/HTTP summary drift: cli={cli_payload.get('summary')} http={http_payload.get('summary')}", failures)
            after = db_counts(db_path)
            require(before == after, f"loop-supervision mutated ledger: before={before} after={after}", failures)
            require(not leaked("\n".join(outputs)), "loop-supervision leaked token-like material", failures)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_loop_supervision_smoke",
        "failures": failures,
        "secret_leaked": leaked("\n".join(outputs)),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or leaked("\n".join(outputs)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
