#!/usr/bin/env node

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import {
  canonicalExecutorRequestBytes,
  EXECUTOR_REQUEST_SCHEMA,
  parseCanonicalExecutorRequest,
} from "./openclaw-executor-request.mjs";

export const EXECUTOR_PUBLIC_REQUEST_SCHEMA = "agentops_openclaw_executor_public_request_v2";
export const EXECUTOR_DISPATCH_ENVELOPE_SCHEMA = "agentops_openclaw_executor_dispatch_v2";
export const EXECUTOR_PRIVATE_RESPONSE_SCHEMA = "agentops_openclaw_executor_private_response_v2";
export const MAX_EXECUTOR_PROMPT_BYTES = 1024 * 1024 - 2048;

const PUBLIC_FIELDS = Object.freeze([
  "agent_name",
  "nonce",
  "prompt",
  "prompt_sha256",
  "request_id",
  "run_id",
  "schema",
  "timeout_seconds",
  "workspace_id_hash",
]);
const DISPATCH_FIELDS = Object.freeze(["provider_request", "request", "schema"]);
const PROVIDER_REQUEST_FIELDS = Object.freeze([
  "agent_name", "prompt", "prompt_hash", "schema", "timeout_seconds",
]);
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const AGENT_NAME = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const BOOT_ID = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function object(value, code) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(code);
  return value;
}

function exactFields(value, fields, code) {
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((name, index) => name !== expected[index])) {
    fail(code);
  }
}

function token(value, label) {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(`${label}_invalid`);
  return value;
}

function digest(value, label) {
  if (typeof value !== "string" || !SHA256.test(value)) fail(`${label}_invalid`);
  return value;
}

function canonical(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) fail("executor_protocol_canonical_number_invalid");
    return value;
  }
  if (Array.isArray(value)) return value.map(canonical);
  const source = object(value, "executor_protocol_canonical_object_invalid");
  return Object.fromEntries(Object.keys(source).sort().map((name) => [name, canonical(source[name])]));
}

export function canonicalExecutorProtocolBytes(value) {
  return Buffer.from(JSON.stringify(canonical(value)), "utf8");
}

export function validateExecutorPublicRequest(value) {
  const request = object(value, "executor_public_request_invalid");
  exactFields(request, PUBLIC_FIELDS, "executor_public_request_fields_invalid");
  if (request.schema !== EXECUTOR_PUBLIC_REQUEST_SCHEMA) fail("executor_public_request_schema_invalid");
  if (typeof request.agent_name !== "string" || !AGENT_NAME.test(request.agent_name)) {
    fail("executor_public_agent_name_invalid");
  }
  token(request.request_id, "executor_public_request_id");
  token(request.run_id, "executor_public_run_id");
  token(request.nonce, "executor_public_nonce");
  digest(request.workspace_id_hash, "executor_public_workspace_id_hash");
  digest(request.prompt_sha256, "executor_public_prompt_sha256");
  if (
    typeof request.prompt !== "string"
    || !request.prompt.trim()
    || request.prompt.includes("\u0000")
    || Buffer.byteLength(request.prompt, "utf8") > MAX_EXECUTOR_PROMPT_BYTES
  ) fail("executor_public_prompt_invalid");
  if (createHash("sha256").update(request.prompt, "utf8").digest("hex") !== request.prompt_sha256) {
    fail("executor_public_prompt_hash_mismatch");
  }
  if (!Number.isSafeInteger(request.timeout_seconds) || request.timeout_seconds < 1 || request.timeout_seconds > 600) {
    fail("executor_public_timeout_invalid");
  }
  return Object.freeze({ ...request });
}

function providerRequest(source) {
  return Object.freeze({
    agent_name: source.agent_name,
    prompt: source.prompt,
    prompt_hash: source.prompt_sha256,
    schema: "agentops_openclaw_provider_request_v1",
    timeout_seconds: source.timeout_seconds,
  });
}

export function validateExecutorProviderRequest(value) {
  const request = object(value, "executor_provider_request_invalid");
  exactFields(request, PROVIDER_REQUEST_FIELDS, "executor_provider_request_fields_invalid");
  const publicShape = {
    agent_name: request.agent_name,
    nonce: "provider-request-validation",
    prompt: request.prompt,
    prompt_sha256: request.prompt_hash,
    request_id: "provider-request-validation",
    run_id: "provider-request-validation",
    schema: EXECUTOR_PUBLIC_REQUEST_SCHEMA,
    timeout_seconds: request.timeout_seconds,
    workspace_id_hash: "0".repeat(64),
  };
  validateExecutorPublicRequest(publicShape);
  if (request.schema !== "agentops_openclaw_provider_request_v1") {
    fail("executor_provider_request_schema_invalid");
  }
  return Object.freeze({ ...request });
}

export function readLinuxBootClock({
  bootIdPath = "/proc/sys/kernel/random/boot_id",
  uptimePath = "/proc/uptime",
} = {}) {
  let bootId;
  let uptime;
  try {
    bootId = readFileSync(bootIdPath, "ascii").trim().toLowerCase();
    uptime = readFileSync(uptimePath, "ascii").trim().split(/\s+/u)[0];
  } catch {
    fail("executor_boot_clock_unavailable");
  }
  if (!BOOT_ID.test(bootId)) fail("executor_boot_id_invalid");
  const match = /^(?:0|[1-9][0-9]*)(?:\.([0-9]{1,9}))?$/.exec(uptime);
  if (!match) fail("executor_boottime_invalid");
  const [seconds] = uptime.split(".");
  const fraction = (match[1] || "").padEnd(9, "0");
  const now = (BigInt(seconds) * 1_000_000_000n) + BigInt(fraction || "0");
  return Object.freeze({ boot_id: bootId, now_boottime_ns: now.toString() });
}

export function buildExecutorDispatch(value, {
  bootClock,
  isolationPolicySha256,
  runtimeManifestSha256,
}) {
  const source = validateExecutorPublicRequest(value);
  const clock = object(bootClock, "executor_boot_clock_invalid");
  if (typeof clock.boot_id !== "string" || !BOOT_ID.test(clock.boot_id)) fail("executor_boot_id_invalid");
  if (typeof clock.now_boottime_ns !== "string" || !/^(?:0|[1-9][0-9]{0,19})$/.test(clock.now_boottime_ns)) {
    fail("executor_boottime_invalid");
  }
  digest(isolationPolicySha256, "executor_isolation_policy_sha256");
  digest(runtimeManifestSha256, "executor_runtime_manifest_sha256");
  const now = BigInt(clock.now_boottime_ns);
  const deadline = now + (BigInt(source.timeout_seconds) * 1_000_000_000n);
  const request = {
    boot_id: clock.boot_id,
    deadline_boottime_ns: deadline.toString(),
    isolation_policy_sha256: isolationPolicySha256,
    nonce: source.nonce,
    prompt_sha256: source.prompt_sha256,
    request_id: source.request_id,
    run_id: source.run_id,
    runtime_manifest_sha256: runtimeManifestSha256,
    schema: EXECUTOR_REQUEST_SCHEMA,
    workspace_id_hash: source.workspace_id_hash,
  };
  parseCanonicalExecutorRequest(canonicalExecutorRequestBytes(request), clock);
  return Object.freeze({
    provider_request: providerRequest(source),
    request: Object.freeze(request),
    schema: EXECUTOR_DISPATCH_ENVELOPE_SCHEMA,
  });
}

export function parseCanonicalExecutorDispatch(value, expectedClock) {
  if (!(Buffer.isBuffer(value) || value instanceof Uint8Array)) fail("executor_dispatch_bytes_required");
  const bytes = Buffer.from(value);
  if (bytes.byteLength < 2 || bytes.byteLength > 1024 * 1024) fail("executor_dispatch_size_invalid");
  let parsed;
  try {
    parsed = JSON.parse(new TextDecoder("utf8", { fatal: true }).decode(bytes));
  } catch {
    fail("executor_dispatch_json_invalid");
  }
  const envelope = object(parsed, "executor_dispatch_invalid");
  exactFields(envelope, DISPATCH_FIELDS, "executor_dispatch_fields_invalid");
  if (envelope.schema !== EXECUTOR_DISPATCH_ENVELOPE_SCHEMA) fail("executor_dispatch_schema_invalid");
  const provider = validateExecutorProviderRequest(envelope.provider_request);
  const request = parseCanonicalExecutorRequest(canonicalExecutorRequestBytes(envelope.request), expectedClock);
  if (provider.prompt_hash !== request.prompt_sha256) {
    fail("executor_dispatch_prompt_hash_mismatch");
  }
  if (!bytes.equals(canonicalExecutorProtocolBytes(envelope))) fail("executor_dispatch_encoding_noncanonical");
  return Object.freeze({
    provider_request: provider,
    request,
    schema: envelope.schema,
  });
}
