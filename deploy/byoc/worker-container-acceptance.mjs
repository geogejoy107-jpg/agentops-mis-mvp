#!/usr/bin/env node

import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const IMAGE = /^[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}$/;
const REVISION = /^[0-9a-f]{40}$/;
const root = mkdtempSync(join(tmpdir(), "agentops-worker-container-acceptance-"));
const suffix = `${process.pid}-${randomBytes(5).toString("hex")}`;
const stubName = `agentops-worker-stub-${suffix}`;
const workerName = `agentops-worker-under-test-${suffix}`;
const token = `acceptance-agent-token-${randomBytes(32).toString("hex")}`;

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function option(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || index === process.argv.length - 1) {
    fail(`${name.slice(2).replaceAll("-", "_")}_required`);
  }
  return process.argv[index + 1];
}

function docker(arguments_, acceptedStatuses = [0]) {
  const result = spawnSync("docker", arguments_, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 30_000,
  });
  if (!acceptedStatuses.includes(result.status ?? -1)) {
    fail("docker_command_failed");
  }
  return result.stdout;
}

function sleep(milliseconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
}

function waitFor(name, probe, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const value = probe();
      if (value) return value;
    } catch {
      // The bounded deadline remains authoritative while the container starts.
    }
    const running = docker(
      ["inspect", "--format", "{{.State.Running}}", name],
      [0, 1],
    ).trim();
    if (running === "false") fail("acceptance_container_exited_early");
    sleep(500);
  }
  fail("acceptance_container_timeout");
}

function jsonLines(value) {
  return value.split("\n").map((line) => line.trim()).filter(Boolean).flatMap((line) => {
    try {
      return [JSON.parse(line)];
    } catch {
      return [];
    }
  });
}

const stubProgram = String.raw`
const http = require("node:http");
const net = require("node:net");
const state = { requests: [], provider_connections: 0 };
http.createServer(async (request, response) => {
  if (request.url === "/__acceptance__") {
    response.setHeader("content-type", "application/json");
    response.end(JSON.stringify(state));
    return;
  }
  let bodyBytes = 0;
  for await (const chunk of request) {
    bodyBytes += chunk.length;
    if (bodyBytes > 65536) request.destroy();
  }
  state.requests.push({
    method: request.method,
    path: String(request.url || "").split("?", 1)[0],
    authorization_present: /^Bearer [^ ]{16,}$/.test(String(request.headers.authorization || "")),
    body_bytes: bodyBytes,
    token_omitted: true,
  });
  response.setHeader("content-type", "application/json");
  if (request.method === "GET" && String(request.url).startsWith("/api/mis/agent-gateway/tasks/pull?")) {
    response.end(JSON.stringify({ ok: true, tasks: [] }));
    return;
  }
  if (request.method === "POST" && request.url === "/api/mis/agent-gateway/heartbeat") {
    response.end(JSON.stringify({ ok: true }));
    return;
  }
  response.statusCode = 404;
  response.end(JSON.stringify({ error: "acceptance_route_forbidden" }));
}).listen(18765, "127.0.0.1");
net.createServer((socket) => {
  state.provider_connections += 1;
  socket.destroy();
}).listen(18766, "127.0.0.1");
`;

let receipt;
try {
  const releaseRoot = resolve(option("--release-root"));
  const manifestPath = join(releaseRoot, "release-manifest.json");
  if (!existsSync(manifestPath)) fail("release_manifest_missing");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  if (
    manifest.contract !== "agentops_byoc_release_bundle_v1"
    || !IMAGE.test(String(manifest.image || ""))
    || !REVISION.test(String(manifest.source_revision || ""))
    || manifest.application_source_included !== false
    || manifest.repository_checkout_required !== false
  ) {
    fail("release_manifest_boundary_invalid");
  }
  for (const forbidden of [".git", "Dockerfile", "package.json", "package-lock.json", "ui", "migrations"]) {
    if (existsSync(join(releaseRoot, forbidden))) fail("release_source_checkout_present");
  }

  const image = manifest.image;
  const imageInspection = JSON.parse(docker(["image", "inspect", image]))[0];
  assert.equal(imageInspection.Os, "linux");
  assert.equal(imageInspection.Architecture, "amd64");
  assert.equal(
    imageInspection.Config?.Labels?.["org.opencontainers.image.revision"],
    manifest.source_revision,
  );

  const tokenPath = join(root, "agent-token");
  writeFileSync(tokenPath, `${token}\n`, { encoding: "utf8", mode: 0o400, flag: "wx" });
  chmodSync(tokenPath, 0o444);

  docker([
    "run", "--detach", "--name", stubName,
    "--platform", "linux/amd64",
    "--read-only", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--tmpfs", "/tmp:rw,noexec,nosuid,size=1m",
    "--entrypoint", "node", image, "-e", stubProgram,
  ]);
  waitFor(stubName, () => {
    const output = docker([
      "exec", stubName, "node", "-e",
      "fetch('http://127.0.0.1:18765/__acceptance__').then(r=>r.text()).then(console.log)",
    ]);
    return JSON.parse(output);
  }, 20_000);

  docker([
    "run", "--detach", "--name", workerName,
    "--platform", "linux/amd64",
    "--network", `container:${stubName}`,
    "--user", "1000:1000", "--read-only", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--tmpfs", "/run/agentops-worker:rw,noexec,nosuid,size=1m,mode=0700,uid=1000,gid=1000",
    "--tmpfs", "/tmp:rw,noexec,nosuid,size=8m,mode=0700,uid=1000,gid=1000",
    "--mount", `type=bind,src=${tokenPath},dst=/run/secrets/agent_token,readonly`,
    "--env", "NODE_ENV=production",
    "--env", "AGENTOPS_WORKER_ADAPTER=hermes",
    "--env", "AGENTOPS_AGENT_TOKEN_SOURCE_FILE=/run/secrets/agent_token",
    "--env", "AGENTOPS_BASE_URL=http://127.0.0.1:18765",
    "--env", "AGENTOPS_WORKSPACE_ID=ws_container_acceptance",
    "--env", "AGENTOPS_AGENT_ID=agt_container_acceptance",
    "--env", "AGENTOPS_RUN_ESTIMATED_COST_USD=1.000000",
    "--env", "AGENTOPS_POLL_INTERVAL_MS=1000",
    "--env", "AGENTOPS_ADAPTER_MAX_ATTEMPTS=1",
    "--env", "AGENTOPS_WORKER_HEALTH_LEASE_SECONDS=30",
    "--env", "AGENTOPS_ALLOW_INSECURE_LOOPBACK=true",
    "--env", "AGENTOPS_ALLOW_HIGH_RISK=false",
    "--env", "HERMES_GATEWAY_URL=https://127.0.0.1:18766",
    "--env", "HERMES_MODEL=acceptance-provider-must-not-run",
    "--env", "HERMES_TIMEOUT_MS=1000",
    "--env", "HERMES_MAX_TOKENS=64",
    "--entrypoint", "node", image,
    "/usr/local/lib/agentops/worker-entrypoint.mjs",
  ]);

  receipt = waitFor(workerName, () => jsonLines(docker(["logs", workerName])).find((item) =>
    item.contract === "agentops_byoc_typescript_worker_receipt_v1"
    && item.ok === true
    && item.processed === false
    && item.reason === "no_task"
  ), 60_000);
  assert.equal(receipt.provider_call_performed, false);
  assert.equal(receipt.dry_run, false);
  assert.equal(receipt.token_omitted, true);

  const health = waitFor(workerName, () => {
    const output = docker([
      "exec", workerName, "node", "-e",
      "process.stdout.write(require('node:fs').readFileSync('/run/agentops-worker/health.json','utf8'))",
    ]);
    const candidate = JSON.parse(output);
    return candidate.status === "ready" ? candidate : null;
  }, 60_000);
  const healthRaw = JSON.stringify(health);
  assert.equal(health.token_omitted, true);
  docker(["exec", workerName, "node", "/usr/local/lib/agentops/worker-healthcheck.mjs"]);

  const processArgv = JSON.parse(docker([
    "exec", workerName, "node", "-e",
    "const f=require('node:fs');const rows=f.readdirSync('/proc').filter(x=>/^\\d+$/.test(x)).flatMap(x=>{try{return [f.readFileSync('/proc/'+x+'/cmdline').toString('utf8').split('\\0').filter(Boolean)]}catch{return []}});process.stdout.write(JSON.stringify(rows))",
  ]));
  const inspection = docker(["inspect", workerName]);
  const logs = docker(["logs", workerName]);
  for (const exposed of [healthRaw, JSON.stringify(processArgv), inspection, logs]) {
    if (exposed.includes(token)) fail("agent_token_exposed_by_container");
  }

  const stubState = JSON.parse(docker([
    "exec", stubName, "node", "-e",
    "fetch('http://127.0.0.1:18765/__acceptance__').then(r=>r.text()).then(console.log)",
  ]));
  assert.equal(stubState.provider_connections, 0);
  assert.ok(stubState.requests.some((item) =>
    item.method === "GET"
    && item.path === "/api/mis/agent-gateway/tasks/pull"
    && item.authorization_present === true
    && item.token_omitted === true
  ));
  assert.ok(stubState.requests.every((item) => [
    "/api/mis/agent-gateway/tasks/pull",
    "/api/mis/agent-gateway/heartbeat",
  ].includes(item.path)));

  process.stdout.write(`${JSON.stringify({
    ok: true,
    contract: "agentops_byoc_typescript_worker_container_v1",
    source_revision: manifest.source_revision,
    image_digest_verified: true,
    source_checkout_required: false,
    worker_container_started: true,
    worker_health_verified: true,
    no_task_receipt_verified: true,
    provider_connections: 0,
    provider_call_performed: false,
    token_in_argv: false,
    token_in_receipt: false,
    token_in_health: false,
    token_omitted: true,
  })}\n`);
} catch (error) {
  const code = typeof error?.code === "string" && /^[a-z][a-z0-9_]{2,80}$/.test(error.code)
    ? error.code
    : "worker_container_acceptance_failed";
  process.stderr.write(`${code}\n`);
  process.exitCode = 1;
} finally {
  docker(["rm", "--force", workerName], [0, 1]);
  docker(["rm", "--force", stubName], [0, 1]);
  rmSync(root, { recursive: true, force: true });
}
