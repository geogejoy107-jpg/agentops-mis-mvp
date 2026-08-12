#!/usr/bin/env node

import {
  chmodSync,
  chownSync,
  lstatSync,
  unlinkSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { createServer, request as httpRequest } from "node:http";
import { createConnection } from "node:net";
import { dirname, isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const MAX_REQUEST_BYTES = 1024 * 1024;
export const MAX_RESPONSE_BYTES = 1024 * 1024;

const HEALTH_SCHEMA = "agentops_openclaw_broker_health_v1";
const ERROR_SCHEMA = "agentops_openclaw_broker_error_v1";
const DEFAULT_PUBLIC_SOCKET = "/run/agentops-openclaw-public/broker.sock";
const DEFAULT_PRIVATE_SOCKET = "/run/agentops-openclaw-private/executor.sock";
const DEFAULT_PUBLIC_GID = 2100;
const DEFAULT_PRIVATE_GID = 2200;
const DEFAULT_REQUEST_TIMEOUT_MS = 240_000;
const DEFAULT_BODY_TIMEOUT_MS = 5_000;
const REQUEST_SCHEMA = "agentops_openclaw_provider_request_v1";
const REQUEST_FIELDS = Object.freeze([
  "agent_name",
  "prompt",
  "prompt_hash",
  "schema",
  "timeout_seconds",
]);
const SAFE_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/;
const SHA256_HEX = /^[a-f0-9]{64}$/;

const FORBIDDEN_ENVIRONMENT_NAMES = /(?:^|_)(?:TOKEN|PASSWORD|SECRET|API_KEY|DSN|COOKIE|CREDENTIALS?)(?:$|_)/i;
const FORBIDDEN_ENVIRONMENT_PREFIXES = [
  "AWS_",
  "AZURE_",
  "GOOGLE_",
  "OPENAI_",
  "ANTHROPIC_",
];
const FORBIDDEN_ENVIRONMENT_EXACT = new Set([
  "ALL_PROXY",
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "LD_PRELOAD",
  "NODE_EXTRA_CA_CERTS",
  "NODE_OPTIONS",
  "NODE_PATH",
  "NO_PROXY",
  "SSH_AUTH_SOCK",
  "OPENCLAW_CONFIG",
  "OPENCLAW_HOME",
  "XDG_CONFIG_HOME",
]);
const ALLOWED_BROKER_ENVIRONMENT = new Set([
  "AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_PATH",
  "AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_PATH",
  "AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_GID",
  "AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_DIRECTORY_MODE",
  "AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_GID",
  "AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_UID",
  "AGENTOPS_OPENCLAW_BROKER_REQUEST_TIMEOUT_MS",
  "AGENTOPS_OPENCLAW_BROKER_BODY_TIMEOUT_MS",
]);

function fail(message) {
  const error = new Error(message);
  error.code = message;
  throw error;
}

function requiredAbsolutePath(value, fallback, label) {
  const candidate = String(value || fallback).trim();
  if (!candidate || !isAbsolute(candidate) || resolve(candidate) !== candidate) {
    fail(`${label}_absolute_path_required`);
  }
  return candidate;
}

function integerValue(value, fallback, minimum, maximum, label) {
  const candidate = value === undefined || value === "" ? fallback : Number(value);
  if (!Number.isSafeInteger(candidate) || candidate < minimum || candidate > maximum) {
    fail(`${label}_invalid`);
  }
  return candidate;
}

function assertCredentialFreeEnvironment(environment) {
  for (const name of Object.keys(environment)) {
    if (ALLOWED_BROKER_ENVIRONMENT.has(name)) continue;
    if (
      FORBIDDEN_ENVIRONMENT_EXACT.has(name)
      || FORBIDDEN_ENVIRONMENT_NAMES.test(name)
      || FORBIDDEN_ENVIRONMENT_PREFIXES.some((prefix) => name.startsWith(prefix))
      || name.startsWith("DYLD_")
      || (name.startsWith("OPENCLAW_") && !name.startsWith("AGENTOPS_OPENCLAW_BROKER_"))
      || (name.startsWith("AGENTOPS_POSTGRES_"))
      || (name.startsWith("AGENTOPS_HUMAN_SESSION_"))
    ) {
      fail("broker_environment_contains_credentials_or_runtime_config");
    }
  }
}

export function loadConfiguration(environment = process.env) {
  assertCredentialFreeEnvironment(environment);
  const publicSocketPath = requiredAbsolutePath(
    environment.AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_PATH,
    DEFAULT_PUBLIC_SOCKET,
    "broker_public_socket",
  );
  const privateSocketPath = requiredAbsolutePath(
    environment.AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_PATH,
    DEFAULT_PRIVATE_SOCKET,
    "broker_private_socket",
  );
  if (publicSocketPath === privateSocketPath || dirname(publicSocketPath) === dirname(privateSocketPath)) {
    fail("broker_public_private_socket_separation_required");
  }
  const publicSocketDirectoryMode = integerValue(
    environment.AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_DIRECTORY_MODE,
    0o750,
    0o700,
    0o750,
    "broker_public_socket_directory_mode",
  );
  if (![0o700, 0o750].includes(publicSocketDirectoryMode)) {
    fail("broker_public_socket_directory_mode_invalid");
  }
  return {
    publicSocketPath,
    privateSocketPath,
    publicSocketGid: integerValue(
      environment.AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_GID,
      DEFAULT_PUBLIC_GID,
      0,
      2 ** 31 - 1,
      "broker_public_socket_gid",
    ),
    publicSocketDirectoryMode,
    privateSocketGid: integerValue(
      environment.AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_GID,
      DEFAULT_PRIVATE_GID,
      0,
      2 ** 31 - 1,
      "broker_private_socket_gid",
    ),
    privateSocketUid: integerValue(
      environment.AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_UID,
      0,
      0,
      2 ** 31 - 1,
      "broker_private_socket_uid",
    ),
    requestTimeoutMs: integerValue(
      environment.AGENTOPS_OPENCLAW_BROKER_REQUEST_TIMEOUT_MS,
      DEFAULT_REQUEST_TIMEOUT_MS,
      1_000,
      300_000,
      "broker_request_timeout_ms",
    ),
    bodyTimeoutMs: integerValue(
      environment.AGENTOPS_OPENCLAW_BROKER_BODY_TIMEOUT_MS,
      DEFAULT_BODY_TIMEOUT_MS,
      250,
      30_000,
      "broker_body_timeout_ms",
    ),
  };
}

function fileIdentity(metadata) {
  return {
    dev: String(metadata.dev),
    ino: String(metadata.ino),
    uid: metadata.uid,
    gid: metadata.gid,
    mode: metadata.mode & 0o777,
  };
}

function sameIdentity(left, right) {
  return left.dev === right.dev
    && left.ino === right.ino
    && left.uid === right.uid
    && left.gid === right.gid
    && left.mode === right.mode;
}

function validatePublicRequest(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value).sort();
  if (
    keys.length !== REQUEST_FIELDS.length
    || keys.some((key, index) => key !== REQUEST_FIELDS[index])
    || value.schema !== REQUEST_SCHEMA
    || typeof value.agent_name !== "string"
    || !SAFE_IDENTIFIER.test(value.agent_name)
    || typeof value.prompt !== "string"
    || !value.prompt.trim()
    || value.prompt.includes("\u0000")
    || Buffer.byteLength(value.prompt, "utf8") > MAX_REQUEST_BYTES - 1024
    || typeof value.prompt_hash !== "string"
    || !SHA256_HEX.test(value.prompt_hash)
    || createHash("sha256").update(value.prompt, "utf8").digest("hex") !== value.prompt_hash
    || !Number.isInteger(value.timeout_seconds)
    || value.timeout_seconds < 1
    || value.timeout_seconds > 600
  ) {
    return false;
  }
  return true;
}

function inspectDirectory(path, expectedUid, expectedGid, expectedMode, label) {
  let metadata;
  try {
    metadata = lstatSync(path, { bigint: false });
  } catch {
    fail(`${label}_directory_unavailable`);
  }
  if (
    !metadata.isDirectory()
    || metadata.isSymbolicLink()
    || metadata.uid !== expectedUid
    || metadata.gid !== expectedGid
    || (metadata.mode & 0o777) !== expectedMode
  ) {
    fail(`${label}_directory_permissions_invalid`);
  }
  return fileIdentity(metadata);
}

function inspectPrivateSocket(configuration, expectedIdentity = null) {
  inspectDirectory(
    dirname(configuration.privateSocketPath),
    configuration.privateSocketUid,
    configuration.privateSocketGid,
    0o750,
    "broker_private_socket",
  );
  let metadata;
  try {
    metadata = lstatSync(configuration.privateSocketPath, { bigint: false });
  } catch {
    fail("broker_private_socket_unavailable");
  }
  if (
    !metadata.isSocket()
    || metadata.isSymbolicLink()
    || metadata.uid !== configuration.privateSocketUid
    || metadata.gid !== configuration.privateSocketGid
    || (metadata.mode & 0o777) !== 0o660
  ) {
    fail("broker_private_socket_permissions_invalid");
  }
  const identity = fileIdentity(metadata);
  if (expectedIdentity && !sameIdentity(identity, expectedIdentity)) {
    fail("broker_private_socket_identity_changed");
  }
  return identity;
}

function socketIsLive(socketPath) {
  return new Promise((resolveLive) => {
    const socket = createConnection({ path: socketPath });
    let settled = false;
    const finish = (live) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolveLive(live);
    };
    socket.setTimeout(250, () => finish(true));
    socket.once("connect", () => finish(true));
    socket.once("error", (error) => {
      finish(!["ECONNREFUSED", "ENOENT"].includes(error?.code));
    });
  });
}

async function preparePublicSocket(configuration) {
  inspectDirectory(
    dirname(configuration.publicSocketPath),
    process.getuid(),
    configuration.publicSocketGid,
    configuration.publicSocketDirectoryMode,
    "broker_public_socket",
  );
  try {
    const existing = lstatSync(configuration.publicSocketPath);
    if (!existing.isSocket()) fail("broker_public_socket_path_not_socket");
    if (await socketIsLive(configuration.publicSocketPath)) fail("broker_public_socket_in_use");
    unlinkSync(configuration.publicSocketPath);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

function writeJson(response, status, payload) {
  if (response.destroyed || response.writableEnded) return;
  const body = Buffer.from(`${JSON.stringify(payload)}\n`, "utf8");
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": body.byteLength,
    "Cache-Control": "no-store",
    Connection: "close",
  });
  response.end(body);
}

function boundaryError(response, status, error) {
  writeJson(response, status, {
    schema: ERROR_SCHEMA,
    error,
    raw_prompt_omitted: true,
    raw_response_omitted: true,
  });
}

function readBoundedJson(request, response, timeoutMs) {
  return new Promise((resolveBody, rejectBody) => {
    const contentLength = String(request.headers["content-length"] || "");
    if (!/^(?:0|[1-9][0-9]*)$/.test(contentLength)) {
      request.resume();
      boundaryError(response, 411, "ContentLengthRequired");
      resolveBody(null);
      return;
    }
    const declared = Number(contentLength);
    if (!Number.isSafeInteger(declared) || declared > MAX_REQUEST_BYTES) {
      request.resume();
      boundaryError(response, 413, "RequestBodyTooLarge");
      resolveBody(null);
      return;
    }
    if (request.headers["transfer-encoding"] !== undefined) {
      request.resume();
      boundaryError(response, 400, "TransferEncodingUnsupported");
      resolveBody(null);
      return;
    }
    const chunks = [];
    let size = 0;
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      request.destroy();
      rejectBody(new Error("request_body_timeout"));
    }, timeoutMs);
    timer.unref();
    const finish = (callback) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      callback();
    };
    request.on("data", (chunk) => {
      size += chunk.byteLength;
      if (size > declared || size > MAX_REQUEST_BYTES) {
        finish(() => rejectBody(new Error("request_body_length_mismatch")));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.once("aborted", () => finish(() => rejectBody(new Error("request_aborted"))));
    request.once("error", (error) => finish(() => rejectBody(error)));
    request.once("end", () => finish(() => {
      if (size !== declared) {
        rejectBody(new Error("request_body_length_mismatch"));
        return;
      }
      const raw = Buffer.concat(chunks);
      try {
        const value = JSON.parse(raw.toString("utf8"));
        if (!validatePublicRequest(value)) {
          boundaryError(response, 400, "RequestValidationFailed");
          resolveBody(null);
          return;
        }
        resolveBody(raw);
      } catch {
        boundaryError(response, 400, "RequestJsonInvalid");
        resolveBody(null);
      }
    }));
  });
}

function forwardToPrivate(configuration, privateIdentity, body, publicResponse) {
  let upstream;
  let completed = false;
  const result = new Promise((resolveResult, rejectResult) => {
    inspectPrivateSocket(configuration, privateIdentity);
    upstream = httpRequest({
      socketPath: configuration.privateSocketPath,
      method: "POST",
      path: "/v1/execute",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": body.byteLength,
        Connection: "close",
      },
      agent: false,
    }, (privateResponse) => {
      const responseStatus = privateResponse.statusCode;
      const declaredHeader = privateResponse.headers["content-length"];
      const declared = declaredHeader === undefined ? null : Number(declaredHeader);
      if (
        !Number.isInteger(responseStatus)
        || responseStatus < 100
        || responseStatus > 599
        || (declared !== null && (!Number.isSafeInteger(declared) || declared < 0 || declared > MAX_RESPONSE_BYTES))
        || !/^application\/json(?:\s*;|$)/i.test(String(privateResponse.headers["content-type"] || ""))
      ) {
        privateResponse.destroy();
        rejectResult(new Error("private_response_boundary_invalid"));
        return;
      }
      const chunks = [];
      let size = 0;
      privateResponse.on("data", (chunk) => {
        size += chunk.byteLength;
        if (size > MAX_RESPONSE_BYTES) {
          privateResponse.destroy(new Error("private_response_too_large"));
          return;
        }
        chunks.push(chunk);
      });
      privateResponse.once("aborted", () => rejectResult(new Error("private_response_aborted")));
      privateResponse.once("error", rejectResult);
      privateResponse.once("end", () => {
        if (declared !== null && size !== declared) {
          rejectResult(new Error("private_response_length_mismatch"));
          return;
        }
        const raw = Buffer.concat(chunks);
        try {
          const value = JSON.parse(raw.toString("utf8"));
          if (!value || typeof value !== "object" || Array.isArray(value)) {
            rejectResult(new Error("private_response_json_object_required"));
            return;
          }
        } catch {
          rejectResult(new Error("private_response_json_invalid"));
          return;
        }
        completed = true;
        resolveResult({
          status: responseStatus,
          body: raw,
        });
      });
    });
    upstream.setTimeout(configuration.requestTimeoutMs, () => {
      upstream.destroy(new Error("private_request_timeout"));
    });
    upstream.once("error", rejectResult);
    upstream.end(body);
  });
  const cancel = () => {
    if (!completed && upstream && !upstream.destroyed) {
      upstream.destroy(new Error("public_client_disconnected"));
      return true;
    }
    return false;
  };
  publicResponse.once("close", cancel);
  return {
    result: result.finally(() => publicResponse.off("close", cancel)),
    cancel,
  };
}

function writePrivateResponse(publicResponse, forwarded) {
  if (publicResponse.destroyed || publicResponse.writableEnded) return;
  publicResponse.writeHead(forwarded.status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": forwarded.body.byteLength,
    "Cache-Control": "no-store",
    Connection: "close",
  });
  publicResponse.end(forwarded.body);
}

export async function startBrokerService(configuration = loadConfiguration()) {
  await preparePublicSocket(configuration);
  const privateIdentity = inspectPrivateSocket(configuration);
  const state = {
    activeRequest: null,
    executeRequestsReceived: 0,
    shuttingDown: false,
  };
  const sockets = new Set();
  const server = createServer(async (request, response) => {
    if (request.method === "GET" && request.url === "/health") {
      request.resume();
      let privateSocketIdentityVerified = false;
      try {
        inspectPrivateSocket(configuration, privateIdentity);
        privateSocketIdentityVerified = true;
      } catch {
        privateSocketIdentityVerified = false;
      }
      const ready = !state.shuttingDown && privateSocketIdentityVerified;
      writeJson(response, ready ? 200 : 503, {
        schema: HEALTH_SCHEMA,
        ok: ready,
        ready,
        busy: state.activeRequest !== null,
        execute_requests_received: state.executeRequestsReceived,
        a03_mount_path_separation_only: true,
        public_private_socket_paths_distinct: true,
        private_socket_identity_verified: privateSocketIdentityVerified,
        so_peercred_verified: false,
        full_hostile_runtime_isolation_verified: false,
      });
      return;
    }
    if (request.method !== "POST" || request.url !== "/v1/execute") {
      request.resume();
      boundaryError(response, 404, "RouteNotFound");
      return;
    }
    state.executeRequestsReceived += 1;
    if (state.shuttingDown || state.activeRequest) {
      request.resume();
      boundaryError(response, 503, "BrokerBusy");
      return;
    }
    const slot = { request, response, forward: null };
    state.activeRequest = slot;
    try {
      if (!/^application\/json(?:\s*;|$)/i.test(String(request.headers["content-type"] || ""))) {
        request.resume();
        boundaryError(response, 415, "ContentTypeUnsupported");
        return;
      }
      let body;
      try {
        body = await readBoundedJson(request, response, configuration.bodyTimeoutMs);
      } catch {
        if (!response.headersSent && !response.destroyed) boundaryError(response, 400, "RequestReadFailed");
        return;
      }
      if (body === null || response.headersSent || response.destroyed) return;
      try {
        slot.forward = forwardToPrivate(configuration, privateIdentity, body, response);
        const forwarded = await slot.forward.result;
        writePrivateResponse(response, forwarded);
      } catch {
        if (!response.headersSent && !response.destroyed) boundaryError(response, 502, "PrivateExecutorUnavailable");
      }
    } finally {
      if (state.activeRequest === slot) state.activeRequest = null;
    }
  });
  server.requestTimeout = configuration.requestTimeoutMs + configuration.bodyTimeoutMs + 1_000;
  server.headersTimeout = configuration.bodyTimeoutMs;
  server.keepAliveTimeout = 1_000;
  server.maxRequestsPerSocket = 1;
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
  });
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
    server.listen(configuration.publicSocketPath, () => {
      server.off("error", rejectListen);
      resolveListen();
    });
  });
  chmodSync(configuration.publicSocketPath, 0o660);
  chownSync(configuration.publicSocketPath, process.getuid(), configuration.publicSocketGid);
  const publicSocket = lstatSync(configuration.publicSocketPath);
  if (
    !publicSocket.isSocket()
    || publicSocket.uid !== process.getuid()
    || publicSocket.gid !== configuration.publicSocketGid
    || (publicSocket.mode & 0o777) !== 0o660
  ) {
    fail("broker_public_socket_permissions_invalid");
  }

  let shutdownPromise = null;
  const shutdown = () => {
    if (shutdownPromise) {
      state.activeRequest?.forward?.cancel();
      for (const socket of sockets) socket.destroy();
      return shutdownPromise;
    }
    state.shuttingDown = true;
    shutdownPromise = (async () => {
      const closed = new Promise((resolveClosed) => server.close(resolveClosed));
      state.activeRequest?.forward?.cancel();
      if (state.activeRequest && !state.activeRequest.forward) {
        state.activeRequest.request.destroy();
        state.activeRequest.response.destroy();
      }
      for (const socket of sockets) socket.destroy();
      await closed;
      try {
        unlinkSync(configuration.publicSocketPath);
      } catch (error) {
        if (error?.code !== "ENOENT") {
          process.exitCode = 1;
          return false;
        }
      }
      return true;
    })();
    return shutdownPromise;
  };

  return { server, state, shutdown, configuration };
}

async function main() {
  try {
    const service = await startBrokerService();
    let handlingSignal = false;
    for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
      process.on(signal, async () => {
        if (handlingSignal) {
          service.shutdown();
          return;
        }
        handlingSignal = true;
        await service.shutdown();
      });
    }
  } catch (error) {
    process.stderr.write(`${error?.code || "broker_start_failed"}\n`);
    process.exitCode = 78;
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  await main();
}
