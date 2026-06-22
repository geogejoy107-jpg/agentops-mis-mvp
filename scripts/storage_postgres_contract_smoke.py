#!/usr/bin/env python3
"""Validate the first Postgres parity contract derived from the SQLite schema.

This smoke does not require a running Postgres server. It locks the adapter
contract that a future Postgres container smoke must satisfy:

- derive DDL from the executable SQLite schema in server.py, not stale docs;
- preserve core ledger/prepared-action tables and indexes;
- keep JSON-ish columns as text for response-shape parity in the first adapter;
- translate DB-API `?` placeholders into Postgres `$n` placeholders safely.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


REQUIRED_TABLES = {
    "users",
    "agents",
    "tasks",
    "runs",
    "tool_calls",
    "approvals",
    "prepared_actions",
    "memories",
    "evaluations",
    "artifacts",
    "audit_logs",
    "runtime_connectors",
    "runtime_events",
    "workflow_jobs",
    "agent_gateway_tokens",
    "agent_gateway_sessions",
    "agent_gateway_enrollment_requests",
    "agent_plans",
    "plan_evidence_manifests",
    "knowledge_documents",
}

JSON_TEXT_COLUMNS = {
    "allowed_tools",
    "collaborator_agent_ids",
    "normalized_args_json",
    "metadata_json",
    "result_json",
    "scopes_json",
    "referenced_specs_json",
    "referenced_memories_json",
    "referenced_bases_json",
    "proposed_files_to_change_json",
    "execution_steps_json",
    "expected_steps_json",
    "tool_call_ids_json",
    "evaluation_ids_json",
    "artifact_ids_json",
    "audit_ids_json",
    "verification_json",
    "default_bases_json",
    "swappable_bases_json",
    "agent_roles_json",
    "task_schema_json",
    "memory_schema_json",
    "quality_gates_json",
    "approval_policy_json",
    "mapping_json",
    "preview_json",
}

REPRESENTATIVE_SQL = {
    "task_lookup": "SELECT * FROM tasks WHERE task_id=? AND COALESCE(workspace_id,'local-demo')=?",
    "prepared_status_filter": "SELECT * FROM prepared_actions WHERE workspace_id=? AND status IN (?,?) ORDER BY updated_at DESC LIMIT ?",
    "audit_entity": "SELECT * FROM audit_logs WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC LIMIT ?",
    "literal_question_mark": "SELECT '?' AS literal_value, task_id FROM tasks WHERE task_id=?",
}


def sqlite_schema_tables(sql: str) -> set[str]:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql))


def sqlite_schema_indexes(sql: str) -> set[str]:
    return set(re.findall(r"CREATE INDEX IF NOT EXISTS\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql))


def split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    for char in sql:
        if char == "'":
            in_single = not in_single
        if char == ";" and not in_single:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue
        current.append(char)
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def postgres_ddl_from_sqlite(sql: str) -> str:
    statements = []
    for raw in split_statements(sql):
        statement = raw.strip()
        if not statement:
            continue
        if "CREATE VIRTUAL TABLE" in statement.upper() or "USING fts5" in statement:
            continue
        statement = re.sub(r"\bINTEGER\b", "INTEGER", statement)
        statement = re.sub(r"\bREAL\b", "DOUBLE PRECISION", statement)
        statement = re.sub(r"\bTEXT\b", "TEXT", statement)
        statement = re.sub(r"\bDEFAULT\s+0\b", "DEFAULT 0", statement)
        statement = re.sub(r"\bDEFAULT\s+1\b", "DEFAULT 1", statement)
        statements.append(statement + ";")
    return "\n\n".join(statements) + "\n"


def translate_qmark_placeholders(sql: str) -> str:
    output: list[str] = []
    in_single = False
    param_index = 1
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
            output.append(f"${param_index}")
            param_index += 1
            i += 1
            continue
        output.append(char)
        i += 1
    return "".join(output)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    sqlite_sql = server.SCHEMA_SQL
    postgres_sql = postgres_ddl_from_sqlite(sqlite_sql)
    tables = sqlite_schema_tables(sqlite_sql)
    indexes = sqlite_schema_indexes(sqlite_sql)

    missing_tables = sorted(REQUIRED_TABLES - tables)
    require(not missing_tables, f"required tables missing from executable schema: {missing_tables}", failures)
    require("knowledge_fts" not in sqlite_schema_tables(postgres_sql), "Postgres contract must not include SQLite FTS virtual table", failures)
    require("PRAGMA" not in postgres_sql.upper(), "Postgres contract must not include PRAGMA", failures)
    require("AUTOINCREMENT" not in postgres_sql.upper(), "Postgres contract must not include AUTOINCREMENT", failures)
    require("USING fts5" not in postgres_sql, "Postgres contract must not include SQLite fts5 syntax", failures)
    require("DOUBLE PRECISION" in postgres_sql, "REAL columns should map to DOUBLE PRECISION", failures)

    for column in JSON_TEXT_COLUMNS:
        if column in sqlite_sql:
            pattern = rf"\b{re.escape(column)}\s+TEXT\b"
            require(re.search(pattern, postgres_sql), f"{column} should remain TEXT for first response-shape parity adapter", failures)

    placeholder_results = {
        name: translate_qmark_placeholders(sql)
        for name, sql in REPRESENTATIVE_SQL.items()
    }
    require("$1" in placeholder_results["task_lookup"] and "$2" in placeholder_results["task_lookup"], "basic placeholder translation failed", failures)
    require("'?'" in placeholder_results["literal_question_mark"], "placeholder translator changed literal question mark", failures)
    require(placeholder_results["prepared_status_filter"].count("$") == 4, "IN/LIMIT placeholder translation count failed", failures)

    required_indexes = {
        "idx_tasks_workspace",
        "idx_runs_workspace",
        "idx_prepared_actions_workspace",
        "idx_prepared_actions_status",
        "idx_agent_plans_workspace",
        "idx_plan_evidence_run",
    }
    missing_indexes = sorted(required_indexes - indexes)
    require(not missing_indexes, f"required parity indexes missing: {missing_indexes}", failures)

    output = {
        "ok": not failures,
        "contract": "postgres_parity_pre_container_v1",
        "sqlite_schema_hash": sha256_text(sqlite_sql),
        "postgres_ddl_hash": sha256_text(postgres_sql),
        "tables": sorted(tables),
        "required_tables": sorted(REQUIRED_TABLES),
        "required_indexes": sorted(required_indexes),
        "placeholder_results": placeholder_results,
        "json_columns_remain_text": sorted(column for column in JSON_TEXT_COLUMNS if column in sqlite_sql),
        "next_proof": "Run a Postgres container smoke against this generated DDL plus the storage-boundary fixture.",
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
