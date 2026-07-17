#!/usr/bin/env python3
"""Prove Postgres-backed Agent Gateway lifecycle HTTP writes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter  # noqa: E402
from storage_postgres_http_read_parity_smoke import (  # noqa: E402
    connect_postgres_when_ready,
    free_port,
    wait_json,
)
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402


CONTRACT_ID = "postgres_http_gateway_lifecycle_write_v1"
WORKSPACE_ID = "ws_pg_gateway_lifecycle"
OTHER_WORKSPACE_ID = "ws_pg_gateway_lifecycle_other"
AGENT_ID = "agt_pg_gateway_lifecycle"
REQUEST_AGENT_ID = "agt_pg_gateway_lifecycle_request"
API_KEY = "postgres_gateway_lifecycle_api_key"
ADMIN_KEY = "postgres_gateway_lifecycle_admin_key"


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_GATEWAY_LIFECYCLE_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_GATEWAY_LIFECYCLE_PG_REEXEC"] = "1"
        os.execv(str(BUNDLED_PYTHON), [str(BUNDLED_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def unavailable(message: str, *, skip: bool) -> int:
    payload = {
        "ok": bool(skip),
        "skipped": bool(skip),
        "contract": CONTRACT_ID,
        "reason": message,
        "next_action": "Run again with Docker and optional psycopg available; skipped mode is diagnostic only.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if skip else 1


def redact(value: str, *secrets: str) -> str:
    redacted = value or ""
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def safe_json(value) -> str:
    def scrub(item):
        if isinstance(item, dict):
            return {
                key: ("[REDACTED]" if key in {"token", "session_token", "token_hash", "session_hash"} else scrub(val))
                for key, val in item.items()
            }
        if isinstance(item, list):
            return [scrub(val) for val in item]
        return item

    return json.dumps(scrub(value), ensure_ascii=False, sort_keys=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    token: str | None = None,
    admin_key: str | None = None,
    query: dict | None = None,
) -> tuple[int, dict]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode({key: val for key, val in query.items() if val is not None}, doseq=True)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if admin_key:
        headers["X-AgentOps-Admin-Key"] = admin_key
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as res:
            raw = res.read().decode("utf-8")
            return int(res.status), json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return int(exc.code), payload


def server_env(dsn: str, pythonpath: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "AGENTOPS_STORAGE_BACKEND": "postgres",
            "AGENTOPS_EDITION": "enterprise_byoc",
            "AGENTOPS_POSTGRES_DSN": dsn,
            "AGENTOPS_ENABLE_POSTGRES_STORAGE": "1",
            "AGENTOPS_POSTGRES_READ_ONLY_HTTP": "1",
            "AGENTOPS_POSTGRES_WRITE_HTTP": "1",
            "AGENTOPS_API_KEY": API_KEY,
            "AGENTOPS_ADMIN_KEY": ADMIN_KEY,
            "PYTHONPATH": pythonpath,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    env.pop("AGENTOPS_DB_PATH", None)
    return env


def start_server(env: dict[str, str], port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def stop_server(proc: subprocess.Popen[str] | None) -> tuple[str, str]:
    if proc is None:
        return "", ""
    proc.terminate()
    try:
        out, err = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate(timeout=5)
    return out or "", err or ""


def seed_reference_rows(adapter: PostgresAdapter) -> None:
    now = "2026-07-17T00:00:00+00:00"
    adapter.execute(
        "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
        ("usr_founder", "Founder", "founder@example.local", "founder", now),
    )
    adapter.execute(
        """INSERT INTO runtime_connectors(runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,require_confirm_run,trust_status,trust_note,trust_updated_at,last_health_at,last_error,created_at,updated_at)
        VALUES(:runtime_connector_id,:provider,:connector_type,:profile_name,:base_url,:binary_path,:status,:allow_real_run,:require_confirm_run,:trust_status,:trust_note,:trust_updated_at,:last_health_at,:last_error,:created_at,:updated_at)""",
        {
            "runtime_connector_id": "rtc_agent_gateway_local",
            "provider": "agent-gateway",
            "connector_type": "local_cli_api_mcp",
            "profile_name": "postgres-gateway-lifecycle-smoke",
            "base_url": "http://127.0.0.1:8787/api/agent-gateway",
            "binary_path": None,
            "status": "ready",
            "allow_real_run": 0,
            "require_confirm_run": 1,
            "trust_status": "trusted",
            "trust_note": "Postgres Gateway lifecycle smoke reference connector.",
            "trust_updated_at": now,
            "last_health_at": now,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    adapter.commit()


def safe_ref(prefix: str, value: str) -> str:
    return server.stable_id(prefix, value)[-12:] if value else ""


def assert_secret_absent(label: str, haystack, *secrets: str) -> None:
    text = haystack if isinstance(haystack, str) else json.dumps(haystack, ensure_ascii=False, sort_keys=True)
    for secret in secrets:
        if secret and secret in text:
            raise AssertionError(f"{label} leaked a one-time token")


def run_lifecycle(base_url: str, adapter: PostgresAdapter, observed_secrets: list[str]) -> dict:
    failures: list[str] = []

    backend_status, backend = request_json(base_url, "/api/storage/backend-status")
    require(backend_status == 200 and backend.get("writes_allowed") is True, f"backend not writable: {safe_json(backend)}")
    allowlist = {f"{route.get('method')} {route.get('path')}" for route in backend.get("write_allowlist") or []}
    expected_routes = {
        "POST /api/agent-gateway/register",
        "POST /api/agent-gateway/enrollment/policy-preview",
        "POST /api/agent-gateway/enrollment/request",
        "POST /api/agent-gateway/enrollment/create",
        "POST /api/agent-gateway/enrollment/issue-approved",
        "POST /api/agent-gateway/enrollment/rotate",
        "POST /api/agent-gateway/enrollment/revoke",
        "POST /api/agent-gateway/session/create",
        "POST /api/agent-gateway/session/revoke",
    }
    missing_routes = sorted(expected_routes - allowlist)
    require(not missing_routes, f"missing lifecycle routes in write allowlist: {missing_routes}")

    preview_status, preview = request_json(
        base_url,
        "/api/agent-gateway/enrollment/policy-preview",
        method="POST",
        body={"workspace_id": WORKSPACE_ID, "runtime_type": "mock", "scopes": ["agents:heartbeat", "tasks:read"]},
    )
    require(preview_status == 200 and preview.get("ledger_mutated") is not True, f"policy preview failed: {safe_json(preview)}")

    blocked_status, blocked = request_json(
        base_url,
        "/api/agent-gateway/enrollment/create",
        method="POST",
        body={"agent_id": f"{AGENT_ID}_blocked", "workspace_id": WORKSPACE_ID, "scopes": ["agents:heartbeat"]},
        admin_key="wrong-admin-key",
    )
    require(blocked_status == 401, f"wrong admin key was not rejected: {blocked_status} {safe_json(blocked)}")

    register_status, registered = request_json(
        base_url,
        "/api/agent-gateway/register",
        method="POST",
        token=API_KEY,
        body={
            "agent_id": AGENT_ID,
            "name": "Postgres Gateway Lifecycle",
            "runtime_type": "mock",
            "workspace_id": WORKSPACE_ID,
            "scopes": ["agent_gateway.task", "agent_gateway.run", "agent_gateway.audit"],
        },
    )
    require(register_status == 201 and (registered.get("agent") or {}).get("agent_id") == AGENT_ID, f"register failed: {register_status} {safe_json(registered)}")

    request_status, requested = request_json(
        base_url,
        "/api/agent-gateway/enrollment/request",
        method="POST",
        body={
            "agent_id": REQUEST_AGENT_ID,
            "name": "Postgres Request Agent",
            "runtime_type": "mock",
            "workspace_id": WORKSPACE_ID,
            "scopes": ["agents:heartbeat", "tasks:read"],
            "reason": "Postgres lifecycle smoke request.",
        },
    )
    require(request_status == 201 and requested.get("token_issued") is False, f"enrollment request failed: {request_status} {safe_json(requested)}")
    request = requested.get("request") or {}
    request_id = request.get("request_id")
    approval_id = request.get("approval_id")
    require(request_id and approval_id, f"enrollment request identifiers missing: {safe_json(requested)}")
    request_row = adapter.fetchone("SELECT status,workspace_id,agent_id,token_id FROM agent_gateway_enrollment_requests WHERE request_id=?", [request_id])
    require(request_row and request_row.get("status") == "pending" and not request_row.get("token_id"), f"request row mismatch: {request_row}")

    issue_block_status, issue_block = request_json(
        base_url,
        "/api/agent-gateway/enrollment/issue-approved",
        method="POST",
        body={"request_id": request_id},
        admin_key=ADMIN_KEY,
    )
    require(issue_block_status == 409 and issue_block.get("error") == "approval_required", f"unapproved issue was not business-blocked: {issue_block_status} {safe_json(issue_block)}")

    approve_status, approved = request_json(
        base_url,
        f"/api/approvals/{approval_id}/approve",
        method="POST",
        body={},
    )
    require(approve_status == 200 and approved.get("decision") == "approved", f"enrollment approval failed: {approve_status} {safe_json(approved)}")
    approved_request_row = adapter.fetchone("SELECT status,token_id FROM agent_gateway_enrollment_requests WHERE request_id=?", [request_id])
    require(approved_request_row and approved_request_row.get("status") == "approved", f"approved request row mismatch: {approved_request_row}")

    issue_status, issued = request_json(
        base_url,
        "/api/agent-gateway/enrollment/issue-approved",
        method="POST",
        body={"approval_id": approval_id, "ttl_days": 1, "heartbeat_timeout_sec": 60},
        admin_key=ADMIN_KEY,
    )
    require(issue_status == 201 and issued.get("issued_from_request_id") == request_id, f"approved issue failed: {issue_status} {safe_json(issued)}")
    approved_token = issued.get("token")
    approved_token_id = issued.get("token_id")
    require(approved_token and approved_token_id, "approved issue did not return one-time token and token id")
    observed_secrets.append(approved_token)
    approved_heartbeat_status, approved_heartbeat = request_json(
        base_url,
        "/api/agent-gateway/heartbeat",
        method="POST",
        body={"status": "idle", "summary": "approved enrollment online"},
        token=approved_token,
    )
    require(approved_heartbeat_status == 200, f"approved token heartbeat failed: {approved_heartbeat_status} {safe_json(approved_heartbeat)}")
    approved_revoke_status, approved_revoke = request_json(
        base_url,
        "/api/agent-gateway/enrollment/revoke",
        method="POST",
        body={"token_id": approved_token_id},
        admin_key=ADMIN_KEY,
    )
    require(approved_revoke_status == 200 and approved_revoke.get("revoked") == 1, f"approved token revoke failed: {approved_revoke_status} {safe_json(approved_revoke)}")

    create_status, created = request_json(
        base_url,
        "/api/agent-gateway/enrollment/create",
        method="POST",
        body={
            "agent_id": AGENT_ID,
            "name": "Postgres Gateway Lifecycle",
            "runtime_type": "mock",
            "workspace_id": WORKSPACE_ID,
            "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        },
        admin_key=ADMIN_KEY,
    )
    require(create_status == 201, f"enrollment create failed: {create_status} {safe_json(created)}")
    enrollment_token = created.get("token")
    token_id = created.get("token_id")
    require(enrollment_token and token_id, "enrollment create did not return one-time token and token id")
    observed_secrets.append(enrollment_token)
    token_row = adapter.fetchone(
        "SELECT token_hash,workspace_id,agent_id,status,last_used_at,last_heartbeat_at FROM agent_gateway_tokens WHERE token_id=?",
        [token_id],
    )
    require(token_row and token_row.get("token_hash") == server.token_hash(enrollment_token), f"token hash row mismatch: {token_row}")
    assert_secret_absent("token row", token_row, enrollment_token)

    cross_status, cross = request_json(
        base_url,
        "/api/agent-gateway/heartbeat",
        method="POST",
        body={"workspace_id": OTHER_WORKSPACE_ID, "status": "idle"},
        token=enrollment_token,
    )
    require(cross_status == 403, f"cross-workspace token heartbeat was not rejected: {cross_status} {safe_json(cross)}")

    session_status, session = request_json(
        base_url,
        "/api/agent-gateway/session/create",
        method="POST",
        body={"ttl_sec": 120, "scopes": ["agents:heartbeat", "tasks:read"]},
        token=enrollment_token,
    )
    require(session_status == 201, f"session create failed: {session_status} {safe_json(session)}")
    session_token = session.get("session_token")
    session_id = session.get("session_id")
    require(session_token and session_id, "session create did not return one-time token and session id")
    observed_secrets.append(session_token)
    session_row = adapter.fetchone(
        "SELECT session_hash,parent_token_id,workspace_id,agent_id,status,last_used_at FROM agent_gateway_sessions WHERE session_id=?",
        [session_id],
    )
    require(session_row and session_row.get("session_hash") == server.token_hash(session_token), f"session hash row mismatch: {session_row}")
    require(session_row.get("parent_token_id") == token_id, f"session parent token mismatch: {session_row}")
    assert_secret_absent("session row", session_row, session_token, enrollment_token)

    nested_status, nested = request_json(
        base_url,
        "/api/agent-gateway/session/create",
        method="POST",
        body={"ttl_sec": 30},
        token=session_token,
    )
    require(nested_status == 401, f"session minted nested session: {nested_status} {safe_json(nested)}")

    heartbeat_status, heartbeat = request_json(
        base_url,
        "/api/agent-gateway/heartbeat",
        method="POST",
        body={"status": "idle", "summary": "postgres lifecycle heartbeat"},
        token=session_token,
    )
    require(heartbeat_status == 200 and heartbeat.get("agent_id") == AGENT_ID, f"session heartbeat failed: {heartbeat_status} {safe_json(heartbeat)}")
    heartbeat_row = adapter.fetchone(
        "SELECT last_used_at,last_heartbeat_at FROM agent_gateway_tokens WHERE token_id=?",
        [token_id],
    )
    require(heartbeat_row and heartbeat_row.get("last_used_at") and heartbeat_row.get("last_heartbeat_at"), f"token heartbeat timestamps missing: {heartbeat_row}")

    listed_status, listed = request_json(
        base_url,
        "/api/agent-gateway/sessions",
        admin_key=ADMIN_KEY,
        query={"workspace_id": WORKSPACE_ID},
    )
    require(listed_status == 200, f"session list failed: {listed_status} {safe_json(listed)}")
    assert_secret_absent("session list", listed, session_token, enrollment_token)
    for item in listed.get("sessions") or []:
        if item.get("session_id") == session_id:
            require("session_hash" not in item, f"session list leaked hash: {safe_json(item)}")

    revoke_session_status, revoked_session = request_json(
        base_url,
        "/api/agent-gateway/session/revoke",
        method="POST",
        body={"session_id": session_id},
        admin_key=ADMIN_KEY,
    )
    require(revoke_session_status == 200 and revoked_session.get("revoked") == 1, f"session revoke failed: {revoke_session_status} {safe_json(revoked_session)}")
    revoked_heartbeat_status, revoked_heartbeat = request_json(
        base_url,
        "/api/agent-gateway/heartbeat",
        method="POST",
        body={"status": "idle"},
        token=session_token,
    )
    require(revoked_heartbeat_status == 401, f"revoked session still authenticated: {revoked_heartbeat_status} {safe_json(revoked_heartbeat)}")

    rotate_status, rotated = request_json(
        base_url,
        "/api/agent-gateway/enrollment/rotate",
        method="POST",
        body={"token_id": token_id, "ttl_days": 1},
        admin_key=ADMIN_KEY,
    )
    require(rotate_status == 201, f"enrollment rotate failed: {rotate_status} {safe_json(rotated)}")
    rotated_token = rotated.get("token")
    rotated_token_id = rotated.get("token_id")
    require(rotated_token and rotated_token_id and rotated_token_id != token_id, "rotate did not return replacement token")
    observed_secrets.append(rotated_token)
    old_row = adapter.fetchone("SELECT status,revoked_at FROM agent_gateway_tokens WHERE token_id=?", [token_id])
    new_row = adapter.fetchone("SELECT token_hash,status FROM agent_gateway_tokens WHERE token_id=?", [rotated_token_id])
    require(old_row and old_row.get("status") == "revoked" and old_row.get("revoked_at"), f"old token not revoked: {old_row}")
    require(new_row and new_row.get("status") == "active" and new_row.get("token_hash") == server.token_hash(rotated_token), f"new token row mismatch: {new_row}")
    assert_secret_absent("rotated token row", new_row, rotated_token)

    old_token_status, old_token_payload = request_json(
        base_url,
        "/api/agent-gateway/heartbeat",
        method="POST",
        body={"status": "idle"},
        token=enrollment_token,
    )
    require(old_token_status == 401, f"old token still authenticated after rotate: {old_token_status} {safe_json(old_token_payload)}")

    rotated_session_status, rotated_session = request_json(
        base_url,
        "/api/agent-gateway/session/create",
        method="POST",
        body={"ttl_sec": 120, "scopes": ["agents:heartbeat"]},
        token=rotated_token,
    )
    require(rotated_session_status == 201, f"rotated token could not mint session: {rotated_session_status} {safe_json(rotated_session)}")
    rotated_session_token = rotated_session.get("session_token")
    rotated_session_id = rotated_session.get("session_id")
    require(rotated_session_token and rotated_session_id, "rotated token session response missing token/id")
    observed_secrets.append(rotated_session_token)

    revoke_enrollment_status, revoked_enrollment = request_json(
        base_url,
        "/api/agent-gateway/enrollment/revoke",
        method="POST",
        body={"token_id": rotated_token_id},
        admin_key=ADMIN_KEY,
    )
    require(revoke_enrollment_status == 200 and revoked_enrollment.get("revoked") == 1, f"enrollment revoke failed: {revoke_enrollment_status} {safe_json(revoked_enrollment)}")
    require(revoked_enrollment.get("sessions_revoked", 0) >= 1, f"enrollment revoke did not cascade sessions: {safe_json(revoked_enrollment)}")
    revoked_token_status, revoked_token_payload = request_json(
        base_url,
        "/api/agent-gateway/heartbeat",
        method="POST",
        body={"status": "idle"},
        token=rotated_token,
    )
    require(revoked_token_status == 401, f"revoked token still authenticated: {revoked_token_status} {safe_json(revoked_token_payload)}")
    revoked_session_status, revoked_session_payload = request_json(
        base_url,
        "/api/agent-gateway/heartbeat",
        method="POST",
        body={"status": "idle"},
        token=rotated_session_token,
    )
    require(revoked_session_status == 401, f"cascade-revoked session still authenticated: {revoked_session_status} {safe_json(revoked_session_payload)}")

    audit_rows = adapter.fetchall(
        "SELECT metadata_json FROM audit_logs WHERE action LIKE 'agent_gateway.%' ORDER BY created_at DESC LIMIT 50",
    )
    runtime_rows = adapter.fetchall(
        "SELECT input_summary,output_summary,error_message,raw_payload_hash FROM runtime_events WHERE event_type LIKE 'agent.%' ORDER BY created_at DESC LIMIT 50",
    )
    assert_secret_absent("audit rows", audit_rows, approved_token, enrollment_token, session_token, rotated_token, rotated_session_token)
    assert_secret_absent("runtime rows", runtime_rows, approved_token, enrollment_token, session_token, rotated_token, rotated_session_token)

    if failures:
        raise AssertionError("; ".join(failures))

    return {
        "contract": CONTRACT_ID,
        "workspace_id": WORKSPACE_ID,
        "agent_id": AGENT_ID,
        "request_ref": safe_ref("enroll_req_ref", request_id),
        "approval_ref": safe_ref("approval_ref", approval_id),
        "approved_token_ref": safe_ref("token_ref", approved_token_id),
        "token_ref": safe_ref("token_ref", token_id),
        "rotated_token_ref": safe_ref("token_ref", rotated_token_id),
        "session_ref": safe_ref("session_ref", session_id),
        "rotated_session_ref": safe_ref("session_ref", rotated_session_id),
        "rbac_checks": {
            "wrong_admin_rejected": blocked_status == 401,
            "cross_workspace_rejected": cross_status == 403,
            "nested_session_rejected": nested_status == 401,
            "revoked_session_rejected": revoked_heartbeat_status == 401,
            "old_token_rejected_after_rotate": old_token_status == 401,
            "revoked_token_rejected": revoked_token_status == 401,
            "approved_enrollment_token_heartbeat": approved_heartbeat_status == 200,
        },
        "db_readback": {
            "request_status": approved_request_row.get("status"),
            "old_token_status": old_row.get("status"),
            "new_token_status_after_create": new_row.get("status"),
            "heartbeat_recorded": bool(heartbeat_row.get("last_heartbeat_at")),
            "audit_rows_checked": len(audit_rows),
            "runtime_rows_checked": len(runtime_rows),
        },
        "safety": {
            "token_values_omitted_from_evidence": True,
            "token_hashes_omitted_from_http_readback": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "private_transcripts_omitted": True,
        },
        "token_omitted": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Postgres-backed Agent Gateway lifecycle write smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE, help="Postgres Docker image to use.")
    parser.add_argument("--skip-if-unavailable", action="store_true", help="Return success with skipped=true when Docker or psycopg is unavailable.")
    parser.add_argument("--no-install-driver", action="store_true", help="Do not install psycopg into a temporary target when missing.")
    args = parser.parse_args()

    reexec_self_with_bundled_python_if_needed()

    early = container_smoke.docker_available(args.skip_if_unavailable)
    if early is not None:
        return early
    early = container_smoke.ensure_image(args.image, args.skip_if_unavailable)
    if early is not None:
        return early

    with tempfile.TemporaryDirectory(prefix="agentops-pg-gateway-lifecycle-") as temp_dir:
        temp_root = Path(temp_dir)
        driver_ok, driver_status = ensure_psycopg(temp_root, install=not args.no_install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=args.skip_if_unavailable)

        pythonpath_parts = [str(ROOT)]
        package_target = temp_root / "python-packages"
        if package_target.exists():
            pythonpath_parts.insert(0, str(package_target))
        if os.environ.get("PYTHONPATH"):
            pythonpath_parts.append(os.environ["PYTHONPATH"])
        pythonpath = os.pathsep.join(pythonpath_parts)

        container = f"agentops-pg-gateway-lifecycle-{container_smoke.secrets.token_hex(6)}"
        pg_auth = container_smoke.secrets.token_urlsafe(18)
        started = container_smoke.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                container,
                "-p",
                "127.0.0.1::5432",
                "-e",
                "POSTGRES_USER=agentops",
                "-e",
                "POSTGRES_DB=agentops",
                "-e",
                f"POSTGRES_PASSWORD={pg_auth}",
                args.image,
            ],
            timeout=60,
        )
        if started.returncode != 0:
            detail = redact((started.stderr or started.stdout or "docker run failed").strip(), pg_auth)
            return unavailable(f"Postgres container failed to start: {detail}", skip=args.skip_if_unavailable)

        adapter: PostgresAdapter | None = None
        proc: subprocess.Popen[str] | None = None
        secret_values: list[str] = []
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=args.skip_if_unavailable)
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = connect_postgres_when_ready(dsn, secret=pg_auth)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            seed_reference_rows(adapter)
            http_port = free_port()
            proc = start_server(server_env(dsn, pythonpath), http_port)
            base_url = f"http://127.0.0.1:{http_port}"
            wait_json(f"{base_url}/api/storage/backend-status", proc, secret=pg_auth)
            payload = run_lifecycle(base_url, adapter, secret_values)
            secret_values.extend(
                value
                for row in adapter.fetchall("SELECT token_hash FROM agent_gateway_tokens")
                for value in [row.get("token_hash")]
                if value
            )
            stdout, stderr = stop_server(proc)
            proc = None
            assert_secret_absent("server stdout/stderr", stdout + stderr, *secret_values)
            print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        except Exception as exc:
            stdout, stderr = stop_server(proc)
            proc = None
            detail = redact(str(exc), pg_auth, API_KEY, ADMIN_KEY, *secret_values)
            logs = redact((stdout or "") + (stderr or ""), pg_auth, API_KEY, ADMIN_KEY, *secret_values)
            print(
                json.dumps(
                    {
                        "ok": False,
                        "contract": CONTRACT_ID,
                        "error": detail,
                        "server_log_sha256": hashlib.sha256(logs.encode("utf-8", errors="replace")).hexdigest(),
                        "server_log_size_bytes": len(logs.encode("utf-8", errors="replace")),
                        "server_log_text_stored": False,
                        "token_omitted": True,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
            return 1
        finally:
            stop_server(proc)
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
