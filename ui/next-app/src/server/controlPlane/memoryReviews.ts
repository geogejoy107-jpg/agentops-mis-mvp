import type { PoolClient } from "pg";

import { withPostgresTransaction } from "./db";
import {
  authenticateHumanReviewer,
  opaqueReference,
  rejectMachineCredentials,
  validateWriteOrigin,
  type HumanSessionIdentity,
} from "./humanSession";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, appendRuntimeEvent, stableHash } from "./ledger";

type MemoryDecision = "approved" | "rejected";

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
const HUMAN_OWNED_FIELDS = new Set([
  "actor_id",
  "actor_type",
  "decision",
  "owner_user_id",
  "review_status",
  "session_id",
  "user_id",
]);

type MemoryReviewRow = {
  memory_id: string;
  workspace_id: string;
  task_id: string | null;
  agent_id: string | null;
  review_status: string;
  owner_user_id: string | null;
  updated_at: string;
};

type IdempotencyRow = {
  workspace_id: string;
  user_id: string;
  idempotency_key_hash: string;
  request_hash: string;
  memory_id: string;
  decision: string;
  status: string;
  created_at: string;
  completed_at: string | null;
};

type EntitlementRow = {
  edition: string;
  status: string;
  effective_at: Date | string;
  expires_at: Date | string | null;
};

function identifier(value: unknown, field: string) {
  if (typeof value !== "string" || !/^[A-Za-z0-9._:-]{1,128}$/.test(value)) {
    throw new ControlPlaneHttpError(400, `${field}_invalid`, `${field} must use 1-128 safe identifier characters.`);
  }
  return value;
}

function decision(value: unknown): MemoryDecision {
  if (value === "approve") return "approved";
  if (value === "reject") return "rejected";
  throw new ControlPlaneHttpError(404, "memory_review_not_found", "Memory review route was not found.");
}

function timestamp(value: Date | string | null) {
  if (value === null) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}

export function validateMemoryReviewPath(
  rawMemoryId: unknown,
  rawDecision: unknown,
) {
  return {
    memoryId: identifier(rawMemoryId, "memory_id"),
    requestedDecision: decision(rawDecision),
  };
}

export function validateMemoryReviewQuery(requestUrl: string) {
  let url: URL;
  try {
    url = new URL(requestUrl);
  } catch {
    throw new ControlPlaneHttpError(
      400,
      "memory_review_url_invalid",
      "Memory review URL is invalid.",
    );
  }
  if ([...url.searchParams.keys()].length > 0) {
    throw new ControlPlaneHttpError(
      400,
      "memory_review_query_unsupported",
      "Memory review decisions do not accept query parameters.",
    );
  }
}

export function validateMemoryReviewBody(body: Record<string, unknown>) {
  for (const field of Object.keys(body)) {
    if (HUMAN_OWNED_FIELDS.has(field)) {
      throw new ControlPlaneHttpError(
        403,
        "human_actor_server_owned",
        "Memory review actor and terminal state are derived from the authenticated Human Session.",
      );
    }
    if (field !== "workspace_id") {
      throw new ControlPlaneHttpError(
        400,
        "memory_review_field_unsupported",
        "Memory review decisions accept only workspace_id.",
      );
    }
  }
  if (Object.hasOwn(body, "workspace_id")) {
    identifier(body.workspace_id, "workspace_id");
  }
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
      "Memory review decisions require a commercial workspace edition.",
    );
  }
  return entitlement.edition;
}

function idempotencyKey(headers: Headers) {
  const value = String(headers.get("idempotency-key") || "").trim();
  if (!/^[A-Za-z0-9._:-]{16,128}$/.test(value)) {
    throw new ControlPlaneHttpError(
      400,
      "idempotency_key_required",
      "Idempotency-Key must use 16-128 safe identifier characters.",
    );
  }
  return value;
}

function publicMemory(row: MemoryReviewRow) {
  return {
    memory_id: row.memory_id,
    workspace_id: row.workspace_id,
    task_id: row.task_id,
    agent_id: row.agent_id,
    review_status: row.review_status,
    updated_at: row.updated_at,
    owner_user_id_omitted: true,
    source_ref_omitted: true,
    access_tags_omitted: true,
    raw_content_omitted: true,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    credentials_omitted: true,
    token_omitted: true,
  };
}

function response(
  row: MemoryReviewRow,
  outcome: "updated" | "unchanged",
  entitlementEdition: string,
) {
  return {
    status: 200,
    body: {
      ok: true,
      provider: "agentops-human-memory-review",
      control_plane: "typescript_postgres",
      operation: "memory_review",
      outcome,
      review_status: row.review_status,
      entitlement_edition: entitlementEdition,
      memory: publicMemory(row),
      audit_recorded: true,
      runtime_event_recorded: true,
      python_proxy_performed: false,
      owner_user_id_omitted: true,
      source_ref_omitted: true,
      access_tags_omitted: true,
      credentials_omitted: true,
      raw_body_omitted: true,
      raw_content_omitted: true,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      token_omitted: true,
    },
  };
}

async function findMemory(client: PoolClient, memoryId: string, workspaceId: string, lock = false) {
  const suffix = lock ? " FOR UPDATE" : "";
  const result = await client.query<MemoryReviewRow>(
    `SELECT memory_id,workspace_id,task_id,agent_id,review_status,owner_user_id,updated_at
    FROM memories WHERE memory_id=$1 AND workspace_id=$2${suffix}`,
    [memoryId, workspaceId],
  );
  return result.rows[0];
}

async function reviewCandidate(
  client: PoolClient,
  identity: HumanSessionIdentity,
  memoryId: string,
  requestedDecision: MemoryDecision,
  rawIdempotencyKey: string,
  entitlementEdition: string,
) {
  const idempotencyHash = stableHash({
    workspace_id: identity.workspaceId,
    user_id: identity.userId,
    idempotency_key: rawIdempotencyKey,
  });
  const requestHash = stableHash({
    workspace_id: identity.workspaceId,
    user_id: identity.userId,
    memory_id: memoryId,
    decision: requestedDecision,
  });
  await client.query(
    "SELECT pg_advisory_xact_lock(hashtext($1))",
    [`agentops-human-memory-idempotency:${identity.workspaceId}:${identity.userId}:${idempotencyHash}`],
  );
  const existingResult = await client.query<IdempotencyRow>(
    `SELECT workspace_id,user_id,idempotency_key_hash,request_hash,memory_id,decision,status,created_at,completed_at
    FROM human_memory_review_requests
    WHERE workspace_id=$1 AND user_id=$2 AND idempotency_key_hash=$3 FOR UPDATE`,
    [identity.workspaceId, identity.userId, idempotencyHash],
  );
  const existing = existingResult.rows[0];
  if (existing) {
    if (existing.request_hash !== requestHash
      || existing.memory_id !== memoryId
      || existing.decision !== requestedDecision
      || existing.status !== "completed") {
      throw new ControlPlaneHttpError(
        409,
        "memory_review_idempotency_conflict",
        "Idempotency-Key is already bound to another memory review request.",
      );
    }
    const replay = await findMemory(client, memoryId, identity.workspaceId);
    if (!replay || replay.review_status !== requestedDecision || replay.owner_user_id !== identity.userId) {
      throw new ControlPlaneHttpError(409, "memory_review_state_conflict", "Memory review replay state is unavailable.");
    }
    const evidence = (await client.query<{
      audit_recorded: boolean;
      runtime_event_recorded: boolean;
    }>(
      `SELECT
        EXISTS(
          SELECT 1 FROM audit_logs
          WHERE workspace_id=$1 AND actor_type='user' AND actor_id=$2
            AND action=$3 AND entity_type='memories' AND entity_id=$4
            AND metadata_json::jsonb ->> 'idempotency_ref'=$5
        ) AS audit_recorded,
        EXISTS(
          SELECT 1 FROM runtime_events
          WHERE workspace_id=$1 AND event_type=$3 AND status='completed'
            AND raw_payload_hash=$6
        ) AS runtime_event_recorded`,
      [
        identity.workspaceId,
        identity.userId,
        `memory.${requestedDecision}`,
        memoryId,
        opaqueReference("idemref", idempotencyHash),
        requestHash,
      ],
    )).rows[0];
    if (!evidence?.audit_recorded || !evidence.runtime_event_recorded) {
      throw new ControlPlaneHttpError(
        409,
        "memory_review_evidence_conflict",
        "Memory review replay evidence is unavailable.",
      );
    }
    return response(replay, "unchanged", entitlementEdition);
  }

  await client.query(
    "SELECT pg_advisory_xact_lock(hashtext($1))",
    [`agentops-memory:${identity.workspaceId}:${memoryId}`],
  );
  const before = await findMemory(client, memoryId, identity.workspaceId, true);
  if (!before) {
    throw new ControlPlaneHttpError(404, "memory_not_found", "Memory was not found in this workspace.");
  }
  if (before.review_status !== "candidate") {
    throw new ControlPlaneHttpError(409, "memory_review_conflict", "Memory candidate has already received a terminal review.");
  }
  if (before.owner_user_id && before.owner_user_id !== identity.userId) {
    throw new ControlPlaneHttpError(409, "memory_reviewer_conflict", "Memory candidate is assigned to another reviewer.");
  }

  const now = new Date().toISOString();
  const updated = await client.query<MemoryReviewRow>(
    `UPDATE memories SET review_status=$1,owner_user_id=$2,updated_at=$3
    WHERE memory_id=$4 AND workspace_id=$5 AND review_status='candidate'
    RETURNING memory_id,workspace_id,task_id,agent_id,review_status,owner_user_id,updated_at`,
    [requestedDecision, identity.userId, now, memoryId, identity.workspaceId],
  );
  const after = updated.rows[0];
  if (!after) {
    throw new ControlPlaneHttpError(409, "memory_review_conflict", "Memory review lost its single-winner transition.");
  }
  await client.query(
    `INSERT INTO human_memory_review_requests(
      workspace_id,user_id,idempotency_key_hash,request_hash,memory_id,decision,status,created_at,completed_at
    ) VALUES($1,$2,$3,$4,$5,$6,'completed',$7,$7)`,
    [identity.workspaceId, identity.userId, idempotencyHash, requestHash, memoryId, requestedDecision, now],
  );
  await appendAudit(client, {
    workspaceId: identity.workspaceId,
    actorType: "user",
    actorId: identity.userId,
    action: `memory.${requestedDecision}`,
    entityType: "memories",
    entityId: memoryId,
    before: publicMemory(before),
    after: publicMemory(after),
    metadata: {
      workspace_id: identity.workspaceId,
      membership_role: identity.membershipRole,
      entitlement_edition: entitlementEdition,
      session_ref: identity.sessionRef,
      idempotency_ref: opaqueReference("idemref", idempotencyHash),
      credentials_omitted: true,
      raw_body_omitted: true,
      raw_content_omitted: true,
    },
  });
  await appendRuntimeEvent(client, {
    workspaceId: identity.workspaceId,
    eventType: `memory.${requestedDecision}`,
    status: "completed",
    taskId: before.task_id,
    agentId: before.agent_id,
    outputSummary: `Human reviewer marked the candidate memory ${requestedDecision}.`,
    rawPayloadHash: requestHash,
  });
  return response(after, "updated", entitlementEdition);
}

export async function reviewWorkspaceMemory(
  request: Request,
  body: Record<string, unknown>,
  rawMemoryId: unknown,
  rawDecision: unknown,
) {
  validateMemoryReviewQuery(request.url);
  validateMemoryReviewBody(body);
  const { memoryId, requestedDecision } = validateMemoryReviewPath(
    rawMemoryId,
    rawDecision,
  );
  const replayKey = idempotencyKey(request.headers);
  rejectMachineCredentials(request.headers);
  validateWriteOrigin(request.headers);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanReviewer(client, request.headers, body.workspace_id);
    const entitlementEdition = await activeCommercialEntitlement(
      client,
      identity.workspaceId,
    );
    return reviewCandidate(
      client,
      identity,
      memoryId,
      requestedDecision,
      replayKey,
      entitlementEdition,
    );
  });
}
