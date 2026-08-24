import { createHash } from "node:crypto";
import {
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
  realpathSync,
} from "node:fs";
import { isAbsolute, join, normalize, relative, resolve, sep } from "node:path";

const MOUNTINFO_ESCAPE = /\\([0-7]{3})/g;
const SHA256 = /^[a-f0-9]{64}$/;
const MAX_CONTENT_BOUND_FILE_BYTES = 4096;
const MUTABLE_MOUNT_FIELDS = Object.freeze(["kind", "path", "read_only"]);
const CONTENT_BOUND_MUTABLE_MOUNT_FIELDS = Object.freeze(["kind", "path", "read_only", "sha256"]);
const REQUIRED_KINDS = Object.freeze([
  "hosts_file",
  "resolver_config_file",
  "workspace_directory",
  "state_directory",
  "config_file",
  "temp_directory",
]);
const POLICY = Object.freeze({
  config_file: Object.freeze({
    path: "/run/secrets/openclaw_config",
    readOnly: true,
    type: "file",
    uid: 0,
    gid: 0,
    mode: 0o400,
    filesystems: Object.freeze(new Set(["btrfs", "erofs", "ext4", "overlay", "xfs"])),
  }),
  hosts_file: Object.freeze({
    path: "/etc/hosts",
    readOnly: true,
    type: "file",
    uid: 0,
    gid: 2200,
    mode: 0o444,
    contentBound: true,
    filesystems: Object.freeze(new Set(["tmpfs"])),
  }),
  resolver_config_file: Object.freeze({
    path: "/etc/resolv.conf",
    readOnly: true,
    type: "file",
    uid: 0,
    gid: 2200,
    mode: 0o444,
    contentBound: true,
    filesystems: Object.freeze(new Set(["tmpfs"])),
  }),
  workspace_directory: Object.freeze({
    path: "/opt/agentops-worker/workspace",
    readOnly: true,
    type: "directory",
    uid: 0,
    gid: 0,
    filesystems: Object.freeze(new Set(["btrfs", "erofs", "ext4", "overlay", "xfs"])),
  }),
  state_directory: Object.freeze({
    path: "/run/openclaw-state",
    readOnly: false,
    type: "directory",
    uid: 1200,
    gid: 1200,
    mode: 0o700,
    filesystems: Object.freeze(new Set(["tmpfs"])),
  }),
  temp_directory: Object.freeze({
    path: "/tmp",
    readOnly: false,
    type: "directory",
    uid: 1200,
    gid: 1200,
    mode: 0o1777,
    filesystems: Object.freeze(new Set(["tmpfs"])),
  }),
});

function fail(code) {
  throw new Error(code);
}

function canonicalAbsolutePath(value, code) {
  if (
    typeof value !== "string"
    || value.length === 0
    || value.includes("\0")
    || !isAbsolute(value)
    || normalize(value) !== value
    || (value !== "/" && value.endsWith("/"))
  ) fail(code);
  return value;
}

function decodeMountInfoField(value) {
  if (
    typeof value !== "string"
    || value.length === 0
    || /[\t\r\n ]/.test(value)
    || /\\(?![0-7]{3})/.test(value)
  ) {
    fail("runtime_mount_policy_mountinfo_escape_invalid");
  }
  return value.replace(MOUNTINFO_ESCAPE, (_match, octal) => {
    const byte = Number.parseInt(octal, 8);
    if (![0x09, 0x0a, 0x20, 0x5c].includes(byte)) {
      fail("runtime_mount_policy_mountinfo_escape_invalid");
    }
    return String.fromCharCode(byte);
  });
}

function parsePositiveInteger(value) {
  if (!/^[1-9][0-9]*$/.test(value)) fail("runtime_mount_policy_mountinfo_malformed");
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) fail("runtime_mount_policy_mountinfo_malformed");
  return parsed;
}

function parseDevice(value) {
  const match = /^([0-9]+):([0-9]+)$/.exec(value);
  if (!match) fail("runtime_mount_policy_mountinfo_malformed");
  const major = Number(match[1]);
  const minor = Number(match[2]);
  if (!Number.isSafeInteger(major) || !Number.isSafeInteger(minor)) {
    fail("runtime_mount_policy_mountinfo_malformed");
  }
  return { major, minor, value };
}

function parseOptions(value) {
  if (typeof value !== "string" || value.length === 0) {
    fail("runtime_mount_policy_mountinfo_malformed");
  }
  const options = value.split(",");
  if (options.some((option) => option.length === 0 || /[\s\\]/.test(option))) {
    fail("runtime_mount_policy_mountinfo_malformed");
  }
  return new Set(options);
}

export function parseOpenClawMountInfo(mountInfoText) {
  if (typeof mountInfoText !== "string" || mountInfoText.length === 0 || mountInfoText.includes("\0")) {
    fail("runtime_mount_policy_mountinfo_malformed");
  }
  const entries = [];
  const mountIds = new Set();
  for (const line of mountInfoText.split("\n")) {
    if (line.length === 0) continue;
    const fields = line.split(" ");
    if (fields.some((field) => field.length === 0)) fail("runtime_mount_policy_mountinfo_malformed");
    const separator = fields.indexOf("-");
    if (separator < 6 || fields.length - separator !== 4) {
      fail("runtime_mount_policy_mountinfo_malformed");
    }
    const mountId = parsePositiveInteger(fields[0]);
    if (mountIds.has(mountId)) fail("runtime_mount_policy_mount_id_duplicate");
    mountIds.add(mountId);
    const parentId = parsePositiveInteger(fields[1]);
    const device = parseDevice(fields[2]);
    const root = canonicalAbsolutePath(
      decodeMountInfoField(fields[3]),
      "runtime_mount_policy_mount_root_noncanonical",
    );
    const mountPoint = canonicalAbsolutePath(
      decodeMountInfoField(fields[4]),
      "runtime_mount_policy_mount_target_noncanonical",
    );
    const mountOptions = parseOptions(fields[5]);
    const optionalFields = fields.slice(6, separator);
    if (optionalFields.some((field) => field.startsWith("shared:") || field.startsWith("master:"))) {
      fail("runtime_mount_policy_propagation_forbidden");
    }
    if (optionalFields.some((field) => !/^(?:propagate_from:[1-9][0-9]*|unbindable)$/.test(field))) {
      fail("runtime_mount_policy_mountinfo_malformed");
    }
    const filesystemType = fields[separator + 1];
    if (!/^[a-z0-9][a-z0-9._+-]*$/.test(filesystemType)) {
      fail("runtime_mount_policy_mountinfo_malformed");
    }
    const mountSource = decodeMountInfoField(fields[separator + 2]);
    const superOptions = parseOptions(fields[separator + 3]);
    entries.push(Object.freeze({
      mountId,
      parentId,
      device: Object.freeze(device),
      root,
      mountPoint,
      mountOptions,
      optionalFields: Object.freeze(optionalFields),
      filesystemType,
      mountSource,
      superOptions,
    }));
  }
  if (entries.length === 0) fail("runtime_mount_policy_mountinfo_malformed");
  return Object.freeze(entries);
}

function validateMutableMounts(mutableMounts) {
  if (!Array.isArray(mutableMounts) || mutableMounts.length !== REQUIRED_KINDS.length) {
    fail("runtime_mount_policy_mutable_mounts_invalid");
  }
  const seenKinds = new Set();
  let previousPath = null;
  return mutableMounts.map((mount) => {
    if (
      mount === null
      || typeof mount !== "object"
      || Array.isArray(mount)
      || !Object.hasOwn(POLICY, mount.kind)
      || seenKinds.has(mount.kind)
    ) fail("runtime_mount_policy_mutable_mounts_invalid");
    const policy = POLICY[mount.kind];
    const expectedFields = policy.contentBound
      ? CONTENT_BOUND_MUTABLE_MOUNT_FIELDS
      : MUTABLE_MOUNT_FIELDS;
    if (Object.keys(mount).sort().join(",") !== [...expectedFields].sort().join(",")) {
      fail("runtime_mount_policy_mutable_mounts_invalid");
    }
    seenKinds.add(mount.kind);
    const guestPath = canonicalAbsolutePath(mount.path, "runtime_mount_policy_guest_path_invalid");
    if (
      guestPath === "/"
      || guestPath !== policy.path
      || mount.read_only !== policy.readOnly
      || (previousPath !== null && Buffer.compare(Buffer.from(previousPath), Buffer.from(guestPath)) >= 0)
    ) {
      fail("runtime_mount_policy_mutable_mounts_invalid");
    }
    if (policy.contentBound && (typeof mount.sha256 !== "string" || !SHA256.test(mount.sha256))) {
      fail("runtime_mount_policy_mutable_mount_sha256_invalid");
    }
    previousPath = guestPath;
    return Object.freeze({
      kind: mount.kind,
      path: guestPath,
      read_only: mount.read_only,
      ...(policy.contentBound ? { sha256: mount.sha256 } : {}),
    });
  });
}

function assertTargetsDisjoint(targets) {
  for (let left = 0; left < targets.length; left += 1) {
    for (let right = left + 1; right < targets.length; right += 1) {
      const leftPath = `${targets[left]}${sep}`;
      const rightPath = `${targets[right]}${sep}`;
      if (targets[left] === targets[right] || leftPath.startsWith(rightPath) || rightPath.startsWith(leftPath)) {
        fail("runtime_mount_policy_targets_overlap");
      }
    }
  }
}

function assertMountFlags(entry, policy) {
  const options = entry.mountOptions;
  const expectedAccess = policy.readOnly ? "ro" : "rw";
  const oppositeAccess = policy.readOnly ? "rw" : "ro";
  if (!options.has(expectedAccess) || options.has(oppositeAccess)) {
    fail("runtime_mount_policy_access_mode_invalid");
  }
  const requiredFlags = new Map([
    ["nosuid", "suid"],
    ["nodev", "dev"],
    ["noexec", "exec"],
  ]);
  for (const [required, forbidden] of requiredFlags) {
    if (!options.has(required)) fail("runtime_mount_policy_required_flag_missing");
    if (options.has(forbidden)) fail("runtime_mount_policy_flag_conflict");
  }
  if (!policy.filesystems.has(entry.filesystemType)) {
    fail("runtime_mount_policy_filesystem_invalid");
  }
}

function assertFilesystemObject(stat, policy) {
  if (policy.type === "file" ? !stat.isFile() : !stat.isDirectory()) {
    fail("runtime_mount_policy_object_type_invalid");
  }
  if (stat.uid !== policy.uid || stat.gid !== policy.gid) {
    fail("runtime_mount_policy_owner_invalid");
  }
  const mode = stat.mode & 0o7777;
  if (policy.mode !== undefined && mode !== policy.mode) {
    fail("runtime_mount_policy_mode_invalid");
  }
  if (policy.type === "directory" && policy.mode === undefined && (mode & 0o222) !== 0) {
    fail("runtime_mount_policy_mode_invalid");
  }
  if (policy.contentBound && stat.nlink !== 1) {
    fail("runtime_mount_policy_link_count_invalid");
  }
}

function fileIdentity(stat) {
  return [
    stat.dev,
    stat.ino,
    stat.mode,
    stat.nlink,
    stat.size,
    stat.ctimeMs,
    stat.mtimeMs,
  ].map(String).join(":");
}

function verifyContentDigest(target, pathBefore, expectedSha256) {
  if (!Number.isInteger(constants.O_NOFOLLOW) || constants.O_NOFOLLOW <= 0) {
    fail("runtime_mount_policy_nofollow_unavailable");
  }
  let descriptor;
  try {
    descriptor = openSync(
      target,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
    );
  } catch (error) {
    fail(error?.code === "ELOOP"
      ? "runtime_mount_policy_content_symlink_rejected"
      : "runtime_mount_policy_content_open_failed");
  }
  try {
    const opened = fstatSync(descriptor);
    if (
      !opened.isFile()
      || opened.nlink !== 1
      || opened.size < 1
      || opened.size > MAX_CONTENT_BOUND_FILE_BYTES
      || fileIdentity(opened) !== fileIdentity(pathBefore)
    ) fail("runtime_mount_policy_content_identity_changed");
    const bytes = readFileSync(descriptor);
    const descriptorAfter = fstatSync(descriptor);
    const pathAfter = lstatSync(target);
    if (
      bytes.byteLength !== opened.size
      || fileIdentity(descriptorAfter) !== fileIdentity(opened)
      || fileIdentity(pathAfter) !== fileIdentity(opened)
    ) fail("runtime_mount_policy_content_identity_changed");
    const actualSha256 = createHash("sha256").update(bytes).digest("hex");
    if (actualSha256 !== expectedSha256) fail("runtime_mount_policy_content_sha256_mismatch");
    return actualSha256;
  } finally {
    closeSync(descriptor);
  }
}

export function verifyOpenClawRuntimeMountPolicy({
  guestRoot,
  mutableMounts,
  mountInfoText,
  platform = process.platform,
  readMountInfo = () => readFileSync("/proc/self/mountinfo", "utf8"),
  lstatPath = lstatSync,
  realpathPath = realpathSync,
} = {}) {
  if (platform !== "linux") fail("runtime_mount_policy_unsupported_platform");
  const root = canonicalAbsolutePath(guestRoot, "runtime_mount_policy_guest_root_invalid");
  if (resolve(root) !== root || realpathPath(root) !== root) {
    fail("runtime_mount_policy_guest_root_noncanonical");
  }
  const mounts = validateMutableMounts(mutableMounts);
  const targets = mounts.map((mount) => {
    const target = join(root, mount.path.slice(1));
    const withinRoot = relative(root, target);
    if (withinRoot === "" || withinRoot === ".." || withinRoot.startsWith(`..${sep}`) || isAbsolute(withinRoot)) {
      fail("runtime_mount_policy_guest_path_invalid");
    }
    return target;
  });
  assertTargetsDisjoint(targets);
  for (const target of targets) {
    if (realpathPath(target) !== target) fail("runtime_mount_policy_target_noncanonical");
  }

  const entries = parseOpenClawMountInfo(mountInfoText ?? readMountInfo());
  const byTarget = new Map();
  for (const entry of entries) {
    if (!byTarget.has(entry.mountPoint)) byTarget.set(entry.mountPoint, []);
    byTarget.get(entry.mountPoint).push(entry);
  }
  const selectedIds = new Set();
  const evidence = mounts.map((mount, index) => {
    const matches = byTarget.get(targets[index]) ?? [];
    if (matches.length !== 1) fail("runtime_mount_policy_independent_mount_missing");
    const entry = matches[0];
    if (selectedIds.has(entry.mountId)) fail("runtime_mount_policy_mount_id_duplicate");
    selectedIds.add(entry.mountId);
    const policy = POLICY[mount.kind];
    assertMountFlags(entry, policy);
    const stat = lstatPath(targets[index]);
    assertFilesystemObject(stat, policy);
    const contentSha256 = policy.contentBound
      ? verifyContentDigest(targets[index], stat, mount.sha256)
      : null;
    return Object.freeze({
      kind: mount.kind,
      guest_path: mount.path,
      host_path: targets[index],
      mount_id: entry.mountId,
      parent_mount_id: entry.parentId,
      device: entry.device.value,
      mount_root: entry.root,
      mount_target: entry.mountPoint,
      filesystem_type: entry.filesystemType,
      mount_options: Object.freeze([...entry.mountOptions].sort()),
      read_only: policy.readOnly,
      uid: stat.uid,
      gid: stat.gid,
      mode: (stat.mode & 0o7777).toString(8).padStart(4, "0"),
      content_sha256: contentSha256,
    });
  });

  return Object.freeze({
    contract: "agentops_openclaw_runtime_nested_mount_policy_v1",
    ok: true,
    platform: "linux",
    guest_root: root,
    mounts: Object.freeze(evidence),
  });
}
