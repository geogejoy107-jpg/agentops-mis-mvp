import type { PoolClient } from "pg";

import { withPostgresTransaction } from "./db";
import { authenticateHumanMember } from "./humanSession";
import { ControlPlaneHttpError } from "./http";
import type { HumanReadResult } from "./humanReadRoute";
import { stableHash } from "./ledger";

const GRAPH_SCHEMA_VERSION = "work_delivery_graph_v1";

type GraphRow = {
  workspace_id: string;
  task_id: string;
  task_status: string;
  run_id: string;
  run_status: string;
  agent_id: string;
  agent_status: string;
  agent_plan_id: string | null;
  run_plan_hash: string | null;
  plan_id: string | null;
  plan_status: string | null;
  plan_hash: string | null;
  plan_verification_hash: string | null;
  manifest_id: string | null;
  manifest_status: string | null;
  manifest_plan_hash: string | null;
  manifest_verification_hash: string | null;
  tool_calls: string;
  runtime_events: string;
  evaluations: string;
  approvals: string;
  artifacts: string;
  memories: string;
  audit_logs: string;
  plan_evidence_manifests: string;
};

function runIdentifier(value: unknown) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      "run_id_invalid",
      "run_id must use 1-128 safe identifier characters.",
    );
  }
  return normalized;
}

function requestedWorkspace(request: Request) {
  const searchParams = new URL(request.url).searchParams;
  for (const key of new Set(searchParams.keys())) {
    if (key !== "workspace_id") {
      throw new ControlPlaneHttpError(
        400,
        "human_read_query_unsupported",
        "The evidence graph received an unsupported query parameter.",
      );
    }
  }
  const values = searchParams.getAll("workspace_id");
  if (values.length > 1) {
    throw new ControlPlaneHttpError(
      400,
      "human_read_query_ambiguous",
      "The evidence graph accepts one workspace_id.",
    );
  }
  return values[0] ?? "";
}

function count(value: string) {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0;
}

function aggregateStatus(value: number) {
  return value > 0 ? "present" : "missing";
}

async function graphRow(
  client: PoolClient,
  workspaceId: string,
  runId: string,
) {
  const result = await client.query<GraphRow>(
    `WITH root AS (
      SELECT
        task.workspace_id,
        task.task_id,
        task.status AS task_status,
        run.run_id,
        run.status AS run_status,
        run.agent_id,
        run.agent_plan_id,
        run.plan_hash AS run_plan_hash,
        agent.status AS agent_status
      FROM tasks task
      JOIN runs run
        ON run.task_id=task.task_id
        AND run.workspace_id=task.workspace_id
      JOIN agents agent
        ON agent.agent_id=run.agent_id
      WHERE task.workspace_id=$1 AND run.run_id=$2
    ),
    bound_plan AS (
      SELECT
        plan.plan_id,
        plan.status AS plan_status,
        plan.plan_hash,
        plan.verification_result_hash
      FROM root
      JOIN agent_plans plan
        ON plan.plan_id=root.agent_plan_id
        AND plan.workspace_id=root.workspace_id
        AND plan.task_id=root.task_id
        AND plan.run_id=root.run_id
        AND plan.agent_id=root.agent_id
        AND plan.plan_hash IS NOT DISTINCT FROM root.run_plan_hash
    ),
    bound_tools AS (
      SELECT tool.tool_call_id
      FROM root
      JOIN tool_calls tool
        ON tool.run_id=root.run_id
        AND tool.agent_id=root.agent_id
    ),
    bound_runtime_events AS (
      SELECT event.runtime_event_id
      FROM root
      JOIN runtime_events event
        ON event.workspace_id=root.workspace_id
        AND event.run_id=root.run_id
        AND event.task_id=root.task_id
        AND event.agent_id=root.agent_id
    ),
    bound_evaluations AS (
      SELECT evaluation.evaluation_id
      FROM root
      JOIN evaluations evaluation
        ON evaluation.run_id=root.run_id
        AND evaluation.task_id=root.task_id
        AND evaluation.agent_id=root.agent_id
    ),
    bound_approvals AS (
      SELECT approval.approval_id
      FROM root
      JOIN approvals approval
        ON approval.run_id=root.run_id
        AND approval.task_id=root.task_id
      LEFT JOIN bound_tools tool
        ON tool.tool_call_id=approval.tool_call_id
      WHERE approval.tool_call_id IS NULL
        OR tool.tool_call_id IS NOT NULL
    ),
    bound_artifacts AS (
      SELECT artifact.artifact_id
      FROM root
      JOIN artifacts artifact
        ON artifact.run_id=root.run_id
        AND artifact.task_id=root.task_id
    ),
    bound_memories AS (
      SELECT memory.memory_id
      FROM root
      JOIN memories memory
        ON memory.workspace_id=root.workspace_id
        AND memory.run_id=root.run_id
        AND memory.task_id=root.task_id
        AND memory.agent_id=root.agent_id
    ),
    bound_manifests AS (
      SELECT
        manifest.manifest_id,
        manifest.status AS manifest_status,
        manifest.plan_hash AS manifest_plan_hash,
        manifest.verification_result_hash AS manifest_verification_hash,
        manifest.updated_at,
        manifest.created_at
      FROM root
      JOIN bound_plan plan ON TRUE
      JOIN plan_evidence_manifests manifest
        ON manifest.workspace_id=root.workspace_id
        AND manifest.run_id=root.run_id
        AND manifest.task_id=root.task_id
        AND manifest.agent_id=root.agent_id
        AND manifest.plan_id=plan.plan_id
        AND manifest.plan_hash IS NOT DISTINCT FROM plan.plan_hash
        AND manifest.verification_result_hash
          IS NOT DISTINCT FROM plan.verification_result_hash
    ),
    latest_manifest AS (
      SELECT *
      FROM bound_manifests
      ORDER BY updated_at DESC,created_at DESC,manifest_id DESC
      LIMIT 1
    ),
    bound_audit_entities AS (
      SELECT 'runs'::text AS entity_type,root.run_id AS entity_id FROM root
      UNION
      SELECT 'agent_plans',plan.plan_id FROM bound_plan plan
      UNION
      SELECT 'tool_calls',tool.tool_call_id FROM bound_tools tool
      UNION
      SELECT 'runtime_events',event.runtime_event_id
        FROM bound_runtime_events event
      UNION
      SELECT 'evaluations',evaluation.evaluation_id
        FROM bound_evaluations evaluation
      UNION
      SELECT 'approvals',approval.approval_id
        FROM bound_approvals approval
      UNION
      SELECT 'artifacts',artifact.artifact_id FROM bound_artifacts artifact
      UNION
      SELECT 'memories',memory.memory_id FROM bound_memories memory
      UNION
      SELECT 'plan_evidence_manifests',manifest.manifest_id
        FROM bound_manifests manifest
    ),
    bound_audits AS (
      SELECT audit.audit_id
      FROM root
      JOIN audit_logs audit
        ON audit.workspace_id=root.workspace_id
      JOIN bound_audit_entities entity
        ON entity.entity_type=audit.entity_type
        AND entity.entity_id=audit.entity_id
    )
    SELECT
      root.workspace_id,
      root.task_id,
      root.task_status,
      root.run_id,
      root.run_status,
      root.agent_id,
      root.agent_status,
      root.agent_plan_id,
      root.run_plan_hash,
      plan.plan_id,
      plan.plan_status,
      plan.plan_hash,
      plan.verification_result_hash AS plan_verification_hash,
      manifest.manifest_id,
      manifest.manifest_status,
      manifest.manifest_plan_hash,
      manifest.manifest_verification_hash,
      (SELECT COUNT(*)::text FROM bound_tools) AS tool_calls,
      (SELECT COUNT(*)::text FROM bound_runtime_events) AS runtime_events,
      (SELECT COUNT(*)::text FROM bound_evaluations) AS evaluations,
      (SELECT COUNT(*)::text FROM bound_approvals) AS approvals,
      (SELECT COUNT(*)::text FROM bound_artifacts) AS artifacts,
      (SELECT COUNT(*)::text FROM bound_memories) AS memories,
      (SELECT COUNT(*)::text FROM bound_audits) AS audit_logs,
      (SELECT COUNT(*)::text FROM bound_manifests)
        AS plan_evidence_manifests
    FROM root
    LEFT JOIN bound_plan plan ON TRUE
    LEFT JOIN latest_manifest manifest ON TRUE`,
    [workspaceId, runId],
  );
  const row = result.rows[0];
  if (!row) {
    throw new ControlPlaneHttpError(
      404,
      "run_not_found",
      "Run was not found in the Human Session workspace.",
    );
  }
  return row;
}

function graphPayload(row: GraphRow) {
  const evidenceCounts = {
    tool_calls: count(row.tool_calls),
    runtime_events: count(row.runtime_events),
    evaluations: count(row.evaluations),
    approvals: count(row.approvals),
    artifacts: count(row.artifacts),
    memories: count(row.memories),
    audit_logs: count(row.audit_logs),
    plan_evidence_manifests: count(row.plan_evidence_manifests),
  };
  const nodes = [
    { kind: "workspace", id: row.workspace_id, status: "authority" },
    { kind: "task", id: row.task_id, status: row.task_status },
    { kind: "agent", id: row.agent_id, status: row.agent_status },
    {
      kind: "agent_plan",
      id: row.plan_id,
      status: row.plan_status ?? "missing",
      hash: row.plan_hash,
    },
    {
      kind: "run",
      id: row.run_id,
      status: row.run_status,
      hash: row.run_plan_hash,
    },
    {
      kind: "plan_evidence_manifest",
      id: row.manifest_id,
      status: row.manifest_status ?? "missing",
      hash: row.manifest_verification_hash,
    },
    ...Object.entries(evidenceCounts)
      .filter(([kind]) => kind !== "plan_evidence_manifests")
      .map(([kind, evidenceCount]) => ({
        kind,
        status: aggregateStatus(evidenceCount),
        count: evidenceCount,
      })),
  ];
  const edges = [
    { from: "workspace", to: "task", relationship: "owns" },
    { from: "task", to: "agent_plan", relationship: "planned_by" },
    { from: "agent_plan", to: "run", relationship: "binds" },
    { from: "agent", to: "run", relationship: "executes" },
    { from: "run", to: "tool_calls", relationship: "records" },
    { from: "run", to: "runtime_events", relationship: "emits" },
    { from: "run", to: "evaluations", relationship: "evaluated_by" },
    { from: "run", to: "approvals", relationship: "governed_by" },
    { from: "run", to: "artifacts", relationship: "produces" },
    { from: "run", to: "memories", relationship: "proposes" },
    { from: "run", to: "audit_logs", relationship: "audited_by" },
    { from: "plan_evidence_manifest", to: "run", relationship: "verifies" },
  ];
  const graphMaterial = {
    schema_version: GRAPH_SCHEMA_VERSION,
    workspace_id: row.workspace_id,
    task_id: row.task_id,
    task_status: row.task_status,
    agent_id: row.agent_id,
    agent_status: row.agent_status,
    agent_plan_id: row.plan_id,
    plan_status: row.plan_status,
    plan_hash: row.plan_hash,
    plan_verification_hash: row.plan_verification_hash,
    run_id: row.run_id,
    run_status: row.run_status,
    run_plan_hash: row.run_plan_hash,
    plan_evidence_manifest_id: row.manifest_id,
    manifest_status: row.manifest_status,
    manifest_plan_hash: row.manifest_plan_hash,
    manifest_verification_hash: row.manifest_verification_hash,
    evidence_counts: evidenceCounts,
    nodes,
    edges,
  };
  return {
    ok: true,
    provider: "agentops-human-session",
    operation: "work_delivery_graph_readback",
    schema_version: GRAPH_SCHEMA_VERSION,
    status: "ready",
    control_plane: "typescript_postgres",
    workspace_id: row.workspace_id,
    run_id: row.run_id,
    task_id: row.task_id,
    agent_id: row.agent_id,
    agent_plan_id: row.plan_id,
    plan_hash: row.plan_hash,
    plan_evidence_manifest_id: row.manifest_id,
    evidence_counts: evidenceCounts,
    nodes,
    edges,
    graph_hash: stableHash(graphMaterial),
    authority: "workspace_authoritative_postgres_joins",
    safety: {
      read_only: true,
      evidence_ledger_mutated: false,
      ledger_mutated: false,
      live_execution_performed: false,
      provider_call_performed: false,
      python_proxy_performed: false,
      workspace_bound: true,
      audit_workspace_bound: true,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      raw_content_omitted: true,
      normalized_args_omitted: true,
      uri_omitted: true,
      approval_reason_omitted: true,
      credentials_omitted: true,
      token_omitted: true,
      dsn_omitted: true,
    },
    provider_call_performed: false,
    python_proxy_performed: false,
    token_omitted: true,
  };
}

export async function readWorkspaceRunEvidenceGraph(
  request: Request,
  rawRunId: unknown,
): Promise<HumanReadResult> {
  const runId = runIdentifier(rawRunId);
  const workspaceId = requestedWorkspace(request);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(
      client,
      request.headers,
      workspaceId,
    );
    return {
      status: 200,
      body: graphPayload(
        await graphRow(client, identity.workspaceId, runId),
      ),
    };
  });
}
