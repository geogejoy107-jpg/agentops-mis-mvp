import type { PoolClient } from "pg";
import { NextRequest, NextResponse } from "next/server";

import {
  controlPlaneMode,
  legacyPythonProxyAllowed,
} from "./config";
import { withPostgresTransaction } from "./db";
import { authenticateHumanMember } from "./humanSession";
import { ControlPlaneHttpError, errorPayload } from "./http";
import { appendAudit, stableHash } from "./ledger";
import { proxyControlPlaneRequest } from "./proxy";

const AGENT_DETAIL_ROLES = new Set([
  "operator",
  "approver",
  "workspace-admin",
  "owner",
]);
const COMMERCIAL_AGENT_EDITIONS = new Set([
  "pro_workspace",
  "team_governance",
  "enterprise_byoc",
]);
const KNOWN_ENTITLEMENT_STATUSES = new Set([
  "inactive",
  "suspended",
  "expired",
]);
const RELATED_RUN_LIMIT = 50;
const RELATED_TASK_LIMIT = 50;
const PRIVATE_READ_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, X-AgentOps-Workspace-Id",
};

type EntitlementRow = {
  edition: string;
  status: string;
  effective_at: Date | string;
  expires_at: Date | string | null;
};

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
  budget_limit_usd: number;
  created_at: string;
  updated_at: string;
};

type RunRow = {
  run_id: string;
  task_id: string;
  runtime_type: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  model_provider: string | null;
  model_name: string | null;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cost_usd: number;
  approval_required: number;
  created_at: string;
};

type TaskRow = {
  task_id: string;
  title: string;
  status: string;
  priority: string;
  due_date: string | null;
  risk_level: string;
  budget_limit_usd: number;
  created_at: string;
  updated_at: string;
};

function identifier(value: unknown, field: string) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      `human_agent_${field}_invalid`,
      `${field} must use the bounded MIS identifier format.`,
    );
  }
  return normalized;
}

function boundedText(
  value: unknown,
  field: string,
  maximum: number,
  nullable = false,
) {
  if (value === null && nullable) return null;
  if (typeof value !== "string" || value.length > maximum) {
    throw new ControlPlaneHttpError(
      503,
      "human_agent_detail_state_invalid",
      `The stored ${field} is outside the bounded Agent detail contract.`,
    );
  }
  return value;
}

function boundedNumber(value: unknown, field: string, minimum = 0) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < minimum) {
    throw new ControlPlaneHttpError(
      503,
      "human_agent_detail_state_invalid",
      `The stored ${field} is outside the bounded Agent detail contract.`,
    );
  }
  return parsed;
}

function boundedTools(raw: string) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    parsed = null;
  }
  if (!Array.isArray(parsed) || parsed.length > 64) {
    throw new ControlPlaneHttpError(
      503,
      "human_agent_detail_state_invalid",
      "The stored allowed tool set is outside the bounded Agent detail contract.",
    );
  }
  const tools = parsed.map((value) => boundedText(value, "allowed tool", 128));
  if (new Set(tools).size !== tools.length) {
    throw new ControlPlaneHttpError(
      503,
      "human_agent_detail_state_invalid",
      "The stored allowed tool set is not canonical.",
    );
  }
  return [...tools].sort();
}

function asTimestamp(value: Date | string | null) {
  if (value === null) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}

function rejectUnknownQuery(request: Request) {
  const searchParams = new URL(request.url).searchParams;
  const keys = [...new Set(searchParams.keys())];
  if (keys.some((key) => key !== "workspace_id")) {
    throw new ControlPlaneHttpError(
      400,
      "human_agent_detail_query_unsupported",
      "The Agent detail read received an unsupported query parameter.",
    );
  }
  const values = searchParams.getAll("workspace_id");
  if (values.length > 1) {
    throw new ControlPlaneHttpError(
      400,
      "human_agent_detail_query_ambiguous",
      "Agent detail workspace binding must have one value.",
    );
  }
  return values[0] ?? "";
}

async function assertActiveCommercialEntitlement(
  client: PoolClient,
  workspaceId: string,
) {
  await client.query(
    "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
    [`agentops:workspace-entitlement:${workspaceId}`],
  );
  const now = asTimestamp((await client.query<{ evaluated_at: Date | string }>(
    "SELECT clock_timestamp() AS evaluated_at",
  )).rows[0]?.evaluated_at ?? "");
  const entitlement = (await client.query<EntitlementRow>(
    `SELECT edition,status,effective_at,expires_at
    FROM workspace_entitlements WHERE workspace_id=$1`,
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
    const known = KNOWN_ENTITLEMENT_STATUSES.has(entitlement.status);
    throw new ControlPlaneHttpError(
      known ? 403 : 503,
      known
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
  if (!COMMERCIAL_AGENT_EDITIONS.has(entitlement.edition)) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_edition_forbidden",
      "Agent detail reads require a commercial workspace edition.",
    );
  }
  return entitlement.edition;
}

function publicAgent(row: AgentRow) {
  return {
    agent_id: identifier(row.agent_id, "agent_id"),
    name: boundedText(row.name, "Agent name", 200),
    role: boundedText(row.role, "Agent role", 128),
    description: boundedText(row.description, "Agent description", 2_000, true),
    runtime_type: boundedText(row.runtime_type, "runtime type", 64),
    model_provider: boundedText(row.model_provider, "model provider", 128, true),
    model_name: boundedText(row.model_name, "model name", 256, true),
    status: boundedText(row.status, "Agent status", 32),
    permission_level: boundedText(row.permission_level, "permission level", 64),
    allowed_tools: boundedTools(row.allowed_tools),
    budget_limit_usd: boundedNumber(row.budget_limit_usd, "Agent budget"),
    created_at: boundedText(row.created_at, "Agent created timestamp", 64),
    updated_at: boundedText(row.updated_at, "Agent updated timestamp", 64),
  };
}

function publicRun(row: RunRow) {
  return {
    run_id: identifier(row.run_id, "run_id"),
    task_id: identifier(row.task_id, "task_id"),
    runtime_type: boundedText(row.runtime_type, "run runtime type", 64),
    status: boundedText(row.status, "run status", 32),
    started_at: boundedText(row.started_at, "run start timestamp", 64),
    ended_at: boundedText(row.ended_at, "run end timestamp", 64, true),
    duration_ms: row.duration_ms === null
      ? null
      : boundedNumber(row.duration_ms, "run duration"),
    model_provider: boundedText(row.model_provider, "run model provider", 128, true),
    model_name: boundedText(row.model_name, "run model name", 256, true),
    input_tokens: boundedNumber(row.input_tokens, "run input tokens"),
    output_tokens: boundedNumber(row.output_tokens, "run output tokens"),
    reasoning_tokens: boundedNumber(row.reasoning_tokens, "run reasoning tokens"),
    cost_usd: boundedNumber(row.cost_usd, "run cost"),
    approval_required: row.approval_required === 1,
    created_at: boundedText(row.created_at, "run created timestamp", 64),
  };
}

function publicTask(row: TaskRow) {
  return {
    task_id: identifier(row.task_id, "task_id"),
    title: boundedText(row.title, "task title", 500),
    status: boundedText(row.status, "task status", 32),
    priority: boundedText(row.priority, "task priority", 32),
    due_date: boundedText(row.due_date, "task due date", 64, true),
    risk_level: boundedText(row.risk_level, "task risk level", 32),
    budget_limit_usd: boundedNumber(row.budget_limit_usd, "task budget"),
    created_at: boundedText(row.created_at, "task created timestamp", 64),
    updated_at: boundedText(row.updated_at, "task updated timestamp", 64),
  };
}

async function readCommercialAgentDetail(
  client: PoolClient,
  workspaceId: string,
  agentId: string,
) {
  const agent = (await client.query<AgentRow>(
    `SELECT agent.agent_id,agent.name,agent.role,agent.description,
      agent.runtime_type,agent.model_provider,agent.model_name,agent.status,
      agent.permission_level,agent.allowed_tools,agent.budget_limit_usd,
      agent.created_at,agent.updated_at
    FROM agents agent
    WHERE agent.agent_id=$2 AND EXISTS (
      SELECT 1 FROM agent_gateway_tokens token
      WHERE token.workspace_id=$1 AND token.agent_id=agent.agent_id
      UNION ALL
      SELECT 1 FROM agent_gateway_sessions session
      WHERE session.workspace_id=$1 AND session.agent_id=agent.agent_id
      UNION ALL
      SELECT 1 FROM runs run
      WHERE run.workspace_id=$1 AND run.agent_id=agent.agent_id
      UNION ALL
      SELECT 1 FROM tasks task
      WHERE task.workspace_id=$1 AND (
        task.owner_agent_id=agent.agent_id
        OR task.collaborator_agent_ids::jsonb ? agent.agent_id
      )
    )`,
    [workspaceId, agentId],
  )).rows[0];
  if (!agent) {
    throw new ControlPlaneHttpError(
      404,
      "human_agent_not_found",
      "The Agent was not found in this workspace.",
    );
  }
  const runs = await client.query<RunRow>(
    `SELECT run_id,task_id,runtime_type,status,started_at,ended_at,duration_ms,
      model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,
      cost_usd,approval_required,created_at
    FROM runs WHERE workspace_id=$1 AND agent_id=$2
    ORDER BY created_at DESC,run_id LIMIT $3`,
    [workspaceId, agentId, RELATED_RUN_LIMIT],
  );
  const tasks = await client.query<TaskRow>(
    `SELECT task_id,title,status,priority,due_date,risk_level,budget_limit_usd,
      created_at,updated_at
    FROM tasks WHERE workspace_id=$1 AND (
      owner_agent_id=$2 OR collaborator_agent_ids::jsonb ? $2
    )
    ORDER BY created_at DESC,task_id LIMIT $3`,
    [workspaceId, agentId, RELATED_TASK_LIMIT],
  );
  return {
    agent: publicAgent(agent),
    runs: runs.rows.map(publicRun),
    tasks: tasks.rows.map(publicTask),
  };
}

export async function ownHumanAgentDetailGet(
  request: NextRequest,
  rawAgentId: unknown,
) {
  try {
    const agentId = identifier(rawAgentId, "agent_id");
    if (controlPlaneMode() === "proxy") {
      if (!legacyPythonProxyAllowed()) {
        throw new ControlPlaneHttpError(
          503,
          "human_agent_detail_direct_route_required",
          "Production Agent detail reads require TypeScript Postgres authority.",
        );
      }
      const response = await proxyControlPlaneRequest(
        request,
        `/agents/${encodeURIComponent(agentId)}`,
      );
      response.headers.set("Cache-Control", PRIVATE_READ_HEADERS["Cache-Control"]);
      response.headers.set("Vary", PRIVATE_READ_HEADERS.Vary);
      return response;
    }
    const requestedWorkspace = rejectUnknownQuery(request);
    const body = await withPostgresTransaction(async (client) => {
      const identity = await authenticateHumanMember(
        client,
        request.headers,
        requestedWorkspace,
      );
      const role = identity.membershipRole.trim().toLowerCase();
      if (!AGENT_DETAIL_ROLES.has(role)) {
        throw new ControlPlaneHttpError(
          403,
          "human_agent_detail_role_forbidden",
          "Agent detail reads require operator, approver, workspace-admin, or owner authority.",
        );
      }
      const edition = await assertActiveCommercialEntitlement(
        client,
        identity.workspaceId,
      );
      const detail = await readCommercialAgentDetail(
        client,
        identity.workspaceId,
        agentId,
      );
      await appendAudit(client, {
        workspaceId: identity.workspaceId,
        actorType: "user",
        actorId: identity.userId,
        action: "human.agent_detail_read",
        entityType: "agents",
        entityId: agentId,
        metadata: {
          membership_role: role,
          route: "GET /api/mis/agents/:agentId",
          raw_payload_omitted: true,
          session_credential_omitted: true,
          token_omitted: true,
        },
        requestHash: stableHash({
          workspace_id: identity.workspaceId,
          user_id: identity.userId,
          agent_id: agentId,
          operation: "human.agent_detail_read",
        }),
      });
      return {
        ok: true,
        control_plane: "typescript_postgres",
        workspace_id: identity.workspaceId,
        entitlement_edition: edition,
        ...detail,
        bounds: {
          related_runs_limit: RELATED_RUN_LIMIT,
          related_tasks_limit: RELATED_TASK_LIMIT,
        },
        audit_recorded: true,
        python_proxy_performed: false,
        raw_prompt_omitted: true,
        raw_response_omitted: true,
        credentials_omitted: true,
        token_omitted: true,
      };
    });
    return NextResponse.json(body, {
      status: 200,
      headers: PRIVATE_READ_HEADERS,
    });
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: PRIVATE_READ_HEADERS,
    });
  }
}
