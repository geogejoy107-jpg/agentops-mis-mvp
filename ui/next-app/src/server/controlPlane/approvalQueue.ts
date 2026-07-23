import { withPostgresTransaction } from "./db";
import { authenticateHumanMember } from "./humanSession";
import { ControlPlaneHttpError } from "./http";

type ApprovalDecision = "pending" | "approved" | "rejected" | "expired";

type ApprovalQueueRow = {
  approval_id: string;
  approval_kind: "customer_delivery" | "prepared_action";
  task_id: string;
  run_id: string;
  tool_call_id: string | null;
  requested_by_agent_id: string | null;
  approver_user_id: string | null;
  decision: ApprovalDecision;
  reason: string | null;
  expires_at: string | null;
  created_at: string;
  decided_at: string | null;
  task_status: string;
  run_status: string;
  run_agent_id: string;
  runtime_type: string;
  model_provider: string | null;
  action_id: string | null;
  action_tool_call_id: string | null;
  action_type: string | null;
  target_resource: string | null;
  risk_level: string | null;
  policy_version: string | null;
  action_hash: string | null;
  prepared_action_status: string | null;
  provider_side_effect_id: string | null;
};

function decisionFilter(value: unknown): ApprovalDecision | null {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (!normalized) return null;
  if (
    normalized === "pending"
    || normalized === "approved"
    || normalized === "rejected"
    || normalized === "expired"
  ) {
    return normalized;
  }
  throw new ControlPlaneHttpError(
    400,
    "approval_decision_filter_invalid",
    "Approval decision filter must be pending, approved, rejected, or expired.",
  );
}

function boundedLimit(value: unknown) {
  const normalized = String(value ?? "").trim();
  if (!normalized) return 200;
  if (!/^[1-9][0-9]{0,2}$/.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      "approval_limit_invalid",
      "Approval limit must be an integer between 1 and 200.",
    );
  }
  const parsed = Number(normalized);
  if (parsed > 200) {
    throw new ControlPlaneHttpError(
      400,
      "approval_limit_invalid",
      "Approval limit must be an integer between 1 and 200.",
    );
  }
  return parsed;
}

function publicApproval(row: ApprovalQueueRow) {
  const preparedAction = row.approval_kind === "prepared_action";
  if (
    row.requested_by_agent_id !== row.run_agent_id
    || (
      preparedAction
      && (
        !row.tool_call_id
        || !row.action_id
        || row.action_tool_call_id !== row.tool_call_id
        || !row.action_type
        || !row.risk_level
        || !row.policy_version
        || !row.action_hash
        || !row.prepared_action_status
      )
    )
    || (
      !preparedAction
      && (
        row.tool_call_id !== null
        || row.action_id !== null
      )
    )
  ) {
    throw new ControlPlaneHttpError(
      409,
      "approval_binding_invalid",
      "Approval workspace, task, run, Agent, or PreparedAction binding is invalid.",
    );
  }

  return {
    approval_id: row.approval_id,
    approval_kind: row.approval_kind,
    task_id: row.task_id,
    run_id: row.run_id,
    tool_call_id: row.tool_call_id,
    requested_by_agent_id: row.requested_by_agent_id,
    approver_user_id: row.approver_user_id,
    decision: row.decision,
    reason: row.reason,
    expires_at: row.expires_at,
    created_at: row.created_at,
    decided_at: row.decided_at,
    task_status: row.task_status,
    run_status: row.run_status,
    runtime_type: row.runtime_type,
    model_provider: row.model_provider,
    prepared_action: preparedAction
      ? {
        action_id: row.action_id,
        action_type: row.action_type,
        target_resource: row.target_resource,
        risk_level: row.risk_level,
        policy_version: row.policy_version,
        action_hash: row.action_hash,
        status: row.prepared_action_status,
        provider_side_effect_id: row.provider_side_effect_id,
      }
      : null,
    review_supported: true,
    normalized_args_omitted: true,
    checkpoint_omitted: true,
    credentials_omitted: true,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    raw_provider_output_omitted: true,
    token_omitted: true,
  };
}

export async function listWorkspaceApprovals(
  headers: Headers,
  workspaceId: unknown,
  rawDecision?: unknown,
  rawLimit?: unknown,
) {
  const decision = decisionFilter(rawDecision);
  const limit = boundedLimit(rawLimit);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(
      client,
      headers,
      workspaceId,
    );
    const rows = await client.query<ApprovalQueueRow>(
      `SELECT
        approval.approval_id,
        approval.approval_kind,
        approval.task_id,
        approval.run_id,
        approval.tool_call_id,
        approval.requested_by_agent_id,
        approval.approver_user_id,
        approval.decision,
        approval.reason,
        approval.expires_at,
        approval.created_at,
        approval.decided_at,
        task.status AS task_status,
        run.status AS run_status,
        run.agent_id AS run_agent_id,
        run.runtime_type,
        run.model_provider,
        action.action_id,
        action.tool_call_id AS action_tool_call_id,
        action.action_type,
        action.target_resource,
        action.risk_level,
        action.policy_version,
        action.action_hash,
        action.status AS prepared_action_status,
        action.provider_side_effect_id
      FROM approvals approval
      JOIN tasks task
        ON task.task_id=approval.task_id
        AND task.workspace_id=$1
      JOIN runs run
        ON run.run_id=approval.run_id
        AND run.task_id=task.task_id
        AND run.workspace_id=task.workspace_id
      LEFT JOIN prepared_actions action
        ON action.approval_id=approval.approval_id
        AND action.workspace_id=task.workspace_id
        AND action.task_id=task.task_id
        AND action.run_id=run.run_id
        AND action.tool_call_id=approval.tool_call_id
      WHERE approval.approval_kind IN ('customer_delivery','prepared_action')
        AND ($2::text IS NULL OR approval.decision=$2)
      ORDER BY
        CASE approval.decision
          WHEN 'pending' THEN 0
          WHEN 'approved' THEN 1
          WHEN 'rejected' THEN 2
          ELSE 3
        END,
        approval.created_at DESC,
        approval.approval_id
      LIMIT $3`,
      [identity.workspaceId, decision, limit],
    );
    return {
      status: 200,
      body: rows.rows.map(publicApproval),
    };
  });
}
