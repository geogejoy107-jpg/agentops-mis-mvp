#!/usr/bin/env node

import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import {
  chmodSync,
  chownSync,
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  openSync,
  readSync,
  statSync,
  unlinkSync,
} from "node:fs";
import { createServer } from "node:http";
import { createConnection } from "node:net";
import { dirname, isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const REQUEST_SCHEMA = "agentops_openclaw_provider_request_v1";
export const RESPONSE_SCHEMA = "agentops_openclaw_provider_response_v1";
export const HEALTH_SCHEMA = "agentops_openclaw_provider_health_v1";
export const DEFAULT_SOCKET_PATH = "/run/agentops-openclaw-provider/provider.sock";
export const MAX_BODY_BYTES = 1024 * 1024;
export const RESPONSE_FIELDS = Object.freeze([
  "schema",
  "ok",
  "provider_call_performed",
  "dry_run",
  "model_name",
  "duration_ms",
  "output_tokens",
  "raw_payload_hash",
  "output_present",
  "retryable",
  "error_type",
  "error_message",
  "raw_prompt_omitted",
  "raw_response_omitted",
]);

const REQUEST_FIELDS = Object.freeze([
  "agent_name",
  "prompt",
  "prompt_hash",
  "schema",
  "timeout_seconds",
]);
const SHA256_HEX = /^[a-f0-9]{64}$/;
const SAFE_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/;
const FIXED_PROVIDER_ERROR =
  "Provider error detail omitted; OpenClaw execution failed.";
const MAX_PROVIDER_OUTPUT_BYTES = 1024 * 1024;
const MAX_RUNTIME_BINARY_BYTES = 256 * 1024 * 1024;
const TOKEN_ENVIRONMENT_NAMES = Object.freeze([
  "AGENTOPS_AGENT_TOKEN",
  "AGENTOPS_AGENT_TOKEN_FILE",
  "AGENTOPS_AGENT_TOKEN_SOURCE_FILE",
  "AGENTOPS_API_KEY",
  "AGENTOPS_API_KEY_FILE",
]);

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function sameFileIdentity(left, right) {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.mode === right.mode
    && left.size === right.size
    && left.mtimeNs === right.mtimeNs
    && left.ctimeNs === right.ctimeNs;
}

function verifyBinaryIdentity(binaryPath, expectedSha256) {
  if (!Number.isInteger(constants.O_NOFOLLOW) || constants.O_NOFOLLOW <= 0) {
    fail("openclaw_bin_nofollow_unavailable");
  }
  let pathBefore;
  try {
    pathBefore = lstatSync(binaryPath, { bigint: true });
  } catch {
    fail("openclaw_bin_identity_unavailable");
  }
  if (pathBefore.isSymbolicLink()) fail("openclaw_bin_symlink_forbidden");
  if (!pathBefore.isFile()) fail("openclaw_bin_regular_file_required");
  if (pathBefore.size > BigInt(MAX_RUNTIME_BINARY_BYTES)) {
    fail("openclaw_bin_too_large");
  }

  let descriptor;
  try {
    descriptor = openSync(binaryPath, constants.O_RDONLY | constants.O_NOFOLLOW);
  } catch {
    fail("openclaw_bin_open_failed");
  }
  try {
    const descriptorBefore = fstatSync(descriptor, { bigint: true });
    if (!descriptorBefore.isFile() || !sameFileIdentity(pathBefore, descriptorBefore)) {
      fail("openclaw_bin_identity_changed");
    }
    const digest = createHash("sha256");
    const buffer = Buffer.allocUnsafe(64 * 1024);
    let bytesReadTotal = 0;
    while (true) {
      const bytesRead = readSync(descriptor, buffer, 0, buffer.byteLength, null);
      if (bytesRead === 0) break;
      bytesReadTotal += bytesRead;
      if (bytesReadTotal > MAX_RUNTIME_BINARY_BYTES) fail("openclaw_bin_too_large");
      digest.update(buffer.subarray(0, bytesRead));
    }
    const descriptorAfter = fstatSync(descriptor, { bigint: true });
    let pathAfter;
    try {
      pathAfter = lstatSync(binaryPath, { bigint: true });
    } catch {
      fail("openclaw_bin_identity_changed");
    }
    if (
      BigInt(bytesReadTotal) !== descriptorBefore.size
      || !sameFileIdentity(descriptorBefore, descriptorAfter)
      || !sameFileIdentity(descriptorAfter, pathAfter)
      || pathAfter.isSymbolicLink()
    ) {
      fail("openclaw_bin_identity_changed");
    }
    if (digest.digest("hex") !== expectedSha256) fail("openclaw_bin_digest_mismatch");
  } finally {
    closeSync(descriptor);
  }
}

function boundedInteger(value, fallback, minimum, maximum, name) {
  const candidate = value === undefined || value === "" ? fallback : Number(value);
  if (!Number.isSafeInteger(candidate) || candidate < minimum || candidate > maximum) {
    fail(`${name}_invalid`);
  }
  return candidate;
}

function requiredAbsolutePath(value, name) {
  if (typeof value !== "string" || !value || !isAbsolute(value) || resolve(value) !== value) {
    fail(`${name}_absolute_required`);
  }
  return value;
}

function safeIdentifier(value, name) {
  if (typeof value !== "string" || !SAFE_IDENTIFIER.test(value)) {
    fail(`${name}_invalid`);
  }
  return value;
}

function exactKeys(value, expected) {
  return Object.keys(value).sort().join("\n") === expected.join("\n");
}

function providerEnvironment() {
  const allowed = [
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "SHELL",
    "TMPDIR",
    "TMP",
    "TEMP",
    "TZ",
    "OPENCLAW_HOME",
    "OPENCLAW_STATE_DIR",
    "OPENCLAW_CONFIG_PATH",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
  ];
  return {
    NODE_ENV: "production",
    ...Object.fromEntries(
      allowed
        .filter((name) => typeof process.env[name] === "string" && process.env[name])
        .map((name) => [name, process.env[name]]),
    ),
  };
}

export function loadConfiguration(environment = process.env) {
  if (Number(process.versions.node.split(".")[0]) < 20) fail("node_20_required");
  if (process.getuid?.() === 0 || process.getgid?.() === 0) fail("provider_root_forbidden");
  for (const name of TOKEN_ENVIRONMENT_NAMES) {
    if (String(environment[name] || "")) fail("agent_token_environment_forbidden");
  }

  const socketPath = requiredAbsolutePath(
    environment.OPENCLAW_PROVIDER_SOCKET || DEFAULT_SOCKET_PATH,
    "openclaw_provider_socket",
  );
  const binaryPath = requiredAbsolutePath(environment.OPENCLAW_BIN, "openclaw_bin");
  const binarySha256 = String(environment.OPENCLAW_BIN_SHA256 || "");
  if (!SHA256_HEX.test(binarySha256)) fail("openclaw_bin_sha256_invalid");
  const workspace = requiredAbsolutePath(
    environment.OPENCLAW_WORKSPACE || environment.AGENTOPS_WORKER_CWD || process.cwd(),
    "openclaw_workspace",
  );
  if (!statSync(workspace).isDirectory()) fail("openclaw_workspace_directory_required");

  const configuration = {
    socketPath,
    binaryPath,
    binarySha256,
    workspace,
    agentName: safeIdentifier(environment.OPENCLAW_AGENT || "main", "openclaw_agent"),
    timeoutSeconds: boundedInteger(
      environment.OPENCLAW_TIMEOUT_SECONDS,
      180,
      1,
      600,
      "openclaw_timeout_seconds",
    ),
    socketGid: boundedInteger(
      environment.OPENCLAW_PROVIDER_SOCKET_GID,
      process.getgid?.(),
      1,
      2 ** 31 - 1,
      "openclaw_provider_socket_gid",
    ),
    shutdownGraceMs: boundedInteger(
      environment.OPENCLAW_PROVIDER_SHUTDOWN_GRACE_MS,
      5_000,
      100,
      30_000,
      "openclaw_provider_shutdown_grace_ms",
    ),
  };
  verifyBinaryIdentity(configuration.binaryPath, configuration.binarySha256);
  return Object.freeze(configuration);
}

function validateRequest(value, configuration) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail("request_object_required");
  }
  if (!exactKeys(value, REQUEST_FIELDS)) fail("request_fields_invalid");
  if (value.schema !== REQUEST_SCHEMA) fail("request_schema_invalid");
  const agentName = safeIdentifier(value.agent_name, "agent_name");
  if (agentName !== configuration.agentName) fail("agent_name_not_configured");
  if (
    typeof value.prompt !== "string"
    || !value.prompt.trim()
    || value.prompt.includes("\u0000")
    || Buffer.byteLength(value.prompt, "utf8") > MAX_BODY_BYTES - 1024
  ) {
    fail("prompt_invalid");
  }
  if (typeof value.prompt_hash !== "string" || !SHA256_HEX.test(value.prompt_hash)) {
    fail("prompt_hash_invalid");
  }
  if (sha256(value.prompt) !== value.prompt_hash) fail("prompt_hash_mismatch");
  const timeoutSeconds = boundedInteger(
    value.timeout_seconds,
    undefined,
    1,
    configuration.timeoutSeconds,
    "timeout_seconds",
  );
  return { agentName, prompt: value.prompt, timeoutSeconds };
}

function response({
  ok,
  providerCallPerformed,
  modelName,
  durationMs,
  rawPayloadHash,
  outputPresent,
  retryable,
  errorType,
}) {
  const payload = {
    schema: RESPONSE_SCHEMA,
    ok,
    provider_call_performed: providerCallPerformed,
    dry_run: false,
    model_name: safeIdentifier(modelName, "model_name"),
    duration_ms: boundedInteger(durationMs, 0, 0, 86_400_000, "duration_ms"),
    output_tokens: 0,
    raw_payload_hash: SHA256_HEX.test(rawPayloadHash)
      ? rawPayloadHash
      : fail("raw_payload_hash_invalid"),
    output_present: outputPresent,
    retryable,
    error_type: errorType,
    error_message: ok ? null : FIXED_PROVIDER_ERROR,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
  };
  if (!exactKeys(payload, [...RESPONSE_FIELDS].sort())) fail("response_fields_invalid");
  if (ok) {
    if (
      !outputPresent
      || !providerCallPerformed
      || retryable
      || errorType !== null
      || payload.error_message !== null
    ) fail("success_response_invariant_invalid");
  } else if (
    outputPresent
    || typeof errorType !== "string"
    || !SAFE_IDENTIFIER.test(errorType)
    || payload.error_message !== FIXED_PROVIDER_ERROR
  ) {
    fail("failure_response_invariant_invalid");
  }
  return payload;
}

function visibleOutput(stdout) {
  let payload;
  try {
    payload = stdout ? JSON.parse(stdout) : {};
  } catch {
    return { valid: false, present: false, durationMs: null };
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { valid: false, present: false, durationMs: null };
  }
  const result = payload.result && typeof payload.result === "object" ? payload.result : {};
  const meta = result.meta && typeof result.meta === "object" ? result.meta : {};
  const payloads = Array.isArray(result.payloads) ? result.payloads : [];
  const first = payloads[0] && typeof payloads[0] === "object" ? payloads[0] : {};
  const candidate = meta.finalAssistantVisibleText ?? first.text;
  return {
    valid: true,
    present: typeof candidate === "string" && candidate.trim().length > 0,
    durationMs: Number.isSafeInteger(meta.durationMs) ? meta.durationMs : null,
  };
}

function signalProcessGroup(child, signal) {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return true;
  try {
    process.kill(-child.pid, signal);
    return true;
  } catch (error) {
    if (error?.code === "ESRCH") return true;
    try {
      return child.kill(signal);
    } catch {
      return false;
    }
  }
}

function executeOpenClaw(configuration, request) {
  const started = Date.now();
  const stdout = [];
  let stdoutBytes = 0;
  let totalBytes = 0;
  const stdoutHash = createHash("sha256");
  const stderrHash = createHash("sha256");
  let spawned = false;
  let spawnFailed = false;
  let terminalReason = null;
  let forceTimer;
  let settleDone;

  const done = new Promise((resolveDone) => {
    settleDone = resolveDone;
  });
  try {
    verifyBinaryIdentity(configuration.binaryPath, configuration.binarySha256);
  } catch {
    const payload = response({
      ok: false,
      providerCallPerformed: false,
      modelName: request.agentName,
      durationMs: Date.now() - started,
      rawPayloadHash: sha256("OpenClawBinaryIdentityFailure"),
      outputPresent: false,
      retryable: false,
      errorType: "OpenClawBinaryIdentityFailure",
    });
    settleDone();
    return { child: null, done, result: Promise.resolve(payload), terminate: () => true };
  }
  let child;
  try {
    child = spawn(
      configuration.binaryPath,
      [
        "agent",
        "--agent",
        request.agentName,
        "--message",
        request.prompt,
        "--timeout",
        String(request.timeoutSeconds),
        "--json",
      ],
      {
        cwd: configuration.workspace,
        env: providerEnvironment(),
        stdio: ["ignore", "pipe", "pipe"],
        detached: true,
        windowsHide: true,
      },
    );
  } catch {
    const payload = response({
      ok: false,
      providerCallPerformed: false,
      modelName: request.agentName,
      durationMs: Date.now() - started,
      rawPayloadHash: sha256("OpenClawSpawnFailure"),
      outputPresent: false,
      retryable: true,
      errorType: "OpenClawSpawnFailure",
    });
    settleDone();
    return { child: null, done, result: Promise.resolve(payload), terminate: () => true };
  }

  const terminate = (reason, signal = "SIGTERM") => {
    if (!terminalReason) terminalReason = reason;
    const signalled = signalProcessGroup(child, signal);
    if (signal !== "SIGKILL" && !forceTimer) {
      forceTimer = setTimeout(() => {
        signalProcessGroup(child, "SIGKILL");
      }, Math.min(2_000, configuration.shutdownGraceMs));
      forceTimer.unref();
    }
    return signalled;
  };

  const result = new Promise((resolveResult) => {
    child.once("spawn", () => {
      spawned = true;
    });
    child.once("error", () => {
      spawnFailed = !spawned;
      if (!terminalReason) terminalReason = "OpenClawSpawnFailure";
    });
    child.stdout.on("data", (chunk) => {
      const bytes = Buffer.from(chunk);
      stdoutHash.update(bytes);
      totalBytes += bytes.byteLength;
      if (stdoutBytes < MAX_PROVIDER_OUTPUT_BYTES) {
        const remaining = MAX_PROVIDER_OUTPUT_BYTES - stdoutBytes;
        stdout.push(bytes.subarray(0, remaining));
        stdoutBytes += Math.min(bytes.byteLength, remaining);
      }
      if (totalBytes > MAX_PROVIDER_OUTPUT_BYTES && !terminalReason) {
        terminate("OpenClawOutputTooLarge");
      }
    });
    child.stderr.on("data", (chunk) => {
      const bytes = Buffer.from(chunk);
      stderrHash.update(bytes);
      totalBytes += bytes.byteLength;
      if (totalBytes > MAX_PROVIDER_OUTPUT_BYTES && !terminalReason) {
        terminate("OpenClawOutputTooLarge");
      }
    });

    const timeout = setTimeout(() => {
      terminate("OpenClawTimeout");
    }, request.timeoutSeconds * 1000);
    timeout.unref();

    child.once("close", (code) => {
      clearTimeout(timeout);
      clearTimeout(forceTimer);
      const measuredDuration = Date.now() - started;
      const rawPayloadHash = sha256(JSON.stringify({
        stdout_sha256: stdoutHash.digest("hex"),
        stderr_sha256: stderrHash.digest("hex"),
      }));
      const parsed = visibleOutput(Buffer.concat(stdout).toString("utf8"));
      let errorType = terminalReason;
      if (!errorType && (spawnFailed || !spawned)) errorType = "OpenClawSpawnFailure";
      if (!errorType && code !== 0) errorType = "OpenClawExitFailure";
      if (!errorType && !parsed.valid) errorType = "OpenClawInvalidResponse";
      if (!errorType && !parsed.present) errorType = "OpenClawEmptyResponse";
      const ok = errorType === null;
      const payload = response({
        ok,
        providerCallPerformed: spawned,
        modelName: request.agentName,
        durationMs: parsed.durationMs === null ? measuredDuration : parsed.durationMs,
        rawPayloadHash,
        outputPresent: ok,
        retryable: ok ? false : errorType !== "OpenClawInterrupted",
        errorType,
      });
      resolveResult(payload);
      settleDone();
    });
  });

  return { child, done, result, terminate };
}

function writeJson(res, status, payload) {
  const body = `${JSON.stringify(payload)}\n`;
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
    Connection: "close",
  });
  res.end(body);
}

function boundaryError(res, status, error) {
  writeJson(res, status, {
    schema: "agentops_openclaw_provider_error_v1",
    error,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
  });
}

function readJsonBody(req, res) {
  return new Promise((resolveBody, rejectBody) => {
    const declared = Number(req.headers["content-length"] || 0);
    if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) {
      req.resume();
      boundaryError(res, 413, "RequestBodyTooLarge");
      resolveBody(null);
      return;
    }
    const chunks = [];
    let size = 0;
    let rejected = false;
    req.on("data", (chunk) => {
      size += chunk.byteLength;
      if (size > MAX_BODY_BYTES) {
        rejected = true;
        chunks.length = 0;
        return;
      }
      if (!rejected) chunks.push(chunk);
    });
    req.once("aborted", () => rejectBody(new Error("request_aborted")));
    req.once("error", rejectBody);
    req.once("end", () => {
      if (rejected) {
        boundaryError(res, 413, "RequestBodyTooLarge");
        resolveBody(null);
        return;
      }
      try {
        resolveBody(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        boundaryError(res, 400, "RequestJsonInvalid");
        resolveBody(null);
      }
    });
  });
}

function socketIsLive(socketPath) {
  return new Promise((resolveLive) => {
    const socket = createConnection({ path: socketPath });
    const finish = (live) => {
      socket.destroy();
      resolveLive(live);
    };
    socket.setTimeout(250, () => finish(true));
    socket.once("connect", () => finish(true));
    socket.once("error", (error) => {
      if (["ECONNREFUSED", "ENOENT"].includes(error?.code)) finish(false);
      else finish(true);
    });
  });
}

async function prepareSocket(configuration) {
  const directoryPath = dirname(configuration.socketPath);
  let directory;
  try {
    directory = lstatSync(directoryPath);
  } catch {
    fail("provider_socket_directory_unavailable");
  }
  if (
    !directory.isDirectory()
    || directory.isSymbolicLink()
    || directory.uid !== process.getuid()
    || directory.gid !== configuration.socketGid
    || !new Set([0o700, 0o750]).has(directory.mode & 0o777)
  ) {
    fail("provider_socket_directory_permissions_invalid");
  }
  try {
    const existing = lstatSync(configuration.socketPath);
    if (!existing.isSocket()) fail("provider_socket_path_not_socket");
    if (await socketIsLive(configuration.socketPath)) fail("provider_socket_in_use");
    unlinkSync(configuration.socketPath);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

export async function startProviderService(configuration = loadConfiguration()) {
  await prepareSocket(configuration);
  const state = { activeRequest: null, shuttingDown: false };
  const server = createServer(async (req, res) => {
    if (req.method === "GET" && req.url === "/health") {
      writeJson(res, state.shuttingDown ? 503 : 200, {
        schema: HEALTH_SCHEMA,
        ok: !state.shuttingDown,
        ready: !state.shuttingDown,
        busy: state.activeRequest !== null,
      });
      return;
    }
    if (req.method !== "POST" || req.url !== "/v1/execute") {
      req.resume();
      boundaryError(res, 404, "RouteNotFound");
      return;
    }
    if (state.shuttingDown || state.activeRequest) {
      req.resume();
      boundaryError(res, 503, "ProviderBusy");
      return;
    }
    const requestSlot = { req, res, execution: null };
    state.activeRequest = requestSlot;
    try {
      if (!/^application\/json(?:\s*;|$)/i.test(String(req.headers["content-type"] || ""))) {
        req.resume();
        boundaryError(res, 415, "ContentTypeUnsupported");
        return;
      }
      let body;
      try {
        body = await readJsonBody(req, res);
      } catch {
        if (!res.headersSent) boundaryError(res, 400, "RequestReadFailed");
        return;
      }
      if (body === null || res.headersSent) return;
      let request;
      try {
        request = validateRequest(body, configuration);
      } catch {
        boundaryError(res, 400, "RequestValidationFailed");
        return;
      }
      const execution = executeOpenClaw(configuration, request);
      requestSlot.execution = execution;
      let responseCompleted = false;
      const cancelDisconnectedClient = () => {
        if (!responseCompleted && !res.writableEnded) {
          execution.terminate("OpenClawInterrupted");
        }
      };
      res.once("close", cancelDisconnectedClient);
      const result = await execution.result;
      if (!res.destroyed && !res.writableEnded) {
        writeJson(res, 200, result);
        responseCompleted = true;
      }
      res.off("close", cancelDisconnectedClient);
    } finally {
      if (state.activeRequest === requestSlot) state.activeRequest = null;
    }
  });
  server.requestTimeout = (configuration.timeoutSeconds + 35) * 1000;
  server.headersTimeout = 5_000;
  server.keepAliveTimeout = 1_000;
  server.on("clientError", (error, socket) => {
    if (error?.code === "ECONNRESET" || !socket.writable) {
      socket.destroy();
      return;
    }
    socket.once("error", () => socket.destroy());
    socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n");
  });

  await new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(configuration.socketPath, () => {
      server.off("error", rejectListen);
      resolveListen();
    });
  });
  chmodSync(configuration.socketPath, 0o660);
  chownSync(configuration.socketPath, process.getuid(), configuration.socketGid);
  const socket = lstatSync(configuration.socketPath);
  if (!socket.isSocket() || (socket.mode & 0o777) !== 0o660 || socket.gid !== configuration.socketGid) {
    fail("provider_socket_permissions_invalid");
  }

  let shutdownPromise = null;
  const shutdown = (signal = "SIGTERM") => {
    if (shutdownPromise) {
      const killed = state.activeRequest?.execution?.terminate("OpenClawInterrupted", "SIGKILL") ?? true;
      process.exitCode = 1;
      return shutdownPromise.then(() => killed);
    }
    state.shuttingDown = true;
    shutdownPromise = (async () => {
      const closed = new Promise((resolveClosed) => server.close(resolveClosed));
      const activeRequest = state.activeRequest;
      const execution = activeRequest?.execution;
      let forced = false;
      if (activeRequest && !execution) {
        activeRequest.req.destroy();
        if (!activeRequest.res.destroyed) activeRequest.res.destroy();
      }
      if (execution) {
        if (!execution.terminate("OpenClawInterrupted", signal)) forced = true;
        const force = setTimeout(() => {
          forced = true;
          if (!execution.terminate("OpenClawInterrupted", "SIGKILL")) process.exitCode = 1;
        }, configuration.shutdownGraceMs);
        force.unref();
        await execution.done;
        clearTimeout(force);
      }
      await closed;
      try {
        unlinkSync(configuration.socketPath);
      } catch (error) {
        if (error?.code !== "ENOENT") forced = true;
      }
      if (forced) process.exitCode = 1;
      return !forced;
    })();
    return shutdownPromise;
  };

  return { server, state, shutdown, configuration };
}

async function main() {
  const service = await startProviderService();
  let handlingSignal = false;
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
    process.on(signal, async () => {
      if (handlingSignal) {
        service.shutdown(signal);
        return;
      }
      handlingSignal = true;
      await service.shutdown(signal);
    });
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(() => {
    process.stderr.write("agentops_openclaw_provider_start_failed\n");
    process.exitCode = 78;
  });
}
