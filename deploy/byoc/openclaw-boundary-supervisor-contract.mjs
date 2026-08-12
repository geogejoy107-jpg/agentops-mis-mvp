#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import {
  chmodSync,
  chownSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const supervisor = join(here, "openclaw-boundary-supervisor.mjs");
const root = mkdtempSync("/tmp/aobs-");
const secret = "supervisor-contract-secret-must-not-reach-children";

function sleep(milliseconds) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, milliseconds));
}

async function waitFor(predicate, label, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await sleep(25);
  }
  throw new Error(`${label}_timeout`);
}

function processGone(pid) {
  if (!Number.isSafeInteger(pid) || pid < 1) return false;
  try {
    process.kill(pid, 0);
    return false;
  } catch (error) {
    return error?.code === "ESRCH";
  }
}

function fixturePaths(name) {
  const fixture = join(root, name.slice(0, 12));
  for (const directory of [
    fixture,
    join(fixture, "broker-backend"),
    join(fixture, "provider-backend"),
    join(fixture, "public"),
    join(fixture, "private"),
  ]) {
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    chownSync(directory, process.getuid(), process.getgid());
    chmodSync(directory, 0o700);
  }
  return {
    fixture,
    brokerInternalSocket: join(fixture, "broker-backend", "broker.sock"),
    executorInternalSocket: join(fixture, "provider-backend", "provider.sock"),
    brokerState: join(fixture, "broker-backend", "supervisor-state.json"),
    executorState: join(fixture, "provider-backend", "supervisor-state.json"),
    events: join(fixture, "events.jsonl"),
    gateRecord: join(fixture, "gate-record.json"),
    backendRecord: join(fixture, "backend-record.json"),
    backendPid: join(fixture, "backend-descendant.pid"),
    gatePid: join(fixture, "gate-descendant.pid"),
    childError: join(fixture, "child-error.txt"),
  };
}

function writeExecutable(path, source) {
  writeFileSync(path, source, { encoding: "utf8", mode: 0o755, flag: "wx" });
  chmodSync(path, 0o755);
}

function backendSource(paths, schema, { earlyExit = false, descendants = false } = {}) {
  return `#!${process.execPath}
const fs=require("node:fs");const http=require("node:http");const cp=require("node:child_process");
process.on("uncaughtException",error=>{fs.writeFileSync(${JSON.stringify(paths.childError)},String(error?.stack||error));process.exit(97)});
fs.appendFileSync(${JSON.stringify(paths.events)},"backend_started\\n");
fs.writeFileSync(${JSON.stringify(paths.backendRecord)},JSON.stringify({argv:process.argv,env:process.env}));
${earlyExit ? "process.exit(23);" : ""}
${descendants ? `const d=cp.spawn(process.execPath,["-e","process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],{stdio:"ignore"});fs.writeFileSync(${JSON.stringify(paths.backendPid)},String(d.pid));process.on("SIGTERM",()=>{});` : ""}
const socket=process.env.AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_PATH||process.env.OPENCLAW_PROVIDER_SOCKET;
const server=http.createServer((req,res)=>{const body=JSON.stringify({schema:${JSON.stringify(schema)},ok:true,ready:true,busy:false});res.writeHead(200,{"content-type":"application/json","content-length":Buffer.byteLength(body)});res.end(body)});
  server.listen(socket,()=>{fs.chownSync(socket,process.getuid(),process.getgid());fs.chmodSync(socket,0o660);fs.appendFileSync(${JSON.stringify(paths.events)},"backend_ready\\n")});
process.on("SIGTERM",()=>server.close(()=>process.exit(0)));
`;
}

function gateSource(paths, { earlyExit = false, descendants = false } = {}) {
  return `#!${process.execPath}
const fs=require("node:fs");const net=require("node:net");const cp=require("node:child_process");
const args=process.argv.slice(2);const value=name=>args[args.indexOf(name)+1];
fs.appendFileSync(${JSON.stringify(paths.events)},"gate_started\\n");
fs.writeFileSync(${JSON.stringify(paths.gateRecord)},JSON.stringify({argv:args,env:process.env}));
${earlyExit ? "process.exit(29);" : ""}
${descendants ? `const d=cp.spawn(process.execPath,["-e","process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],{stdio:"ignore"});fs.writeFileSync(${JSON.stringify(paths.gatePid)},String(d.pid));process.on("SIGTERM",()=>{});` : ""}
const listen=value("--listen"),upstream=value("--upstream");
const server=net.createServer(client=>{const target=net.createConnection({path:upstream});client.pipe(target);target.pipe(client);client.on("error",()=>target.destroy());target.on("error",()=>client.destroy())});
  server.listen(listen,()=>{fs.chownSync(listen,process.getuid(),process.getgid());fs.chmodSync(listen,0o660);fs.appendFileSync(${JSON.stringify(paths.events)},"gate_ready\\n")});
process.on("SIGTERM",()=>server.close(()=>process.exit(0)));
`;
}

function environment(role, paths, backend, gate, extra = {}) {
  return {
    PATH: process.env.PATH,
    HOME: process.env.HOME,
    NODE_ENV: "test",
    AGENTOPS_OPENCLAW_BOUNDARY_ROLE: role,
    AGENTOPS_OPENCLAW_BOUNDARY_TEST_ROOT: paths.fixture,
    AGENTOPS_OPENCLAW_BOUNDARY_TEST_BACKEND_ENTRYPOINT: backend,
    AGENTOPS_OPENCLAW_BOUNDARY_TEST_GATE_PATH: gate,
    AGENTOPS_OPENCLAW_BOUNDARY_TEST_STARTUP_TIMEOUT_MS: "3000",
    AGENTOPS_OPENCLAW_BOUNDARY_TEST_SHUTDOWN_GRACE_MS: "200",
    AGENTOPS_AGENT_TOKEN: secret,
    OPENAI_API_KEY: secret,
    OPENCLAW_BIN: "/fixture/openclaw",
    OPENCLAW_BIN_SHA256: "a".repeat(64),
    OPENCLAW_CONFIG_PATH: "/fixture/config",
    OPENCLAW_STATE_DIR: "/fixture/state",
    OPENCLAW_WORKSPACE: "/fixture/workspace",
    OPENCLAW_AGENT: "contract-agent",
    AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_GID: "2200",
    AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_UID: "1001",
    ...extra,
  };
}

function start(role, paths, options = {}) {
  const schema = role === "broker"
    ? "agentops_openclaw_broker_health_v1"
    : "agentops_openclaw_provider_health_v1";
  const backend = join(paths.fixture, "fake-backend.cjs");
  const gate = join(paths.fixture, "fake-gate.cjs");
  writeExecutable(backend, backendSource(paths, schema, options.backend));
  writeExecutable(gate, gateSource(paths, options.gate));
  for (const executable of [backend, gate]) {
    const checked = spawnSync(process.execPath, ["--check", executable], { encoding: "utf8" });
    assert.equal(checked.status, 0, checked.stderr);
  }
  const child = spawn(process.execPath, [supervisor], {
    env: environment(role, paths, backend, gate, options.environment),
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  child.stdout.on("data", (chunk) => { output += chunk.toString("utf8"); });
  child.stderr.on("data", (chunk) => { output += chunk.toString("utf8"); });
  return { child, output: () => output };
}

function waitForExit(child) {
  return new Promise((resolveExit) => {
    if (child.exitCode !== null) resolveExit(child.exitCode);
    else child.once("exit", resolveExit);
  });
}

function assertNoSecret(record) {
  const raw = readFileSync(record, "utf8");
  assert.doesNotMatch(raw, new RegExp(secret));
  return JSON.parse(raw);
}

async function successfulRole(role) {
  const paths = fixturePaths(`ok-${role}`);
  const process = start(role, paths, {
    backend: { descendants: true },
    gate: { descendants: true },
  });
  const statePath = role === "broker" ? paths.brokerState : paths.executorState;
  const internalSocket = role === "broker"
    ? paths.brokerInternalSocket
    : paths.executorInternalSocket;
  await waitFor(() => {
    if (process.child.exitCode !== null) {
      throw new Error(`${role}_supervisor_early_exit:${process.output()}`);
    }
    return existsSync(statePath);
  }, `${role}_ready_state`);
  const state = JSON.parse(readFileSync(statePath, "utf8"));
  assert.equal(state.ready, true);
  assert.equal(state.role, role);
  assert.equal(state.backend_health_verified, true);
  assert.equal(state.external_gate_health_verified, true);
  assert.equal(state.peercred_gate_process_started, true);
  assert.equal(state.peercred_runtime_verified, false);
  assert.equal(state.linux_peercred_gate_contract_verified, false);
  assert.equal(state.phase_a_a04_verified, false);
  assert.equal(state.phase_a_a05_verified, false);
  const events = readFileSync(paths.events, "utf8").trim().split("\n");
  assert.deepEqual(events.slice(0, 3), ["backend_started", "backend_ready", "gate_started"]);
  assert.ok(events.includes("gate_ready"));
  const gate = assertNoSecret(paths.gateRecord);
  const backend = assertNoSecret(paths.backendRecord);
  const expected = role === "broker"
    ? {
        listen: join(paths.fixture, "public", "broker.sock"),
        uid: "1000",
        gid: "2100",
      }
    : {
        listen: join(paths.fixture, "private", "executor.sock"),
        uid: "1100",
        gid: "2200",
      };
  assert.deepEqual(gate.argv, [
    "--listen", expected.listen,
    "--upstream", internalSocket,
    "--expected-uid", expected.uid,
    "--listen-gid", expected.gid,
  ]);
  const gateEnvironmentNames = Object.keys(gate.env)
    .filter((name) => name !== "__CF_USER_TEXT_ENCODING")
    .sort();
  assert.deepEqual(gateEnvironmentNames, ["LANG", "LC_ALL", "NODE_ENV", "PATH"].sort());
  assert.equal(
    backend.env[role === "broker"
      ? "AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_PATH"
      : "OPENCLAW_PROVIDER_SOCKET"],
    internalSocket,
  );
  const backendDescendant = Number(readFileSync(paths.backendPid, "utf8"));
  const gateDescendant = Number(readFileSync(paths.gatePid, "utf8"));
  process.child.kill("SIGTERM");
  assert.equal(await waitForExit(process.child), 0);
  await waitFor(() => processGone(backendDescendant), `${role}_backend_descendant_gone`);
  await waitFor(() => processGone(gateDescendant), `${role}_gate_descendant_gone`);
  assert.equal(existsSync(internalSocket), false);
  assert.equal(existsSync(statePath), false);
  assert.doesNotMatch(process.output(), new RegExp(secret));
}

try {
  const source = readFileSync(supervisor, "utf8");
  assert.match(source, /GATE_BINARY = "\/usr\/local\/bin\/agentops-openclaw-peercred-gate"/);
  assert.match(source, /"--expected-uid", String\(configuration\.expectedUid\)/);
  assert.match(source, /"--listen-gid", String\(configuration\.listenGid\)/);
  assert.match(source, /metadata\.uid !== process\.getuid\?\.\(\)/);
  assert.match(source, /metadata\.gid !== process\.getgid\?\.\(\)/);
  assert.match(source, /\(metadata\.mode & 0o777\) !== 0o700/);
  assert.doesNotMatch(source, /shell:\s*true|exec\(|execFile\(/);
  assert.doesNotMatch(source, /peercred_runtime_verified:\s*true/);
  assert.doesNotMatch(source, /phase_a_a0[45]_verified:\s*true/);

  const productionOverride = spawnSync(process.execPath, [supervisor], {
    encoding: "utf8",
    env: {
      PATH: process.env.PATH,
      NODE_ENV: "production",
      AGENTOPS_OPENCLAW_BOUNDARY_ROLE: "broker",
      AGENTOPS_OPENCLAW_BOUNDARY_TEST_GATE_PATH: "/tmp/fake-gate",
    },
  });
  assert.equal(productionOverride.status, 1);
  assert.match(productionOverride.stderr, /boundary_test_override_forbidden/);

  const unknownEnvironment = spawnSync(process.execPath, [supervisor], {
    encoding: "utf8",
    env: {
      PATH: process.env.PATH,
      NODE_ENV: "test",
      AGENTOPS_OPENCLAW_BOUNDARY_ROLE: "broker",
      AGENTOPS_OPENCLAW_BOUNDARY_UNKNOWN: "forbidden",
    },
  });
  assert.equal(unknownEnvironment.status, 1);
  assert.match(unknownEnvironment.stderr, /boundary_environment_unknown/);

  const unsafeRoot = fixturePaths("unsafe-root");
  chmodSync(join(unsafeRoot.fixture, "broker-backend"), 0o750);
  const unsafeRootProcess = start("broker", unsafeRoot);
  assert.equal(await waitForExit(unsafeRootProcess.child), 1);
  assert.match(unsafeRootProcess.output(), /boundary_internal_root_invalid/);
  assert.equal(existsSync(unsafeRoot.backendRecord), false);

  const early = fixturePaths("early-backend");
  const earlyProcess = start("broker", early, { backend: { earlyExit: true } });
  assert.equal(await waitForExit(earlyProcess.child), 1);
  assert.equal(existsSync(early.gateRecord), false);
  assert.equal(existsSync(early.brokerState), false);
  assert.match(earlyProcess.output(), /boundary_backend_health_child_exited/);
  assert.doesNotMatch(earlyProcess.output(), new RegExp(secret));

  const earlyGate = fixturePaths("early-gate");
  const earlyGateProcess = start("broker", earlyGate, { gate: { earlyExit: true } });
  assert.equal(await waitForExit(earlyGateProcess.child), 1);
  assert.equal(existsSync(earlyGate.brokerState), false);
  assert.equal(existsSync(earlyGate.brokerInternalSocket), false);
  assert.match(earlyGateProcess.output(), /boundary_gate_health_child_exited/);
  assert.doesNotMatch(earlyGateProcess.output(), new RegExp(secret));

  await successfulRole("broker");
  await successfulRole("executor");

  process.stdout.write(`${JSON.stringify({
    contract: "agentops_openclaw_boundary_supervisor_contract_v1",
    ok: true,
    modes_verified: ["broker", "executor"],
    backend_health_before_gate_verified: true,
    external_gate_health_verified: true,
    fixed_gate_argv_verified: true,
    gate_credential_environment_omitted: true,
    backend_environment_allowlisted: true,
    internal_root_process_identity_mode_0700_verified: true,
    production_test_override_rejected: true,
    early_backend_death_fail_closed: true,
    early_gate_death_fail_closed: true,
    bounded_group_shutdown_verified: true,
    descendant_cleanup_verified: true,
    internal_socket_and_state_cleanup_verified: true,
    raw_child_logs_omitted: true,
    peercred_runtime_verified: false,
    linux_peercred_gate_contract_verified: false,
    phase_a_a04_verified: false,
    phase_a_a05_verified: false,
  })}\n`);
} finally {
  rmSync(root, { recursive: true, force: true });
}
