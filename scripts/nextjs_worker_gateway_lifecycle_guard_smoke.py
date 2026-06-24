#!/usr/bin/env python3
"""Verify Next.js blocks Agent Gateway token/session lifecycle writes."""
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
CONTRACT_ID = "nextjs_worker_gateway_lifecycle_guard_v1"

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


def assert_next_guard(label: str, status: int, payload: Any, operation: str) -> None:
    require(status == 403, f"{label} did not fail closed at Next proxy: {status} {payload}")
    require(payload.get("error") == "gateway_lifecycle_write_not_allowed_next_parity", f"{label} wrong error: {payload}")
    require(payload.get("blocked_operation") == operation, f"{label} wrong blocked operation: {payload}")
    require(payload.get("lifecycle_mutation_performed") is False, f"{label} reported mutation: {payload}")
    require(payload.get("token_omitted") is True, f"{label} token omission missing: {payload}")
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    require("session_token" not in text, f"{label} returned session_token field: {payload}")
    require("token" not in {key.lower() for key in payload if isinstance(key, str) and key != "token_omitted"}, f"{label} returned token field: {payload}")
    require(not leaked_secret(text), f"{label} leaked token-like material: {payload}")


def sessions_by_id(payload: Any) -> dict[str, dict[str, Any]]:
    sessions = payload.get("sessions") if isinstance(payload, dict) else []
    if not isinstance(sessions, list):
        return {}
    return {str(item.get("session_id") or ""): item for item in sessions if isinstance(item, dict)}


def session_refs(payload: Any) -> set[str]:
    sessions = payload.get("sessions") if isinstance(payload, dict) else []
    if not isinstance(sessions, list):
        return set()
    return {str(item.get("session_ref") or "") for item in sessions if isinstance(item, dict) and item.get("session_ref")}


def enrollments_by_id(payload: Any) -> dict[str, dict[str, Any]]:
    enrollments = payload.get("enrollments") if isinstance(payload, dict) else []
    if not isinstance(enrollments, list):
        return {}
    return {str(item.get("token_id") or ""): item for item in enrollments if isinstance(item, dict)}


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Next.js lifecycle guard smoke"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-gateway-lifecycle-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset_env["AGENTOPS_BASE_URL"] = api_base
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_env["AGENTOPS_BASE_URL"] = api_base
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            agent_id = f"agt_next_lifecycle_{stamp}"
            direct_create_status, direct_enrollment = http_json_status("POST", f"{api_base}/api/agent-gateway/enrollment/create", {
                "agent_id": agent_id,
                "name": "Next Lifecycle Guard Agent",
                "runtime_type": "mock",
                "workspace_id": "local-demo",
                "scopes": WORKER_SCOPES,
                "ttl_days": 1,
                "heartbeat_timeout_sec": 60,
            })
            require(direct_create_status == 201, f"direct backend enrollment create failed: {direct_create_status} {direct_enrollment}")
            enrollment_token = direct_enrollment.get("token")
            token_id = direct_enrollment.get("token_id")
            require(enrollment_token and token_id, f"direct backend setup did not return token: {direct_enrollment}")

            direct_session_status, direct_session = http_json_status("POST", f"{api_base}/api/agent-gateway/session/create", {
                "ttl_sec": 600,
                "scopes": ["agents:heartbeat", "tasks:read"],
            }, token=enrollment_token)
            require(direct_session_status == 201, f"direct backend session create failed: {direct_session_status} {direct_session}")
            session_id = direct_session.get("session_id")
            require(session_id and direct_session.get("session_token"), f"direct backend setup did not return session token: {direct_session}")
            require(direct_session.get("token_omitted") is False, "direct backend session create should expose one-time token, proving this path must stay out of Next")

            next_env = os.environ.copy()
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/agents")

            listed_status, listed = http_json_status("GET", f"{next_base}/api/mis/agent-gateway/sessions")
            require(listed_status == 200, f"Next session readback failed: {listed_status} {listed}")
            require(listed.get("token_omitted") is True, f"Next session readback token omission missing: {listed}")
            require(session_refs(listed), f"Next session readback missing safe refs: {listed}")
            safe_list_text = json.dumps(listed, ensure_ascii=False, sort_keys=True)
            require("session_hash" not in safe_list_text and "session_token" not in safe_list_text, f"Next session list leaked secret fields: {listed}")
            require('"session_id":' not in safe_list_text and '"parent_token_id":' not in safe_list_text, f"Next session list leaked raw stable ids: {listed}")
            require(not leaked_secret(safe_list_text), f"Next session list leaked token-like material: {listed}")

            direct_before_status, direct_before_sessions = http_json_status("GET", f"{api_base}/api/agent-gateway/sessions")
            require(direct_before_status == 200, f"backend session list before guards failed: {direct_before_status} {direct_before_sessions}")
            before_session_count = len(sessions_by_id(direct_before_sessions))
            next_create_status, next_create = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/session/create", {
                "ttl_sec": 600,
                "scopes": ["agents:heartbeat"],
            }, token=enrollment_token)
            assert_next_guard("session create", next_create_status, next_create, "agent-gateway/session/create")

            next_revoke_status, next_revoke = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/session/revoke", {
                "session_id": session_id,
            })
            assert_next_guard("session revoke", next_revoke_status, next_revoke, "agent-gateway/session/revoke")

            next_enrollment_revoke_status, next_enrollment_revoke = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/enrollment/revoke", {
                "token_id": token_id,
            })
            assert_next_guard("enrollment revoke", next_enrollment_revoke_status, next_enrollment_revoke, "agent-gateway/enrollment/revoke")

            next_rotate_status, next_rotate = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/enrollment/rotate", {
                "token_id": token_id,
            })
            require(next_rotate_status == 403, f"enrollment rotate did not fail closed at Next proxy: {next_rotate_status} {next_rotate}")
            require(next_rotate.get("error") == "enrollment_token_issue_not_allowed_next_parity", f"enrollment rotate wrong error: {next_rotate}")
            require(next_rotate.get("token_omitted") is True and next_rotate.get("token_issued") is False, f"enrollment rotate token flags wrong: {next_rotate}")
            require(not leaked_secret(json.dumps(next_rotate, ensure_ascii=False, sort_keys=True)), f"enrollment rotate leaked token-like material: {next_rotate}")

            after_sessions_status, after_sessions = http_json_status("GET", f"{api_base}/api/agent-gateway/sessions")
            require(after_sessions_status == 200, f"backend session list after guards failed: {after_sessions_status} {after_sessions}")
            after_sessions_by_id = sessions_by_id(after_sessions)
            require(len(after_sessions_by_id) == before_session_count, f"Next session create guard mutated session count: {after_sessions}")
            require(after_sessions_by_id.get(session_id, {}).get("session_state") == "active", f"Next session revoke guard mutated session: {after_sessions_by_id.get(session_id)}")

            after_enrollments_status, after_enrollments = http_json_status("GET", f"{api_base}/api/agent-gateway/enrollments")
            require(after_enrollments_status == 200, f"backend enrollment list after guard failed: {after_enrollments_status} {after_enrollments}")
            require(enrollments_by_id(after_enrollments).get(token_id, {}).get("status") == "active", f"Next enrollment revoke guard mutated enrollment: {after_enrollments}")

            pw_env = os.environ.copy()
            opened = playwright(pw_env, "open", f"{next_base}/workspace/agents")
            require(opened.returncode == 0, f"Playwright open failed: {opened.stderr or opened.stdout}")
            resized = playwright(pw_env, "resize", "1365", "900")
            require(resized.returncode == 0, f"Playwright resize failed: {resized.stderr or resized.stdout}")
            snapshot = snapshot_route(next_base, "/workspace/agents", [
                "Remote enrollment request",
                "session token omitted",
                "session create blocked",
                "session revoke blocked",
                "enrollment revoke blocked",
                "session id hidden",
            ], pw_env)

            transcript = json.dumps([
                listed,
                next_create,
                next_revoke,
                next_enrollment_revoke,
                next_rotate,
                snapshot,
            ], ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript), "Next lifecycle guard evidence leaked token-like material")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "session_read_route": "/api/mis/agent-gateway/sessions",
                "blocked_session_create_route": "/api/mis/agent-gateway/session/create",
                "blocked_session_revoke_route": "/api/mis/agent-gateway/session/revoke",
                "blocked_enrollment_revoke_route": "/api/mis/agent-gateway/enrollment/revoke",
                "backend_direct_session_token_seen": True,
                "next_session_create_status": next_create_status,
                "next_session_revoke_status": next_revoke_status,
                "next_enrollment_revoke_status": next_enrollment_revoke_status,
                "next_enrollment_rotate_status": next_rotate_status,
                "session_count_after": len(after_sessions_by_id),
                "session_state_after": after_sessions_by_id.get(session_id, {}).get("session_state"),
                "enrollment_status_after": enrollments_by_id(after_enrollments).get(token_id, {}).get("status"),
                "secret_leaked": False,
                "token_omitted": True,
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
