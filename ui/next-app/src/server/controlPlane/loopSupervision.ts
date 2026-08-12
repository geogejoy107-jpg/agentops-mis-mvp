import type { PoolClient } from "pg";

import {
  authenticateAgentGateway,
  enforceWorkspaceBinding,
} from "./auth";
import { withPostgresTransaction } from "./db";
import { ControlPlaneHttpError } from "./http";
import { stableHash } from "./ledger";
import { POSTGRES_MIGRATION_MANIFEST } from "./schemaManifest";

const IDENTIFIER = /^[A-Za-z0-9._:-]{1,128}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const SUPPORTED_ADAPTERS = new Set(["hermes", "openclaw"]);
const REQUIRED_METHOD_STEPS = [
  "READ",
  "PLAN",
  "RETRIEVE",
  "COMPARE",
  "EXECUTE",
  "VERIFY",
  "RECORD",
] as const;
const CONNECTOR_FRESHNESS_MS = 72 * 60 * 60 * 1000;

type LoopSupervisionResult = {
  status: number;
  body: Record<string, unknown>;
};

type TaskRow = {
  task_id: string;
  workspace_id: string;
  owner_agent_id: string | null;
  collaborator_agent_ids: string;
  status: string;
};

type AgentRow = {
  agent_id: string;
  runtime_type: string;
  status: string;
};

type PlanRow = {
  plan_id: string;
  workspace_id: string;
  task_id: string | null;
  agent_id: string;
  status: string;
  approval_required: number;
  execution_steps_json: string;
  plan_hash: string | null;
  verified_at: string | null;
  verification_result_hash: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
};

type ConnectorRow = {
  runtime_connector_id: string;
  provider: string;
  status: string;
  allow_real_run: number;
  require_confirm_run: number;
  trust_status: string;
  observation_level: string;
  last_health_at: string | null;
  last_error: string | null;
};

function identifier(value: unknown, field: string) {
  const normalized = String(value ?? "").trim();
  if (!IDENTIFIER.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      `${field}_invalid`,
      `${field} must use 1-128 safe identifier characters.`,
    );
  }
  return normalized;
}

function stringList(value: string) {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed)
      ? [...new Set(parsed.map(String).map((item) => item.trim()).filter(Boolean))]
      : [];
  } catch {
    return [];
  }
}

async function assertSchemaReady(client: PoolClient) {
  const result = await client.query<{
    component: string;
    version: string;
    schema_contract: string;
    checksum: string;
  }>(
    `SELECT component,version,schema_contract,checksum
    FROM agentops_schema_migrations
    WHERE component=ANY($1::text[])`,
    [POSTGRES_MIGRATION_MANIFEST.map((migration) => migration.component)],
  );
  const rows = new Map(result.rows.map((row) => [row.component, row]));
  const ready = POSTGRES_MIGRATION_MANIFEST.every((migration) => {
    const row = rows.get(migration.component);
    return row?.version === migration.version
      && row.schema_contract === migration.schemaContract
      && row.checksum === migration.checksum;
  });
  if (!ready) {
    throw new ControlPlaneHttpError(
      503,
      "loop_supervision_schema_not_ready",
      "Loop supervision requires the current commercial Postgres schema.",
    );
  }
}

function connectorFresh(row: ConnectorRow | undefined) {
  const checkedAt = Date.parse(String(row?.last_health_at || ""));
  return Boolean(
    row
    && row.status === "ready"
    && Boolean(row.allow_real_run)
    && Boolean(row.require_confirm_run)
    && row.trust_status === "trusted"
    && row.observation_level === "ledger_summary_only"
    && !String(row.last_error || "").trim()
    && Number.isFinite(checkedAt)
    && Date.now() - checkedAt <= CONNECTOR_FRESHNESS_MS
    && checkedAt <= Date.now() + 60_000,
  );
}

function gate(id: string, ok: boolean) {
  return {
    id,
    ok,
    status: ok ? "pass" : "blocked",
    confirm_required: id === "trusted_runtime_connector",
    server_executes_shell: false,
    token_omitted: true,
  };
}

export async function getOperatorLoopSupervision(
  request: Request,
): Promise<LoopSupervisionResult> {
  const url = new URL(request.url);
  const adapter = String(url.searchParams.get("adapter") || "").trim().toLowerCase();
  if (!SUPPORTED_ADAPTERS.has(adapter)) {
    throw new ControlPlaneHttpError(
      400,
      "adapter_invalid",
      "Loop supervision supports hermes or openclaw.",
    );
  }
  const taskId = identifier(url.searchParams.get("task_id"), "task_id");

  return withPostgresTransaction(async (client) => {
    await assertSchemaReady(client);
    const identity = await authenticateAgentGateway(
      client,
      request.headers,
      "tasks:read",
    );
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
    });
    const requestedAgentId = identifier(
      url.searchParams.get("agent_id") || identity.agentId,
      "agent_id",
    );
    if (requestedAgentId !== identity.agentId) {
      throw new ControlPlaneHttpError(
        403,
        "forbidden",
        "Loop supervision agent_id must match the Agent credential.",
      );
    }

    const task = (await client.query<TaskRow>(
      `SELECT task_id,workspace_id,owner_agent_id,collaborator_agent_ids,status
      FROM tasks WHERE task_id=$1 AND workspace_id=$2 FOR SHARE`,
      [taskId, identity.workspaceId],
    )).rows[0];
    if (!task) {
      throw new ControlPlaneHttpError(
        404,
        "task_not_found",
        "Loop supervision task was not found.",
      );
    }
    const collaborators = stringList(task.collaborator_agent_ids);
    const assigned = task.owner_agent_id === identity.agentId
      || collaborators.includes(identity.agentId);
    if (!assigned) {
      throw new ControlPlaneHttpError(
        403,
        "forbidden",
        "Agent is not currently assigned to the supervised task.",
      );
    }

    const agent = (await client.query<AgentRow>(
      `SELECT agent_id,runtime_type,status
      FROM agents WHERE agent_id=$1 FOR SHARE`,
      [identity.agentId],
    )).rows[0];
    const plan = (await client.query<PlanRow>(
      `SELECT plan_id,workspace_id,task_id,agent_id,status,approval_required,
        execution_steps_json,plan_hash,verified_at,verification_result_hash,
        approved_by_user_id,approved_at
      FROM agent_plans
      WHERE workspace_id=$1 AND task_id=$2 AND agent_id=$3
        AND status IN ('submitted','approved')
      ORDER BY updated_at DESC,plan_id DESC
      LIMIT 1 FOR SHARE`,
      [identity.workspaceId, taskId, identity.agentId],
    )).rows[0];
    const connector = (await client.query<ConnectorRow>(
      `SELECT runtime_connector_id,provider,status,allow_real_run,
        require_confirm_run,trust_status,observation_level,last_health_at,
        last_error
      FROM runtime_connectors
      WHERE provider IN ('agent_gateway',$1)
      ORDER BY
        CASE WHEN provider=$1 THEN 0 ELSE 1 END,
        updated_at DESC,runtime_connector_id
      LIMIT 1 FOR SHARE`,
      [adapter],
    )).rows[0];

    const planSteps = plan ? stringList(plan.execution_steps_json) : [];
    const planIdentityValid = Boolean(
      plan
      && plan.workspace_id === identity.workspaceId
      && plan.task_id === taskId
      && plan.agent_id === identity.agentId,
    );
    const planVerified = Boolean(
      planIdentityValid
      && SHA256.test(String(plan?.plan_hash || ""))
      && SHA256.test(String(plan?.verification_result_hash || ""))
      && Number.isFinite(Date.parse(String(plan?.verified_at || "")))
      && REQUIRED_METHOD_STEPS.every((step) => planSteps.includes(step)),
    );
    const planApprovalValid = Boolean(
      plan
      && (
        !Boolean(plan.approval_required)
        || (
          plan.status === "approved"
          && Boolean(plan.approved_by_user_id)
          && Number.isFinite(Date.parse(String(plan.approved_at || "")))
        )
      ),
    );
    const taskStateValid = ["planned", "running"].includes(task.status);
    const agentRuntimeValid = Boolean(
      agent
      && agent.runtime_type === adapter
      && ["idle", "running"].includes(agent.status),
    );
    const runtimeConnectorValid = connectorFresh(connector);
    const gates = [
      gate("task_current_assignment", assigned),
      gate("task_pre_execution_state", taskStateValid),
      gate("agent_runtime_binding", agentRuntimeValid),
      gate("verified_agent_plan", planVerified),
      gate("agent_plan_approval", planApprovalValid),
      gate("trusted_runtime_connector", runtimeConnectorValid),
    ];
    const blockers = gates
      .filter((entry) => !entry.ok)
      .map((entry) => entry.id);
    const canConfirm = blockers.length === 0;
    const status = canConfirm ? "ready_to_confirm" : "blocked";
    const recommendedNext = canConfirm
      ? null
      : "Resolve the blocked supervision gates before live dispatch.";

    const item = {
      operation: "operator_loop_supervision_item",
      adapter,
      status,
      can_preview_loop: canConfirm,
      can_confirm_bounded_loop: canConfirm,
      should_record_before_execute: false,
      ready_for_live_dispatch: canConfirm,
      blockers,
      attention: [],
      review_pressure: {
        human_review_required: false,
        memory_review_required: false,
        review_items_total: 0,
        pending_approvals: 0,
        memory_candidates: 0,
        token_omitted: true,
      },
      plan_quality: {
        status: planVerified ? "pass" : "blocked",
        issue_count: planVerified ? 0 : 1,
        hard_run_start_gate: true,
        token_omitted: true,
      },
      service_closure: {
        required: false,
        status: "not_applicable",
        hard_run_start_gate: false,
        server_executes_shell: false,
        token_omitted: true,
      },
      gates,
      local_deployment: {
        local_run_path: {
          recommended_adapter: adapter,
          safety: {
            server_executes_shell: false,
            token_omitted: true,
          },
        },
        service_managed_loop: {
          adapter,
          manager: "trusted_worker_client",
          status: "not_applicable",
          service_managed_loop_ready: false,
          service_loaded: false,
          service_active_loop_ready: false,
          token_omitted: true,
        },
      },
      next_commands: {
        recommended_next: recommendedNext,
        token_omitted: true,
      },
      commands: {
        recommended_next: recommendedNext,
      },
      task_id: taskId,
      agent_id: identity.agentId,
      agent_plan_id: plan?.plan_id || null,
      runtime_connector_id: connector?.runtime_connector_id || null,
      safety: {
        read_only: true,
        ledger_mutated: false,
        live_execution_performed: false,
        server_executes_shell: false,
        raw_content_omitted: true,
        raw_prompt_omitted: true,
        raw_response_omitted: true,
        token_omitted: true,
      },
      token_omitted: true,
    };
    const projectionHash = stableHash({
      workspace_id: identity.workspaceId,
      task_id: taskId,
      agent_id: identity.agentId,
      adapter,
      status,
      blockers,
      agent_plan_id: plan?.plan_id || null,
      plan_hash: plan?.plan_hash || null,
      verification_result_hash: plan?.verification_result_hash || null,
      runtime_connector_id: connector?.runtime_connector_id || null,
      runtime_connector_health_at: connector?.last_health_at || null,
    });

    return {
      status: 200,
      body: {
        provider: "agentops-typescript-postgres",
        operation: "operator_loop_supervision",
        status,
        workspace_id: identity.workspaceId,
        adapters: [adapter],
        summary: {
          items: 1,
          ready_to_confirm: canConfirm ? 1 : 0,
          blocked: canConfirm ? 0 : 1,
          can_confirm_all: canConfirm,
          record_required: false,
          current_code_ok: true,
        },
        items: [item],
        projection_hash: projectionHash,
        contract: "nextjs_postgres_worker_loop_supervision_v1",
        auth: {
          mode: identity.mode,
          required_scope: "tasks:read",
          workspace_id: identity.workspaceId,
          agent_id: identity.agentId,
          token_omitted: true,
        },
        safety: {
          read_only: true,
          ledger_mutated: false,
          live_execution_performed: false,
          server_executes_shell: false,
          raw_content_omitted: true,
          raw_prompt_omitted: true,
          raw_response_omitted: true,
          token_omitted: true,
        },
        token_omitted: true,
        live_execution_performed: false,
      },
    };
  });
}
