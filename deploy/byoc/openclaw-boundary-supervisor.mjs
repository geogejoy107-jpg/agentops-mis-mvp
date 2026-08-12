#!/usr/bin/env node

import { spawn } from "node:child_process";
import {
  chmodSync,
  existsSync,
  lstatSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { request } from "node:http";
import { isAbsolute, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const GATE_BINARY = "/usr/local/bin/agentops-openclaw-peercred-gate";
export const BROKER_INTERNAL_ROOT = "/run/agentops-openclaw-broker-backend";
export const BROKER_INTERNAL_SOCKET = `${BROKER_INTERNAL_ROOT}/broker.sock`;
export const EXECUTOR_INTERNAL_ROOT = "/run/agentops-openclaw-provider-backend";
export const EXECUTOR_INTERNAL_SOCKET = `${EXECUTOR_INTERNAL_ROOT}/provider.sock`;

const BROKER_ENTRYPOINT = "/usr/local/lib/agentops/openclaw-broker-entrypoint.mjs";
const EXECUTOR_ENTRYPOINT = "/usr/local/lib/agentops/openclaw-provider-entrypoint.mjs";
const PUBLIC_SOCKET = "/run/agentops-openclaw-public/broker.sock";
const PRIVATE_SOCKET = "/run/agentops-openclaw-private/executor.sock";
const MAX_HEALTH_BYTES = 8 * 1024;
const SAFE_ENVIRONMENT_NAMES = new Set([
  "AGENTOPS_OPENCLAW_BOUNDARY_ROLE",
  "AGENTOPS_OPENCLAW_BOUNDARY_TEST_BACKEND_ENTRYPOINT",
  "AGENTOPS_OPENCLAW_BOUNDARY_TEST_GATE_PATH",
  "AGENTOPS_OPENCLAW_BOUNDARY_TEST_ROOT",
  "AGENTOPS_OPENCLAW_BOUNDARY_TEST_STARTUP_TIMEOUT_MS",
  "AGENTOPS_OPENCLAW_BOUNDARY_TEST_SHUTDOWN_GRACE_MS",
]);
const BROKER_BACKEND_ENVIRONMENT = new Set([
  "AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_GID",
  "AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_UID",
  "AGENTOPS_OPENCLAW_BROKER_REQUEST_TIMEOUT_MS",
  "AGENTOPS_OPENCLAW_BROKER_BODY_TIMEOUT_MS",
]);
const EXECUTOR_BACKEND_ENVIRONMENT = new Set([
  "OPENCLAW_BIN",
  "OPENCLAW_BIN_SHA256",
  "OPENCLAW_CONFIG_PATH",
  "OPENCLAW_STATE_DIR",
  "OPENCLAW_WORKSPACE",
  "AGENTOPS_WORKER_CWD",
  "OPENCLAW_AGENT",
  "OPENCLAW_TIMEOUT_SECONDS",
  "OPENCLAW_PROVIDER_SHUTDOWN_GRACE_MS",
  "OPENCLAW_HOME",
  "XDG_CONFIG_HOME",
  "XDG_DATA_HOME",
]);

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function absolutePath(value, label) {
  if (typeof value !== "string" || !value || !isAbsolute(value) || resolve(value) !== value) {
    fail(`${label}_absolute_path_required`);
  }
  return value;
}

function boundedInteger(value, fallback, minimum, maximum, label) {
  const candidate = value === undefined || value === "" ? fallback : Number(value);
  if (!Number.isSafeInteger(candidate) || candidate < minimum || candidate > maximum) {
    fail(`${label}_invalid`);
  }
  return candidate;
}

function testOverride(environment, name, fallback) {
  const value = environment[name];
  if (value === undefined || value === "") return fallback;
  if (environment.NODE_ENV !== "test") fail("boundary_test_override_forbidden");
  return absolutePath(value, name.toLowerCase());
}

function roleContract(role, testRoot) {
  const paths = testRoot
    ? {
        brokerInternalRoot: join(testRoot, "broker-backend"),
        executorInternalRoot: join(testRoot, "provider-backend"),
        publicSocket: join(testRoot, "public", "broker.sock"),
        privateSocket: join(testRoot, "private", "executor.sock"),
      }
    : {
        brokerInternalRoot: BROKER_INTERNAL_ROOT,
        executorInternalRoot: EXECUTOR_INTERNAL_ROOT,
        publicSocket: PUBLIC_SOCKET,
        privateSocket: PRIVATE_SOCKET,
      };
  if (role === "broker") {
    return {
      backendEntrypoint: BROKER_ENTRYPOINT,
      backendSchema: "agentops_openclaw_broker_health_v1",
      externalSocket: paths.publicSocket,
      expectedUid: 1000,
      listenGid: 2100,
      internalRoot: paths.brokerInternalRoot,
      internalSocket: join(paths.brokerInternalRoot, "broker.sock"),
      privateSocket: paths.privateSocket,
    };
  }
  if (role === "executor") {
    return {
      backendEntrypoint: EXECUTOR_ENTRYPOINT,
      backendSchema: "agentops_openclaw_provider_health_v1",
      externalSocket: paths.privateSocket,
      expectedUid: 1100,
      listenGid: 2200,
      internalRoot: paths.executorInternalRoot,
      internalSocket: join(paths.executorInternalRoot, "provider.sock"),
      privateSocket: paths.privateSocket,
    };
  }
  fail("boundary_role_invalid");
}

export function loadConfiguration(environment = process.env) {
  for (const name of Object.keys(environment)) {
    if (name.startsWith("AGENTOPS_OPENCLAW_BOUNDARY_") && !SAFE_ENVIRONMENT_NAMES.has(name)) {
      fail("boundary_environment_unknown");
    }
    if (
      name.startsWith("AGENTOPS_OPENCLAW_BOUNDARY_TEST_")
      && environment[name] !== ""
      && environment.NODE_ENV !== "test"
    ) {
      fail("boundary_test_override_forbidden");
    }
  }
  const role = String(environment.AGENTOPS_OPENCLAW_BOUNDARY_ROLE || "");
  const testRootValue = environment.AGENTOPS_OPENCLAW_BOUNDARY_TEST_ROOT;
  if (testRootValue && environment.NODE_ENV !== "test") fail("boundary_test_override_forbidden");
  const testRoot = testRootValue
    ? absolutePath(testRootValue, "boundary_test_root")
    : null;
  const contract = roleContract(role, testRoot);
  const internalSocket = contract.internalSocket;
  const statePath = join(contract.internalRoot, "supervisor-state.json");
  return Object.freeze({
    role,
    backendEntrypoint: testOverride(
      environment,
      "AGENTOPS_OPENCLAW_BOUNDARY_TEST_BACKEND_ENTRYPOINT",
      contract.backendEntrypoint,
    ),
    backendSchema: contract.backendSchema,
    gatePath: testOverride(
      environment,
      "AGENTOPS_OPENCLAW_BOUNDARY_TEST_GATE_PATH",
      GATE_BINARY,
    ),
    externalSocket: contract.externalSocket,
    privateSocket: contract.privateSocket,
    expectedUid: contract.expectedUid,
    listenGid: contract.listenGid,
    internalRoot: contract.internalRoot,
    internalSocket,
    statePath,
    startupTimeoutMs: boundedInteger(
      environment.AGENTOPS_OPENCLAW_BOUNDARY_TEST_STARTUP_TIMEOUT_MS,
      30_000,
      1_000,
      120_000,
      "boundary_startup_timeout_ms",
    ),
    shutdownGraceMs: boundedInteger(
      environment.AGENTOPS_OPENCLAW_BOUNDARY_TEST_SHUTDOWN_GRACE_MS,
      5_000,
      100,
      30_000,
      "boundary_shutdown_grace_ms",
    ),
    testMode: environment.NODE_ENV === "test",
  });
}

function validateInternalRoot(configuration) {
  let metadata;
  try {
    metadata = lstatSync(configuration.internalRoot);
  } catch {
    fail("boundary_internal_root_unavailable");
  }
  if (
    !metadata.isDirectory()
    || metadata.isSymbolicLink()
    || metadata.uid !== process.getuid?.()
    || metadata.gid !== process.getgid?.()
    || (metadata.mode & 0o777) !== 0o700
  ) {
    fail("boundary_internal_root_invalid");
  }
  for (const path of [configuration.internalSocket, configuration.statePath]) {
    if (existsSync(path)) fail("boundary_internal_state_not_clean");
  }
}

function copyAllowed(source, names) {
  return Object.fromEntries(
    [...names]
      .filter((name) => typeof source[name] === "string" && source[name] !== "")
      .map((name) => [name, source[name]]),
  );
}

function baseChildEnvironment(environment) {
  return {
    NODE_ENV: environment.NODE_ENV === "test" ? "test" : "production",
    PATH: "/usr/local/bin:/usr/bin:/bin",
    LANG: "C",
    LC_ALL: "C",
  };
}

export function backendEnvironment(configuration, environment = process.env) {
  const base = baseChildEnvironment(environment);
  if (configuration.role === "broker") {
    return {
      ...base,
      ...copyAllowed(environment, BROKER_BACKEND_ENVIRONMENT),
      AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_PATH: configuration.internalSocket,
      AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_PATH: configuration.privateSocket,
      AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_GID: String(process.getgid?.()),
    };
  }
  return {
    ...base,
    ...copyAllowed(environment, EXECUTOR_BACKEND_ENVIRONMENT),
    OPENCLAW_PROVIDER_SOCKET: configuration.internalSocket,
    OPENCLAW_PROVIDER_SOCKET_GID: String(process.getgid?.()),
  };
}

export function gateArguments(configuration) {
  return [
    "--listen", configuration.externalSocket,
    "--upstream", configuration.internalSocket,
    "--expected-uid", String(configuration.expectedUid),
    "--listen-gid", String(configuration.listenGid),
  ];
}

export function gateEnvironment(environment = process.env) {
  return baseChildEnvironment(environment);
}

function spawnChild(command, arguments_, environment) {
  const child = spawn(command, arguments_, {
    env: environment,
    stdio: "ignore",
    detached: true,
    windowsHide: true,
  });
  child.boundarySpawnErrorCode = null;
  child.boundaryTerminal = null;
  const exited = new Promise((resolveExit) => {
    child.once("exit", (code, signal) => {
      child.boundaryTerminal = { code, signal };
      resolveExit({ code, signal });
    });
    child.once("error", (error) => {
      child.boundarySpawnErrorCode = typeof error?.code === "string" ? error.code : "UNKNOWN";
      child.boundaryTerminal = { code: null, signal: null };
      resolveExit({ code: null, signal: null });
    });
  });
  return { child, exited };
}

function processGroupGone(pid) {
  if (!Number.isSafeInteger(pid) || pid < 1) return true;
  try {
    process.kill(-pid, 0);
    return false;
  } catch (error) {
    return error?.code === "ESRCH";
  }
}

function signalGroup(child, signal) {
  if (!child?.pid || processGroupGone(child.pid)) return true;
  try {
    process.kill(-child.pid, signal);
    return true;
  } catch (error) {
    return error?.code === "ESRCH";
  }
}

function sleep(milliseconds) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds));
}

async function waitForGroupsGone(children, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (children.every((child) => processGroupGone(child?.pid))) return true;
    await sleep(25);
  }
  return children.every((child) => processGroupGone(child?.pid));
}

function healthRequest(socketPath, expectedSchema, timeoutMs = 500) {
  return new Promise((resolveHealth) => {
    let settled = false;
    const finish = (healthy) => {
      if (settled) return;
      settled = true;
      resolveHealth(healthy);
    };
    const check = request({
      socketPath,
      path: "/health",
      method: "GET",
      headers: { Connection: "close" },
    }, (response) => {
      const chunks = [];
      let size = 0;
      response.on("data", (chunk) => {
        size += chunk.byteLength;
        if (size > MAX_HEALTH_BYTES) response.destroy();
        else chunks.push(chunk);
      });
      response.once("error", () => finish(false));
      response.once("end", () => {
        try {
          const value = JSON.parse(Buffer.concat(chunks).toString("utf8"));
          finish(
            size <= MAX_HEALTH_BYTES
            && response.statusCode === 200
            && value?.schema === expectedSchema
            && value.ok === true
            && value.ready === true,
          );
        } catch {
          finish(false);
        }
      });
    });
    check.once("socket", (socket) => socket.once("error", () => finish(false)));
    check.setTimeout(timeoutMs, () => check.destroy());
    check.once("error", () => finish(false));
    check.end();
  });
}

function socketIdentity(socketPath, expectedUid, expectedGid) {
  try {
    const metadata = lstatSync(socketPath);
    return metadata.isSocket()
      && !metadata.isSymbolicLink()
      && metadata.uid === expectedUid
      && metadata.gid === expectedGid
      && (metadata.mode & 0o777) === 0o660;
  } catch {
    return false;
  }
}

async function waitForHealth(
  socketPath,
  expectedSchema,
  expectedUid,
  expectedGid,
  child,
  timeoutMs,
  label,
  shutdownRequested,
) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (shutdownRequested()) fail("boundary_shutdown_requested_during_startup");
    if (child.boundarySpawnErrorCode) fail(`${label}_spawn_failed`);
    if (child.boundaryTerminal || child.exitCode !== null || child.signalCode !== null) {
      fail(`${label}_child_exited`);
    }
    if (
      socketIdentity(socketPath, expectedUid, expectedGid)
      && await healthRequest(socketPath, expectedSchema)
    ) return;
    await sleep(50);
  }
  fail(`${label}_timeout`);
}

async function waitForSocketMetadata(
  socketPath,
  expectedUid,
  expectedGid,
  child,
  timeoutMs,
  label,
  shutdownRequested,
) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (shutdownRequested()) fail("boundary_shutdown_requested_during_startup");
    if (child.boundarySpawnErrorCode) fail(`${label}_spawn_failed`);
    if (child.boundaryTerminal || child.exitCode !== null || child.signalCode !== null) {
      fail(`${label}_child_exited`);
    }
    if (socketIdentity(socketPath, expectedUid, expectedGid)) return;
    await sleep(50);
  }
  fail(`${label}_timeout`);
}

function writeState(configuration, payload) {
  const temporary = `${configuration.statePath}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(payload)}\n`, {
    encoding: "utf8",
    mode: 0o600,
    flag: "wx",
  });
  chmodSync(temporary, 0o600);
  renameSync(temporary, configuration.statePath);
}

function cleanupInternalState(configuration) {
  let ok = true;
  for (const path of [configuration.internalSocket, configuration.statePath]) {
    try {
      unlinkSync(path);
    } catch (error) {
      if (error?.code !== "ENOENT") ok = false;
    }
  }
  return ok;
}

async function stopChildren(children, graceMs) {
  for (const child of children) signalGroup(child, "SIGTERM");
  if (!(await waitForGroupsGone(children, graceMs))) {
    for (const child of children) signalGroup(child, "SIGKILL");
  }
  return waitForGroupsGone(children, Math.max(1_000, graceMs));
}

export async function runSupervisor(configuration = loadConfiguration()) {
  validateInternalRoot(configuration);
  let backend = null;
  let gate = null;
  let shuttingDown = false;
  let requestedSignal = null;
  let resolveSignal;
  const signalReceived = new Promise((resolveReceived) => { resolveSignal = resolveReceived; });
  const signalHandler = (signal) => {
    requestedSignal = signal;
    resolveSignal({ kind: "signal", signal });
  };
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) process.on(signal, signalHandler);
  try {
    backend = spawnChild(
      process.execPath,
      [configuration.backendEntrypoint],
      backendEnvironment(configuration),
    );
    await waitForHealth(
      configuration.internalSocket,
      configuration.backendSchema,
      process.getuid?.(),
      process.getgid?.(),
      backend.child,
      configuration.startupTimeoutMs,
      "boundary_backend_health",
      () => requestedSignal !== null,
    );
    gate = spawnChild(
      configuration.gatePath,
      gateArguments(configuration),
      gateEnvironment(),
    );
    await waitForSocketMetadata(
      configuration.externalSocket,
      process.getuid?.(),
      configuration.testMode ? process.getgid?.() : configuration.listenGid,
      gate.child,
      configuration.startupTimeoutMs,
      "boundary_gate_listener",
      () => requestedSignal !== null,
    );
    writeState(configuration, {
      schema: "agentops_openclaw_boundary_supervisor_state_v1",
      ready: true,
      role: configuration.role,
      backend_pid: backend.child.pid,
      gate_pid: gate.child.pid,
      backend_health_verified: true,
      external_gate_health_verified: false,
      external_gate_listener_metadata_verified: true,
      gate_expected_uid: configuration.expectedUid,
      gate_listen_gid: configuration.listenGid,
      peercred_gate_process_started: true,
      peercred_runtime_verified: false,
      linux_peercred_gate_contract_verified: false,
      phase_a_a04_verified: false,
      phase_a_a05_verified: false,
      raw_logs_omitted: true,
    });
    const terminal = await Promise.race([
      signalReceived,
      backend.exited.then((result) => ({ kind: "backend_exit", result })),
      gate.exited.then((result) => ({ kind: "gate_exit", result })),
    ]);
    shuttingDown = true;
    const groupsGone = await stopChildren(
      [gate.child, backend.child],
      configuration.shutdownGraceMs,
    );
    const stateRemoved = cleanupInternalState(configuration);
    if (!groupsGone) fail("boundary_child_groups_not_empty");
    if (!stateRemoved) fail("boundary_internal_cleanup_failed");
    if (terminal.kind !== "signal") fail(`boundary_${terminal.kind}`);
    return { ok: true, signal: requestedSignal };
  } catch (error) {
    if (!shuttingDown) {
      shuttingDown = true;
      const children = [gate?.child, backend?.child].filter(Boolean);
      const groupsGone = await stopChildren(children, configuration.shutdownGraceMs);
      const stateRemoved = cleanupInternalState(configuration);
      if (!groupsGone) fail("boundary_child_groups_not_empty");
      if (!stateRemoved) fail("boundary_internal_cleanup_failed");
    }
    throw error;
  } finally {
    for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) process.off(signal, signalHandler);
  }
}

async function main() {
  try {
    await runSupervisor();
  } catch (error) {
    const code = typeof error?.code === "string"
      && /^[a-z][a-z0-9_]{2,100}$/.test(error.code)
      ? error.code
      : "openclaw_boundary_supervisor_failed";
    process.stderr.write(`${code}\n`);
    process.exitCode = 1;
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  await main();
}
