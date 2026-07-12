#!/usr/bin/env python3
"""Prove Hermes HTTP failures remain useful without storing response bodies."""

from __future__ import annotations

import contextlib
import hashlib
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_cli.worker import execute_hermes


SENSITIVE_BODY = b'{"error":{"message":"private upstream response must stay omitted"}}'


class FailingHermesHandler(BaseHTTPRequestHandler):
    def log_message(self, _fmt: str, *_args) -> None:
        return

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(SENSITIVE_BODY)))
        self.end_headers()
        self.wfile.write(SENSITIVE_BODY)


def free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> int:
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), FailingHermesHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = execute_hermes(
            {"task_id": "tsk_http_error_smoke", "title": "Safe HTTP error evidence"},
            f"http://127.0.0.1:{port}",
            "hermes-agent",
            5,
            True,
            64,
        )
    finally:
        server.shutdown()
        server.server_close()

    visible = " ".join([result.output_summary, result.error_message or ""])
    checks = {
        "failed_closed": not result.ok,
        "typed_status": result.error_type == "HermesHTTP500",
        "safe_summary": visible == "Hermes gateway returned HTTP 500. Hermes gateway returned HTTP 500; response body omitted.",
        "body_omitted": SENSITIVE_BODY.decode("utf-8") not in visible and "private upstream" not in visible,
        "body_hashed": result.raw_payload_hash == hashlib.sha256(SENSITIVE_BODY).hexdigest(),
        "retryable_server_error": result.retryable,
    }
    failures = [name for name, passed in checks.items() if not passed]
    print({"status": "pass" if not failures else "fail", "checks": checks})
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
