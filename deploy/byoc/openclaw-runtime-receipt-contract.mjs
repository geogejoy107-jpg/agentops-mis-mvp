#!/usr/bin/env node

import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import {
  canonicalRuntimeReceiptBytes,
  MAX_RUNTIME_RECEIPT_BYTES,
  serializeRuntimeReceiptEnvelope,
  signRuntimeReceipt,
  verifyCanonicalRuntimeReceipt,
} from "./openclaw-runtime-receipt.mjs";

const digest = (character) => character.repeat(64);
const body = {
  receipt_id: "rtr_contract_001",
  request_id: "req_contract_001",
  workspace_id_hash: digest("1"),
  run_id: "run_gw_contract_001",
  nonce: "nonce_contract_001",
  prompt_sha256: digest("2"),
  result_sha256: digest("3"),
  runtime_manifest_sha256: digest("4"),
  executor_image_digest: `sha256:${digest("5")}`,
  executor_key_id: "executor-contract-key-1",
  runtime_uid: 1200,
  runtime_gid: 1200,
  public_peer_uid: 1000,
  private_peer_uid: 1100,
  cgroup_id: "agentops-openclaw-contract-001",
  isolation_policy_sha256: digest("6"),
  started_monotonic_ns: "1000000000",
  finished_monotonic_ns: "2000000000",
  deadline_monotonic_ns: "3000000000",
  exit_kind: "completed",
  exit_code: 0,
  termination_signal: null,
  descendants_cleanup_verified: true,
  runtime_process_spawned: true,
  argv_confidentiality: false,
  provider_call_verified: false,
};
const expected = Object.fromEntries([
  "cgroup_id",
  "deadline_monotonic_ns",
  "executor_image_digest",
  "executor_key_id",
  "isolation_policy_sha256",
  "nonce",
  "private_peer_uid",
  "prompt_sha256",
  "public_peer_uid",
  "request_id",
  "result_sha256",
  "run_id",
  "runtime_gid",
  "runtime_manifest_sha256",
  "runtime_uid",
  "verification_monotonic_ns",
  "workspace_id_hash",
].map((name) => [name, name === "verification_monotonic_ns" ? "2500000000" : body[name]]));
const primary = generateKeyPairSync("ed25519");
const other = generateKeyPairSync("ed25519");
const wrongAlgorithm = generateKeyPairSync("rsa", { modulusLength: 2048 });
const envelope = signRuntimeReceipt(body, body.executor_key_id, primary.privateKey);
const envelopeBytes = serializeRuntimeReceiptEnvelope(envelope);
const roots = new Map([[body.executor_key_id, primary.publicKey]]);

assert.deepEqual(
  canonicalRuntimeReceiptBytes({ z: 1, a: { y: false, b: "value" } }),
  Buffer.from('{"a":{"b":"value","y":false},"z":1}'),
);
const verified = verifyCanonicalRuntimeReceipt(envelopeBytes, roots, expected, new Set());
assert.equal(verified.receipt_id, body.receipt_id);
assert.equal(verified.runtime_process_spawned, true);
assert.equal(verified.provider_call_verified, false);

const replayCache = new Set();
verifyCanonicalRuntimeReceipt(envelopeBytes, roots, expected, replayCache);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(envelopeBytes, roots, expected, replayCache),
  /runtime_receipt_replayed/,
);
const sameNonceEnvelope = signRuntimeReceipt(
  { ...body, receipt_id: "rtr_contract_002" },
  body.executor_key_id,
  primary.privateKey,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    serializeRuntimeReceiptEnvelope(sameNonceEnvelope),
    roots,
    expected,
    replayCache,
  ),
  /runtime_receipt_replayed/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(envelopeBytes, new Map(), expected, new Set()),
  /runtime_receipt_unknown_key/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(envelopeBytes, new Map([[body.executor_key_id, other.publicKey]]), expected, new Set()),
  /runtime_receipt_signature_unverified/,
);
const finalSignatureCharacter = envelope.signature.at(-1);
const alternateFinalCharacter = finalSignatureCharacter === "A" ? "B" : "A";
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    serializeRuntimeReceiptEnvelope({
      ...envelope,
      signature: `${envelope.signature.slice(0, -1)}${alternateFinalCharacter}`,
    }),
    roots,
    expected,
    new Set(),
  ),
  /runtime_receipt_signature_(?:invalid|unverified)/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(envelopeBytes, { [body.executor_key_id]: "not-a-public-key" }, expected, new Set()),
  /runtime_receipt_public_key_invalid/,
);
assert.throws(
  () => signRuntimeReceipt(body, body.executor_key_id, wrongAlgorithm.privateKey),
  /runtime_receipt_private_key_invalid/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    envelopeBytes,
    new Map([[body.executor_key_id, wrongAlgorithm.publicKey]]),
    expected,
    new Set(),
  ),
  /runtime_receipt_public_key_invalid/,
);

for (const [name, value, failure] of [
  ["runtime_uid", 1001, "runtime_receipt_runtime_uid_invalid"],
  ["private_peer_uid", 1001, "runtime_receipt_private_peer_uid_invalid"],
  ["descendants_cleanup_verified", false, "runtime_receipt_cleanup_unverified"],
  ["runtime_process_spawned", false, "runtime_receipt_process_unverified"],
  ["argv_confidentiality", true, "runtime_receipt_argv_claim_invalid"],
  ["provider_call_verified", true, "runtime_receipt_provider_claim_invalid"],
  ["finished_monotonic_ns", "4000000000", "runtime_receipt_monotonic_order_invalid"],
]) {
  assert.throws(
    () => signRuntimeReceipt({ ...body, [name]: value }, body.executor_key_id, primary.privateKey),
    new RegExp(failure),
  );
}

const tamperedBody = { ...envelope.body, result_sha256: digest("7") };
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    serializeRuntimeReceiptEnvelope({ ...envelope, body: tamperedBody }),
    roots,
    { ...expected, result_sha256: digest("7") },
    new Set(),
  ),
  /runtime_receipt_signature_unverified/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(envelopeBytes, roots, { ...expected, nonce: "different_nonce" }, new Set()),
  /runtime_receipt_nonce_mismatch/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    envelopeBytes,
    roots,
    { ...expected, cgroup_id: "different-cgroup" },
    new Set(),
  ),
  /runtime_receipt_cgroup_id_mismatch/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    envelopeBytes,
    roots,
    { ...expected, deadline_monotonic_ns: "3000000001" },
    new Set(),
  ),
  /runtime_receipt_deadline_monotonic_ns_mismatch/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    envelopeBytes,
    roots,
    { ...expected, verification_monotonic_ns: "3000000001" },
    new Set(),
  ),
  /runtime_receipt_verification_time_invalid/,
);
assert.throws(
  () => signRuntimeReceipt({ ...body, raw_prompt: "forbidden" }, body.executor_key_id, primary.privateKey),
  /runtime_receipt_body_fields_invalid/,
);
assert.throws(
  () => signRuntimeReceipt({ ...body, raw_response: "forbidden" }, body.executor_key_id, primary.privateKey),
  /runtime_receipt_body_fields_invalid/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    canonicalRuntimeReceiptBytes({ ...envelope, unknown: true }),
    roots,
    expected,
    new Set(),
  ),
  /runtime_receipt_envelope_fields_invalid/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(Buffer.from(` ${envelopeBytes.toString("utf8")}`), roots, expected, new Set()),
  /runtime_receipt_encoding_noncanonical/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    Buffer.from(envelopeBytes.toString("utf8").replace(
      '"algorithm":"Ed25519"',
      '"algorithm":"Ed25519","algorithm":"Ed25519"',
    )),
    roots,
    expected,
    new Set(),
  ),
  /runtime_receipt_encoding_noncanonical/,
);
assert.throws(
  () => verifyCanonicalRuntimeReceipt(Buffer.alloc(MAX_RUNTIME_RECEIPT_BYTES + 1, 0x20), roots, expected, new Set()),
  /runtime_receipt_size_invalid/,
);
const deeplyNested = `${"[".repeat(3_000)}0${"]".repeat(3_000)}`;
assert.throws(
  () => verifyCanonicalRuntimeReceipt(
    Buffer.from(`{"algorithm":"Ed25519","body":${deeplyNested},"key_id":"key","schema":"schema","signature":"signature"}`),
    roots,
    expected,
    new Set(),
  ),
  /runtime_receipt_body_invalid/,
);

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_runtime_receipt_primitive_a06_v1",
  canonical_encoding_verified: true,
  canonical_wire_encoding_verified: true,
  duplicate_json_key_rejected: true,
  oversized_envelope_rejected: true,
  ed25519_signature_verified: true,
  pinned_executor_key_verified: true,
  complete_expected_bindings_verified: true,
  bounded_in_process_receipt_and_nonce_replay_rejected: true,
  expired_deadline_rejected: true,
  deep_structure_rejected_before_canonicalization: true,
  tamper_rejected: true,
  noncanonical_signature_rejected: true,
  malformed_trust_root_rejected: true,
  non_ed25519_keys_rejected: true,
  wrong_runtime_identity_rejected: true,
  incomplete_cleanup_rejected: true,
  raw_prompt_response_omitted: true,
  provider_call_verified: false,
  real_runtime_process_spawned: false,
  runtime_receipt_verified: false,
  hostile_runtime_isolation_verified: false,
})}\n`);
