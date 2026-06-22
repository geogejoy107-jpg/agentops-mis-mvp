#!/usr/bin/env python3
"""Verify Notion live export cannot bypass prepared-action approval."""

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
SECRET_RE = re.compile(r"(Authorization:|Bearer\s+[A-Za-z0-9._~+/=-]+|agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{20,}|ntn_[A-Za-z0-9_-]{8,})")


class FakeNotionHandler(BaseHTTPRequestHandler):
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
            "has_authorization": bool(self.headers.get("Authorization")),
            "child_count": len(body.get("children") or []),
        })
        response = {
            "id": "notion_page_smoke_001",
            "url": "https://notion.local/notion_page_smoke_001",
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
        with urllib.request.urlopen(req, timeout=60) as resp:
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


def start_mis_server(db_path: Path, port: int, notion_base_url: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    env["NOTION_TOKEN"] = "notion-smoke-token"
    env["NOTION_PARENT_PAGE_ID"] = "notion_parent_smoke"
    env["NOTION_API_BASE_URL"] = notion_base_url.rstrip("/")
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
    FakeNotionHandler.requests = []
    notion_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeNotionHandler)
    notion_thread = threading.Thread(target=notion_server.serve_forever, daemon=True)
    notion_thread.start()
    notion_base_url = f"http://127.0.0.1:{notion_server.server_port}/v1"
    mis_port = choose_port()
    base_url = f"http://127.0.0.1:{mis_port}"
    server: subprocess.Popen[str] | None = None

    with tempfile.TemporaryDirectory(prefix="agentops-notion-gate-") as tmp:
        db_path = Path(tmp) / "agentops_notion_gate.db"
        try:
            server = start_mis_server(db_path, mis_port, notion_base_url)
            require(wait_ready(base_url, server), "isolated MIS server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            export_body = {
                "dry_run": False,
                "confirm_export": True,
                "title": "AgentOps MIS Notion prepared action smoke",
                "idempotency_key": "notion-export-prepared-action-smoke",
            }
            status, prepared, raw = http_json("POST", base_url, "/api/integrations/notion/export-report", export_body)
            outputs.append(raw)
            require(status == 201, f"prepared gate request failed: {status} {prepared}", failures)
            require(prepared.get("reason") == "notion_external_write_prepared_action_required", f"wrong prepared gate reason: {prepared}", failures)
            require(prepared.get("live_export_performed") is False, f"Notion export should not run before approval: {prepared}", failures)
            require(len(FakeNotionHandler.requests) == 0, f"Notion provider was called before approval: {FakeNotionHandler.requests}", failures)
            prepared_action_id = prepared.get("prepared_action_id")
            approval_id = prepared.get("approval_id")
            require(bool(prepared_action_id and approval_id), f"prepared action/approval missing: {prepared}", failures)

            status, approved, raw = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
            outputs.append(raw)
            require(status == 200, f"approval failed: {status} {approved}", failures)
            require((approved.get("prepared_action") or {}).get("status") == "approved", f"prepared action not approved: {approved}", failures)
            require(approved.get("resume_required") is True, f"approval should require explicit resume/export: {approved}", failures)

            status, exported, raw = http_json("POST", base_url, "/api/integrations/notion/export-report", {**export_body, "prepared_action_id": prepared_action_id})
            outputs.append(raw)
            require(status == 201, f"approved Notion export failed: {status} {exported}", failures)
            require(exported.get("created") is True, f"Notion export should succeed against fake provider: {exported}", failures)
            require(exported.get("notion_page_id") == "notion_page_smoke_001", f"page id mismatch: {exported}", failures)
            require(exported.get("live_export_performed") is True, f"export should mark live execution: {exported}", failures)
            require(len(FakeNotionHandler.requests) == 1, f"Notion provider should be called exactly once: {FakeNotionHandler.requests}", failures)
            require((exported.get("prepared_action") or {}).get("status") == "consumed", f"prepared action should be consumed after success: {exported}", failures)

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                action = conn.execute("SELECT status, consumed_at, provider_side_effect_id FROM prepared_actions WHERE action_id=?", (prepared_action_id,)).fetchone()
                tool = conn.execute("SELECT status, side_effect_id FROM tool_calls WHERE tool_call_id=?", ((exported.get("prepared_action") or {}).get("tool_call_id"),)).fetchone()
                sync_event = conn.execute("SELECT * FROM sync_events WHERE external_object_id='notion_page_smoke_001' ORDER BY created_at DESC LIMIT 1").fetchone()
                audit_count = conn.execute("SELECT COUNT(*) c FROM audit_logs WHERE action IN ('notion.export.prepared_action_required','approval_wall.prepared_action_resumed','notion.export_confirmed')").fetchone()["c"]
            require(action and action["status"] == "consumed" and action["provider_side_effect_id"] == "notion_page_smoke_001", f"prepared action ledger mismatch: {dict(action) if action else None}", failures)
            require(tool and tool["status"] == "completed" and tool["side_effect_id"] == "notion_page_smoke_001", f"tool call ledger mismatch: {dict(tool) if tool else None}", failures)
            require(sync_event and sync_event["status"] == "created", f"sync event missing: {dict(sync_event) if sync_event else None}", failures)
            require(audit_count >= 3, f"expected Notion/prepared-action audit trail, got {audit_count}", failures)
        finally:
            if server and server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
            notion_server.shutdown()
            notion_server.server_close()

    require(not SECRET_RE.search("\n".join(outputs)), "smoke output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "notion_export_prepared_action_gate",
        "provider_calls": len(FakeNotionHandler.requests),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
