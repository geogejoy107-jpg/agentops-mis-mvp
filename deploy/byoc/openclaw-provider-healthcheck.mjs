#!/usr/bin/env node

import { request } from "node:http";
import { isAbsolute, resolve } from "node:path";

const socketPath = process.env.OPENCLAW_PROVIDER_SOCKET
  || "/run/agentops-openclaw-provider/provider.sock";
const expectedSchema = "agentops_openclaw_provider_health_v1";
const maxResponseBytes = 8 * 1024;

if (!isAbsolute(socketPath) || resolve(socketPath) !== socketPath) process.exit(1);

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
