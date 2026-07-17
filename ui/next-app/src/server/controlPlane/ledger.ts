import { createHash, randomUUID } from "node:crypto";
import type { PoolClient } from "pg";

type PythonFloat = { __agentops_python_float__: number };
type JsonValue = null | boolean | number | string | PythonFloat | JsonValue[] | { [key: string]: JsonValue };

export function pythonFloat(value: number): PythonFloat {
  return { __agentops_python_float__: value };
}

function canonicalValue(value: unknown): JsonValue {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (typeof value === "object") {
    if ("__agentops_python_float__" in (value as Record<string, unknown>)) {
      return value as PythonFloat;
    }
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
  return createHash("sha256").update(pythonJson(canonicalValue(value)), "utf8").digest("hex");
}

export function newLedgerId(prefix: string) {
  return `${prefix}_${randomUUID().replaceAll("-", "").slice(0, 12)}`;
}

function isoToEpochMicros(value: string) {
  const match = value.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/);
  if (!match) throw new Error("audit_created_at_invalid");
  const epochMillis = Date.parse(`${match[1]}${match[3]}`);
  if (!Number.isFinite(epochMillis)) throw new Error("audit_created_at_invalid");
  const fractionMicros = BigInt((match[2] || "").padEnd(6, "0"));
  return BigInt(epochMillis) * 1000n + fractionMicros;
}

function epochMicrosToPythonIso(value: bigint) {
  const epochMillis = value / 1000n;
  const micros = value % 1_000_000n;
  const seconds = new Date(Number(epochMillis)).toISOString().slice(0, 19);
  return `${seconds}.${micros.toString().padStart(6, "0")}+00:00`;
}

function nextAuditCreatedAt(previousCreatedAt: string | null) {
  let nextMicros = BigInt(Date.now()) * 1000n;
  if (previousCreatedAt) {
    const previousMicros = isoToEpochMicros(previousCreatedAt);
    if (nextMicros <= previousMicros) nextMicros = previousMicros + 1n;
  }
  let createdAt = epochMicrosToPythonIso(nextMicros);
  if (previousCreatedAt && createdAt <= previousCreatedAt) {
    const previousMicros = isoToEpochMicros(previousCreatedAt);
    nextMicros = ((previousMicros / 1_000_000n) + 1n) * 1_000_000n;
    createdAt = epochMicrosToPythonIso(nextMicros);
  }
  if (previousCreatedAt && createdAt <= previousCreatedAt) throw new Error("audit_created_at_not_monotonic");
  return createdAt;
}

export async function appendAudit(
  client: PoolClient,
  input: {
    actorType: "user" | "agent" | "system";
    actorId: string | null;
    action: string;
    entityType: string;
    entityId: string;
    before?: unknown;
    after?: unknown;
    metadata?: Record<string, unknown>;
  },
) {
  await client.query("SELECT pg_advisory_xact_lock(1095779668)");
  const previous = await client.query<{ tamper_chain_hash: string | null; created_at: string | null }>(
    "SELECT tamper_chain_hash,created_at FROM audit_logs ORDER BY created_at DESC, audit_id DESC LIMIT 1",
  );
  const previousRow = previous.rows[0];
  const metadata = input.metadata || {};
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
    previous: previousRow?.tamper_chain_hash || "genesis",
  });
  const createdAt = nextAuditCreatedAt(previousRow?.created_at || null);
  await client.query(
    `INSERT INTO audit_logs(
      audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at
    ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`,
    [
      newLedgerId("aud"),
      input.actorType,
      input.actorId,
      input.action,
      input.entityType,
      input.entityId,
      beforeHash,
      afterHash,
      JSON.stringify(metadata),
      chainHash,
      createdAt,
    ],
  );
}

export async function appendRuntimeEvent(
  client: PoolClient,
  input: {
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
  await client.query(
    `INSERT INTO runtime_events(
      runtime_event_id,runtime_connector_id,event_type,status,run_id,task_id,agent_id,model_name,latency_ms,prompt_hash,
      input_summary,output_summary,error_message,raw_payload_hash,created_at
    ) VALUES($1,$2,$3,$4,$5,$6,$7,NULL,NULL,NULL,$8,$9,$10,$11,$12)`,
    [
      newLedgerId("rte"),
      "rtc_agent_gateway_local",
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
