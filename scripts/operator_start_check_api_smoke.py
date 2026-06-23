#!/usr/bin/env python3
"""Smoke-test the read-only operator start-check API surface."""
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
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
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
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str, *, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    req = Request(base_url.rstrip("/") + path, headers=headers or {}, method="GET")
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


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def validate_payload(payload: dict, adapter: str, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-operator", f"{adapter} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "operator_start_check", f"{adapter} operation mismatch: {payload}", failures)
    require(payload.get("adapter") == adapter, f"{adapter} adapter mismatch: {payload.get('adapter')}", failures)
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"{adapter} bad status: {payload.get('status')}", failures)
    require(payload.get("token_omitted") is True, f"{adapter} token omission missing", failures)
    require(payload.get("live_execution_performed") is False, f"{adapter} must not execute live work", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{adapter} read_only safety missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{adapter} ledger_mutated must be false: {safety}", failures)
    require(safety.get("server_executes_shell") is False, f"{adapter} server shell must be false: {safety}", failures)
    require(safety.get("token_omitted") is True, f"{adapter} safety token proof missing: {safety}", failures)
    gates = payload.get("gates") or []
    gate_ids = {gate.get("id") for gate in gates}
    for gate_id in {
        "local_readiness",
        "worker_connection_policy",
        "adapter_preflight",
        "runtime_doctor",
        "loop_launch_brief",
        "loop_driver_entry",
        "local_run_path",
        "agent_plan_boundary",
        "live_product_readiness",
    }:
        require(gate_id in gate_ids, f"{adapter} missing gate {gate_id}: {gate_ids}", failures)
    for gate in gates:
        require(gate.get("token_omitted") is True, f"{adapter} gate token proof missing: {gate}", failures)
    worker_policy = payload.get("worker_connection_policy") or {}
    require(worker_policy.get("schema") == "agentops-worker-connection-policy-v1", f"{adapter} worker policy schema missing: {worker_policy}", failures)
    policy_safety = worker_policy.get("safety") if isinstance(worker_policy.get("safety"), dict) else {}
    policy_server_shell = worker_policy.get("server_executes_shell") if "server_executes_shell" in worker_policy else policy_safety.get("server_executes_shell")
    require(policy_server_shell is False, f"{adapter} worker policy server-shell proof missing: {worker_policy}", failures)
    local_run_path = payload.get("local_run_path") or {}
    steps = local_run_path.get("steps") or []
    require(len(steps) >= 8, f"{adapter} local run path too short: {local_run_path}", failures)
    require((local_run_path.get("safety") or {}).get("server_executes_shell") is False, f"{adapter} local run path safety missing", failures)
    launch_brief = payload.get("launch_brief") or {}
    require(launch_brief.get("operation") == "operator_loop_launch_brief", f"{adapter} launch brief missing: {launch_brief}", failures)
    require((launch_brief.get("safety") or {}).get("read_only") is True, f"{adapter} launch brief read-only proof missing: {launch_brief}", failures)
    loop_driver = payload.get("loop_driver_entry") or {}
    loop_commands = loop_driver.get("commands") or {}
    review_snapshot = loop_driver.get("review_snapshot") or {}
    review_summary = review_snapshot.get("summary") or {}
    require(loop_driver.get("operation") == "operator_start_check_loop_driver_entry", f"{adapter} loop driver entry missing: {loop_driver}", failures)
    require((loop_driver.get("safety") or {}).get("read_only") is True, f"{adapter} loop driver entry read-only proof missing: {loop_driver}", failures)
    require((loop_driver.get("safety") or {}).get("ledger_mutated") is False, f"{adapter} loop driver entry mutated ledger: {loop_driver}", failures)
    require((loop_driver.get("safety") or {}).get("server_executes_shell") is False, f"{adapter} loop driver entry server shell proof missing: {loop_driver}", failures)
    require(str(loop_commands.get("preview") or "").startswith(f"agentops operator loop-driver --adapter {adapter}"), f"{adapter} loop driver preview missing: {loop_driver}", failures)
    require(str(loop_commands.get("confirm_loop") or "").startswith(f"agentops operator loop-driver --adapter {adapter}"), f"{adapter} loop driver confirm missing: {loop_driver}", failures)
    require("--confirm-loop" in str(loop_commands.get("confirm_loop") or ""), f"{adapter} loop driver confirm flag missing: {loop_driver}", failures)
    require(str(loop_commands.get("review_queue") or "").startswith("agentops review queue"), f"{adapter} loop driver review command missing: {loop_driver}", failures)
    require(review_snapshot.get("operation") == "loop_driver_record_review_snapshot", f"{adapter} review snapshot missing: {loop_driver}", failures)
    require((review_snapshot.get("safety") or {}).get("read_only") is True, f"{adapter} review snapshot read-only proof missing: {loop_driver}", failures)
    require((review_snapshot.get("safety") or {}).get("ledger_mutated") is False, f"{adapter} review snapshot mutated ledger: {loop_driver}", failures)
    for key in ["review_items_total", "returned_items", "pending_approvals", "memory_candidates"]:
        require(isinstance(review_summary.get(key), int), f"{adapter} review summary {key} missing: {loop_driver}", failures)
    require(review_snapshot.get("summary_omitted") is True, f"{adapter} review summary omission proof missing: {loop_driver}", failures)
    require(review_snapshot.get("raw_content_omitted") is True, f"{adapter} review raw omission proof missing: {loop_driver}", failures)
    require(all(item.get("summary_omitted") is True and item.get("token_omitted") is True for item in (review_snapshot.get("items") or [])), f"{adapter} review items should be compact: {loop_driver}", failures)
    commands = payload.get("next_commands") or []
    require(any("operator loop-launch-packet" in str(command) for command in commands), f"{adapter} launch command missing: {commands}", failures)
    require(any("operator loop-driver" in str(command) for command in commands), f"{adapter} loop-driver command missing: {commands}", failures)
    require(any("review queue" in str(command) for command in commands), f"{adapter} review queue command missing: {commands}", failures)
    if adapter in {"hermes", "openclaw"}:
        summary = payload.get("summary") or {}
        require(summary.get("requires_confirm_run") is True, f"{adapter} confirm-run proof missing: {summary}", failures)
        require(any("--confirm-loop" in str(command) for command in commands), f"{adapter} confirm-loop command missing: {commands}", failures)
        live = payload.get("live_product_readiness") or {}
        require(live.get("operation") == "operator_live_product_readiness", f"{adapter} live readiness readback missing: {live}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-start-check-api-") as tmp:
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
            before = db_counts(db_path)
            checked = []
            for adapter in ("mock", "hermes", "openclaw"):
                query = urlencode({"adapter": adapter, "limit": "4"})
                status, payload = http_json(base_url, f"/api/operator/start-check?{query}")
                outputs.append(json.dumps(payload, ensure_ascii=False))
                require(status == 200, f"{adapter} API status mismatch: {status} {payload}", failures)
                validate_payload(payload, adapter, failures)
                checked.append({"adapter": adapter, "status": payload.get("status")})
            after = db_counts(db_path)
            require(before == after, f"operator start-check API mutated ledger counts: before={before} after={after}", failures)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
            if proc.stdout:
                outputs.append(proc.stdout.read() or "")
            if proc.stderr:
                outputs.append(proc.stderr.read() or "")
    require(not leaked_secret("\n".join(outputs)), "operator start-check API leaked token-like material", failures)
    if failures:
        print(json.dumps({"ok": False, "failures": failures}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "operation": "operator_start_check_api_smoke",
        "checked": checked,
        "ledger_mutated": False,
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
