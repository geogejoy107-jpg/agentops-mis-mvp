#!/usr/bin/env python3
"""Dogfood the decision-gated loop-driver packet in an isolated local MIS.

This is a no-live-runtime product smoke: it proves Hermes/OpenClaw style
machine callers can consume the compact decision projection and loop-driver
packet from a real local server without scraping UI or executing adapters.
"""
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
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_-]{12,}"),
    re.compile(r"agtsess_[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ntn_[A-Za-z0-9_-]{16,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            with urllib.request.urlopen(base_url + "/api/local/readiness", timeout=1.5) as resp:
                payload = json.loads(resp.read().decode("utf-8") or "{}")
                if resp.status == 200 and payload.get("operation") == "local_readiness":
                    return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def start_server(db_path: Path, port: int, log_path: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    env["HERMES_GATEWAY_URL"] = "http://127.0.0.1:9/v1"
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
        cwd=ROOT,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._agentops_log_fh = log_fh  # type: ignore[attr-defined]
    return proc


def stop_server(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=8)
    log_fh = getattr(proc, "_agentops_log_fh", None)
    if log_fh:
        log_fh.close()


def run_cli(args: list[str], base_url: str, outputs: list[str]) -> dict:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    proc = subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    outputs.extend([proc.stdout, proc.stderr])
    if proc.returncode != 0:
        raise RuntimeError(f"agentops {' '.join(args)} failed: {proc.stderr or proc.stdout}")
    return json.loads(proc.stdout or "{}")


def db_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {
            "runs": int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] or 0),
            "audit_logs": int(conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] or 0),
            "runtime_events": int(conn.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0] or 0),
        }


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def validate_adapter(adapter: str, base_url: str, db_path: Path, outputs: list[str], failures: list[str]) -> dict:
    before = db_counts(db_path)
    decision = run_cli(["operator", "loop-supervision", "--adapter", adapter, "--limit", "5", "--decision"], base_url, outputs)
    driver = run_cli(["operator", "loop-driver", "--adapter", adapter, "--max-steps", "1", "--limit", "5"], base_url, outputs)
    after = db_counts(db_path)

    decisions = [item for item in (decision.get("decisions") or []) if item.get("adapter") == adapter]
    selected = decisions[0] if decisions else {}
    driver_gate = driver.get("work_packet_decision") or {}
    driver_selected = driver_gate.get("decision") or {}
    agent_packet = driver.get("agent_loop_packet") or {}
    commands = agent_packet.get("commands") or {}
    phase_commands = agent_packet.get("phase_commands") or {}

    require(before == after, f"{adapter} dogfood read path mutated DB: {before} -> {after}", failures)
    require(decision.get("operation") == "operator_loop_work_packet_decision", f"{adapter} decision operation mismatch: {decision}", failures)
    require(decision.get("schema_version") == "agent_work_packet_decision_v1", f"{adapter} decision schema mismatch: {decision}", failures)
    require((decision.get("summary") or {}).get("server_may_execute") is False, f"{adapter} decision server execution proof missing: {decision}", failures)
    require(selected.get("decision") not in {"stop", "blocked", "missing"}, f"{adapter} decision hard-blocked: {selected}", failures)
    require((selected.get("policy") or {}).get("server_may_execute") is False, f"{adapter} decision policy unsafe: {selected}", failures)
    require((selected.get("safety") or {}).get("live_execution_performed") is False, f"{adapter} decision live proof missing: {selected}", failures)
    require(driver.get("operation") == "operator_loop_driver", f"{adapter} driver operation mismatch: {driver}", failures)
    require(driver.get("status") == "preview", f"{adapter} driver should be preview-only: {driver}", failures)
    require((driver.get("safety") or {}).get("read_only") is True, f"{adapter} driver read-only proof missing: {driver}", failures)
    require((driver.get("safety") or {}).get("ledger_mutated") is False, f"{adapter} driver mutated ledger: {driver}", failures)
    require(driver_gate.get("operation") == "operator_loop_driver_work_packet_decision_gate", f"{adapter} driver decision gate missing: {driver}", failures)
    require(driver_gate.get("ok") is True, f"{adapter} driver decision gate blocked: {driver_gate}", failures)
    require(driver_selected.get("adapter") == adapter, f"{adapter} driver selected wrong decision: {driver_gate}", failures)
    require((driver_selected.get("policy") or {}).get("server_may_execute") is False, f"{adapter} driver decision policy unsafe: {driver_gate}", failures)
    require(agent_packet.get("operation") == "operator_loop_driver_agent_loop_packet", f"{adapter} agent packet missing: {driver}", failures)
    require(agent_packet.get("ready_to_confirm_loop") is True, f"{adapter} agent packet not confirm-ready: {agent_packet}", failures)
    require(str(commands.get("confirm_loop") or "").startswith(f"agentops operator loop-driver --adapter {adapter}"), f"{adapter} confirm command missing: {commands}", failures)
    require("--confirm-loop" in str(commands.get("confirm_loop") or ""), f"{adapter} confirm flag missing: {commands}", failures)
    require(str(phase_commands.get("execute") or "").startswith(f"agentops operator loop-driver --adapter {adapter}"), f"{adapter} execute phase missing: {phase_commands}", failures)
    require((agent_packet.get("safety") or {}).get("server_executes_shell") is False, f"{adapter} agent packet shell proof missing: {agent_packet}", failures)
    return {
        "decision": selected.get("decision"),
        "packet_hash": selected.get("packet_hash"),
        "confirm_loop": commands.get("confirm_loop"),
        "execute": phase_commands.get("execute"),
    }


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-loop-dogfood-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        proc = start_server(db_path, port, tmp_path / "server.log")
        try:
            wait_ready(base_url, proc)
            adapters = {
                adapter: validate_adapter(adapter, base_url, db_path, outputs, failures)
                for adapter in ["hermes", "openclaw"]
            }
        finally:
            stop_server(proc)

    serialized = "\n".join(outputs)
    require(not leaked(serialized), "dogfood output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_loop_driver_dogfood_smoke",
        "contract": "Hermes/OpenClaw style machine callers consume decision-gated loop-driver packets from a real isolated local MIS without live adapter execution.",
        "adapters": adapters if "adapters" in locals() else {},
        "failures": failures,
        "secret_leaked": leaked(serialized),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures and not leaked(serialized) else 1


if __name__ == "__main__":
    raise SystemExit(main())
