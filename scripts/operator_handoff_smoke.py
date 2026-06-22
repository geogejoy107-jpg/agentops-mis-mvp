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


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = Request(base_url.rstrip("/") + path, headers={"Content-Type": "application/json"}, method="GET")
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
            after = db_fingerprint(db_path)
            require(before == after, f"handoff changed DB fingerprint: {before} -> {after}", failures)
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
