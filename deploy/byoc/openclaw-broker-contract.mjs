#!/usr/bin/env node

import assert from "node:assert/strict";
import {
  chmodSync,
  chownSync,
  existsSync,
  lstatSync,
  mkdtempSync,
  readFileSync,
  rmSync,
} from "node:fs";
import { createServer, request } from "node:http";
import { createHash } from "node:crypto";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const entrypoint = fileURLToPath(new URL("./openclaw-broker-entrypoint.mjs", import.meta.url));
const root = mkdtempSync(join(tmpdir(), "agentops-openclaw-broker-contract-"));
const publicRoot = join(root, "public");
const privateRoot = join(root, "private");
const publicSocket = join(publicRoot, "broker.sock");
const privateSocket = join(privateRoot, "executor.sock");
const uid = process.getuid();
const gid = process.getgid();
const secretCanary = "broker-secret-canary-must-not-appear";

await import("node:fs/promises").then(async ({ mkdir }) => {
  await mkdir(publicRoot, { mode: 0o750 });
  await mkdir(privateRoot, { mode: 0o750 });
});
chmodSync(publicRoot, 0o750);
chmodSync(privateRoot, 0o750);
chownSync(publicRoot, uid, gid);
chownSync(privateRoot, uid, gid);

let executor;
let broker;
let brokerOutput = "";
let privateCalls = 0;
let privateCancellationObserved = false;
let slowResponse = null;
let lastPrivateBody = null;

function jsonResponse(response, status, payload) {
  const body = Buffer.from(`${JSON.stringify(payload)}\n`);
  response.writeHead(status, {
    "Content-Type": "application/json",
    "Content-Length": body.byteLength,
    Connection: "close",
  });
  response.end(body);
}

function executionRequest(prompt, timeoutSeconds = 5) {
  return {
    schema: "agentops_openclaw_provider_request_v1",
    agent_name: "main",
    prompt,
    prompt_hash: createHash("sha256").update(prompt, "utf8").digest("hex"),
    timeout_seconds: timeoutSeconds,
  };
}

function startExecutor() {
  return new Promise((resolveStart, rejectStart) => {
    executor = createServer((incoming, response) => {
      response.once("error", () => {});
      privateCalls += 1;
      const chunks = [];
      incoming.on("data", (chunk) => chunks.push(chunk));
      incoming.once("end", () => {
        lastPrivateBody = Buffer.concat(chunks);
        const payload = JSON.parse(lastPrivateBody.toString("utf8"));
        if (payload.prompt === "slow") {
          slowResponse = response;
          response.once("close", () => {
            if (!response.writableEnded) privateCancellationObserved = true;
          });
          return;
        }
        if (payload.prompt === "oversized-response") {
          response.writeHead(200, { "Content-Type": "application/json", Connection: "close" });
          response.end(Buffer.alloc(1024 * 1024 + 1, 0x61));
          return;
        }
        if (payload.prompt === "invalid-status") {
          jsonResponse(response, 700, { schema: "executor-test-response-v1", ok: false });
          return;
        }
        jsonResponse(response, payload.status || 200, {
          schema: "executor-test-response-v1",
          ok: true,
          agent_name: payload.agent_name,
        });
      });
    });
    executor.on("connection", (socket) => socket.on("error", () => {}));
    executor.on("clientError", (_error, socket) => socket.destroy());
    executor.once("error", rejectStart);
    executor.listen(privateSocket, () => {
      executor.off("error", rejectStart);
      chmodSync(privateSocket, 0o660);
      chownSync(privateSocket, uid, gid);
      resolveStart();
    });
  });
}

function brokerEnvironment(extra = {}) {
  return {
    PATH: process.env.PATH,
    LANG: "C",
    AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_PATH: publicSocket,
    AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_PATH: privateSocket,
    AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_GID: String(gid),
    AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_GID: String(gid),
    AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_UID: String(uid),
    AGENTOPS_OPENCLAW_BROKER_REQUEST_TIMEOUT_MS: "10000",
    AGENTOPS_OPENCLAW_BROKER_BODY_TIMEOUT_MS: "1000",
    ...extra,
  };
}

function spawnBroker(extra = {}) {
  const child = spawn(process.execPath, [entrypoint], {
    env: brokerEnvironment(extra),
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (chunk) => { brokerOutput += chunk.toString("utf8"); });
  child.stderr.on("data", (chunk) => { brokerOutput += chunk.toString("utf8"); });
  return child;
}

function call({ method = "POST", path = "/v1/execute", body = executionRequest("success"), headers = {} } = {}) {
  const payload = Buffer.isBuffer(body) ? body : Buffer.from(JSON.stringify(body));
  return new Promise((resolveCall, rejectCall) => {
    const client = request({
      socketPath: publicSocket,
      method,
      path,
      headers: method === "POST" ? {
        "Content-Type": "application/json",
        "Content-Length": payload.byteLength,
        ...headers,
      } : headers,
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.once("error", rejectCall);
      response.once("end", () => {
        const raw = Buffer.concat(chunks).toString("utf8");
        let parsed = null;
        try { parsed = JSON.parse(raw); } catch {}
        resolveCall({ status: response.statusCode, body: parsed, raw });
      });
    });
    client.once("error", rejectCall);
    client.end(method === "POST" ? payload : undefined);
  });
}

async function waitFor(predicate, label, attempts = 200) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (await predicate()) return;
    await new Promise((resolveWait) => setTimeout(resolveWait, 20));
  }
  throw new Error(`${label}_timeout`);
}

async function waitForBrokerReady() {
  await waitFor(async () => {
    if (broker.exitCode !== null) throw new Error(`broker_early_exit_${broker.exitCode}`);
    if (!existsSync(publicSocket)) return false;
    try {
      const health = await call({ method: "GET", path: "/health", body: Buffer.alloc(0) });
      return health.status === 200 && health.body?.ready === true;
    } catch {
      return false;
    }
  }, "broker_ready");
}

function waitForExit(child) {
  return new Promise((resolveExit) => {
    if (child.exitCode !== null) resolveExit(child.exitCode);
    else child.once("exit", resolveExit);
  });
}

try {
  const source = readFileSync(entrypoint, "utf8");
  assert.match(source, /a03_mount_path_separation_only:\s*true/);
  assert.match(source, /so_peercred_verified:\s*false/);
  assert.match(source, /full_hostile_runtime_isolation_verified:\s*false/);
  assert.doesNotMatch(source, /so_peercred_verified:\s*true/);
  assert.doesNotMatch(source, /full_hostile_runtime_isolation_verified:\s*true/);
  assert.doesNotMatch(source, /execFile|spawn\(|fork\(/);
  assert.doesNotMatch(source, /createConnection\(\{\s*host|listen\([^)]*,\s*["'](?:0\.0\.0\.0|127\.0\.0\.1|localhost)/);
  assert.equal((source.match(/publicResponse\.once\("close", cancel\)/g) || []).length, 1);
  assert.match(source, /publicSocketDirectoryMode/);
  assert.match(source, /\(metadata\.mode & 0o777\) !== expectedMode/);

  await startExecutor();
  broker = spawnBroker();
  await waitForBrokerReady();

  const publicMetadata = lstatSync(publicSocket);
  assert.equal(publicMetadata.isSocket(), true);
  assert.equal(publicMetadata.mode & 0o777, 0o660);
  assert.equal(publicMetadata.uid, uid);
  assert.equal(publicMetadata.gid, gid);

  const health = await call({ method: "GET", path: "/health", body: Buffer.alloc(0) });
  assert.equal(health.status, 200);
  assert.equal(health.body.a03_mount_path_separation_only, true);
  assert.equal(health.body.public_private_socket_paths_distinct, true);
  assert.equal(health.body.private_socket_identity_verified, true);
  assert.equal(health.body.execute_requests_received, 0);
  assert.equal(health.body.so_peercred_verified, false);
  assert.equal(health.body.full_hostile_runtime_isolation_verified, false);

  const successRequest = executionRequest("success");
  const successBytes = Buffer.from(`{\n  "timeout_seconds": ${successRequest.timeout_seconds},\n  "prompt_hash": "${successRequest.prompt_hash}",\n  "prompt": "${successRequest.prompt}",\n  "agent_name": "${successRequest.agent_name}",\n  "schema": "${successRequest.schema}"\n}`);
  const success = await call({ body: successBytes });
  const healthAfterSuccess = await call({ method: "GET", path: "/health", body: Buffer.alloc(0) });
  assert.equal(healthAfterSuccess.body.execute_requests_received, 1);
  assert.equal(success.status, 200);
  assert.deepEqual(success.body, {
    schema: "executor-test-response-v1",
    ok: true,
    agent_name: "main",
  });
  assert.deepEqual(lastPrivateBody, successBytes);

  const privateCallsBeforeInvalidRequests = privateCalls;
  const wrongSchemaRequest = executionRequest("wrong-schema");
  wrongSchemaRequest.schema = "agentops_openclaw_provider_request_v0";
  const wrongSchema = await call({ body: wrongSchemaRequest });
  assert.equal(wrongSchema.status, 400);
  assert.equal(wrongSchema.body.error, "RequestValidationFailed");
  assert.equal(privateCalls, privateCallsBeforeInvalidRequests);

  const extraFieldRequest = { ...executionRequest("extra-field"), unexpected: true };
  const extraField = await call({ body: extraFieldRequest });
  assert.equal(extraField.status, 400);
  assert.equal(extraField.body.error, "RequestValidationFailed");
  assert.equal(privateCalls, privateCallsBeforeInvalidRequests);

  const hashMismatchRequest = executionRequest("hash-mismatch");
  hashMismatchRequest.prompt_hash = "0".repeat(64);
  const hashMismatch = await call({ body: hashMismatchRequest });
  assert.equal(hashMismatch.status, 400);
  assert.equal(hashMismatch.body.error, "RequestValidationFailed");
  assert.equal(privateCalls, privateCallsBeforeInvalidRequests);

  const unsafeAgentRequest = executionRequest("unsafe-agent");
  unsafeAgentRequest.agent_name = "../unsafe";
  const unsafeAgent = await call({ body: unsafeAgentRequest });
  assert.equal(unsafeAgent.status, 400);
  assert.equal(unsafeAgent.body.error, "RequestValidationFailed");
  assert.equal(privateCalls, privateCallsBeforeInvalidRequests);

  const malformed = await call({ body: Buffer.from("{") });
  assert.equal(malformed.status, 400);
  assert.equal(malformed.body.error, "RequestJsonInvalid");
  assert.equal(privateCalls, privateCallsBeforeInvalidRequests);
  const unsupported = await call({
    body: executionRequest("wrong-type"),
    headers: { "Content-Type": "text/plain" },
  });
  assert.equal(unsupported.status, 415);
  assert.equal(privateCalls, privateCallsBeforeInvalidRequests);
  const oversized = await call({ body: Buffer.alloc(1024 * 1024 + 1, 0x61) });
  assert.equal(oversized.status, 413);
  assert.equal(privateCalls, privateCallsBeforeInvalidRequests);

  const slowClient = call({ body: executionRequest("slow") }).catch(() => null);
  await waitFor(() => slowResponse !== null, "private_slow_request");
  const busy = await call({ body: executionRequest("busy") });
  assert.equal(busy.status, 503);
  assert.equal(busy.body.error, "BrokerBusy");
  slowResponse.end(`${JSON.stringify({ schema: "executor-test-response-v1", ok: true, agent_name: "main" })}\n`);
  await slowClient;

  const cancellationBody = Buffer.from(JSON.stringify(executionRequest("slow")));
  const cancelling = request({
    socketPath: publicSocket,
    method: "POST",
    path: "/v1/execute",
    headers: {
      "Content-Type": "application/json",
      "Content-Length": cancellationBody.byteLength,
    },
  });
  cancelling.once("error", () => {});
  cancelling.end(cancellationBody);
  await waitFor(() => slowResponse?.writableEnded === false, "private_cancellation_started");
  cancelling.destroy();
  await waitFor(() => privateCancellationObserved, "private_cancellation");
  await waitFor(async () => {
    const candidate = await call({ method: "GET", path: "/health", body: Buffer.alloc(0) });
    return candidate.body?.busy === false;
  }, "broker_slot_release");

  const beforeOversizedResponse = privateCalls;
  const oversizedResponse = await call({ body: executionRequest("oversized-response") });
  assert.equal(oversizedResponse.status, 502);
  assert.equal(oversizedResponse.body.error, "PrivateExecutorUnavailable");
  assert.equal(privateCalls, beforeOversizedResponse + 1);

  const beforeInvalidStatus = privateCalls;
  const invalidStatus = await call({ body: executionRequest("invalid-status") });
  assert.equal(invalidStatus.status, 502);
  assert.equal(invalidStatus.body.error, "PrivateExecutorUnavailable");
  assert.equal(privateCalls, beforeInvalidStatus + 1);

  privateCancellationObserved = false;
  slowResponse = null;
  const shutdownRequest = call({
    body: executionRequest("slow"),
  }).catch(() => null);
  await waitFor(() => slowResponse !== null, "private_shutdown_request");
  broker.kill("SIGTERM");
  await shutdownRequest;
  assert.equal(await waitForExit(broker), 0);
  assert.equal(privateCancellationObserved, true);
  assert.equal(existsSync(publicSocket), false);
  assert.doesNotMatch(brokerOutput, new RegExp(secretCanary));

  chmodSync(publicRoot, 0o700);
  brokerOutput = "";
  const privateDirectoryWithoutOverride = spawnBroker();
  assert.equal(await waitForExit(privateDirectoryWithoutOverride), 78);
  assert.equal(existsSync(publicSocket), false);
  broker = spawnBroker({ AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_DIRECTORY_MODE: "448" });
  await waitForBrokerReady();
  broker.kill("SIGTERM");
  assert.equal(await waitForExit(broker), 0);
  assert.equal(existsSync(publicSocket), false);
  chmodSync(publicRoot, 0o750);

  chmodSync(privateSocket, 0o666);
  brokerOutput = "";
  const badPrivateMode = spawnBroker();
  assert.equal(await waitForExit(badPrivateMode), 78);
  assert.equal(existsSync(publicSocket), false);
  chmodSync(privateSocket, 0o660);

  chmodSync(publicRoot, 0o770);
  const badPublicMode = spawnBroker();
  assert.equal(await waitForExit(badPublicMode), 78);
  assert.equal(existsSync(publicSocket), false);
  chmodSync(publicRoot, 0o750);

  const credentialBroker = spawnBroker({ OPENAI_API_KEY: secretCanary });
  assert.equal(await waitForExit(credentialBroker), 78);
  assert.equal(existsSync(publicSocket), false);

  const samePathBroker = spawn(process.execPath, [entrypoint], {
    env: brokerEnvironment({
      AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_PATH: join(publicRoot, "executor.sock"),
    }),
    stdio: ["ignore", "pipe", "pipe"],
  });
  assert.equal(await waitForExit(samePathBroker), 78);

  process.stdout.write(`${JSON.stringify({
    schema: "agentops_openclaw_broker_contract_v1",
    ok: true,
    a03_mount_path_separation_only: true,
    bounded_public_http_verified: true,
    bounded_private_response_verified: true,
    exact_public_request_schema_verified: true,
    valid_request_raw_bytes_preserved: true,
    malformed_requests_private_calls_omitted: true,
    private_http_status_range_verified: true,
    atomic_single_flight_verified: true,
    public_client_cancellation_forwarded: true,
    broker_shutdown_cancellation_forwarded: true,
    public_socket_mode_0660_verified: true,
    public_directory_mode_0750_verified: true,
    supervisor_internal_backend_directory_mode_0700_verified: true,
    external_public_directory_mode_0700_rejected_without_supervisor_override: true,
    private_socket_mode_0660_verified: true,
    private_directory_mode_0750_verified: true,
    private_socket_metadata_checked_before_connect: true,
    private_socket_identity_pinned_across_connect: false,
    public_private_socket_paths_distinct: true,
    credential_and_runtime_config_environment_rejected: true,
    tcp_listener_omitted: true,
    runtime_spawn_omitted: true,
    so_peercred_verified: false,
    full_hostile_runtime_isolation_verified: false,
  })}\n`);
} finally {
  if (broker && broker.exitCode === null) broker.kill("SIGKILL");
  if (slowResponse && !slowResponse.writableEnded) slowResponse.destroy();
  if (executor) await new Promise((resolveClose) => executor.close(resolveClose));
  rmSync(root, { recursive: true, force: true });
}
