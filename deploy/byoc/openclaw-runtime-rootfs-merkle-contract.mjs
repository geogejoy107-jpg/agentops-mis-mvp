#!/usr/bin/env node

import assert from "node:assert/strict";
import {
  chmodSync,
  linkSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

import {
  computeOpenClawRuntimeRootfsMerkle,
  OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS,
  OPENCLAW_RUNTIME_ROOTFS_MERKLE_SCHEMA,
} from "./openclaw-runtime-rootfs-merkle.mjs";

function fixture() {
  const root = mkdtempSync(path.join(tmpdir(), "agentops-rootfs-merkle-"));
  for (const directory of [
    "bin",
    "lib",
    "opt/agentops-worker/workspace",
    "run/openclaw-state",
    "run/secrets",
    "tmp",
    "usr/local/bin",
  ]) mkdirSync(path.join(root, directory), { recursive: true, mode: 0o755 });
  writeFileSync(path.join(root, "bin/runtime"), "runtime-v1\n", { mode: 0o555 });
  writeFileSync(path.join(root, "lib/module.js"), "export const value = 1;\n", { mode: 0o444 });
  writeFileSync(path.join(root, "run/secrets/openclaw_config"), "mutable-config-v1\n", { mode: 0o600 });
  writeFileSync(path.join(root, "opt/agentops-worker/workspace/input.txt"), "mutable-workspace-v1\n", { mode: 0o600 });
  writeFileSync(path.join(root, "run/openclaw-state/state.json"), "mutable-state-v1\n", { mode: 0o600 });
  writeFileSync(path.join(root, "tmp/scratch"), "mutable-temp-v1\n", { mode: 0o600 });
  symlinkSync("../../../bin/runtime", path.join(root, "usr/local/bin/node"));
  mkdirSync(path.join(root, "etc"), { mode: 0o755 });
  symlinkSync("/proc/mounts", path.join(root, "etc/mtab"));
  return root;
}

function scan(root) {
  return computeOpenClawRuntimeRootfsMerkle(
    root,
    [...OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS].reverse(),
  );
}

function withFixture(callback) {
  const root = fixture();
  try {
    return callback(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

const baseline = withFixture((root) => {
  const first = scan(root);
  const second = scan(root);
  assert.deepEqual(second, first);
  assert.equal(first.schema, OPENCLAW_RUNTIME_ROOTFS_MERKLE_SCHEMA);
  assert.match(first.merkle_sha256, /^[a-f0-9]{64}$/);
  assert.equal(first.file_count, 15);
  assert.equal(first.byte_count, 35);
  return first;
});

withFixture((root) => {
  const modulePath = path.join(root, "lib/module.js");
  chmodSync(modulePath, 0o644);
  writeFileSync(modulePath, "export const value = 2;\n");
  chmodSync(modulePath, 0o444);
  assert.notEqual(scan(root).merkle_sha256, baseline.merkle_sha256);
});

withFixture((root) => {
  chmodSync(path.join(root, "lib/module.js"), 0o544);
  assert.notEqual(scan(root).merkle_sha256, baseline.merkle_sha256);
});

withFixture((root) => {
  writeFileSync(path.join(root, "lib/extra.js"), "extra\n", { mode: 0o444 });
  const changed = scan(root);
  assert.notEqual(changed.merkle_sha256, baseline.merkle_sha256);
  assert.equal(changed.file_count, baseline.file_count + 1);
});

withFixture((root) => {
  writeFileSync(path.join(root, "run/secrets/openclaw_config"), "mutable-config-v2\n", { mode: 0o600 });
  writeFileSync(path.join(root, "opt/agentops-worker/workspace/new.txt"), "new\n", { mode: 0o666 });
  writeFileSync(path.join(root, "run/openclaw-state/state.json"), "mutable-state-v2\n", { mode: 0o600 });
  writeFileSync(path.join(root, "tmp/another"), "another\n", { mode: 0o666 });
  assert.deepEqual(scan(root), baseline);
});

withFixture((root) => {
  symlinkSync("../../../../outside", path.join(root, "usr/local/bin/escape"));
  assert.throws(() => scan(root), /runtime_rootfs_merkle_symlink_target_rejected/);
});

withFixture((root) => {
  symlinkSync("/proc/../outside", path.join(root, "usr/local/bin/noncanonical-absolute"));
  assert.throws(() => scan(root), /runtime_rootfs_merkle_symlink_target_rejected/);
});

withFixture((root) => {
  const mtab = path.join(root, "etc/mtab");
  unlinkSync(mtab);
  symlinkSync("/proc/self/mounts", mtab);
  assert.notEqual(scan(root).merkle_sha256, baseline.merkle_sha256);
});

withFixture((root) => {
  symlinkSync("../tmp/runtime-input", path.join(root, "lib/mutable-input"));
  assert.throws(
    () => scan(root),
    /runtime_rootfs_merkle_symlink_mutable_mount_target_rejected/,
  );
});

withFixture((root) => {
  linkSync(path.join(root, "lib/module.js"), path.join(root, "lib/module-hardlink.js"));
  assert.throws(() => scan(root), /runtime_rootfs_merkle_hardlink_rejected/);
});

withFixture((root) => {
  const fifo = path.join(root, "lib/pipe");
  const created = spawnSync("mkfifo", [fifo], { encoding: "utf8" });
  assert.equal(created.status, 0, created.stderr);
  assert.throws(() => scan(root), /runtime_rootfs_merkle_special_file_rejected/);
});

withFixture((root) => {
  chmodSync(path.join(root, "lib/module.js"), 0o466);
  assert.throws(() => scan(root), /runtime_rootfs_merkle_writable_entry_rejected/);
});

withFixture((root) => {
  chmodSync(path.join(root, "lib"), 0o757);
  assert.throws(() => scan(root), /runtime_rootfs_merkle_writable_entry_rejected/);
});

withFixture((root) => {
  unlinkSync(path.join(root, "run/secrets/openclaw_config"));
  assert.throws(() => scan(root), /runtime_rootfs_merkle_mount_path_missing/);
});

withFixture((root) => {
  unlinkSync(path.join(root, "run/secrets/openclaw_config"));
  mkdirSync(path.join(root, "run/secrets/openclaw_config"), { mode: 0o700 });
  assert.throws(() => scan(root), /runtime_rootfs_merkle_mount_path_type_invalid/);
});

withFixture((root) => {
  assert.throws(
    () => computeOpenClawRuntimeRootfsMerkle(root, [
      "/opt/agentops-worker/workspace",
      "/run/openclaw-state",
      "/run/secrets/openclaw_config",
      "/var/tmp",
    ]),
    /runtime_rootfs_merkle_mount_paths_invalid/,
  );
});

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_runtime_rootfs_merkle_contract_v1",
  stable_result_verified: true,
  content_and_metadata_binding_verified: true,
  added_file_binding_verified: true,
  excluded_mount_contents_ignored: true,
  safe_guest_absolute_symlink_verified: true,
  symlink_escape_rejected: true,
  symlink_to_excluded_mount_rejected: true,
  hardlink_special_file_and_writable_entries_rejected: true,
  mount_presence_and_type_verified: true,
  shell_find_used: false,
})}\n`);
