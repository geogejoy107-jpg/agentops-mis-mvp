#!/usr/bin/env node

import {
  createPrivateKey,
  createPublicKey,
  sign,
  verify,
} from "node:crypto";

export const RUNTIME_RECEIPT_SCHEMA = "agentops_openclaw_runtime_receipt_v1";
export const RUNTIME_RECEIPT_ALGORITHM = "Ed25519";
export const MAX_RUNTIME_RECEIPT_BYTES = 16 * 1024;

const BODY_FIELDS = Object.freeze([
  "argv_confidentiality",
  "cgroup_id",
  "deadline_monotonic_ns",
  "descendants_cleanup_verified",
  "executor_image_digest",
  "executor_key_id",
  "exit_code",
  "exit_kind",
  "finished_monotonic_ns",
  "isolation_policy_sha256",
  "nonce",
  "private_peer_uid",
  "prompt_sha256",
  "provider_call_verified",
  "public_peer_uid",
  "receipt_id",
  "request_id",
  "result_sha256",
  "run_id",
  "runtime_gid",
  "runtime_manifest_sha256",
  "runtime_process_spawned",
  "runtime_uid",
  "started_monotonic_ns",
  "termination_signal",
  "workspace_id_hash",
]);
const ENVELOPE_FIELDS = Object.freeze(["algorithm", "body", "key_id", "schema", "signature"]);
const EXPECTED_FIELDS = Object.freeze([
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
]);
const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const SAFE_TOKEN_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const MONOTONIC_PATTERN = /^(?:0|[1-9][0-9]{0,19})$/;

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function plainObject(value, code) {
  if (
    !value
    || typeof value !== "object"
    || Array.isArray(value)
    || Object.getPrototypeOf(value) !== Object.prototype
  ) fail(code);
  return value;
}

function exactFields(value, expected, code) {
  const actual = Object.keys(value).sort();
  if (actual.length !== expected.length || actual.some((name, index) => name !== expected[index])) {
    fail(code);
  }
}

function canonicalValue(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) fail("runtime_receipt_canonical_number_invalid");
    return value;
  }
  if (Array.isArray(value)) return value.map(canonicalValue);
  const object = plainObject(value, "runtime_receipt_canonical_object_invalid");
  return Object.fromEntries(
    Object.keys(object).sort().map((name) => [name, canonicalValue(object[name])]),
  );
}

export function canonicalRuntimeReceiptBytes(value) {
  return Buffer.from(JSON.stringify(canonicalValue(value)), "utf8");
}

function receiptBytes(value) {
  if (!(Buffer.isBuffer(value) || value instanceof Uint8Array)) {
    fail("runtime_receipt_bytes_required");
  }
  const bytes = Buffer.from(value);
  if (bytes.byteLength < 2 || bytes.byteLength > MAX_RUNTIME_RECEIPT_BYTES) {
    fail("runtime_receipt_size_invalid");
  }
  return bytes;
}

export function parseCanonicalRuntimeReceiptEnvelope(value) {
  const bytes = receiptBytes(value);
  let envelope;
  try {
    envelope = JSON.parse(bytes.toString("utf8"));
  } catch {
    fail("runtime_receipt_json_invalid");
  }
  const object = plainObject(envelope, "runtime_receipt_envelope_invalid");
  exactFields(object, ENVELOPE_FIELDS, "runtime_receipt_envelope_fields_invalid");
  if (
    typeof object.algorithm !== "string"
    || typeof object.key_id !== "string"
    || typeof object.schema !== "string"
    || typeof object.signature !== "string"
  ) fail("runtime_receipt_envelope_shape_invalid");
  validateRuntimeReceiptBody(object.body);
  const canonical = canonicalRuntimeReceiptBytes(envelope);
  if (!bytes.equals(canonical)) fail("runtime_receipt_encoding_noncanonical");
  return envelope;
}

function sha256(value, label) {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) fail(`${label}_invalid`);
}

function token(value, label) {
  if (typeof value !== "string" || !SAFE_TOKEN_PATTERN.test(value)) fail(`${label}_invalid`);
}

function uid(value, expected, label) {
  if (!Number.isSafeInteger(value) || value !== expected) fail(`${label}_invalid`);
}

function monotonic(value, label) {
  if (typeof value !== "string" || !MONOTONIC_PATTERN.test(value)) fail(`${label}_invalid`);
  return BigInt(value);
}

export function validateRuntimeReceiptBody(value) {
  const body = plainObject(value, "runtime_receipt_body_invalid");
  exactFields(body, BODY_FIELDS, "runtime_receipt_body_fields_invalid");
  token(body.receipt_id, "runtime_receipt_id");
  token(body.request_id, "runtime_receipt_request_id");
  token(body.run_id, "runtime_receipt_run_id");
  token(body.nonce, "runtime_receipt_nonce");
  token(body.cgroup_id, "runtime_receipt_cgroup_id");
  token(body.executor_key_id, "runtime_receipt_executor_key_id");
  sha256(body.workspace_id_hash, "runtime_receipt_workspace_id_hash");
  sha256(body.prompt_sha256, "runtime_receipt_prompt_sha256");
  sha256(body.result_sha256, "runtime_receipt_result_sha256");
  sha256(body.runtime_manifest_sha256, "runtime_receipt_manifest_sha256");
  sha256(body.isolation_policy_sha256, "runtime_receipt_isolation_policy_sha256");
  if (
    typeof body.executor_image_digest !== "string"
    || !/^sha256:[a-f0-9]{64}$/.test(body.executor_image_digest)
  ) fail("runtime_receipt_executor_image_digest_invalid");
  uid(body.runtime_uid, 1200, "runtime_receipt_runtime_uid");
  uid(body.runtime_gid, 1200, "runtime_receipt_runtime_gid");
  uid(body.public_peer_uid, 1000, "runtime_receipt_public_peer_uid");
  uid(body.private_peer_uid, 1100, "runtime_receipt_private_peer_uid");
  const started = monotonic(body.started_monotonic_ns, "runtime_receipt_started_monotonic_ns");
  const finished = monotonic(body.finished_monotonic_ns, "runtime_receipt_finished_monotonic_ns");
  const deadline = monotonic(body.deadline_monotonic_ns, "runtime_receipt_deadline_monotonic_ns");
  if (!(started < finished && finished <= deadline)) fail("runtime_receipt_monotonic_order_invalid");
  if (body.exit_kind !== "completed" || body.exit_code !== 0 || body.termination_signal !== null) {
    fail("runtime_receipt_terminal_state_invalid");
  }
  if (body.descendants_cleanup_verified !== true) fail("runtime_receipt_cleanup_unverified");
  if (body.runtime_process_spawned !== true) fail("runtime_receipt_process_unverified");
  if (body.argv_confidentiality !== false) fail("runtime_receipt_argv_claim_invalid");
  if (body.provider_call_verified !== false) fail("runtime_receipt_provider_claim_invalid");
  return body;
}

function unsignedEnvelope(body, keyId) {
  return {
    algorithm: RUNTIME_RECEIPT_ALGORITHM,
    body,
    key_id: keyId,
    schema: RUNTIME_RECEIPT_SCHEMA,
  };
}

function ed25519PrivateKey(value) {
  let key;
  try {
    key = value?.type === "private" ? value : createPrivateKey(value);
  } catch {
    fail("runtime_receipt_private_key_invalid");
  }
  if (key.type !== "private" || key.asymmetricKeyType !== "ed25519") {
    fail("runtime_receipt_private_key_invalid");
  }
  return key;
}

function ed25519PublicKey(value) {
  let key;
  try {
    key = value?.type === "public" ? value : createPublicKey(value);
  } catch {
    fail("runtime_receipt_public_key_invalid");
  }
  if (key.type !== "public" || key.asymmetricKeyType !== "ed25519") {
    fail("runtime_receipt_public_key_invalid");
  }
  return key;
}

export function signRuntimeReceipt(bodyValue, keyId, privateKey) {
  const body = validateRuntimeReceiptBody(bodyValue);
  token(keyId, "runtime_receipt_key_id");
  if (keyId !== body.executor_key_id) fail("runtime_receipt_key_id_mismatch");
  let signature;
  try {
    signature = sign(
      null,
      canonicalRuntimeReceiptBytes(unsignedEnvelope(body, keyId)),
      ed25519PrivateKey(privateKey),
    );
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("runtime_receipt_")) throw error;
    fail("runtime_receipt_signing_failed");
  }
  if (signature.byteLength !== 64) fail("runtime_receipt_signature_invalid");
  return {
    ...unsignedEnvelope(body, keyId),
    signature: signature.toString("base64url"),
  };
}

export function serializeRuntimeReceiptEnvelope(envelopeValue) {
  const envelope = plainObject(envelopeValue, "runtime_receipt_envelope_invalid");
  exactFields(envelope, ENVELOPE_FIELDS, "runtime_receipt_envelope_fields_invalid");
  const bytes = canonicalRuntimeReceiptBytes(envelope);
  if (bytes.byteLength > MAX_RUNTIME_RECEIPT_BYTES) fail("runtime_receipt_size_invalid");
  return bytes;
}

function pinnedKey(keys, keyId) {
  if (keys instanceof Map) return keys.get(keyId);
  const object = plainObject(keys, "runtime_receipt_trust_roots_invalid");
  return Object.hasOwn(object, keyId) ? object[keyId] : undefined;
}

export function verifyRuntimeReceipt(envelopeValue, trustRoots, expectedValue, replayCache) {
  const envelope = plainObject(envelopeValue, "runtime_receipt_envelope_invalid");
  exactFields(envelope, ENVELOPE_FIELDS, "runtime_receipt_envelope_fields_invalid");
  if (envelope.schema !== RUNTIME_RECEIPT_SCHEMA) fail("runtime_receipt_schema_invalid");
  if (envelope.algorithm !== RUNTIME_RECEIPT_ALGORITHM) fail("runtime_receipt_algorithm_invalid");
  token(envelope.key_id, "runtime_receipt_key_id");
  if (typeof envelope.signature !== "string" || !/^[A-Za-z0-9_-]{86}$/.test(envelope.signature)) {
    fail("runtime_receipt_signature_invalid");
  }
  const body = validateRuntimeReceiptBody(envelope.body);
  if (envelope.key_id !== body.executor_key_id) fail("runtime_receipt_key_id_mismatch");
  const expected = plainObject(expectedValue, "runtime_receipt_expected_bindings_invalid");
  exactFields(expected, EXPECTED_FIELDS, "runtime_receipt_expected_bindings_invalid");
  for (const name of EXPECTED_FIELDS) {
    if (name === "verification_monotonic_ns") continue;
    if (body[name] !== expected[name]) fail(`runtime_receipt_${name}_mismatch`);
  }
  const verificationTime = monotonic(
    expected.verification_monotonic_ns,
    "runtime_receipt_verification_monotonic_ns",
  );
  if (
    verificationTime < BigInt(body.finished_monotonic_ns)
    || verificationTime > BigInt(body.deadline_monotonic_ns)
  ) fail("runtime_receipt_verification_time_invalid");
  if (!(replayCache instanceof Set)) fail("runtime_receipt_replay_cache_required");
  const receiptReplayKey = `receipt:${body.receipt_id}`;
  const nonceReplayKey = `nonce:${body.nonce}`;
  if (replayCache.has(receiptReplayKey) || replayCache.has(nonceReplayKey)) {
    fail("runtime_receipt_replayed");
  }
  const publicKey = pinnedKey(trustRoots, envelope.key_id);
  if (!publicKey) fail("runtime_receipt_unknown_key");
  let signature;
  try {
    signature = Buffer.from(envelope.signature, "base64url");
  } catch {
    fail("runtime_receipt_signature_invalid");
  }
  if (signature.toString("base64url") !== envelope.signature) {
    fail("runtime_receipt_signature_invalid");
  }
  let verified = false;
  try {
    verified = signature.byteLength === 64 && verify(
      null,
      canonicalRuntimeReceiptBytes(unsignedEnvelope(body, envelope.key_id)),
      ed25519PublicKey(publicKey),
      signature,
    );
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("runtime_receipt_")) throw error;
    fail("runtime_receipt_signature_unverified");
  }
  if (
    !verified
  ) fail("runtime_receipt_signature_unverified");
  replayCache.add(receiptReplayKey);
  replayCache.add(nonceReplayKey);
  return Object.freeze({ ...body });
}

export function verifyCanonicalRuntimeReceipt(value, trustRoots, expectedValue, replayCache) {
  return verifyRuntimeReceipt(
    parseCanonicalRuntimeReceiptEnvelope(value),
    trustRoots,
    expectedValue,
    replayCache,
  );
}
