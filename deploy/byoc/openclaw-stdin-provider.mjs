#!/usr/bin/env node

import { createHash, randomUUID } from "node:crypto";
import {
  chmodSync,
  lstatSync,
  mkdtempSync,
  readdirSync,
  realpathSync,
  rmSync,
  unlinkSync,
} from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const REQUEST_SCHEMA = "agentops_openclaw_provider_request_v1";
const RESPONSE_SCHEMA = "agentops_openclaw_provider_response_v1";
const STDIN_PROTOCOL = "canonical_provider_request_stdin_v1";
const FIXED_ERROR = "Provider error detail omitted; OpenClaw execution failed.";
const REQUEST_FIELDS = ["agent_name", "prompt", "prompt_hash", "schema", "timeout_seconds"].sort();
const MAX_REQUEST_BYTES = 1024 * 1024;

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function canonical(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) fail("stdin_provider_canonical_number_invalid");
    return value;
  }
  if (Array.isArray(value)) return value.map(canonical);
  if (!value || typeof value !== "object" || Object.getPrototypeOf(value) !== Object.prototype) {
    fail("stdin_provider_canonical_object_invalid");
  }
  return Object.fromEntries(Object.keys(value).sort().map((name) => [name, canonical(value[name])]));
}

function canonicalBytes(value) {
  return Buffer.from(JSON.stringify(canonical(value)), "utf8");
}

function validateRequest(bytes) {
  if (bytes.length < 2 || bytes.length > MAX_REQUEST_BYTES) fail("stdin_provider_request_size_invalid");
  let request;
  try {
    request = JSON.parse(new TextDecoder("utf8", { fatal: true }).decode(bytes));
  } catch {
    fail("stdin_provider_request_json_invalid");
  }
  const fields = request && typeof request === "object" && !Array.isArray(request)
    ? Object.keys(request).sort()
    : [];
  if (fields.length !== REQUEST_FIELDS.length || fields.some((name, index) => name !== REQUEST_FIELDS[index])) {
    fail("stdin_provider_request_fields_invalid");
  }
  if (
    request.schema !== REQUEST_SCHEMA
    || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(String(request.agent_name || ""))
    || typeof request.prompt !== "string"
    || !request.prompt.trim()
    || request.prompt.includes("\0")
    || !/^[a-f0-9]{64}$/.test(String(request.prompt_hash || ""))
    || digest(Buffer.from(request.prompt, "utf8")) !== request.prompt_hash
    || !Number.isSafeInteger(request.timeout_seconds)
    || request.timeout_seconds < 1
    || request.timeout_seconds > 600
    || !bytes.equals(canonicalBytes(request))
  ) fail("stdin_provider_request_invalid");
  return Object.freeze(request);
}

async function readBoundedStdin(stdin) {
  const chunks = [];
  let size = 0;
  for await (const chunk of stdin) {
    size += chunk.byteLength;
    if (size > MAX_REQUEST_BYTES) fail("stdin_provider_request_size_invalid");
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

function safeModelName(result, fallback) {
  const provider = result?.meta?.agentMeta?.provider;
  const model = result?.meta?.agentMeta?.model;
  const value = provider && model ? `${provider}/${model}` : fallback;
  return /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$/.test(String(value)) ? String(value) : fallback;
}

function outputTokens(result) {
  const value = result?.meta?.agentMeta?.usage?.output;
  return Number.isSafeInteger(value) && value >= 0 && value <= 10_000_000 ? value : 0;
}

function elapsed(started, now) {
  return Math.min(86_400_000, Math.max(0, now() - started));
}

function responseFromResult(request, result, started, now) {
  const wire = Buffer.from(JSON.stringify(result), "utf8");
  const outputPresent = Array.isArray(result?.payloads)
    && result.payloads.some((payload) => typeof payload?.text === "string" && payload.text.length > 0);
  const errorPayloadPresent = Array.isArray(result?.payloads)
    && result.payloads.some((payload) => payload?.isError === true);
  const failed = result?.isError === true
    || errorPayloadPresent
    || result?.meta?.aborted === true
    || result?.meta?.error
    || result?.meta?.failureSignal;
  return {
    dry_run: false,
    duration_ms: elapsed(started, now),
    error_message: failed || !outputPresent ? FIXED_ERROR : null,
    error_type: failed || !outputPresent ? "OpenClawExecutionFailed" : null,
    model_name: safeModelName(result, request.agent_name),
    ok: !failed && outputPresent,
    output_present: !failed && outputPresent,
    output_tokens: outputTokens(result),
    provider_call_performed: !failed && outputPresent,
    raw_payload_hash: digest(wire),
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    retryable: false,
    schema: RESPONSE_SCHEMA,
  };
}

function failureResponse(agentName, started, errorType = "OpenClawExecutionFailed", now = Date.now) {
  return {
    dry_run: false,
    duration_ms: elapsed(started, now),
    error_message: FIXED_ERROR,
    error_type: errorType,
    model_name: agentName,
    ok: false,
    output_present: false,
    output_tokens: 0,
    provider_call_performed: false,
    raw_payload_hash: digest(Buffer.alloc(0)),
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    retryable: false,
    schema: RESPONSE_SCHEMA,
  };
}

function cleanupSessionFiles(stateRoot, agentName, sessionId) {
  if (typeof stateRoot !== "string" || !path.isAbsolute(stateRoot) || stateRoot.includes("\0")) {
    fail("stdin_provider_state_root_invalid");
  }
  const sessionDirectory = path.join(stateRoot, "agents", agentName, "sessions");
  const normalized = path.resolve(sessionDirectory);
  if (!normalized.startsWith(`${path.resolve(stateRoot)}${path.sep}`)) fail("stdin_provider_state_root_escape");
  let removed = 0;
  for (const suffix of [".jsonl", ".jsonl.lock", ".trajectory.jsonl", ".trajectory-path.json"]) {
    const target = path.join(normalized, `${sessionId}${suffix}`);
    try {
      const metadata = lstatSync(target);
      if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.nlink !== 1) {
        fail("stdin_provider_session_cleanup_metadata_invalid");
      }
      unlinkSync(target);
      removed += 1;
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  }
  return removed;
}

export function createEphemeralStateRoot(baseStateRoot) {
  if (typeof baseStateRoot !== "string" || !path.isAbsolute(baseStateRoot) || baseStateRoot.includes("\0")) {
    fail("stdin_provider_state_root_invalid");
  }
  const metadata = lstatSync(baseStateRoot);
  if (
    !metadata.isDirectory()
    || metadata.isSymbolicLink()
    || metadata.uid !== process.getuid?.()
    || (metadata.mode & 0o077) !== 0
  ) fail("stdin_provider_state_root_metadata_invalid");
  if (readdirSync(baseStateRoot).length !== 0) fail("stdin_provider_state_root_not_empty");
  const target = mkdtempSync(path.join(baseStateRoot, "agentops-request-"));
  chmodSync(target, 0o700);
  return target;
}

export function removeEphemeralStateRoot(baseStateRoot, target) {
  const base = realpathSync(baseStateRoot);
  const expectedParent = realpathSync(path.dirname(target));
  const baseMetadata = lstatSync(base);
  if (
    expectedParent !== base
    || !path.basename(target).startsWith("agentops-request-")
    || !baseMetadata.isDirectory()
    || baseMetadata.isSymbolicLink()
    || baseMetadata.uid !== process.getuid?.()
    || (baseMetadata.mode & 0o077) !== 0
  ) fail("stdin_provider_ephemeral_state_metadata_invalid");
  for (const name of readdirSync(base)) {
    const entry = path.join(base, name);
    if (path.dirname(entry) !== base || name === "." || name === "..") {
      fail("stdin_provider_ephemeral_state_entry_invalid");
    }
    rmSync(entry, { force: false, maxRetries: 2, recursive: true, retryDelay: 10 });
  }
  if (readdirSync(base).length !== 0) fail("stdin_provider_ephemeral_state_cleanup_incomplete");
}

export async function executeCanonicalProviderRequest(bytes, {
  agentCommand,
  now = Date.now,
  stateRoot = process.env.OPENCLAW_STATE_DIR,
  workspaceDir = process.env.OPENCLAW_WORKSPACE,
} = {}) {
  const request = validateRequest(Buffer.from(bytes));
  if (typeof agentCommand !== "function") fail("stdin_provider_agent_command_required");
  if (typeof workspaceDir !== "string" || !workspaceDir.startsWith("/") || workspaceDir.includes("\0")) {
    fail("stdin_provider_workspace_invalid");
  }
  const started = now();
  const sessionId = `agentops-${randomUUID()}`;
  let result = null;
  let executionFailed = false;
  try {
    result = await agentCommand({
      abortSignal: AbortSignal.timeout(request.timeout_seconds * 1000),
      agentId: request.agent_name,
      allowModelOverride: false,
      bootstrapContextMode: "lightweight",
      cleanupBundleMcpOnRunEnd: true,
      cleanupCliLiveSessionOnRunEnd: true,
      deliver: false,
      json: true,
      message: request.prompt,
      modelRun: true,
      runId: randomUUID(),
      senderIsOwner: false,
      sessionId,
      timeout: String(request.timeout_seconds),
      transcriptMessage: "[omitted]",
      workspaceDir,
    }, {
      error: () => {},
      exit: () => fail("stdin_provider_agent_command_exit_forbidden"),
      log: () => {},
    });
  } catch {
    executionFailed = true;
  }
  try {
    cleanupSessionFiles(stateRoot, request.agent_name, sessionId);
  } catch {
    return canonicalBytes(failureResponse(request.agent_name, started, "AdapterCleanupFailed", now));
  }
  return canonicalBytes(executionFailed
    ? failureResponse(request.agent_name, started, "OpenClawExecutionFailed", now)
    : responseFromResult(request, result, started, now));
}

async function main() {
  if (process.argv.length !== 3 || process.argv[2] !== `--stdin-protocol=${STDIN_PROTOCOL}`) {
    fail("stdin_provider_arguments_invalid");
  }
  const baseStateRoot = process.env.OPENCLAW_STATE_DIR;
  const stateRoot = createEphemeralStateRoot(baseStateRoot);
  process.env.OPENCLAW_STATE_DIR = stateRoot;
  let response;
  try {
    const [runtime, bytes] = await Promise.all([
      import("openclaw/plugin-sdk/agent-runtime"),
      readBoundedStdin(process.stdin),
    ]);
    response = await executeCanonicalProviderRequest(bytes, {
      agentCommand: runtime.agentCommand,
      stateRoot,
    });
    removeEphemeralStateRoot(baseStateRoot, stateRoot);
  } catch (error) {
    try { removeEphemeralStateRoot(baseStateRoot, stateRoot); } catch {}
    throw error;
  }
  process.stdout.write(response);
}

if (process.argv[1] && import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href) {
  main().catch(() => {
    process.stdout.write(canonicalBytes(failureResponse("openclaw", Date.now(), "AdapterRejected")));
    process.exitCode = 1;
  });
}
