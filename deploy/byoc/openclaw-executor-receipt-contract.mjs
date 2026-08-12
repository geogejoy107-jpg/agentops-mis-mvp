#!/usr/bin/env node

import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import {
  canonicalExecutorReceiptBytes,
  EXECUTOR_RECEIPT_SCHEMA,
  MAX_EXECUTOR_RECEIPT_BYTES,
  serializeExecutorReceiptEnvelope,
  signExecutorReceipt,
  verifyCanonicalExecutorReceipt,
} from "./openclaw-executor-receipt.mjs";

const digest = (character) => character.repeat(64);
const rawPrompt = "contract prompt must never enter the receipt";
const rawResponse = "contract response must never enter the receipt";
const secret = "sk-contract-secret-must-never-enter-the-receipt";
const cgroup = {
  cgroup_id: "cg-41-9001",
  device: "41",
  inode: "9001",
  limits: {
    cpu_max: "50000 100000",
    io_max: "8:0 rbps=1048576 wbps=1048576",
    memory_max_bytes: "536870912",
    memory_swap_max_bytes: "0",
    pids_max: "64",
  },
  process_entry_verified: true,
  root_device: "41",
  root_inode: "7001",
};
const launcher = {
  binary_sha256: digest("a"),
  device: "41",
  inode: "8001",
  invoked: true,
  no_new_privs_applied: true,
  runtime_gid: 1200,
  runtime_uid: 1200,
  seccomp_applied: true,
};
const body = {
  agent_name: "contract-agent",
  boot_id: "12345678-1234-4123-8123-123456789abc",
  cgroup,
  deadline_boottime_ns: "4000000000",
  descendants_cleanup_verified: true,
  executor_image_digest: `sha256:${digest("1")}`,
  executor_key_id: "executor-receipt-key-1",
  exit_code: 0,
  exit_kind: "completed",
  finished_boottime_ns: "3000000000",
  hostile_runtime_isolation_verified: false,
  isolation_policy_sha256: digest("2"),
  launcher,
  nonce: "nonce-contract-001",
  private_dispatch_schema: "agentops_openclaw_executor_dispatch_v2",
  private_dispatch_sha256: digest("3"),
  process: { pid: 4242, spawned: true },
  prompt_sha256: digest("4"),
  provider: {
    call_observed: true,
    request_sha256: digest("5"),
    response_complete: true,
    response_sha256: digest("6"),
  },
  provider_call_verified: false,
  public_request_schema: "agentops_openclaw_executor_public_request_v2",
  public_request_sha256: digest("7"),
  raw_prompt_omitted: true,
  raw_response_omitted: true,
  receipt_id: "exr-contract-001",
  request_id: "req-contract-001",
  run_id: "run-gw-contract-001",
  runtime_image_digest: `sha256:${digest("8")}`,
  runtime_manifest_sha256: digest("9"),
  secrets_omitted: true,
  seccomp_profile_sha256: digest("b"),
  started_boottime_ns: "2000000000",
  termination_signal: null,
  timeout: { enforced: true, expired: false },
  workspace_id_hash: digest("c"),
};
const expected = {
  agent_name: body.agent_name,
  boot_id: body.boot_id,
  cgroup: body.cgroup,
  deadline_boottime_ns: body.deadline_boottime_ns,
  executor_image_digest: body.executor_image_digest,
  executor_key_id: body.executor_key_id,
  isolation_policy_sha256: body.isolation_policy_sha256,
  launcher: body.launcher,
  nonce: body.nonce,
  private_dispatch_schema: body.private_dispatch_schema,
  private_dispatch_sha256: body.private_dispatch_sha256,
  prompt_sha256: body.prompt_sha256,
  provider_request_sha256: body.provider.request_sha256,
  public_request_schema: body.public_request_schema,
  public_request_sha256: body.public_request_sha256,
  request_id: body.request_id,
  run_id: body.run_id,
  runtime_image_digest: body.runtime_image_digest,
  runtime_manifest_sha256: body.runtime_manifest_sha256,
  seccomp_profile_sha256: body.seccomp_profile_sha256,
  verification_boottime_ns: "3500000000",
  workspace_id_hash: body.workspace_id_hash,
};

const primary = generateKeyPairSync("ed25519");
const other = generateKeyPairSync("ed25519");
const wrongAlgorithm = generateKeyPairSync("rsa", { modulusLength: 2048 });
const envelope = signExecutorReceipt(body, body.executor_key_id, primary.privateKey);
const bytes = serializeExecutorReceiptEnvelope(envelope);
const roots = new Map([[body.executor_key_id, primary.publicKey]]);

assert.equal(envelope.schema, EXECUTOR_RECEIPT_SCHEMA);
assert.deepEqual(
  canonicalExecutorReceiptBytes({ z: 1, a: { y: false, b: "value" } }),
  Buffer.from('{"a":{"b":"value","y":false},"z":1}'),
);
const verified = verifyCanonicalExecutorReceipt(bytes, roots, expected, new Set());
assert.equal(verified.receipt_id, body.receipt_id);
assert.equal(verified.provider.response_sha256, body.provider.response_sha256);
assert.equal(verified.provider_call_verified, false);
assert.equal(verified.hostile_runtime_isolation_verified, false);

const wireText = bytes.toString("utf8");
for (const forbidden of [rawPrompt, rawResponse, secret]) assert.equal(wireText.includes(forbidden), false);
for (const forbiddenField of ["raw_prompt\"", "raw_response\"", "api_key\"", "authorization\""]) {
  assert.equal(wireText.includes(forbiddenField), false);
}
assert.match(wireText, /"raw_prompt_omitted":true/);
assert.match(wireText, /"raw_response_omitted":true/);
assert.match(wireText, /"secrets_omitted":true/);

const replay = new Set();
verifyCanonicalExecutorReceipt(bytes, roots, expected, replay);
assert.throws(
  () => verifyCanonicalExecutorReceipt(bytes, roots, expected, replay),
  /executor_receipt_replayed/,
);
const sameNonce = signExecutorReceipt(
  { ...body, receipt_id: "exr-contract-002" },
  body.executor_key_id,
  primary.privateKey,
);
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    serializeExecutorReceiptEnvelope(sameNonce),
    roots,
    expected,
    replay,
  ),
  /executor_receipt_replayed/,
);

assert.throws(
  () => verifyCanonicalExecutorReceipt(bytes, new Map(), expected, new Set()),
  /executor_receipt_unknown_key/,
);
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    bytes,
    new Map([[body.executor_key_id, other.publicKey]]),
    expected,
    new Set(),
  ),
  /executor_receipt_signature_unverified/,
);
assert.throws(
  () => signExecutorReceipt(body, "different-key-id", primary.privateKey),
  /executor_receipt_key_id_mismatch/,
);
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    serializeExecutorReceiptEnvelope({ ...envelope, key_id: "different-key-id" }),
    new Map([["different-key-id", other.publicKey]]),
    expected,
    new Set(),
  ),
  /executor_receipt_key_id_mismatch/,
);
assert.throws(
  () => signExecutorReceipt(body, body.executor_key_id, wrongAlgorithm.privateKey),
  /executor_receipt_private_key_invalid/,
);
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    bytes,
    new Map([[body.executor_key_id, wrongAlgorithm.publicKey]]),
    expected,
    new Set(),
  ),
  /executor_receipt_public_key_invalid/,
);

for (const [name, value] of [
  ["request_id", "different-request"],
  ["run_id", "different-run"],
  ["workspace_id_hash", digest("d")],
  ["agent_name", "different-agent"],
  ["nonce", "different-nonce"],
  ["boot_id", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"],
  ["deadline_boottime_ns", "4000000001"],
  ["public_request_sha256", digest("d")],
  ["private_dispatch_sha256", digest("d")],
  ["runtime_manifest_sha256", digest("d")],
  ["isolation_policy_sha256", digest("d")],
  ["seccomp_profile_sha256", digest("d")],
  ["executor_image_digest", `sha256:${digest("d")}`],
  ["runtime_image_digest", `sha256:${digest("d")}`],
  ["provider_request_sha256", digest("d")],
]) {
  assert.throws(
    () => verifyCanonicalExecutorReceipt(bytes, roots, { ...expected, [name]: value }, new Set()),
    new RegExp(`executor_receipt_${name}_mismatch`),
  );
}
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    bytes,
    roots,
    { ...expected, cgroup: { ...cgroup, inode: "9002" } },
    new Set(),
  ),
  /executor_receipt_cgroup_mismatch/,
);
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    bytes,
    roots,
    { ...expected, launcher: { ...launcher, inode: "8002" } },
    new Set(),
  ),
  /executor_receipt_launcher_mismatch/,
);
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    bytes,
    roots,
    { ...expected, verification_boottime_ns: "2999999999" },
    new Set(),
  ),
  /executor_receipt_verification_time_invalid/,
);

const tampered = {
  ...envelope,
  body: {
    ...envelope.body,
    provider: { ...envelope.body.provider, response_sha256: digest("d") },
  },
};
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    serializeExecutorReceiptEnvelope(tampered),
    roots,
    expected,
    new Set(),
  ),
  /executor_receipt_signature_unverified/,
);
const changedSignature = `${envelope.signature.slice(0, -1)}${envelope.signature.endsWith("A") ? "B" : "A"}`;
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    serializeExecutorReceiptEnvelope({ ...envelope, signature: changedSignature }),
    roots,
    expected,
    new Set(),
  ),
  /executor_receipt_signature_(?:invalid|unverified)/,
);

for (const forbidden of [
  { raw_prompt: rawPrompt },
  { raw_response: rawResponse },
  { api_key: secret },
  { authorization: secret },
]) {
  assert.throws(
    () => signExecutorReceipt({ ...body, ...forbidden }, body.executor_key_id, primary.privateKey),
    /executor_receipt_body_fields_invalid/,
  );
}
assert.throws(
  () => signExecutorReceipt(
    { ...body, provider: { ...body.provider, raw_response: rawResponse } },
    body.executor_key_id,
    primary.privateKey,
  ),
  /executor_receipt_provider_fields_invalid/,
);
assert.throws(
  () => signExecutorReceipt(
    { ...body, launcher: { ...body.launcher, secret } },
    body.executor_key_id,
    primary.privateKey,
  ),
  /executor_receipt_launcher_fields_invalid/,
);

for (const field of ["request_id", "provider", "cgroup", "runtime_image_digest"]) {
  const incomplete = { ...body };
  delete incomplete[field];
  assert.throws(
    () => signExecutorReceipt(incomplete, body.executor_key_id, primary.privateKey),
    /executor_receipt_body_fields_invalid/,
  );
}
for (const [name, value, failure] of [
  ["public_request_schema", "agentops_openclaw_executor_public_request_v1", "public_request_schema_invalid"],
  ["private_dispatch_schema", "agentops_openclaw_executor_dispatch_v1", "private_dispatch_schema_invalid"],
]) {
  assert.throws(
    () => signExecutorReceipt({ ...body, [name]: value }, body.executor_key_id, primary.privateKey),
    new RegExp(`executor_receipt_${failure}`),
  );
}
assert.throws(
  () => signExecutorReceipt(
    { ...body, descendants_cleanup_verified: false },
    body.executor_key_id,
    primary.privateKey,
  ),
  /executor_receipt_descendants_cleanup_verified_invalid/,
);
assert.throws(
  () => signExecutorReceipt(
    { ...body, provider_call_verified: true },
    body.executor_key_id,
    primary.privateKey,
  ),
  /executor_receipt_provider_call_verified_invalid/,
);
assert.throws(
  () => signExecutorReceipt(
    { ...body, hostile_runtime_isolation_verified: true },
    body.executor_key_id,
    primary.privateKey,
  ),
  /executor_receipt_hostile_runtime_isolation_verified_invalid/,
);
assert.throws(
  () => signExecutorReceipt(
    { ...body, raw_prompt_omitted: false },
    body.executor_key_id,
    primary.privateKey,
  ),
  /executor_receipt_raw_prompt_omitted_invalid/,
);
assert.throws(
  () => signExecutorReceipt(
    { ...body, process: { pid: 4242, spawned: true }, cgroup: { ...cgroup, process_entry_verified: false } },
    body.executor_key_id,
    primary.privateKey,
  ),
  /executor_receipt_spawn_evidence_incomplete/,
);

const timedOutBody = {
  ...body,
  exit_code: null,
  exit_kind: "timed_out",
  finished_boottime_ns: "4000000001",
  provider: {
    ...body.provider,
    response_complete: false,
    response_sha256: null,
  },
  termination_signal: 9,
  timeout: { enforced: true, expired: true },
};
const timedOutEnvelope = signExecutorReceipt(timedOutBody, body.executor_key_id, primary.privateKey);
assert.equal(timedOutEnvelope.body.exit_kind, "timed_out");
assert.throws(
  () => signExecutorReceipt(
    { ...timedOutBody, timeout: { enforced: true, expired: false } },
    body.executor_key_id,
    primary.privateKey,
  ),
  /executor_receipt_timeout_state_invalid/,
);
assert.throws(
  () => signExecutorReceipt(
    { ...body, provider: { ...body.provider, call_observed: false } },
    body.executor_key_id,
    primary.privateKey,
  ),
  /executor_receipt_provider_state_invalid/,
);

assert.throws(
  () => verifyCanonicalExecutorReceipt(Buffer.from(` ${wireText}`), roots, expected, new Set()),
  /executor_receipt_encoding_noncanonical/,
);
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    Buffer.from(wireText.replace(
      '"algorithm":"Ed25519"',
      '"algorithm":"Ed25519","algorithm":"Ed25519"',
    )),
    roots,
    expected,
    new Set(),
  ),
  /executor_receipt_encoding_noncanonical/,
);
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    canonicalExecutorReceiptBytes({ ...envelope, unknown: true }),
    roots,
    expected,
    new Set(),
  ),
  /executor_receipt_envelope_fields_invalid/,
);
assert.throws(
  () => verifyCanonicalExecutorReceipt(
    Buffer.alloc(MAX_EXECUTOR_RECEIPT_BYTES + 1, 0x20),
    roots,
    expected,
    new Set(),
  ),
  /executor_receipt_size_invalid/,
);

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_executor_receipt_primitive_a07_v1",
  canonical_json_verified: true,
  canonical_wire_encoding_verified: true,
  duplicate_json_key_rejected: true,
  ed25519_signature_verified: true,
  key_confusion_rejected: true,
  public_private_dispatch_identity_bound: true,
  request_run_workspace_agent_nonce_bound: true,
  boot_deadline_bound: true,
  manifest_policy_seccomp_images_bound: true,
  cgroup_identity_and_limits_bound: true,
  launcher_process_exit_timeout_bound: true,
  provider_request_response_digests_bound: true,
  missing_and_extra_fields_rejected: true,
  tampering_and_replay_rejected: true,
  raw_prompt_response_and_secrets_omitted: true,
  provider_call_verified: false,
  hostile_runtime_isolation_verified: false,
  real_runtime_process_spawned: false,
  executor_receipt_integrated: false,
})}\n`);
