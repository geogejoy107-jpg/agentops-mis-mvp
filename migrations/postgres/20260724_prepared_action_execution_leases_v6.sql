-- Harden the current-main PreparedAction execution lease as an append-only,
-- action_id-bound terminal receipt contract. The migration runner owns the
-- transaction and applies this after the commercial baseline plus v1-v5.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

LOCK TABLE prepared_actions IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE prepared_action_execution_leases IN SHARE ROW EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM prepared_actions action
    WHERE action.action_hash !~ '^[a-f0-9]{64}$'
      OR btrim(action.idempotency_key)=''
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_identity_invalid';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM prepared_actions action
    GROUP BY action.workspace_id,action.run_id,action.idempotency_key
    HAVING COUNT(*)>1
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23505',
      MESSAGE='prepared_action_idempotency_ambiguous';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM prepared_action_execution_leases lease
    LEFT JOIN prepared_actions action
      ON action.action_id=lease.action_id
    LEFT JOIN approvals approval
      ON approval.approval_id=action.approval_id
    LEFT JOIN runs run
      ON run.run_id=action.run_id
    LEFT JOIN tasks task
      ON task.task_id=action.task_id
    LEFT JOIN tool_calls tool
      ON tool.tool_call_id=action.tool_call_id
    WHERE action.action_id IS NULL
      OR action.action_type<>'agent_worker.codex.workspace_write'
      OR approval.approval_id IS NULL
      OR run.run_id IS NULL
      OR task.task_id IS NULL
      OR tool.tool_call_id IS NULL
      OR lease.workspace_id<>action.workspace_id
      OR lease.requested_by_agent_id<>action.requested_by_agent_id
      OR lease.action_hash<>action.action_hash
      OR approval.approval_kind<>'prepared_action'
      OR approval.decision<>'approved'
      OR approval.task_id<>action.task_id
      OR approval.run_id<>action.run_id
      OR approval.tool_call_id<>action.tool_call_id
      OR approval.requested_by_agent_id<>action.requested_by_agent_id
      OR run.task_id<>action.task_id
      OR run.workspace_id<>action.workspace_id
      OR run.agent_id<>action.requested_by_agent_id
      OR task.workspace_id<>action.workspace_id
      OR tool.run_id<>action.run_id
      OR tool.agent_id<>action.requested_by_agent_id
      OR lease.action_hash !~ '^[a-f0-9]{64}$'
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_lease_binding_invalid';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM prepared_action_execution_leases lease
    JOIN prepared_actions action
      ON action.action_id=lease.action_id
    WHERE lease.started_at::timestamptz>=lease.expires_at::timestamptz
    OR (
      lease.status='executing'
      AND (
        action.status<>'approved'
        OR action.approved_at IS NULL
        OR lease.completed_at IS NOT NULL
        OR lease.failure_reason IS NOT NULL
        OR lease.started_at::timestamptz>=lease.expires_at::timestamptz
      )
    ) OR (
      lease.status='completed'
      AND (
        action.status<>'consumed'
        OR action.approved_at IS NULL
        OR action.consumed_at IS NULL
        OR action.provider_side_effect_id IS NULL
        OR lease.completed_at IS NULL
        OR lease.failure_reason IS NOT NULL
        OR lease.completed_at::timestamptz>lease.expires_at::timestamptz
      )
    ) OR (
      lease.status='failed'
      AND (
        action.status<>'expired'
        OR action.approved_at IS NULL
        OR lease.completed_at IS NULL
        OR NULLIF(btrim(lease.failure_reason),'') IS NULL
        OR lease.completed_at::timestamptz<lease.started_at::timestamptz
      )
    )
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_lease_state_ambiguous';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM prepared_action_execution_leases lease
    GROUP BY
      lease.workspace_id,
      lease.requested_by_agent_id,
      lease.action_hash
    HAVING COUNT(*)>1
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23505',
      MESSAGE='prepared_action_legacy_claim_identity_ambiguous';
  END IF;
END
$$;

ALTER TABLE prepared_action_execution_leases
ADD COLUMN IF NOT EXISTS claim_request_hash TEXT;

ALTER TABLE prepared_action_execution_leases
ADD COLUMN IF NOT EXISTS claim_idempotency_hash TEXT;

ALTER TABLE prepared_action_execution_leases
ADD COLUMN IF NOT EXISTS claim_identity_source TEXT;

UPDATE prepared_action_execution_leases
SET
  claim_request_hash=action_hash,
  claim_idempotency_hash=action_hash,
  claim_identity_source='legacy_action_hash_backfill_v1'
WHERE claim_request_hash IS NULL
  AND claim_idempotency_hash IS NULL
  AND claim_identity_source IS NULL;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM prepared_action_execution_leases lease
    WHERE lease.claim_request_hash IS NULL
      OR lease.claim_idempotency_hash IS NULL
      OR lease.claim_identity_source IS NULL
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_claim_identity_partial';
  END IF;
END
$$;

ALTER TABLE prepared_action_execution_leases
ALTER COLUMN claim_request_hash SET NOT NULL;

ALTER TABLE prepared_action_execution_leases
ALTER COLUMN claim_idempotency_hash SET NOT NULL;

ALTER TABLE prepared_action_execution_leases
ALTER COLUMN claim_identity_source SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='prepared_actions'::regclass
      AND conname='prepared_actions_action_hash_v6_check'
  ) THEN
    ALTER TABLE prepared_actions
    ADD CONSTRAINT prepared_actions_action_hash_v6_check
    CHECK(action_hash ~ '^[a-f0-9]{64}$');
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='prepared_actions'::regclass
      AND conname='prepared_actions_idempotency_v6_check'
  ) THEN
    ALTER TABLE prepared_actions
    ADD CONSTRAINT prepared_actions_idempotency_v6_check
    CHECK(NULLIF(btrim(idempotency_key),'') IS NOT NULL);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='prepared_action_execution_leases'::regclass
      AND conname='prepared_action_execution_leases_claim_request_hash_check'
  ) THEN
    ALTER TABLE prepared_action_execution_leases
    ADD CONSTRAINT
      prepared_action_execution_leases_claim_request_hash_check
    CHECK(claim_request_hash ~ '^[a-f0-9]{64}$');
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='prepared_action_execution_leases'::regclass
      AND conname='prepared_action_execution_leases_claim_idempotency_hash_check'
  ) THEN
    ALTER TABLE prepared_action_execution_leases
    ADD CONSTRAINT
      prepared_action_execution_leases_claim_idempotency_hash_check
    CHECK(claim_idempotency_hash ~ '^[a-f0-9]{64}$');
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='prepared_action_execution_leases'::regclass
      AND conname='prepared_action_execution_leases_claim_source_check'
  ) THEN
    ALTER TABLE prepared_action_execution_leases
    ADD CONSTRAINT prepared_action_execution_leases_claim_source_check
    CHECK(
      claim_identity_source IN (
        'request_hash_v1',
        'legacy_action_hash_backfill_v1'
      )
    );
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS
idx_prepared_actions_run_idempotency_v6
ON prepared_actions(workspace_id,run_id,idempotency_key);

CREATE UNIQUE INDEX IF NOT EXISTS
idx_prepared_action_lease_claim_idempotency_v6
ON prepared_action_execution_leases(
  workspace_id,
  requested_by_agent_id,
  claim_idempotency_hash
);

CREATE TABLE IF NOT EXISTS prepared_action_execution_receipts (
    receipt_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    requested_by_agent_id TEXT NOT NULL,
    action_hash TEXT NOT NULL,
    claim_request_hash TEXT NOT NULL,
    claim_idempotency_hash TEXT NOT NULL,
    receipt_request_hash TEXT NOT NULL,
    outcome TEXT NOT NULL,
    provider_call_performed BOOLEAN NOT NULL,
    provider_call_may_have_completed BOOLEAN NOT NULL,
    terminal_evidence_hash TEXT,
    terminal_evidence_source TEXT NOT NULL,
    terminal_evidence_verified BOOLEAN NOT NULL DEFAULT FALSE,
    automatic_retry_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    retry_requires_new_action BOOLEAN NOT NULL DEFAULT TRUE,
    raw_provider_output_omitted BOOLEAN NOT NULL DEFAULT TRUE,
    raw_prompt_omitted BOOLEAN NOT NULL DEFAULT TRUE,
    raw_response_omitted BOOLEAN NOT NULL DEFAULT TRUE,
    token_omitted BOOLEAN NOT NULL DEFAULT TRUE,
    terminal_at TEXT NOT NULL,
    CONSTRAINT prepared_action_execution_receipts_pkey
      PRIMARY KEY(receipt_id),
    CONSTRAINT prepared_action_execution_receipts_lease_key
      UNIQUE(lease_id),
    CONSTRAINT prepared_action_execution_receipts_action_key
      UNIQUE(action_id),
    CONSTRAINT prepared_action_execution_receipts_request_key
      UNIQUE(workspace_id,requested_by_agent_id,receipt_request_hash),
    CONSTRAINT prepared_action_execution_receipts_outcome_check
      CHECK(outcome IN ('succeeded','failed','unknown')),
    CONSTRAINT prepared_action_execution_receipts_action_hash_check
      CHECK(action_hash ~ '^[a-f0-9]{64}$'),
    CONSTRAINT prepared_action_execution_receipts_claim_request_hash_check
      CHECK(claim_request_hash ~ '^[a-f0-9]{64}$'),
    CONSTRAINT prepared_action_execution_receipts_claim_idempotency_hash_check
      CHECK(claim_idempotency_hash ~ '^[a-f0-9]{64}$'),
    CONSTRAINT prepared_action_execution_receipts_request_hash_check
      CHECK(receipt_request_hash ~ '^[a-f0-9]{64}$'),
    CONSTRAINT prepared_action_execution_receipts_evidence_hash_check
      CHECK(
        terminal_evidence_hash IS NULL
        OR terminal_evidence_hash ~ '^[a-f0-9]{64}$'
      ),
    CONSTRAINT prepared_action_execution_receipts_source_check
      CHECK(
        terminal_evidence_source IN (
          'worker_verified_v1',
          'provider_idempotency_lookup_v1',
          'control_plane_failure_v1',
          'control_plane_timeout_v1',
          'legacy_control_plane_transition_v1'
        )
      ),
    CONSTRAINT prepared_action_execution_receipts_retry_check
      CHECK(
        automatic_retry_allowed=FALSE
        AND retry_requires_new_action=TRUE
      ),
    CONSTRAINT prepared_action_execution_receipts_omission_check
      CHECK(
        raw_provider_output_omitted=TRUE
        AND raw_prompt_omitted=TRUE
        AND raw_response_omitted=TRUE
        AND token_omitted=TRUE
      ),
    CONSTRAINT prepared_action_execution_receipts_outcome_evidence_check
      CHECK(
        (
          outcome='succeeded'
          AND provider_call_performed=TRUE
          AND provider_call_may_have_completed=FALSE
          AND terminal_evidence_hash IS NOT NULL
        )
        OR (
          outcome='failed'
          AND provider_call_may_have_completed=FALSE
        )
        OR (
          outcome='unknown'
          AND provider_call_may_have_completed=TRUE
          AND terminal_evidence_verified=FALSE
        )
      ),
    CONSTRAINT prepared_action_execution_receipts_lease_fkey
      FOREIGN KEY(lease_id)
      REFERENCES prepared_action_execution_leases(lease_id),
    CONSTRAINT prepared_action_execution_receipts_action_fkey
      FOREIGN KEY(action_id) REFERENCES prepared_actions(action_id),
    CONSTRAINT prepared_action_execution_receipts_agent_fkey
      FOREIGN KEY(requested_by_agent_id) REFERENCES agents(agent_id)
);

INSERT INTO prepared_action_execution_receipts(
  receipt_id,
  lease_id,
  action_id,
  workspace_id,
  requested_by_agent_id,
  action_hash,
  claim_request_hash,
  claim_idempotency_hash,
  receipt_request_hash,
  outcome,
  provider_call_performed,
  provider_call_may_have_completed,
  terminal_evidence_hash,
  terminal_evidence_source,
  terminal_evidence_verified,
  automatic_retry_allowed,
  retry_requires_new_action,
  raw_provider_output_omitted,
  raw_prompt_omitted,
  raw_response_omitted,
  token_omitted,
  terminal_at
)
SELECT
  'pa_receipt_legacy_' || lease.lease_id,
  lease.lease_id,
  lease.action_id,
  lease.workspace_id,
  lease.requested_by_agent_id,
  lease.action_hash,
  lease.claim_request_hash,
  lease.claim_idempotency_hash,
  lease.action_hash,
  CASE
    WHEN lease.status='completed' THEN 'succeeded'
    ELSE 'unknown'
  END,
  lease.status='completed',
  lease.status='failed',
  CASE
    WHEN lease.status='completed' THEN lease.action_hash
    ELSE NULL
  END,
  'legacy_control_plane_transition_v1',
  FALSE,
  FALSE,
  TRUE,
  TRUE,
  TRUE,
  TRUE,
  TRUE,
  lease.completed_at
FROM prepared_action_execution_leases lease
WHERE lease.status IN ('completed','failed')
ON CONFLICT(lease_id) DO NOTHING;

CREATE OR REPLACE FUNCTION
agentops_assert_prepared_action_execution_lease_v6(target_lease_id TEXT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
  binding RECORD;
  receipt_count INTEGER;
  receipt_outcome TEXT;
BEGIN
  SELECT
    lease.lease_id,
    lease.action_id,
    lease.workspace_id,
    lease.requested_by_agent_id,
    lease.action_hash,
    lease.claim_request_hash,
    lease.claim_idempotency_hash,
    lease.status AS lease_status,
    lease.completed_at,
    lease.failure_reason,
    action.workspace_id AS action_workspace_id,
    action.task_id,
    action.run_id,
    action.tool_call_id,
    action.approval_id,
    action.requested_by_agent_id AS action_agent_id,
    action.action_hash AS stored_action_hash,
    action.action_type,
    action.status AS action_status,
    action.approved_at,
    action.consumed_at,
    action.provider_side_effect_id,
    approval.approval_kind,
    approval.decision AS approval_decision,
    approval.task_id AS approval_task_id,
    approval.run_id AS approval_run_id,
    approval.tool_call_id AS approval_tool_call_id,
    approval.requested_by_agent_id AS approval_agent_id,
    run.workspace_id AS run_workspace_id,
    run.task_id AS run_task_id,
    run.agent_id AS run_agent_id,
    task.workspace_id AS task_workspace_id,
    tool.run_id AS tool_run_id,
    tool.agent_id AS tool_agent_id
  INTO binding
  FROM prepared_action_execution_leases lease
  JOIN prepared_actions action
    ON action.action_id=lease.action_id
  JOIN approvals approval
    ON approval.approval_id=action.approval_id
  JOIN runs run
    ON run.run_id=action.run_id
  JOIN tasks task
    ON task.task_id=action.task_id
  JOIN tool_calls tool
    ON tool.tool_call_id=action.tool_call_id
  WHERE lease.lease_id=target_lease_id;

  IF NOT FOUND
    OR binding.workspace_id<>binding.action_workspace_id
    OR binding.requested_by_agent_id<>binding.action_agent_id
    OR binding.action_hash<>binding.stored_action_hash
    OR binding.action_type<>'agent_worker.codex.workspace_write'
    OR binding.approval_kind<>'prepared_action'
    OR binding.approval_decision<>'approved'
    OR binding.approval_task_id<>binding.task_id
    OR binding.approval_run_id<>binding.run_id
    OR binding.approval_tool_call_id<>binding.tool_call_id
    OR binding.approval_agent_id<>binding.action_agent_id
    OR binding.run_workspace_id<>binding.action_workspace_id
    OR binding.run_task_id<>binding.task_id
    OR binding.run_agent_id<>binding.action_agent_id
    OR binding.task_workspace_id<>binding.action_workspace_id
    OR binding.tool_run_id<>binding.run_id
    OR binding.tool_agent_id<>binding.action_agent_id THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_lease_binding_invalid';
  END IF;

  SELECT COUNT(*)::INTEGER,MIN(receipt.outcome)
  INTO receipt_count,receipt_outcome
  FROM prepared_action_execution_receipts receipt
  WHERE receipt.lease_id=target_lease_id;

  IF binding.lease_status='executing' THEN
    IF binding.action_status<>'approved'
      OR receipt_count<>0
      OR binding.completed_at IS NOT NULL
      OR binding.failure_reason IS NOT NULL THEN
      RAISE EXCEPTION USING
        ERRCODE='23514',
        MESSAGE='prepared_action_execution_lease_state_invalid';
    END IF;
  ELSIF binding.lease_status='completed' THEN
    IF binding.action_status<>'consumed'
      OR binding.consumed_at IS NULL
      OR binding.provider_side_effect_id IS NULL
      OR binding.completed_at IS NULL
      OR binding.failure_reason IS NOT NULL
      OR receipt_count<>1
      OR receipt_outcome<>'succeeded' THEN
      RAISE EXCEPTION USING
        ERRCODE='23514',
        MESSAGE='prepared_action_execution_terminal_receipt_required';
    END IF;
  ELSIF binding.lease_status='failed' THEN
    IF binding.action_status<>'expired'
      OR binding.completed_at IS NULL
      OR NULLIF(btrim(binding.failure_reason),'') IS NULL
      OR receipt_count<>1
      OR receipt_outcome NOT IN ('failed','unknown') THEN
      RAISE EXCEPTION USING
        ERRCODE='23514',
        MESSAGE='prepared_action_execution_terminal_receipt_required';
    END IF;
  ELSE
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_lease_state_invalid';
  END IF;
END
$$;

CREATE OR REPLACE FUNCTION
agentops_enforce_prepared_action_identity_v6()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_append_only';
  END IF;

  IF OLD.action_id IS DISTINCT FROM NEW.action_id
    OR OLD.workspace_id IS DISTINCT FROM NEW.workspace_id
    OR OLD.task_id IS DISTINCT FROM NEW.task_id
    OR OLD.run_id IS DISTINCT FROM NEW.run_id
    OR OLD.tool_call_id IS DISTINCT FROM NEW.tool_call_id
    OR OLD.approval_id IS DISTINCT FROM NEW.approval_id
    OR OLD.requested_by_agent_id IS DISTINCT FROM NEW.requested_by_agent_id
    OR OLD.action_type IS DISTINCT FROM NEW.action_type
    OR OLD.normalized_args_json IS DISTINCT FROM NEW.normalized_args_json
    OR OLD.target_resource IS DISTINCT FROM NEW.target_resource
    OR OLD.risk_level IS DISTINCT FROM NEW.risk_level
    OR OLD.policy_version IS DISTINCT FROM NEW.policy_version
    OR OLD.checkpoint_json IS DISTINCT FROM NEW.checkpoint_json
    OR OLD.action_hash IS DISTINCT FROM NEW.action_hash
    OR OLD.idempotency_key IS DISTINCT FROM NEW.idempotency_key
    OR OLD.created_at IS DISTINCT FROM NEW.created_at
    OR OLD.expires_at IS DISTINCT FROM NEW.expires_at THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_identity_immutable';
  END IF;

  IF OLD.approved_at IS NOT NULL
    AND OLD.approved_at IS DISTINCT FROM NEW.approved_at THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_approval_identity_immutable';
  END IF;

  IF OLD.status IN ('rejected','consumed','expired')
    AND to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_terminal_immutable';
  END IF;

  IF NOT (
    OLD.status=NEW.status
    OR (OLD.status='prepared' AND NEW.status IN (
      'approved','rejected','expired'
    ))
    OR (OLD.status='approved' AND NEW.status IN ('consumed','expired'))
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_status_transition_invalid';
  END IF;

  IF NEW.status='approved'
    AND NEW.approved_at IS NULL THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_approval_state_invalid';
  END IF;

  IF NEW.status='consumed'
    AND (
      NEW.approved_at IS NULL
      OR NEW.consumed_at IS NULL
      OR NEW.provider_side_effect_id IS NULL
    ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_consumed_state_invalid';
  END IF;

  IF NEW.status IN ('prepared','approved','rejected')
    AND (
      NEW.consumed_at IS NOT NULL
      OR NEW.provider_side_effect_id IS NOT NULL
    ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_terminal_fields_invalid';
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION
agentops_enforce_prepared_action_execution_lease_v6()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_lease_append_only';
  END IF;

  IF TG_OP='INSERT' THEN
    IF NEW.status<>'executing'
      OR NEW.completed_at IS NOT NULL
      OR NEW.failure_reason IS NOT NULL
      OR NEW.started_at::timestamptz>=NEW.expires_at::timestamptz THEN
      RAISE EXCEPTION USING
        ERRCODE='23514',
        MESSAGE='prepared_action_execution_lease_state_invalid';
    END IF;
    RETURN NEW;
  END IF;

  IF OLD.lease_id IS DISTINCT FROM NEW.lease_id
    OR OLD.action_id IS DISTINCT FROM NEW.action_id
    OR OLD.workspace_id IS DISTINCT FROM NEW.workspace_id
    OR OLD.requested_by_agent_id IS DISTINCT FROM NEW.requested_by_agent_id
    OR OLD.action_hash IS DISTINCT FROM NEW.action_hash
    OR OLD.claim_request_hash IS DISTINCT FROM NEW.claim_request_hash
    OR OLD.claim_idempotency_hash IS DISTINCT FROM NEW.claim_idempotency_hash
    OR OLD.claim_identity_source IS DISTINCT FROM NEW.claim_identity_source
    OR OLD.started_at IS DISTINCT FROM NEW.started_at
    OR OLD.expires_at IS DISTINCT FROM NEW.expires_at THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_claim_immutable';
  END IF;

  IF OLD.status IN ('completed','failed')
    AND to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_lease_terminal_immutable';
  END IF;

  IF NOT (
    OLD.status=NEW.status
    OR (
      OLD.status='executing'
      AND NEW.status IN ('completed','failed')
    )
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_lease_transition_invalid';
  END IF;

  IF NEW.status='completed'
    AND (
      NEW.completed_at IS NULL
      OR NEW.failure_reason IS NOT NULL
      OR NEW.completed_at::timestamptz>NEW.expires_at::timestamptz
    ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_lease_state_invalid';
  END IF;

  IF NEW.status='failed'
    AND (
      NEW.completed_at IS NULL
      OR NULLIF(btrim(NEW.failure_reason),'') IS NULL
      OR NEW.completed_at::timestamptz<NEW.started_at::timestamptz
    ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_lease_state_invalid';
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION
agentops_check_prepared_action_execution_action_v6()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  target_lease_id TEXT;
BEGIN
  SELECT lease.lease_id
  INTO target_lease_id
  FROM prepared_action_execution_leases lease
  WHERE lease.action_id=NEW.action_id;

  IF target_lease_id IS NOT NULL THEN
    PERFORM agentops_assert_prepared_action_execution_lease_v6(
      target_lease_id
    );
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION
agentops_enforce_prepared_action_execution_receipt_v6()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  binding RECORD;
BEGIN
  SELECT
    lease.action_id,
    lease.workspace_id,
    lease.requested_by_agent_id,
    lease.action_hash,
    lease.claim_request_hash,
    lease.claim_idempotency_hash,
    lease.status AS lease_status,
    lease.completed_at,
    action.status AS action_status
  INTO binding
  FROM prepared_action_execution_leases lease
  JOIN prepared_actions action
    ON action.action_id=lease.action_id
  WHERE lease.lease_id=NEW.lease_id;

  IF NOT FOUND
    OR NEW.action_id<>binding.action_id
    OR NEW.workspace_id<>binding.workspace_id
    OR NEW.requested_by_agent_id<>binding.requested_by_agent_id
    OR NEW.action_hash<>binding.action_hash
    OR NEW.claim_request_hash<>binding.claim_request_hash
    OR NEW.claim_idempotency_hash<>binding.claim_idempotency_hash
    OR NEW.terminal_at IS DISTINCT FROM binding.completed_at THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_receipt_binding_invalid';
  END IF;

  IF (
    NEW.outcome='succeeded'
    AND (
      binding.lease_status<>'completed'
      OR binding.action_status<>'consumed'
    )
  ) OR (
    NEW.outcome IN ('failed','unknown')
    AND (
      binding.lease_status<>'failed'
      OR binding.action_status<>'expired'
    )
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='prepared_action_execution_receipt_terminal_state_invalid';
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION
agentops_reject_prepared_action_execution_receipt_mutation_v6()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION USING
    ERRCODE='23514',
    MESSAGE='prepared_action_execution_receipt_append_only';
END
$$;

CREATE OR REPLACE FUNCTION
agentops_check_prepared_action_execution_lease_v6()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM agentops_assert_prepared_action_execution_lease_v6(
    CASE
      WHEN TG_OP='DELETE' THEN OLD.lease_id
      ELSE NEW.lease_id
    END
  );
  RETURN CASE
    WHEN TG_OP='DELETE' THEN OLD
    ELSE NEW
  END;
END
$$;

DROP TRIGGER IF EXISTS prepared_actions_identity_v6
ON prepared_actions;
CREATE TRIGGER prepared_actions_identity_v6
BEFORE UPDATE OR DELETE ON prepared_actions
FOR EACH ROW
EXECUTE FUNCTION agentops_enforce_prepared_action_identity_v6();

DROP TRIGGER IF EXISTS prepared_actions_execution_binding_v6
ON prepared_actions;
CREATE CONSTRAINT TRIGGER prepared_actions_execution_binding_v6
AFTER INSERT OR UPDATE
ON prepared_actions
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION agentops_check_prepared_action_execution_action_v6();

DROP TRIGGER IF EXISTS prepared_action_execution_leases_guard_v6
ON prepared_action_execution_leases;
CREATE TRIGGER prepared_action_execution_leases_guard_v6
BEFORE INSERT OR UPDATE OR DELETE
ON prepared_action_execution_leases
FOR EACH ROW
EXECUTE FUNCTION agentops_enforce_prepared_action_execution_lease_v6();

DROP TRIGGER IF EXISTS prepared_action_execution_leases_binding_v6
ON prepared_action_execution_leases;
CREATE CONSTRAINT TRIGGER prepared_action_execution_leases_binding_v6
AFTER INSERT OR UPDATE
ON prepared_action_execution_leases
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION agentops_check_prepared_action_execution_lease_v6();

DROP TRIGGER IF EXISTS prepared_action_execution_receipts_guard_v6
ON prepared_action_execution_receipts;
CREATE TRIGGER prepared_action_execution_receipts_guard_v6
BEFORE INSERT ON prepared_action_execution_receipts
FOR EACH ROW
EXECUTE FUNCTION agentops_enforce_prepared_action_execution_receipt_v6();

DROP TRIGGER IF EXISTS prepared_action_execution_receipts_append_only_v6
ON prepared_action_execution_receipts;
CREATE TRIGGER prepared_action_execution_receipts_append_only_v6
BEFORE UPDATE OR DELETE ON prepared_action_execution_receipts
FOR EACH ROW
EXECUTE FUNCTION
  agentops_reject_prepared_action_execution_receipt_mutation_v6();

DO $$
DECLARE
  lease_record RECORD;
BEGIN
  FOR lease_record IN
    SELECT lease_id
    FROM prepared_action_execution_leases
    ORDER BY lease_id
  LOOP
    PERFORM agentops_assert_prepared_action_execution_lease_v6(
      lease_record.lease_id
    );
  END LOOP;
END
$$;
