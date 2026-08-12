import type { PoolClient } from "pg";
import { NextRequest, NextResponse } from "next/server";

import { parseBoundedJsonObject, readBoundedBody } from "./boundedJson";
import {
  controlPlaneMode,
  legacyPythonProxyAllowed,
} from "./config";
import { withPostgresTransaction } from "./db";
import { authenticateHumanWriteMember } from "./humanSession";
import { ControlPlaneHttpError, errorPayload } from "./http";
import { appendAudit, appendRuntimeEvent, stableHash } from "./ledger";
import { proxyControlPlaneRequest } from "./proxy";

const TASK_OPERATION_MAX_BODY_BYTES = 4 * 1024;
const TASK_OPERATOR_ROLES = new Set(["operator", "workspace-admin", "owner"]);
const COMMERCIAL_TASK_EDITIONS = new Set([
  "pro_workspace",
  "team_governance",
  "enterprise_byoc",
]);
const KNOWN_ENTITLEMENT_STATUSES = new Set([
  "inactive",
  "suspended",
  "expired",
]);
const HUMAN_MANAGED_STATUSES = new Set([
  "backlog",
  "planned",
  "blocked",
  "canceled",
]);
const STATUS_TRANSITIONS: Readonly<Record<string, ReadonlySet<string>>> = {
  backlog: new Set(["planned", "canceled"]),
  planned: new Set(["backlog", "blocked", "canceled"]),
  blocked: new Set(["planned", "canceled"]),
  canceled: new Set(),
};
const PRIVATE_WRITE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, Origin, X-AgentOps-Workspace-Id, X-AgentOps-CSRF",
};

type TaskOperation = "status" | "assign";

type TaskRow = {
  task_id: string;
  workspace_id: string;
  title: string;
  description: string | null;
  requester_id: string | null;
  owner_agent_id: string | null;
  collaborator_agent_ids: string;
  status: string;
  priority: string;
  due_date: string | null;
  acceptance_criteria: string | null;
  risk_level: string;
  budget_limit_usd: number;
  created_at: string;
  updated_at: string;
};

type EntitlementRow = {
  edition: string;
  status: string;
  effective_at: Date | string;
  expires_at: Date | string | null;
};

function identifier(value: unknown, field: string) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      `human_task_${field}_invalid`,
      `${field} must use the bounded MIS identifier format.`,
    );
  }
  return normalized;
}

function exactBodyKeys(
  body: Record<string, unknown>,
  allowed: readonly string[],
) {
  const allowlist = new Set(allowed);
  const unsupported = Object.keys(body).find((key) => !allowlist.has(key));
  if (unsupported) {
    throw new ControlPlaneHttpError(
      400,
      "human_task_operation_field_unsupported",
      "The task operation received an unsupported field.",
    );
  }
}

function asTimestamp(value: Date | string | null) {
  if (value === null) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}

async function assertActiveWorkspaceEntitlement(
  client: PoolClient,
  workspaceId: string,
) {
  await client.query(
    "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
    [`agentops:workspace-entitlement:${workspaceId}`],
  );
  const clock = await client.query<{ evaluated_at: Date | string }>(
    "SELECT clock_timestamp() AS evaluated_at",
  );
  const now = asTimestamp(clock.rows[0]?.evaluated_at || "");
  const entitlement = (await client.query<EntitlementRow>(
    `SELECT edition,status,effective_at,expires_at
    FROM workspace_entitlements
    WHERE workspace_id=$1`,
    [workspaceId],
  )).rows[0];
  if (!entitlement) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_missing",
      "This workspace has no commercial entitlement.",
    );
  }
  const effectiveAt = asTimestamp(entitlement.effective_at);
  const expiresAt = asTimestamp(entitlement.expires_at);
  if (!now || !effectiveAt || (entitlement.expires_at !== null && !expiresAt)) {
    throw new ControlPlaneHttpError(
      503,
      "workspace_entitlement_invalid",
      "The workspace entitlement state is invalid.",
    );
  }
  if (entitlement.status !== "active") {
    const knownStatus = KNOWN_ENTITLEMENT_STATUSES.has(entitlement.status);
    throw new ControlPlaneHttpError(
      knownStatus ? 403 : 503,
      knownStatus
        ? `workspace_entitlement_${entitlement.status}`
        : "workspace_entitlement_invalid",
      "The workspace entitlement is not active.",
    );
  }
  if (effectiveAt.getTime() > now.getTime()) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_not_effective",
      "The workspace entitlement is not effective yet.",
    );
  }
  if (expiresAt && expiresAt.getTime() <= now.getTime()) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_expired",
      "The workspace entitlement has expired.",
    );
  }
  if (!COMMERCIAL_TASK_EDITIONS.has(entitlement.edition)) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_edition_forbidden",
      "Task operations require a commercial workspace edition.",
    );
  }
  return { edition: entitlement.edition, status: entitlement.status };
}

async function lockWorkspaceTask(
  client: PoolClient,
  workspaceId: string,
  taskId: string,
) {
  const task = (await client.query<TaskRow>(
    "SELECT * FROM tasks WHERE task_id=$1 AND workspace_id=$2 FOR UPDATE",
    [taskId, workspaceId],
  )).rows[0];
  if (!task) {
    throw new ControlPlaneHttpError(
      404,
      "human_task_not_found",
      "The task was not found in this workspace.",
    );
  }
  return task;
}

async function assertTaskHasNoActiveRun(
  client: PoolClient,
  workspaceId: string,
  taskId: string,
) {
  const active = (await client.query<{ run_id: string }>(
    `SELECT run_id FROM runs
    WHERE workspace_id=$1 AND task_id=$2
      AND status IN ('running','waiting_approval')
    ORDER BY created_at DESC,run_id
    LIMIT 1 FOR SHARE`,
    [workspaceId, taskId],
  )).rows[0];
  if (active) {
    throw new ControlPlaneHttpError(
      409,
      "human_task_active_run_conflict",
      "Task assignment and manual status changes are blocked while a run is active.",
    );
  }
}

async function updateTaskStatus(
  client: PoolClient,
  task: TaskRow,
  body: Record<string, unknown>,
) {
  exactBodyKeys(body, ["workspace_id", "status"]);
  const status = String(body.status ?? "").trim().toLowerCase();
  if (!HUMAN_MANAGED_STATUSES.has(status)) {
    throw new ControlPlaneHttpError(
      400,
      "human_task_status_invalid",
      "Human task operations may use backlog, planned, blocked, or canceled.",
    );
  }
  if (task.status === status) return { outcome: "unchanged" as const, task };
  if (!STATUS_TRANSITIONS[task.status]?.has(status)) {
    throw new ControlPlaneHttpError(
      409,
      "human_task_status_transition_forbidden",
      "The requested Human task status transition is not allowed.",
    );
  }
  await assertTaskHasNoActiveRun(client, task.workspace_id, task.task_id);
  const updated = (await client.query<TaskRow>(
    `UPDATE tasks SET status=$1,updated_at=$2
    WHERE task_id=$3 AND workspace_id=$4 RETURNING *`,
    [status, new Date().toISOString(), task.task_id, task.workspace_id],
  )).rows[0];
  return { outcome: "updated" as const, task: updated };
}

async function assignTask(
  client: PoolClient,
  task: TaskRow,
  body: Record<string, unknown>,
) {
  exactBodyKeys(body, ["workspace_id", "owner_agent_id"]);
  const ownerAgentId = identifier(body.owner_agent_id, "owner_agent_id");
  const agent = (await client.query<{ agent_id: string; status: string }>(
    `SELECT agent.agent_id,agent.status
    FROM agents agent
    WHERE agent.agent_id=$1
      AND EXISTS (
        SELECT 1 FROM agent_gateway_tokens token
        WHERE token.agent_id=agent.agent_id AND token.workspace_id=$2
        UNION ALL
        SELECT 1 FROM runs run
        WHERE run.agent_id=agent.agent_id AND run.workspace_id=$2
        UNION ALL
        SELECT 1 FROM tasks scoped_task
        WHERE scoped_task.owner_agent_id=agent.agent_id
          AND scoped_task.workspace_id=$2
      )
    FOR SHARE`,
    [ownerAgentId, task.workspace_id],
  )).rows[0];
  if (!agent || agent.status === "disabled") {
    throw new ControlPlaneHttpError(
      400,
      "human_task_owner_unavailable",
      "The selected Agent is unavailable in this workspace.",
    );
  }
  if (task.owner_agent_id === ownerAgentId) {
    return { outcome: "unchanged" as const, task };
  }
  if (!HUMAN_MANAGED_STATUSES.has(task.status) || task.status === "canceled") {
    throw new ControlPlaneHttpError(
      409,
      "human_task_assignment_state_forbidden",
      "The task cannot be reassigned from its current state.",
    );
  }
  await assertTaskHasNoActiveRun(client, task.workspace_id, task.task_id);
  const updated = (await client.query<TaskRow>(
    `UPDATE tasks SET owner_agent_id=$1,updated_at=$2
    WHERE task_id=$3 AND workspace_id=$4 RETURNING *`,
    [ownerAgentId, new Date().toISOString(), task.task_id, task.workspace_id],
  )).rows[0];
  return { outcome: "updated" as const, task: updated };
}

export async function ownHumanTaskOperation(
  request: NextRequest,
  input: Readonly<{
    operation: TaskOperation;
    taskId: unknown;
  }>,
) {
  try {
    const taskId = identifier(input.taskId, "task_id");
    const rawBody = await readBoundedBody(request, {
      maxBytes: TASK_OPERATION_MAX_BODY_BYTES,
      label: "Human task operation",
    });
    if (controlPlaneMode() === "proxy") {
      if (!legacyPythonProxyAllowed()) {
        throw new ControlPlaneHttpError(
          503,
          "human_task_direct_route_required",
          "Production task operations require TypeScript Postgres authority.",
        );
      }
      const response = await proxyControlPlaneRequest(
        request,
        `/tasks/${encodeURIComponent(taskId)}/${input.operation}`,
        rawBody,
      );
      response.headers.set("Cache-Control", PRIVATE_WRITE_HEADERS["Cache-Control"]);
      response.headers.set("Vary", PRIVATE_WRITE_HEADERS.Vary);
      return response;
    }
    const body = parseBoundedJsonObject(rawBody, {
      maxBytes: TASK_OPERATION_MAX_BODY_BYTES,
      label: "Human task operation",
    });
    const result = await withPostgresTransaction(async (client) => {
      const identity = await authenticateHumanWriteMember(
        client,
        request.headers,
        body.workspace_id,
      );
      if (!TASK_OPERATOR_ROLES.has(identity.membershipRole.trim().toLowerCase())) {
        throw new ControlPlaneHttpError(
          403,
          "human_task_role_forbidden",
          "Task operations require operator, workspace-admin, or owner authority.",
        );
      }
      const before = await lockWorkspaceTask(client, identity.workspaceId, taskId);
      // Keep the same task-row then workspace-entitlement lock order as run start.
      const entitlement = await assertActiveWorkspaceEntitlement(
        client,
        identity.workspaceId,
      );
      const mutation = input.operation === "status"
        ? await updateTaskStatus(client, before, body)
        : await assignTask(client, before, body);
      if (mutation.outcome === "updated") {
        const requestHash = stableHash({
          workspace_id: identity.workspaceId,
          user_id: identity.userId,
          operation: input.operation,
          task_id: taskId,
          body,
        });
        await appendAudit(client, {
          workspaceId: identity.workspaceId,
          actorType: "user",
          actorId: identity.userId,
          action: input.operation === "status"
            ? "human.task_status_update"
            : "human.task_assign",
          entityType: "tasks",
          entityId: taskId,
          before,
          after: mutation.task,
          metadata: {
            membership_role: identity.membershipRole,
            operation: input.operation,
            raw_payload_omitted: true,
            token_omitted: true,
          },
          requestHash,
        });
        await appendRuntimeEvent(client, {
          workspaceId: identity.workspaceId,
          eventType: input.operation === "status"
            ? "task.human_status_update"
            : "task.human_assign",
          status: mutation.task.status,
          taskId,
          agentId: mutation.task.owner_agent_id,
          inputSummary: input.operation === "status"
            ? `Human updated task status to ${mutation.task.status}.`
            : "Human reassigned task owner.",
          rawPayloadHash: requestHash,
        });
      }
      return { identity, entitlement, ...mutation };
    });
    return NextResponse.json({
      ok: true,
      provider: "agentops-human-session",
      control_plane: "typescript_postgres",
      operation: input.operation === "status"
        ? "task_status_update"
        : "task_assignment",
      outcome: result.outcome,
      task: result.task,
      task_id: result.task.task_id,
      workspace_id: result.identity.workspaceId,
      entitlement: {
        authority: "postgres",
        edition: result.entitlement.edition,
        status: result.entitlement.status,
        gate: "active_commercial_workspace",
        raw_config_omitted: true,
      },
      python_proxy_performed: false,
      token_omitted: true,
    }, { status: 200, headers: PRIVATE_WRITE_HEADERS });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: PRIVATE_WRITE_HEADERS,
    });
  }
}
