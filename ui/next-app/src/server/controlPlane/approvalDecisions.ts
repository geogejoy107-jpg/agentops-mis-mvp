import type { PoolClient } from "pg";

import { verifyLatestWorkspacePlanEvidence } from "./agentGatewayPlans";
import { withPostgresTransaction } from "./db";
import {
  authenticateHumanReviewer,
  opaqueReference,
  rejectMachineCredentials,
  validateWriteOrigin,
  type HumanSessionIdentity,
} from "./humanSession";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, appendRuntimeEvent, stableHash } from "./ledger";

type ApprovalDecision = "approved" | "rejected";
type ApprovalKind =
  | "run_execution"
  | "tool_execution"
  | "prepared_action"
  | "agent_enrollment"
  | "customer_delivery";

type TaskRow = {
  task_id: string;
  workspace_id: string;
  status: string;
  updated_at: string;
};

type RunRow = {
  run_id: string;
  workspace_id: string;
  task_id: string;
  agent_id: string;
  status: string;
  approval_required: number;
  ended_at: string | null;
  error_type: string | null;
  error_message: string | null;
};

type ApprovalRow = {
  approval_id: string;
  approval_kind: ApprovalKind;
  task_id: string;
  run_id: string;
  tool_call_id: string | null;
  requested_by_agent_id: string | null;
  approver_user_id: string | null;
  decision: string;
  expires_at: string | null;
  created_at: string;
  decided_at: string | null;
};

type ToolCallRow = {
  tool_call_id: string;
  run_id: string;
  agent_id: string;
  risk_level: string;
  status: string;
  ended_at: string | null;
};

type PreparedActionRow = {
  prepared_action_id: string;
  workspace_id: string;
  task_id: string;
  run_id: string;
  tool_call_id: string;
  approval_id: string | null;
  requested_by_agent_id: string | null;
  status: string;
  updated_at: string;
  approved_at: string | null;
};

type EnrollmentRow = {
  request_id: string;
  approval_id: string;
  task_id: string;
  run_id: string;
  workspace_id: string;
  agent_id: string;
  status: string;
  updated_at: string;
  decided_at: string | null;
};

type IdempotencyRow = {
  workspace_id: string;
  user_id: string;
  idempotency_key_hash: string;
  request_hash: string;
  approval_id: string;
  decision: string;
  status: string;
  created_at: string;
  completed_at: string | null;
};

type LockedApprovalGraph = {
  task: TaskRow;
  run: RunRow;
  approval: ApprovalRow;
  toolCall: ToolCallRow | null;
  preparedAction: PreparedActionRow | null;
  enrollment: EnrollmentRow | null;
};

function identifier(value: unknown, field: string) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(400, `${field}_invalid`, `${field} must use 1-128 safe identifier characters.`);
  }
  return normalized;
}

function decision(value: unknown): ApprovalDecision {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "approve") return "approved";
  if (normalized === "reject") return "rejected";
  throw new ControlPlaneHttpError(404, "approval_decision_not_found", "Approval decision route was not found.");
}

function idempotencyKey(headers: Headers) {
  const value = String(headers.get("idempotency-key") || "").trim();
  if (!/^[A-Za-z0-9._:-]{16,128}$/.test(value)) {
    throw new ControlPlaneHttpError(
      400,
      "idempotency_key_required",
      "Idempotency-Key must use 16-128 safe identifier characters.",
    );
  }
  return value;
}

function taskSnapshot(row: TaskRow) {
  return { task_id: row.task_id, workspace_id: row.workspace_id, status: row.status, updated_at: row.updated_at };
}

function runSnapshot(row: RunRow) {
  return {
    run_id: row.run_id,
    workspace_id: row.workspace_id,
    task_id: row.task_id,
    agent_id: row.agent_id,
    status: row.status,
    approval_required: Boolean(row.approval_required),
    ended_at: row.ended_at,
    error_type: row.error_type,
  };
}

function approvalSnapshot(row: ApprovalRow) {
  return {
    approval_id: row.approval_id,
    approval_kind: row.approval_kind,
    task_id: row.task_id,
    run_id: row.run_id,
    tool_call_id: row.tool_call_id,
    requested_by_agent_id: row.requested_by_agent_id,
    approver_user_id: row.approver_user_id,
    decision: row.decision,
    expires_at: row.expires_at,
    decided_at: row.decided_at,
  };
}

function toolSnapshot(row: ToolCallRow) {
  return {
    tool_call_id: row.tool_call_id,
    run_id: row.run_id,
    agent_id: row.agent_id,
    risk_level: row.risk_level,
    status: row.status,
    ended_at: row.ended_at,
  };
}

function preparedActionSnapshot(row: PreparedActionRow) {
  return {
    prepared_action_id: row.prepared_action_id,
    workspace_id: row.workspace_id,
    task_id: row.task_id,
    run_id: row.run_id,
    tool_call_id: row.tool_call_id,
    approval_id: row.approval_id,
    status: row.status,
    updated_at: row.updated_at,
    approved_at: row.approved_at,
  };
}

function enrollmentSnapshot(row: EnrollmentRow) {
  return {
    request_id: row.request_id,
    approval_id: row.approval_id,
    task_id: row.task_id,
    run_id: row.run_id,
    workspace_id: row.workspace_id,
    agent_id: row.agent_id,
    status: row.status,
    updated_at: row.updated_at,
    decided_at: row.decided_at,
  };
}

function publicApproval(row: ApprovalRow) {
  return {
    ...approvalSnapshot(row),
    created_at: row.created_at,
  };
}

function approvalExpired(row: ApprovalRow) {
  if (!row.expires_at) return false;
  const expiresAt = Date.parse(row.expires_at);
  if (!Number.isFinite(expiresAt)) {
    throw new ControlPlaneHttpError(503, "approval_state_invalid", "Approval expiry state is invalid.");
  }
  return expiresAt <= Date.now();
}

function hiddenApproval(): never {
  throw new ControlPlaneHttpError(404, "approval_not_found", "Approval was not found in this workspace.");
}

async function lockApprovalGraph(
  client: PoolClient,
  workspaceId: string,
  approvalId: string,
): Promise<LockedApprovalGraph> {
  const hintResult = await client.query<Pick<ApprovalRow, "task_id" | "run_id" | "tool_call_id">>(
    `SELECT approval.task_id,approval.run_id,approval.tool_call_id
    FROM approvals approval
    JOIN runs run ON run.run_id=approval.run_id
      AND run.task_id=approval.task_id AND run.workspace_id=$2
    JOIN tasks task ON task.task_id=approval.task_id AND task.workspace_id=$2
    WHERE approval.approval_id=$1`,
    [approvalId, workspaceId],
  );
  const hint = hintResult.rows[0];
  if (!hint) return hiddenApproval();

  await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-task:${hint.task_id}`]);
  const taskResult = await client.query<TaskRow>(
    `SELECT task_id,workspace_id,status,updated_at FROM tasks
    WHERE task_id=$1 AND workspace_id=$2 FOR UPDATE`,
    [hint.task_id, workspaceId],
  );
  const task = taskResult.rows[0];
  if (!task) return hiddenApproval();

  await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-run:${hint.run_id}`]);
  const runResult = await client.query<RunRow>(
    `SELECT run_id,workspace_id,task_id,agent_id,status,approval_required,ended_at,error_type,error_message
    FROM runs WHERE run_id=$1 AND task_id=$2 AND workspace_id=$3 FOR UPDATE`,
    [hint.run_id, hint.task_id, workspaceId],
  );
  const run = runResult.rows[0];
  if (!run) return hiddenApproval();

  let toolCall: ToolCallRow | null = null;
  if (hint.tool_call_id) {
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [
      `agentops-tool-call:${hint.tool_call_id}`,
    ]);
    const toolResult = await client.query<ToolCallRow>(
      `SELECT tool_call_id,run_id,agent_id,risk_level,status,ended_at FROM tool_calls
      WHERE tool_call_id=$1 AND run_id=$2 AND agent_id=$3 FOR UPDATE`,
      [hint.tool_call_id, run.run_id, run.agent_id],
    );
    toolCall = toolResult.rows[0] || null;
    if (!toolCall) throw new ControlPlaneHttpError(409, "approval_binding_invalid", "Approval tool binding is invalid.");
  }

  await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [
    `agentops-approval:${workspaceId}:${approvalId}`,
  ]);
  const approvalResult = await client.query<ApprovalRow>(
    `SELECT approval_id,approval_kind,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,
    decision,expires_at,created_at,decided_at
    FROM approvals WHERE approval_id=$1 FOR UPDATE`,
    [approvalId],
  );
  const approval = approvalResult.rows[0];
  if (!approval) return hiddenApproval();
  if (approval.task_id !== task.task_id
    || approval.run_id !== run.run_id
    || approval.tool_call_id !== (toolCall?.tool_call_id || null)
    || (approval.requested_by_agent_id && approval.requested_by_agent_id !== run.agent_id)) {
    throw new ControlPlaneHttpError(409, "approval_binding_invalid", "Approval parent binding is invalid.");
  }

  const preparedResult = await client.query<PreparedActionRow>(
    `SELECT prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,
    requested_by_agent_id,status,updated_at,approved_at
    FROM prepared_actions WHERE approval_id=$1
    ORDER BY prepared_action_id LIMIT 2 FOR UPDATE`,
    [approvalId],
  );
  if (preparedResult.rows.length > 1) {
    throw new ControlPlaneHttpError(409, "approval_binding_invalid", "Approval has multiple prepared-action bindings.");
  }
  const preparedAction = preparedResult.rows[0] || null;
  if (preparedAction) {
    if (!preparedAction
      || preparedAction.workspace_id !== workspaceId
      || preparedAction.task_id !== task.task_id
      || preparedAction.run_id !== run.run_id
      || preparedAction.tool_call_id !== toolCall?.tool_call_id
      || preparedAction.approval_id !== approval.approval_id
      || (preparedAction.requested_by_agent_id && preparedAction.requested_by_agent_id !== run.agent_id)) {
      throw new ControlPlaneHttpError(409, "approval_binding_invalid", "Prepared-action tenant binding is invalid.");
    }
  }

  const enrollmentResult = await client.query<EnrollmentRow>(
    `SELECT request_id,approval_id,task_id,run_id,workspace_id,agent_id,status,updated_at,decided_at
    FROM agent_gateway_enrollment_requests WHERE approval_id=$1
    ORDER BY request_id FOR UPDATE`,
    [approvalId],
  );
  if (enrollmentResult.rows.length > 1 || (preparedAction && enrollmentResult.rows.length)) {
    throw new ControlPlaneHttpError(409, "approval_binding_invalid", "Approval has conflicting linked workflows.");
  }
  const enrollment = enrollmentResult.rows[0] || null;
  if (enrollment
    && (enrollment.workspace_id !== workspaceId
      || enrollment.task_id !== task.task_id
      || enrollment.run_id !== run.run_id
      || enrollment.agent_id !== run.agent_id)) {
    throw new ControlPlaneHttpError(409, "approval_binding_invalid", "Enrollment tenant binding is invalid.");
  }
  const kindBindingValid = approval.approval_kind === "prepared_action"
    ? Boolean(toolCall && preparedAction && !enrollment)
    : approval.approval_kind === "agent_enrollment"
      ? Boolean(!toolCall && !preparedAction && enrollment)
      : approval.approval_kind === "tool_execution"
        ? Boolean(toolCall && !preparedAction && !enrollment)
        : ["run_execution", "customer_delivery"].includes(approval.approval_kind)
          ? Boolean(!toolCall && !preparedAction && !enrollment)
          : false;
  if (!kindBindingValid) {
    throw new ControlPlaneHttpError(409, "approval_binding_invalid", "Approval kind binding is invalid.");
  }
  return { task, run, approval, toolCall, preparedAction, enrollment };
}

function response(graph: LockedApprovalGraph, outcome: "updated" | "unchanged") {
  return {
    status: 200,
    body: {
      ok: true,
      provider: "agentops-human-approval-decision",
      control_plane: "typescript_postgres",
      operation: "approval_decision",
      outcome,
      decision: graph.approval.decision,
      approval: publicApproval(graph.approval),
      linked_state: {
        task_status: graph.task.status,
        run_status: graph.run.status,
        tool_call_status: graph.toolCall?.status || null,
        prepared_action_status: graph.preparedAction?.status || null,
        enrollment_status: graph.enrollment?.status || null,
      },
      credentials_omitted: true,
      raw_body_omitted: true,
      token_omitted: true,
    },
  };
}

async function updateLinkedState(
  client: PoolClient,
  identity: HumanSessionIdentity,
  graph: LockedApprovalGraph,
  requestedDecision: ApprovalDecision,
  now: string,
) {
  let toolAfter = graph.toolCall;
  let preparedAfter = graph.preparedAction;
  let enrollmentAfter = graph.enrollment;

  if (graph.toolCall) {
    const targetStatus = requestedDecision === "approved" ? "planned" : "blocked";
    const toolUpdate = await client.query<ToolCallRow>(
      `UPDATE tool_calls SET status=$1,ended_at=CASE WHEN $1='blocked' THEN COALESCE(ended_at,$2) ELSE NULL END
      WHERE tool_call_id=$3 AND run_id=$4 AND agent_id=$5 AND status='waiting_approval'
      RETURNING tool_call_id,run_id,agent_id,risk_level,status,ended_at`,
      [targetStatus, now, graph.toolCall.tool_call_id, graph.run.run_id, graph.run.agent_id],
    );
    toolAfter = toolUpdate.rows[0] || null;
    if (!toolAfter) {
      throw new ControlPlaneHttpError(409, "approval_linked_state_conflict", "Tool call is no longer waiting for this approval.");
    }
  }

  if (graph.preparedAction) {
    const targetStatus = requestedDecision === "approved" ? "approved" : "rejected";
    const preparedUpdate = await client.query<PreparedActionRow>(
      `UPDATE prepared_actions
      SET status=$1,updated_at=$2,approved_at=CASE WHEN $1='approved' THEN COALESCE(approved_at,$2) ELSE approved_at END
      WHERE prepared_action_id=$3 AND workspace_id=$4 AND approval_id=$5
        AND status IN ('prepared','waiting_approval')
      RETURNING prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,
        requested_by_agent_id,status,updated_at,approved_at`,
      [targetStatus, now, graph.preparedAction.prepared_action_id, identity.workspaceId, graph.approval.approval_id],
    );
    preparedAfter = preparedUpdate.rows[0] || null;
    if (!preparedAfter) {
      throw new ControlPlaneHttpError(409, "approval_linked_state_conflict", "Prepared action is no longer waiting for this approval.");
    }
  }

  if (graph.enrollment) {
    const targetStatus = requestedDecision === "approved" ? "approved" : "rejected";
    const enrollmentUpdate = await client.query<EnrollmentRow>(
      `UPDATE agent_gateway_enrollment_requests SET status=$1,decided_at=$2,updated_at=$2
      WHERE request_id=$3 AND workspace_id=$4 AND approval_id=$5 AND status='pending'
      RETURNING request_id,approval_id,task_id,run_id,workspace_id,agent_id,status,updated_at,decided_at`,
      [targetStatus, now, graph.enrollment.request_id, identity.workspaceId, graph.approval.approval_id],
    );
    enrollmentAfter = enrollmentUpdate.rows[0] || null;
    if (!enrollmentAfter) {
      throw new ControlPlaneHttpError(409, "approval_linked_state_conflict", "Enrollment is no longer waiting for this approval.");
    }
  }

  const remainingResult = await client.query<{ count: number }>(
    `SELECT COUNT(*)::int AS count FROM approvals approval
    JOIN tasks task ON task.task_id=approval.task_id
    JOIN runs run ON run.run_id=approval.run_id AND run.task_id=task.task_id
    WHERE approval.run_id=$1 AND approval.decision='pending'
      AND task.workspace_id=$2 AND run.workspace_id=$2`,
    [graph.run.run_id, identity.workspaceId],
  );
  const remaining = Number(remainingResult.rows[0]?.count || 0);
  let runAfter: RunRow;
  let taskAfter: TaskRow;
  if (requestedDecision === "rejected" && graph.approval.approval_kind === "customer_delivery") {
    const runUpdate = await client.query<RunRow>(
      `UPDATE runs SET approval_required=CASE WHEN $1>0 THEN 1 ELSE 0 END
      WHERE run_id=$2 AND task_id=$3 AND workspace_id=$4
      RETURNING run_id,workspace_id,task_id,agent_id,status,approval_required,ended_at,error_type,error_message`,
      [remaining, graph.run.run_id, graph.task.task_id, identity.workspaceId],
    );
    const taskUpdate = await client.query<TaskRow>(
      `UPDATE tasks SET status='blocked',updated_at=$1 WHERE task_id=$2 AND workspace_id=$3
      RETURNING task_id,workspace_id,status,updated_at`,
      [now, graph.task.task_id, identity.workspaceId],
    );
    runAfter = runUpdate.rows[0];
    taskAfter = taskUpdate.rows[0];
  } else if (requestedDecision === "rejected") {
    const runUpdate = await client.query<RunRow>(
      `UPDATE runs SET status='blocked',approval_required=0,ended_at=COALESCE(ended_at,$1),
      error_type='ApprovalRejected',error_message='A required human approval was rejected.'
      WHERE run_id=$2 AND task_id=$3 AND workspace_id=$4
      RETURNING run_id,workspace_id,task_id,agent_id,status,approval_required,ended_at,error_type,error_message`,
      [now, graph.run.run_id, graph.task.task_id, identity.workspaceId],
    );
    const taskUpdate = await client.query<TaskRow>(
      `UPDATE tasks SET status='blocked',updated_at=$1 WHERE task_id=$2 AND workspace_id=$3
      RETURNING task_id,workspace_id,status,updated_at`,
      [now, graph.task.task_id, identity.workspaceId],
    );
    runAfter = runUpdate.rows[0];
    taskAfter = taskUpdate.rows[0];
  } else if (graph.enrollment) {
    const runUpdate = await client.query<RunRow>(
      `UPDATE runs SET status=CASE WHEN status='waiting_approval' AND $1=0 THEN 'completed' ELSE status END,
      approval_required=CASE WHEN $1>0 THEN 1 ELSE 0 END,
      ended_at=CASE WHEN status='waiting_approval' AND $1=0 THEN COALESCE(ended_at,$2) ELSE ended_at END
      WHERE run_id=$3 AND task_id=$4 AND workspace_id=$5
      RETURNING run_id,workspace_id,task_id,agent_id,status,approval_required,ended_at,error_type,error_message`,
      [remaining, now, graph.run.run_id, graph.task.task_id, identity.workspaceId],
    );
    const taskUpdate = await client.query<TaskRow>(
      `UPDATE tasks SET status=CASE WHEN status='waiting_approval' AND $1=0 THEN 'completed' ELSE status END,updated_at=$2
      WHERE task_id=$3 AND workspace_id=$4 RETURNING task_id,workspace_id,status,updated_at`,
      [remaining, now, graph.task.task_id, identity.workspaceId],
    );
    runAfter = runUpdate.rows[0];
    taskAfter = taskUpdate.rows[0];
  } else if (graph.preparedAction) {
    const runUpdate = await client.query<RunRow>(
      `UPDATE runs SET approval_required=CASE WHEN $1>0 THEN 1 ELSE 0 END
      WHERE run_id=$2 AND task_id=$3 AND workspace_id=$4
      RETURNING run_id,workspace_id,task_id,agent_id,status,approval_required,ended_at,error_type,error_message`,
      [remaining, graph.run.run_id, graph.task.task_id, identity.workspaceId],
    );
    runAfter = runUpdate.rows[0];
    taskAfter = graph.task;
  } else if (graph.approval.approval_kind === "customer_delivery") {
    const runUpdate = await client.query<RunRow>(
      `UPDATE runs SET approval_required=CASE WHEN $1>0 THEN 1 ELSE 0 END
      WHERE run_id=$2 AND task_id=$3 AND workspace_id=$4
      RETURNING run_id,workspace_id,task_id,agent_id,status,approval_required,ended_at,error_type,error_message`,
      [remaining, graph.run.run_id, graph.task.task_id, identity.workspaceId],
    );
    const taskUpdate = await client.query<TaskRow>(
      `UPDATE tasks SET status=CASE WHEN status='waiting_approval' AND $1=0 THEN 'completed' ELSE status END,updated_at=$2
      WHERE task_id=$3 AND workspace_id=$4 RETURNING task_id,workspace_id,status,updated_at`,
      [remaining, now, graph.task.task_id, identity.workspaceId],
    );
    runAfter = runUpdate.rows[0];
    taskAfter = taskUpdate.rows[0];
  } else {
    const runUpdate = await client.query<RunRow>(
      `UPDATE runs SET status=CASE WHEN status='waiting_approval' AND $1=0 THEN 'running' ELSE status END,
      approval_required=CASE WHEN $1>0 THEN 1 ELSE 0 END
      WHERE run_id=$2 AND task_id=$3 AND workspace_id=$4
      RETURNING run_id,workspace_id,task_id,agent_id,status,approval_required,ended_at,error_type,error_message`,
      [remaining, graph.run.run_id, graph.task.task_id, identity.workspaceId],
    );
    const taskUpdate = await client.query<TaskRow>(
      `UPDATE tasks SET status=CASE WHEN status='waiting_approval' AND $1=0 THEN 'running' ELSE status END,updated_at=$2
      WHERE task_id=$3 AND workspace_id=$4 RETURNING task_id,workspace_id,status,updated_at`,
      [remaining, now, graph.task.task_id, identity.workspaceId],
    );
    runAfter = runUpdate.rows[0];
    taskAfter = taskUpdate.rows[0];
  }
  if (!runAfter || !taskAfter) throw new Error("typescript_control_plane_approval_transition_missing");

  return {
    ...graph,
    run: runAfter,
    task: taskAfter,
    toolCall: toolAfter,
    preparedAction: preparedAfter,
    enrollment: enrollmentAfter,
  };
}

async function appendTransitionEvidence(
  client: PoolClient,
  identity: HumanSessionIdentity,
  before: LockedApprovalGraph,
  after: LockedApprovalGraph,
  requestHash: string,
  idempotencyHash: string,
) {
  const metadata = {
    workspace_id: identity.workspaceId,
    membership_role: identity.membershipRole,
    session_ref: identity.sessionRef,
    idempotency_ref: opaqueReference("idemref", idempotencyHash),
    credentials_omitted: true,
    raw_body_omitted: true,
  };
  if (before.toolCall && after.toolCall) {
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "user",
      actorId: identity.userId,
      action: `tool_call.approval_${after.approval.decision}`,
      entityType: "tool_calls",
      entityId: after.toolCall.tool_call_id,
      before: toolSnapshot(before.toolCall),
      after: toolSnapshot(after.toolCall),
      metadata: { ...metadata, approval_id: after.approval.approval_id },
    });
  }
  if (before.preparedAction && after.preparedAction) {
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "user",
      actorId: identity.userId,
      action: `prepared_action.${after.approval.decision}`,
      entityType: "prepared_actions",
      entityId: after.preparedAction.prepared_action_id,
      before: preparedActionSnapshot(before.preparedAction),
      after: preparedActionSnapshot(after.preparedAction),
      metadata: { ...metadata, approval_id: after.approval.approval_id },
    });
  }
  if (before.enrollment && after.enrollment) {
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "user",
      actorId: identity.userId,
      action: `agent_gateway.enrollment_request_${after.approval.decision}`,
      entityType: "agent_gateway_enrollment_requests",
      entityId: after.enrollment.request_id,
      before: enrollmentSnapshot(before.enrollment),
      after: enrollmentSnapshot(after.enrollment),
      metadata: { ...metadata, approval_id: after.approval.approval_id },
    });
  }
  if (stableHash(runSnapshot(before.run)) !== stableHash(runSnapshot(after.run))) {
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "user",
      actorId: identity.userId,
      action: after.run.status === "blocked" && before.run.status !== "blocked"
        ? "run.blocked"
        : "run.approval_resolved",
      entityType: "runs",
      entityId: after.run.run_id,
      before: runSnapshot(before.run),
      after: runSnapshot(after.run),
      metadata: { ...metadata, approval_id: after.approval.approval_id },
    });
  }
  if (stableHash(taskSnapshot(before.task)) !== stableHash(taskSnapshot(after.task))) {
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "user",
      actorId: identity.userId,
      action: after.task.status === "blocked" && before.task.status !== "blocked"
        ? "task.blocked"
        : "task.approval_resolved",
      entityType: "tasks",
      entityId: after.task.task_id,
      before: taskSnapshot(before.task),
      after: taskSnapshot(after.task),
      metadata: { ...metadata, approval_id: after.approval.approval_id },
    });
  }
  await appendAudit(client, {
    workspaceId: identity.workspaceId,
    actorType: "user",
    actorId: identity.userId,
    action: `approval.${after.approval.decision}`,
    entityType: "approvals",
    entityId: after.approval.approval_id,
    before: approvalSnapshot(before.approval),
    after: approvalSnapshot(after.approval),
    metadata,
  });
  await appendRuntimeEvent(client, {
    eventType: `approval.${after.approval.decision}`,
    status: "completed",
    runId: after.run.run_id,
    taskId: after.task.task_id,
    agentId: after.run.agent_id,
    outputSummary: `Human reviewer marked the approval ${after.approval.decision}.`,
    rawPayloadHash: requestHash,
  });
}

async function decidePendingApproval(
  client: PoolClient,
  identity: HumanSessionIdentity,
  graph: LockedApprovalGraph,
  requestedDecision: ApprovalDecision,
  requestHash: string,
  idempotencyHash: string,
) {
  if (graph.approval.decision !== "pending") {
    throw new ControlPlaneHttpError(
      409,
      "approval_decision_conflict",
      "A terminal approval decision cannot be changed or replayed with another request identity.",
    );
  }
  const terminalParentStatuses = ["completed", "blocked", "failed", "canceled"];
  if (graph.approval.approval_kind !== "customer_delivery"
    && terminalParentStatuses.includes(graph.task.status)) {
    throw new ControlPlaneHttpError(
      409,
      "approval_parent_state_blocked",
      "Approval cannot change linked state after the parent task is terminal.",
    );
  }
  if (graph.approval.approval_kind !== "customer_delivery"
    && terminalParentStatuses.includes(graph.run.status)) {
    throw new ControlPlaneHttpError(
      409,
      "approval_parent_state_blocked",
      "Approval cannot change linked state after the parent run is terminal.",
    );
  }
  if (requestedDecision === "approved" && approvalExpired(graph.approval)) {
    throw new ControlPlaneHttpError(409, "approval_expired", "Expired approval cannot authorize an action.");
  }
  if (requestedDecision === "approved"
    && graph.toolCall
    && !graph.preparedAction
    && ["high", "critical"].includes(graph.toolCall.risk_level)) {
    throw new ControlPlaneHttpError(
      409,
      "prepared_action_required",
      "High-risk tool approval requires an exact-resume Prepared Action before it can be authorized.",
    );
  }
  let deliveryGate: Awaited<ReturnType<typeof verifyLatestWorkspacePlanEvidence>> | null = null;
  if (graph.approval.approval_kind === "customer_delivery") {
    if (graph.run.status !== "completed" || graph.task.status !== "waiting_approval") {
      throw new ControlPlaneHttpError(
        409,
        "customer_delivery_run_incomplete",
        "Customer delivery cannot be decided until the bound run is completed and its task is waiting for review.",
      );
    }
  }
  if (requestedDecision === "approved" && graph.approval.approval_kind === "customer_delivery") {
    deliveryGate = await verifyLatestWorkspacePlanEvidence(
      client,
      identity.workspaceId,
      graph.task.task_id,
      graph.run.run_id,
      graph.run.agent_id,
    );
    if (!deliveryGate.pass) {
      throw new ControlPlaneHttpError(
        409,
        "verified_plan_evidence_manifest_required",
        "Customer delivery requires a currently verified plan-evidence manifest.",
      );
    }
  }

  const now = new Date().toISOString();
  const approvalUpdate = await client.query<ApprovalRow>(
    `UPDATE approvals SET decision=$1,approver_user_id=$2,decided_at=$3
    WHERE approval_id=$4 AND task_id=$5 AND run_id=$6 AND decision='pending'
    RETURNING approval_id,approval_kind,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,
      decision,expires_at,created_at,decided_at`,
    [requestedDecision, identity.userId, now, graph.approval.approval_id, graph.task.task_id, graph.run.run_id],
  );
  const approvalAfter = approvalUpdate.rows[0];
  if (!approvalAfter) {
    throw new ControlPlaneHttpError(409, "approval_decision_conflict", "Approval lost its single-winner transition.");
  }
  const transitioned = await updateLinkedState(
    client,
    identity,
    { ...graph, approval: approvalAfter },
    requestedDecision,
    now,
  );
  const after = { ...transitioned, approval: approvalAfter };
  await client.query(
    `INSERT INTO human_approval_decision_requests(
      workspace_id,user_id,idempotency_key_hash,request_hash,approval_id,decision,status,created_at,completed_at
    ) VALUES($1,$2,$3,$4,$5,$6,'completed',$7,$7)`,
    [identity.workspaceId, identity.userId, idempotencyHash, requestHash, approvalAfter.approval_id, requestedDecision, now],
  );
  await appendTransitionEvidence(client, identity, graph, after, requestHash, idempotencyHash);
  return response(after, "updated");
}

export async function decideWorkspaceApproval(
  request: Request,
  body: Record<string, unknown>,
  rawApprovalId: unknown,
  rawDecision: unknown,
) {
  const approvalId = identifier(rawApprovalId, "approval_id");
  const requestedDecision = decision(rawDecision);
  const replayKey = idempotencyKey(request.headers);
  rejectMachineCredentials(request.headers);
  validateWriteOrigin(request.headers);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanReviewer(client, request.headers, body.workspace_id);
    const idempotencyHash = stableHash({
      workspace_id: identity.workspaceId,
      user_id: identity.userId,
      idempotency_key: replayKey,
    });
    const requestHash = stableHash({
      workspace_id: identity.workspaceId,
      user_id: identity.userId,
      approval_id: approvalId,
      decision: requestedDecision,
    });
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [
      `agentops-human-approval-idempotency:${identity.workspaceId}:${identity.userId}:${idempotencyHash}`,
    ]);
    const existingResult = await client.query<IdempotencyRow>(
      `SELECT workspace_id,user_id,idempotency_key_hash,request_hash,approval_id,decision,status,created_at,completed_at
      FROM human_approval_decision_requests
      WHERE workspace_id=$1 AND user_id=$2 AND idempotency_key_hash=$3 FOR UPDATE`,
      [identity.workspaceId, identity.userId, idempotencyHash],
    );
    const existing = existingResult.rows[0];
    if (existing
      && (existing.request_hash !== requestHash
        || existing.approval_id !== approvalId
        || existing.decision !== requestedDecision
        || existing.status !== "completed")) {
      throw new ControlPlaneHttpError(
        409,
        "approval_idempotency_conflict",
        "Idempotency-Key is already bound to another approval decision.",
      );
    }
    const graph = await lockApprovalGraph(client, identity.workspaceId, approvalId);
    if (existing) {
      if (graph.approval.decision !== requestedDecision || graph.approval.approver_user_id !== identity.userId) {
        throw new ControlPlaneHttpError(409, "approval_replay_state_conflict", "Approval replay state is unavailable.");
      }
      return response(graph, "unchanged");
    }
    return decidePendingApproval(client, identity, graph, requestedDecision, requestHash, idempotencyHash);
  });
}
