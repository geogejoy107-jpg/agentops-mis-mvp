import type { PoolClient } from "pg";

import {
  authenticateAgentGateway,
  enforceWorkspaceBinding,
  type AgentGatewayIdentity,
} from "./auth";
import { boundedJsonObject } from "./boundedJson";
import { withPostgresTransaction } from "./db";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, appendRuntimeEvent } from "./ledger";

const AGENT_STATUSES = new Set(["idle", "running", "paused", "error", "disabled"]);
const RUNTIME_TYPES = new Set([
  "mock",
  "claude_code",
  "codex",
  "openhands",
  "crewai",
  "langgraph",
  "openclaw",
  "hermes",
]);
const AUDIT_ENTITY_TYPES = new Set(["agents", "agent_gateway", "runs", "tasks"]);
const SENSITIVE_KEY = /(authorization|cookie|credential|password|secret|token|api[_-]?key|raw[_-]?(prompt|response|transcript|content|metadata))/i;

type AgentRow = {
  agent_id: string;
  name: string;
  role: string;
  description: string | null;
  runtime_type: string;
  model_provider: string | null;
  model_name: string | null;
  status: string;
  permission_level: string;
  allowed_tools: string;
  budget_limit_usd: number | string;
  owner_user_id: string | null;
  created_at: string;
  updated_at: string;
};

type TaskBindingRow = {
  task_id: string;
  workspace_id: string;
  owner_agent_id: string | null;
  collaborator_agent_ids: string;
};

type RunBindingRow = {
  run_id: string;
  workspace_id: string;
  task_id: string;
  agent_id: string;
};

type SafeJsonResult = {
  value: unknown;
  omitted: number;
};

function redactText(value: unknown, limit: number) {
  return String(value ?? "")
    .replace(/-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----/g, "[PRIVATE_KEY_REDACTED]")
    .replace(/(bearer\s+)[a-z0-9._-]+/gi, "$1[REDACTED]")
    .replace(/(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;]+/gi, "$1=[REDACTED]")
    .replace(/\b(?:sk-[a-z0-9._-]+|ntn_[a-z0-9._-]+|github_pat_[a-z0-9_]+)\b/gi, "[SECRET_REDACTED]")
    .replace(/\b(?:agtok|agtsess)_[A-Za-z0-9_-]+\b/g, "[AGENT_TOKEN_REF_REDACTED]")
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "[EMAIL_REDACTED]")
    .replace(/(?<![\w])\+?\d{10,15}(?![\w])/g, "[PHONE_REDACTED]")
    .trim()
    .slice(0, limit);
}

function requiredIdentifier(value: unknown, field: string, limit = 160) {
  if (typeof value !== "string") {
    throw new ControlPlaneHttpError(400, `${field}_required`, `${field} is required.`);
  }
  const normalized = value.trim();
  if (!normalized || normalized.length > limit || !/^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(normalized)) {
    throw new ControlPlaneHttpError(400, `${field}_invalid`, `${field} is invalid.`);
  }
  return normalized;
}

function optionalIdentifier(value: unknown, field: string, limit = 160) {
  if (value === undefined || value === null || value === "") return null;
  return requiredIdentifier(value, field, limit);
}

function choice(value: unknown, allowed: Set<string>, fallback: string) {
  const normalized = String(value ?? "").trim().toLowerCase();
  return allowed.has(normalized) ? normalized : fallback;
}

function finiteBudget(value: unknown) {
  const parsed = value === undefined || value === null || value === "" ? 5 : Number(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1_000_000) {
    throw new ControlPlaneHttpError(400, "budget_limit_usd_invalid", "budget_limit_usd must be a bounded non-negative number.");
  }
  return parsed;
}

function safeTools(value: unknown) {
  const candidate = value === undefined || value === null
    ? ["agent_gateway.task", "agent_gateway.run", "agent_gateway.audit"]
    : Array.isArray(value)
      ? value
      : [value];
  if (candidate.length > 64) {
    throw new ControlPlaneHttpError(400, "allowed_tools_invalid", "allowed_tools exceeds the maximum item count.");
  }
  return candidate
    .map((item) => redactText(item, 120))
    .filter(Boolean);
}

function sanitizeJson(value: unknown, depth = 0): SafeJsonResult {
  if (depth > 5) return { value: "[OMITTED]", omitted: 1 };
  if (value === null || typeof value === "boolean") return { value, omitted: 0 };
  if (typeof value === "number") return { value: Number.isFinite(value) ? value : null, omitted: Number.isFinite(value) ? 0 : 1 };
  if (typeof value === "string") return { value: redactText(value, 600), omitted: 0 };
  if (Array.isArray(value)) {
    let omitted = Math.max(0, value.length - 32);
    const items = value.slice(0, 32).map((item) => {
      const safe = sanitizeJson(item, depth + 1);
      omitted += safe.omitted;
      return safe.value;
    });
    return { value: items, omitted };
  }
  if (value && typeof value === "object") {
    let omitted = 0;
    const entries: Array<[string, unknown]> = [];
    for (const [rawKey, item] of Object.entries(value as Record<string, unknown>).slice(0, 64)) {
      const key = redactText(rawKey, 80);
      if (!key || SENSITIVE_KEY.test(key)) {
        omitted += 1;
        continue;
      }
      const safe = sanitizeJson(item, depth + 1);
      omitted += safe.omitted;
      entries.push([key, safe.value]);
    }
    omitted += Math.max(0, Object.keys(value).length - 64);
    return { value: Object.fromEntries(entries.sort(([left], [right]) => left.localeCompare(right))), omitted };
  }
  return { value: null, omitted: 1 };
}

function assertAgentIdentity(identity: AgentGatewayIdentity, body: Record<string, unknown>, message: string) {
  if (body.agent_id !== undefined && requiredIdentifier(body.agent_id, "agent_id", 120) !== identity.agentId) {
    throw new ControlPlaneHttpError(403, "forbidden", message);
  }
}

function enforceMachineBinding(
  identity: AgentGatewayIdentity,
  request: Request,
  body: Record<string, unknown>,
  agentMessage: string,
) {
  if (body.workspace_id !== undefined && typeof body.workspace_id !== "string") {
    throw new ControlPlaneHttpError(400, "workspace_id_invalid", "workspace_id must be a string.");
  }
  enforceWorkspaceBinding(identity, {
    header: request.headers.get("x-agentops-workspace-id"),
    body: body.workspace_id,
  });
  assertAgentIdentity(identity, body, agentMessage);
}

async function assertExclusiveWorkspaceBinding(client: PoolClient, identity: AgentGatewayIdentity) {
  const result = await client.query<{ workspace_id: string }>(
    `SELECT workspace_id FROM (
      SELECT workspace_id FROM agent_gateway_tokens WHERE agent_id=$1
      UNION
      SELECT workspace_id FROM agent_gateway_sessions WHERE agent_id=$1
    ) bindings WHERE workspace_id<>$2 LIMIT 1`,
    [identity.agentId, identity.workspaceId],
  );
  if (result.rows[0]) {
    throw new ControlPlaneHttpError(
      409,
      "agent_workspace_binding_conflict",
      "Agent identity is already bound to another workspace.",
    );
  }
}

function comparableAgent(row: AgentRow) {
  return {
    agent_id: row.agent_id,
    name: row.name,
    role: row.role,
    description: row.description,
    runtime_type: row.runtime_type,
    model_provider: row.model_provider,
    model_name: row.model_name,
    status: row.status,
    permission_level: row.permission_level,
    allowed_tools: row.allowed_tools,
    budget_limit_usd: Number(row.budget_limit_usd),
    owner_user_id: row.owner_user_id,
  };
}

function sameAgent(left: AgentRow, right: AgentRow) {
  return JSON.stringify(comparableAgent(left)) === JSON.stringify(comparableAgent(right));
}

function collaboratorIds(task: TaskBindingRow) {
  try {
    const parsed = JSON.parse(task.collaborator_agent_ids || "[]");
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function assertTaskAccess(task: TaskBindingRow, identity: AgentGatewayIdentity) {
  if (task.owner_agent_id !== identity.agentId && !collaboratorIds(task).includes(identity.agentId)) {
    throw new ControlPlaneHttpError(403, "forbidden", "Task is assigned to another agent.");
  }
}

async function lockTask(client: PoolClient, identity: AgentGatewayIdentity, taskId: string) {
  const candidate = await client.query<TaskBindingRow>(
    "SELECT task_id,workspace_id,owner_agent_id,collaborator_agent_ids FROM tasks WHERE task_id=$1 AND workspace_id=$2",
    [taskId, identity.workspaceId],
  );
  if (!candidate.rows[0]) {
    throw new ControlPlaneHttpError(404, "task_not_found", "Task was not found in the credential workspace.");
  }
  await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-task:${taskId}`]);
  const locked = await client.query<TaskBindingRow>(
    "SELECT task_id,workspace_id,owner_agent_id,collaborator_agent_ids FROM tasks WHERE task_id=$1 AND workspace_id=$2 FOR UPDATE",
    [taskId, identity.workspaceId],
  );
  const task = locked.rows[0];
  if (!task) throw new ControlPlaneHttpError(404, "task_not_found", "Task was not found in the credential workspace.");
  assertTaskAccess(task, identity);
  return task;
}

async function lockRun(client: PoolClient, identity: AgentGatewayIdentity, runId: string, requestedTaskId: string | null) {
  const candidate = await client.query<RunBindingRow>(
    "SELECT run_id,workspace_id,task_id,agent_id FROM runs WHERE run_id=$1 AND workspace_id=$2",
    [runId, identity.workspaceId],
  );
  const before = candidate.rows[0];
  if (!before) throw new ControlPlaneHttpError(404, "run_not_found", "Run was not found in the credential workspace.");
  if (before.agent_id !== identity.agentId) {
    throw new ControlPlaneHttpError(403, "forbidden", "Run belongs to another agent.");
  }
  if (requestedTaskId && requestedTaskId !== before.task_id) {
    throw new ControlPlaneHttpError(403, "forbidden", "Audit task_id must match the referenced run.");
  }
  const task = await lockTask(client, identity, before.task_id);
  await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-run:${runId}`]);
  const locked = await client.query<RunBindingRow>(
    "SELECT run_id,workspace_id,task_id,agent_id FROM runs WHERE run_id=$1 AND workspace_id=$2 FOR UPDATE",
    [runId, identity.workspaceId],
  );
  const run = locked.rows[0];
  if (!run) throw new ControlPlaneHttpError(404, "run_not_found", "Run was not found in the credential workspace.");
  if (run.task_id !== before.task_id || run.agent_id !== before.agent_id) {
    throw new ControlPlaneHttpError(409, "run_immutable_binding_conflict", "Run binding changed while the audit write was waiting.");
  }
  return { run, task };
}

async function lockAuditBinding(
  client: PoolClient,
  identity: AgentGatewayIdentity,
  body: Record<string, unknown>,
  entityType: string,
  entityId: string,
) {
  const requestedRunId = optionalIdentifier(body.run_id, "run_id");
  const requestedTaskId = optionalIdentifier(body.task_id, "task_id");
  if (entityType === "agents") {
    if (entityId !== identity.agentId || requestedRunId || requestedTaskId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Agent audit entity does not match the credential identity.");
    }
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-agent:${identity.agentId}`]);
    const agent = await client.query<{ agent_id: string }>("SELECT agent_id FROM agents WHERE agent_id=$1 FOR UPDATE", [identity.agentId]);
    if (!agent.rows[0]) throw new ControlPlaneHttpError(404, "agent_not_found", "Agent was not found.");
    return { runId: null, taskId: null };
  }
  if (entityType === "agent_gateway") {
    if (entityId !== identity.agentId || requestedRunId || requestedTaskId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Agent Gateway audit entity does not match the credential identity.");
    }
    return { runId: null, taskId: null };
  }
  if (entityType === "runs" || requestedRunId) {
    const runId = requestedRunId || entityId;
    if (entityType !== "runs" || entityId !== runId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Audit entity_id must match the referenced run.");
    }
    const binding = await lockRun(client, identity, runId, requestedTaskId);
    return { runId: binding.run.run_id, taskId: binding.task.task_id };
  }
  if (entityType === "tasks" || requestedTaskId) {
    const taskId = requestedTaskId || entityId;
    if (entityType !== "tasks" || entityId !== taskId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Audit entity_id must match the referenced task.");
    }
    const task = await lockTask(client, identity, taskId);
    return { runId: null, taskId: task.task_id };
  }
  throw new ControlPlaneHttpError(400, "audit_binding_required", "Audit must bind to the credential agent, a task, or a run.");
}

export async function registerAgentGatewayWorker(request: Request) {
  const body = await boundedJsonObject(request, { maxBytes: 16 * 1024, label: "Agent Gateway register" });
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "agents:write");
    enforceMachineBinding(identity, request, body, "Agent credential cannot register another agent.");
    await assertExclusiveWorkspaceBinding(client, identity);
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-agent:${identity.agentId}`]);
    const existingResult = await client.query<AgentRow>("SELECT * FROM agents WHERE agent_id=$1 FOR UPDATE", [identity.agentId]);
    const before = existingResult.rows[0];
    const now = new Date().toISOString();
    const desired: AgentRow = {
      agent_id: identity.agentId,
      name: redactText(body.name ?? body.agent_name ?? "Gateway Agent", 120) || "Gateway Agent",
      role: redactText(body.role ?? "AI Digital Employee", 120) || "AI Digital Employee",
      description: redactText(body.description ?? "Agent registered through local Agent Gateway.", 360) || null,
      runtime_type: choice(body.runtime_type, RUNTIME_TYPES, "mock"),
      model_provider: redactText(body.model_provider ?? body.provider ?? "external", 80) || null,
      model_name: redactText(body.model_name ?? body.model ?? "gateway-client", 120) || null,
      status: choice(body.status, AGENT_STATUSES, "idle"),
      permission_level: redactText(body.permission_level ?? "standard", 80) || "standard",
      allowed_tools: JSON.stringify(safeTools(body.allowed_tools ?? body.scopes)),
      budget_limit_usd: finiteBudget(body.budget_limit_usd),
      owner_user_id: before?.owner_user_id || "usr_founder",
      created_at: before?.created_at || now,
      updated_at: now,
    };
    let outcome: "created" | "updated" | "unchanged";
    let after: AgentRow;
    if (!before) {
      const owner = await client.query<{ user_id: string }>("SELECT user_id FROM users WHERE user_id=$1", [desired.owner_user_id]);
      if (!owner.rows[0]) throw new ControlPlaneHttpError(409, "agent_owner_missing", "Agent owner reference is missing.");
      const inserted = await client.query<AgentRow>(
        `INSERT INTO agents(
          agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,
          allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING *`,
        [desired.agent_id, desired.name, desired.role, desired.description, desired.runtime_type,
          desired.model_provider, desired.model_name, desired.status, desired.permission_level,
          desired.allowed_tools, desired.budget_limit_usd, desired.owner_user_id, desired.created_at, desired.updated_at],
      );
      after = inserted.rows[0];
      outcome = "created";
    } else if (sameAgent(before, desired)) {
      after = before;
      outcome = "unchanged";
    } else {
      const updated = await client.query<AgentRow>(
        `UPDATE agents SET name=$2,role=$3,description=$4,runtime_type=$5,model_provider=$6,model_name=$7,
          status=$8,permission_level=$9,allowed_tools=$10,budget_limit_usd=$11,updated_at=$12
        WHERE agent_id=$1 RETURNING *`,
        [desired.agent_id, desired.name, desired.role, desired.description, desired.runtime_type,
          desired.model_provider, desired.model_name, desired.status, desired.permission_level,
          desired.allowed_tools, desired.budget_limit_usd, desired.updated_at],
      );
      after = updated.rows[0];
      outcome = "updated";
    }
    if (outcome !== "unchanged") {
      await appendAudit(client, {
        workspaceId: identity.workspaceId,
        actorType: "agent",
        actorId: identity.agentId,
        action: outcome === "created" ? "agent.create" : "agent.update",
        entityType: "agents",
        entityId: identity.agentId,
        before,
        after,
        metadata: { workspace_id: identity.workspaceId, credential_mode: identity.mode, raw_omitted: true },
      });
    }
    await appendRuntimeEvent(client, {
      eventType: "agent.register",
      status: "completed",
      agentId: identity.agentId,
      outputSummary: `${outcome}: ${after.name}`,
    });
    return { status: outcome === "created" ? 201 : 200, body: { agent: after, outcome } };
  });
}

export async function recordAgentGatewayHeartbeat(request: Request) {
  const body = await boundedJsonObject(request, { maxBytes: 8 * 1024, label: "Agent Gateway heartbeat" });
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "agents:heartbeat");
    enforceMachineBinding(identity, request, body, "Agent credential cannot heartbeat another agent.");
    await assertExclusiveWorkspaceBinding(client, identity);
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-agent:${identity.agentId}`]);
    const beforeResult = await client.query<AgentRow>("SELECT * FROM agents WHERE agent_id=$1 FOR UPDATE", [identity.agentId]);
    const before = beforeResult.rows[0];
    if (!before) throw new ControlPlaneHttpError(404, "agent_not_found", "Agent was not found.");
    const now = new Date().toISOString();
    const status = choice(body.status, AGENT_STATUSES, "idle");
    const updated = await client.query<AgentRow>(
      "UPDATE agents SET status=$2,updated_at=$3 WHERE agent_id=$1 RETURNING *",
      [identity.agentId, status, now],
    );
    const after = updated.rows[0];
    const heartbeatTokenId = identity.mode === "agent_token" ? identity.credentialId : identity.parentTokenId;
    if (!heartbeatTokenId) {
      throw new ControlPlaneHttpError(409, "heartbeat_parent_token_missing", "Heartbeat credential parent token is missing.");
    }
    const heartbeat = await client.query(
      `UPDATE agent_gateway_tokens SET last_heartbeat_at=$1,last_used_at=$1
      WHERE token_id=$2 AND workspace_id=$3 AND agent_id=$4`,
      [now, heartbeatTokenId, identity.workspaceId, identity.agentId],
    );
    if (heartbeat.rowCount !== 1) {
      throw new ControlPlaneHttpError(409, "heartbeat_credential_binding_conflict", "Heartbeat credential binding changed.");
    }
    const summary = redactText(body.summary ?? "Heartbeat recorded.", 240) || "Heartbeat recorded.";
    await appendRuntimeEvent(client, {
      eventType: "agent.heartbeat",
      status,
      agentId: identity.agentId,
      outputSummary: summary,
    });
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "agent",
      actorId: identity.agentId,
      action: "agent_gateway.heartbeat",
      entityType: "agents",
      entityId: identity.agentId,
      before,
      after,
      metadata: {
        workspace_id: identity.workspaceId,
        credential_mode: identity.mode,
        raw_summary_omitted: true,
      },
    });
    return { status: 200, body: { agent_id: identity.agentId, status, recorded_at: now } };
  });
}

export async function emitAgentGatewayAudit(request: Request) {
  const body = await boundedJsonObject(request, { maxBytes: 32 * 1024, label: "Agent Gateway audit" });
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "audit:write");
    enforceMachineBinding(identity, request, body, "Agent credential cannot emit audit as another agent.");
    await assertExclusiveWorkspaceBinding(client, identity);
    const requestedEntityType = String(body.entity_type ?? "agent_gateway").trim().toLowerCase();
    if (!AUDIT_ENTITY_TYPES.has(requestedEntityType)) {
      throw new ControlPlaneHttpError(400, "entity_type_invalid", "entity_type is not supported by the Agent Gateway audit boundary.");
    }
    const entityType = requestedEntityType;
    const entityId = body.entity_id === undefined
      ? identity.agentId
      : requiredIdentifier(body.entity_id, "entity_id");
    const action = redactText(body.action ?? "agent_gateway.audit_emit", 160) || "agent_gateway.audit_emit";
    const binding = await lockAuditBinding(client, identity, body, entityType, entityId);
    const safeMetadata = sanitizeJson(
      body.metadata && typeof body.metadata === "object" && !Array.isArray(body.metadata) ? body.metadata : {},
    );
    const safeAfter = sanitizeJson(body.after ?? { status: "emitted" });
    const metadata = {
      ...(safeMetadata.value as Record<string, unknown>),
      workspace_id: identity.workspaceId,
      agent_id: identity.agentId,
      credential_mode: identity.mode,
      raw_omitted: true,
      raw_metadata_omitted: true,
      omitted_metadata_fields: safeMetadata.omitted,
      omitted_after_fields: safeAfter.omitted,
    };
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "agent",
      actorId: identity.agentId,
      action,
      entityType,
      entityId,
      after: safeAfter.value,
      metadata,
    });
    await appendRuntimeEvent(client, {
      eventType: "audit.emit",
      status: "completed",
      runId: binding.runId,
      taskId: binding.taskId,
      agentId: identity.agentId,
      outputSummary: `Audit emitted: ${action}`,
    });
    return {
      status: 201,
      body: { emitted: true, entity_type: entityType, entity_id: entityId, token_omitted: true },
    };
  });
}
