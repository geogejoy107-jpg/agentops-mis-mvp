#!/usr/bin/env node

import {
  chmodSync,
  chownSync,
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
  unlinkSync,
} from "node:fs";
import { createHash, createPublicKey } from "node:crypto";
import { createServer, request as httpRequest } from "node:http";
import { createConnection } from "node:net";
import { dirname, isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import {
  buildExecutorDispatch,
  canonicalExecutorProtocolBytes,
  EXECUTOR_PUBLIC_REQUEST_SCHEMA,
  EXECUTOR_PRIVATE_RESPONSE_SCHEMA,
  readLinuxBootClock,
  validateExecutorPublicRequest,
} from "./openclaw-executor-protocol.mjs";
import {
  parseCanonicalExecutorReceiptEnvelope,
  verifyExecutorReceipt,
} from "./openclaw-executor-receipt.mjs";
import {
  RESPONSE_FIELDS as PROVIDER_RESPONSE_FIELDS,
  RESPONSE_SCHEMA as PROVIDER_RESPONSE_SCHEMA,
} from "./openclaw-provider-entrypoint.mjs";

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
const IMAGE_DIGEST = /^sha256:[a-f0-9]{64}$/;
const IMAGE_REFERENCE = /^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*){1,7}@(sha256:[a-f0-9]{64})$/;
const EXECUTOR_PRIVATE_RESPONSE_FIELDS = Object.freeze(["provider_response", "receipt", "schema"].sort());
const RECEIPT_TRUST_ROOT_SCHEMA = "agentops_openclaw_executor_receipt_trust_roots_v1";

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
  "AGENTOPS_OPENCLAW_BROKER_RUNTIME_MANIFEST_SHA256",
  "AGENTOPS_OPENCLAW_BROKER_ISOLATION_POLICY_SHA256",
  "AGENTOPS_OPENCLAW_BROKER_SECCOMP_PROFILE_SHA256",
  "AGENTOPS_OPENCLAW_BROKER_EXECUTOR_IMAGE_REFERENCE",
  "AGENTOPS_OPENCLAW_BROKER_RUNTIME_IMAGE_DIGEST",
  "AGENTOPS_OPENCLAW_BROKER_RECEIPT_KEY_ID",
  "AGENTOPS_OPENCLAW_RECEIPT_TRUST_ROOT_PATH",
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

function optionalDigest(value, label) {
  const candidate = String(value || "").trim().toLowerCase();
  if (candidate && !SHA256_HEX.test(candidate)) fail(`${label}_invalid`);
  return candidate || null;
}

function optionalAbsolutePath(value, label) {
  const candidate = String(value || "").trim();
  return candidate ? requiredAbsolutePath(candidate, "", label) : null;
}

function optionalToken(value, label) {
  const candidate = String(value || "").trim();
  if (candidate && !SAFE_IDENTIFIER.test(candidate)) fail(`${label}_invalid`);
  return candidate || null;
}

function optionalImageDigest(value, label) {
  const candidate = String(value || "").trim();
  if (candidate && !IMAGE_DIGEST.test(candidate)) fail(`${label}_invalid`);
  return candidate || null;
}

function optionalImageReference(value, label) {
  const candidate = String(value || "").trim();
  const match = candidate ? IMAGE_REFERENCE.exec(candidate) : null;
  if (candidate && !match) fail(`${label}_invalid`);
  return candidate ? { reference: candidate, digest: match[1] } : null;
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
  const executorImage = optionalImageReference(
    environment.AGENTOPS_OPENCLAW_BROKER_EXECUTOR_IMAGE_REFERENCE,
    "broker_executor_image_reference",
  );
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
    runtimeManifestSha256: optionalDigest(
      environment.AGENTOPS_OPENCLAW_BROKER_RUNTIME_MANIFEST_SHA256,
      "broker_runtime_manifest_sha256",
    ),
    isolationPolicySha256: optionalDigest(
      environment.AGENTOPS_OPENCLAW_BROKER_ISOLATION_POLICY_SHA256,
      "broker_isolation_policy_sha256",
    ),
    seccompProfileSha256: optionalDigest(
      environment.AGENTOPS_OPENCLAW_BROKER_SECCOMP_PROFILE_SHA256,
      "broker_seccomp_profile_sha256",
    ),
    executorImageReference: executorImage?.reference || null,
    executorImageDigest: executorImage?.digest || null,
    runtimeImageDigest: optionalImageDigest(
      environment.AGENTOPS_OPENCLAW_BROKER_RUNTIME_IMAGE_DIGEST,
      "broker_runtime_image_digest",
    ),
    receiptKeyId: optionalToken(
      environment.AGENTOPS_OPENCLAW_BROKER_RECEIPT_KEY_ID,
      "broker_receipt_key_id",
    ),
    receiptTrustRootPath: optionalAbsolutePath(
      environment.AGENTOPS_OPENCLAW_RECEIPT_TRUST_ROOT_PATH,
      "broker_receipt_trust_root",
    ),
  };
}

function exactFields(value, expected, code) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(code);
  const actual = Object.keys(value).sort();
  const fields = [...expected].sort();
  if (actual.length !== fields.length || actual.some((name, index) => name !== fields[index])) fail(code);
  return value;
}

export function loadExecutorReceiptTrustRoots(path, { expectedUid = 0 } = {}) {
  const before = lstatSync(path);
  if (
    !before.isFile()
    || before.isSymbolicLink()
    || before.nlink !== 1
    || before.uid !== expectedUid
    || (before.mode & 0o022) !== 0
    || before.size < 2
    || before.size > 64 * 1024
  ) fail("broker_receipt_trust_root_metadata_invalid");
  const descriptor = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  let bytes;
  try {
    const opened = fstatSync(descriptor);
    if (opened.dev !== before.dev || opened.ino !== before.ino) fail("broker_receipt_trust_root_identity_changed");
    bytes = readFileSync(descriptor);
    const afterDescriptor = fstatSync(descriptor);
    const afterPath = lstatSync(path);
    if (
      afterDescriptor.dev !== opened.dev
      || afterDescriptor.ino !== opened.ino
      || afterDescriptor.size !== opened.size
      || afterDescriptor.mtimeMs !== opened.mtimeMs
      || afterDescriptor.ctimeMs !== opened.ctimeMs
      || afterPath.dev !== opened.dev
      || afterPath.ino !== opened.ino
      || afterPath.size !== opened.size
    ) fail("broker_receipt_trust_root_identity_changed");
  } finally {
    closeSync(descriptor);
  }
  let value;
  try {
    value = JSON.parse(new TextDecoder("utf8", { fatal: true }).decode(bytes));
  } catch {
    fail("broker_receipt_trust_root_json_invalid");
  }
  exactFields(value, ["keys", "schema"], "broker_receipt_trust_root_fields_invalid");
  if (value.schema !== RECEIPT_TRUST_ROOT_SCHEMA) fail("broker_receipt_trust_root_schema_invalid");
  const keys = value.keys;
  if (!keys || typeof keys !== "object" || Array.isArray(keys)) fail("broker_receipt_trust_root_keys_invalid");
  const entries = Object.entries(keys);
  if (entries.length < 1 || entries.length > 8) fail("broker_receipt_trust_root_count_invalid");
  const parsedEntries = [];
  for (const [keyId, publicKeyPem] of entries) {
    if (
      !SAFE_IDENTIFIER.test(keyId)
      || typeof publicKeyPem !== "string"
      || publicKeyPem.length > 4096
      || !/^-----BEGIN PUBLIC KEY-----\n[A-Za-z0-9+/=\n]+-----END PUBLIC KEY-----\n?$/.test(publicKeyPem)
    ) {
      fail("broker_receipt_trust_root_key_invalid");
    }
    let publicKey;
    try {
      publicKey = createPublicKey(publicKeyPem);
    } catch {
      fail("broker_receipt_trust_root_key_invalid");
    }
    if (publicKey.type !== "public" || publicKey.asymmetricKeyType !== "ed25519") {
      fail("broker_receipt_trust_root_key_invalid");
    }
    parsedEntries.push([keyId, publicKey]);
  }
  if (!bytes.equals(canonicalExecutorProtocolBytes(value))) fail("broker_receipt_trust_root_encoding_noncanonical");
  return new Map(parsedEntries);
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
  if (value.schema === EXECUTOR_PUBLIC_REQUEST_SCHEMA) {
    try {
      validateExecutorPublicRequest(value);
      return true;
    } catch {
      return false;
    }
  }
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

export function privateRequestBytes(configuration, publicBytes, bootClock = null) {
  let value;
  try {
    value = JSON.parse(Buffer.from(publicBytes).toString("utf8"));
  } catch {
    fail("broker_public_request_json_invalid");
  }
  if (value?.schema !== EXECUTOR_PUBLIC_REQUEST_SCHEMA) return Buffer.from(publicBytes);
  requireV2ReceiptConfiguration(configuration);
  const dispatchClock = typeof bootClock === "function"
    ? bootClock()
    : (bootClock || readLinuxBootClock());
  const dispatch = buildExecutorDispatch(value, {
    bootClock: dispatchClock,
    isolationPolicySha256: configuration.isolationPolicySha256,
    runtimeManifestSha256: configuration.runtimeManifestSha256,
  });
  return canonicalExecutorProtocolBytes(dispatch);
}

function sha256Bytes(value) {
  return createHash("sha256").update(value).digest("hex");
}

function validateProviderResponse(value) {
  const response = exactFields(value, PROVIDER_RESPONSE_FIELDS, "broker_provider_response_fields_invalid");
  if (
    response.schema !== PROVIDER_RESPONSE_SCHEMA
    || typeof response.ok !== "boolean"
    || typeof response.provider_call_performed !== "boolean"
    || response.dry_run !== false
    || typeof response.output_present !== "boolean"
    || typeof response.retryable !== "boolean"
    || response.raw_prompt_omitted !== true
    || response.raw_response_omitted !== true
    || typeof response.raw_payload_hash !== "string"
    || !SHA256_HEX.test(response.raw_payload_hash)
  ) fail("broker_provider_response_invalid");
  return response;
}

function requireV2ReceiptConfiguration(configuration) {
  for (const [name, value] of [
    ["runtime_manifest_sha256", configuration.runtimeManifestSha256],
    ["isolation_policy_sha256", configuration.isolationPolicySha256],
    ["seccomp_profile_sha256", configuration.seccompProfileSha256],
    ["executor_image_digest", configuration.executorImageDigest],
    ["runtime_image_digest", configuration.runtimeImageDigest],
    ["receipt_key_id", configuration.receiptKeyId],
    ["receipt_trust_root_path", configuration.receiptTrustRootPath],
  ]) if (!value) fail(`broker_executor_v2_${name}_unavailable`);
}

export function verifyExecutorPrivateResponse(
  configuration,
  publicBytes,
  privateDispatchBytes,
  privateResponseBytes,
  trustRoots,
  replayCache,
  verificationClock = null,
) {
  requireV2ReceiptConfiguration(configuration);
  let publicRequest;
  let dispatch;
  let privateResponse;
  try {
    publicRequest = validateExecutorPublicRequest(JSON.parse(Buffer.from(publicBytes).toString("utf8")));
    dispatch = JSON.parse(Buffer.from(privateDispatchBytes).toString("utf8"));
    privateResponse = JSON.parse(Buffer.from(privateResponseBytes).toString("utf8"));
  } catch (error) {
    if (typeof error?.code === "string" && error.code.startsWith("executor_")) throw error;
    fail("broker_executor_v2_response_json_invalid");
  }
  exactFields(privateResponse, EXECUTOR_PRIVATE_RESPONSE_FIELDS, "broker_executor_v2_response_fields_invalid");
  if (privateResponse.schema !== EXECUTOR_PRIVATE_RESPONSE_SCHEMA) fail("broker_executor_v2_response_schema_invalid");
  if (!Buffer.from(privateResponseBytes).equals(canonicalExecutorProtocolBytes(privateResponse))) {
    fail("broker_executor_v2_response_encoding_noncanonical");
  }
  const providerResponse = validateProviderResponse(privateResponse.provider_response);
  const receiptBytes = canonicalExecutorProtocolBytes(privateResponse.receipt);
  const receipt = parseCanonicalExecutorReceiptEnvelope(receiptBytes);
  const clock = verificationClock || readLinuxBootClock();
  if (clock.boot_id !== dispatch.request?.boot_id) fail("broker_executor_v2_boot_id_changed");
  const providerRequestBytes = canonicalExecutorProtocolBytes(dispatch.provider_request);
  const expected = {
    agent_name: publicRequest.agent_name,
    boot_id: dispatch.request.boot_id,
    cgroup: receipt.body.cgroup,
    deadline_boottime_ns: dispatch.request.deadline_boottime_ns,
    executor_image_digest: configuration.executorImageDigest,
    executor_key_id: configuration.receiptKeyId,
    isolation_policy_sha256: configuration.isolationPolicySha256,
    launcher: receipt.body.launcher,
    nonce: publicRequest.nonce,
    private_dispatch_schema: dispatch.schema,
    private_dispatch_sha256: sha256Bytes(canonicalExecutorProtocolBytes(dispatch)),
    prompt_sha256: publicRequest.prompt_sha256,
    provider_request_sha256: sha256Bytes(providerRequestBytes),
    public_request_schema: publicRequest.schema,
    public_request_sha256: sha256Bytes(canonicalExecutorProtocolBytes(publicRequest)),
    request_id: publicRequest.request_id,
    run_id: publicRequest.run_id,
    runtime_image_digest: configuration.runtimeImageDigest,
    runtime_manifest_sha256: configuration.runtimeManifestSha256,
    seccomp_profile_sha256: configuration.seccompProfileSha256,
    verification_boottime_ns: clock.now_boottime_ns,
    workspace_id_hash: publicRequest.workspace_id_hash,
  };
  const stagedReplayCache = new Set(replayCache);
  const verified = verifyExecutorReceipt(receipt, trustRoots, expected, stagedReplayCache);
  const providerResponseSha256 = sha256Bytes(canonicalExecutorProtocolBytes(providerResponse));
  if (
    verified.provider.response_complete !== true
    || verified.provider.response_sha256 !== providerResponseSha256
    || verified.provider.call_observed !== providerResponse.provider_call_performed
  ) fail("broker_executor_v2_provider_response_binding_invalid");
  for (const key of stagedReplayCache) replayCache.add(key);
  return canonicalExecutorProtocolBytes(providerResponse);
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

export async function startBrokerService(configuration = loadConfiguration(), dependencies = {}) {
  const readBootClock = dependencies.readBootClock || readLinuxBootClock;
  if (typeof readBootClock !== "function") fail("broker_boot_clock_reader_invalid");
  await preparePublicSocket(configuration);
  const privateIdentity = inspectPrivateSocket(configuration);
  const receiptTrustRoots = dependencies.receiptTrustRoots === undefined
    ? (configuration.receiptTrustRootPath
      ? loadExecutorReceiptTrustRoots(configuration.receiptTrustRootPath)
      : null)
    : dependencies.receiptTrustRoots;
  if (receiptTrustRoots !== null && !(receiptTrustRoots instanceof Map)) {
    fail("broker_receipt_trust_roots_invalid");
  }
  const receiptReplayCache = new Set();
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
        executor_receipt_verification_configured: receiptTrustRoots !== null,
        runtime_receipt_verified: false,
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
        const publicRequest = JSON.parse(body.toString("utf8"));
        if (
          publicRequest.schema === EXECUTOR_PUBLIC_REQUEST_SCHEMA
          && (!receiptTrustRoots || !receiptTrustRoots.has(configuration.receiptKeyId))
        ) fail("broker_executor_v2_receipt_trust_root_unavailable");
        const privateBody = privateRequestBytes(configuration, body, readBootClock);
        slot.forward = forwardToPrivate(configuration, privateIdentity, privateBody, response);
        const forwarded = await slot.forward.result;
        if (publicRequest.schema === EXECUTOR_PUBLIC_REQUEST_SCHEMA) {
          forwarded.body = verifyExecutorPrivateResponse(
            configuration,
            body,
            privateBody,
            forwarded.body,
            receiptTrustRoots,
            receiptReplayCache,
            readBootClock(),
          );
        }
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
