#!/usr/bin/env node

import { closeSync, constants, fstatSync, openSync, readFileSync } from "node:fs";

const statePath = "/run/agentops-worker/health.json";

function fail() {
  process.exitCode = 1;
}

try {
  if (typeof constants.O_NOFOLLOW !== "number") throw new Error("nofollow_unavailable");
  const descriptor = openSync(statePath, constants.O_RDONLY | constants.O_NOFOLLOW);
  let payload;
  try {
    const stat = fstatSync(descriptor);
    if (!stat.isFile() || stat.size < 2 || stat.size > 16 * 1024) {
      throw new Error("state_invalid");
    }
    payload = JSON.parse(readFileSync(descriptor, "utf8"));
  } finally {
    closeSync(descriptor);
  }
  const now = Date.now();
  const leaseMs = Number(payload.lease_seconds) * 1_000;
  if (
    !["starting", "ready"].includes(payload.status)
    || !Number.isSafeInteger(payload.pid)
    || payload.pid < 2
    || !Number.isFinite(leaseMs)
    || leaseMs < 30_000
    || leaseMs > 600_000
    || !Number.isSafeInteger(payload.updated_at_ms)
    || payload.updated_at_ms > now + 5_000
    || now - payload.updated_at_ms > leaseMs
  ) {
    throw new Error("lease_invalid");
  }
  process.kill(payload.pid, 0);
} catch {
  fail();
}
