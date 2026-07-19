#!/usr/bin/env python3
"""Exercise the Next.js-owned Agent Gateway memory proposal route on Postgres."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_postgres_memory_propose_v1"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter  # noqa: E402
from agentops_mis_cli.worker import build_worker_memory_candidate_payload  # noqa: E402
from nextjs_playwright_snapshot_smoke import free_port, start_process, stop_process  # noqa: E402
from storage_postgres_http_read_parity_smoke import connect_postgres_when_ready  # noqa: E402
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402


WORKSPACE_ID = "ws_ts_memory_smoke"
OTHER_WORKSPACE_ID = "ws_ts_memory_smoke_other"
AGENT_ID = "agt_ts_memory_smoke"
OTHER_AGENT_ID = "agt_ts_memory_smoke_other"
REQUESTER_ID = "usr_ts_memory_smoke"
OWNER_TASK_ID = "tsk_ts_memory_owner"
COLLABORATOR_TASK_ID = "tsk_ts_memory_collaborator"
UNASSIGNED_TASK_ID = "tsk_ts_memory_unassigned"
FOREIGN_TASK_ID = "tsk_ts_memory_foreign"
OTHER_WORKSPACE_TASK_ID = "tsk_ts_memory_other_workspace"
WORKER_RUN_ONE_ID = "run_ts_memory_worker_one"
WORKER_RUN_TWO_ID = "run_ts_memory_worker_two"
FOREIGN_MEMORY_ID = "mem_ts_memory_foreign_oracle"
UNUSED_MEMORY_ID = "mem_ts_memory_unused_oracle"


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_MEMORY_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists() or Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_MEMORY_PG_REEXEC"] = "1"
        os.execv(str(BUNDLED_PYTHON), [str(BUNDLED_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def json_default(value: object) -> str:
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)


def redact(value: object, secrets: list[str]) -> str:
    output = str(value)
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        output = output.replace(secret, "[REDACTED]")
    return output


def unavailable(message: str, *, skip: bool, secrets: list[str] | None = None) -> int:
    print(json.dumps({
        "ok": bool(skip),
        "skipped": bool(skip),
        "contract": CONTRACT_ID,
        "reason": redact(message, secrets or []),
        "deterministic_integration_smoke": True,
        "real_agent_runtime_claimed": False,
        "next_action": "Run with Node dependencies, psycopg, and an isolated Postgres database available.",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if skip else 1


def http_json(
    method: str,
    url: str,
    body: dict | None = None,
    *,
    token: str | None = None,
) -> tuple[int, dict]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def wait_for_next(route: str, proc: subprocess.Popen[str], *, secrets: list[str], timeout_sec: int = 60) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=2)
            detail = f"Next.js exited early rc={proc.returncode} stdout={stdout} stderr={stderr}"
            raise RuntimeError(redact(detail, secrets))
        try:
            status, payload = http_json("POST", route, {"scope": "task"})
            if status == 401 and payload.get("error") == "unauthorized":
                return
            last_error = f"unexpected readiness response {status}:{payload}"
        except Exception as exc:  # pragma: no cover - diagnostic only
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(redact(f"Next.js memory route did not become ready: {last_error}", secrets))


def dsn_with_search_path(dsn: str, schema: str) -> str:
    parsed = urllib.parse.urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("--postgres-dsn must be a postgres:// or postgresql:// URL")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    existing_options = [value for key, value in query if key == "options"]
    query = [(key, value) for key, value in query if key != "options"]
    options = " ".join([*existing_options, f"-c search_path={schema}"]).strip()
    query.append(("options", options))
    return urllib.parse.urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        urllib.parse.urlencode(query, quote_via=urllib.parse.quote),
        parsed.fragment,
    ))


def insert_task(
    adapter: PostgresAdapter,
    task_id: str,
    workspace_id: str,
    owner_agent_id: str | None,
    collaborator_agent_ids: list[str],
    now: str,
) -> None:
    adapter.execute(
        """INSERT INTO tasks(
            task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,
            status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            task_id,
            workspace_id,
            task_id,
            "Task-scoped TypeScript/Postgres memory authorization fixture.",
            REQUESTER_ID,
            owner_agent_id,
            json.dumps(collaborator_agent_ids),
            "planned",
            "medium",
            None,
            "Only an owner or collaborator may propose a task memory.",
            "low",
            0,
            now,
            now,
        ),
    )


def seed(
    adapter: PostgresAdapter,
    *,
    parent_tokens: list[str],
    sessions: list[str],
    limited_parent_token: str,
    limited_session: str,
) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    now_text = now.isoformat()
    expires = (now + dt.timedelta(days=1)).isoformat()
    adapter.execute(
        "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
        (REQUESTER_ID, REQUESTER_ID, "memory-smoke@example.local", "customer", now_text),
    )
    for agent_id in [AGENT_ID, OTHER_AGENT_ID]:
        adapter.execute(
            """INSERT INTO agents(
                agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,
                allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                agent_id,
                agent_id,
                "operator",
                "Deterministic memory route smoke fixture.",
                "mock",
                "mock",
                "mock-model",
                "idle",
                "standard",
                "[]",
                0,
                REQUESTER_ID,
                now_text,
                now_text,
            ),
        )
    insert_task(adapter, OWNER_TASK_ID, WORKSPACE_ID, AGENT_ID, [], now_text)
    insert_task(adapter, COLLABORATOR_TASK_ID, WORKSPACE_ID, OTHER_AGENT_ID, [AGENT_ID], now_text)
    insert_task(adapter, UNASSIGNED_TASK_ID, WORKSPACE_ID, None, [], now_text)
    insert_task(adapter, FOREIGN_TASK_ID, WORKSPACE_ID, OTHER_AGENT_ID, [], now_text)
    insert_task(adapter, OTHER_WORKSPACE_TASK_ID, OTHER_WORKSPACE_ID, OTHER_AGENT_ID, [], now_text)
    for run_id in [WORKER_RUN_ONE_ID, WORKER_RUN_TWO_ID]:
        adapter.execute(
            """INSERT INTO runs(
                run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,input_summary,
                model_provider,model_name,approval_required,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                WORKSPACE_ID,
                OWNER_TASK_ID,
                AGENT_ID,
                "openclaw",
                "completed",
                now_text,
                "Worker memory proposal parity fixture.",
                "openai",
                "fixture-model",
                0,
                now_text,
            ),
        )
    adapter.execute(
        """INSERT INTO runtime_connectors(
            runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,
            require_confirm_run,trust_status,trust_note,trust_updated_at,last_health_at,last_error,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "rtc_agent_gateway_local",
            "agent_gateway",
            "local",
            "TypeScript memory control plane",
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
        ("tok_ts_memory_parent_a", parent_tokens[0], ["memories:propose"]),
        ("tok_ts_memory_parent_b", parent_tokens[1], ["memories:propose"]),
        ("tok_ts_memory_limited", limited_parent_token, ["tasks:read"]),
    ]
    for token_id, raw_token, scopes in token_rows:
        adapter.execute(
            """INSERT INTO agent_gateway_tokens(
                token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,
                created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at
            ) VALUES(?,?,?,?,?,'active',?,60,?,?,NULL,NULL,NULL)""",
            (
                token_id,
                server.token_hash(raw_token),
                WORKSPACE_ID,
                AGENT_ID,
                json.dumps(scopes),
                "TypeScript memory smoke parent",
                now_text,
                expires,
            ),
        )
    session_rows = [
        ("ses_ts_memory_a", sessions[0], "tok_ts_memory_parent_a", ["memories:propose"]),
        ("ses_ts_memory_b", sessions[1], "tok_ts_memory_parent_b", ["memories:propose"]),
        ("ses_ts_memory_limited", limited_session, "tok_ts_memory_limited", ["tasks:read"]),
    ]
    for session_id, raw_session, parent_token_id, scopes in session_rows:
        adapter.execute(
            """INSERT INTO agent_gateway_sessions(
                session_id,session_hash,parent_token_id,workspace_id,agent_id,scopes_json,status,
                created_at,expires_at,revoked_at,last_used_at
            ) VALUES(?,?,?,?,?,?,'active',?,?,NULL,NULL)""",
            (
                session_id,
                server.token_hash(raw_session),
                parent_token_id,
                WORKSPACE_ID,
                AGENT_ID,
                json.dumps(scopes),
                now_text,
                expires,
            ),
        )
    adapter.execute(
        """INSERT INTO memories(
            memory_id,workspace_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,
            task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,
            supersedes_memory_id,access_tags,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            FOREIGN_MEMORY_ID,
            OTHER_WORKSPACE_ID,
            "project",
            "project_context",
            "Foreign workspace memory used only to test ID-oracle resistance.",
            "manual",
            "smoke-fixture",
            None,
            OTHER_WORKSPACE_TASK_ID,
            OTHER_AGENT_ID,
            1.0,
            "candidate",
            None,
            None,
            None,
            "[]",
            now_text,
            now_text,
        ),
    )
    adapter.commit()


def task_memory_body(task_id: str, canonical_text: str) -> dict:
    return {
        "task_id": task_id,
        "scope": "task",
        "memory_type": "agent_lesson",
        "canonical_text": canonical_text,
        "source_type": "run_log",
        "source_ref": "deterministic-memory-smoke",
        "confidence": 1.0,
        "access_tags": ["agent-gateway", "review"],
    }


def check(condition: bool, failure: str, failures: list[str]) -> bool:
    if not condition:
        failures.append(failure)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the dedicated Next.js/Postgres memory-propose smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE)
    parser.add_argument("--postgres-dsn", default="", help="Use an external Postgres URL in an isolated temporary schema.")
    parser.add_argument("--skip-if-unavailable", action="store_true")
    parser.add_argument("--no-install-driver", action="store_true")
    args = parser.parse_args()

    reexec_self_with_bundled_python_if_needed()
    if not args.postgres_dsn:
        early = container_smoke.docker_available(args.skip_if_unavailable)
        if early is not None:
            return early
        early = container_smoke.ensure_image(args.image, args.skip_if_unavailable)
        if early is not None:
            return early
    if not (NEXT_APP / "node_modules" / "next").exists():
        return unavailable("ui/next-app Node dependencies are required", skip=args.skip_if_unavailable)
    node_binary = shutil.which("node")
    if not node_binary:
        return unavailable("node is required", skip=args.skip_if_unavailable)

    with tempfile.TemporaryDirectory(prefix="agentops-next-memory-pg-") as temp_dir:
        driver_ok, driver_status = ensure_psycopg(Path(temp_dir), install=not args.no_install_driver)
        if not driver_ok:
            return unavailable(
                f"Optional psycopg driver unavailable: {driver_status}",
                skip=args.skip_if_unavailable,
            )

        container = f"agentops-next-memory-pg-{container_smoke.secrets.token_hex(6)}" if not args.postgres_dsn else ""
        pg_secret = container_smoke.secrets.token_urlsafe(18)
        parent_tokens = [
            "agtok_ts_memory_parent_a_" + container_smoke.secrets.token_urlsafe(18),
            "agtok_ts_memory_parent_b_" + container_smoke.secrets.token_urlsafe(18),
        ]
        sessions = [
            "agtsess_ts_memory_a_" + container_smoke.secrets.token_urlsafe(18),
            "agtsess_ts_memory_b_" + container_smoke.secrets.token_urlsafe(18),
        ]
        limited_parent_token = "agtok_ts_memory_limited_" + container_smoke.secrets.token_urlsafe(18)
        limited_session = "agtsess_ts_memory_limited_" + container_smoke.secrets.token_urlsafe(18)
        phone_spaced = "+86 138 0013 8000"
        phone_contiguous = "13800138000"
        pat = "github" + "_pat_" + container_smoke.secrets.token_hex(18)
        jwt = ".".join([
            "eyJ" + container_smoke.secrets.token_urlsafe(10),
            container_smoke.secrets.token_urlsafe(12),
            container_smoke.secrets.token_urlsafe(12),
        ])
        private_key_body = "memory-smoke-private-key-material"
        private_key = f"-----BEGIN PRIVATE KEY-----\n{private_key_body}\n-----END PRIVATE KEY-----"
        payload_token = "agtok_memory_payload_" + container_smoke.secrets.token_urlsafe(18)
        worker_title_secret = "sk-" + container_smoke.secrets.token_urlsafe(24)
        secrets = [
            pg_secret,
            *parent_tokens,
            *sessions,
            limited_parent_token,
            limited_session,
            phone_spaced,
            phone_contiguous,
            pat,
            jwt,
            private_key,
            private_key_body,
            payload_token,
            worker_title_secret,
        ]
        if args.postgres_dsn:
            secrets.append(args.postgres_dsn)

        base_dsn = args.postgres_dsn
        schema = f"agentops_memory_smoke_{container_smoke.secrets.token_hex(8)}"
        runtime_dsn = ""
        setup_adapter: PostgresAdapter | None = None
        adapter: PostgresAdapter | None = None
        next_proc: subprocess.Popen[str] | None = None
        failures: list[str] = []
        checks: dict[str, bool] = {}
        try:
            if not base_dsn:
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
                    return unavailable(
                        started.stderr or started.stdout or "Postgres container failed to start",
                        skip=args.skip_if_unavailable,
                        secrets=secrets,
                    )
                if not container_smoke.wait_for_postgres(container):
                    raise RuntimeError("Postgres container did not become ready")
                port = mapped_port(container)
                base_dsn = f"postgresql://agentops:{pg_secret}@127.0.0.1:{port}/agentops"
                secrets.append(base_dsn)

            setup_adapter = connect_postgres_when_ready(base_dsn, secret=pg_secret)
            setup_adapter.execute(f'CREATE SCHEMA "{schema}"')
            setup_adapter.commit()
            setup_adapter.close()
            setup_adapter = None

            runtime_dsn = dsn_with_search_path(base_dsn, schema)
            secrets.append(runtime_dsn)
            adapter = connect_postgres_when_ready(runtime_dsn, secret=pg_secret)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            adapter.execute("ALTER TABLE audit_logs ADD COLUMN workspace_id TEXT")
            adapter.execute(
                "ALTER TABLE audit_logs ADD CONSTRAINT audit_logs_workspace_metadata_match "
                "CHECK (CASE WHEN workspace_id IS NULL THEN TRUE ELSE metadata_json IS NOT NULL "
                "AND jsonb_typeof(metadata_json::jsonb) = 'object' "
                "AND metadata_json::jsonb ->> 'workspace_id' = workspace_id END)"
            )
            adapter.execute(
                "CREATE INDEX idx_audit_logs_workspace_created "
                "ON audit_logs(workspace_id,created_at DESC,audit_id DESC)"
            )
            seed(
                adapter,
                parent_tokens=parent_tokens,
                sessions=sessions,
                limited_parent_token=limited_parent_token,
                limited_session=limited_session,
            )
            adapter.close()
            adapter = None

            next_port = free_port()
            next_base = f"http://127.0.0.1:{next_port}"
            route = f"{next_base}/api/mis/agent-gateway/memories/propose"
            next_env = os.environ.copy()
            next_env.update({
                "AGENTOPS_DEPLOYMENT_MODE": "production",
                "AGENTOPS_TS_CONTROL_PLANE_MODE": "postgres",
                "AGENTOPS_POSTGRES_DSN": runtime_dsn,
                "AGENTOPS_API_BASE": f"http://127.0.0.1:{free_port()}/api",
                "NEXT_TELEMETRY_DISABLED": "1",
            })
            next_proc = start_process(
                [node_binary, str(NEXT_APP / "node_modules" / "next" / "dist" / "bin" / "next"), "dev", "-p", str(next_port)],
                cwd=NEXT_APP,
                env=next_env,
            )
            wait_for_next(route, next_proc, secrets=secrets)

            owner_status, owner_payload = http_json(
                "POST",
                route,
                task_memory_body(OWNER_TASK_ID, "Owner assignment memory proof."),
                token=sessions[0],
            )
            collaborator_status, collaborator_payload = http_json(
                "POST",
                route,
                task_memory_body(COLLABORATOR_TASK_ID, "Collaborator assignment memory proof."),
                token=sessions[1],
            )
            unassigned_status, unassigned_payload = http_json(
                "POST",
                route,
                task_memory_body(UNASSIGNED_TASK_ID, "Unassigned task memory must be denied."),
                token=sessions[0],
            )
            foreign_status, foreign_payload = http_json(
                "POST",
                route,
                task_memory_body(FOREIGN_TASK_ID, "Foreign-owned task memory must be denied."),
                token=sessions[0],
            )
            no_session_status, no_session_payload = http_json(
                "POST",
                route,
                task_memory_body(OWNER_TASK_ID, "Anonymous memory must be denied."),
            )
            missing_scope_status, missing_scope_payload = http_json(
                "POST",
                route,
                task_memory_body(OWNER_TASK_ID, "Missing-scope memory must be denied."),
                token=limited_session,
            )
            cross_workspace_status, cross_workspace_payload = http_json(
                "POST",
                route,
                {
                    **task_memory_body(OWNER_TASK_ID, "Cross-workspace memory must be denied."),
                    "workspace_id": OTHER_WORKSPACE_ID,
                },
                token=sessions[0],
            )
            missing_task_status, missing_task_payload = http_json(
                "POST",
                route,
                {
                    "scope": "task",
                    "memory_type": "agent_lesson",
                    "canonical_text": "Task scope without task_id or run_id must fail.",
                },
                token=sessions[0],
            )
            invalid_scope_status, invalid_scope_payload = http_json(
                "POST",
                route,
                {
                    **task_memory_body(OWNER_TASK_ID, "Invalid scope must fail."),
                    "scope": "workspace",
                },
                token=sessions[0],
            )
            oversized_status, oversized_payload = http_json(
                "POST",
                route,
                {"scope": "task", "canonical_text": "x" * (65 * 1024)},
            )

            worker_body_one = build_worker_memory_candidate_payload(
                workspace_id=WORKSPACE_ID,
                agent_id=AGENT_ID,
                task_id=OWNER_TASK_ID,
                run_id=WORKER_RUN_ONE_ID,
                task_title=f"Worker title {worker_title_secret}",
                adapter="openclaw",
            )
            worker_body_two = build_worker_memory_candidate_payload(
                workspace_id=WORKSPACE_ID,
                agent_id=AGENT_ID,
                task_id=OWNER_TASK_ID,
                run_id=WORKER_RUN_TWO_ID,
                task_title=f"Worker title {worker_title_secret}",
                adapter="openclaw",
            )
            worker_one_status, worker_one_payload = http_json(
                "POST", route, worker_body_one, token=sessions[0]
            )
            worker_two_status, worker_two_payload = http_json(
                "POST", route, worker_body_two, token=sessions[0]
            )

            with sqlite3.connect(":memory:") as rollback_conn:
                rollback_conn.row_factory = sqlite3.Row
                rollback_conn.executescript(server.SCHEMA_SQL)
                seed(
                    rollback_conn,
                    parent_tokens=parent_tokens,
                    sessions=sessions,
                    limited_parent_token=limited_parent_token,
                    limited_session=limited_session,
                )
                rollback_one_payload, rollback_one_status = server.agent_gateway_memory_propose(
                    rollback_conn, worker_body_one
                )
                rollback_one_repeat_payload, rollback_one_repeat_status = server.agent_gateway_memory_propose(
                    rollback_conn, worker_body_one
                )
                rollback_two_payload, rollback_two_status = server.agent_gateway_memory_propose(
                    rollback_conn, worker_body_two
                )

            oracle_body = task_memory_body(OWNER_TASK_ID, "Explicit ID oracle resistance proof.")
            foreign_id_status, foreign_id_payload = http_json(
                "POST",
                route,
                {**oracle_body, "memory_id": FOREIGN_MEMORY_ID},
                token=sessions[0],
            )
            unused_id_status, unused_id_payload = http_json(
                "POST",
                route,
                {**oracle_body, "memory_id": UNUSED_MEMORY_ID},
                token=sessions[0],
            )

            sensitive_body = task_memory_body(
                OWNER_TASK_ID,
                (
                    f"PAT {pat}; JWT {jwt}; spaced phone {phone_spaced}; contiguous phone {phone_contiguous}; "
                    f"private key {private_key}; payload token {payload_token}; active session {sessions[0]}."
                ),
            )
            sensitive_body["source_ref"] = f"phone={phone_contiguous}; token={payload_token}"
            sensitive_body["access_tags"] = [pat, jwt, phone_spaced, phone_contiguous, private_key, payload_token]
            human_owner_status, human_owner_payload = http_json(
                "POST",
                route,
                {**sensitive_body, "owner_user_id": REQUESTER_ID},
                token=sessions[0],
            )
            human_review_status, human_review_payload = http_json(
                "POST",
                route,
                {**sensitive_body, "review_status": "approved"},
                token=sessions[0],
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(http_json, "POST", route, sensitive_body, token=session)
                    for session in sessions
                ]
                concurrent_results = [future.result(timeout=20) for future in futures]

            memory_ids = {
                str((payload.get("memory") or {}).get("memory_id") or "")
                for _, payload in concurrent_results
                if (payload.get("memory") or {}).get("memory_id")
            }
            memory_id = next(iter(memory_ids), "")
            worker_one_memory = worker_one_payload.get("memory") or {}
            worker_two_memory = worker_two_payload.get("memory") or {}
            worker_one_id = str(worker_one_memory.get("memory_id") or "")
            worker_two_id = str(worker_two_memory.get("memory_id") or "")
            immutable_status, immutable_payload = http_json(
                "POST",
                route,
                {**sensitive_body, "memory_id": memory_id, "memory_type": "policy"},
                token=sessions[0],
            )
            adapter = connect_postgres_when_ready(runtime_dsn, secret=pg_secret)
            memory_row = adapter.fetchone(
                "SELECT * FROM memories WHERE memory_id=? AND workspace_id=?",
                (memory_id, WORKSPACE_ID),
            ) if memory_id else None
            worker_memory_rows = adapter.fetchall(
                "SELECT * FROM memories WHERE memory_id IN (?,?) ORDER BY memory_id",
                (worker_one_id, worker_two_id),
            ) if worker_one_id and worker_two_id else []
            runtime_rows = adapter.fetchall(
                "SELECT * FROM runtime_events WHERE event_type='memory.propose' AND task_id=? ORDER BY created_at",
                (OWNER_TASK_ID,),
            )
            audit_rows = adapter.fetchall(
                "SELECT * FROM audit_logs WHERE entity_type='memories' AND entity_id=? ORDER BY created_at",
                (memory_id,),
            ) if memory_id else []
            worker_audit_rows = adapter.fetchall(
                "SELECT * FROM audit_logs WHERE entity_type='memories' AND entity_id IN (?,?) ORDER BY created_at",
                (worker_one_id, worker_two_id),
            ) if worker_one_id and worker_two_id else []
            session_rows = adapter.fetchall(
                "SELECT session_id,parent_token_id,workspace_id,agent_id,status,last_used_at FROM agent_gateway_sessions ORDER BY session_id"
            )
            credential_rows = adapter.fetchall(
                """SELECT token_id,token_hash,workspace_id,agent_id,scopes_json,status,last_used_at
                FROM agent_gateway_tokens ORDER BY token_id"""
            )
            foreign_memory_row = adapter.fetchone(
                "SELECT memory_id,workspace_id FROM memories WHERE memory_id=?",
                (FOREIGN_MEMORY_ID,),
            )
            task_scope_without_binding_rows = adapter.fetchall(
                "SELECT memory_id FROM memories WHERE workspace_id=? AND scope='task' AND task_id IS NULL",
                (WORKSPACE_ID,),
            )

            response_evidence = [
                owner_payload,
                collaborator_payload,
                unassigned_payload,
                foreign_payload,
                no_session_payload,
                missing_scope_payload,
                cross_workspace_payload,
                missing_task_payload,
                invalid_scope_payload,
                oversized_payload,
                foreign_id_payload,
                unused_id_payload,
                worker_one_payload,
                worker_two_payload,
                rollback_one_payload,
                rollback_one_repeat_payload,
                rollback_two_payload,
                human_owner_payload,
                human_review_payload,
                immutable_payload,
                *[payload for _, payload in concurrent_results],
            ]
            db_evidence = [
                memory_row,
                worker_memory_rows,
                runtime_rows,
                audit_rows,
                worker_audit_rows,
                session_rows,
                credential_rows,
            ]
            sensitive_values = [
                *parent_tokens,
                *sessions,
                limited_parent_token,
                limited_session,
                phone_spaced,
                phone_contiguous,
                pat,
                jwt,
                private_key,
                private_key_body,
                payload_token,
            ]
            response_text = json_text(response_evidence)
            db_text = json_text(db_evidence)
            redacted_memory_text = json_text(memory_row or {})
            session_by_id = {str(row.get("session_id")): row for row in session_rows}
            statuses = sorted(status for status, _ in concurrent_results)
            outcomes = sorted(str(payload.get("outcome") or "") for _, payload in concurrent_results)
            parity_fields = [
                "scope", "memory_type", "canonical_text", "source_type", "source_ref", "project_id",
                "task_id", "agent_id", "confidence", "review_status", "owner_user_id",
                "supersedes_memory_id", "access_tags",
            ]
            rollback_one_memory = rollback_one_payload.get("memory") or {}
            rollback_two_memory = rollback_two_payload.get("memory") or {}
            worker_one_projection = {field: worker_one_memory.get(field) for field in parity_fields}
            worker_two_projection = {field: worker_two_memory.get(field) for field in parity_fields}
            rollback_one_projection = {field: rollback_one_memory.get(field) for field in parity_fields}
            rollback_two_projection = {field: rollback_two_memory.get(field) for field in parity_fields}

            checks["next_route_postgres_owned"] = check(
                owner_status == 201
                and owner_payload.get("control_plane") == "typescript_postgres"
                and owner_payload.get("provider") == "agentops-memory-candidate",
                "next_route_postgres_ownership_failed",
                failures,
            )
            checks["agent_session_required"] = check(
                no_session_status == 401 and no_session_payload.get("error") == "unauthorized",
                "agent_session_required_failed",
                failures,
            )
            checks["memory_scope_permission_required"] = check(
                missing_scope_status == 403
                and missing_scope_payload.get("error") == "forbidden"
                and "memories:propose" in json_text(missing_scope_payload),
                "memory_scope_permission_failed",
                failures,
            )
            checks["workspace_binding_enforced"] = check(
                cross_workspace_status == 403 and cross_workspace_payload.get("error") == "forbidden",
                "workspace_binding_failed",
                failures,
            )
            checks["owner_allowed"] = check(
                owner_status == 201
                and (owner_payload.get("memory") or {}).get("task_id") == OWNER_TASK_ID
                and (owner_payload.get("memory") or {}).get("scope") == "task",
                "owner_task_memory_rejected",
                failures,
            )
            checks["collaborator_allowed"] = check(
                collaborator_status == 201
                and (collaborator_payload.get("memory") or {}).get("task_id") == COLLABORATOR_TASK_ID
                and (collaborator_payload.get("memory") or {}).get("scope") == "task",
                "collaborator_task_memory_rejected",
                failures,
            )
            checks["unassigned_rejected"] = check(
                unassigned_status == 403 and unassigned_payload.get("error") == "forbidden",
                "unassigned_task_memory_not_rejected",
                failures,
            )
            checks["foreign_owner_rejected"] = check(
                foreign_status == 403 and foreign_payload.get("error") == "forbidden",
                "foreign_owned_task_memory_not_rejected",
                failures,
            )
            checks["task_scope_requires_binding"] = check(
                missing_task_status == 400
                and missing_task_payload.get("error") == "memory_task_id_required"
                and not task_scope_without_binding_rows,
                "task_scope_without_task_or_run_not_rejected",
                failures,
            )
            checks["invalid_scope_rejected"] = check(
                invalid_scope_status == 400 and invalid_scope_payload.get("error") == "memory_scope_invalid",
                "invalid_memory_scope_not_rejected",
                failures,
            )
            checks["request_body_bounded_before_auth"] = check(
                oversized_status == 413 and oversized_payload.get("error") == "request_too_large",
                "oversized_memory_body_not_rejected",
                failures,
            )
            checks["human_owner_and_review_boundary"] = check(
                human_owner_status == 403
                and human_owner_payload.get("error") == "memory_owner_human_assignment_required"
                and human_review_status == 403
                and human_review_payload.get("error") == "memory_review_human_required",
                "agent_crossed_human_memory_boundary",
                failures,
            )
            checks["explicit_id_workspace_oracle_blocked"] = check(
                bool(foreign_memory_row)
                and foreign_memory_row.get("workspace_id") == OTHER_WORKSPACE_ID
                and foreign_id_status == unused_id_status == 409
                and foreign_id_payload.get("error") == unused_id_payload.get("error") == "memory_id_unavailable"
                and foreign_id_payload.get("message") == unused_id_payload.get("message"),
                "explicit_memory_id_workspace_oracle_visible",
                failures,
            )
            checks["independent_session_concurrency_idempotent"] = check(
                statuses == [200, 201]
                and outcomes == ["created", "unchanged"]
                and len(memory_ids) == 1
                and all((session_by_id.get(session_id) or {}).get("last_used_at") for session_id in ["ses_ts_memory_a", "ses_ts_memory_b"])
                and (session_by_id.get("ses_ts_memory_a") or {}).get("parent_token_id") != (session_by_id.get("ses_ts_memory_b") or {}).get("parent_token_id"),
                "independent_session_concurrency_not_idempotent",
                failures,
            )
            checks["immutable_candidate_rewrite_rejected"] = check(
                immutable_status == 409 and immutable_payload.get("error") == "memory_immutable_conflict",
                "memory_candidate_rewrite_not_rejected",
                failures,
            )
            checks["worker_payload_redacted_before_transport"] = check(
                worker_title_secret not in json_text([worker_body_one, worker_body_two])
                and "[SECRET_REDACTED]" in json_text([worker_body_one, worker_body_two]),
                "worker_payload_retained_secret_suffix",
                failures,
            )
            checks["second_run_creates_distinct_candidate"] = check(
                worker_one_status == worker_two_status == 201
                and bool(worker_one_id)
                and bool(worker_two_id)
                and worker_one_id != worker_two_id
                and len(worker_memory_rows) == 2
                and len(worker_audit_rows) == 2
                and sum(1 for row in runtime_rows if row.get("output_summary") == worker_one_memory.get("canonical_text")) == 2,
                "second_worker_run_memory_conflicted_or_lost_evidence",
                failures,
            )
            checks["python_rollback_contract_parity"] = check(
                rollback_one_status == 201
                and rollback_one_repeat_status == 200
                and rollback_one_repeat_payload.get("outcome") == "unchanged"
                and rollback_two_status == 201
                and rollback_one_memory.get("memory_id") == worker_one_id
                and rollback_two_memory.get("memory_id") == worker_two_id
                and rollback_one_projection == worker_one_projection
                and rollback_two_projection == worker_two_projection,
                "python_rollback_memory_contract_drifted",
                failures,
            )
            checks["single_persistence_winner"] = check(
                bool(memory_row)
                and len(audit_rows) == 1
                and sum(1 for row in runtime_rows if row.get("output_summary") == (memory_row or {}).get("canonical_text")) == 1,
                "memory_concurrency_persistence_not_single_winner",
                failures,
            )
            checks["sensitive_values_omitted_from_response"] = check(
                not any(value in response_text for value in sensitive_values),
                "sensitive_value_present_in_response",
                failures,
            )
            checks["sensitive_values_omitted_from_database"] = check(
                not any(value in db_text for value in sensitive_values),
                "sensitive_value_present_in_database",
                failures,
            )
            checks["continuous_phone_redacted"] = check(
                phone_contiguous not in response_text
                and phone_contiguous not in db_text
                and "[PHONE_REDACTED]" in redacted_memory_text,
                "continuous_phone_not_redacted",
                failures,
            )
            checks["redaction_categories_proven"] = check(
                all(marker in redacted_memory_text for marker in [
                    "[SECRET_REDACTED]",
                    "[JWT_REDACTED]",
                    "[PHONE_REDACTED]",
                    "[PRIVATE_KEY_REDACTED]",
                ])
                and ("[AGENT_TOKEN_REF_REDACTED]" in redacted_memory_text or "token=[REDACTED]" in redacted_memory_text),
                "redaction_markers_incomplete",
                failures,
            )
            checks["token_omitted_contract"] = check(
                all(payload.get("token_omitted") is True for _, payload in concurrent_results),
                "token_omitted_contract_missing",
                failures,
            )

            output = {
                "ok": not failures,
                "contract": CONTRACT_ID,
                "control_plane": "typescript_postgres",
                "route": "/api/mis/agent-gateway/memories/propose",
                "postgres_fixture": "external_temporary_schema" if args.postgres_dsn else "docker_temporary_schema",
                "deterministic_integration_smoke": True,
                "real_agent_runtime_claimed": False,
                "checks": checks,
                "concurrent_statuses": statuses,
                "concurrent_outcomes": outcomes,
                "memory_rows_created": 1 if memory_row else 0,
                "worker_memory_rows_created": len(worker_memory_rows),
                "memory_audit_rows": len(audit_rows),
                "worker_memory_audit_rows": len(worker_audit_rows),
                "memory_runtime_rows": sum(
                    1 for row in runtime_rows if row.get("output_summary") == (memory_row or {}).get("canonical_text")
                ),
                "token_omitted": True,
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "python_api_started": False,
                "python_rollback_contract_checked_in_process": True,
                "failures": failures,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not failures else 1
        except Exception as exc:
            frames = traceback.extract_tb(exc.__traceback__)
            current_file = Path(__file__).resolve()
            location = next(
                (frame for frame in reversed(frames) if Path(frame.filename).resolve() == current_file),
                frames[-1] if frames else None,
            )
            message = (
                f"{type(exc).__name__} at {Path(location.filename).name}:{location.lineno}: {exc}"
                if location
                else f"{type(exc).__name__}: {exc}"
            )
            return unavailable(message, skip=args.skip_if_unavailable, secrets=secrets)
        finally:
            if next_proc is not None:
                stop_process(next_proc)
                next_proc.communicate()
            if adapter is not None:
                adapter.close()
            if setup_adapter is not None:
                setup_adapter.close()
            if base_dsn:
                cleanup_adapter: PostgresAdapter | None = None
                try:
                    cleanup_adapter = connect_postgres_when_ready(base_dsn, secret=pg_secret)
                    cleanup_adapter.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    cleanup_adapter.commit()
                except Exception:
                    pass
                finally:
                    if cleanup_adapter is not None:
                        cleanup_adapter.close()
            if container:
                container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
