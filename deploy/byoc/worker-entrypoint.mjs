#!/usr/bin/env node

import { spawn } from "node:child_process";
import {
  closeSync,
  constants,
  fstatSync,
  lstatSync,
  openSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_SECRET_BYTES = 64 * 1024;
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/;
const COST = /^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$/;
const RUNTIMES = new Set(["hermes", "openclaw"]);
const TOKEN_ENVIRONMENT_NAMES = ["AGENTOPS_API_KEY", "AGENTOPS_AGENT_TOKEN"];
const STATE_PATH = "/run/agentops-worker/health.json";
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1", "localhost"]);

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function required(name) {
  const value = String(process.env[name] || "").trim();
  if (!value) fail(`${name.toLowerCase()}_required`);
  return value;
}

function identifier(name) {
  const value = required(name);
  if (!IDENTIFIER.test(value)) fail(`${name.toLowerCase()}_invalid`);
  return value;
}

function boundedInteger(name, fallback, minimum, maximum) {
  const source = String(process.env[name] || "").trim();
  if (!source) return fallback;
  if (!/^\d+$/.test(source)) fail(`${name.toLowerCase()}_invalid`);
  const value = Number(source);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    fail(`${name.toLowerCase()}_invalid`);
  }
  return value;
}

function boolean(name, fallback = false) {
  const value = String(process.env[name] || "").trim().toLowerCase();
  if (!value) return fallback;
  if (["1", "true", "yes", "on"].includes(value)) return true;
  if (["0", "false", "no", "off"].includes(value)) return false;
  fail(`${name.toLowerCase()}_invalid`);
}

function isLoopback(hostname) {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (LOOPBACK_HOSTS.has(normalized) || normalized.endsWith(".localhost")) {
    return true;
  }
  const octets = normalized.split(".");
  return octets.length === 4
    && octets.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)
    && Number(octets[0]) === 127;
}

function validatedUrl(name, { allowLoopbackHttp = false } = {}) {
  let url;
  try {
    url = new URL(required(name));
  } catch {
    fail(`${name.toLowerCase()}_invalid`);
  }
  if (
    !["http:", "https:"].includes(url.protocol)
    || url.username
    || url.password
    || url.search
    || url.hash
  ) {
    fail(`${name.toLowerCase()}_invalid`);
  }
  if (url.protocol !== "https:" && !(allowLoopbackHttp && isLoopback(url.hostname))) {
    fail(`${name.toLowerCase()}_https_required`);
  }
  return url.toString().replace(/\/$/, "");
}

function stableSecret(sourcePath) {
  const before = lstatSync(sourcePath);
  if (!before.isFile() || before.isSymbolicLink()) fail("agent_token_source_not_regular");
  if (before.size < 16 || before.size > MAX_SECRET_BYTES) {
    fail("agent_token_source_size_invalid");
  }
  if (typeof constants.O_NOFOLLOW !== "number") fail("nofollow_unavailable");
  const descriptor = openSync(sourcePath, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const opened = fstatSync(descriptor);
    if (
      !opened.isFile()
      || opened.dev !== before.dev
      || opened.ino !== before.ino
      || opened.size !== before.size
    ) {
      fail("agent_token_source_identity_changed");
    }
    const value = readFileSync(descriptor);
    const after = fstatSync(descriptor);
    if (
      after.dev !== opened.dev
      || after.ino !== opened.ino
      || after.size !== opened.size
      || after.mtimeMs !== opened.mtimeMs
      || after.ctimeMs !== opened.ctimeMs
    ) {
      value.fill(0);
      fail("agent_token_source_changed_during_read");
    }
    return value;
  } finally {
    closeSync(descriptor);
  }
}

export function readAgentToken(sourcePath) {
  const bytes = stableSecret(sourcePath);
  try {
    if (bytes.includes(0)) fail("agent_token_nul_forbidden");
    const token = bytes.toString("utf8").replace(/[\r\n]+$/, "");
    if (
      Buffer.byteLength(token, "utf8") < 16
      || Buffer.byteLength(token, "utf8") > 16 * 1024
      || /[\r\n\u0000-\u001f\u007f]/.test(token)
    ) {
      fail("agent_token_invalid");
    }
    return token;
  } finally {
    bytes.fill(0);
  }
}

function writeState(payload, statePath = STATE_PATH) {
  const temporaryPath = `${statePath}.${process.pid}.tmp`;
  writeFileSync(temporaryPath, `${JSON.stringify(payload)}\n`, {
    encoding: "utf8",
    mode: 0o600,
    flag: "wx",
  });
  renameSync(temporaryPath, statePath);
}

function sanitizeReceipt(value, runtime) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail("worker_receipt_object_required");
  }
  if (
    value.runtime !== runtime
    || typeof value.ok !== "boolean"
    || typeof value.processed !== "boolean"
    || typeof value.reason !== "string"
    || value.reason.length > 120
    || value.token_omitted !== true
    || value.raw_prompt_omitted !== true
    || value.raw_response_omitted !== true
  ) {
    fail("worker_receipt_boundary_invalid");
  }
  return {
    ok: value.ok,
    processed: value.processed,
    reason: value.reason,
    provider_call_performed: value.provider_call_performed === true,
    dry_run: value.dry_run === true,
    task_id: typeof value.task_id === "string" ? value.task_id : null,
    run_id: typeof value.run_id === "string" ? value.run_id : null,
  };
}

function workerCommand(runtime) {
  const cost = required("AGENTOPS_RUN_ESTIMATED_COST_USD");
  if (!COST.test(cost) || /^0(?:\.0{1,6})?$/.test(cost)) {
    fail("agentops_run_estimated_cost_usd_invalid");
  }
  const command = [
    "node",
    "node_modules/tsx/dist/cli.mjs",
    "scripts/commercial-worker.ts",
    "--daemon",
    "--confirm-run",
    "--adapter",
    runtime,
    "--base-url",
    validatedUrl("AGENTOPS_BASE_URL", {
      allowLoopbackHttp: boolean("AGENTOPS_ALLOW_INSECURE_LOOPBACK"),
    }),
    "--workspace-id",
    identifier("AGENTOPS_WORKSPACE_ID"),
    "--agent-id",
    identifier("AGENTOPS_AGENT_ID"),
    "--estimated-cost-usd",
    cost,
    "--poll-interval-ms",
    String(boundedInteger("AGENTOPS_POLL_INTERVAL_MS", 5_000, 1_000, 300_000)),
    "--max-adapter-attempts",
    String(boundedInteger("AGENTOPS_ADAPTER_MAX_ATTEMPTS", 2, 1, 5)),
  ];
  if (boolean("AGENTOPS_ALLOW_INSECURE_LOOPBACK")) command.push("--allow-insecure-loopback");
  if (boolean("AGENTOPS_ALLOW_HIGH_RISK")) command.push("--allow-high-risk");
  if (runtime === "hermes") {
    command.push(
      "--hermes-gateway-url",
      validatedUrl("HERMES_GATEWAY_URL", { allowLoopbackHttp: false }),
      "--hermes-model",
      required("HERMES_MODEL"),
      "--hermes-timeout-ms",
      String(boundedInteger("HERMES_TIMEOUT_MS", 180_000, 1_000, 300_000)),
      "--hermes-max-tokens",
      String(boundedInteger("HERMES_MAX_TOKENS", 512, 64, 4_096)),
    );
  } else {
    const binary = resolve(required("OPENCLAW_BIN"));
    if (binary !== required("OPENCLAW_BIN")) fail("openclaw_bin_absolute_required");
    command.push(
      "--openclaw-bin",
      binary,
      "--openclaw-agent",
      required("OPENCLAW_AGENT"),
      "--openclaw-timeout-seconds",
      String(boundedInteger("OPENCLAW_TIMEOUT_SECONDS", 180, 1, 600)),
      "--working-directory",
      resolve(required("AGENTOPS_WORKER_CWD")),
    );
  }
  return command;
}

function childEnvironment(tokenSource) {
  const allowed = [
    "HOME", "HOSTNAME", "LANG", "LC_ALL", "NODE_ENV", "PATH", "PWD", "SHELL",
    "TMPDIR", "TMP", "TEMP", "TZ", "OPENCLAW_HOME", "OPENCLAW_STATE_DIR",
    "OPENCLAW_CONFIG_PATH", "XDG_CONFIG_HOME", "XDG_DATA_HOME",
  ];
  return {
    ...Object.fromEntries(allowed.filter((name) => process.env[name]).map((name) => [name, process.env[name]])),
    NODE_ENV: "production",
    AGENTOPS_AGENT_TOKEN_SOURCE_FILE: tokenSource,
  };
}

function signalChildGroup(child, signal) {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
  try {
    process.kill(-child.pid, signal);
  } catch (error) {
    if (error?.code !== "ESRCH") child.kill(signal);
  }
}

export async function runWorker({ statePath = STATE_PATH } = {}) {
  if (process.env.NODE_ENV !== "production") fail("worker_production_mode_required");
  if (process.getuid?.() === 0 || process.getgid?.() === 0) fail("worker_root_forbidden");
  for (const name of TOKEN_ENVIRONMENT_NAMES) {
    if (String(process.env[name] || "")) fail("direct_agent_token_environment_forbidden");
  }
  const runtime = required("AGENTOPS_WORKER_ADAPTER");
  if (!RUNTIMES.has(runtime)) fail("agentops_worker_adapter_invalid");
  const tokenSource = required("AGENTOPS_AGENT_TOKEN_SOURCE_FILE");
  const token = readAgentToken(tokenSource);
  const command = workerCommand(runtime);
  const leaseSeconds = boundedInteger("AGENTOPS_WORKER_HEALTH_LEASE_SECONDS", 120, 30, 600);
  let stopping = false;
  let status = "starting";
  let lastReceiptAt = Date.now();
  let lastReceipt = null;
  writeState({ status, runtime, pid: process.pid, lease_seconds: leaseSeconds, updated_at_ms: lastReceiptAt }, statePath);

  const child = spawn(command[0], command.slice(1), {
    cwd: "/opt/agentops/ui/next-app",
    env: childEnvironment(tokenSource),
    stdio: ["ignore", "pipe", "pipe"],
    detached: true,
  });
  const refresh = setInterval(() => {
    writeState({
      status,
      runtime,
      pid: process.pid,
      child_pid: child.pid || null,
      lease_seconds: leaseSeconds,
      updated_at_ms: Date.now(),
      last_receipt_at_ms: lastReceiptAt,
      last_receipt: lastReceipt,
      token_omitted: true,
    }, statePath);
  }, Math.min(10_000, Math.floor(leaseSeconds * 1_000 / 3)));
  refresh.unref();

  let stdout = "";
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
    if (Buffer.byteLength(stdout, "utf8") > 1024 * 1024) {
      signalChildGroup(child, "SIGTERM");
      status = "failed";
      return;
    }
    while (stdout.includes("\n")) {
      const index = stdout.indexOf("\n");
      const line = stdout.slice(0, index);
      stdout = stdout.slice(index + 1);
      if (!line.trim()) continue;
      const receipt = sanitizeReceipt(JSON.parse(line), runtime);
      lastReceipt = receipt;
      lastReceiptAt = Date.now();
      status = receipt.ok ? "ready" : "failed";
      process.stdout.write(`${JSON.stringify({
        contract: "agentops_byoc_typescript_worker_receipt_v1",
        runtime,
        ...receipt,
        token_omitted: true,
        raw_prompt_omitted: true,
        raw_response_omitted: true,
      })}\n`);
      if (!receipt.ok && child.exitCode === null) signalChildGroup(child, "SIGTERM");
    }
  });
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => {
    const text = String(chunk).trim();
    if (!text) return;
    if (text.includes(token)) {
      status = "failed";
      if (child.exitCode === null) signalChildGroup(child, "SIGTERM");
      return;
    }
    process.stderr.write("agentops_worker_child_error_detail_omitted\n");
  });

  const handlers = new Map();
  let forceStop;
  let forcedStop = false;
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
    const handler = () => {
      stopping = true;
      status = "stopping";
      signalChildGroup(child, signal);
      if (!forceStop) {
        forceStop = setTimeout(() => {
          forcedStop = true;
          status = "failed";
          signalChildGroup(child, "SIGKILL");
        }, 20_000);
        forceStop.unref();
      }
    };
    handlers.set(signal, handler);
    process.on(signal, handler);
  }
  const result = await new Promise((resolveResult, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => resolveResult({ code, signal }));
  });
  clearInterval(refresh);
  if (forceStop) clearTimeout(forceStop);
  for (const [signal, handler] of handlers) process.removeListener(signal, handler);
  status = stopping && !forcedStop && result.code === 0
    ? "stopped"
    : "failed";
  writeState({
    status,
    runtime,
    pid: process.pid,
    child_pid: child.pid || null,
    lease_seconds: leaseSeconds,
    updated_at_ms: Date.now(),
    last_receipt_at_ms: lastReceiptAt,
    last_receipt: lastReceipt,
    token_omitted: true,
  }, statePath);
  return result.code === 0 && status === "stopped" ? 0 : 1;
}

function isMain() {
  return process.argv[1] === fileURLToPath(import.meta.url);
}

if (isMain()) {
  runWorker().then((code) => {
    process.exitCode = code;
  }).catch((error) => {
    rmSync(`${STATE_PATH}.${process.pid}.tmp`, { force: true });
    const code = typeof error?.code === "string" ? error.code : "worker_initialization_failed";
    process.stderr.write(`byoc_worker_preflight_failed:${code}\n`);
    process.exitCode = 78;
  });
}
