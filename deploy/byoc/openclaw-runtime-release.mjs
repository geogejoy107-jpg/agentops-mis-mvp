#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
} from "node:fs";
import path from "node:path";

import {
  canonicalRuntimeManifestV2Bytes,
  parseCanonicalRuntimeManifestV2Envelope,
} from "./openclaw-runtime-manifest-v2.mjs";
import {
  OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA,
  parseCanonicalOpenClawRuntimeOciExportProvenance,
} from "./openclaw-runtime-oci-export.mjs";

export const OPENCLAW_RUNTIME_RELEASE_SCHEMA =
  "agentops_openclaw_runtime_manifest_v2_release_v2";
export const OPENCLAW_RUNTIME_RELEASE_FILES = Object.freeze([
  "openclaw-runtime-manifest-metadata-receipt.json",
  "openclaw-runtime-manifest.json",
  "openclaw-runtime-oci-export-provenance.json",
]);

const SHA256 = /^[a-f0-9]{64}$/;
const MAX_FILE_BYTES = 1024 * 1024;

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function sameIdentity(left, right) {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.uid === right.uid
    && left.gid === right.gid
    && left.mode === right.mode
    && left.nlink === right.nlink
    && left.size === right.size
    && left.ctimeNs === right.ctimeNs
    && left.mtimeNs === right.mtimeNs;
}

function exactObject(value, fields, code) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(code);
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((name, index) => name !== expected[index])) {
    fail(code);
  }
  return value;
}

function canonicalJson(bytes, code) {
  let value;
  try {
    value = JSON.parse(new TextDecoder("utf8", { fatal: true }).decode(bytes));
  } catch {
    fail(code);
  }
  if (!Buffer.from(JSON.stringify(value), "utf8").equals(bytes)) fail(`${code}_noncanonical`);
  return value;
}

function readCommittedFile(target, expectedOwner) {
  const before = lstatSync(target, { bigint: true });
  if (
    !before.isFile()
    || before.isSymbolicLink()
    || before.nlink !== 1n
    || before.uid !== BigInt(expectedOwner.uid)
    || before.gid !== BigInt(expectedOwner.gid)
    || (before.mode & 0o7777n) !== 0o444n
    || before.size < 2n
    || before.size > BigInt(MAX_FILE_BYTES)
  ) fail("runtime_release_file_metadata_invalid");
  const descriptor = openSync(target, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  try {
    const opened = fstatSync(descriptor, { bigint: true });
    if (!sameIdentity(before, opened)) fail("runtime_release_file_identity_changed");
    const bytes = readFileSync(descriptor);
    const after = lstatSync(target, { bigint: true });
    if (!sameIdentity(opened, after)) fail("runtime_release_file_identity_changed");
    return bytes;
  } finally {
    closeSync(descriptor);
  }
}

function validateReceipt(value, manifestBytes, provenanceBytes, trustRootBytes) {
  const receipt = exactObject(value, [
    "claims",
    "cgroup_policy_sha256",
    "created_at",
    "expires_at",
    "files",
    "issuer",
    "key_id",
    "oci_export_provenance",
    "oci_image",
    "platform",
    "private_key_copied",
    "rootfs",
    "schema",
    "seccomp_profile_sha256",
    "trust_root_copied",
    "trust_root_sha256",
  ], "runtime_release_receipt_fields_invalid");
  if (
    receipt.schema !== OPENCLAW_RUNTIME_RELEASE_SCHEMA
    || receipt.private_key_copied !== false
    || receipt.trust_root_copied !== false
    || !SHA256.test(String(receipt.trust_root_sha256 || ""))
    || receipt.trust_root_sha256 !== sha256(trustRootBytes)
  ) fail("runtime_release_receipt_invalid");
  const files = exactObject(
    receipt.files,
    ["manifest", "provenance"],
    "runtime_release_receipt_files_invalid",
  );
  const provenance = exactObject(
    receipt.oci_export_provenance,
    ["schema", "sha256"],
    "runtime_release_receipt_provenance_invalid",
  );
  if (
    provenance.schema !== OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA
    || !SHA256.test(String(provenance.sha256 || ""))
    || provenance.sha256 !== sha256(provenanceBytes)
  ) fail("runtime_release_receipt_provenance_invalid");
  const provenanceFile = exactObject(
    files.provenance,
    ["name", "sha256"],
    "runtime_release_receipt_provenance_file_invalid",
  );
  if (
    provenanceFile.name !== "openclaw-runtime-oci-export-provenance.json"
    || provenanceFile.sha256 !== provenance.sha256
  ) fail("runtime_release_receipt_provenance_file_invalid");
  const manifest = exactObject(
    files.manifest,
    ["name", "sha256"],
    "runtime_release_receipt_manifest_invalid",
  );
  if (
    manifest.name !== "openclaw-runtime-manifest.json"
    || !SHA256.test(String(manifest.sha256 || ""))
    || manifest.sha256 !== sha256(manifestBytes)
  ) fail("runtime_release_receipt_manifest_invalid");
  let envelope;
  let source;
  try {
    envelope = parseCanonicalRuntimeManifestV2Envelope(manifestBytes);
    source = parseCanonicalOpenClawRuntimeOciExportProvenance(provenanceBytes);
  } catch {
    fail("runtime_release_manifest_invalid");
  }
  if (
    !canonicalRuntimeManifestV2Bytes(receipt.oci_image).equals(
      canonicalRuntimeManifestV2Bytes(envelope.body.oci_image),
    )
    || !canonicalRuntimeManifestV2Bytes(receipt.rootfs).equals(
      canonicalRuntimeManifestV2Bytes(envelope.body.rootfs),
    )
    || !canonicalRuntimeManifestV2Bytes(source.oci).equals(canonicalRuntimeManifestV2Bytes({
      digest: envelope.body.oci_image.digest,
      exact_reference: `${envelope.body.oci_image.name}@${envelope.body.oci_image.digest}`,
      name: envelope.body.oci_image.name,
    }))
    || !canonicalRuntimeManifestV2Bytes({
      byte_count: source.rootfs.byte_count,
      file_count: source.rootfs.file_count,
      merkle_sha256: source.rootfs.merkle_sha256,
    }).equals(
      canonicalRuntimeManifestV2Bytes(envelope.body.rootfs),
    )
    || source.platform.os !== envelope.body.platform.os
    || source.platform.architecture !== envelope.body.platform.arch
  ) fail("runtime_release_receipt_manifest_binding_invalid");
  return receipt;
}

export function readCommittedOpenClawRuntimeRelease(
  releaseRoot,
  trustRootBytesValue,
  { expectedOwner = { uid: 0, gid: 0 } } = {},
) {
  if (
    typeof releaseRoot !== "string"
    || !path.isAbsolute(releaseRoot)
    || path.resolve(releaseRoot) !== releaseRoot
    || realpathSync(releaseRoot) !== releaseRoot
    || !Number.isSafeInteger(expectedOwner.uid)
    || !Number.isSafeInteger(expectedOwner.gid)
  ) fail("runtime_release_root_invalid");
  const before = lstatSync(releaseRoot, { bigint: true });
  if (
    !before.isDirectory()
    || before.isSymbolicLink()
    || before.uid !== BigInt(expectedOwner.uid)
    || before.gid !== BigInt(expectedOwner.gid)
    || (before.mode & 0o7777n) !== 0o555n
  ) fail("runtime_release_root_metadata_invalid");
  const entries = readdirSync(releaseRoot).sort();
  if (
    entries.length !== OPENCLAW_RUNTIME_RELEASE_FILES.length
    || entries.some((name, index) => name !== OPENCLAW_RUNTIME_RELEASE_FILES[index])
  ) fail("runtime_release_file_set_invalid");
  const manifestBytes = readCommittedFile(
    path.join(releaseRoot, "openclaw-runtime-manifest.json"),
    expectedOwner,
  );
  const receiptBytes = readCommittedFile(
    path.join(releaseRoot, "openclaw-runtime-manifest-metadata-receipt.json"),
    expectedOwner,
  );
  const provenanceBytes = readCommittedFile(
    path.join(releaseRoot, "openclaw-runtime-oci-export-provenance.json"),
    expectedOwner,
  );
  const after = lstatSync(releaseRoot, { bigint: true });
  if (!sameIdentity(before, after)) fail("runtime_release_root_identity_changed");
  const trustRootBytes = Buffer.from(trustRootBytesValue);
  const receipt = validateReceipt(
    canonicalJson(receiptBytes, "runtime_release_receipt_invalid"),
    manifestBytes,
    provenanceBytes,
    trustRootBytes,
  );
  return Object.freeze({ manifestBytes, provenanceBytes, receipt, receiptBytes });
}
