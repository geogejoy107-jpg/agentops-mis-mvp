#!/usr/bin/env python3
"""Verify the fresh-main PreparedAction lease v6 on real PostgreSQL."""
from __future__ import annotations

import argparse
import concurrent.futures
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
V6 = MIGRATION_ROOT / "20260724_prepared_action_execution_leases_v6.sql"
PRE_V6 = (BASELINE, V1, V2, V3, V4, V5)
ORDERED_SQL = (*PRE_V6, V6)
CONTRACT = "postgres_prepared_action_execution_lease_v6"


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
    env["PGAPPNAME"] = "agentops_prepared_action_lease_v6_contract"
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


def process_error(
    stage: str,
    result: subprocess.CompletedProcess[str],
) -> ContractError:
    return ContractError(
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
) -> subprocess.CompletedProcess[str]:
    prefix = ""
    if schema is not None:
        prefix = f"SET search_path TO {quote_identifier(schema)},public;\n"
    result = psql(
        executable,
        dsn,
        prefix + sql,
        single_transaction=single_transaction,
    )
    if result.returncode != 0:
        raise process_error(stage, result)
    return result


def expect_failure(
    executable: str,
    dsn: str,
    sql: str,
    *,
    schema: str,
    stage: str,
    marker: str | None = None,
) -> None:
    result = psql(
        executable,
        dsn,
        f"SET search_path TO {quote_identifier(schema)},public;\n{sql}",
        single_transaction=True,
    )
    if result.returncode == 0:
        raise ContractError(f"{stage}_unexpected_success")
    if marker is not None:
        diagnostic = (result.stdout or "") + (result.stderr or "")
        if marker not in diagnostic:
            raise ContractError(
                f"{stage}_unexpected_error",
                returncode=result.returncode,
                stdout_hash=digest(result.stdout or ""),
                stderr_hash=digest(result.stderr or ""),
            )


def query_value(
    executable: str,
    dsn: str,
    schema: str,
    sql: str,
    *,
    stage: str,
) -> str:
    result = execute(
        executable,
        dsn,
        sql,
        schema=schema,
        stage=stage,
    )
    values = [
        line.strip()
        for line in (result.stdout or "").splitlines()
        if line.strip()
    ]
    if len(values) != 1:
        raise ContractError(
            f"{stage}_result_shape_invalid",
            stdout_hash=digest(result.stdout or ""),
            stderr_hash=digest(result.stderr or ""),
        )
    return values[0]


def expect_true(
    executable: str,
    dsn: str,
    schema: str,
    sql: str,
    *,
    stage: str,
) -> None:
    if query_value(executable, dsn, schema, sql, stage=stage) != "t":
        raise ContractError(f"{stage}_assertion_failed")


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
        stage="create_disposable_schema",
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


def graph_sql(
    label: str,
    *,
    action_status: str = "approved",
    principal_label: str | None = None,
) -> str:
    principal = principal_label or label
    action_hash = digest(f"action:{label}")
    approved_at = "'2026-07-24T00:01:00Z'"
    consumed_at = "NULL"
    side_effect = "NULL"
    if action_status == "consumed":
        consumed_at = "'2026-07-24T00:10:00Z'"
        side_effect = f"'provider_ref_sha256_{digest(f'side-effect:{label}')[:24]}'"
    principal_sql = ""
    if principal_label is None:
        principal_sql = f"""
INSERT INTO users(user_id,name,email,role,created_at)
VALUES(
  'usr_{principal}','Contract User {principal}',
  '{principal}@example.invalid','owner','2026-07-24T00:00:00Z'
);
INSERT INTO agents(
  agent_id,name,role,runtime_type,status,permission_level,allowed_tools,
  owner_user_id,created_at,updated_at
) VALUES(
  'agt_{principal}','Contract Agent {principal}','worker','codex','idle',
  'worker','[]','usr_{principal}','2026-07-24T00:00:00Z',
  '2026-07-24T00:00:00Z'
);
"""
    return f"""
BEGIN;
{principal_sql}
INSERT INTO tasks(
  task_id,workspace_id,title,requester_id,owner_agent_id,status,priority,
  risk_level,created_at,updated_at
) VALUES(
  'tsk_{label}','ws_contract','Contract task {label}','usr_{principal}',
  'agt_{principal}','waiting_approval','medium','high',
  '2026-07-24T00:00:00Z','2026-07-24T00:00:00Z'
);
INSERT INTO runs(
  run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,
  approval_required,created_at
) VALUES(
  'run_{label}','ws_contract','tsk_{label}','agt_{principal}','codex',
  'waiting_approval','2026-07-24T00:00:00Z',1,
  '2026-07-24T00:00:00Z'
);
INSERT INTO tool_calls(
  tool_call_id,run_id,agent_id,tool_name,tool_category,
  normalized_args_json,risk_level,status,started_at,created_at
) VALUES(
  'tool_{label}','run_{label}','agt_{principal}',
  'agent_worker.codex.workspace_write','custom','{{}}','high',
  'waiting_approval','2026-07-24T00:00:00Z',
  '2026-07-24T00:00:00Z'
);
INSERT INTO approvals(
  approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,
  approver_user_id,decision,reason,created_at,decided_at,approval_kind
) VALUES(
  'ap_{label}','tsk_{label}','run_{label}','tool_{label}',
  'agt_{principal}','usr_{principal}','approved','bounded contract approval',
  '2026-07-24T00:00:00Z','2026-07-24T00:01:00Z','prepared_action'
);
INSERT INTO prepared_actions(
  action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,
  requested_by_agent_id,action_type,normalized_args_json,target_resource,
  risk_level,policy_version,checkpoint_json,action_hash,idempotency_key,
  status,provider_side_effect_id,result_summary,created_at,approved_at,
  consumed_at,expires_at
) VALUES(
  'act_{label}','ws_contract','tsk_{label}','run_{label}','tool_{label}',
  'ap_{label}','agt_{principal}','agent_worker.codex.workspace_write',
  '{{"request_hash":"{digest(f"args:{label}")}"}}',
  'git+local://sha256/{digest(f"target:{label}")}',
  'high','approval-wall-codex-workspace-write-v2',
  '{{"checkpoint_hash":"{digest(f"checkpoint:{label}")}"}}',
  '{action_hash}','idem_{label}','{action_status}',{side_effect},
  'bounded terminal summary; provider content omitted',
  '2026-07-24T00:00:00Z',{approved_at},{consumed_at},
  '2026-07-26T00:00:00Z'
);
COMMIT;
"""


def legacy_lease_sql(label: str, status: str) -> str:
    completed_at = "NULL"
    failure_reason = "NULL"
    if status == "completed":
        completed_at = "'2026-07-24T00:10:00Z'"
    elif status == "failed":
        completed_at = "'2026-07-24T00:25:00Z'"
        failure_reason = "'Execution closure unknown; provider output omitted.'"
    return f"""
INSERT INTO prepared_action_execution_leases(
  lease_id,action_id,workspace_id,requested_by_agent_id,action_hash,status,
  started_at,expires_at,completed_at,failure_reason
) VALUES(
  'lease_{label}','act_{label}','ws_contract','agt_{label}',
  '{digest(f"action:{label}")}','{status}','2026-07-24T00:02:00Z',
  '2026-07-24T00:20:00Z',{completed_at},{failure_reason}
);
"""


def claim_sql(
    label: str,
    lease_id: str,
    *,
    principal_label: str | None = None,
    action_hash: str | None = None,
    claim_request_hash: str | None = None,
    claim_idempotency_hash: str | None = None,
    started_at: str = "2026-07-24T00:02:00Z",
    expires_at: str = "2026-07-24T00:20:00Z",
) -> str:
    principal = principal_label or label
    stored_action_hash = action_hash or digest(f"action:{label}")
    request_hash = claim_request_hash or digest(f"claim-request:{label}")
    idempotency_hash = (
        claim_idempotency_hash or digest(f"claim-idempotency:{label}")
    )
    return f"""
INSERT INTO prepared_action_execution_leases(
  lease_id,action_id,workspace_id,requested_by_agent_id,action_hash,
  status,started_at,expires_at,completed_at,failure_reason,
  claim_request_hash,claim_idempotency_hash,claim_identity_source
) VALUES(
  '{lease_id}','act_{label}','ws_contract','agt_{principal}',
  '{stored_action_hash}','executing','{started_at}','{expires_at}',NULL,NULL,
  '{request_hash}','{idempotency_hash}','request_hash_v1'
)
ON CONFLICT DO NOTHING
RETURNING lease_id;
"""


def receipt_sql(
    label: str,
    lease_id: str,
    outcome: str,
    *,
    automatic_retry_allowed: bool = False,
) -> str:
    provider_performed = outcome in {"succeeded", "failed"}
    may_have_completed = outcome == "unknown"
    evidence_hash = (
        f"'{digest(f'terminal-evidence:{label}:{outcome}')}'"
        if outcome != "unknown"
        else "NULL"
    )
    source = {
        "succeeded": "worker_verified_v1",
        "failed": "control_plane_failure_v1",
        "unknown": "control_plane_timeout_v1",
    }[outcome]
    terminal_at = (
        "2026-07-24T00:25:00Z"
        if outcome == "unknown"
        else "2026-07-24T00:10:00Z"
    )
    return f"""
INSERT INTO prepared_action_execution_receipts(
  receipt_id,lease_id,action_id,workspace_id,requested_by_agent_id,
  action_hash,claim_request_hash,claim_idempotency_hash,
  receipt_request_hash,outcome,provider_call_performed,
  provider_call_may_have_completed,terminal_evidence_hash,
  terminal_evidence_source,terminal_evidence_verified,
  automatic_retry_allowed,retry_requires_new_action,
  raw_provider_output_omitted,raw_prompt_omitted,raw_response_omitted,
  token_omitted,terminal_at
) VALUES(
  'receipt_{label}','{lease_id}','act_{label}','ws_contract','agt_{label}',
  '{digest(f"action:{label}")}','{digest(f"claim-request:{label}")}',
  '{digest(f"claim-idempotency:{label}")}',
  '{digest(f"receipt-request:{label}:{outcome}")}','{outcome}',
  {str(provider_performed).upper()},{str(may_have_completed).upper()},
  {evidence_hash},'{source}',FALSE,
  {str(automatic_retry_allowed).upper()},TRUE,TRUE,TRUE,TRUE,TRUE,
  '{terminal_at}'
);
"""


def terminal_sql(label: str, lease_id: str, outcome: str) -> str:
    if outcome == "succeeded":
        action_update = f"""
UPDATE prepared_actions
SET status='consumed',consumed_at='2026-07-24T00:10:00Z',
  provider_side_effect_id='provider_ref_sha256_{digest(f"side-effect:{label}")[:24]}',
  result_summary='Verified provider receipt recorded; content omitted.'
WHERE action_id='act_{label}';
"""
        lease_update = f"""
UPDATE prepared_action_execution_leases
SET status='completed',completed_at='2026-07-24T00:10:00Z'
WHERE lease_id='{lease_id}';
"""
    else:
        terminal_at = (
            "2026-07-24T00:25:00Z"
            if outcome == "unknown"
            else "2026-07-24T00:10:00Z"
        )
        reason = (
            "Execution lease expired; provider may have completed."
            if outcome == "unknown"
            else "Provider reported a bounded failure before side effect."
        )
        action_update = f"""
UPDATE prepared_actions
SET status='expired',result_summary='{reason}'
WHERE action_id='act_{label}';
"""
        lease_update = f"""
UPDATE prepared_action_execution_leases
SET status='failed',completed_at='{terminal_at}',
  failure_reason='{reason}'
WHERE lease_id='{lease_id}';
"""
    return (
        "BEGIN;\n"
        + action_update
        + lease_update
        + receipt_sql(label, lease_id, outcome)
        + "COMMIT;\n"
    )


def run_upgrade_contract(
    executable: str,
    dsn: str,
    schema: str,
) -> dict[str, bool]:
    apply_paths(executable, dsn, schema, PRE_V6)
    execute(
        executable,
        dsn,
        graph_sql("legacy_executing"),
        schema=schema,
        stage="seed_legacy_executing",
    )
    execute(
        executable,
        dsn,
        graph_sql("legacy_completed", action_status="consumed"),
        schema=schema,
        stage="seed_legacy_completed",
    )
    execute(
        executable,
        dsn,
        graph_sql("legacy_failed", action_status="expired"),
        schema=schema,
        stage="seed_legacy_failed",
    )
    execute(
        executable,
        dsn,
        legacy_lease_sql("legacy_executing", "executing")
        + legacy_lease_sql("legacy_completed", "completed")
        + legacy_lease_sql("legacy_failed", "failed"),
        schema=schema,
        single_transaction=True,
        stage="seed_legacy_leases",
    )
    apply_path(executable, dsn, schema, V6)
    apply_path(executable, dsn, schema, V6)

    expect_true(
        executable,
        dsn,
        schema,
        """
SELECT
  (SELECT COUNT(*)=3 FROM prepared_actions WHERE action_id LIKE 'act_legacy_%')
  AND
  (SELECT COUNT(*)=3 FROM prepared_action_execution_leases
   WHERE action_id LIKE 'act_legacy_%')
  AND
  (SELECT COUNT(*)=2 FROM prepared_action_execution_receipts
   WHERE action_id LIKE 'act_legacy_%');
""",
        stage="legacy_rows_preserved",
    )
    expect_true(
        executable,
        dsn,
        schema,
        """
SELECT bool_and(
  claim_request_hash=action_hash
  AND claim_idempotency_hash=action_hash
  AND claim_identity_source='legacy_action_hash_backfill_v1'
)
FROM prepared_action_execution_leases
WHERE action_id LIKE 'act_legacy_%';
""",
        stage="legacy_claim_identity_backfilled",
    )
    expect_true(
        executable,
        dsn,
        schema,
        """
SELECT
  COUNT(*) FILTER(WHERE outcome='succeeded')=1
  AND COUNT(*) FILTER(WHERE outcome='unknown')=1
  AND bool_and(automatic_retry_allowed=FALSE)
  AND bool_and(retry_requires_new_action=TRUE)
FROM prepared_action_execution_receipts
WHERE action_id LIKE 'act_legacy_%';
""",
        stage="legacy_terminal_receipts_backfilled",
    )
    return {
        "baseline_v1_v5_v6_upgrade": True,
        "existing_legal_rows_preserved": True,
        "legacy_claim_identity_backfilled": True,
        "legacy_terminal_receipts_backfilled": True,
        "migration_repeat_safe": True,
    }


def run_ambiguous_rollback_contract(
    executable: str,
    dsn: str,
    schema: str,
) -> dict[str, bool]:
    apply_paths(executable, dsn, schema, PRE_V6)
    execute(
        executable,
        dsn,
        graph_sql("ambiguous"),
        schema=schema,
        stage="seed_ambiguous_graph",
    )
    execute(
        executable,
        dsn,
        f"""
INSERT INTO prepared_action_execution_leases(
  lease_id,action_id,workspace_id,requested_by_agent_id,action_hash,status,
  started_at,expires_at
) VALUES(
  'lease_ambiguous','act_ambiguous','ws_wrong','agt_ambiguous',
  '{digest("action:ambiguous")}','executing','2026-07-24T00:02:00Z',
  '2026-07-24T00:20:00Z'
);
""",
        schema=schema,
        stage="seed_ambiguous_lease",
    )
    expect_failure(
        executable,
        dsn,
        read_sql(V6),
        schema=schema,
        stage="ambiguous_upgrade",
        marker="prepared_action_execution_lease_binding_invalid",
    )
    expect_true(
        executable,
        dsn,
        schema,
        """
SELECT
  NOT EXISTS(
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='prepared_action_execution_leases'
      AND column_name='claim_request_hash'
  )
  AND to_regclass(
    current_schema() || '.prepared_action_execution_receipts'
  ) IS NULL
  AND (
    SELECT COUNT(*)=1
    FROM prepared_action_execution_leases
    WHERE lease_id='lease_ambiguous'
  );
""",
        stage="ambiguous_upgrade_rolled_back",
    )
    return {
        "ambiguous_history_fails_closed": True,
        "ambiguous_upgrade_transaction_rolled_back": True,
    }


def concurrent_claims(
    executable: str,
    dsn: str,
    schema: str,
    label: str,
    count: int,
) -> list[str]:
    def contender(index: int) -> subprocess.CompletedProcess[str]:
        return psql(
            executable,
            dsn,
            f"SET search_path TO {quote_identifier(schema)},public;\n"
            + claim_sql(label, f"lease_{label}_{index}"),
            single_transaction=True,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
        results = list(executor.map(contender, range(count)))
    for result in results:
        if result.returncode != 0:
            raise process_error("concurrent_claim", result)
    return [
        result.stdout.strip()
        for result in results
        if (result.stdout or "").strip()
    ]


def run_fresh_contract(
    executable: str,
    dsn: str,
    schema: str,
) -> dict[str, bool]:
    apply_paths(executable, dsn, schema, ORDERED_SQL)
    apply_path(executable, dsn, schema, V6)

    for label in (
        "concurrent",
        "wrong_binding",
        "success",
        "failure",
        "unknown",
        "receipt_required",
        "retry_guard",
    ):
        execute(
            executable,
            dsn,
            graph_sql(label),
            schema=schema,
            stage=f"seed_{label}_graph",
        )
    execute(
        executable,
        dsn,
        graph_sql("idempotency_guard", principal_label="concurrent"),
        schema=schema,
        stage="seed_idempotency_guard_graph",
    )

    winners = concurrent_claims(
        executable,
        dsn,
        schema,
        "concurrent",
        8,
    )
    if len(winners) != 1:
        raise ContractError("concurrent_claim_single_winner_failed")
    winning_lease = winners[0]
    expect_true(
        executable,
        dsn,
        schema,
        """
SELECT COUNT(*)=1
FROM prepared_action_execution_leases
WHERE action_id='act_concurrent';
""",
        stage="concurrent_claim_count",
    )

    replay = execute(
        executable,
        dsn,
        claim_sql("concurrent", winning_lease),
        schema=schema,
        single_transaction=True,
        stage="claim_exact_replay",
    )
    if (replay.stdout or "").strip():
        raise ContractError("claim_exact_replay_created_duplicate")
    expect_true(
        executable,
        dsn,
        schema,
        f"""
SELECT
  lease_id='{winning_lease}'
  AND action_hash='{digest("action:concurrent")}'
  AND claim_request_hash='{digest("claim-request:concurrent")}'
  AND claim_idempotency_hash='{digest("claim-idempotency:concurrent")}'
FROM prepared_action_execution_leases
WHERE action_id='act_concurrent';
""",
        stage="claim_exact_replay_unchanged",
    )

    expect_failure(
        executable,
        dsn,
        claim_sql(
            "wrong_binding",
            "lease_wrong_binding",
            action_hash=digest("action:concurrent"),
        ),
        schema=schema,
        stage="claim_wrong_binding",
        marker="prepared_action_execution_lease_binding_invalid",
    )
    idempotency_reuse = execute(
        executable,
        dsn,
        claim_sql(
            "idempotency_guard",
            "lease_idempotency_guard",
            principal_label="concurrent",
            claim_idempotency_hash=digest("claim-idempotency:concurrent"),
        ),
        schema=schema,
        stage="claim_idempotency_reuse",
    )
    if (idempotency_reuse.stdout or "").strip():
        raise ContractError("claim_idempotency_reuse_created_lease")
    expect_true(
        executable,
        dsn,
        schema,
        """
SELECT COUNT(*)=0
FROM prepared_action_execution_leases
WHERE action_id='act_idempotency_guard';
""",
        stage="claim_idempotency_reuse_blocked",
    )
    expect_failure(
        executable,
        dsn,
        f"""
UPDATE prepared_action_execution_leases
SET claim_request_hash='{digest("mutated-claim")}'
WHERE action_id='act_concurrent';
""",
        schema=schema,
        stage="claim_identity_mutation",
        marker="prepared_action_execution_claim_immutable",
    )
    expect_failure(
        executable,
        dsn,
        f"""
UPDATE prepared_actions
SET action_hash='{digest("mutated-action")}'
WHERE action_id='act_concurrent';
""",
        schema=schema,
        stage="action_identity_mutation",
        marker="prepared_action_identity_immutable",
    )

    success_lease = "lease_success"
    failure_lease = "lease_failure"
    unknown_lease = "lease_unknown"
    for label, lease_id, started_at, expires_at in (
        (
            "success",
            success_lease,
            "2026-07-24T00:02:00Z",
            "2026-07-24T00:20:00Z",
        ),
        (
            "failure",
            failure_lease,
            "2026-07-24T00:02:00Z",
            "2026-07-24T00:20:00Z",
        ),
        (
            "unknown",
            unknown_lease,
            "2026-07-24T00:02:00Z",
            "2026-07-24T00:20:00Z",
        ),
    ):
        execute(
            executable,
            dsn,
            claim_sql(
                label,
                lease_id,
                started_at=started_at,
                expires_at=expires_at,
            ),
            schema=schema,
            single_transaction=True,
            stage=f"claim_{label}",
        )

    execute(
        executable,
        dsn,
        terminal_sql("success", success_lease, "succeeded"),
        schema=schema,
        stage="terminal_success",
    )
    execute(
        executable,
        dsn,
        terminal_sql("failure", failure_lease, "failed"),
        schema=schema,
        stage="terminal_failure",
    )
    execute(
        executable,
        dsn,
        terminal_sql("unknown", unknown_lease, "unknown"),
        schema=schema,
        stage="terminal_unknown",
    )
    expect_true(
        executable,
        dsn,
        schema,
        """
SELECT
  COUNT(*) FILTER(WHERE outcome='succeeded')=1
  AND COUNT(*) FILTER(WHERE outcome='failed')=1
  AND COUNT(*) FILTER(WHERE outcome='unknown')=1
  AND bool_and(automatic_retry_allowed=FALSE)
  AND bool_and(retry_requires_new_action=TRUE)
FROM prepared_action_execution_receipts
WHERE action_id IN ('act_success','act_failure','act_unknown');
""",
        stage="terminal_receipt_outcomes",
    )

    unknown_retry = execute(
        executable,
        dsn,
        claim_sql("unknown", "lease_unknown_retry"),
        schema=schema,
        single_transaction=True,
        stage="unknown_retry",
    )
    if (unknown_retry.stdout or "").strip():
        raise ContractError("unknown_outcome_retry_created_lease")

    exact_receipt_replay = execute(
        executable,
        dsn,
        receipt_sql("success", success_lease, "succeeded").replace(
            ");\n",
            ")\nON CONFLICT DO NOTHING\nRETURNING receipt_id;\n",
        ),
        schema=schema,
        single_transaction=True,
        stage="receipt_exact_replay",
    )
    if (exact_receipt_replay.stdout or "").strip():
        raise ContractError("receipt_exact_replay_created_duplicate")

    expect_failure(
        executable,
        dsn,
        """
UPDATE prepared_action_execution_receipts
SET terminal_at='2026-07-24T00:11:00Z'
WHERE receipt_id='receipt_success';
""",
        schema=schema,
        stage="receipt_update",
        marker="prepared_action_execution_receipt_append_only",
    )
    expect_failure(
        executable,
        dsn,
        """
DELETE FROM prepared_action_execution_receipts
WHERE receipt_id='receipt_failure';
""",
        schema=schema,
        stage="receipt_delete",
        marker="prepared_action_execution_receipt_append_only",
    )

    execute(
        executable,
        dsn,
        claim_sql("receipt_required", "lease_receipt_required"),
        schema=schema,
        single_transaction=True,
        stage="claim_receipt_required",
    )
    expect_failure(
        executable,
        dsn,
        """
UPDATE prepared_actions
SET status='expired',result_summary='Action-only closure is invalid.'
WHERE action_id='act_receipt_required';
""",
        schema=schema,
        stage="action_only_terminal_transition",
        marker="prepared_action_execution_lease_state_invalid",
    )
    expect_failure(
        executable,
        dsn,
        """
UPDATE prepared_actions
SET status='expired',result_summary='Closure unknown.'
WHERE action_id='act_receipt_required';
UPDATE prepared_action_execution_leases
SET status='failed',completed_at='2026-07-24T00:25:00Z',
  failure_reason='Closure unknown.'
WHERE lease_id='lease_receipt_required';
""",
        schema=schema,
        stage="terminal_without_receipt",
        marker="prepared_action_execution_terminal_receipt_required",
    )

    execute(
        executable,
        dsn,
        claim_sql("retry_guard", "lease_retry_guard"),
        schema=schema,
        single_transaction=True,
        stage="claim_retry_guard",
    )
    expect_failure(
        executable,
        dsn,
        terminal_sql("retry_guard", "lease_retry_guard", "unknown").replace(
            "FALSE,TRUE,TRUE,TRUE,TRUE,TRUE,",
            "TRUE,TRUE,TRUE,TRUE,TRUE,TRUE,",
        ),
        schema=schema,
        stage="automatic_retry_allowed",
    )

    expect_true(
        executable,
        dsn,
        schema,
        """
SELECT COUNT(*)=0
FROM information_schema.columns
WHERE table_schema=current_schema()
  AND table_name='prepared_action_execution_receipts'
  AND column_name IN (
    'raw_provider_output','provider_output','provider_response',
    'raw_prompt','raw_response','token','credential'
  );
""",
        stage="forbidden_receipt_columns_absent",
    )
    expect_true(
        executable,
        dsn,
        schema,
        """
SELECT
  (SELECT COUNT(*)=1 FROM prepared_action_execution_leases
   WHERE action_id='act_unknown' AND status='failed')
  AND
  (SELECT COUNT(*)=1 FROM prepared_action_execution_receipts
   WHERE action_id='act_unknown' AND outcome='unknown'
     AND provider_call_may_have_completed=TRUE
     AND automatic_retry_allowed=FALSE
     AND retry_requires_new_action=TRUE);
""",
        stage="unknown_no_retry_state",
    )
    return {
        "fresh_full_chain_upgrade": True,
        "eight_way_claim_single_winner": True,
        "claim_exact_replay": True,
        "one_lease_ever_per_action": True,
        "wrong_binding_rejected": True,
        "claim_idempotency_reuse_rejected": True,
        "claim_and_action_identity_immutable": True,
        "success_failure_unknown_receipts": True,
        "action_and_lease_terminal_state_atomic": True,
        "terminal_receipt_required": True,
        "terminal_receipt_append_only": True,
        "expired_unknown_blocks_automatic_retry": True,
        "forbidden_receipt_columns_absent": True,
    }


def run_contract(executable: str, dsn: str) -> dict[str, object]:
    suffix = secrets.token_hex(6)
    schemas = {
        "upgrade": f"pa_v6_upgrade_{suffix}",
        "ambiguous": f"pa_v6_ambiguous_{suffix}",
        "fresh": f"pa_v6_fresh_{suffix}",
    }
    created: list[str] = []
    cleaned = 0
    checks: dict[str, object] = {
        "raw_rows_emitted": False,
        "secrets_emitted": False,
    }
    try:
        version_result = execute(
            executable,
            dsn,
            """
SELECT current_setting('server_version_num')::INTEGER
  BETWEEN 160000 AND 169999;
""",
            stage="postgres_16_version",
        )
        if (version_result.stdout or "").strip() != "t":
            raise ContractError("postgres_16_required")
        checks["postgres_16_verified"] = True
        for schema in schemas.values():
            create_schema(executable, dsn, schema)
            created.append(schema)
        checks.update(
            run_upgrade_contract(executable, dsn, schemas["upgrade"])
        )
        checks.update(
            run_ambiguous_rollback_contract(
                executable,
                dsn,
                schemas["ambiguous"],
            )
        )
        checks.update(run_fresh_contract(executable, dsn, schemas["fresh"]))
        return checks
    finally:
        for schema in reversed(created):
            if drop_schema(executable, dsn, schema):
                cleaned += 1
        checks["disposable_schemas_created"] = len(created)
        checks["disposable_schemas_cleaned"] = cleaned
        if cleaned != len(created) and sys.exc_info()[0] is None:
            raise ContractError("disposable_schema_cleanup_failed")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the PreparedAction execution lease v6 in disposable "
            "schemas on an existing PostgreSQL 16 service."
        )
    )
    parser.add_argument(
        "--postgres-dsn",
        default=os.environ.get("AGENTOPS_POSTGRES_DSN"),
        help=(
            "PostgreSQL DSN. The value is never included in contract output; "
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

    ok = (
        all(
            value is True
            for key, value in checks.items()
            if key
            not in {
                "disposable_schemas_created",
                "disposable_schemas_cleaned",
                "raw_rows_emitted",
                "secrets_emitted",
            }
        )
        and checks["disposable_schemas_created"]
        == checks["disposable_schemas_cleaned"]
        and checks["raw_rows_emitted"] is False
        and checks["secrets_emitted"] is False
    )
    print(
        json.dumps(
            {
                "checks": checks,
                "contract": CONTRACT,
                "migration_artifact_count": len(ORDERED_SQL),
                "ok": ok,
            },
            sort_keys=True,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
