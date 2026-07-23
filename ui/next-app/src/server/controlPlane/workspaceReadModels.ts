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

type TaskDetailRow = Omit<TaskRow, "description" | "acceptance_criteria">;

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

type RunGraphAnchorRow = RunRow & {
  parent_run_id: string | null;
  delegation_id: string | null;
};

type ToolCallRow = {
  tool_call_id: string;
  run_id: string;
  agent_id: string;
  tool_name: string;
  tool_version: string;
  tool_category: string;
  risk_level: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  created_at: string;
};

type ApprovalRow = {
  approval_id: string;
  approval_kind: string;
  decision: string;
  task_id: string;
  run_id: string;
  tool_call_id: string | null;
  requested_by_agent_id: string | null;
  expires_at: string | null;
  decided_at: string | null;
};

type EvaluationRow = {
  evaluation_id: string;
  task_id: string;
  run_id: string;
  agent_id: string;
  evaluator_type: string;
  score: number;
  pass_fail: string;
  created_at: string;
};

type MemoryRow = {
  memory_id: string;
  scope: string;
  memory_type: string;
  source_type: string;
  task_id: string | null;
  agent_id: string | null;
  confidence: number;
  review_status: string;
  ttl_review_due_at: string | null;
  created_at: string;
  updated_at: string;
};

type ArtifactRow = {
  artifact_id: string;
  task_id: string | null;
  run_id: string | null;
  artifact_type: string;
  title: string;
  created_at: string;
};

type RuntimeEventRow = {
  runtime_event_id: string;
  event_type: string;
  status: string;
  run_id: string | null;
  task_id: string | null;
  created_at: string;
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

const IDENTIFIER_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;
const RISK_LEVELS = new Set(["low", "medium", "high", "critical"]);
const EVALUATOR_TYPES = new Set(["human", "rule", "llm_mock"]);
const EVALUATION_RESULTS = new Set(["pass", "fail"]);

function boundedLimit(value: unknown, fallback: number) {
  if (value === undefined || value === null) return fallback;
  const raw = String(value).trim();
  if (!/^\d+$/.test(raw) || Number(raw) < 1 || Number(raw) > 200) {
    throw new ControlPlaneHttpError(400, "limit_invalid", "limit must be an integer between 1 and 200.");
  }
  return Number(raw);
}

function requiredIdentifier(name: "task_id" | "run_id" | "agent_id", value: unknown) {
  const normalized = String(value ?? "").trim();
  if (!IDENTIFIER_PATTERN.test(normalized)) {
    throw new ControlPlaneHttpError(400, `${name}_invalid`, `${name} must be a valid identifier.`);
  }
  return normalized;
}

function optionalIdentifierFilter(name: "task_id" | "run_id" | "agent_id", value: unknown) {
  if (value === undefined || value === null) return undefined;
  return requiredIdentifier(name, value);
}

function optionalChoiceFilter(name: string, value: unknown, allowed: Set<string>) {
  if (value === undefined || value === null) return undefined;
  const normalized = String(value).trim().toLowerCase();
  if (!allowed.has(normalized)) {
    throw new ControlPlaneHttpError(400, `${name}_invalid`, `${name} is not supported.`);
  }
  return normalized;
}

function optionalStatusFilter(value: unknown) {
  if (value === undefined || value === null) return undefined;
  const normalized = String(value).trim().toLowerCase();
  if (!/^[a-z][a-z0-9_-]{0,63}$/.test(normalized)) {
    throw new ControlPlaneHttpError(400, "status_invalid", "status must be a valid status identifier.");
  }
  return normalized;
}

function hiddenNotFound(entity: "Task" | "Run"): never {
  throw new ControlPlaneHttpError(404, "not_found", `${entity} not found in requested workspace.`);
}

export function assertStrictReadQuery(searchParams: URLSearchParams, allowedFilters: readonly string[]) {
  const allowed = new Set(["workspace_id", "limit", ...allowedFilters]);
  for (const key of new Set(searchParams.keys())) {
    if (!allowed.has(key) || searchParams.getAll(key).length !== 1) {
      throw new ControlPlaneHttpError(
        400,
        "filter_invalid",
        "The request contains an unsupported or repeated read filter.",
      );
    }
  }
}

async function taskRows(client: PoolClient, workspaceId: string, limit: number) {
  return client.query<TaskRow>(
    `SELECT task.task_id,LEFT(task.title,240) AS title,LEFT(task.description,512) AS description,
    task.status,task.priority,task.risk_level,task.owner_agent_id,
    LEFT(task.acceptance_criteria,512) AS acceptance_criteria,
    task.budget_limit_usd,task.created_at,task.updated_at
    FROM tasks task WHERE task.workspace_id=$1
    ORDER BY task.created_at DESC,task.task_id DESC
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
    `SELECT run.run_id,run.task_id,run.agent_id,run.runtime_type,run.status,run.duration_ms,
    run.cost_usd,run.started_at,run.created_at
    FROM runs run
    JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
    WHERE run.workspace_id=$1
      AND ($2::text IS NULL OR run.task_id=$2)
      AND ($3::text IS NULL OR run.agent_id=$3)
    ORDER BY run.created_at DESC,run.run_id DESC
    LIMIT $4`,
    [workspaceId, filters?.taskId || null, filters?.agentId || null, limit],
  );
}

async function requireWorkspaceTask(client: PoolClient, workspaceId: string, taskId: string) {
  const result = await client.query<TaskDetailRow>(
    `SELECT task.task_id,LEFT(task.title,240) AS title,task.status,task.priority,task.risk_level,
    task.owner_agent_id,task.budget_limit_usd,task.created_at,task.updated_at
    FROM tasks task
    WHERE task.workspace_id=$1 AND task.task_id=$2`,
    [workspaceId, taskId],
  );
  if (!result.rows[0]) hiddenNotFound("Task");
  return result.rows[0];
}

async function requireWorkspaceRun(client: PoolClient, workspaceId: string, runId: string) {
  const result = await client.query<RunRow>(
    `SELECT run.run_id,run.task_id,run.agent_id,run.runtime_type,run.status,run.duration_ms,
    run.cost_usd,run.started_at,run.created_at
    FROM runs run
    JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
    WHERE run.workspace_id=$1 AND run.run_id=$2`,
    [workspaceId, runId],
  );
  if (!result.rows[0]) hiddenNotFound("Run");
  return result.rows[0];
}

async function approvalRows(
  client: PoolClient,
  workspaceId: string,
  limit: number,
  filters?: { taskId?: string; runId?: string },
) {
  return client.query<ApprovalRow>(
    `SELECT approval.approval_id,approval.approval_kind,approval.decision,approval.task_id,approval.run_id,
    approval.tool_call_id,approval.requested_by_agent_id,
    approval.expires_at,approval.decided_at
    FROM approvals approval
    JOIN tasks task ON task.task_id=approval.task_id AND task.workspace_id=$1
    JOIN runs run ON run.run_id=approval.run_id AND run.task_id=task.task_id AND run.workspace_id=$1
    LEFT JOIN tool_calls tool ON tool.tool_call_id=approval.tool_call_id
      AND tool.run_id=run.run_id AND tool.agent_id=run.agent_id
    WHERE ($2::text IS NULL OR approval.task_id=$2)
      AND ($3::text IS NULL OR approval.run_id=$3)
      AND (approval.requested_by_agent_id IS NULL OR approval.requested_by_agent_id=run.agent_id)
      AND (approval.tool_call_id IS NULL OR tool.tool_call_id IS NOT NULL)
    ORDER BY approval.created_at DESC,approval.approval_id DESC
    LIMIT $4`,
    [workspaceId, filters?.taskId || null, filters?.runId || null, limit],
  );
}

async function toolCallRows(
  client: PoolClient,
  workspaceId: string,
  limit: number,
  filters?: { runId?: string; agentId?: string; riskLevel?: string; status?: string },
) {
  return client.query<ToolCallRow>(
    `SELECT tool.tool_call_id,tool.run_id,tool.agent_id,tool.tool_name,tool.tool_version,
    tool.tool_category,tool.risk_level,tool.status,
    tool.started_at,tool.ended_at,tool.created_at
    FROM tool_calls tool
    JOIN runs run ON run.run_id=tool.run_id AND run.workspace_id=$1
      AND run.agent_id=tool.agent_id
    JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
    WHERE ($2::text IS NULL OR tool.run_id=$2)
      AND ($3::text IS NULL OR tool.agent_id=$3)
      AND ($4::text IS NULL OR tool.risk_level=$4)
      AND ($5::text IS NULL OR tool.status=$5)
    ORDER BY tool.created_at DESC,tool.tool_call_id DESC
    LIMIT $6`,
    [
      workspaceId,
      filters?.runId || null,
      filters?.agentId || null,
      filters?.riskLevel || null,
      filters?.status || null,
      limit,
    ],
  );
}

async function evaluationRows(
  client: PoolClient,
  workspaceId: string,
  limit: number,
  filters?: {
    taskId?: string;
    runId?: string;
    agentId?: string;
    evaluatorType?: string;
    passFail?: string;
  },
) {
  return client.query<EvaluationRow>(
    `SELECT evaluation.evaluation_id,evaluation.task_id,evaluation.run_id,evaluation.agent_id,
    evaluation.evaluator_type,evaluation.score,evaluation.pass_fail,evaluation.created_at
    FROM evaluations evaluation
    JOIN runs run ON run.run_id=evaluation.run_id AND run.workspace_id=$1
      AND run.agent_id=evaluation.agent_id
    JOIN tasks task ON task.task_id=evaluation.task_id
      AND task.task_id=run.task_id AND task.workspace_id=$1
    WHERE ($2::text IS NULL OR evaluation.task_id=$2)
      AND ($3::text IS NULL OR evaluation.run_id=$3)
      AND ($4::text IS NULL OR evaluation.agent_id=$4)
      AND ($5::text IS NULL OR evaluation.evaluator_type=$5)
      AND ($6::text IS NULL OR evaluation.pass_fail=$6)
    ORDER BY evaluation.created_at DESC,evaluation.evaluation_id DESC
    LIMIT $7`,
    [
      workspaceId,
      filters?.taskId || null,
      filters?.runId || null,
      filters?.agentId || null,
      filters?.evaluatorType || null,
      filters?.passFail || null,
      limit,
    ],
  );
}

async function taskMemoryRows(client: PoolClient, workspaceId: string, taskId: string, limit: number) {
  return client.query<MemoryRow>(
    `SELECT memory.memory_id,memory.scope,memory.memory_type,memory.source_type,
    memory.task_id,memory.agent_id,memory.confidence,memory.review_status,
    memory.ttl_review_due_at,memory.created_at,memory.updated_at
    FROM memories memory
    JOIN tasks task ON task.task_id=memory.task_id AND task.workspace_id=$1
    WHERE memory.workspace_id=$1 AND memory.task_id=$2
    ORDER BY memory.created_at DESC,memory.memory_id DESC
    LIMIT $3`,
    [workspaceId, taskId, limit],
  );
}

async function taskArtifactRows(client: PoolClient, workspaceId: string, taskId: string, limit: number) {
  return client.query<ArtifactRow>(
    `SELECT artifact.artifact_id,artifact.task_id,artifact.run_id,artifact.artifact_type,
    LEFT(artifact.title,240) AS title,artifact.created_at
    FROM artifacts artifact
    JOIN tasks task ON task.task_id=artifact.task_id AND task.workspace_id=$1
    LEFT JOIN runs run ON run.run_id=artifact.run_id
      AND run.workspace_id=$1 AND run.task_id=task.task_id
    WHERE artifact.task_id=$2
      AND (artifact.run_id IS NULL OR run.run_id IS NOT NULL)
    ORDER BY artifact.created_at DESC,artifact.artifact_id DESC
    LIMIT $3`,
    [workspaceId, taskId, limit],
  );
}

async function runArtifactRows(client: PoolClient, workspaceId: string, runId: string, limit: number) {
  return client.query<ArtifactRow>(
    `SELECT artifact.artifact_id,artifact.task_id,artifact.run_id,artifact.artifact_type,
    LEFT(artifact.title,240) AS title,artifact.created_at
    FROM artifacts artifact
    JOIN runs run ON run.run_id=artifact.run_id AND run.workspace_id=$1
    JOIN tasks run_task ON run_task.task_id=run.task_id AND run_task.workspace_id=$1
    LEFT JOIN tasks artifact_task ON artifact_task.task_id=artifact.task_id
      AND artifact_task.workspace_id=$1
    WHERE artifact.run_id=$2
      AND (artifact.task_id IS NULL OR (
        artifact_task.task_id=run.task_id
      ))
    ORDER BY artifact.created_at DESC,artifact.artifact_id DESC
    LIMIT $3`,
    [workspaceId, runId, limit],
  );
}

async function runRuntimeEventRows(client: PoolClient, workspaceId: string, runId: string, limit: number) {
  return client.query<RuntimeEventRow>(
    `SELECT event.runtime_event_id,event.event_type,event.status,
    event.run_id,event.task_id,event.created_at
    FROM runtime_events event
    JOIN runs run ON run.run_id=event.run_id AND run.workspace_id=$1
    JOIN tasks run_task ON run_task.task_id=run.task_id AND run_task.workspace_id=$1
    LEFT JOIN tasks event_task ON event_task.task_id=event.task_id
      AND event_task.workspace_id=$1
    WHERE event.run_id=$2
      AND (event.agent_id IS NULL OR event.agent_id=run.agent_id)
      AND (event.task_id IS NULL OR (
        event_task.task_id=run.task_id
      ))
    ORDER BY event.created_at DESC,event.runtime_event_id DESC
    LIMIT $3`,
    [workspaceId, runId, limit],
  );
}

async function runAuditRows(client: PoolClient, workspaceId: string, runId: string, limit: number) {
  return client.query<AuditRow>(
    `WITH selected_run AS (
      SELECT run.run_id,run.task_id,run.agent_id
      FROM runs run
      JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
      WHERE run.workspace_id=$1 AND run.run_id=$2
    ), authorized_entities(entity_type,entity_id) AS (
      SELECT 'runs'::text,selected.run_id FROM selected_run selected
      UNION
      SELECT 'tasks'::text,selected.task_id FROM selected_run selected
      UNION
      SELECT 'tool_calls'::text,tool.tool_call_id
      FROM tool_calls tool JOIN selected_run selected
        ON selected.run_id=tool.run_id AND selected.agent_id=tool.agent_id
      UNION
      SELECT 'approvals'::text,approval.approval_id
      FROM approvals approval
      JOIN selected_run selected
        ON selected.run_id=approval.run_id AND selected.task_id=approval.task_id
      LEFT JOIN tool_calls tool
        ON tool.tool_call_id=approval.tool_call_id
        AND tool.run_id=selected.run_id AND tool.agent_id=selected.agent_id
      WHERE (approval.requested_by_agent_id IS NULL OR approval.requested_by_agent_id=selected.agent_id)
        AND (approval.tool_call_id IS NULL OR tool.tool_call_id IS NOT NULL)
      UNION
      SELECT 'evaluations'::text,evaluation.evaluation_id
      FROM evaluations evaluation
      JOIN selected_run selected
        ON selected.run_id=evaluation.run_id
        AND selected.task_id=evaluation.task_id
        AND selected.agent_id=evaluation.agent_id
      UNION
      SELECT 'artifacts'::text,artifact.artifact_id
      FROM artifacts artifact
      JOIN selected_run selected ON selected.run_id=artifact.run_id
      LEFT JOIN tasks artifact_task ON artifact_task.task_id=artifact.task_id
        AND artifact_task.workspace_id=$1
      WHERE artifact.task_id IS NULL OR (
        artifact_task.task_id=selected.task_id
      )
      UNION
      SELECT 'runtime_events'::text,event.runtime_event_id
      FROM runtime_events event
      JOIN selected_run selected ON selected.run_id=event.run_id
      LEFT JOIN tasks event_task ON event_task.task_id=event.task_id
        AND event_task.workspace_id=$1
      WHERE (event.agent_id IS NULL OR event.agent_id=selected.agent_id)
        AND (event.task_id IS NULL OR event_task.task_id=selected.task_id)
    )
    SELECT audit.audit_id,audit.actor_type,audit.actor_id,audit.action,
    audit.entity_type,audit.entity_id,audit.created_at
    FROM audit_logs audit
    JOIN authorized_entities entity
      ON entity.entity_type=audit.entity_type AND entity.entity_id=audit.entity_id
    WHERE audit.workspace_id=$1
      AND audit.metadata_json::jsonb ->> 'workspace_id'=$1
    ORDER BY audit.created_at DESC,audit.audit_id DESC
    LIMIT $3`,
    [workspaceId, runId, limit],
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

export async function getWorkspaceTaskDetail(
  headers: Headers,
  workspaceId: unknown,
  suppliedTaskId: unknown,
  suppliedLimit: unknown,
) {
  const taskId = requiredIdentifier("task_id", suppliedTaskId);
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const task = await requireWorkspaceTask(client, identity.workspaceId, taskId);
    const runs = await runRows(client, identity.workspaceId, limit, { taskId });
    const approvals = await approvalRows(client, identity.workspaceId, limit, { taskId });
    const evaluations = await evaluationRows(client, identity.workspaceId, limit, { taskId });
    const memories = await taskMemoryRows(client, identity.workspaceId, taskId, limit);
    const artifacts = await taskArtifactRows(client, identity.workspaceId, taskId, limit);
    return {
      status: 200,
      body: {
        task,
        runs: runs.rows,
        approvals: approvals.rows,
        evaluations: evaluations.rows,
        memories: memories.rows,
        artifacts: artifacts.rows,
        token_omitted: true as const,
      },
    };
  });
}

export async function getWorkspaceRunDetail(
  headers: Headers,
  workspaceId: unknown,
  suppliedRunId: unknown,
  suppliedLimit: unknown,
) {
  const runId = requiredIdentifier("run_id", suppliedRunId);
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const run = await requireWorkspaceRun(client, identity.workspaceId, runId);
    const task = await requireWorkspaceTask(client, identity.workspaceId, run.task_id);
    const toolCalls = await toolCallRows(client, identity.workspaceId, limit, { runId });
    const approvals = await approvalRows(client, identity.workspaceId, limit, { runId });
    const evaluations = await evaluationRows(client, identity.workspaceId, limit, { runId });
    const artifacts = await runArtifactRows(client, identity.workspaceId, runId, limit);
    const runtimeEvents = await runRuntimeEventRows(client, identity.workspaceId, runId, limit);
    const auditLogs = await runAuditRows(client, identity.workspaceId, runId, limit);
    return {
      status: 200,
      body: {
        run,
        task,
        tool_calls: toolCalls.rows,
        approvals: approvals.rows,
        evaluations: evaluations.rows,
        artifacts: artifacts.rows,
        runtime_events: runtimeEvents.rows,
        audit_logs: auditLogs.rows,
        token_omitted: true as const,
      },
    };
  });
}

export async function getWorkspaceRunGraph(
  headers: Headers,
  workspaceId: unknown,
  suppliedRunId: unknown,
  suppliedLimit: unknown,
) {
  const runId = requiredIdentifier("run_id", suppliedRunId);
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const anchorResult = await client.query<RunGraphAnchorRow>(
      `SELECT run.run_id,run.task_id,run.agent_id,run.runtime_type,run.status,run.duration_ms,
      run.cost_usd,run.started_at,run.created_at,run.parent_run_id,run.delegation_id
      FROM runs run
      JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
      WHERE run.workspace_id=$1 AND run.run_id=$2`,
      [identity.workspaceId, runId],
    );
    const anchor = anchorResult.rows[0];
    if (!anchor) hiddenNotFound("Run");

    const parentResult = anchor.parent_run_id
      ? await client.query<RunRow>(
        `SELECT run.run_id,run.task_id,run.agent_id,run.runtime_type,run.status,run.duration_ms,
        run.cost_usd,run.started_at,run.created_at
        FROM runs run
        JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
        WHERE run.workspace_id=$1 AND run.run_id=$2`,
        [identity.workspaceId, anchor.parent_run_id],
      )
      : { rows: [] as RunRow[] };
    const children = await client.query<RunRow>(
      `SELECT run.run_id,run.task_id,run.agent_id,run.runtime_type,run.status,run.duration_ms,
      run.cost_usd,run.started_at,run.created_at
      FROM runs run
      JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
      WHERE run.workspace_id=$1 AND run.parent_run_id=$2
      ORDER BY run.created_at,run.run_id
      LIMIT $3`,
      [identity.workspaceId, runId, limit],
    );
    const siblings = anchor.delegation_id
      ? await client.query<RunRow>(
        `SELECT run.run_id,run.task_id,run.agent_id,run.runtime_type,run.status,run.duration_ms,
        run.cost_usd,run.started_at,run.created_at
        FROM runs run
        JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
        WHERE run.workspace_id=$1 AND run.delegation_id=$2 AND run.run_id<>$3
        ORDER BY run.created_at,run.run_id
        LIMIT $4`,
        [identity.workspaceId, anchor.delegation_id, runId, limit],
      )
      : { rows: [] as RunRow[] };
    const { parent_run_id: _parentRunId, delegation_id: _delegationId, ...run } = anchor;
    return {
      status: 200,
      body: {
        run,
        parent: parentResult.rows[0] || null,
        children: children.rows,
        siblings_by_delegation: siblings.rows,
        token_omitted: true as const,
      },
    };
  });
}

export async function listWorkspaceToolCalls(
  headers: Headers,
  workspaceId: unknown,
  suppliedLimit: unknown,
  filters?: {
    runId?: string | null;
    agentId?: string | null;
    riskLevel?: string | null;
    status?: string | null;
  },
) {
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const result = await toolCallRows(client, identity.workspaceId, limit, {
      runId: optionalIdentifierFilter("run_id", filters?.runId),
      agentId: optionalIdentifierFilter("agent_id", filters?.agentId),
      riskLevel: optionalChoiceFilter("risk_level", filters?.riskLevel, RISK_LEVELS),
      status: optionalStatusFilter(filters?.status),
    });
    return { status: 200, body: result.rows };
  });
}

export async function listWorkspaceEvaluations(
  headers: Headers,
  workspaceId: unknown,
  suppliedLimit: unknown,
  filters?: {
    taskId?: string | null;
    runId?: string | null;
    agentId?: string | null;
    evaluatorType?: string | null;
    passFail?: string | null;
  },
) {
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const result = await evaluationRows(client, identity.workspaceId, limit, {
      taskId: optionalIdentifierFilter("task_id", filters?.taskId),
      runId: optionalIdentifierFilter("run_id", filters?.runId),
      agentId: optionalIdentifierFilter("agent_id", filters?.agentId),
      evaluatorType: optionalChoiceFilter("evaluator_type", filters?.evaluatorType, EVALUATOR_TYPES),
      passFail: optionalChoiceFilter("pass_fail", filters?.passFail, EVALUATION_RESULTS),
    });
    return { status: 200, body: result.rows };
  });
}

export async function listWorkspaceApprovals(headers: Headers, workspaceId: unknown, suppliedLimit: unknown) {
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const result = await approvalRows(client, identity.workspaceId, limit);
    return { status: 200, body: result.rows };
  });
}

export async function listWorkspaceAudit(headers: Headers, workspaceId: unknown, suppliedLimit: unknown) {
  const limit = boundedLimit(suppliedLimit, 200);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const result = await client.query<AuditRow>(
      `WITH workspace_agents(agent_id) AS (
        SELECT task.owner_agent_id FROM tasks task
        WHERE task.workspace_id=$1 AND task.owner_agent_id IS NOT NULL
        UNION
        SELECT run.agent_id FROM runs run
        JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
        WHERE run.workspace_id=$1
        UNION
        SELECT token.agent_id FROM agent_gateway_tokens token WHERE token.workspace_id=$1
        UNION
        SELECT session.agent_id FROM agent_gateway_sessions session WHERE session.workspace_id=$1
      ), authorized_entities(entity_type,entity_id) AS (
        SELECT 'tasks'::text,task.task_id FROM tasks task WHERE task.workspace_id=$1
        UNION
        SELECT 'runs'::text,run.run_id FROM runs run
        JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
        WHERE run.workspace_id=$1
        UNION
        SELECT 'tool_calls'::text,tool.tool_call_id FROM tool_calls tool
        JOIN runs run ON run.run_id=tool.run_id AND run.workspace_id=$1
          AND run.agent_id=tool.agent_id
        JOIN tasks task ON task.task_id=run.task_id AND task.workspace_id=$1
        UNION
        SELECT 'approvals'::text,approval.approval_id FROM approvals approval
        JOIN tasks task ON task.task_id=approval.task_id AND task.workspace_id=$1
        JOIN runs run ON run.run_id=approval.run_id AND run.task_id=task.task_id
          AND run.workspace_id=$1
        LEFT JOIN tool_calls tool ON tool.tool_call_id=approval.tool_call_id
          AND tool.run_id=run.run_id AND tool.agent_id=run.agent_id
        WHERE (approval.requested_by_agent_id IS NULL OR approval.requested_by_agent_id=run.agent_id)
          AND (approval.tool_call_id IS NULL OR tool.tool_call_id IS NOT NULL)
        UNION
        SELECT 'evaluations'::text,evaluation.evaluation_id FROM evaluations evaluation
        JOIN runs run ON run.run_id=evaluation.run_id AND run.workspace_id=$1
          AND run.agent_id=evaluation.agent_id
        JOIN tasks task ON task.task_id=evaluation.task_id
          AND task.task_id=run.task_id AND task.workspace_id=$1
        UNION
        SELECT 'memories'::text,memory.memory_id FROM memories memory
        LEFT JOIN tasks task ON task.task_id=memory.task_id AND task.workspace_id=$1
        LEFT JOIN workspace_agents agent ON agent.agent_id=memory.agent_id
        WHERE memory.workspace_id=$1
          AND (memory.task_id IS NULL OR task.task_id IS NOT NULL)
          AND (memory.agent_id IS NULL OR agent.agent_id IS NOT NULL)
        UNION
        SELECT 'artifacts'::text,artifact.artifact_id FROM artifacts artifact
        LEFT JOIN tasks task ON task.task_id=artifact.task_id AND task.workspace_id=$1
        LEFT JOIN runs run ON run.run_id=artifact.run_id AND run.workspace_id=$1
        LEFT JOIN tasks run_task ON run_task.task_id=run.task_id AND run_task.workspace_id=$1
        WHERE (artifact.task_id IS NOT NULL OR artifact.run_id IS NOT NULL)
          AND (artifact.task_id IS NULL OR task.task_id IS NOT NULL)
          AND (artifact.run_id IS NULL OR (run.run_id IS NOT NULL AND run_task.task_id IS NOT NULL))
          AND (artifact.task_id IS NULL OR artifact.run_id IS NULL OR artifact.task_id=run.task_id)
        UNION
        SELECT 'runtime_events'::text,event.runtime_event_id FROM runtime_events event
        LEFT JOIN runs run ON run.run_id=event.run_id AND run.workspace_id=$1
        LEFT JOIN tasks run_task ON run_task.task_id=run.task_id AND run_task.workspace_id=$1
        LEFT JOIN tasks event_task ON event_task.task_id=event.task_id AND event_task.workspace_id=$1
        LEFT JOIN workspace_agents agent ON agent.agent_id=event.agent_id
        WHERE (event.run_id IS NOT NULL OR event.task_id IS NOT NULL)
          AND (event.run_id IS NULL OR (run.run_id IS NOT NULL AND run_task.task_id IS NOT NULL))
          AND (event.task_id IS NULL OR event_task.task_id IS NOT NULL)
          AND (event.run_id IS NULL OR event.task_id IS NULL OR event.task_id=run.task_id)
          AND (event.agent_id IS NULL OR (
            (event.run_id IS NOT NULL AND event.agent_id=run.agent_id)
            OR (event.run_id IS NULL AND agent.agent_id IS NOT NULL)
          ))
        UNION
        SELECT 'prepared_actions'::text,action.prepared_action_id FROM prepared_actions action
        JOIN tasks task ON task.task_id=action.task_id AND task.workspace_id=$1
        JOIN runs run ON run.run_id=action.run_id AND run.task_id=task.task_id
          AND run.workspace_id=$1
        JOIN tool_calls tool ON tool.tool_call_id=action.tool_call_id
          AND tool.run_id=run.run_id AND tool.agent_id=run.agent_id
        WHERE action.workspace_id=$1
          AND (action.requested_by_agent_id IS NULL OR action.requested_by_agent_id=run.agent_id)
        UNION
        SELECT 'agent_gateway_enrollment_requests'::text,enrollment.request_id
        FROM agent_gateway_enrollment_requests enrollment
        JOIN tasks task ON task.task_id=enrollment.task_id AND task.workspace_id=$1
        JOIN runs run ON run.run_id=enrollment.run_id AND run.task_id=task.task_id
          AND run.workspace_id=$1
        JOIN approvals approval ON approval.approval_id=enrollment.approval_id
          AND approval.task_id=task.task_id AND approval.run_id=run.run_id
        WHERE enrollment.workspace_id=$1
        UNION
        SELECT 'agent_gateway_tokens'::text,token.token_id
        FROM agent_gateway_tokens token WHERE token.workspace_id=$1
        UNION
        SELECT 'agent_gateway_sessions'::text,session.session_id
        FROM agent_gateway_sessions session
        LEFT JOIN agent_gateway_tokens token ON token.token_id=session.parent_token_id
          AND token.workspace_id=$1 AND token.agent_id=session.agent_id
        WHERE session.workspace_id=$1
          AND (session.parent_token_id IS NULL OR token.token_id IS NOT NULL)
        UNION
        SELECT 'agents'::text,agent.agent_id FROM workspace_agents agent
        UNION
        SELECT 'agent_plans'::text,plan.plan_id FROM agent_plans plan
        LEFT JOIN tasks task ON task.task_id=plan.task_id AND task.workspace_id=$1
        LEFT JOIN runs run ON run.run_id=plan.run_id AND run.workspace_id=$1
        LEFT JOIN tasks run_task ON run_task.task_id=run.task_id AND run_task.workspace_id=$1
        JOIN workspace_agents agent ON agent.agent_id=plan.agent_id
        WHERE plan.workspace_id=$1
          AND (plan.task_id IS NULL OR task.task_id IS NOT NULL)
          AND (plan.run_id IS NULL OR (
            run.run_id IS NOT NULL AND run_task.task_id IS NOT NULL AND run.agent_id=plan.agent_id
          ))
          AND (plan.task_id IS NULL OR plan.run_id IS NULL OR plan.task_id=run.task_id)
        UNION
        SELECT 'plan_evidence_manifests'::text,manifest.manifest_id
        FROM plan_evidence_manifests manifest
        JOIN agent_plans plan ON plan.plan_id=manifest.plan_id AND plan.workspace_id=$1
          AND plan.agent_id=manifest.agent_id
        JOIN runs run ON run.run_id=manifest.run_id AND run.workspace_id=$1
          AND run.agent_id=manifest.agent_id
        JOIN tasks run_task ON run_task.task_id=run.task_id AND run_task.workspace_id=$1
        LEFT JOIN tasks task ON task.task_id=manifest.task_id AND task.workspace_id=$1
        WHERE manifest.workspace_id=$1
          AND (manifest.task_id IS NULL OR task.task_id=run.task_id)
          AND (plan.task_id IS NULL OR plan.task_id=run.task_id)
          AND (plan.run_id IS NULL OR plan.run_id=manifest.run_id)
        UNION
        SELECT 'human_sessions'::text,session.session_id FROM human_sessions session
        JOIN workspace_memberships membership ON membership.user_id=session.user_id
          AND membership.workspace_id=$1
      )
      SELECT audit.audit_id,audit.actor_type,audit.actor_id,audit.action,
      audit.entity_type,audit.entity_id,audit.created_at
      FROM audit_logs audit
      JOIN authorized_entities entity
        ON entity.entity_type=audit.entity_type AND entity.entity_id=audit.entity_id
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
            AND tool.run_id=run.run_id AND tool.agent_id=run.agent_id
          WHERE task.workspace_id=$1 AND run.workspace_id=$1 AND approval.decision='pending'
            AND (approval.requested_by_agent_id IS NULL OR approval.requested_by_agent_id=run.agent_id)
            AND (approval.tool_call_id IS NULL OR tool.tool_call_id IS NOT NULL)
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
