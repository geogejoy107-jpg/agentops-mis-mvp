#!/usr/bin/env node

import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
import {
  buildExecutorDispatch,
  canonicalExecutorProtocolBytes,
  EXECUTOR_PUBLIC_REQUEST_SCHEMA,
  parseCanonicalExecutorDispatch,
  readLinuxBootClock,
  validateExecutorPublicRequest,
} from "./openclaw-executor-protocol.mjs";

const root = mkdtempSync("/tmp/aoep-");
const bootIdPath = join(root, "boot-id");
const uptimePath = join(root, "uptime");
const bootId = "123e4567-e89b-42d3-a456-426614174000";
writeFileSync(bootIdPath, `${bootId}\n`);
writeFileSync(uptimePath, "12.345678901 10.00\n");
const clock = readLinuxBootClock({ bootIdPath, uptimePath });
assert.deepEqual(clock, { boot_id: bootId, now_boottime_ns: "12345678901" });

const prompt = "A07 bounded runtime protocol contract";
const request = {
  agent_name: "main",
  nonce: "nonce_a07_contract",
  prompt,
  prompt_sha256: createHash("sha256").update(prompt).digest("hex"),
  request_id: "req_a07_contract",
  run_id: "run_gw_a07_contract",
  schema: EXECUTOR_PUBLIC_REQUEST_SCHEMA,
  timeout_seconds: 30,
  workspace_id_hash: "1".repeat(64),
};
assert.equal(validateExecutorPublicRequest(request).request_id, request.request_id);
const dispatch = buildExecutorDispatch(request, {
  bootClock: clock,
  isolationPolicySha256: "2".repeat(64),
  runtimeManifestSha256: "3".repeat(64),
});
  assert.equal(dispatch.request.deadline_boottime_ns, "42345678901");
  assert.equal(dispatch.request.prompt_sha256, request.prompt_sha256);
  assert.deepEqual(dispatch.provider_request, {
    agent_name: request.agent_name,
    prompt: request.prompt,
    prompt_hash: request.prompt_sha256,
    schema: "agentops_openclaw_provider_request_v1",
    timeout_seconds: request.timeout_seconds,
  });
const bytes = canonicalExecutorProtocolBytes(dispatch);
assert.deepEqual(parseCanonicalExecutorDispatch(bytes, clock), dispatch);

for (const invalid of [
  { ...request, prompt: `${prompt}!` },
  { ...request, timeout_seconds: 0 },
  { ...request, request_id: "../escape" },
  { ...request, raw_response: "forbidden" },
]) assert.throws(() => validateExecutorPublicRequest(invalid), /executor_public_/);
assert.throws(
  () => parseCanonicalExecutorDispatch(Buffer.from(` ${bytes}`), clock),
  /executor_dispatch_encoding_noncanonical/,
);
assert.throws(
  () => parseCanonicalExecutorDispatch(
    canonicalExecutorProtocolBytes({
      ...dispatch,
      provider_request: { ...dispatch.provider_request, prompt: `${prompt}!` },
    }),
    clock,
  ),
  /executor_(?:provider_request|dispatch)_prompt_hash_mismatch|executor_public_prompt_hash_mismatch/,
);
assert.throws(
  () => parseCanonicalExecutorDispatch(bytes, { ...clock, now_boottime_ns: dispatch.request.deadline_boottime_ns }),
  /executor_request_deadline_expired/,
);
assert.throws(
  () => buildExecutorDispatch(request, {
    bootClock: clock,
    isolationPolicySha256: "bad",
    runtimeManifestSha256: "3".repeat(64),
  }),
  /executor_isolation_policy_sha256_invalid/,
);
writeFileSync(uptimePath, "not-uptime\n");
assert.throws(() => readLinuxBootClock({ bootIdPath, uptimePath }), /executor_boottime_invalid/);

rmSync(root, { recursive: true, force: true });
console.log(JSON.stringify({
  contract: "agentops_openclaw_executor_protocol_a07_v1",
  public_v2_governance_bindings_verified: true,
  canonical_private_dispatch_verified: true,
  boot_and_boottime_deadline_verified: true,
  prompt_hash_binding_verified: true,
  raw_prompt_persisted: false,
  runtime_receipt_verified: false,
  hostile_runtime_isolation_verified: false,
}));
