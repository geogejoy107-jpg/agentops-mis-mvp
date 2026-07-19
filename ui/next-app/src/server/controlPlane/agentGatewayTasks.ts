import type { PoolClient } from "pg";

import { authenticateAgentGateway, enforceWorkspaceBinding } from "./auth";
import { withPostgresTransaction } from "./db";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, appendRuntimeEvent, newLedgerId, pythonFloat, stableHash } from "./ledger";

const TASK_STATUSES = new Set(["backlog", "planned", "running", "waiting_approval", "blocked", "completed", "failed", "canceled"]);
const PRIORITIES = new Set(["low", "medium", "high", "urgent"]);
const RISK_LEVELS = new Set(["low", "medium", "high", "critical"]);
const TASK_CLAIM_BODY_MAX_BYTES = 4 * 1024;

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

function text(value: unknown, limit: number) {
  return String(value || "").replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, limit);
}

function choice(value: unknown, allowed: Set<string>, fallback: string) {
  const normalized = String(value || "").trim().toLowerCase();
  return allowed.has(normalized) ? normalized : fallback;
}

function taskId(value: unknown) {
  if (!value) return newLedgerId("tsk");
  const normalized = String(value).trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(400, "task_id_invalid", "task_id must use 1-128 safe identifier characters.");
  }
  return normalized;
}

function requiredTaskId(value: unknown) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(400, "task_id_invalid", "task_id must use 1-128 safe identifier characters.");
  }
  return normalized;
}

function collaboratorIds(value: unknown) {
  const parsed = Array.isArray(value) ? value : [];
  return parsed.map((item) => text(item, 120)).filter(Boolean).slice(0, 32);
}

function number(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function taskAuditSnapshot(row: TaskRow | undefined) {
  return row ? { ...row, budget_limit_usd: pythonFloat(Number(row.budget_limit_usd)) } : undefined;
}

function taskCollaborators(row: TaskRow) {
  try {
    const parsed = JSON.parse(row.collaborator_agent_ids || "[]");
    return Array.isArray(parsed) ? parsed.map((item) => String(item)) : [];
  } catch {
    return [];
  }
}

function agentCanAccessTask(row: TaskRow, agentId: string) {
  return !row.owner_agent_id
    || row.owner_agent_id === agentId
    || taskCollaborators(row).includes(agentId);
}

function suppliedBinding(value: unknown) {
  if (value === undefined || value === null || value === "") return null;
  return String(value).trim();
}

function enforceAgentBinding(agentId: string, ...requestedValues: unknown[]) {
  for (const value of requestedValues) {
    const requested = suppliedBinding(value);
    if (requested && requested !== agentId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Agent credential cannot act as another agent.");
    }
  }
}

async function taskClaimBody(request: Request) {
  const declaredLength = request.headers.get("content-length");
  if (declaredLength && (!/^\d+$/.test(declaredLength) || Number(declaredLength) > TASK_CLAIM_BODY_MAX_BYTES)) {
    throw new ControlPlaneHttpError(
      413,
      "request_too_large",
      `Task claim body exceeds ${TASK_CLAIM_BODY_MAX_BYTES} bytes.`,
    );
  }
  const chunks: Buffer[] = [];
  let receivedBytes = 0;
  const reader = request.body?.getReader();
  if (reader) {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      receivedBytes += value.byteLength;
      if (receivedBytes > TASK_CLAIM_BODY_MAX_BYTES) {
        await reader.cancel().catch(() => undefined);
        throw new ControlPlaneHttpError(
          413,
          "request_too_large",
          `Task claim body exceeds ${TASK_CLAIM_BODY_MAX_BYTES} bytes.`,
        );
      }
      chunks.push(Buffer.from(value));
    }
  }
  const raw = Buffer.concat(chunks, receivedBytes).toString("utf8");
  if (!raw.trim()) return {} as Record<string, unknown>;
  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  if (!body || Array.isArray(body) || typeof body !== "object") {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  return body as Record<string, unknown>;
}

async function ensureTaskOwner(client: PoolClient, agentId: string) {
  const agent = await client.query("SELECT 1 FROM agents WHERE agent_id=$1", [agentId]);
  if (!agent.rowCount) {
    throw new ControlPlaneHttpError(400, "owner_agent_not_found", `Task owner agent does not exist: ${agentId}`);
  }
}

async function ensureTaskRequester(client: PoolClient, requesterId: string) {
  const requester = await client.query("SELECT 1 FROM users WHERE user_id=$1", [requesterId]);
  if (!requester.rowCount) {
    throw new ControlPlaneHttpError(400, "requester_user_not_found", `Task requester user does not exist: ${requesterId}`);
  }
}

export async function listAgentGatewayTasks(request: Request) {
  const url = new URL(request.url);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "tasks:read");
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
      query: url.searchParams.get("workspace_id"),
    });
    const requestedLimit = Number(url.searchParams.get("limit") || 25);
    const limit = Number.isFinite(requestedLimit) ? Math.max(1, Math.min(Math.trunc(requestedLimit), 200)) : 25;
    const statuses = url.searchParams.getAll("status").filter((status) => TASK_STATUSES.has(status));
    const requesterId = text(url.searchParams.get("requester_id"), 120) || null;
    const result = await client.query<TaskRow>(
      `SELECT * FROM tasks
      WHERE COALESCE(workspace_id,'local-demo')=$1
        AND (owner_agent_id IS NULL OR owner_agent_id='' OR owner_agent_id=$2 OR COALESCE(collaborator_agent_ids,'[]')::jsonb ? $2)
        AND (cardinality($3::text[])=0 OR status=ANY($3::text[]))
        AND ($4::text IS NULL OR requester_id=$4)
      ORDER BY created_at DESC
      LIMIT $5`,
      [identity.workspaceId, identity.agentId, statuses, requesterId, limit],
    );
    return {
      provider: "agent_gateway",
      control_plane: "typescript_postgres",
      operation: "task_list",
      tasks: result.rows,
      count: result.rows.length,
      workspace_id: identity.workspaceId,
      token_omitted: true,
    };
  });
}

export async function pullAgentGatewayTasks(request: Request) {
  const url = new URL(request.url);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "tasks:read");
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
      query: url.searchParams.get("workspace_id"),
    });
    enforceAgentBinding(
      identity.agentId,
      request.headers.get("x-agentops-agent-id"),
      url.searchParams.get("agent_id"),
    );

    const requestedLimit = Number(url.searchParams.get("limit") || 10);
    const limit = Number.isFinite(requestedLimit)
      ? Math.max(1, Math.min(Math.trunc(requestedLimit), 50))
      : 10;
    const requestedStatuses = url.searchParams.getAll("status");
    const statuses = (requestedStatuses.length ? requestedStatuses : ["planned", "backlog"])
      .map((status) => choice(status, TASK_STATUSES, "planned"));
    const result = await client.query<TaskRow>(
      `SELECT * FROM tasks
      WHERE workspace_id=$1
        AND status=ANY($2::text[])
        AND (
          owner_agent_id IS NULL OR owner_agent_id='' OR owner_agent_id=$3
          OR COALESCE(collaborator_agent_ids,'[]')::jsonb ? $3
        )
      ORDER BY created_at ASC
      LIMIT $4`,
      [identity.workspaceId, statuses, identity.agentId, limit],
    );
    await appendRuntimeEvent(client, {
      eventType: "task.pull",
      status: "completed",
      agentId: identity.agentId,
      outputSummary: `Pulled ${result.rows.length} task(s).`,
      rawPayloadHash: stableHash({
        workspace_id: identity.workspaceId,
        agent_id: identity.agentId,
        statuses,
        limit,
        count: result.rows.length,
      }),
    });
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "agent",
      actorId: identity.agentId,
      action: "agent_gateway.task_pull",
      entityType: "tasks",
      entityId: identity.agentId,
      after: { count: result.rows.length },
      metadata: {
        workspace_id: identity.workspaceId,
        statuses,
        limit,
        raw_payload_omitted: true,
        token_omitted: true,
      },
    });
    return {
      provider: "agent_gateway",
      control_plane: "typescript_postgres",
      operation: "task_pull",
      tasks: result.rows,
      count: result.rows.length,
      workspace_id: identity.workspaceId,
      token_omitted: true,
    };
  });
}

export async function claimAgentGatewayTask(request: Request, requestedTaskId: string) {
  const body = await taskClaimBody(request);
  const id = requiredTaskId(requestedTaskId);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "tasks:claim");
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
      body: suppliedBinding(body.workspace_id),
    });
    enforceAgentBinding(
      identity.agentId,
      request.headers.get("x-agentops-agent-id"),
      body.agent_id,
      body.requested_by_agent_id,
    );
    const bodyTaskId = suppliedBinding(body.task_id);
    if (bodyTaskId && bodyTaskId !== id) {
      throw new ControlPlaneHttpError(403, "forbidden", "Task claim body does not match the requested task.");
    }

    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-task:${id}`]);
    const taskResult = await client.query<TaskRow>(
      "SELECT * FROM tasks WHERE task_id=$1 AND workspace_id=$2 FOR UPDATE",
      [id, identity.workspaceId],
    );
    const before = taskResult.rows[0];
    if (!before) {
      throw new ControlPlaneHttpError(404, "task_not_found", "Task was not found in the credential workspace.");
    }
    if (!agentCanAccessTask(before, identity.agentId)) {
      throw new ControlPlaneHttpError(403, "forbidden", "Task is assigned to another agent.");
    }
    if (before.status === "running") {
      if (before.owner_agent_id === identity.agentId) {
        return {
          status: 200,
          body: {
            ok: true,
            provider: "agentops-mis",
            control_plane: "typescript_postgres",
            operation: "task_claim",
            outcome: "unchanged",
            task: before,
            claimed_by: identity.agentId,
            already_claimed: true,
            workspace_id: identity.workspaceId,
            token_omitted: true,
          },
        };
      }
      throw new ControlPlaneHttpError(409, "task_running_conflict", "Task is already running for another agent.");
    }
    if (before.status !== "planned" && before.status !== "backlog") {
      throw new ControlPlaneHttpError(
        409,
        "task_status_conflict",
        `Task cannot be claimed from status ${before.status}.`,
      );
    }

    const now = new Date().toISOString();
    const updated = await client.query<TaskRow>(
      `UPDATE tasks SET owner_agent_id=$1,status='running',updated_at=$2
      WHERE task_id=$3 AND workspace_id=$4 AND status IN ('planned','backlog')
      RETURNING *`,
      [identity.agentId, now, id, identity.workspaceId],
    );
    const after = updated.rows[0];
    if (!after) {
      throw new ControlPlaneHttpError(409, "task_claim_conflict", "Task was claimed or changed before this claim completed.");
    }
    await appendRuntimeEvent(client, {
      eventType: "task.claim",
      status: "completed",
      taskId: id,
      agentId: identity.agentId,
      outputSummary: `${identity.agentId} claimed ${id}.`,
      rawPayloadHash: stableHash({
        workspace_id: identity.workspaceId,
        task_id: id,
        agent_id: identity.agentId,
        before_status: before.status,
        after_status: after.status,
      }),
    });
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "agent",
      actorId: identity.agentId,
      action: "agent_gateway.task_claim",
      entityType: "tasks",
      entityId: id,
      before: taskAuditSnapshot(before),
      after: taskAuditSnapshot(after),
      metadata: {
        workspace_id: identity.workspaceId,
        credential_mode: identity.mode,
        raw_payload_omitted: true,
        token_omitted: true,
      },
    });
    return {
      status: 200,
      body: {
        ok: true,
        provider: "agentops-mis",
        control_plane: "typescript_postgres",
        operation: "task_claim",
        outcome: "claimed",
        task: after,
        claimed_by: identity.agentId,
        workspace_id: identity.workspaceId,
        token_omitted: true,
      },
    };
  });
}

export async function createAgentGatewayTask(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json() as Record<string, unknown>;
  } catch {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  if (!body || Array.isArray(body) || typeof body !== "object") {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "tasks:create");
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
      body: body.workspace_id,
    });
    const requestedOwner = text(body.owner_agent_id || body.agent_id || identity.agentId, 120);
    if (requestedOwner && requestedOwner !== identity.agentId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Agent credential cannot create a task for another agent.");
    }
    await ensureTaskOwner(client, identity.agentId);
    const requesterId = text(
      body.requester_id || process.env.AGENTOPS_CONTROL_PLANE_REQUESTER_ID || "usr_customer_demo",
      120,
    );
    await ensureTaskRequester(client, requesterId);
    const id = taskId(body.task_id);
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-task:${id}`]);
    const existingResult = await client.query<TaskRow>("SELECT * FROM tasks WHERE task_id=$1 FOR UPDATE", [id]);
    const existing = existingResult.rows[0];
    if (existing && existing.workspace_id !== identity.workspaceId) {
      throw new ControlPlaneHttpError(409, "task_immutable_binding_conflict", "task_id is already bound to another workspace.");
    }
    if (existing?.owner_agent_id && existing.owner_agent_id !== identity.agentId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Agent credential cannot update another agent's task.");
    }
    const now = new Date().toISOString();
    const row: TaskRow = {
      task_id: id,
      workspace_id: identity.workspaceId,
      title: text(body.title || "New MIS task", 160),
      description: text(body.description, 1200) || null,
      requester_id: requesterId,
      owner_agent_id: identity.agentId,
      collaborator_agent_ids: JSON.stringify(collaboratorIds(body.collaborator_agent_ids)),
      status: choice(body.status, TASK_STATUSES, "planned"),
      priority: choice(body.priority, PRIORITIES, "medium"),
      due_date: text(body.due_date, 64) || null,
      acceptance_criteria: text(
        body.acceptance_criteria || body.acceptance || "Worker must satisfy task acceptance criteria and write ledger evidence.",
        600,
      ),
      risk_level: choice(body.risk_level, RISK_LEVELS, "medium"),
      budget_limit_usd: number(body.budget_limit_usd, 3),
      created_at: existing?.created_at || now,
      updated_at: now,
    };
    await client.query(
      `INSERT INTO tasks(
        task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,
        acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at
      ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
      ON CONFLICT(task_id) DO UPDATE SET
        title=EXCLUDED.title,description=EXCLUDED.description,requester_id=EXCLUDED.requester_id,
        owner_agent_id=EXCLUDED.owner_agent_id,collaborator_agent_ids=EXCLUDED.collaborator_agent_ids,status=EXCLUDED.status,
        priority=EXCLUDED.priority,due_date=EXCLUDED.due_date,acceptance_criteria=EXCLUDED.acceptance_criteria,
        risk_level=EXCLUDED.risk_level,budget_limit_usd=EXCLUDED.budget_limit_usd,updated_at=EXCLUDED.updated_at`,
      [
        row.task_id,
        row.workspace_id,
        row.title,
        row.description,
        row.requester_id,
        row.owner_agent_id,
        row.collaborator_agent_ids,
        row.status,
        row.priority,
        row.due_date,
        row.acceptance_criteria,
        row.risk_level,
        row.budget_limit_usd,
        row.created_at,
        row.updated_at,
      ],
    );
    const outcome = existing ? "updated" : "created";
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "system",
      actorId: "task-api",
      action: existing ? "task.update" : "task.create",
      entityType: "tasks",
      entityId: id,
      before: taskAuditSnapshot(existing),
      after: taskAuditSnapshot(row),
      metadata: {},
    });
    await appendRuntimeEvent(client, {
      eventType: existing ? "task.update" : "task.create",
      status: row.status,
      taskId: id,
      agentId: identity.agentId,
      inputSummary: `Task ${outcome} through TypeScript API: ${row.title}`.slice(0, 200),
      rawPayloadHash: stableHash({ task_id: id, title: row.title, owner_agent_id: row.owner_agent_id }),
    });
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "user",
      actorId: row.requester_id,
      action: existing ? "task.api_update" : "task.api_create",
      entityType: "tasks",
      entityId: id,
      before: taskAuditSnapshot(existing),
      after: taskAuditSnapshot(row),
      metadata: {
        workspace_id: row.workspace_id,
        source: "agent-gateway-typescript",
        raw_payload_omitted: true,
      },
    });
    return {
      status: existing ? 200 : 201,
      body: {
        ok: true,
        provider: "agentops-mis",
        control_plane: "typescript_postgres",
        operation: "task_create",
        outcome,
        task: row,
        task_id: id,
        workspace_id: row.workspace_id,
        token_omitted: true,
      },
    };
  });
}
