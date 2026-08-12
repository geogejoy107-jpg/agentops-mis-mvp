#!/usr/bin/env node

import {
  createHash,
  createPrivateKey,
  createPublicKey,
  sign,
  verify,
} from "node:crypto";
import {
  constants as fsConstants,
  lstat,
  open,
  readdir,
  realpath,
} from "node:fs/promises";
import path from "node:path";

export const RUNTIME_MANIFEST_SCHEMA = "agentops_openclaw_runtime_manifest_v1";
export const RUNTIME_MANIFEST_ALGORITHM = "Ed25519";
export const MAX_RUNTIME_MANIFEST_BYTES = 1024 * 1024;
export const MAX_RUNTIME_MANIFEST_FILES = 20_000;
export const MAX_RUNTIME_FILE_BYTES = 512 * 1024 * 1024;
export const MAX_RUNTIME_TREE_BYTES = 2 * 1024 * 1024 * 1024;

const BODY_FIELDS = Object.freeze([
  "argv_template",
  "cgroup_policy_sha256",
  "created_at",
  "entrypoint",
  "environment_name_allowlist",
  "expires_at",
  "files",
  "issuer",
  "key_id",
  "oci_image_digest",
  "oci_image_name",
  "runtime_created_path_allowlist",
  "runtime_executable",
  "runtime_gid",
  "runtime_state_root",
  "runtime_uid",
  "seccomp_profile_sha256",
]);
const ENVELOPE_FIELDS = Object.freeze([
  "algorithm",
  "body",
  "key_id",
  "schema",
  "signature",
]);
const EXPECTED_FIELDS = Object.freeze([
  "cgroup_policy_sha256",
  "entrypoint",
  "issuer",
  "key_id",
  "oci_image_digest",
  "oci_image_name",
  "runtime_executable",
  "runtime_gid",
  "runtime_uid",
  "seccomp_profile_sha256",
  "verification_time",
]);
const FILE_FIELDS = Object.freeze(["gid", "mode", "path", "sha256", "size", "type", "uid"]);
const METADATA_FIELDS = Object.freeze(BODY_FIELDS.filter((name) => name !== "files"));
const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const IMAGE_DIGEST_PATTERN = /^sha256:[a-f0-9]{64}$/;
const SAFE_TOKEN_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,255}$/;
const ENVIRONMENT_NAME_PATTERN = /^[A-Z_][A-Z0-9_]{0,127}$/;
const ABSOLUTE_RUNTIME_PATH_PATTERN = /^\/(?:[^/\0]+\/)*[^/\0]+$/;

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
    if (!Number.isSafeInteger(value)) fail("runtime_manifest_canonical_number_invalid");
    return value;
  }
  if (Array.isArray(value)) return value.map(canonicalValue);
  const object = plainObject(value, "runtime_manifest_canonical_object_invalid");
  return Object.fromEntries(
    Object.keys(object).sort().map((name) => [name, canonicalValue(object[name])]),
  );
}

export function canonicalRuntimeManifestBytes(value) {
  return Buffer.from(JSON.stringify(canonicalValue(value)), "utf8");
}

function manifestBytes(value) {
  if (!(Buffer.isBuffer(value) || value instanceof Uint8Array)) {
    fail("runtime_manifest_bytes_required");
  }
  const bytes = Buffer.from(value);
  if (bytes.byteLength < 2 || bytes.byteLength > MAX_RUNTIME_MANIFEST_BYTES) {
    fail("runtime_manifest_size_invalid");
  }
  return bytes;
}

function token(value, label) {
  if (typeof value !== "string" || !SAFE_TOKEN_PATTERN.test(value)) fail(`${label}_invalid`);
}

function sha256(value, label) {
  if (typeof value !== "string" || !SHA256_PATTERN.test(value)) fail(`${label}_invalid`);
}

function absoluteRuntimePath(value, label) {
  if (
    typeof value !== "string"
    || value.length > 4096
    || !ABSOLUTE_RUNTIME_PATH_PATTERN.test(value)
    || value.includes("\\")
    || path.posix.normalize(value) !== value
    || value.normalize("NFC") !== value
    || value.split("/").some((segment) => segment === "." || segment === "..")
  ) fail(`${label}_invalid`);
  return value;
}

function normalizedRelativePath(value, label = "runtime_manifest_file_path") {
  if (
    typeof value !== "string"
    || value.length < 1
    || value.length > 4096
    || value.startsWith("/")
    || value.endsWith("/")
    || value.includes("\\")
    || value.includes("\0")
    || value.normalize("NFC") !== value
    || path.posix.normalize(value) !== value
  ) fail(`${label}_invalid`);
  const segments = value.split("/");
  if (segments.some((segment) => !segment || segment === "." || segment === "..")) {
    fail(`${label}_invalid`);
  }
  return value;
}

function canonicalTimestamp(value, label) {
  if (typeof value !== "string" || value.length !== 24) fail(`${label}_invalid`);
  const timestamp = new Date(value);
  if (!Number.isFinite(timestamp.valueOf()) || timestamp.toISOString() !== value) {
    fail(`${label}_invalid`);
  }
  return timestamp.valueOf();
}

function compareStrings(left, right) {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

function sortedUniqueStrings(values, validator, label) {
  if (!Array.isArray(values)) fail(`${label}_invalid`);
  const result = values.map((value) => validator(value, label));
  for (let index = 1; index < result.length; index += 1) {
    if (compareStrings(result[index - 1], result[index]) >= 0) fail(`${label}_order_invalid`);
  }
  return result;
}

function environmentName(value, label) {
  if (typeof value !== "string" || !ENVIRONMENT_NAME_PATTERN.test(value)) fail(`${label}_invalid`);
  return value;
}

function argvValue(value) {
  if (typeof value !== "string" || value.length > 4096 || value.includes("\0")) {
    fail("runtime_manifest_argv_template_invalid");
  }
  return value;
}

function validateFileEntry(value) {
  const file = plainObject(value, "runtime_manifest_file_invalid");
  exactFields(file, FILE_FIELDS, "runtime_manifest_file_fields_invalid");
  normalizedRelativePath(file.path);
  if (file.type !== "regular") fail("runtime_manifest_file_type_invalid");
  if (!Number.isSafeInteger(file.size) || file.size < 0 || file.size > MAX_RUNTIME_FILE_BYTES) {
    fail("runtime_manifest_file_size_invalid");
  }
  for (const [name, fieldValue] of [["uid", file.uid], ["gid", file.gid]]) {
    if (!Number.isSafeInteger(fieldValue) || fieldValue < 0 || fieldValue > 0x7fffffff) {
      fail(`runtime_manifest_file_${name}_invalid`);
    }
  }
  if (!Number.isSafeInteger(file.mode) || file.mode < 0 || file.mode > 0o7777) {
    fail("runtime_manifest_file_mode_invalid");
  }
  if ((file.mode & 0o222) !== 0) fail("runtime_manifest_file_writable");
  sha256(file.sha256, "runtime_manifest_file_sha256");
  return file;
}

function validateFiles(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_RUNTIME_MANIFEST_FILES) {
    fail("runtime_manifest_files_invalid");
  }
  let totalSize = 0;
  let previousPath = null;
  const caseFoldedPaths = new Set();
  for (const item of value) {
    const file = validateFileEntry(item);
    if (previousPath !== null && compareStrings(previousPath, file.path) >= 0) {
      fail("runtime_manifest_file_path_order_invalid");
    }
    const caseFoldedPath = file.path.toLocaleLowerCase("en-US");
    if (caseFoldedPaths.has(caseFoldedPath)) fail("runtime_manifest_file_path_case_conflict");
    caseFoldedPaths.add(caseFoldedPath);
    previousPath = file.path;
    totalSize += file.size;
    if (!Number.isSafeInteger(totalSize) || totalSize > MAX_RUNTIME_TREE_BYTES) {
      fail("runtime_manifest_tree_size_invalid");
    }
  }
  return value;
}

function manifestPathToRelative(value) {
  return normalizedRelativePath(value.slice(1), "runtime_manifest_absolute_file_path");
}

export function validateRuntimeManifestBody(value) {
  const body = plainObject(value, "runtime_manifest_body_invalid");
  exactFields(body, BODY_FIELDS, "runtime_manifest_body_fields_invalid");
  token(body.issuer, "runtime_manifest_issuer");
  token(body.key_id, "runtime_manifest_key_id");
  if (
    typeof body.oci_image_name !== "string"
    || body.oci_image_name.length < 1
    || body.oci_image_name.length > 512
    || /[\s\0]/.test(body.oci_image_name)
  ) fail("runtime_manifest_oci_image_name_invalid");
  if (typeof body.oci_image_digest !== "string" || !IMAGE_DIGEST_PATTERN.test(body.oci_image_digest)) {
    fail("runtime_manifest_oci_image_digest_invalid");
  }
  absoluteRuntimePath(body.entrypoint, "runtime_manifest_entrypoint");
  absoluteRuntimePath(body.runtime_executable, "runtime_manifest_runtime_executable");
  absoluteRuntimePath(body.runtime_state_root, "runtime_manifest_runtime_state_root");
  if (!Number.isSafeInteger(body.runtime_uid) || body.runtime_uid !== 1200) {
    fail("runtime_manifest_runtime_uid_invalid");
  }
  if (!Number.isSafeInteger(body.runtime_gid) || body.runtime_gid !== 1200) {
    fail("runtime_manifest_runtime_gid_invalid");
  }
  sha256(body.seccomp_profile_sha256, "runtime_manifest_seccomp_profile_sha256");
  sha256(body.cgroup_policy_sha256, "runtime_manifest_cgroup_policy_sha256");
  const createdAt = canonicalTimestamp(body.created_at, "runtime_manifest_created_at");
  const expiresAt = canonicalTimestamp(body.expires_at, "runtime_manifest_expires_at");
  if (expiresAt <= createdAt) fail("runtime_manifest_expiry_invalid");
  if (!Array.isArray(body.argv_template) || body.argv_template.length < 2 || body.argv_template.length > 64) {
    fail("runtime_manifest_argv_template_invalid");
  }
  body.argv_template.forEach(argvValue);
  if (body.argv_template[0] !== body.runtime_executable || body.argv_template[1] !== body.entrypoint) {
    fail("runtime_manifest_argv_template_binding_invalid");
  }
  sortedUniqueStrings(
    body.environment_name_allowlist,
    environmentName,
    "runtime_manifest_environment_name_allowlist",
  );
  const runtimeCreatedPaths = sortedUniqueStrings(
    body.runtime_created_path_allowlist,
    absoluteRuntimePath,
    "runtime_manifest_runtime_created_path_allowlist",
  );
  for (const runtimePath of runtimeCreatedPaths) {
    if (!runtimePath.startsWith(`${body.runtime_state_root}/`)) {
      fail("runtime_manifest_runtime_created_path_outside_state_root");
    }
  }
  const files = validateFiles(body.files);
  const measuredPaths = new Set(files.map((file) => file.path));
  if (!measuredPaths.has(manifestPathToRelative(body.entrypoint))) {
    fail("runtime_manifest_entrypoint_unmeasured");
  }
  if (!measuredPaths.has(manifestPathToRelative(body.runtime_executable))) {
    fail("runtime_manifest_runtime_executable_unmeasured");
  }
  return body;
}

function unsignedEnvelope(body, keyId) {
  return {
    algorithm: RUNTIME_MANIFEST_ALGORITHM,
    body,
    key_id: keyId,
    schema: RUNTIME_MANIFEST_SCHEMA,
  };
}

function ed25519PrivateKey(value) {
  let key;
  try {
    key = value?.type === "private" ? value : createPrivateKey(value);
  } catch {
    fail("runtime_manifest_private_key_invalid");
  }
  if (key.type !== "private" || key.asymmetricKeyType !== "ed25519") {
    fail("runtime_manifest_private_key_invalid");
  }
  return key;
}

function ed25519PublicKey(value) {
  let key;
  try {
    key = value?.type === "public" ? value : createPublicKey(value);
  } catch {
    fail("runtime_manifest_public_key_invalid");
  }
  if (key.type !== "public" || key.asymmetricKeyType !== "ed25519") {
    fail("runtime_manifest_public_key_invalid");
  }
  return key;
}

export function signRuntimeManifest(bodyValue, keyId, privateKey) {
  const body = validateRuntimeManifestBody(bodyValue);
  token(keyId, "runtime_manifest_key_id");
  if (keyId !== body.key_id) fail("runtime_manifest_key_id_mismatch");
  let signature;
  try {
    signature = sign(
      null,
      canonicalRuntimeManifestBytes(unsignedEnvelope(body, keyId)),
      ed25519PrivateKey(privateKey),
    );
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("runtime_manifest_")) throw error;
    fail("runtime_manifest_signing_failed");
  }
  if (signature.byteLength !== 64) fail("runtime_manifest_signature_invalid");
  const envelope = {
    ...unsignedEnvelope(body, keyId),
    signature: signature.toString("base64url"),
  };
  if (canonicalRuntimeManifestBytes(envelope).byteLength > MAX_RUNTIME_MANIFEST_BYTES) {
    fail("runtime_manifest_size_invalid");
  }
  return envelope;
}

export function serializeRuntimeManifestEnvelope(envelopeValue) {
  const envelope = plainObject(envelopeValue, "runtime_manifest_envelope_invalid");
  exactFields(envelope, ENVELOPE_FIELDS, "runtime_manifest_envelope_fields_invalid");
  validateRuntimeManifestBody(envelope.body);
  const bytes = canonicalRuntimeManifestBytes(envelope);
  if (bytes.byteLength > MAX_RUNTIME_MANIFEST_BYTES) fail("runtime_manifest_size_invalid");
  return bytes;
}

export function parseCanonicalRuntimeManifestEnvelope(value) {
  const bytes = manifestBytes(value);
  let envelope;
  try {
    envelope = JSON.parse(bytes.toString("utf8"));
  } catch {
    fail("runtime_manifest_json_invalid");
  }
  const object = plainObject(envelope, "runtime_manifest_envelope_invalid");
  exactFields(object, ENVELOPE_FIELDS, "runtime_manifest_envelope_fields_invalid");
  if (
    typeof object.algorithm !== "string"
    || typeof object.key_id !== "string"
    || typeof object.schema !== "string"
    || typeof object.signature !== "string"
  ) fail("runtime_manifest_envelope_shape_invalid");
  validateRuntimeManifestBody(object.body);
  if (!bytes.equals(canonicalRuntimeManifestBytes(object))) {
    fail("runtime_manifest_encoding_noncanonical");
  }
  return object;
}

function pinnedKey(keys, keyId) {
  if (keys instanceof Map) return keys.get(keyId);
  const object = plainObject(keys, "runtime_manifest_trust_roots_invalid");
  return Object.hasOwn(object, keyId) ? object[keyId] : undefined;
}

function validateExpectedBindings(expectedValue) {
  const expected = plainObject(expectedValue, "runtime_manifest_expected_bindings_invalid");
  exactFields(expected, EXPECTED_FIELDS, "runtime_manifest_expected_bindings_invalid");
  token(expected.issuer, "runtime_manifest_expected_issuer");
  token(expected.key_id, "runtime_manifest_expected_key_id");
  if (typeof expected.oci_image_digest !== "string" || !IMAGE_DIGEST_PATTERN.test(expected.oci_image_digest)) {
    fail("runtime_manifest_expected_oci_image_digest_invalid");
  }
  if (typeof expected.oci_image_name !== "string" || expected.oci_image_name.length < 1) {
    fail("runtime_manifest_expected_oci_image_name_invalid");
  }
  absoluteRuntimePath(expected.entrypoint, "runtime_manifest_expected_entrypoint");
  absoluteRuntimePath(expected.runtime_executable, "runtime_manifest_expected_runtime_executable");
  sha256(expected.seccomp_profile_sha256, "runtime_manifest_expected_seccomp_profile_sha256");
  sha256(expected.cgroup_policy_sha256, "runtime_manifest_expected_cgroup_policy_sha256");
  if (expected.runtime_uid !== 1200) fail("runtime_manifest_expected_runtime_uid_invalid");
  if (expected.runtime_gid !== 1200) fail("runtime_manifest_expected_runtime_gid_invalid");
  canonicalTimestamp(expected.verification_time, "runtime_manifest_verification_time");
  return expected;
}

export function verifyRuntimeManifest(envelopeValue, trustRoots, expectedValue) {
  const envelope = plainObject(envelopeValue, "runtime_manifest_envelope_invalid");
  exactFields(envelope, ENVELOPE_FIELDS, "runtime_manifest_envelope_fields_invalid");
  if (envelope.schema !== RUNTIME_MANIFEST_SCHEMA) fail("runtime_manifest_schema_invalid");
  if (envelope.algorithm !== RUNTIME_MANIFEST_ALGORITHM) fail("runtime_manifest_algorithm_invalid");
  token(envelope.key_id, "runtime_manifest_key_id");
  if (typeof envelope.signature !== "string" || !/^[A-Za-z0-9_-]{86}$/.test(envelope.signature)) {
    fail("runtime_manifest_signature_invalid");
  }
  const body = validateRuntimeManifestBody(envelope.body);
  if (envelope.key_id !== body.key_id) fail("runtime_manifest_key_id_mismatch");
  const expected = validateExpectedBindings(expectedValue);
  for (const name of EXPECTED_FIELDS) {
    if (name === "verification_time") continue;
    if (body[name] !== expected[name]) fail(`runtime_manifest_${name}_mismatch`);
  }
  const verificationTime = canonicalTimestamp(expected.verification_time, "runtime_manifest_verification_time");
  if (
    verificationTime < canonicalTimestamp(body.created_at, "runtime_manifest_created_at")
    || verificationTime > canonicalTimestamp(body.expires_at, "runtime_manifest_expires_at")
  ) fail("runtime_manifest_verification_time_invalid");
  const publicKey = pinnedKey(trustRoots, envelope.key_id);
  if (!publicKey) fail("runtime_manifest_unknown_key");
  let signature;
  try {
    signature = Buffer.from(envelope.signature, "base64url");
  } catch {
    fail("runtime_manifest_signature_invalid");
  }
  if (signature.byteLength !== 64 || signature.toString("base64url") !== envelope.signature) {
    fail("runtime_manifest_signature_invalid");
  }
  let verified = false;
  try {
    verified = verify(
      null,
      canonicalRuntimeManifestBytes(unsignedEnvelope(body, envelope.key_id)),
      ed25519PublicKey(publicKey),
      signature,
    );
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("runtime_manifest_")) throw error;
    fail("runtime_manifest_signature_unverified");
  }
  if (!verified) fail("runtime_manifest_signature_unverified");
  return immutableManifestBody(body);
}

export function verifyCanonicalRuntimeManifest(value, trustRoots, expectedValue) {
  return verifyRuntimeManifest(
    parseCanonicalRuntimeManifestEnvelope(value),
    trustRoots,
    expectedValue,
  );
}

function safeNumber(value, label) {
  const converted = Number(value);
  if (!Number.isSafeInteger(converted) || converted < 0) fail(label);
  return converted;
}

function statIdentity(stat) {
  return [
    stat.dev,
    stat.ino,
    stat.mode,
    stat.nlink,
    stat.uid,
    stat.gid,
    stat.size,
    stat.mtimeNs,
    stat.ctimeNs,
  ].join(":");
}

function immutableManifestBody(body) {
  return Object.freeze({
    ...body,
    argv_template: Object.freeze([...body.argv_template]),
    environment_name_allowlist: Object.freeze([...body.environment_name_allowlist]),
    files: Object.freeze(body.files.map((file) => Object.freeze({ ...file }))),
    runtime_created_path_allowlist: Object.freeze([...body.runtime_created_path_allowlist]),
  });
}

function validateOpenRegularFile(stat) {
  if (!stat.isFile()) fail("runtime_manifest_tree_special_file");
  if (stat.nlink !== 1n) fail("runtime_manifest_tree_hard_link_rejected");
  const mode = safeNumber(stat.mode & 0o7777n, "runtime_manifest_tree_mode_invalid");
  if ((mode & 0o222) !== 0) fail("runtime_manifest_tree_writable_file");
  const size = safeNumber(stat.size, "runtime_manifest_tree_file_size_invalid");
  if (size > MAX_RUNTIME_FILE_BYTES) fail("runtime_manifest_tree_file_size_invalid");
  return {
    gid: safeNumber(stat.gid, "runtime_manifest_tree_gid_invalid"),
    mode,
    size,
    uid: safeNumber(stat.uid, "runtime_manifest_tree_uid_invalid"),
  };
}

function validateImmutableDirectory(stat, expectedUid, expectedGid) {
  if (!stat.isDirectory() || stat.isSymbolicLink()) fail("runtime_manifest_tree_directory_invalid");
  const mode = safeNumber(stat.mode & 0o7777n, "runtime_manifest_tree_directory_mode_invalid");
  if ((mode & 0o222) !== 0) fail("runtime_manifest_tree_writable_directory");
  if (
    safeNumber(stat.uid, "runtime_manifest_tree_directory_uid_invalid") !== expectedUid
    || safeNumber(stat.gid, "runtime_manifest_tree_directory_gid_invalid") !== expectedGid
  ) fail("runtime_manifest_tree_directory_owner_invalid");
  return statIdentity(stat);
}

async function discoverTree(rootPath, expectedUid, expectedGid) {
  const discovered = [];
  const directories = [];
  const caseFoldedPaths = new Set();
  async function walk(relativeDirectory) {
    const absoluteDirectory = relativeDirectory
      ? path.join(rootPath, ...relativeDirectory.split("/"))
      : rootPath;
    let entries;
    let directoryStat;
    try {
      directoryStat = await lstat(absoluteDirectory, { bigint: true });
      directories.push(`${relativeDirectory}:${validateImmutableDirectory(
        directoryStat,
        expectedUid,
        expectedGid,
      )}`);
      entries = await readdir(absoluteDirectory, { withFileTypes: true });
    } catch (error) {
      if (typeof error?.code === "string" && error.code.startsWith("runtime_manifest_")) throw error;
      fail("runtime_manifest_tree_read_failed");
    }
    if (relativeDirectory && entries.length === 0) fail("runtime_manifest_tree_empty_directory");
    entries.sort((left, right) => compareStrings(left.name, right.name));
    for (const entry of entries) {
      const relativePath = normalizedRelativePath(
        relativeDirectory ? `${relativeDirectory}/${entry.name}` : entry.name,
        "runtime_manifest_tree_path",
      );
      const folded = relativePath.toLocaleLowerCase("en-US");
      if (caseFoldedPaths.has(folded)) fail("runtime_manifest_tree_path_case_conflict");
      caseFoldedPaths.add(folded);
      if (entry.isSymbolicLink()) fail("runtime_manifest_tree_symlink_rejected");
      if (entry.isDirectory()) {
        await walk(relativePath);
      } else if (entry.isFile()) {
        discovered.push(relativePath);
        if (discovered.length > MAX_RUNTIME_MANIFEST_FILES) fail("runtime_manifest_tree_file_count_invalid");
      } else {
        fail("runtime_manifest_tree_special_file");
      }
    }
  }
  await walk("");
  discovered.sort(compareStrings);
  directories.sort(compareStrings);
  return { directories, files: discovered };
}

async function assertNoSymlinkComponents(rootPath, relativePath) {
  let currentPath = rootPath;
  for (const segment of relativePath.split("/")) {
    currentPath = path.join(currentPath, segment);
    let stat;
    try {
      stat = await lstat(currentPath, { bigint: true });
    } catch {
      fail("runtime_manifest_tree_path_changed");
    }
    if (stat.isSymbolicLink()) fail("runtime_manifest_tree_symlink_rejected");
  }
  let resolved;
  try {
    resolved = await realpath(currentPath);
  } catch {
    fail("runtime_manifest_tree_path_changed");
  }
  if (resolved !== currentPath) fail("runtime_manifest_tree_path_escape");
}

async function assertPathMatchesOpenFile(rootPath, relativePath, openStat) {
  await assertNoSymlinkComponents(rootPath, relativePath);
  let pathStat;
  try {
    pathStat = await lstat(
      path.join(rootPath, ...relativePath.split("/")),
      { bigint: true },
    );
  } catch {
    fail("runtime_manifest_tree_path_changed");
  }
  if (
    !pathStat.isFile()
    || pathStat.dev !== openStat.dev
    || pathStat.ino !== openStat.ino
  ) fail("runtime_manifest_tree_path_changed");
}

async function measureOpenFile(rootPath, relativePath) {
  const absolutePath = path.join(rootPath, ...relativePath.split("/"));
  await assertNoSymlinkComponents(rootPath, relativePath);
  let handle;
  try {
    handle = await open(
      absolutePath,
      fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW | (fsConstants.O_CLOEXEC ?? 0),
    );
  } catch {
    fail("runtime_manifest_tree_open_failed");
  }
  try {
    const before = await handle.stat({ bigint: true });
    const fields = validateOpenRegularFile(before);
    await assertPathMatchesOpenFile(rootPath, relativePath, before);
    const hash = createHash("sha256");
    const buffer = Buffer.allocUnsafe(64 * 1024);
    let totalRead = 0;
    for (;;) {
      const { bytesRead } = await handle.read(buffer, 0, buffer.byteLength, null);
      if (bytesRead === 0) break;
      totalRead += bytesRead;
      if (totalRead > MAX_RUNTIME_FILE_BYTES || totalRead > fields.size) {
        fail("runtime_manifest_tree_file_changed");
      }
      hash.update(buffer.subarray(0, bytesRead));
    }
    const after = await handle.stat({ bigint: true });
    await assertPathMatchesOpenFile(rootPath, relativePath, after);
    if (totalRead !== fields.size || statIdentity(before) !== statIdentity(after)) {
      fail("runtime_manifest_tree_file_changed");
    }
    return {
      gid: fields.gid,
      mode: fields.mode,
      path: relativePath,
      sha256: hash.digest("hex"),
      size: fields.size,
      type: "regular",
      uid: fields.uid,
    };
  } finally {
    await handle.close().catch(() => {});
  }
}

async function stableMeasuredTree(rootValue) {
  if (typeof rootValue !== "string" || !path.isAbsolute(rootValue)) {
    fail("runtime_manifest_tree_root_invalid");
  }
  let rootPath;
  let rootUid;
  let rootGid;
  try {
    const rootLstat = await lstat(rootValue, { bigint: true });
    if (rootLstat.isSymbolicLink() || !rootLstat.isDirectory()) fail("runtime_manifest_tree_root_invalid");
    rootPath = await realpath(rootValue);
    validateImmutableDirectory(
      rootLstat,
      safeNumber(rootLstat.uid, "runtime_manifest_tree_root_uid_invalid"),
      safeNumber(rootLstat.gid, "runtime_manifest_tree_root_gid_invalid"),
    );
    rootUid = safeNumber(rootLstat.uid, "runtime_manifest_tree_root_uid_invalid");
    rootGid = safeNumber(rootLstat.gid, "runtime_manifest_tree_root_gid_invalid");
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("runtime_manifest_")) throw error;
    fail("runtime_manifest_tree_root_invalid");
  }
  const before = await discoverTree(rootPath, rootUid, rootGid);
  const beforePaths = before.files;
  if (beforePaths.length < 1) fail("runtime_manifest_tree_empty");
  const files = [];
  let totalSize = 0;
  for (const relativePath of beforePaths) {
    const measured = await measureOpenFile(rootPath, relativePath);
    files.push(measured);
    totalSize += measured.size;
    if (!Number.isSafeInteger(totalSize) || totalSize > MAX_RUNTIME_TREE_BYTES) {
      fail("runtime_manifest_tree_size_invalid");
    }
  }
  const after = await discoverTree(rootPath, rootUid, rootGid);
  const afterPaths = after.files;
  if (
    beforePaths.length !== afterPaths.length
    || beforePaths.some((relativePath, index) => relativePath !== afterPaths[index])
    || before.directories.length !== after.directories.length
    || before.directories.some((identity, index) => identity !== after.directories[index])
  ) fail("runtime_manifest_tree_changed");
  return files;
}

export async function measureRuntimeManifestTree(rootPath) {
  return stableMeasuredTree(rootPath);
}

export async function generateRuntimeManifest(rootPath, metadataValue, privateKey) {
  const metadata = plainObject(metadataValue, "runtime_manifest_metadata_invalid");
  exactFields(metadata, METADATA_FIELDS, "runtime_manifest_metadata_fields_invalid");
  const files = await stableMeasuredTree(rootPath);
  const body = validateRuntimeManifestBody({ ...metadata, files });
  return signRuntimeManifest(body, body.key_id, privateKey);
}

export async function verifyRuntimeManifestTree(rootPath, bodyValue) {
  const body = validateRuntimeManifestBody(bodyValue);
  const actualFiles = await stableMeasuredTree(rootPath);
  if (actualFiles.length !== body.files.length) fail("runtime_manifest_tree_exact_set_mismatch");
  for (let index = 0; index < body.files.length; index += 1) {
    const expected = body.files[index];
    const actual = actualFiles[index];
    for (const name of FILE_FIELDS) {
      if (actual[name] !== expected[name]) fail(`runtime_manifest_tree_file_${name}_mismatch`);
    }
  }
  return Object.freeze({
    exact_tree_verified: true,
    measured_file_count: actualFiles.length,
    measured_tree_bytes: actualFiles.reduce((sum, file) => sum + file.size, 0),
  });
}

export async function verifyCanonicalRuntimeManifestAndTree(
  value,
  rootPath,
  trustRoots,
  expectedValue,
) {
  const body = verifyCanonicalRuntimeManifest(value, trustRoots, expectedValue);
  const tree = await verifyRuntimeManifestTree(rootPath, body);
  return Object.freeze({ body, tree });
}

export function runtimeManifestSha256(value) {
  return createHash("sha256").update(manifestBytes(value)).digest("hex");
}
