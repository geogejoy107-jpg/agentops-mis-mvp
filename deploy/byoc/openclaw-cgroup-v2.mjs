#!/usr/bin/env node

import {
  accessSync,
  chmodSync,
  constants,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  rmdirSync,
  writeSync,
  closeSync,
} from "node:fs";
import { basename, isAbsolute, join, resolve, sep } from "node:path";

export const OPENCLAW_CGROUP_ROOT = "/sys/fs/cgroup/agentops-openclaw-executor";
export const OPENCLAW_CGROUP_SCHEMA = "agentops_openclaw_cgroup_v2";

const REQUIRED_CONTROLLERS = Object.freeze(["cpu", "io", "memory", "pids"]);
const SAFE_REQUEST_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;
const POSITIVE_INTEGER = /^[1-9][0-9]{0,18}$/;
const CPU_MAX = /^(?:max|[1-9][0-9]{0,18}) [1-9][0-9]{0,18}$/;
const IO_MAX = /^[0-9]+:[0-9]+ (?:rbps|wbps|riops|wiops)=(?:max|[1-9][0-9]{0,18})(?: (?:rbps|wbps|riops|wiops)=(?:max|[1-9][0-9]{0,18})){0,3}$/;

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
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

function tokens(value) {
  return new Set(String(value).trim().split(/\s+/u).filter(Boolean).map((item) => item.replace(/^\+/, "")));
}

function safeRequestId(value) {
  if (typeof value !== "string" || !SAFE_REQUEST_ID.test(value)) fail("cgroup_request_id_invalid");
  return value;
}

function absoluteRoot(value) {
  if (typeof value !== "string" || !isAbsolute(value) || resolve(value) !== value) {
    fail("cgroup_root_absolute_path_required");
  }
  return value;
}

function assertDirectory(path, uid, mode, label) {
  let metadata;
  try {
    metadata = lstatSync(path);
  } catch {
    fail(`${label}_unavailable`);
  }
  if (!metadata.isDirectory() || metadata.isSymbolicLink()) fail(`${label}_directory_invalid`);
  if (metadata.uid !== uid) fail(`${label}_owner_invalid`);
  if ((metadata.mode & 0o7777) !== mode) fail(`${label}_mode_invalid`);
  if (realpathSync(path) !== path) fail(`${label}_identity_invalid`);
  return metadata;
}

function assertContained(root, path) {
  if (!path.startsWith(`${root}${sep}`) || resolve(path) !== path || basename(path) === "..") {
    fail("cgroup_path_escape");
  }
}

function controllerFile(path, name, writable = false) {
  const target = join(path, name);
  let metadata;
  try {
    metadata = lstatSync(target);
    if (metadata.isSymbolicLink() || !metadata.isFile()) fail("cgroup_control_file_invalid");
    if (writable) accessSync(target, constants.W_OK);
  } catch (error) {
    if (error?.code === "cgroup_control_file_invalid") throw error;
    fail("cgroup_control_file_unavailable");
  }
  return target;
}

function writeControl(path, value) {
  const descriptor = openSync(path, constants.O_WRONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  try {
    const bytes = Buffer.from(`${value}\n`, "ascii");
    if (writeSync(descriptor, bytes, 0, bytes.byteLength, null) !== bytes.byteLength) {
      fail("cgroup_control_write_incomplete");
    }
  } finally {
    closeSync(descriptor);
  }
}

function positiveLimit(value, label) {
  if (typeof value !== "string" || !POSITIVE_INTEGER.test(value)) fail(`${label}_invalid`);
  return value;
}

export function validateOpenClawCgroupPolicy(value) {
  const policy = exactObject(
    value,
    ["cpuMax", "ioMax", "memoryMax", "pidsMax"],
    "cgroup_policy_fields_invalid",
  );
  positiveLimit(policy.pidsMax, "cgroup_pids_max");
  positiveLimit(policy.memoryMax, "cgroup_memory_max");
  if (typeof policy.cpuMax !== "string" || !CPU_MAX.test(policy.cpuMax)) {
    fail("cgroup_cpu_max_invalid");
  }
  if (typeof policy.ioMax !== "string" || !IO_MAX.test(policy.ioMax)) {
    fail("cgroup_io_max_invalid");
  }
  return Object.freeze({ ...policy });
}

export function parseCgroupEvents(value) {
  if (typeof value !== "string" || value.length > 4096) fail("cgroup_events_invalid");
  const events = Object.create(null);
  for (const line of value.trim().split("\n")) {
    if (!line) continue;
    const match = /^([a-z][a-z0-9_]*) ([0-9]+)$/.exec(line);
    if (!match || Object.hasOwn(events, match[1])) fail("cgroup_events_invalid");
    events[match[1]] = match[2];
  }
  if (!(events.populated === "0" || events.populated === "1")) fail("cgroup_events_populated_invalid");
  return Object.freeze(events);
}

export function inspectDelegatedCgroupRoot({
  root = OPENCLAW_CGROUP_ROOT,
  expectedUid = 0,
  expectedMode = 0o700,
} = {}) {
  const path = absoluteRoot(root);
  const metadata = assertDirectory(path, expectedUid, expectedMode, "cgroup_root");
  const available = tokens(readFileSync(controllerFile(path, "cgroup.controllers"), "utf8"));
  const delegated = tokens(readFileSync(controllerFile(path, "cgroup.subtree_control", true), "utf8"));
  for (const controller of REQUIRED_CONTROLLERS) {
    if (!available.has(controller)) fail("cgroup_controller_unavailable");
    if (!delegated.has(controller)) fail("cgroup_controller_not_delegated");
  }
  return Object.freeze({
    schema: OPENCLAW_CGROUP_SCHEMA,
    root: path,
    rootDevice: String(metadata.dev),
    rootInode: String(metadata.ino),
    controllers: Object.freeze([...available].sort()),
    delegatedControllers: Object.freeze([...delegated].sort()),
  });
}

export function createRequestCgroup(delegation, requestId, policyValue, {
  expectedUid = 0,
  expectedMode = 0o700,
  testMaterializeControls = null,
} = {}) {
  if (testMaterializeControls !== null && process.env.NODE_ENV !== "test") {
    fail("cgroup_test_hook_forbidden");
  }
  if (!delegation || delegation.schema !== OPENCLAW_CGROUP_SCHEMA) fail("cgroup_delegation_invalid");
  const root = absoluteRoot(delegation.root);
  const current = inspectDelegatedCgroupRoot({ root, expectedUid, expectedMode });
  if (current.rootDevice !== delegation.rootDevice || current.rootInode !== delegation.rootInode) {
    fail("cgroup_root_identity_changed");
  }
  const policy = validateOpenClawCgroupPolicy(policyValue);
  const id = safeRequestId(requestId);
  const path = join(root, `request-${id}`);
  assertContained(root, path);
  try {
    mkdirSync(path, { mode: 0o700 });
    chmodSync(path, 0o700);
    if (testMaterializeControls !== null) testMaterializeControls(path);
  } catch {
    fail("cgroup_request_create_failed");
  }
  const metadata = assertDirectory(path, expectedUid, 0o700, "cgroup_request");
  const controls = [
    ["pids.max", policy.pidsMax],
    ["memory.max", policy.memoryMax],
    ["memory.swap.max", "0"],
    ["cpu.max", policy.cpuMax],
  ];
  try {
    controls.push(["io.max", policy.ioMax]);
    for (const [name, value] of controls) writeControl(controllerFile(path, name, true), value);
    controllerFile(path, "cgroup.procs", true);
    controllerFile(path, "cgroup.kill", true);
    parseCgroupEvents(readFileSync(controllerFile(path, "cgroup.events"), "utf8"));
  } catch (error) {
    try {
      rmdirSync(path);
    } catch {}
    throw error;
  }
  return Object.freeze({
    schema: OPENCLAW_CGROUP_SCHEMA,
    requestId: id,
    root,
    rootDevice: current.rootDevice,
    rootInode: current.rootInode,
    path,
    cgroupId: `cg-${metadata.dev}-${metadata.ino}`,
    device: String(metadata.dev),
    inode: String(metadata.ino),
    policy,
    testExpectedUid: expectedUid === 0 ? null : expectedUid,
  });
}

function assertRequestIdentity(request) {
  if (!request || request.schema !== OPENCLAW_CGROUP_SCHEMA) fail("cgroup_request_invalid");
  if (request.testExpectedUid !== null && request.testExpectedUid !== undefined && process.env.NODE_ENV !== "test") {
    fail("cgroup_test_identity_forbidden");
  }
  const expectedUid = process.env.NODE_ENV === "test" && Number.isSafeInteger(request.testExpectedUid)
    ? request.testExpectedUid
    : 0;
  const root = absoluteRoot(request.root);
  assertContained(root, request.path);
  const rootMetadata = assertDirectory(root, expectedUid, 0o700, "cgroup_root");
  if (String(rootMetadata.dev) !== request.rootDevice || String(rootMetadata.ino) !== request.rootInode) {
    fail("cgroup_root_identity_changed");
  }
  const metadata = assertDirectory(request.path, expectedUid, 0o700, "cgroup_request");
  if (String(metadata.dev) !== request.device || String(metadata.ino) !== request.inode) {
    fail("cgroup_request_identity_changed");
  }
  return request;
}

export function requestCgroupPopulated(request) {
  assertRequestIdentity(request);
  return parseCgroupEvents(readFileSync(controllerFile(request.path, "cgroup.events"), "utf8")).populated === "1";
}

export async function killAndRemoveRequestCgroup(request, {
  timeoutMs = 5000,
  pollMs = 20,
  testRemoveControls = null,
} = {}) {
  if (testRemoveControls !== null && process.env.NODE_ENV !== "test") {
    fail("cgroup_test_hook_forbidden");
  }
  assertRequestIdentity(request);
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 60_000) {
    fail("cgroup_cleanup_timeout_invalid");
  }
  if (!Number.isSafeInteger(pollMs) || pollMs < 1 || pollMs > 1000) {
    fail("cgroup_cleanup_poll_invalid");
  }
  writeControl(controllerFile(request.path, "cgroup.kill", true), "1");
  const deadline = process.hrtime.bigint() + (BigInt(timeoutMs) * 1_000_000n);
  while (requestCgroupPopulated(request)) {
    if (process.hrtime.bigint() >= deadline) fail("cgroup_cleanup_timeout");
    await new Promise((resolveWait) => setTimeout(resolveWait, pollMs));
  }
  assertRequestIdentity(request);
  if (testRemoveControls !== null) testRemoveControls(request.path);
  try {
    rmdirSync(request.path);
  } catch {
    fail("cgroup_request_remove_failed");
  }
  return Object.freeze({ cgroupId: request.cgroupId, descendantsCleanupVerified: true });
}
