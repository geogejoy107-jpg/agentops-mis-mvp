#!/usr/bin/env node

import {
  closeSync,
  constants,
  fstatSync,
  openSync,
  readSync,
} from "node:fs";
import { request } from "node:http";
import { isAbsolute, resolve } from "node:path";

const socketPath = process.env.OPENCLAW_PROVIDER_SOCKET
  || "/run/agentops-openclaw-provider/provider.sock";
const expectedSchema = "agentops_openclaw_provider_health_v1";
const maxResponseBytes = 8 * 1024;
const boundaryStatePath = process.env.AGENTOPS_OPENCLAW_BOUNDARY_STATE_PATH || "";

if (!isAbsolute(socketPath) || resolve(socketPath) !== socketPath) process.exit(1);
if (boundaryStatePath) {
  if (!isAbsolute(boundaryStatePath) || resolve(boundaryStatePath) !== boundaryStatePath) {
    process.exit(1);
  }
  let descriptor;
  try {
    if (!Number.isInteger(constants.O_NOFOLLOW) || constants.O_NOFOLLOW <= 0) process.exit(1);
    descriptor = openSync(
      boundaryStatePath,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK,
    );
    const metadata = fstatSync(descriptor);
    if (
      !metadata.isFile()
      || metadata.uid !== process.getuid?.()
      || metadata.gid !== process.getgid?.()
      || (metadata.mode & 0o777) !== 0o600
      || metadata.size < 2
      || metadata.size > maxResponseBytes
    ) process.exit(1);
    const bytes = Buffer.alloc(metadata.size);
    let offset = 0;
    while (offset < bytes.byteLength) {
      const count = readSync(descriptor, bytes, offset, bytes.byteLength - offset, offset);
      if (count === 0) process.exit(1);
      offset += count;
    }
    const after = fstatSync(descriptor);
    if (
      after.dev !== metadata.dev
      || after.ino !== metadata.ino
      || after.mode !== metadata.mode
      || after.uid !== metadata.uid
      || after.gid !== metadata.gid
      || after.size !== metadata.size
      || after.mtimeMs !== metadata.mtimeMs
      || after.ctimeMs !== metadata.ctimeMs
    ) process.exit(1);
    const state = JSON.parse(bytes.toString("utf8"));
    if (
      state?.schema !== "agentops_openclaw_boundary_supervisor_state_v1"
      || state.ready !== true
      || state.role !== "executor"
      || state.backend_health_verified !== true
      || state.external_gate_health_verified !== false
      || state.external_gate_listener_metadata_verified !== true
      || state.peercred_gate_process_started !== true
      || state.peercred_runtime_verified !== false
      || state.linux_peercred_gate_contract_verified !== false
    ) process.exit(1);
  } catch {
    process.exit(1);
  } finally {
    if (descriptor !== undefined) closeSync(descriptor);
  }
}

const check = request({
  socketPath,
  path: "/health",
  method: "GET",
  headers: { Connection: "close" },
}, (response) => {
  const chunks = [];
  let size = 0;
  response.on("data", (chunk) => {
    size += chunk.byteLength;
    if (size > maxResponseBytes) {
      check.destroy();
      process.exitCode = 1;
      return;
    }
    chunks.push(chunk);
  });
  response.on("end", () => {
    if (size > maxResponseBytes || response.statusCode !== 200) {
      process.exitCode = 1;
      return;
    }
    try {
      const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (
        !payload
        || typeof payload !== "object"
        || Array.isArray(payload)
        || payload.schema !== expectedSchema
        || payload.ok !== true
        || payload.ready !== true
        || typeof payload.busy !== "boolean"
      ) {
        process.exitCode = 1;
      }
    } catch {
      process.exitCode = 1;
    }
  });
});

check.setTimeout(2_000, () => check.destroy());
check.once("error", () => {
  process.exitCode = 1;
});
check.end();
