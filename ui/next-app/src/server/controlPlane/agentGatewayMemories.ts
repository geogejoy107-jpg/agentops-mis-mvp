import type { PoolClient } from "pg";

import { authenticateAgentGateway, enforceWorkspaceBinding } from "./auth";
import { withPostgresTransaction } from "./db";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, appendRuntimeEvent, pythonFloat, stableHash } from "./ledger";

const MEMORY_SCOPES = new Set(["task", "project", "org"]);
const MEMORY_TYPES = new Set([
  "policy", "sop", "decision", "commitment", "risk", "failure_case", "project_context",
  "customer_preference", "agent_lesson", "artifact_summary",
]);
const SOURCE_TYPES = new Set(["chat", "email", "meeting", "github", "notion", "run_log", "manual"]);
const MAX_BODY_BYTES = 64 * 1024;

type TaskRow = {
  task_id: string;
  workspace_id: string;
  owner_agent_id: string | null;
  collaborator_agent_ids: string;
};

type RunRow = {
  run_id: string;
  workspace_id: string;
  task_id: string;
  agent_id: string;
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

function text(value: unknown, limit: number) {
  return String(value ?? "")
    .replace(/-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----/g, "[PRIVATE_KEY_REDACTED]")
    .replace(/(bearer\s+)[a-z0-9._-]+/gi, "$1[REDACTED]")
    .replace(/(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;]+/gi, "$1=[REDACTED]")
    .replace(/(?<![A-Za-z0-9])(?:sk|gh[pousr])[-_][A-Za-z0-9_-]{16,}/g, "[SECRET_REDACTED]")
    .replace(/github_pat_[A-Za-z0-9_]{20,}/g, "[SECRET_REDACTED]")
    .replace(/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, "[JWT_REDACTED]")
    .replace(/\b(?:sk-[a-z0-9._-]+|ntn_[a-z0-9._-]+)\b/gi, "[SECRET_REDACTED]")
    .replace(/\b(?:agtok|agtsess)_[A-Za-z0-9_-]+\b/g, "[AGENT_TOKEN_REF_REDACTED]")
    .replace(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g, "[EMAIL_REDACTED]")
    .replace(/(?<![\w])(?:\+\d{1,3}[\s.-]*)?(?:\(?\d{2,4}\)?[\s.-]+){2,4}\d{2,4}(?![\w])/g, "[PHONE_REDACTED]")
    .replace(/(?<![\w])\+?\d{10,15}(?![\w])/g, "[PHONE_REDACTED]")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, limit);
}

function identifier(value: unknown, field: string) {
  const normalized = String(value ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(normalized)) {
    throw new ControlPlaneHttpError(400, `${field}_invalid`, `${field} must use 1-128 safe identifier characters.`);
  }
  return normalized;
}

function optionalIdentifier(value: unknown, field: string) {
  return value === undefined || value === null || value === "" ? null : identifier(value, field);
}

function choice(value: unknown, allowed: Set<string>, fallback: string) {
  const normalized = String(value ?? "").trim().toLowerCase();
  return allowed.has(normalized) ? normalized : fallback;
}

function memoryScope(value: unknown, fallback: string) {
  if (value === undefined || value === null || value === "") return fallback;
  const normalized = String(value).trim().toLowerCase();
  if (!MEMORY_SCOPES.has(normalized)) {
    throw new ControlPlaneHttpError(400, "memory_scope_invalid", "scope must be task, project, or org.");
  }
  return normalized;
}

function futureIso(value: unknown, fallback: Date) {
  if (value === undefined || value === null || value === "") return fallback.toISOString();
  const timestamp = Date.parse(String(value));
  if (!Number.isFinite(timestamp) || timestamp <= Date.now()) {
    throw new ControlPlaneHttpError(400, "ttl_review_due_at_invalid", "ttl_review_due_at must be a future ISO-8601 timestamp.");
  }
  return new Date(timestamp).toISOString();
}

function collaborators(task: TaskRow) {
  try {
    const parsed = JSON.parse(task.collaborator_agent_ids || "[]");
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function accessTags(value: unknown) {
  if (value === undefined || value === null || value === "") return ["agent-gateway", "review"];
  if (!Array.isArray(value)) throw new ControlPlaneHttpError(400, "access_tags_invalid", "access_tags must be a list.");
  return [...new Set(value.slice(0, 24).map((item) => text(item, 80)).filter(Boolean))];
}

function confidence(value: unknown) {
  const parsed = Number(value ?? 0.72);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
    throw new ControlPlaneHttpError(400, "confidence_invalid", "confidence must be between 0 and 1.");
  }
  return parsed;
}

async function bodyObject(request: Request) {
  const declaredLength = request.headers.get("content-length");
  if (declaredLength && (!/^\d+$/.test(declaredLength) || Number(declaredLength) > MAX_BODY_BYTES)) {
    throw new ControlPlaneHttpError(413, "request_too_large", "Memory proposal body exceeds 64 KiB.");
  }
  const raw = await request.text();
  if (Buffer.byteLength(raw, "utf8") > MAX_BODY_BYTES) {
    throw new ControlPlaneHttpError(413, "request_too_large", "Memory proposal body exceeds 64 KiB.");
  }
  let body: Record<string, unknown>;
  try {
    body = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  if (!body || Array.isArray(body) || typeof body !== "object") {
    throw new ControlPlaneHttpError(400, "invalid_json", "A JSON object is required.");
  }
  return body;
}

function sameMemory(left: MemoryRow, right: MemoryRow) {
  const fields: Array<keyof MemoryRow> = [
    "workspace_id", "scope", "memory_type", "canonical_text", "source_type", "source_ref", "project_id",
    "task_id", "agent_id", "confidence", "review_status", "owner_user_id", "ttl_review_due_at",
    "supersedes_memory_id", "access_tags",
  ];
  return fields.every((field) => String(left[field] ?? "") === String(right[field] ?? ""));
}

function memorySnapshot(row: MemoryRow) {
  return { ...row, confidence: pythonFloat(Number(row.confidence)) };
}

function response(row: MemoryRow, outcome: "created" | "unchanged") {
  return {
    status: outcome === "created" ? 201 : 200,
    body: {
      ok: true,
      provider: "agentops-memory-candidate",
      control_plane: "typescript_postgres",
      operation: "memory_propose",
      outcome,
      memory: row,
      token_omitted: true,
    },
  };
}

async function lockTaskAndRun(
  client: PoolClient,
  workspaceId: string,
  agentId: string,
  body: Record<string, unknown>,
) {
  const requestedRunId = optionalIdentifier(body.run_id, "run_id");
  let taskId = optionalIdentifier(body.task_id, "task_id");
  if (requestedRunId) {
    const candidateResult = await client.query<Pick<RunRow, "task_id" | "agent_id">>(
      "SELECT task_id,agent_id FROM runs WHERE run_id=$1 AND workspace_id=$2",
      [requestedRunId, workspaceId],
    );
    const candidate = candidateResult.rows[0];
    if (!candidate) throw new ControlPlaneHttpError(404, "run_not_found", "Run was not found in the credential workspace.");
    if (candidate.agent_id !== agentId) throw new ControlPlaneHttpError(403, "forbidden", "Run belongs to another agent.");
    if (taskId && taskId !== candidate.task_id) {
      throw new ControlPlaneHttpError(403, "forbidden", "Memory task_id must match the target run.");
    }
    taskId = candidate.task_id;
  }
  let task: TaskRow | null = null;
  if (taskId) {
    const taskResult = await client.query<TaskRow>(
      "SELECT task_id,workspace_id,owner_agent_id,collaborator_agent_ids FROM tasks WHERE task_id=$1 AND workspace_id=$2 FOR UPDATE",
      [taskId, workspaceId],
    );
    task = taskResult.rows[0] || null;
    if (!task) throw new ControlPlaneHttpError(404, "task_not_found", "Task was not found in the credential workspace.");
    if (task.owner_agent_id !== agentId && !collaborators(task).includes(agentId)) {
      throw new ControlPlaneHttpError(403, "forbidden", "Task is not assigned to this agent.");
    }
  }
  let run: RunRow | null = null;
  if (requestedRunId) {
    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-run:${requestedRunId}`]);
    const runResult = await client.query<RunRow>(
      "SELECT run_id,workspace_id,task_id,agent_id FROM runs WHERE run_id=$1 AND workspace_id=$2 FOR UPDATE",
      [requestedRunId, workspaceId],
    );
    run = runResult.rows[0] || null;
    if (!run || run.task_id !== taskId || run.agent_id !== agentId) {
      throw new ControlPlaneHttpError(409, "run_immutable_binding_conflict", "Run binding changed while memory proposal waited.");
    }
  }
  return { taskId, runId: requestedRunId, task, run };
}

export async function proposeAgentGatewayMemory(request: Request) {
  const body = await bodyObject(request);
  return withPostgresTransaction(async (client) => {
    const identity = await authenticateAgentGateway(client, request.headers, "memories:propose");
    enforceWorkspaceBinding(identity, {
      header: request.headers.get("x-agentops-workspace-id"),
      body: body.workspace_id,
    });
    if (body.agent_id !== undefined && text(body.agent_id, 128) !== identity.agentId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Agent credential cannot propose another agent's memory.");
    }
    if (body.owner_user_id !== undefined && body.owner_user_id !== null && body.owner_user_id !== "") {
      throw new ControlPlaneHttpError(403, "memory_owner_human_assignment_required", "Agent credentials cannot assign a human memory owner.");
    }
    if (body.review_status !== undefined && String(body.review_status).trim().toLowerCase() !== "candidate") {
      throw new ControlPlaneHttpError(403, "memory_review_human_required", "Agent credentials can only propose candidate memories.");
    }

    const canonicalText = text(body.canonical_text ?? body.text, 360);
    if (!canonicalText) throw new ControlPlaneHttpError(400, "canonical_text_required", "canonical_text is required.");
    const binding = await lockTaskAndRun(client, identity.workspaceId, identity.agentId, body);
    const generatedMemoryId = `mem_gw_${stableHash([
      identity.workspaceId,
      identity.agentId,
      binding.taskId || "project",
      binding.runId || "no-run",
      canonicalText,
    ]).slice(0, 16)}`;
    const memoryId = body.memory_id ? identifier(body.memory_id, "memory_id") : generatedMemoryId;
    if (memoryId !== generatedMemoryId) {
      throw new ControlPlaneHttpError(409, "memory_id_unavailable", "memory_id is unavailable for this proposal.");
    }
    const supersedesMemoryId = optionalIdentifier(body.supersedes_memory_id, "supersedes_memory_id");
    if (supersedesMemoryId === memoryId) {
      throw new ControlPlaneHttpError(400, "supersedes_memory_id_invalid", "A memory cannot supersede itself.");
    }
    if (supersedesMemoryId) {
      const superseded = await client.query(
        "SELECT 1 FROM memories WHERE memory_id=$1 AND workspace_id=$2 FOR SHARE",
        [supersedesMemoryId, identity.workspaceId],
      );
      if (!superseded.rowCount) {
        throw new ControlPlaneHttpError(404, "superseded_memory_not_found", "Superseded memory was not found in the credential workspace.");
      }
    }

    await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-memory:${memoryId}`]);
    const existingResult = await client.query<MemoryRow>(
      "SELECT * FROM memories WHERE memory_id=$1 AND workspace_id=$2 FOR UPDATE",
      [memoryId, identity.workspaceId],
    );
    const existing = existingResult.rows[0];
    const now = new Date();
    const resolvedScope = body.scope === undefined && existing
      ? existing.scope
      : memoryScope(body.scope, binding.taskId ? "task" : "project");
    if (resolvedScope === "task" && !binding.taskId) {
      throw new ControlPlaneHttpError(
        400,
        "memory_task_id_required",
        "Task-scoped memory candidates require a task_id or a bound run_id.",
      );
    }
    const candidate: MemoryRow = {
      memory_id: memoryId,
      workspace_id: identity.workspaceId,
      scope: resolvedScope,
      memory_type: body.memory_type === undefined && existing ? existing.memory_type : choice(body.memory_type, MEMORY_TYPES, "artifact_summary"),
      canonical_text: canonicalText,
      source_type: body.source_type === undefined && existing ? existing.source_type : choice(body.source_type, SOURCE_TYPES, "run_log"),
      source_ref: body.source_ref === undefined && existing ? existing.source_ref : text(body.source_ref || binding.runId || "agent-gateway", 200) || null,
      project_id: body.project_id === undefined && existing ? existing.project_id : optionalIdentifier(body.project_id, "project_id"),
      task_id: binding.taskId,
      agent_id: identity.agentId,
      confidence: body.confidence === undefined && existing ? Number(existing.confidence) : confidence(body.confidence),
      review_status: "candidate",
      owner_user_id: null,
      ttl_review_due_at: body.ttl_review_due_at === undefined && existing
        ? existing.ttl_review_due_at
        : futureIso(body.ttl_review_due_at, new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000)),
      supersedes_memory_id: supersedesMemoryId,
      access_tags: body.access_tags === undefined && existing
        ? existing.access_tags
        : JSON.stringify(accessTags(body.access_tags)),
      created_at: existing?.created_at || now.toISOString(),
      updated_at: existing?.updated_at || now.toISOString(),
    };
    if (existing) {
      if (existing.review_status !== "candidate") {
        throw new ControlPlaneHttpError(403, "memory_review_human_required", "Agent credentials cannot modify a reviewed memory.");
      }
      if (!sameMemory(existing, candidate)) {
        throw new ControlPlaneHttpError(409, "memory_immutable_conflict", "memory_id is immutable; create a new candidate.");
      }
      return response(existing, "unchanged");
    }

    const insertResult = await client.query<MemoryRow>(
      `INSERT INTO memories(
        memory_id,workspace_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,
        confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at
      ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'candidate',NULL,$12,$13,$14,$15,$16)
      ON CONFLICT (memory_id) DO NOTHING RETURNING *`,
      [candidate.memory_id, candidate.workspace_id, candidate.scope, candidate.memory_type, candidate.canonical_text,
        candidate.source_type, candidate.source_ref, candidate.project_id, candidate.task_id, candidate.agent_id,
        candidate.confidence, candidate.ttl_review_due_at, candidate.supersedes_memory_id, candidate.access_tags,
        candidate.created_at, candidate.updated_at],
    );
    const memory = insertResult.rows[0];
    if (!memory) throw new ControlPlaneHttpError(409, "memory_id_unavailable", "memory_id is unavailable in this workspace.");
    await appendRuntimeEvent(client, {
      eventType: "memory.propose",
      status: "completed",
      runId: binding.runId,
      taskId: binding.taskId,
      agentId: identity.agentId,
      outputSummary: memory.canonical_text,
    });
    await appendAudit(client, {
      workspaceId: identity.workspaceId,
      actorType: "agent",
      actorId: identity.agentId,
      action: "agent_gateway.memory_candidate",
      entityType: "memories",
      entityId: memoryId,
      after: memorySnapshot(memory),
      metadata: {
        workspace_id: identity.workspaceId,
        run_id: binding.runId,
        task_id: binding.taskId,
        raw_omitted: true,
      },
    });
    return response(memory, "created");
  });
}
