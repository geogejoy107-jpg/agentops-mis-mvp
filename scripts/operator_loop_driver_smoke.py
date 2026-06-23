#!/usr/bin/env python3
"""Verify the bounded multi-step operator loop driver."""

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
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(text: str) -> dict:
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/dashboard/metrics", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def start_server(db_path: Path, port: int, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    fake_key = "sk-" + "LOOPDRIVERSECRET123"
    env["HERMES_GATEWAY_URL"] = f"http://127.0.0.1:9/v1?api_key={fake_key}"
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


def stop_server(proc: subprocess.Popen) -> None:
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


def run_cli(args: list[str], base_url: str, outputs: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env.pop("AGENTOPS_API_KEY", None)
    env.pop("AGENTOPS_AGENT_ID", None)
    proc = subprocess.run([str(CLI), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def fingerprint(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        return {
            "audit_logs": int(conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] or 0),
            "operator_action_receipts": int(
                conn.execute(
                    "SELECT COUNT(*) FROM audit_logs WHERE action='operator.action_queue_receipt' AND entity_type='operator_action_receipts'"
                ).fetchone()[0] or 0
            ),
        }


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-loop-driver-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        proc = start_server(db_path, port, tmp_path / "server.log")
        try:
            wait_for_server(base_url)
            before_preview = fingerprint(db_path)
            preview = run_cli(
                ["operator", "loop-driver", "--adapter", "hermes", "--max-steps", "2", "--limit", "5"],
                base_url,
                outputs,
            )
            preview_payload = load_json(preview.stdout)
            after_preview = fingerprint(db_path)
            require(preview.returncode == 0, f"loop-driver preview failed: {preview.stderr or preview.stdout}", failures)
            require(preview_payload.get("operation") == "operator_loop_driver", f"preview operation mismatch: {preview_payload}", failures)
            require(preview_payload.get("status") == "preview", f"preview status mismatch: {preview_payload}", failures)
            require((preview_payload.get("safety") or {}).get("read_only") is True, f"preview should be read-only: {preview_payload}", failures)
            require((preview_payload.get("safety") or {}).get("ledger_mutated") is False, f"preview mutated ledger: {preview_payload}", failures)
            require(before_preview == after_preview, f"preview fingerprint changed: {before_preview} -> {after_preview}", failures)
            initial_brief = preview_payload.get("initial_brief") or {}
            preview_readiness = preview_payload.get("adapter_readiness") or {}
            preview_readiness_commands = preview_readiness.get("commands") or {}
            preview_gate = preview_readiness.get("gate") or {}
            preview_remediation = preview_readiness.get("remediation") or {}
            require(initial_brief.get("operation") == "operator_loop_launch_brief", f"initial brief missing: {initial_brief}", failures)
            require((initial_brief.get("policy") or {}).get("server_executes_shell") is False, f"brief server shell boundary missing: {initial_brief}", failures)
            require(preview_readiness.get("operation") == "operator_loop_driver_adapter_readiness", f"preview readiness missing: {preview_readiness}", failures)
            require(preview_readiness.get("adapter") == "hermes", f"preview readiness adapter mismatch: {preview_readiness}", failures)
            require((preview_readiness.get("safety") or {}).get("read_only") is True, f"preview readiness should be read-only: {preview_readiness}", failures)
            require(preview_readiness_commands.get("adapter_preflight") == "agentops worker preflight --adapter hermes", f"preview preflight command missing: {preview_readiness}", failures)
            require(preview_gate.get("loop_control_may_continue") is True, f"preview loop-control gate missing: {preview_readiness}", failures)
            require(preview_remediation.get("status") in {"ready", "action_required"}, f"preview remediation missing: {preview_readiness}", failures)
            require(any(command.get("phase") == "preflight" for command in (preview_remediation.get("commands") or [])), f"preview remediation preflight missing: {preview_readiness}", failures)
            require((preview_remediation.get("safety") or {}).get("server_executes_shell") is False, f"preview remediation server shell boundary missing: {preview_readiness}", failures)
            require("agentops worker preflight --adapter hermes" in (preview_payload.get("next_actions") or []), f"preview next actions missing preflight: {preview_payload}", failures)

            before_confirm = fingerprint(db_path)
            confirmed = run_cli(
                ["operator", "loop-driver", "--adapter", "openclaw", "--max-steps", "2", "--limit", "5", "--confirm-loop"],
                base_url,
                outputs,
                timeout=120,
            )
            confirmed_payload = load_json(confirmed.stdout)
            after_confirm = fingerprint(db_path)
            require(confirmed.returncode == 0, f"loop-driver confirm failed: {confirmed.stderr or confirmed.stdout}", failures)
            require(confirmed_payload.get("operation") == "operator_loop_driver", f"confirm operation mismatch: {confirmed_payload}", failures)
            require(confirmed_payload.get("status") in {"advanced", "empty"}, f"confirm status mismatch: {confirmed_payload}", failures)
            require((confirmed_payload.get("safety") or {}).get("live_execution_performed") is False, f"confirm should not run live work: {confirmed_payload}", failures)
            require((confirmed_payload.get("safety") or {}).get("server_executes_shell") is False, f"server shell boundary missing: {confirmed_payload}", failures)
            final_readiness = confirmed_payload.get("adapter_readiness") or {}
            final_remediation = final_readiness.get("remediation") or {}
            require(final_readiness.get("operation") == "operator_loop_driver_adapter_readiness", f"confirm readiness missing: {final_readiness}", failures)
            require(final_readiness.get("adapter") == "openclaw", f"confirm readiness adapter mismatch: {final_readiness}", failures)
            require((final_readiness.get("safety") or {}).get("live_execution_performed") is False, f"confirm readiness live execution boundary missing: {final_readiness}", failures)
            require(any("openclaw" in str(command.get("command") or "") for command in (final_remediation.get("commands") or [])), f"confirm remediation commands missing openclaw: {final_readiness}", failures)
            steps = confirmed_payload.get("steps") or []
            require(1 <= len(steps) <= 2, f"unexpected step count: {confirmed_payload}", failures)
            require(after_confirm["operator_action_receipts"] >= before_confirm["operator_action_receipts"] + 1, f"receipt count did not increase: {before_confirm} -> {after_confirm}", failures)
            for step in steps:
                advance = step.get("advance") or {}
                before_readiness = step.get("adapter_readiness_before") or {}
                after_readiness = step.get("adapter_readiness_after") or {}
                require(advance.get("operation") == "operator_advance_loop", f"step advance missing: {step}", failures)
                require(str(advance.get("action_command") or "").startswith("agentops "), f"step action command missing: {step}", failures)
                require(advance.get("receipt_status") in {"verified", "failed", None}, f"step receipt status wrong: {step}", failures)
                require(before_readiness.get("adapter") == "openclaw", f"step before readiness missing: {step}", failures)
                require(after_readiness.get("adapter") == "openclaw", f"step after readiness missing: {step}", failures)
                require((before_readiness.get("safety") or {}).get("server_executes_shell") is False, f"step readiness server shell boundary missing: {step}", failures)
                require(step.get("token_omitted") is True, f"step token omission missing: {step}", failures)
            final_brief = confirmed_payload.get("final_brief") or {}
            require(final_brief.get("operation") == "operator_loop_launch_brief", f"final brief missing: {final_brief}", failures)
            require((confirmed_payload.get("policy") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"policy missing: {confirmed_payload}", failures)
            require((confirmed_payload.get("policy") or {}).get("adapter_preflight_required_before_live_run") is True, f"adapter preflight policy missing: {confirmed_payload}", failures)
        finally:
            stop_server(proc)
    combined = "\n".join(outputs)
    require(not leaked(combined), "secret-like value leaked in loop-driver output", failures)
    result = {
        "ok": not failures,
        "operation": "operator_loop_driver_smoke",
        "failures": failures,
        "secret_leaked": leaked(combined),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
