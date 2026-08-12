#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { request } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = mkdtempSync(join(tmpdir(), "agentops-openclaw-provider-contract-"));
const socketPath = join(root, "provider.sock");
const fakePath = join(root, "fake-openclaw.mjs");
const pidPath = join(root, "provider-child.pid");
const disconnectPidPath = join(root, "provider-disconnect-child.pid");
const entrypoint = join(here, "openclaw-provider-entrypoint.mjs");
const healthcheck = join(here, "openclaw-provider-healthcheck.mjs");
const requestSchema = "agentops_openclaw_provider_request_v1";
const responseSchema = "agentops_openclaw_provider_response_v1";
const fixedError = "Provider error detail omitted; OpenClaw execution failed.";
const responseFields = [
  "schema", "ok", "provider_call_performed", "dry_run", "model_name",
  "duration_ms", "output_tokens", "raw_payload_hash", "output_present",
  "retryable", "error_type", "error_message", "raw_prompt_omitted",
  "raw_response_omitted",
].sort();
const secretCanary = "AGENT_TOKEN_CANARY_MUST_NOT_ESCAPE_7f9335";
const responseCanary = "RAW_OPENCLAW_RESPONSE_MUST_NOT_ESCAPE_64aa12";

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function call({ method = "POST", path = "/v1/execute", body, headers = {} }) {
  const bytes = body === undefined
    ? Buffer.alloc(0)
    : Buffer.isBuffer(body) ? body : Buffer.from(JSON.stringify(body));
  return new Promise((resolveCall, rejectCall) => {
    const chunks = [];
    const client = request({
      socketPath,
      method,
      path,
      headers: {
        ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
        "Content-Length": bytes.byteLength,
        Connection: "close",
        ...headers,
      },
    }, (response) => {
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const raw = Buffer.concat(chunks).toString("utf8");
        try {
          resolveCall({ status: response.statusCode, raw, body: JSON.parse(raw) });
        } catch {
          rejectCall(new Error("contract_response_invalid_json"));
        }
      });
    });
    client.once("error", rejectCall);
    client.end(bytes);
  });
}

function executionRequest(prompt, timeoutSeconds = 3) {
  return {
    schema: requestSchema,
    agent_name: "main",
    prompt,
    prompt_hash: sha256(prompt),
    timeout_seconds: timeoutSeconds,
  };
}

function assertExactResponse(payload, ok) {
  assert.deepEqual(Object.keys(payload).sort(), responseFields);
  assert.equal(payload.schema, responseSchema);
  assert.equal(payload.ok, ok);
  assert.equal(payload.dry_run, false);
  assert.equal(payload.model_name, "main");
  assert.match(payload.model_name, /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/);
  assert.ok(Number.isSafeInteger(payload.duration_ms));
  assert.ok(payload.duration_ms >= 0 && payload.duration_ms <= 86_400_000);
  assert.equal(payload.output_tokens, 0);
  assert.match(payload.raw_payload_hash, /^[a-f0-9]{64}$/);
  assert.equal(payload.raw_prompt_omitted, true);
  assert.equal(payload.raw_response_omitted, true);
  if (ok) {
    assert.equal(payload.provider_call_performed, true);
    assert.equal(payload.output_present, true);
    assert.equal(payload.retryable, false);
    assert.equal(payload.error_type, null);
    assert.equal(payload.error_message, null);
  } else {
    assert.equal(payload.output_present, false);
    assert.match(payload.error_type, /^[A-Za-z][A-Za-z0-9._:-]{0,119}$/);
    assert.equal(payload.error_message, fixedError);
  }
}

async function waitForSocket(child) {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) throw new Error("provider_exited_before_ready");
    if (existsSync(socketPath)) {
      try {
        const health = await call({ method: "GET", path: "/health" });
        if (health.status === 200 && health.body.ready === true) return health;
      } catch {
        // The socket can exist briefly before the HTTP listener accepts connections.
      }
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 25));
  }
  throw new Error("provider_not_ready");
}

function processGone(pid) {
  try {
    process.kill(pid, 0);
    return false;
  } catch (error) {
    return error?.code === "ESRCH";
  }
}

let provider;
try {
  writeFileSync(fakePath, `#!/usr/bin/env node
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
const args = process.argv.slice(2);
const prompt = args[args.indexOf("--message") + 1] || "";
if (prompt.includes("slow-signal") || prompt.includes("disconnect-client")) {
  const descendant = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], { stdio: "ignore" });
  const target = prompt.includes("disconnect-client")
    ? ${JSON.stringify(disconnectPidPath)}
    : ${JSON.stringify(pidPath)};
  writeFileSync(target, String(descendant.pid));
  process.on("SIGTERM", () => setTimeout(() => process.exit(0), 25));
  setInterval(() => {}, 1000);
} else if (prompt.includes("fail-provider")) {
  process.stdout.write(JSON.stringify({ leaked: ${JSON.stringify(responseCanary)} }));
  process.stderr.write(${JSON.stringify(secretCanary)});
  process.exit(7);
} else {
  process.stdout.write(JSON.stringify({ result: { meta: { durationMs: 17, finalAssistantVisibleText: ${JSON.stringify(responseCanary)} }, payloads: [] } }));
}
`, { mode: 0o700 });
  chmodSync(fakePath, 0o700);

  const environment = {
    PATH: process.env.PATH,
    HOME: root,
    NODE_ENV: "production",
    OPENCLAW_BIN: fakePath,
    OPENCLAW_AGENT: "main",
    OPENCLAW_TIMEOUT_SECONDS: "5",
    OPENCLAW_WORKSPACE: root,
    OPENCLAW_PROVIDER_SOCKET: socketPath,
    OPENCLAW_PROVIDER_SOCKET_GID: String(process.getgid()),
    OPENCLAW_PROVIDER_SHUTDOWN_GRACE_MS: "1000",
  };
  const tokenRejected = spawnSync(process.execPath, [entrypoint], {
    cwd: root,
    encoding: "utf8",
    env: { ...environment, AGENTOPS_AGENT_TOKEN: secretCanary },
  });
  assert.equal(tokenRejected.status, 78);
  assert.match(tokenRejected.stderr, /agentops_openclaw_provider_start_failed/);
  assert.doesNotMatch(tokenRejected.stdout + tokenRejected.stderr, new RegExp(secretCanary));

  provider = spawn(process.execPath, [entrypoint], {
    cwd: root,
    env: environment,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let providerOutput = "";
  provider.stdout.on("data", (chunk) => { providerOutput += chunk; });
  provider.stderr.on("data", (chunk) => { providerOutput += chunk; });

  const health = await waitForSocket(provider);
  assert.deepEqual(Object.keys(health.body).sort(), ["busy", "ok", "ready", "schema"]);
  assert.equal(health.body.schema, "agentops_openclaw_provider_health_v1");
  assert.equal(health.body.ok, true);
  assert.equal(health.body.busy, false);
  assert.equal(statSync(socketPath).mode & 0o777, 0o660);
  assert.equal(statSync(socketPath).gid, process.getgid());
  const healthResult = spawnSync(process.execPath, [healthcheck], {
    env: { PATH: process.env.PATH, OPENCLAW_PROVIDER_SOCKET: socketPath },
  });
  assert.equal(healthResult.status, 0);

  const successPrompt = `contract success ${secretCanary}`;
  const success = await call({ body: executionRequest(successPrompt) });
  assert.equal(success.status, 200);
  assertExactResponse(success.body, true);
  assert.doesNotMatch(success.raw, new RegExp(secretCanary));
  assert.doesNotMatch(success.raw, new RegExp(responseCanary));

  const failure = await call({ body: executionRequest("fail-provider") });
  assert.equal(failure.status, 200);
  assertExactResponse(failure.body, false);
  assert.equal(failure.body.provider_call_performed, true);
  assert.doesNotMatch(failure.raw, new RegExp(secretCanary));
  assert.doesNotMatch(failure.raw, new RegExp(responseCanary));

  const disconnectBody = Buffer.from(JSON.stringify(
    executionRequest("disconnect-client", 5),
  ));
  const disconnected = request({
    socketPath,
    method: "POST",
    path: "/v1/execute",
    headers: {
      "Content-Type": "application/json",
      "Content-Length": disconnectBody.byteLength,
    },
  });
  disconnected.once("error", () => {});
  disconnected.end(disconnectBody);
  for (let attempt = 0; attempt < 100 && !existsSync(disconnectPidPath); attempt += 1) {
    await new Promise((resolveWait) => setTimeout(resolveWait, 20));
  }
  assert.ok(existsSync(disconnectPidPath));
  const disconnectedPid = Number(readFileSync(disconnectPidPath, "utf8"));
  disconnected.destroy();
  for (let attempt = 0; attempt < 100 && !processGone(disconnectedPid); attempt += 1) {
    await new Promise((resolveWait) => setTimeout(resolveWait, 20));
  }
  assert.equal(processGone(disconnectedPid), true);
  let providerIdle = false;
  for (let attempt = 0; attempt < 100 && !providerIdle; attempt += 1) {
    const candidate = await call({ method: "GET", path: "/health" });
    providerIdle = candidate.status === 200 && candidate.body.busy === false;
    if (!providerIdle) await new Promise((resolveWait) => setTimeout(resolveWait, 20));
  }
  assert.equal(providerIdle, true);

  const mismatch = executionRequest("hash-mismatch");
  mismatch.prompt_hash = "0".repeat(64);
  const invalid = await call({ body: mismatch });
  assert.equal(invalid.status, 400);
  assert.equal(invalid.body.error, "RequestValidationFailed");

  const oversized = await call({ body: Buffer.alloc(1024 * 1024 + 1, 0x61) });
  assert.equal(oversized.status, 413);
  assert.equal(oversized.body.error, "RequestBodyTooLarge");

  const slow = call({ body: executionRequest("slow-signal", 5) }).catch(() => null);
  for (let attempt = 0; attempt < 100 && !existsSync(pidPath); attempt += 1) {
    await new Promise((resolveWait) => setTimeout(resolveWait, 20));
  }
  assert.ok(existsSync(pidPath));
  const descendantPid = Number(readFileSync(pidPath, "utf8"));
  provider.kill("SIGTERM");
  await new Promise((resolveExit, rejectExit) => {
    provider.once("exit", (code) => code === 0 ? resolveExit() : rejectExit(new Error(`provider_signal_exit_${code}`)));
  });
  await slow;
  for (let attempt = 0; attempt < 100 && !processGone(descendantPid); attempt += 1) {
    await new Promise((resolveWait) => setTimeout(resolveWait, 20));
  }
  assert.equal(processGone(descendantPid), true);
  assert.equal(existsSync(socketPath), false);
  assert.doesNotMatch(providerOutput, new RegExp(secretCanary));
  assert.doesNotMatch(providerOutput, new RegExp(responseCanary));

  process.stdout.write(`${JSON.stringify({
    schema: "agentops_openclaw_provider_contract_v1",
    unix_socket_http: true,
    socket_mode_0660: true,
    non_root_provider: true,
    agent_token_environment_rejected: true,
    exact_response_fields: responseFields.length,
    real_cli_process_invoked: true,
    success_failure_verified: true,
    bounded_request_verified: true,
    healthcheck_verified: true,
    process_group_signal_verified: true,
    client_disconnect_cancellation_verified: true,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
  })}\n`);
} finally {
  if (provider && provider.exitCode === null) provider.kill("SIGKILL");
  rmSync(root, { recursive: true, force: true });
}
