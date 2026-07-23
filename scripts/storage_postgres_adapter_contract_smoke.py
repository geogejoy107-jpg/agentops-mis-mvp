#!/usr/bin/env python3
"""Validate the first Python Postgres adapter SQL contract.

This is the bridge between the generated-schema container smoke and a future
Python Postgres storage adapter. It proves three commercial-migration
invariants without changing the Free Local runtime path:

- Free Local keeps zero required Python dependencies; psycopg remains optional.
- SQLite `?` and `:named` helper placeholders translate into psycopg-compatible
  `%s` and `%(name)s` forms without touching SQL string literals.
- Representative helper insert/update/select SQL can be rendered and executed
  inside a real Postgres container created from `server.SCHEMA_SQL`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402


NAMED_SQL = {
    "insert_user": """
        INSERT INTO users(user_id,name,email,role,created_at)
        VALUES(:user_id,:name,:email,:role,:created_at)
    """,
    "insert_agent": """
        INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
        VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)
    """,
    "insert_task": """
        INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
        VALUES(:task_id,:workspace_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)
    """,
    "update_task": """
        UPDATE tasks SET title=:title, description=:description, requester_id=:requester_id,
        owner_agent_id=:owner_agent_id, collaborator_agent_ids=:collaborator_agent_ids, status=:status,
        priority=:priority, due_date=:due_date, acceptance_criteria=:acceptance_criteria, risk_level=:risk_level,
        budget_limit_usd=:budget_limit_usd, workspace_id=:workspace_id, updated_at=:updated_at WHERE task_id=:task_id
    """,
    "insert_run": """
        INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
        VALUES(:run_id,:workspace_id,:task_id,:agent_id,:runtime_type,:status,:started_at,:ended_at,:duration_ms,:input_summary,:output_summary,:model_provider,:model_name,:input_tokens,:output_tokens,:reasoning_tokens,:cost_usd,:error_type,:error_message,:trace_id,:parent_run_id,:delegation_id,:approval_required,:created_at)
    """,
    "update_run": """
        UPDATE runs SET task_id=:task_id, agent_id=:agent_id, runtime_type=:runtime_type, status=:status,
        started_at=:started_at, ended_at=:ended_at, duration_ms=:duration_ms, input_summary=:input_summary,
        output_summary=:output_summary, model_provider=:model_provider, model_name=:model_name,
        input_tokens=:input_tokens, output_tokens=:output_tokens, reasoning_tokens=:reasoning_tokens,
        cost_usd=:cost_usd, error_type=:error_type, error_message=:error_message, trace_id=:trace_id,
        parent_run_id=:parent_run_id, delegation_id=:delegation_id, approval_required=:approval_required,
        workspace_id=:workspace_id
        WHERE run_id=:run_id
    """,
    "insert_prepared_action": """
        INSERT INTO prepared_actions(prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,
        requested_by_agent_id,action_type,provider,target_resource,normalized_args_json,args_hash,snapshot_ref,
        snapshot_hash,status,result_json,created_at,updated_at,approved_at,consumed_at)
        VALUES(:prepared_action_id,:workspace_id,:task_id,:run_id,:tool_call_id,:approval_id,
        :requested_by_agent_id,:action_type,:provider,:target_resource,:normalized_args_json,:args_hash,:snapshot_ref,
        :snapshot_hash,:status,:result_json,:created_at,:updated_at,:approved_at,:consumed_at)
    """,
    "update_prepared_action": """
        UPDATE prepared_actions SET workspace_id=:workspace_id, task_id=:task_id, run_id=:run_id,
        tool_call_id=:tool_call_id, approval_id=:approval_id, requested_by_agent_id=:requested_by_agent_id,
        action_type=:action_type, provider=:provider, target_resource=:target_resource,
        normalized_args_json=:normalized_args_json, args_hash=:args_hash, snapshot_ref=:snapshot_ref,
        snapshot_hash=:snapshot_hash, status=:status, result_json=:result_json, updated_at=:updated_at,
        approved_at=:approved_at, consumed_at=:consumed_at WHERE prepared_action_id=:prepared_action_id
    """,
}

QMARK_SQL = {
    "workspace_task_lookup": "SELECT * FROM tasks WHERE workspace_id=? AND task_id=?",
    "workspace_prepared_status": "SELECT * FROM prepared_actions WHERE workspace_id=? AND status IN (?,?) ORDER BY updated_at DESC LIMIT ?",
    "literal_question_mark": "SELECT '?' AS literal_value, task_id FROM tasks WHERE task_id=?",
}


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def translate_named_placeholders(sql: str) -> tuple[str, list[str]]:
    output: list[str] = []
    names: list[str] = []
    in_single = False
    i = 0
    while i < len(sql):
        char = sql[i]
        if char == "'":
            output.append(char)
            if i + 1 < len(sql) and sql[i + 1] == "'":
                output.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if char == ":" and not in_single:
            match = re.match(r":([A-Za-z_][A-Za-z0-9_]*)", sql[i:])
            if match:
                name = match.group(1)
                output.append(f"%({name})s")
                names.append(name)
                i += len(name) + 1
                continue
        output.append(char)
        i += 1
    return "".join(output), names


def translate_qmark_to_psycopg(sql: str) -> tuple[str, int]:
    translated = contract.translate_qmark_placeholders(sql).replace("$", "%")
    return re.sub(r"%\d+", "%s", translated), translated.count("%")


def render_named_for_psql(sql: str, values: dict) -> str:
    output: list[str] = []
    in_single = False
    i = 0
    while i < len(sql):
        char = sql[i]
        if char == "'":
            output.append(char)
            if i + 1 < len(sql) and sql[i + 1] == "'":
                output.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if char == ":" and not in_single:
            match = re.match(r":([A-Za-z_][A-Za-z0-9_]*)", sql[i:])
            if match:
                name = match.group(1)
                if name not in values:
                    raise KeyError(name)
                output.append(sql_literal(values[name]))
                i += len(name) + 1
                continue
        output.append(char)
        i += 1
    return "".join(output).strip() + ";"


def render_qmark_for_psql(sql: str, values: list) -> str:
    output: list[str] = []
    in_single = False
    value_index = 0
    i = 0
    while i < len(sql):
        char = sql[i]
        if char == "'":
            output.append(char)
            if i + 1 < len(sql) and sql[i + 1] == "'":
                output.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if char == "?" and not in_single:
            output.append(sql_literal(values[value_index]))
            value_index += 1
            i += 1
            continue
        output.append(char)
        i += 1
    if value_index != len(values):
        raise ValueError(f"unused qmark values: used={value_index} provided={len(values)}")
    return "".join(output).strip() + ";"


def free_local_dependencies() -> list[str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(pyproject.get("project", {}).get("dependencies", []))


def representative_rows() -> dict[str, dict]:
    now = "2026-06-22T01:00:00+00:00"
    user = {
        "user_id": "usr_adapter_founder",
        "name": "Adapter Founder",
        "email": "adapter@example.local",
        "role": "founder",
        "created_at": now,
    }
    agent = {
        "agent_id": "agt_adapter_a",
        "name": "Adapter Agent A",
        "role": "operator",
        "description": "Adapter parity agent.",
        "runtime_type": "mock",
        "model_provider": "mock",
        "model_name": "mock-model",
        "status": "idle",
        "permission_level": "standard",
        "allowed_tools": "[]",
        "budget_limit_usd": 0,
        "owner_user_id": "usr_adapter_founder",
        "created_at": now,
        "updated_at": now,
    }
    task = {
        "task_id": "tsk_adapter_a",
        "workspace_id": "ws_adapter_a",
        "title": "Adapter contract task",
        "description": "Created through translated helper SQL.",
        "requester_id": "usr_adapter_founder",
        "owner_agent_id": "agt_adapter_a",
        "collaborator_agent_ids": "[]",
        "status": "planned",
        "priority": "medium",
        "due_date": None,
        "acceptance_criteria": "Translated helper SQL must execute in Postgres.",
        "risk_level": "low",
        "budget_limit_usd": 0,
        "created_at": now,
        "updated_at": now,
    }
    run = {
        "run_id": "run_adapter_a",
        "workspace_id": "ws_adapter_a",
        "task_id": "tsk_adapter_a",
        "agent_id": "agt_adapter_a",
        "runtime_type": "mock",
        "status": "running",
        "started_at": now,
        "ended_at": None,
        "duration_ms": None,
        "input_summary": "Adapter contract input.",
        "output_summary": None,
        "model_provider": "mock",
        "model_name": "mock-model",
        "input_tokens": 1,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0,
        "error_type": None,
        "error_message": None,
        "trace_id": "trace_adapter_a",
        "parent_run_id": None,
        "delegation_id": None,
        "approval_required": 1,
        "created_at": now,
    }
    return {"user": user, "agent": agent, "task": task, "run": run}


def adapter_fixture_sql() -> str:
    rows = representative_rows()
    task_updated = dict(rows["task"], status="running", updated_at="2026-06-22T01:01:00+00:00")
    run_completed = dict(
        rows["run"],
        status="completed",
        ended_at="2026-06-22T01:02:00+00:00",
        duration_ms=7,
        output_summary="Adapter contract output.",
        approval_required=0,
    )
    tool_call_sql = """
        INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
        VALUES('tc_adapter_a','run_adapter_a','agt_adapter_a','adapter_contract','v1','database','{}','postgres://adapter','high','waiting_approval','Adapter prepared action pending.',NULL,'2026-06-22T01:00:00+00:00',NULL,'2026-06-22T01:00:00+00:00');
    """
    approval_sql = """
        INSERT INTO approvals(approval_id,approval_kind,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,decision,reason,expires_at,created_at,decided_at)
        VALUES('ap_adapter_a','prepared_action','tsk_adapter_a','run_adapter_a','tc_adapter_a','agt_adapter_a',NULL,'pending','Adapter contract approval.',NULL,'2026-06-22T01:00:00+00:00',NULL);
    """
    prepared = {
        "prepared_action_id": "pact_adapter_a",
        "workspace_id": "ws_adapter_a",
        "task_id": "tsk_adapter_a",
        "run_id": "run_adapter_a",
        "tool_call_id": "tc_adapter_a",
        "approval_id": "ap_adapter_a",
        "requested_by_agent_id": "agt_adapter_a",
        "action_type": "runtime.external_write",
        "provider": "adapter-contract",
        "target_resource": "postgres://adapter",
        "normalized_args_json": '{"workspace_id":"ws_adapter_a"}',
        "args_hash": "args_hash_adapter_a",
        "snapshot_ref": "snapshot://adapter/a",
        "snapshot_hash": "snapshot_hash_adapter_a",
        "status": "waiting_approval",
        "result_json": "{}",
        "created_at": "2026-06-22T01:00:00+00:00",
        "updated_at": "2026-06-22T01:00:00+00:00",
        "approved_at": None,
        "consumed_at": None,
    }
    prepared_consumed = dict(
        prepared,
        status="consumed",
        result_json='{"provider_result_id":"adapter-result"}',
        updated_at="2026-06-22T01:03:00+00:00",
        approved_at="2026-06-22T01:02:30+00:00",
        consumed_at="2026-06-22T01:03:00+00:00",
    )
    qmark_queries = [
        render_qmark_for_psql(QMARK_SQL["workspace_task_lookup"], ["ws_adapter_a", "tsk_adapter_a"]),
        render_qmark_for_psql(QMARK_SQL["workspace_prepared_status"], ["ws_adapter_a", "waiting_approval", "consumed", 5]),
        render_qmark_for_psql(QMARK_SQL["literal_question_mark"], ["tsk_adapter_a"]),
    ]
    statements = [
        "BEGIN;",
        render_named_for_psql(NAMED_SQL["insert_user"], rows["user"]),
        render_named_for_psql(NAMED_SQL["insert_agent"], rows["agent"]),
        render_named_for_psql(NAMED_SQL["insert_task"], rows["task"]),
        render_named_for_psql(NAMED_SQL["update_task"], task_updated),
        render_named_for_psql(NAMED_SQL["insert_run"], rows["run"]),
        render_named_for_psql(NAMED_SQL["update_run"], run_completed),
        tool_call_sql.strip(),
        approval_sql.strip(),
        render_named_for_psql(NAMED_SQL["insert_prepared_action"], prepared),
        render_named_for_psql(NAMED_SQL["update_prepared_action"], prepared_consumed),
        *qmark_queries,
        """
        DO $$
        DECLARE
            count_value integer;
        BEGIN
            SELECT COUNT(*) INTO count_value FROM tasks WHERE workspace_id='ws_adapter_a' AND status='running';
            IF count_value != 1 THEN
                RAISE EXCEPTION 'translated task helper SQL did not persist expected row: %', count_value;
            END IF;

            SELECT COUNT(*) INTO count_value FROM runs WHERE workspace_id='ws_adapter_a' AND status='completed';
            IF count_value != 1 THEN
                RAISE EXCEPTION 'translated run helper SQL did not persist expected row: %', count_value;
            END IF;

            SELECT COUNT(*) INTO count_value FROM prepared_actions WHERE workspace_id='ws_adapter_a' AND status='consumed' AND result_json LIKE '%adapter-result%';
            IF count_value != 1 THEN
                RAISE EXCEPTION 'translated prepared-action helper SQL did not persist consumed result: %', count_value;
            END IF;
        END $$;
        """.strip(),
        "COMMIT;",
    ]
    return "\n\n".join(statements) + "\n"


def validate_translation_contract() -> tuple[list[dict], list[str]]:
    failures: list[str] = []
    translated: list[dict] = []
    dependencies = free_local_dependencies()
    if any("psycopg" in dep.lower() for dep in dependencies):
        failures.append(f"Free Local pyproject dependencies must not require psycopg: {dependencies}")
    for name, sql in NAMED_SQL.items():
        driver_sql, names = translate_named_placeholders(sql)
        if ":" in driver_sql:
            failures.append(f"{name} still contains SQLite named placeholders")
        if "%(" not in driver_sql:
            failures.append(f"{name} did not translate to psycopg named placeholders")
        translated.append({"name": name, "kind": "named", "placeholder_count": len(names)})
    for name, sql in QMARK_SQL.items():
        driver_sql, count = translate_qmark_to_psycopg(sql)
        if "'?'" not in driver_sql and name == "literal_question_mark":
            failures.append("literal question mark changed during qmark translation")
        if "$" in driver_sql or "?" in driver_sql.replace("'?'", ""):
            failures.append(f"{name} still contains non-psycopg placeholders")
        translated.append({"name": name, "kind": "qmark", "placeholder_count": count})
    return translated, failures


def run_container_sql(image: str, skip: bool) -> tuple[int | None, dict | None]:
    early = container_smoke.docker_available(skip)
    if early is not None:
        return early, None
    early = container_smoke.ensure_image(image, skip)
    if early is not None:
        return early, None

    container = f"agentops-pg-adapter-contract-{container_smoke.secrets.token_hex(6)}"
    pg_auth = container_smoke.secrets.token_urlsafe(18)
    started = container_smoke.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container,
            "-e",
            "POSTGRES_USER=agentops",
            "-e",
            "POSTGRES_DB=agentops",
            "-e",
            f"POSTGRES_PASSWORD={pg_auth}",
            image,
        ],
        timeout=60,
    )
    if started.returncode != 0:
        return container_smoke.unavailable((started.stderr or started.stdout).strip(), skip=skip), None

    try:
        if not container_smoke.wait_for_postgres(container):
            return container_smoke.unavailable("Postgres container did not become ready before timeout.", skip=skip), None
        postgres_sql = contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL)
        fixture_sql = adapter_fixture_sql()
        with tempfile.TemporaryDirectory(prefix="agentops-pg-adapter-contract-") as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            fixture_path = Path(temp_dir) / "adapter_fixture.sql"
            schema_path.write_text(postgres_sql, encoding="utf-8")
            fixture_path.write_text(fixture_sql, encoding="utf-8")
            for local_path, remote_path in [
                (schema_path, "/tmp/agentops_schema.sql"),
                (fixture_path, "/tmp/agentops_adapter_fixture.sql"),
            ]:
                copied = container_smoke.run(["docker", "cp", str(local_path), f"{container}:{remote_path}"], timeout=30)
                if copied.returncode != 0:
                    raise RuntimeError((copied.stderr or copied.stdout).strip())
            schema_result = container_smoke.docker_exec(container, pg_auth, ["-f", "/tmp/agentops_schema.sql"], timeout=90)
            if schema_result.returncode != 0:
                raise RuntimeError((schema_result.stderr or schema_result.stdout).strip())
            fixture_result = container_smoke.docker_exec(container, pg_auth, ["-f", "/tmp/agentops_adapter_fixture.sql"], timeout=90)
            if fixture_result.returncode != 0:
                raise RuntimeError((fixture_result.stderr or fixture_result.stdout).strip())
        return None, {
            "image": image,
            "postgres_ddl_hash": contract.sha256_text(postgres_sql),
            "fixture_hash": contract.sha256_text(fixture_sql),
            "executed": True,
        }
    finally:
        container_smoke.run(["docker", "rm", "-f", container], timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Postgres adapter SQL contract.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE, help="Postgres Docker image to use.")
    parser.add_argument("--skip-if-unavailable", action="store_true", help="Return success with skipped=true when Docker/image is unavailable.")
    args = parser.parse_args()

    translated, failures = validate_translation_contract()
    if failures:
        output = {
            "ok": False,
            "contract": "postgres_adapter_sql_contract_v1",
            "failures": failures,
            "translated_sql": translated,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    early_code, container_result = run_container_sql(args.image, args.skip_if_unavailable)
    if early_code is not None:
        return early_code

    output = {
        "ok": True,
        "skipped": False,
        "contract": "postgres_adapter_sql_contract_v1",
        "free_local_dependencies": free_local_dependencies(),
        "translated_sql": translated,
        "container": container_result,
        "next_proof": "Add the optional psycopg execution adapter and run the full storage-boundary fixture through it.",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
