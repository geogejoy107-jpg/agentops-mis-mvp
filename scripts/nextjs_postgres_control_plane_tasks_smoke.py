#!/usr/bin/env python3
"""Prove Next.js owns scoped Agent Gateway task writes directly in Postgres."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_postgres_control_plane_tasks_v1"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter  # noqa: E402
from nextjs_playwright_snapshot_smoke import free_port, require, run, start_process  # noqa: E402
from storage_postgres_http_read_parity_smoke import connect_postgres_when_ready  # noqa: E402
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402


WORKSPACE_ID = "ws_ts_control_plane"
OTHER_WORKSPACE_ID = "ws_ts_control_plane_other"
AGENT_ID = "agt_ts_control_plane"
OTHER_AGENT_ID = "agt_ts_control_plane_other"
TASK_ID = "tsk_ts_control_plane"
OTHER_TASK_ID = "tsk_ts_control_plane_other"
RUN_ID = "run_ts_control_plane"
CONCURRENT_RUN_ID = "run_ts_control_plane_concurrent"
CONFLICT_RUN_ID = "run_ts_control_plane_conflicting_terminal"
RUN_PLAN_ID = "plan_ts_control_plane"
CONFLICT_PLAN_ID = "plan_ts_control_plane_conflicting_terminal"
EVIDENCE_TASK_ID = "tsk_ts_control_plane_evidence"
EVIDENCE_RUN_ID = "run_ts_control_plane_evidence"
EVIDENCE_PLAN_ID = "plan_ts_control_plane_evidence"
MANIFEST_ID = "pem_ts_control_plane_evidence"
BLOCKED_MANIFEST_ID = "pem_ts_control_plane_blocked"
UNPLANNED_TASK_ID = "tsk_ts_control_plane_unplanned"
HIGH_RISK_TASK_ID = "tsk_ts_control_plane_high_risk_plan"
HIGH_RISK_PLAN_ID = "plan_ts_control_plane_high_risk"
TOOL_CALL_ID = "tc_ts_control_plane_evidence"
HIGH_RISK_TOOL_CALL_ID = "tc_ts_control_plane_high_risk"
EVALUATION_ID = "eval_ts_control_plane_evidence"
ARTIFACT_ID = "art_ts_control_plane_evidence"
OTHER_EVIDENCE_RUN_ID = "run_ts_control_plane_other_evidence"
OTHER_TOOL_CALL_ID = "tc_ts_control_plane_other_evidence"
OTHER_EVALUATION_ID = "eval_ts_control_plane_other_evidence"
OTHER_ARTIFACT_ID = "art_ts_control_plane_other_evidence"
REQUESTER_ID = "usr_ts_control_plane_requester"
OTHER_REQUESTER_ID = "usr_ts_control_plane_other_requester"


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_TS_CONTROL_PLANE_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists() or Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_TS_CONTROL_PLANE_PG_REEXEC"] = "1"
        os.execv(str(BUNDLED_PYTHON), [str(BUNDLED_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def unavailable(message: str, *, skip: bool) -> int:
    print(json.dumps({
        "ok": bool(skip),
        "skipped": bool(skip),
        "contract": CONTRACT_ID,
        "reason": message,
        "next_action": "Run with Docker, Node dependencies, and psycopg available; skipped evidence is diagnostic only.",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if skip else 1


def http_json(
    method: str,
    url: str,
    body: dict | None = None,
    *,
    token: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    request_headers = dict(headers or {})
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def wait_for_next(url: str, proc: subprocess.Popen[str], *, secret: str, timeout_sec: int = 60) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=2)
            detail = f"Next.js exited early rc={proc.returncode} stdout={stdout} stderr={stderr}"
            raise RuntimeError(detail.replace(secret, "[REDACTED]"))
        try:
            status, payload = http_json("GET", url)
            if status == 401 and payload.get("error") == "unauthorized":
                return
            last_error = f"unexpected readiness response {status}: {payload}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"Next.js TypeScript control-plane route did not become ready: {last_error}".replace(secret, "[REDACTED]"))


def endpoint_unreachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.5):
            return False
    except urllib.error.HTTPError:
        return False
    except urllib.error.URLError:
        return True


def seed(
    adapter: PostgresAdapter,
    *,
    token: str,
    observer_token: str,
    other_token: str,
    session: str,
    expired_token: str,
    orphan_session: str,
    expired_parent_session: str,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    expires = (now + dt.timedelta(days=1)).isoformat()
    expired_at = (now - dt.timedelta(minutes=1)).isoformat()
    now_text = now.isoformat()
    users = [
        ("usr_founder", "founder-ts@example.local"),
        ("usr_customer_demo", "customer-ts@example.local"),
        (REQUESTER_ID, "requester-ts@example.local"),
        (OTHER_REQUESTER_ID, "other-requester-ts@example.local"),
    ]
    for user_id, email in users:
        adapter.execute(
            "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
            (user_id, user_id, email, "founder" if user_id == "usr_founder" else "customer", now_text),
        )
    for agent_id in [AGENT_ID, OTHER_AGENT_ID]:
        adapter.execute(
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                agent_id,
                agent_id,
                "operator",
                "TypeScript Postgres control-plane smoke agent.",
                "mock",
                "mock",
                "mock-model",
                "idle",
                "standard",
                "[]",
                0,
                "usr_founder",
                now_text,
                now_text,
            ),
        )
    adapter.execute(
        """INSERT INTO runtime_connectors(runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,require_confirm_run,trust_status,trust_note,trust_updated_at,last_health_at,last_error,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "rtc_agent_gateway_local",
            "agent_gateway",
            "local",
            "TypeScript control plane",
            None,
            None,
            "ready",
            0,
            1,
            "trusted",
            None,
            now_text,
            now_text,
            None,
            now_text,
            now_text,
        ),
    )
    token_rows = [
        ("tok_ts_control_plane", token, WORKSPACE_ID, AGENT_ID, ["tasks:create", "tasks:read", "runs:write", "toolcalls:write", "evaluations:submit", "artifacts:write", "agent_plans:write", "plan_evidence:write"]),
        ("tok_ts_control_plane_observer", observer_token, WORKSPACE_ID, AGENT_ID, ["tasks:read"]),
        ("tok_ts_control_plane_other", other_token, OTHER_WORKSPACE_ID, OTHER_AGENT_ID, ["tasks:create", "tasks:read", "runs:write", "toolcalls:write", "evaluations:submit", "artifacts:write", "agent_plans:write", "plan_evidence:write"]),
    ]
    for token_id, raw_token, workspace_id, agent_id, scopes in token_rows:
        adapter.execute(
            """INSERT INTO agent_gateway_tokens(token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at)
            VALUES(?,?,?,?,?,'active',?,60,?,?,NULL,NULL,NULL)""",
            (token_id, server.token_hash(raw_token), workspace_id, agent_id, json.dumps(scopes), "TypeScript control-plane smoke", now_text, expires),
        )
    adapter.execute(
        """INSERT INTO agent_gateway_tokens(token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at)
        VALUES(?,?,?,?,?,'active',?,60,?,?,NULL,NULL,NULL)""",
        (
            "tok_ts_control_plane_expired",
            server.token_hash(expired_token),
            WORKSPACE_ID,
            AGENT_ID,
            json.dumps(["tasks:read"]),
            "TypeScript expired credential smoke",
            now_text,
            expired_at,
        ),
    )
    adapter.execute(
        """INSERT INTO agent_gateway_tokens(token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at)
        VALUES(?,?,?,?,?,'revoked',?,60,?,?,?,NULL,NULL)""",
        (
            "tok_ts_control_plane_revoked_parent",
            server.token_hash("unused-revoked-parent-credential"),
            WORKSPACE_ID,
            AGENT_ID,
            json.dumps(["tasks:read"]),
            "TypeScript revoked parent smoke",
            now_text,
            expires,
            now_text,
        ),
    )
    adapter.execute(
        """INSERT INTO agent_gateway_tokens(token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at)
        VALUES(?,?,?,?,?,'active',?,60,?,?,NULL,NULL,NULL)""",
        (
            "tok_ts_control_plane_expired_parent",
            server.token_hash("unused-expired-parent-credential"),
            WORKSPACE_ID,
            AGENT_ID,
            json.dumps(["tasks:read"]),
            "TypeScript expired parent smoke",
            now_text,
            expired_at,
        ),
    )
    adapter.execute(
        """INSERT INTO agent_gateway_sessions(session_id,session_hash,parent_token_id,workspace_id,agent_id,scopes_json,status,created_at,expires_at,revoked_at,last_used_at)
        VALUES(?,?,?,?,?,?,'active',?,?,NULL,NULL)""",
        (
            "ses_ts_control_plane",
            server.token_hash(session),
            "tok_ts_control_plane",
            WORKSPACE_ID,
            AGENT_ID,
            json.dumps(["tasks:create", "tasks:read", "runs:write", "toolcalls:write", "evaluations:submit", "artifacts:write", "agent_plans:write", "plan_evidence:write"]),
            now_text,
            expires,
        ),
    )
    adapter.execute(
        """INSERT INTO agent_gateway_sessions(session_id,session_hash,parent_token_id,workspace_id,agent_id,scopes_json,status,created_at,expires_at,revoked_at,last_used_at)
        VALUES(?,?,?,?,?,?,'active',?,?,NULL,NULL)""",
        (
            "ses_ts_control_plane_orphan",
            server.token_hash(orphan_session),
            "tok_ts_control_plane_revoked_parent",
            WORKSPACE_ID,
            AGENT_ID,
            json.dumps(["tasks:read"]),
            now_text,
            expires,
        ),
    )
    adapter.execute(
        """INSERT INTO agent_gateway_sessions(session_id,session_hash,parent_token_id,workspace_id,agent_id,scopes_json,status,created_at,expires_at,revoked_at,last_used_at)
        VALUES(?,?,?,?,?,?,'active',?,?,NULL,NULL)""",
        (
            "ses_ts_control_plane_expired_parent",
            server.token_hash(expired_parent_session),
            "tok_ts_control_plane_expired_parent",
            WORKSPACE_ID,
            AGENT_ID,
            json.dumps(["tasks:read"]),
            now_text,
            expires,
        ),
    )
    adapter.commit()


def task_body(
    task_id: str,
    *,
    owner_agent_id: str,
    workspace_id: str | None = None,
    requester_id: str | None = None,
) -> dict:
    body = {
        "task_id": task_id,
        "title": "TypeScript owns this Postgres task",
        "description": "Created without starting the Python MIS API.",
        "owner_agent_id": owner_agent_id,
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Task, runtime event, and audit chain persist atomically in Postgres.",
        "budget_limit_usd": 1.0,
    }
    if workspace_id is not None:
        body["workspace_id"] = workspace_id
    if requester_id is not None:
        body["requester_id"] = requester_id
    return body


def agent_plan_body(
    plan_id: str,
    task_id: str,
    *,
    risk_level: str = "low",
    task_understanding: str = "Execute the task through the TypeScript/Postgres control plane.",
) -> dict:
    return {
        "plan_id": plan_id,
        "task_id": task_id,
        "task_understanding": task_understanding,
        "referenced_specs": ["docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md"],
        "referenced_memories": ["project-memory:commercial-migration"],
        "referenced_bases": ["typescript-postgres-control-plane"],
        "proposed_files_to_change": ["ui/next-app/src/server/controlPlane"],
        "risk_level": risk_level,
        "execution_steps": [
            "Read the task-bound contract and current ledger state.",
            "Execute only through the authenticated Agent Gateway.",
            "Write bounded evidence and verify the audit chain.",
        ],
        "verification_plan": "Require bound tool, evaluation, artifact, and audit evidence.",
        "rollback_plan": "Stop the run and retain immutable evidence for operator review.",
        "status": "submitted",
    }


def audit_chain_valid(rows: list[dict], *, initial_previous: str = "genesis") -> bool:
    previous = initial_previous
    for row in rows:
        try:
            metadata = json.loads(row.get("metadata_json") or "{}")
        except json.JSONDecodeError:
            return False
        expected = server.stable_hash({
            "actor_type": row.get("actor_type"),
            "actor_id": row.get("actor_id"),
            "action": row.get("action"),
            "entity_type": row.get("entity_type"),
            "entity_id": row.get("entity_id"),
            "before_hash": row.get("before_hash"),
            "after_hash": row.get("after_hash"),
            "metadata_json": metadata,
            "previous": previous,
        })
        if row.get("tamper_chain_hash") != expected:
            return False
        previous = str(row.get("tamper_chain_hash") or "")
    return bool(rows)


def seed_future_audit_head(adapter: PostgresAdapter) -> tuple[str, float]:
    created_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=2)
    metadata: dict = {}
    chain_hash = server.stable_hash({
        "actor_type": "system",
        "actor_id": "typescript-control-plane-smoke",
        "action": "control_plane.future_audit_head",
        "entity_type": "runtime_connectors",
        "entity_id": "rtc_agent_gateway_local",
        "before_hash": None,
        "after_hash": None,
        "metadata_json": metadata,
        "previous": "genesis",
    })
    adapter.execute(
        """INSERT INTO audit_logs(
        audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "aud_ts_control_plane_future_head",
            "system",
            "typescript-control-plane-smoke",
            "control_plane.future_audit_head",
            "runtime_connectors",
            "rtc_agent_gateway_local",
            None,
            None,
            json.dumps(metadata),
            chain_hash,
            created_at.isoformat(timespec="microseconds"),
        ),
    )
    adapter.commit()
    return chain_hash, created_at.timestamp()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Next.js direct-Postgres control-plane task smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE)
    parser.add_argument("--skip-if-unavailable", action="store_true")
    parser.add_argument("--no-install-driver", action="store_true")
    args = parser.parse_args()

    reexec_self_with_bundled_python_if_needed()
    early = container_smoke.docker_available(args.skip_if_unavailable)
    if early is not None:
        return early
    early = container_smoke.ensure_image(args.image, args.skip_if_unavailable)
    if early is not None:
        return early
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        return unavailable("npx is required", skip=args.skip_if_unavailable)

    with tempfile.TemporaryDirectory(prefix="agentops-next-ts-pg-") as temp_dir:
        driver_ok, driver_status = ensure_psycopg(Path(temp_dir), install=not args.no_install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=args.skip_if_unavailable)

        container = f"agentops-next-ts-pg-{container_smoke.secrets.token_hex(6)}"
        pg_secret = container_smoke.secrets.token_urlsafe(18)
        raw_token = "agtok_ts_" + container_smoke.secrets.token_urlsafe(24)
        observer_token = "agtok_ts_observer_" + container_smoke.secrets.token_urlsafe(18)
        other_token = "agtok_ts_other_" + container_smoke.secrets.token_urlsafe(18)
        raw_session = "agtsess_ts_" + container_smoke.secrets.token_urlsafe(24)
        expired_token = "agtok_ts_expired_" + container_smoke.secrets.token_urlsafe(18)
        orphan_session = "agtsess_ts_orphan_" + container_smoke.secrets.token_urlsafe(18)
        expired_parent_session = "agtsess_ts_expired_parent_" + container_smoke.secrets.token_urlsafe(18)
        run_summary_secret = "sk-" + container_smoke.secrets.token_urlsafe(18)
        heartbeat_summary_secret = "sk-" + container_smoke.secrets.token_urlsafe(18)
        evidence_secret = "sk-" + container_smoke.secrets.token_urlsafe(18)
        heartbeat_error_message = "Direct Postgres heartbeat diagnostic."
        secrets = [
            pg_secret,
            raw_token,
            observer_token,
            other_token,
            raw_session,
            expired_token,
            orphan_session,
            expired_parent_session,
            run_summary_secret,
            heartbeat_summary_secret,
            evidence_secret,
        ]
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
                f"POSTGRES_PASSWORD={pg_secret}",
                args.image,
            ],
            timeout=60,
        )
        if started.returncode != 0:
            return unavailable(started.stderr or started.stdout or "Postgres container failed to start", skip=args.skip_if_unavailable)

        adapter: PostgresAdapter | None = None
        next_proc: subprocess.Popen[str] | None = None
        try:
            require(container_smoke.wait_for_postgres(container), "Postgres container did not become ready")
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_secret}@127.0.0.1:{port}/agentops"
            adapter = connect_postgres_when_ready(dsn, secret=pg_secret)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            seed(
                adapter,
                token=raw_token,
                observer_token=observer_token,
                other_token=other_token,
                session=raw_session,
                expired_token=expired_token,
                orphan_session=orphan_session,
                expired_parent_session=expired_parent_session,
            )
            adapter.close()
            adapter = None

            next_port = free_port()
            next_base = f"http://127.0.0.1:{next_port}"
            python_api_port = free_port()
            python_api_base = f"http://127.0.0.1:{python_api_port}/api"
            python_api_unreachable_before = endpoint_unreachable(python_api_base)
            next_env = os.environ.copy()
            next_env.pop("AGENTOPS_TS_CONTROL_PLANE_MODE", None)
            next_env.update({
                "AGENTOPS_DEPLOYMENT_MODE": "production",
                "AGENTOPS_POSTGRES_DSN": dsn,
                "AGENTOPS_API_BASE": python_api_base,
                "NEXT_TELEMETRY_DISABLED": "1",
            })
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            route = f"{next_base}/api/mis/agent-gateway/tasks"
            run_route = f"{next_base}/api/mis/agent-gateway/runs/start"
            heartbeat_route = f"{next_base}/api/mis/agent-gateway/runs/{RUN_ID}/heartbeat"
            tool_route = f"{next_base}/api/mis/agent-gateway/tool-calls"
            evaluation_route = f"{next_base}/api/mis/agent-gateway/evaluations/submit"
            artifact_route = f"{next_base}/api/mis/agent-gateway/artifacts"
            plan_route = f"{next_base}/api/mis/agent-gateway/agent-plans"
            manifest_route = f"{next_base}/api/mis/agent-gateway/plan-evidence-manifests"
            wait_for_next(route, next_proc, secret=pg_secret)

            payloads: list[dict] = []
            no_token_status, no_token_payload = http_json("POST", route, task_body(f"{TASK_ID}_no_token", owner_agent_id=AGENT_ID))
            missing_scope_status, missing_scope_payload = http_json("POST", route, task_body(f"{TASK_ID}_missing_scope", owner_agent_id=AGENT_ID), token=observer_token)
            cross_workspace_status, cross_workspace_payload = http_json(
                "POST",
                route,
                task_body(f"{TASK_ID}_cross_workspace", owner_agent_id=AGENT_ID, workspace_id=OTHER_WORKSPACE_ID),
                token=raw_token,
            )
            other_agent_status, other_agent_payload = http_json("POST", route, task_body(f"{TASK_ID}_other_agent", owner_agent_id=OTHER_AGENT_ID), token=raw_token)
            audit_seed_adapter = connect_postgres_when_ready(dsn, secret=pg_secret)
            future_audit_hash, future_audit_epoch = seed_future_audit_head(audit_seed_adapter)
            audit_seed_adapter.close()
            create_status, create_payload = http_json(
                "POST",
                route,
                task_body(TASK_ID, owner_agent_id=AGENT_ID, requester_id=REQUESTER_ID),
                token=raw_session,
            )
            other_requester_task_id = f"{TASK_ID}_other_requester"
            other_requester_create_status, other_requester_create_payload = http_json(
                "POST",
                route,
                task_body(other_requester_task_id, owner_agent_id=AGENT_ID, requester_id=OTHER_REQUESTER_ID),
                token=raw_session,
            )
            session_list_status, session_list_payload = http_json("GET", route, token=raw_session)
            requester_filter_status, requester_filter_payload = http_json(
                "GET",
                f"{route}?requester_id={REQUESTER_ID}",
                token=raw_session,
            )
            query_cross_workspace_status, query_cross_workspace_payload = http_json(
                "GET",
                f"{route}?workspace_id={OTHER_WORKSPACE_ID}",
                token=raw_token,
            )
            other_workspace_list_status, other_workspace_list_payload = http_json("GET", route, token=other_token)
            expired_token_status, expired_token_payload = http_json("GET", route, token=expired_token)
            orphan_session_status, orphan_session_payload = http_json("GET", route, token=orphan_session)
            expired_parent_session_status, expired_parent_session_payload = http_json(
                "GET",
                route,
                token=expired_parent_session,
            )
            immutable_rebind_status, immutable_rebind_payload = http_json(
                "POST",
                route,
                task_body(TASK_ID, owner_agent_id=OTHER_AGENT_ID, workspace_id=OTHER_WORKSPACE_ID),
                token=other_token,
            )
            other_task_status, other_task_payload = http_json(
                "POST",
                route,
                task_body(OTHER_TASK_ID, owner_agent_id=OTHER_AGENT_ID),
                token=other_token,
            )
            other_evidence_run_status, other_evidence_run_payload = http_json(
                "POST",
                run_route,
                {
                    "run_id": OTHER_EVIDENCE_RUN_ID,
                    "task_id": OTHER_TASK_ID,
                    "runtime_type": "mock",
                    "input_summary": "Cross-workspace evidence isolation fixture.",
                },
                token=other_token,
            )
            other_evidence_tool_status, other_evidence_tool_payload = http_json(
                "POST",
                tool_route,
                {
                    "tool_call_id": OTHER_TOOL_CALL_ID,
                    "run_id": OTHER_EVIDENCE_RUN_ID,
                    "task_id": OTHER_TASK_ID,
                    "tool_name": "agent_gateway.note",
                    "tool_category": "custom",
                    "risk_level": "low",
                    "status": "completed",
                    "args": {"contract": "cross_workspace_evidence_fixture_v1"},
                    "result_summary": "Completed evidence in the other workspace.",
                },
                token=other_token,
            )
            other_evidence_evaluation_status, other_evidence_evaluation_payload = http_json(
                "POST",
                evaluation_route,
                {
                    "evaluation_id": OTHER_EVALUATION_ID,
                    "run_id": OTHER_EVIDENCE_RUN_ID,
                    "task_id": OTHER_TASK_ID,
                    "evaluator_type": "rule",
                    "score": 1.0,
                    "pass_fail": "pass",
                    "rubric": {"gate": "cross_workspace_evidence_fixture"},
                    "notes": "Passing evidence that must remain isolated.",
                },
                token=other_token,
            )
            other_evidence_artifact_status, other_evidence_artifact_payload = http_json(
                "POST",
                artifact_route,
                {
                    "artifact_id": OTHER_ARTIFACT_ID,
                    "run_id": OTHER_EVIDENCE_RUN_ID,
                    "task_id": OTHER_TASK_ID,
                    "artifact_type": "delivery_report",
                    "title": "Cross-workspace evidence artifact",
                    "uri": f"run://{OTHER_EVIDENCE_RUN_ID}",
                    "summary": "Valid artifact from the other workspace.",
                    "content_hash": "cross_workspace_evidence_hash",
                },
                token=other_token,
            )
            unplanned_task_status, unplanned_task_payload = http_json(
                "POST",
                route,
                task_body(UNPLANNED_TASK_ID, owner_agent_id=AGENT_ID),
                token=raw_session,
            )
            high_risk_task_status, high_risk_task_payload = http_json(
                "POST",
                route,
                task_body(HIGH_RISK_TASK_ID, owner_agent_id=AGENT_ID),
                token=raw_session,
            )

            main_plan_body = agent_plan_body(RUN_PLAN_ID, TASK_ID)
            plan_no_token_status, plan_no_token_payload = http_json("POST", plan_route, main_plan_body)
            plan_missing_scope_status, plan_missing_scope_payload = http_json(
                "POST", plan_route, main_plan_body, token=observer_token
            )
            plan_hidden_status, plan_hidden_payload = http_json(
                "POST", plan_route, main_plan_body, token=other_token
            )
            plan_cross_workspace_status, plan_cross_workspace_payload = http_json(
                "POST",
                plan_route,
                {**main_plan_body, "workspace_id": OTHER_WORKSPACE_ID},
                token=raw_session,
            )
            plan_other_agent_status, plan_other_agent_payload = http_json(
                "POST", plan_route, {**main_plan_body, "agent_id": OTHER_AGENT_ID}, token=raw_session
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                plan_futures = [
                    executor.submit(http_json, "POST", plan_route, main_plan_body, token=raw_session)
                    for _ in range(2)
                ]
                plan_results = [future.result(timeout=15) for future in plan_futures]
            plan_rewrite_status, plan_rewrite_payload = http_json(
                "POST",
                plan_route,
                {**main_plan_body, "task_understanding": "Attempted submitted plan rewrite."},
                token=raw_session,
            )
            plan_human_status, plan_human_payload = http_json(
                "POST", plan_route, {**main_plan_body, "status": "approved"}, token=raw_session
            )
            plan_incomplete_status, plan_incomplete_payload = http_json(
                "POST",
                plan_route,
                {**agent_plan_body(f"{RUN_PLAN_ID}_incomplete", TASK_ID), "execution_steps": []},
                token=raw_session,
            )
            conflict_plan_status, conflict_plan_payload = http_json(
                "POST",
                plan_route,
                agent_plan_body(CONFLICT_PLAN_ID, other_requester_task_id),
                token=raw_session,
            )
            unplanned_run_status, unplanned_run_payload = http_json(
                "POST",
                run_route,
                {
                    "run_id": f"{RUN_ID}_unplanned",
                    "task_id": UNPLANNED_TASK_ID,
                    "runtime_type": "openclaw",
                },
                token=raw_session,
            )
            high_risk_plan_status, high_risk_plan_payload = http_json(
                "POST",
                plan_route,
                agent_plan_body(HIGH_RISK_PLAN_ID, HIGH_RISK_TASK_ID, risk_level="high"),
                token=raw_session,
            )
            high_risk_plan_run_status, high_risk_plan_run_payload = http_json(
                "POST",
                run_route,
                {
                    "run_id": f"{RUN_ID}_high_risk_plan",
                    "task_id": HIGH_RISK_TASK_ID,
                    "runtime_type": "openclaw",
                },
                token=raw_session,
            )
            run_body = {
                "run_id": RUN_ID,
                "task_id": TASK_ID,
                "runtime_type": "openclaw",
                "input_summary": f"TypeScript run start secret={run_summary_secret}",
            }
            run_no_token_status, run_no_token_payload = http_json("POST", run_route, run_body)
            run_missing_scope_status, run_missing_scope_payload = http_json("POST", run_route, run_body, token=observer_token)
            run_cross_workspace_status, run_cross_workspace_payload = http_json(
                "POST",
                run_route,
                {**run_body, "workspace_id": OTHER_WORKSPACE_ID},
                token=raw_token,
            )
            run_other_agent_status, run_other_agent_payload = http_json(
                "POST",
                run_route,
                {**run_body, "agent_id": OTHER_AGENT_ID},
                token=raw_token,
            )
            run_hidden_task_status, run_hidden_task_payload = http_json(
                "POST",
                run_route,
                {**run_body, "run_id": f"{RUN_ID}_hidden"},
                token=other_token,
            )
            run_start_status, run_start_payload = http_json("POST", run_route, run_body, token=raw_session)
            run_repeat_status, run_repeat_payload = http_json("POST", run_route, run_body, token=raw_session)
            concurrent_run_body = {
                "run_id": CONCURRENT_RUN_ID,
                "task_id": TASK_ID,
                "runtime_type": "openclaw",
                "input_summary": "Concurrent TypeScript run start proof.",
            }
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                concurrent_run_futures = [
                    executor.submit(http_json, "POST", run_route, concurrent_run_body, token=raw_session)
                    for _ in range(2)
                ]
                concurrent_run_results = [future.result(timeout=15) for future in concurrent_run_futures]
            run_rebind_status, run_rebind_payload = http_json(
                "POST",
                run_route,
                {"run_id": RUN_ID, "task_id": OTHER_TASK_ID, "runtime_type": "openclaw"},
                token=other_token,
            )
            heartbeat_body = {
                "task_id": TASK_ID,
                "status": "running",
                "duration_ms": 2345,
                "output_tokens": 17,
                "cost_usd": 0.125,
                "output_summary": f"TypeScript heartbeat api_key={heartbeat_summary_secret}",
                "error_message": heartbeat_error_message,
            }
            heartbeat_no_token_status, heartbeat_no_token_payload = http_json(
                "POST", heartbeat_route, heartbeat_body
            )
            heartbeat_missing_scope_status, heartbeat_missing_scope_payload = http_json(
                "POST", heartbeat_route, heartbeat_body, token=observer_token
            )
            heartbeat_workspace_status, heartbeat_workspace_payload = http_json(
                "POST",
                heartbeat_route,
                {**heartbeat_body, "workspace_id": OTHER_WORKSPACE_ID},
                token=raw_token,
            )
            heartbeat_hidden_status, heartbeat_hidden_payload = http_json(
                "POST", heartbeat_route, heartbeat_body, token=other_token
            )
            heartbeat_agent_status, heartbeat_agent_payload = http_json(
                "POST",
                heartbeat_route,
                {**heartbeat_body, "agent_id": OTHER_AGENT_ID},
                token=raw_token,
            )
            heartbeat_task_status, heartbeat_task_payload = http_json(
                "POST",
                heartbeat_route,
                {**heartbeat_body, "task_id": other_requester_task_id},
                token=raw_token,
            )
            heartbeat_status, heartbeat_payload = http_json(
                "POST", heartbeat_route, heartbeat_body, token=raw_session
            )
            heartbeat_repeat_status, heartbeat_repeat_payload = http_json(
                "POST", heartbeat_route, heartbeat_body, token=raw_session
            )
            terminal_heartbeat_body = {
                "task_id": TASK_ID,
                "status": "completed",
                "duration_ms": 3456,
                "output_tokens": 29,
                "cost_usd": 0.25,
                "output_summary": "TypeScript concurrent completion heartbeat proof.",
            }
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                terminal_heartbeat_futures = [
                    executor.submit(http_json, "POST", heartbeat_route, terminal_heartbeat_body, token=raw_session)
                    for _ in range(2)
                ]
                terminal_heartbeat_results = [future.result(timeout=15) for future in terminal_heartbeat_futures]
            heartbeat_revival_status, heartbeat_revival_payload = http_json(
                "POST",
                heartbeat_route,
                {"task_id": TASK_ID, "status": "running"},
                token=raw_session,
            )

            conflict_start_body = {
                "run_id": CONFLICT_RUN_ID,
                "task_id": other_requester_task_id,
                "runtime_type": "openclaw",
                "input_summary": "Conflicting terminal heartbeat proof.",
            }
            conflict_start_status, conflict_start_payload = http_json(
                "POST", run_route, conflict_start_body, token=raw_session
            )
            conflict_heartbeat_route = f"{next_base}/api/mis/agent-gateway/runs/{CONFLICT_RUN_ID}/heartbeat"
            conflicting_terminal_bodies = [
                {"task_id": other_requester_task_id, "status": "completed", "output_summary": "Completion won."},
                {"task_id": other_requester_task_id, "status": "failed", "output_summary": "Failure won."},
            ]
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                conflicting_terminal_futures = [
                    executor.submit(http_json, "POST", conflict_heartbeat_route, body, token=raw_session)
                    for body in conflicting_terminal_bodies
                ]
                conflicting_terminal_results = [future.result(timeout=15) for future in conflicting_terminal_futures]

            evidence_task_status, evidence_task_payload = http_json(
                "POST",
                route,
                task_body(EVIDENCE_TASK_ID, owner_agent_id=AGENT_ID, requester_id=REQUESTER_ID),
                token=raw_session,
            )
            evidence_plan_body = agent_plan_body(
                EVIDENCE_PLAN_ID,
                EVIDENCE_TASK_ID,
                task_understanding=f"Write bounded evidence without retaining secret={evidence_secret}.",
            )
            evidence_plan_body.update({
                "referenced_specs": [
                    {"path": "docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "authorization": f"Bearer {evidence_secret}"},
                ],
                "referenced_memories": [
                    {"memory_id": "project-memory:commercial-migration", "raw_prompt": evidence_secret},
                ],
                "referenced_bases": [
                    {"base": "typescript-postgres-control-plane", "api_key": evidence_secret},
                ],
                "proposed_files_to_change": [
                    {"path": "ui/next-app/src/server/controlPlane", "credential": evidence_secret},
                ],
                "execution_steps": [
                    {"step": "READ", "token": evidence_secret},
                    {"step": "EXECUTE", "secret": evidence_secret},
                    {"step": "VERIFY", "raw_response": evidence_secret},
                ],
                "verification_plan": f"Verify bounded evidence with api_key={evidence_secret} omitted.",
                "rollback_plan": f"Stop the run without retaining token={evidence_secret}.",
            })
            evidence_plan_status, evidence_plan_payload = http_json(
                "POST", plan_route, evidence_plan_body, token=raw_session
            )
            evidence_run_status, evidence_run_payload = http_json(
                "POST",
                run_route,
                {
                    "run_id": EVIDENCE_RUN_ID,
                    "task_id": EVIDENCE_TASK_ID,
                    "runtime_type": "openclaw",
                    "input_summary": "TypeScript evidence writeback proof.",
                },
                token=raw_session,
            )
            tool_body = {
                "tool_call_id": TOOL_CALL_ID,
                "run_id": EVIDENCE_RUN_ID,
                "task_id": EVIDENCE_TASK_ID,
                "tool_name": "agent_gateway.note",
                "tool_category": "custom",
                "risk_level": "low",
                "status": "completed",
                "args": {"contract": "typescript_postgres_evidence_write_v1", "secret": evidence_secret},
                "result_summary": f"Tool evidence api_key={evidence_secret}",
            }
            tool_no_token_status, tool_no_token_payload = http_json("POST", tool_route, tool_body)
            tool_missing_scope_status, tool_missing_scope_payload = http_json(
                "POST", tool_route, tool_body, token=observer_token
            )
            tool_hidden_status, tool_hidden_payload = http_json(
                "POST", tool_route, tool_body, token=other_token
            )
            tool_agent_status, tool_agent_payload = http_json(
                "POST", tool_route, {**tool_body, "agent_id": OTHER_AGENT_ID}, token=raw_token
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                tool_futures = [
                    executor.submit(http_json, "POST", tool_route, tool_body, token=raw_session)
                    for _ in range(2)
                ]
                tool_results = [future.result(timeout=15) for future in tool_futures]
            tool_rebind_status, tool_rebind_payload = http_json(
                "POST",
                tool_route,
                {**tool_body, "run_id": CONCURRENT_RUN_ID, "task_id": TASK_ID},
                token=raw_session,
            )
            tool_terminal_status, tool_terminal_payload = http_json(
                "POST", tool_route, {**tool_body, "status": "running"}, token=raw_session
            )

            evaluation_body = {
                "evaluation_id": EVALUATION_ID,
                "run_id": EVIDENCE_RUN_ID,
                "task_id": EVIDENCE_TASK_ID,
                "evaluator_type": "rule",
                "score": 1.0,
                "pass_fail": "pass",
                "rubric": {"gate": "typescript_postgres_evidence_write", "api_key": evidence_secret},
                "notes": f"Evaluation evidence token={evidence_secret}",
            }
            evaluation_no_token_status, evaluation_no_token_payload = http_json(
                "POST", evaluation_route, evaluation_body
            )
            evaluation_missing_scope_status, evaluation_missing_scope_payload = http_json(
                "POST", evaluation_route, evaluation_body, token=observer_token
            )
            evaluation_hidden_status, evaluation_hidden_payload = http_json(
                "POST", evaluation_route, evaluation_body, token=other_token
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                evaluation_futures = [
                    executor.submit(http_json, "POST", evaluation_route, evaluation_body, token=raw_session)
                    for _ in range(2)
                ]
                evaluation_results = [future.result(timeout=15) for future in evaluation_futures]
            evaluation_mutation_status, evaluation_mutation_payload = http_json(
                "POST", evaluation_route, {**evaluation_body, "score": 0.2, "pass_fail": "fail"}, token=raw_session
            )

            artifact_body = {
                "artifact_id": ARTIFACT_ID,
                "run_id": EVIDENCE_RUN_ID,
                "task_id": EVIDENCE_TASK_ID,
                "artifact_type": "delivery_report",
                "title": "TypeScript evidence artifact",
                "uri": f"run://{EVIDENCE_RUN_ID}",
                "summary": f"Artifact evidence secret={evidence_secret}",
                "content_hash": "typescript_postgres_evidence_hash",
            }
            artifact_no_token_status, artifact_no_token_payload = http_json("POST", artifact_route, artifact_body)
            artifact_missing_scope_status, artifact_missing_scope_payload = http_json(
                "POST", artifact_route, artifact_body, token=observer_token
            )
            artifact_hidden_status, artifact_hidden_payload = http_json(
                "POST", artifact_route, artifact_body, token=other_token
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                artifact_futures = [
                    executor.submit(http_json, "POST", artifact_route, artifact_body, token=raw_session)
                    for _ in range(2)
                ]
                artifact_results = [future.result(timeout=15) for future in artifact_futures]
            artifact_mutation_status, artifact_mutation_payload = http_json(
                "POST",
                artifact_route,
                {**artifact_body, "summary": "Attempted artifact rewrite."},
                token=raw_session,
            )

            manifest_body = {
                "manifest_id": MANIFEST_ID,
                "plan_id": EVIDENCE_PLAN_ID,
                "task_id": EVIDENCE_TASK_ID,
                "run_id": EVIDENCE_RUN_ID,
                "mismatch_policy": "block",
                "expected_steps": evidence_plan_body["execution_steps"],
                "tool_call_ids": [TOOL_CALL_ID],
                "evaluation_ids": [EVALUATION_ID],
                "artifact_ids": [ARTIFACT_ID],
                "verify_now": True,
            }
            manifest_no_token_status, manifest_no_token_payload = http_json(
                "POST", manifest_route, manifest_body
            )
            manifest_missing_scope_status, manifest_missing_scope_payload = http_json(
                "POST", manifest_route, manifest_body, token=observer_token
            )
            manifest_hidden_status, manifest_hidden_payload = http_json(
                "POST", manifest_route, manifest_body, token=other_token
            )
            manifest_cross_workspace_status, manifest_cross_workspace_payload = http_json(
                "POST",
                manifest_route,
                {**manifest_body, "workspace_id": OTHER_WORKSPACE_ID},
                token=raw_session,
            )
            manifest_other_agent_status, manifest_other_agent_payload = http_json(
                "POST",
                manifest_route,
                {**manifest_body, "agent_id": OTHER_AGENT_ID},
                token=raw_session,
            )
            manifest_task_mismatch_status, manifest_task_mismatch_payload = http_json(
                "POST", manifest_route, {**manifest_body, "task_id": TASK_ID}, token=raw_session
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                manifest_futures = [
                    executor.submit(http_json, "POST", manifest_route, manifest_body, token=raw_session)
                    for _ in range(2)
                ]
                manifest_results = [future.result(timeout=15) for future in manifest_futures]
            manifest_mutation_status, manifest_mutation_payload = http_json(
                "POST", manifest_route, {**manifest_body, "artifact_ids": []}, token=raw_session
            )
            blocked_manifest_status, blocked_manifest_payload = http_json(
                "POST",
                manifest_route,
                {
                    **manifest_body,
                    "manifest_id": BLOCKED_MANIFEST_ID,
                    "tool_call_ids": [OTHER_TOOL_CALL_ID],
                    "evaluation_ids": [OTHER_EVALUATION_ID],
                    "artifact_ids": [OTHER_ARTIFACT_ID],
                },
                token=raw_session,
            )

            high_risk_tool_body = {
                "tool_call_id": HIGH_RISK_TOOL_CALL_ID,
                "run_id": EVIDENCE_RUN_ID,
                "task_id": EVIDENCE_TASK_ID,
                "tool_name": "shell.exec",
                "tool_category": "shell",
                "risk_level": "low",
                "status": "completed",
                "args": {"summary": "Raw command omitted", "raw_command": evidence_secret},
                "result_summary": "Caller claimed completion; policy must hold for approval.",
            }
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                high_risk_tool_futures = [
                    executor.submit(http_json, "POST", tool_route, high_risk_tool_body, token=raw_session)
                    for _ in range(2)
                ]
                high_risk_tool_results = [future.result(timeout=15) for future in high_risk_tool_futures]

            concurrency_adapter = connect_postgres_when_ready(dsn, secret=pg_secret)
            concurrency_parent = concurrency_adapter.fetchone(
                "SELECT token_id FROM agent_gateway_tokens WHERE token_id=? FOR UPDATE",
                ["tok_ts_control_plane"],
            )
            concurrent_session_statuses: list[int] = []
            concurrent_session_payloads: list[dict] = []
            concurrent_session_waiters = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                session_futures = [executor.submit(http_json, "GET", route, token=raw_session) for _ in range(6)]
                time.sleep(0.25)
                concurrent_session_waiters = sum(not future.done() for future in session_futures)
                concurrency_adapter.commit()
                for future in session_futures:
                    status, payload = future.result(timeout=15)
                    concurrent_session_statuses.append(status)
                    concurrent_session_payloads.append(payload)
            concurrency_adapter.close()

            lock_adapter = connect_postgres_when_ready(dsn, secret=pg_secret)
            lock_adapter.execute("SELECT pg_advisory_xact_lock(?)", [1095779668])
            lock_task_id = f"{TASK_ID}_audit_lock"
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                typescript_future = executor.submit(
                    http_json,
                    "POST",
                    route,
                    task_body(lock_task_id, owner_agent_id=AGENT_ID),
                    token=raw_token,
                )
                time.sleep(0.25)
                typescript_audit_lock_waited = not typescript_future.done()
                lock_adapter.commit()
                lock_task_status, lock_task_payload = typescript_future.result(timeout=15)
            lock_adapter.close()

            wait_for_python_audit = future_audit_epoch + 0.1 - time.time()
            if wait_for_python_audit > 0:
                time.sleep(wait_for_python_audit)
            lock_adapter = connect_postgres_when_ready(dsn, secret=pg_secret)
            lock_adapter.execute("SELECT pg_advisory_xact_lock(?)", [1095779668])

            def append_python_audit() -> None:
                audit_adapter = connect_postgres_when_ready(dsn, secret=pg_secret)
                previous_backend = server.STORAGE_BACKEND
                server.STORAGE_BACKEND = "postgres"
                try:
                    server.audit(
                        audit_adapter,
                        "system",
                        "typescript-control-plane-smoke",
                        "control_plane.cross_language_audit_lock",
                        "runtime_connectors",
                        "rtc_agent_gateway_local",
                        None,
                        {"status": "ready"},
                        {"raw_payload_omitted": True},
                    )
                    audit_adapter.commit()
                finally:
                    server.STORAGE_BACKEND = previous_backend
                    audit_adapter.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                python_future = executor.submit(append_python_audit)
                time.sleep(0.25)
                python_audit_lock_waited = not python_future.done()
                lock_adapter.commit()
                python_future.result(timeout=15)
            lock_adapter.close()

            revoke_adapter = connect_postgres_when_ready(dsn, secret=pg_secret)
            revoke_adapter.execute("SET LOCAL lock_timeout = '500ms'")
            locked_parent = revoke_adapter.fetchone(
                "SELECT token_id FROM agent_gateway_tokens WHERE token_id=? FOR UPDATE",
                ["tok_ts_control_plane"],
            )
            session_request_waited_for_parent_lock = False
            session_parent_revoke_lock_order_consistent = False
            parent_revoke_status = 0
            parent_revoke_payload: dict = {}
            parent_revoke_error = ""
            session_after_parent_revoke_status = 0
            session_after_parent_revoke_payload: dict = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                session_future = executor.submit(http_json, "GET", route, token=raw_session)
                monitor_adapter = connect_postgres_when_ready(dsn, secret=pg_secret)
                try:
                    deadline = time.time() + 5
                    while time.time() < deadline:
                        waiter = monitor_adapter.fetchone(
                            """SELECT pid FROM pg_stat_activity
                            WHERE datname=current_database()
                              AND application_name='agentops-mis-typescript-control-plane'
                              AND state='active'
                              AND wait_event_type='Lock'
                              AND query LIKE '%agent_gateway_tokens%'
                              AND query LIKE '%FOR UPDATE%'
                            LIMIT 1"""
                        )
                        monitor_adapter.rollback()
                        if waiter:
                            session_request_waited_for_parent_lock = True
                            break
                        if session_future.done():
                            break
                        time.sleep(0.05)
                finally:
                    monitor_adapter.close()
                previous_backend = server.STORAGE_BACKEND
                server.STORAGE_BACKEND = "postgres"
                try:
                    locked_session = revoke_adapter.fetchone(
                        "SELECT session_id FROM agent_gateway_sessions WHERE session_id=? AND status='active' FOR UPDATE",
                        ["ses_ts_control_plane"],
                    )
                    session_parent_revoke_lock_order_consistent = bool(locked_parent and locked_session)
                    parent_revoke_payload, parent_revoke_status = server.agent_gateway_revoke_enrollment(
                        revoke_adapter,
                        {"token_id": "tok_ts_control_plane", "_admin_workspace_id": WORKSPACE_ID},
                    )
                    revoke_adapter.commit()
                except Exception as exc:
                    parent_revoke_error = str(exc)
                    revoke_adapter.rollback()
                finally:
                    server.STORAGE_BACKEND = previous_backend
                    revoke_adapter.close()
                session_after_parent_revoke_status, session_after_parent_revoke_payload = session_future.result(timeout=15)
            payloads.extend([
                no_token_payload,
                missing_scope_payload,
                cross_workspace_payload,
                other_agent_payload,
                create_payload,
                other_requester_create_payload,
                session_list_payload,
                requester_filter_payload,
                query_cross_workspace_payload,
                other_workspace_list_payload,
                expired_token_payload,
                orphan_session_payload,
                expired_parent_session_payload,
                immutable_rebind_payload,
                other_task_payload,
                other_evidence_run_payload,
                other_evidence_tool_payload,
                other_evidence_evaluation_payload,
                other_evidence_artifact_payload,
                unplanned_task_payload,
                high_risk_task_payload,
                plan_no_token_payload,
                plan_missing_scope_payload,
                plan_hidden_payload,
                plan_cross_workspace_payload,
                plan_other_agent_payload,
                *(payload for _, payload in plan_results),
                plan_rewrite_payload,
                plan_human_payload,
                plan_incomplete_payload,
                conflict_plan_payload,
                unplanned_run_payload,
                high_risk_plan_payload,
                high_risk_plan_run_payload,
                run_no_token_payload,
                run_missing_scope_payload,
                run_cross_workspace_payload,
                run_other_agent_payload,
                run_hidden_task_payload,
                run_start_payload,
                run_repeat_payload,
                *(payload for _, payload in concurrent_run_results),
                run_rebind_payload,
                heartbeat_no_token_payload,
                heartbeat_missing_scope_payload,
                heartbeat_workspace_payload,
                heartbeat_hidden_payload,
                heartbeat_agent_payload,
                heartbeat_task_payload,
                heartbeat_payload,
                heartbeat_repeat_payload,
                *(payload for _, payload in terminal_heartbeat_results),
                heartbeat_revival_payload,
                conflict_start_payload,
                *(payload for _, payload in conflicting_terminal_results),
                evidence_task_payload,
                evidence_plan_payload,
                evidence_run_payload,
                tool_no_token_payload,
                tool_missing_scope_payload,
                tool_hidden_payload,
                tool_agent_payload,
                *(payload for _, payload in tool_results),
                tool_rebind_payload,
                tool_terminal_payload,
                evaluation_no_token_payload,
                evaluation_missing_scope_payload,
                evaluation_hidden_payload,
                *(payload for _, payload in evaluation_results),
                evaluation_mutation_payload,
                artifact_no_token_payload,
                artifact_missing_scope_payload,
                artifact_hidden_payload,
                *(payload for _, payload in artifact_results),
                artifact_mutation_payload,
                manifest_no_token_payload,
                manifest_missing_scope_payload,
                manifest_hidden_payload,
                manifest_cross_workspace_payload,
                manifest_other_agent_payload,
                manifest_task_mismatch_payload,
                *(payload for _, payload in manifest_results),
                manifest_mutation_payload,
                blocked_manifest_payload,
                *(payload for _, payload in high_risk_tool_results),
                lock_task_payload,
                parent_revoke_payload,
                session_after_parent_revoke_payload,
                *concurrent_session_payloads,
            ])

            adapter = connect_postgres_when_ready(dsn, secret=pg_secret)
            task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [TASK_ID])
            runtime_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE task_id=? AND event_type=?", [TASK_ID, "task.create"])["c"]
            audit_rows = adapter.fetchall("SELECT * FROM audit_logs WHERE entity_type=? AND entity_id=? ORDER BY created_at,audit_id", ["tasks", TASK_ID])
            all_audit_rows = adapter.fetchall("SELECT * FROM audit_logs ORDER BY created_at,audit_id")
            session_last_used = adapter.fetchone("SELECT last_used_at FROM agent_gateway_sessions WHERE session_id=?", ["ses_ts_control_plane"])
            expired_token_row = adapter.fetchone("SELECT status FROM agent_gateway_tokens WHERE token_id=?", ["tok_ts_control_plane_expired"])
            orphan_session_row = adapter.fetchone("SELECT status,revoked_at FROM agent_gateway_sessions WHERE session_id=?", ["ses_ts_control_plane_orphan"])
            expired_parent_token_row = adapter.fetchone(
                "SELECT status FROM agent_gateway_tokens WHERE token_id=?",
                ["tok_ts_control_plane_expired_parent"],
            )
            expired_parent_session_row = adapter.fetchone(
                "SELECT status,revoked_at FROM agent_gateway_sessions WHERE session_id=?",
                ["ses_ts_control_plane_expired_parent"],
            )
            expired_parent_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE action=? AND entity_id=?",
                ["agent_gateway.session_parent_expired", "ses_ts_control_plane_expired_parent"],
            )["c"]
            revoked_parent_row = adapter.fetchone("SELECT status,revoked_at FROM agent_gateway_tokens WHERE token_id=?", ["tok_ts_control_plane"])
            revoked_session_row = adapter.fetchone("SELECT status,revoked_at FROM agent_gateway_sessions WHERE session_id=?", ["ses_ts_control_plane"])
            parent_revoke_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE action=? AND entity_id=?",
                ["agent_gateway.enrollment_revoke", "tok_ts_control_plane"],
            )["c"]
            session_revoke_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE action=? AND entity_id=?",
                ["agent_gateway.session_revoke_cascade", "ses_ts_control_plane"],
            )["c"]
            run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [RUN_ID])
            run_audit_rows = adapter.fetchall(
                "SELECT * FROM audit_logs WHERE entity_type=? AND entity_id=? ORDER BY created_at,audit_id",
                ["runs", RUN_ID],
            )
            run_create_audit_rows = [row for row in run_audit_rows if row.get("action") == "run.create"]
            run_heartbeat_audit_rows = [
                row for row in run_audit_rows if row.get("action") == "agent_gateway.run_heartbeat"
            ]
            run_event_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type=? AND run_id=?",
                ["run.start", RUN_ID],
            )["c"]
            concurrent_run_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runs WHERE run_id=?", [CONCURRENT_RUN_ID])["c"]
            concurrent_run_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE action=? AND entity_id=?",
                ["run.create", CONCURRENT_RUN_ID],
            )["c"]
            concurrent_run_event_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type=? AND run_id=?",
                ["run.start", CONCURRENT_RUN_ID],
            )["c"]
            run_heartbeat_event_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type=? AND run_id=?",
                ["run.heartbeat", RUN_ID],
            )["c"]
            run_heartbeat_error_event = adapter.fetchone(
                """SELECT error_message FROM runtime_events
                   WHERE event_type=? AND run_id=? AND error_message IS NOT NULL
                   ORDER BY created_at ASC LIMIT 1""",
                ["run.heartbeat", RUN_ID],
            )
            conflict_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [CONFLICT_RUN_ID])
            conflict_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [other_requester_task_id])
            conflict_run_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE action=? AND entity_type=? AND entity_id=?",
                ["agent_gateway.run_heartbeat", "runs", CONFLICT_RUN_ID],
            )["c"]
            conflict_run_event_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type=? AND run_id=?",
                ["run.heartbeat", CONFLICT_RUN_ID],
            )["c"]
            main_plan_row = adapter.fetchone("SELECT * FROM agent_plans WHERE plan_id=?", [RUN_PLAN_ID])
            other_evidence_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [OTHER_EVIDENCE_RUN_ID])
            other_evidence_tool_row = adapter.fetchone(
                "SELECT * FROM tool_calls WHERE tool_call_id=?",
                [OTHER_TOOL_CALL_ID],
            )
            other_evidence_evaluation_row = adapter.fetchone(
                "SELECT * FROM evaluations WHERE evaluation_id=?",
                [OTHER_EVALUATION_ID],
            )
            other_evidence_artifact_row = adapter.fetchone(
                "SELECT * FROM artifacts WHERE artifact_id=?",
                [OTHER_ARTIFACT_ID],
            )
            main_plan_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?",
                ["agent_plans", RUN_PLAN_ID],
            )["c"]
            main_plan_event_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type=? AND task_id=?",
                ["agent_plan.create", TASK_ID],
            )["c"]
            incomplete_plan_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM agent_plans WHERE plan_id=?",
                [f"{RUN_PLAN_ID}_incomplete"],
            )["c"]
            evidence_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [EVIDENCE_RUN_ID])
            evidence_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [EVIDENCE_TASK_ID])
            evidence_plan_row = adapter.fetchone("SELECT * FROM agent_plans WHERE plan_id=?", [EVIDENCE_PLAN_ID])
            manifest_row = adapter.fetchone(
                "SELECT * FROM plan_evidence_manifests WHERE manifest_id=?",
                [MANIFEST_ID],
            )
            blocked_manifest_row = adapter.fetchone(
                "SELECT * FROM plan_evidence_manifests WHERE manifest_id=?",
                [BLOCKED_MANIFEST_ID],
            )
            manifest_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?",
                ["plan_evidence_manifests", MANIFEST_ID],
            )["c"]
            manifest_event_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type=? AND run_id=? AND output_summary LIKE ?",
                ["plan_evidence_manifest.create", EVIDENCE_RUN_ID, f"%{MANIFEST_ID}%"],
            )["c"]
            blocked_manifest_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?",
                ["plan_evidence_manifests", BLOCKED_MANIFEST_ID],
            )["c"]
            main_plan_latest_audit = adapter.fetchone(
                "SELECT after_hash FROM audit_logs WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC,audit_id DESC LIMIT 1",
                ["agent_plans", RUN_PLAN_ID],
            )
            manifest_latest_audit = adapter.fetchone(
                "SELECT after_hash FROM audit_logs WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC,audit_id DESC LIMIT 1",
                ["plan_evidence_manifests", MANIFEST_ID],
            )
            tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [TOOL_CALL_ID])
            high_risk_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [HIGH_RISK_TOOL_CALL_ID])
            evaluation_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [EVALUATION_ID])
            artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [ARTIFACT_ID])
            tool_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?",
                ["tool_calls", TOOL_CALL_ID],
            )["c"]
            tool_event_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type=? AND run_id=? AND raw_payload_hash IS NOT NULL",
                ["tool_call.record", EVIDENCE_RUN_ID],
            )["c"]
            high_risk_tool_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?",
                ["tool_calls", HIGH_RISK_TOOL_CALL_ID],
            )["c"]
            evaluation_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?",
                ["evaluations", EVALUATION_ID],
            )["c"]
            evaluation_event_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type=? AND run_id=?",
                ["evaluation.submit", EVIDENCE_RUN_ID],
            )["c"]
            artifact_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?",
                ["artifacts", ARTIFACT_ID],
            )["c"]
            artifact_event_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type=? AND run_id=?",
                ["artifact.record", EVIDENCE_RUN_ID],
            )["c"]
            evidence_run_waiting_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE action=? AND entity_id=?",
                ["agent_gateway.tool_call_run_waiting_approval", EVIDENCE_RUN_ID],
            )["c"]
            evidence_task_waiting_audit_count = adapter.fetchone(
                "SELECT COUNT(*) AS c FROM audit_logs WHERE action=? AND entity_id=?",
                ["agent_gateway.tool_call_task_waiting_approval", EVIDENCE_TASK_ID],
            )["c"]
            evidence_run_latest_audit = adapter.fetchone(
                "SELECT after_hash FROM audit_logs WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC,audit_id DESC LIMIT 1",
                ["runs", EVIDENCE_RUN_ID],
            )
            evidence_task_latest_audit = adapter.fetchone(
                "SELECT after_hash FROM audit_logs WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC,audit_id DESC LIMIT 1",
                ["tasks", EVIDENCE_TASK_ID],
            )
            other_workspace_task = adapter.fetchone("SELECT * FROM tasks WHERE task_id=? AND workspace_id=?", [TASK_ID, OTHER_WORKSPACE_ID])
            other_requester_task = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [other_requester_task_id])
            requester_audit = adapter.fetchone(
                "SELECT actor_id FROM audit_logs WHERE entity_type=? AND entity_id=? AND action=?",
                ["tasks", TASK_ID, "task.api_create"],
            )
            task_create_audit_rows = [
                row for row in audit_rows if row.get("action") in {"task.create", "task.api_create"}
            ]
            task_transition_audits = [
                row for row in audit_rows
                if row.get("action") in {"agent_gateway.task_run_start", "agent_gateway.task_run_heartbeat"}
            ]
            task_transition_audit = task_transition_audits[-1] if task_transition_audits else None
            chain_valid = audit_chain_valid(task_create_audit_rows, initial_previous=future_audit_hash)
            cross_language_chain_valid = audit_chain_valid(all_audit_rows)
            audit_created_at_values = [str(row.get("created_at") or "") for row in all_audit_rows]
            audit_created_at_strictly_monotonic = all(
                left < right for left, right in zip(audit_created_at_values, audit_created_at_values[1:])
            )
            future_audit_head_first = bool(
                all_audit_rows and all_audit_rows[0].get("audit_id") == "aud_ts_control_plane_future_head"
            )
            task_after_hash_valid = bool(
                task_row
                and task_transition_audit
                and task_transition_audit.get("after_hash") == server.stable_hash(task_row)
            )
            run_after_hash_valid = bool(
                run_row and run_audit_rows and run_audit_rows[-1].get("after_hash") == server.stable_hash(run_row)
            )
            main_plan_after_hash_valid = bool(
                main_plan_row
                and main_plan_latest_audit
                and main_plan_latest_audit.get("after_hash") == server.stable_hash(main_plan_row)
            )
            manifest_after_hash_valid = bool(
                manifest_row
                and manifest_latest_audit
                and manifest_latest_audit.get("after_hash") == server.stable_hash(manifest_row)
            )
            try:
                manifest_verification = json.loads((manifest_row or {}).get("verification_json") or "{}")
            except json.JSONDecodeError:
                manifest_verification = {}
            try:
                blocked_manifest_verification = json.loads(
                    (blocked_manifest_row or {}).get("verification_json") or "{}"
                )
            except json.JSONDecodeError:
                blocked_manifest_verification = {}
            python_api_unreachable_after = endpoint_unreachable(python_api_base)

            failures: list[str] = []
            if not python_api_unreachable_before or not python_api_unreachable_after:
                failures.append(
                    "python_api_was_reachable:"
                    f"before={python_api_unreachable_before}:after={python_api_unreachable_after}"
                )
            if no_token_status != 401 or no_token_payload.get("error") != "unauthorized":
                failures.append(f"no_token_not_rejected:{no_token_status}:{no_token_payload}")
            if missing_scope_status != 403 or "tasks:create" not in json.dumps(missing_scope_payload):
                failures.append(f"missing_scope_not_rejected:{missing_scope_status}:{missing_scope_payload}")
            if cross_workspace_status != 403 or cross_workspace_payload.get("error") != "forbidden":
                failures.append(f"cross_workspace_not_rejected:{cross_workspace_status}:{cross_workspace_payload}")
            if other_agent_status != 403 or other_agent_payload.get("error") != "forbidden":
                failures.append(f"other_agent_not_rejected:{other_agent_status}:{other_agent_payload}")
            if create_status != 201 or create_payload.get("control_plane") != "typescript_postgres" or create_payload.get("task_id") != TASK_ID:
                failures.append(f"typescript_create_failed:{create_status}:{create_payload}")
            if other_requester_create_status != 201 or other_requester_create_payload.get("task_id") != other_requester_task_id:
                failures.append(
                    f"typescript_other_requester_create_failed:{other_requester_create_status}:{other_requester_create_payload}"
                )
            listed_ids = [item.get("task_id") for item in session_list_payload.get("tasks") or []]
            if session_list_status != 200 or session_list_payload.get("control_plane") != "typescript_postgres" or TASK_ID not in listed_ids:
                failures.append(f"typescript_session_list_failed:{session_list_status}:{session_list_payload}")
            requester_filtered_ids = [item.get("task_id") for item in requester_filter_payload.get("tasks") or []]
            if (
                requester_filter_status != 200
                or TASK_ID not in requester_filtered_ids
                or other_requester_task_id in requester_filtered_ids
            ):
                failures.append(
                    f"requester_filter_mismatch:{requester_filter_status}:{requester_filter_payload}"
                )
            if query_cross_workspace_status != 403 or query_cross_workspace_payload.get("error") != "forbidden":
                failures.append(f"query_cross_workspace_not_rejected:{query_cross_workspace_status}:{query_cross_workspace_payload}")
            if other_workspace_list_status != 200 or TASK_ID in [item.get("task_id") for item in other_workspace_list_payload.get("tasks") or []]:
                failures.append(f"other_workspace_list_leaked_task:{other_workspace_list_status}:{other_workspace_list_payload}")
            if expired_token_status != 401 or expired_token_payload.get("error") != "unauthorized" or (expired_token_row or {}).get("status") != "expired":
                failures.append(f"expired_token_lifecycle_not_committed:{expired_token_status}:{expired_token_payload}:{expired_token_row}")
            if (
                orphan_session_status != 401
                or orphan_session_payload.get("error") != "unauthorized"
                or (orphan_session_row or {}).get("status") != "revoked"
                or not (orphan_session_row or {}).get("revoked_at")
            ):
                failures.append(f"orphan_session_lifecycle_not_committed:{orphan_session_status}:{orphan_session_payload}:{orphan_session_row}")
            if (
                expired_parent_session_status != 401
                or expired_parent_session_payload.get("error") != "unauthorized"
                or (expired_parent_token_row or {}).get("status") != "expired"
                or (expired_parent_session_row or {}).get("status") != "expired"
                or (expired_parent_session_row or {}).get("revoked_at") is not None
                or int(expired_parent_audit_count or 0) != 1
            ):
                failures.append(
                    "expired_parent_lifecycle_not_committed:"
                    f"{expired_parent_session_status}:{expired_parent_session_payload}:"
                    f"token={expired_parent_token_row}:session={expired_parent_session_row}:audit={expired_parent_audit_count}"
                )
            if immutable_rebind_status != 409 or immutable_rebind_payload.get("error") != "task_immutable_binding_conflict":
                failures.append(f"task_rebind_not_rejected:{immutable_rebind_status}:{immutable_rebind_payload}")
            if other_task_status != 201 or other_task_payload.get("task_id") != OTHER_TASK_ID:
                failures.append(f"other_workspace_task_create_failed:{other_task_status}:{other_task_payload}")
            if (
                other_evidence_run_status != 201
                or other_evidence_tool_status != 201
                or other_evidence_evaluation_status != 201
                or other_evidence_artifact_status != 201
                or not other_evidence_run_row
                or other_evidence_run_row.get("workspace_id") != OTHER_WORKSPACE_ID
                or (other_evidence_tool_row or {}).get("run_id") != OTHER_EVIDENCE_RUN_ID
                or (other_evidence_evaluation_row or {}).get("run_id") != OTHER_EVIDENCE_RUN_ID
                or (other_evidence_artifact_row or {}).get("run_id") != OTHER_EVIDENCE_RUN_ID
            ):
                failures.append(
                    "cross_workspace_evidence_fixture_failed:"
                    f"http={other_evidence_run_status}/{other_evidence_tool_status}/"
                    f"{other_evidence_evaluation_status}/{other_evidence_artifact_status}:"
                    f"run={other_evidence_run_row}:tool={other_evidence_tool_row}:"
                    f"evaluation={other_evidence_evaluation_row}:artifact={other_evidence_artifact_row}"
                )
            if unplanned_task_status != 201 or high_risk_task_status != 201:
                failures.append(
                    f"plan_gate_fixture_task_create_failed:unplanned={unplanned_task_status}:{unplanned_task_payload}:"
                    f"high_risk={high_risk_task_status}:{high_risk_task_payload}"
                )
            if plan_no_token_status != 401 or plan_no_token_payload.get("error") != "unauthorized":
                failures.append(f"plan_no_token_not_rejected:{plan_no_token_status}:{plan_no_token_payload}")
            if plan_missing_scope_status != 403 or "agent_plans:write" not in json.dumps(plan_missing_scope_payload):
                failures.append(f"plan_missing_scope_not_rejected:{plan_missing_scope_status}:{plan_missing_scope_payload}")
            if plan_hidden_status != 404 or plan_hidden_payload.get("error") != "task_not_found":
                failures.append(f"plan_cross_workspace_task_not_hidden:{plan_hidden_status}:{plan_hidden_payload}")
            if plan_cross_workspace_status != 403 or plan_cross_workspace_payload.get("error") != "forbidden":
                failures.append(
                    f"plan_cross_workspace_binding_not_rejected:{plan_cross_workspace_status}:{plan_cross_workspace_payload}"
                )
            if plan_other_agent_status != 403 or plan_other_agent_payload.get("error") != "forbidden":
                failures.append(f"plan_other_agent_not_rejected:{plan_other_agent_status}:{plan_other_agent_payload}")
            plan_statuses = sorted(status for status, _ in plan_results)
            plan_outcomes = sorted(str(payload.get("outcome") or "") for _, payload in plan_results)
            method_check_ids = {
                "read_specs",
                "retrieve_memory",
                "compare_bases",
                "execution_steps",
                "verification_plan",
                "rollback_plan",
                "risk_gate",
                "file_scope",
            }
            plan_verifications = [payload.get("verification") or {} for _, payload in plan_results]
            plan_method_blocks_passed = bool(plan_verifications) and all(
                verification.get("pass") is True
                and not verification.get("failed_checks")
                and method_check_ids.issubset({
                    str(check.get("id"))
                    for check in verification.get("checks") or []
                    if check.get("ok") is True
                })
                for verification in plan_verifications
            )
            if plan_statuses != [200, 201] or plan_outcomes != ["created", "unchanged"]:
                failures.append(f"concurrent_plan_write_not_single_winner:{plan_results}")
            if not plan_method_blocks_passed:
                failures.append(f"submitted_plan_method_blocks_not_verified:{plan_verifications}")
            if plan_rewrite_status != 409 or plan_rewrite_payload.get("error") != "agent_plan_immutable_conflict":
                failures.append(f"submitted_plan_rewrite_not_rejected:{plan_rewrite_status}:{plan_rewrite_payload}")
            if plan_human_status != 403 or plan_human_payload.get("error") != "agent_plan_human_status_required":
                failures.append(f"agent_plan_human_status_not_protected:{plan_human_status}:{plan_human_payload}")
            if (
                plan_incomplete_status != 422
                or plan_incomplete_payload.get("error") != "agent_plan_verification_failed"
                or int(incomplete_plan_count or 0) != 0
            ):
                failures.append(
                    f"incomplete_submitted_plan_not_rolled_back:{plan_incomplete_status}:{plan_incomplete_payload}:"
                    f"rows={incomplete_plan_count}"
                )
            if conflict_plan_status != 201 or conflict_plan_payload.get("control_plane") != "typescript_postgres":
                failures.append(f"conflict_plan_create_failed:{conflict_plan_status}:{conflict_plan_payload}")
            if unplanned_run_status != 409 or unplanned_run_payload.get("error") != "verified_agent_plan_required":
                failures.append(f"non_mock_run_without_plan_not_blocked:{unplanned_run_status}:{unplanned_run_payload}")
            if (
                high_risk_plan_status != 201
                or not (high_risk_plan_payload.get("agent_plan") or {}).get("approval_required")
                or high_risk_plan_run_status != 409
                or high_risk_plan_run_payload.get("error") != "agent_plan_approval_required"
            ):
                failures.append(
                    f"approval_required_plan_run_not_blocked:plan={high_risk_plan_status}:{high_risk_plan_payload}:"
                    f"run={high_risk_plan_run_status}:{high_risk_plan_run_payload}"
                )
            if (
                not main_plan_row
                or main_plan_row.get("status") != "submitted"
                or int(main_plan_audit_count or 0) != 1
                or int(main_plan_event_count or 0) != 1
                or not main_plan_after_hash_valid
            ):
                failures.append(
                    f"agent_plan_persistence_or_evidence_mismatch:row={main_plan_row}:"
                    f"audit={main_plan_audit_count}:event={main_plan_event_count}:hash={main_plan_after_hash_valid}"
                )
            if run_no_token_status != 401 or run_no_token_payload.get("error") != "unauthorized":
                failures.append(f"run_no_token_not_rejected:{run_no_token_status}:{run_no_token_payload}")
            if run_missing_scope_status != 403 or "runs:write" not in json.dumps(run_missing_scope_payload):
                failures.append(f"run_missing_scope_not_rejected:{run_missing_scope_status}:{run_missing_scope_payload}")
            if run_cross_workspace_status != 403 or run_cross_workspace_payload.get("error") != "forbidden":
                failures.append(f"run_cross_workspace_not_rejected:{run_cross_workspace_status}:{run_cross_workspace_payload}")
            if run_other_agent_status != 403 or run_other_agent_payload.get("error") != "forbidden":
                failures.append(f"run_other_agent_not_rejected:{run_other_agent_status}:{run_other_agent_payload}")
            if run_hidden_task_status != 404 or run_hidden_task_payload.get("error") != "task_not_found":
                failures.append(f"run_cross_workspace_task_not_hidden:{run_hidden_task_status}:{run_hidden_task_payload}")
            started_run = run_start_payload.get("run") or {}
            if (
                run_start_status != 201
                or run_start_payload.get("control_plane") != "typescript_postgres"
                or started_run.get("run_id") != RUN_ID
                or started_run.get("workspace_id") != WORKSPACE_ID
                or started_run.get("agent_id") != AGENT_ID
                or run_start_payload.get("agent_plan_id") != RUN_PLAN_ID
                or run_summary_secret in str(started_run.get("input_summary") or "")
                or "[REDACTED]" not in str(started_run.get("input_summary") or "")
            ):
                failures.append(f"typescript_run_start_failed:{run_start_status}:{run_start_payload}")
            if run_repeat_status != 200 or run_repeat_payload.get("outcome") != "unchanged":
                failures.append(f"typescript_run_start_not_idempotent:{run_repeat_status}:{run_repeat_payload}")
            concurrent_statuses = sorted(status for status, _ in concurrent_run_results)
            concurrent_outcomes = sorted(str(payload.get("outcome") or "") for _, payload in concurrent_run_results)
            if concurrent_statuses != [200, 201] or concurrent_outcomes != ["created", "unchanged"]:
                failures.append(f"typescript_concurrent_run_start_not_single_winner:{concurrent_run_results}")
            if run_rebind_status != 409 or run_rebind_payload.get("error") != "run_immutable_binding_conflict":
                failures.append(f"run_rebind_not_rejected:{run_rebind_status}:{run_rebind_payload}")
            if heartbeat_no_token_status != 401 or heartbeat_no_token_payload.get("error") != "unauthorized":
                failures.append(f"heartbeat_no_token_not_rejected:{heartbeat_no_token_status}:{heartbeat_no_token_payload}")
            if heartbeat_missing_scope_status != 403 or "runs:write" not in json.dumps(heartbeat_missing_scope_payload):
                failures.append(
                    f"heartbeat_missing_scope_not_rejected:{heartbeat_missing_scope_status}:{heartbeat_missing_scope_payload}"
                )
            if heartbeat_workspace_status != 403 or heartbeat_workspace_payload.get("error") != "forbidden":
                failures.append(f"heartbeat_workspace_not_rejected:{heartbeat_workspace_status}:{heartbeat_workspace_payload}")
            if heartbeat_hidden_status != 404 or heartbeat_hidden_payload.get("error") != "run_not_found":
                failures.append(f"heartbeat_cross_workspace_run_not_hidden:{heartbeat_hidden_status}:{heartbeat_hidden_payload}")
            if heartbeat_agent_status != 403 or heartbeat_agent_payload.get("error") != "forbidden":
                failures.append(f"heartbeat_other_agent_not_rejected:{heartbeat_agent_status}:{heartbeat_agent_payload}")
            if heartbeat_task_status != 403 or heartbeat_task_payload.get("error") != "forbidden":
                failures.append(f"heartbeat_task_rebind_not_rejected:{heartbeat_task_status}:{heartbeat_task_payload}")
            heartbeat_run = heartbeat_payload.get("run") or {}
            if (
                heartbeat_status != 200
                or heartbeat_payload.get("control_plane") != "typescript_postgres"
                or heartbeat_payload.get("outcome") != "updated"
                or heartbeat_run.get("status") != "running"
                or int(heartbeat_run.get("duration_ms") or 0) != 2345
                or int(heartbeat_run.get("output_tokens") or 0) != 17
                or heartbeat_run.get("error_message") != heartbeat_error_message
                or heartbeat_summary_secret in json.dumps(heartbeat_payload, ensure_ascii=False)
                or "[REDACTED]" not in str(heartbeat_run.get("output_summary") or "")
            ):
                failures.append(f"typescript_run_heartbeat_failed:{heartbeat_status}:{heartbeat_payload}")
            if heartbeat_repeat_status != 200 or heartbeat_repeat_payload.get("outcome") != "unchanged":
                failures.append(
                    f"typescript_run_heartbeat_not_idempotent:{heartbeat_repeat_status}:{heartbeat_repeat_payload}"
                )
            terminal_heartbeat_statuses = sorted(status for status, _ in terminal_heartbeat_results)
            terminal_heartbeat_outcomes = sorted(str(payload.get("outcome") or "") for _, payload in terminal_heartbeat_results)
            if terminal_heartbeat_statuses != [200, 200] or terminal_heartbeat_outcomes != ["unchanged", "updated"]:
                failures.append(f"concurrent_terminal_heartbeat_not_single_winner:{terminal_heartbeat_results}")
            if heartbeat_revival_status != 409 or heartbeat_revival_payload.get("error") != "run_terminal_conflict":
                failures.append(f"terminal_run_revival_not_rejected:{heartbeat_revival_status}:{heartbeat_revival_payload}")
            conflicting_statuses = sorted(status for status, _ in conflicting_terminal_results)
            conflicting_successes = [payload for status, payload in conflicting_terminal_results if status == 200]
            conflicting_failures = [payload for status, payload in conflicting_terminal_results if status == 409]
            if (
                conflict_start_status != 201
                or conflicting_statuses != [200, 409]
                or len(conflicting_successes) != 1
                or conflicting_successes[0].get("outcome") != "updated"
                or len(conflicting_failures) != 1
                or conflicting_failures[0].get("error") != "run_terminal_conflict"
            ):
                failures.append(
                    f"conflicting_terminal_heartbeat_not_single_winner:start={conflict_start_status}:results={conflicting_terminal_results}"
                )
            if not run_row or run_row.get("workspace_id") != WORKSPACE_ID or run_row.get("task_id") != TASK_ID or run_row.get("agent_id") != AGENT_ID:
                failures.append(f"postgres_run_binding_mismatch:{run_row}")
            if any(secret in json.dumps(run_row or {}, ensure_ascii=False) for secret in [run_summary_secret, heartbeat_summary_secret]):
                failures.append("raw_run_summary_secret_persisted")
            if len(run_create_audit_rows) != 1 or int(run_event_count or 0) != 1 or not run_after_hash_valid:
                failures.append(
                    f"run_start_evidence_mismatch:audit={len(run_create_audit_rows)}:event={run_event_count}:after={run_after_hash_valid}"
                )
            if len(run_heartbeat_audit_rows) != 2 or int(run_heartbeat_event_count or 0) != 2:
                failures.append(
                    f"run_heartbeat_evidence_not_idempotent:audit={len(run_heartbeat_audit_rows)}:event={run_heartbeat_event_count}"
                )
            if (run_heartbeat_error_event or {}).get("error_message") != heartbeat_error_message:
                failures.append(f"run_heartbeat_error_message_not_persisted:{run_heartbeat_error_event}")
            conflict_winner_status = str(((conflicting_successes[0].get("run") or {}).get("status")) if conflicting_successes else "")
            if (
                not conflict_run_row
                or conflict_run_row.get("status") != conflict_winner_status
                or not conflict_task_row
                or conflict_task_row.get("status") != conflict_winner_status
                or int(conflict_run_audit_count or 0) != 1
                or int(conflict_run_event_count or 0) != 1
            ):
                failures.append(
                    "conflicting_terminal_state_or_evidence_mismatch:"
                    f"run={conflict_run_row}:task={conflict_task_row}:winner={conflict_winner_status}:"
                    f"audit={conflict_run_audit_count}:event={conflict_run_event_count}"
                )
            if (
                evidence_task_status != 201
                or evidence_plan_status != 201
                or evidence_run_status != 201
                or evidence_run_payload.get("agent_plan_id") != EVIDENCE_PLAN_ID
            ):
                failures.append(
                    f"evidence_fixture_create_failed:task={evidence_task_status}:{evidence_task_payload}:"
                    f"plan={evidence_plan_status}:{evidence_plan_payload}:run={evidence_run_status}:{evidence_run_payload}"
                )
            if evidence_secret in json.dumps(evidence_plan_row or {}, ensure_ascii=False):
                failures.append("raw_agent_plan_secret_persisted")
            if (
                not (evidence_plan_payload.get("verification") or {}).get("pass")
                or evidence_secret in json.dumps(evidence_plan_payload, ensure_ascii=False)
                or "[REDACTED]" not in json.dumps(evidence_plan_row or {}, ensure_ascii=False)
            ):
                failures.append(
                    f"agent_plan_sensitive_method_blocks_not_safely_redacted:{evidence_plan_payload}:{evidence_plan_row}"
                )
            if tool_no_token_status != 401 or tool_no_token_payload.get("error") != "unauthorized":
                failures.append(f"tool_no_token_not_rejected:{tool_no_token_status}:{tool_no_token_payload}")
            if tool_missing_scope_status != 403 or "toolcalls:write" not in json.dumps(tool_missing_scope_payload):
                failures.append(f"tool_missing_scope_not_rejected:{tool_missing_scope_status}:{tool_missing_scope_payload}")
            if tool_hidden_status != 404 or tool_hidden_payload.get("error") != "run_not_found":
                failures.append(f"tool_cross_workspace_run_not_hidden:{tool_hidden_status}:{tool_hidden_payload}")
            if tool_agent_status != 403 or tool_agent_payload.get("error") != "forbidden":
                failures.append(f"tool_other_agent_not_rejected:{tool_agent_status}:{tool_agent_payload}")
            tool_statuses = sorted(status for status, _ in tool_results)
            tool_outcomes = sorted(str(payload.get("outcome") or "") for _, payload in tool_results)
            if tool_statuses != [200, 201] or tool_outcomes != ["created", "unchanged"]:
                failures.append(f"concurrent_tool_write_not_single_winner:{tool_results}")
            if tool_rebind_status != 409 or tool_rebind_payload.get("error") != "tool_call_immutable_binding_conflict":
                failures.append(f"tool_rebind_not_rejected:{tool_rebind_status}:{tool_rebind_payload}")
            if tool_terminal_status != 409 or tool_terminal_payload.get("error") != "tool_call_terminal_conflict":
                failures.append(f"tool_terminal_reset_not_rejected:{tool_terminal_status}:{tool_terminal_payload}")

            if evaluation_no_token_status != 401 or evaluation_no_token_payload.get("error") != "unauthorized":
                failures.append(
                    f"evaluation_no_token_not_rejected:{evaluation_no_token_status}:{evaluation_no_token_payload}"
                )
            if evaluation_missing_scope_status != 403 or "evaluations:submit" not in json.dumps(evaluation_missing_scope_payload):
                failures.append(
                    f"evaluation_missing_scope_not_rejected:{evaluation_missing_scope_status}:{evaluation_missing_scope_payload}"
                )
            if evaluation_hidden_status != 404 or evaluation_hidden_payload.get("error") != "run_not_found":
                failures.append(
                    f"evaluation_cross_workspace_run_not_hidden:{evaluation_hidden_status}:{evaluation_hidden_payload}"
                )
            evaluation_statuses = sorted(status for status, _ in evaluation_results)
            evaluation_outcomes = sorted(str(payload.get("outcome") or "") for _, payload in evaluation_results)
            if evaluation_statuses != [200, 201] or evaluation_outcomes != ["created", "unchanged"]:
                failures.append(f"concurrent_evaluation_write_not_single_winner:{evaluation_results}")
            if evaluation_mutation_status != 409 or evaluation_mutation_payload.get("error") != "evaluation_immutable_conflict":
                failures.append(
                    f"evaluation_rewrite_not_rejected:{evaluation_mutation_status}:{evaluation_mutation_payload}"
                )

            if artifact_no_token_status != 401 or artifact_no_token_payload.get("error") != "unauthorized":
                failures.append(f"artifact_no_token_not_rejected:{artifact_no_token_status}:{artifact_no_token_payload}")
            if artifact_missing_scope_status != 403 or "artifacts:write" not in json.dumps(artifact_missing_scope_payload):
                failures.append(
                    f"artifact_missing_scope_not_rejected:{artifact_missing_scope_status}:{artifact_missing_scope_payload}"
                )
            if artifact_hidden_status != 404 or artifact_hidden_payload.get("error") != "run_not_found":
                failures.append(f"artifact_cross_workspace_run_not_hidden:{artifact_hidden_status}:{artifact_hidden_payload}")
            artifact_statuses = sorted(status for status, _ in artifact_results)
            artifact_outcomes = sorted(str(payload.get("outcome") or "") for _, payload in artifact_results)
            if artifact_statuses != [200, 201] or artifact_outcomes != ["created", "unchanged"]:
                failures.append(f"concurrent_artifact_write_not_single_winner:{artifact_results}")
            if artifact_mutation_status != 409 or artifact_mutation_payload.get("error") != "artifact_immutable_conflict":
                failures.append(f"artifact_rewrite_not_rejected:{artifact_mutation_status}:{artifact_mutation_payload}")

            if manifest_no_token_status != 401 or manifest_no_token_payload.get("error") != "unauthorized":
                failures.append(f"manifest_no_token_not_rejected:{manifest_no_token_status}:{manifest_no_token_payload}")
            if (
                manifest_missing_scope_status != 403
                or "plan_evidence:write" not in json.dumps(manifest_missing_scope_payload)
            ):
                failures.append(
                    f"manifest_missing_scope_not_rejected:{manifest_missing_scope_status}:{manifest_missing_scope_payload}"
                )
            if manifest_hidden_status != 404 or manifest_hidden_payload.get("error") != "agent_plan_not_found":
                failures.append(f"manifest_cross_workspace_plan_not_hidden:{manifest_hidden_status}:{manifest_hidden_payload}")
            if (
                manifest_cross_workspace_status != 403
                or manifest_cross_workspace_payload.get("error") != "forbidden"
            ):
                failures.append(
                    "manifest_cross_workspace_binding_not_rejected:"
                    f"{manifest_cross_workspace_status}:{manifest_cross_workspace_payload}"
                )
            if manifest_other_agent_status != 403 or manifest_other_agent_payload.get("error") != "forbidden":
                failures.append(
                    f"manifest_other_agent_not_rejected:{manifest_other_agent_status}:{manifest_other_agent_payload}"
                )
            if manifest_task_mismatch_status != 403 or manifest_task_mismatch_payload.get("error") != "forbidden":
                failures.append(
                    f"manifest_task_rebind_not_rejected:{manifest_task_mismatch_status}:{manifest_task_mismatch_payload}"
                )
            manifest_statuses = sorted(status for status, _ in manifest_results)
            manifest_outcomes = sorted(str(payload.get("outcome") or "") for _, payload in manifest_results)
            if manifest_statuses != [200, 201] or manifest_outcomes != ["created", "unchanged"]:
                failures.append(f"concurrent_manifest_write_not_single_winner:{manifest_results}")
            if (
                manifest_mutation_status != 409
                or manifest_mutation_payload.get("error") != "plan_evidence_immutable_conflict"
            ):
                failures.append(f"manifest_rewrite_not_rejected:{manifest_mutation_status}:{manifest_mutation_payload}")
            if (
                not manifest_row
                or manifest_row.get("status") != "verified"
                or not manifest_verification.get("pass")
                or int(manifest_audit_count or 0) != 1
                or int(manifest_event_count or 0) != 1
                or not manifest_after_hash_valid
            ):
                failures.append(
                    f"manifest_verification_or_single_write_mismatch:row={manifest_row}:"
                    f"verification={manifest_verification}:audit={manifest_audit_count}:"
                    f"event={manifest_event_count}:hash={manifest_after_hash_valid}"
                )
            blocked_manifest_failed_ids = {
                str(check.get("id")) for check in blocked_manifest_verification.get("failed_checks") or []
            }
            cross_workspace_evidence_rejected = (
                {"tool_ids_found", "evaluation_ids_found", "artifact_ids_found"}.issubset(blocked_manifest_failed_ids)
                and (blocked_manifest_verification.get("declared_counts") or {}).get("tool_call_ids") == 1
                and (blocked_manifest_verification.get("declared_counts") or {}).get("evaluation_ids") == 1
                and (blocked_manifest_verification.get("declared_counts") or {}).get("artifact_ids") == 1
            )
            if (
                blocked_manifest_status != 201
                or not blocked_manifest_row
                or blocked_manifest_row.get("status") != "blocked"
                or blocked_manifest_verification.get("pass") is not False
                or int(blocked_manifest_audit_count or 0) != 1
                or not cross_workspace_evidence_rejected
            ):
                failures.append(
                    f"manifest_cross_workspace_evidence_not_blocked:http={blocked_manifest_status}:{blocked_manifest_payload}:"
                    f"row={blocked_manifest_row}:verification={blocked_manifest_verification}:"
                    f"audit={blocked_manifest_audit_count}"
                )

            high_risk_tool_statuses = sorted(status for status, _ in high_risk_tool_results)
            high_risk_tool_outcomes = sorted(str(payload.get("outcome") or "") for _, payload in high_risk_tool_results)
            high_risk_tool_payloads = [payload.get("tool_call") or {} for _, payload in high_risk_tool_results]
            if (
                high_risk_tool_statuses != [200, 201]
                or high_risk_tool_outcomes != ["created", "unchanged"]
                or any(row.get("risk_level") != "high" or row.get("status") != "waiting_approval" for row in high_risk_tool_payloads)
            ):
                failures.append(f"high_risk_tool_not_held_for_approval:{high_risk_tool_results}")
            persisted_evidence = json.dumps(
                [tool_row, high_risk_tool_row, evaluation_row, artifact_row],
                ensure_ascii=False,
                sort_keys=True,
            )
            if evidence_secret in persisted_evidence:
                failures.append("raw_evidence_secret_persisted")
            if (
                not tool_row
                or tool_row.get("status") != "completed"
                or not high_risk_tool_row
                or high_risk_tool_row.get("risk_level") != "high"
                or high_risk_tool_row.get("status") != "waiting_approval"
                or not evaluation_row
                or evaluation_row.get("pass_fail") != "pass"
                or not artifact_row
                or artifact_row.get("run_id") != EVIDENCE_RUN_ID
            ):
                failures.append(
                    f"postgres_evidence_rows_mismatch:tool={tool_row}:high={high_risk_tool_row}:"
                    f"evaluation={evaluation_row}:artifact={artifact_row}"
                )
            if (
                int(tool_audit_count or 0) != 1
                or int(high_risk_tool_audit_count or 0) != 1
                or int(tool_event_count or 0) != 2
                or int(evaluation_audit_count or 0) != 1
                or int(evaluation_event_count or 0) != 1
                or int(artifact_audit_count or 0) != 1
                or int(artifact_event_count or 0) != 1
            ):
                failures.append(
                    "evidence_audit_runtime_not_single_winner:"
                    f"tool={tool_audit_count}/{tool_event_count}:high={high_risk_tool_audit_count}:"
                    f"evaluation={evaluation_audit_count}/{evaluation_event_count}:"
                    f"artifact={artifact_audit_count}/{artifact_event_count}"
                )
            evidence_run_after_hash_valid = bool(
                evidence_run_row
                and evidence_run_latest_audit
                and evidence_run_latest_audit.get("after_hash") == server.stable_hash(evidence_run_row)
            )
            evidence_task_after_hash_valid = bool(
                evidence_task_row
                and evidence_task_latest_audit
                and evidence_task_latest_audit.get("after_hash") == server.stable_hash(evidence_task_row)
            )
            if (
                not evidence_run_row
                or evidence_run_row.get("status") != "waiting_approval"
                or int(evidence_run_row.get("approval_required") or 0) != 1
                or not evidence_task_row
                or evidence_task_row.get("status") != "waiting_approval"
                or int(evidence_run_waiting_audit_count or 0) != 1
                or int(evidence_task_waiting_audit_count or 0) != 1
                or not evidence_run_after_hash_valid
                or not evidence_task_after_hash_valid
            ):
                failures.append(
                    "high_risk_waiting_approval_state_mismatch:"
                    f"run={evidence_run_row}:task={evidence_task_row}:"
                    f"audit={evidence_run_waiting_audit_count}/{evidence_task_waiting_audit_count}:"
                    f"hash={evidence_run_after_hash_valid}/{evidence_task_after_hash_valid}"
                )
            if int(concurrent_run_count or 0) != 1 or int(concurrent_run_audit_count or 0) != 1 or int(concurrent_run_event_count or 0) != 1:
                failures.append(
                    "concurrent_run_start_evidence_not_single:"
                    f"run={concurrent_run_count}:audit={concurrent_run_audit_count}:event={concurrent_run_event_count}"
                )
            if not concurrency_parent or concurrent_session_waiters != 6 or concurrent_session_statuses != [200] * 6:
                failures.append(
                    f"concurrent_session_deadlock_or_failure:parent={concurrency_parent}:"
                    f"waiters={concurrent_session_waiters}:statuses={concurrent_session_statuses}"
                )
            if lock_task_status != 201 or lock_task_payload.get("task_id") != lock_task_id:
                failures.append(f"audit_lock_typescript_write_failed:{lock_task_status}:{lock_task_payload}")
            if not typescript_audit_lock_waited:
                failures.append("typescript_audit_append_did_not_wait_for_shared_lock")
            if not python_audit_lock_waited:
                failures.append("python_audit_append_did_not_wait_for_shared_lock")
            if not session_request_waited_for_parent_lock:
                failures.append("session_request_did_not_wait_for_parent_token_lock")
            if not session_parent_revoke_lock_order_consistent:
                failures.append(f"session_parent_revoke_lock_order_inconsistent:{parent_revoke_error}")
            if parent_revoke_status != 200 or parent_revoke_payload.get("revoked") != 1 or parent_revoke_payload.get("sessions_revoked") != 1:
                failures.append(f"parent_revoke_failed:{parent_revoke_status}:{parent_revoke_payload}:{parent_revoke_error}")
            if session_after_parent_revoke_status != 401 or session_after_parent_revoke_payload.get("error") != "unauthorized":
                failures.append(
                    f"session_not_rejected_after_parent_revoke:{session_after_parent_revoke_status}:{session_after_parent_revoke_payload}"
                )
            if (revoked_parent_row or {}).get("status") != "revoked" or not (revoked_parent_row or {}).get("revoked_at"):
                failures.append(f"parent_revoke_state_not_committed:{revoked_parent_row}")
            if (revoked_session_row or {}).get("status") != "revoked" or not (revoked_session_row or {}).get("revoked_at"):
                failures.append(f"session_cascade_revoke_state_not_committed:{revoked_session_row}")
            if int(parent_revoke_audit_count or 0) != 1 or int(session_revoke_audit_count or 0) != 1:
                failures.append(
                    f"parent_session_revoke_audit_not_single:token={parent_revoke_audit_count}:session={session_revoke_audit_count}"
                )
            if not cross_language_chain_valid:
                failures.append("cross_language_audit_chain_invalid")
            if not audit_created_at_strictly_monotonic or not future_audit_head_first:
                failures.append(
                    f"audit_created_at_not_monotonic:future_head_first={future_audit_head_first}:values={audit_created_at_values}"
                )
            if (
                not task_row
                or task_row.get("workspace_id") != WORKSPACE_ID
                or task_row.get("owner_agent_id") != AGENT_ID
                or task_row.get("requester_id") != REQUESTER_ID
                or (requester_audit or {}).get("actor_id") != REQUESTER_ID
            ):
                failures.append(f"postgres_task_binding_mismatch:{task_row}")
            if not other_requester_task or other_requester_task.get("requester_id") != OTHER_REQUESTER_ID:
                failures.append(f"postgres_other_requester_binding_mismatch:{other_requester_task}")
            if int(runtime_count or 0) != 1:
                failures.append(f"runtime_event_count_mismatch:{runtime_count}")
            if len(audit_rows) != 4 or len(task_create_audit_rows) != 2 or not chain_valid or not task_after_hash_valid:
                failures.append(f"audit_chain_mismatch:count={len(audit_rows)}:chain={chain_valid}:after={task_after_hash_valid}")
            if not (session_last_used or {}).get("last_used_at"):
                failures.append("session_last_used_not_recorded")
            if other_workspace_task:
                failures.append("cross_workspace_rebind_mutated_task")
            transcript = json.dumps(payloads, ensure_ascii=False, sort_keys=True)
            if any(secret in transcript for secret in secrets):
                failures.append("raw_secret_leaked_in_http_payload")
            next_proc.terminate()
            try:
                stdout, stderr = next_proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                next_proc.kill()
                stdout, stderr = next_proc.communicate(timeout=5)
            next_proc = None
            if any(secret in f"{stdout}\n{stderr}" for secret in secrets):
                failures.append("raw_secret_leaked_in_next_logs")

            output = {
                "ok": not failures,
                "skipped": False,
                "contract": CONTRACT_ID,
                "control_plane": "typescript_postgres",
                "production_default_postgres": True,
                "python_api_started": not (python_api_unreachable_before and python_api_unreachable_after),
                "python_api_unreachable_before_and_after": (
                    python_api_unreachable_before and python_api_unreachable_after
                ),
                "workspace_id": WORKSPACE_ID,
                "task_id": TASK_ID,
                "no_token_status": no_token_status,
                "missing_scope_status": missing_scope_status,
                "cross_workspace_status": cross_workspace_status,
                "other_agent_status": other_agent_status,
                "create_status": create_status,
                "requester_id": (task_row or {}).get("requester_id"),
                "requester_filter_status": requester_filter_status,
                "requester_filter_ids": requester_filtered_ids,
                "session_list_status": session_list_status,
                "query_cross_workspace_status": query_cross_workspace_status,
                "other_workspace_list_status": other_workspace_list_status,
                "expired_token_status": expired_token_status,
                "expired_token_state_committed": (expired_token_row or {}).get("status") == "expired",
                "orphan_session_status": orphan_session_status,
                "orphan_session_state_committed": (orphan_session_row or {}).get("status") == "revoked",
                "expired_parent_session_status": expired_parent_session_status,
                "expired_parent_token_state_committed": (expired_parent_token_row or {}).get("status") == "expired",
                "expired_parent_session_state_committed": (expired_parent_session_row or {}).get("status") == "expired",
                "immutable_rebind_status": immutable_rebind_status,
                "typescript_agent_plan_owned": plan_statuses == [200, 201],
                "concurrent_agent_plan_single_winner": plan_outcomes == ["created", "unchanged"],
                "submitted_agent_plan_method_blocks_verified": plan_method_blocks_passed,
                "agent_plan_immutable": plan_rewrite_status == 409,
                "agent_plan_human_status_protected": plan_human_status == 403,
                "agent_plan_sensitive_values_redacted": (
                    evidence_secret not in json.dumps(evidence_plan_row or {}, ensure_ascii=False)
                    and "[REDACTED]" in json.dumps(evidence_plan_row or {}, ensure_ascii=False)
                ),
                "agent_plan_after_hash_valid": main_plan_after_hash_valid,
                "non_mock_run_requires_agent_plan": unplanned_run_status == 409,
                "approval_required_agent_plan_blocks_run": high_risk_plan_run_status == 409,
                "typescript_run_start_owned": run_start_status == 201 and run_start_payload.get("control_plane") == "typescript_postgres",
                "run_start_status": run_start_status,
                "run_repeat_idempotent": run_repeat_status == 200 and run_repeat_payload.get("outcome") == "unchanged",
                "concurrent_run_start_single_winner": sorted(status for status, _ in concurrent_run_results) == [200, 201],
                "run_immutable_binding_enforced": run_rebind_status == 409,
                "run_cross_workspace_task_hidden": run_hidden_task_status == 404,
                "run_summary_secret_redacted": bool(run_row) and run_summary_secret not in json.dumps(run_row, ensure_ascii=False),
                "run_audit_count": len(run_create_audit_rows),
                "run_runtime_event_count": int(run_event_count or 0),
                "run_after_hash_valid": run_after_hash_valid,
                "typescript_run_heartbeat_owned": heartbeat_status == 200 and heartbeat_payload.get("control_plane") == "typescript_postgres",
                "run_heartbeat_repeat_idempotent": heartbeat_repeat_status == 200 and heartbeat_repeat_payload.get("outcome") == "unchanged",
                "run_heartbeat_cross_workspace_hidden": heartbeat_hidden_status == 404,
                "run_heartbeat_terminal_revival_blocked": heartbeat_revival_status == 409,
                "concurrent_terminal_heartbeat_single_winner": terminal_heartbeat_outcomes == ["unchanged", "updated"],
                "conflicting_terminal_heartbeat_single_winner": conflicting_statuses == [200, 409],
                "run_heartbeat_audit_count": len(run_heartbeat_audit_rows),
                "run_heartbeat_runtime_event_count": int(run_heartbeat_event_count or 0),
                "run_heartbeat_error_message_persisted": (
                    (run_heartbeat_error_event or {}).get("error_message") == heartbeat_error_message
                ),
                "heartbeat_summary_secret_redacted": heartbeat_summary_secret not in json.dumps(payloads, ensure_ascii=False),
                "typescript_tool_call_owned": tool_statuses == [200, 201],
                "typescript_evaluation_owned": evaluation_statuses == [200, 201],
                "typescript_artifact_owned": artifact_statuses == [200, 201],
                "concurrent_tool_call_single_winner": tool_outcomes == ["created", "unchanged"],
                "concurrent_evaluation_single_winner": evaluation_outcomes == ["created", "unchanged"],
                "concurrent_artifact_single_winner": artifact_outcomes == ["created", "unchanged"],
                "tool_call_immutable_binding_enforced": tool_rebind_status == 409 and tool_terminal_status == 409,
                "evaluation_immutable_evidence_enforced": evaluation_mutation_status == 409,
                "artifact_immutable_evidence_enforced": artifact_mutation_status == 409,
                "typescript_plan_evidence_owned": manifest_statuses == [200, 201],
                "concurrent_manifest_single_winner": manifest_outcomes == ["created", "unchanged"],
                "manifest_verification_passed": bool(manifest_verification.get("pass")),
                "manifest_immutable": manifest_mutation_status == 409,
                "manifest_cross_workspace_evidence_blocked": cross_workspace_evidence_rejected,
                "manifest_after_hash_valid": manifest_after_hash_valid,
                "high_risk_tool_forced_waiting_approval": bool(
                    high_risk_tool_row
                    and high_risk_tool_row.get("risk_level") == "high"
                    and high_risk_tool_row.get("status") == "waiting_approval"
                    and evidence_run_row
                    and evidence_run_row.get("status") == "waiting_approval"
                    and evidence_task_row
                    and evidence_task_row.get("status") == "waiting_approval"
                ),
                "evidence_secret_redacted": evidence_secret not in json.dumps(payloads, ensure_ascii=False),
                "evidence_run_after_hash_valid": evidence_run_after_hash_valid,
                "evidence_task_after_hash_valid": evidence_task_after_hash_valid,
                "concurrent_session_statuses": concurrent_session_statuses,
                "concurrent_session_waiters": concurrent_session_waiters,
                "runtime_event_count": int(runtime_count or 0),
                "audit_count": len(audit_rows),
                "audit_chain_valid": chain_valid,
                "cross_language_audit_chain_valid": cross_language_chain_valid,
                "audit_created_at_strictly_monotonic": audit_created_at_strictly_monotonic,
                "future_audit_head_first": future_audit_head_first,
                "typescript_audit_lock_waited": typescript_audit_lock_waited,
                "python_audit_lock_waited": python_audit_lock_waited,
                "session_request_waited_for_parent_lock": session_request_waited_for_parent_lock,
                "session_parent_revoke_lock_order_consistent": session_parent_revoke_lock_order_consistent,
                "session_rejected_after_parent_revoke": session_after_parent_revoke_status == 401,
                "parent_revoke_audit_count": int(parent_revoke_audit_count or 0),
                "session_revoke_audit_count": int(session_revoke_audit_count or 0),
                "task_after_hash_valid": task_after_hash_valid,
                "token_omitted": True,
                "raw_prompt_omitted": True,
                "failures": failures,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not failures else 1
        except Exception as exc:
            message = str(exc)
            for secret in secrets:
                message = message.replace(secret, "[REDACTED]")
            return unavailable(message, skip=args.skip_if_unavailable)
        finally:
            if next_proc is not None:
                next_proc.terminate()
                try:
                    next_proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    next_proc.kill()
                    next_proc.communicate(timeout=5)
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
