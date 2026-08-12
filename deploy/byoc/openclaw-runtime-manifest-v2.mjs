#!/usr/bin/env node

import {
  createHash,
  createPrivateKey,
  createPublicKey,
  sign,
  verify,
} from "node:crypto";
import path from "node:path";

export const RUNTIME_MANIFEST_V2_SCHEMA = "agentops_openclaw_runtime_manifest_v2";
export const RUNTIME_MANIFEST_V2_ALGORITHM = "Ed25519";
export const RUNTIME_MANIFEST_V2_PATH_MODEL = "guest_root_absolute_v1";
export const MAX_RUNTIME_MANIFEST_V2_BYTES = 128 * 1024;

export const RUNTIME_MANIFEST_V2_ENVIRONMENT_NAMES = Object.freeze([
  "LANG",
  "OPENCLAW_CONFIG_PATH",
  "OPENCLAW_STATE_DIR",
  "OPENCLAW_WORKSPACE",
  "PATH",
]);

const fields = (...names) => Object.freeze([...names].sort());
const BODY_FIELDS = fields(
  "argv",
  "cgroup_policy_sha256",
  "claims",
  "created_at",
  "entrypoint",
  "environment_name_allowlist",
  "expires_at",
  "immutable_code_roots",
  "issuer",
  "key_id",
  "mutable_mounts",
  "oci_image",
  "path_model",
  "platform",
  "rootfs",
  "runtime_executable",
  "runtime_gid",
  "runtime_uid",
  "schema_semantics",
  "seccomp_profile_sha256",
);
const ENVELOPE_FIELDS = fields("algorithm", "body", "key_id", "schema", "signature");
const SCHEMA_SEMANTICS_FIELDS = fields(
  "artifact_kind",
  "identity_model",
  "manifest_version",
  "signature_scope",
);
const PLATFORM_FIELDS = fields("arch", "libc", "os");
const OCI_IMAGE_FIELDS = fields("digest", "name");
const ROOTFS_FIELDS = fields("byte_count", "file_count", "merkle_sha256");
const ARGV_FIELDS = fields("kind", "value");
const MUTABLE_MOUNT_FIELDS = fields("kind", "path", "read_only");
const CLAIM_FIELDS = fields(
  "guest_root_artifact_built",
  "guest_root_immutability_verified",
  "launcher_guest_root_handoff_verified",
  "real_openclaw_execution_verified",
  "runtime_path_toctou_closed",
);
const EXPECTED_FIELDS = fields(
  "body_sha256",
  "cgroup_policy_sha256",
  "entrypoint",
  "issuer",
  "key_id",
  "oci_image",
  "platform",
  "rootfs_merkle_sha256",
  "runtime_executable",
  "runtime_gid",
  "runtime_uid",
  "seccomp_profile_sha256",
  "verification_time",
);

const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const OCI_DIGEST_PATTERN = /^sha256:[a-f0-9]{64}$/;
const IMAGE_NAME_PATTERN = /^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]{1,5})?(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)+$/;
const TOKEN_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,255}$/;
const OPAQUE_ARG_PATTERN = /^[\x21-\x2e\x30-\x5b\x5d-\x7e]{1,4096}$/;
const SIGNATURE_PATTERN = /^[A-Za-z0-9_-]{86}$/;
const MAX_TIMESTAMP_WINDOW_MS = 31 * 24 * 60 * 60 * 1000;
const MAX_ROOTFS_FILES = 1_000_000;
const MAX_ROOTFS_BYTES = 16 * 1024 * 1024 * 1024;
const SUPPORTED_ARCHES = Object.freeze(new Set(["amd64", "arm64"]));
const REQUIRED_MOUNT_POLICY = Object.freeze({
  config_file: true,
  state_directory: false,
  temp_directory: false,
  workspace_directory: true,
});

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

function canonicalValue(value, depth = 0) {
  if (depth > 64) fail("runtime_manifest_v2_canonical_depth_invalid");
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value)) fail("runtime_manifest_v2_canonical_number_invalid");
    return value;
  }
  if (Array.isArray(value)) return value.map((item) => canonicalValue(item, depth + 1));
  const object = plainObject(value, "runtime_manifest_v2_canonical_object_invalid");
  return Object.fromEntries(
    Object.keys(object).sort().map((name) => [name, canonicalValue(object[name], depth + 1)]),
  );
}

export function canonicalRuntimeManifestV2Bytes(value) {
  return Buffer.from(JSON.stringify(canonicalValue(value)), "utf8");
}

function canonicalClone(value) {
  return JSON.parse(canonicalRuntimeManifestV2Bytes(value).toString("utf8"));
}

function manifestBytes(value) {
  if (!(Buffer.isBuffer(value) || value instanceof Uint8Array)) {
    fail("runtime_manifest_v2_bytes_required");
  }
  const bytes = Buffer.from(value);
  if (bytes.byteLength < 2 || bytes.byteLength > MAX_RUNTIME_MANIFEST_V2_BYTES) {
    fail("runtime_manifest_v2_size_invalid");
  }
  return bytes;
}

function token(value, label) {
  if (typeof value !== "string" || !TOKEN_PATTERN.test(value)) fail(`${label}_invalid`);
  return value;
}

function sha256(value, label) {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) fail(`${label}_invalid`);
  return value;
}

function positiveSafeInteger(value, maximum, label) {
  if (!Number.isSafeInteger(value) || value < 1 || value > maximum) fail(`${label}_invalid`);
  return value;
}

function absoluteGuestPath(value, label) {
  if (
    typeof value !== "string"
    || value.length < 2
    || value.length > 4096
    || !value.startsWith("/")
    || value.endsWith("/")
    || value.includes("\\")
    || value.includes("\0")
    || value.normalize("NFC") !== value
    || path.posix.normalize(value) !== value
  ) fail(`${label}_invalid`);
  const segments = value.slice(1).split("/");
  if (segments.some((segment) => (
    !segment
    || segment === "."
    || segment === ".."
    || !/^[A-Za-z0-9._@+-]+$/.test(segment)
  ))) {
    fail(`${label}_invalid`);
  }
  return value;
}

function timestamp(value, label) {
  if (typeof value !== "string" || value.length !== 24) fail(`${label}_invalid`);
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.valueOf()) || parsed.toISOString() !== value) fail(`${label}_invalid`);
  return parsed.valueOf();
}

function compareStrings(left, right) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function isWithin(candidate, root) {
  return candidate === root || candidate.startsWith(`${root}/`);
}

function assertDisjointPaths(paths, label) {
  for (let index = 0; index < paths.length; index += 1) {
    for (let candidate = 0; candidate < index; candidate += 1) {
      if (isWithin(paths[index], paths[candidate]) || isWithin(paths[candidate], paths[index])) {
        fail(`${label}_overlap_invalid`);
      }
    }
  }
}

function validateSchemaSemantics(value) {
  const semantics = plainObject(value, "runtime_manifest_v2_schema_semantics_invalid");
  exactFields(semantics, SCHEMA_SEMANTICS_FIELDS, "runtime_manifest_v2_schema_semantics_fields_invalid");
  if (
    semantics.artifact_kind !== "openclaw_runtime_guest_root"
    || semantics.identity_model !== "oci_digest_and_rootfs_merkle_v1"
    || semantics.manifest_version !== 2
    || semantics.signature_scope !== "canonical_unsigned_envelope_v1"
  ) fail("runtime_manifest_v2_schema_semantics_invalid");
}

function validatePlatform(value, label = "runtime_manifest_v2_platform") {
  const platform = plainObject(value, `${label}_invalid`);
  exactFields(platform, PLATFORM_FIELDS, `${label}_fields_invalid`);
  if (platform.os !== "linux" || !SUPPORTED_ARCHES.has(platform.arch) || platform.libc !== "glibc") {
    fail(`${label}_unsupported`);
  }
  return platform;
}

function validateOciImage(value, label = "runtime_manifest_v2_oci_image") {
  const image = plainObject(value, `${label}_invalid`);
  exactFields(image, OCI_IMAGE_FIELDS, `${label}_fields_invalid`);
  if (typeof image.name !== "string" || !IMAGE_NAME_PATTERN.test(image.name)) fail(`${label}_name_invalid`);
  if (typeof image.digest !== "string" || !OCI_DIGEST_PATTERN.test(image.digest)) {
    fail(`${label}_digest_invalid`);
  }
  return image;
}

function validateRootfs(value) {
  const rootfs = plainObject(value, "runtime_manifest_v2_rootfs_invalid");
  exactFields(rootfs, ROOTFS_FIELDS, "runtime_manifest_v2_rootfs_fields_invalid");
  sha256(rootfs.merkle_sha256, "runtime_manifest_v2_rootfs_merkle_sha256");
  positiveSafeInteger(rootfs.file_count, MAX_ROOTFS_FILES, "runtime_manifest_v2_rootfs_file_count");
  positiveSafeInteger(rootfs.byte_count, MAX_ROOTFS_BYTES, "runtime_manifest_v2_rootfs_byte_count");
  return rootfs;
}

function validateImmutableRoots(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 32) {
    fail("runtime_manifest_v2_immutable_code_roots_invalid");
  }
  const roots = value.map((item) => absoluteGuestPath(item, "runtime_manifest_v2_immutable_code_root"));
  for (let index = 1; index < roots.length; index += 1) {
    if (compareStrings(roots[index - 1], roots[index]) >= 0) {
      fail("runtime_manifest_v2_immutable_code_roots_order_invalid");
    }
  }
  assertDisjointPaths(roots, "runtime_manifest_v2_immutable_code_roots");
  return roots;
}

function validateMutableMounts(value) {
  if (!Array.isArray(value) || value.length !== 4) fail("runtime_manifest_v2_mutable_mounts_invalid");
  const seenKinds = new Set();
  let previousPath = null;
  const mounts = value.map((item) => {
    const mount = plainObject(item, "runtime_manifest_v2_mutable_mount_invalid");
    exactFields(mount, MUTABLE_MOUNT_FIELDS, "runtime_manifest_v2_mutable_mount_fields_invalid");
    const mountPath = absoluteGuestPath(mount.path, "runtime_manifest_v2_mutable_mount_path");
    if (!Object.hasOwn(REQUIRED_MOUNT_POLICY, mount.kind)) {
      fail("runtime_manifest_v2_mutable_mount_kind_invalid");
    }
    if (seenKinds.has(mount.kind)) fail("runtime_manifest_v2_mutable_mount_kind_duplicate");
    seenKinds.add(mount.kind);
    if (mount.read_only !== REQUIRED_MOUNT_POLICY[mount.kind]) {
      fail("runtime_manifest_v2_mutable_mount_read_only_invalid");
    }
    if (previousPath !== null && compareStrings(previousPath, mountPath) >= 0) {
      fail("runtime_manifest_v2_mutable_mounts_order_invalid");
    }
    previousPath = mountPath;
    return mount;
  });
  if (seenKinds.size !== Object.keys(REQUIRED_MOUNT_POLICY).length) {
    fail("runtime_manifest_v2_mutable_mount_set_invalid");
  }
  assertDisjointPaths(mounts.map((mount) => mount.path), "runtime_manifest_v2_mutable_mounts");
  return mounts;
}

function validateArgv(value, executable, entrypoint) {
  if (!Array.isArray(value) || value.length < 2 || value.length > 64) {
    fail("runtime_manifest_v2_argv_invalid");
  }
  const argv = value.map((item, index) => {
    const argument = plainObject(item, "runtime_manifest_v2_argv_item_invalid");
    exactFields(argument, ARGV_FIELDS, "runtime_manifest_v2_argv_item_fields_invalid");
    if (argument.kind === "guest_path") {
      absoluteGuestPath(argument.value, "runtime_manifest_v2_argv_guest_path");
      if (index > 1) fail("runtime_manifest_v2_argv_guest_path_scope_invalid");
    } else if (argument.kind === "opaque") {
      if (index < 2 || typeof argument.value !== "string" || !OPAQUE_ARG_PATTERN.test(argument.value)) {
        fail("runtime_manifest_v2_argv_opaque_invalid");
      }
    } else {
      fail("runtime_manifest_v2_argv_kind_invalid");
    }
    return argument;
  });
  if (
    argv[0].kind !== "guest_path"
    || argv[0].value !== executable
    || argv[1].kind !== "guest_path"
    || argv[1].value !== entrypoint
  ) fail("runtime_manifest_v2_argv_runtime_binding_invalid");
  return argv;
}

function validateEnvironmentNames(value) {
  if (
    !Array.isArray(value)
    || value.length !== RUNTIME_MANIFEST_V2_ENVIRONMENT_NAMES.length
    || value.some((name, index) => name !== RUNTIME_MANIFEST_V2_ENVIRONMENT_NAMES[index])
  ) fail("runtime_manifest_v2_environment_name_allowlist_invalid");
}

function validateClaims(value) {
  const claims = plainObject(value, "runtime_manifest_v2_claims_invalid");
  exactFields(claims, CLAIM_FIELDS, "runtime_manifest_v2_claims_fields_invalid");
  for (const name of CLAIM_FIELDS) {
    if (claims[name] !== false) fail("runtime_manifest_v2_claim_scope_invalid");
  }
}

export function validateRuntimeManifestV2Body(value) {
  const body = plainObject(value, "runtime_manifest_v2_body_invalid");
  exactFields(body, BODY_FIELDS, "runtime_manifest_v2_body_fields_invalid");
  validateSchemaSemantics(body.schema_semantics);
  validatePlatform(body.platform);
  validateOciImage(body.oci_image);
  validateRootfs(body.rootfs);
  if (body.path_model !== RUNTIME_MANIFEST_V2_PATH_MODEL) fail("runtime_manifest_v2_path_model_invalid");

  token(body.issuer, "runtime_manifest_v2_issuer");
  token(body.key_id, "runtime_manifest_v2_key_id");
  const executable = absoluteGuestPath(body.runtime_executable, "runtime_manifest_v2_runtime_executable");
  const entrypoint = absoluteGuestPath(body.entrypoint, "runtime_manifest_v2_entrypoint");
  if (executable === entrypoint) fail("runtime_manifest_v2_runtime_paths_conflict");
  if (body.runtime_uid !== 1200) fail("runtime_manifest_v2_runtime_uid_invalid");
  if (body.runtime_gid !== 1200) fail("runtime_manifest_v2_runtime_gid_invalid");
  sha256(body.seccomp_profile_sha256, "runtime_manifest_v2_seccomp_profile_sha256");
  sha256(body.cgroup_policy_sha256, "runtime_manifest_v2_cgroup_policy_sha256");

  const createdAt = timestamp(body.created_at, "runtime_manifest_v2_created_at");
  const expiresAt = timestamp(body.expires_at, "runtime_manifest_v2_expires_at");
  if (expiresAt <= createdAt || expiresAt - createdAt > MAX_TIMESTAMP_WINDOW_MS) {
    fail("runtime_manifest_v2_expiry_invalid");
  }

  const immutableRoots = validateImmutableRoots(body.immutable_code_roots);
  const mutableMounts = validateMutableMounts(body.mutable_mounts);
  if (!immutableRoots.some((root) => isWithin(executable, root))) {
    fail("runtime_manifest_v2_runtime_executable_outside_immutable_root");
  }
  if (!immutableRoots.some((root) => isWithin(entrypoint, root))) {
    fail("runtime_manifest_v2_entrypoint_outside_immutable_root");
  }
  for (const root of immutableRoots) {
    if (mutableMounts.some((mount) => isWithin(root, mount.path) || isWithin(mount.path, root))) {
      fail("runtime_manifest_v2_code_and_mutable_paths_overlap");
    }
  }

  validateArgv(body.argv, executable, entrypoint);
  validateEnvironmentNames(body.environment_name_allowlist);
  validateClaims(body.claims);
  return body;
}

function unsignedEnvelope(body, keyId) {
  return {
    algorithm: RUNTIME_MANIFEST_V2_ALGORITHM,
    body,
    key_id: keyId,
    schema: RUNTIME_MANIFEST_V2_SCHEMA,
  };
}

function ed25519PrivateKey(value) {
  let key;
  try {
    key = value?.type === "private" ? value : createPrivateKey(value);
  } catch {
    fail("runtime_manifest_v2_private_key_invalid");
  }
  if (key.type !== "private" || key.asymmetricKeyType !== "ed25519") {
    fail("runtime_manifest_v2_private_key_invalid");
  }
  return key;
}

function ed25519PublicKey(value) {
  let key;
  try {
    key = value?.type === "public" ? value : createPublicKey(value);
  } catch {
    fail("runtime_manifest_v2_public_key_invalid");
  }
  if (key.type !== "public" || key.asymmetricKeyType !== "ed25519") {
    fail("runtime_manifest_v2_public_key_invalid");
  }
  return key;
}

function validateEnvelope(value) {
  const envelope = plainObject(value, "runtime_manifest_v2_envelope_invalid");
  exactFields(envelope, ENVELOPE_FIELDS, "runtime_manifest_v2_envelope_fields_invalid");
  if (envelope.schema !== RUNTIME_MANIFEST_V2_SCHEMA) fail("runtime_manifest_v2_schema_invalid");
  if (envelope.algorithm !== RUNTIME_MANIFEST_V2_ALGORITHM) fail("runtime_manifest_v2_algorithm_invalid");
  token(envelope.key_id, "runtime_manifest_v2_key_id");
  if (typeof envelope.signature !== "string" || !SIGNATURE_PATTERN.test(envelope.signature)) {
    fail("runtime_manifest_v2_signature_invalid");
  }
  const signature = Buffer.from(envelope.signature, "base64url");
  if (signature.byteLength !== 64 || signature.toString("base64url") !== envelope.signature) {
    fail("runtime_manifest_v2_signature_invalid");
  }
  const body = validateRuntimeManifestV2Body(envelope.body);
  if (body.key_id !== envelope.key_id) fail("runtime_manifest_v2_key_id_mismatch");
  return { body, envelope, signature };
}

export function signRuntimeManifestV2(bodyValue, keyId, privateKey) {
  const body = canonicalClone(bodyValue);
  validateRuntimeManifestV2Body(body);
  token(keyId, "runtime_manifest_v2_key_id");
  if (body.key_id !== keyId) fail("runtime_manifest_v2_key_id_mismatch");
  let signature;
  try {
    signature = sign(
      null,
      canonicalRuntimeManifestV2Bytes(unsignedEnvelope(body, keyId)),
      ed25519PrivateKey(privateKey),
    );
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("runtime_manifest_v2_")) throw error;
    fail("runtime_manifest_v2_signing_failed");
  }
  const envelope = {
    ...unsignedEnvelope(body, keyId),
    signature: signature.toString("base64url"),
  };
  if (canonicalRuntimeManifestV2Bytes(envelope).byteLength > MAX_RUNTIME_MANIFEST_V2_BYTES) {
    fail("runtime_manifest_v2_size_invalid");
  }
  return envelope;
}

export function serializeRuntimeManifestV2Envelope(envelopeValue) {
  const envelope = canonicalClone(envelopeValue);
  validateEnvelope(envelope);
  const bytes = canonicalRuntimeManifestV2Bytes(envelope);
  if (bytes.byteLength > MAX_RUNTIME_MANIFEST_V2_BYTES) fail("runtime_manifest_v2_size_invalid");
  return bytes;
}

export function parseCanonicalRuntimeManifestV2Envelope(value) {
  const bytes = manifestBytes(value);
  let envelope;
  try {
    envelope = JSON.parse(bytes.toString("utf8"));
  } catch {
    fail("runtime_manifest_v2_json_invalid");
  }
  validateEnvelope(envelope);
  if (!bytes.equals(canonicalRuntimeManifestV2Bytes(envelope))) {
    fail("runtime_manifest_v2_encoding_noncanonical");
  }
  return envelope;
}

function pinnedKey(trustRoots, keyId) {
  if (trustRoots instanceof Map) return trustRoots.get(keyId);
  const roots = plainObject(trustRoots, "runtime_manifest_v2_trust_roots_invalid");
  return Object.hasOwn(roots, keyId) ? roots[keyId] : undefined;
}

function validateExpected(value) {
  const expected = plainObject(value, "runtime_manifest_v2_expected_bindings_invalid");
  exactFields(expected, EXPECTED_FIELDS, "runtime_manifest_v2_expected_bindings_fields_invalid");
  sha256(expected.body_sha256, "runtime_manifest_v2_expected_body_sha256");
  token(expected.issuer, "runtime_manifest_v2_expected_issuer");
  token(expected.key_id, "runtime_manifest_v2_expected_key_id");
  validatePlatform(expected.platform, "runtime_manifest_v2_expected_platform");
  validateOciImage(expected.oci_image, "runtime_manifest_v2_expected_oci_image");
  sha256(expected.rootfs_merkle_sha256, "runtime_manifest_v2_expected_rootfs_merkle_sha256");
  absoluteGuestPath(expected.runtime_executable, "runtime_manifest_v2_expected_runtime_executable");
  absoluteGuestPath(expected.entrypoint, "runtime_manifest_v2_expected_entrypoint");
  if (expected.runtime_uid !== 1200) fail("runtime_manifest_v2_expected_runtime_uid_invalid");
  if (expected.runtime_gid !== 1200) fail("runtime_manifest_v2_expected_runtime_gid_invalid");
  sha256(expected.seccomp_profile_sha256, "runtime_manifest_v2_expected_seccomp_profile_sha256");
  sha256(expected.cgroup_policy_sha256, "runtime_manifest_v2_expected_cgroup_policy_sha256");
  timestamp(expected.verification_time, "runtime_manifest_v2_verification_time");
  return expected;
}

function equalCanonical(left, right) {
  return canonicalRuntimeManifestV2Bytes(left).equals(canonicalRuntimeManifestV2Bytes(right));
}

function deepFreeze(value) {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value)) deepFreeze(child);
  }
  return value;
}

export function verifyRuntimeManifestV2(envelopeValue, trustRoots, expectedValue) {
  const { body, envelope, signature } = validateEnvelope(envelopeValue);
  const expected = validateExpected(expectedValue);
  const bindings = [
    ["body_sha256", createHash("sha256").update(canonicalRuntimeManifestV2Bytes(body)).digest("hex"), expected.body_sha256],
    ["issuer", body.issuer, expected.issuer],
    ["key_id", body.key_id, expected.key_id],
    ["platform", body.platform, expected.platform],
    ["oci_image", body.oci_image, expected.oci_image],
    ["rootfs_merkle_sha256", body.rootfs.merkle_sha256, expected.rootfs_merkle_sha256],
    ["runtime_executable", body.runtime_executable, expected.runtime_executable],
    ["entrypoint", body.entrypoint, expected.entrypoint],
    ["runtime_uid", body.runtime_uid, expected.runtime_uid],
    ["runtime_gid", body.runtime_gid, expected.runtime_gid],
    ["seccomp_profile_sha256", body.seccomp_profile_sha256, expected.seccomp_profile_sha256],
    ["cgroup_policy_sha256", body.cgroup_policy_sha256, expected.cgroup_policy_sha256],
  ];
  for (const [name, actual, wanted] of bindings) {
    if (!equalCanonical(actual, wanted)) fail(`runtime_manifest_v2_${name}_mismatch`);
  }
  const verificationTime = timestamp(expected.verification_time, "runtime_manifest_v2_verification_time");
  if (
    verificationTime < timestamp(body.created_at, "runtime_manifest_v2_created_at")
    || verificationTime >= timestamp(body.expires_at, "runtime_manifest_v2_expires_at")
  ) fail("runtime_manifest_v2_verification_time_invalid");

  const publicKey = pinnedKey(trustRoots, envelope.key_id);
  if (!publicKey) fail("runtime_manifest_v2_unknown_key");
  let verified = false;
  try {
    verified = verify(
      null,
      canonicalRuntimeManifestV2Bytes(unsignedEnvelope(body, envelope.key_id)),
      ed25519PublicKey(publicKey),
      signature,
    );
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("runtime_manifest_v2_")) throw error;
    fail("runtime_manifest_v2_signature_unverified");
  }
  if (!verified) fail("runtime_manifest_v2_signature_unverified");
  return deepFreeze(canonicalClone(body));
}

export function verifyCanonicalRuntimeManifestV2(value, trustRoots, expectedValue) {
  return verifyRuntimeManifestV2(
    parseCanonicalRuntimeManifestV2Envelope(value),
    trustRoots,
    expectedValue,
  );
}
