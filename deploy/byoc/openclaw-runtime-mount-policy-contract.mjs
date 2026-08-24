#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { chmodSync, existsSync, linkSync, lstatSync, mkdirSync, mkdtempSync, realpathSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  parseOpenClawMountInfo,
  verifyOpenClawRuntimeMountPolicy,
} from "./openclaw-runtime-mount-policy.mjs";

const scratch = mkdtempSync(join(realpathSync(tmpdir()), "agentops-mount-policy-"));
const guestRoot = join(scratch, "guest root");
const paths = Object.freeze({
  hosts_file: "/etc/hosts",
  resolver_config_file: "/etc/resolv.conf",
  workspace_directory: "/opt/agentops-worker/workspace",
  state_directory: "/run/openclaw-state",
  config_file: "/run/secrets/openclaw_config",
  temp_directory: "/tmp",
});
const HOSTS_BYTES = Buffer.from(
  "127.0.0.1 localhost\n::1 localhost\n172.31.250.3 openclaw-egress-gateway\n",
  "utf8",
);
const RESOLVER_CONFIG_BYTES = Buffer.from(
  "nameserver 127.0.0.1\noptions timeout:1 attempts:1 ndots:0\n",
  "utf8",
);
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const mounts = Object.freeze([
  Object.freeze({ kind: "hosts_file", path: paths.hosts_file, read_only: true, sha256: sha256(HOSTS_BYTES) }),
  Object.freeze({ kind: "resolver_config_file", path: paths.resolver_config_file, read_only: true, sha256: sha256(RESOLVER_CONFIG_BYTES) }),
  Object.freeze({ kind: "workspace_directory", path: paths.workspace_directory, read_only: true }),
  Object.freeze({ kind: "state_directory", path: paths.state_directory, read_only: false }),
  Object.freeze({ kind: "config_file", path: paths.config_file, read_only: true }),
  Object.freeze({ kind: "temp_directory", path: paths.temp_directory, read_only: false }),
]);

const hostPath = (guestPath) => join(guestRoot, guestPath.slice(1));
const escapeMountInfo = (value) => value.replace(/\\/g, "\\134").replace(/ /g, "\\040").replace(/\t/g, "\\011").replace(/\n/g, "\\012");

function fixtureStat(path, ownerOverrides = {}) {
  const stat = lstatSync(path);
  const kind = Object.entries(paths).find(([, guestPath]) => hostPath(guestPath) === path)?.[0];
  const owners = {
    config_file: { uid: 0, gid: 0 },
    hosts_file: { uid: 0, gid: 2200 },
    resolver_config_file: { uid: 0, gid: 2200 },
    workspace_directory: { uid: 0, gid: 0 },
    state_directory: { uid: 1200, gid: 1200 },
    temp_directory: { uid: 1200, gid: 1200 },
    ...ownerOverrides,
  };
  return Object.assign(Object.create(Object.getPrototypeOf(stat)), stat, owners[kind] ?? {});
}

function mountInfo(overrides = {}) {
  const entries = [
    { id: 41, parent: 1, dev: "0:70", root: "/hosts", target: hostPath(paths.hosts_file), options: "ro,nosuid,nodev,noexec", optional: "", fs: "tmpfs", source: "tmpfs", superOptions: "rw" },
    { id: 42, parent: 1, dev: "0:70", root: "/resolv.conf", target: hostPath(paths.resolver_config_file), options: "ro,nosuid,nodev,noexec", optional: "", fs: "tmpfs", source: "tmpfs", superOptions: "rw" },
    { id: 43, parent: 1, dev: "8:1", root: "/srv/workspace", target: hostPath(paths.workspace_directory), options: "ro,nosuid,nodev,noexec", optional: "", fs: "ext4", source: "/dev/sda1", superOptions: "rw" },
    { id: 44, parent: 1, dev: "0:71", root: "/", target: hostPath(paths.state_directory), options: "rw,nosuid,nodev,noexec", optional: "", fs: "tmpfs", source: "tmpfs", superOptions: "rw" },
    { id: 45, parent: 1, dev: "8:1", root: "/srv/openclaw/config", target: hostPath(paths.config_file), options: "ro,nosuid,nodev,noexec", optional: "", fs: "ext4", source: "/dev/sda1", superOptions: "rw" },
    { id: 46, parent: 1, dev: "0:72", root: "/", target: hostPath(paths.temp_directory), options: "rw,nosuid,nodev,noexec", optional: "", fs: "tmpfs", source: "tmpfs", superOptions: "rw" },
  ].map((entry) => ({ ...entry, ...(overrides[entry.id] ?? {}) }));
  return entries.map((entry) => [
    entry.id,
    entry.parent,
    entry.dev,
    escapeMountInfo(entry.root),
    escapeMountInfo(entry.target),
    entry.options,
    entry.optional,
    "-",
    entry.fs,
    escapeMountInfo(entry.source),
    entry.superOptions,
  ].filter((field) => field !== "").join(" ")).join("\n") + "\n";
}

function verify(overrides = {}) {
  return verifyOpenClawRuntimeMountPolicy({
    guestRoot,
    mutableMounts: mounts,
    mountInfoText: mountInfo(),
    platform: "linux",
    lstatPath: fixtureStat,
    ...overrides,
  });
}

function rejects(overrides, pattern) {
  assert.throws(() => verify(overrides), pattern);
}

try {
  mkdirSync(join(guestRoot, "etc"), { recursive: true, mode: 0o755 });
  writeFileSync(hostPath(paths.hosts_file), HOSTS_BYTES, { mode: 0o444 });
  writeFileSync(hostPath(paths.resolver_config_file), RESOLVER_CONFIG_BYTES, { mode: 0o444 });
  mkdirSync(hostPath(paths.workspace_directory), { recursive: true, mode: 0o755 });
  mkdirSync(hostPath(paths.state_directory), { recursive: true, mode: 0o755 });
  mkdirSync(join(guestRoot, "run", "secrets"), { recursive: true, mode: 0o755 });
  writeFileSync(hostPath(paths.config_file), "{}\n", { mode: 0o400 });
  mkdirSync(hostPath(paths.temp_directory), { recursive: true, mode: 0o1777 });
  chmodSync(hostPath(paths.workspace_directory), 0o555);
  chmodSync(hostPath(paths.state_directory), 0o700);
  chmodSync(hostPath(paths.config_file), 0o400);
  chmodSync(hostPath(paths.temp_directory), 0o1777);
  chmodSync(hostPath(paths.hosts_file), 0o444);
  chmodSync(hostPath(paths.resolver_config_file), 0o444);

  const result = verify();
  assert.equal(result.ok, true);
  assert.equal(result.contract, "agentops_openclaw_runtime_nested_mount_policy_v1");
  assert.equal(result.mounts.length, 6);
  assert.deepEqual(result.mounts.map((entry) => entry.mount_id), [41, 42, 43, 44, 45, 46]);
  assert.deepEqual(result.mounts.map((entry) => entry.device), ["0:70", "0:70", "8:1", "0:71", "8:1", "0:72"]);
  assert.ok(result.mounts.every((entry) => entry.host_path.startsWith(`${guestRoot}/`)));
  assert.equal(result.mounts[0].mount_target, hostPath(paths.hosts_file));
  assert.deepEqual(
    result.mounts.slice(0, 2).map((entry) => [entry.filesystem_type, entry.uid, entry.gid, entry.mode]),
    [["tmpfs", 0, 2200, "0444"], ["tmpfs", 0, 2200, "0444"]],
  );
  assert.deepEqual(
    result.mounts.slice(0, 2).map((entry) => entry.content_sha256),
    [sha256(HOSTS_BYTES), sha256(RESOLVER_CONFIG_BYTES)],
  );
  assert.ok(result.mounts.slice(2).every((entry) => entry.content_sha256 === null));

  const parsedEscaped = parseOpenClawMountInfo(mountInfo());
  assert.equal(parsedEscaped[0].mountPoint, hostPath(paths.hosts_file));
  assert.ok(parsedEscaped[0].mountPoint.includes("guest root"));

  rejects({ mountInfoText: mountInfo().split("\n").filter((line) => !line.startsWith("43 ")).join("\n") }, /runtime_mount_policy_independent_mount_missing/);
  rejects({ mountInfoText: mountInfo({ 41: { options: "rw,nosuid,nodev,noexec" } }) }, /runtime_mount_policy_access_mode_invalid/);
  rejects({ mountInfoText: mountInfo({ 41: { fs: "ext4" } }) }, /runtime_mount_policy_filesystem_invalid/);
  rejects({ mountInfoText: mountInfo({ 42: { fs: "overlay" } }) }, /runtime_mount_policy_filesystem_invalid/);
  rejects({ mountInfoText: mountInfo({ 44: { options: "ro,nosuid,nodev,noexec" } }) }, /runtime_mount_policy_access_mode_invalid/);
  rejects({ mountInfoText: mountInfo({ 44: { options: "rw,nodev,noexec" } }) }, /runtime_mount_policy_required_flag_missing/);
  rejects({ mountInfoText: mountInfo({ 44: { options: "rw,nosuid,noexec" } }) }, /runtime_mount_policy_required_flag_missing/);
  rejects({ mountInfoText: mountInfo({ 44: { options: "rw,nosuid,nodev" } }) }, /runtime_mount_policy_required_flag_missing/);
  rejects({ mountInfoText: mountInfo({ 44: { options: "rw,nosuid,suid,nodev,noexec" } }) }, /runtime_mount_policy_flag_conflict/);
  rejects({ mountInfoText: mountInfo({ 44: { fs: "proc" } }) }, /runtime_mount_policy_filesystem_invalid/);
  rejects({ mountInfoText: mountInfo({ 43: { fs: "tmpfs" } }) }, /runtime_mount_policy_filesystem_invalid/);
  rejects({ mountInfoText: mountInfo({ 44: { fs: "ext4" } }) }, /runtime_mount_policy_filesystem_invalid/);
  rejects({ mountInfoText: mountInfo({ 43: { optional: "shared:9" } }) }, /runtime_mount_policy_propagation_forbidden/);
  rejects({ mountInfoText: mountInfo({ 43: { optional: "master:9" } }) }, /runtime_mount_policy_propagation_forbidden/);
  rejects({ mountInfoText: `${mountInfo()}43 1 8:1 /duplicate /duplicate ro,nosuid,nodev,noexec - ext4 /dev/sda1 rw\n` }, /runtime_mount_policy_mount_id_duplicate/);
  rejects({ mountInfoText: `${mountInfo()}47 1 8:1 /duplicate ${escapeMountInfo(hostPath(paths.config_file))} ro,nosuid,nodev,noexec - ext4 /dev/sda1 rw\n` }, /runtime_mount_policy_independent_mount_missing/);
  rejects({ mountInfoText: "41 1 broken\n" }, /runtime_mount_policy_mountinfo_malformed/);
  rejects({ mountInfoText: mountInfo().replace("\\040", "\\041") }, /runtime_mount_policy_mountinfo_escape_invalid/);
  rejects({ mountInfoText: mountInfo({ 41: { root: "/srv/../workspace" } }) }, /runtime_mount_policy_mount_root_noncanonical/);
  rejects({ mountInfoText: mountInfo({ 41: { root: "/srv/workspace/" } }) }, /runtime_mount_policy_mount_root_noncanonical/);
  rejects({ mountInfoText: mountInfo({ 41: { target: `${hostPath(paths.workspace_directory)}/../workspace` } }) }, /runtime_mount_policy_mount_target_noncanonical/);
  rejects({ mutableMounts: mounts.map((mount) => mount.kind === "temp_directory" ? { ...mount, path: "/run/openclaw-state/tmp" } : mount) }, /runtime_mount_policy_mutable_mounts_invalid/);
  rejects({ mutableMounts: mounts.slice(1) }, /runtime_mount_policy_mutable_mounts_invalid/);
  rejects({ mutableMounts: [mounts[1], mounts[0], ...mounts.slice(2)] }, /runtime_mount_policy_mutable_mounts_invalid/);
  rejects({ mutableMounts: mounts.map((mount) => mount.kind === "hosts_file" ? { ...mount, path: "/etc/hostname" } : mount) }, /runtime_mount_policy_mutable_mounts_invalid/);
  rejects({ mutableMounts: mounts.map((mount) => mount.kind === "resolver_config_file" ? { ...mount, read_only: false } : mount) }, /runtime_mount_policy_mutable_mounts_invalid/);
  rejects({ mutableMounts: mounts.map((mount) => mount.kind === "hosts_file" ? { kind: mount.kind, path: mount.path, read_only: mount.read_only } : mount) }, /runtime_mount_policy_mutable_mounts_invalid/);
  rejects({ mutableMounts: mounts.map((mount) => mount.kind === "resolver_config_file" ? { ...mount, sha256: "A".repeat(64) } : mount) }, /runtime_mount_policy_mutable_mount_sha256_invalid/);
  rejects({ mutableMounts: mounts.map((mount) => mount.kind === "workspace_directory" ? { ...mount, sha256: sha256("unexpected") } : mount) }, /runtime_mount_policy_mutable_mounts_invalid/);
  rejects({ mutableMounts: mounts.map((mount) => mount.kind === "hosts_file" ? { ...mount, sha256: sha256("wrong but valid digest") } : mount) }, /runtime_mount_policy_content_sha256_mismatch/);

  const hostsHardlink = join(scratch, "hosts-hardlink");
  linkSync(hostPath(paths.hosts_file), hostsHardlink);
  rejects({}, /runtime_mount_policy_link_count_invalid/);
  unlinkSync(hostsHardlink);

  chmodSync(hostPath(paths.resolver_config_file), 0o644);
  writeFileSync(hostPath(paths.resolver_config_file), "nameserver 127.0.0.11\n");
  chmodSync(hostPath(paths.resolver_config_file), 0o444);
  rejects({}, /runtime_mount_policy_content_sha256_mismatch/);
  chmodSync(hostPath(paths.resolver_config_file), 0o644);
  writeFileSync(hostPath(paths.resolver_config_file), RESOLVER_CONFIG_BYTES);
  chmodSync(hostPath(paths.resolver_config_file), 0o444);

  rejects({ lstatPath: (path) => fixtureStat(path, { config_file: { uid: 1200, gid: 0 } }) }, /runtime_mount_policy_owner_invalid/);
  rejects({ lstatPath: (path) => fixtureStat(path, { hosts_file: { uid: 1200, gid: 2200 } }) }, /runtime_mount_policy_owner_invalid/);
  rejects({ lstatPath: (path) => fixtureStat(path, { resolver_config_file: { uid: 0, gid: 0 } }) }, /runtime_mount_policy_owner_invalid/);
  chmodSync(hostPath(paths.hosts_file), 0o400);
  rejects({}, /runtime_mount_policy_mode_invalid/);
  chmodSync(hostPath(paths.hosts_file), 0o444);
  rmSync(hostPath(paths.resolver_config_file));
  mkdirSync(hostPath(paths.resolver_config_file), { mode: 0o444 });
  rejects({}, /runtime_mount_policy_object_type_invalid/);
  rmSync(hostPath(paths.resolver_config_file), { recursive: true });
  writeFileSync(hostPath(paths.resolver_config_file), RESOLVER_CONFIG_BYTES, { mode: 0o444 });
  chmodSync(hostPath(paths.config_file), 0o600);
  rejects({}, /runtime_mount_policy_mode_invalid/);
  chmodSync(hostPath(paths.config_file), 0o400);

  rmSync(hostPath(paths.config_file));
  mkdirSync(hostPath(paths.config_file), { mode: 0o400 });
  rejects({}, /runtime_mount_policy_object_type_invalid/);
  rmSync(hostPath(paths.config_file), { recursive: true });
  writeFileSync(hostPath(paths.config_file), "{}\n", { mode: 0o400 });

  chmodSync(hostPath(paths.workspace_directory), 0o755);
  rejects({}, /runtime_mount_policy_mode_invalid/);
  chmodSync(hostPath(paths.workspace_directory), 0o555);
  rejects({ lstatPath: (path) => fixtureStat(path, { workspace_directory: { uid: 1200, gid: 0 } }) }, /runtime_mount_policy_owner_invalid/);
  rejects({ lstatPath: (path) => fixtureStat(path, { state_directory: { uid: 0, gid: 1200 } }) }, /runtime_mount_policy_owner_invalid/);
  rejects({ lstatPath: (path) => fixtureStat(path, { temp_directory: { uid: 1200, gid: 0 } }) }, /runtime_mount_policy_owner_invalid/);
  rejects({ lstatPath: (path) => {
    const stat = fixtureStat(path);
    return path === hostPath(paths.state_directory) ? { ...stat, isDirectory: () => false } : stat;
  } }, /runtime_mount_policy_object_type_invalid/);

  chmodSync(hostPath(paths.state_directory), 0o755);
  rejects({}, /runtime_mount_policy_mode_invalid/);
  chmodSync(hostPath(paths.state_directory), 0o700);
  chmodSync(hostPath(paths.temp_directory), 0o777);
  rejects({}, /runtime_mount_policy_mode_invalid/);
  chmodSync(hostPath(paths.temp_directory), 0o1777);

  assert.throws(
    () => verifyOpenClawRuntimeMountPolicy({
      guestRoot,
      mutableMounts: mounts,
      mountInfoText: mountInfo(),
      platform: "darwin",
    }),
    /runtime_mount_policy_unsupported_platform/,
  );
  if (process.platform !== "linux") {
    assert.throws(
      () => verifyOpenClawRuntimeMountPolicy({ guestRoot, mutableMounts: mounts, mountInfoText: mountInfo() }),
      /runtime_mount_policy_unsupported_platform/,
    );
  }

  process.stdout.write(`${JSON.stringify({
    contract: result.contract,
    ok: true,
    successful_mount_evidence: result.mounts,
    negative_cases_verified: 49,
    content_digest_binding_verified: true,
    compose_text_used: false,
    non_linux_default_fail_closed_verified: process.platform === "linux" ? "not_applicable" : true,
  })}\n`);
} finally {
  if (existsSync(hostPath(paths.workspace_directory))) chmodSync(hostPath(paths.workspace_directory), 0o755);
  rmSync(scratch, { recursive: true, force: true });
}
