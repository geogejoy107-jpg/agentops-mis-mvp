#!/usr/bin/env python3
"""Verify `agentops operator action-receipts` is read-only and redacted."""

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


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-action-receipts-cli-") as tmp:
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
            status, plan = http_json(base_url, "/api/operator/action-plan?limit=8")
            outputs.append(json.dumps(plan, ensure_ascii=False))
            require(status == 200, f"action-plan status mismatch: {status} {plan}", failures)
            action = next((item for item in plan.get("actions") or [] if item.get("receipt_required") is True), {})
            receipt_payload = {
                "action_command": action.get("command") or "agentops worker status",
                "verify_command": action.get("verify_command") or "agentops operator action-plan --limit 20",
                "action_id": action.get("action_id") or "smoke:cli-action",
                "action_signature": action.get("action_signature") or "smoke_cli_signature",
                "source": "smoke.operator_action_receipts_cli",
                "status": "verified",
                "result_summary": "Smoke verified CLI receipt readback.",
            }
            status, receipt = http_json(base_url, "/api/operator/action-receipts", "POST", receipt_payload)
            outputs.append(json.dumps(receipt, ensure_ascii=False))
            require(status == 201, f"receipt POST status mismatch: {status} {receipt}", failures)
            receipt_id = ((receipt.get("receipt") or {}).get("receipt_id"))
            require(bool(receipt_id), f"receipt_id missing: {receipt}", failures)
            before_cli = db_counts(db_path)
            cli_proc = subprocess.run(
                [str(CLI), "operator", "action-receipts", "--limit", "5", "--plan-limit", "8"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            outputs.extend([cli_proc.stdout, cli_proc.stderr])
            payload = load_json(cli_proc.stdout)
            after_cli = db_counts(db_path)
            require(cli_proc.returncode == 0, f"CLI failed: {cli_proc.returncode} {cli_proc.stderr}", failures)
            require(payload.get("operation") == "operator_action_receipts_cli", f"wrong CLI operation: {payload}", failures)
            require((payload.get("safety") or {}).get("read_only") is True, f"CLI safety read_only missing: {payload}", failures)
            require((payload.get("safety") or {}).get("ledger_mutated") is False, f"CLI should not mutate ledger: {payload}", failures)
            require(before_cli == after_cli, f"CLI mutated receipt ledger: {before_cli} -> {after_cli}", failures)
            require(receipt_id in {row.get("receipt_id") for row in payload.get("receipts") or []}, f"CLI receipt readback missing: {payload}", failures)
            coverage = payload.get("receipt_coverage") or {}
            require(isinstance(coverage.get("required"), int), f"coverage.required missing: {coverage}", failures)
            require(isinstance(coverage.get("verified"), int), f"coverage.verified missing: {coverage}", failures)
            require(coverage.get("status") in {"ready", "attention"}, f"coverage status wrong: {coverage}", failures)
            require(payload.get("action_plan_status") in {"ready", "attention", "blocked"}, f"action plan status missing: {payload}", failures)
            require("read-only" in (payload.get("contract") or ""), f"CLI contract missing: {payload}", failures)
            require(not leaked_secret("\n".join(outputs)), "CLI output leaked token-like material", failures)
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
        "operation": "operator_action_receipts_cli_smoke",
        "failures": failures,
        "secret_leaked": leaked_secret("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
