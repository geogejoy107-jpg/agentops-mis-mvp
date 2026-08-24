#!/usr/bin/env node

import {
  closeSync,
  constants,
  fstatSync,
  openSync,
  readFileSync,
  readSync,
} from "node:fs";
import { request } from "node:http";

const STATE_PATH = "/run/agentops-openclaw-provider-backend/supervisor-state.json";
const SOCKET_PATH = "/run/agentops-openclaw-private/executor.sock";
const MAX_BYTES = 8 * 1024;

function fail() {
  process.exit(1);
}

function readSupervisorState() {
  let descriptor;
  try {
    descriptor = openSync(
      STATE_PATH,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK | constants.O_CLOEXEC,
    );
    const before = fstatSync(descriptor);
    if (
      !before.isFile()
      || before.uid !== 0
      || before.gid !== 2200
      || (before.mode & 0o777) !== 0o600
      || before.size < 2
      || before.size > MAX_BYTES
    ) fail();
    const bytes = Buffer.alloc(before.size);
    let offset = 0;
    while (offset < bytes.length) {
      const count = readSync(descriptor, bytes, offset, bytes.length - offset, offset);
      if (count <= 0) fail();
      offset += count;
    }
    const after = fstatSync(descriptor);
    if (
      after.dev !== before.dev
      || after.ino !== before.ino
      || after.uid !== before.uid
      || after.gid !== before.gid
      || after.mode !== before.mode
      || after.size !== before.size
      || after.ctimeMs !== before.ctimeMs
      || after.mtimeMs !== before.mtimeMs
    ) fail();
    const state = JSON.parse(bytes.toString("utf8"));
    if (
      state?.schema !== "agentops_openclaw_boundary_supervisor_state_v1"
      || state.ready !== true
      || state.role !== "root-executor"
      || state.backend_health_verified !== true
      || state.external_gate_health_verified !== false
      || state.external_gate_listener_metadata_verified !== true
      || state.peercred_gate_process_started !== true
      || state.peercred_runtime_verified !== false
      || state.linux_peercred_gate_contract_verified !== false
    ) fail();
  } catch {
    fail();
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
}

function dropToBrokerIdentity() {
  try {
    process.setgroups([]);
    process.setgid(2200);
    process.setuid(1100);
  } catch {
    fail();
  }
  if (
    process.getuid() !== 1100
    || process.geteuid() !== 1100
    || process.getgid() !== 2200
    || process.getegid() !== 2200
    || process.getgroups().some((gid) => gid !== 2200)
  ) fail();
  const status = readFileSync("/proc/self/status", "utf8");
  for (const name of ["CapInh", "CapPrm", "CapEff", "CapAmb"]) {
    if (!new RegExp(`^${name}:\\s+0+$`, "m").test(status)) fail();
  }
}

readSupervisorState();
dropToBrokerIdentity();

const check = request({
  socketPath: SOCKET_PATH,
  path: "/health",
  method: "GET",
  headers: { Connection: "close" },
}, (response) => {
  const chunks = [];
  let size = 0;
  response.on("data", (chunk) => {
    size += chunk.byteLength;
    if (size > MAX_BYTES) {
      check.destroy();
      process.exitCode = 1;
      return;
    }
    chunks.push(Buffer.from(chunk));
  });
  response.on("end", () => {
    if (size > MAX_BYTES || response.statusCode !== 200) fail();
    try {
      const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (
        !payload
        || typeof payload !== "object"
        || Array.isArray(payload)
        || payload.schema !== "agentops_openclaw_executor_health_v1"
        || payload.ok !== true
        || payload.ready !== true
        || typeof payload.busy !== "boolean"
        || payload.manifest_tree_verified_at_startup !== true
        || payload.cgroup_delegation_verified_at_startup !== true
        || payload.replay_recovery_completed !== true
        || payload.provider_egress_config_verified_at_startup !== true
        || payload.runtime_receipt_verified !== false
        || payload.hostile_runtime_isolation_verified !== false
      ) fail();
    } catch {
      fail();
    }
  });
});

check.setTimeout(2_000, () => check.destroy());
check.once("error", () => { process.exitCode = 1; });
check.end();
