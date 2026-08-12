import type { PoolClient } from "pg";

import { withPostgresTransaction } from "./db";
import { authenticateHumanMember } from "./humanSession";
import { ControlPlaneHttpError } from "./http";
import type { HumanReadResult } from "./humanReadRoute";

type HumanReadWork = (
  client: PoolClient,
  workspaceId: string,
  searchParams: URLSearchParams,
) => Promise<Record<string, unknown> | Array<Record<string, unknown>>>;

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
  owner_user_id: string | null;
  created_at: string;
  updated_at: string;
};

type AggregateRow = Record<string, string | number | null>;

const WORKSPACE_AGENT_CTE = `
workspace_agent_ids AS (
  SELECT token.agent_id
  FROM agent_gateway_tokens token
  WHERE token.workspace_id=$1
  UNION
  SELECT run.agent_id
  FROM runs run
  WHERE run.workspace_id=$1
  UNION
  SELECT task.owner_agent_id
  FROM tasks task
  WHERE task.workspace_id=$1 AND task.owner_agent_id IS NOT NULL
)`;

function rejectUnknownParameters(
  searchParams: URLSearchParams,
  allowed: readonly string[],
) {
  const allowlist = new Set(allowed);
  for (const key of new Set(searchParams.keys())) {
    if (!allowlist.has(key)) {
      throw new ControlPlaneHttpError(
        400,
        "human_read_query_unsupported",
        "The Human read received an unsupported query parameter.",
      );
    }
  }
}

function singleParameter(searchParams: URLSearchParams, name: string) {
  const values = searchParams.getAll(name);
  if (values.length > 1) {
    throw new ControlPlaneHttpError(
      400,
      "human_read_query_ambiguous",
      "Human read query parameters must have one value.",
    );
  }
  return values[0] ?? "";
}

function identifierParameter(
  searchParams: URLSearchParams,
  name: string,
) {
  const value = singleParameter(searchParams, name).trim();
  if (!value) return "";
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(value)) {
    throw new ControlPlaneHttpError(
      400,
      "human_read_identifier_invalid",
      "Human read identifiers must use the bounded MIS identifier format.",
    );
  }
  return value;
}

function identifier(value: unknown, label: string) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      "human_read_identifier_invalid",
      `${label} must use the bounded MIS identifier format.`,
    );
  }
  return normalized;
}

function boundedInteger(
  searchParams: URLSearchParams,
  name: string,
  fallback: number,
  maximum: number,
  allowZero = false,
) {
  const value = singleParameter(searchParams, name).trim();
  if (!value) return fallback;
  if (!/^[0-9]{1,6}$/.test(value)) {
    throw new ControlPlaneHttpError(
      400,
      "human_read_pagination_invalid",
      "Human read pagination is invalid.",
    );
  }
  const parsed = Number(value);
  const minimum = allowZero ? 0 : 1;
  if (parsed < minimum || parsed > maximum) {
    throw new ControlPlaneHttpError(
      400,
      "human_read_pagination_invalid",
      "Human read pagination is outside the allowed range.",
    );
  }
  return parsed;
}

function numberValue(value: unknown) {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function rounded(value: unknown, digits = 3) {
  const factor = 10 ** digits;
  return Math.round(numberValue(value) * factor) / factor;
}

function publicAgent(row: AgentRow) {
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
    budget_limit_usd: numberValue(row.budget_limit_usd),
    owner_user_id: row.owner_user_id,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

async function humanRead(
  request: Request,
  allowedParameters: readonly string[],
  work: HumanReadWork,
): Promise<HumanReadResult> {
  const searchParams = new URL(request.url).searchParams;
  rejectUnknownParameters(searchParams, allowedParameters);
  const requestedWorkspace = singleParameter(
    searchParams,
    "workspace_id",
  );
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(
      client,
      request.headers,
      requestedWorkspace,
    );
    return {
      status: 200,
      body: await work(client, identity.workspaceId, searchParams),
    };
  });
}

function appendIdentifierFilter(
  conditions: string[],
  values: unknown[],
  searchParams: URLSearchParams,
  parameter: string,
  column: string,
) {
  const value = identifierParameter(searchParams, parameter);
  if (!value) return;
  values.push(value);
  conditions.push(`${column}=$${values.length}`);
}

export async function listHumanAgents(request: Request) {
  return humanRead(
    request,
    ["workspace_id", "limit", "offset"],
    async (client, workspaceId, searchParams) => {
      const limit = boundedInteger(searchParams, "limit", 200, 200);
      const offset = boundedInteger(searchParams, "offset", 0, 5000, true);
      const rows = await client.query<AgentRow>(
        `WITH ${WORKSPACE_AGENT_CTE}
        SELECT agent.agent_id,agent.name,agent.role,agent.description,
          agent.runtime_type,agent.model_provider,agent.model_name,agent.status,
          agent.permission_level,agent.allowed_tools,agent.budget_limit_usd,
          CASE WHEN owner_membership.user_id IS NULL
            THEN NULL ELSE agent.owner_user_id END AS owner_user_id,
          agent.created_at,agent.updated_at
        FROM agents agent
        JOIN workspace_agent_ids workspace_agent
          ON workspace_agent.agent_id=agent.agent_id
        LEFT JOIN workspace_memberships owner_membership
          ON owner_membership.workspace_id=$1
          AND owner_membership.user_id=agent.owner_user_id
          AND owner_membership.status='active'
        ORDER BY agent.created_at DESC,agent.agent_id
        LIMIT $2 OFFSET $3`,
        [workspaceId, limit, offset],
      );
      return rows.rows.map(publicAgent);
    },
  );
}

export async function readHumanAgentPerformance(
  request: Request,
  rawAgentId: unknown,
) {
  const agentId = identifier(rawAgentId, "agent_id");
  return humanRead(
    request,
    ["workspace_id"],
    async (client, workspaceId) => {
      const agent = (await client.query<AgentRow>(
        `WITH ${WORKSPACE_AGENT_CTE}
        SELECT agent.agent_id,agent.name,agent.role,agent.description,
          agent.runtime_type,agent.model_provider,agent.model_name,agent.status,
          agent.permission_level,agent.allowed_tools,agent.budget_limit_usd,
          CASE WHEN owner_membership.user_id IS NULL
            THEN NULL ELSE agent.owner_user_id END AS owner_user_id,
          agent.created_at,agent.updated_at
        FROM agents agent
        JOIN workspace_agent_ids workspace_agent
          ON workspace_agent.agent_id=agent.agent_id
        LEFT JOIN workspace_memberships owner_membership
          ON owner_membership.workspace_id=$1
          AND owner_membership.user_id=agent.owner_user_id
          AND owner_membership.status='active'
        WHERE agent.agent_id=$2`,
        [workspaceId, agentId],
      )).rows[0];
      if (!agent) {
        throw new ControlPlaneHttpError(
          404,
          "agent_not_found",
          "The Agent was not found in this workspace.",
        );
      }
      const summary = (await client.query<AggregateRow>(
        `SELECT
          COUNT(*)::text AS total_runs,
          COUNT(*) FILTER (WHERE status='completed')::text AS completed_runs,
          COUNT(*) FILTER (WHERE status IN ('failed','blocked'))::text AS failures,
          COALESCE(AVG(duration_ms),0)::text AS avg_duration_ms,
          COALESCE(SUM(cost_usd),0)::text AS total_cost_usd,
          COUNT(*) FILTER (WHERE approval_required=1)::text
            AS approval_required_count
        FROM runs
        WHERE workspace_id=$1 AND agent_id=$2`,
        [workspaceId, agentId],
      )).rows[0] || {};
      const recentErrors = await client.query<AggregateRow>(
        `SELECT error_type,COUNT(*)::text AS count
        FROM runs
        WHERE workspace_id=$1 AND agent_id=$2 AND error_type IS NOT NULL
        GROUP BY error_type
        ORDER BY COUNT(*) DESC,error_type
        LIMIT 5`,
        [workspaceId, agentId],
      );
      const recentRuns = await client.query<Record<string, unknown>>(
        `SELECT * FROM runs
        WHERE workspace_id=$1 AND agent_id=$2
        ORDER BY created_at DESC,run_id
        LIMIT 10`,
        [workspaceId, agentId],
      );
      const totalRuns = numberValue(summary.total_runs);
      const completedRuns = numberValue(summary.completed_runs);
      return {
        agent: publicAgent(agent),
        total_runs: totalRuns,
        completed_runs: completedRuns,
        failures: numberValue(summary.failures),
        success_rate: totalRuns ? rounded(completedRuns / totalRuns) : 0,
        avg_duration_ms: Math.round(numberValue(summary.avg_duration_ms)),
        total_cost_usd: rounded(summary.total_cost_usd, 4),
        approval_required_count: numberValue(
          summary.approval_required_count,
        ),
        recent_error_types: recentErrors.rows.map((row) => ({
          error_type: row.error_type,
          count: numberValue(row.count),
        })),
        recent_runs: recentRuns.rows,
      };
    },
  );
}

export async function listHumanEvaluations(request: Request) {
  return humanRead(
    request,
    ["workspace_id", "task_id", "run_id", "agent_id", "limit", "offset"],
    async (client, workspaceId, searchParams) => {
      const conditions = ["run.workspace_id=$1"];
      const values: unknown[] = [workspaceId];
      appendIdentifierFilter(
        conditions,
        values,
        searchParams,
        "task_id",
        "evaluation.task_id",
      );
      appendIdentifierFilter(
        conditions,
        values,
        searchParams,
        "run_id",
        "evaluation.run_id",
      );
      appendIdentifierFilter(
        conditions,
        values,
        searchParams,
        "agent_id",
        "evaluation.agent_id",
      );
      const limit = boundedInteger(searchParams, "limit", 200, 500);
      const offset = boundedInteger(searchParams, "offset", 0, 5000, true);
      values.push(limit, offset);
      const rows = await client.query<Record<string, unknown>>(
        `SELECT evaluation.*
        FROM evaluations evaluation
        JOIN runs run
          ON run.run_id=evaluation.run_id
          AND run.task_id=evaluation.task_id
          AND run.agent_id=evaluation.agent_id
        JOIN tasks task
          ON task.task_id=run.task_id
          AND task.workspace_id=run.workspace_id
        WHERE ${conditions.join(" AND ")}
        ORDER BY evaluation.created_at DESC,evaluation.evaluation_id
        LIMIT $${values.length - 1} OFFSET $${values.length}`,
        values,
      );
      return rows.rows;
    },
  );
}

export async function listHumanToolCalls(request: Request) {
  return humanRead(
    request,
    ["workspace_id", "run_id", "agent_id", "limit", "offset"],
    async (client, workspaceId, searchParams) => {
      const conditions = ["run.workspace_id=$1"];
      const values: unknown[] = [workspaceId];
      appendIdentifierFilter(
        conditions,
        values,
        searchParams,
        "run_id",
        "tool_call.run_id",
      );
      appendIdentifierFilter(
        conditions,
        values,
        searchParams,
        "agent_id",
        "tool_call.agent_id",
      );
      const limit = boundedInteger(searchParams, "limit", 150, 500);
      const offset = boundedInteger(searchParams, "offset", 0, 5000, true);
      values.push(limit, offset);
      const rows = await client.query<Record<string, unknown>>(
        `SELECT tool_call.*
        FROM tool_calls tool_call
        JOIN runs run
          ON run.run_id=tool_call.run_id
          AND run.agent_id=tool_call.agent_id
        WHERE ${conditions.join(" AND ")}
        ORDER BY tool_call.created_at DESC,tool_call.tool_call_id
        LIMIT $${values.length - 1} OFFSET $${values.length}`,
        values,
      );
      return rows.rows;
    },
  );
}

export async function listHumanAudit(request: Request) {
  return humanRead(
    request,
    ["workspace_id", "limit", "offset"],
    async (client, workspaceId, searchParams) => {
      const limit = boundedInteger(searchParams, "limit", 150, 500);
      const offset = boundedInteger(searchParams, "offset", 0, 5000, true);
      const rows = await client.query<Record<string, unknown>>(
        `SELECT audit_id,actor_type,actor_id,action,entity_type,entity_id,
          before_hash,after_hash,metadata_json,tamper_chain_hash,created_at
        FROM audit_logs
        WHERE workspace_id=$1
        ORDER BY created_at DESC,audit_id DESC
        LIMIT $2 OFFSET $3`,
        [workspaceId, limit, offset],
      );
      return rows.rows;
    },
  );
}

export async function readHumanDashboard(request: Request) {
  return humanRead(
    request,
    ["workspace_id"],
    async (client, workspaceId) => {
      const now = new Date().toISOString();
      const counts = (await client.query<AggregateRow>(
        `WITH ${WORKSPACE_AGENT_CTE}
        SELECT
          (SELECT COUNT(*) FROM workspace_agent_ids)::text AS agents_total,
          (SELECT COUNT(*) FROM agents agent
            JOIN workspace_agent_ids item ON item.agent_id=agent.agent_id
            WHERE agent.status='running')::text AS agents_running,
          (SELECT COUNT(*) FROM tasks
            WHERE workspace_id=$1 AND status='completed')::text
            AS tasks_completed_total,
          (SELECT COUNT(*) FROM tasks
            WHERE workspace_id=$1)::text AS tasks_total,
          (SELECT COUNT(*) FROM tasks
            WHERE workspace_id=$1
              AND status IN ('failed','blocked'))::text AS tasks_failed,
          (SELECT COALESCE(SUM(cost_usd),0) FROM runs
            WHERE workspace_id=$1)::text AS total_cost_usd,
          (SELECT COALESCE(AVG(cost_usd),0) FROM runs
            WHERE workspace_id=$1 AND status='completed')::text
            AS avg_task_cost_usd,
          (SELECT COUNT(*) FROM approvals approval
            JOIN runs run ON run.run_id=approval.run_id
            WHERE run.workspace_id=$1 AND approval.decision='pending')::text
            AS pending_approvals,
          (SELECT COUNT(*) FROM memories
            WHERE workspace_id=$1
              AND (
                review_status='stale'
                OR (ttl_review_due_at IS NOT NULL AND ttl_review_due_at<$2)
              ))::text AS stale_or_due_memories`,
        [workspaceId, now],
      )).rows[0] || {};
      const taskStatus = await client.query<AggregateRow>(
        `SELECT status,COUNT(*)::text AS count
        FROM tasks
        WHERE workspace_id=$1
        GROUP BY status
        ORDER BY status`,
        [workspaceId],
      );
      const topCostAgents = await client.query<AggregateRow>(
        `WITH ${WORKSPACE_AGENT_CTE}
        SELECT agent.agent_id,agent.name,
          COALESCE(SUM(run.cost_usd),0)::text AS cost_usd
        FROM agents agent
        JOIN workspace_agent_ids item ON item.agent_id=agent.agent_id
        LEFT JOIN runs run
          ON run.agent_id=agent.agent_id AND run.workspace_id=$1
        GROUP BY agent.agent_id,agent.name
        ORDER BY COALESCE(SUM(run.cost_usd),0) DESC,agent.agent_id
        LIMIT 5`,
        [workspaceId],
      );
      const topFailingAgents = await client.query<AggregateRow>(
        `WITH ${WORKSPACE_AGENT_CTE}
        SELECT agent.agent_id,agent.name,
          COUNT(run.run_id) FILTER (
            WHERE run.status IN ('failed','blocked')
          )::text AS failures
        FROM agents agent
        JOIN workspace_agent_ids item ON item.agent_id=agent.agent_id
        LEFT JOIN runs run
          ON run.agent_id=agent.agent_id AND run.workspace_id=$1
        GROUP BY agent.agent_id,agent.name
        ORDER BY COUNT(run.run_id) FILTER (
          WHERE run.status IN ('failed','blocked')
        ) DESC,agent.agent_id
        LIMIT 5`,
        [workspaceId],
      );
      const performance = await client.query<AggregateRow>(
        `WITH ${WORKSPACE_AGENT_CTE}
        SELECT agent.agent_id,agent.name,agent.runtime_type,
          COUNT(run.run_id)::text AS total_runs,
          COUNT(run.run_id) FILTER (
            WHERE run.status='completed'
          )::text AS completed_runs,
          COALESCE(AVG(run.duration_ms),0)::text AS avg_duration_ms,
          COALESCE(SUM(run.cost_usd),0)::text AS total_cost_usd,
          COUNT(run.run_id) FILTER (
            WHERE run.status IN ('failed','blocked')
          )::text AS failures,
          COUNT(run.run_id) FILTER (
            WHERE run.approval_required=1
          )::text AS approval_required_count
        FROM agents agent
        JOIN workspace_agent_ids item ON item.agent_id=agent.agent_id
        LEFT JOIN runs run
          ON run.agent_id=agent.agent_id AND run.workspace_id=$1
        GROUP BY agent.agent_id,agent.name,agent.runtime_type
        ORDER BY COUNT(run.run_id) DESC,agent.agent_id
        LIMIT 8`,
        [workspaceId],
      );
      const recentRuns = await client.query<Record<string, unknown>>(
        `SELECT * FROM runs
        WHERE workspace_id=$1
        ORDER BY created_at DESC,run_id
        LIMIT 20`,
        [workspaceId],
      );
      const runtimeHealth = await client.query<Record<string, unknown>>(
        `WITH ${WORKSPACE_AGENT_CTE}
        SELECT DISTINCT ON (connector.provider)
          connector.provider,connector.status,connector.trust_status,
          connector.allow_real_run,connector.require_confirm_run,
          connector.last_health_at
        FROM runtime_connectors connector
        JOIN agents agent ON agent.runtime_type=connector.provider
        JOIN workspace_agent_ids item ON item.agent_id=agent.agent_id
        ORDER BY connector.provider,connector.updated_at DESC,
          connector.runtime_connector_id`,
        [workspaceId],
      );
      const openclaw = (await client.query<AggregateRow>(
        `WITH ${WORKSPACE_AGENT_CTE}
        SELECT
          (SELECT COUNT(*) FROM agents agent
            JOIN workspace_agent_ids item ON item.agent_id=agent.agent_id
            WHERE agent.runtime_type='openclaw')::text AS agents,
          (SELECT COUNT(*) FROM tasks
            WHERE workspace_id=$1
              AND task_id LIKE 'tsk_oc_cron_%')::text AS cron_tasks,
          (SELECT COUNT(*) FROM tasks
            WHERE workspace_id=$1
              AND task_id LIKE 'tsk_oc_cron_%'
              AND status='planned')::text AS enabled_cron_tasks,
          (SELECT COUNT(*) FROM runs
            WHERE workspace_id=$1
              AND runtime_type='openclaw')::text AS cron_runs,
          (SELECT COUNT(*) FROM runs
            WHERE workspace_id=$1
              AND runtime_type='openclaw'
              AND status='failed')::text AS failed_runs,
          (SELECT COUNT(*) FROM evaluations evaluation
            JOIN runs run ON run.run_id=evaluation.run_id
            WHERE run.workspace_id=$1
              AND run.runtime_type='openclaw'
              AND evaluation.pass_fail='fail')::text
            AS failed_quality_gates`,
        [workspaceId],
      )).rows[0] || {};
      const tasksTotal = numberValue(counts.tasks_total);
      const tasksFailed = numberValue(counts.tasks_failed);
      return {
        workspace_id: workspaceId,
        agents_total: numberValue(counts.agents_total),
        agents_running: numberValue(counts.agents_running),
        tasks_completed_total: numberValue(counts.tasks_completed_total),
        total_cost_usd: rounded(counts.total_cost_usd),
        avg_task_cost_usd: rounded(counts.avg_task_cost_usd),
        failure_rate: tasksTotal ? rounded(tasksFailed / tasksTotal) : 0,
        pending_approvals: numberValue(counts.pending_approvals),
        stale_or_due_memories: numberValue(
          counts.stale_or_due_memories,
        ),
        task_status_distribution: taskStatus.rows.map((row) => ({
          status: row.status,
          count: numberValue(row.count),
        })),
        top_cost_agents: topCostAgents.rows.map((row) => ({
          agent_id: row.agent_id,
          name: row.name,
          cost_usd: rounded(row.cost_usd),
        })),
        top_failing_agents: topFailingAgents.rows.map((row) => ({
          agent_id: row.agent_id,
          name: row.name,
          failures: numberValue(row.failures),
        })),
        runtime_health: runtimeHealth.rows,
        openclaw_import: {
          agents: numberValue(openclaw.agents),
          cron_tasks: numberValue(openclaw.cron_tasks),
          enabled_cron_tasks: numberValue(openclaw.enabled_cron_tasks),
          cron_runs: numberValue(openclaw.cron_runs),
          failed_runs: numberValue(openclaw.failed_runs),
          failed_quality_gates: numberValue(openclaw.failed_quality_gates),
        },
        agent_performance_summary: performance.rows.map((row) => {
          const totalRuns = numberValue(row.total_runs);
          const completedRuns = numberValue(row.completed_runs);
          return {
            agent_id: row.agent_id,
            name: row.name,
            runtime_type: row.runtime_type,
            total_runs: totalRuns,
            success_rate: totalRuns
              ? rounded(completedRuns / totalRuns)
              : 0,
            avg_duration_ms: Math.round(numberValue(row.avg_duration_ms)),
            total_cost_usd: rounded(row.total_cost_usd, 4),
            failures: numberValue(row.failures),
            approval_required_count: numberValue(
              row.approval_required_count,
            ),
          };
        }),
        recent_runs: recentRuns.rows,
        control_plane: "typescript_postgres",
        raw_prompt_omitted: true,
        raw_response_omitted: true,
        token_omitted: true,
      };
    },
  );
}
