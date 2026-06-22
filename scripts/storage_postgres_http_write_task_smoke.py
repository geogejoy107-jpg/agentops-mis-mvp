#!/usr/bin/env python3
"""Prove one explicit Postgres-backed HTTP write route."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402
from storage_postgres_http_read_parity_smoke import (  # noqa: E402
    connect_postgres_when_ready,
    free_port,
    request_json,
    start_server,
    wait_json,
)
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402


CONTRACT_ID = "postgres_http_write_task_parity_v1"
WORKSPACE_ID = "ws_pg_http_write"
AGENT_ID = "agt_pg_http_write"
TASK_ID = "tsk_pg_http_write_task"
BLOCKED_TASK_ID = "tsk_pg_http_write_blocked"
BLOCKED_AGENT_ID = "agt_pg_http_write_blocked"
GATEWAY_WORKSPACE_ID = "ws_pg_gateway_write"
GATEWAY_AGENT_ID = "agt_pg_gateway_write"
GATEWAY_OBSERVER_AGENT_ID = "agt_pg_gateway_observer"
GATEWAY_OTHER_AGENT_ID = "agt_pg_gateway_other"
GATEWAY_INTRUDER_AGENT_ID = "agt_pg_gateway_intruder"
GATEWAY_TASK_ID = "tsk_pg_gateway_write_task"
GATEWAY_RUN_ID = "run_pg_gateway_write_start"
GATEWAY_TOOL_CALL_ID = "tc_pg_gateway_write_evidence"
GATEWAY_EVALUATION_ID = "eval_pg_gateway_write_evidence"
GATEWAY_ARTIFACT_ID = "art_pg_gateway_write_evidence"
GATEWAY_READ_ONLY_TASK_ID = "tsk_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_CLAIM_TASK_ID = "tsk_pg_gateway_read_only_claim_blocked"
GATEWAY_READ_ONLY_RUN_ID = "run_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_TOOL_CALL_ID = "tc_pg_gateway_read_only_blocked"
GATEWAY_READ_ONLY_ARTIFACT_ID = "art_pg_gateway_read_only_blocked"
GATEWAY_MISSING_SCOPE_TASK_ID = "tsk_pg_gateway_missing_scope"
GATEWAY_CROSS_WORKSPACE_TASK_ID = "tsk_pg_gateway_cross_workspace"
GATEWAY_HEADER_WORKSPACE_TASK_ID = "tsk_pg_gateway_header_workspace"
GATEWAY_OTHER_AGENT_TASK_ID = "tsk_pg_gateway_other_agent"
GATEWAY_NO_TOKEN_TASK_ID = "tsk_pg_gateway_no_token"
GATEWAY_BLOCKED_APPROVAL_ID = "ap_pg_gateway_should_block"
SMOKE_API_KEY = "postgres_write_smoke_required_api_key"


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_HTTP_WRITE_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_HTTP_WRITE_PG_REEXEC"] = "1"
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


def redact(value: str, secret: str) -> str:
    return (value or "").replace(secret, "[REDACTED]")


def seed_reference_rows(adapter: PostgresAdapter) -> None:
    now = "2026-06-22T05:00:00+00:00"
    adapter.execute(
        "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
        ("usr_founder", "Founder", "founder@example.local", "founder", now),
    )
    adapter.execute(
        "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
        ("usr_customer_demo", "Customer Demo", "customer@example.local", "customer", now),
    )
    for agent_id, name in [
        (AGENT_ID, "Postgres HTTP Writer"),
        (GATEWAY_AGENT_ID, "Postgres Gateway Writer"),
        (GATEWAY_OBSERVER_AGENT_ID, "Postgres Gateway Observer"),
        (GATEWAY_OTHER_AGENT_ID, "Postgres Gateway Other Agent"),
        (GATEWAY_INTRUDER_AGENT_ID, "Postgres Gateway Intruder Agent"),
    ]:
        adapter.execute(
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""",
            {
                "agent_id": agent_id,
                "name": name,
                "role": "operator",
                "description": "Seed agent for routed Postgres HTTP task write smoke.",
                "runtime_type": "mock",
                "model_provider": "mock",
                "model_name": "mock-model",
                "status": "idle",
                "permission_level": "standard",
                "allowed_tools": "[]",
                "budget_limit_usd": 0,
                "owner_user_id": "usr_founder",
                "created_at": now,
                "updated_at": now,
            },
        )
    adapter.execute(
        """INSERT INTO runtime_connectors(runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,require_confirm_run,trust_status,trust_note,trust_updated_at,last_health_at,last_error,created_at,updated_at)
        VALUES(:runtime_connector_id,:provider,:connector_type,:profile_name,:base_url,:binary_path,:status,:allow_real_run,:require_confirm_run,:trust_status,:trust_note,:trust_updated_at,:last_health_at,:last_error,:created_at,:updated_at)""",
        {
            "runtime_connector_id": "rtc_agent_gateway_local",
            "provider": "agent-gateway",
            "connector_type": "local_cli_api_mcp",
            "profile_name": "postgres-http-write-smoke",
            "base_url": "http://127.0.0.1:8787/api/agent-gateway",
            "binary_path": None,
            "status": "available",
            "allow_real_run": 0,
            "require_confirm_run": 1,
            "trust_status": "trusted",
            "trust_note": "Seeded for Postgres HTTP write smoke.",
            "trust_updated_at": now,
            "last_health_at": now,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
    )
    adapter.commit()


def seed_gateway_token(adapter: PostgresAdapter, *, token_id: str, raw_token: str, agent_id: str, workspace_id: str, scopes: list[str]) -> None:
    now = "2026-06-22T05:01:00+00:00"
    adapter.execute(
        """INSERT INTO agent_gateway_tokens(token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at)
        VALUES(:token_id,:token_hash,:workspace_id,:agent_id,:scopes_json,:status,:label,:heartbeat_timeout_sec,:created_at,:expires_at,:revoked_at,:last_used_at,:last_heartbeat_at)""",
        {
            "token_id": token_id,
            "token_hash": server.token_hash(raw_token),
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "scopes_json": json.dumps(scopes, ensure_ascii=False),
            "status": "active",
            "label": "Postgres HTTP Gateway write smoke",
            "heartbeat_timeout_sec": 60,
            "created_at": now,
            "expires_at": "2026-06-23T05:01:00+00:00",
            "revoked_at": None,
            "last_used_at": None,
            "last_heartbeat_at": None,
        },
    )
    adapter.commit()


def server_env(dsn: str, pythonpath: str, *, write_enabled: bool) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "AGENTOPS_STORAGE_BACKEND": "postgres",
            "AGENTOPS_EDITION": "enterprise_byoc",
            "AGENTOPS_POSTGRES_DSN": dsn,
            "AGENTOPS_ENABLE_POSTGRES_STORAGE": "1",
            "AGENTOPS_POSTGRES_READ_ONLY_HTTP": "1",
            "AGENTOPS_API_KEY": SMOKE_API_KEY,
            "PYTHONPATH": pythonpath,
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    if write_enabled:
        env["AGENTOPS_POSTGRES_WRITE_HTTP"] = "1"
    else:
        env.pop("AGENTOPS_POSTGRES_WRITE_HTTP", None)
    env.pop("AGENTOPS_DB_PATH", None)
    return env


def stop_server(proc: subprocess.Popen[str] | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=5)


def task_body(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "workspace_id": WORKSPACE_ID,
        "title": "Postgres routed HTTP task write",
        "description": "Created only through the explicit Postgres HTTP write allowlist.",
        "requester_id": "usr_customer_demo",
        "owner_agent_id": AGENT_ID,
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Task, runtime event, and audit rows persist in Postgres.",
        "budget_limit_usd": 1.5,
    }


def gateway_task_body(task_id: str, *, workspace_id: str | None = None, owner_agent_id: str | None = None) -> dict:
    body = {
        "task_id": task_id,
        "title": "Postgres routed Agent Gateway task write",
        "description": "Created through scoped Agent Gateway token on Postgres.",
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Gateway task, runtime event, and audit rows persist in Postgres.",
        "budget_limit_usd": 2.0,
    }
    if workspace_id is not None:
        body["workspace_id"] = workspace_id
    if owner_agent_id is not None:
        body["owner_agent_id"] = owner_agent_id
    return body


def request_json_with_token(url: str, *, token: str, method: str = "POST", body: dict | None = None, extra_headers: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    headers.update(extra_headers or {})
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=5) as res:
            return int(res.status), json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Postgres-backed HTTP task write smoke.")
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

    with tempfile.TemporaryDirectory(prefix="agentops-http-pg-write-") as temp_dir:
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

        container = f"agentops-pg-http-write-{container_smoke.secrets.token_hex(6)}"
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
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=args.skip_if_unavailable)
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = connect_postgres_when_ready(dsn, secret=pg_auth)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            seed_reference_rows(adapter)
            gateway_token = "agtok_pg_" + container_smoke.secrets.token_urlsafe(24)
            gateway_observer_token = "agtok_pg_observer_" + container_smoke.secrets.token_urlsafe(18)
            gateway_intruder_token = "agtok_pg_intruder_" + container_smoke.secrets.token_urlsafe(18)
            seed_gateway_token(
                adapter,
                token_id="agtok_pg_gateway_write",
                raw_token=gateway_token,
                agent_id=GATEWAY_AGENT_ID,
                workspace_id=GATEWAY_WORKSPACE_ID,
                scopes=["tasks:create", "tasks:read", "tasks:claim", "runs:write", "toolcalls:write", "artifacts:write", "evaluations:submit"],
            )
            seed_gateway_token(
                adapter,
                token_id="agtok_pg_gateway_observer",
                raw_token=gateway_observer_token,
                agent_id=GATEWAY_OBSERVER_AGENT_ID,
                workspace_id=GATEWAY_WORKSPACE_ID,
                scopes=["tasks:read"],
            )
            seed_gateway_token(
                adapter,
                token_id="tok_pg_gateway_intruder",
                raw_token=gateway_intruder_token,
                agent_id=GATEWAY_INTRUDER_AGENT_ID,
                workspace_id=GATEWAY_WORKSPACE_ID,
                scopes=["tasks:read", "tasks:claim", "runs:write", "toolcalls:write", "artifacts:write", "evaluations:submit"],
            )
            adapter.close()
            adapter = None

            read_only_port = free_port()
            proc = start_server(server_env(dsn, pythonpath, write_enabled=False), read_only_port)
            read_only_base = f"http://127.0.0.1:{read_only_port}"
            read_only_status_code, read_only_backend = wait_json(f"{read_only_base}/api/storage/backend-status", proc, secret=pg_auth)
            blocked_status, blocked_payload = request_json(f"{read_only_base}/api/tasks", method="POST", body=task_body(BLOCKED_TASK_ID))
            gateway_blocked_status, gateway_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_READ_ONLY_TASK_ID, owner_agent_id=GATEWAY_AGENT_ID),
            )
            gateway_claim_blocked_status, gateway_claim_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/tasks/{GATEWAY_READ_ONLY_CLAIM_TASK_ID}/claim",
                token=gateway_token,
                body={"runtime_type": "mock"},
            )
            gateway_run_start_blocked_status, gateway_run_start_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/runs/start",
                token=gateway_token,
                body={
                    "run_id": GATEWAY_READ_ONLY_RUN_ID,
                    "task_id": GATEWAY_READ_ONLY_CLAIM_TASK_ID,
                    "runtime_type": "mock",
                },
            )
            gateway_tool_blocked_status, gateway_tool_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/tool-calls",
                token=gateway_token,
                body={
                    "tool_call_id": GATEWAY_READ_ONLY_TOOL_CALL_ID,
                    "run_id": GATEWAY_READ_ONLY_RUN_ID,
                    "tool_name": "postgres.read_only_blocked_tool",
                    "tool_category": "custom",
                    "status": "completed",
                },
            )
            gateway_eval_blocked_status, gateway_eval_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/evaluations/submit",
                token=gateway_token,
                body={
                    "evaluation_id": f"{GATEWAY_EVALUATION_ID}_read_only",
                    "run_id": GATEWAY_READ_ONLY_RUN_ID,
                    "score": 1.0,
                    "pass_fail": "pass",
                },
            )
            gateway_artifact_blocked_status, gateway_artifact_blocked_payload = request_json_with_token(
                f"{read_only_base}/api/agent-gateway/artifacts",
                token=gateway_token,
                body={
                    "artifact_id": GATEWAY_READ_ONLY_ARTIFACT_ID,
                    "run_id": GATEWAY_READ_ONLY_RUN_ID,
                    "title": "Read-only blocked artifact",
                    "summary": "This artifact must not persist in read-only Postgres mode.",
                },
            )
            stop_server(proc)
            proc = None

            write_port = free_port()
            proc = start_server(server_env(dsn, pythonpath, write_enabled=True), write_port)
            write_base = f"http://127.0.0.1:{write_port}"
            write_status_code, write_backend = wait_json(f"{write_base}/api/storage/backend-status", proc, secret=pg_auth)
            create_status, create_payload = request_json(f"{write_base}/api/tasks", method="POST", body=task_body(TASK_ID))
            readback_status, readback_payload = request_json(f"{write_base}/api/tasks/{TASK_ID}?workspace_id={WORKSPACE_ID}")
            gateway_missing_scope_status, gateway_missing_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_observer_token,
                body=gateway_task_body(GATEWAY_MISSING_SCOPE_TASK_ID, owner_agent_id=GATEWAY_OBSERVER_AGENT_ID),
            )
            gateway_cross_workspace_status, gateway_cross_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_CROSS_WORKSPACE_TASK_ID, workspace_id="other-workspace", owner_agent_id=GATEWAY_AGENT_ID),
            )
            gateway_header_workspace_status, gateway_header_workspace_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_HEADER_WORKSPACE_TASK_ID, owner_agent_id=GATEWAY_AGENT_ID),
                extra_headers={"X-AgentOps-Workspace-Id": "other-workspace"},
            )
            gateway_other_agent_status, gateway_other_agent_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_OTHER_AGENT_TASK_ID, owner_agent_id=GATEWAY_OTHER_AGENT_ID),
            )
            gateway_no_token_status, gateway_no_token_payload = request_json(
                f"{write_base}/api/agent-gateway/tasks",
                method="POST",
                body=gateway_task_body(GATEWAY_NO_TOKEN_TASK_ID, owner_agent_id=GATEWAY_AGENT_ID),
            )
            gateway_create_status, gateway_create_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks",
                token=gateway_token,
                body=gateway_task_body(GATEWAY_TASK_ID, owner_agent_id=GATEWAY_AGENT_ID),
            )
            gateway_missing_claim_scope_status, gateway_missing_claim_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks/{GATEWAY_TASK_ID}/claim",
                token=gateway_observer_token,
                body={"runtime_type": "mock"},
            )
            gateway_claim_status, gateway_claim_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks/{GATEWAY_TASK_ID}/claim",
                token=gateway_token,
                body={"runtime_type": "mock"},
            )
            gateway_missing_run_scope_status, gateway_missing_run_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/start",
                token=gateway_observer_token,
                body={
                    "run_id": f"{GATEWAY_RUN_ID}_missing_scope",
                    "task_id": GATEWAY_TASK_ID,
                    "runtime_type": "mock",
                },
            )
            gateway_run_start_status, gateway_run_start_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/start",
                token=gateway_token,
                body={
                    "run_id": GATEWAY_RUN_ID,
                    "task_id": GATEWAY_TASK_ID,
                    "runtime_type": "mock",
                    "input_summary": "Postgres Agent Gateway run start write proof.",
                },
            )
            gateway_intruder_claim_status, gateway_intruder_claim_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tasks/{GATEWAY_TASK_ID}/claim",
                token=gateway_intruder_token,
                body={"runtime_type": "mock"},
            )
            gateway_intruder_run_status, gateway_intruder_run_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/runs/start",
                token=gateway_intruder_token,
                body={
                    "run_id": f"{GATEWAY_RUN_ID}_intruder",
                    "task_id": GATEWAY_TASK_ID,
                    "runtime_type": "mock",
                },
            )
            gateway_missing_tool_scope_status, gateway_missing_tool_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tool-calls",
                token=gateway_observer_token,
                body={
                    "tool_call_id": f"{GATEWAY_TOOL_CALL_ID}_missing_scope",
                    "run_id": GATEWAY_RUN_ID,
                    "tool_name": "postgres.gateway_missing_tool_scope",
                    "tool_category": "custom",
                    "status": "completed",
                },
            )
            gateway_tool_write_status, gateway_tool_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tool-calls",
                token=gateway_token,
                body={
                    "tool_call_id": GATEWAY_TOOL_CALL_ID,
                    "run_id": GATEWAY_RUN_ID,
                    "tool_name": "postgres.gateway_evidence_tool",
                    "tool_category": "custom",
                    "risk_level": "low",
                    "status": "completed",
                    "args": {"raw_omitted": True, "contract": "postgres_http_gateway_evidence_write_v1"},
                    "result_summary": "Postgres Gateway tool-call evidence write proof.",
                },
            )
            gateway_missing_eval_scope_status, gateway_missing_eval_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/evaluations/submit",
                token=gateway_observer_token,
                body={
                    "evaluation_id": f"{GATEWAY_EVALUATION_ID}_missing_scope",
                    "run_id": GATEWAY_RUN_ID,
                    "score": 1.0,
                    "pass_fail": "pass",
                },
            )
            gateway_eval_write_status, gateway_eval_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/evaluations/submit",
                token=gateway_token,
                body={
                    "evaluation_id": GATEWAY_EVALUATION_ID,
                    "run_id": GATEWAY_RUN_ID,
                    "task_id": GATEWAY_TASK_ID,
                    "evaluator_type": "rule",
                    "score": 1.0,
                    "pass_fail": "pass",
                    "rubric": {"gate": "postgres_gateway_evidence_write"},
                    "notes": "Postgres Gateway evaluation evidence write proof.",
                },
            )
            gateway_missing_artifact_scope_status, gateway_missing_artifact_scope_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/artifacts",
                token=gateway_observer_token,
                body={
                    "artifact_id": f"{GATEWAY_ARTIFACT_ID}_missing_scope",
                    "run_id": GATEWAY_RUN_ID,
                    "title": "Missing artifact scope",
                    "summary": "This artifact must not persist without artifacts:write.",
                },
            )
            gateway_artifact_write_status, gateway_artifact_write_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/artifacts",
                token=gateway_token,
                body={
                    "artifact_id": GATEWAY_ARTIFACT_ID,
                    "run_id": GATEWAY_RUN_ID,
                    "artifact_type": "postgres_gateway_evidence",
                    "title": "Postgres Gateway evidence artifact",
                    "uri": f"run://{GATEWAY_RUN_ID}",
                    "summary": "Postgres Gateway artifact evidence write proof.",
                    "content_hash": "pg_gateway_evidence_hash",
                },
            )
            gateway_intruder_tool_status, gateway_intruder_tool_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/tool-calls",
                token=gateway_intruder_token,
                body={
                    "tool_call_id": f"{GATEWAY_TOOL_CALL_ID}_intruder",
                    "run_id": GATEWAY_RUN_ID,
                    "tool_name": "postgres.gateway_intruder_tool",
                    "tool_category": "custom",
                    "status": "completed",
                },
            )
            gateway_intruder_eval_status, gateway_intruder_eval_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/evaluations/submit",
                token=gateway_intruder_token,
                body={
                    "evaluation_id": f"{GATEWAY_EVALUATION_ID}_intruder",
                    "run_id": GATEWAY_RUN_ID,
                    "score": 1.0,
                    "pass_fail": "pass",
                },
            )
            gateway_intruder_artifact_status, gateway_intruder_artifact_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/artifacts",
                token=gateway_intruder_token,
                body={
                    "artifact_id": f"{GATEWAY_ARTIFACT_ID}_intruder",
                    "run_id": GATEWAY_RUN_ID,
                    "title": "Intruder artifact",
                    "summary": "This artifact must not persist for another agent's run.",
                },
            )
            gateway_readback_status, gateway_readback_payload = request_json(f"{write_base}/api/tasks/{GATEWAY_TASK_ID}?workspace_id={GATEWAY_WORKSPACE_ID}")
            gateway_run_readback_status, gateway_run_readback_payload = request_json(f"{write_base}/api/runs/{GATEWAY_RUN_ID}?workspace_id={GATEWAY_WORKSPACE_ID}")
            agent_block_status, agent_block_payload = request_json(
                f"{write_base}/api/agents",
                method="POST",
                body={"agent_id": BLOCKED_AGENT_ID, "name": "Should stay blocked"},
            )
            gateway_approval_block_status, gateway_approval_block_payload = request_json_with_token(
                f"{write_base}/api/agent-gateway/approvals/request",
                token=gateway_token,
                body={
                    "approval_id": GATEWAY_BLOCKED_APPROVAL_ID,
                    "run_id": GATEWAY_RUN_ID,
                    "reason": "Approval writes remain outside this Postgres allowlist slice.",
                },
            )
            stop_server(proc)
            proc = None

            adapter = connect_postgres_when_ready(dsn, secret=pg_auth)
            task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [TASK_ID])
            blocked_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [BLOCKED_TASK_ID])
            gateway_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_TASK_ID])
            gateway_read_only_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_READ_ONLY_TASK_ID])
            gateway_read_only_claim_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_READ_ONLY_CLAIM_TASK_ID])
            gateway_read_only_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [GATEWAY_READ_ONLY_RUN_ID])
            gateway_read_only_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [GATEWAY_READ_ONLY_TOOL_CALL_ID])
            gateway_read_only_eval_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [f"{GATEWAY_EVALUATION_ID}_read_only"])
            gateway_read_only_artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [GATEWAY_READ_ONLY_ARTIFACT_ID])
            gateway_missing_scope_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_MISSING_SCOPE_TASK_ID])
            gateway_cross_workspace_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_CROSS_WORKSPACE_TASK_ID])
            gateway_header_workspace_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_HEADER_WORKSPACE_TASK_ID])
            gateway_other_agent_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_OTHER_AGENT_TASK_ID])
            gateway_no_token_task_row = adapter.fetchone("SELECT * FROM tasks WHERE task_id=?", [GATEWAY_NO_TOKEN_TASK_ID])
            blocked_agent_row = adapter.fetchone("SELECT * FROM agents WHERE agent_id=?", [BLOCKED_AGENT_ID])
            gateway_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [GATEWAY_RUN_ID])
            gateway_missing_run_scope_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [f"{GATEWAY_RUN_ID}_missing_scope"])
            gateway_intruder_run_row = adapter.fetchone("SELECT * FROM runs WHERE run_id=?", [f"{GATEWAY_RUN_ID}_intruder"])
            gateway_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [GATEWAY_TOOL_CALL_ID])
            gateway_eval_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [GATEWAY_EVALUATION_ID])
            gateway_artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [GATEWAY_ARTIFACT_ID])
            gateway_missing_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [f"{GATEWAY_TOOL_CALL_ID}_missing_scope"])
            gateway_missing_eval_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [f"{GATEWAY_EVALUATION_ID}_missing_scope"])
            gateway_missing_artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [f"{GATEWAY_ARTIFACT_ID}_missing_scope"])
            gateway_intruder_tool_row = adapter.fetchone("SELECT * FROM tool_calls WHERE tool_call_id=?", [f"{GATEWAY_TOOL_CALL_ID}_intruder"])
            gateway_intruder_eval_row = adapter.fetchone("SELECT * FROM evaluations WHERE evaluation_id=?", [f"{GATEWAY_EVALUATION_ID}_intruder"])
            gateway_intruder_artifact_row = adapter.fetchone("SELECT * FROM artifacts WHERE artifact_id=?", [f"{GATEWAY_ARTIFACT_ID}_intruder"])
            gateway_blocked_approval_row = adapter.fetchone("SELECT * FROM approvals WHERE approval_id=?", [GATEWAY_BLOCKED_APPROVAL_ID])
            runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE task_id=?", [TASK_ID])["c"]
            audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["tasks", TASK_ID])["c"]
            gateway_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE task_id=?", [GATEWAY_TASK_ID])["c"]
            gateway_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["tasks", GATEWAY_TASK_ID])["c"]
            gateway_run_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=?", [GATEWAY_RUN_ID])["c"]
            gateway_run_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["runs", GATEWAY_RUN_ID])["c"]
            gateway_tool_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "tool_call.record"])["c"]
            gateway_eval_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "evaluation.submit"])["c"]
            gateway_artifact_runtime_event_count = adapter.fetchone("SELECT COUNT(*) AS c FROM runtime_events WHERE run_id=? AND event_type=?", [GATEWAY_RUN_ID, "artifact.record"])["c"]
            gateway_artifact_audit_count = adapter.fetchone("SELECT COUNT(*) AS c FROM audit_logs WHERE entity_type=? AND entity_id=?", ["artifacts", GATEWAY_ARTIFACT_ID])["c"]
            gateway_token_last_used = adapter.fetchone("SELECT last_used_at FROM agent_gateway_tokens WHERE token_id=?", ["agtok_pg_gateway_write"])

            failures: list[str] = []
            if read_only_status_code != 200 or read_only_backend.get("mode") != "read_only_http" or read_only_backend.get("writes_allowed") is not False:
                failures.append(f"read_only_backend_mismatch:{read_only_backend}")
            if blocked_status != 503 or blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"read_only_write_block_mismatch:{blocked_status}:{blocked_payload}")
            if gateway_blocked_status != 503 or gateway_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_write_block_mismatch:{gateway_blocked_status}:{gateway_blocked_payload}")
            if gateway_claim_blocked_status != 503 or gateway_claim_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_claim_block_mismatch:{gateway_claim_blocked_status}:{gateway_claim_blocked_payload}")
            if gateway_run_start_blocked_status != 503 or gateway_run_start_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_run_start_block_mismatch:{gateway_run_start_blocked_status}:{gateway_run_start_blocked_payload}")
            if gateway_tool_blocked_status != 503 or gateway_tool_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_tool_block_mismatch:{gateway_tool_blocked_status}:{gateway_tool_blocked_payload}")
            if gateway_eval_blocked_status != 503 or gateway_eval_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_eval_block_mismatch:{gateway_eval_blocked_status}:{gateway_eval_blocked_payload}")
            if gateway_artifact_blocked_status != 503 or gateway_artifact_blocked_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_read_only_artifact_block_mismatch:{gateway_artifact_blocked_status}:{gateway_artifact_blocked_payload}")
            if blocked_task_row:
                failures.append("read_only_post_created_blocked_task")
            if gateway_read_only_task_row:
                failures.append("read_only_post_created_blocked_gateway_task")
            if gateway_read_only_claim_task_row:
                failures.append("read_only_claim_created_or_mutated_gateway_task")
            if gateway_read_only_run_row:
                failures.append("read_only_run_start_created_gateway_run")
            if gateway_read_only_tool_row or gateway_read_only_eval_row or gateway_read_only_artifact_row:
                failures.append("read_only_evidence_write_created_row")
            if write_status_code != 200 or write_backend.get("mode") != "experimental_write_http" or write_backend.get("writes_allowed") is not True:
                failures.append(f"write_backend_mismatch:{write_backend}")
            if create_status != 201 or create_payload.get("task_id") != TASK_ID or create_payload.get("token_omitted") is not True:
                failures.append(f"task_create_payload_mismatch:{create_status}:{create_payload}")
            if readback_status != 200 or readback_payload.get("task", {}).get("task_id") != TASK_ID:
                failures.append(f"task_readback_mismatch:{readback_status}:{readback_payload}")
            if gateway_missing_scope_status != 403 or "tasks:create" not in json.dumps(gateway_missing_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_scope_mismatch:{gateway_missing_scope_status}:{gateway_missing_scope_payload}")
            if gateway_cross_workspace_status != 403 or "workspace" not in json.dumps(gateway_cross_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_cross_workspace_mismatch:{gateway_cross_workspace_status}:{gateway_cross_workspace_payload}")
            if gateway_header_workspace_status != 403 or "workspace" not in json.dumps(gateway_header_workspace_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_header_workspace_mismatch:{gateway_header_workspace_status}:{gateway_header_workspace_payload}")
            if gateway_other_agent_status != 403 or "another agent" not in json.dumps(gateway_other_agent_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_other_agent_mismatch:{gateway_other_agent_status}:{gateway_other_agent_payload}")
            if gateway_no_token_status != 401 or "token" not in json.dumps(gateway_no_token_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_no_token_mismatch:{gateway_no_token_status}:{gateway_no_token_payload}")
            if gateway_create_status != 201 or gateway_create_payload.get("task_id") != GATEWAY_TASK_ID or gateway_create_payload.get("token_omitted") is not True:
                failures.append(f"gateway_task_create_payload_mismatch:{gateway_create_status}:{gateway_create_payload}")
            gateway_task = gateway_create_payload.get("task") or {}
            if gateway_task.get("workspace_id") != GATEWAY_WORKSPACE_ID or gateway_task.get("owner_agent_id") != GATEWAY_AGENT_ID:
                failures.append(f"gateway_task_binding_mismatch:{gateway_task}")
            if gateway_missing_claim_scope_status != 403 or "tasks:claim" not in json.dumps(gateway_missing_claim_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_claim_scope_mismatch:{gateway_missing_claim_scope_status}:{gateway_missing_claim_scope_payload}")
            if gateway_claim_status != 200 or gateway_claim_payload.get("claimed_by") != GATEWAY_AGENT_ID:
                failures.append(f"gateway_claim_payload_mismatch:{gateway_claim_status}:{gateway_claim_payload}")
            if gateway_missing_run_scope_status != 403 or "runs:write" not in json.dumps(gateway_missing_run_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_run_scope_mismatch:{gateway_missing_run_scope_status}:{gateway_missing_run_scope_payload}")
            gateway_run = gateway_run_start_payload.get("run") or {}
            if gateway_run_start_status != 201 or gateway_run.get("run_id") != GATEWAY_RUN_ID or gateway_run.get("workspace_id") != GATEWAY_WORKSPACE_ID:
                failures.append(f"gateway_run_start_payload_mismatch:{gateway_run_start_status}:{gateway_run_start_payload}")
            if gateway_intruder_claim_status != 403 or "another agent" not in json.dumps(gateway_intruder_claim_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_claim_mismatch:{gateway_intruder_claim_status}:{gateway_intruder_claim_payload}")
            if gateway_intruder_run_status != 403 or "another agent" not in json.dumps(gateway_intruder_run_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_run_mismatch:{gateway_intruder_run_status}:{gateway_intruder_run_payload}")
            if gateway_missing_tool_scope_status != 403 or "toolcalls:write" not in json.dumps(gateway_missing_tool_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_tool_scope_mismatch:{gateway_missing_tool_scope_status}:{gateway_missing_tool_scope_payload}")
            if gateway_tool_write_status != 201 or (gateway_tool_write_payload.get("tool_call") or {}).get("tool_call_id") != GATEWAY_TOOL_CALL_ID:
                failures.append(f"gateway_tool_write_mismatch:{gateway_tool_write_status}:{gateway_tool_write_payload}")
            if gateway_missing_eval_scope_status != 403 or "evaluations:submit" not in json.dumps(gateway_missing_eval_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_eval_scope_mismatch:{gateway_missing_eval_scope_status}:{gateway_missing_eval_scope_payload}")
            if gateway_eval_write_status != 201 or (gateway_eval_write_payload.get("evaluation") or {}).get("evaluation_id") != GATEWAY_EVALUATION_ID:
                failures.append(f"gateway_eval_write_mismatch:{gateway_eval_write_status}:{gateway_eval_write_payload}")
            if gateway_missing_artifact_scope_status != 403 or "artifacts:write" not in json.dumps(gateway_missing_artifact_scope_payload, ensure_ascii=False):
                failures.append(f"gateway_missing_artifact_scope_mismatch:{gateway_missing_artifact_scope_status}:{gateway_missing_artifact_scope_payload}")
            if gateway_artifact_write_status != 201 or (gateway_artifact_write_payload.get("artifact") or {}).get("artifact_id") != GATEWAY_ARTIFACT_ID:
                failures.append(f"gateway_artifact_write_mismatch:{gateway_artifact_write_status}:{gateway_artifact_write_payload}")
            if gateway_intruder_tool_status != 403 or "another agent" not in json.dumps(gateway_intruder_tool_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_tool_mismatch:{gateway_intruder_tool_status}:{gateway_intruder_tool_payload}")
            if gateway_intruder_eval_status != 403 or "another agent" not in json.dumps(gateway_intruder_eval_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_eval_mismatch:{gateway_intruder_eval_status}:{gateway_intruder_eval_payload}")
            if gateway_intruder_artifact_status != 403 or "another agent" not in json.dumps(gateway_intruder_artifact_payload, ensure_ascii=False).lower():
                failures.append(f"gateway_intruder_artifact_mismatch:{gateway_intruder_artifact_status}:{gateway_intruder_artifact_payload}")
            if gateway_readback_status != 200 or gateway_readback_payload.get("task", {}).get("task_id") != GATEWAY_TASK_ID:
                failures.append(f"gateway_task_readback_mismatch:{gateway_readback_status}:{gateway_readback_payload}")
            if gateway_run_readback_status != 200 or gateway_run_readback_payload.get("run", {}).get("run_id") != GATEWAY_RUN_ID:
                failures.append(f"gateway_run_readback_mismatch:{gateway_run_readback_status}:{gateway_run_readback_payload}")
            if agent_block_status != 503 or agent_block_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"non_allowlisted_write_not_blocked:{agent_block_status}:{agent_block_payload}")
            if gateway_approval_block_status != 503 or gateway_approval_block_payload.get("error") != "postgres_read_only_backend":
                failures.append(f"gateway_non_allowlisted_write_not_blocked:{gateway_approval_block_status}:{gateway_approval_block_payload}")
            if blocked_agent_row:
                failures.append("non_allowlisted_agent_write_created_row")
            if gateway_blocked_approval_row:
                failures.append("non_allowlisted_gateway_approval_created_row")
            if not task_row or task_row.get("workspace_id") != WORKSPACE_ID or task_row.get("owner_agent_id") != AGENT_ID:
                failures.append(f"postgres_task_row_mismatch:{task_row}")
            if int(runtime_event_count or 0) < 1:
                failures.append("postgres_runtime_event_missing")
            if int(audit_count or 0) < 1:
                failures.append("postgres_audit_missing")
            if not gateway_task_row or gateway_task_row.get("workspace_id") != GATEWAY_WORKSPACE_ID or gateway_task_row.get("owner_agent_id") != GATEWAY_AGENT_ID:
                failures.append(f"postgres_gateway_task_row_mismatch:{gateway_task_row}")
            if gateway_missing_scope_task_row or gateway_cross_workspace_task_row or gateway_header_workspace_task_row or gateway_other_agent_task_row or gateway_no_token_task_row:
                failures.append("postgres_gateway_rejected_task_created_row")
            if gateway_missing_run_scope_row:
                failures.append("postgres_gateway_missing_scope_run_created_row")
            if gateway_intruder_run_row:
                failures.append("postgres_gateway_intruder_run_created_row")
            if gateway_missing_tool_row or gateway_missing_eval_row or gateway_missing_artifact_row:
                failures.append("postgres_gateway_missing_scope_evidence_created_row")
            if gateway_intruder_tool_row or gateway_intruder_eval_row or gateway_intruder_artifact_row:
                failures.append("postgres_gateway_intruder_evidence_created_row")
            if not gateway_run_row or gateway_run_row.get("workspace_id") != GATEWAY_WORKSPACE_ID or gateway_run_row.get("task_id") != GATEWAY_TASK_ID or gateway_run_row.get("agent_id") != GATEWAY_AGENT_ID:
                failures.append(f"postgres_gateway_run_row_mismatch:{gateway_run_row}")
            if not gateway_tool_row or gateway_tool_row.get("run_id") != GATEWAY_RUN_ID or gateway_tool_row.get("agent_id") != GATEWAY_AGENT_ID:
                failures.append(f"postgres_gateway_tool_row_mismatch:{gateway_tool_row}")
            if not gateway_eval_row or gateway_eval_row.get("run_id") != GATEWAY_RUN_ID or gateway_eval_row.get("task_id") != GATEWAY_TASK_ID:
                failures.append(f"postgres_gateway_eval_row_mismatch:{gateway_eval_row}")
            if not gateway_artifact_row or gateway_artifact_row.get("run_id") != GATEWAY_RUN_ID or gateway_artifact_row.get("task_id") != GATEWAY_TASK_ID:
                failures.append(f"postgres_gateway_artifact_row_mismatch:{gateway_artifact_row}")
            if not gateway_task_row or gateway_task_row.get("status") != "running":
                failures.append(f"postgres_gateway_claim_did_not_mark_task_running:{gateway_task_row}")
            if int(gateway_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_runtime_event_missing")
            if int(gateway_audit_count or 0) < 1:
                failures.append("postgres_gateway_audit_missing")
            if int(gateway_run_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_run_runtime_event_missing")
            if int(gateway_run_audit_count or 0) < 1:
                failures.append("postgres_gateway_run_audit_missing")
            if int(gateway_tool_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_tool_runtime_event_missing")
            if int(gateway_eval_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_eval_runtime_event_missing")
            if int(gateway_artifact_runtime_event_count or 0) < 1:
                failures.append("postgres_gateway_artifact_runtime_event_missing")
            if int(gateway_artifact_audit_count or 0) < 1:
                failures.append("postgres_gateway_artifact_audit_missing")
            if not (gateway_token_last_used or {}).get("last_used_at"):
                failures.append("postgres_gateway_token_last_used_not_updated")
            transcript = json.dumps(
                [
                    blocked_payload,
                    gateway_blocked_payload,
                    gateway_claim_blocked_payload,
                    gateway_run_start_blocked_payload,
                    gateway_missing_scope_payload,
                    gateway_missing_claim_scope_payload,
                    gateway_missing_run_scope_payload,
                    gateway_tool_blocked_payload,
                    gateway_eval_blocked_payload,
                    gateway_artifact_blocked_payload,
                    gateway_cross_workspace_payload,
                    gateway_header_workspace_payload,
                    gateway_other_agent_payload,
                    gateway_no_token_payload,
                    gateway_create_payload,
                    gateway_claim_payload,
                    gateway_run_start_payload,
                    gateway_missing_tool_scope_payload,
                    gateway_tool_write_payload,
                    gateway_missing_eval_scope_payload,
                    gateway_eval_write_payload,
                    gateway_missing_artifact_scope_payload,
                    gateway_artifact_write_payload,
                    gateway_intruder_claim_payload,
                    gateway_intruder_run_payload,
                    gateway_intruder_tool_payload,
                    gateway_intruder_eval_payload,
                    gateway_intruder_artifact_payload,
                    agent_block_payload,
                    gateway_approval_block_payload,
                ],
                ensure_ascii=False,
                sort_keys=True,
            )
            if gateway_token in transcript or gateway_observer_token in transcript or gateway_intruder_token in transcript:
                failures.append("postgres_gateway_raw_token_leaked")

            output = {
                "ok": not failures,
                "skipped": False,
                "contract": CONTRACT_ID,
                "contracts": [
                    CONTRACT_ID,
                    "postgres_http_gateway_task_write_parity_v1",
                    "postgres_http_gateway_execution_start_write_v1",
                    "postgres_http_gateway_evidence_write_v1",
                ],
                "image": args.image,
                "driver_status": driver_status,
                "read_only_backend_mode": read_only_backend.get("mode"),
                "read_only_write_block_status": blocked_status,
                "write_backend_mode": write_backend.get("mode"),
                "write_allowlist": write_backend.get("write_allowlist"),
                "task_create_status": create_status,
                "task_readback_status": readback_status,
                "gateway_read_only_write_block_status": gateway_blocked_status,
                "gateway_read_only_claim_block_status": gateway_claim_blocked_status,
                "gateway_read_only_run_start_block_status": gateway_run_start_blocked_status,
                "gateway_read_only_tool_block_status": gateway_tool_blocked_status,
                "gateway_read_only_eval_block_status": gateway_eval_blocked_status,
                "gateway_read_only_artifact_block_status": gateway_artifact_blocked_status,
                "gateway_missing_scope_status": gateway_missing_scope_status,
                "gateway_missing_claim_scope_status": gateway_missing_claim_scope_status,
                "gateway_missing_run_scope_status": gateway_missing_run_scope_status,
                "gateway_missing_tool_scope_status": gateway_missing_tool_scope_status,
                "gateway_missing_eval_scope_status": gateway_missing_eval_scope_status,
                "gateway_missing_artifact_scope_status": gateway_missing_artifact_scope_status,
                "gateway_cross_workspace_status": gateway_cross_workspace_status,
                "gateway_header_workspace_status": gateway_header_workspace_status,
                "gateway_other_agent_status": gateway_other_agent_status,
                "gateway_no_token_status": gateway_no_token_status,
                "gateway_task_create_status": gateway_create_status,
                "gateway_claim_status": gateway_claim_status,
                "gateway_run_start_status": gateway_run_start_status,
                "gateway_tool_write_status": gateway_tool_write_status,
                "gateway_eval_write_status": gateway_eval_write_status,
                "gateway_artifact_write_status": gateway_artifact_write_status,
                "gateway_intruder_claim_status": gateway_intruder_claim_status,
                "gateway_intruder_run_status": gateway_intruder_run_status,
                "gateway_intruder_tool_status": gateway_intruder_tool_status,
                "gateway_intruder_eval_status": gateway_intruder_eval_status,
                "gateway_intruder_artifact_status": gateway_intruder_artifact_status,
                "gateway_task_readback_status": gateway_readback_status,
                "gateway_run_readback_status": gateway_run_readback_status,
                "non_allowlisted_write_status": agent_block_status,
                "gateway_non_allowlisted_write_status": gateway_approval_block_status,
                "task_id": TASK_ID,
                "gateway_task_id": GATEWAY_TASK_ID,
                "gateway_run_id": GATEWAY_RUN_ID,
                "gateway_tool_call_id": GATEWAY_TOOL_CALL_ID,
                "gateway_evaluation_id": GATEWAY_EVALUATION_ID,
                "gateway_artifact_id": GATEWAY_ARTIFACT_ID,
                "workspace_id": WORKSPACE_ID,
                "gateway_workspace_id": GATEWAY_WORKSPACE_ID,
                "runtime_event_count": int(runtime_event_count or 0),
                "audit_count": int(audit_count or 0),
                "gateway_runtime_event_count": int(gateway_runtime_event_count or 0),
                "gateway_audit_count": int(gateway_audit_count or 0),
                "gateway_run_runtime_event_count": int(gateway_run_runtime_event_count or 0),
                "gateway_run_audit_count": int(gateway_run_audit_count or 0),
                "gateway_tool_runtime_event_count": int(gateway_tool_runtime_event_count or 0),
                "gateway_eval_runtime_event_count": int(gateway_eval_runtime_event_count or 0),
                "gateway_artifact_runtime_event_count": int(gateway_artifact_runtime_event_count or 0),
                "gateway_artifact_audit_count": int(gateway_artifact_audit_count or 0),
                "gateway_token_last_used": bool((gateway_token_last_used or {}).get("last_used_at")),
                "free_local_dependencies": [],
                "fallback_performed": False,
                "token_omitted": True,
                "failures": failures,
                "next_proof": "Widen the routed Postgres write allowlist only after each route has a dedicated HTTP/CLI smoke.",
            }
            print(json.dumps(server.json_safe(output), ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not failures else 1
        except (AssertionError, PostgresAdapterUnavailable, RuntimeError, ValueError, KeyError) as exc:
            if adapter is not None:
                adapter.rollback()
            return unavailable(redact(str(exc), pg_auth), skip=args.skip_if_unavailable)
        finally:
            stop_server(proc)
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
