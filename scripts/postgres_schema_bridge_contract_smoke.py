#!/usr/bin/env python3
"""Verify the explicit current-main PostgreSQL schema bridge in isolation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_ROOT = ROOT / "migrations" / "postgres"
BASELINE = MIGRATION_ROOT / "20260724_current_main_commercial_baseline.sql"
V1 = MIGRATION_ROOT / "20260718_human_session_memory_review.sql"
V2 = MIGRATION_ROOT / "20260719_workspace_read_models_v2.sql"
V3 = MIGRATION_ROOT / "20260719_human_approval_decisions_v3.sql"
V4 = MIGRATION_ROOT / "20260719_approval_kind_bindings_v4.sql"
V5 = MIGRATION_ROOT / "20260724_customer_delivery_run_unique_v5.sql"
ORDERED_SQL = (BASELINE, V1, V2, V3, V4, V5)
CONTRACT = "current_main_postgres_schema_bridge_v1"

PLAN_COLUMNS = (
    "plan_id",
    "workspace_id",
    "task_id",
    "run_id",
    "agent_id",
    "task_understanding",
    "referenced_specs_json",
    "referenced_memories_json",
    "referenced_bases_json",
    "proposed_files_to_change_json",
    "risk_level",
    "approval_required",
    "execution_steps_json",
    "verification_plan",
    "rollback_plan",
    "status",
    "plan_version",
    "plan_hash",
    "verified_at",
    "verification_result_hash",
    "approval_id",
    "approved_by_user_id",
    "approved_at",
    "created_at",
    "updated_at",
)


class ContractError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        returncode: int | None = None,
        stdout_hash: str | None = None,
        stderr_hash: str | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.returncode = returncode
        self.stdout_hash = stdout_hash
        self.stderr_hash = stderr_hash


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def quote_identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
        raise ContractError("unsafe_schema_identifier")
    return f'"{value}"'


def psql(
    executable: str,
    dsn: str,
    sql: str,
    *,
    single_transaction: bool = False,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    command = [
        executable,
        "-X",
        "--no-password",
        "--dbname",
        dsn,
        "--set",
        "ON_ERROR_STOP=1",
        "--quiet",
        "--no-align",
        "--tuples-only",
    ]
    if single_transaction:
        command.append("--single-transaction")
    env = os.environ.copy()
    env["PGCONNECT_TIMEOUT"] = "5"
    env["PGAPPNAME"] = "agentops_schema_bridge_contract"
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        input=sql,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def raise_process_error(
    stage: str,
    result: subprocess.CompletedProcess[str],
) -> None:
    raise ContractError(
        f"{stage}_failed",
        returncode=result.returncode,
        stdout_hash=digest(result.stdout or ""),
        stderr_hash=digest(result.stderr or ""),
    )


def execute(
    executable: str,
    dsn: str,
    sql: str,
    *,
    schema: str | None = None,
    single_transaction: bool = False,
    stage: str,
) -> None:
    prefix = ""
    if schema is not None:
        prefix = (
            f"SET search_path TO {quote_identifier(schema)},public;\n"
        )
    result = psql(
        executable,
        dsn,
        prefix + sql,
        single_transaction=single_transaction,
    )
    if result.returncode != 0:
        raise_process_error(stage, result)


def expect_failure(
    executable: str,
    dsn: str,
    sql: str,
    *,
    schema: str,
    marker: str,
    stage: str,
) -> None:
    payload = (
        f"SET search_path TO {quote_identifier(schema)},public;\n"
        + sql
    )
    result = psql(
        executable,
        dsn,
        payload,
        single_transaction=True,
    )
    if result.returncode == 0:
        raise ContractError(f"{stage}_unexpected_success")
    diagnostic = (result.stdout or "") + (result.stderr or "")
    if marker not in diagnostic:
        raise ContractError(
            f"{stage}_unexpected_error",
            returncode=result.returncode,
            stdout_hash=digest(result.stdout or ""),
            stderr_hash=digest(result.stderr or ""),
        )


def query_bool(
    executable: str,
    dsn: str,
    schema: str,
    sql: str,
    *,
    stage: str,
) -> None:
    payload = (
        f"SET search_path TO {quote_identifier(schema)},public;\n"
        + sql.rstrip()
        + "\n"
    )
    result = psql(executable, dsn, payload)
    if result.returncode != 0:
        raise_process_error(stage, result)
    values = [
        line.strip()
        for line in (result.stdout or "").splitlines()
        if line.strip()
    ]
    if values != ["t"]:
        raise ContractError(
            f"{stage}_assertion_failed",
            returncode=result.returncode,
            stdout_hash=digest(result.stdout or ""),
            stderr_hash=digest(result.stderr or ""),
        )


def read_sql(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError(f"sql_artifact_unreadable_{path.name}") from exc


def create_schema(
    executable: str,
    dsn: str,
    schema: str,
) -> None:
    execute(
        executable,
        dsn,
        f"CREATE SCHEMA {quote_identifier(schema)};\n",
        stage="create_isolated_schema",
    )


def drop_schema(
    executable: str,
    dsn: str,
    schema: str,
) -> bool:
    result = psql(
        executable,
        dsn,
        f"DROP SCHEMA IF EXISTS {quote_identifier(schema)} CASCADE;\n",
    )
    return result.returncode == 0


def apply_path(
    executable: str,
    dsn: str,
    schema: str,
    path: Path,
) -> None:
    execute(
        executable,
        dsn,
        read_sql(path),
        schema=schema,
        single_transaction=True,
        stage=f"apply_{path.stem}",
    )


def apply_paths(
    executable: str,
    dsn: str,
    schema: str,
    paths: tuple[Path, ...],
) -> None:
    for path in paths:
        apply_path(executable, dsn, schema, path)


COMMON_GRAPH_SQL = """
INSERT INTO users(user_id,name,email,role,created_at)
VALUES(
  'usr_contract','Contract User','contract@example.invalid',
  'owner','2026-07-24T00:00:00Z'
);

INSERT INTO agents(
  agent_id,name,role,description,runtime_type,model_provider,model_name,
  status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,
  created_at,updated_at
) VALUES(
  'agt_contract','Contract Agent','worker','schema fixture','openclaw',
  'local','fixture','idle','worker','[]',0,'usr_contract',
  '2026-07-24T00:00:00Z','2026-07-24T00:00:00Z'
);

INSERT INTO tasks(
  task_id,workspace_id,title,description,requester_id,owner_agent_id,
  collaborator_agent_ids,status,priority,acceptance_criteria,risk_level,
  budget_limit_usd,created_at,updated_at
) VALUES(
  'tsk_contract','ws_contract','Contract task','schema fixture',
  'usr_contract','agt_contract','[]','running','medium',
  'schema contract','medium',0,
  '2026-07-24T00:00:00Z','2026-07-24T00:00:00Z'
);

INSERT INTO agent_plans(
  plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,
  referenced_specs_json,referenced_memories_json,referenced_bases_json,
  proposed_files_to_change_json,risk_level,approval_required,
  execution_steps_json,verification_plan,rollback_plan,status,plan_version,
  plan_hash,verified_at,verification_result_hash,approval_id,
  approved_by_user_id,approved_at,created_at,updated_at
) VALUES(
  'plan_contract','ws_contract','tsk_contract',NULL,'agt_contract',
  'schema contract','[]','[]','[]','[]','medium',0,
  '["READ","PLAN","RETRIEVE","COMPARE","EXECUTE","VERIFY","RECORD"]',
  'contract verification','drop isolated schema','submitted',1,
  'plan_hash_contract','2026-07-24T00:00:00Z',
  'verification_hash_contract',NULL,NULL,NULL,
  '2026-07-24T00:00:00Z','2026-07-24T00:00:00Z'
);

INSERT INTO runs(
  run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,
  approval_required,agent_plan_id,plan_hash,created_at
) VALUES(
  'run_contract','ws_contract','tsk_contract','agt_contract','openclaw',
  'running','2026-07-24T00:00:00Z',0,'plan_contract',
  'plan_hash_contract','2026-07-24T00:00:00Z'
);

UPDATE agent_plans
SET run_id='run_contract'
WHERE plan_id='plan_contract';
"""


LEGAL_FIXTURE_SQL = (
    COMMON_GRAPH_SQL
    + """
INSERT INTO tool_calls(
  tool_call_id,run_id,agent_id,tool_name,tool_category,
  normalized_args_json,risk_level,status,started_at,created_at
) VALUES
  (
    'tool_contract','run_contract','agt_contract','contract_tool','custom',
    '{}','medium','completed','2026-07-24T00:00:00Z',
    '2026-07-24T00:00:00Z'
  ),
  (
    'tool_prepared_contract','run_contract','agt_contract',
    'prepared_contract_tool','custom','{}','high','waiting_approval',
    '2026-07-24T00:00:00Z','2026-07-24T00:00:00Z'
  );

INSERT INTO approvals(
  approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,
  decision,reason,created_at
) VALUES
  (
    'ap_run_contract','tsk_contract','run_contract',NULL,'agt_contract',
    'pending','run review','2026-07-24T00:00:00Z'
  ),
  (
    'ap_tool_contract','tsk_contract','run_contract','tool_contract',
    'agt_contract','pending','tool review','2026-07-24T00:00:00Z'
  ),
  (
    'ap_prepared_contract','tsk_contract','run_contract',
    'tool_prepared_contract','agt_contract','pending','prepared review',
    '2026-07-24T00:00:00Z'
  ),
  (
    'ap_enrollment_contract','tsk_contract','run_contract',NULL,
    'agt_contract','pending','enrollment review',
    '2026-07-24T00:00:00Z'
  ),
  (
    'ap_delivery_contract','tsk_contract','run_contract',NULL,
    'agt_contract','pending','delivery review',
    '2026-07-24T00:00:00Z'
  );

INSERT INTO prepared_actions(
  action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,
  requested_by_agent_id,action_type,normalized_args_json,target_resource,
  risk_level,policy_version,checkpoint_json,action_hash,idempotency_key,
  status,created_at
) VALUES(
  'act_contract','ws_contract','tsk_contract','run_contract',
  'tool_prepared_contract','ap_prepared_contract','agt_contract',
  'contract.write','{}','contract://resource','high','approval-wall-v1',
  '{}','action_hash_contract','idempotency_contract','prepared',
  '2026-07-24T00:00:00Z'
);

INSERT INTO prepared_action_execution_leases(
  lease_id,action_id,workspace_id,requested_by_agent_id,action_hash,status,
  started_at,expires_at
) VALUES(
  'lease_contract','act_contract','ws_contract','agt_contract',
  'action_hash_contract','executing','2026-07-24T00:00:00Z',
  '2026-07-24T00:05:00Z'
);

INSERT INTO agent_gateway_enrollment_requests(
  request_id,approval_id,task_id,run_id,workspace_id,agent_id,name,role,
  runtime_type,scopes_json,reason,status,created_at,updated_at
) VALUES(
  'enroll_contract','ap_enrollment_contract','tsk_contract','run_contract',
  'ws_contract','agt_contract','Contract Agent','worker','openclaw','[]',
  'contract enrollment','pending','2026-07-24T00:00:00Z',
  '2026-07-24T00:00:00Z'
);

INSERT INTO evaluations(
  evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,
  rubric_json,notes,created_at
) VALUES(
  'eval_contract','tsk_contract','run_contract','agt_contract','rule',1,
  'pass','{}','contract evaluation','2026-07-24T00:00:00Z'
);

INSERT INTO artifacts(
  artifact_id,task_id,run_id,artifact_type,title,summary,content_hash,
  created_at
) VALUES(
  'art_contract','tsk_contract','run_contract','contract','Contract artifact',
  'bounded fixture','artifact_hash_contract','2026-07-24T00:00:00Z'
);

INSERT INTO runtime_connectors(
  runtime_connector_id,provider,connector_type,profile_name,status,
  allow_real_run,require_confirm_run,trust_status,observation_level,
  capability_manifest_json,created_at,updated_at
) VALUES(
  'runtime_contract','openclaw','local','contract','ready',0,1,'trusted',
  'ledger_summary_only','{}','2026-07-24T00:00:00Z',
  '2026-07-24T00:00:00Z'
);

INSERT INTO runtime_events(
  runtime_event_id,runtime_connector_id,event_type,status,run_id,task_id,
  agent_id,prompt_hash,input_summary,output_summary,raw_payload_hash,
  created_at
) VALUES(
  'event_contract','runtime_contract','contract','completed','run_contract',
  'tsk_contract','agt_contract','prompt_hash_contract','bounded input',
  'bounded output','payload_hash_contract','2026-07-24T00:00:00Z'
);

INSERT INTO plan_evidence_manifests(
  manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,
  expected_steps_json,tool_call_ids_json,evaluation_ids_json,
  artifact_ids_json,audit_ids_json,plan_hash,verification_result_hash,
  status,verification_json,created_at,updated_at
) VALUES(
  'manifest_contract','ws_contract','plan_contract','tsk_contract',
  'run_contract','agt_contract','block','[]','[]','[]','[]','[]',
  'plan_hash_contract','verification_hash_contract','verified','{}',
  '2026-07-24T00:00:00Z','2026-07-24T00:00:00Z'
);

INSERT INTO audit_logs(
  audit_id,actor_type,actor_id,action,entity_type,entity_id,metadata_json,
  created_at,workspace_id
) VALUES
  (
    'audit_run_contract','agent','agt_contract',
    'agent_gateway.approval_request','approvals','ap_run_contract',
    '{"workspace_id":"ws_contract"}','2026-07-24T00:00:00Z',
    'ws_contract'
  ),
  (
    'audit_delivery_contract','agent','agt_contract',
    'workflow.customer_worker_task.delivery_approval','approvals',
    'ap_delivery_contract','{"workspace_id":"ws_contract"}',
    '2026-07-24T00:00:00Z','ws_contract'
  );
"""
)


AMBIGUOUS_FIXTURE_SQL = (
    COMMON_GRAPH_SQL
    + """
INSERT INTO tool_calls(
  tool_call_id,run_id,agent_id,tool_name,tool_category,
  normalized_args_json,risk_level,status,started_at,created_at
) VALUES(
  'tool_ambiguous','run_contract','agt_contract','ambiguous_tool','custom',
  '{}','high','waiting_approval','2026-07-24T00:00:00Z',
  '2026-07-24T00:00:00Z'
);

INSERT INTO approvals(
  approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,
  decision,reason,created_at
) VALUES(
  'ap_ambiguous','tsk_contract','run_contract','tool_ambiguous',
  'agt_contract','pending','ambiguous legacy binding',
  '2026-07-24T00:00:00Z'
);

INSERT INTO prepared_actions(
  action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,
  requested_by_agent_id,action_type,normalized_args_json,risk_level,
  checkpoint_json,action_hash,idempotency_key,status,created_at
) VALUES(
  'act_ambiguous','ws_contract','tsk_contract','run_contract',
  'tool_ambiguous','ap_ambiguous','agt_contract','contract.write','{}',
  'high','{}','ambiguous_action_hash','ambiguous_idempotency','prepared',
  '2026-07-24T00:00:00Z'
);

INSERT INTO agent_gateway_enrollment_requests(
  request_id,approval_id,task_id,run_id,workspace_id,agent_id,name,
  runtime_type,scopes_json,status,created_at,updated_at
) VALUES(
  'enroll_ambiguous','ap_ambiguous','tsk_contract','run_contract',
  'ws_contract','agt_contract','Contract Agent','openclaw','[]','pending',
  '2026-07-24T00:00:00Z','2026-07-24T00:00:00Z'
);
"""
)


DUPLICATE_DELIVERY_FIXTURE_SQL = (
    COMMON_GRAPH_SQL
    + """
INSERT INTO approvals(
  approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,
  decision,reason,created_at
) VALUES
  (
    'ap_delivery_one','tsk_contract','run_contract',NULL,'agt_contract',
    'pending','delivery review one','2026-07-24T00:00:00Z'
  ),
  (
    'ap_delivery_two','tsk_contract','run_contract',NULL,'agt_contract',
    'pending','delivery review two','2026-07-24T00:00:00Z'
  );

INSERT INTO audit_logs(
  audit_id,actor_type,actor_id,action,entity_type,entity_id,metadata_json,
  created_at,workspace_id
) VALUES
  (
    'audit_delivery_one','agent','agt_contract',
    'workflow.customer_worker_task.delivery_approval','approvals',
    'ap_delivery_one','{"workspace_id":"ws_contract"}',
    '2026-07-24T00:00:00Z','ws_contract'
  ),
  (
    'audit_delivery_two','agent','agt_contract',
    'workflow.customer_worker_task.delivery_approval','approvals',
    'ap_delivery_two','{"workspace_id":"ws_contract"}',
    '2026-07-24T00:00:00Z','ws_contract'
  );
"""
)


def verify_structure(
    executable: str,
    dsn: str,
    schema: str,
) -> None:
    required_tables = (
        "users",
        "agents",
        "tasks",
        "agent_plans",
        "runs",
        "tool_calls",
        "approvals",
        "prepared_actions",
        "prepared_action_execution_leases",
        "memories",
        "evaluations",
        "artifacts",
        "audit_logs",
        "runtime_connectors",
        "runtime_events",
        "agent_gateway_tokens",
        "agent_gateway_sessions",
        "agent_gateway_enrollment_requests",
        "plan_evidence_manifests",
        "workspace_memberships",
        "human_login_credentials",
        "human_sessions",
        "human_login_throttle",
        "human_memory_review_requests",
        "human_approval_decision_requests",
    )
    table_literals = ",".join(f"'{name}'" for name in required_tables)
    query_bool(
        executable,
        dsn,
        schema,
        f"""
SELECT COUNT(*)={len(required_tables)}
FROM information_schema.tables
WHERE table_schema=current_schema()
  AND table_name IN ({table_literals});
""",
        stage="required_tables",
    )

    plan_literals = ",".join(f"'{name}'" for name in PLAN_COLUMNS)
    query_bool(
        executable,
        dsn,
        schema,
        f"""
SELECT array_agg(column_name::text ORDER BY ordinal_position)
  =ARRAY[{plan_literals}]::text[]
FROM information_schema.columns
WHERE table_schema=current_schema()
  AND table_name='agent_plans';
""",
        stage="current_agent_plan_columns",
    )

    query_bool(
        executable,
        dsn,
        schema,
        """
SELECT
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='prepared_actions'
      AND column_name='action_id'
  )
  AND NOT EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='prepared_actions'
      AND column_name='prepared_action_id'
  )
  AND EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='prepared_action_execution_leases'
      AND column_name='action_id'
  )
  AND EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='runs'
      AND column_name='agent_plan_id'
  )
  AND EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='runs'
      AND column_name='plan_hash'
  );
""",
        stage="current_main_identity_columns",
    )

    query_bool(
        executable,
        dsn,
        schema,
        """
SELECT COUNT(*)=9
FROM information_schema.columns
WHERE table_schema=current_schema()
  AND column_name='workspace_id'
  AND table_name IN (
    'tasks','runs','prepared_actions',
    'prepared_action_execution_leases','agent_plans',
    'plan_evidence_manifests','agent_gateway_tokens',
    'agent_gateway_sessions','agent_gateway_enrollment_requests'
  );
""",
        stage="workspace_binding_columns",
    )

    query_bool(
        executable,
        dsn,
        schema,
        """
SELECT COUNT(*)=9
FROM pg_constraint
WHERE connamespace=current_schema()::regnamespace
  AND conname IN (
    'prepared_actions_pkey',
    'prepared_action_execution_leases_action_id_key',
    'prepared_action_execution_leases_action_id_fkey',
    'runs_agent_plan_id_fkey',
    'agent_plans_run_id_fkey',
    'agent_gateway_enrollment_requests_approval_id_fkey',
    'agent_gateway_enrollment_requests_task_id_fkey',
    'agent_gateway_enrollment_requests_run_id_fkey',
    'agent_gateway_enrollment_requests_token_id_fkey'
  );
""",
        stage="authority_graph_constraints",
    )

    query_bool(
        executable,
        dsn,
        schema,
        """
SELECT COUNT(*)=3 AND bool_and(
  trigger_record.tgdeferrable
  AND trigger_record.tginitdeferred
)
FROM pg_trigger trigger_record
JOIN pg_class relation
  ON relation.oid=trigger_record.tgrelid
JOIN pg_namespace namespace
  ON namespace.oid=relation.relnamespace
WHERE namespace.nspname=current_schema()
  AND NOT trigger_record.tgisinternal
  AND trigger_record.tgname IN (
    'approvals_kind_binding_enforced',
    'prepared_actions_kind_binding_enforced',
    'enrollment_requests_kind_binding_enforced'
  );
""",
        stage="deferred_approval_binding_triggers",
    )

    query_bool(
        executable,
        dsn,
        schema,
        """
SELECT
  index_record.indisunique
  AND pg_get_expr(
    index_record.indpred,index_record.indrelid,true
  )='approval_kind = ''customer_delivery''::text'
FROM pg_index index_record
JOIN pg_class index_relation
  ON index_relation.oid=index_record.indexrelid
JOIN pg_namespace namespace
  ON namespace.oid=index_relation.relnamespace
WHERE namespace.nspname=current_schema()
  AND index_relation.relname=
    'idx_approvals_customer_delivery_run_unique';
""",
        stage="customer_delivery_partial_unique_index",
    )

    query_bool(
        executable,
        dsn,
        schema,
        """
SELECT
  COUNT(*)=5
  AND COUNT(DISTINCT approval_kind)=5
  AND bool_and(
    approval_kind IN (
      'run_execution','tool_execution','prepared_action',
      'agent_enrollment','customer_delivery'
    )
  )
FROM approvals;
""",
        stage="approval_kind_backfill",
    )

    query_bool(
        executable,
        dsn,
        schema,
        """
SELECT COUNT(*)=1
FROM prepared_actions action
JOIN prepared_action_execution_leases lease
  ON lease.action_id=action.action_id
  AND lease.workspace_id=action.workspace_id
  AND lease.requested_by_agent_id=action.requested_by_agent_id
  AND lease.action_hash=action.action_hash
JOIN approvals approval
  ON approval.approval_id=action.approval_id
  AND approval.approval_kind='prepared_action'
  AND approval.run_id=action.run_id
  AND approval.task_id=action.task_id;
""",
        stage="prepared_action_lease_binding",
    )

    query_bool(
        executable,
        dsn,
        schema,
        """
SELECT COUNT(*)=1
FROM agent_gateway_enrollment_requests request
JOIN approvals approval
  ON approval.approval_id=request.approval_id
  AND approval.approval_kind='agent_enrollment'
  AND approval.task_id=request.task_id
  AND approval.run_id=request.run_id
JOIN runs run
  ON run.run_id=request.run_id
  AND run.workspace_id=request.workspace_id
  AND run.agent_id=request.agent_id;
""",
        stage="enrollment_request_binding",
    )


def run_contract(executable: str, dsn: str) -> dict[str, bool | int]:
    suffix = secrets.token_hex(5)
    schemas = [
        f"agentops_bridge_fresh_{suffix}",
        f"agentops_bridge_ambiguous_{suffix}",
        f"agentops_bridge_duplicate_{suffix}",
    ]
    created: list[str] = []
    cleaned = 0
    checks: dict[str, bool | int] = {
        "fresh_bootstrap": False,
        "idempotent_reapply": False,
        "current_main_contract": False,
        "v4_ambiguous_backfill_rollback": False,
        "v5_existing_duplicate_rollback": False,
        "v5_new_duplicate_rejection": False,
        "raw_rows_emitted": False,
        "secrets_emitted": False,
    }
    try:
        for schema in schemas:
            create_schema(executable, dsn, schema)
            created.append(schema)

        fresh, ambiguous, duplicate = schemas
        apply_paths(executable, dsn, fresh, (BASELINE, V1, V2, V3))
        execute(
            executable,
            dsn,
            LEGAL_FIXTURE_SQL,
            schema=fresh,
            single_transaction=True,
            stage="seed_legal_fixture",
        )
        apply_paths(executable, dsn, fresh, (V4, V5))
        checks["fresh_bootstrap"] = True
        verify_structure(executable, dsn, fresh)
        checks["current_main_contract"] = True

        apply_paths(executable, dsn, fresh, ORDERED_SQL)
        verify_structure(executable, dsn, fresh)
        checks["idempotent_reapply"] = True

        expect_failure(
            executable,
            dsn,
            """
INSERT INTO approvals(
  approval_id,approval_kind,task_id,run_id,tool_call_id,
  requested_by_agent_id,decision,reason,created_at
) VALUES(
  'ap_delivery_duplicate_new','customer_delivery','tsk_contract',
  'run_contract',NULL,'agt_contract','pending','duplicate contract',
  '2026-07-24T00:00:00Z'
);
""",
            schema=fresh,
            marker="idx_approvals_customer_delivery_run_unique",
            stage="v5_new_duplicate",
        )
        query_bool(
            executable,
            dsn,
            fresh,
            """
SELECT COUNT(*)=1
FROM approvals
WHERE approval_kind='customer_delivery';
""",
            stage="v5_new_duplicate_rolled_back",
        )
        checks["v5_new_duplicate_rejection"] = True

        apply_paths(
            executable,
            dsn,
            ambiguous,
            (BASELINE, V1, V2, V3),
        )
        execute(
            executable,
            dsn,
            AMBIGUOUS_FIXTURE_SQL,
            schema=ambiguous,
            single_transaction=True,
            stage="seed_ambiguous_fixture",
        )
        expect_failure(
            executable,
            dsn,
            read_sql(V4),
            schema=ambiguous,
            marker="approval_kind_backfill_ambiguous",
            stage="v4_ambiguous_backfill",
        )
        query_bool(
            executable,
            dsn,
            ambiguous,
            """
SELECT NOT EXISTS(
  SELECT 1
  FROM information_schema.columns
  WHERE table_schema=current_schema()
    AND table_name='approvals'
    AND column_name='approval_kind'
);
""",
            stage="v4_ambiguous_column_rollback",
        )
        checks["v4_ambiguous_backfill_rollback"] = True

        apply_paths(
            executable,
            dsn,
            duplicate,
            (BASELINE, V1, V2, V3),
        )
        execute(
            executable,
            dsn,
            DUPLICATE_DELIVERY_FIXTURE_SQL,
            schema=duplicate,
            single_transaction=True,
            stage="seed_duplicate_delivery_fixture",
        )
        apply_path(executable, dsn, duplicate, V4)
        expect_failure(
            executable,
            dsn,
            read_sql(V5),
            schema=duplicate,
            marker="customer_delivery_approval_run_duplicate",
            stage="v5_existing_duplicate",
        )
        query_bool(
            executable,
            dsn,
            duplicate,
            """
SELECT
  COUNT(*)=2
  AND NOT EXISTS(
    SELECT 1
    FROM pg_class relation
    JOIN pg_namespace namespace
      ON namespace.oid=relation.relnamespace
    WHERE namespace.nspname=current_schema()
      AND relation.relname=
        'idx_approvals_customer_delivery_run_unique'
  )
FROM approvals
WHERE approval_kind='customer_delivery';
""",
            stage="v5_existing_duplicate_rollback",
        )
        checks["v5_existing_duplicate_rollback"] = True
        return checks
    finally:
        for schema in reversed(created):
            if drop_schema(executable, dsn, schema):
                cleaned += 1
        checks["isolated_schemas_created"] = len(created)
        checks["isolated_schemas_cleaned"] = cleaned
        if cleaned != len(created) and sys.exc_info()[0] is None:
            raise ContractError("isolated_schema_cleanup_failed")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the explicit current-main PostgreSQL schema bridge "
            "inside disposable schemas."
        )
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.environ.get("AGENTOPS_POSTGRES_DSN"),
        help=(
            "PostgreSQL DSN. The value is never included in smoke output; "
            "AGENTOPS_POSTGRES_DSN is used when omitted."
        ),
    )
    args = parser.parse_args()
    if not args.postgres_dsn:
        print(
            json.dumps(
                {
                    "contract": CONTRACT,
                    "error_code": "postgres_dsn_required",
                    "ok": False,
                },
                sort_keys=True,
            )
        )
        return 2

    executable = shutil.which("psql")
    if executable is None:
        print(
            json.dumps(
                {
                    "contract": CONTRACT,
                    "error_code": "psql_unavailable",
                    "ok": False,
                },
                sort_keys=True,
            )
        )
        return 2

    missing = [path.name for path in ORDERED_SQL if not path.is_file()]
    if missing:
        print(
            json.dumps(
                {
                    "contract": CONTRACT,
                    "error_code": "sql_artifact_missing",
                    "missing_count": len(missing),
                    "ok": False,
                },
                sort_keys=True,
            )
        )
        return 2

    try:
        checks = run_contract(executable, args.postgres_dsn)
    except ContractError as exc:
        payload: dict[str, object] = {
            "contract": CONTRACT,
            "error_code": exc.code,
            "ok": False,
            "raw_rows_emitted": False,
            "secrets_emitted": False,
        }
        if exc.returncode is not None:
            payload["process_exit_code"] = exc.returncode
        if exc.stdout_hash is not None:
            payload["stdout_sha256"] = exc.stdout_hash
        if exc.stderr_hash is not None:
            payload["stderr_sha256"] = exc.stderr_hash
        print(json.dumps(payload, sort_keys=True))
        return 1
    except subprocess.TimeoutExpired as exc:
        print(
            json.dumps(
                {
                    "contract": CONTRACT,
                    "error_code": "psql_timeout",
                    "ok": False,
                    "timeout_seconds": exc.timeout,
                    "raw_rows_emitted": False,
                    "secrets_emitted": False,
                },
                sort_keys=True,
            )
        )
        return 1

    print(
        json.dumps(
            {
                "checks": checks,
                "contract": CONTRACT,
                "migration_artifact_count": len(ORDERED_SQL),
                "ok": all(
                    value is True
                    for key, value in checks.items()
                    if key
                    not in {
                        "isolated_schemas_created",
                        "isolated_schemas_cleaned",
                        "raw_rows_emitted",
                        "secrets_emitted",
                    }
                )
                and checks["isolated_schemas_created"]
                == checks["isolated_schemas_cleaned"]
                and checks["raw_rows_emitted"] is False
                and checks["secrets_emitted"] is False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
