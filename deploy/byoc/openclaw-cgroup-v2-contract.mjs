#!/usr/bin/env node

import assert from "node:assert/strict";
import {
  chmodSync,
  chownSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  realpathSync,
  rmSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import {
  createRequestCgroup,
  inspectDelegatedCgroupRoot,
  killAndRemoveRequestCgroup,
  parseCgroupEvents,
  requestCgroupPopulated,
  validateOpenClawCgroupPolicy,
} from "./openclaw-cgroup-v2.mjs";

process.env.NODE_ENV = "test";
const fixture = realpathSync(mkdtempSync("/tmp/aocg-"));
const uid = process.getuid();
const policy = Object.freeze({
  cpuMax: "50000 100000",
  ioMax: "8:0 rbps=1048576 wbps=1048576 riops=128 wiops=128",
  memoryMax: "268435456",
  pidsMax: "64",
});

function control(path, value = "") {
  writeFileSync(path, value, { encoding: "ascii", mode: 0o600, flag: "wx" });
}

function root(name, { controllers = "cpu io memory pids", delegated = "cpu memory pids" } = {}) {
  const path = join(fixture, name);
  mkdirSync(path, { mode: 0o700 });
  chmodSync(path, 0o700);
  chownSync(path, uid, process.getgid());
  control(join(path, "cgroup.controllers"), `${controllers}\n`);
  control(join(path, "cgroup.subtree_control"), `${delegated}\n`);
  return path;
}

function seedRequestControls(path, requestId, { populated = "0" } = {}) {
  const requestPath = join(path, `request-${requestId}`);
  mkdirSync(requestPath, { mode: 0o700 });
  rmSync(requestPath, { recursive: true });
  const originalMkdir = mkdirSync;
  return {
    requestPath,
    install() {
      originalMkdir(requestPath, { mode: 0o700 });
      for (const name of ["pids.max", "memory.max", "memory.swap.max", "cpu.max", "io.max", "cgroup.procs", "cgroup.kill"]) {
        control(join(requestPath, name));
      }
      control(join(requestPath, "cgroup.events"), `populated ${populated}\nfrozen 0\n`);
    },
  };
}

function materializeControls(path) {
  for (const name of ["pids.max", "memory.max", "memory.swap.max", "cpu.max", "io.max", "cgroup.procs", "cgroup.kill"]) {
    control(join(path, name));
  }
  control(join(path, "cgroup.events"), "populated 0\nfrozen 0\n");
}

function removeMaterializedControls(path) {
  for (const name of ["pids.max", "memory.max", "memory.swap.max", "cpu.max", "io.max", "cgroup.procs", "cgroup.kill", "cgroup.events"]) {
    rmSync(join(path, name), { force: true });
  }
}

assert.deepEqual(validateOpenClawCgroupPolicy(policy), policy);
assert.equal(parseCgroupEvents("populated 0\nfrozen 1\n").populated, "0");
assert.throws(() => parseCgroupEvents("populated 2\n"), /cgroup_events_populated_invalid/);
assert.throws(() => parseCgroupEvents("populated 0\npopulated 1\n"), /cgroup_events_invalid/);
for (const invalid of [
  { ...policy, pidsMax: "0" },
  { ...policy, memoryMax: "max" },
  { ...policy, cpuMax: "0 100000" },
  { ...policy, ioMax: null },
  { ...policy, ioMax: "../../escape" },
  { ...policy, unknown: true },
]) assert.throws(() => validateOpenClawCgroupPolicy(invalid), /cgroup_/);

const goodRoot = root("good", { delegated: "cpu io memory pids" });
const delegation = inspectDelegatedCgroupRoot({ root: goodRoot, expectedUid: uid });
assert.deepEqual(delegation.delegatedControllers, ["cpu", "io", "memory", "pids"]);
assert.throws(
  () => inspectDelegatedCgroupRoot({ root: root("missing", { controllers: "cpu pids" }), expectedUid: uid }),
  /cgroup_controller_unavailable/,
);
assert.throws(
  () => inspectDelegatedCgroupRoot({ root: root("not-delegated", { delegated: "cpu memory pids" }), expectedUid: uid }),
  /cgroup_controller_not_delegated/,
);
const weakRoot = root("weak-mode");
chmodSync(weakRoot, 0o755);
assert.throws(() => inspectDelegatedCgroupRoot({ root: weakRoot, expectedUid: uid }), /cgroup_root_mode_invalid/);
const linkedRootTarget = root("link-target");
const linkedRoot = join(fixture, "linked-root");
symlinkSync(linkedRootTarget, linkedRoot);
assert.throws(() => inspectDelegatedCgroupRoot({ root: linkedRoot, expectedUid: uid }), /cgroup_root_directory_invalid/);

// createRequestCgroup is exercised against a synchronous kernel-like fixture by
// precreating controls from a child hook is impossible; use a prepared request
// directory to prove that a collision fails closed, then cover lifecycle helpers.
const collision = seedRequestControls(goodRoot, "collision");
collision.install();
assert.throws(
  () => createRequestCgroup(delegation, "collision", policy, { expectedUid: uid }),
  /cgroup_request_create_failed/,
);
assert.throws(
  () => createRequestCgroup(delegation, "../escape", policy, { expectedUid: uid }),
  /cgroup_request_id_invalid/,
);
const created = createRequestCgroup(delegation, "created", policy, {
  expectedUid: uid,
  testMaterializeControls: materializeControls,
});
assert.equal(created.requestId, "created");
assert.match(readFileSync(join(created.path, "pids.max"), "ascii"), /^64\n/);
assert.match(readFileSync(join(created.path, "memory.max"), "ascii"), /^268435456\n/);
assert.match(readFileSync(join(created.path, "memory.swap.max"), "ascii"), /^0\n/);
assert.match(readFileSync(join(created.path, "cpu.max"), "ascii"), /^50000 100000\n/);
assert.match(readFileSync(join(created.path, "io.max"), "ascii"), /^8:0 rbps=1048576 wbps=1048576 riops=128 wiops=128\n/);
await killAndRemoveRequestCgroup(created, {
  timeoutMs: 100,
  pollMs: 1,
  testRemoveControls: removeMaterializedControls,
}).then((result) => assert.equal(result.descendantsCleanupVerified, true));

const lifecyclePath = join(goodRoot, "request-lifecycle");
mkdirSync(lifecyclePath, { mode: 0o700 });
for (const name of ["pids.max", "memory.max", "memory.swap.max", "cpu.max", "io.max", "cgroup.procs", "cgroup.kill"]) {
  control(join(lifecyclePath, name));
}
control(join(lifecyclePath, "cgroup.events"), "populated 0\nfrozen 0\n");
const metadata = lstatSync(lifecyclePath);
const request = Object.freeze({
  schema: "agentops_openclaw_cgroup_v2",
  requestId: "lifecycle",
  root: goodRoot,
  rootDevice: delegation.rootDevice,
  rootInode: delegation.rootInode,
  path: lifecyclePath,
  cgroupId: `cg-${metadata.dev}-${metadata.ino}`,
  device: String(metadata.dev),
  inode: String(metadata.ino),
  policy,
  testExpectedUid: uid,
});
assert.equal(requestCgroupPopulated(request), false);
const cleanup = await killAndRemoveRequestCgroup(request, {
  timeoutMs: 100,
  pollMs: 1,
  testRemoveControls: removeMaterializedControls,
});
assert.equal(cleanup.descendantsCleanupVerified, true);
assert.equal(existsSync(lifecyclePath), false);

const identityPath = join(goodRoot, "request-identity");
mkdirSync(identityPath, { mode: 0o700 });
const identityMetadata = lstatSync(identityPath);
const stale = { ...request, path: identityPath, device: String(identityMetadata.dev), inode: String(identityMetadata.ino) };
rmSync(identityPath, { recursive: true });
mkdirSync(identityPath, { mode: 0o700 });
assert.throws(() => requestCgroupPopulated(stale), /cgroup_request_identity_changed|cgroup_control_file_unavailable/);

const linkRequest = join(goodRoot, "request-link");
symlinkSync(linkedRootTarget, linkRequest);
assert.throws(
  () => requestCgroupPopulated({ ...request, path: linkRequest }),
  /cgroup_request_directory_invalid/,
);
unlinkSync(linkRequest);

assert.throws(
  () => requestCgroupPopulated({ ...request, root: linkedRootTarget, path: linkedRootTarget }),
  /cgroup_path_escape/,
);
assert.throws(
  () => requestCgroupPopulated({ ...request, rootInode: "0" }),
  /cgroup_root_identity_changed/,
);

rmSync(fixture, { recursive: true, force: true });
console.log(JSON.stringify({
  contract: "agentops_openclaw_cgroup_v2_filesystem_unit_v1",
  configuration_and_path_unit_verified: true,
  launcher_owned_race_free_cgroup_entry_required: true,
  real_linux_cgroupfs_acceptance_performed: false,
  hostile_runtime_isolation_verified: false,
}));
