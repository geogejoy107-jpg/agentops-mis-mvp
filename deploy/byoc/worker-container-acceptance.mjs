#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
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
const tokenSha256 = createHash("sha256").update(token).digest("hex");

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

function docker(arguments_, acceptedStatuses = [0], failureCode = "docker_command_failed") {
  const result = spawnSync("docker", arguments_, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 30_000,
  });
  if (!acceptedStatuses.includes(result.status ?? -1)) {
    fail(failureCode);
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
      "acceptance_container_inspect_failed",
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
const crypto = require("node:crypto");
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
    authorization_matches: crypto.createHash("sha256").update(
      String(request.headers.authorization || "").replace(/^Bearer /, ""),
    ).digest("hex") === process.env.EXPECTED_TOKEN_SHA256,
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
  const imageInspection = JSON.parse(docker(
    ["image", "inspect", image],
    [0],
    "acceptance_image_inspect_failed",
  ))[0];
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
    "--network", "none",
    "--read-only", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--tmpfs", "/tmp:rw,noexec,nosuid,size=1m",
    "--env", `EXPECTED_TOKEN_SHA256=${tokenSha256}`,
    "--entrypoint", "node", image, "-e", stubProgram,
  ], [0], "acceptance_stub_start_failed");
  waitFor(stubName, () => {
    const output = docker([
      "exec", stubName, "node", "-e",
      "fetch('http://127.0.0.1:18765/__acceptance__').then(r=>r.text()).then(console.log)",
    ], [0], "acceptance_stub_probe_failed");
    return JSON.parse(output);
  }, 20_000);

  docker([
    "run", "--detach", "--name", workerName,
    "--platform", "linux/amd64",
    "--init",
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
  ], [0], "acceptance_worker_start_failed");

  receipt = waitFor(workerName, () => jsonLines(docker(
    ["logs", workerName],
    [0],
    "acceptance_worker_logs_failed",
  )).find((item) =>
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
    ], [0], "acceptance_worker_health_read_failed");
    const candidate = JSON.parse(output);
    return candidate.status === "ready" ? candidate : null;
  }, 60_000);
  const healthRaw = JSON.stringify(health);
  assert.equal(health.token_omitted, true);
  docker(
    ["exec", workerName, "node", "/usr/local/lib/agentops/worker-healthcheck.mjs"],
    [0],
    "acceptance_worker_healthcheck_failed",
  );

  const processArgv = JSON.parse(docker([
    "exec", workerName, "node", "-e",
    "const f=require('node:fs');const rows=f.readdirSync('/proc').filter(x=>/^\\d+$/.test(x)).flatMap(x=>{try{return [f.readFileSync('/proc/'+x+'/cmdline').toString('utf8').split('\\0').filter(Boolean)]}catch{return []}});process.stdout.write(JSON.stringify(rows))",
  ], [0], "acceptance_worker_argv_probe_failed"));
  const initArgv = JSON.parse(docker([
    "exec", workerName, "node", "-e",
    "const f=require('node:fs');process.stdout.write(JSON.stringify(f.readFileSync('/proc/1/cmdline').toString('utf8').split('\\0').filter(Boolean)))",
  ], [0], "acceptance_worker_init_probe_failed"));
  assert.ok(initArgv.some((item) => /(?:docker-init|tini)$/.test(item)));
  assert.ok(Number.isSafeInteger(health.pid) && health.pid > 1);
  assert.ok(Number.isSafeInteger(health.child_pid) && health.child_pid >= 1);
  const processEnvironment = JSON.parse(docker([
    "exec", workerName, "node", "-e",
    `const f=require('node:fs');const pids=${JSON.stringify([health.pid, health.child_pid])};const rows=pids.map(pid=>({pid,environment:f.readFileSync('/proc/'+pid+'/environ').toString('utf8').split('\\0').filter(Boolean)}));process.stdout.write(JSON.stringify(rows))`,
  ], [0], "acceptance_worker_environment_probe_failed"));
  assert.equal(processEnvironment.length, 2);
  const inspection = docker(
    ["inspect", workerName],
    [0],
    "acceptance_worker_inspect_failed",
  );
  const logs = docker(
    ["logs", workerName],
    [0],
    "acceptance_worker_logs_failed",
  );
  for (const exposed of [
    healthRaw,
    JSON.stringify(processArgv),
    JSON.stringify(processEnvironment),
    inspection,
    logs,
  ]) {
    if (exposed.includes(token)) fail("agent_token_exposed_by_container");
  }

  const stubState = JSON.parse(docker([
    "exec", stubName, "node", "-e",
    "fetch('http://127.0.0.1:18765/__acceptance__').then(r=>r.text()).then(console.log)",
  ], [0], "acceptance_stub_state_read_failed"));
  assert.equal(stubState.provider_connections, 0);
  assert.ok(stubState.requests.some((item) =>
    item.method === "GET"
    && item.path === "/api/mis/agent-gateway/tasks/pull"
    && item.authorization_matches === true
    && item.token_omitted === true
  ));
  assert.ok(stubState.requests.every((item) => [
    "/api/mis/agent-gateway/tasks/pull",
    "/api/mis/agent-gateway/heartbeat",
  ].includes(item.path)));

  docker(
    ["stop", "--time", "10", workerName],
    [0],
    "acceptance_worker_graceful_stop_failed",
  );
  const stoppedInspection = JSON.parse(docker(
    ["inspect", workerName],
    [0],
    "acceptance_worker_stopped_inspect_failed",
  ))[0];
  assert.equal(stoppedInspection.State?.Running, false);
  assert.equal(stoppedInspection.State?.ExitCode, 0);
  const stoppedLogs = docker(
    ["logs", workerName],
    [0],
    "acceptance_worker_stopped_logs_failed",
  );
  if (stoppedLogs.includes(token)) fail("agent_token_exposed_after_worker_stop");

  process.stdout.write(`${JSON.stringify({
    ok: true,
    contract: "agentops_byoc_typescript_worker_container_v1",
    source_revision: manifest.source_revision,
    image_digest_verified: true,
    source_checkout_required: false,
    worker_container_started: true,
    worker_health_verified: true,
    worker_init_reaper_verified: true,
    graceful_stop_verified: true,
    no_task_receipt_verified: true,
    network_egress_disabled: true,
    agent_token_authorization_verified: true,
    provider_connections: 0,
    provider_call_performed: false,
    token_in_argv: false,
    token_in_environment: false,
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
  spawnSync("docker", ["rm", "--force", workerName], { stdio: "ignore" });
  spawnSync("docker", ["rm", "--force", stubName], { stdio: "ignore" });
  rmSync(root, { recursive: true, force: true });
}
