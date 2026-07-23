import type { PoolClient } from "pg";

const SHA256_HEX = /^[a-f0-9]{64}$/;

type PreparedActionCheckpointRow = {
  action_id: string;
  action_hash: string;
  action_workspace_id: string;
  action_task_id: string;
  action_run_id: string;
  action_tool_call_id: string | null;
  action_agent_id: string;
  action_status: string;
  action_approved_at: string | null;
  action_consumed_at: string | null;
  action_side_effect_id: string | null;
  action_expires_at: string | null;
  approval_id: string;
  approval_task_id: string;
  approval_run_id: string;
  approval_tool_call_id: string | null;
  approval_agent_id: string | null;
  approval_decision: string;
  approval_approver_user_id: string | null;
  approval_decided_at: string | null;
  approval_expires_at: string | null;
  lease_id: string;
  lease_action_id: string;
  lease_workspace_id: string;
  lease_agent_id: string;
  lease_action_hash: string;
  lease_status: string;
  lease_started_at: string;
  lease_expires_at: string;
  lease_completed_at: string | null;
  lease_failure_reason: string | null;
  tool_call_id: string;
  tool_run_id: string;
  tool_agent_id: string;
  tool_status: string;
  tool_side_effect_id: string | null;
  tool_ended_at: string | null;
};

export type PlanEvidenceExecutionCheckpoint =
  | {
      kind: "terminal_run_v1";
      valid: true;
      prepared_action_id: null;
      execution_lease_id: null;
      active_tool_call_id: null;
      action_hash: null;
      failed_reason: null;
    }
  | {
      kind: "prepared_action_execution_v1";
      valid: true;
      prepared_action_id: string;
      execution_lease_id: string;
      active_tool_call_id: string;
      action_hash: string;
      failed_reason: null;
    }
  | {
      kind: "invalid";
      valid: false;
      prepared_action_id: null;
      execution_lease_id: null;
      active_tool_call_id: null;
      action_hash: null;
      failed_reason: string;
    };

function invalidCheckpoint(failedReason: string): PlanEvidenceExecutionCheckpoint {
  return {
    kind: "invalid",
    valid: false,
    prepared_action_id: null,
    execution_lease_id: null,
    active_tool_call_id: null,
    action_hash: null,
    failed_reason: failedReason,
  };
}

function timestamp(value: string | null) {
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? parsed : null;
}

export async function resolvePlanEvidenceExecutionCheckpoint(
  client: PoolClient,
  input: {
    workspaceId: string;
    taskId: string;
    runId: string;
    agentId: string;
    taskOwnerAgentId: string | null;
    taskStatus: string;
    runStatus: string;
  },
): Promise<PlanEvidenceExecutionCheckpoint> {
  if (input.runStatus === "completed") {
    return {
      kind: "terminal_run_v1",
      valid: true,
      prepared_action_id: null,
      execution_lease_id: null,
      active_tool_call_id: null,
      action_hash: null,
      failed_reason: null,
    };
  }
  if (
    input.runStatus !== "running"
    || input.taskStatus !== "running"
    || input.taskOwnerAgentId !== input.agentId
  ) {
    return invalidCheckpoint("run_or_assignment_not_at_evidence_checkpoint");
  }

  const result = await client.query<PreparedActionCheckpointRow>(
    `SELECT
      action.action_id,
      action.action_hash,
      action.workspace_id AS action_workspace_id,
      action.task_id AS action_task_id,
      action.run_id AS action_run_id,
      action.tool_call_id AS action_tool_call_id,
      action.requested_by_agent_id AS action_agent_id,
      action.status AS action_status,
      action.approved_at AS action_approved_at,
      action.consumed_at AS action_consumed_at,
      action.provider_side_effect_id AS action_side_effect_id,
      action.expires_at AS action_expires_at,
      approval.approval_id,
      approval.task_id AS approval_task_id,
      approval.run_id AS approval_run_id,
      approval.tool_call_id AS approval_tool_call_id,
      approval.requested_by_agent_id AS approval_agent_id,
      approval.decision AS approval_decision,
      approval.approver_user_id AS approval_approver_user_id,
      approval.decided_at AS approval_decided_at,
      approval.expires_at AS approval_expires_at,
      lease.lease_id,
      lease.action_id AS lease_action_id,
      lease.workspace_id AS lease_workspace_id,
      lease.requested_by_agent_id AS lease_agent_id,
      lease.action_hash AS lease_action_hash,
      lease.status AS lease_status,
      lease.started_at AS lease_started_at,
      lease.expires_at AS lease_expires_at,
      lease.completed_at AS lease_completed_at,
      lease.failure_reason AS lease_failure_reason,
      tool.tool_call_id,
      tool.run_id AS tool_run_id,
      tool.agent_id AS tool_agent_id,
      tool.status AS tool_status,
      tool.side_effect_id AS tool_side_effect_id,
      tool.ended_at AS tool_ended_at
    FROM prepared_actions action
    JOIN approvals approval ON approval.approval_id=action.approval_id
    JOIN prepared_action_execution_leases lease
      ON lease.action_id=action.action_id
    JOIN tool_calls tool ON tool.tool_call_id=action.tool_call_id
    WHERE action.workspace_id=$1
      AND action.task_id=$2
      AND action.run_id=$3
      AND action.requested_by_agent_id=$4
      AND action.status='approved'
      AND approval.decision='approved'
      AND lease.status='executing'
    ORDER BY action.created_at,action.action_id
    FOR SHARE OF action,approval,lease,tool`,
    [input.workspaceId, input.taskId, input.runId, input.agentId],
  );
  if (result.rows.length !== 1) {
    return invalidCheckpoint("active_prepared_action_count_invalid");
  }

  const row = result.rows[0];
  const now = Date.now();
  const actionExpiry = timestamp(row.action_expires_at);
  const approvalExpiry = timestamp(row.approval_expires_at);
  const leaseStartedAt = timestamp(row.lease_started_at);
  const leaseExpiry = timestamp(row.lease_expires_at);
  if (
    row.action_workspace_id !== input.workspaceId
    || row.action_task_id !== input.taskId
    || row.action_run_id !== input.runId
    || row.action_agent_id !== input.agentId
    || row.action_status !== "approved"
    || !row.action_tool_call_id
    || !row.action_approved_at
    || row.action_consumed_at !== null
    || row.action_side_effect_id !== null
    || row.approval_task_id !== input.taskId
    || row.approval_run_id !== input.runId
    || row.approval_tool_call_id !== row.action_tool_call_id
    || row.approval_agent_id !== input.agentId
    || row.approval_decision !== "approved"
    || !row.approval_approver_user_id
    || !row.approval_decided_at
    || row.lease_action_id !== row.action_id
    || row.lease_workspace_id !== input.workspaceId
    || row.lease_agent_id !== input.agentId
    || row.lease_action_hash !== row.action_hash
    || row.lease_status !== "executing"
    || row.lease_completed_at !== null
    || row.lease_failure_reason !== null
    || row.tool_call_id !== row.action_tool_call_id
    || row.tool_run_id !== input.runId
    || row.tool_agent_id !== input.agentId
    || row.tool_status !== "running"
    || row.tool_side_effect_id !== null
    || row.tool_ended_at !== null
    || !SHA256_HEX.test(row.action_hash)
    || actionExpiry === null
    || approvalExpiry === null
    || leaseStartedAt === null
    || leaseExpiry === null
    || actionExpiry <= now
    || approvalExpiry <= now
    || leaseExpiry <= now
    || leaseStartedAt >= leaseExpiry
  ) {
    return invalidCheckpoint("prepared_action_execution_binding_invalid");
  }

  return {
    kind: "prepared_action_execution_v1",
    valid: true,
    prepared_action_id: row.action_id,
    execution_lease_id: row.lease_id,
    active_tool_call_id: row.tool_call_id,
    action_hash: row.action_hash,
    failed_reason: null,
  };
}
