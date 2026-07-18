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

function identifier(value: unknown, field: string) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(400, `${field}_invalid`, `${field} must use 1-128 safe identifier characters.`);
  }
  return normalized;
}

function decision(value: unknown): MemoryDecision {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "approve" || normalized === "approved") return "approved";
  if (normalized === "reject" || normalized === "rejected") return "rejected";
  throw new ControlPlaneHttpError(404, "memory_review_not_found", "Memory review route was not found.");
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
    owner_user_id: row.owner_user_id,
    updated_at: row.updated_at,
    raw_content_omitted: true,
  };
}

function response(row: MemoryReviewRow, outcome: "updated" | "unchanged") {
  return {
    status: 200,
    body: {
      ok: true,
      provider: "agentops-human-memory-review",
      control_plane: "typescript_postgres",
      operation: "memory_review",
      outcome,
      review_status: row.review_status,
      memory: publicMemory(row),
      credentials_omitted: true,
      raw_body_omitted: true,
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
    return response(replay, "unchanged");
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
      session_ref: identity.sessionRef,
      idempotency_ref: opaqueReference("idemref", idempotencyHash),
      credentials_omitted: true,
      raw_body_omitted: true,
      raw_content_omitted: true,
    },
  });
  await appendRuntimeEvent(client, {
    eventType: `memory.${requestedDecision}`,
    status: "completed",
    taskId: before.task_id,
    agentId: before.agent_id,
    outputSummary: `Human reviewer marked the candidate memory ${requestedDecision}.`,
    rawPayloadHash: requestHash,
  });
  return response(after, "updated");
}

export async function reviewWorkspaceMemory(
  request: Request,
  body: Record<string, unknown>,
  rawMemoryId: unknown,
  rawDecision: unknown,
) {
  const memoryId = identifier(rawMemoryId, "memory_id");
  const requestedDecision = decision(rawDecision);
  const replayKey = idempotencyKey(request.headers);
  rejectMachineCredentials(request.headers);
  validateWriteOrigin(request.headers);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateHumanReviewer(client, request.headers, body.workspace_id);
    return reviewCandidate(client, identity, memoryId, requestedDecision, replayKey);
  });
}
