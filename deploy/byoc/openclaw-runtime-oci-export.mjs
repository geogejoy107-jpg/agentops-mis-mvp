#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmodSync,
  chownSync,
  closeSync,
  constants,
  createWriteStream,
  existsSync,
  fchmodSync,
  fchownSync,
  fstatSync,
  fsyncSync,
  linkSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readdirSync,
  readFileSync,
  readSync,
  realpathSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";
import { TextDecoder } from "node:util";

import {
  computeOpenClawRuntimeRootfsMerkle,
  OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS,
  OPENCLAW_RUNTIME_ROOTFS_MERKLE_SCHEMA,
} from "./openclaw-runtime-rootfs-merkle.mjs";

export const OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA =
  "agentops_openclaw_runtime_oci_export_provenance_v2";

const DOCKER_PATH = "/usr/bin/docker";
const TAR_PATH = "/usr/bin/tar";
const MV_PATH = "/usr/bin/mv";
const OCI_REFERENCE = /^(?<name>[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*)+)@sha256:(?<digest>[a-f0-9]{64})$/;
const SAFE_ENV = Object.freeze({
  HOME: "/root",
  LANG: "C.UTF-8",
  LC_ALL: "C.UTF-8",
  PATH: "/usr/bin:/bin",
});
const MAX_METADATA_BYTES = 1024 * 1024;
const MAX_LOCAL_PAX_BYTES = 16 * 1024;
const MAX_LOCAL_PAX_RECORDS = 2;
const TAR_BLOCK_BYTES = 512;
const UTF8 = new TextDecoder("utf-8", { fatal: true });

function fail(code, cause) {
  const error = new Error(code, cause ? { cause } : undefined);
  error.code = code;
  throw error;
}

function stableRuntimeErrorCode(error, depth = 0, seen = new Set()) {
  if (!error || depth > 8 || seen.has(error)) return undefined;
  if (typeof error === "object" || typeof error === "function") seen.add(error);
  if (
    typeof error?.code === "string"
    && /^runtime_oci_export_[a-z0-9_]+$/.test(error.code)
  ) return error.code;
  const causeCode = stableRuntimeErrorCode(error?.cause, depth + 1, seen);
  if (causeCode) return causeCode;
  if (Array.isArray(error?.errors)) {
    for (const nested of error.errors.slice(0, 16)) {
      const nestedCode = stableRuntimeErrorCode(nested, depth + 1, seen);
      if (nestedCode) return nestedCode;
    }
  }
  return undefined;
}

function exactOciReference(value) {
  if (typeof value !== "string" || value.length > 512 || value.includes("\0")) {
    fail("runtime_oci_export_reference_invalid");
  }
  const match = OCI_REFERENCE.exec(value);
  if (!match) fail("runtime_oci_export_reference_invalid");
  return Object.freeze({
    exact: value,
    name: match.groups.name,
    digest: `sha256:${match.groups.digest}`,
  });
}

function loopbackRegistry(reference) {
  const registry = reference.name.split("/", 1)[0];
  if (!/^127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(registry)) return false;
  return Number(registry.slice(registry.lastIndexOf(":") + 1)) <= 65_535;
}

function canonicalEmptyPath(value, kind) {
  const prefix = kind === "guest"
    ? "runtime_oci_export_output"
    : "runtime_oci_export_provenance_output";
  if (
    typeof value !== "string"
    || value.includes("\0")
    || !path.isAbsolute(value)
    || path.normalize(value) !== value
    || value === path.parse(value).root
    || value.endsWith(path.sep)
  ) fail(`${prefix}_path_invalid`);
  if (existsSync(value)) fail(`${prefix}_exists`);
  return Object.freeze({ path: value, parent: path.dirname(value), prefix });
}

function validateTrustedParent(candidate) {
  let metadata;
  try {
    metadata = lstatSync(candidate.parent, { bigint: true });
  } catch (error) {
    fail(`${candidate.prefix}_parent_invalid`, error);
  }
  if (
    !metadata.isDirectory()
    || metadata.isSymbolicLink()
    || metadata.uid !== 0n
    || (metadata.mode & 0o022n) !== 0n
    || realpathSync(candidate.parent) !== candidate.parent
  ) fail(`${candidate.prefix}_parent_invalid`);
}

function canonicalOutputs(outputValue, provenanceValue) {
  const guest = canonicalEmptyPath(outputValue, "guest");
  const provenance = canonicalEmptyPath(provenanceValue, "provenance");
  if (guest.parent !== provenance.parent || guest.path === provenance.path) {
    fail("runtime_oci_export_provenance_output_parent_mismatch");
  }
  return Object.freeze({ guest, provenance });
}

function assertReleaseHost() {
  if (process.platform !== "linux") fail("runtime_oci_export_linux_required");
  if (typeof process.geteuid !== "function" || process.geteuid() !== 0) {
    fail("runtime_oci_export_root_required");
  }
}

function hashDescriptor(descriptor, size) {
  const hash = createHash("sha256");
  const buffer = Buffer.allocUnsafe(256 * 1024);
  let offset = 0;
  while (offset < size) {
    const bytes = readSync(descriptor, buffer, 0, Math.min(buffer.length, size - offset), offset);
    if (bytes <= 0) fail("runtime_oci_export_tool_read_failed");
    hash.update(buffer.subarray(0, bytes));
    offset += bytes;
  }
  return hash.digest("hex");
}

function pinExecutable(executable, expectedName) {
  let before;
  try {
    before = lstatSync(executable, { bigint: true });
  } catch (error) {
    fail(`runtime_oci_export_${expectedName}_unavailable`, error);
  }
  if (
    !before.isFile()
    || before.isSymbolicLink()
    || before.uid !== 0n
    || (before.mode & 0o022n) !== 0n
    || realpathSync(executable) !== executable
    || before.size > BigInt(Number.MAX_SAFE_INTEGER)
  ) fail(`runtime_oci_export_${expectedName}_metadata_invalid`);
  const descriptor = openSync(executable, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  const opened = fstatSync(descriptor, { bigint: true });
  if (opened.dev !== before.dev || opened.ino !== before.ino || opened.ctimeNs !== before.ctimeNs) {
    closeSync(descriptor);
    fail(`runtime_oci_export_${expectedName}_identity_changed`);
  }
  const execPath = `/proc/${process.pid}/fd/${descriptor}`;
  let procOpened;
  try {
    procOpened = statSync(execPath, { bigint: true });
  } catch (error) {
    closeSync(descriptor);
    fail(`runtime_oci_export_${expectedName}_proc_fd_unavailable`, error);
  }
  if (
    procOpened.dev !== opened.dev
    || procOpened.ino !== opened.ino
    || procOpened.ctimeNs !== opened.ctimeNs
    || procOpened.size !== opened.size
  ) {
    closeSync(descriptor);
    fail(`runtime_oci_export_${expectedName}_proc_fd_identity_invalid`);
  }
  return Object.freeze({
    descriptor,
    exec_path: execPath,
    identity: Object.freeze({
      path: executable,
      sha256: hashDescriptor(descriptor, Number(opened.size)),
      dev: before.dev.toString(),
      ino: before.ino.toString(),
      mode: Number(before.mode & 0o7777n).toString(8).padStart(4, "0"),
      uid: Number(before.uid),
      gid: Number(before.gid),
      size: Number(before.size),
      ctime_ns: before.ctimeNs.toString(),
    }),
  });
}

function assertPinned(tool, expectedName) {
  const descriptor = fstatSync(tool.descriptor, { bigint: true });
  let pathname;
  let procOpened;
  try {
    pathname = lstatSync(tool.identity.path, { bigint: true });
    procOpened = statSync(tool.exec_path, { bigint: true });
  } catch (error) {
    fail(`runtime_oci_export_${expectedName}_identity_changed`, error);
  }
  for (const current of [descriptor, pathname, procOpened]) {
    if (
      current.dev.toString() !== tool.identity.dev
      || current.ino.toString() !== tool.identity.ino
      || current.ctimeNs.toString() !== tool.identity.ctime_ns
      || current.size !== BigInt(tool.identity.size)
    ) fail(`runtime_oci_export_${expectedName}_identity_changed`);
  }
}

function runPinned(tool, expectedName, args, options = {}) {
  assertPinned(tool, expectedName);
  const result = spawnSync(tool.exec_path, args, {
    encoding: "utf8",
    env: SAFE_ENV,
    maxBuffer: options.maxBuffer ?? MAX_METADATA_BYTES,
    stdio: options.stdio,
    timeout: options.timeout ?? 300_000,
  });
  assertPinned(tool, expectedName);
  if (result.error || result.status !== 0 || result.signal) {
    fail(
      options.failureCode ?? `runtime_oci_export_${expectedName}_command_failed`,
      result.error,
    );
  }
  return result;
}

function canonicalJson(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isSafeInteger(value) || value < 0) fail("runtime_oci_export_provenance_invalid");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => (
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`
    )).join(",")}}`;
  }
  fail("runtime_oci_export_provenance_invalid");
}

function syncDirectory(directory) {
  const descriptor = openSync(
    directory,
    constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
  );
  try {
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
}

function syncTree(root) {
  const metadata = lstatSync(root, { bigint: true });
  if (!metadata.isDirectory() || metadata.isSymbolicLink()) {
    fail("runtime_oci_export_sync_tree_root_invalid");
  }
  for (const name of readdirSync(root, { encoding: "utf8" }).sort()) {
    if (!name || name === "." || name === ".." || name.includes("/") || name.includes("\0")) {
      fail("runtime_oci_export_sync_tree_entry_invalid");
    }
    const target = path.join(root, name);
    const entry = lstatSync(target, { bigint: true });
    if (entry.isDirectory()) {
      syncTree(target);
    } else if (entry.isFile()) {
      const descriptor = openSync(
        target,
        constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
      );
      try {
        const opened = fstatSync(descriptor, { bigint: true });
        if (opened.dev !== entry.dev || opened.ino !== entry.ino || opened.ctimeNs !== entry.ctimeNs) {
          fail("runtime_oci_export_sync_tree_identity_changed");
        }
        fsyncSync(descriptor);
      } finally {
        closeSync(descriptor);
      }
    } else if (!entry.isSymbolicLink()) {
      fail("runtime_oci_export_sync_tree_special_file_rejected");
    }
  }
  syncDirectory(root);
}

function publishGuestRoot(mv, stagingRoot, destination) {
  const before = lstatSync(stagingRoot, { bigint: true });
  if (!before.isDirectory() || before.isSymbolicLink() || existsSync(destination)) {
    fail(existsSync(destination)
      ? "runtime_oci_export_output_exists"
      : "runtime_oci_export_guest_staging_invalid");
  }
  try {
    runPinned(mv, "mv", ["--no-clobber", "--no-target-directory", stagingRoot, destination]);
    if (existsSync(stagingRoot)) {
      fail(existsSync(destination)
        ? "runtime_oci_export_output_exists"
        : "runtime_oci_export_guest_publish_failed");
    }
    const published = lstatSync(destination, { bigint: true });
    if (
      !published.isDirectory()
      || published.isSymbolicLink()
      || published.dev !== before.dev
      || published.ino !== before.ino
    ) fail("runtime_oci_export_guest_publish_identity_invalid");
    return Object.freeze({ dev: published.dev, ino: published.ino });
  } catch (error) {
    if (!existsSync(stagingRoot) && existsSync(destination)) {
      try {
        const candidate = lstatSync(destination, { bigint: true });
        if (candidate.dev === before.dev && candidate.ino === before.ino) {
          rmSync(destination, { recursive: true, force: true });
          syncDirectory(path.dirname(destination));
        }
      } catch {}
    }
    throw error;
  }
}

function canonicalExistingPath(value, code) {
  if (
    typeof value !== "string"
    || value.includes("\0")
    || !path.isAbsolute(value)
    || path.normalize(value) !== value
    || value === path.parse(value).root
    || value.endsWith(path.sep)
  ) fail(code);
  return value;
}

function assertExactKeys(value, expected, code) {
  if (
    !value
    || typeof value !== "object"
    || Array.isArray(value)
    || Object.keys(value).sort().join("\n") !== [...expected].sort().join("\n")
  ) fail(code);
}

function safeIdentityNumber(value) {
  const number = typeof value === "bigint" ? Number(value) : value;
  if (!Number.isSafeInteger(number) || number < 0) {
    fail("runtime_oci_export_identity_invalid");
  }
  return number;
}

function directoryIdentity(metadata) {
  if (!metadata.isDirectory()) fail("runtime_oci_export_identity_invalid");
  return Object.freeze({
    ctime_ns: metadata.ctimeNs.toString(),
    dev: metadata.dev.toString(),
    gid: safeIdentityNumber(metadata.gid),
    ino: metadata.ino.toString(),
    mode: Number(metadata.mode & 0o7777n).toString(8).padStart(4, "0"),
    mtime_ns: metadata.mtimeNs.toString(),
    uid: safeIdentityNumber(metadata.uid),
  });
}

function sameDirectoryIdentity(left, right) {
  return canonicalJson(directoryIdentity(left)) === canonicalJson(directoryIdentity(right));
}

function validateDecimalIdentity(value) {
  return typeof value === "string" && /^(?:0|[1-9][0-9]*)$/.test(value);
}

function validateToolIdentity(value, expectedPath) {
  assertExactKeys(value, [
    "ctime_ns", "dev", "gid", "ino", "mode", "path", "sha256", "size", "uid",
  ], "runtime_oci_export_provenance_tool_identity_invalid");
  if (
    value.path !== expectedPath
    || !/^[a-f0-9]{64}$/.test(value.sha256)
    || !validateDecimalIdentity(value.dev)
    || !validateDecimalIdentity(value.ino)
    || !validateDecimalIdentity(value.ctime_ns)
    || !/^[0-7]{4}$/.test(value.mode)
    || (Number.parseInt(value.mode, 8) & 0o022) !== 0
    || !Number.isSafeInteger(value.uid)
    || value.uid !== 0
    || !Number.isSafeInteger(value.gid)
    || value.gid < 0
    || !Number.isSafeInteger(value.size)
    || value.size < 1
  ) fail("runtime_oci_export_provenance_tool_identity_invalid");
}

function validateGuestRootIdentity(value) {
  assertExactKeys(value, [
    "ctime_ns", "dev", "gid", "ino", "mode", "mtime_ns", "uid",
  ], "runtime_oci_export_provenance_guest_root_identity_invalid");
  if (
    !validateDecimalIdentity(value.dev)
    || !validateDecimalIdentity(value.ino)
    || !validateDecimalIdentity(value.ctime_ns)
    || !validateDecimalIdentity(value.mtime_ns)
    || value.uid !== 0
    || value.gid !== 0
    || value.mode !== "0555"
  ) fail("runtime_oci_export_provenance_guest_root_identity_invalid");
}

function provenanceBytes(value) {
  if (!(value instanceof Uint8Array) || value.byteLength < 2 || value.byteLength > MAX_METADATA_BYTES) {
    fail("runtime_oci_export_provenance_bytes_invalid");
  }
  return Buffer.from(value.buffer, value.byteOffset, value.byteLength);
}

export function parseCanonicalOpenClawRuntimeOciExportProvenance(inputBytes) {
  const bytes = provenanceBytes(inputBytes);
  let receipt;
  try {
    receipt = JSON.parse(UTF8.decode(bytes));
  } catch (error) {
    fail("runtime_oci_export_provenance_invalid", error);
  }
  if (!Buffer.from(canonicalJson(receipt), "utf8").equals(bytes)) {
    fail("runtime_oci_export_provenance_noncanonical");
  }
  assertExactKeys(receipt, [
    "export_archive_sha256",
    "export_policy",
    "export_tool_identity",
    "guest_root",
    "guest_root_identity",
    "oci",
    "platform",
    "rootfs",
    "schema",
    "source_image_id",
  ], "runtime_oci_export_provenance_invalid");
  assertExactKeys(receipt.oci, ["digest", "exact_reference", "name"],
    "runtime_oci_export_provenance_oci_invalid");
  assertExactKeys(receipt.platform, ["architecture", "os"],
    "runtime_oci_export_provenance_platform_invalid");
  assertExactKeys(receipt.rootfs, ["byte_count", "file_count", "merkle_sha256", "schema"],
    "runtime_oci_export_provenance_rootfs_invalid");
  assertExactKeys(receipt.export_policy, ["archive_format", "extraction", "root_directory"],
    "runtime_oci_export_provenance_policy_invalid");
  assertExactKeys(receipt.export_tool_identity, ["docker", "mv", "tar"],
    "runtime_oci_export_provenance_tool_identity_invalid");
  validateToolIdentity(receipt.export_tool_identity.docker, DOCKER_PATH);
  validateToolIdentity(receipt.export_tool_identity.tar, TAR_PATH);
  validateToolIdentity(receipt.export_tool_identity.mv, MV_PATH);
  validateGuestRootIdentity(receipt.guest_root_identity);
  let parsedReference;
  try {
    parsedReference = exactOciReference(receipt.oci.exact_reference);
  } catch (error) {
    fail("runtime_oci_export_provenance_oci_invalid", error);
  }
  if (
    receipt.schema !== OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA
    || !/^[a-f0-9]{64}$/.test(receipt.export_archive_sha256)
    || !/^sha256:[a-f0-9]{64}$/.test(receipt.source_image_id)
    || receipt.platform.os !== "linux"
    || receipt.platform.architecture !== "amd64"
    || receipt.oci.name !== parsedReference.name
    || receipt.oci.digest !== parsedReference.digest
    || receipt.rootfs.schema !== OPENCLAW_RUNTIME_ROOTFS_MERKLE_SCHEMA
    || !/^[a-f0-9]{64}$/.test(receipt.rootfs.merkle_sha256)
    || !Number.isSafeInteger(receipt.rootfs.file_count)
    || receipt.rootfs.file_count < 1
    || !Number.isSafeInteger(receipt.rootfs.byte_count)
    || receipt.rootfs.byte_count < 0
    || ![
      "strict_ustar_only_gnu_longname_and_pax_extensions_rejected_fail_closed",
      "strict_ustar_with_single_entry_path_linkpath_pax_only_gnu_global_and_other_extensions_rejected_fail_closed",
    ].includes(receipt.export_policy.archive_format)
    || receipt.export_policy.extraction
      !== "two_identical_stopped_container_exports_strict_ustar_then_gnu_tar_stream"
    || receipt.export_policy.root_directory !== "normalized_root_0_0_0555"
  ) fail("runtime_oci_export_provenance_invalid");
  canonicalExistingPath(receipt.guest_root, "runtime_oci_export_provenance_guest_root_invalid");
  return Object.freeze(receipt);
}

export function readCommittedOpenClawRuntimeOciExportReceipt(receiptPathValue) {
  const receiptPath = canonicalExistingPath(
    receiptPathValue,
    "runtime_oci_export_commit_receipt_path_invalid",
  );
  const parentCandidate = Object.freeze({
    parent: path.dirname(receiptPath),
    prefix: "runtime_oci_export_commit_receipt",
  });
  validateTrustedParent(parentCandidate);
  let before;
  try {
    before = lstatSync(receiptPath, { bigint: true });
  } catch (error) {
    fail("runtime_oci_export_commit_receipt_missing", error);
  }
  if (
    !before.isFile()
    || before.isSymbolicLink()
    || before.uid !== 0n
    || before.gid !== 0n
    || (before.mode & 0o7777n) !== 0o444n
    || before.nlink !== 1n
    || before.size < 2n
    || before.size > BigInt(MAX_METADATA_BYTES)
  ) fail("runtime_oci_export_commit_receipt_metadata_invalid");
  const descriptor = openSync(
    receiptPath,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
  );
  let bytes;
  try {
    const opened = fstatSync(descriptor, { bigint: true });
    if (
      opened.dev !== before.dev
      || opened.ino !== before.ino
      || opened.ctimeNs !== before.ctimeNs
      || opened.mtimeNs !== before.mtimeNs
      || opened.size !== before.size
    ) fail("runtime_oci_export_commit_receipt_identity_changed");
    bytes = readFileSync(descriptor);
    const after = lstatSync(receiptPath, { bigint: true });
    if (
      after.dev !== opened.dev
      || after.ino !== opened.ino
      || after.ctimeNs !== opened.ctimeNs
      || after.mtimeNs !== opened.mtimeNs
      || after.size !== opened.size
    ) fail("runtime_oci_export_commit_receipt_identity_changed");
  } finally {
    closeSync(descriptor);
  }
  const receipt = parseCanonicalOpenClawRuntimeOciExportProvenance(bytes);
  const guestRoot = canonicalExistingPath(
    receipt.guest_root,
    "runtime_oci_export_commit_guest_root_invalid",
  );
  if (path.dirname(guestRoot) !== path.dirname(receiptPath)) {
    fail("runtime_oci_export_commit_parent_mismatch");
  }
  let guestMetadata;
  try {
    guestMetadata = lstatSync(guestRoot, { bigint: true });
  } catch (error) {
    fail("runtime_oci_export_commit_guest_root_missing", error);
  }
  if (
    !guestMetadata.isDirectory()
    || guestMetadata.isSymbolicLink()
    || realpathSync(guestRoot) !== guestRoot
    || canonicalJson(directoryIdentity(guestMetadata)) !== canonicalJson(receipt.guest_root_identity)
  ) fail("runtime_oci_export_commit_guest_root_identity_mismatch");
  const guestDescriptor = openSync(
    guestRoot,
    constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
  );
  try {
    const opened = fstatSync(guestDescriptor, { bigint: true });
    const pathBefore = lstatSync(guestRoot, { bigint: true });
    if (
      !sameDirectoryIdentity(opened, pathBefore)
      || canonicalJson(directoryIdentity(opened)) !== canonicalJson(receipt.guest_root_identity)
    ) fail("runtime_oci_export_commit_guest_root_identity_mismatch");
    const measured = computeOpenClawRuntimeRootfsMerkle(
      guestRoot,
      OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS,
    );
    const descriptorAfter = fstatSync(guestDescriptor, { bigint: true });
    const pathAfter = lstatSync(guestRoot, { bigint: true });
    if (
      !sameDirectoryIdentity(opened, descriptorAfter)
      || !sameDirectoryIdentity(opened, pathAfter)
      || canonicalJson(directoryIdentity(pathAfter)) !== canonicalJson(receipt.guest_root_identity)
    ) fail("runtime_oci_export_commit_guest_root_identity_changed");
    if (canonicalJson(measured) !== canonicalJson(receipt.rootfs)) {
      fail("runtime_oci_export_commit_rootfs_merkle_mismatch");
    }
  } finally {
    closeSync(guestDescriptor);
  }
  return Object.freeze({
    committed: true,
    guest_root: guestRoot,
    provenance: Object.freeze(receipt),
    provenance_bytes: Buffer.from(bytes),
    provenance_output: receiptPath,
    provenance_sha256: createHash("sha256").update(bytes).digest("hex"),
  });
}

function publishProvenanceReceipt(working, destination, value) {
  const bytes = Buffer.from(canonicalJson(value), "utf8");
  parseCanonicalOpenClawRuntimeOciExportProvenance(bytes);
  const sha256 = createHash("sha256").update(bytes).digest("hex");
  const staging = path.join(working, "provenance-receipt.staging.json");
  const descriptor = openSync(
    staging,
    constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_CLOEXEC,
    0o400,
  );
  try {
    writeFileSync(descriptor, bytes);
    fchownSync(descriptor, 0, 0);
    fchmodSync(descriptor, 0o444);
    fsyncSync(descriptor);
    const metadata = fstatSync(descriptor, { bigint: true });
    if (
      !metadata.isFile()
      || metadata.uid !== 0n
      || metadata.gid !== 0n
      || (metadata.mode & 0o7777n) !== 0o444n
      || metadata.nlink !== 1n
      || metadata.size !== BigInt(bytes.length)
    ) fail("runtime_oci_export_provenance_staging_metadata_invalid");
  } finally {
    closeSync(descriptor);
  }
  syncDirectory(working);
  let linked = false;
  try {
    linkSync(staging, destination);
    linked = true;
  } catch (error) {
    fail(error?.code === "EEXIST"
      ? "runtime_oci_export_provenance_output_exists"
      : "runtime_oci_export_provenance_publish_failed", error);
  }
  try {
    unlinkSync(staging);
    syncDirectory(working);
    syncDirectory(path.dirname(destination));
    const published = lstatSync(destination, { bigint: true });
    if (
      !published.isFile()
      || published.isSymbolicLink()
      || published.uid !== 0n
      || published.gid !== 0n
      || (published.mode & 0o7777n) !== 0o444n
      || published.nlink !== 1n
      || published.size !== BigInt(bytes.length)
    ) fail("runtime_oci_export_provenance_metadata_invalid");
    return Object.freeze({ bytes, sha256 });
  } catch (error) {
    if (linked) {
      try { unlinkSync(destination); } catch {}
      try { syncDirectory(path.dirname(destination)); } catch {}
    }
    if (typeof error?.code === "string" && error.code.startsWith("runtime_oci_export_")) {
      throw error;
    }
    fail("runtime_oci_export_failed", error);
  }
}

function insecureLoopbackRegistryAllowed(reference, input) {
  if (input !== true) return false;
  if (!loopbackRegistry(reference)) fail("runtime_oci_export_insecure_registry_forbidden");
  return true;
}

function inspectManifest(docker, reference, allowInsecureLoopback) {
  const args = ["manifest", "inspect", "--verbose"];
  if (allowInsecureLoopback) args.push("--insecure");
  args.push(reference.exact);
  const result = runPinned(docker, "docker", args, {
    failureCode: "runtime_oci_export_docker_manifest_inspect_failed",
  });
  let value;
  try {
    value = JSON.parse(result.stdout);
  } catch (error) {
    fail("runtime_oci_export_manifest_inspect_invalid", error);
  }
  if (
    Array.isArray(value)
    || value?.Ref !== reference.exact
    || value?.Descriptor?.digest !== reference.digest
    || value?.Descriptor?.platform?.os !== "linux"
    || value?.Descriptor?.platform?.architecture !== "amd64"
    || !value?.SchemaV2Manifest
  ) fail("runtime_oci_export_manifest_list_or_platform_rejected");
}

function inspectImage(docker, reference, allowInsecureLoopback) {
  runPinned(docker, "docker", ["pull", "--platform", "linux/amd64", reference.exact], {
    failureCode: "runtime_oci_export_docker_pull_failed",
  });
  inspectManifest(docker, reference, allowInsecureLoopback);
  const result = runPinned(docker, "docker", [
    "image", "inspect", "--format", "{{json .}}", reference.exact,
  ], { failureCode: "runtime_oci_export_docker_image_inspect_failed" });
  let value;
  try {
    value = JSON.parse(result.stdout);
  } catch (error) {
    fail("runtime_oci_export_inspect_invalid", error);
  }
  if (
    value?.Os !== "linux"
    || value?.Architecture !== "amd64"
    || !Array.isArray(value?.RepoDigests)
    || !value.RepoDigests.includes(reference.exact)
    || typeof value?.Id !== "string"
    || !/^sha256:[a-f0-9]{64}$/.test(value.Id)
  ) fail("runtime_oci_export_inspect_identity_rejected");
  return Object.freeze({ image_id: value.Id });
}

function createContainer(docker, reference, imageId) {
  const result = runPinned(docker, "docker", [
    "create", "--platform", "linux/amd64", "--network", "none", reference.exact,
  ], { failureCode: "runtime_oci_export_docker_create_failed" });
  const id = result.stdout.trim();
  if (!/^[a-f0-9]{64}$/.test(id)) fail("runtime_oci_export_container_id_invalid");
  const inspected = runPinned(docker, "docker", [
    "container", "inspect", "--format", "{{json .}}", id,
  ]);
  let value;
  try {
    value = JSON.parse(inspected.stdout);
  } catch (error) {
    fail("runtime_oci_export_container_inspect_invalid", error);
  }
  if (value?.Image !== imageId || value?.State?.Running !== false) {
    fail("runtime_oci_export_container_identity_rejected");
  }
  return id;
}

function removeContainer(docker, id) {
  if (!id) return;
  try {
    runPinned(docker, "docker", ["container", "rm", "--force", "--volumes", id]);
  } catch {}
}

function tarText(field, code) {
  const end = field.indexOf(0);
  const bytes = end === -1 ? field : field.subarray(0, end);
  if (end !== -1 && field.subarray(end + 1).some((value) => value !== 0)) fail(code);
  try {
    return UTF8.decode(bytes);
  } catch (error) {
    fail(code, error);
  }
}

function tarOctal(field, code) {
  if ((field[0] & 0x80) !== 0) fail(code);
  const raw = field.toString("latin1");
  if (![...field].every((byte) => byte === 0 || byte === 0x20 || (byte >= 0x30 && byte <= 0x37))) {
    fail(code);
  }
  const value = raw.replaceAll("\0", " ").trim();
  if (!/^[0-7]+$/.test(value)) fail(code);
  const parsed = Number.parseInt(value, 8);
  if (!Number.isSafeInteger(parsed) || parsed < 0) fail(code);
  return parsed;
}

function tarChecksum(block) {
  const expected = tarOctal(block.subarray(148, 156), "runtime_oci_export_tar_checksum_invalid");
  let actual = 0;
  for (let index = 0; index < block.length; index += 1) {
    actual += index >= 148 && index < 156 ? 0x20 : block[index];
  }
  if (actual !== expected) fail("runtime_oci_export_tar_checksum_invalid");
}

function canonicalArchivePath(rawName, type) {
  let name = rawName.startsWith("./") ? rawName.slice(2) : rawName;
  if (type === "directory" && name.endsWith("/")) name = name.slice(0, -1);
  if (
    !name
    || name === "."
    || name.startsWith("/")
    || name.includes("\\")
    || name.includes("\0")
    || name.normalize("NFC") !== name
    || path.posix.normalize(name) !== name
    || name.split("/").some((segment) => !segment || segment === "." || segment === "..")
  ) fail("runtime_oci_export_tar_path_rejected");
  return name;
}

function safeSymlinkTarget(entryName, target) {
  if (
    !target
    || target.includes("\\")
    || target.includes("\0")
    || target.normalize("NFC") !== target
  ) fail("runtime_oci_export_tar_symlink_rejected");
  if (target.startsWith("/")) {
    if (
      path.posix.normalize(target) !== target
      || target.split("/").slice(1).some((segment) => !segment || segment === "." || segment === "..")
    ) fail("runtime_oci_export_tar_symlink_rejected");
    return target;
  }
  const resolved = path.posix.dirname(entryName).split("/").filter(Boolean);
  for (const segment of target.split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (resolved.length === 0) fail("runtime_oci_export_tar_symlink_rejected");
      resolved.pop();
    } else {
      resolved.push(segment);
    }
  }
  return target;
}

function assertTarHeaderFormat(block) {
  tarChecksum(block);
  const magic = block.subarray(257, 263).toString("latin1");
  if (magic !== "ustar\0" && magic !== "ustar ") fail("runtime_oci_export_tar_format_rejected");
}

function tarOwnerAndMode(block) {
  const mode = tarOctal(block.subarray(100, 108), "runtime_oci_export_tar_mode_invalid");
  const uid = tarOctal(block.subarray(108, 116), "runtime_oci_export_tar_owner_invalid");
  const gid = tarOctal(block.subarray(116, 124), "runtime_oci_export_tar_owner_invalid");
  if (
    mode > 0o7777
    || (mode & 0o6000) !== 0
    || uid > 0xffff
    || gid > 0xffff
  ) fail("runtime_oci_export_tar_owner_or_mode_rejected");
}

function parseLocalPaxHeader(block) {
  assertTarHeaderFormat(block);
  if (block[156] !== 0x78) fail("runtime_oci_export_tar_special_or_extension_rejected");
  tarOwnerAndMode(block);
  const prefix = tarText(block.subarray(345, 500), "runtime_oci_export_tar_path_rejected");
  const leaf = tarText(block.subarray(0, 100), "runtime_oci_export_tar_path_rejected");
  canonicalArchivePath(prefix ? `${prefix}/${leaf}` : leaf, "regular");
  if (tarText(block.subarray(157, 257), "runtime_oci_export_tar_link_rejected")) {
    fail("runtime_oci_export_tar_link_rejected");
  }
  const size = tarOctal(block.subarray(124, 136), "runtime_oci_export_tar_size_invalid");
  if (size < 1 || size > MAX_LOCAL_PAX_BYTES) {
    fail("runtime_oci_export_tar_pax_size_rejected");
  }
  return Object.freeze({
    header_sha256: createHash("sha256").update(block).digest("hex"),
    size,
  });
}

function parseCanonicalLocalPaxPayload(payload, headerSha256) {
  if (payload.length < 1 || payload.length > MAX_LOCAL_PAX_BYTES || payload.includes(0)) {
    fail("runtime_oci_export_tar_pax_payload_rejected");
  }
  const values = Object.create(null);
  let offset = 0;
  let records = 0;
  while (offset < payload.length) {
    const space = payload.indexOf(0x20, offset);
    if (space < 0) fail("runtime_oci_export_tar_pax_record_rejected");
    const lengthBytes = payload.subarray(offset, space);
    if (
      lengthBytes.length < 1
      || lengthBytes.length > 5
      || lengthBytes[0] === 0x30
      || !lengthBytes.every((byte) => byte >= 0x30 && byte <= 0x39)
    ) fail("runtime_oci_export_tar_pax_record_rejected");
    const length = Number.parseInt(lengthBytes.toString("ascii"), 10);
    if (
      !Number.isSafeInteger(length)
      || String(length) !== lengthBytes.toString("ascii")
      || length < 5
      || offset + length > payload.length
    ) {
      fail("runtime_oci_export_tar_pax_record_rejected");
    }
    const record = payload.subarray(offset, offset + length);
    if (record[length - 1] !== 0x0a) fail("runtime_oci_export_tar_pax_record_rejected");
    const body = record.subarray(space - offset + 1, record.length - 1);
    const equals = body.indexOf(0x3d);
    if (equals < 1) fail("runtime_oci_export_tar_pax_record_rejected");
    const keyBytes = body.subarray(0, equals);
    if (!keyBytes.every((byte) => (
      (byte >= 0x61 && byte <= 0x7a) || byte === 0x5f
    ))) fail("runtime_oci_export_tar_pax_key_rejected");
    const key = keyBytes.toString("ascii");
    if (key !== "path" && key !== "linkpath") {
      fail("runtime_oci_export_tar_pax_key_rejected");
    }
    if (Object.hasOwn(values, key)) fail("runtime_oci_export_tar_pax_duplicate_key_rejected");
    const valueBytes = body.subarray(equals + 1);
    if (valueBytes.length < 1) fail("runtime_oci_export_tar_pax_value_rejected");
    let value;
    try {
      value = UTF8.decode(valueBytes);
    } catch (error) {
      fail("runtime_oci_export_tar_pax_value_rejected", error);
    }
    if (
      value.includes("\0")
      || /[\u0000-\u001f\u007f]/.test(value)
      || value.normalize("NFC") !== value
    ) {
      fail("runtime_oci_export_tar_pax_value_rejected");
    }
    values[key] = value;
    records += 1;
    if (records > MAX_LOCAL_PAX_RECORDS) fail("runtime_oci_export_tar_pax_record_count_rejected");
    offset += length;
  }
  if (offset !== payload.length || records < 1) fail("runtime_oci_export_tar_pax_record_rejected");
  return Object.freeze({
    header_sha256: headerSha256,
    payload_sha256: createHash("sha256").update(payload).digest("hex"),
    values: Object.freeze(values),
  });
}

function parseTarHeader(block, localPax = null) {
  assertTarHeaderFormat(block);
  const typeByte = block[156];
  const type = typeByte === 0 || typeByte === 0x30
    ? "regular"
    : typeByte === 0x35
      ? "directory"
      : typeByte === 0x32
        ? "symlink"
        : null;
  if (!type) fail(typeByte === 0x31
    ? "runtime_oci_export_tar_hardlink_rejected"
    : "runtime_oci_export_tar_special_or_extension_rejected");
  const prefix = tarText(block.subarray(345, 500), "runtime_oci_export_tar_path_rejected");
  const leaf = tarText(block.subarray(0, 100), "runtime_oci_export_tar_path_rejected");
  const name = canonicalArchivePath(
    localPax?.values.path ?? (prefix ? `${prefix}/${leaf}` : leaf),
    type,
  );
  if (
    localPax?.values.path !== undefined
    && localPax.values.path !== name
    && !(type === "directory" && localPax.values.path === `${name}/`)
  ) fail("runtime_oci_export_tar_pax_value_rejected");
  tarOwnerAndMode(block);
  const size = tarOctal(block.subarray(124, 136), "runtime_oci_export_tar_size_invalid");
  if (type !== "regular" && size !== 0) fail("runtime_oci_export_tar_size_invalid");
  if (localPax?.values.linkpath !== undefined && type !== "symlink") {
    fail("runtime_oci_export_tar_pax_linkpath_rejected");
  }
  const link = localPax?.values.linkpath
    ?? tarText(block.subarray(157, 257), "runtime_oci_export_tar_symlink_rejected");
  if (type === "symlink") safeSymlinkTarget(name, link);
  else if (link) fail("runtime_oci_export_tar_link_rejected");
  return Object.freeze({
    local_pax_header_sha256: localPax?.header_sha256 ?? null,
    local_pax_payload_sha256: localPax?.payload_sha256 ?? null,
    header_sha256: createHash("sha256").update(block).digest("hex"),
    name,
    size,
    type,
  });
}

class TarArchiveValidator {
  constructor(expectedHeaders = null) {
    this.archiveHash = createHash("sha256");
    this.buffer = Buffer.alloc(0);
    this.dataBlocks = 0;
    this.ended = false;
    this.entries = new Map();
    this.extension = null;
    this.extensionChunks = null;
    this.extensionBytesRemaining = 0;
    this.headers = [];
    this.expectedHeaders = expectedHeaders;
    this.zeroBlocks = 0;
  }

  update(chunk) {
    this.archiveHash.update(chunk);
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (this.buffer.length >= TAR_BLOCK_BYTES) {
      const block = this.buffer.subarray(0, TAR_BLOCK_BYTES);
      this.buffer = this.buffer.subarray(TAR_BLOCK_BYTES);
      this.#block(block);
    }
  }

  #block(block) {
    if (this.dataBlocks > 0) {
      if (this.extensionChunks) {
        const bytes = Math.min(this.extensionBytesRemaining, TAR_BLOCK_BYTES);
        this.extensionChunks.push(Buffer.from(block.subarray(0, bytes)));
        if (bytes < TAR_BLOCK_BYTES && block.subarray(bytes).some((value) => value !== 0)) {
          fail("runtime_oci_export_tar_pax_padding_rejected");
        }
        this.extensionBytesRemaining -= bytes;
      }
      this.dataBlocks -= 1;
      if (this.dataBlocks === 0 && this.extensionChunks) {
        if (this.extensionBytesRemaining !== 0) fail("runtime_oci_export_tar_truncated");
        const payload = Buffer.concat(this.extensionChunks);
        this.extension = parseCanonicalLocalPaxPayload(payload, this.extension.header_sha256);
        this.extensionChunks = null;
      }
      return;
    }
    const zero = block.every((value) => value === 0);
    if (zero) {
      if (this.extension) fail("runtime_oci_export_tar_pax_unbound_rejected");
      this.zeroBlocks += 1;
      if (this.zeroBlocks >= 2) this.ended = true;
      return;
    }
    if (this.ended || this.zeroBlocks !== 0) fail("runtime_oci_export_tar_trailing_data_rejected");
    if (block[156] === 0x78) {
      if (this.extension) fail("runtime_oci_export_tar_pax_unbound_rejected");
      this.extension = parseLocalPaxHeader(block);
      this.extensionChunks = [];
      this.extensionBytesRemaining = this.extension.size;
      this.dataBlocks = Math.ceil(this.extension.size / TAR_BLOCK_BYTES);
      return;
    }
    const localPax = this.extension;
    this.extension = null;
    const header = parseTarHeader(block, localPax);
    if (this.entries.has(header.name)) fail("runtime_oci_export_tar_duplicate_path_rejected");
    const segments = header.name.split("/");
    let ancestor = "";
    for (const segment of segments.slice(0, -1)) {
      ancestor = ancestor ? `${ancestor}/${segment}` : segment;
      if (this.entries.get(ancestor) === "symlink") {
        fail("runtime_oci_export_tar_symlink_ancestor_rejected");
      }
    }
    if (
      header.type === "symlink"
      && [...this.entries.keys()].some((name) => name.startsWith(`${header.name}/`))
    ) fail("runtime_oci_export_tar_symlink_ancestor_rejected");
    this.entries.set(header.name, header.type);
    const expected = this.expectedHeaders?.[this.headers.length];
    if (this.expectedHeaders && (
      !expected
      || expected.header_sha256 !== header.header_sha256
      || expected.local_pax_header_sha256 !== header.local_pax_header_sha256
      || expected.local_pax_payload_sha256 !== header.local_pax_payload_sha256
      || expected.name !== header.name
      || expected.size !== header.size
      || expected.type !== header.type
    )) fail("runtime_oci_export_tar_second_stream_mismatch");
    this.headers.push(header);
    this.dataBlocks = Math.ceil(header.size / TAR_BLOCK_BYTES);
  }

  finish() {
    if (
      this.buffer.length !== 0
      || this.dataBlocks !== 0
      || this.extension
      || this.extensionChunks
      || !this.ended
    ) {
      fail("runtime_oci_export_tar_truncated");
    }
    if (this.expectedHeaders && this.headers.length !== this.expectedHeaders.length) {
      fail("runtime_oci_export_tar_second_stream_mismatch");
    }
    return Object.freeze({
      archive_sha256: this.archiveHash.digest("hex"),
      entry_count: this.headers.length,
      headers: Object.freeze(this.headers),
    });
  }
}

export function inspectOpenClawRuntimeTarArchive(archivePath) {
  const descriptor = openSync(archivePath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  const validator = new TarArchiveValidator();
  try {
    const buffer = Buffer.allocUnsafe(256 * 1024);
    for (;;) {
      const bytes = readSync(descriptor, buffer, 0, buffer.length, null);
      if (bytes === 0) break;
      validator.update(buffer.subarray(0, bytes));
    }
    return validator.finish();
  } finally {
    closeSync(descriptor);
  }
}

export function verifyOpenClawRuntimeTarArchiveHeaders(archivePath, expectedHeaders) {
  if (!Array.isArray(expectedHeaders)) fail("runtime_oci_export_tar_expected_headers_invalid");
  const descriptor = openSync(archivePath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  const validator = new TarArchiveValidator(expectedHeaders);
  try {
    const buffer = Buffer.allocUnsafe(256 * 1024);
    for (;;) {
      const bytes = readSync(descriptor, buffer, 0, buffer.length, null);
      if (bytes === 0) break;
      validator.update(buffer.subarray(0, bytes));
    }
    return validator.finish();
  } finally {
    closeSync(descriptor);
  }
}

class TarValidationTransform extends Transform {
  constructor(expectedHeaders) {
    super();
    this.validator = new TarArchiveValidator(expectedHeaders);
  }

  _transform(chunk, _encoding, callback) {
    try {
      this.validator.update(chunk);
      callback(null, chunk);
    } catch (error) {
      callback(error);
    }
  }

  _flush(callback) {
    try {
      this.result = this.validator.finish();
      callback();
    } catch (error) {
      callback(error);
    }
  }
}

async function exportToArchive(docker, containerId, archivePath) {
  assertPinned(docker, "docker");
  const child = spawn(docker.exec_path, ["export", containerId], {
    env: SAFE_ENV,
    stdio: ["ignore", "pipe", "ignore"],
  });
  const closed = new Promise((resolve) => child.once("close", (code, signal) => resolve({ code, signal })));
  try {
    await pipeline(child.stdout, createWriteStream(archivePath, { flags: "wx", mode: 0o600 }));
  } catch (error) {
    child.kill("SIGKILL");
    fail("runtime_oci_export_stream_failed", error);
  }
  const status = await closed;
  assertPinned(docker, "docker");
  if (status.code !== 0 || status.signal) fail("runtime_oci_export_docker_command_failed");
}

async function exportDirectlyToTar(docker, tar, containerId, stagingRoot, expected) {
  assertPinned(docker, "docker");
  assertPinned(tar, "tar");
  const dockerChild = spawn(docker.exec_path, ["export", containerId], {
    env: SAFE_ENV,
    stdio: ["ignore", "pipe", "ignore"],
  });
  const tarChild = spawn(tar.exec_path, [
    "--extract", "--file", "-", "--directory", stagingRoot,
    "--numeric-owner", "--same-owner", "--same-permissions",
    "--delay-directory-restore",
    "--warning=no-unknown-keyword",
  ], { env: SAFE_ENV, stdio: ["pipe", "ignore", "ignore"] });
  const dockerClosed = new Promise((resolve) => (
    dockerChild.once("close", (code, signal) => resolve({ code, signal }))
  ));
  const tarClosed = new Promise((resolve) => (
    tarChild.once("close", (code, signal) => resolve({ code, signal }))
  ));
  const validator = new TarValidationTransform(expected.headers);
  try {
    await pipeline(dockerChild.stdout, validator, tarChild.stdin);
  } catch (error) {
    dockerChild.kill("SIGKILL");
    tarChild.kill("SIGKILL");
    fail(stableRuntimeErrorCode(error) ?? "runtime_oci_export_extract_stream_failed", error);
  }
  const [dockerStatus, tarStatus] = await Promise.all([
    dockerClosed,
    tarClosed,
  ]);
  assertPinned(docker, "docker");
  assertPinned(tar, "tar");
  if (dockerStatus.code !== 0 || dockerStatus.signal) fail("runtime_oci_export_docker_command_failed");
  if (tarStatus.code !== 0 || tarStatus.signal) fail("runtime_oci_export_tar_command_failed");
  if (validator.result.archive_sha256 !== expected.archive_sha256) {
    fail("runtime_oci_export_tar_second_stream_mismatch");
  }
  return validator.result.archive_sha256;
}

function canonicalToolIdentity(docker, tar, mv) {
  return Object.freeze({ docker: docker.identity, mv: mv.identity, tar: tar.identity });
}

export async function exportOpenClawRuntimeOciRootfs(input) {
  const reference = exactOciReference(input?.oci);
  const allowInsecureLoopback = insecureLoopbackRegistryAllowed(
    reference,
    input?.allow_insecure_loopback_registry_contract,
  );
  const destinations = canonicalOutputs(input?.output, input?.provenance_output);
  assertReleaseHost();
  validateTrustedParent(destinations.guest);
  let docker;
  let tar;
  let mv;
  let containerId;
  let working;
  let guestPublished = false;
  let provenancePublished = false;
  try {
    docker = pinExecutable(DOCKER_PATH, "docker");
    tar = pinExecutable(TAR_PATH, "tar");
    mv = pinExecutable(MV_PATH, "mv");
    const tarVersion = runPinned(tar, "tar", ["--version"]).stdout;
    if (!tarVersion.startsWith("tar (GNU tar) ")) fail("runtime_oci_export_gnu_tar_required");
    const mvVersion = runPinned(mv, "mv", ["--version"]).stdout;
    if (!mvVersion.startsWith("mv (GNU coreutils) ")) fail("runtime_oci_export_gnu_mv_required");
    const image = inspectImage(docker, reference, allowInsecureLoopback);
    containerId = createContainer(docker, reference, image.image_id);
    working = mkdtempSync(path.join(
      destinations.guest.parent,
      `.${path.basename(destinations.guest.path)}.oci-export-`,
    ));
    chmodSync(working, 0o700);
    const archive = path.join(working, "rootfs.tar");
    const stagingRoot = path.join(working, "guest-root");
    mkdirSync(stagingRoot, { mode: 0o700 });
    // The first complete export is only inspected. A second export from the same
    // never-started container is validated before each header reaches tar, and
    // its full hash must match. Any late drift can only touch this reserved 0700 root.
    await exportToArchive(docker, containerId, archive);
    const firstPass = inspectOpenClawRuntimeTarArchive(archive);
    const exportSha256 = await exportDirectlyToTar(
      docker, tar, containerId, stagingRoot, firstPass,
    );
    rmSync(archive, { force: true });
    chownSync(stagingRoot, 0, 0);
    chmodSync(stagingRoot, 0o555);
    syncTree(stagingRoot);
    const rootfs = computeOpenClawRuntimeRootfsMerkle(
      stagingRoot,
      OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS,
    );
    syncTree(stagingRoot);
    publishGuestRoot(mv, stagingRoot, destinations.guest.path);
    guestPublished = true;
    syncDirectory(destinations.guest.parent);
    const publishedGuestMetadata = lstatSync(destinations.guest.path, { bigint: true });
    const publishedGuestDescriptor = openSync(
      destinations.guest.path,
      constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
    );
    let receipt;
    try {
      const publishedGuestOpened = fstatSync(publishedGuestDescriptor, { bigint: true });
      if (!sameDirectoryIdentity(publishedGuestMetadata, publishedGuestOpened)) {
        fail("runtime_oci_export_guest_publish_identity_invalid");
      }
      const guestRootIdentity = directoryIdentity(publishedGuestOpened);
      if (
        publishedGuestMetadata.isSymbolicLink()
        || guestRootIdentity.uid !== 0
        || guestRootIdentity.gid !== 0
        || guestRootIdentity.mode !== "0555"
      ) fail("runtime_oci_export_guest_publish_identity_invalid");
      const provenance = Object.freeze({
        export_archive_sha256: exportSha256,
        export_policy: Object.freeze({
          archive_format: "strict_ustar_with_single_entry_path_linkpath_pax_only_gnu_global_and_other_extensions_rejected_fail_closed",
          extraction: "two_identical_stopped_container_exports_strict_ustar_then_gnu_tar_stream",
          root_directory: "normalized_root_0_0_0555",
        }),
        export_tool_identity: canonicalToolIdentity(docker, tar, mv),
        guest_root: destinations.guest.path,
        guest_root_identity: guestRootIdentity,
        oci: Object.freeze({
          digest: reference.digest,
          exact_reference: reference.exact,
          name: reference.name,
        }),
        platform: Object.freeze({ architecture: "amd64", os: "linux" }),
        rootfs,
        schema: OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA,
        source_image_id: image.image_id,
      });
      receipt = publishProvenanceReceipt(
        working,
        destinations.provenance.path,
        provenance,
      );
      provenancePublished = true;
      const guestDescriptorAfter = fstatSync(publishedGuestDescriptor, { bigint: true });
      const guestPathAfter = lstatSync(destinations.guest.path, { bigint: true });
      if (
        !sameDirectoryIdentity(publishedGuestOpened, guestDescriptorAfter)
        || !sameDirectoryIdentity(publishedGuestOpened, guestPathAfter)
      ) fail("runtime_oci_export_guest_publish_identity_changed");
    } finally {
      closeSync(publishedGuestDescriptor);
    }
    return Object.freeze({
      provenance_output: destinations.provenance.path,
      provenance_sha256: receipt.sha256,
      rootfs_merkle_sha256: rootfs.merkle_sha256,
      schema: OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA,
    });
  } catch (error) {
    if (provenancePublished) rmSync(destinations.provenance.path, { force: true });
    if (guestPublished) {
      rmSync(destinations.guest.path, { recursive: true, force: true });
      try { syncDirectory(destinations.guest.parent); } catch {}
    }
    const stableCode = stableRuntimeErrorCode(error);
    if (stableCode) fail(stableCode, error);
    fail("runtime_oci_export_failed", error);
  } finally {
    if (docker) removeContainer(docker, containerId);
    if (working) rmSync(working, { recursive: true, force: true });
    if (docker) closeSync(docker.descriptor);
    if (tar) closeSync(tar.descriptor);
    if (mv) closeSync(mv.descriptor);
  }
}

function parseArguments(argv) {
  const required = new Set(["--oci", "--output", "--provenance-output"]);
  const optional = "--allow-insecure-loopback-registry-contract";
  if (argv.length !== 6 && argv.length !== 8) fail("runtime_oci_export_arguments_invalid");
  const values = {};
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    if ((!required.has(name) && name !== optional) || Object.hasOwn(values, name)) {
      fail("runtime_oci_export_arguments_invalid");
    }
    values[name] = argv[index + 1];
  }
  if ([...required].some((name) => !Object.hasOwn(values, name))) {
    fail("runtime_oci_export_arguments_invalid");
  }
  if (Object.hasOwn(values, optional) && values[optional] !== "true") {
    fail("runtime_oci_export_arguments_invalid");
  }
  return {
    allow_insecure_loopback_registry_contract: values[optional] === "true",
    oci: values["--oci"],
    output: values["--output"],
    provenance_output: values["--provenance-output"],
  };
}

const invokedPath = process.argv[1] ? realpathSync(process.argv[1]) : "";
if (invokedPath === realpathSync(fileURLToPath(import.meta.url))) {
  try {
    const result = await exportOpenClawRuntimeOciRootfs(parseArguments(process.argv.slice(2)));
    process.stdout.write(`${canonicalJson(result)}\n`);
  } catch (error) {
    process.stderr.write(`${error?.code ?? "runtime_oci_export_failed"}\n`);
    process.exitCode = 1;
  }
}
