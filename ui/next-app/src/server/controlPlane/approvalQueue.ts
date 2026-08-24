import { withPostgresTransaction } from "./db";
import { authenticateHumanMember } from "./humanSession";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, stableHash } from "./ledger";
import {
  assertActiveApprovalReadEntitlement,
  assertApprovalReadRole,
  boundedApprovalReadText,
  boundedApprovalReadTimestamp,
} from "./approvalReadBoundary";

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
  risk_level: string | null;
  policy_version: string | null;
  action_hash: string | null;
  prepared_action_status: string | null;
};

function decisionFilter(value: unknown): ApprovalDecision | null {
  if (value === undefined || value === null || value === "") return null;
  const normalized = String(value);
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
  if (value === undefined || value === null || value === "") return 200;
  const normalized = String(value);
  if (!/^(?:[1-9]|[1-9][0-9]|1[0-9]{2}|200)$/.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      "approval_limit_invalid",
      "Approval limit must be an integer between 1 and 200.",
    );
  }
  const parsed = Number(normalized);
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
    approval_id: boundedApprovalReadText(row.approval_id, "approval_id", 128),
    approval_kind: boundedApprovalReadText(
      row.approval_kind,
      "approval_kind",
      32,
    ),
    task_id: boundedApprovalReadText(row.task_id, "task_id", 128),
    run_id: boundedApprovalReadText(row.run_id, "run_id", 128),
    tool_call_id: boundedApprovalReadText(
      row.tool_call_id,
      "tool_call_id",
      128,
      true,
    ),
    requested_by_agent_id: boundedApprovalReadText(
      row.requested_by_agent_id,
      "requested_by_agent_id",
      128,
      true,
    ),
    approver_user_id: boundedApprovalReadText(
      row.approver_user_id,
      "approver_user_id",
      128,
      true,
    ),
    decision: boundedApprovalReadText(row.decision, "decision", 32),
    expires_at: boundedApprovalReadTimestamp(row.expires_at, "expires_at", true),
    created_at: boundedApprovalReadTimestamp(row.created_at, "created_at"),
    decided_at: boundedApprovalReadTimestamp(row.decided_at, "decided_at", true),
    task_status: boundedApprovalReadText(row.task_status, "task_status", 64),
    run_status: boundedApprovalReadText(row.run_status, "run_status", 64),
    runtime_type: boundedApprovalReadText(row.runtime_type, "runtime_type", 64),
    model_provider: boundedApprovalReadText(
      row.model_provider,
      "model_provider",
      128,
      true,
    ),
    prepared_action: preparedAction
      ? {
        action_id: boundedApprovalReadText(row.action_id, "action_id", 128),
        action_type: boundedApprovalReadText(row.action_type, "action_type", 128),
        risk_level: boundedApprovalReadText(row.risk_level, "risk_level", 32),
        policy_version: boundedApprovalReadText(
          row.policy_version,
          "policy_version",
          128,
        ),
        action_hash: boundedApprovalReadText(row.action_hash, "action_hash", 128),
        status: boundedApprovalReadText(
          row.prepared_action_status,
          "prepared_action_status",
          64,
        ),
      }
      : null,
    review_supported: true,
    normalized_args_omitted: true,
    checkpoint_omitted: true,
    credentials_omitted: true,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    raw_provider_output_omitted: true,
    reason_omitted: true,
    target_resource_omitted: true,
    provider_side_effect_id_omitted: true,
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
    const role = assertApprovalReadRole(identity);
    await assertActiveApprovalReadEntitlement(client, identity.workspaceId);
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
        action.risk_level,
        action.policy_version,
        action.action_hash,
        action.status AS prepared_action_status
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
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "user",
      actorId: identity.userId,
      action: "human.approval_collection_read",
      entityType: "approvals",
      entityId: identity.workspaceId,
      metadata: {
        membership_role: role,
        decision_filter: decision,
        result_limit: limit,
        result_count: rows.rows.length,
        route: "GET /api/mis/approvals",
        sensitive_fields_omitted: true,
        session_credential_omitted: true,
        token_omitted: true,
      },
      requestHash: stableHash({
        workspace_id: identity.workspaceId,
        user_id: identity.userId,
        decision,
        limit,
        operation: "human.approval_collection_read",
      }),
    });
    return {
      status: 200,
      body: rows.rows.map(publicApproval),
    };
  });
}
