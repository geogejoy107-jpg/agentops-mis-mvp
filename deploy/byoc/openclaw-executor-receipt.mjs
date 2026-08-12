#!/usr/bin/env node

import {
  createPrivateKey,
  createPublicKey,
  sign,
  verify,
} from "node:crypto";
import {
  EXECUTOR_DISPATCH_ENVELOPE_SCHEMA,
  EXECUTOR_PUBLIC_REQUEST_SCHEMA,
} from "./openclaw-executor-protocol.mjs";

export const EXECUTOR_RECEIPT_SCHEMA = "agentops_openclaw_executor_receipt_v1";
export const EXECUTOR_RECEIPT_ALGORITHM = "Ed25519";
export const MAX_EXECUTOR_RECEIPT_BYTES = 32 * 1024;

const BODY_FIELDS = Object.freeze([
  "agent_name",
  "boot_id",
  "cgroup",
  "deadline_boottime_ns",
  "descendants_cleanup_verified",
  "executor_image_digest",
  "executor_key_id",
  "exit_code",
  "exit_kind",
  "finished_boottime_ns",
  "hostile_runtime_isolation_verified",
  "isolation_policy_sha256",
  "launcher",
  "nonce",
  "private_dispatch_schema",
  "private_dispatch_sha256",
  "process",
  "prompt_sha256",
  "provider",
  "provider_call_verified",
  "public_request_schema",
  "public_request_sha256",
  "raw_prompt_omitted",
  "raw_response_omitted",
  "receipt_id",
  "request_id",
  "run_id",
  "runtime_image_digest",
  "runtime_manifest_sha256",
  "secrets_omitted",
  "seccomp_profile_sha256",
  "started_boottime_ns",
  "termination_signal",
  "timeout",
  "workspace_id_hash",
].sort());
const CGROUP_FIELDS = Object.freeze([
  "cgroup_id",
  "device",
  "inode",
  "limits",
  "process_entry_verified",
  "root_device",
  "root_inode",
].sort());
const LIMIT_FIELDS = Object.freeze([
  "cpu_max",
  "io_max",
  "memory_max_bytes",
  "memory_swap_max_bytes",
  "pids_max",
].sort());
const LAUNCHER_FIELDS = Object.freeze([
  "binary_sha256",
  "device",
  "inode",
  "invoked",
  "no_new_privs_applied",
  "runtime_gid",
  "runtime_uid",
  "seccomp_applied",
].sort());
const PROCESS_FIELDS = Object.freeze(["pid", "spawned"].sort());
const PROVIDER_FIELDS = Object.freeze([
  "call_observed",
  "request_sha256",
  "response_complete",
  "response_sha256",
].sort());
const TIMEOUT_FIELDS = Object.freeze(["enforced", "expired"].sort());
const ENVELOPE_FIELDS = Object.freeze(["algorithm", "body", "key_id", "schema", "signature"].sort());
const EXPECTED_FIELDS = Object.freeze([
  "agent_name",
  "boot_id",
  "cgroup",
  "deadline_boottime_ns",
  "executor_image_digest",
  "executor_key_id",
  "isolation_policy_sha256",
  "launcher",
  "nonce",
  "private_dispatch_schema",
  "private_dispatch_sha256",
  "prompt_sha256",
  "provider_request_sha256",
  "public_request_schema",
  "public_request_sha256",
  "request_id",
  "run_id",
  "runtime_image_digest",
  "runtime_manifest_sha256",
  "seccomp_profile_sha256",
  "verification_boottime_ns",
  "workspace_id_hash",
].sort());

const SHA256 = /^[a-f0-9]{64}$/;
const IMAGE_DIGEST = /^sha256:[a-f0-9]{64}$/;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const BOOT_ID = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
const DECIMAL = /^(?:0|[1-9][0-9]{0,19})$/;
const POSITIVE_DECIMAL = /^[1-9][0-9]{0,19}$/;
const CPU_MAX = /^(?:max|[1-9][0-9]{0,18}) [1-9][0-9]{0,18}$/;
const IO_MAX = /^[0-9]+:[0-9]+ (?:rbps|wbps|riops|wiops)=(?:max|[1-9][0-9]{0,18})(?: (?:rbps|wbps|riops|wiops)=(?:max|[1-9][0-9]{0,18})){0,3}$/;
const UINT64_MAX = 18_446_744_073_709_551_615n;
const EXIT_KINDS = new Set(["completed", "failed", "launch_failed", "signaled", "timed_out"]);

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function plainObject(value, code) {
  if (
    value === null
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
    if (!Number.isSafeInteger(value)) fail("executor_receipt_canonical_number_invalid");
    return value;
  }
  if (Array.isArray(value)) return value.map(canonicalValue);
  const object = plainObject(value, "executor_receipt_canonical_object_invalid");
  return Object.fromEntries(
    Object.keys(object).sort().map((name) => [name, canonicalValue(object[name])]),
  );
}

export function canonicalExecutorReceiptBytes(value) {
  return Buffer.from(JSON.stringify(canonicalValue(value)), "utf8");
}

function token(value, label) {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(`${label}_invalid`);
  return value;
}

function sha256(value, label) {
  if (typeof value !== "string" || !SHA256.test(value)) fail(`${label}_invalid`);
  return value;
}

function imageDigest(value, label) {
  if (typeof value !== "string" || !IMAGE_DIGEST.test(value)) fail(`${label}_invalid`);
  return value;
}

function decimal(value, label, { positive = false } = {}) {
  const pattern = positive ? POSITIVE_DECIMAL : DECIMAL;
  if (typeof value !== "string" || !pattern.test(value)) fail(`${label}_invalid`);
  const parsed = BigInt(value);
  if (parsed > UINT64_MAX) fail(`${label}_invalid`);
  return parsed;
}

function boolean(value, expected, label) {
  if (typeof value !== "boolean" || (expected !== undefined && value !== expected)) {
    fail(`${label}_invalid`);
  }
}

function validateLimits(value) {
  const limits = plainObject(value, "executor_receipt_cgroup_limits_invalid");
  exactFields(limits, LIMIT_FIELDS, "executor_receipt_cgroup_limit_fields_invalid");
  decimal(limits.pids_max, "executor_receipt_cgroup_pids_max", { positive: true });
  decimal(limits.memory_max_bytes, "executor_receipt_cgroup_memory_max", { positive: true });
  decimal(limits.memory_swap_max_bytes, "executor_receipt_cgroup_memory_swap_max");
  if (typeof limits.cpu_max !== "string" || !CPU_MAX.test(limits.cpu_max)) {
    fail("executor_receipt_cgroup_cpu_max_invalid");
  }
  if (typeof limits.io_max !== "string" || !IO_MAX.test(limits.io_max)) {
    fail("executor_receipt_cgroup_io_max_invalid");
  }
  return limits;
}

function validateCgroup(value) {
  const cgroup = plainObject(value, "executor_receipt_cgroup_invalid");
  exactFields(cgroup, CGROUP_FIELDS, "executor_receipt_cgroup_fields_invalid");
  token(cgroup.cgroup_id, "executor_receipt_cgroup_id");
  decimal(cgroup.root_device, "executor_receipt_cgroup_root_device");
  decimal(cgroup.root_inode, "executor_receipt_cgroup_root_inode", { positive: true });
  decimal(cgroup.device, "executor_receipt_cgroup_device");
  decimal(cgroup.inode, "executor_receipt_cgroup_inode", { positive: true });
  boolean(cgroup.process_entry_verified, undefined, "executor_receipt_cgroup_process_entry_verified");
  validateLimits(cgroup.limits);
  return cgroup;
}

function validateLauncher(value) {
  const launcher = plainObject(value, "executor_receipt_launcher_invalid");
  exactFields(launcher, LAUNCHER_FIELDS, "executor_receipt_launcher_fields_invalid");
  sha256(launcher.binary_sha256, "executor_receipt_launcher_sha256");
  decimal(launcher.device, "executor_receipt_launcher_device");
  decimal(launcher.inode, "executor_receipt_launcher_inode", { positive: true });
  boolean(launcher.invoked, undefined, "executor_receipt_launcher_invoked");
  boolean(launcher.no_new_privs_applied, undefined, "executor_receipt_launcher_no_new_privs");
  boolean(launcher.seccomp_applied, undefined, "executor_receipt_launcher_seccomp");
  if (launcher.runtime_uid !== 1200 || launcher.runtime_gid !== 1200) {
    fail("executor_receipt_launcher_runtime_identity_invalid");
  }
  return launcher;
}

function validateProcess(value) {
  const process = plainObject(value, "executor_receipt_process_invalid");
  exactFields(process, PROCESS_FIELDS, "executor_receipt_process_fields_invalid");
  boolean(process.spawned, undefined, "executor_receipt_process_spawned");
  if (process.spawned) {
    if (!Number.isSafeInteger(process.pid) || process.pid < 1 || process.pid > 4_194_304) {
      fail("executor_receipt_process_pid_invalid");
    }
  } else if (process.pid !== null) {
    fail("executor_receipt_process_pid_invalid");
  }
  return process;
}

function validateProvider(value) {
  const provider = plainObject(value, "executor_receipt_provider_invalid");
  exactFields(provider, PROVIDER_FIELDS, "executor_receipt_provider_fields_invalid");
  boolean(provider.call_observed, undefined, "executor_receipt_provider_call_observed");
  sha256(provider.request_sha256, "executor_receipt_provider_request_sha256");
  boolean(provider.response_complete, undefined, "executor_receipt_provider_response_complete");
  if (provider.response_complete) {
    if (!provider.call_observed) fail("executor_receipt_provider_state_invalid");
    sha256(provider.response_sha256, "executor_receipt_provider_response_sha256");
  } else if (provider.response_sha256 !== null) {
    fail("executor_receipt_provider_response_sha256_invalid");
  }
  return provider;
}

function validateTimeout(value) {
  const timeout = plainObject(value, "executor_receipt_timeout_invalid");
  exactFields(timeout, TIMEOUT_FIELDS, "executor_receipt_timeout_fields_invalid");
  boolean(timeout.enforced, true, "executor_receipt_timeout_enforced");
  boolean(timeout.expired, undefined, "executor_receipt_timeout_expired");
  return timeout;
}

function validateTerminalState(body, started, finished, deadline) {
  if (!EXIT_KINDS.has(body.exit_kind)) fail("executor_receipt_exit_kind_invalid");
  if (!(started < finished)) fail("executor_receipt_boottime_order_invalid");
  if (body.exit_kind === "timed_out") {
    if (!body.process.spawned || !body.timeout.expired || finished < deadline) {
      fail("executor_receipt_timeout_state_invalid");
    }
    if (body.exit_code !== null || !Number.isSafeInteger(body.termination_signal)) {
      fail("executor_receipt_terminal_state_invalid");
    }
  } else {
    if (body.timeout.expired || finished > deadline) fail("executor_receipt_timeout_state_invalid");
    if (body.exit_kind === "completed") {
      if (
        !body.process.spawned
        || body.exit_code !== 0
        || body.termination_signal !== null
        || !body.provider.response_complete
      ) fail("executor_receipt_terminal_state_invalid");
    } else if (body.exit_kind === "failed") {
      if (
        !body.process.spawned
        || !Number.isSafeInteger(body.exit_code)
        || body.exit_code < 1
        || body.exit_code > 255
        || body.termination_signal !== null
      ) fail("executor_receipt_terminal_state_invalid");
    } else if (body.exit_kind === "signaled") {
      if (!body.process.spawned || body.exit_code !== null || !Number.isSafeInteger(body.termination_signal)) {
        fail("executor_receipt_terminal_state_invalid");
      }
    } else if (body.exit_kind === "launch_failed") {
      if (
        body.process.spawned
        || body.exit_code !== null
        || body.termination_signal !== null
        || body.provider.call_observed
        || body.provider.response_complete
      ) fail("executor_receipt_terminal_state_invalid");
    }
  }
  if (
    body.termination_signal !== null
    && (!Number.isSafeInteger(body.termination_signal) || body.termination_signal < 1 || body.termination_signal > 64)
  ) fail("executor_receipt_termination_signal_invalid");
}

export function validateExecutorReceiptBody(value) {
  const body = plainObject(value, "executor_receipt_body_invalid");
  exactFields(body, BODY_FIELDS, "executor_receipt_body_fields_invalid");
  token(body.receipt_id, "executor_receipt_id");
  token(body.executor_key_id, "executor_receipt_executor_key_id");
  token(body.request_id, "executor_receipt_request_id");
  token(body.run_id, "executor_receipt_run_id");
  token(body.agent_name, "executor_receipt_agent_name");
  token(body.nonce, "executor_receipt_nonce");
  token(body.public_request_schema, "executor_receipt_public_request_schema");
  token(body.private_dispatch_schema, "executor_receipt_private_dispatch_schema");
  if (body.public_request_schema !== EXECUTOR_PUBLIC_REQUEST_SCHEMA) {
    fail("executor_receipt_public_request_schema_invalid");
  }
  if (body.private_dispatch_schema !== EXECUTOR_DISPATCH_ENVELOPE_SCHEMA) {
    fail("executor_receipt_private_dispatch_schema_invalid");
  }
  if (typeof body.boot_id !== "string" || !BOOT_ID.test(body.boot_id)) {
    fail("executor_receipt_boot_id_invalid");
  }
  for (const [name, label] of [
    ["workspace_id_hash", "workspace_id_hash"],
    ["prompt_sha256", "prompt_sha256"],
    ["public_request_sha256", "public_request_sha256"],
    ["private_dispatch_sha256", "private_dispatch_sha256"],
    ["runtime_manifest_sha256", "runtime_manifest_sha256"],
    ["isolation_policy_sha256", "isolation_policy_sha256"],
    ["seccomp_profile_sha256", "seccomp_profile_sha256"],
  ]) sha256(body[name], `executor_receipt_${label}`);
  imageDigest(body.executor_image_digest, "executor_receipt_executor_image_digest");
  imageDigest(body.runtime_image_digest, "executor_receipt_runtime_image_digest");
  const started = decimal(body.started_boottime_ns, "executor_receipt_started_boottime_ns");
  const finished = decimal(body.finished_boottime_ns, "executor_receipt_finished_boottime_ns");
  const deadline = decimal(body.deadline_boottime_ns, "executor_receipt_deadline_boottime_ns");
  validateCgroup(body.cgroup);
  validateLauncher(body.launcher);
  validateProcess(body.process);
  validateProvider(body.provider);
  validateTimeout(body.timeout);
  boolean(body.descendants_cleanup_verified, true, "executor_receipt_descendants_cleanup_verified");
  boolean(body.raw_prompt_omitted, true, "executor_receipt_raw_prompt_omitted");
  boolean(body.raw_response_omitted, true, "executor_receipt_raw_response_omitted");
  boolean(body.secrets_omitted, true, "executor_receipt_secrets_omitted");
  boolean(body.provider_call_verified, false, "executor_receipt_provider_call_verified");
  boolean(
    body.hostile_runtime_isolation_verified,
    false,
    "executor_receipt_hostile_runtime_isolation_verified",
  );
  if (body.process.spawned) {
    if (
      !body.launcher.invoked
      || !body.launcher.no_new_privs_applied
      || !body.launcher.seccomp_applied
      || !body.cgroup.process_entry_verified
    ) fail("executor_receipt_spawn_evidence_incomplete");
  } else if (body.cgroup.process_entry_verified) {
    fail("executor_receipt_spawn_evidence_invalid");
  }
  validateTerminalState(body, started, finished, deadline);
  return body;
}

function unsignedEnvelope(body, keyId) {
  return {
    algorithm: EXECUTOR_RECEIPT_ALGORITHM,
    body,
    key_id: keyId,
    schema: EXECUTOR_RECEIPT_SCHEMA,
  };
}

function ed25519PrivateKey(value) {
  let key;
  try {
    key = value?.type === "private" ? value : createPrivateKey(value);
  } catch {
    fail("executor_receipt_private_key_invalid");
  }
  if (key.type !== "private" || key.asymmetricKeyType !== "ed25519") {
    fail("executor_receipt_private_key_invalid");
  }
  return key;
}

function ed25519PublicKey(value) {
  let key;
  try {
    key = value?.type === "public" ? value : createPublicKey(value);
  } catch {
    fail("executor_receipt_public_key_invalid");
  }
  if (key.type !== "public" || key.asymmetricKeyType !== "ed25519") {
    fail("executor_receipt_public_key_invalid");
  }
  return key;
}

export function signExecutorReceipt(bodyValue, keyId, privateKey) {
  const body = validateExecutorReceiptBody(bodyValue);
  token(keyId, "executor_receipt_key_id");
  if (keyId !== body.executor_key_id) fail("executor_receipt_key_id_mismatch");
  let signature;
  try {
    signature = sign(
      null,
      canonicalExecutorReceiptBytes(unsignedEnvelope(body, keyId)),
      ed25519PrivateKey(privateKey),
    );
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("executor_receipt_")) throw error;
    fail("executor_receipt_signing_failed");
  }
  if (signature.byteLength !== 64) fail("executor_receipt_signature_invalid");
  return Object.freeze({
    ...unsignedEnvelope(body, keyId),
    signature: signature.toString("base64url"),
  });
}

export function serializeExecutorReceiptEnvelope(value) {
  const envelope = plainObject(value, "executor_receipt_envelope_invalid");
  exactFields(envelope, ENVELOPE_FIELDS, "executor_receipt_envelope_fields_invalid");
  const bytes = canonicalExecutorReceiptBytes(envelope);
  if (bytes.byteLength > MAX_EXECUTOR_RECEIPT_BYTES) fail("executor_receipt_size_invalid");
  return bytes;
}

function receiptBytes(value) {
  if (!(Buffer.isBuffer(value) || value instanceof Uint8Array)) {
    fail("executor_receipt_bytes_required");
  }
  const bytes = Buffer.from(value);
  if (bytes.byteLength < 2 || bytes.byteLength > MAX_EXECUTOR_RECEIPT_BYTES) {
    fail("executor_receipt_size_invalid");
  }
  return bytes;
}

export function parseCanonicalExecutorReceiptEnvelope(value) {
  const bytes = receiptBytes(value);
  let envelope;
  try {
    envelope = JSON.parse(new TextDecoder("utf8", { fatal: true }).decode(bytes));
  } catch {
    fail("executor_receipt_json_invalid");
  }
  const object = plainObject(envelope, "executor_receipt_envelope_invalid");
  exactFields(object, ENVELOPE_FIELDS, "executor_receipt_envelope_fields_invalid");
  validateExecutorReceiptBody(object.body);
  if (!bytes.equals(canonicalExecutorReceiptBytes(object))) {
    fail("executor_receipt_encoding_noncanonical");
  }
  return object;
}

function pinnedKey(keys, keyId) {
  if (keys instanceof Map) return keys.get(keyId);
  const object = plainObject(keys, "executor_receipt_trust_roots_invalid");
  return Object.hasOwn(object, keyId) ? object[keyId] : undefined;
}

function validateExpected(value) {
  const expected = plainObject(value, "executor_receipt_expected_bindings_invalid");
  exactFields(expected, EXPECTED_FIELDS, "executor_receipt_expected_bindings_invalid");
  decimal(expected.verification_boottime_ns, "executor_receipt_verification_boottime_ns");
  return expected;
}

function equalBinding(actual, expected) {
  return canonicalExecutorReceiptBytes(actual).equals(canonicalExecutorReceiptBytes(expected));
}

export function verifyExecutorReceipt(
  envelopeValue,
  trustRoots,
  expectedValue,
  replayCache,
  { commitReplay = true } = {},
) {
  const envelope = plainObject(envelopeValue, "executor_receipt_envelope_invalid");
  exactFields(envelope, ENVELOPE_FIELDS, "executor_receipt_envelope_fields_invalid");
  if (envelope.schema !== EXECUTOR_RECEIPT_SCHEMA) fail("executor_receipt_schema_invalid");
  if (envelope.algorithm !== EXECUTOR_RECEIPT_ALGORITHM) fail("executor_receipt_algorithm_invalid");
  token(envelope.key_id, "executor_receipt_key_id");
  if (typeof envelope.signature !== "string" || !/^[A-Za-z0-9_-]{86}$/.test(envelope.signature)) {
    fail("executor_receipt_signature_invalid");
  }
  const body = validateExecutorReceiptBody(envelope.body);
  if (envelope.key_id !== body.executor_key_id) fail("executor_receipt_key_id_mismatch");
  const expected = validateExpected(expectedValue);
  const bindings = [
    "agent_name",
    "boot_id",
    "cgroup",
    "deadline_boottime_ns",
    "executor_image_digest",
    "executor_key_id",
    "isolation_policy_sha256",
    "launcher",
    "nonce",
    "private_dispatch_schema",
    "private_dispatch_sha256",
    "prompt_sha256",
    "public_request_schema",
    "public_request_sha256",
    "request_id",
    "run_id",
    "runtime_image_digest",
    "runtime_manifest_sha256",
    "seccomp_profile_sha256",
    "workspace_id_hash",
  ];
  for (const name of bindings) {
    if (!equalBinding(body[name], expected[name])) fail(`executor_receipt_${name}_mismatch`);
  }
  if (!equalBinding(body.provider.request_sha256, expected.provider_request_sha256)) {
    fail("executor_receipt_provider_request_sha256_mismatch");
  }
  if (BigInt(expected.verification_boottime_ns) < BigInt(body.finished_boottime_ns)) {
    fail("executor_receipt_verification_time_invalid");
  }
  if (!(replayCache instanceof Set)) fail("executor_receipt_replay_cache_required");
  const receiptReplayKey = `receipt:${body.receipt_id}`;
  const nonceReplayKey = `nonce:${body.nonce}`;
  if (replayCache.has(receiptReplayKey) || replayCache.has(nonceReplayKey)) {
    fail("executor_receipt_replayed");
  }
  const publicKey = pinnedKey(trustRoots, envelope.key_id);
  if (!publicKey) fail("executor_receipt_unknown_key");
  let signature;
  try {
    signature = Buffer.from(envelope.signature, "base64url");
  } catch {
    fail("executor_receipt_signature_invalid");
  }
  if (signature.toString("base64url") !== envelope.signature) {
    fail("executor_receipt_signature_invalid");
  }
  let verified = false;
  try {
    verified = signature.byteLength === 64 && verify(
      null,
      canonicalExecutorReceiptBytes(unsignedEnvelope(body, envelope.key_id)),
      ed25519PublicKey(publicKey),
      signature,
    );
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("executor_receipt_")) throw error;
    fail("executor_receipt_signature_unverified");
  }
  if (!verified) fail("executor_receipt_signature_unverified");
  if (commitReplay) {
    replayCache.add(receiptReplayKey);
    replayCache.add(nonceReplayKey);
  }
  return Object.freeze({ ...body });
}

export function verifyCanonicalExecutorReceipt(value, trustRoots, expectedValue, replayCache) {
  return verifyExecutorReceipt(
    parseCanonicalExecutorReceiptEnvelope(value),
    trustRoots,
    expectedValue,
    replayCache,
  );
}
