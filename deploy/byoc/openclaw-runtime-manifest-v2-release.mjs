#!/usr/bin/env node

import { createHash, createPrivateKey, createPublicKey } from "node:crypto";
import {
  chmodSync,
  closeSync,
  constants,
  existsSync,
  fstatSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  canonicalRuntimeManifestV2Bytes,
  serializeRuntimeManifestV2Envelope,
  signRuntimeManifestV2,
} from "./openclaw-runtime-manifest-v2.mjs";
import {
  computeOpenClawRuntimeRootfsMerkle,
  OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS,
} from "./openclaw-runtime-rootfs-merkle.mjs";
import {
  OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA,
  readCommittedOpenClawRuntimeOciExportReceipt,
} from "./openclaw-runtime-oci-export.mjs";

export const OPENCLAW_RUNTIME_MANIFEST_V2_RELEASE_SCHEMA =
  "agentops_openclaw_runtime_manifest_v2_release_v2";
export const OPENCLAW_RUNTIME_MANIFEST_V2_TRUST_ROOTS_SCHEMA =
  "agentops_openclaw_runtime_manifest_trust_roots_v1";

const OUTPUT_FILES = Object.freeze({
  manifest: "openclaw-runtime-manifest.json",
  provenance: "openclaw-runtime-oci-export-provenance.json",
  receipt: "openclaw-runtime-manifest-metadata-receipt.json",
});
const SHA256 = /^[a-f0-9]{64}$/;
const OCI_REFERENCE = /^([a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]{1,5})?(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)+)@(sha256:[a-f0-9]{64})$/;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,255}$/;
const EXPECTED_OPTIONS = Object.freeze([
  "--cgroup-policy-sha256",
  "--created",
  "--expires",
  "--issuer",
  "--key-id",
  "--output",
  "--private-key",
  "--provenance",
  "--seccomp-profile-sha256",
  "--trust-root",
]);

function fail(code, cause) {
  const error = new Error(code, cause ? { cause } : undefined);
  error.code = code;
  throw error;
}

function currentUid() {
  const getter = typeof process.geteuid === "function"
    ? process.geteuid
    : typeof process.getuid === "function"
      ? process.getuid
      : null;
  if (getter === null) fail("runtime_manifest_v2_release_posix_uid_required");
  const uid = getter.call(process);
  if (!Number.isSafeInteger(uid) || uid < 0) {
    fail("runtime_manifest_v2_release_posix_uid_invalid");
  }
  return uid;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function parseTimestamp(value, label) {
  if (typeof value !== "string" || value.length !== 24) fail(`${label}_invalid`);
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.valueOf()) || parsed.toISOString() !== value) {
    fail(`${label}_noncanonical`);
  }
  return value;
}

function absoluteCanonicalPath(value, label) {
  if (
    typeof value !== "string"
    || value.includes("\0")
    || !path.isAbsolute(value)
    || path.normalize(value) !== value
    || (value !== path.parse(value).root && value.endsWith(path.sep))
  ) fail(`${label}_noncanonical`);
  return value;
}

function parseOptions(arguments_) {
  if (arguments_.length !== EXPECTED_OPTIONS.length * 2) fail("runtime_manifest_v2_release_options_invalid");
  const values = new Map();
  for (let index = 0; index < arguments_.length; index += 2) {
    const name = arguments_[index];
    const value = arguments_[index + 1];
    if (!EXPECTED_OPTIONS.includes(name) || values.has(name) || typeof value !== "string" || !value) {
      fail("runtime_manifest_v2_release_options_invalid");
    }
    values.set(name, value);
  }
  if (EXPECTED_OPTIONS.some((name) => !values.has(name))) {
    fail("runtime_manifest_v2_release_options_invalid");
  }
  return Object.fromEntries(EXPECTED_OPTIONS.map((name) => [name.slice(2), values.get(name)]));
}

function inspectDirectory(value, label, { expectedUid = null, rejectGroupWorldWrite = false } = {}) {
  const target = absoluteCanonicalPath(value, label);
  let metadata;
  try {
    metadata = lstatSync(target);
  } catch (error) {
    fail(`${label}_invalid`, error);
  }
  if (
    !metadata.isDirectory()
    || metadata.isSymbolicLink()
    || (expectedUid !== null && metadata.uid !== expectedUid)
    || (rejectGroupWorldWrite && (metadata.mode & 0o022) !== 0)
  ) fail(`${label}_invalid`);
  let canonical;
  try {
    canonical = realpathSync(target);
    if (canonical !== target) fail(`${label}_noncanonical`);
    const after = lstatSync(target);
    if (after.ino !== metadata.ino || after.dev !== metadata.dev) fail(`${label}_identity_changed`);
  } catch (error) {
    if (error?.code?.startsWith?.("runtime_manifest_v2_release_")) throw error;
    fail(`${label}_invalid`, error);
  }
  return canonical;
}

function readPrivateKey(keyPathValue, expectedUid) {
  const keyPath = absoluteCanonicalPath(keyPathValue, "runtime_manifest_v2_release_private_key_path");
  let before;
  try {
    before = lstatSync(keyPath, { bigint: true });
  } catch (error) {
    fail("runtime_manifest_v2_release_private_key_invalid", error);
  }
  if (
    !before.isFile()
    || before.isSymbolicLink()
    || before.nlink !== 1n
    || before.uid !== BigInt(expectedUid)
    || (before.mode & 0o777n) !== 0o400n
    || before.size < 2n
    || before.size > 16_384n
  ) fail("runtime_manifest_v2_release_private_key_metadata_invalid");
  try {
    if (realpathSync(keyPath) !== keyPath) fail("runtime_manifest_v2_release_private_key_path_noncanonical");
  } catch (error) {
    if (error?.code === "runtime_manifest_v2_release_private_key_path_noncanonical") throw error;
    fail("runtime_manifest_v2_release_private_key_invalid", error);
  }

  let descriptor;
  try {
    descriptor = openSync(keyPath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
    const opened = fstatSync(descriptor, { bigint: true });
    if (opened.dev !== before.dev || opened.ino !== before.ino || opened.nlink !== 1n) {
      fail("runtime_manifest_v2_release_private_key_identity_changed");
    }
    const bytes = readFileSync(descriptor);
    const after = lstatSync(keyPath, { bigint: true });
    if (
      after.dev !== before.dev
      || after.ino !== before.ino
      || after.size !== before.size
      || after.ctimeNs !== before.ctimeNs
      || after.mtimeNs !== before.mtimeNs
    ) fail("runtime_manifest_v2_release_private_key_identity_changed");
    let privateKey;
    try {
      privateKey = createPrivateKey(bytes);
    } catch (error) {
      fail("runtime_manifest_v2_release_private_key_invalid", error);
    }
    if (privateKey.type !== "private" || privateKey.asymmetricKeyType !== "ed25519") {
      fail("runtime_manifest_v2_release_private_key_invalid");
    }
    return privateKey;
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
}

function readPinnedTrustRoot(trustPathValue, expectedUid, keyId) {
  const trustPath = absoluteCanonicalPath(
    trustPathValue,
    "runtime_manifest_v2_release_trust_root_path",
  );
  let before;
  try {
    before = lstatSync(trustPath, { bigint: true });
  } catch (error) {
    fail("runtime_manifest_v2_release_trust_root_invalid", error);
  }
  if (
    !before.isFile()
    || before.isSymbolicLink()
    || before.nlink !== 1n
    || before.uid !== BigInt(expectedUid)
    || (before.mode & 0o222n) !== 0n
    || before.size < 2n
    || before.size > 65_536n
  ) fail("runtime_manifest_v2_release_trust_root_metadata_invalid");
  if (realpathSync(trustPath) !== trustPath) {
    fail("runtime_manifest_v2_release_trust_root_path_noncanonical");
  }
  let descriptor;
  try {
    descriptor = openSync(trustPath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
    const opened = fstatSync(descriptor, { bigint: true });
    if (opened.dev !== before.dev || opened.ino !== before.ino || opened.nlink !== 1n) {
      fail("runtime_manifest_v2_release_trust_root_identity_changed");
    }
    const bytes = readFileSync(descriptor);
    const after = lstatSync(trustPath, { bigint: true });
    if (
      after.dev !== before.dev
      || after.ino !== before.ino
      || after.size !== before.size
      || after.ctimeNs !== before.ctimeNs
      || after.mtimeNs !== before.mtimeNs
    ) fail("runtime_manifest_v2_release_trust_root_identity_changed");
    let value;
    try {
      value = JSON.parse(new TextDecoder("utf8", { fatal: true }).decode(bytes));
    } catch (error) {
      fail("runtime_manifest_v2_release_trust_root_invalid", error);
    }
    if (!Buffer.from(JSON.stringify(value), "utf8").equals(bytes)) {
      fail("runtime_manifest_v2_release_trust_root_noncanonical");
    }
    if (
      value?.schema !== OPENCLAW_RUNTIME_MANIFEST_V2_TRUST_ROOTS_SCHEMA
      || !value.keys
      || typeof value.keys !== "object"
      || Array.isArray(value.keys)
      || Object.keys(value).length !== 2
      || Object.keys(value.keys).length !== 1
      || !Object.hasOwn(value.keys, keyId)
    ) fail("runtime_manifest_v2_release_trust_root_invalid");
    let publicKey;
    try {
      publicKey = createPublicKey(value.keys[keyId]);
    } catch (error) {
      fail("runtime_manifest_v2_release_trust_root_invalid", error);
    }
    if (publicKey.type !== "public" || publicKey.asymmetricKeyType !== "ed25519") {
      fail("runtime_manifest_v2_release_trust_root_invalid");
    }
    return Object.freeze({ bytes, publicKey });
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
}

function releaseBody(input, rootfs, provenance) {
  const image = OCI_REFERENCE.exec(provenance.oci.exact_reference);
  if (!image) fail("runtime_manifest_v2_release_oci_invalid");
  if (!TOKEN.test(input.issuer)) fail("runtime_manifest_v2_release_issuer_invalid");
  if (!TOKEN.test(input["key-id"])) fail("runtime_manifest_v2_release_key_id_invalid");
  if (!SHA256.test(input["cgroup-policy-sha256"])) {
    fail("runtime_manifest_v2_release_cgroup_policy_sha256_invalid");
  }
  if (!SHA256.test(input["seccomp-profile-sha256"])) {
    fail("runtime_manifest_v2_release_seccomp_profile_sha256_invalid");
  }
  return {
    argv: [
      { kind: "guest_path", value: "/usr/local/bin/node" },
      { kind: "guest_path", value: "/opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs" },
      { kind: "opaque", value: "--stdin-protocol=canonical_provider_request_stdin_v1" },
    ],
    cgroup_policy_sha256: input["cgroup-policy-sha256"],
    claims: {
      guest_root_artifact_built: false,
      guest_root_immutability_verified: false,
      launcher_guest_root_handoff_verified: false,
      real_openclaw_execution_verified: false,
      runtime_path_toctou_closed: false,
    },
    created_at: parseTimestamp(input.created, "runtime_manifest_v2_release_created"),
    entrypoint: "/opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs",
    environment_name_allowlist: [
      "LANG",
      "OPENCLAW_CONFIG_PATH",
      "OPENCLAW_STATE_DIR",
      "OPENCLAW_WORKSPACE",
      "PATH",
    ],
    expires_at: parseTimestamp(input.expires, "runtime_manifest_v2_release_expires"),
    immutable_code_roots: ["/opt/agentops/openclaw-adapter", "/opt/openclaw", "/usr/local"],
    issuer: input.issuer,
    key_id: input["key-id"],
    mutable_mounts: [
      { kind: "workspace_directory", path: "/opt/agentops-worker/workspace", read_only: true },
      { kind: "state_directory", path: "/run/openclaw-state", read_only: false },
      { kind: "config_file", path: "/run/secrets/openclaw_config", read_only: true },
      { kind: "temp_directory", path: "/tmp", read_only: false },
    ],
    oci_image: { name: image[1], digest: image[2] },
    path_model: "guest_root_absolute_v1",
    platform: { arch: "amd64", libc: "glibc", os: "linux" },
    rootfs: {
      byte_count: rootfs.byte_count,
      file_count: rootfs.file_count,
      merkle_sha256: rootfs.merkle_sha256,
    },
    runtime_executable: "/usr/local/bin/node",
    runtime_gid: 1200,
    runtime_uid: 1200,
    schema_semantics: {
      artifact_kind: "openclaw_runtime_guest_root",
      identity_model: "oci_digest_and_rootfs_merkle_v1",
      manifest_version: 2,
      signature_scope: "canonical_unsigned_envelope_v1",
    },
    seccomp_profile_sha256: input["seccomp-profile-sha256"],
  };
}

function writeReadonly(target, bytes) {
  writeFileSync(target, bytes, { flag: "wx", mode: 0o444 });
  chmodSync(target, 0o444);
  const descriptor = openSync(target, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  try {
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
}

function syncDirectory(target) {
  const descriptor = openSync(
    target,
    constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
  );
  try {
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
}

export function buildOpenClawRuntimeManifestV2Release(input) {
  const releaseUid = currentUid();
  const source = readCommittedOpenClawRuntimeOciExportReceipt(input.provenance);
  if (/^(?:127\.0\.0\.1|localhost):[1-9][0-9]{0,4}\//.test(source.provenance.oci.name)) {
    fail("runtime_manifest_v2_release_insecure_registry_provenance_rejected");
  }
  const guestRoot = inspectDirectory(source.guest_root, "runtime_manifest_v2_release_guest_root");
  const output = absoluteCanonicalPath(input.output, "runtime_manifest_v2_release_output");
  if (existsSync(output)) fail("runtime_manifest_v2_release_output_exists");
  const parent = inspectDirectory(
    path.dirname(output),
    "runtime_manifest_v2_release_output_parent",
    {
      expectedUid: releaseUid,
      rejectGroupWorldWrite: true,
    },
  );
  if (path.dirname(output) !== parent) fail("runtime_manifest_v2_release_output_parent_noncanonical");
  const privateKey = readPrivateKey(input["private-key"], releaseUid);
  const trustRoot = readPinnedTrustRoot(input["trust-root"], releaseUid, input["key-id"]);
  const privatePublicDer = createPublicKey(privateKey).export({ type: "spki", format: "der" });
  const pinnedPublicDer = trustRoot.publicKey.export({ type: "spki", format: "der" });
  if (!privatePublicDer.equals(pinnedPublicDer)) {
    fail("runtime_manifest_v2_release_signing_key_not_pinned");
  }
  const rootfs = computeOpenClawRuntimeRootfsMerkle(
    guestRoot,
    OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS,
  );
  if (canonicalRuntimeManifestV2Bytes(rootfs).compare(
    canonicalRuntimeManifestV2Bytes(source.provenance.rootfs),
  ) !== 0) fail("runtime_manifest_v2_release_provenance_rootfs_mismatch");
  const body = releaseBody(input, rootfs, source.provenance);
  const envelope = signRuntimeManifestV2(body, body.key_id, privateKey);
  const manifestBytes = serializeRuntimeManifestV2Envelope(envelope);
  const receiptBytes = canonicalRuntimeManifestV2Bytes({
    claims: body.claims,
    cgroup_policy_sha256: body.cgroup_policy_sha256,
    created_at: body.created_at,
    expires_at: body.expires_at,
    files: {
      manifest: { name: OUTPUT_FILES.manifest, sha256: sha256(manifestBytes) },
      provenance: {
        name: OUTPUT_FILES.provenance,
        sha256: source.provenance_sha256,
      },
    },
    issuer: body.issuer,
    key_id: body.key_id,
    oci_export_provenance: {
      schema: OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA,
      sha256: source.provenance_sha256,
    },
    oci_image: body.oci_image,
    platform: body.platform,
    private_key_copied: false,
    trust_root_copied: false,
    trust_root_sha256: sha256(trustRoot.bytes),
    rootfs: body.rootfs,
    schema: OPENCLAW_RUNTIME_MANIFEST_V2_RELEASE_SCHEMA,
    seccomp_profile_sha256: body.seccomp_profile_sha256,
  });

  try {
    mkdirSync(output, { mode: 0o700 });
  } catch (error) {
    fail("runtime_manifest_v2_release_output_exists", error);
  }
  try {
    writeReadonly(path.join(output, OUTPUT_FILES.manifest), manifestBytes);
    writeReadonly(path.join(output, OUTPUT_FILES.provenance), source.provenance_bytes);
    writeReadonly(path.join(output, OUTPUT_FILES.receipt), receiptBytes);
    syncDirectory(output);
    chmodSync(output, 0o555);
    syncDirectory(output);
    syncDirectory(parent);
  } catch (error) {
    try { chmodSync(output, 0o700); } catch {}
    rmSync(output, { recursive: true, force: true });
    try { syncDirectory(parent); } catch {}
    throw error;
  }
  return Object.freeze({
    contract: OPENCLAW_RUNTIME_MANIFEST_V2_RELEASE_SCHEMA,
    manifest_sha256: sha256(manifestBytes),
    output_files: OUTPUT_FILES,
    private_key_copied: false,
    trust_root_copied: false,
    rootfs_merkle_sha256: body.rootfs.merkle_sha256,
    provenance_sha256: source.provenance_sha256,
  });
}

function main() {
  try {
    const input = parseOptions(process.argv.slice(2));
    const result = buildOpenClawRuntimeManifestV2Release(input);
    process.stdout.write(`${JSON.stringify(result)}\n`);
  } catch (error) {
    process.stderr.write(`${typeof error?.code === "string" ? error.code : "runtime_manifest_v2_release_failed"}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) main();
