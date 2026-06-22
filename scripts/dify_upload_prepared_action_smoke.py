#!/usr/bin/env python3
"""Verify Dify text upload uses prepared-action exact resume without storing raw text."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


class FakeDifyHandler(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, fmt, *args):  # noqa: D401
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        self.__class__.calls.append({
            "path": self.path,
            "has_authorization": bool(self.headers.get("Authorization")),
            "provider_received_text": bool(payload.get("text")),
        })
        body = json.dumps({
            "document": {
                "id": "fake_dify_document_001",
                "name": payload.get("name") or "fake",
            }
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[dict, int]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=20) as res:
            raw = res.read().decode("utf-8")
            return (json.loads(raw) if raw else {}), res.status
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return payload, exc.code


def wait_for_server(base_url: str) -> None:
    deadline = time.time() + 20
    last_error = ""
    while time.time() < deadline:
        try:
            payload, status = http_json("GET", base_url, "/api/integrations/dify/status")
            if status == 200 and payload.get("provider") == "dify":
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"MIS server did not become ready: {last_error}")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    fake_port = free_port()
    app_port = free_port()
    fake = ThreadingHTTPServer(("127.0.0.1", fake_port), FakeDifyHandler)
    fake_thread = threading.Thread(target=fake.serve_forever, daemon=True)
    fake_thread.start()

    handle = tempfile.NamedTemporaryFile(prefix="agentops-dify-prepared-action-", suffix=".sqlite", delete=False)
    db_path = handle.name
    handle.close()
    env = os.environ.copy()
    env.update({
        "AGENTOPS_DB_PATH": db_path,
        "DIFY_API_BASE_URL": f"http://127.0.0.1:{fake_port}/v1",
        "DIFY_KB_API_KEY": "fake_dify_key_for_smoke",
        "DIFY_DATASET_ID": "fake_dataset",
        "DIFY_ALLOW_REAL_UPLOAD": "true",
        "DIFY_REQUIRE_APPROVAL": "true",
    })
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(app_port), "--reset", "--serve"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{app_port}"
    text = "Dify prepared-action smoke upload text. Non-sensitive fixture."
    try:
        wait_for_server(base_url)
        prepare, prepare_status = http_json("POST", base_url, "/api/integrations/dify/upload-text", {
            "confirm_upload": True,
            "document_name": "Prepared Action Dify Smoke",
            "text": text,
        })
        require(prepare_status == 202, f"prepare should be 202: {prepare_status} {prepare}", failures)
        prepared_action_id = prepare.get("prepared_action_id")
        approval_id = prepare.get("approval_id")
        require(bool(prepared_action_id and approval_id), f"prepare missing ids: {prepare}", failures)
        require(prepare.get("provider_call_performed") is False, f"prepare performed provider call: {prepare}", failures)
        require(prepare.get("raw_text_omitted") is True, f"prepare did not mark raw text omitted: {prepare}", failures)
        require(len(FakeDifyHandler.calls) == 0, f"fake Dify called before approval: {FakeDifyHandler.calls}", failures)

        premature, premature_status = http_json("POST", base_url, "/api/integrations/dify/upload-text", {
            "confirm_upload": True,
            "prepared_action_id": prepared_action_id,
            "text": text,
        })
        require(premature_status == 428 and premature.get("error") == "approval_required", f"premature resume should require approval: {premature_status} {premature}", failures)
        require(len(FakeDifyHandler.calls) == 0, "fake Dify called during premature resume", failures)

        approved, approved_status = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
        require(approved_status == 200 and approved.get("decision") == "approved", f"approval failed: {approved_status} {approved}", failures)
        require(len(FakeDifyHandler.calls) == 0, "fake Dify called during approval", failures)

        mismatch, mismatch_status = http_json("POST", base_url, "/api/integrations/dify/upload-text", {
            "confirm_upload": True,
            "prepared_action_id": prepared_action_id,
            "text": text + " changed",
        })
        require(mismatch_status == 409 and mismatch.get("error") == "prepared_action_text_hash_mismatch", f"mismatch should be blocked: {mismatch_status} {mismatch}", failures)
        require(len(FakeDifyHandler.calls) == 0, "fake Dify called during hash mismatch", failures)

        resumed, resumed_status = http_json("POST", base_url, "/api/integrations/dify/upload-text", {
            "confirm_upload": True,
            "prepared_action_id": prepared_action_id,
            "text": text,
        })
        require(resumed_status == 201 and resumed.get("created") is True, f"resume should upload Dify document: {resumed_status} {resumed}", failures)
        require(resumed.get("prepared_action_status") == "consumed", f"prepared action not consumed: {resumed}", failures)
        require(len(FakeDifyHandler.calls) == 1, f"fake Dify should be called exactly once: {FakeDifyHandler.calls}", failures)

        replay, replay_status = http_json("POST", base_url, "/api/integrations/dify/upload-text", {
            "confirm_upload": True,
            "prepared_action_id": prepared_action_id,
            "text": text,
        })
        require(replay_status == 409 and replay.get("error") == "prepared_action_already_consumed", f"replay should be blocked: {replay_status} {replay}", failures)
        require(len(FakeDifyHandler.calls) == 1, "fake Dify called during replay", failures)

        print(json.dumps({
            "ok": not failures,
            "failures": failures,
            "prepared_action_id": prepared_action_id,
            "approval_id": approval_id,
            "provider_call_count": len(FakeDifyHandler.calls),
            "token_omitted": True,
            "raw_text_omitted": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not failures else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        fake.shutdown()
        fake.server_close()
        try:
            os.unlink(db_path)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
