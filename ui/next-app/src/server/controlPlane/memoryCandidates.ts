import type { PoolClient } from "pg";

import { withPostgresTransaction } from "./db";
import { authenticateHumanMember } from "./humanSession";
import { ControlPlaneHttpError } from "./http";
import { appendAudit } from "./ledger";

const HUMAN_MEMORY_READ_ROLES = new Set([
  "operator",
  "reviewer",
  "approver",
  "workspace-admin",
  "owner",
]);
const COMMERCIAL_EDITIONS = new Set([
  "pro_workspace",
  "team_governance",
  "enterprise_byoc",
]);
const KNOWN_INACTIVE_ENTITLEMENTS = new Set([
  "inactive",
  "suspended",
  "expired",
]);
const MEMORY_READ_LIMIT = 200;

type MemoryReviewStatus =
  | "candidate"
  | "approved"
  | "rejected"
  | "stale"
  | "superseded";

type EntitlementRow = {
  edition: string;
  status: string;
  effective_at: Date | string;
  expires_at: Date | string | null;
};

type MemoryReadRow = {
  memory_id: string;
  workspace_id: string;
  scope: string;
  memory_type: string;
  canonical_text: string;
  source_type: string;
  project_id: string | null;
  task_id: string | null;
  run_id: string | null;
  agent_id: string | null;
  confidence: number;
  review_status: MemoryReviewStatus;
  ttl_review_due_at: string | null;
  supersedes_memory_id: string | null;
  created_at: string;
  updated_at: string;
};

function timestamp(value: Date | string | null) {
  if (value === null) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
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
      "human_memory_read_state_invalid",
      `The stored ${field} is outside the bounded Memory read contract.`,
    );
  }
  return value;
}

function boundedConfidence(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
    throw new ControlPlaneHttpError(
      503,
      "human_memory_read_state_invalid",
      "The stored confidence is outside the bounded Memory read contract.",
    );
  }
  return parsed;
}

function publicMemory(row: MemoryReadRow) {
  return {
    memory_id: boundedText(row.memory_id, "memory_id", 128),
    workspace_id: boundedText(row.workspace_id, "workspace_id", 128),
    scope: boundedText(row.scope, "scope", 32),
    memory_type: boundedText(row.memory_type, "memory_type", 64),
    canonical_text: boundedText(row.canonical_text, "canonical_text", 16_384),
    source_type: boundedText(row.source_type, "source_type", 64),
    project_id: boundedText(row.project_id, "project_id", 128, true),
    task_id: boundedText(row.task_id, "task_id", 128, true),
    run_id: boundedText(row.run_id, "run_id", 128, true),
    agent_id: boundedText(row.agent_id, "agent_id", 128, true),
    confidence: boundedConfidence(row.confidence),
    review_status: boundedText(row.review_status, "review_status", 32),
    ttl_review_due_at: boundedText(
      row.ttl_review_due_at,
      "ttl_review_due_at",
      64,
      true,
    ),
    supersedes_memory_id: boundedText(
      row.supersedes_memory_id,
      "supersedes_memory_id",
      128,
      true,
    ),
    created_at: boundedText(row.created_at, "created_at", 64),
    updated_at: boundedText(row.updated_at, "updated_at", 64),
    source_ref_omitted: true,
    owner_user_id_omitted: true,
    access_tags_omitted: true,
    credentials_omitted: true,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    token_omitted: true,
  };
}

async function activeCommercialEntitlement(
  client: PoolClient,
  workspaceId: string,
) {
  await client.query(
    "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
    [`agentops:workspace-entitlement:${workspaceId}`],
  );
  const now = timestamp((await client.query<{ evaluated_at: Date | string }>(
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
  const effectiveAt = timestamp(entitlement.effective_at);
  const expiresAt = timestamp(entitlement.expires_at);
  if (!now || !effectiveAt || (entitlement.expires_at !== null && !expiresAt)) {
    throw new ControlPlaneHttpError(
      503,
      "workspace_entitlement_invalid",
      "The workspace entitlement state is invalid.",
    );
  }
  if (entitlement.status !== "active") {
    const known = KNOWN_INACTIVE_ENTITLEMENTS.has(entitlement.status);
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
  if (!COMMERCIAL_EDITIONS.has(entitlement.edition)) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_edition_forbidden",
      "Memory governance reads require a commercial workspace edition.",
    );
  }
  return entitlement.edition;
}

function reviewStatus(value: unknown): MemoryReviewStatus | null {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (!normalized) return null;
  if (
    normalized === "candidate"
    || normalized === "approved"
    || normalized === "rejected"
    || normalized === "stale"
    || normalized === "superseded"
  ) {
    return normalized;
  }
  throw new ControlPlaneHttpError(
    400,
    "human_memory_review_status_invalid",
    "Memory review_status is invalid.",
  );
}

function boundedLimit(value: unknown) {
  const normalized = String(value ?? "").trim();
  if (!normalized) return MEMORY_READ_LIMIT;
  if (!/^[1-9][0-9]{0,2}$/.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      "human_memory_limit_invalid",
      "Memory limit must be an integer between 1 and 200.",
    );
  }
  const parsed = Number(normalized);
  if (parsed > MEMORY_READ_LIMIT) {
    throw new ControlPlaneHttpError(
      400,
      "human_memory_limit_invalid",
      "Memory limit must be an integer between 1 and 200.",
    );
  }
  return parsed;
}

async function readWorkspaceMemories(
  headers: Headers,
  workspaceId: unknown,
  options: Readonly<{
    operation: "candidates" | "export";
    status: MemoryReviewStatus | null;
    limit: number;
  }>,
) {
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanMember(client, headers, workspaceId);
    const role = identity.membershipRole.trim().toLowerCase();
    if (!HUMAN_MEMORY_READ_ROLES.has(role)) {
      throw new ControlPlaneHttpError(
        403,
        "human_memory_read_role_forbidden",
        "Memory governance reads require operator, reviewer, approver, workspace-admin, or owner authority.",
      );
    }
    const edition = await activeCommercialEntitlement(client, identity.workspaceId);
    const rows = await client.query<MemoryReadRow>(
      `SELECT memory_id,workspace_id,scope,memory_type,canonical_text,
        source_type,project_id,task_id,run_id,agent_id,confidence,
        review_status,ttl_review_due_at,supersedes_memory_id,created_at,updated_at
      FROM memories
      WHERE workspace_id=$1
        AND ($2::text IS NULL OR review_status=$2)
      ORDER BY updated_at DESC,memory_id
      LIMIT $3`,
      [identity.workspaceId, options.status, options.limit],
    );
    const body = rows.rows.map(publicMemory);
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "user",
      actorId: identity.userId,
      action: `human.memory_${options.operation}_read`,
      entityType: "memories",
      entityId: options.operation,
      metadata: {
        membership_role: role,
        entitlement_edition: edition,
        review_status: options.status,
        result_count: body.length,
        result_limit: options.limit,
        response_bounded: true,
        sensitive_fields_omitted: true,
        token_omitted: true,
      },
    });
    return {
      status: 200,
      body,
      workspaceId: identity.workspaceId,
      entitlementEdition: edition,
    };
  });
}

export async function listWorkspaceMemoryCandidates(
  headers: Headers,
  workspaceId: unknown,
) {
  const result = await readWorkspaceMemories(headers, workspaceId, {
    operation: "candidates",
    status: "candidate",
    limit: MEMORY_READ_LIMIT,
  });
  return { status: result.status, body: result.body };
}

export async function exportWorkspaceMemories(
  headers: Headers,
  workspaceId: unknown,
  rawStatus: unknown,
  rawLimit: unknown,
) {
  const result = await readWorkspaceMemories(headers, workspaceId, {
    operation: "export",
    status: reviewStatus(rawStatus),
    limit: boundedLimit(rawLimit),
  });
  return {
    status: result.status,
    body: {
      ok: true,
      control_plane: "typescript_postgres",
      workspace_id: result.workspaceId,
      entitlement_edition: result.entitlementEdition,
      memories: result.body,
      bounds: { memories: MEMORY_READ_LIMIT },
      audit_recorded: true,
      python_proxy_performed: false,
      source_ref_omitted: true,
      owner_user_id_omitted: true,
      access_tags_omitted: true,
      credentials_omitted: true,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      token_omitted: true,
    },
  };
}
