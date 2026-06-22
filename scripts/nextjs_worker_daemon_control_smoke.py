#!/usr/bin/env python3
"""Verify Next.js can control only the safe mock worker daemon."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_worker_daemon_control_v1"

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    free_port,
    leaked_secret,
    require,
    restore_next_env,
    run,
    start_process,
    wait_http,
)


def http_json_status(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def post_form_no_redirect(url: str, payload: dict[str, str]) -> tuple[int, str]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=90) as response:
            return int(response.status), response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        if exc.code in {302, 303, 307, 308}:
            return int(exc.code), exc.headers.get("Location", "")
        raise


def mock_daemon(payload: Any) -> dict[str, Any]:
    daemons = payload.get("daemons") if isinstance(payload, dict) else []
    if not isinstance(daemons, list):
        return {}
    return next((item for item in daemons if isinstance(item, dict) and item.get("adapter") == "mock"), {})


def next_worker_status(next_base: str) -> dict[str, Any]:
    status, payload = http_json_status("GET", f"{next_base}/api/mis/workers/status")
    require(status == 200, f"worker status failed: {status} {payload}")
    return payload


def wait_for_mock_running(next_base: str, timeout_sec: int = 20) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = next_worker_status(next_base)
        if mock_daemon(last).get("running"):
            return last
        time.sleep(0.4)
    raise AssertionError(f"timed out waiting for mock daemon running: {last}")


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Next.js daemon smoke"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-worker-daemon-") as tmp:
            tmp_path = Path(tmp)
            db_path = str(tmp_path / "agentops.db")
            runtime_dir = str(tmp_path / "runtime")
            reset_env = os.environ.copy()
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset_env["AGENTOPS_BASE_URL"] = api_base
            reset_env["AGENTOPS_RUNTIME_DIR"] = runtime_dir
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_env["AGENTOPS_BASE_URL"] = api_base
            api_env["AGENTOPS_RUNTIME_DIR"] = runtime_dir
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/agents")

            blocked_status, blocked = http_json_status("POST", f"{next_base}/api/mis/workers/local/start", {
                "adapter": "hermes",
                "confirm_run": True,
                "poll_interval": 2,
                "max_tasks": 0,
            })
            require(blocked_status == 403, f"non-mock daemon start did not fail closed: {blocked_status} {blocked}")
            require(blocked.get("error") == "mock_daemon_only_next_parity", f"wrong non-mock daemon error: {blocked}")

            confirm_status, confirm_blocked = http_json_status("POST", f"{next_base}/api/mis/workers/local/start", {
                "adapter": "mock",
                "confirm_run": True,
                "poll_interval": 2,
                "max_tasks": 0,
            })
            require(confirm_status == 403, f"confirm_run daemon start did not fail closed: {confirm_status} {confirm_blocked}")
            require(confirm_blocked.get("error") == "live_worker_daemon_not_allowed_next_parity", f"wrong confirm_run daemon error: {confirm_blocked}")

            start_status, started = http_json_status("POST", f"{next_base}/api/mis/workers/local/start", {
                "adapter": "mock",
                "confirm_run": False,
                "poll_interval": 2,
                "max_tasks": 0,
                "status": ["planned"],
            })
            require(start_status in {200, 201} and started.get("ok") is True, f"mock daemon start failed: {start_status} {started}")
            require((started.get("daemon") or {}).get("adapter") == "mock", f"mock daemon start returned wrong daemon: {started}")

            running_status = wait_for_mock_running(next_base)
            running_daemon = mock_daemon(running_status)
            require(running_daemon.get("pid"), f"running daemon missing pid: {running_status}")

            restart_status, restarted = http_json_status("POST", f"{next_base}/api/mis/workers/local/restart", {
                "adapter": "mock",
                "confirm_run": False,
                "poll_interval": 2,
                "max_tasks": 0,
                "status": ["planned"],
            })
            require(restart_status in {200, 201} and restarted.get("ok") is True, f"mock daemon restart failed: {restart_status} {restarted}")
            require((restarted.get("daemon") or {}).get("adapter") == "mock", f"mock daemon restart returned wrong daemon: {restarted}")

            stop_status, stopped = http_json_status("POST", f"{next_base}/api/mis/workers/local/stop", {"adapter": "mock"})
            require(stop_status == 200 and stopped.get("ok") is True, f"mock daemon stop failed: {stop_status} {stopped}")
            stopped_daemon = (stopped.get("daemons") or [{}])[0]
            require(stopped_daemon.get("adapter") == "mock", f"mock daemon stop returned wrong daemon: {stopped}")

            invalid_form_status, invalid_form_location = post_form_no_redirect(f"{next_base}/workspace/agents/daemon-control", {
                "action": "start",
                "adapter": "openclaw",
                "poll_interval": "2",
                "max_tasks": "0",
            })
            require(invalid_form_status == 303, f"invalid daemon form did not redirect: {invalid_form_status} {invalid_form_location}")
            invalid_query = urllib.parse.parse_qs(urllib.parse.urlparse(invalid_form_location).query)
            require(invalid_query.get("daemon_status") == ["failed"], f"invalid daemon form did not fail: {invalid_form_location}")
            require(invalid_query.get("error") == ["mock_daemon_only_next_parity"], f"invalid daemon form wrong error: {invalid_form_location}")

            form_start_status, form_start_location = post_form_no_redirect(f"{next_base}/workspace/agents/daemon-control", {
                "action": "start",
                "adapter": "mock",
                "poll_interval": "2",
                "max_tasks": "0",
            })
            require(form_start_status == 303, f"form start did not redirect: {form_start_status} {form_start_location}")
            form_start_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_start_location).query)
            require(form_start_query.get("daemon_status") == ["started"], f"form start did not report started: {form_start_location}")

            form_restart_status, form_restart_location = post_form_no_redirect(f"{next_base}/workspace/agents/daemon-control", {
                "action": "restart",
                "adapter": "mock",
                "poll_interval": "2",
                "max_tasks": "0",
            })
            require(form_restart_status == 303, f"form restart did not redirect: {form_restart_status} {form_restart_location}")
            form_restart_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_restart_location).query)
            require(form_restart_query.get("daemon_status") == ["restarted"], f"form restart did not report restarted: {form_restart_location}")

            form_stop_status, form_stop_location = post_form_no_redirect(f"{next_base}/workspace/agents/daemon-control", {
                "action": "stop",
                "adapter": "mock",
            })
            require(form_stop_status == 303, f"form stop did not redirect: {form_stop_status} {form_stop_location}")
            form_stop_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_stop_location).query)
            require(form_stop_query.get("daemon_status") == ["stopped"], f"form stop did not report stopped: {form_stop_location}")

            final_status = next_worker_status(next_base)
            final_mock = mock_daemon(final_status)
            require(final_mock and not final_mock.get("running"), f"mock daemon still running after stop: {final_status}")

            transcript = json.dumps([
                blocked,
                confirm_blocked,
                started,
                running_status,
                restarted,
                stopped,
                invalid_form_location,
                form_start_location,
                form_restart_location,
                form_stop_location,
                final_status,
            ], ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript), "Next worker daemon control leaked token-like material")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "proxy_start_route": "/api/mis/workers/local/start",
                "proxy_restart_route": "/api/mis/workers/local/restart",
                "proxy_stop_route": "/api/mis/workers/local/stop",
                "form_route": "/workspace/agents/daemon-control",
                "non_mock_status": blocked_status,
                "non_mock_error": "mock_daemon_only_next_parity",
                "confirm_run_status": confirm_status,
                "confirm_run_error": "live_worker_daemon_not_allowed_next_parity",
                "start_status": start_status,
                "restart_status": restart_status,
                "stop_status": stop_status,
                "form_start_status": form_start_status,
                "form_restart_status": form_restart_status,
                "form_stop_status": form_stop_status,
                "running_pid_seen": bool(running_daemon.get("pid")),
                "final_running": bool(final_mock.get("running")),
                "secret_leaked": False,
                "token_omitted": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        try:
            http_json_status("POST", f"{next_base}/api/mis/workers/local/stop", {"adapter": "mock"})
        except Exception:
            pass
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()


if __name__ == "__main__":
    raise SystemExit(main())
