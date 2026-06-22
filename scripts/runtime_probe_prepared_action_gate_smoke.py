#!/usr/bin/env python3
"""Verify fixed live runtime probes use Approval Wall exact-resume gates."""

from __future__ import annotations

import json
import os
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
        content = (((body.get("messages") or [{}])[0] or {}).get("content") or "")
        if "HERMES_DEFAULT_RUN_OK" in content:
            reply = "HERMES_DEFAULT_RUN_OK"
        elif "HERMES_AGNES_API_OK" in content:
            reply = "HERMES_AGNES_API_OK"
        else:
            reply = "UNEXPECTED_FIXED_PROBE"
        self.__class__.calls.append({"path": self.path, "reply": reply})
        payload = {"id": f"fake-{len(self.__class__.calls)}", "choices": [{"message": {"role": "assistant", "content": reply}}]}
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method != "GET" else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(base_url.rstrip("/") + "/api/dashboard/metrics", timeout=1) as resp:
                return resp.status == 200
        except Exception:
            time.sleep(0.2)
    return False


def make_fake_cli(path: Path, counter_path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"p=pathlib.Path({str(counter_path)!r})\n"
        "count=int(p.read_text() or '0') if p.exists() else 0\n"
        "p.write_text(str(count+1))\n"
        "print('AGNESFALLBACK_OK')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def approve(base_url: str, approval_id: str, failures: list[str]) -> None:
    status, payload = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
    require(status == 200, f"approval failed: {status} {payload}", failures)
    require((payload.get("prepared_action") or {}).get("status") == "approved", f"prepared action not approved: {payload}", failures)


def assert_gate_and_resume(base_url: str, path: str, body: dict, provider_calls: callable, failures: list[str]) -> None:
    before_calls = provider_calls()
    status, prepared = http_json("POST", base_url, path, body)
    require(status == 201, f"prepare request failed for {path}: {status} {prepared}", failures)
    require(prepared.get("reason") == "runtime_probe_prepared_action_required", f"wrong prepared reason for {path}: {prepared}", failures)
    require(prepared.get("live_probe_performed") is False, f"live probe should not execute before approval for {path}: {prepared}", failures)
    require(provider_calls() == before_calls, f"provider was called before approval for {path}", failures)
    approval_id = prepared.get("approval_id")
    action_id = prepared.get("prepared_action_id")
    require(bool(approval_id and action_id), f"approval/action missing for {path}: {prepared}", failures)
    if not approval_id or not action_id:
        return
    approve(base_url, approval_id, failures)
    status, executed = http_json("POST", base_url, path, {**body, "prepared_action_id": action_id})
    require(status == 201, f"approved execution failed for {path}: {status} {executed}", failures)
    require(executed.get("dry_run") is False and executed.get("live_probe_performed") is True, f"approved execution should be live for {path}: {executed}", failures)
    require(provider_calls() == before_calls + 1, f"provider should be called exactly once after approval for {path}", failures)
    require((executed.get("prepared_action") or {}).get("status") == "consumed", f"prepared action not consumed for {path}: {executed}", failures)
    status, replay = http_json("POST", base_url, path, {**body, "prepared_action_id": action_id})
    require(status == 201, f"replay endpoint should return API payload for {path}: {status} {replay}", failures)
    require(replay.get("error") == "prepared_action_already_consumed", f"replay should be blocked for {path}: {replay}", failures)
    require(provider_calls() == before_calls + 1, f"provider was called during replay for {path}", failures)


def main() -> int:
    failures: list[str] = []
    FakeGatewayHandler.calls = []
    fake_gateway = ThreadingHTTPServer(("127.0.0.1", 0), FakeGatewayHandler)
    gateway_thread = threading.Thread(target=fake_gateway.serve_forever, daemon=True)
    gateway_thread.start()
    gateway_url = f"http://127.0.0.1:{fake_gateway.server_port}"

    with tempfile.TemporaryDirectory(prefix="agentops-runtime-gate-") as tmp:
        tmp_path = Path(tmp)
        cli_count = tmp_path / "cli_count.txt"
        fake_cli = tmp_path / "agnesfallback"
        make_fake_cli(fake_cli, cli_count)
        port = choose_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({
            "AGENTOPS_DB_PATH": str(tmp_path / "agentops_runtime_gate.db"),
            "AGENTOPS_SKIP_SEED_EXPORTS": "1",
            "HERMES_ALLOW_REAL_RUN": "true",
            "HERMES_REQUIRE_CONFIRM_RUN": "true",
            "HERMES_GATEWAY_URL": gateway_url,
            "AGNESFALLBACK_GATEWAY_URL": gateway_url,
            "AGNESFALLBACK_BIN": str(fake_cli),
        })
        server = subprocess.Popen(
            [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            require(wait_ready(base_url, server), "isolated MIS server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            status, openclaw = http_json("POST", base_url, "/api/integrations/openclaw/probe", {"confirm_run": True})
            require(status == 201, f"openclaw prepare request failed: {status} {openclaw}", failures)
            require(openclaw.get("reason") == "runtime_probe_prepared_action_required", f"OpenClaw confirm should prepare, not execute: {openclaw}", failures)
            require(bool(openclaw.get("prepared_action_id") and openclaw.get("approval_id")), f"OpenClaw prepared ids missing: {openclaw}", failures)

            assert_gate_and_resume(
                base_url,
                "/api/integrations/hermes/cli-probe",
                {"confirm_run": True},
                lambda: int(cli_count.read_text() or "0") if cli_count.exists() else 0,
                failures,
            )
            assert_gate_and_resume(
                base_url,
                "/api/integrations/hermes/chat-completion-probe",
                {"confirm_run": True},
                lambda: len([call for call in FakeGatewayHandler.calls if call["reply"] == "HERMES_AGNES_API_OK"]),
                failures,
            )
            assert_gate_and_resume(
                base_url,
                "/api/integrations/hermes/run-task",
                {"confirm_run": True},
                lambda: len([call for call in FakeGatewayHandler.calls if call["reply"] == "HERMES_DEFAULT_RUN_OK"]),
                failures,
            )

            with sqlite3.connect(env["AGENTOPS_DB_PATH"]) as conn:
                conn.row_factory = sqlite3.Row
                consumed = conn.execute("SELECT COUNT(*) c FROM prepared_actions WHERE action_type='runtime.fixed_probe' AND status='consumed'").fetchone()["c"]
                audits = conn.execute("SELECT COUNT(*) c FROM audit_logs WHERE action LIKE 'runtime.%prepared_action%' OR action='approval_wall.prepared_action_resumed'").fetchone()["c"]
            require(consumed >= 3, f"expected consumed runtime prepared actions, got {consumed}", failures)
            require(audits >= 6, f"expected runtime prepared-action audit trail, got {audits}", failures)
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
            fake_gateway.shutdown()
            fake_gateway.server_close()

    print(json.dumps({
        "ok": not failures,
        "operation": "runtime_probe_prepared_action_gate",
        "fake_gateway_calls": len(FakeGatewayHandler.calls),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
