import type { PoolClient } from "pg";

import {
  authenticateAgentGateway,
  enforceWorkspaceBinding,
  type AgentGatewayIdentity,
} from "./auth";
import { boundedJsonObject } from "./boundedJson";
import {
  verifyCurrentCustomerDeliveryPlanEvidence,
  type CustomerDeliveryPlanEvidence,
} from "./customerDeliveryPlanEvidence";
import { assertCustomerDeliverySchemaReady } from "./customerDeliverySchema";
import { withPostgresTransaction } from "./db";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, appendRuntimeEvent, stableHash } from "./ledger";

export const CUSTOMER_DELIVERY_APPROVAL_MAX_BODY_BYTES = 16 * 1024;

const APPROVAL_KIND = "customer_delivery";
const APPROVAL_TTL_MS = 48 * 60 * 60 * 1000;
const DEFAULT_REASON =
  "Customer delivery acceptance is required before publishing or treating this run as approved.";
const ALLOWED_FIELDS = new Set([
  "agent_id",
  "approval_id",
  "approval_kind",
  "decision",
  "reason",
  "requested_by_agent_id",
  "run_id",
  "task_id",
  "workspace_id",
]);
const HUMAN_FIELDS = new Set([
  "approver_id",
  "approver_user_id",
  "assigned_approver_id",
  "decided_by",
  "decided_at",
]);
const SERVER_EXPIRY_FIELDS = new Set(["expires_at", "ttl_seconds"]);

type TaskRow = {
  task_id: string;
  workspace_id: string;
  owner_agent_id: string | null;
  collaborator_agent_ids: string;
  status: string;
  updated_at: string;
};

type RunRow = {
  run_id: string;
  workspace_id: string;
  task_id: string;
  agent_id: string;
  runtime_type: string;
  model_provider: string | null;
  status: string;
  agent_plan_id: string | null;
  plan_hash: string | null;
};

type ApprovalRow = {
  approval_id: string;
  approval_kind: string;
  task_id: string;
  run_id: string;
  tool_call_id: string | null;
  requested_by_agent_id: string | null;
  approver_user_id: string | null;
  decision: string;
  reason: string | null;
  expires_at: string | null;
  created_at: string;
  decided_at: string | null;
};

function identifier(value: unknown, field: string) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      `${field}_invalid`,
      `${field} must use 1-128 safe identifier characters.`,
    );
  }
  return normalized;
}

function optionalIdentifier(value: unknown, field: string) {
  return value === undefined || value === null || value === ""
    ? null
    : identifier(value, field);
}

function sanitizedReason(value: unknown) {
  const sanitized = String(value ?? "")
    .replace(
      /-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----/g,
      "[PRIVATE_KEY_REDACTED]",
    )
    .replace(/(bearer\s+)[a-z0-9._-]+/gi, "$1[REDACTED]")
    .replace(
      /raw[_-]?(?:prompt|response|transcript|content)\s*[:=]\s*['"]?[^'"\s,;]+/gi,
      "[RAW_FIELD_REDACTED]",
    )
    .replace(
      /(token|secret|password|api[_-]?key)\s*[:=]\s*['"]?[^'"\s,;]+/gi,
      "$1=[REDACTED]",
    )
    .replace(
      /(?<![A-Za-z0-9])(?:sk|gh[pousr])[-_][A-Za-z0-9_-]{16,}/g,
      "[SECRET_REDACTED]",
    )
    .replace(/github_pat_[A-Za-z0-9_]{20,}/g, "[SECRET_REDACTED]")
    .replace(
      /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,
      "[JWT_REDACTED]",
    )
    .replace(/\b(?:agtok|agtsess)_[A-Za-z0-9_-]+\b/g, "[AGENT_TOKEN_REF_REDACTED]")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 260);
  return sanitized || DEFAULT_REASON;
}

function collaborators(value: string) {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

export function validateCustomerDeliveryApprovalInput(
  body: Record<string, unknown>,
) {
  for (const field of HUMAN_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(body, field)) {
      throw new ControlPlaneHttpError(
        403,
        "approval_approver_human_owned",
        "Agent credentials cannot assign or perform customer-delivery approval.",
      );
    }
  }
  for (const field of SERVER_EXPIRY_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(body, field)) {
      throw new ControlPlaneHttpError(
        400,
        "approval_expiry_server_owned",
        "Customer-delivery approval expiry is assigned by the server.",
      );
    }
  }
  const unknown = Object.keys(body).find((field) => !ALLOWED_FIELDS.has(field));
  if (unknown) {
    throw new ControlPlaneHttpError(
      400,
      "approval_request_field_unsupported",
      "The customer-delivery approval owner received an unsupported request field.",
    );
  }
  if (String(body.approval_kind ?? "").trim().toLowerCase() !== APPROVAL_KIND) {
    throw new ControlPlaneHttpError(
      409,
      "approval_kind_owner_unsupported",
      "This production owner supports only approval_kind=customer_delivery.",
    );
  }
  if (
    body.decision !== undefined
    && String(body.decision).trim().toLowerCase() !== "pending"
  ) {
    throw new ControlPlaneHttpError(
      403,
      "approval_decision_human_owned",
      "Agent credentials can create only pending customer-delivery approvals.",
    );
  }
}

function enforceAgentBinding(
  identity: AgentGatewayIdentity,
  request: Request,
  body: Record<string, unknown>,
) {
  for (const value of [
    request.headers.get("x-agentops-agent-id"),
    body.agent_id,
    body.requested_by_agent_id,
  ]) {
    if (value !== undefined && value !== null && value !== "") {
      if (identifier(value, "agent_id") !== identity.agentId) {
        throw new ControlPlaneHttpError(
          403,
          "forbidden",
          "Agent credential cannot request approval for another agent.",
        );
      }
    }
  }
}

export function stableCustomerDeliveryApprovalId(
  workspaceId: string,
  runId: string,
) {
  return `ap_gw_customer_delivery_${stableHash([
    "agent-gateway-customer-delivery",
    workspaceId,
    runId,
  ]).slice(0, 16)}`;
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
    reason: row.reason,
    expires_at: row.expires_at,
    created_at: row.created_at,
    decided_at: row.decided_at,
  };
}

function taskSnapshot(row: TaskRow) {
  return {
    task_id: row.task_id,
    workspace_id: row.workspace_id,
    owner_agent_id: row.owner_agent_id,
    collaborator_agent_ids: row.collaborator_agent_ids,
    status: row.status,
    updated_at: row.updated_at,
  };
}

function response(
  approval: ApprovalRow,
  task: TaskRow,
  run: RunRow,
  gate: CustomerDeliveryPlanEvidence,
  outcome: "created" | "unchanged",
) {
  return {
    status: outcome === "created" ? 201 : 200,
    body: {
      ok: true,
      provider: "agentops-customer-delivery-approval",
      control_plane: "typescript_postgres",
      operation: "customer_delivery_approval_request",
      outcome,
      approval: approvalSnapshot(approval),
      linked_state: {
        workspace_id: task.workspace_id,
        task_id: task.task_id,
        run_id: run.run_id,
        requested_by_agent_id: approval.requested_by_agent_id,
        task_status: task.status,
        run_status: run.status,
      },
      plan_evidence: gate,
      credentials_omitted: true,
      raw_body_omitted: true,
      token_omitted: true,
    },
  };
}

function assertReplay(
  existing: ApprovalRow,
  input: {
    requestedApprovalId: string | null;
    taskId: string;
    runId: string;
    agentId: string;
    requestedReason: string | null;
  },
) {
  if (
    input.requestedApprovalId
    && existing.approval_id !== input.requestedApprovalId
  ) {
    throw new ControlPlaneHttpError(
      409,
      "customer_delivery_approval_immutable_conflict",
      "The run already has another immutable customer-delivery approval identity.",
    );
  }
  if (
    existing.approval_kind !== APPROVAL_KIND
    || existing.task_id !== input.taskId
    || existing.run_id !== input.runId
    || existing.tool_call_id !== null
    || existing.requested_by_agent_id !== input.agentId
    || existing.approver_user_id !== null
    || existing.decided_at !== null
  ) {
    throw new ControlPlaneHttpError(
      409,
      "customer_delivery_approval_binding_conflict",
      "The existing customer-delivery approval has an invalid immutable binding.",
    );
  }
  if (existing.decision !== "pending") {
    throw new ControlPlaneHttpError(
      409,
      "customer_delivery_approval_terminal",
      "A terminal customer-delivery approval cannot be recreated as pending.",
    );
  }
  if (input.requestedReason !== null && existing.reason !== input.requestedReason) {
    throw new ControlPlaneHttpError(
      409,
      "customer_delivery_approval_immutable_conflict",
      "The pending customer-delivery approval reason is immutable.",
    );
  }
  const expiresAt = Date.parse(String(existing.expires_at || ""));
  const createdAt = Date.parse(existing.created_at);
  if (
    !Number.isFinite(expiresAt)
    || !Number.isFinite(createdAt)
    || expiresAt <= Date.now()
    || expiresAt <= createdAt
    || expiresAt - createdAt > APPROVAL_TTL_MS + 1000
  ) {
    throw new ControlPlaneHttpError(
      409,
      "customer_delivery_approval_expired",
      "The run's customer-delivery approval has expired.",
    );
  }
}

async function lockTaskAndRun(
  client: PoolClient,
  workspaceId: string,
  agentId: string,
  runId: string,
  requestedTaskId: string | null,
) {
  await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [
    `agentops-customer-delivery:${workspaceId}:${runId}`,
  ]);
  const runResult = await client.query<RunRow>(
    `SELECT run_id,workspace_id,task_id,agent_id,runtime_type,model_provider,
      status,agent_plan_id,plan_hash
    FROM runs WHERE run_id=$1 AND workspace_id=$2 FOR UPDATE`,
    [runId, workspaceId],
  );
  const run = runResult.rows[0];
  if (!run) {
    throw new ControlPlaneHttpError(
      404,
      "run_not_found",
      "Run was not found in the credential workspace.",
    );
  }
  if (run.agent_id !== agentId) {
    throw new ControlPlaneHttpError(403, "forbidden", "Run belongs to another agent.");
  }
  if (requestedTaskId && requestedTaskId !== run.task_id) {
    throw new ControlPlaneHttpError(
      403,
      "forbidden",
      "Customer-delivery approval task_id must match the target run.",
    );
  }
  const taskResult = await client.query<TaskRow>(
    `SELECT task_id,workspace_id,owner_agent_id,collaborator_agent_ids,status,updated_at
    FROM tasks WHERE task_id=$1 AND workspace_id=$2 FOR UPDATE`,
    [run.task_id, workspaceId],
  );
  const task = taskResult.rows[0];
  if (!task) {
    throw new ControlPlaneHttpError(
      404,
      "task_not_found",
      "Task was not found in the credential workspace.",
    );
  }
  if (
    task.owner_agent_id !== agentId
    && !collaborators(task.collaborator_agent_ids).includes(agentId)
  ) {
    throw new ControlPlaneHttpError(
      403,
      "forbidden",
      "Requester is not bound to the target task.",
    );
  }
  if (run.status !== "completed") {
    throw new ControlPlaneHttpError(
      409,
      "customer_delivery_run_incomplete",
      "Customer delivery approval requires a completed run.",
    );
  }
  return { task, run };
}

export async function requestCustomerDeliveryApproval(request: Request) {
  const body = await boundedJsonObject(request, {
    maxBytes: CUSTOMER_DELIVERY_APPROVAL_MAX_BODY_BYTES,
    label: "Customer-delivery approval request",
  });
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(
      client,
      request.headers,
      "approvals:request",
    );
    await assertCustomerDeliverySchemaReady(client);
    const requestedWorkspaceId = optionalIdentifier(
      body.workspace_id,
      "workspace_id",
    );
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
      body: requestedWorkspaceId,
    });
    enforceAgentBinding(identity, request, body);
    validateCustomerDeliveryApprovalInput(body);

    const runId = identifier(body.run_id, "run_id");
    const requestedTaskId = optionalIdentifier(body.task_id, "task_id");
    const requestedApprovalId = optionalIdentifier(body.approval_id, "approval_id");
    const requestedReason = body.reason === undefined
      ? null
      : sanitizedReason(body.reason);
    const { task, run } = await lockTaskAndRun(
      client,
      identity.workspaceId,
      identity.agentId,
      runId,
      requestedTaskId,
    );

    const existingResult = await client.query<ApprovalRow>(
      `SELECT approval_id,approval_kind,task_id,run_id,tool_call_id,
        requested_by_agent_id,approver_user_id,decision,reason,expires_at,
        created_at,decided_at
      FROM approvals
      WHERE run_id=$1 AND approval_kind='customer_delivery'
      ORDER BY approval_id FOR UPDATE`,
      [run.run_id],
    );
    if (existingResult.rows.length > 1) {
      throw new ControlPlaneHttpError(
        409,
        "customer_delivery_approval_duplicate_conflict",
        "The run has multiple customer-delivery approvals and requires repair.",
      );
    }
    const existing = existingResult.rows[0];
    if (existing) {
      assertReplay(existing, {
        requestedApprovalId,
        taskId: task.task_id,
        runId: run.run_id,
        agentId: identity.agentId,
        requestedReason,
      });
      if (task.status !== "waiting_approval") {
        throw new ControlPlaneHttpError(
          409,
          "customer_delivery_task_state_conflict",
          "The pending approval is not paired with a waiting task.",
        );
      }
    } else if (task.status !== "completed") {
      throw new ControlPlaneHttpError(
        409,
        "customer_delivery_task_incomplete",
        "A new customer-delivery approval requires a completed task.",
      );
    }

    const gate = await verifyCurrentCustomerDeliveryPlanEvidence(
      client,
      identity.workspaceId,
      task.task_id,
      run,
      identity.agentId,
    );
    if (!gate.pass || !gate.verification_pass) {
      throw new ControlPlaneHttpError(
        409,
        "verified_plan_evidence_manifest_required",
        "Customer delivery requires current verified Hermes or OpenClaw plan evidence.",
      );
    }
    if (existing) return response(existing, task, run, gate, "unchanged");

    const approvalId = requestedApprovalId
      || stableCustomerDeliveryApprovalId(identity.workspaceId, run.run_id);
    const collision = await client.query<{ approval_id: string }>(
      "SELECT approval_id FROM approvals WHERE approval_id=$1 FOR UPDATE",
      [approvalId],
    );
    if (collision.rows[0]) {
      throw new ControlPlaneHttpError(
        409,
        "approval_id_unavailable",
        "approval_id is unavailable for this customer-delivery request.",
      );
    }

    const now = new Date();
    const row: ApprovalRow = {
      approval_id: approvalId,
      approval_kind: APPROVAL_KIND,
      task_id: task.task_id,
      run_id: run.run_id,
      tool_call_id: null,
      requested_by_agent_id: identity.agentId,
      approver_user_id: null,
      decision: "pending",
      reason: requestedReason || DEFAULT_REASON,
      expires_at: new Date(now.getTime() + APPROVAL_TTL_MS).toISOString(),
      created_at: now.toISOString(),
      decided_at: null,
    };
    const approvalResult = await client.query<ApprovalRow>(
      `INSERT INTO approvals(
        approval_id,approval_kind,task_id,run_id,tool_call_id,
        requested_by_agent_id,approver_user_id,decision,reason,expires_at,
        created_at,decided_at
      ) VALUES($1,'customer_delivery',$2,$3,NULL,$4,NULL,'pending',$5,$6,$7,NULL)
      RETURNING approval_id,approval_kind,task_id,run_id,tool_call_id,
        requested_by_agent_id,approver_user_id,decision,reason,expires_at,
        created_at,decided_at`,
      [
        row.approval_id,
        row.task_id,
        row.run_id,
        row.requested_by_agent_id,
        row.reason,
        row.expires_at,
        row.created_at,
      ],
    );
    const approval = approvalResult.rows[0];
    const taskUpdate = await client.query<TaskRow>(
      `UPDATE tasks SET status='waiting_approval',updated_at=$1
      WHERE task_id=$2 AND workspace_id=$3 AND status='completed'
      RETURNING task_id,workspace_id,owner_agent_id,collaborator_agent_ids,
        status,updated_at`,
      [now.toISOString(), task.task_id, identity.workspaceId],
    );
    const updatedTask = taskUpdate.rows[0];
    if (!approval || !updatedTask) {
      throw new ControlPlaneHttpError(
        409,
        "customer_delivery_task_transition_conflict",
        "The customer-delivery review transition lost its completed task.",
      );
    }

    await appendRuntimeEvent(client, {
      eventType: "approval.customer_delivery.request",
      status: "waiting_approval",
      runId: run.run_id,
      taskId: task.task_id,
      agentId: identity.agentId,
      outputSummary: approval.reason || DEFAULT_REASON,
      rawPayloadHash: stableHash({
        approval_id: approval.approval_id,
        workspace_id: identity.workspaceId,
        task_id: task.task_id,
        run_id: run.run_id,
        manifest_id: gate.manifest_id,
        plan_hash: gate.plan_hash,
        verification_result_hash: gate.verification_result_hash,
      }),
    });
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "agent",
      actorId: identity.agentId,
      action: "agent_gateway.customer_delivery_approval_request",
      entityType: "approvals",
      entityId: approval.approval_id,
      after: approvalSnapshot(approval),
      metadata: {
        task_id: task.task_id,
        run_id: run.run_id,
        manifest_id: gate.manifest_id,
        plan_id: gate.plan_id,
        plan_version: gate.plan_version,
        plan_hash: gate.plan_hash,
        verification_result_hash: gate.verification_result_hash,
        approval_kind: APPROVAL_KIND,
        approver_attribution_omitted: true,
        raw_body_omitted: true,
        token_omitted: true,
      },
    });
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "agent",
      actorId: identity.agentId,
      action: "agent_gateway.customer_delivery_task_waiting_approval",
      entityType: "tasks",
      entityId: task.task_id,
      before: taskSnapshot(task),
      after: taskSnapshot(updatedTask),
      metadata: {
        run_id: run.run_id,
        approval_id: approval.approval_id,
        raw_body_omitted: true,
        token_omitted: true,
      },
    });
    return response(approval, updatedTask, run, gate, "created");
  });
}
