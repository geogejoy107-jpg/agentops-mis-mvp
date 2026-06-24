#!/usr/bin/env python3
"""Verify operator loop-bootstrap produces a safe local service/loop startup packet."""
from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
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
    fake_key = "sk-" + "LOOPBOOTSTRAPSECRET123"
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


def run_cli(args: list[str], base_url: str, outputs: list[str], timeout: int = 60, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env.pop("AGENTOPS_API_KEY", None)
    env.pop("AGENTOPS_AGENT_ID", None)
    if extra_env:
        env.update(extra_env)
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
            "runtime_events": int(conn.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0] or 0),
        }


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def write_launchd_service_fixture(path: Path, adapter: str, base_url: str) -> None:
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.agentops.worker.{adapter}</string>
  <key>ProgramArguments</key>
  <array>
    <string>agentops-worker</string>
    <string>--adapter</string>
    <string>{adapter}</string>
    <string>--confirm-run</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>AGENTOPS_BASE_URL</key>
    <string>{base_url}</string>
  </dict>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
""",
        encoding="utf-8",
    )


class LegacyBootstrapHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        if self.path.startswith("/api/operator/start-check"):
            payload = {
                "operation": "operator_start_check",
                "status": "attention",
                "local_loop_admission_packet": {
                    "operation": "operator_local_loop_admission_packet",
                    "admission": {"current_code_ok": False},
                    "commands": {"current_code_check": "agentops local readiness --require-current-code"},
                },
                "acceptance_packet": {
                    "decision": {"can_confirm_bounded_loop": False},
                    "safety": {"server_executes_shell": False, "token_omitted": True},
                },
                "token_omitted": True,
            }
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if self.path.startswith("/api/operator/loop-supervision"):
            payload = {"error": "unknown endpoint"}
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if self.path == "/api/agent-gateway/status":
            payload = {"status": "ready", "auth": {"mode": "local_dev_no_token"}, "token_omitted": True}
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if self.path == "/api/local/readiness":
            payload = {
                "operation": "local_readiness",
                "status": "attention",
                "running_instance": {"status": "stale", "current": False},
                "token_omitted": True,
            }
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        self.send_response(404)
        self.end_headers()


def validate_stale_endpoint(payload: dict, failures: list[str]) -> None:
    require(payload.get("operation") == "operator_loop_bootstrap", f"stale endpoint operation mismatch: {payload}", failures)
    require(payload.get("status") == "blocked", f"stale endpoint should block: {payload}", failures)
    require(payload.get("error_type") == "stale_server_or_missing_endpoint", f"stale endpoint error type missing: {payload}", failures)
    require(payload.get("missing_endpoint") == "/api/operator/loop-supervision", f"missing endpoint mismatch: {payload}", failures)
    diagnostic = payload.get("diagnostic") or {}
    require("local_demo_probe" in diagnostic, f"local demo probe missing: {payload}", failures)
    require("repair_commands" in diagnostic and diagnostic["repair_commands"], f"repair commands missing: {payload}", failures)
    commands = payload.get("commands") or {}
    require("local readiness --require-current-code" in str(commands.get("current_code_check")), f"current-code command missing: {payload}", failures)
    steps = payload.get("bootstrap_steps") or []
    require({step.get("id") for step in steps} >= {"verify_current_code", "restart_current_mis", "retry_loop_bootstrap"}, f"recovery steps missing: {payload}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"stale endpoint read-only proof missing: {payload}", failures)
    require(safety.get("ledger_mutated") is False, f"stale endpoint ledger proof missing: {payload}", failures)
    require(safety.get("server_executes_shell") is False, f"stale endpoint shell proof missing: {payload}", failures)
    require(safety.get("live_execution_performed") is False, f"stale endpoint live proof missing: {payload}", failures)
    require(payload.get("token_omitted") is True, f"stale endpoint token proof missing: {payload}", failures)


def validate_bootstrap(payload: dict, adapter: str, failures: list[str], *, service_check_performed: bool) -> None:
    require(payload.get("provider") == "agentops-operator", f"{adapter} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "operator_loop_bootstrap", f"{adapter} operation mismatch: {payload}", failures)
    require(payload.get("adapter") == adapter, f"{adapter} adapter mismatch: {payload}", failures)
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"{adapter} status mismatch: {payload}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{adapter} read-only proof missing: {payload}", failures)
    require(safety.get("ledger_mutated") is False, f"{adapter} ledger mutation proof missing: {payload}", failures)
    require(safety.get("server_executes_shell") is False, f"{adapter} server shell proof missing: {payload}", failures)
    require(safety.get("live_execution_performed") is False, f"{adapter} live boundary missing: {payload}", failures)
    require(safety.get("local_cli_service_check_performed") is service_check_performed, f"{adapter} service-check flag mismatch: {payload}", failures)
    require(payload.get("live_execution_performed") is False, f"{adapter} top-level live flag mismatch: {payload}", failures)
    commands = payload.get("commands") or {}
    for key in [
        "start_check",
        "current_code_check",
        "service_install_preview",
        "service_install_confirm",
        "service_check",
        "service_closure_record",
        "service_control_load_confirm",
        "loop_driver_auto_service_closure",
        "loop_supervision",
    ]:
        require(commands.get(key), f"{adapter} command {key} missing: {payload}", failures)
    require("--confirm-install" in str(commands.get("service_install_confirm")), f"{adapter} install confirm missing: {commands}", failures)
    require("--run-service-check" in str(commands.get("service_closure_record")), f"{adapter} service closure auto-check missing: {commands}", failures)
    require("--confirm-record" in str(commands.get("service_closure_record")), f"{adapter} service closure confirm missing: {commands}", failures)
    require("--confirm-control" in str(commands.get("service_control_load_confirm")), f"{adapter} service load confirm missing: {commands}", failures)
    require("--auto-service-closure" in str(commands.get("loop_driver_auto_service_closure")), f"{adapter} auto service closure loop command missing: {commands}", failures)
    require("--confirm-loop" in str(commands.get("loop_driver_auto_service_closure")), f"{adapter} confirm loop missing: {commands}", failures)
    steps = payload.get("bootstrap_steps") or []
    step_ids = {step.get("id") for step in steps}
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
        require(step_id in step_ids, f"{adapter} bootstrap step {step_id} missing: {payload}", failures)
    require(all(step.get("token_omitted") is True for step in steps), f"{adapter} token proof missing in steps: {steps}", failures)
    service_check = payload.get("service_check") or {}
    require(service_check.get("performed") is service_check_performed, f"{adapter} service-check performed mismatch: {service_check}", failures)
    if service_check_performed:
        require(service_check.get("ok") is True, f"{adapter} service-check should pass fixture: {service_check}", failures)
        require(service_check.get("service_file_exists") is True, f"{adapter} service file proof missing: {service_check}", failures)
        require(service_check.get("service_loaded") in {True, False}, f"{adapter} service-loaded bool missing: {service_check}", failures)
    admission = payload.get("local_loop_admission_packet") or {}
    require(admission.get("operation") == "operator_local_loop_admission_packet", f"{adapter} admission packet missing: {payload}", failures)
    supervision = payload.get("supervision") or {}
    require(isinstance(supervision.get("primary_next_action") or {}, dict), f"{adapter} supervision primary action missing: {payload}", failures)
    require(payload.get("token_omitted") is True, f"{adapter} token omission missing: {payload}", failures)
    require("never mutates ledgers" in str(payload.get("contract") or ""), f"{adapter} contract missing safety boundary: {payload.get('contract')}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    legacy_port = free_port()
    legacy_url = f"http://127.0.0.1:{legacy_port}"
    legacy_server = ThreadingHTTPServer(("127.0.0.1", legacy_port), LegacyBootstrapHandler)
    legacy_thread = threading.Thread(target=legacy_server.serve_forever, daemon=True)
    legacy_thread.start()
    try:
        stale = run_cli(
            ["operator", "loop-bootstrap", "--adapter", "hermes", "--limit", "5", "--run-service-check"],
            legacy_url,
            outputs,
            extra_env={"AGENTOPS_LOCAL_DEMO_DEFAULT_URL": legacy_url},
        )
        stale_payload = load_json(stale.stdout)
        require(stale.returncode == 2, f"stale endpoint should return rc=2: rc={stale.returncode} stdout={stale.stdout} stderr={stale.stderr}", failures)
        validate_stale_endpoint(stale_payload, failures)
    finally:
        legacy_server.shutdown()
        legacy_server.server_close()
    with tempfile.TemporaryDirectory(prefix="agentops-loop-bootstrap-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        proc = start_server(db_path, port, tmp_path / "server.log")
        try:
            wait_for_server(base_url)
            for adapter in ("hermes", "openclaw"):
                before_preview = fingerprint(db_path)
                preview = run_cli(
                    ["operator", "loop-bootstrap", "--adapter", adapter, "--limit", "5"],
                    base_url,
                    outputs,
                )
                preview_payload = load_json(preview.stdout)
                after_preview = fingerprint(db_path)
                require(preview.returncode == 0, f"{adapter} loop-bootstrap preview failed: {preview.stderr or preview.stdout}", failures)
                validate_bootstrap(preview_payload, adapter, failures, service_check_performed=False)
                require(before_preview == after_preview, f"{adapter} preview mutated ledger: {before_preview} -> {after_preview}", failures)

                service_path = tmp_path / f"{adapter}-worker.plist"
                write_launchd_service_fixture(service_path, adapter, base_url)
                before_check = fingerprint(db_path)
                checked = run_cli(
                    [
                        "operator",
                        "loop-bootstrap",
                        "--adapter",
                        adapter,
                        "--limit",
                        "5",
                        "--run-service-check",
                        "--service-path",
                        str(service_path),
                    ],
                    base_url,
                    outputs,
                )
                checked_payload = load_json(checked.stdout)
                after_check = fingerprint(db_path)
                require(checked.returncode == 0, f"{adapter} loop-bootstrap check failed: {checked.stderr or checked.stdout}", failures)
                validate_bootstrap(checked_payload, adapter, failures, service_check_performed=True)
                require(before_check == after_check, f"{adapter} run-service-check mutated ledger: {before_check} -> {after_check}", failures)
                require(str(service_path) in str((checked_payload.get("commands") or {}).get("loop_driver_auto_service_closure")), f"{adapter} loop command missing service path: {checked_payload}", failures)
                require(str(service_path) in str((checked_payload.get("commands") or {}).get("service_closure_record")), f"{adapter} closure command missing service path: {checked_payload}", failures)
        finally:
            stop_server(proc)
    combined = "\n".join(outputs)
    require(not leaked(combined), "secret-like value leaked in loop-bootstrap output", failures)
    result = {
        "ok": not failures,
        "operation": "operator_loop_bootstrap_smoke",
        "failures": failures,
        "secret_leaked": leaked(combined),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
