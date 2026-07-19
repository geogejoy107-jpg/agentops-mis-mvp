import type { PoolClient } from "pg";

import { withPostgresTransaction } from "./db";
import { authenticateHumanMember } from "./humanSession";
import { ControlPlaneHttpError } from "./http";

type TaskRow = {
  task_id: string;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  risk_level: string;
  owner_agent_id: string | null;
  acceptance_criteria: string | null;
  budget_limit_usd: number;
  created_at: string;
  updated_at: string;
};

type RunRow = {
  run_id: string;
  task_id: string;
  agent_id: string;
  runtime_type: string;
  status: string;
  duration_ms: number | null;
  cost_usd: number;
  started_at: string;
  created_at: string;
};

type ApprovalRow = {
  approval_id: string;
  decision: string;
  task_id: string;
  run_id: string;
  tool_call_id: string | null;
  requested_by_agent_id: string | null;
  reason: string | null;
  expires_at: string | null;
  decided_at: string | null;
};

type AuditRow = {
  audit_id: string;
  actor_type: string;
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  created_at: string;
};

type CountMetricsRow = {
  agents_total: number;
  agents_running: number;
  tasks_completed_total: number;
  total_cost_usd: number;
  failure_rate: number;
  pending_approvals: number;
  stale_or_due_memories: number;
};

type StatusCountRow = { status: string; count: number };
type AgentCostRow = { agent_id: string; name: string; cost_usd: number };
function boundedLimit(value: unknown, fallback: number) {
  const raw = String(value ?? "").trim();
  if (!raw) return fallback;
  if (!/^\d+$/.test(raw) || Number(raw) < 1 || Number(raw) > 200) {
    throw new ControlPlaneHttpError(400, "limit_invalid", "limit must be an integer between 1 and 200.");
  }
  return Number(raw);
}

function optionalIdentifierFilter(name: "task_id" | "agent_id", value: unknown) {
  const normalized = String(value ?? "").trim();
  if (!normalized) return undefined;
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(400, `${name}_invalid`, `${name} must be a valid identifier.`);
  }
  return normalized;
}

async function taskRows(client: PoolClient, workspaceId: string, limit: number) {
  return client.query<TaskRow>(
    `SELECT task_id,title,description,status,priority,risk_level,owner_agent_id,
    acceptance_criteria,budget_limit_usd,created_at,updated_at
    FROM tasks WHERE workspace_id=$1
    ORDER BY created_at DESC,task_id DESC
    LIMIT $2`,
    [workspaceId, limit],
  );
}

async function runRows(
  client: PoolClient,
  workspaceId: string,
  limit: number,
  filters?: { taskId?: string; agentId?: string },
) {
  return client.query<RunRow>(
    `SELECT run_id,task_id,agent_id,runtime_type,status,duration_ms,cost_usd,started_at,created_at
    FROM runs WHERE workspace_id=$1
      AND ($2::text IS NULL OR task_id=$2)
      AND ($3::text IS NULL OR agent_id=$3)
    ORDER BY created_at DESC,run_id DESC
    LIMIT $4`,
    [workspaceId, filters?.taskId || null, filters?.agentId || null, limit],
  );
}

export async function listWorkspaceTasks(headers: Headers, workspaceId: unknown, suppliedLimit: unknown) {
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const result = await taskRows(client, identity.workspaceId, limit);
    return { status: 200, body: result.rows };
  });
}

export async function listWorkspaceRuns(
  headers: Headers,
  workspaceId: unknown,
  suppliedLimit: unknown,
  filters?: { taskId?: string | null; agentId?: string | null },
) {
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const result = await runRows(client, identity.workspaceId, limit, {
      taskId: optionalIdentifierFilter("task_id", filters?.taskId),
      agentId: optionalIdentifierFilter("agent_id", filters?.agentId),
    });
    return { status: 200, body: result.rows };
  });
}

export async function listWorkspaceApprovals(headers: Headers, workspaceId: unknown, suppliedLimit: unknown) {
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const result = await client.query<ApprovalRow>(
      `SELECT approval.approval_id,approval.decision,approval.task_id,approval.run_id,
      approval.tool_call_id,approval.requested_by_agent_id,approval.reason,
      approval.expires_at,approval.decided_at
      FROM approvals approval
      JOIN tasks task ON task.task_id=approval.task_id
      JOIN runs run ON run.run_id=approval.run_id AND run.task_id=task.task_id
      LEFT JOIN tool_calls tool ON tool.tool_call_id=approval.tool_call_id
      WHERE task.workspace_id=$1 AND run.workspace_id=$1
        AND (approval.tool_call_id IS NULL OR tool.run_id=approval.run_id)
      ORDER BY approval.created_at DESC,approval.approval_id DESC
      LIMIT $2`,
      [identity.workspaceId, limit],
    );
    return { status: 200, body: result.rows };
  });
}

export async function listWorkspaceAudit(headers: Headers, workspaceId: unknown, suppliedLimit: unknown) {
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const result = await client.query<AuditRow>(
      `SELECT audit.audit_id,audit.actor_type,audit.actor_id,audit.action,
      audit.entity_type,audit.entity_id,audit.created_at
      FROM audit_logs audit
      WHERE audit.workspace_id=$1
        AND audit.metadata_json::jsonb ->> 'workspace_id'=$1
      ORDER BY audit.created_at DESC,audit.audit_id DESC
      LIMIT $2`,
      [identity.workspaceId, limit],
    );
    return { status: 200, body: result.rows };
  });
}

export async function workspaceDashboardMetrics(headers: Headers, workspaceId: unknown) {
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const metrics = await client.query<CountMetricsRow>(
      `WITH workspace_agents AS (
        SELECT owner_agent_id AS agent_id FROM tasks
        WHERE workspace_id=$1 AND owner_agent_id IS NOT NULL
        UNION
        SELECT agent_id FROM runs WHERE workspace_id=$1
        UNION
        SELECT agent_id FROM agent_gateway_tokens
        WHERE workspace_id=$1 AND status='active' AND revoked_at IS NULL
          AND (expires_at IS NULL OR expires_at>$2)
        UNION
        SELECT agent_id FROM agent_gateway_sessions
        WHERE workspace_id=$1 AND status='active' AND revoked_at IS NULL AND expires_at>$2
      )
      SELECT
        (SELECT COUNT(*)::int FROM workspace_agents) AS agents_total,
        (SELECT COUNT(DISTINCT agent_id)::int FROM runs
          WHERE workspace_id=$1 AND status='running') AS agents_running,
        (SELECT COUNT(*)::int FROM tasks
          WHERE workspace_id=$1 AND status='completed') AS tasks_completed_total,
        (SELECT COALESCE(SUM(cost_usd),0)::float8 FROM runs
          WHERE workspace_id=$1) AS total_cost_usd,
        (SELECT COALESCE(
          COUNT(*) FILTER (WHERE status IN ('failed','blocked'))::float8 / NULLIF(COUNT(*),0),0
        )::float8 FROM tasks WHERE workspace_id=$1) AS failure_rate,
        (SELECT COUNT(*)::int FROM approvals approval
          JOIN tasks task ON task.task_id=approval.task_id
          JOIN runs run ON run.run_id=approval.run_id AND run.task_id=task.task_id
          LEFT JOIN tool_calls tool ON tool.tool_call_id=approval.tool_call_id
          WHERE task.workspace_id=$1 AND run.workspace_id=$1 AND approval.decision='pending'
            AND (approval.tool_call_id IS NULL OR tool.run_id=approval.run_id)
        ) AS pending_approvals,
        (SELECT COUNT(*)::int FROM memories
          WHERE workspace_id=$1 AND (
            review_status='stale'
            OR (ttl_review_due_at IS NOT NULL AND ttl_review_due_at <= $2)
          )) AS stale_or_due_memories`,
      [identity.workspaceId, new Date().toISOString()],
    );
    const recentRuns = await runRows(client, identity.workspaceId, 20);
    const statusDistribution = await client.query<StatusCountRow>(
      `SELECT status,COUNT(*)::int AS count FROM tasks
      WHERE workspace_id=$1 GROUP BY status ORDER BY status`,
      [identity.workspaceId],
    );
    const topCostAgents = await client.query<AgentCostRow>(
      `SELECT run.agent_id,COALESCE(agent.name,run.agent_id) AS name,
      COALESCE(SUM(run.cost_usd),0)::float8 AS cost_usd
      FROM runs run LEFT JOIN agents agent ON agent.agent_id=run.agent_id
      WHERE run.workspace_id=$1
      GROUP BY run.agent_id,agent.name
      ORDER BY cost_usd DESC,run.agent_id
      LIMIT 5`,
      [identity.workspaceId],
    );
    return {
      status: 200,
      body: {
        ...(metrics.rows[0] || {
          agents_total: 0,
          agents_running: 0,
          tasks_completed_total: 0,
          total_cost_usd: 0,
          failure_rate: 0,
          pending_approvals: 0,
          stale_or_due_memories: 0,
        }),
        recent_runs: recentRuns.rows,
        task_status_distribution: statusDistribution.rows,
        top_cost_agents: topCostAgents.rows,
      },
    };
  });
}
