#!/usr/bin/env python3
"""Verify Research Lab packet consumption records governance evidence only."""

from __future__ import annotations

import argparse
import datetime as dt
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
    re.compile(r"Bearer\s+(?!\[REDACTED\])[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"agtok_[A-Za-z0-9_-]{16,}"),
    re.compile(r"agtsess_[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ntn_[A-Za-z0-9_-]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(raw: str) -> dict:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def http_json(base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json", "X-AgentOps-Workspace-Id": "local-demo"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return res.status, load_json(raw)
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, load_json(raw) or {"raw": raw}


def run_cli(base_url: str, env: dict, args: list[str]) -> subprocess.CompletedProcess[str]:
    cli_env = env.copy()
    cli_env["AGENTOPS_BASE_URL"] = base_url
    cli_env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=cli_env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def wait_ready(base_url: str, proc: subprocess.Popen[str] | None = None) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _ = http_json(base_url, "/api/agent-gateway/status")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_fingerprint(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            "memories",
            "audit_logs",
            "runtime_events",
            "operator_action_evaluations",
            "tasks",
            "runs",
            "tool_calls",
            "approvals",
            "artifacts",
        ]
        result = {}
        for table in tables:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return result
    finally:
        conn.close()


def validate_preview(payload: dict, label: str, adapter: str, failures: list[str]) -> str:
    require(payload.get("operation") == "operator_research_lab_consumption", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") == "preview", f"{label} status mismatch: {payload}", failures)
    require(payload.get("recorded") is False, f"{label} should not be recorded: {payload}", failures)
    require(payload.get("adapter") == adapter, f"{label} adapter mismatch: {payload}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read_only missing: {safety}", failures)
    for key in ["ledger_mutated", "live_execution_performed", "server_executes_shell", "ssh_command_executed", "network_probe_performed"]:
        require(safety.get(key) is False, f"{label} should be false for {key}: {safety}", failures)
    packet = payload.get("packet") or {}
    packet_hash = str(packet.get("packet_hash") or "")
    require(bool(packet_hash), f"{label} packet hash missing: {packet}", failures)
    command = str(packet.get("action_command") or "")
    require(f"agentops operator loop-supervision --adapter {adapter}" in command, f"{label} action command missing loop supervision: {command}", failures)
    require("--work-packet" in command, f"{label} action command missing work packet: {command}", failures)
    verify = str(packet.get("verify_command") or "")
    require("scripts/operator_research_lab_packet_smoke.py" in verify, f"{label} verify command missing packet smoke: {verify}", failures)
    packet_safety = packet.get("safety") or {}
    require(packet_safety.get("research_lab_read_only") is True, f"{label} embedded packet not read-only: {packet_safety}", failures)
    for key in ["server_executes_shell", "ssh_command_executed", "network_probe_performed"]:
        require(packet_safety.get(key) is False, f"{label} embedded packet should not do {key}: {packet_safety}", failures)
    require(not leaked(json.dumps(payload, ensure_ascii=False)), f"{label} leaked secret-like text", failures)
    return packet_hash


def validate_recorded(payload: dict, packet_hash: str, failures: list[str]) -> None:
    require(payload.get("operation") == "operator_research_lab_consumption", f"record operation mismatch: {payload}", failures)
    require(payload.get("status") == "recorded", f"record status mismatch: {payload}", failures)
    require(payload.get("recorded") is True, f"recorded flag mismatch: {payload}", failures)
    require(payload.get("review_status") == "candidate", f"memory review status mismatch: {payload}", failures)
    require(payload.get("memory_id", "").startswith("mem_"), f"memory id missing: {payload}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is False, f"record safety read_only mismatch: {safety}", failures)
    require(safety.get("ledger_mutated") is True, f"record safety ledger mismatch: {safety}", failures)
    for key in ["live_execution_performed", "server_executes_shell", "ssh_command_executed", "network_probe_performed"]:
        require(safety.get(key) is False, f"record should not do {key}: {safety}", failures)
    receipt = payload.get("receipt") or {}
    require(receipt.get("status") == "verified", f"receipt should be verified: {receipt}", failures)
    require(receipt.get("source") == "operator.research_lab_consumption:openclaw", f"receipt source mismatch: {receipt}", failures)
    require(receipt.get("action_id") == "research_lab_packet_consumption:openclaw", f"receipt action id mismatch: {receipt}", failures)
    require((payload.get("packet") or {}).get("packet_hash") == packet_hash, f"recorded packet hash drifted: {payload}", failures)
    require(not leaked(json.dumps(payload, ensure_ascii=False)), "recorded response leaked secret-like text", failures)


def validate_loop_consumed(payload: dict, packet_hash: str, failures: list[str]) -> None:
    require(payload.get("operation") == "operator_loop_work_packet_bundle", f"loop bundle operation mismatch: {payload}", failures)
    summary = payload.get("summary") or {}
    require(summary.get("research_lab_consumptions") == 1, f"loop bundle consumption summary missing: {summary}", failures)
    require(summary.get("research_lab_consumed") == 1, f"loop bundle should read back one consumed packet: {summary}", failures)
    require(summary.get("research_lab_consumption_missing") == 0, f"loop bundle should not report missing consumption after confirm: {summary}", failures)
    packets = payload.get("work_packets") or []
    require(len(packets) == 1, f"expected one adapter work packet: {payload}", failures)
    packet = packets[0] if packets else {}
    contract = (packet.get("evidence_contract") or {}).get("research_lab_consumption") or {}
    require(contract.get("status") == "consumed", f"consumption contract should be consumed: {contract}", failures)
    require(contract.get("consumed") is True, f"consumption contract consumed flag missing: {contract}", failures)
    require(contract.get("packet_hash") == packet_hash, f"consumption contract hash mismatch: {contract}", failures)
    require(contract.get("receipt_verified") is True, f"consumption receipt should be verified: {contract}", failures)
    require(contract.get("evaluation_pass") is True, f"consumption evaluation should pass: {contract}", failures)
    require(contract.get("memory_recorded") is True, f"consumption memory readback missing: {contract}", failures)
    require(contract.get("server_executes_shell") is False, f"consumption contract shell proof missing: {contract}", failures)
    gate = next((item for item in (packet.get("gates") or []) if item.get("id") == "research_lab_consumption"), {})
    require(gate.get("status") == "pass" and gate.get("ok") is True, f"work packet consumption gate should pass: {gate}", failures)
    require(not leaked(json.dumps(payload, ensure_ascii=False)), "loop consumption readback leaked secret-like text", failures)


def validate_ledger(db_path: Path, before: dict, after: dict, failures: list[str]) -> None:
    for table in ["memories", "audit_logs", "runtime_events", "operator_action_evaluations"]:
        require(after.get(table, 0) > before.get(table, 0), f"{table} did not increase: before={before} after={after}", failures)
    for table in ["tasks", "runs", "tool_calls", "approvals", "artifacts"]:
        require(after.get(table, 0) == before.get(table, 0), f"{table} should not change: before={before} after={after}", failures)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        memory = conn.execute(
            "SELECT * FROM memories WHERE source_ref LIKE 'research_lab_packet://%' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        require(memory is not None, "memory candidate row missing", failures)
        if memory is not None:
            require(memory["review_status"] == "candidate", f"memory should remain candidate: {dict(memory)}", failures)
        audit_row = conn.execute(
            "SELECT * FROM audit_logs WHERE action='operator.research_lab_consumption' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        require(audit_row is not None, "research lab consumption audit row missing", failures)
        event = conn.execute(
            "SELECT * FROM runtime_events WHERE event_type='operator.research_lab_consumption' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        require(event is not None, "research lab consumption runtime event missing", failures)
    finally:
        conn.close()


def exercise(base_url: str, env: dict, failures: list[str], db_path: Path | None = None) -> None:
    before_preview = db_fingerprint(db_path) if db_path else None
    status, preview = http_json(base_url, "/api/operator/research-lab-consumption", {"adapter": "openclaw", "limit": 8, "profile": "lab-gpu-01"})
    require(status == 200, f"preview status {status}: {preview}", failures)
    packet_hash = validate_preview(preview, "api-preview", "openclaw", failures)
    if db_path:
        after_preview = db_fingerprint(db_path)
        require(before_preview == after_preview, f"preview mutated ledger: before={before_preview} after={after_preview}", failures)
    before_mismatch = db_fingerprint(db_path) if db_path else None
    mismatch_status, mismatch = http_json(
        base_url,
        "/api/operator/research-lab-consumption",
        {"adapter": "openclaw", "limit": 8, "packet_hash": "bad-hash", "confirm_record": True},
    )
    require(mismatch_status == 409, f"hash mismatch should fail closed: {mismatch_status} {mismatch}", failures)
    require(mismatch.get("recorded") is False and mismatch.get("status") == "blocked", f"hash mismatch body wrong: {mismatch}", failures)
    if db_path:
        after_mismatch = db_fingerprint(db_path)
        require(before_mismatch == after_mismatch, f"hash mismatch mutated ledger: before={before_mismatch} after={after_mismatch}", failures)
    before_record = db_fingerprint(db_path) if db_path else None
    cli = run_cli(
        base_url,
        env,
        [
            "operator",
            "research-lab-consumption",
            "--adapter",
            "openclaw",
            "--limit",
            "8",
            "--profile",
            "lab-gpu-01",
            "--packet-hash",
            packet_hash,
            "--confirm-record",
        ],
    )
    require(cli.returncode == 0, f"CLI confirm failed: stdout={cli.stdout} stderr={cli.stderr}", failures)
    require(not leaked(cli.stdout + cli.stderr), "CLI confirm leaked secret-like text", failures)
    recorded = load_json(cli.stdout)
    validate_recorded(recorded, packet_hash, failures)
    loop_cli = run_cli(base_url, env, ["operator", "loop-supervision", "--adapter", "openclaw", "--limit", "8", "--work-packet"])
    require(loop_cli.returncode == 0, f"loop-supervision readback failed: stdout={loop_cli.stdout} stderr={loop_cli.stderr}", failures)
    require(not leaked(loop_cli.stdout + loop_cli.stderr), "loop-supervision readback leaked secret-like text", failures)
    validate_loop_consumed(load_json(loop_cli.stdout), packet_hash, failures)
    if db_path:
        after_record = db_fingerprint(db_path)
        validate_ledger(db_path, before_record or {}, after_record, failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    parser.add_argument("--db-path", default="")
    args = parser.parse_args()
    failures: list[str] = []
    if args.base_url:
        base_url = args.base_url.rstrip("/")
        wait_ready(base_url)
        db_path = Path(args.db_path) if args.db_path else None
        exercise(base_url, os.environ.copy(), failures, db_path=db_path)
    else:
        with tempfile.TemporaryDirectory(prefix="agentops-research-lab-consumption-") as tmp:
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
                exercise(base_url, env, failures, db_path=db_path)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
    if failures:
        print(json.dumps({"ok": False, "operation": "operator_research_lab_consumption_smoke", "failures": failures}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "operation": "operator_research_lab_consumption_smoke", "stamp": now_stamp()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
