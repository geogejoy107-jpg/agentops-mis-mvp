#!/usr/bin/env node

import assert from "node:assert/strict";
import {
  chmodSync,
  existsSync,
  linkSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { request } from "node:http";
import { generateKeyPairSync } from "node:crypto";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  inspectExecutorLauncher,
  loadExecutorConfiguration,
  parseRuntimeManifestTrustRoots,
  startExecutorServiceForTest,
} from "./openclaw-executor-service.mjs";

const digest = (character) => character.repeat(64);
const environment = {
  OPENCLAW_EXECUTOR_SOCKET: "/run/test/executor.sock",
  OPENCLAW_EXECUTOR_SOCKET_GID: "2200",
  OPENCLAW_EXECUTOR_JOURNAL_ROOT: "/var/lib/test/replay",
  OPENCLAW_EXECUTOR_LAUNCHER: "/usr/local/bin/launcher",
  OPENCLAW_CGROUP_ROOT: "/sys/fs/cgroup/agentops-openclaw-executor",
  OPENCLAW_CGROUP_POLICY_PATH: "/run/policy/cgroup.json",
  OPENCLAW_SECCOMP_PROFILE_PATH: "/run/policy/seccomp.json",
  OPENCLAW_RUNTIME_MANIFEST_PATH: "/run/manifest/runtime.json",
  OPENCLAW_RUNTIME_MANIFEST_TRUST_ROOT_PATH: "/run/manifest/roots.json",
  OPENCLAW_RUNTIME_MANIFEST_ISSUER: "agentops-release",
  OPENCLAW_RUNTIME_MANIFEST_KEY_ID: "manifest-key-1",
  OPENCLAW_RECEIPT_SIGNING_KEY_PATH: "/run/secret/receipt-key",
  OPENCLAW_RECEIPT_KEY_ID: "receipt-key-1",
  OPENCLAW_EXECUTOR_IMAGE_REFERENCE: `registry.invalid/agentops/a07@sha256:${digest("1")}`,
  OPENCLAW_RUNTIME_IMAGE_DIGEST: `sha256:${digest("2")}`,
  OPENCLAW_RUNTIME_IMAGE_NAME: "registry.invalid/openclaw-runtime",
  OPENCLAW_RUNTIME_ROOT: "/opt/openclaw",
  OPENCLAW_RUNTIME_UID: "1200",
  OPENCLAW_RUNTIME_GID: "1200",
  OPENCLAW_EXTERNAL_PROVIDER_EGRESS_ATTESTED: "true",
};
const configuration = loadExecutorConfiguration(environment);
assert.equal(configuration.runtimeUid, 1200);
assert.equal(configuration.runtimeGid, 1200);
assert.equal(configuration.providerEgressOperatorAttested, true);
assert.equal(configuration.executorImageDigest, `sha256:${digest("1")}`);
const manifestKeyId = "manifest-key-contract";
const manifestKeys = generateKeyPairSync("ed25519");
const manifestTrustRootBytes = (pem) => Buffer.from(JSON.stringify({
  keys: { [manifestKeyId]: pem },
  schema: "agentops_openclaw_runtime_manifest_trust_roots_v1",
}), "utf8");
const parsedManifestRoots = parseRuntimeManifestTrustRoots(manifestTrustRootBytes(
  manifestKeys.publicKey.export({ type: "spki", format: "pem" }),
));
assert.equal(parsedManifestRoots.get(manifestKeyId)?.asymmetricKeyType, "ed25519");
assert.throws(
  () => parseRuntimeManifestTrustRoots(manifestTrustRootBytes(
    manifestKeys.privateKey.export({ type: "pkcs8", format: "pem" }),
  )),
  /executor_manifest_trust_root_key_invalid/,
);
for (const [name, value] of [
  ["OPENCLAW_RUNTIME_UID", "1001"],
  ["OPENCLAW_EXECUTOR_SOCKET_GID", "0"],
  ["OPENCLAW_EXECUTOR_IMAGE_REFERENCE", `registry.invalid/agentops/a07:mutable@sha256:${digest("1")}`],
  ["OPENCLAW_EXECUTOR_SOCKET", "relative.sock"],
  ["OPENCLAW_EXTERNAL_PROVIDER_EGRESS_ATTESTED", "false"],
]) {
  assert.throws(() => loadExecutorConfiguration({ ...environment, [name]: value }), /executor_/);
}
const launcherRoot = mkdtempSync(path.join(os.tmpdir(), "agentops-executor-launcher-"));
try {
  const launcherPath = path.join(launcherRoot, "launcher");
  const launcherLinkPath = path.join(launcherRoot, "launcher-link");
  const launcherSymlinkPath = path.join(launcherRoot, "launcher-symlink");
  writeFileSync(launcherPath, "contract launcher\n", { mode: 0o555 });
  chmodSync(launcherPath, 0o555);
  const metadata = lstatSync(launcherPath);
  assert.deepEqual(
    inspectExecutorLauncher(launcherPath, { expectedUid: metadata.uid, expectedGid: metadata.gid }),
    { dev: metadata.dev, ino: metadata.ino },
  );
  chmodSync(launcherPath, 0o755);
  assert.throws(
    () => inspectExecutorLauncher(launcherPath, { expectedUid: metadata.uid, expectedGid: metadata.gid }),
    /executor_launcher_metadata_invalid/,
  );
  chmodSync(launcherPath, 0o555);
  linkSync(launcherPath, launcherLinkPath);
  assert.throws(
    () => inspectExecutorLauncher(launcherPath, { expectedUid: metadata.uid, expectedGid: metadata.gid }),
    /executor_launcher_metadata_invalid/,
  );
  rmSync(launcherLinkPath);
  symlinkSync(launcherPath, launcherSymlinkPath);
  assert.throws(
    () => inspectExecutorLauncher(launcherSymlinkPath, { expectedUid: metadata.uid, expectedGid: metadata.gid }),
    /executor_launcher_metadata_invalid/,
  );
} finally {
  rmSync(launcherRoot, { recursive: true, force: true });
}
const source = readFileSync(fileURLToPath(new URL("./openclaw-executor-service.mjs", import.meta.url)), "utf8");
assert.match(source, /verifyCanonicalRuntimeManifestAndTree/);
assert.match(source, /inspectDelegatedCgroupRoot/);
assert.match(source, /ExecutorReplayJournal\.open/);
assert.match(source, /runExecutorDispatch/);
assert.match(source, /const ready = !state\.shuttingDown/);
assert.match(source, /ExecutorBusy/);
assert.match(source, /MAX_EXECUTE_BYTES/);
assert.match(source, /runtime_receipt_verified: false/);
assert.doesNotMatch(source, /runtime_receipt_verified: true/);

const serviceRoot = mkdtempSync(path.join(os.tmpdir(), "agentops-executor-service-contract-"));
const socketRoot = path.join(serviceRoot, "socket");
const socketPath = path.join(socketRoot, "executor.sock");
const uid = process.getuid();
const gid = process.getgid();
mkdirSync(socketRoot, { mode: 0o700 });
chmodSync(socketRoot, 0o700);
let mode = "success";
let runCalls = 0;
let releaseSlow = null;
const privateResponseBytes = Buffer.from('{"schema":"agentops_openclaw_executor_private_response_v2"}', "utf8");
const runDispatch = async () => {
  runCalls += 1;
  if (mode === "slow") {
    await new Promise((resolveSlow) => { releaseSlow = resolveSlow; });
  }
  if (mode === "failed") return { provider_response: null };
  return { private_response_bytes: privateResponseBytes };
};

function callService({ method = "POST", body = Buffer.from("{}"), headers = {} } = {}) {
  return new Promise((resolveCall, rejectCall) => {
    const client = request({
      socketPath,
      method,
      path: method === "GET" ? "/health" : "/v1/execute",
      headers: method === "POST" ? {
        "content-type": "application/json",
        "content-length": body.byteLength,
        ...headers,
      } : headers,
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.once("error", rejectCall);
      response.once("end", () => {
        const bytes = Buffer.concat(chunks);
        let parsed = null;
        try { parsed = JSON.parse(bytes.toString("utf8")); } catch {}
        resolveCall({ status: response.statusCode, bytes, body: parsed });
      });
    });
    client.once("error", rejectCall);
    client.end(method === "POST" ? body : undefined);
  });
}

let service = null;
try {
  await assert.rejects(
    () => startExecutorServiceForTest(
      { ...configuration, socketPath, socketGid: gid },
      Object.freeze({ contract: true }),
      { runDispatch, socketOwner: { uid, gid } },
    ),
    /executor_test_dependencies_forbidden/,
  );
  const previousNodeEnvironment = process.env.NODE_ENV;
  process.env.NODE_ENV = "test";
  service = await startExecutorServiceForTest(
    { ...configuration, socketPath, socketGid: gid },
    Object.freeze({ contract: true }),
    { runDispatch, socketOwner: { uid, gid } },
  );
  if (previousNodeEnvironment === undefined) delete process.env.NODE_ENV;
  else process.env.NODE_ENV = previousNodeEnvironment;
  const socket = lstatSync(socketPath);
  assert.equal(socket.isSocket(), true);
  assert.equal(socket.uid, uid);
  assert.equal(socket.gid, gid);
  assert.equal(socket.mode & 0o777, 0o660);

  const health = await callService({ method: "GET", body: Buffer.alloc(0) });
  assert.equal(health.status, 200);
  assert.equal(health.body.ready, true);
  assert.equal(health.body.busy, false);
  assert.equal(health.body.runtime_process_spawned, false);
  assert.equal(health.body.runtime_receipt_verified, false);

  const success = await callService();
  assert.equal(success.status, 200);
  assert.deepEqual(success.bytes, privateResponseBytes);
  const healthAfterSuccess = await callService({ method: "GET", body: Buffer.alloc(0) });
  assert.equal(healthAfterSuccess.body.runtime_process_spawned, true);

  mode = "failed";
  const failed = await callService();
  assert.equal(failed.status, 502);
  assert.equal(failed.body.error, "ExecutorRunFailed");
  assert.equal(failed.body.raw_prompt_omitted, true);
  assert.equal(failed.body.raw_response_omitted, true);

  mode = "slow";
  const slow = callService();
  while (releaseSlow === null) await new Promise((resolveWait) => setTimeout(resolveWait, 5));
  const busy = await callService();
  assert.equal(busy.status, 503);
  assert.equal(busy.body.error, "ExecutorBusy");
  releaseSlow();
  await slow;
  mode = "success";

  const oversized = await callService({
    body: Buffer.alloc(0),
    headers: { "content-length": String(1024 * 1024 + 1) },
  });
  assert.equal(oversized.status, 413);
  assert.equal(oversized.body.error, "RequestTooLarge");
  assert.equal(runCalls, 3);
} finally {
  if (service) await service.shutdown();
  assert.equal(existsSync(socketPath), false);
  rmSync(serviceRoot, { recursive: true, force: true });
}
console.log(JSON.stringify({
  contract: "agentops_openclaw_root_executor_service_integration_a07_v1",
  strict_configuration_verified: true,
  immutable_executor_image_reference_bound: true,
  root_owned_single_link_launcher_metadata_required: true,
  signed_manifest_and_exact_tree_preflight_present: true,
  cgroup_delegation_preflight_present: true,
  crash_recovery_preflight_present: true,
  bounded_execute_body_verified: true,
  execute_route_runner_integration_verified: true,
  single_flight_verified: true,
  failure_response_redacted: true,
  socket_shutdown_cleanup_verified: true,
  health_ready: true,
  injected_runner_success_state_transition_verified: true,
  real_runtime_process_spawned: false,
  runtime_receipt_verified: false,
  hostile_runtime_isolation_verified: false,
}));
