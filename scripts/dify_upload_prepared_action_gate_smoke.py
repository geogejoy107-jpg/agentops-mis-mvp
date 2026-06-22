#!/usr/bin/env python3
"""Verify Dify live uploads cannot bypass prepared-action approval."""

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
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server.py"
SECRET_RE = re.compile(r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{12,}|agtsess_[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{12,}|ntn_[A-Za-z0-9_-]{12,})")


class FakeDifyHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, _format: str, *_args) -> None:
        return

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}
        self.__class__.requests.append({
            "path": self.path,
            "name": body.get("name"),
            "has_authorization": bool(self.headers.get("Authorization")),
        })
        response = {
            "document": {
                "id": "dify_doc_smoke_001",
                "name": body.get("name") or "smoke",
            },
        }
        encoded = json.dumps(response).encode("utf-8")
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


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict, str]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method != "GET" else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw), raw
        except Exception:
            return exc.code, {"raw": raw}, raw


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(base_url.rstrip("/") + "/api/dashboard/metrics", timeout=1) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    return False


def start_mis_server(db_path: Path, port: int, dify_base_url: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    env["DIFY_API_BASE_URL"] = dify_base_url.rstrip("/")
    env["DIFY_KB_API_KEY"] = "dify-smoke-key"
    env["DIFY_DATASET_ID"] = "ds_dify_smoke"
    env["DIFY_ALLOW_REAL_UPLOAD"] = "true"
    env["DIFY_REQUIRE_APPROVAL"] = "false"
    return subprocess.Popen(
        [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    FakeDifyHandler.requests = []
    dify_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeDifyHandler)
    dify_thread = threading.Thread(target=dify_server.serve_forever, daemon=True)
    dify_thread.start()
    dify_base_url = f"http://127.0.0.1:{dify_server.server_port}/v1"
    mis_port = choose_port()
    base_url = f"http://127.0.0.1:{mis_port}"
    server: subprocess.Popen[str] | None = None

    with tempfile.TemporaryDirectory(prefix="agentops-dify-gate-") as tmp:
        db_path = Path(tmp) / "agentops_dify_gate.db"
        try:
            server = start_mis_server(db_path, mis_port, dify_base_url)
            require(wait_ready(base_url, server), "isolated MIS server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            upload_body = {
                "agent_id": "agt_gw_kb_builder",
                "document_name": "Dify prepared action smoke document",
                "text": "Dify prepared action smoke text. This is intentionally small and non-sensitive.",
                "dataset_id": "ds_dify_smoke",
                "confirm_upload": True,
            }
            status, prepared, raw = http_json("POST", base_url, "/api/integrations/dify/upload-text", upload_body)
            outputs.append(raw)
            require(status == 201, f"prepared gate request failed: {status} {prepared}", failures)
            require(prepared.get("reason") == "dify_external_write_prepared_action_required", f"wrong prepared gate reason: {prepared}", failures)
            require(prepared.get("live_upload_performed") is False, f"provider upload should not run before approval: {prepared}", failures)
            require(len(FakeDifyHandler.requests) == 0, f"Dify provider was called before prepared action approval: {FakeDifyHandler.requests}", failures)
            prepared_action_id = prepared.get("prepared_action_id")
            approval_id = prepared.get("approval_id")
            require(bool(prepared_action_id and approval_id), f"prepared action/approval missing: {prepared}", failures)

            status, approved, raw = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
            outputs.append(raw)
            require(status == 200, f"approval failed: {status} {approved}", failures)
            require((approved.get("prepared_action") or {}).get("status") == "approved", f"prepared action not approved: {approved}", failures)
            require(approved.get("resume_required") is True, f"approval should require explicit resume/execution: {approved}", failures)

            status, uploaded, raw = http_json("POST", base_url, "/api/integrations/dify/upload-text", {**upload_body, "prepared_action_id": prepared_action_id})
            outputs.append(raw)
            require(status == 201, f"approved Dify upload failed: {status} {uploaded}", failures)
            require(uploaded.get("ok") is True, f"Dify upload should succeed against fake provider: {uploaded}", failures)
            require(uploaded.get("document_id") == "dify_doc_smoke_001", f"document id mismatch: {uploaded}", failures)
            require(uploaded.get("live_upload_performed") is True, f"upload should mark live execution: {uploaded}", failures)
            require(len(FakeDifyHandler.requests) == 1, f"Dify provider should be called exactly once: {FakeDifyHandler.requests}", failures)
            require((uploaded.get("prepared_action") or {}).get("status") == "consumed", f"prepared action should be consumed after success: {uploaded}", failures)

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                action = conn.execute("SELECT status, consumed_at, provider_side_effect_id FROM prepared_actions WHERE action_id=?", (prepared_action_id,)).fetchone()
                tool = conn.execute("SELECT status, side_effect_id FROM tool_calls WHERE tool_call_id=?", (uploaded.get("tool_call_id"),)).fetchone()
                audit_count = conn.execute("SELECT COUNT(*) c FROM audit_logs WHERE action IN ('dify.upload_text.prepared_action_required','approval_wall.prepared_action_resumed','dify.upload_text')").fetchone()["c"]
            require(action and action["status"] == "consumed" and action["provider_side_effect_id"] == "dify_doc_smoke_001", f"prepared action ledger mismatch: {dict(action) if action else None}", failures)
            require(tool and tool["status"] == "completed" and tool["side_effect_id"] == "dify_doc_smoke_001", f"tool call ledger mismatch: {dict(tool) if tool else None}", failures)
            require(audit_count >= 3, f"expected Dify/prepared-action audit trail, got {audit_count}", failures)
        finally:
            if server and server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
            dify_server.shutdown()
            dify_server.server_close()

    require(not SECRET_RE.search("\n".join(outputs)), "smoke output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "dify_upload_prepared_action_gate",
        "provider_calls": len(FakeDifyHandler.requests),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
