import { createHash, randomUUID } from "node:crypto";
import type { PoolClient } from "pg";

type PythonFloat = { __agentops_python_float__: number };
type JsonValue =
  | null
  | boolean
  | number
  | string
  | PythonFloat
  | JsonValue[]
  | { [key: string]: JsonValue };

export function pythonFloat(value: number): PythonFloat {
  return { __agentops_python_float__: value };
}

function canonicalValue(value: unknown): JsonValue {
  if (
    value === null
    || typeof value === "boolean"
    || typeof value === "number"
    || typeof value === "string"
  ) {
    return value;
  }
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([, item]) => item !== undefined)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonicalValue(item)]),
    );
  }
  return String(value);
}

function pythonJson(value: JsonValue): string {
  if (Array.isArray(value)) return `[${value.map(pythonJson).join(", ")}]`;
  if (value && typeof value === "object") {
    if ("__agentops_python_float__" in value) {
      const floatValue = value.__agentops_python_float__;
      return Number.isInteger(floatValue) ? `${floatValue}.0` : String(floatValue);
    }
    return `{${Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => `${JSON.stringify(key)}: ${pythonJson(item)}`)
      .join(", ")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

export function stableHash(value: unknown) {
  return createHash("sha256")
    .update(pythonJson(canonicalValue(value)), "utf8")
    .digest("hex");
}

export function newLedgerId(prefix: string) {
  return `${prefix}_${randomUUID().replaceAll("-", "").slice(0, 12)}`;
}

function nextAuditCreatedAt(previousCreatedAt: string | null) {
  const previousMs = previousCreatedAt ? Date.parse(previousCreatedAt) : Number.NaN;
  const nowMs = Date.now();
  const nextMs = Number.isFinite(previousMs) && previousMs >= nowMs
    ? previousMs + 1
    : nowMs;
  return new Date(nextMs).toISOString();
}

export async function appendAudit(
  client: PoolClient,
  input: {
    workspaceId?: string;
    actorType: "user" | "agent" | "system";
    actorId: string | null;
    action: string;
    entityType: string;
    entityId: string;
    before?: unknown;
    after?: unknown;
    metadata?: Record<string, unknown>;
    requestHash?: string;
  },
) {
  const workspaceId = String(
    input.workspaceId || input.metadata?.workspace_id || "",
  ).trim();
  if (!workspaceId) throw new Error("audit_workspace_required");
  await client.query("SELECT pg_advisory_xact_lock(1095779668)");
  if (input.requestHash) {
    const existingResult = await client.query<{ audit_id: string }>(
      `SELECT audit_id
      FROM audit_logs
      WHERE workspace_id=$1
        AND actor_type=$2
        AND actor_id IS NOT DISTINCT FROM $3
        AND action=$4
        AND entity_type=$5
        AND entity_id=$6
        AND metadata_json::jsonb ->> 'request_hash'=$7
      ORDER BY created_at DESC,audit_id DESC
      LIMIT 1`,
      [
        workspaceId,
        input.actorType,
        input.actorId,
        input.action,
        input.entityType,
        input.entityId,
        input.requestHash,
      ],
    );
    const existing = existingResult.rows[0];
    if (existing) {
      return { auditId: existing.audit_id, outcome: "unchanged" as const };
    }
  }
  const previousResult = await client.query<{
    tamper_chain_hash: string | null;
    created_at: string | null;
  }>(
    `SELECT tamper_chain_hash,created_at
    FROM audit_logs ORDER BY created_at DESC,audit_id DESC LIMIT 1`,
  );
  const previous = previousResult.rows[0];
  const metadata = {
    ...(input.metadata || {}),
    ...(input.requestHash ? { request_hash: input.requestHash } : {}),
    workspace_id: workspaceId,
  };
  const beforeHash = input.before === undefined ? null : stableHash(input.before);
  const afterHash = input.after === undefined ? null : stableHash(input.after);
  const chainHash = stableHash({
    actor_type: input.actorType,
    actor_id: input.actorId,
    action: input.action,
    entity_type: input.entityType,
    entity_id: input.entityId,
    before_hash: beforeHash,
    after_hash: afterHash,
    metadata_json: metadata,
    previous: previous?.tamper_chain_hash || "genesis",
  });
  const auditId = newLedgerId("aud");
  await client.query(
    `INSERT INTO audit_logs(
      audit_id,workspace_id,actor_type,actor_id,action,entity_type,entity_id,
      before_hash,after_hash,metadata_json,tamper_chain_hash,created_at
    ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
    [
      auditId,
      workspaceId,
      input.actorType,
      input.actorId,
      input.action,
      input.entityType,
      input.entityId,
      beforeHash,
      afterHash,
      JSON.stringify(metadata),
      chainHash,
      nextAuditCreatedAt(previous?.created_at || null),
    ],
  );
  return { auditId, outcome: "created" as const };
}

export async function appendRuntimeEvent(
  client: PoolClient,
  input: {
    workspaceId?: string;
    eventType: string;
    status: string;
    runId?: string | null;
    taskId?: string | null;
    agentId?: string | null;
    inputSummary?: string | null;
    outputSummary?: string | null;
    errorMessage?: string | null;
    rawPayloadHash?: string | null;
  },
) {
  let workspaceId = String(input.workspaceId || "").trim();
  if (!workspaceId && input.runId) {
    const runResult = await client.query<{
      workspace_id: string;
      task_id: string;
      agent_id: string;
    }>(
      `SELECT workspace_id,task_id,agent_id
      FROM runs WHERE run_id=$1`,
      [input.runId],
    );
    const run = runResult.rows[0];
    if (
      !run
      || (input.taskId && input.taskId !== run.task_id)
      || (input.agentId && input.agentId !== run.agent_id)
    ) {
      throw new Error("runtime_event_run_binding_invalid");
    }
    workspaceId = run.workspace_id;
  }
  if (!workspaceId && input.taskId) {
    const taskResult = await client.query<{ workspace_id: string }>(
      `SELECT workspace_id FROM tasks WHERE task_id=$1`,
      [input.taskId],
    );
    workspaceId = taskResult.rows[0]?.workspace_id || "";
  }
  if (!workspaceId) throw new Error("runtime_event_workspace_required");
  await client.query(
    `INSERT INTO runtime_events(
      runtime_event_id,workspace_id,runtime_connector_id,event_type,status,run_id,task_id,
      agent_id,model_name,latency_ms,prompt_hash,input_summary,output_summary,
      error_message,raw_payload_hash,created_at
    ) VALUES($1,$2,NULL,$3,$4,$5,$6,$7,NULL,NULL,NULL,$8,$9,$10,$11,$12)`,
    [
      newLedgerId("rte"),
      workspaceId,
      input.eventType,
      input.status,
      input.runId || null,
      input.taskId || null,
      input.agentId || null,
      input.inputSummary || null,
      input.outputSummary || null,
      input.errorMessage || null,
      input.rawPayloadHash || null,
      new Date().toISOString(),
    ],
  );
}
