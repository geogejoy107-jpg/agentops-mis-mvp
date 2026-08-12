#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  openSync,
  readdirSync,
  readlinkSync,
  readSync,
} from "node:fs";
import path from "node:path";
import { TextDecoder } from "node:util";

export const OPENCLAW_RUNTIME_ROOTFS_MERKLE_SCHEMA =
  "agentops_openclaw_runtime_rootfs_merkle_v1";

export const OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS = Object.freeze([
  "/opt/agentops-worker/workspace",
  "/run/openclaw-state",
  "/run/secrets/openclaw_config",
  "/tmp",
]);

const EXPECTED_MOUNT_TYPES = new Map([
  ["/opt/agentops-worker/workspace", "directory"],
  ["/run/openclaw-state", "directory"],
  ["/run/secrets/openclaw_config", "regular"],
  ["/tmp", "directory"],
]);
const UTF8_DECODER = new TextDecoder("utf-8", { fatal: true });
const READ_BUFFER_BYTES = 256 * 1024;

function fail(code, cause) {
  const error = new Error(code, cause ? { cause } : undefined);
  error.code = code;
  throw error;
}

function safeStatNumber(value, label) {
  const number = typeof value === "bigint" ? Number(value) : value;
  if (!Number.isSafeInteger(number) || number < 0) fail(`${label}_invalid`);
  return number;
}

function statIdentity(metadata) {
  return Object.freeze({
    dev: metadata.dev,
    gid: metadata.gid,
    ino: metadata.ino,
    mode: metadata.mode,
    nlink: metadata.nlink,
    size: metadata.size,
    uid: metadata.uid,
    ctimeNs: metadata.ctimeNs,
    mtimeNs: metadata.mtimeNs,
  });
}

function sameIdentity(left, right) {
  return left.dev === right.dev
    && left.gid === right.gid
    && left.ino === right.ino
    && left.mode === right.mode
    && left.nlink === right.nlink
    && left.size === right.size
    && left.uid === right.uid
    && left.ctimeNs === right.ctimeNs
    && left.mtimeNs === right.mtimeNs;
}

function checkedLstat(hostPath, code) {
  try {
    return lstatSync(hostPath, { bigint: true, throwIfNoEntry: true });
  } catch (error) {
    fail(code, error);
  }
}

function canonicalRootPath(value) {
  if (
    typeof value !== "string"
    || value.includes("\0")
    || !path.isAbsolute(value)
    || path.normalize(value) !== value
    || (value !== path.parse(value).root && value.endsWith(path.sep))
  ) fail("runtime_rootfs_merkle_root_path_invalid");
  return value;
}

function canonicalGuestPath(value) {
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
  ) fail("runtime_rootfs_merkle_mount_path_invalid");
  const segments = value.slice(1).split("/");
  if (segments.some((segment) => !segment || segment === "." || segment === "..")) {
    fail("runtime_rootfs_merkle_mount_path_invalid");
  }
  return value;
}

function validateMountPaths(values) {
  if (!Array.isArray(values) || values.length !== 4) {
    fail("runtime_rootfs_merkle_mount_paths_invalid");
  }
  const paths = values.map(canonicalGuestPath).sort(compareUtf8);
  if (paths.some((value, index) => value !== OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS[index])) {
    fail("runtime_rootfs_merkle_mount_paths_invalid");
  }
  return Object.freeze(paths);
}

function compareUtf8(left, right) {
  return Buffer.compare(Buffer.from(left, "utf8"), Buffer.from(right, "utf8"));
}

function isWithinGuestPath(candidate, root) {
  return candidate === root || candidate.startsWith(`${root}/`);
}

function hostPathFor(rootPath, guestPath) {
  return guestPath === "/" ? rootPath : path.resolve(rootPath, `.${guestPath}`);
}

function recordMode(metadata) {
  return Number(metadata.mode & 0o7777n).toString(8).padStart(4, "0");
}

function commonRecord(type, guestPath, metadata) {
  return {
    type,
    path: guestPath,
    mode: recordMode(metadata),
    uid: safeStatNumber(metadata.uid, "runtime_rootfs_merkle_uid"),
    gid: safeStatNumber(metadata.gid, "runtime_rootfs_merkle_gid"),
  };
}

function assertSameDevice(metadata, rootDevice) {
  if (metadata.dev !== rootDevice) fail("runtime_rootfs_merkle_mount_crossing_rejected");
}

function assertNotGroupOrWorldWritable(metadata) {
  if ((metadata.mode & 0o022n) !== 0n) {
    fail("runtime_rootfs_merkle_writable_entry_rejected");
  }
}

function assertSingleLink(metadata) {
  if (metadata.nlink !== 1n) fail("runtime_rootfs_merkle_hardlink_rejected");
}

function decodeEntryName(value) {
  let decoded;
  try {
    decoded = UTF8_DECODER.decode(value);
  } catch (error) {
    fail("runtime_rootfs_merkle_entry_name_invalid", error);
  }
  if (
    !decoded
    || decoded === "."
    || decoded === ".."
    || decoded.includes("/")
    || decoded.includes("\0")
    || decoded.normalize("NFC") !== decoded
  ) fail("runtime_rootfs_merkle_entry_name_invalid");
  return decoded;
}

function decodeSymlinkTarget(value) {
  try {
    return UTF8_DECODER.decode(value);
  } catch (error) {
    fail("runtime_rootfs_merkle_symlink_target_rejected", error);
  }
}

function canonicalSymlinkTarget(guestPath, target) {
  if (
    typeof target !== "string"
    || !target
    || target.includes("\\")
    || target.includes("\0")
    || target.normalize("NFC") !== target
  ) fail("runtime_rootfs_merkle_symlink_target_rejected");

  if (target.startsWith("/")) {
    if (
      (target !== "/" && target.endsWith("/"))
      || path.posix.normalize(target) !== target
      || (target !== "/" && target.split("/").slice(1).some((segment) => (
        !segment || segment === "." || segment === ".."
      )))
    ) fail("runtime_rootfs_merkle_symlink_target_rejected");
    return Object.freeze({ target, resolved_guest_path: target });
  }

  const resolved = guestPath === "/"
    ? []
    : path.posix.dirname(guestPath).slice(1).split("/").filter(Boolean);
  for (const segment of target.split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (resolved.length === 0) fail("runtime_rootfs_merkle_symlink_target_rejected");
      resolved.pop();
      continue;
    }
    resolved.push(segment);
  }
  const resolvedGuestPath = `/${resolved.join("/")}`;
  if (path.posix.normalize(resolvedGuestPath) !== resolvedGuestPath) {
    fail("runtime_rootfs_merkle_symlink_target_rejected");
  }
  return Object.freeze({ target, resolved_guest_path: resolvedGuestPath });
}

function openNoFollow(hostPath, directory, code) {
  if (!Number.isInteger(constants.O_NOFOLLOW) || constants.O_NOFOLLOW <= 0) {
    fail("runtime_rootfs_merkle_nofollow_unavailable");
  }
  const directoryFlag = directory ? constants.O_DIRECTORY : 0;
  try {
    return openSync(
      hostPath,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC | directoryFlag,
    );
  } catch (error) {
    fail(code, error);
  }
}

function validateMount(rootPath, guestPath) {
  const metadata = checkedLstat(
    hostPathFor(rootPath, guestPath),
    "runtime_rootfs_merkle_mount_path_missing",
  );
  const expected = EXPECTED_MOUNT_TYPES.get(guestPath);
  if (
    (expected === "directory" && !metadata.isDirectory())
    || (expected === "regular" && !metadata.isFile())
  ) fail("runtime_rootfs_merkle_mount_path_type_invalid");
  return statIdentity(metadata);
}

function scanRegular(hostPath, guestPath, pathBefore, rootDevice) {
  assertSameDevice(pathBefore, rootDevice);
  assertSingleLink(pathBefore);
  assertNotGroupOrWorldWritable(pathBefore);
  const descriptor = openNoFollow(hostPath, false, "runtime_rootfs_merkle_file_open_failed");
  try {
    const opened = fstatSync(descriptor, { bigint: true });
    if (!opened.isFile() || !sameIdentity(statIdentity(pathBefore), statIdentity(opened))) {
      fail("runtime_rootfs_merkle_file_identity_changed");
    }
    const hash = createHash("sha256");
    const buffer = Buffer.allocUnsafe(READ_BUFFER_BYTES);
    let offset = 0n;
    for (;;) {
      const bytesRead = readSync(descriptor, buffer, 0, buffer.byteLength, null);
      if (bytesRead === 0) break;
      hash.update(buffer.subarray(0, bytesRead));
      offset += BigInt(bytesRead);
    }
    const descriptorAfter = fstatSync(descriptor, { bigint: true });
    const pathAfter = checkedLstat(hostPath, "runtime_rootfs_merkle_file_identity_changed");
    if (
      offset !== opened.size
      || !sameIdentity(statIdentity(opened), statIdentity(descriptorAfter))
      || !sameIdentity(statIdentity(opened), statIdentity(pathAfter))
    ) fail("runtime_rootfs_merkle_file_identity_changed");
    return {
      ...commonRecord("regular", guestPath, opened),
      size: safeStatNumber(opened.size, "runtime_rootfs_merkle_file_size"),
      sha256: hash.digest("hex"),
    };
  } finally {
    closeSync(descriptor);
  }
}

function scanSymlink(hostPath, guestPath, before, rootDevice, excludedPaths) {
  assertSameDevice(before, rootDevice);
  assertSingleLink(before);
  let target;
  try {
    target = decodeSymlinkTarget(readlinkSync(hostPath, { encoding: "buffer" }));
  } catch (error) {
    if (error?.code === "runtime_rootfs_merkle_symlink_target_rejected") throw error;
    fail("runtime_rootfs_merkle_symlink_read_failed", error);
  }
  const after = checkedLstat(hostPath, "runtime_rootfs_merkle_symlink_identity_changed");
  if (!after.isSymbolicLink() || !sameIdentity(statIdentity(before), statIdentity(after))) {
    fail("runtime_rootfs_merkle_symlink_identity_changed");
  }
  const canonicalTarget = canonicalSymlinkTarget(guestPath, target);
  if ([...excludedPaths].some((mountPath) => (
    isWithinGuestPath(canonicalTarget.resolved_guest_path, mountPath)
  ))) fail("runtime_rootfs_merkle_symlink_mutable_mount_target_rejected");
  return {
    ...commonRecord("symlink", guestPath, before),
    target: canonicalTarget.target,
    resolved_guest_path: canonicalTarget.resolved_guest_path,
  };
}

function scanDirectory(hostPath, guestPath, rootDevice, excludedPaths, records) {
  const pathBefore = checkedLstat(hostPath, "runtime_rootfs_merkle_directory_identity_changed");
  if (!pathBefore.isDirectory()) fail("runtime_rootfs_merkle_special_file_rejected");
  assertSameDevice(pathBefore, rootDevice);
  assertNotGroupOrWorldWritable(pathBefore);
  const descriptor = openNoFollow(hostPath, true, "runtime_rootfs_merkle_directory_open_failed");
  try {
    const opened = fstatSync(descriptor, { bigint: true });
    if (!opened.isDirectory() || !sameIdentity(statIdentity(pathBefore), statIdentity(opened))) {
      fail("runtime_rootfs_merkle_directory_identity_changed");
    }
    records.push(commonRecord("directory", guestPath, opened));

    let names;
    try {
      names = readdirSync(hostPath, { encoding: "buffer" }).sort(Buffer.compare);
    } catch (error) {
      fail("runtime_rootfs_merkle_directory_read_failed", error);
    }
    for (const nameBytes of names) {
      const name = decodeEntryName(nameBytes);
      const childGuestPath = guestPath === "/" ? `/${name}` : `${guestPath}/${name}`;
      if (excludedPaths.has(childGuestPath)) continue;
      const childHostPath = path.join(hostPath, name);
      const metadata = checkedLstat(childHostPath, "runtime_rootfs_merkle_entry_identity_changed");
      if (metadata.isDirectory()) {
        scanDirectory(childHostPath, childGuestPath, rootDevice, excludedPaths, records);
      } else if (metadata.isFile()) {
        records.push(scanRegular(childHostPath, childGuestPath, metadata, rootDevice));
      } else if (metadata.isSymbolicLink()) {
        records.push(scanSymlink(
          childHostPath,
          childGuestPath,
          metadata,
          rootDevice,
          excludedPaths,
        ));
      } else {
        fail("runtime_rootfs_merkle_special_file_rejected");
      }
    }

    const descriptorAfter = fstatSync(descriptor, { bigint: true });
    const pathAfter = checkedLstat(hostPath, "runtime_rootfs_merkle_directory_identity_changed");
    if (
      !sameIdentity(statIdentity(opened), statIdentity(descriptorAfter))
      || !sameIdentity(statIdentity(opened), statIdentity(pathAfter))
    ) fail("runtime_rootfs_merkle_directory_identity_changed");
  } finally {
    closeSync(descriptor);
  }
}

function canonicalRecordBytes(record) {
  if (record.type === "regular") {
    return Buffer.from(JSON.stringify({
      type: record.type,
      path: record.path,
      mode: record.mode,
      uid: record.uid,
      gid: record.gid,
      size: record.size,
      sha256: record.sha256,
    }), "utf8");
  }
  if (record.type === "symlink") {
    return Buffer.from(JSON.stringify({
      type: record.type,
      path: record.path,
      mode: record.mode,
      uid: record.uid,
      gid: record.gid,
      target: record.target,
      resolved_guest_path: record.resolved_guest_path,
    }), "utf8");
  }
  return Buffer.from(JSON.stringify({
    type: record.type,
    path: record.path,
    mode: record.mode,
    uid: record.uid,
    gid: record.gid,
  }), "utf8");
}

function updateLengthPrefixed(hash, bytes) {
  const length = Buffer.alloc(8);
  length.writeBigUInt64BE(BigInt(bytes.byteLength));
  hash.update(length);
  hash.update(bytes);
}

export function computeOpenClawRuntimeRootfsMerkle(rootPath, guestMountPaths) {
  const root = canonicalRootPath(rootPath);
  const mounts = validateMountPaths(guestMountPaths);
  const rootBefore = checkedLstat(root, "runtime_rootfs_merkle_root_invalid");
  if (!rootBefore.isDirectory() || rootBefore.isSymbolicLink()) {
    fail("runtime_rootfs_merkle_root_invalid");
  }
  const rootDescriptor = openNoFollow(root, true, "runtime_rootfs_merkle_root_open_failed");
  try {
    const rootOpened = fstatSync(rootDescriptor, { bigint: true });
    if (!sameIdentity(statIdentity(rootBefore), statIdentity(rootOpened))) {
      fail("runtime_rootfs_merkle_root_identity_changed");
    }
    const mountIdentities = new Map(mounts.map((guestPath) => [
      guestPath,
      validateMount(root, guestPath),
    ]));
    const records = [];
    scanDirectory(root, "/", rootOpened.dev, new Set(mounts), records);
    for (const guestPath of mounts) {
      if (!sameIdentity(mountIdentities.get(guestPath), validateMount(root, guestPath))) {
        fail("runtime_rootfs_merkle_mount_path_identity_changed");
      }
    }
    const rootDescriptorAfter = fstatSync(rootDescriptor, { bigint: true });
    const rootAfter = checkedLstat(root, "runtime_rootfs_merkle_root_identity_changed");
    if (
      !sameIdentity(statIdentity(rootOpened), statIdentity(rootDescriptorAfter))
      || !sameIdentity(statIdentity(rootOpened), statIdentity(rootAfter))
    ) fail("runtime_rootfs_merkle_root_identity_changed");

    records.sort((left, right) => compareUtf8(left.path, right.path));
    const aggregate = createHash("sha256");
    updateLengthPrefixed(aggregate, Buffer.from(OPENCLAW_RUNTIME_ROOTFS_MERKLE_SCHEMA, "utf8"));
    let byteCount = 0;
    for (const record of records) {
      updateLengthPrefixed(aggregate, canonicalRecordBytes(record));
      if (record.type === "regular") {
        byteCount += record.size;
        if (!Number.isSafeInteger(byteCount)) fail("runtime_rootfs_merkle_byte_count_invalid");
      }
    }
    return Object.freeze({
      merkle_sha256: aggregate.digest("hex"),
      file_count: records.length,
      byte_count: byteCount,
      schema: OPENCLAW_RUNTIME_ROOTFS_MERKLE_SCHEMA,
    });
  } finally {
    closeSync(rootDescriptor);
  }
}
