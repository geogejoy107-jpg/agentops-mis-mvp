import { createHash } from "node:crypto";
import type { PoolClient } from "pg";

import {
  authenticateAgentGateway,
  enforceWorkspaceBinding,
  type AgentGatewayIdentity,
} from "./auth";
import { boundedJsonObject } from "./boundedJson";
import { withPostgresTransaction } from "./db";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, stableHash } from "./ledger";

export type EvidenceRouteResult = Readonly<{
  status: number;
  body: Record<string, unknown>;
}>;

const MAX_BODY_BYTES = 32 * 1024;
const IDENTIFIER = /^[A-Za-z0-9._:-]{1,128}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const RUNTIME_STATUSES = new Set([
  "planned",
  "running",
  "completed",
  "failed",
  "blocked",
  "waiting_approval",
  "unavailable",
]);
const MEMORY_SCOPES = new Set(["task", "project", "org"]);
const MEMORY_TYPES = new Set([
  "policy",
  "sop",
  "decision",
  "commitment",
  "risk",
  "failure_case",
  "project_context",
  "customer_preference",
  "agent_lesson",
  "artifact_summary",
  "loop_record",
]);
const SAFE_SENSITIVE_EVIDENCE_SUFFIXES = [
  "_omitted",
  "_hash",
  "_id",
  "_ids",
  "_ref",
  "_refs",
  "_count",
  "_present",
  "_performed",
  "_stored",
  "_source",
  "_summary",
  "_tokens",
];
const TRUSTED_WORKER_SECRET_BOUNDARY = "trusted_worker_client_v1";
const TRUSTED_WORKER_CREDENTIAL_TRANSPORT = "trusted_worker_client_only";

type RunBinding = {
  run_id: string;
  workspace_id: string;
  task_id: string;
  agent_id: string;
  runtime_type: string;
};

type TaskBinding = {
  task_id: string;
  workspace_id: string;
  owner_agent_id: string | null;
  collaborator_agent_ids: string;
  title: string;
  description: string | null;
  acceptance_criteria: string | null;
  risk_level: string;
};

type RuntimeEventRow = {
  runtime_event_id: string;
  workspace_id: string;
  runtime_connector_id: string | null;
  event_type: string;
  status: string;
  run_id: string | null;
  task_id: string | null;
  agent_id: string | null;
  model_name: string | null;
  latency_ms: number | null;
  prompt_hash: string | null;
  input_summary: string | null;
  output_summary: string | null;
  error_message: string | null;
  raw_payload_hash: string | null;
  created_at: string;
};

type MemoryRow = {
  memory_id: string;
  workspace_id: string;
  scope: string;
  memory_type: string;
  canonical_text: string;
  source_type: string;
  source_ref: string | null;
  project_id: string | null;
  task_id: string | null;
  run_id: string | null;
  agent_id: string | null;
  confidence: number;
  review_status: string;
  owner_user_id: string | null;
  ttl_review_due_at: string | null;
  supersedes_memory_id: string | null;
  access_tags: string;
  created_at: string;
  updated_at: string;
};

type KnowledgeRow = {
  doc_id: string;
  chunk_id: string;
  workspace_id: string;
  access_level: string;
  path: string;
  title: string;
  heading: string;
  heading_path: string;
  source_hash: string;
  rank: number;
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

function optionalIdentifier(value: unknown, field: string) {
  return value === undefined || value === null || value === ""
    ? null
    : identifier(value, field);
}

function boundedInteger(
  value: unknown,
  fallback: number,
  minimum: number,
  maximum: number,
) {
  if (value === undefined || value === null || value === "") return fallback;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new ControlPlaneHttpError(
      400,
      "numeric_value_invalid",
      `Numeric value must be an integer between ${minimum} and ${maximum}.`,
    );
  }
  return parsed;
}

function safeText(value: unknown, maximum: number, fallback = "") {
  const redacted = String(value ?? "")
    .replace(
      /-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----/g,
      "[PRIVATE_KEY_REDACTED]",
    )
    .replace(/(bearer\s+)[a-z0-9._-]+/gi, "$1[REDACTED]")
    .replace(
      /(token|secret|password|api[_-]?key)\s*[:=]\s*['"]?[^'"\s,;]+/gi,
      "$1=[REDACTED]",
    )
    .replace(/github_pat_[A-Za-z0-9_]{20,}/g, "[SECRET_REDACTED]")
    .replace(/\b(?:sk|gh[pousr])[-_][A-Za-z0-9_-]{16,}\b/g, "[SECRET_REDACTED]")
    .replace(
      /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,
      "[JWT_REDACTED]",
    )
    .replace(/\b(?:agtok|agtsess)_[A-Za-z0-9_-]+\b/g, "[AGENT_TOKEN_REF_REDACTED]")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maximum);
  return redacted || fallback;
}

function optionalHash(value: unknown, field: string) {
  if (value === undefined || value === null || value === "") return null;
  const normalized = String(value).trim().toLowerCase();
  if (!SHA256.test(normalized)) {
    throw new ControlPlaneHttpError(
      400,
      `${field}_invalid`,
      `${field} must be a lowercase SHA-256 digest.`,
    );
  }
  return normalized;
}

function assertNoRawEvidence(value: unknown, path = "body", depth = 0): void {
  if (depth > 8) {
    throw new ControlPlaneHttpError(
      400,
      "evidence_depth_exceeded",
      "Evidence metadata nesting exceeds the supported depth.",
    );
  }
  if (Array.isArray(value)) {
    if (value.length > 128) {
      throw new ControlPlaneHttpError(
        400,
        "evidence_array_too_large",
        "Evidence metadata arrays are limited to 128 items.",
      );
    }
    value.forEach((item, index) => assertNoRawEvidence(item, `${path}[${index}]`, depth + 1));
    return;
  }
  if (!value || typeof value !== "object") return;
  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length > 128) {
    throw new ControlPlaneHttpError(
      400,
      "evidence_object_too_large",
      "Evidence metadata objects are limited to 128 fields.",
    );
  }
  for (const [key, item] of entries) {
    const normalized = key.trim().toLowerCase().replaceAll("-", "_");
    const trustedWorkerBoundary = (
      (normalized === "secret_boundary"
        && item === TRUSTED_WORKER_SECRET_BOUNDARY)
      || (normalized === "credential_transport"
        && item === TRUSTED_WORKER_CREDENTIAL_TRANSPORT)
      || (normalized === "model_visible_credentials" && item === false)
      || (normalized === "secrets_in_prompt" && item === false)
      || (normalized === "secrets_in_output" && item === false)
    );
    const sensitive = (
      normalized === "content"
      || normalized === "payload"
      || /(^|_)(raw|prompt|response|transcript|credential|secret|password|api_key|token)(_|$)/.test(
        normalized,
      )
    );
    const safeEvidence = SAFE_SENSITIVE_EVIDENCE_SUFFIXES.some(
      (suffix) => normalized.endsWith(suffix),
    );
    if (sensitive && !safeEvidence && !trustedWorkerBoundary) {
      throw new ControlPlaneHttpError(
        400,
        "raw_evidence_forbidden",
        `Raw or credential-bearing evidence is not accepted at ${path}.${key}.`,
      );
    }
    assertNoRawEvidence(item, `${path}.${key}`, depth + 1);
  }
}

function boundedMetadata(value: unknown) {
  const metadata = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
  assertNoRawEvidence(metadata, "metadata");
  const encoded = JSON.stringify(metadata);
  if (Buffer.byteLength(encoded, "utf8") > 12 * 1024) {
    throw new ControlPlaneHttpError(
      413,
      "metadata_too_large",
      "Evidence metadata exceeds 12288 bytes.",
    );
  }
  return metadata;
}

function stringList(value: unknown, maximum = 32) {
  if (!Array.isArray(value)) return [];
  return [...new Set(
    value
      .slice(0, maximum)
      .map((item) => safeText(item, 80))
      .filter(Boolean),
  )];
}

async function requestBody(request: Request, label: string) {
  const body = await boundedJsonObject(request, {
    maxBytes: MAX_BODY_BYTES,
    label,
  });
  assertNoRawEvidence(body);
  return body;
}

function enforceAgentBinding(
  identity: AgentGatewayIdentity,
  request: Request,
  body?: Record<string, unknown>,
) {
  enforceWorkspaceBinding(identity, {
    header: request.headers.get("x-agentops-workspace-id"),
    body: body?.workspace_id,
  });
  for (const requested of [
    request.headers.get("x-agentops-agent-id"),
    body?.agent_id,
  ]) {
    if (requested && String(requested).trim() !== identity.agentId) {
      throw new ControlPlaneHttpError(
        403,
        "forbidden",
        "Agent credential cannot act as another agent.",
      );
    }
  }
}

function parseCollaborators(value: string) {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

async function requireRunBinding(
  client: PoolClient,
  identity: AgentGatewayIdentity,
  runId: string,
) {
  const result = await client.query<RunBinding>(
    `SELECT run_id,workspace_id,task_id,agent_id,runtime_type
    FROM runs WHERE run_id=$1 FOR SHARE`,
    [runId],
  );
  const run = result.rows[0];
  if (!run) {
    throw new ControlPlaneHttpError(404, "run_not_found", "Run was not found.");
  }
  if (run.workspace_id !== identity.workspaceId || run.agent_id !== identity.agentId) {
    throw new ControlPlaneHttpError(
      403,
      "forbidden",
      "Agent credential is not bound to this run.",
    );
  }
  return run;
}

async function requireTaskBinding(
  client: PoolClient,
  identity: AgentGatewayIdentity,
  taskId: string,
) {
  const result = await client.query<TaskBinding>(
    `SELECT task_id,workspace_id,owner_agent_id,collaborator_agent_ids,
      title,description,acceptance_criteria,risk_level
    FROM tasks WHERE task_id=$1 FOR SHARE`,
    [taskId],
  );
  const task = result.rows[0];
  if (!task) {
    throw new ControlPlaneHttpError(404, "task_not_found", "Task was not found.");
  }
  if (
    task.workspace_id !== identity.workspaceId
    || (
      task.owner_agent_id !== identity.agentId
      && !parseCollaborators(task.collaborator_agent_ids).includes(identity.agentId)
    )
  ) {
    throw new ControlPlaneHttpError(
      403,
      "forbidden",
      "Agent credential is not bound to this task.",
    );
  }
  return task;
}

function runtimeEventPublic(row: RuntimeEventRow) {
  return {
    runtime_event_id: row.runtime_event_id,
    workspace_id: row.workspace_id,
    runtime_connector_id: row.runtime_connector_id,
    event_type: row.event_type,
    status: row.status,
    run_id: row.run_id,
    task_id: row.task_id,
    agent_id: row.agent_id,
    model_name: row.model_name,
    latency_ms: row.latency_ms,
    prompt_hash: row.prompt_hash,
    input_summary: row.input_summary,
    output_summary: row.output_summary,
    error_message: row.error_message,
    raw_payload_hash: row.raw_payload_hash,
    created_at: row.created_at,
    raw_payload_omitted: true,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    token_omitted: true,
  };
}

export async function recordAgentRuntimeEvent(
  request: Request,
): Promise<EvidenceRouteResult> {
  const body = await requestBody(request, "Agent RuntimeEvent");
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(
      client,
      request.headers,
      "runtime_events:write",
    );
    enforceAgentBinding(identity, request, body);
    const runId = identifier(body.run_id, "run_id");
    const run = await requireRunBinding(client, identity, runId);
    const requestedTaskId = optionalIdentifier(body.task_id, "task_id");
    if (requestedTaskId && requestedTaskId !== run.task_id) {
      throw new ControlPlaneHttpError(
        403,
        "forbidden",
        "RuntimeEvent task_id must match the run.",
      );
    }
    const eventType = safeText(
      body.event_type,
      120,
      "agent_worker.adapter_execution_summary",
    );
    if (!/^[A-Za-z0-9._:-]{1,120}$/.test(eventType)) {
      throw new ControlPlaneHttpError(
        400,
        "event_type_invalid",
        "event_type contains unsupported characters.",
      );
    }
    const status = String(body.status || "completed").trim();
    if (!RUNTIME_STATUSES.has(status)) {
      throw new ControlPlaneHttpError(
        400,
        "runtime_event_status_invalid",
        "RuntimeEvent status is invalid.",
      );
    }
    const rawPayloadHash = optionalHash(
      body.raw_payload_hash ?? body.payload_hash,
      "raw_payload_hash",
    ) || stableHash({
      workspace_id: identity.workspaceId,
      run_id: run.run_id,
      task_id: run.task_id,
      agent_id: identity.agentId,
      event_type: eventType,
      status,
      metadata: boundedMetadata(body.metadata),
      raw_payload_omitted: true,
    });
    const promptHash = optionalHash(body.prompt_hash, "prompt_hash");
    const eventId = `rte_gw_${stableHash({
      workspace_id: identity.workspaceId,
      run_id: run.run_id,
      agent_id: identity.agentId,
      event_type: eventType,
      status,
      raw_payload_hash: rawPayloadHash,
    }).slice(0, 20)}`;
    const createdAt = new Date().toISOString();
    const values = {
      runtimeConnectorId: optionalIdentifier(
        body.runtime_connector_id ?? body.connector_id,
        "runtime_connector_id",
      ),
      modelName: safeText(body.model_name ?? body.model, 120) || null,
      latencyMs: body.latency_ms === undefined || body.latency_ms === null
        ? null
        : boundedInteger(body.latency_ms, 0, 0, 86_400_000),
      inputSummary: safeText(body.input_summary, 360) || null,
      outputSummary: safeText(body.output_summary ?? body.summary, 720) || null,
      errorMessage: safeText(body.error_message, 360) || null,
    };
    const insert = await client.query(
      `INSERT INTO runtime_events(
        runtime_event_id,workspace_id,runtime_connector_id,event_type,status,
        run_id,task_id,agent_id,model_name,latency_ms,prompt_hash,input_summary,
        output_summary,error_message,raw_payload_hash,created_at
      ) VALUES(
        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16
      ) ON CONFLICT(runtime_event_id) DO NOTHING`,
      [
        eventId,
        identity.workspaceId,
        values.runtimeConnectorId,
        eventType,
        status,
        run.run_id,
        run.task_id,
        identity.agentId,
        values.modelName,
        values.latencyMs,
        promptHash,
        values.inputSummary,
        values.outputSummary,
        values.errorMessage,
        rawPayloadHash,
        createdAt,
      ],
    );
    const result = await client.query<RuntimeEventRow>(
      `SELECT * FROM runtime_events WHERE runtime_event_id=$1`,
      [eventId],
    );
    const row = result.rows[0];
    if (
      !row
      || row.workspace_id !== identity.workspaceId
      || row.run_id !== run.run_id
      || row.agent_id !== identity.agentId
      || row.raw_payload_hash !== rawPayloadHash
    ) {
      throw new ControlPlaneHttpError(
        409,
        "runtime_event_idempotency_conflict",
        "RuntimeEvent replay does not match the stored event.",
      );
    }
    if (insert.rowCount === 1) {
      await appendAudit(client, {
        workspaceId: identity.workspaceId,
        actorType: "agent",
        actorId: identity.agentId,
        action: "agent_gateway.runtime_event_record",
        entityType: "runtime_events",
        entityId: eventId,
        after: runtimeEventPublic(row),
        metadata: {
          run_id: run.run_id,
          task_id: run.task_id,
          event_type: eventType,
          raw_payload_omitted: true,
          token_omitted: true,
        },
        requestHash: stableHash({ operation: "runtime_event_record", event_id: eventId }),
      });
    }
    return {
      status: insert.rowCount === 1 ? 201 : 200,
      body: {
        provider: "agentops-typescript-postgres",
        operation: "runtime_event_record",
        runtime_event: runtimeEventPublic(row),
        outcome: insert.rowCount === 1 ? "created" : "unchanged",
        workspace_id: identity.workspaceId,
        token_omitted: true,
      },
    };
  });
}

export async function emitAgentAudit(
  request: Request,
): Promise<EvidenceRouteResult> {
  const body = await requestBody(request, "Agent audit");
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(
      client,
      request.headers,
      "audit:write",
    );
    enforceAgentBinding(identity, request, body);
    const runId = optionalIdentifier(body.run_id, "run_id");
    const taskId = optionalIdentifier(body.task_id, "task_id");
    if (runId) {
      const run = await requireRunBinding(client, identity, runId);
      if (taskId && taskId !== run.task_id) {
        throw new ControlPlaneHttpError(
          403,
          "forbidden",
          "Audit task_id must match the run.",
        );
      }
    } else if (taskId) {
      await requireTaskBinding(client, identity, taskId);
    }
    const action = safeText(body.action, 160, "agent_gateway.audit_emit");
    const entityType = safeText(body.entity_type, 80, "agent_gateway");
    const entityId = identifier(
      body.entity_id ?? runId ?? taskId ?? identity.agentId,
      "entity_id",
    );
    const metadata = boundedMetadata(body.metadata);
    const after = body.after && typeof body.after === "object"
      ? boundedMetadata(body.after)
      : { status: "emitted" };
    const requestHash = stableHash({
      workspace_id: identity.workspaceId,
      agent_id: identity.agentId,
      action,
      entity_type: entityType,
      entity_id: entityId,
      run_id: runId,
      task_id: taskId,
      metadata,
      after,
    });
    const receipt = await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "agent",
      actorId: identity.agentId,
      action,
      entityType,
      entityId,
      after,
      metadata: {
        ...metadata,
        ...(runId ? { run_id: runId } : {}),
        ...(taskId ? { task_id: taskId } : {}),
        raw_prompt_omitted: true,
        raw_response_omitted: true,
        token_omitted: true,
      },
      requestHash,
    });
    return {
      status: receipt.outcome === "created" ? 201 : 200,
      body: {
        provider: "agentops-typescript-postgres",
        operation: "audit_emit",
        emitted: true,
        audit_id: receipt.auditId,
        outcome: receipt.outcome,
        entity_type: entityType,
        entity_id: entityId,
        workspace_id: identity.workspaceId,
        token_omitted: true,
      },
    };
  });
}

function memoryPublic(row: MemoryRow) {
  let accessTags: string[] = [];
  try {
    const parsed: unknown = JSON.parse(row.access_tags);
    accessTags = Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    accessTags = [];
  }
  return {
    memory_id: row.memory_id,
    workspace_id: row.workspace_id,
    scope: row.scope,
    memory_type: row.memory_type,
    canonical_text: row.canonical_text,
    source_type: row.source_type,
    source_ref: row.source_ref,
    project_id: row.project_id,
    task_id: row.task_id,
    run_id: row.run_id,
    agent_id: row.agent_id,
    confidence: row.confidence,
    review_status: row.review_status,
    owner_user_id: row.owner_user_id,
    ttl_review_due_at: row.ttl_review_due_at,
    supersedes_memory_id: row.supersedes_memory_id,
    access_tags: accessTags,
    created_at: row.created_at,
    updated_at: row.updated_at,
    raw_source_omitted: true,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    token_omitted: true,
  };
}

export async function proposeAgentMemory(
  request: Request,
): Promise<EvidenceRouteResult> {
  const body = await requestBody(request, "Agent Memory proposal");
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(
      client,
      request.headers,
      "memories:propose",
    );
    enforceAgentBinding(identity, request, body);
    const runId = optionalIdentifier(body.run_id, "run_id");
    const taskId = optionalIdentifier(body.task_id, "task_id");
    let boundTaskId = taskId;
    if (runId) {
      const run = await requireRunBinding(client, identity, runId);
      if (taskId && taskId !== run.task_id) {
        throw new ControlPlaneHttpError(
          403,
          "forbidden",
          "Memory task_id must match the run.",
        );
      }
      boundTaskId = run.task_id;
    } else if (taskId) {
      await requireTaskBinding(client, identity, taskId);
    } else {
      throw new ControlPlaneHttpError(
        400,
        "memory_binding_required",
        "A task_id or run_id is required for an agent Memory proposal.",
      );
    }
    const canonicalText = safeText(
      body.canonical_text ?? body.text,
      360,
    );
    if (!canonicalText) {
      throw new ControlPlaneHttpError(
        400,
        "canonical_text_required",
        "canonical_text is required.",
      );
    }
    const scope = String(body.scope || "project").trim();
    const memoryType = String(body.memory_type || "artifact_summary").trim();
    if (!MEMORY_SCOPES.has(scope) || !MEMORY_TYPES.has(memoryType)) {
      throw new ControlPlaneHttpError(
        400,
        "memory_classification_invalid",
        "Memory scope or type is invalid.",
      );
    }
    const confidenceInput = Number(body.confidence ?? 0.72);
    if (!Number.isFinite(confidenceInput)) {
      throw new ControlPlaneHttpError(
        400,
        "memory_confidence_invalid",
        "Memory confidence must be numeric.",
      );
    }
    const confidence = Math.max(0, Math.min(confidenceInput, 1));
    const sourceRef = safeText(body.source_ref ?? runId ?? boundTaskId, 200);
    const projectId = optionalIdentifier(
      body.project_id ?? "agentops-mis",
      "project_id",
    );
    const accessTags = stringList(
      body.access_tags ?? ["worker-loop", "review"],
    );
    const requestHash = stableHash({
      workspace_id: identity.workspaceId,
      agent_id: identity.agentId,
      task_id: boundTaskId,
      run_id: runId,
      scope,
      memory_type: memoryType,
      canonical_text: canonicalText,
      source_ref: sourceRef,
      project_id: projectId,
      confidence,
      access_tags: accessTags,
    });
    const memoryId = optionalIdentifier(body.memory_id, "memory_id")
      || `mem_gw_${requestHash.slice(0, 20)}`;
    const now = new Date().toISOString();
    const reviewDue = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString();
    const insert = await client.query(
      `INSERT INTO memories(
        memory_id,workspace_id,scope,memory_type,canonical_text,source_type,
        source_ref,project_id,task_id,run_id,agent_id,confidence,review_status,
        owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,
        created_at,updated_at
      ) VALUES(
        $1,$2,$3,$4,$5,'run_log',$6,$7,$8,$9,$10,$11,'candidate',
        NULL,$12,NULL,$13,$14,$14
      ) ON CONFLICT(memory_id) DO NOTHING`,
      [
        memoryId,
        identity.workspaceId,
        scope,
        memoryType,
        canonicalText,
        sourceRef,
        projectId,
        boundTaskId,
        runId,
        identity.agentId,
        confidence,
        reviewDue,
        JSON.stringify(accessTags),
        now,
      ],
    );
    const result = await client.query<MemoryRow>(
      `SELECT * FROM memories WHERE memory_id=$1`,
      [memoryId],
    );
    const memory = result.rows[0];
    if (
      !memory
      || memory.workspace_id !== identity.workspaceId
      || memory.agent_id !== identity.agentId
      || memory.task_id !== boundTaskId
      || memory.run_id !== runId
      || memory.canonical_text !== canonicalText
    ) {
      throw new ControlPlaneHttpError(
        409,
        "memory_idempotency_conflict",
        "Memory replay does not match the stored candidate.",
      );
    }
    if (insert.rowCount === 1) {
      await appendAudit(client, {
        workspaceId: identity.workspaceId,
        actorType: "agent",
        actorId: identity.agentId,
        action: "agent_gateway.memory_propose",
        entityType: "memories",
        entityId: memoryId,
        after: memoryPublic(memory),
        metadata: {
          task_id: boundTaskId,
          run_id: runId,
          review_status: "candidate",
          raw_source_omitted: true,
          token_omitted: true,
        },
        requestHash,
      });
    }
    return {
      status: insert.rowCount === 1 ? 201 : 200,
      body: {
        provider: "agentops-typescript-postgres",
        operation: "memory_propose",
        memory: memoryPublic(memory),
        outcome: insert.rowCount === 1 ? "created" : "unchanged",
        token_omitted: true,
      },
    };
  });
}

const GOVERNED_KNOWLEDGE_BASELINE = Object.freeze([
  {
    docId: "kdoc_global_gateway_cli_v1",
    chunkId: "kchunk_global_gateway_cli_v1",
    path: "docs/AGENT_GATEWAY_CLI_SPEC.md",
    title: "Agent Gateway CLI contract",
    category: "gateway",
    summary:
      "Agent Gateway worker task pull, claim, plan, run heartbeat, tool, evaluation, artifact, approval, memory, runtime event and audit evidence contract.",
  },
  {
    docId: "kdoc_global_actor_model_v1",
    chunkId: "kchunk_global_actor_model_v1",
    path: "docs/PRODUCT_USAGE_AND_ACTOR_MODEL.md",
    title: "Product usage and actor model",
    category: "product",
    summary:
      "Solo owner, team member, human approver and AI digital employee authority boundaries for governed workspaces.",
  },
  {
    docId: "kdoc_global_method_block_v1",
    chunkId: "kchunk_global_method_block_v1",
    path: "AGENT_WORKFLOW.md",
    title: "Agent work method block",
    category: "method",
    summary:
      "READ PLAN RETRIEVE COMPARE EXECUTE VERIFY RECORD with bounded evidence, rollback planning and human approval for external writes.",
  },
  {
    docId: "kdoc_global_runtime_loop_v1",
    chunkId: "kchunk_global_runtime_loop_v1",
    path: "docs/HERMES_OPENCLAW_LOOP_RUNBOOK.md",
    title: "Hermes and OpenClaw governed loop",
    category: "runtime",
    summary:
      "Hermes OpenClaw loop uses verified Agent Plan, MIS ledger, plan evidence manifest, runtime event, evaluation, artifact and pending customer delivery approval.",
  },
  {
    docId: "kdoc_global_pixel_map_v1",
    chunkId: "kchunk_global_pixel_map_v1",
    path: "docs/PIXEL_OPERATING_MAP_SPEC.md",
    title: "Pixel Office operating map",
    category: "product",
    summary:
      "Pixel Office zones route users to formal MIS task hall, run inspector, approval queue and operations evidence views.",
  },
] as const);

function baselineSourceHash(item: (typeof GOVERNED_KNOWLEDGE_BASELINE)[number]) {
  return createHash("sha256")
    .update(JSON.stringify({
      contract: "governed_knowledge_baseline_v1",
      path: item.path,
      title: item.title,
      category: item.category,
      summary: item.summary,
    }))
    .digest("hex");
}

export async function indexGovernedKnowledge(
  request: Request,
): Promise<EvidenceRouteResult> {
  const body = await requestBody(request, "Governed Knowledge index");
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(
      client,
      request.headers,
      "knowledge:write",
    );
    enforceAgentBinding(identity, request, body);
    let changed = 0;
    const now = new Date().toISOString();
    for (const item of GOVERNED_KNOWLEDGE_BASELINE) {
      const existing = await client.query<{
        workspace_id: string;
        source_hash: string;
      }>(
        `SELECT workspace_id,source_hash
        FROM knowledge_documents WHERE doc_id=$1 FOR UPDATE`,
        [item.docId],
      );
      if (
        existing.rows[0]
        && existing.rows[0].workspace_id !== "global"
      ) {
        throw new ControlPlaneHttpError(
          409,
          "knowledge_baseline_identity_conflict",
          "Governed Knowledge baseline identity is already tenant-owned.",
        );
      }
      const sourceHash = baselineSourceHash(item);
      if (existing.rows[0]?.source_hash !== sourceHash) changed += 1;
      await client.query(
        `INSERT INTO knowledge_documents(
          doc_id,workspace_id,project_id,access_level,path,title,category,scope,
          source_hash,content_summary,indexed_at,updated_at
        ) VALUES(
          $1,'global','agentops-mis','internal',$2,$3,$4,'project',$5,$6,$7,$7
        ) ON CONFLICT(doc_id) DO UPDATE SET
          project_id=EXCLUDED.project_id,
          access_level=EXCLUDED.access_level,
          path=EXCLUDED.path,
          title=EXCLUDED.title,
          category=EXCLUDED.category,
          scope=EXCLUDED.scope,
          source_hash=EXCLUDED.source_hash,
          content_summary=EXCLUDED.content_summary,
          indexed_at=EXCLUDED.indexed_at,
          updated_at=EXCLUDED.updated_at`,
        [
          item.docId,
          item.path,
          item.title,
          item.category,
          sourceHash,
          item.summary,
          now,
        ],
      );
      await client.query(
        `INSERT INTO knowledge_chunks(
          chunk_id,doc_id,workspace_id,project_id,access_level,path,title,
          heading,heading_path,heading_level,chunk_index,source_hash,
          content_summary,indexed_at,updated_at
        ) VALUES(
          $1,$2,'global','agentops-mis','internal',$3,$4,$4,$4,1,1,$5,$6,$7,$7
        ) ON CONFLICT(chunk_id) DO UPDATE SET
          doc_id=EXCLUDED.doc_id,
          workspace_id=EXCLUDED.workspace_id,
          project_id=EXCLUDED.project_id,
          access_level=EXCLUDED.access_level,
          path=EXCLUDED.path,
          title=EXCLUDED.title,
          heading=EXCLUDED.heading,
          heading_path=EXCLUDED.heading_path,
          heading_level=EXCLUDED.heading_level,
          chunk_index=EXCLUDED.chunk_index,
          source_hash=EXCLUDED.source_hash,
          content_summary=EXCLUDED.content_summary,
          indexed_at=EXCLUDED.indexed_at,
          updated_at=EXCLUDED.updated_at`,
        [
          item.chunkId,
          item.docId,
          item.path,
          item.title,
          sourceHash,
          item.summary,
          now,
        ],
      );
    }
    const requestHash = stableHash({
      operation: "governed_knowledge_index",
      contract: "governed_knowledge_baseline_v1",
    });
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "agent",
      actorId: identity.agentId,
      action: "agent_gateway.knowledge_index",
      entityType: "knowledge_documents",
      entityId: "governed_knowledge_baseline_v1",
      after: {
        indexed: GOVERNED_KNOWLEDGE_BASELINE.length,
        changed,
        raw_content_omitted: true,
      },
      metadata: {
        rebuild_requested: body.rebuild === true,
        destructive_rebuild_performed: false,
        raw_content_omitted: true,
        token_omitted: true,
      },
      requestHash,
    });
    return {
      status: 200,
      body: {
        provider: "agentops-typescript-postgres",
        operation: "knowledge_index",
        status: changed > 0 ? "updated" : "current",
        indexed: GOVERNED_KNOWLEDGE_BASELINE.length,
        changed,
        chunks_indexed: GOVERNED_KNOWLEDGE_BASELINE.length,
        chunks_changed: changed,
        deleted: 0,
        incremental_noop: changed === 0,
        heading_aware_chunks: true,
        postgres_full_text_search: true,
        destructive_rebuild_performed: false,
        raw_content_omitted: true,
        token_omitted: true,
      },
    };
  });
}

function knowledgeQueryTerms(value: string) {
  const extracted = value
    .toLowerCase()
    .match(/[a-z0-9_]{2,48}/g) || [];
  return [...new Set([
    ...extracted,
    "read",
    "plan",
    "retrieve",
    "compare",
    "execute",
    "verify",
    "record",
  ])].slice(0, 32);
}

function knowledgeResult(row: KnowledgeRow, queryHash: string) {
  return {
    retrieval_id: `krv_${stableHash({
      doc_id: row.doc_id,
      chunk_id: row.chunk_id,
      query_hash: queryHash,
    }).slice(0, 20)}`,
    retrieval_granularity: "heading_chunk",
    doc_id: row.doc_id,
    chunk_id: row.chunk_id,
    workspace_id: row.workspace_id,
    access_level: row.access_level,
    path: row.path,
    title: row.title,
    category: row.path.startsWith("docs/") ? "docs" : "root",
    scope: "project",
    chunk_heading: row.heading,
    chunk_heading_path: row.heading_path,
    source_hash: row.source_hash,
    rank: Number(row.rank || 0),
    snippet_omitted: true,
    content_summary_omitted: true,
    raw_content_omitted: true,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    token_omitted: true,
  };
}

export async function getKnowledgeEvidencePacket(
  request: Request,
): Promise<EvidenceRouteResult> {
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(
      client,
      request.headers,
      "knowledge:read",
    );
    const url = new URL(request.url);
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
      body: url.searchParams.get("workspace_id"),
    });
    const headerAgent = request.headers.get("x-agentops-agent-id");
    if (headerAgent && headerAgent.trim() !== identity.agentId) {
      throw new ControlPlaneHttpError(
        403,
        "forbidden",
        "Agent credential cannot retrieve evidence as another agent.",
      );
    }
    const taskId = optionalIdentifier(url.searchParams.get("task_id"), "task_id");
    const adapter = safeText(
      url.searchParams.get("adapter") || url.searchParams.get("runtime_type"),
      40,
      "worker",
    );
    const task = taskId
      ? await requireTaskBinding(client, identity, taskId)
      : null;
    const explicitQuery = safeText(
      url.searchParams.get("q") || url.searchParams.get("query"),
      240,
    );
    const query = safeText(
      task
        ? [
          task.title,
          task.description,
          task.acceptance_criteria,
          task.risk_level,
          adapter,
          "READ PLAN RETRIEVE COMPARE EXECUTE VERIFY RECORD",
        ].filter(Boolean).join(" ")
        : explicitQuery || "READ PLAN RETRIEVE COMPARE EXECUTE VERIFY RECORD",
      640,
    );
    const queryHash = stableHash(query);
    const terms = knowledgeQueryTerms(query);
    const tsQuery = terms.join(" | ");
    const limit = boundedInteger(url.searchParams.get("limit"), 5, 1, 10);
    let rows = (await client.query<KnowledgeRow>(
      `SELECT document.doc_id,chunk.chunk_id,chunk.workspace_id,
        chunk.access_level,chunk.path,chunk.title,chunk.heading,
        chunk.heading_path,chunk.source_hash,
        ts_rank_cd(chunk.search_document,to_tsquery('simple'::regconfig,$2)) AS rank
      FROM knowledge_chunks chunk
      JOIN knowledge_documents document
        ON document.doc_id=chunk.doc_id
        AND document.workspace_id=chunk.workspace_id
        AND document.path=chunk.path
        AND document.source_hash=chunk.source_hash
      WHERE chunk.workspace_id IN ('global',$1)
        AND chunk.search_document @@ to_tsquery('simple'::regconfig,$2)
      ORDER BY rank DESC,chunk.updated_at DESC,chunk.chunk_id
      LIMIT $3`,
      [identity.workspaceId, tsQuery, limit],
    )).rows;
    let fallbackUsed = false;
    if (rows.length === 0) {
      fallbackUsed = true;
      rows = (await client.query<KnowledgeRow>(
        `SELECT document.doc_id,chunk.chunk_id,chunk.workspace_id,
          chunk.access_level,chunk.path,chunk.title,chunk.heading,
          chunk.heading_path,chunk.source_hash,0::real AS rank
        FROM knowledge_chunks chunk
        JOIN knowledge_documents document
          ON document.doc_id=chunk.doc_id
          AND document.workspace_id=chunk.workspace_id
          AND document.path=chunk.path
          AND document.source_hash=chunk.source_hash
        WHERE chunk.workspace_id IN ('global',$1)
        ORDER BY (chunk.workspace_id=$1) DESC,chunk.updated_at DESC,chunk.chunk_id
        LIMIT $2`,
        [identity.workspaceId, limit],
      )).rows;
    }
    const results = rows.map((row) => knowledgeResult(row, queryHash));
    const counts = await client.query<{
      knowledge_documents: string;
      knowledge_chunks: string;
      workspace_documents: string;
      workspace_chunks: string;
    }>(
      `SELECT
        (SELECT COUNT(*) FROM knowledge_documents)::text AS knowledge_documents,
        (SELECT COUNT(*) FROM knowledge_chunks)::text AS knowledge_chunks,
        (SELECT COUNT(*) FROM knowledge_documents
          WHERE workspace_id IN ('global',$1))::text AS workspace_documents,
        (SELECT COUNT(*) FROM knowledge_chunks
          WHERE workspace_id IN ('global',$1))::text AS workspace_chunks`,
      [identity.workspaceId],
    );
    const count = counts.rows[0];
    const status = results.length > 0 ? "ready" : "attention";
    const metrics = {
      queries: 1,
      hits_at_5: results.length > 0 ? 1 : 0,
      recall_at_5: results.length > 0 ? 1 : 0,
      mrr: results.length > 0 ? 1 : 0,
      fallback_queries: fallbackUsed ? 1 : 0,
      heading_chunk_queries: 1,
      token_omitted: true,
    };
    return {
      status: 200,
      body: {
        provider: "agentops-typescript-postgres",
        operation: "knowledge_retrieval_evidence_packet",
        version: "v1",
        status,
        workspace_id: identity.workspaceId,
        task_context: {
          task_id: task?.task_id || null,
          task_found: Boolean(task),
          query_source: task ? "task_id" : "explicit_query",
          source_fields: task
            ? ["title", "description", "acceptance_criteria", "risk_level"]
            : [],
          task_text_omitted: true,
          token_omitted: true,
        },
        query_hash: queryHash,
        query_omitted: true,
        counts: {
          knowledge_documents: Number(count?.knowledge_documents || 0),
          knowledge_chunks: Number(count?.knowledge_chunks || 0),
          knowledge_chunk_fts_rows: Number(count?.knowledge_chunks || 0),
          workspace_documents: Number(count?.workspace_documents || 0),
          workspace_chunks: Number(count?.workspace_chunks || 0),
        },
        metrics,
        primary_search: {
          operation: "knowledge_search",
          query_hash: queryHash,
          query_omitted: true,
          count: results.length,
          search_quality: {
            result_quality: status,
            fallback_used: fallbackUsed,
            heading_aware_chunks: true,
            content_body_searched: false,
            postgres_full_text_search: true,
          },
          visibility: {
            bound_visibility_enforced: true,
            workspace_id: identity.workspaceId,
            visible_workspaces: ["global", identity.workspaceId],
            access_levels: ["internal", "private"],
          },
          results,
          snippet_omitted: true,
          content_summary_omitted: true,
          raw_content_omitted: true,
          raw_prompt_omitted: true,
          raw_response_omitted: true,
          token_omitted: true,
        },
        baseline: [],
        safety: {
          read_only_evidence: true,
          task_mutated: false,
          run_mutated: false,
          tool_mutated: false,
          live_execution_performed: false,
          external_network: false,
          raw_prompt_omitted: true,
          raw_response_omitted: true,
          raw_content_omitted: true,
          snippet_omitted: true,
          token_omitted: true,
        },
        token_omitted: true,
        live_execution_performed: false,
      },
    };
  });
}
