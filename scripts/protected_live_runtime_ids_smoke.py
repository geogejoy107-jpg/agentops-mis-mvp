#!/usr/bin/env python3
"""Verify optional live-runtime IDs are protected release-packet evidence."""
from __future__ import annotations

import datetime as dt
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
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server.py"
SECRET_RE = re.compile(
    r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,})"
)


class FakeGatewayHandler(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}
        self.__class__.calls.append({"path": self.path, "body_hash": hash(json.dumps(body, sort_keys=True))})
        payload = {"id": f"fake-{len(self.__class__.calls)}", "choices": [{"message": {"role": "assistant", "content": "PROTECTED_RUNTIME_OK"}}]}
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict, str]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method != "GET" else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body, raw


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(base_url + "/api/agent-gateway/status", timeout=1) as resp:
                return resp.status == 200
        except Exception:
            time.sleep(0.2)
    return False


def start_server(db_path: Path, port: int, gateway_url: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.update({
        "AGENTOPS_DB_PATH": str(db_path),
        "AGENTOPS_SKIP_SEED_EXPORTS": "1",
        "HERMES_ALLOW_REAL_RUN": "true",
        "HERMES_REQUIRE_CONFIRM_RUN": "true",
        "HERMES_GATEWAY_URL": gateway_url,
        "AGNESFALLBACK_GATEWAY_URL": gateway_url,
    })
    return subprocess.Popen(
        [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def set_trust(base_url: str, connector_id: str, trust_status: str, note: str) -> tuple[int, dict, str]:
    return http_json("POST", base_url, f"/api/runtime-connectors/{connector_id}/trust", {
        "trust_status": trust_status,
        "trust_note": note,
    })


def db_count(db_path: Path, sql: str, params: tuple = ()) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] or 0) if row else 0


def validate_readiness(payload: dict, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-worker", f"wrong readiness provider: {payload}", failures)
    require(payload.get("live_execution_performed") is False, f"readiness executed live work: {payload}", failures)
    require(payload.get("token_omitted") is True, f"readiness token omission missing: {payload}", failures)
    adapters = payload.get("adapters") or {}
    for adapter in ("hermes", "openclaw"):
        item = adapters.get(adapter) or {}
        manifest = item.get("capability_manifest") or {}
        governance = manifest.get("governance") or {}
        require(item.get("adapter") == adapter, f"missing {adapter} readiness: {payload}", failures)
        require((item.get("checks") or {}).get("live_execution_performed") is False, f"{adapter} readiness performed live work: {item}", failures)
        require(item.get("observation_level") == "ledger_summary_only", f"{adapter} observation boundary missing: {item}", failures)
        require(item.get("commercial_readiness") == "restricted_until_runtime_tool_events", f"{adapter} commercial restriction missing: {item}", failures)
        require(governance.get("requires_prepared_action_for_external_write") is True, f"{adapter} external-write governance missing: {item}", failures)
        require(bool(item.get("capability_policy_hash")), f"{adapter} capability hash missing: {item}", failures)


def main() -> int:
    suffix = stamp()
    failures: list[str] = []
    outputs: list[str] = []
    FakeGatewayHandler.calls = []
    fake_gateway = ThreadingHTTPServer(("127.0.0.1", 0), FakeGatewayHandler)
    gateway_thread = threading.Thread(target=fake_gateway.serve_forever, daemon=True)
    gateway_thread.start()
    gateway_url = f"http://127.0.0.1:{fake_gateway.server_port}"
    protected_packet: dict = {}
    server: subprocess.Popen[str] | None = None

    with tempfile.TemporaryDirectory(prefix="agentops-protected-live-ids-") as tmp:
        db_path = Path(tmp) / "agentops_protected_live_ids.db"
        port = choose_port()
        base_url = f"http://127.0.0.1:{port}"
        try:
            server = start_server(db_path, port, gateway_url)
            require(wait_ready(base_url, server), "isolated server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            status, readiness, raw = http_json("GET", base_url, "/api/workers/adapter-readiness")
            outputs.append(raw)
            require(status == 200, f"adapter readiness failed: {status} {readiness}", failures)
            validate_readiness(readiness, failures)

            status, hermes_gate, raw = http_json("POST", base_url, "/api/workflows/customer-worker-task", {
                "adapter": "hermes",
                "title": f"Protected Hermes live ID release gate {suffix}",
                "description": "This task must plan but not execute Hermes because confirm_run is absent.",
                "acceptance_criteria": "Release packet may record only the planned task id and confirm gate reason.",
                "risk_level": "medium",
            })
            outputs.append(raw)
            require(status == 201, f"Hermes confirm gate failed: {status} {hermes_gate}", failures)
            require(hermes_gate.get("dry_run") is True, f"Hermes gate should be dry-run/planned: {hermes_gate}", failures)
            require(hermes_gate.get("reason") == "confirm_run_required_for_live_adapter", f"Hermes gate reason missing: {hermes_gate}", failures)
            require(bool(hermes_gate.get("task_id")) and not hermes_gate.get("run_id"), f"Hermes gate should expose task id but no live run id: {hermes_gate}", failures)

            status, blocked_trust, raw = set_trust(base_url, "rtc_openclaw_local", "blocked", "Release packet smoke blocks OpenClaw live IDs.")
            outputs.append(raw)
            require(status == 200 and (blocked_trust.get("connector") or {}).get("trust_status") == "blocked", f"OpenClaw trust block failed: {status} {blocked_trust}", failures)
            status, openclaw_blocked, raw = http_json("POST", base_url, "/api/workflows/customer-worker-task", {
                "adapter": "openclaw",
                "confirm_run": True,
                "title": f"Protected OpenClaw live ID release gate {suffix}",
                "description": "This task must not execute while the OpenClaw connector is blocked.",
                "acceptance_criteria": "Release packet may record blocked task id and trust reason only.",
                "risk_level": "medium",
            })
            outputs.append(raw)
            require(status == 409, f"OpenClaw blocked trust should return 409: {status} {openclaw_blocked}", failures)
            require(openclaw_blocked.get("reason") == "runtime_connector_trust_blocked", f"OpenClaw wrong block reason: {openclaw_blocked}", failures)
            require(bool(openclaw_blocked.get("task_id")) and not openclaw_blocked.get("run_id"), f"OpenClaw block should expose task id but no live run id: {openclaw_blocked}", failures)
            restore_status, restored, raw = set_trust(base_url, "rtc_openclaw_local", "trusted", "Release packet smoke restored OpenClaw trust.")
            outputs.append(raw)
            require(restore_status == 200 and (restored.get("connector") or {}).get("trust_status") == "trusted", f"OpenClaw trust restore failed: {restore_status} {restored}", failures)

            provider_calls_before_probe = len(FakeGatewayHandler.calls)
            status, hermes_probe, raw = http_json("POST", base_url, "/api/integrations/hermes/run-task", {"confirm_run": True})
            outputs.append(raw)
            require(status == 201, f"Hermes fixed probe prepare failed: {status} {hermes_probe}", failures)
            require(hermes_probe.get("reason") == "runtime_probe_prepared_action_required", f"Hermes probe did not prepare first: {hermes_probe}", failures)
            require(hermes_probe.get("live_probe_performed") is False, f"Hermes probe executed before approval: {hermes_probe}", failures)
            require(bool(hermes_probe.get("prepared_action_id") and hermes_probe.get("approval_id")), f"Hermes protected IDs missing: {hermes_probe}", failures)

            status, openclaw_probe, raw = http_json("POST", base_url, "/api/integrations/openclaw/probe", {"confirm_run": True})
            outputs.append(raw)
            require(status == 201, f"OpenClaw fixed probe prepare failed: {status} {openclaw_probe}", failures)
            require(openclaw_probe.get("reason") == "runtime_probe_prepared_action_required", f"OpenClaw probe did not prepare first: {openclaw_probe}", failures)
            require(openclaw_probe.get("live_probe_performed") is False, f"OpenClaw probe executed before approval: {openclaw_probe}", failures)
            require(bool(openclaw_probe.get("prepared_action_id") and openclaw_probe.get("approval_id")), f"OpenClaw protected IDs missing: {openclaw_probe}", failures)
            require(len(FakeGatewayHandler.calls) == provider_calls_before_probe, "fixed probes called provider before prepared-action approval", failures)

            prepared_ids = [hermes_probe.get("prepared_action_id"), openclaw_probe.get("prepared_action_id")]
            approval_ids = [hermes_probe.get("approval_id"), openclaw_probe.get("approval_id")]
            protected_packet = {
                "optional_live_runtime_ids_present": False,
                "live_execution_performed": False,
                "provider_calls_before_approval": len(FakeGatewayHandler.calls),
                "readiness_status": readiness.get("status"),
                "hermes_confirm_gate_task_id": hermes_gate.get("task_id"),
                "openclaw_blocked_task_id": openclaw_blocked.get("task_id"),
                "openclaw_connector_id": "rtc_openclaw_local",
                "runtime_probe_prepared_action_ids": prepared_ids,
                "runtime_probe_approval_ids": approval_ids,
                "prepared_action_count": db_count(db_path, "SELECT COUNT(*) FROM prepared_actions WHERE action_id IN (?,?)", tuple(prepared_ids)),
                "pending_runtime_approval_count": db_count(db_path, "SELECT COUNT(*) FROM approvals WHERE approval_id IN (?,?) AND decision='pending'", tuple(approval_ids)),
                "raw_payload_omitted": True,
                "token_omitted": True,
            }
            require(protected_packet["prepared_action_count"] == 2, f"prepared actions not persisted: {protected_packet}", failures)
            require(protected_packet["pending_runtime_approval_count"] == 2, f"runtime approvals not pending: {protected_packet}", failures)
            require(not SECRET_RE.search("\n".join(outputs) + json.dumps(protected_packet, ensure_ascii=False)), "protected live runtime ID smoke leaked token-like material", failures)
        except Exception as exc:
            failures.append(f"unexpected exception: {type(exc).__name__}: {exc}")
        finally:
            if server:
                server.terminate()
                try:
                    out, err = server.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    out, err = server.communicate(timeout=5)
                outputs.extend([out or "", err or ""])
            fake_gateway.shutdown()
            fake_gateway.server_close()

    print(json.dumps({
        "ok": not failures,
        "operation": "protected_live_runtime_ids",
        "failures": failures,
        "protected_packet": protected_packet,
        "secret_leaked": False if not SECRET_RE.search("\n".join(outputs)) else True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
