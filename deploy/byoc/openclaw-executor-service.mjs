#!/usr/bin/env node

import { createHash, createPrivateKey, createPublicKey } from "node:crypto";
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
import { createServer } from "node:http";
import { dirname, isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { inspectDelegatedCgroupRoot, validateOpenClawCgroupPolicy } from "./openclaw-cgroup-v2.mjs";
import { readLinuxBootClock } from "./openclaw-executor-protocol.mjs";
import { ExecutorReplayJournal } from "./openclaw-executor-request.mjs";
import { runExecutorDispatch } from "./openclaw-executor-runner.mjs";
import {
  parseCanonicalRuntimeManifestEnvelope,
  runtimeManifestSha256,
  verifyCanonicalRuntimeManifestAndTree,
} from "./openclaw-runtime-manifest.mjs";

export const EXECUTOR_HEALTH_SCHEMA = "agentops_openclaw_executor_health_v1";
const MAX_CONFIG_BYTES = 1024 * 1024;
const MAX_EXECUTE_BYTES = 1024 * 1024;
const EXECUTE_BODY_TIMEOUT_MS = 5_000;
const IMAGE_DIGEST = /^sha256:[a-f0-9]{64}$/;
const IMAGE_REFERENCE = /^([a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*){1,7})@(sha256:[a-f0-9]{64})$/;
const SHA256 = /^[a-f0-9]{64}$/;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const OCI_IMAGE_NAME = /^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:\/[a-z0-9]+(?:[._-][a-z0-9]+)*){1,7}$/;

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function absolute(value, label) {
  const path = String(value || "");
  if (!path || !isAbsolute(path) || resolve(path) !== path) fail(`${label}_absolute_path_required`);
  return path;
}

function token(value, label) {
  const candidate = String(value || "");
  if (!TOKEN.test(candidate)) fail(`${label}_invalid`);
  return candidate;
}

function fixedInteger(value, expected, label) {
  const candidate = Number(value);
  if (!Number.isSafeInteger(candidate) || candidate !== expected) fail(`${label}_invalid`);
  return candidate;
}

export function loadExecutorConfiguration(environment = process.env) {
  const imageReference = String(environment.OPENCLAW_EXECUTOR_IMAGE_REFERENCE || "");
  const imageReferenceMatch = IMAGE_REFERENCE.exec(imageReference);
  if (!imageReferenceMatch) fail("executor_image_reference_invalid");
  return Object.freeze({
    socketPath: absolute(environment.OPENCLAW_EXECUTOR_SOCKET, "executor_socket"),
    socketGid: fixedInteger(environment.OPENCLAW_EXECUTOR_SOCKET_GID, 2200, "executor_socket_gid"),
    journalRoot: absolute(environment.OPENCLAW_EXECUTOR_JOURNAL_ROOT, "executor_journal_root"),
    launcherPath: absolute(environment.OPENCLAW_EXECUTOR_LAUNCHER, "executor_launcher"),
    cgroupRoot: absolute(environment.OPENCLAW_CGROUP_ROOT, "executor_cgroup_root"),
    cgroupPolicyPath: absolute(environment.OPENCLAW_CGROUP_POLICY_PATH, "executor_cgroup_policy"),
    seccompProfilePath: absolute(environment.OPENCLAW_SECCOMP_PROFILE_PATH, "executor_seccomp_profile"),
    manifestPath: absolute(environment.OPENCLAW_RUNTIME_MANIFEST_PATH, "executor_runtime_manifest"),
    manifestTrustRootPath: absolute(
      environment.OPENCLAW_RUNTIME_MANIFEST_TRUST_ROOT_PATH,
      "executor_runtime_manifest_trust_root",
    ),
    manifestIssuer: token(environment.OPENCLAW_RUNTIME_MANIFEST_ISSUER, "executor_manifest_issuer"),
    manifestKeyId: token(environment.OPENCLAW_RUNTIME_MANIFEST_KEY_ID, "executor_manifest_key_id"),
    receiptSigningKeyPath: absolute(
      environment.OPENCLAW_RECEIPT_SIGNING_KEY_PATH,
      "executor_receipt_signing_key",
    ),
    receiptKeyId: token(environment.OPENCLAW_RECEIPT_KEY_ID, "executor_receipt_key_id"),
    executorImageReference: imageReference,
    executorImageDigest: imageReferenceMatch[2],
    runtimeImageDigest: (() => {
      const value = String(environment.OPENCLAW_RUNTIME_IMAGE_DIGEST || "");
      if (!IMAGE_DIGEST.test(value)) fail("executor_runtime_image_digest_invalid");
      return value;
    })(),
    runtimeImageName: (() => {
      const value = String(environment.OPENCLAW_RUNTIME_IMAGE_NAME || "");
      if (value.length > 255 || !OCI_IMAGE_NAME.test(value)) fail("executor_runtime_image_name_invalid");
      return value;
    })(),
    runtimeRoot: absolute(environment.OPENCLAW_RUNTIME_ROOT, "executor_runtime_root"),
    runtimeUid: fixedInteger(environment.OPENCLAW_RUNTIME_UID, 1200, "executor_runtime_uid"),
    runtimeGid: fixedInteger(environment.OPENCLAW_RUNTIME_GID, 1200, "executor_runtime_gid"),
    providerEgressOperatorAttested: (() => {
      const value = String(environment.OPENCLAW_EXTERNAL_PROVIDER_EGRESS_ATTESTED || "");
      if (value !== "true") fail("executor_provider_egress_operator_attestation_required");
      return true;
    })(),
  });
}

function readSecureFile(path, { maximum = MAX_CONFIG_BYTES, privateMode = false } = {}) {
  const before = lstatSync(path);
  if (
    !before.isFile()
    || before.isSymbolicLink()
    || before.nlink !== 1
    || before.uid !== 0
    || (before.mode & 0o022) !== 0
    || (privateMode && (before.mode & 0o777) !== 0o400)
    || before.size < 2
    || before.size > maximum
  ) fail("executor_input_file_metadata_invalid");
  const descriptor = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  try {
    const opened = fstatSync(descriptor);
    if (opened.dev !== before.dev || opened.ino !== before.ino) fail("executor_input_file_identity_changed");
    const bytes = readFileSync(descriptor);
    const after = lstatSync(path);
    if (after.dev !== before.dev || after.ino !== before.ino || after.size !== before.size) {
      fail("executor_input_file_identity_changed");
    }
    return bytes;
  } finally {
    closeSync(descriptor);
  }
}

export function inspectExecutorLauncher(path, { expectedUid = 0, expectedGid = 0 } = {}) {
  const metadata = lstatSync(path);
  if (
    !metadata.isFile()
    || metadata.isSymbolicLink()
    || metadata.nlink !== 1
    || metadata.uid !== expectedUid
    || metadata.gid !== expectedGid
    || (metadata.mode & 0o7777) !== 0o555
  ) fail("executor_launcher_metadata_invalid");
  return Object.freeze({ dev: metadata.dev, ino: metadata.ino });
}

function exactObject(value, fields, code) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(code);
  const actual = Object.keys(value).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((name, index) => name !== expected[index])) fail(code);
  return value;
}

function parseCanonicalJson(bytes, code) {
  let value;
  try {
    value = JSON.parse(new TextDecoder("utf8", { fatal: true }).decode(bytes));
  } catch {
    fail(code);
  }
  if (!Buffer.from(JSON.stringify(value), "utf8").equals(bytes)) fail(`${code}_noncanonical`);
  return value;
}

export function parseRuntimeManifestTrustRoots(bytes) {
  const value = exactObject(
    parseCanonicalJson(bytes, "executor_manifest_trust_roots_invalid"),
    ["keys", "schema"],
    "executor_manifest_trust_roots_invalid",
  );
  if (value.schema !== "agentops_openclaw_runtime_manifest_trust_roots_v1") {
    fail("executor_manifest_trust_roots_schema_invalid");
  }
  const keys = exactObject(value.keys, Object.keys(value.keys || {}), "executor_manifest_trust_roots_invalid");
  const entries = Object.entries(keys);
  if (entries.length < 1 || entries.length > 8) fail("executor_manifest_trust_roots_count_invalid");
  const parsedEntries = [];
  for (const [keyId, publicKeyPem] of entries) {
    token(keyId, "executor_manifest_trust_root_key_id");
    if (
      typeof publicKeyPem !== "string"
      || publicKeyPem.length > 4096
      || !/^-----BEGIN PUBLIC KEY-----\n[A-Za-z0-9+/=\n]+-----END PUBLIC KEY-----\n?$/.test(publicKeyPem)
    ) fail("executor_manifest_trust_root_key_invalid");
    let publicKey;
    try {
      publicKey = createPublicKey(publicKeyPem);
    } catch {
      fail("executor_manifest_trust_root_key_invalid");
    }
    if (publicKey.type !== "public" || publicKey.asymmetricKeyType !== "ed25519") {
      fail("executor_manifest_trust_root_key_invalid");
    }
    parsedEntries.push([keyId, publicKey]);
  }
  return new Map(parsedEntries);
}

export async function preflightExecutor(configuration, {
  expectedOwner = { uid: 0, gid: 2200 },
  inspectCgroup = inspectDelegatedCgroupRoot,
} = {}) {
  inspectExecutorLauncher(configuration.launcherPath);
  const policyBytes = readSecureFile(configuration.cgroupPolicyPath);
  const policy = validateOpenClawCgroupPolicy(parseCanonicalJson(policyBytes, "executor_cgroup_policy_invalid"));
  const policySha256 = createHash("sha256").update(policyBytes).digest("hex");
  const seccompBytes = readSecureFile(configuration.seccompProfilePath);
  const seccompSha256 = createHash("sha256").update(seccompBytes).digest("hex");
  const manifestBytes = readSecureFile(configuration.manifestPath);
  const roots = parseRuntimeManifestTrustRoots(readSecureFile(configuration.manifestTrustRootPath));
  const envelope = parseCanonicalRuntimeManifestEnvelope(manifestBytes);
  const manifest = await verifyCanonicalRuntimeManifestAndTree(
    manifestBytes,
    configuration.runtimeRoot,
    roots,
    {
      cgroup_policy_sha256: policySha256,
      entrypoint: envelope.body.entrypoint,
      issuer: configuration.manifestIssuer,
      key_id: configuration.manifestKeyId,
      oci_image_digest: configuration.runtimeImageDigest,
      oci_image_name: configuration.runtimeImageName,
      runtime_executable: envelope.body.runtime_executable,
      runtime_gid: configuration.runtimeGid,
      runtime_uid: configuration.runtimeUid,
      seccomp_profile_sha256: seccompSha256,
      verification_time: new Date().toISOString(),
    },
  );
  const receiptKeyBytes = readSecureFile(configuration.receiptSigningKeyPath, { maximum: 16 * 1024, privateMode: true });
  let receiptKey;
  try {
    receiptKey = createPrivateKey(receiptKeyBytes);
  } catch {
    fail("executor_receipt_private_key_invalid");
  }
  if (receiptKey.asymmetricKeyType !== "ed25519") fail("executor_receipt_private_key_invalid");
  const delegation = inspectCgroup({ root: configuration.cgroupRoot });
  const journal = await ExecutorReplayJournal.open(configuration.journalRoot, { expectedOwner });
  const clock = readLinuxBootClock();
  const recovery = await journal.recover(clock);
  return Object.freeze({
    clock,
    delegation,
    journal,
    manifest: manifest.body,
    manifestSha256: runtimeManifestSha256(manifestBytes),
    policy,
    policySha256,
    receiptKey,
    recovery,
    seccompSha256,
  });
}

function writeJson(response, status, value) {
  const bytes = Buffer.from(`${JSON.stringify(value)}\n`, "utf8");
  response.writeHead(status, {
    "content-type": "application/json",
    "content-length": bytes.byteLength,
    "cache-control": "no-store",
    connection: "close",
  });
  response.end(bytes);
}

function writeBytes(response, status, bytes) {
  if (response.destroyed || response.writableEnded) return;
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": bytes.byteLength,
    "cache-control": "no-store",
    connection: "close",
  });
  response.end(bytes);
}

function readExecuteBody(request, response) {
  return new Promise((resolveBody) => {
    const length = String(request.headers["content-length"] || "");
    if (length && (!/^(?:0|[1-9][0-9]*)$/.test(length) || BigInt(length) > BigInt(MAX_EXECUTE_BYTES))) {
      request.resume();
      writeJson(response, 413, { schema: "agentops_openclaw_executor_error_v1", error: "RequestTooLarge" });
      resolveBody(null);
      return;
    }
    const chunks = [];
    let size = 0;
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveBody(value);
    };
    const timer = setTimeout(() => {
      request.destroy();
      if (!response.headersSent && !response.destroyed) {
        writeJson(response, 408, { schema: "agentops_openclaw_executor_error_v1", error: "RequestTimeout" });
      }
      finish(null);
    }, EXECUTE_BODY_TIMEOUT_MS);
    request.on("data", (chunk) => {
      size += chunk.byteLength;
      if (size > MAX_EXECUTE_BYTES) {
        request.resume();
        writeJson(response, 413, { schema: "agentops_openclaw_executor_error_v1", error: "RequestTooLarge" });
        finish(null);
        return;
      }
      chunks.push(Buffer.from(chunk));
    });
    request.once("aborted", () => finish(null));
    request.once("error", () => finish(null));
    request.once("end", () => finish(Buffer.concat(chunks)));
  });
}

async function startExecutorServiceWithDependencies(configuration, preflight, dependencies) {
  const runDispatch = dependencies.runDispatch || runExecutorDispatch;
  const socketOwner = dependencies.socketOwner || { uid: 0, gid: 2200 };
  if (typeof runDispatch !== "function") fail("executor_runner_invalid");
  if (!Number.isSafeInteger(socketOwner.uid) || !Number.isSafeInteger(socketOwner.gid)) {
    fail("executor_socket_owner_invalid");
  }
  const parent = lstatSync(dirname(configuration.socketPath));
  if (
    !parent.isDirectory()
    || parent.uid !== socketOwner.uid
    || parent.gid !== socketOwner.gid
    || (parent.mode & 0o777) !== 0o700
  ) {
    fail("executor_socket_directory_invalid");
  }
  try {
    unlinkSync(configuration.socketPath);
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  const state = {
    activeRequest: null,
    executeRequestsReceived: 0,
    runtimeProcessSpawned: false,
    shuttingDown: false,
  };
  const server = createServer(async (request, response) => {
    if (request.method === "GET" && request.url === "/health") {
      request.resume();
      const ready = !state.shuttingDown;
      writeJson(response, ready ? 200 : 503, {
        schema: EXECUTOR_HEALTH_SCHEMA,
        ok: ready,
        ready,
        busy: state.activeRequest !== null,
        execute_requests_received: state.executeRequestsReceived,
        manifest_tree_verified_at_startup: true,
        cgroup_delegation_verified_at_startup: true,
        replay_recovery_completed: true,
        provider_egress_operator_attested: configuration.providerEgressOperatorAttested,
        runtime_process_spawned: state.runtimeProcessSpawned,
        runtime_receipt_verified: false,
        hostile_runtime_isolation_verified: false,
      });
      return;
    }
    if (request.method === "POST" && request.url === "/v1/execute") {
      state.executeRequestsReceived += 1;
      if (state.shuttingDown || state.activeRequest !== null) {
        request.resume();
        writeJson(response, 503, { schema: "agentops_openclaw_executor_error_v1", error: "ExecutorBusy" });
        return;
      }
      if (!/^application\/json(?:\s*;|$)/i.test(String(request.headers["content-type"] || ""))) {
        request.resume();
        writeJson(response, 415, { schema: "agentops_openclaw_executor_error_v1", error: "ContentTypeUnsupported" });
        return;
      }
      const slot = { request, response };
      state.activeRequest = slot;
      try {
        const body = await readExecuteBody(request, response);
        if (body === null || response.headersSent || response.destroyed) return;
        try {
          const result = await runDispatch(body, configuration, preflight);
          if (!Buffer.isBuffer(result?.private_response_bytes)) {
            writeJson(response, 502, {
              schema: "agentops_openclaw_executor_error_v1",
              error: "ExecutorRunFailed",
              raw_prompt_omitted: true,
              raw_response_omitted: true,
            });
            return;
          }
          state.runtimeProcessSpawned = true;
          writeBytes(response, 200, result.private_response_bytes);
        } catch {
          writeJson(response, 502, {
            schema: "agentops_openclaw_executor_error_v1",
            error: "ExecutorRunFailed",
            raw_prompt_omitted: true,
            raw_response_omitted: true,
          });
        }
      } finally {
        if (state.activeRequest === slot) state.activeRequest = null;
      }
      return;
    }
    request.resume();
    writeJson(response, 404, { schema: "agentops_openclaw_executor_error_v1", error: "RouteNotFound" });
  });
  await new Promise((resolveListen, rejectListen) => {
    server.once("error", rejectListen);
    server.listen(configuration.socketPath, () => {
      server.off("error", rejectListen);
      resolveListen();
    });
  });
  chmodSync(configuration.socketPath, 0o660);
  chownSync(configuration.socketPath, socketOwner.uid, socketOwner.gid);
  let shutdownPromise = null;
  const shutdown = () => {
    if (shutdownPromise) return shutdownPromise;
    state.shuttingDown = true;
    shutdownPromise = new Promise((resolveShutdown) => {
      server.close(() => {
        try { unlinkSync(configuration.socketPath); } catch (error) {
          if (error?.code !== "ENOENT") throw error;
        }
        resolveShutdown(true);
      });
    });
    return shutdownPromise;
  };
  return { server, preflight, state, shutdown };
}

export async function startExecutorService(configuration, preflight) {
  return startExecutorServiceWithDependencies(configuration, preflight, {});
}

export async function startExecutorServiceForTest(configuration, preflight, dependencies) {
  if (process.env.NODE_ENV !== "test") fail("executor_test_dependencies_forbidden");
  return startExecutorServiceWithDependencies(configuration, preflight, dependencies);
}

async function main() {
  if (process.env.NODE_ENV !== "production") fail("executor_production_mode_required");
  if (process.getuid?.() !== 0 || process.getgid?.() !== 2200) fail("executor_root_identity_required");
  const configuration = loadExecutorConfiguration();
  const preflight = await preflightExecutor(configuration);
  const service = await startExecutorService(configuration, preflight);
  const shutdown = () => service.shutdown().then(() => process.exit(0));
  process.once("SIGTERM", shutdown);
  process.once("SIGINT", shutdown);
  process.once("SIGHUP", shutdown);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${typeof error?.code === "string" ? error.code : "executor_start_failed"}\n`);
    process.exitCode = 1;
  });
}
