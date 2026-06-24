#!/usr/bin/env python3
"""Verify loop-bootstrap API and AI Employees UI contract."""
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
SERVER = ROOT / "server.py"
AI_EMPLOYEES = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "AIEmployees.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_-]{16,}"),
    re.compile(r"agtsess_[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ntn_[A-Za-z0-9_-]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


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
    env["HERMES_GATEWAY_URL"] = "http://127.0.0.1:9/v1?api_key=loop-bootstrap-api-fixture"
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


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(base_url + path, timeout=20) as resp:
        text = resp.read().decode("utf-8")
        return int(resp.status), json.loads(text or "{}")


def fingerprint(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        return {
            "audit_logs": int(conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0] or 0),
            "runtime_events": int(conn.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0] or 0),
            "operator_action_receipts": int(
                conn.execute(
                    "SELECT COUNT(*) FROM audit_logs WHERE action='operator.action_queue_receipt' AND entity_type='operator_action_receipts'"
                ).fetchone()[0] or 0
            ),
        }


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def validate_payload(payload: dict, failures: list[str], *, expected_adapters: set[str]) -> None:
    require(payload.get("provider") == "agentops-operator", f"provider mismatch: {payload}", failures)
    require(payload.get("operation") == "operator_loop_bootstrap", f"operation mismatch: {payload}", failures)
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"status mismatch: {payload}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"read-only proof missing: {payload}", failures)
    require(safety.get("ledger_mutated") is False, f"ledger mutation proof missing: {payload}", failures)
    require(safety.get("server_executes_shell") is False, f"server shell proof missing: {payload}", failures)
    require(safety.get("live_execution_performed") is False, f"live boundary missing: {payload}", failures)
    require(safety.get("local_cli_service_check_performed") is False, f"API must not run service-check: {payload}", failures)
    items = payload.get("items") or []
    adapters = {item.get("adapter") for item in items if isinstance(item, dict)}
    require(adapters == expected_adapters, f"adapter set mismatch {adapters} != {expected_adapters}: {payload}", failures)
    for item in items:
        commands = item.get("commands") or {}
        steps = item.get("bootstrap_steps") or []
        step_ids = {step.get("id") for step in steps if isinstance(step, dict)}
        for command_key in [
            "start_check",
            "service_install_preview",
            "service_install_confirm",
            "service_check",
            "service_closure_record",
            "service_control_load_confirm",
            "loop_driver_auto_service_closure",
            "loop_bootstrap_cli",
            "loop_bootstrap_cli_with_service_check",
        ]:
            require(commands.get(command_key), f"{item.get('adapter')} missing command {command_key}: {item}", failures)
        for step_id in {
            "read_start_check",
            "verify_current_code",
            "preview_service_install",
            "confirm_service_install",
            "run_service_check",
            "record_service_closure",
            "confirm_service_activation",
            "confirm_bounded_loop",
        }:
            require(step_id in step_ids, f"{item.get('adapter')} missing step {step_id}: {item}", failures)
        require("--confirm-install" in str(commands.get("service_install_confirm")), f"{item.get('adapter')} install confirm missing", failures)
        require("--run-service-check" in str(commands.get("service_closure_record")), f"{item.get('adapter')} closure auto-check missing", failures)
        require("--auto-service-closure" in str(commands.get("loop_driver_auto_service_closure")), f"{item.get('adapter')} loop auto service closure missing", failures)
        item_safety = item.get("safety") or {}
        require(item_safety.get("read_only") is True, f"{item.get('adapter')} item read-only proof missing", failures)
        require(item_safety.get("server_executes_shell") is False, f"{item.get('adapter')} item server shell proof missing", failures)
        require((item.get("service_check") or {}).get("performed") is False, f"{item.get('adapter')} API service-check should be false", failures)


def validate_static_ui(failures: list[str]) -> None:
    ai = AI_EMPLOYEES.read_text(encoding="utf-8")
    live = LIVE_API.read_text(encoding="utf-8")
    server = SERVER.read_text(encoding="utf-8")
    expected = {
        "api_route": (server, 'path == "/api/operator/loop-bootstrap"'),
        "server_projection": (server, "def operator_loop_bootstrap("),
        "live_loader": (live, "loadOperatorLoopBootstrap"),
        "live_endpoint": (live, "/operator/loop-bootstrap?${params.toString()}"),
        "live_type": (live, "OperatorLoopBootstrapPayload"),
        "ui_import": (ai, "loadOperatorLoopBootstrap"),
        "ui_loader": (ai, 'id: "operator_loop_bootstrap", load: async () => ({ operatorLoopBootstrap: await loadOperatorLoopBootstrap(8) })'),
        "ui_panel": (ai, 'data-testid="operator-loop-bootstrap-panel"'),
        "ui_item": (ai, 'data-testid="operator-loop-bootstrap-item"'),
        "ui_steps": (ai, 'data-testid="operator-loop-bootstrap-steps"'),
        "ui_no_server_shell": (ai, 'operatorLoopBootstrap.safety.server_executes_shell ? "blocked" : "pass"'),
        "ui_copy_only": (ai, 'operatorLoopBootstrap.safety.local_cli_service_check_performed ? "attention" : "pass"'),
    }
    for name, (text, marker) in expected.items():
        require(marker in text, f"{name}: missing marker {marker}", failures)
    require(not leaked(ai), "AI Employees contains token-like material", failures)
    require(not leaked(live), "liveApi contains token-like material", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    validate_static_ui(failures)
    with tempfile.TemporaryDirectory(prefix="agentops-loop-bootstrap-api-ui-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        proc = start_server(db_path, port, tmp_path / "server.log")
        try:
            wait_for_server(base_url)
            before = fingerprint(db_path)
            status, payload = http_json(base_url, "/api/operator/loop-bootstrap?limit=5")
            outputs.append(json.dumps(payload, ensure_ascii=False))
            after = fingerprint(db_path)
            require(status == 200, f"loop-bootstrap API status {status}: {payload}", failures)
            validate_payload(payload, failures, expected_adapters={"hermes", "openclaw"})
            require(before == after, f"loop-bootstrap API mutated ledger: {before} -> {after}", failures)

            before_single = fingerprint(db_path)
            single_status, single = http_json(base_url, "/api/operator/loop-bootstrap?adapter=hermes&manager=systemd&limit=5")
            outputs.append(json.dumps(single, ensure_ascii=False))
            after_single = fingerprint(db_path)
            require(single_status == 200, f"single adapter API status {single_status}: {single}", failures)
            validate_payload(single, failures, expected_adapters={"hermes"})
            require(before_single == after_single, f"single adapter API mutated ledger: {before_single} -> {after_single}", failures)
            item = (single.get("items") or [{}])[0]
            require(item.get("manager") == "systemd", f"manager rewrite missing: {item}", failures)
            require("--manager systemd" in str((item.get("commands") or {}).get("service_check")), f"systemd service-check command missing: {item}", failures)
        finally:
            stop_server(proc)
    combined = "\n".join(outputs)
    require(not leaked(combined), "secret-like value leaked in loop-bootstrap API output", failures)
    result = {
        "ok": not failures,
        "operation": "operator_loop_bootstrap_api_ui_smoke",
        "failures": failures,
        "secret_leaked": leaked(combined),
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "token_omitted": True,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
