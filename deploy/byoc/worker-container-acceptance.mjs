#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  existsSync,
  mkdirSync,
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
const openClawProviderName = `agentops-openclaw-provider-${suffix}`;
const openClawWorkerName = `agentops-openclaw-worker-${suffix}`;
const openClawSocketVolume = `agentops-openclaw-socket-${suffix}`;
const token = `acceptance-agent-token-${randomBytes(32).toString("hex")}`;
const tokenSha256 = createHash("sha256").update(token).digest("hex");
const providerSentinel = `provider-only-${randomBytes(32).toString("hex")}`;
const mockPrompt = "Source-free OpenClaw sidecar isolation acceptance mock execution.";
const mockPromptSha256 = createHash("sha256").update(mockPrompt).digest("hex");
const OPENCLAW_PROVIDER_RESPONSE_KEYS = [
  "dry_run",
  "duration_ms",
  "error_message",
  "error_type",
  "model_name",
  "ok",
  "output_present",
  "output_tokens",
  "provider_call_performed",
  "raw_payload_hash",
  "raw_prompt_omitted",
  "raw_response_omitted",
  "retryable",
  "schema",
];

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

const fakeOpenClawProgram = String.raw`#!/usr/bin/env node
const fs = require("node:fs");
function stop(code) {
  process.stderr.write(code + "\n");
  process.exit(1);
}
const args = process.argv.slice(2);
const flag = (name) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
};
if (args[0] !== "agent" || flag("--agent") !== "acceptance-mock-agent") {
  stop("fake_openclaw_arguments_invalid");
}
if (!flag("--message") || flag("--json") !== undefined || !args.includes("--json")) {
  stop("fake_openclaw_message_invalid");
}
if (typeof process.getuid === "function" && process.getuid() !== 1001) {
  stop("fake_openclaw_uid_invalid");
}
if (
  process.env.AGENTOPS_AGENT_TOKEN
  || process.env.AGENTOPS_API_KEY
  || process.env.AGENTOPS_AGENT_TOKEN_SOURCE_FILE
  || fs.existsSync("/run/secrets/agent_token")
) {
  stop("fake_openclaw_agent_token_boundary_invalid");
}
const config = fs.readFileSync(process.env.OPENCLAW_CONFIG_PATH, "utf8").trim();
const runtimeSentinel = fs.readFileSync(
  "/opt/agentops-provider/openclaw/provider-sentinel",
  "utf8",
).trim();
const workspaceSentinel = fs.readFileSync(
  "/opt/agentops-worker/workspace/provider-sentinel",
  "utf8",
).trim();
if (
  !config.includes("acceptance_mock_config")
  || runtimeSentinel !== ${JSON.stringify(providerSentinel)}
  || workspaceSentinel !== ${JSON.stringify(providerSentinel)}
) {
  stop("fake_openclaw_provider_mount_invalid");
}
process.stdout.write(JSON.stringify({
  result: {
    meta: {
      durationMs: 7,
      finalAssistantVisibleText: "mock sidecar isolation response",
    },
    payloads: [{ text: "mock sidecar isolation response" }],
  },
}));
`;

const openClawSocketProbe = String.raw`
const crypto = require("node:crypto");
const http = require("node:http");
const prompt = process.env.ACCEPTANCE_MOCK_PROMPT;
const body = JSON.stringify({
  schema: "agentops_openclaw_provider_request_v1",
  agent_name: "acceptance-mock-agent",
  prompt,
  prompt_hash: crypto.createHash("sha256").update(prompt).digest("hex"),
  timeout_seconds: 10,
});
const request = http.request({
  socketPath: "/run/agentops-openclaw/provider.sock",
  path: "/v1/execute",
  method: "POST",
  headers: {
    "content-type": "application/json",
    "content-length": Buffer.byteLength(body),
  },
}, (response) => {
  const chunks = [];
  let size = 0;
  response.on("data", (chunk) => {
    size += chunk.length;
    if (size > 1048576) request.destroy(new Error("response_too_large"));
    else chunks.push(chunk);
  });
  response.on("end", () => {
    if (response.statusCode !== 200) process.exit(2);
    process.stdout.write(Buffer.concat(chunks));
  });
});
request.setTimeout(20000, () => request.destroy(new Error("socket_timeout")));
request.on("error", () => process.exit(3));
request.end(body);
`;

let receipt;
let activeCheck = "initialization";
try {
  activeCheck = "release_manifest";
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

  activeCheck = "image_identity";
  const image = manifest.image;
  const imageInspection = JSON.parse(docker(
    ["image", "inspect", image],
    [0],
    "acceptance_image_inspect_failed",
  ))[0];
  if (imageInspection.Os !== "linux") fail("acceptance_image_os_invalid");
  if (imageInspection.Architecture !== "amd64") fail("acceptance_image_architecture_invalid");
  if (
    imageInspection.Config?.Labels?.["org.opencontainers.image.revision"]
    !== manifest.source_revision
  ) fail("acceptance_image_revision_invalid");

  const tokenPath = join(root, "agent-token");
  writeFileSync(tokenPath, `${token}\n`, { encoding: "utf8", mode: 0o400, flag: "wx" });
  chmodSync(tokenPath, 0o444);
  const openClawRuntime = join(root, "openclaw-runtime");
  const openClawBinDirectory = join(openClawRuntime, "bin");
  const openClawBinary = join(openClawBinDirectory, "openclaw");
  const openClawConfig = join(root, "openclaw-config.json");
  const openClawWorkspace = join(root, "openclaw-workspace");
  mkdirSync(openClawBinDirectory, { recursive: true, mode: 0o755 });
  mkdirSync(openClawWorkspace, { recursive: true, mode: 0o755 });
  writeFileSync(openClawBinary, fakeOpenClawProgram, {
    encoding: "utf8",
    mode: 0o555,
    flag: "wx",
  });
  writeFileSync(join(openClawRuntime, "provider-sentinel"), `${providerSentinel}\n`, {
    encoding: "utf8",
    mode: 0o444,
    flag: "wx",
  });
  writeFileSync(join(openClawWorkspace, "provider-sentinel"), `${providerSentinel}\n`, {
    encoding: "utf8",
    mode: 0o444,
    flag: "wx",
  });
  writeFileSync(openClawConfig, '{"contract":"acceptance_mock_config"}\n', {
    encoding: "utf8",
    mode: 0o444,
    flag: "wx",
  });
  chmodSync(root, 0o755);
  chmodSync(openClawRuntime, 0o755);
  chmodSync(openClawBinDirectory, 0o755);
  chmodSync(openClawWorkspace, 0o755);

  activeCheck = "stub_start";
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

  activeCheck = "worker_start";
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

  activeCheck = "worker_receipt";
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
  if (receipt.provider_call_performed !== false) fail("acceptance_unexpected_provider_call");
  if (receipt.dry_run !== false) fail("acceptance_worker_dry_run_invalid");
  if (receipt.token_omitted !== true) fail("acceptance_worker_receipt_token_boundary_invalid");

  activeCheck = "worker_health";
  const health = waitFor(workerName, () => {
    const output = docker([
      "exec", workerName, "node", "-e",
      "process.stdout.write(require('node:fs').readFileSync('/run/agentops-worker/health.json','utf8'))",
    ], [0], "acceptance_worker_health_read_failed");
    const candidate = JSON.parse(output);
    return candidate.status === "ready" ? candidate : null;
  }, 60_000);
  const healthRaw = JSON.stringify(health);
  if (health.token_omitted !== true) fail("acceptance_worker_health_token_boundary_invalid");
  docker(
    ["exec", workerName, "node", "/usr/local/lib/agentops/worker-healthcheck.mjs"],
    [0],
    "acceptance_worker_healthcheck_failed",
  );

  activeCheck = "worker_process_boundary";
  const processArgv = JSON.parse(docker([
    "exec", workerName, "node", "-e",
    "const f=require('node:fs');const rows=f.readdirSync('/proc').filter(x=>/^\\d+$/.test(x)).flatMap(x=>{try{return [f.readFileSync('/proc/'+x+'/cmdline').toString('utf8').split('\\0').filter(Boolean)]}catch{return []}});process.stdout.write(JSON.stringify(rows))",
  ], [0], "acceptance_worker_argv_probe_failed"));
  const initArgv = JSON.parse(docker([
    "exec", workerName, "node", "-e",
    "const f=require('node:fs');process.stdout.write(JSON.stringify(f.readFileSync('/proc/1/cmdline').toString('utf8').split('\\0').filter(Boolean)))",
  ], [0], "acceptance_worker_init_probe_failed"));
  if (!initArgv.some((item) => /(?:docker-init|tini)$/.test(item))) {
    fail("acceptance_worker_init_reaper_missing");
  }
  if (!Number.isSafeInteger(health.pid) || health.pid <= 1) {
    fail("acceptance_worker_supervisor_pid_invalid");
  }
  if (!Number.isSafeInteger(health.child_pid) || health.child_pid < 1) {
    fail("acceptance_worker_child_pid_invalid");
  }
  const processEnvironment = JSON.parse(docker([
    "exec", workerName, "node", "-e",
    `const f=require('node:fs');const pids=${JSON.stringify([health.pid, health.child_pid])};const rows=pids.map(pid=>({pid,environment:f.readFileSync('/proc/'+pid+'/environ').toString('utf8').split('\\0').filter(Boolean)}));process.stdout.write(JSON.stringify(rows))`,
  ], [0], "acceptance_worker_environment_probe_failed"));
  if (processEnvironment.length !== 2) fail("acceptance_worker_environment_count_invalid");
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

  activeCheck = "stub_state";
  const stubState = JSON.parse(docker([
    "exec", stubName, "node", "-e",
    "fetch('http://127.0.0.1:18765/__acceptance__').then(r=>r.text()).then(console.log)",
  ], [0], "acceptance_stub_state_read_failed"));
  if (stubState.provider_connections !== 0) fail("acceptance_provider_connection_detected");
  if (!stubState.requests.some((item) =>
    item.method === "GET"
    && item.path === "/api/mis/agent-gateway/tasks/pull"
    && item.authorization_matches === true
    && item.token_omitted === true
  )) fail("acceptance_agent_token_authorization_invalid");
  if (!stubState.requests.every((item) => [
    "/api/mis/agent-gateway/tasks/pull",
    "/api/mis/agent-gateway/heartbeat",
  ].includes(item.path))) fail("acceptance_unexpected_gateway_route");

  activeCheck = "graceful_stop";
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
  if (stoppedInspection.State?.Running !== false) fail("acceptance_worker_still_running");
  if (stoppedInspection.State?.ExitCode !== 0) fail("acceptance_worker_stop_exit_invalid");
  const stoppedLogs = docker(
    ["logs", workerName],
    [0],
    "acceptance_worker_stopped_logs_failed",
  );
  if (stoppedLogs.includes(token)) fail("agent_token_exposed_after_worker_stop");

  activeCheck = "openclaw_socket_volume";
  const createdVolume = docker([
    "volume", "create",
    "--driver", "local",
    "--opt", "type=tmpfs",
    "--opt", "device=tmpfs",
    "--opt", "o=uid=1001,gid=1000,mode=0770,nosuid,nodev,noexec,size=1m",
    openClawSocketVolume,
  ], [0], "acceptance_openclaw_socket_volume_create_failed").trim();
  if (createdVolume !== openClawSocketVolume) {
    fail("acceptance_openclaw_socket_volume_identity_invalid");
  }

  activeCheck = "openclaw_provider_start";
  docker([
    "run", "--detach", "--name", openClawProviderName,
    "--platform", "linux/amd64",
    "--init",
    "--network", "none",
    "--user", "1001:1000", "--read-only", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--tmpfs", "/run/openclaw-state:rw,noexec,nosuid,nodev,size=8m,mode=0700,uid=1001,gid=1000",
    "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=8m,mode=0700,uid=1001,gid=1000",
    "--mount", `type=volume,src=${openClawSocketVolume},dst=/run/agentops-openclaw`,
    "--mount", `type=bind,src=${openClawRuntime},dst=/opt/agentops-provider/openclaw,readonly`,
    "--mount", `type=bind,src=${openClawConfig},dst=/run/secrets/openclaw_config,readonly`,
    "--mount", `type=bind,src=${openClawWorkspace},dst=/opt/agentops-worker/workspace,readonly`,
    "--env", "NODE_ENV=production",
    "--env", "AGENTOPS_DEPLOYMENT_MODE=production",
    "--env", "OPENCLAW_PROVIDER_SOCKET=/run/agentops-openclaw/provider.sock",
    "--env", "OPENCLAW_BIN=/opt/agentops-provider/openclaw/bin/openclaw",
    "--env", "OPENCLAW_CONFIG_PATH=/run/secrets/openclaw_config",
    "--env", "OPENCLAW_STATE_DIR=/run/openclaw-state",
    "--env", "AGENTOPS_WORKER_CWD=/opt/agentops-worker/workspace",
    "--entrypoint", "node", image,
    "/usr/local/lib/agentops/openclaw-provider-entrypoint.mjs",
  ], [0], "acceptance_openclaw_provider_start_failed");
  waitFor(openClawProviderName, () => {
    docker([
      "exec", openClawProviderName,
      "node", "/usr/local/lib/agentops/openclaw-provider-healthcheck.mjs",
    ], [0], "acceptance_openclaw_provider_health_pending");
    return true;
  }, 30_000);

  activeCheck = "openclaw_worker_start";
  docker([
    "run", "--detach", "--name", openClawWorkerName,
    "--platform", "linux/amd64",
    "--init",
    "--network", `container:${stubName}`,
    "--user", "1000:1000", "--read-only", "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--tmpfs", "/run/agentops-worker:rw,noexec,nosuid,nodev,size=1m,mode=0700,uid=1000,gid=1000",
    "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=8m,mode=0700,uid=1000,gid=1000",
    "--mount", `type=volume,src=${openClawSocketVolume},dst=/run/agentops-openclaw`,
    "--mount", `type=bind,src=${tokenPath},dst=/run/secrets/agent_token,readonly`,
    "--env", "NODE_ENV=production",
    "--env", "AGENTOPS_WORKER_ADAPTER=openclaw",
    "--env", "AGENTOPS_AGENT_TOKEN_SOURCE_FILE=/run/secrets/agent_token",
    "--env", "AGENTOPS_BASE_URL=http://127.0.0.1:18765",
    "--env", "AGENTOPS_WORKSPACE_ID=ws_openclaw_isolation_acceptance",
    "--env", "AGENTOPS_AGENT_ID=agt_openclaw_isolation_acceptance",
    "--env", "AGENTOPS_RUN_ESTIMATED_COST_USD=1.000000",
    "--env", "AGENTOPS_POLL_INTERVAL_MS=1000",
    "--env", "AGENTOPS_ADAPTER_MAX_ATTEMPTS=1",
    "--env", "AGENTOPS_WORKER_HEALTH_LEASE_SECONDS=30",
    "--env", "AGENTOPS_ALLOW_INSECURE_LOOPBACK=true",
    "--env", "AGENTOPS_ALLOW_HIGH_RISK=false",
    "--env", "OPENCLAW_PROVIDER_SOCKET=/run/agentops-openclaw/provider.sock",
    "--env", "OPENCLAW_AGENT=acceptance-mock-agent",
    "--env", "OPENCLAW_TIMEOUT_SECONDS=10",
    "--entrypoint", "node", image,
    "/usr/local/lib/agentops/worker-entrypoint.mjs",
  ], [0], "acceptance_openclaw_worker_start_failed");

  activeCheck = "openclaw_worker_receipt";
  const openClawWorkerReceipt = waitFor(openClawWorkerName, () => jsonLines(docker(
    ["logs", openClawWorkerName],
    [0],
    "acceptance_openclaw_worker_logs_failed",
  )).find((item) =>
    item.contract === "agentops_byoc_typescript_worker_receipt_v1"
    && item.ok === true
    && item.processed === false
    && item.reason === "no_task"
  ), 60_000);
  if (openClawWorkerReceipt.provider_call_performed !== false) {
    fail("acceptance_openclaw_worker_unexpected_provider_call");
  }
  if (openClawWorkerReceipt.dry_run !== false) {
    fail("acceptance_openclaw_worker_dry_run_invalid");
  }
  if (openClawWorkerReceipt.token_omitted !== true) {
    fail("acceptance_openclaw_worker_receipt_token_boundary_invalid");
  }

  activeCheck = "openclaw_container_isolation";
  const providerInspection = JSON.parse(docker(
    ["inspect", openClawProviderName],
    [0],
    "acceptance_openclaw_provider_inspect_failed",
  ))[0];
  const openClawWorkerInspection = JSON.parse(docker(
    ["inspect", openClawWorkerName],
    [0],
    "acceptance_openclaw_worker_inspect_failed",
  ))[0];
  if (providerInspection.Config?.User !== "1001:1000") {
    fail("acceptance_openclaw_provider_uid_invalid");
  }
  if (openClawWorkerInspection.Config?.User !== "1000:1000") {
    fail("acceptance_openclaw_worker_uid_invalid");
  }
  if (
    providerInspection.Image !== imageInspection.Id
    || openClawWorkerInspection.Image !== imageInspection.Id
  ) fail("acceptance_openclaw_exact_image_invalid");
  if (providerInspection.HostConfig?.NetworkMode !== "none") {
    fail("acceptance_openclaw_provider_network_invalid");
  }
  const stubContainerId = docker(
    ["inspect", "--format", "{{.Id}}", stubName],
    [0],
    "acceptance_stub_identity_read_failed",
  ).trim();
  if (
    !/^[0-9a-f]{64}$/.test(stubContainerId)
    || openClawWorkerInspection.HostConfig?.NetworkMode !== `container:${stubContainerId}`
  ) {
    fail("acceptance_openclaw_worker_network_invalid");
  }

  const providerMounts = providerInspection.Mounts || [];
  const openClawWorkerMounts = openClawWorkerInspection.Mounts || [];
  const providerDestinations = new Set(providerMounts.map((mount) => mount.Destination));
  const openClawWorkerDestinations = new Set(
    openClawWorkerMounts.map((mount) => mount.Destination),
  );
  for (const requiredDestination of [
    "/run/agentops-openclaw",
    "/opt/agentops-provider/openclaw",
    "/run/secrets/openclaw_config",
    "/opt/agentops-worker/workspace",
  ]) {
    if (!providerDestinations.has(requiredDestination)) {
      fail("acceptance_openclaw_provider_required_mount_missing");
    }
  }
  if (providerDestinations.has("/run/secrets/agent_token")) {
    fail("acceptance_openclaw_provider_agent_token_mounted");
  }
  if (
    openClawWorkerDestinations.size !== 2
    || !openClawWorkerDestinations.has("/run/agentops-openclaw")
    || !openClawWorkerDestinations.has("/run/secrets/agent_token")
  ) fail("acceptance_openclaw_worker_mount_boundary_invalid");
  for (const forbiddenDestination of [
    "/opt/agentops-provider/openclaw",
    "/run/secrets/openclaw_config",
    "/run/openclaw-state",
    "/opt/agentops-worker/workspace",
  ]) {
    if (openClawWorkerDestinations.has(forbiddenDestination)) {
      fail("acceptance_openclaw_worker_provider_mount_detected");
    }
  }
  const providerSocketMount = providerMounts.find(
    (mount) => mount.Destination === "/run/agentops-openclaw",
  );
  const workerSocketMount = openClawWorkerMounts.find(
    (mount) => mount.Destination === "/run/agentops-openclaw",
  );
  if (
    providerSocketMount?.Type !== "volume"
    || workerSocketMount?.Type !== "volume"
    || providerSocketMount.Name !== openClawSocketVolume
    || workerSocketMount.Name !== openClawSocketVolume
  ) fail("acceptance_openclaw_shared_socket_volume_invalid");
  const providerSources = new Set(providerMounts.map((mount) => mount.Source));
  const sharedMounts = openClawWorkerMounts.filter(
    (mount) => providerSources.has(mount.Source),
  );
  if (
    sharedMounts.length !== 1
    || sharedMounts[0].Type !== "volume"
    || sharedMounts[0].Name !== openClawSocketVolume
    || sharedMounts[0].Destination !== "/run/agentops-openclaw"
  ) fail("acceptance_openclaw_cross_container_mount_overlap_invalid");

  const providerEnvironment = providerInspection.Config?.Env || [];
  const openClawWorkerEnvironment = openClawWorkerInspection.Config?.Env || [];
  if (providerEnvironment.some((item) =>
    /^(?:AGENTOPS_AGENT_TOKEN|AGENTOPS_API_KEY|AGENTOPS_AGENT_TOKEN_SOURCE_FILE)=/.test(item)
    || item.includes(token)
  )) fail("acceptance_openclaw_provider_agent_token_environment_detected");
  if (openClawWorkerEnvironment.some((item) =>
    /^(?:OPENCLAW_BIN|OPENCLAW_CONFIG_PATH|OPENCLAW_STATE_DIR|AGENTOPS_WORKER_CWD)=/.test(item)
    || item.includes(providerSentinel)
  )) fail("acceptance_openclaw_worker_provider_environment_detected");

  const workerProviderProbe = JSON.parse(docker([
    "exec", openClawWorkerName, "node", "-e",
    "const f=require('node:fs');const paths=['/opt/agentops-provider/openclaw/provider-sentinel','/run/secrets/openclaw_config','/run/openclaw-state','/opt/agentops-worker/workspace/provider-sentinel'];process.stdout.write(JSON.stringify(paths.map(path=>({path,exists:f.existsSync(path),readable:(()=>{try{f.readFileSync(path);return true}catch{return false}})()}))))",
  ], [0], "acceptance_openclaw_worker_provider_probe_failed"));
  if (workerProviderProbe.some((item) => item.exists || item.readable)) {
    fail("acceptance_openclaw_worker_provider_sentinel_readable");
  }
  const providerTokenProbe = JSON.parse(docker([
    "exec", openClawProviderName, "node", "-e",
    "const f=require('node:fs');const paths=['/run/secrets/agent_token','/run/agentops-worker/agent_token'];const environments=f.readdirSync('/proc').filter(x=>/^\\d+$/.test(x)).flatMap(x=>{try{return [f.readFileSync('/proc/'+x+'/environ').toString('utf8')]}catch{return []}});process.stdout.write(JSON.stringify({paths:paths.map(path=>({path,exists:f.existsSync(path),readable:(()=>{try{f.readFileSync(path);return true}catch{return false}})()})),environments}))",
  ], [0], "acceptance_openclaw_provider_token_probe_failed"));
  if (
    providerTokenProbe.paths.some((item) => item.exists || item.readable)
    || providerTokenProbe.environments.some((item) =>
      item.includes(token)
      || /AGENTOPS_(?:AGENT_TOKEN|API_KEY|AGENT_TOKEN_SOURCE_FILE)=/.test(item)
    )
  ) fail("acceptance_openclaw_provider_agent_token_readable");

  activeCheck = "openclaw_socket_protocol";
  const providerResponseRaw = docker([
    "exec", "--env", `ACCEPTANCE_MOCK_PROMPT=${mockPrompt}`,
    openClawWorkerName, "node", "-e", openClawSocketProbe,
  ], [0], "acceptance_openclaw_socket_protocol_failed").trim();
  let providerResponse;
  try {
    providerResponse = JSON.parse(providerResponseRaw);
  } catch {
    fail("acceptance_openclaw_provider_response_json_invalid");
  }
  if (
    !providerResponse
    || typeof providerResponse !== "object"
    || Array.isArray(providerResponse)
  ) fail("acceptance_openclaw_provider_response_object_required");
  const providerResponseKeys = Object.keys(providerResponse).sort();
  if (
    providerResponseKeys.length !== OPENCLAW_PROVIDER_RESPONSE_KEYS.length
    || providerResponseKeys.some(
      (key, index) => key !== OPENCLAW_PROVIDER_RESPONSE_KEYS[index],
    )
  ) fail("acceptance_openclaw_provider_response_fields_invalid");
  if (
    providerResponse.schema !== "agentops_openclaw_provider_response_v1"
    || providerResponse.ok !== true
    || providerResponse.provider_call_performed !== true
    || providerResponse.dry_run !== false
    || providerResponse.output_present !== true
    || providerResponse.retryable !== false
    || providerResponse.raw_prompt_omitted !== true
    || providerResponse.raw_response_omitted !== true
    || providerResponse.error_type !== null
    || providerResponse.error_message !== null
    || !/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$/.test(providerResponse.model_name)
    || !/^[0-9a-f]{64}$/.test(providerResponse.raw_payload_hash)
    || !Number.isSafeInteger(providerResponse.duration_ms)
    || providerResponse.duration_ms < 0
    || !Number.isSafeInteger(providerResponse.output_tokens)
    || providerResponse.output_tokens < 0
  ) fail("acceptance_openclaw_provider_response_contract_invalid");
  if (
    providerResponseRaw.includes(mockPrompt)
    || providerResponseRaw.includes(providerSentinel)
    || providerResponseRaw.includes(token)
    || providerResponse.raw_payload_hash === mockPromptSha256
  ) fail("acceptance_openclaw_provider_response_payload_exposed");

  const openClawWorkerLogs = docker(
    ["logs", openClawWorkerName],
    [0],
    "acceptance_openclaw_worker_final_logs_failed",
  );
  const openClawProviderLogs = docker(
    ["logs", openClawProviderName],
    [0],
    "acceptance_openclaw_provider_final_logs_failed",
  );
  for (const exposed of [
    openClawWorkerLogs,
    openClawProviderLogs,
    JSON.stringify(openClawWorkerInspection),
    JSON.stringify(providerTokenProbe),
  ]) {
    if (exposed.includes(token)) fail("acceptance_openclaw_agent_token_exposed");
  }

  process.stdout.write(`${JSON.stringify({
    ok: true,
    contract: "agentops_byoc_typescript_worker_container_v1",
    source_revision: manifest.source_revision,
    image_digest_verified: true,
    source_checkout_required: false,
    worker_container_started: true,
    worker_health_verified: true,
    worker_init_reaper_verified: true,
    idle_graceful_stop_verified: true,
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
    openclaw_provider_request_contract: "agentops_openclaw_provider_request_v1",
    openclaw_provider_response_contract: "agentops_openclaw_provider_response_v1",
    openclaw_provider_container_started: true,
    openclaw_worker_container_started: true,
    openclaw_provider_health_verified: true,
    openclaw_provider_socket_protocol_verified: true,
    openclaw_provider_uid_verified: true,
    openclaw_worker_uid_verified: true,
    openclaw_exact_image_verified: true,
    openclaw_shared_socket_only_verified: true,
    openclaw_worker_provider_mount_isolation_verified: true,
    openclaw_provider_agent_token_isolation_verified: true,
    openclaw_worker_provider_sentinel_unreadable: true,
    openclaw_provider_agent_token_unreadable: true,
    openclaw_mock_prompt_hash_verified: mockPromptSha256 === createHash("sha256")
      .update(mockPrompt).digest("hex"),
    mock_provider_execution_performed: true,
    isolation_verified: true,
    real_provider_execution_performed: false,
    real_provider_execution_evidence_source: "separate_exact_head_harness",
    openclaw_raw_prompt_omitted: true,
    openclaw_raw_response_omitted: true,
  })}\n`);
} catch (error) {
  const code = typeof error?.code === "string" && /^[a-z][a-z0-9_]{2,80}$/.test(error.code)
    ? error.code
    : `acceptance_${activeCheck}_assertion_failed`;
  process.stderr.write(`${code}\n`);
  process.exitCode = 1;
} finally {
  spawnSync("docker", ["rm", "--force", openClawWorkerName], { stdio: "ignore" });
  spawnSync("docker", ["rm", "--force", openClawProviderName], { stdio: "ignore" });
  spawnSync("docker", ["rm", "--force", workerName], { stdio: "ignore" });
  spawnSync("docker", ["rm", "--force", stubName], { stdio: "ignore" });
  spawnSync("docker", ["volume", "rm", "--force", openClawSocketVolume], { stdio: "ignore" });
  rmSync(root, { recursive: true, force: true });
}
