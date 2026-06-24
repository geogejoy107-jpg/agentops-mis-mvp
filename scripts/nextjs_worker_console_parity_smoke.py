#!/usr/bin/env python3
"""Verify the focused Next.js Worker Console parity surface."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_worker_console_parity_v1"

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    free_port,
    leaked_secret,
    playwright,
    require,
    restore_next_env,
    run,
    snapshot_route,
    start_process,
    wait_http,
)


WORKER_SCOPES = [
    "agents:heartbeat",
    "tasks:read",
    "tasks:claim",
    "runs:write",
    "toolcalls:write",
    "evaluations:submit",
    "audit:write",
]


def http_json_status(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
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


def assert_no_next_secret(label: str, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    require("session_token" not in text, f"{label} leaked session_token: {payload}")
    require("token_hash" not in text and "session_hash" not in text, f"{label} leaked token/session hash: {payload}")
    require('"session_id":' not in text and '"parent_token_id":' not in text, f"{label} leaked raw stable session ids: {payload}")
    require(not leaked_secret(text), f"{label} leaked token-like material: {payload}")


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": "npx is required"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-worker-console-") as tmp:
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

            direct_agent_id = f"agt_next_worker_console_{stamp}"
            direct_enrollment_status, direct_enrollment = http_json_status("POST", f"{api_base}/api/agent-gateway/enrollment/create", {
                "agent_id": direct_agent_id,
                "name": "Next Worker Console Guard Agent",
                "runtime_type": "mock",
                "workspace_id": "local-demo",
                "scopes": WORKER_SCOPES,
                "ttl_days": 1,
                "heartbeat_timeout_sec": 60,
            })
            require(direct_enrollment_status == 201, f"direct backend enrollment create failed: {direct_enrollment_status} {direct_enrollment}")
            enrollment_token = direct_enrollment.get("token")
            token_id = direct_enrollment.get("token_id")
            require(enrollment_token and token_id, f"direct backend setup missing token/token_id: {direct_enrollment}")
            direct_session_status, direct_session = http_json_status("POST", f"{api_base}/api/agent-gateway/session/create", {
                "ttl_sec": 600,
                "scopes": ["agents:heartbeat", "tasks:read"],
            }, token=enrollment_token)
            require(direct_session_status == 201, f"direct backend session create failed: {direct_session_status} {direct_session}")
            session_id = direct_session.get("session_id")
            require(session_id and direct_session.get("session_token"), f"direct backend setup missing one-time session token: {direct_session}")

            next_env = os.environ.copy()
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/workers")

            fleet_status, fleet = http_json_status("GET", f"{next_base}/api/mis/workers/fleet")
            require(fleet_status == 200, f"Next worker fleet readback failed: {fleet_status} {fleet}")
            require(fleet.get("provider") == "agentops-worker", f"wrong fleet provider: {fleet}")
            require(fleet.get("operation") == "fleet_view", f"wrong fleet operation: {fleet}")
            require(fleet.get("token_omitted") is True, f"fleet token omission missing: {fleet}")
            require(fleet.get("live_execution_performed") is False, f"fleet unexpectedly performed live execution: {fleet}")
            require((fleet.get("safety") or {}).get("read_only") is True, f"fleet safety read_only missing: {fleet}")
            assert_no_next_secret("worker fleet", fleet)

            hygiene_status, hygiene = http_json_status("GET", f"{next_base}/api/mis/workers/fleet/hygiene?limit=5")
            require(hygiene_status == 200, f"Next worker hygiene readback failed: {hygiene_status} {hygiene}")
            require(hygiene.get("operation") == "fleet_hygiene", f"wrong hygiene operation: {hygiene}")
            require((hygiene.get("safety") or {}).get("read_only") is True, f"hygiene read_only missing: {hygiene}")
            require((hygiene.get("safety") or {}).get("live_execution_performed") is False, f"hygiene unexpectedly performed live execution: {hygiene}")
            require(hygiene.get("token_omitted") is True, f"hygiene token omission missing: {hygiene}")
            assert_no_next_secret("worker hygiene", hygiene)

            sessions_status, sessions = http_json_status("GET", f"{next_base}/api/mis/agent-gateway/sessions")
            require(sessions_status == 200, f"Next session readback failed: {sessions_status} {sessions}")
            require(sessions.get("token_omitted") is True, f"Next sessions token omission missing: {sessions}")
            require(any(item.get("session_ref") for item in sessions.get("sessions", []) if isinstance(item, dict)), f"Next sessions missing safe refs: {sessions}")
            assert_no_next_secret("Next sessions", sessions)

            non_mock_status, non_mock = http_json_status("POST", f"{next_base}/api/mis/workers/local/start", {
                "adapter": "hermes",
                "confirm_run": True,
                "poll_interval": 2,
                "max_tasks": 0,
            })
            require(non_mock_status == 403 and non_mock.get("error") == "mock_daemon_only_next_parity", f"non-mock daemon did not fail closed: {non_mock_status} {non_mock}")
            confirm_status, confirm_blocked = http_json_status("POST", f"{next_base}/api/mis/workers/local/start", {
                "adapter": "mock",
                "confirm_run": True,
                "poll_interval": 2,
                "max_tasks": 0,
            })
            require(confirm_status == 403 and confirm_blocked.get("error") == "live_worker_daemon_not_allowed_next_parity", f"confirm daemon did not fail closed: {confirm_status} {confirm_blocked}")

            token_issue_status, token_issue = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/enrollment/create", {
                "agent_id": f"agt_next_blocked_{stamp}",
                "runtime_type": "mock",
                "workspace_id": "local-demo",
                "scopes": WORKER_SCOPES,
            })
            require(token_issue_status == 403 and token_issue.get("error") == "enrollment_token_issue_not_allowed_next_parity", f"token issue did not fail closed: {token_issue_status} {token_issue}")
            session_create_status, session_create = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/session/create", {
                "ttl_sec": 600,
                "scopes": ["agents:heartbeat"],
            }, token=enrollment_token)
            require(session_create_status == 403 and session_create.get("error") == "gateway_lifecycle_write_not_allowed_next_parity", f"session create did not fail closed: {session_create_status} {session_create}")
            session_revoke_status, session_revoke = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/session/revoke", {"session_id": session_id})
            require(session_revoke_status == 403 and session_revoke.get("error") == "gateway_lifecycle_write_not_allowed_next_parity", f"session revoke did not fail closed: {session_revoke_status} {session_revoke}")
            enrollment_revoke_status, enrollment_revoke = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/enrollment/revoke", {"token_id": token_id})
            require(enrollment_revoke_status == 403 and enrollment_revoke.get("error") == "gateway_lifecycle_write_not_allowed_next_parity", f"enrollment revoke did not fail closed: {enrollment_revoke_status} {enrollment_revoke}")

            pw_env = os.environ.copy()
            opened = playwright(pw_env, "open", f"{next_base}/workspace/workers")
            require(opened.returncode == 0, f"Playwright open failed: {opened.stderr or opened.stdout}")
            resized = playwright(pw_env, "resize", "1365", "900")
            require(resized.returncode == 0, f"Playwright resize failed: {resized.stderr or resized.stdout}")
            snapshot = snapshot_route(next_base, "/workspace/workers", [
                "Worker Console",
                "Worker fleet lanes",
                "Fleet hygiene plan",
                "worker_console_read_model_parity",
                "session token omitted",
                "session id hidden",
                "live daemon blocked",
                "direct token issue blocked",
                "fleet cleanup preview only",
                "execution-mode endpoint pending",
            ], pw_env)

            transcript = json.dumps([
                fleet,
                hygiene,
                sessions,
                non_mock,
                confirm_blocked,
                token_issue,
                session_create,
                session_revoke,
                enrollment_revoke,
                snapshot,
            ], ensure_ascii=False, sort_keys=True)
            assert_no_next_secret("Next worker console transcript", transcript)

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "route": "/workspace/workers",
                "fleet_route": "/api/mis/workers/fleet",
                "hygiene_route": "/api/mis/workers/fleet/hygiene",
                "session_read_route": "/api/mis/agent-gateway/sessions",
                "blocked_live_daemon_status": non_mock_status,
                "blocked_confirm_daemon_status": confirm_status,
                "blocked_token_issue_status": token_issue_status,
                "blocked_session_create_status": session_create_status,
                "blocked_session_revoke_status": session_revoke_status,
                "blocked_enrollment_revoke_status": enrollment_revoke_status,
                "token_omitted": True,
                "secret_leaked": False,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
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
