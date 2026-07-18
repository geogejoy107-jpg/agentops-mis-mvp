#!/usr/bin/env python3
"""Prove commercial production cannot fall through to the Python API proxy."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_production_python_proxy_fail_closed_v1"


class UpstreamHandler(BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self) -> None:  # noqa: N802
        type(self).hits += 1
        body = json.dumps({"ok": True, "unexpected_python_proxy": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def free_port() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    port = int(server.server_port)
    server.server_close()
    return port


def request_json(url: str) -> tuple[int, dict[str, object], dict[str, str]]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return int(response.status), json.loads(raw or "{}"), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), json.loads(raw or "{}"), dict(exc.headers.items())


def wait_for_next(base_url: str, process: subprocess.Popen[str]) -> tuple[int, dict[str, object], dict[str, str]]:
    deadline = time.time() + 90
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=2)
            raise RuntimeError(f"Next exited early: {(stdout or '')[-500:]} {(stderr or '')[-500:]}")
        try:
            return request_json(f"{base_url}/api/mis/not-migrated-production-probe")
        except Exception as exc:  # pragma: no cover - readiness diagnostics
            last_error = str(exc)
            time.sleep(0.2)
    raise RuntimeError(f"Next did not become ready: {last_error}")


def stop(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    node = shutil.which("node")
    require(bool(node), "node is required")
    next_cli = NEXT_APP / "node_modules" / "next" / "dist" / "bin" / "next"
    require(next_cli.exists(), "ui/next-app dependencies are required")

    UpstreamHandler.hits = 0
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    next_port = free_port()
    base_url = f"http://127.0.0.1:{next_port}"
    env = os.environ.copy()
    env.update({
        "AGENTOPS_DEPLOYMENT_MODE": "production",
        "AGENTOPS_CONTROL_PLANE_MODE": "proxy",
        "AGENTOPS_API_BASE": f"http://127.0.0.1:{upstream.server_port}/api",
        "NEXT_TELEMETRY_DISABLED": "1",
    })
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            [str(node), str(next_cli), "dev", "-p", str(next_port)],
            cwd=NEXT_APP,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        status, payload, headers = wait_for_next(base_url, process)
        require(status == 503, f"production catch-all returned {status}")
        require(payload.get("error") == "typescript_route_owner_required", "production catch-all lost its route-owner error")
        require(payload.get("python_proxy_performed") is False, "production catch-all did not deny Python proxy execution")
        require(UpstreamHandler.hits == 0, "production catch-all reached the Python upstream")
        cache_control = next((value for key, value in headers.items() if key.lower() == "cache-control"), "")
        require("no-store" in cache_control.lower(), "production catch-all response is cacheable")
        print(json.dumps({
            "ok": True,
            "contract": CONTRACT_ID,
            "status": status,
            "python_api_started": False,
            "python_proxy_performed": False,
            "upstream_request_count": UpstreamHandler.hits,
            "production_route_owner_required": True,
            "credentials_omitted": True,
        }, indent=2, sort_keys=True))
        return 0
    finally:
        stop(process)
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
