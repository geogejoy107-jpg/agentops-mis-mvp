#!/usr/bin/env python3
"""Verify customer-worker Hermes retry wiring with a local OpenAI-compatible gateway.

This smoke does not call the real Hermes daemon and is not product-readiness
proof. It exercises the real customer-worker -> worker process -> Hermes
adapter HTTP path against a deterministic loopback gateway that fails the first
chat-completions request and succeeds the second one.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_EXPORTS = [
    ROOT / "artifacts" / "sample_export_runs.json",
    ROOT / "artifacts" / "sample_export_memories.json",
]


def free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class TransientHermesHandler(BaseHTTPRequestHandler):
    request_count = 0

    def log_message(self, _fmt: str, *_args) -> None:
        return

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
        TransientHermesHandler.request_count += 1
        if TransientHermesHandler.request_count == 1:
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        _raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        payload = {
            "id": "chatcmpl-agentops-retry-smoke",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hermes retry smoke completed after a transient gateway disconnect.",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"completion_tokens": 12, "prompt_tokens": 24, "total_tokens": 36},
        }
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_fake_hermes(port: int) -> ThreadingHTTPServer:
    TransientHermesHandler.request_count = 0
    httpd = ThreadingHTTPServer(("127.0.0.1", port), TransientHermesHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def snapshot_files(paths: list[Path]) -> dict[Path, bytes | None]:
    snapshot: dict[Path, bytes | None] = {}
    for path in paths:
        snapshot[path] = path.read_bytes() if path.exists() else None
    return snapshot


def restore_files(snapshot: dict[Path, bytes | None]) -> None:
    for path, data in snapshot.items():
        if data is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def wait_for_server(base_url: str, proc: subprocess.Popen[str]) -> None:
    last_error = ""
    for _ in range(80):
        if proc.poll() is not None:
            raise RuntimeError(f"MIS server exited early with code {proc.returncode}")
        try:
            status, payload = http_json("GET", base_url, "/api/workers/status", timeout=2)
            if status == 200 and payload.get("provider") == "agentops-worker":
                return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"MIS server did not become ready: {last_error}")


def parse_tool_args(tool_call: dict) -> dict:
    raw = tool_call.get("normalized_args_json") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def token_like_leaked(payload: object) -> bool:
    return bool(re.search(r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,})", json.dumps(payload, ensure_ascii=False)))


def record_loopback_service_closure(base_url: str, failures: list[str]) -> dict:
    action_command = "agentops worker service-control --manager launchd --action restart --adapter hermes --agent-id agt_worker_daemon_hermes"
    verify_command = "agentops worker service-check --manager launchd --adapter hermes --agent-id agt_worker_daemon_hermes"
    receipt_status, receipt_payload = http_json(
        "POST",
        base_url,
        "/api/operator/action-receipts",
        {
            "workspace_id": "local-demo",
            "actor_id": "usr_retry_gateway_smoke",
            "action_command": action_command,
            "verify_command": verify_command,
            "action_id": "local_readiness.service_control_preview.hermes",
            "source": "local_readiness.service_control_preview.hermes",
            "status": "verified",
            "result_summary": "Hermes retry loopback service-control preview inspected and service-check readback recorded.",
        },
        timeout=30,
    )
    receipt = receipt_payload.get("receipt") or {}
    receipt_id = receipt.get("receipt_id")
    require(receipt_status == 201 and bool(receipt_id), f"service closure receipt failed: {receipt_status} {receipt_payload}", failures)
    if not receipt_id:
        return {"receipt": receipt_payload}
    readback_status, readback_payload = http_json(
        "POST",
        base_url,
        "/api/operator/action-receipts/control-readback",
        {
            "workspace_id": "local-demo",
            "actor_id": "usr_retry_gateway_smoke",
            "receipt_id": receipt_id,
            "source": "local_readiness.service_control_preview.hermes.control_readback",
            "control_readback": {
                "before": {
                    "step_id": "preview_worker_service_control",
                    "status": "preview",
                    "adapter": "hermes",
                    "service_control_preview": True,
                },
                "after": {
                    "verify_command": verify_command,
                    "service_check_expected": True,
                    "service_check_ok": True,
                    "service_file_exists": True,
                    "service_loaded": True,
                    "confirm_gate_ok": True,
                    "relaunch_policy_ok": True,
                    "confirmed_os_mutation": False,
                    "loopback_fixture": True,
                },
                "self_check": {
                    "copy_only": True,
                    "server_executes_shell": False,
                    "writes_ledger_for_service_control": False,
                    "live_execution_performed": False,
                    "token_omitted": True,
                },
                "token_omitted": True,
            },
        },
        timeout=30,
    )
    require(readback_status == 201, f"service closure readback failed: {readback_status} {readback_payload}", failures)
    return {"receipt": receipt_payload, "readback": readback_payload}


def run_smoke() -> dict:
    failures: list[str] = []
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")
    hermes_port = free_port()
    mis_port = free_port()
    base_url = f"http://127.0.0.1:{mis_port}"
    fake_hermes = start_fake_hermes(hermes_port)
    sample_snapshot = snapshot_files(SAMPLE_EXPORTS)
    with tempfile.TemporaryDirectory(prefix="agentops-hermes-retry-") as tmp:
        env = os.environ.copy()
        env.update(
            {
                "AGENTOPS_DB_PATH": str(Path(tmp) / "agentops_retry.db"),
                "AGENTOPS_BASE_URL": base_url,
                "HERMES_GATEWAY_URL": f"http://127.0.0.1:{hermes_port}",
                "HERMES_TIMEOUT": "5",
                "AGENTOPS_ADAPTER_MAX_ATTEMPTS": "2",
                "AGENTOPS_ADAPTER_RETRY_DELAY_SEC": "0",
            }
        )
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(mis_port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_for_server(base_url, proc)
            service_closure = record_loopback_service_closure(base_url, failures)
            task_id = f"tsk_customer_worker_hermes_retry_{stamp}"
            status, result = http_json(
                "POST",
                base_url,
                "/api/workflows/customer-worker-task",
                {
                    "adapter": "hermes",
                    "confirm_run": True,
                    "task_id": task_id,
                    "title": "Hermes retry gateway smoke",
                    "description": "Use the Hermes adapter through a transient local OpenAI-compatible gateway.",
                    "acceptance_criteria": "The worker retries one transient disconnect, completes the run, and records retry metadata.",
                    "hermes_timeout": 5,
                    "adapter_max_attempts": 2,
                    "adapter_retry_delay_sec": 0,
                },
                timeout=120,
            )
            run_id = result.get("run_id")
            require(status == 201, f"customer-worker request failed: {status} {result}", failures)
            require(result.get("ok") is True, f"customer-worker result not ok: {result}", failures)
            require(result.get("adapter") == "hermes", f"wrong adapter: {result}", failures)
            require(bool(run_id), f"missing run_id: {result}", failures)
            require(TransientHermesHandler.request_count == 2, f"fake Hermes saw {TransientHermesHandler.request_count} requests, expected 2", failures)
            detail_status, detail = http_json("GET", base_url, f"/api/runs/{run_id}", timeout=30)
            require(detail_status == 200, f"run detail failed: {detail_status} {detail}", failures)
            run = detail.get("run") or {}
            tool = next((item for item in (detail.get("tool_calls") or []) if item.get("tool_name") == "agent_worker.hermes"), {})
            args = parse_tool_args(tool)
            history = args.get("retry_history") or []
            require(run.get("status") == "completed", f"run did not complete: {run}", failures)
            require(tool.get("status") == "completed", f"tool call did not complete: {tool}", failures)
            require(args.get("attempt_count") == 2 and args.get("max_attempts") == 2, f"retry args missing: {args}", failures)
            require(len(history) == 2 and history[0].get("ok") is False and history[1].get("ok") is True, f"retry history invalid: {history}", failures)
            require((result.get("evidence") or {}).get("evaluations", 0) >= 1, f"missing evaluation evidence: {result.get('evidence')}", failures)
            require(not token_like_leaked(result), "result leaked token-like material", failures)
            return {
                "ok": not failures,
                "operation": "customer_worker_hermes_retry_gateway_smoke",
                "evidence_class": "deterministic_loopback_hermes_adapter_retry",
                "product_readiness_proof": False,
                "base_url": base_url,
                "fake_hermes_url": f"http://127.0.0.1:{hermes_port}",
                "task_id": task_id,
                "run_id": run_id,
                "artifact_id": result.get("artifact_id"),
                "approval_id": result.get("approval_id"),
                "service_closure_receipt_id": ((service_closure.get("receipt") or {}).get("receipt") or {}).get("receipt_id"),
                "attempt_count": args.get("attempt_count"),
                "retry_history": history,
                "fake_hermes_request_count": TransientHermesHandler.request_count,
                "failures": failures,
                "token_omitted": True,
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            fake_hermes.shutdown()
            fake_hermes.server_close()
            restore_files(sample_snapshot)


def main() -> int:
    result = run_smoke()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
