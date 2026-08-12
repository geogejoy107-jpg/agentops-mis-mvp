import { NextRequest, NextResponse } from "next/server";

import { boundedJsonObject } from "@/server/controlPlane/boundedJson";
import { controlPlaneMode } from "@/server/controlPlane/config";
import { withPostgresTransaction } from "@/server/controlPlane/db";
import { authenticateHumanWriteMember } from "@/server/controlPlane/humanSession";
import { ownHumanReadGet } from "@/server/controlPlane/humanReadRoute";
import { ControlPlaneHttpError, errorPayload } from "@/server/controlPlane/http";
import { appendAudit, appendRuntimeEvent, pythonFloat, stableHash } from "@/server/controlPlane/ledger";
import { listWorkspaceTasks } from "@/server/controlPlane/workspaceTaskRunReads";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TASK_WRITE_MAX_BODY_BYTES = 8 * 1024;
const TASK_OPERATOR_ROLES = new Set(["operator", "workspace-admin", "owner"]);
const PRIORITIES = new Set(["low", "medium", "high", "urgent"]);
const RISK_LEVELS = new Set(["low", "medium", "high", "critical"]);
const PRIVATE_WRITE_HEADERS = {
  "Cache-Control": "no-store",
  Vary: "Cookie, Origin, X-AgentOps-Workspace-Id, X-AgentOps-CSRF, Idempotency-Key",
};

type HumanTaskRow = {
  task_id: string;
  workspace_id: string;
  title: string;
  description: string | null;
  requester_id: string;
  owner_agent_id: string;
  collaborator_agent_ids: string;
  status: string;
  priority: string;
  due_date: string | null;
  acceptance_criteria: string;
  risk_level: string;
  budget_limit_usd: number;
  created_at: string;
  updated_at: string;
};

function boundedText(value: unknown, limit: number) {
  const normalized = String(value ?? "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (normalized.length > limit) {
    throw new ControlPlaneHttpError(
      400,
      "human_task_field_too_long",
      `Task fields must not exceed ${limit} characters.`,
    );
  }
  return normalized;
}

function requiredChoice(value: unknown, allowed: Set<string>, field: string) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (!allowed.has(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      `human_task_${field}_invalid`,
      `Task ${field} is invalid.`,
    );
  }
  return normalized;
}

function taskBudget(value: unknown) {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1_000_000) {
    throw new ControlPlaneHttpError(
      400,
      "human_task_budget_invalid",
      "Task budget must be between 0 and 1000000 USD.",
    );
  }
  return Math.round(parsed * 1_000_000) / 1_000_000;
}

function idempotencyKey(headers: Headers) {
  const value = String(headers.get("idempotency-key") || "").trim();
  if (!/^[A-Za-z0-9._:-]{16,128}$/.test(value)) {
    throw new ControlPlaneHttpError(
      400,
      "idempotency_key_invalid",
      "Idempotency-Key must use 16-128 safe identifier characters.",
    );
  }
  return value;
}

export async function GET(request: NextRequest) {
  return ownHumanReadGet(request, {
    upstreamPath: "/tasks",
    handler: (ownedRequest) => {
      const searchParams = new URL(ownedRequest.url).searchParams;
      return listWorkspaceTasks(
        ownedRequest.headers,
        searchParams.get("workspace_id"),
        searchParams.getAll("status"),
        searchParams.get("limit"),
      );
    },
  });
}

export async function POST(request: NextRequest) {
  try {
    if (controlPlaneMode() === "proxy") {
      throw new ControlPlaneHttpError(
        503,
        "human_session_direct_route_required",
        "Commercial task dispatch requires TypeScript Postgres Human Session authority.",
      );
    }
    const body = await boundedJsonObject(request, {
      maxBytes: TASK_WRITE_MAX_BODY_BYTES,
      label: "Human task dispatch",
    });
    const supported = new Set([
      "workspace_id",
      "title",
      "description",
      "owner_agent_id",
      "priority",
      "risk_level",
      "acceptance_criteria",
      "budget_limit_usd",
    ]);
    const unsupported = Object.keys(body).find((field) => !supported.has(field));
    if (unsupported) {
      throw new ControlPlaneHttpError(
        400,
        "human_task_field_unsupported",
        "Human task dispatch received an unsupported field.",
      );
    }
    const replayKey = idempotencyKey(request.headers);
    const result = await withPostgresTransaction(async (client) => {
      const identity = await authenticateHumanWriteMember(
        client,
        request.headers,
        body.workspace_id,
      );
      if (!TASK_OPERATOR_ROLES.has(identity.membershipRole)) {
        throw new ControlPlaneHttpError(
          403,
          "human_task_role_forbidden",
          "Task dispatch requires operator, workspace-admin, or owner authority.",
        );
      }
      const title = boundedText(body.title, 160);
      const ownerAgentId = boundedText(body.owner_agent_id, 120);
      if (!title || !ownerAgentId) {
        throw new ControlPlaneHttpError(
          400,
          "human_task_fields_required",
          "Task title and owner agent are required.",
        );
      }
      const workspaceAgent = (await client.query<{ agent_id: string; status: string }>(
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
            SELECT 1 FROM tasks task
            WHERE task.owner_agent_id=agent.agent_id AND task.workspace_id=$2
          )
        FOR SHARE`,
        [ownerAgentId, identity.workspaceId],
      )).rows[0];
      if (!workspaceAgent || workspaceAgent.status === "disabled") {
        throw new ControlPlaneHttpError(
          400,
          "human_task_owner_unavailable",
          "The selected Agent is unavailable in this workspace.",
        );
      }
      const taskId = `tsk_human_${stableHash({
        workspace_id: identity.workspaceId,
        user_id: identity.userId,
        idempotency_key: replayKey,
      }).slice(0, 24)}`;
      const description = boundedText(body.description, 1200) || null;
      const priority = requiredChoice(
        body.priority || "medium",
        PRIORITIES,
        "priority",
      );
      const acceptanceCriteria = boundedText(body.acceptance_criteria, 600)
        || "Worker must satisfy the task acceptance criteria and write governed ledger evidence.";
      const riskLevel = requiredChoice(
        body.risk_level || "medium",
        RISK_LEVELS,
        "risk_level",
      );
      const budgetLimitUsd = taskBudget(body.budget_limit_usd);
      const requestHash = stableHash({
        workspace_id: identity.workspaceId,
        user_id: identity.userId,
        idempotency_key: replayKey,
        title,
        description,
        owner_agent_id: ownerAgentId,
        priority,
        risk_level: riskLevel,
        acceptance_criteria: acceptanceCriteria,
        budget_limit_usd: pythonFloat(budgetLimitUsd),
      });
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [
        `agentops-task:${taskId}`,
      ]);
      const existing = (await client.query<HumanTaskRow>(
        "SELECT * FROM tasks WHERE task_id=$1 FOR UPDATE",
        [taskId],
      )).rows[0];
      const now = new Date().toISOString();
      const task: HumanTaskRow = {
        task_id: taskId,
        workspace_id: identity.workspaceId,
        title,
        description,
        requester_id: identity.userId,
        owner_agent_id: ownerAgentId,
        collaborator_agent_ids: "[]",
        status: "planned",
        priority,
        due_date: null,
        acceptance_criteria: acceptanceCriteria,
        risk_level: riskLevel,
        budget_limit_usd: budgetLimitUsd,
        created_at: existing?.created_at || now,
        updated_at: existing?.updated_at || now,
      };
      if (existing) {
        const binding = (await client.query<{ request_hash: string | null }>(
          `SELECT metadata_json::jsonb ->> 'request_hash' AS request_hash
          FROM audit_logs
          WHERE workspace_id=$1 AND actor_type='user' AND actor_id=$2
            AND action='human.task_dispatch' AND entity_type='tasks'
            AND entity_id=$3
          ORDER BY created_at DESC,audit_id DESC
          LIMIT 1`,
          [identity.workspaceId, identity.userId, taskId],
        )).rows[0];
        if (binding?.request_hash !== requestHash) {
          throw new ControlPlaneHttpError(
            409,
            "human_task_idempotency_conflict",
            "Idempotency-Key is already bound to another task dispatch.",
          );
        }
        return { status: 200, outcome: "unchanged" as const, task: existing };
      }
      await client.query(
        `INSERT INTO tasks(
          task_id,workspace_id,title,description,requester_id,owner_agent_id,
          collaborator_agent_ids,status,priority,due_date,acceptance_criteria,
          risk_level,budget_limit_usd,created_at,updated_at
        ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)`,
        [
          task.task_id,
          task.workspace_id,
          task.title,
          task.description,
          task.requester_id,
          task.owner_agent_id,
          task.collaborator_agent_ids,
          task.status,
          task.priority,
          task.due_date,
          task.acceptance_criteria,
          task.risk_level,
          task.budget_limit_usd,
          task.created_at,
          task.updated_at,
        ],
      );
      await appendAudit(client, {
        workspaceId: identity.workspaceId,
        actorType: "user",
        actorId: identity.userId,
        action: "human.task_dispatch",
        entityType: "tasks",
        entityId: task.task_id,
        after: task,
        metadata: {
          membership_role: identity.membershipRole,
          owner_agent_id: task.owner_agent_id,
          raw_payload_omitted: true,
          token_omitted: true,
        },
        requestHash,
      });
      await appendRuntimeEvent(client, {
        workspaceId: identity.workspaceId,
        eventType: "task.human_dispatch",
        status: task.status,
        taskId: task.task_id,
        agentId: task.owner_agent_id,
        inputSummary: `Human dispatched task: ${task.title}`,
        rawPayloadHash: requestHash,
      });
      return { status: 201, outcome: "created" as const, task };
    });
    return NextResponse.json(
      {
        ok: true,
        provider: "agentops-human-session",
        control_plane: "typescript_postgres",
        operation: "task_dispatch",
        outcome: result.outcome,
        task: result.task,
        task_id: result.task.task_id,
        workspace_id: result.task.workspace_id,
        token_omitted: true,
      },
      { status: result.status, headers: PRIVATE_WRITE_HEADERS },
    );
  } catch (error) {
    const failure = errorPayload(error);
    return NextResponse.json(failure.body, {
      status: failure.status,
      headers: PRIVATE_WRITE_HEADERS,
    });
  }
}
