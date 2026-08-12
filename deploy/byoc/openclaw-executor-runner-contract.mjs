#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash, generateKeyPairSync } from "node:crypto";
import { EventEmitter } from "node:events";
import { readFileSync } from "node:fs";
import { PassThrough } from "node:stream";
import { fileURLToPath } from "node:url";
import {
  buildExecutorDispatch,
  canonicalExecutorProtocolBytes,
} from "./openclaw-executor-protocol.mjs";
import { verifyCanonicalExecutorReceipt } from "./openclaw-executor-receipt.mjs";
import {
  runExecutorDispatchForTest,
  waitForExecutorChildForTest,
} from "./openclaw-executor-runner.mjs";

const digest = (character) => character.repeat(64);
const bootId = "12345678-1234-4123-8123-123456789abc";
const rawPrompt = "runner contract raw prompt must never persist";
const rawResponse = "runner contract raw response must never persist";
const signing = generateKeyPairSync("ed25519");
const manifestSha256 = digest("1");
const policySha256 = digest("2");
const seccompSha256 = digest("3");
const previousNodeEnvironment = process.env.NODE_ENV;
process.env.NODE_ENV = "test";
const runnerSource = readFileSync(fileURLToPath(new URL("./openclaw-executor-runner.mjs", import.meta.url)), "utf8");

assert.match(runnerSource, /constants\.O_DIRECTORY \| constants\.O_NOFOLLOW \| constants\.O_CLOEXEC/);
assert.match(runnerSource, /return \{ execFd, rootFd, cgroupFd \}/);
assert.match(runnerSource, /const argv = assertPromptTransport\(preflight\.manifest\);/);
assert.match(runnerSource, /"--root-fd", "4"/);
assert.match(runnerSource, /handles\.execFd, handles\.rootFd, handles\.cgroupFd, "pipe"/);
assert.match(runnerSource, /child\.stdio\?\.\[6\]/);
assert.match(runnerSource, /handles\?\.execFd, handles\?\.rootFd, handles\?\.cgroupFd/);

function providerResponse(overrides = {}) {
  return {
    dry_run: false,
    duration_ms: 25,
    error_message: null,
    error_type: null,
    model_name: "contract-agent",
    ok: true,
    output_present: true,
    output_tokens: 0,
    provider_call_performed: true,
    raw_payload_hash: digest("4"),
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    retryable: false,
    schema: "agentops_openclaw_provider_response_v1",
    ...overrides,
  };
}

function dispatch(requestId, nonce = `nonce-${requestId}`) {
  return buildExecutorDispatch({
    agent_name: "contract-agent",
    nonce,
    prompt: rawPrompt,
    prompt_sha256: awaitDigest(rawPrompt),
    request_id: requestId,
    run_id: `run-${requestId}`,
    schema: "agentops_openclaw_executor_public_request_v2",
    timeout_seconds: 2,
    workspace_id_hash: digest("5"),
  }, {
    bootClock: { boot_id: bootId, now_boottime_ns: "1000000000" },
    isolationPolicySha256: policySha256,
    runtimeManifestSha256: manifestSha256,
  });
}

function awaitDigest(value) {
  return createHash("sha256").update(value).digest("hex");
}

class FakeJournal {
  constructor({ crashAt = null } = {}) {
    this.records = new Map();
    this.events = [];
    this.persisted = [];
    this.crashAt = crashAt;
  }
  async reserve(bytes, clock) {
    const body = JSON.parse(bytes);
    if (this.records.has(body.request_id) || [...this.records.values()].some((item) => item.body.nonce === body.nonce)) {
      throw new Error("executor_journal_request_replayed");
    }
    const record = { body, state: "prepared", state_version: 1 };
    this.records.set(body.request_id, record);
    this.persisted.push(canonicalExecutorProtocolBytes({ body, clock }));
    this.events.push("prepared");
    return record;
  }
  async markDispatched(requestId) {
    const record = this.records.get(requestId);
    if (record.state !== "prepared") throw new Error("executor_journal_not_executable");
    record.state = "dispatched";
    record.state_version += 1;
    this.events.push("dispatched");
    if (this.crashAt === "after-dispatch") throw new Error("injected_crash_after_dispatch");
    return record;
  }
  async read(requestId) { return this.records.get(requestId); }
  async toUncertain(record) {
    record.state = "uncertain";
    record.state_version += 1;
    this.events.push("uncertain");
    return record;
  }
  async markTerminal(requestId, _clock, outcome) {
    const record = this.records.get(requestId);
    if (record.state !== "dispatched") throw new Error("executor_journal_transition_invalid");
    record.state = "terminal";
    record.outcome = outcome;
    record.state_version += 1;
    this.events.push(`terminal:${outcome}`);
    return record;
  }
}

function fixture({ outcome = "success", journal = new FakeJournal(), manifest = {} } = {}) {
  let now = 1_100_000_000n;
  let spawnCalls = 0;
  let stdinSeen = null;
  let killed = 0;
  const configuration = {
    executorImageDigest: `sha256:${digest("6")}`,
    launcherPath: "/contract/launcher",
    receiptKeyId: "executor-contract-key",
    runtimeImageDigest: `sha256:${digest("7")}`,
    runtimeRoot: "/contract/runtime",
  };
  const preflight = {
    delegation: { schema: "agentops_openclaw_cgroup_v2" },
    journal,
    manifest: {
      argv_template: [
        "/usr/bin/node",
        "/app/stdin-provider.mjs",
        "--stdin-protocol=canonical_provider_request_stdin_v1",
      ],
      environment_name_allowlist: [],
      runtime_executable: "/usr/bin/node",
      ...manifest,
    },
    manifestSha256,
    policy: {
      cpuMax: "50000 100000",
      ioMax: "8:0 rbps=1048576 wbps=1048576",
      memoryMax: "536870912",
      pidsMax: "64",
    },
    policySha256,
    receiptKey: signing.privateKey,
    seccompSha256,
  };
  const dependencies = {
    clock: () => ({ boot_id: bootId, now_boottime_ns: (now += 100_000_000n).toString() }),
    launcherIdentity: () => ({ binary_sha256: digest("8"), device: "41", inode: "8001" }),
    createCgroup: async (_delegation, requestId, policy) => ({
      cgroupId: `cg-${requestId}`,
      device: "41",
      inode: "9001",
      path: "/contract/cgroup/request",
      policy,
      rootDevice: "41",
      rootInode: "7001",
    }),
    openExecutionFiles: async () => ({ execFd: 31, cgroupFd: 32 }),
    closeFd: () => {},
    spawnLauncher: async (_configuration, _preflight, _handles, stdinBytes) => {
      spawnCalls += 1;
      stdinSeen = Buffer.from(stdinBytes);
      if (outcome === "spawn-fail") throw new Error("spawn_failed");
      return { pid: 4242 };
    },
    waitForChild: async () => {
      if (outcome === "timeout") {
        now = 3_100_000_000n;
        return { code: null, pid: 4242, signal: "SIGKILL", spawned: true, stdout: Buffer.alloc(0), timedOut: true };
      }
      if (outcome === "tampered") {
        const bytes = canonicalExecutorProtocolBytes(providerResponse());
        bytes[bytes.length - 2] ^= 1;
        return { code: 0, launcherStatus: "R", pid: 4242, signal: null, spawned: true, stdout: bytes, timedOut: false };
      }
      return {
        code: 0,
        launcherStatus: outcome === "forged-milestone" ? "RE" : outcome === "missing-milestone" ? "" : "R",
        pid: 4242,
        signal: null,
        spawned: true,
        stdout: canonicalExecutorProtocolBytes(providerResponse()),
        timedOut: false,
      };
    },
    killAndRemoveCgroup: async () => {
      killed += 1;
      return { cgroupId: "cg-contract", descendantsCleanupVerified: true };
    },
  };
  return {
    configuration,
    dependencies,
    journal,
    preflight,
    observations: () => ({ killed, spawnCalls, stdinSeen }),
  };
}

const successFixture = fixture();
const successDispatch = dispatch("req-success");
const successBytes = canonicalExecutorProtocolBytes(successDispatch);
const success = await runExecutorDispatchForTest(successBytes, successFixture.configuration, successFixture.preflight, successFixture.dependencies);
assert.deepEqual(successFixture.journal.events, ["prepared", "dispatched", "terminal:completed"]);
assert.equal(successFixture.observations().spawnCalls, 1);
assert.equal(successFixture.observations().killed, 1);
assert.deepEqual(successFixture.observations().stdinSeen, canonicalExecutorProtocolBytes(successDispatch.provider_request));
const privateResponse = JSON.parse(success.private_response_bytes);
assert.equal(privateResponse.provider_response.ok, true);
assert.equal(privateResponse.receipt.body.provider_call_verified, false);
assert.equal(privateResponse.receipt.body.hostile_runtime_isolation_verified, false);
assert.equal(privateResponse.receipt.body.process.spawned, true);
assert.equal(privateResponse.receipt.body.descendants_cleanup_verified, true);
const expected = {
  agent_name: "contract-agent",
  boot_id: bootId,
  cgroup: privateResponse.receipt.body.cgroup,
  deadline_boottime_ns: successDispatch.request.deadline_boottime_ns,
  executor_image_digest: successFixture.configuration.executorImageDigest,
  executor_key_id: successFixture.configuration.receiptKeyId,
  isolation_policy_sha256: policySha256,
  launcher: privateResponse.receipt.body.launcher,
  nonce: successDispatch.request.nonce,
  private_dispatch_schema: successDispatch.schema,
  private_dispatch_sha256: awaitDigest(successBytes),
  prompt_sha256: successDispatch.request.prompt_sha256,
  provider_request_sha256: awaitDigest(canonicalExecutorProtocolBytes(successDispatch.provider_request)),
  public_request_schema: "agentops_openclaw_executor_public_request_v2",
  public_request_sha256: privateResponse.receipt.body.public_request_sha256,
  request_id: successDispatch.request.request_id,
  run_id: successDispatch.request.run_id,
  runtime_image_digest: successFixture.configuration.runtimeImageDigest,
  runtime_manifest_sha256: manifestSha256,
  seccomp_profile_sha256: seccompSha256,
  verification_boottime_ns: "2500000000",
  workspace_id_hash: successDispatch.request.workspace_id_hash,
};
verifyCanonicalExecutorReceipt(success.receipt_bytes, new Map([[successFixture.configuration.receiptKeyId, signing.publicKey]]), expected, new Set());

await assert.rejects(
  () => runExecutorDispatchForTest(successBytes, successFixture.configuration, successFixture.preflight, successFixture.dependencies),
  /executor_journal_request_replayed/,
);
assert.equal(successFixture.observations().spawnCalls, 1);

for (const outcome of ["timeout", "spawn-fail", "missing-milestone", "forged-milestone"]) {
  const current = fixture({ outcome });
  const bytes = canonicalExecutorProtocolBytes(dispatch(`req-${outcome}`));
  await assert.rejects(
    () => runExecutorDispatchForTest(bytes, current.configuration, current.preflight, current.dependencies),
    /executor_runner_completion_unverified/,
  );
  assert.equal(current.journal.records.get(`req-${outcome}`).state, "uncertain");
  assert.equal(current.observations().killed, 1);
}

const tampered = fixture({ outcome: "tampered" });
await assert.rejects(
  () => runExecutorDispatchForTest(
    canonicalExecutorProtocolBytes(dispatch("req-tampered")),
    tampered.configuration,
    tampered.preflight,
    tampered.dependencies,
  ),
  /executor_runner_provider_response_(json_invalid|fields_invalid|invalid|noncanonical)/,
);
assert.equal(tampered.journal.records.get("req-tampered").state, "uncertain");
assert.equal(tampered.observations().killed, 1);

const crashJournal = new FakeJournal({ crashAt: "after-dispatch" });
const crash = fixture({ journal: crashJournal });
const crashBytes = canonicalExecutorProtocolBytes(dispatch("req-crash"));
await assert.rejects(
  () => runExecutorDispatchForTest(crashBytes, crash.configuration, crash.preflight, crash.dependencies),
  /injected_crash_after_dispatch/,
);
assert.equal(crashJournal.records.get("req-crash").state, "uncertain");
assert.equal(crash.observations().spawnCalls, 0);
await assert.rejects(
  () => runExecutorDispatchForTest(crashBytes, crash.configuration, crash.preflight, crash.dependencies),
  /executor_journal_request_replayed/,
);
assert.equal(crash.observations().spawnCalls, 0);

for (const unsafeManifest of [
  { argv_template: ["/usr/bin/openclaw", "--message", rawPrompt] },
  { argv_template: ["/usr/bin/node", "/app/stdin-provider.mjs"] },
]) {
  const denied = fixture({ manifest: unsafeManifest });
  await assert.rejects(
    () => runExecutorDispatchForTest(canonicalExecutorProtocolBytes(dispatch(`req-denied-${Math.random()}`)), denied.configuration, denied.preflight, denied.dependencies),
    /executor_runner_(prompt_argv_forbidden|provider_stdin_protocol_unsupported)/,
  );
  assert.equal(denied.journal.events.length, 0);
  assert.equal(denied.observations().spawnCalls, 0);
}

for (const current of [successFixture, crash]) {
  const persisted = Buffer.concat(current.journal.persisted).toString("utf8");
  assert.equal(persisted.includes(rawPrompt), false);
  assert.equal(persisted.includes(rawResponse), false);
}
const wire = Buffer.concat([success.private_response_bytes, success.receipt_bytes]).toString("utf8");
assert.equal(wire.includes(rawPrompt), false);
assert.equal(wire.includes(rawResponse), false);

function hangingChild() {
  const child = new EventEmitter();
  child.pid = 2_147_483_647;
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.stdio = [null, child.stdout, child.stderr, null, null, new PassThrough()];
  queueMicrotask(() => child.emit("spawn"));
  return child;
}

const deadlineChild = hangingChild();
const deadlineResult = await Promise.race([
  waitForExecutorChildForTest(
    deadlineChild,
    "100",
    () => ({ boot_id: bootId, now_boottime_ns: "100" }),
  ),
  new Promise((_, reject) => setTimeout(() => reject(new Error("deadline_wait_unbounded")), 250)),
]);
assert.equal(deadlineResult.timedOut, true);
assert.equal(deadlineResult.spawned, true);

const abortController = new AbortController();
const abortChild = hangingChild();
const abortResultPromise = waitForExecutorChildForTest(
  abortChild,
  "1000000000",
  () => ({ boot_id: bootId, now_boottime_ns: "0" }),
  abortController.signal,
);
queueMicrotask(() => abortController.abort());
const abortResult = await Promise.race([
  abortResultPromise,
  new Promise((_, reject) => setTimeout(() => reject(new Error("abort_wait_unbounded")), 250)),
]);
assert.equal(abortResult.aborted, true);
assert.equal(abortResult.spawned, true);

const overflowChild = hangingChild();
const overflowPromise = waitForExecutorChildForTest(
  overflowChild,
  "1000000000",
  () => ({ boot_id: bootId, now_boottime_ns: "0" }),
  undefined,
  4,
);
queueMicrotask(() => overflowChild.stdout.write("12345"));
const overflowResult = await Promise.race([
  overflowPromise,
  new Promise((_, reject) => setTimeout(() => reject(new Error("overflow_wait_unbounded")), 250)),
]);
assert.equal(overflowResult.outputTooLarge, true);
assert.equal(overflowResult.spawned, true);

const preAborted = fixture();
const preAbortController = new AbortController();
preAbortController.abort();
await assert.rejects(
  () => runExecutorDispatchForTest(
    canonicalExecutorProtocolBytes(dispatch("req-pre-aborted")),
    preAborted.configuration,
    preAborted.preflight,
    preAborted.dependencies,
    { signal: preAbortController.signal },
  ),
  /executor_runner_aborted/,
);
assert.equal(preAborted.journal.events.length, 0);
assert.equal(preAborted.observations().spawnCalls, 0);

delete process.env.NODE_ENV;
await assert.rejects(
  () => runExecutorDispatchForTest(
    successBytes,
    successFixture.configuration,
    successFixture.preflight,
    successFixture.dependencies,
  ),
  /executor_runner_test_dependencies_forbidden/,
);
if (previousNodeEnvironment !== undefined) process.env.NODE_ENV = previousNodeEnvironment;

process.stdout.write(`${JSON.stringify({
  schema: "agentops_openclaw_executor_runner_contract_v1",
  success_and_tamper_covered: true,
  timeout_and_spawn_failure_marked_uncertain_without_receipt: true,
  missing_and_forged_launcher_milestones_rejected_without_receipt: true,
  timeout_abort_and_output_overflow_return_before_pipe_close: true,
  cancellation_before_reservation_omits_dispatch: true,
  replay_and_crash_window_no_double_dispatch: true,
  prompt_stdin_only_and_argv_fails_closed: true,
  raw_prompt_and_response_not_persisted: true,
  canonical_signed_executor_receipt_verified: true,
  guest_root_fd_handoff_source_audited: true,
  real_linux_cgroupfs_acceptance_performed: false,
  real_runtime_process_spawned: false,
  provider_call_verified: false,
  hostile_runtime_isolation_verified: false,
})}\n`);
