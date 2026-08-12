#!/usr/bin/env node

import { createHash } from "node:crypto";
import {
  closeSync,
  constants,
  fstatSync,
  openSync,
  readFileSync,
} from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import {
  createRequestCgroup,
  killAndRemoveRequestCgroup,
} from "./openclaw-cgroup-v2.mjs";
import {
  canonicalExecutorProtocolBytes,
  EXECUTOR_PRIVATE_RESPONSE_SCHEMA,
  EXECUTOR_PUBLIC_REQUEST_SCHEMA,
  parseCanonicalExecutorDispatch,
  readLinuxBootClock,
} from "./openclaw-executor-protocol.mjs";
import {
  serializeExecutorReceiptEnvelope,
  signExecutorReceipt,
} from "./openclaw-executor-receipt.mjs";
import { canonicalExecutorRequestBytes } from "./openclaw-executor-request.mjs";

export const EXECUTOR_RUNNER_RESULT_SCHEMA = "agentops_openclaw_executor_runner_result_v1";
export const EXECUTOR_STDIN_PROTOCOL = "canonical_provider_request_stdin_v1";

const PROVIDER_RESPONSE_SCHEMA = "agentops_openclaw_provider_response_v1";
const PROVIDER_RESPONSE_FIELDS = Object.freeze([
  "dry_run", "duration_ms", "error_message", "error_type", "model_name", "ok",
  "output_present", "output_tokens", "provider_call_performed", "raw_payload_hash",
  "raw_prompt_omitted", "raw_response_omitted", "retryable", "schema",
].sort());
const SHA256 = /^[a-f0-9]{64}$/;
const ERROR_TYPE = /^[A-Za-z][A-Za-z0-9]{0,119}$/;
const MODEL_NAME = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$/;
const FIXED_PROVIDER_ERROR = "Provider error detail omitted; OpenClaw execution failed.";
const MAX_PROVIDER_RESPONSE_BYTES = 1024 * 1024;

function fail(code, cause) {
  const error = new Error(code, cause === undefined ? undefined : { cause });
  error.code = code;
  throw error;
}

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function exactFields(value, expected, code) {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail(code);
  const actual = Object.keys(value).sort();
  if (actual.length !== expected.length || actual.some((name, index) => name !== expected[index])) fail(code);
  return value;
}

function safeClock(clock) {
  if (
    !clock
    || typeof clock.boot_id !== "string"
    || typeof clock.now_boottime_ns !== "string"
    || !/^(?:0|[1-9][0-9]{0,19})$/.test(clock.now_boottime_ns)
  ) fail("executor_runner_clock_invalid");
  return clock;
}

function assertPreflight(configuration, preflight) {
  if (!configuration || !preflight) fail("executor_runner_preflight_required");
  for (const name of ["launcherPath", "runtimeRoot", "executorImageDigest", "runtimeImageDigest", "receiptKeyId"]) {
    if (!configuration[name]) fail(`executor_runner_configuration_${name}_required`);
  }
  for (const name of [
    "delegation", "journal", "manifest", "manifestSha256", "policy", "policySha256",
    "receiptKey", "seccompSha256",
  ]) if (!preflight[name]) fail(`executor_runner_preflight_${name}_required`);
  if (!SHA256.test(preflight.manifestSha256)) fail("executor_runner_manifest_digest_invalid");
}

function assertDispatchBindings(dispatch, preflight, clock) {
  if (dispatch.request.boot_id !== clock.boot_id) fail("executor_runner_boot_id_changed");
  if (dispatch.request.runtime_manifest_sha256 !== preflight.manifestSha256) {
    fail("executor_runner_manifest_binding_mismatch");
  }
  if (dispatch.request.isolation_policy_sha256 !== preflight.policySha256) {
    fail("executor_runner_policy_binding_mismatch");
  }
  if (BigInt(dispatch.request.deadline_boottime_ns) <= BigInt(clock.now_boottime_ns)) {
    fail("executor_runner_deadline_expired");
  }
}

function assertPromptTransport(manifest) {
  const argv = manifest.argv_template;
  if (!Array.isArray(argv) || argv.length < 2) fail("executor_runner_manifest_argv_invalid");
  if (argv.some((item) => typeof item !== "string")) fail("executor_runner_manifest_argv_invalid");
  const promptBearingFlags = new Set(["--message", "--prompt", "-m"]);
  if (argv.some((item) => promptBearingFlags.has(item) || /^--(?:message|prompt)=/u.test(item))) {
    fail("executor_runner_prompt_argv_forbidden");
  }
  if (!argv.includes(`--stdin-protocol=${EXECUTOR_STDIN_PROTOCOL}`)) {
    fail("executor_runner_provider_stdin_protocol_unsupported");
  }
  return argv;
}

function manifestAbsolutePath(runtimeRoot, virtualPath) {
  if (typeof virtualPath !== "string" || !virtualPath.startsWith("/")) {
    fail("executor_runner_runtime_path_invalid");
  }
  const relative = virtualPath.slice(1);
  const target = path.resolve(runtimeRoot, relative);
  if (target !== path.join(runtimeRoot, relative) || !target.startsWith(`${runtimeRoot}${path.sep}`)) {
    fail("executor_runner_runtime_path_escape");
  }
  return target;
}

function defaultOpenExecutionFiles(configuration, preflight, cgroup) {
  const executablePath = manifestAbsolutePath(configuration.runtimeRoot, preflight.manifest.runtime_executable);
  const execFd = openSync(
    executablePath,
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
  );
  let cgroupFd;
  try {
    const metadata = fstatSync(execFd);
    const relativePath = preflight.manifest.runtime_executable.slice(1);
    const expected = preflight.manifest.files?.find((item) => item.path === relativePath);
    if (
      !expected
      || !metadata.isFile()
      || metadata.nlink !== 1
      || metadata.uid !== expected.uid
      || metadata.gid !== expected.gid
      || (metadata.mode & 0o7777) !== expected.mode
      || metadata.size !== expected.size
      || digest(readFileSync(execFd)) !== expected.sha256
    ) fail("executor_runner_runtime_executable_manifest_mismatch");
    cgroupFd = openSync(
      path.join(cgroup.path, "cgroup.procs"),
      constants.O_WRONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
    );
  } catch (error) {
    closeSync(execFd);
    throw error;
  }
  return { execFd, cgroupFd };
}

function defaultLauncherIdentity(configuration) {
  const fd = openSync(configuration.launcherPath, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  try {
    const metadata = fstatSync(fd);
    return {
      binary_sha256: digest(readFileSync(fd)),
      device: String(metadata.dev),
      inode: String(metadata.ino),
    };
  } finally {
    closeSync(fd);
  }
}

function defaultSpawnLauncher(configuration, preflight, handles, stdinBytes) {
  const argv = assertPromptTransport(preflight.manifest).map((item, index) => (
    index > 0 && item.startsWith("/")
      ? manifestAbsolutePath(configuration.runtimeRoot, item)
      : item
  ));
  const child = spawn(configuration.launcherPath, [
    "--uid", "1200", "--gid", "1200",
    "--exec-fd", "3",
    "--cgroup-procs-fd", "4",
    "--", ...argv,
  ], {
    detached: true,
    env: { LANG: "C", PATH: "/usr/bin:/bin" },
    stdio: ["pipe", "pipe", "pipe", handles.execFd, handles.cgroupFd],
    windowsHide: true,
  });
  child.stdin.once("error", () => {});
  child.stdin.end(stdinBytes);
  return child;
}

function childResult(child, deadlineNs, clock, maximum = MAX_PROVIDER_RESPONSE_BYTES) {
  return new Promise((resolveResult) => {
    const stdout = [];
    let bytes = 0;
    let settled = false;
    let spawned = false;
    let timedOut = false;
    let timer;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolveResult(value);
    };
    child.once("spawn", () => { spawned = true; });
    child.once("error", (error) => finish({ spawned, spawnError: error }));
    child.stdout?.on("data", (chunk) => {
      bytes += chunk.byteLength;
      if (bytes <= maximum) stdout.push(Buffer.from(chunk));
      else {
        timedOut = false;
        try { process.kill(-child.pid, "SIGKILL"); } catch {}
      }
    });
    child.stderr?.resume();
    const remaining = BigInt(deadlineNs) - BigInt(clock().now_boottime_ns);
    const timeoutMs = Number(remaining > 0n ? (remaining + 999_999n) / 1_000_000n : 0n);
    timer = setTimeout(() => {
      timedOut = true;
      try { process.kill(-child.pid, "SIGKILL"); } catch {}
    }, Math.max(0, timeoutMs));
    timer.unref?.();
    child.once("close", (code, signal) => finish({
      code,
      signal,
      spawned,
      stdout: Buffer.concat(stdout),
      timedOut,
      outputTooLarge: bytes > maximum,
    }));
  });
}

function validateProviderResponseBytes(value) {
  const bytes = Buffer.from(value || []);
  if (bytes.length < 2 || bytes.length > MAX_PROVIDER_RESPONSE_BYTES) fail("executor_runner_provider_response_size_invalid");
  let response;
  try {
    response = JSON.parse(new TextDecoder("utf8", { fatal: true }).decode(bytes));
  } catch {
    fail("executor_runner_provider_response_json_invalid");
  }
  exactFields(response, PROVIDER_RESPONSE_FIELDS, "executor_runner_provider_response_fields_invalid");
  if (
    response.schema !== PROVIDER_RESPONSE_SCHEMA
    || typeof response.ok !== "boolean"
    || typeof response.provider_call_performed !== "boolean"
    || response.dry_run !== false
    || typeof response.output_present !== "boolean"
    || typeof response.retryable !== "boolean"
    || response.raw_prompt_omitted !== true
    || response.raw_response_omitted !== true
    || !MODEL_NAME.test(String(response.model_name || ""))
    || !SHA256.test(String(response.raw_payload_hash || ""))
    || !Number.isSafeInteger(response.duration_ms) || response.duration_ms < 0 || response.duration_ms > 86_400_000
    || !Number.isSafeInteger(response.output_tokens) || response.output_tokens < 0 || response.output_tokens > 10_000_000
    || (response.error_type !== null && !ERROR_TYPE.test(String(response.error_type)))
    || (response.error_message !== null && typeof response.error_message !== "string")
    || (response.ok && (!response.output_present || !response.provider_call_performed || response.retryable
      || response.error_type !== null || response.error_message !== null))
    || (!response.ok && (response.output_present || !response.error_type
      || response.error_message !== FIXED_PROVIDER_ERROR))
  ) fail("executor_runner_provider_response_invalid");
  const canonical = canonicalExecutorProtocolBytes(response);
  if (!bytes.equals(canonical)) fail("executor_runner_provider_response_noncanonical");
  return Object.freeze({ bytes: canonical, value: response });
}

function signalNumber(value) {
  if (value === null || value === undefined) return null;
  const table = { SIGHUP: 1, SIGINT: 2, SIGQUIT: 3, SIGKILL: 9, SIGTERM: 15 };
  return Number.isSafeInteger(value) ? value : table[value] ?? 9;
}

function receiptId(requestId, dispatchSha, finished) {
  return `exr-${digest(Buffer.from(`${requestId}:${dispatchSha}:${finished}`, "utf8")).slice(0, 32)}`;
}

function receiptBody({ configuration, preflight, dispatch, dispatchBytes, cgroup, launcher, result, response, started, finished, cleanup }) {
  const spawned = response !== null;
  const timedOut = result.timedOut === true;
  const signal = signalNumber(result.signal);
  let exitKind = "launch_failed";
  if (spawned && timedOut) exitKind = "timed_out";
  else if (spawned && signal !== null) exitKind = "signaled";
  else if (spawned && result.code === 0 && response) exitKind = "completed";
  else if (spawned) exitKind = "failed";
  const publicRequest = {
    agent_name: dispatch.provider_request.agent_name,
    nonce: dispatch.request.nonce,
    prompt: dispatch.provider_request.prompt,
    prompt_sha256: dispatch.request.prompt_sha256,
    request_id: dispatch.request.request_id,
    run_id: dispatch.request.run_id,
    schema: EXECUTOR_PUBLIC_REQUEST_SCHEMA,
    timeout_seconds: dispatch.provider_request.timeout_seconds,
    workspace_id_hash: dispatch.request.workspace_id_hash,
  };
  return {
    agent_name: dispatch.provider_request.agent_name,
    boot_id: dispatch.request.boot_id,
    cgroup: {
      cgroup_id: cgroup.cgroupId,
      device: cgroup.device,
      inode: cgroup.inode,
      limits: {
        cpu_max: cgroup.policy.cpuMax,
        io_max: cgroup.policy.ioMax,
        memory_max_bytes: cgroup.policy.memoryMax,
        memory_swap_max_bytes: "0",
        pids_max: cgroup.policy.pidsMax,
      },
      process_entry_verified: spawned,
      root_device: cgroup.rootDevice,
      root_inode: cgroup.rootInode,
    },
    deadline_boottime_ns: dispatch.request.deadline_boottime_ns,
    descendants_cleanup_verified: cleanup.descendantsCleanupVerified,
    executor_image_digest: configuration.executorImageDigest,
    executor_key_id: configuration.receiptKeyId,
    exit_code: spawned && signal === null && !timedOut
      ? (result.code === 0 && response === null ? 1 : (result.code ?? 1))
      : null,
    exit_kind: exitKind,
    finished_boottime_ns: finished,
    hostile_runtime_isolation_verified: false,
    isolation_policy_sha256: dispatch.request.isolation_policy_sha256,
    launcher: {
      ...launcher,
      invoked: spawned,
      no_new_privs_applied: spawned,
      runtime_gid: 1200,
      runtime_uid: 1200,
      seccomp_applied: spawned,
    },
    nonce: dispatch.request.nonce,
    private_dispatch_schema: dispatch.schema,
    private_dispatch_sha256: digest(dispatchBytes),
    process: { pid: spawned ? result.pid : null, spawned },
    prompt_sha256: dispatch.request.prompt_sha256,
    provider: {
      call_observed: response?.value.provider_call_performed === true,
      request_sha256: digest(canonicalExecutorProtocolBytes(dispatch.provider_request)),
      response_complete: response !== null,
      response_sha256: response === null ? null : digest(response.bytes),
    },
    provider_call_verified: false,
    public_request_schema: EXECUTOR_PUBLIC_REQUEST_SCHEMA,
    public_request_sha256: digest(canonicalExecutorProtocolBytes(publicRequest)),
    raw_prompt_omitted: true,
    raw_response_omitted: true,
    receipt_id: receiptId(dispatch.request.request_id, digest(dispatchBytes), finished),
    request_id: dispatch.request.request_id,
    run_id: dispatch.request.run_id,
    runtime_image_digest: configuration.runtimeImageDigest,
    runtime_manifest_sha256: dispatch.request.runtime_manifest_sha256,
    secrets_omitted: true,
    seccomp_profile_sha256: preflight.seccompSha256,
    started_boottime_ns: started,
    termination_signal: timedOut ? 9 : signal,
    timeout: { enforced: true, expired: timedOut },
    workspace_id_hash: dispatch.request.workspace_id_hash,
  };
}

function defaultDependencies() {
  return {
    clock: readLinuxBootClock,
    createCgroup: createRequestCgroup,
    killAndRemoveCgroup: killAndRemoveRequestCgroup,
    openExecutionFiles: defaultOpenExecutionFiles,
    spawnLauncher: defaultSpawnLauncher,
    waitForChild: (child, deadline, clock) => childResult(child, deadline, clock),
    launcherIdentity: defaultLauncherIdentity,
    closeFd: closeSync,
  };
}

async function runExecutorDispatchWithDependencies(dispatchBytesValue, configuration, preflight, injected) {
  assertPreflight(configuration, preflight);
  const dependencies = { ...defaultDependencies(), ...injected };
  const initialClock = safeClock(dependencies.clock());
  const dispatchBytes = Buffer.from(dispatchBytesValue);
  const dispatch = parseCanonicalExecutorDispatch(dispatchBytes, initialClock);
  assertDispatchBindings(dispatch, preflight, initialClock);
  assertPromptTransport(preflight.manifest);

  const journalRequestBytes = canonicalExecutorRequestBytes(dispatch.request);
  await preflight.journal.reserve(journalRequestBytes, initialClock);
  let cgroup = null;
  let handles = null;
  let reserved = true;
  let dispatched = false;
  let cleanup = null;
  let result = { spawned: false, spawnError: null };
  let response = null;
  let deferredError = null;
  let child = null;
  const started = initialClock.now_boottime_ns;
  let launcher = null;
  try {
    launcher = dependencies.launcherIdentity(configuration);
    cgroup = await dependencies.createCgroup(
      preflight.delegation,
      dispatch.request.request_id,
      preflight.policy,
    );
    handles = await dependencies.openExecutionFiles(configuration, preflight, cgroup);
    const dispatchClock = safeClock(dependencies.clock());
    assertDispatchBindings(dispatch, preflight, dispatchClock);
    try {
      await preflight.journal.markDispatched(dispatch.request.request_id, dispatchClock);
    } catch (error) {
      const record = await preflight.journal.read(dispatch.request.request_id);
      await preflight.journal.toUncertain(
        record,
        "dispatch_recovery",
        safeClock(dependencies.clock()).now_boottime_ns,
      );
      throw error;
    }
    dispatched = true;
    const stdinBytes = canonicalExecutorProtocolBytes(dispatch.provider_request);
    child = await dependencies.spawnLauncher(configuration, preflight, handles, stdinBytes);
    result = await dependencies.waitForChild(
      child,
      dispatch.request.deadline_boottime_ns,
      dependencies.clock,
    );
    result = { ...result, pid: result.pid ?? child?.pid ?? null };
    if (result.spawned && !result.timedOut && result.code === 0 && !result.outputTooLarge) {
      response = validateProviderResponseBytes(result.stdout);
    }
  } catch (error) {
    if (reserved && !dispatched) {
      const record = await preflight.journal.read(dispatch.request.request_id);
      if (record?.state === "prepared") {
        await preflight.journal.toUncertain(
          record,
          "dispatch_recovery",
          safeClock(dependencies.clock()).now_boottime_ns,
        );
      }
      if (["prepared", "uncertain", "dispatched"].includes(record?.state)) deferredError = error;
    } else if (dispatched && child !== null) {
      const record = await preflight.journal.read(dispatch.request.request_id);
      if (record?.state === "dispatched") {
        await preflight.journal.toUncertain(
          record,
          "dispatch_recovery",
          safeClock(dependencies.clock()).now_boottime_ns,
        );
      }
      deferredError = error;
    }
    if (deferredError === null) result = { ...result, spawnError: result.spawnError ?? error };
  } finally {
    for (const fd of [handles?.execFd, handles?.cgroupFd]) {
      if (Number.isSafeInteger(fd)) {
        try { dependencies.closeFd(fd); } catch {}
      }
    }
    if (cgroup !== null) {
      try {
        cleanup = await dependencies.killAndRemoveCgroup(cgroup);
      } catch (error) {
        if (reserved) {
          const record = await preflight.journal.read(dispatch.request.request_id);
          if (["prepared", "dispatched"].includes(record?.state)) {
          await preflight.journal.toUncertain(record, "dispatch_recovery", safeClock(dependencies.clock()).now_boottime_ns);
          }
        }
        throw error;
      }
    }
  }

  if (deferredError !== null) throw deferredError;

  const finishedClock = safeClock(dependencies.clock());
  if (finishedClock.boot_id !== dispatch.request.boot_id) {
    const record = await preflight.journal.read(dispatch.request.request_id);
    await preflight.journal.toUncertain(record, "dispatch_recovery", finishedClock.now_boottime_ns);
    fail("executor_runner_boot_id_changed_after_dispatch");
  }
  if (!cleanup?.descendantsCleanupVerified) {
    if (dispatched) {
      const record = await preflight.journal.read(dispatch.request.request_id);
      await preflight.journal.toUncertain(record, "dispatch_recovery", finishedClock.now_boottime_ns);
    }
    fail("executor_runner_cleanup_unverified");
  }
  if (response === null) {
    const record = await preflight.journal.read(dispatch.request.request_id);
    if (["prepared", "dispatched"].includes(record?.state)) {
      await preflight.journal.toUncertain(
        record,
        "dispatch_recovery",
        finishedClock.now_boottime_ns,
      );
    }
    fail("executor_runner_completion_unverified");
  }
  const body = receiptBody({
    configuration,
    preflight,
    dispatch,
    dispatchBytes,
    cgroup,
    launcher,
    result,
    response,
    started,
    finished: finishedClock.now_boottime_ns,
    cleanup,
  });
  const receipt = signExecutorReceipt(body, configuration.receiptKeyId, preflight.receiptKey);
  const terminalOutcome = body.exit_kind === "completed" ? "completed" : "failed";
  try {
    await preflight.journal.markTerminal(dispatch.request.request_id, finishedClock.now_boottime_ns, terminalOutcome);
  } catch (error) {
    const record = await preflight.journal.read(dispatch.request.request_id);
    if (record?.state === "dispatched") {
      await preflight.journal.toUncertain(record, "dispatch_recovery", finishedClock.now_boottime_ns);
    }
    throw error;
  }
  return Object.freeze({
    private_response_bytes: canonicalExecutorProtocolBytes({
      provider_response: response.value,
      receipt,
      schema: EXECUTOR_PRIVATE_RESPONSE_SCHEMA,
    }),
    receipt_bytes: serializeExecutorReceiptEnvelope(receipt),
    schema: EXECUTOR_RUNNER_RESULT_SCHEMA,
  });
}

export async function runExecutorDispatch(dispatchBytesValue, configuration, preflight) {
  return runExecutorDispatchWithDependencies(dispatchBytesValue, configuration, preflight, {});
}

export async function runExecutorDispatchForTest(dispatchBytesValue, configuration, preflight, dependencies) {
  if (process.env.NODE_ENV !== "test") fail("executor_runner_test_dependencies_forbidden");
  return runExecutorDispatchWithDependencies(dispatchBytesValue, configuration, preflight, dependencies);
}
