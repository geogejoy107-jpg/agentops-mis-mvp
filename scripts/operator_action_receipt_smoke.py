#!/usr/bin/env python3
"""Verify operator action queue receipts write runtime/audit evidence safely."""

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


def http_json(base_url: str, path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=30) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def db_counts(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        audit_row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt'"
        ).fetchone()
        runtime_row = conn.execute(
            "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type='operator.action_queue_receipt'"
        ).fetchone()
        return {"audit_logs": int(audit_row["c"] or 0), "runtime_events": int(runtime_row["c"] or 0)}
    finally:
        conn.close()


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _ = http_json(base_url, "/api/operator/action-receipts?limit=1")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-action-receipt-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
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
            payload = {
                "action_command": "agentops worker status",
                "verify_command": "agentops operator action-plan --limit 20",
                "action_id": "smoke:fleet:worker-status",
                "source": "smoke.operator_action_queue",
                "status": "verified",
                "result_summary": "Smoke verified action queue receipt recording.",
            }
            status, receipt = http_json(base_url, "/api/operator/action-receipts", "POST", payload)
            outputs.append(json.dumps(receipt, ensure_ascii=False))
            require(status == 201, f"POST status mismatch: {status} {receipt}", failures)
            require(receipt.get("operation") == "operator_action_receipt", f"wrong operation: {receipt}", failures)
            require(receipt.get("status") == "verified", f"wrong receipt status: {receipt}", failures)
            safety = receipt.get("safety") or {}
            require(safety.get("ledger_mutated") is True, f"receipt should mutate ledger: {safety}", failures)
            require(safety.get("live_execution_performed") is False, f"receipt must not execute live work: {safety}", failures)
            item = receipt.get("receipt") or {}
            require(bool(item.get("receipt_id")), f"receipt_id missing: {receipt}", failures)
            require(bool(item.get("audit_id")), f"audit_id missing: {receipt}", failures)
            require(bool(item.get("tamper_chain_hash")), f"tamper hash missing: {receipt}", failures)
            require(item.get("action_command") == payload["action_command"], f"action command mismatch: {item}", failures)
            require(item.get("verify_command") == payload["verify_command"], f"verify command mismatch: {item}", failures)
            require(bool(item.get("action_hash")), f"action hash missing: {item}", failures)
            require(bool(item.get("verify_hash")), f"verify hash missing: {item}", failures)

            status, readback = http_json(base_url, "/api/operator/action-receipts?limit=5")
            outputs.append(json.dumps(readback, ensure_ascii=False))
            require(status == 200, f"GET status mismatch: {status} {readback}", failures)
            require(readback.get("operation") == "operator_action_receipts", f"wrong readback operation: {readback}", failures)
            summary = readback.get("summary") or {}
            require(int(summary.get("verified") or 0) >= 1, f"verified count missing: {summary}", failures)
            receipt_ids = {row.get("receipt_id") for row in readback.get("receipts") or []}
            require(item.get("receipt_id") in receipt_ids, f"receipt missing from readback: {readback}", failures)

            after = db_counts(db_path)
            require(after["audit_logs"] == before["audit_logs"] + 1, f"audit count did not increase once: {before} -> {after}", failures)
            require(after["runtime_events"] == before["runtime_events"] + 1, f"runtime count did not increase once: {before} -> {after}", failures)
            require(not leaked_secret("\n".join(outputs)), "receipt output leaked token-like material", failures)
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
        "operation": "operator_action_receipt_smoke",
        "failures": failures,
        "secret_leaked": leaked_secret("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
