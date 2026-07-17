import type { PoolClient } from "pg";

import { authenticateAgentGateway, enforceWorkspaceBinding } from "./auth";
import { withPostgresTransaction } from "./db";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, appendRuntimeEvent, newLedgerId, pythonFloat, stableHash } from "./ledger";

const TASK_STATUSES = new Set(["backlog", "planned", "running", "waiting_approval", "blocked", "completed", "failed", "canceled"]);
const PRIORITIES = new Set(["low", "medium", "high", "urgent"]);
const RISK_LEVELS = new Set(["low", "medium", "high", "critical"]);

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
