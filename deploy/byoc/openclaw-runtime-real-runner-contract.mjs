#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, randomUUID } from "node:crypto";
import {
  chmodSync,
  closeSync,
  constants,
  existsSync,
  fstatSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const CONTRACT_SCHEMA = "agentops_openclaw_runtime_real_runner_contract_v1";
const PRODUCTION_EXPORT = "runExecutorDispatch";
const REQUIRED_ARGUMENT = "--require-real-runner";
const STDIN_ARGUMENT = "--stdin-protocol=canonical_provider_request_stdin_v1";
const CONTRACT_PATH = fileURLToPath(import.meta.url);
const SOURCE_ROOT = path.dirname(CONTRACT_PATH);
const RUNNER_PATH = path.join(SOURCE_ROOT, "openclaw-executor-runner.mjs");
const IMAGE_DIGEST = /^sha256:[a-f0-9]{64}$/u;
const MAX_STDIN_BYTES = 1024 * 1024;
const GUEST = Object.freeze({
  adapter: "/opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs",
  config: "/run/secrets/openclaw_config",
  evidence: "/tmp/agentops-real-runner-evidence.json",
  hostCanary: "/agentops-host-only-canary",
  openClawRuntime: "/opt/openclaw/node_modules/openclaw/dist/plugin-sdk/agent-runtime.js",
  state: "/run/openclaw-state",
  tmp: "/tmp",
  workspace: "/opt/agentops-worker/workspace",
  workspaceMarker: "/opt/agentops-worker/workspace/contract-marker",
  wrapper: "/opt/agentops/real-runner/openclaw-runtime-real-runner-contract.mjs",
});
const GUEST_FORBIDDEN_PATHS = Object.freeze([
  "/run/agentops-openclaw-public/broker.sock",
  "/run/agentops-openclaw-private/executor.sock",
  "/run/secrets/agent_token",
  "/run/secrets/openclaw_receipt_signing_key",
  "/run/secrets/openclaw_receipt_trust_root",
  "/run/trust/openclaw-runtime-manifest-trust-roots.json",
  "/run/policies/openclaw-runtime-seccomp.json",
  "/run/policies/openclaw-cgroup-policy.json",
  "/var/lib/agentops-openclaw/replay",
]);

function fail(code, cause) {
  const error = new Error(code, cause === undefined ? undefined : { cause });
  error.code = code;
  throw error;
}

function digest(value) {
  return createHash("sha256").update(value).digest("hex");
}

function jsonLine(value) {
  return `${JSON.stringify(value)}\n`;
}

function requiredAbsoluteDirectory(name) {
  const value = String(process.env[name] || "");
  if (!path.isAbsolute(value) || path.resolve(value) !== value || !existsSync(value)) {
    fail(`real_runner_${name.toLowerCase()}_required`);
  }
  const metadata = lstatSync(value);
  if (!metadata.isDirectory() || metadata.isSymbolicLink() || realpathSync(value) !== value) {
    fail(`real_runner_${name.toLowerCase()}_invalid`);
  }
  return value;
}

function requiredAbsoluteFile(name) {
  const value = String(process.env[name] || "");
  if (!path.isAbsolute(value) || path.resolve(value) !== value || !existsSync(value)) {
    fail(`real_runner_${name.toLowerCase()}_required`);
  }
  const metadata = lstatSync(value);
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.nlink !== 1) {
    fail(`real_runner_${name.toLowerCase()}_invalid`);
  }
  return value;
}

function guestWrapperInvocation() {
  return process.argv.length === 3
    && process.argv[1] === GUEST.wrapper
    && process.argv[2] === STDIN_ARGUMENT;
}

async function readBoundedStdin() {
  const chunks = [];
  let size = 0;
  for await (const chunk of process.stdin) {
    size += chunk.byteLength;
    if (size > MAX_STDIN_BYTES) fail("real_runner_guest_stdin_too_large");
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}

function regularReadableFile(target, expectedOwner = null) {
  const metadata = lstatSync(target);
  if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.nlink !== 1) return false;
  if (expectedOwner !== null && metadata.uid !== expectedOwner) return false;
  readFileSync(target);
  return true;
}

function ownedDirectory(target, expectedOwner, expectedMode = null) {
  const metadata = lstatSync(target);
  return metadata.isDirectory()
    && !metadata.isSymbolicLink()
    && metadata.uid === expectedOwner
    && (expectedMode === null || (metadata.mode & 0o7777) === expectedMode);
}

function assertGuestPathOpenDenied(target) {
  let descriptor;
  try {
    descriptor = openSync(target, constants.O_RDONLY | constants.O_NOFOLLOW);
  } catch (error) {
    if (["EACCES", "ENOENT", "EPERM"].includes(error?.code)) return;
    fail("real_runner_guest_sensitive_path_probe_failed", error);
  }
  try { closeSync(descriptor); } catch {}
  fail("real_runner_guest_sensitive_path_visible");
}

function writeGuestEvidence(value) {
  writeFileSync(GUEST.evidence, jsonLine(value), { encoding: "utf8", mode: 0o600 });
  chmodSync(GUEST.evidence, 0o600);
}

async function runGuestWrapper() {
  if (process.platform !== "linux") fail("real_runner_guest_linux_required");
  if (!guestWrapperInvocation()) fail("real_runner_guest_arguments_invalid");
  if (
    process.getuid?.() !== 1200
    || process.geteuid?.() !== 1200
    || process.getgid?.() !== 1200
    || process.getegid?.() !== 1200
  ) fail("real_runner_guest_identity_invalid");
  if (process.cwd() !== "/") fail("real_runner_guest_cwd_invalid");
  if (
    process.env.OPENCLAW_CONFIG_PATH !== GUEST.config
    || process.env.OPENCLAW_STATE_DIR !== GUEST.state
    || process.env.OPENCLAW_WORKSPACE !== GUEST.workspace
    || process.env.NODE_OPTIONS !== undefined
    || Object.keys(process.env).some((name) => name.startsWith("AGENTOPS_"))
  ) fail("real_runner_guest_fixed_environment_invalid");
  if (existsSync(GUEST.hostCanary)) fail("real_runner_guest_host_canary_visible");
  for (const target of GUEST_FORBIDDEN_PATHS) assertGuestPathOpenDenied(target);
  if (!regularReadableFile(GUEST.config)) fail("real_runner_guest_config_unavailable");
  const guestConfig = JSON.parse(readFileSync(GUEST.config, "utf8"));
  if (
    guestConfig?.agents?.defaults?.model?.primary !== "contract/contract-dynamic-model"
    || guestConfig?.models?.providers?.contract?.api !== "openai-completions"
  ) fail("real_runner_guest_config_invalid");
  if (!ownedDirectory(GUEST.state, 1200, 0o700) || readdirSync(GUEST.state).length !== 0) {
    fail("real_runner_guest_state_invalid");
  }
  if (!ownedDirectory(GUEST.workspace, 0, 0o555)) fail("real_runner_guest_workspace_invalid");
  if (readFileSync(GUEST.workspaceMarker, "utf8") !== "workspace-visible\n") {
    fail("real_runner_guest_workspace_marker_invalid");
  }
  if (!ownedDirectory(GUEST.tmp, 1200)) fail("real_runner_guest_tmp_invalid");
  const tmpProbe = path.join(GUEST.tmp, `agentops-node-write-${process.pid}`);
  writeFileSync(tmpProbe, "node-write-only\n", { encoding: "utf8", mode: 0o600 });
  if (readFileSync(tmpProbe, "utf8") !== "node-write-only\n") fail("real_runner_guest_tmp_write_invalid");
  rmSync(tmpProbe);

  const evidence = {
    adapter_core_called: false,
    config_visible: true,
    cwd: "/",
    fixed_environment_verified: true,
    host_canary_visible: false,
    sensitive_path_open_denials_verified: true,
    sensitive_path_probe_count: GUEST_FORBIDDEN_PATHS.length,
    state_visible_and_empty: true,
    tmp_visible_and_node_writable: true,
    uid: 1200,
    gid: 1200,
    workspace_visible: true,
    wrapper_entrypoint: GUEST.wrapper,
  };
  writeGuestEvidence(evidence);

  const baseStateRoot = process.env.OPENCLAW_STATE_DIR;
  const adapter = await import(pathToFileURL(GUEST.adapter).href);
  if (
    typeof adapter.executeCanonicalProviderRequest !== "function"
    || typeof adapter.createEphemeralStateRoot !== "function"
    || typeof adapter.removeEphemeralStateRoot !== "function"
  ) fail("real_runner_guest_adapter_exports_missing");
  const stateRoot = adapter.createEphemeralStateRoot(baseStateRoot);
  process.env.OPENCLAW_STATE_DIR = stateRoot;
  try {
    const [runtime, stdinBytes] = await Promise.all([
      import(pathToFileURL(GUEST.openClawRuntime).href),
      readBoundedStdin(),
    ]);
    if (typeof runtime.agentCommand !== "function") fail("real_runner_guest_openclaw_runtime_missing");
    const response = await adapter.executeCanonicalProviderRequest(stdinBytes, {
      agentCommand: runtime.agentCommand,
      stateRoot,
      workspaceDir: GUEST.workspace,
    });
    adapter.removeEphemeralStateRoot(baseStateRoot, stateRoot);
    evidence.adapter_core_called = true;
    writeGuestEvidence(evidence);
    process.stdout.write(response);
  } catch (error) {
    try { adapter.removeEphemeralStateRoot(baseStateRoot, stateRoot); } catch {}
    throw error;
  }
}

async function loadProductionRunner() {
  if (!existsSync(RUNNER_PATH)) fail("real_runner_production_module_missing");
  const source = readFileSync(RUNNER_PATH, "utf8");
  if (!/export\s+async\s+function\s+runExecutorDispatch\s*\(/u.test(source)) {
    fail("real_runner_production_export_missing");
  }
  const runner = await import(pathToFileURL(RUNNER_PATH).href);
  if (typeof runner[PRODUCTION_EXPORT] !== "function") fail("real_runner_production_export_missing");
  return { runner, source };
}

async function sourceAudit() {
  const { source } = await loadProductionRunner();
  assert.match(source, /function defaultOpenExecutionFiles\(/u);
  assert.match(source, /function defaultSpawnLauncher\(/u);
  assert.match(source, /env:\s*\{\s*LANG:\s*"C",\s*PATH:\s*"\/usr\/bin:\/bin"\s*\}/u);
  assert.match(source, /result\.launcherStatus\s*===\s*"R"/u);
  return Object.freeze({
    contract: CONTRACT_SCHEMA,
    fake_handles_forbidden: true,
    instrumentation_overlay: false,
    ok: true,
    production_export: PRODUCTION_EXPORT,
    production_export_present: true,
    real_default_open_spawn_executed: false,
    runtime_sensitive_path_open_denials_verified: false,
    runtime_path_toctou_closed: false,
    strict_linux_execution_performed: false,
  });
}

function serveOpenAiResponse(response, body) {
  const base = {
    created: Math.floor(Date.now() / 1000),
    id: "chatcmpl-agentops-real-runner",
    model: "contract-dynamic-model",
    object: "chat.completion",
  };
  if (body.stream === true) {
    response.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
    response.write(`data: ${JSON.stringify({ ...base, choices: [{ delta: { role: "assistant" }, finish_reason: null, index: 0 }], object: "chat.completion.chunk" })}\n\n`);
    response.write(`data: ${JSON.stringify({ ...base, choices: [{ delta: { content: "AGENTOPS_REAL_RUNNER_OK" }, finish_reason: null, index: 0 }], object: "chat.completion.chunk" })}\n\n`);
    response.write(`data: ${JSON.stringify({ ...base, choices: [{ delta: {}, finish_reason: "stop", index: 0 }], object: "chat.completion.chunk" })}\n\n`);
    response.end("data: [DONE]\n\n");
    return;
  }
  response.writeHead(200, { "content-type": "application/json" });
  response.end(JSON.stringify({
    ...base,
    choices: [{ finish_reason: "stop", index: 0, message: { content: "AGENTOPS_REAL_RUNNER_OK", role: "assistant" } }],
    usage: { completion_tokens: 4, prompt_tokens: 12, total_tokens: 16 },
  }));
}

function ioDevice() {
  const value = String(process.env.AGENTOPS_REAL_RUNNER_IO_DEVICE || "");
  if (!/^[0-9]+:[0-9]+$/u.test(value)) fail("real_runner_io_device_required");
  return value;
}

function descriptorClosed(fd) {
  try {
    fstatSync(fd);
    return false;
  } catch (error) {
    return error?.code === "EBADF";
  }
}

async function runStrictContract() {
  if (process.platform !== "linux" || process.geteuid?.() !== 0) {
    fail("real_runner_linux_root_required");
  }
  const { runner } = await loadProductionRunner();
  const runExecutorDispatch = runner[PRODUCTION_EXPORT];
  const protocol = await import(pathToFileURL(path.join(SOURCE_ROOT, "openclaw-executor-protocol.mjs")).href);
  const requestModule = await import(pathToFileURL(path.join(SOURCE_ROOT, "openclaw-executor-request.mjs")).href);
  const cgroupModule = await import(pathToFileURL(path.join(SOURCE_ROOT, "openclaw-cgroup-v2.mjs")).href);

  const runtimeRoot = requiredAbsoluteDirectory("AGENTOPS_REAL_RUNNER_GUEST_ROOT");
  const cgroupRoot = requiredAbsoluteDirectory("AGENTOPS_REAL_RUNNER_CGROUP_ROOT");
  const launcherPath = requiredAbsoluteFile("AGENTOPS_REAL_RUNNER_LAUNCHER");
  const guestConfigPath = requiredAbsoluteFile("AGENTOPS_REAL_RUNNER_GUEST_CONFIG");
  const runtimeImageDigest = String(process.env.AGENTOPS_REAL_RUNNER_IMAGE_DIGEST || "");
  if (!IMAGE_DIGEST.test(runtimeImageDigest)) fail("real_runner_image_digest_required");
  const providerKey = "contract-provider-key";
  const providerPort = 18081;
  const guestConfigBytes = readFileSync(guestConfigPath);
  const guestConfig = JSON.parse(guestConfigBytes.toString("utf8"));
  if (
    guestConfig?.models?.providers?.contract?.apiKey !== providerKey
    || guestConfig?.models?.providers?.contract?.baseUrl !== `http://127.0.0.1:${providerPort}/v1`
  ) fail("real_runner_host_config_invalid");

  const executablePath = path.join(runtimeRoot, "usr/local/bin/node");
  const wrapperPath = path.join(runtimeRoot, GUEST.wrapper.slice(1));
  if (!regularReadableFile(executablePath, 0) || !regularReadableFile(wrapperPath, 0)) {
    fail("real_runner_runtime_entrypoints_invalid");
  }
  const scratch = mkdtempSync(path.join(tmpdir(), "agentops-real-runner-"));
  const journalRoot = path.join(scratch, "journal");
  mkdirSync(journalRoot, { mode: 0o700 });
  chmodSync(journalRoot, 0o700);

  let rootFd;
  let execFd;
  let providerListening = false;
  let providerCalls = 0;
  let finalReceipt;
  const providerServer = createServer(async (request, response) => {
    try {
      if (request.method !== "POST" || request.url !== "/v1/chat/completions") {
        response.writeHead(404).end();
        return;
      }
      const chunks = [];
      let bytes = 0;
      for await (const chunk of request) {
        bytes += chunk.byteLength;
        if (bytes > MAX_STDIN_BYTES) fail("real_runner_provider_request_too_large");
        chunks.push(Buffer.from(chunk));
      }
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (
        body.model !== "contract-dynamic-model"
        || request.headers.authorization !== `Bearer ${providerKey}`
      ) {
        response.writeHead(400).end();
        return;
      }
      providerCalls += 1;
      serveOpenAiResponse(response, body);
    } catch {
      if (!response.headersSent) response.writeHead(500);
      response.end();
    }
  });

  try {
    rootFd = openSync(
      runtimeRoot,
      constants.O_RDONLY | constants.O_DIRECTORY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
    );
    execFd = openSync(
      executablePath,
      constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC,
    );
    if (!fstatSync(rootFd).isDirectory() || !fstatSync(execFd).isFile()) {
      fail("real_runner_runtime_handles_invalid");
    }

    const manifest = Object.freeze({
      argv_template: Object.freeze(["/usr/local/bin/node", GUEST.wrapper, STDIN_ARGUMENT]),
      environment_name_allowlist: Object.freeze([]),
      files: Object.freeze([]),
      runtime_executable: "/usr/local/bin/node",
    });
    const manifestSha256 = digest(protocol.canonicalExecutorProtocolBytes(manifest));
    const policy = Object.freeze({
      cpuMax: "50000 100000",
      ioMax: `${ioDevice()} rbps=max wbps=max`,
      memoryMax: "2147483648",
      pidsMax: "256",
    });
    const policySha256 = digest(protocol.canonicalExecutorProtocolBytes(policy));
    const seccompSha256 = digest("production-launcher-built-in-seccomp-contract");
    const signing = generateKeyPairSync("ed25519");
    const journal = await requestModule.ExecutorReplayJournal.open(journalRoot, {
      expectedOwner: { uid: 0, gid: 0 },
    });
    const preflight = Object.freeze({
      delegation: cgroupModule.inspectDelegatedCgroupRoot({ root: cgroupRoot }),
      journal,
      manifest,
      manifestSha256,
      policy,
      policySha256,
      receiptKey: signing.privateKey,
      runtimeHandles: Object.freeze({ execFd, rootFd }),
      seccompSha256,
    });
    const clock = protocol.readLinuxBootClock();
    const requestId = `real-${randomUUID()}`;
    const prompt = "Return exactly the text AGENTOPS_REAL_RUNNER_OK.";
    const dispatch = protocol.buildExecutorDispatch({
      agent_name: "main",
      nonce: `nonce-${requestId}`,
      prompt,
      prompt_sha256: digest(prompt),
      request_id: requestId,
      run_id: `run-${requestId}`,
      schema: protocol.EXECUTOR_PUBLIC_REQUEST_SCHEMA,
      timeout_seconds: 120,
      workspace_id_hash: digest("real-runner-workspace"),
    }, { bootClock: clock, isolationPolicySha256: policySha256, runtimeManifestSha256: manifestSha256 });

    await new Promise((resolve, reject) => {
      providerServer.once("error", reject);
      providerServer.listen(providerPort, "127.0.0.1", () => {
        providerListening = true;
        resolve();
      });
    });
    const result = await runExecutorDispatch(
      protocol.canonicalExecutorProtocolBytes(dispatch),
      Object.freeze({
        executorImageDigest: `sha256:${digest(readFileSync(launcherPath))}`,
        launcherPath,
        receiptKeyId: "real-runner-contract-key",
        runtimeImageDigest,
        runtimeRoot,
      }),
      preflight,
    );
    const privateResponse = JSON.parse(result.private_response_bytes.toString("utf8"));
    const evidence = JSON.parse(readFileSync(path.join(runtimeRoot, GUEST.evidence.slice(1)), "utf8"));
    assert.equal(privateResponse.provider_response.ok, true);
    assert.equal(privateResponse.provider_response.provider_call_performed, true);
    assert.equal(privateResponse.receipt.body.exit_kind, "completed");
    assert.equal(privateResponse.receipt.body.launcher.invoked, true);
    assert.equal(privateResponse.receipt.body.process.spawned, true);
    assert.equal(privateResponse.receipt.body.descendants_cleanup_verified, true);
    assert.equal(providerCalls, 1);
    assert.deepEqual(evidence, {
      adapter_core_called: true,
      config_visible: true,
      cwd: "/",
      fixed_environment_verified: true,
      host_canary_visible: false,
      sensitive_path_open_denials_verified: true,
      sensitive_path_probe_count: GUEST_FORBIDDEN_PATHS.length,
      state_visible_and_empty: true,
      tmp_visible_and_node_writable: true,
      uid: 1200,
      gid: 1200,
      workspace_visible: true,
      wrapper_entrypoint: GUEST.wrapper,
    });
    assert.equal(
      readFileSync(path.join(runtimeRoot, GUEST.config.slice(1)), "utf8"),
      guestConfigBytes.toString("utf8"),
    );
    assert.equal(
      readFileSync(path.join(runtimeRoot, GUEST.workspaceMarker.slice(1)), "utf8"),
      "workspace-visible\n",
    );
    assert.deepEqual(readdirSync(path.join(runtimeRoot, GUEST.state.slice(1))), []);
    finalReceipt = {
      contract: CONTRACT_SCHEMA,
      digest_pinned_guest_root_base_executed: true,
      dynamic_node_openclaw_entrypoint_executed: true,
      fake_handles_injected: false,
      fixed_launcher_environment_verified: true,
      guest_config_state_workspace_tmp_visible: true,
      host_path_invisible: true,
      instrumentation_overlay: true,
      ok: true,
      production_export: PRODUCTION_EXPORT,
      provider_call_observed: true,
      real_default_open_spawn_executed: true,
      runtime_sensitive_path_open_denials_verified: true,
      runtime_path_toctou_closed: false,
      runtime_uid_gid_1200_verified: true,
      status_handshake_r_verified: true,
      strict_linux_execution_performed: true,
    };
  } finally {
    if (providerListening) await new Promise((resolve) => providerServer.close(resolve));
    if (Number.isSafeInteger(execFd)) closeSync(execFd);
    if (Number.isSafeInteger(rootFd)) closeSync(rootFd);
    rmSync(scratch, { force: true, recursive: true });
  }
  assert.equal(descriptorClosed(execFd), true);
  assert.equal(descriptorClosed(rootFd), true);
  finalReceipt.runtime_handles_closed_in_finally = true;
  process.stdout.write(jsonLine(finalReceipt));
}

if (guestWrapperInvocation()) {
  try {
    await runGuestWrapper();
  } catch (error) {
    const guestErrorCode = typeof error?.code === "string"
      && /^[a-z][a-z0-9_]{0,119}$/u.test(error.code)
      ? error.code
      : "real_runner_guest_failed";
    try { writeGuestEvidence({ guest_error_code: guestErrorCode }); } catch {}
    process.exitCode = 1;
  }
} else if (process.argv.length === 3 && process.argv[2] === REQUIRED_ARGUMENT) {
  try {
    await runStrictContract();
  } catch (error) {
    let guestErrorCode = null;
    try {
      const guestEvidence = JSON.parse(readFileSync(
        path.join(String(process.env.AGENTOPS_REAL_RUNNER_GUEST_ROOT || ""), GUEST.evidence.slice(1)),
        "utf8",
      ));
      if (/^[a-z][a-z0-9_]{0,119}$/u.test(String(guestEvidence?.guest_error_code || ""))) {
        guestErrorCode = guestEvidence.guest_error_code;
      }
    } catch {}
    process.stderr.write(jsonLine({
      contract: CONTRACT_SCHEMA,
      error: typeof error?.code === "string" ? error.code : "real_runner_contract_failed",
      guest_error_code: guestErrorCode,
      ok: false,
      raw_prompt_omitted: true,
      raw_response_omitted: true,
      secrets_omitted: true,
    }));
    process.exitCode = 1;
  }
} else if (process.argv.length === 2) {
  process.stdout.write(jsonLine(await sourceAudit()));
} else {
  fail("real_runner_contract_arguments_invalid");
}
