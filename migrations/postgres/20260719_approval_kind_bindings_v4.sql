-- Make approval intent durable and enforce the relationship between each
-- approval kind and its workspace-bound subject. The migration runner owns the
-- surrounding transaction and exact receipt.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE approvals
ADD COLUMN IF NOT EXISTS approval_kind TEXT;

DO $$
DECLARE
  approval_record RECORD;
  inferred_kind TEXT;
BEGIN
  FOR approval_record IN
    SELECT
      approval.approval_id,
      approval.approval_kind,
      approval.tool_call_id,
      EXISTS(
        SELECT 1 FROM prepared_actions action
        WHERE action.approval_id=approval.approval_id
      ) AS has_prepared_action,
      EXISTS(
        SELECT 1 FROM agent_gateway_enrollment_requests request
        WHERE request.approval_id=approval.approval_id
      ) AS has_enrollment_request,
      EXISTS(
        SELECT 1 FROM audit_logs audit
        WHERE audit.entity_type='approvals'
          AND audit.entity_id=approval.approval_id
          AND audit.action='workflow.customer_worker_task.delivery_approval'
      ) AS has_customer_delivery_audit,
      EXISTS(
        SELECT 1 FROM audit_logs audit
        WHERE audit.entity_type='approvals'
          AND audit.entity_id=approval.approval_id
          AND audit.action IN ('agent_gateway.approval_request','workflow.run_execution_approval')
      ) AS has_execution_approval_audit
    FROM approvals approval
    ORDER BY approval.approval_id
  LOOP
    IF (
      approval_record.has_prepared_action
      AND approval_record.has_enrollment_request
    ) OR (
      approval_record.has_customer_delivery_audit
      AND (
        approval_record.tool_call_id IS NOT NULL
        OR approval_record.has_prepared_action
        OR approval_record.has_enrollment_request
      )
    ) THEN
      RAISE EXCEPTION USING
        ERRCODE='23514',
        MESSAGE='approval_kind_backfill_ambiguous';
    END IF;

    inferred_kind=CASE
      WHEN approval_record.has_prepared_action THEN 'prepared_action'
      WHEN approval_record.has_enrollment_request THEN 'agent_enrollment'
      WHEN approval_record.has_customer_delivery_audit THEN 'customer_delivery'
      WHEN approval_record.tool_call_id IS NOT NULL THEN 'tool_execution'
      WHEN approval_record.has_execution_approval_audit THEN 'run_execution'
      ELSE NULL
    END;

    IF inferred_kind IS NULL THEN
      RAISE EXCEPTION USING
        ERRCODE='23514',
        MESSAGE='approval_kind_backfill_evidence_missing';
    END IF;
    IF approval_record.approval_kind IS NOT NULL
      AND approval_record.approval_kind<>inferred_kind THEN
      RAISE EXCEPTION USING
        ERRCODE='23514',
        MESSAGE='approval_kind_prefill_evidence_mismatch';
    END IF;

    UPDATE approvals
    SET approval_kind=inferred_kind
    WHERE approval_id=approval_record.approval_id;
  END LOOP;

  IF EXISTS (
    SELECT 1
    FROM approvals approval
    WHERE approval.approval_kind='run_execution'
      AND (
        approval.approval_id LIKE 'ap_customer_worker_delivery%'
        OR lower(COALESCE(approval.reason,'')) LIKE '%customer delivery%'
      )
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='approval_kind_customer_delivery_evidence_missing';
  END IF;
END
$$;

ALTER TABLE approvals
ALTER COLUMN approval_kind DROP DEFAULT;

ALTER TABLE approvals
ALTER COLUMN approval_kind SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='approvals'::regclass
      AND conname='approvals_kind_binding_check'
  ) THEN
    ALTER TABLE approvals
    ADD CONSTRAINT approvals_kind_binding_check
    CHECK (
      (approval_kind IN ('tool_execution','prepared_action') AND tool_call_id IS NOT NULL)
      OR (approval_kind IN ('run_execution','agent_enrollment','customer_delivery') AND tool_call_id IS NULL)
    );
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_gateway_enrollment_approval_unique
ON agent_gateway_enrollment_requests(approval_id);

CREATE OR REPLACE FUNCTION agentops_assert_approval_kind_binding(target_approval_id TEXT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
  approval_record RECORD;
  prepared_count INTEGER;
  prepared_edges_valid BOOLEAN;
  enrollment_count INTEGER;
  enrollment_edges_valid BOOLEAN;
BEGIN
  SELECT
    approval.approval_id,
    approval.approval_kind,
    approval.task_id,
    approval.run_id,
    approval.tool_call_id,
    approval.requested_by_agent_id,
    task.workspace_id AS task_workspace_id,
    run.workspace_id AS run_workspace_id,
    run.agent_id AS run_agent_id,
    tool.tool_call_id AS bound_tool_call_id,
    tool.run_id AS tool_run_id,
    tool.agent_id AS tool_agent_id
  INTO approval_record
  FROM approvals approval
  LEFT JOIN tasks task ON task.task_id=approval.task_id
  LEFT JOIN runs run ON run.run_id=approval.run_id
  LEFT JOIN tool_calls tool ON tool.tool_call_id=approval.tool_call_id
  WHERE approval.approval_id=target_approval_id;

  IF NOT FOUND THEN
    IF EXISTS(
      SELECT 1 FROM prepared_actions action
      WHERE action.approval_id=target_approval_id
    ) OR EXISTS(
      SELECT 1 FROM agent_gateway_enrollment_requests request
      WHERE request.approval_id=target_approval_id
    ) THEN
      RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_orphaned';
    END IF;
    RETURN;
  END IF;

  IF approval_record.task_workspace_id IS NULL
    OR approval_record.run_workspace_id IS NULL
    OR approval_record.task_workspace_id<>approval_record.run_workspace_id
    OR approval_record.run_id IS NULL
    OR NOT EXISTS(
      SELECT 1 FROM runs bound_run
      WHERE bound_run.run_id=approval_record.run_id
        AND bound_run.task_id=approval_record.task_id
    )
    OR (
      approval_record.requested_by_agent_id IS NOT NULL
      AND approval_record.requested_by_agent_id<>approval_record.run_agent_id
    ) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_invalid';
  END IF;

  IF approval_record.tool_call_id IS NOT NULL AND (
    approval_record.bound_tool_call_id IS NULL
    OR approval_record.tool_run_id<>approval_record.run_id
    OR approval_record.tool_agent_id<>approval_record.run_agent_id
  ) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_invalid';
  END IF;

  SELECT
    COUNT(*)::INTEGER,
    COALESCE(bool_and(
      action.workspace_id=approval_record.run_workspace_id
      AND action.task_id=approval_record.task_id
      AND action.run_id=approval_record.run_id
      AND action.tool_call_id=approval_record.tool_call_id
      AND (
        action.requested_by_agent_id IS NULL
        OR action.requested_by_agent_id=approval_record.run_agent_id
      )
    ),TRUE)
  INTO prepared_count,prepared_edges_valid
  FROM prepared_actions action
  WHERE action.approval_id=target_approval_id;

  SELECT
    COUNT(*)::INTEGER,
    COALESCE(bool_and(
      request.workspace_id=approval_record.run_workspace_id
      AND request.task_id=approval_record.task_id
      AND request.run_id=approval_record.run_id
      AND request.agent_id=approval_record.run_agent_id
    ),TRUE)
  INTO enrollment_count,enrollment_edges_valid
  FROM agent_gateway_enrollment_requests request
  WHERE request.approval_id=target_approval_id;

  IF NOT prepared_edges_valid OR NOT enrollment_edges_valid THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_invalid';
  END IF;

  IF approval_record.approval_kind='prepared_action' THEN
    IF prepared_count<>1 OR enrollment_count<>0 OR approval_record.tool_call_id IS NULL THEN
      RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_invalid';
    END IF;
  ELSIF approval_record.approval_kind='agent_enrollment' THEN
    IF prepared_count<>0 OR enrollment_count<>1 OR approval_record.tool_call_id IS NOT NULL THEN
      RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_invalid';
    END IF;
  ELSIF approval_record.approval_kind='tool_execution' THEN
    IF prepared_count<>0 OR enrollment_count<>0 OR approval_record.tool_call_id IS NULL THEN
      RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_invalid';
    END IF;
  ELSIF approval_record.approval_kind IN ('run_execution','customer_delivery') THEN
    IF prepared_count<>0 OR enrollment_count<>0 OR approval_record.tool_call_id IS NOT NULL THEN
      RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_invalid';
    END IF;
  ELSE
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_invalid';
  END IF;
END
$$;

CREATE OR REPLACE FUNCTION agentops_enforce_approval_kind_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_append_only';
  END IF;
  IF OLD.approval_kind IS DISTINCT FROM NEW.approval_kind THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_immutable';
  END IF;
  IF OLD.approval_id IS DISTINCT FROM NEW.approval_id
    OR OLD.task_id IS DISTINCT FROM NEW.task_id
    OR OLD.run_id IS DISTINCT FROM NEW.run_id
    OR OLD.tool_call_id IS DISTINCT FROM NEW.tool_call_id
    OR OLD.requested_by_agent_id IS DISTINCT FROM NEW.requested_by_agent_id THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_binding_immutable';
  END IF;
  IF OLD.decision<>'pending' AND to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_terminal_immutable';
  END IF;
  IF OLD.decision='pending' AND NEW.decision='pending'
    AND (
      OLD.approver_user_id IS DISTINCT FROM NEW.approver_user_id
      OR OLD.decided_at IS DISTINCT FROM NEW.decided_at
    ) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_decision_state_invalid';
  END IF;
  IF OLD.decision='pending' AND NEW.decision<>'pending'
    AND (NEW.approver_user_id IS NULL OR NEW.decided_at IS NULL) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_decision_state_invalid';
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION agentops_enforce_approval_parent_binding_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  old_record JSONB;
  new_record JSONB;
BEGIN
  old_record=to_jsonb(OLD);
  new_record=to_jsonb(NEW);
  IF (
    TG_TABLE_NAME='tasks'
    AND (
      old_record->>'task_id' IS DISTINCT FROM new_record->>'task_id'
      OR old_record->>'workspace_id' IS DISTINCT FROM new_record->>'workspace_id'
    )
  ) OR (
    TG_TABLE_NAME='runs'
    AND (
      old_record->>'run_id' IS DISTINCT FROM new_record->>'run_id'
      OR old_record->>'task_id' IS DISTINCT FROM new_record->>'task_id'
      OR old_record->>'workspace_id' IS DISTINCT FROM new_record->>'workspace_id'
      OR old_record->>'agent_id' IS DISTINCT FROM new_record->>'agent_id'
    )
  ) OR (
    TG_TABLE_NAME='tool_calls'
    AND (
      old_record->>'tool_call_id' IS DISTINCT FROM new_record->>'tool_call_id'
      OR old_record->>'run_id' IS DISTINCT FROM new_record->>'run_id'
      OR old_record->>'agent_id' IS DISTINCT FROM new_record->>'agent_id'
    )
  ) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_parent_binding_immutable';
  END IF;
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION agentops_enforce_audit_log_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='audit_log_append_only';
END
$$;

CREATE OR REPLACE FUNCTION agentops_enforce_approval_kind_binding()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP='DELETE' THEN
    PERFORM agentops_assert_approval_kind_binding(OLD.approval_id);
    RETURN OLD;
  END IF;

  IF TG_OP='UPDATE' AND OLD.approval_id IS DISTINCT FROM NEW.approval_id THEN
    PERFORM agentops_assert_approval_kind_binding(OLD.approval_id);
  END IF;
  PERFORM agentops_assert_approval_kind_binding(NEW.approval_id);
  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION agentops_enforce_customer_delivery_evidence_seal()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  old_evidence_record JSONB;
  new_evidence_record JSONB;
  old_target_run_id TEXT;
  old_target_task_id TEXT;
  new_target_run_id TEXT;
  new_target_task_id TEXT;
  approval_record RECORD;
BEGIN
  IF TG_OP IN ('UPDATE','DELETE') THEN
    old_evidence_record=to_jsonb(OLD);
    old_target_run_id=NULLIF(old_evidence_record->>'run_id','');
    old_target_task_id=NULLIF(old_evidence_record->>'task_id','');
  END IF;
  IF TG_OP IN ('INSERT','UPDATE') THEN
    new_evidence_record=to_jsonb(NEW);
    new_target_run_id=NULLIF(new_evidence_record->>'run_id','');
    new_target_task_id=NULLIF(new_evidence_record->>'task_id','');
  END IF;
  FOR approval_record IN
    SELECT approval.approval_id,approval.decision
    FROM approvals approval
    JOIN runs run ON run.run_id=approval.run_id AND run.task_id=approval.task_id
    JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=run.workspace_id
    WHERE approval.approval_kind='customer_delivery'
      AND (
        (old_target_run_id IS NOT NULL AND approval.run_id=old_target_run_id)
        OR (
          old_target_run_id IS NULL
          AND old_target_task_id IS NOT NULL
          AND approval.task_id=old_target_task_id
        )
        OR (new_target_run_id IS NOT NULL AND approval.run_id=new_target_run_id)
        OR (
          new_target_run_id IS NULL
          AND new_target_task_id IS NOT NULL
          AND approval.task_id=new_target_task_id
        )
      )
    ORDER BY approval.approval_id
    FOR SHARE OF approval
  LOOP
    IF approval_record.decision<>'pending' THEN
      RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='customer_delivery_evidence_sealed';
    END IF;
  END LOOP;
  IF TG_OP='DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS approvals_kind_immutable ON approvals;
CREATE TRIGGER approvals_kind_immutable
BEFORE UPDATE OR DELETE ON approvals
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_kind_immutable();

DROP TRIGGER IF EXISTS tasks_approval_parent_binding_immutable ON tasks;
CREATE TRIGGER tasks_approval_parent_binding_immutable
BEFORE UPDATE OF task_id,workspace_id ON tasks
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_parent_binding_immutable();

DROP TRIGGER IF EXISTS runs_approval_parent_binding_immutable ON runs;
CREATE TRIGGER runs_approval_parent_binding_immutable
BEFORE UPDATE OF run_id,task_id,workspace_id,agent_id ON runs
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_parent_binding_immutable();

DROP TRIGGER IF EXISTS tool_calls_approval_parent_binding_immutable ON tool_calls;
CREATE TRIGGER tool_calls_approval_parent_binding_immutable
BEFORE UPDATE OF tool_call_id,run_id,agent_id ON tool_calls
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_parent_binding_immutable();

DROP TRIGGER IF EXISTS tool_calls_customer_delivery_evidence_sealed ON tool_calls;
CREATE TRIGGER tool_calls_customer_delivery_evidence_sealed
BEFORE INSERT OR UPDATE OR DELETE ON tool_calls
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_customer_delivery_evidence_seal();

DROP TRIGGER IF EXISTS evaluations_customer_delivery_evidence_sealed ON evaluations;
CREATE TRIGGER evaluations_customer_delivery_evidence_sealed
BEFORE INSERT OR UPDATE OR DELETE ON evaluations
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_customer_delivery_evidence_seal();

DROP TRIGGER IF EXISTS artifacts_customer_delivery_evidence_sealed ON artifacts;
CREATE TRIGGER artifacts_customer_delivery_evidence_sealed
BEFORE INSERT OR UPDATE OR DELETE ON artifacts
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_customer_delivery_evidence_seal();

DROP TRIGGER IF EXISTS manifests_customer_delivery_evidence_sealed ON plan_evidence_manifests;
CREATE TRIGGER manifests_customer_delivery_evidence_sealed
BEFORE INSERT OR UPDATE OR DELETE ON plan_evidence_manifests
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_customer_delivery_evidence_seal();

DROP TRIGGER IF EXISTS agent_plans_customer_delivery_evidence_sealed ON agent_plans;
CREATE TRIGGER agent_plans_customer_delivery_evidence_sealed
BEFORE INSERT OR UPDATE OR DELETE ON agent_plans
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_customer_delivery_evidence_seal();

DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs;
CREATE TRIGGER audit_logs_append_only
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_audit_log_append_only();

DROP TRIGGER IF EXISTS approvals_kind_binding_enforced ON approvals;
CREATE CONSTRAINT TRIGGER approvals_kind_binding_enforced
AFTER INSERT OR UPDATE OR DELETE ON approvals
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_kind_binding();

DROP TRIGGER IF EXISTS prepared_actions_kind_binding_enforced ON prepared_actions;
CREATE CONSTRAINT TRIGGER prepared_actions_kind_binding_enforced
AFTER INSERT OR UPDATE OR DELETE ON prepared_actions
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_kind_binding();

DROP TRIGGER IF EXISTS enrollment_requests_kind_binding_enforced ON agent_gateway_enrollment_requests;
CREATE CONSTRAINT TRIGGER enrollment_requests_kind_binding_enforced
AFTER INSERT OR UPDATE OR DELETE ON agent_gateway_enrollment_requests
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_kind_binding();

DO $$
DECLARE
  approval_record RECORD;
BEGIN
  IF EXISTS (
    SELECT 1
    FROM prepared_actions action
    LEFT JOIN approvals approval ON approval.approval_id=action.approval_id
    WHERE action.approval_id IS NOT NULL AND approval.approval_id IS NULL
  ) OR EXISTS (
    SELECT 1
    FROM agent_gateway_enrollment_requests request
    LEFT JOIN approvals approval ON approval.approval_id=request.approval_id
    WHERE approval.approval_id IS NULL
  ) THEN
    RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='approval_kind_binding_orphaned';
  END IF;

  FOR approval_record IN SELECT approval_id FROM approvals LOOP
    PERFORM agentops_assert_approval_kind_binding(approval_record.approval_id);
  END LOOP;
END
$$;
