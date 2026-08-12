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
  writeFileSync,
} from "node:fs";
import { createServer, request } from "node:http";
import { createHash, generateKeyPairSync } from "node:crypto";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  loadConfiguration,
  loadExecutorReceiptTrustRoots,
  privateRequestBytes,
  startBrokerService,
  verifyExecutorPrivateResponse,
} from "./openclaw-broker-entrypoint.mjs";
import { canonicalExecutorProtocolBytes } from "./openclaw-executor-protocol.mjs";
import { signExecutorReceipt } from "./openclaw-executor-receipt.mjs";

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
let v2ExecutorResponder = null;
let directBrokerService = null;

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

function executorV2Request(prompt, timeoutSeconds = 5) {
  return {
    schema: "agentops_openclaw_executor_public_request_v2",
    agent_name: "main",
    prompt,
    prompt_sha256: createHash("sha256").update(prompt, "utf8").digest("hex"),
    timeout_seconds: timeoutSeconds,
    request_id: "req_broker_contract_v2",
    run_id: "run_gw_broker_contract_v2",
    nonce: "nonce_broker_contract_v2",
    workspace_id_hash: "1".repeat(64),
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
        if (payload.schema === "agentops_openclaw_executor_dispatch_v2" && v2ExecutorResponder) {
          v2ExecutorResponder(payload, response, lastPrivateBody);
          return;
        }
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

  const v2 = executorV2Request("v2-success");
  const v2Configuration = {
    runtimeManifestSha256: "2".repeat(64),
    isolationPolicySha256: "3".repeat(64),
    seccompProfileSha256: "5".repeat(64),
    executorImageDigest: `sha256:${"6".repeat(64)}`,
    runtimeImageDigest: `sha256:${"7".repeat(64)}`,
    receiptKeyId: "executor-receipt-key-contract",
    receiptTrustRootPath: "/run/secrets/receipt-trust-root",
  };
  const v2Private = privateRequestBytes(
    v2Configuration,
    Buffer.from(JSON.stringify(v2)),
    {
      boot_id: "123e4567-e89b-42d3-a456-426614174000",
      now_boottime_ns: "1000000000",
    },
  );
  const v2Dispatch = JSON.parse(v2Private.toString("utf8"));
  assert.equal(v2Dispatch.schema, "agentops_openclaw_executor_dispatch_v2");
  assert.equal(v2Dispatch.provider_request.prompt, v2.prompt);
  assert.equal(v2Dispatch.request.request_id, v2.request_id);
  assert.equal(v2Dispatch.request.run_id, v2.run_id);
  assert.equal(v2Dispatch.request.nonce, v2.nonce);
  assert.equal(v2Dispatch.request.workspace_id_hash, v2.workspace_id_hash);
  assert.equal(v2Dispatch.request.deadline_boottime_ns, "6000000000");
  assert.equal(v2Dispatch.request.runtime_manifest_sha256, "2".repeat(64));
  assert.equal(v2Dispatch.request.isolation_policy_sha256, "3".repeat(64));
  assert.deepEqual(
    privateRequestBytes(
      { runtimeManifestSha256: null, isolationPolicySha256: null },
      successBytes,
    ),
    successBytes,
  );
  assert.throws(
    () => privateRequestBytes(
      { runtimeManifestSha256: null, isolationPolicySha256: null },
      Buffer.from(JSON.stringify(v2)),
    ),
    /broker_executor_v2_runtime_manifest_sha256_unavailable/,
  );
  const privateCallsBeforeUnconfiguredV2 = privateCalls;
  const unconfiguredV2 = await call({ body: v2 });
  assert.equal(unconfiguredV2.status, 502);
  assert.equal(unconfiguredV2.body.error, "PrivateExecutorUnavailable");
  assert.equal(privateCalls, privateCallsBeforeUnconfiguredV2);

  const receiptKeyId = "executor-receipt-key-contract";
  const receiptKeys = generateKeyPairSync("ed25519");
  const receiptTrustRootPath = join(root, "receipt-trust-roots.json");
  writeFileSync(receiptTrustRootPath, canonicalExecutorProtocolBytes({
    keys: {
      [receiptKeyId]: receiptKeys.publicKey.export({ type: "spki", format: "pem" }),
    },
    schema: "agentops_openclaw_executor_receipt_trust_roots_v1",
  }), { mode: 0o444 });
  chmodSync(receiptTrustRootPath, 0o444);
  const trustRoots = loadExecutorReceiptTrustRoots(receiptTrustRootPath, { expectedUid: uid });
  const privateTrustRootPath = join(root, "receipt-private-key.json");
  writeFileSync(privateTrustRootPath, canonicalExecutorProtocolBytes({
    keys: {
      [receiptKeyId]: receiptKeys.privateKey.export({ type: "pkcs8", format: "pem" }),
    },
    schema: "agentops_openclaw_executor_receipt_trust_roots_v1",
  }), { mode: 0o444 });
  chmodSync(privateTrustRootPath, 0o444);
  assert.throws(
    () => loadExecutorReceiptTrustRoots(privateTrustRootPath, { expectedUid: uid }),
    /broker_receipt_trust_root_key_invalid/,
  );
  const providerResponse = {
    schema: "agentops_openclaw_provider_response_v1",
    ok: true,
    provider_call_performed: true,
    dry_run: false,
    model_name: "contract-openclaw",
    duration_ms: 100,
    output_tokens: 12,
    raw_payload_hash: "4".repeat(64),
    output_present: true,
    retryable: false,
    error_type: null,
    error_message: null,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
  };
  const brokerV2Configuration = {
    ...v2Configuration,
    receiptTrustRootPath,
  };
  const canonicalPublic = canonicalExecutorProtocolBytes(v2);
  const canonicalPrivate = canonicalExecutorProtocolBytes(v2Dispatch);
  const providerResponseBytes = canonicalExecutorProtocolBytes(providerResponse);
  const cgroup = {
    cgroup_id: "cg-41-9001",
    device: "41",
    inode: "9001",
    limits: {
      cpu_max: "50000 100000",
      io_max: "8:0 rbps=1048576 wbps=1048576",
      memory_max_bytes: "536870912",
      memory_swap_max_bytes: "0",
      pids_max: "64",
    },
    process_entry_verified: true,
    root_device: "41",
    root_inode: "7001",
  };
  const launcher = {
    binary_sha256: "8".repeat(64),
    device: "41",
    inode: "8001",
    invoked: true,
    no_new_privs_applied: true,
    runtime_gid: 1200,
    runtime_uid: 1200,
    seccomp_applied: true,
  };
  const receipt = signExecutorReceipt({
    agent_name: v2.agent_name,
    boot_id: v2Dispatch.request.boot_id,
    cgroup,
    deadline_boottime_ns: v2Dispatch.request.deadline_boottime_ns,
    descendants_cleanup_verified: true,
    executor_image_digest: brokerV2Configuration.executorImageDigest,
    executor_key_id: receiptKeyId,
    exit_code: 0,
    exit_kind: "completed",
    finished_boottime_ns: "3000000000",
    hostile_runtime_isolation_verified: false,
    isolation_policy_sha256: brokerV2Configuration.isolationPolicySha256,
    launcher,
    nonce: v2.nonce,
    private_dispatch_schema: v2Dispatch.schema,
    private_dispatch_sha256: createHash("sha256").update(canonicalPrivate).digest("hex"),
    process: { pid: 4242, spawned: true },
    prompt_sha256: v2.prompt_sha256,
    provider: {
      call_observed: true,
      request_sha256: createHash("sha256").update(canonicalExecutorProtocolBytes(v2Dispatch.provider_request)).digest("hex"),
      response_complete: true,
      response_sha256: createHash("sha256").update(providerResponseBytes).digest("hex"),
    },
    provider_call_verified: false,
    public_request_schema: v2.schema,
    public_request_sha256: createHash("sha256").update(canonicalPublic).digest("hex"),
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    receipt_id: "exr-broker-contract-001",
    request_id: v2.request_id,
    run_id: v2.run_id,
    runtime_image_digest: brokerV2Configuration.runtimeImageDigest,
    runtime_manifest_sha256: brokerV2Configuration.runtimeManifestSha256,
    secrets_omitted: true,
    seccomp_profile_sha256: brokerV2Configuration.seccompProfileSha256,
    started_boottime_ns: "2000000000",
    termination_signal: null,
    timeout: { enforced: true, expired: false },
    workspace_id_hash: v2.workspace_id_hash,
  }, receiptKeyId, receiptKeys.privateKey);
  const privateResponse = canonicalExecutorProtocolBytes({
    provider_response: providerResponse,
    receipt,
    schema: "agentops_openclaw_executor_private_response_v2",
  });
  const verificationClock = {
    boot_id: v2Dispatch.request.boot_id,
    now_boottime_ns: "3500000000",
  };
  assert.deepEqual(
    verifyExecutorPrivateResponse(
      brokerV2Configuration,
      canonicalPublic,
      canonicalPrivate,
      privateResponse,
      trustRoots,
      new Set(),
      verificationClock,
    ),
    providerResponseBytes,
  );
  const replayCache = new Set();
  verifyExecutorPrivateResponse(
    brokerV2Configuration,
    canonicalPublic,
    canonicalPrivate,
    privateResponse,
    trustRoots,
    replayCache,
    verificationClock,
  );
  const tamperedReplayCache = new Set();
  assert.throws(
    () => verifyExecutorPrivateResponse(
      brokerV2Configuration,
      canonicalPublic,
      canonicalPrivate,
      privateResponse,
      trustRoots,
      replayCache,
      verificationClock,
    ),
    /executor_receipt_replayed/,
  );
  const tamperedPrivateResponse = canonicalExecutorProtocolBytes({
    provider_response: { ...providerResponse, raw_payload_hash: "9".repeat(64) },
    receipt,
    schema: "agentops_openclaw_executor_private_response_v2",
  });
  assert.throws(
    () => verifyExecutorPrivateResponse(
      brokerV2Configuration,
      canonicalPublic,
      canonicalPrivate,
      tamperedPrivateResponse,
      trustRoots,
      tamperedReplayCache,
      verificationClock,
    ),
    /broker_executor_v2_provider_response_binding_invalid/,
  );
  assert.equal(tamperedReplayCache.size, 0);
  assert.deepEqual(
    verifyExecutorPrivateResponse(
      brokerV2Configuration,
      canonicalPublic,
      canonicalPrivate,
      privateResponse,
      trustRoots,
      tamperedReplayCache,
      verificationClock,
    ),
    providerResponseBytes,
  );
  assert.throws(
    () => verifyExecutorPrivateResponse(
      brokerV2Configuration,
      canonicalPublic,
      canonicalPrivate,
      Buffer.from(` ${privateResponse.toString("utf8")}`),
      trustRoots,
      new Set(),
      verificationClock,
    ),
    /broker_executor_v2_response_encoding_noncanonical/,
  );

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

  const directBrokerConfiguration = loadConfiguration(brokerEnvironment({
    AGENTOPS_OPENCLAW_BROKER_RUNTIME_MANIFEST_SHA256: brokerV2Configuration.runtimeManifestSha256,
    AGENTOPS_OPENCLAW_BROKER_ISOLATION_POLICY_SHA256: brokerV2Configuration.isolationPolicySha256,
    AGENTOPS_OPENCLAW_BROKER_SECCOMP_PROFILE_SHA256: brokerV2Configuration.seccompProfileSha256,
    AGENTOPS_OPENCLAW_BROKER_EXECUTOR_IMAGE_REFERENCE: `registry.example/agentops/executor@${brokerV2Configuration.executorImageDigest}`,
    AGENTOPS_OPENCLAW_BROKER_RUNTIME_IMAGE_DIGEST: brokerV2Configuration.runtimeImageDigest,
    AGENTOPS_OPENCLAW_BROKER_RECEIPT_KEY_ID: receiptKeyId,
    AGENTOPS_OPENCLAW_RECEIPT_TRUST_ROOT_PATH: receiptTrustRootPath,
  }));
  const integrationBootId = "123e4567-e89b-42d3-a456-426614174000";
  let integrationClockReads = 0;
  let integrationResponseMode = "tampered";
  let integrationReceiptCounter = 0;
  let integrationPublicRequest = null;
  v2ExecutorResponder = (dispatch, response, privateBytes) => {
    const canonicalProviderResponse = canonicalExecutorProtocolBytes(providerResponse);
    const signedReceipt = signExecutorReceipt({
      agent_name: integrationPublicRequest.agent_name,
      boot_id: dispatch.request.boot_id,
      cgroup,
      deadline_boottime_ns: dispatch.request.deadline_boottime_ns,
      descendants_cleanup_verified: true,
      executor_image_digest: directBrokerConfiguration.executorImageDigest,
      executor_key_id: receiptKeyId,
      exit_code: 0,
      exit_kind: "completed",
      finished_boottime_ns: "3000000000",
      hostile_runtime_isolation_verified: false,
      isolation_policy_sha256: directBrokerConfiguration.isolationPolicySha256,
      launcher,
      nonce: integrationPublicRequest.nonce,
      private_dispatch_schema: dispatch.schema,
      private_dispatch_sha256: createHash("sha256").update(privateBytes).digest("hex"),
      process: { pid: 4242, spawned: true },
      prompt_sha256: integrationPublicRequest.prompt_sha256,
      provider: {
        call_observed: true,
        request_sha256: createHash("sha256")
          .update(canonicalExecutorProtocolBytes(dispatch.provider_request)).digest("hex"),
        response_complete: true,
        response_sha256: createHash("sha256").update(canonicalProviderResponse).digest("hex"),
      },
      provider_call_verified: false,
      public_request_schema: integrationPublicRequest.schema,
      public_request_sha256: createHash("sha256")
        .update(canonicalExecutorProtocolBytes(integrationPublicRequest)).digest("hex"),
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      receipt_id: `exr-broker-http-${String(integrationReceiptCounter += 1).padStart(3, "0")}`,
      request_id: integrationPublicRequest.request_id,
      run_id: integrationPublicRequest.run_id,
      runtime_image_digest: directBrokerConfiguration.runtimeImageDigest,
      runtime_manifest_sha256: directBrokerConfiguration.runtimeManifestSha256,
      secrets_omitted: true,
      seccomp_profile_sha256: directBrokerConfiguration.seccompProfileSha256,
      started_boottime_ns: "2000000000",
      termination_signal: null,
      timeout: { enforced: true, expired: false },
      workspace_id_hash: integrationPublicRequest.workspace_id_hash,
    }, receiptKeyId, receiptKeys.privateKey);
    const returnedProviderResponse = integrationResponseMode === "tampered"
      ? { ...providerResponse, raw_payload_hash: "9".repeat(64) }
      : providerResponse;
    const responseBytes = canonicalExecutorProtocolBytes({
      provider_response: returnedProviderResponse,
      receipt: signedReceipt,
      schema: "agentops_openclaw_executor_private_response_v2",
    });
    response.writeHead(200, {
      "Content-Type": "application/json",
      "Content-Length": responseBytes.byteLength,
      Connection: "close",
    });
    response.end(responseBytes);
  };
  directBrokerService = await startBrokerService(directBrokerConfiguration, {
    receiptTrustRoots: trustRoots,
    readBootClock: () => ({
      boot_id: integrationBootId,
      now_boottime_ns: integrationClockReads++ % 2 === 0 ? "1000000000" : "3500000000",
    }),
  });
  const integrationRequest = {
    ...executorV2Request("v2-http-integration"),
    nonce: "nonce_broker_http_v2",
    request_id: "req_broker_http_v2",
    run_id: "run_gw_broker_http_v2",
  };
  integrationPublicRequest = integrationRequest;
  const tamperedHttpResponse = await call({ body: integrationRequest });
  assert.equal(tamperedHttpResponse.status, 502);
  assert.equal(tamperedHttpResponse.body.error, "PrivateExecutorUnavailable");
  assert.doesNotMatch(tamperedHttpResponse.raw, /9999999999999999/);
  integrationResponseMode = "valid";
  const verifiedHttpResponse = await call({ body: integrationRequest });
  assert.equal(verifiedHttpResponse.status, 200);
  assert.deepEqual(verifiedHttpResponse.body, providerResponse);
  const replayedHttpResponse = await call({ body: integrationRequest });
  assert.equal(replayedHttpResponse.status, 502);
  assert.equal(replayedHttpResponse.body.error, "PrivateExecutorUnavailable");
  await directBrokerService.shutdown();
  directBrokerService = null;
  v2ExecutorResponder = null;

  process.stdout.write(`${JSON.stringify({
    schema: "agentops_openclaw_broker_contract_v1",
    ok: true,
    a03_mount_path_separation_only: true,
    bounded_public_http_verified: true,
    bounded_private_response_verified: true,
    exact_public_request_schema_verified: true,
    valid_request_raw_bytes_preserved: true,
    executor_v2_governance_and_deadline_binding_verified: true,
    executor_v2_incomplete_verification_config_rejected_before_dispatch: true,
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
    receipt_trust_root_environment_accepted: true,
    executor_receipt_signature_request_response_and_replay_verified: true,
    executor_v2_running_http_receipt_integration_verified: true,
    tampered_v2_response_failed_closed_without_burning_nonce: true,
    tcp_listener_omitted: true,
    runtime_spawn_omitted: true,
    so_peercred_verified: false,
    full_hostile_runtime_isolation_verified: false,
  })}\n`);
} finally {
  if (directBrokerService) await directBrokerService.shutdown();
  if (broker && broker.exitCode === null) broker.kill("SIGKILL");
  if (slowResponse && !slowResponse.writableEnded) slowResponse.destroy();
  if (executor) await new Promise((resolveClose) => executor.close(resolveClose));
  rmSync(root, { recursive: true, force: true });
}
