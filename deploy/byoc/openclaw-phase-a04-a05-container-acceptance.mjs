#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import {
  chmodSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const CONTRACT = "agentops_openclaw_phase_a04_a05_container_acceptance_v1";
const PUBLIC_SOCKET = "/run/agentops-openclaw-public/broker.sock";
const PRIVATE_SOCKET = "/run/agentops-openclaw-private/executor.sock";
const IMAGE_DIGEST = /^[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}$/;
const REVISION = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const WRONG_UID = 65534;

function fail(code) {
  const error = new Error(code);
  error.code = code;
  throw error;
}

function option(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || index === process.argv.length - 1) {
    fail(`${name.slice(2).replaceAll("-", "_")}_required`);
  }
  return process.argv[index + 1];
}

function docker(
  args,
  {
    timeout = 60_000,
    accepted = [0],
    code = "docker_command_failed",
    environment = {},
  } = {},
) {
  const result = spawnSync("docker", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout,
    env: { ...process.env, ...environment },
  });
  if (result.error || !accepted.includes(result.status ?? -1)) fail(code);
  return result.stdout;
}

function compose(composeFiles, project, environment, args, options = {}) {
  const files = Array.isArray(composeFiles) ? composeFiles : [composeFiles];
  return docker([
    "compose",
    ...files.flatMap((file) => ["-f", file]),
    "-p",
    project,
    ...args,
  ], { ...options, environment });
}

const SUPERVISOR_STARTUP_ERROR_CODES = new Set([
  "boundary_backend_health_child_exited",
  "boundary_backend_health_spawn_failed",
  "boundary_backend_health_timeout",
  "boundary_backend_exit",
  "boundary_child_groups_not_empty",
  "boundary_environment_unknown",
  "boundary_gate_exit",
  "boundary_gate_listener_child_exited",
  "boundary_gate_listener_spawn_failed",
  "boundary_gate_listener_timeout",
  "boundary_internal_cleanup_failed",
  "boundary_internal_root_invalid",
  "boundary_internal_root_unavailable",
  "boundary_internal_state_not_clean",
  "boundary_role_invalid",
  "boundary_shutdown_requested_during_startup",
  "boundary_shutdown_grace_ms_invalid",
  "boundary_startup_timeout_ms_invalid",
  "boundary_test_override_forbidden",
  "openclaw_boundary_supervisor_failed",
]);

function boundedComposeStartupDiagnostics(composeFiles, project, environment) {
  let rows = [];
  try {
    const output = compose(
      composeFiles,
      project,
      environment,
      ["ps", "--all", "--format", "json"],
      { accepted: [0, 1], code: "compose_diagnostics_unavailable" },
    ).trim();
    let parsed = [];
    if (output.startsWith("[")) {
      const value = JSON.parse(output);
      parsed = Array.isArray(value) ? value : [];
    } else if (output) {
      parsed = output.split("\n").flatMap((line) => {
        try {
          const value = JSON.parse(line);
          return value && typeof value === "object" && !Array.isArray(value) ? [value] : [];
        } catch {
          return [];
        }
      });
    }
    rows = parsed.slice(0, 3).map((value) => {
      const id = String(value.ID || "");
      let fixedCodes = [];
      if (/^[a-f0-9]{12,64}$/.test(id)) {
        const logged = spawnSync("docker", ["logs", "--tail", "20", id], {
          encoding: "utf8",
          stdio: ["ignore", "pipe", "pipe"],
          timeout: 5_000,
          env: process.env,
        });
        fixedCodes = `${logged.stdout || ""}\n${logged.stderr || ""}`.split("\n")
          .map((line) => line.trim())
          .filter((line) => SUPERVISOR_STARTUP_ERROR_CODES.has(line))
          .slice(-3);
      }
      const rawExitCode = value.ExitCode;
      const exitCode = rawExitCode === undefined || rawExitCode === null || rawExitCode === ""
        ? null
        : Number(rawExitCode);
      return {
        service: String(value.Service || "").slice(0, 40),
        state: String(value.State || "").slice(0, 20),
        health: String(value.Health || "").slice(0, 20),
        exit_code: Number.isSafeInteger(exitCode) ? exitCode : null,
        fixed_error_codes: fixedCodes,
      };
    });
  } catch {
    rows = [];
  }
  process.stderr.write(`${JSON.stringify({
    contract: "agentops_openclaw_a04_a05_startup_diagnostics_v1",
    services: rows,
    credentials_omitted: true,
    raw_logs_omitted: true,
  })}\n`);
}

function waitFor(label, probe, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const value = probe();
      if (value) return value;
    } catch {
      // Container startup races stay bounded by the deadline.
    }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100);
  }
  fail(`${label}_timeout`);
}

function inspectContainer(id) {
  return JSON.parse(docker(["inspect", id]))[0];
}

function serviceContainer(composeFiles, project, environment, service) {
  return waitFor(`${service}_container`, () => {
    const id = compose(
      composeFiles,
      project,
      environment,
      ["ps", "--all", "--quiet", service],
    ).trim();
    return /^[0-9a-f]{12,64}$/.test(id) ? id : null;
  });
}

function execJson(container, source, { user = null, environment = {} } = {}) {
  const args = ["exec"];
  if (user) args.push("--user", user);
  for (const [name, value] of Object.entries(environment)) {
    args.push("--env", `${name}=${value}`);
  }
  args.push(container, "node", "-e", source);
  return JSON.parse(docker(args, { code: "container_probe_failed" }));
}

const protocolProbe = String.raw`
const crypto=require("node:crypto");const http=require("node:http");
const prompt="A04 A05 peer credential round trip fixture.";
const body=JSON.stringify({schema:"agentops_openclaw_provider_request_v1",agent_name:"acceptance-a04-a05",prompt,prompt_hash:crypto.createHash("sha256").update(prompt).digest("hex"),timeout_seconds:10});
const req=http.request({socketPath:"/run/agentops-openclaw-public/broker.sock",path:"/v1/execute",method:"POST",headers:{"content-type":"application/json","content-length":Buffer.byteLength(body),connection:"close"}},res=>{
 const chunks=[];let size=0;res.on("data",chunk=>{size+=chunk.length;if(size>1048576)req.destroy();else chunks.push(chunk)});res.on("end",()=>{let value;try{value=JSON.parse(Buffer.concat(chunks).toString("utf8"))}catch{process.exit(3)}
 const ok=res.statusCode===200&&value.schema==="agentops_openclaw_provider_response_v1"&&value.ok===true&&value.provider_call_performed===true&&value.dry_run===false&&value.raw_prompt_omitted===true&&value.raw_response_omitted===true;
 process.stdout.write(JSON.stringify({ok,status:res.statusCode,provider_call_performed:value.provider_call_performed===true,dry_run:value.dry_run===true,raw_prompt_omitted:value.raw_prompt_omitted===true,raw_response_omitted:value.raw_response_omitted===true}));if(!ok)process.exitCode=4;
 });
});req.setTimeout(15000,()=>req.destroy());req.on("error",()=>process.exit(2));req.end(body);
`;

const forbiddenPathProbe = String.raw`
const fs=require("node:fs");const accepted=new Set(["ENOENT","EACCES","EPERM","EROFS","ENXIO","ENODEV"]);const paths=JSON.parse(process.env.A04_A05_PATHS);let denied=0;
for(const path of paths){let read="success",open="success";try{fs.readFileSync(path)}catch(error){read=String(error.code||"UNKNOWN")}try{const fd=fs.openSync(path,fs.constants.O_RDONLY);fs.closeSync(fd)}catch(error){open=String(error.code||"UNKNOWN")}if(!accepted.has(read)||!accepted.has(open))process.exit(3);denied+=1}
process.stdout.write(JSON.stringify({ok:true,denied}));
`;

const mutationProbe = String.raw`
const fs=require("node:fs");let code="success";try{fs.writeFileSync("/run/agentops-openclaw-private/broker-mutation",Buffer.from([1]),{flag:"wx"})}catch(error){code=String(error.code||"UNKNOWN")}const ok=new Set(["EROFS","EACCES","EPERM"]).has(code);process.stdout.write(JSON.stringify({ok,code}));if(!ok)process.exitCode=3;
`;

const backendProcessProbe = String.raw`
const fs=require("node:fs");const marker=process.argv[1];let matches=[];
for(const name of fs.readdirSync("/proc")){if(!/^\d+$/.test(name))continue;try{const command=fs.readFileSync("/proc/"+name+"/cmdline").toString("utf8");if(command.includes(marker)){matches.push({pid:Number(name),fds:fs.readdirSync("/proc/"+name+"/fd").length})}}catch{}}
if(matches.length!==1)process.exit(3);process.stdout.write(JSON.stringify(matches[0]));
`;

const socketMetadataProbe = String.raw`
const fs=require("node:fs");const path=process.argv[1];const uid=Number(process.argv[2]);const gid=Number(process.argv[3]);try{const value=fs.lstatSync(path);if(!value.isSocket()||value.uid!==uid||value.gid!==gid||(value.mode&0o777)!==0o660)process.exit(3)}catch{process.exit(4)}
`;

const wrongPeerProbe = String.raw`
const net=require("node:net");const socket=process.argv[1];let received=0;let connected=false;const client=net.createConnection({path:socket});
client.once("connect",()=>{connected=true;client.write("POST /v1/execute HTTP/1.1\r\nContent-Type: application/json\r\nContent-Length: 4096\r\nConnection: keep-alive\r\n\r\n{");process.stdout.write("READY\n")});
client.on("data",chunk=>{received+=chunk.length});client.on("error",()=>{});setTimeout(()=>{client.destroy();process.stdout.write(JSON.stringify({connected,received_bytes:received})+"\n");process.exit(0)},2500);
`;

function backendProcessState(container, marker) {
  const output = docker([
    "exec",
    container,
    "node",
    "-e",
    backendProcessProbe,
    marker,
  ], { code: "backend_process_probe_failed" });
  const value = JSON.parse(output);
  if (!Number.isSafeInteger(value.pid) || !Number.isSafeInteger(value.fds)) {
    fail("backend_process_probe_invalid");
  }
  return value;
}

async function runWrongPeerAttack({
  name,
  image,
  volumesFrom,
  uid,
  gid,
  socket,
  backendContainer,
  backendMarker,
}) {
  const baseline = backendProcessState(backendContainer, backendMarker);
  const child = spawn("docker", [
    "run",
    "--name", name,
    "--read-only",
    "--network", "none",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges:true",
    "--user", `${uid}:${gid}`,
    "--volumes-from", `${volumesFrom}:ro`,
    "--entrypoint", "node",
    image,
    "-e",
    wrongPeerProbe,
    socket,
  ], {
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "";
  child.stdout.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
  const exited = new Promise((resolveExit) => child.once("exit", resolveExit));
  await new Promise((resolveReady, rejectReady) => {
    const deadline = Date.now() + 10_000;
    const poll = () => {
      if (stdout.includes("READY\n")) resolveReady();
      else if (child.exitCode !== null) rejectReady(new Error("wrong_peer_attacker_early_exit"));
      else if (Date.now() >= deadline) {
        child.kill("SIGKILL");
        rejectReady(new Error("wrong_peer_attacker_ready_timeout"));
      } else setTimeout(poll, 25);
    };
    poll();
  });
  let maximumFds = baseline.fds;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const observed = backendProcessState(backendContainer, backendMarker);
    if (observed.pid !== baseline.pid) fail("backend_process_identity_changed");
    maximumFds = Math.max(maximumFds, observed.fds);
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 50);
  }
  if (await exited !== 0) fail("wrong_peer_attacker_failed");
  const lines = stdout.trim().split("\n");
  const result = JSON.parse(lines.at(-1) || "{}");
  if (result.connected !== true || result.received_bytes !== 0) {
    fail("wrong_peer_rejection_invalid");
  }
  const after = backendProcessState(backendContainer, backendMarker);
  if (
    after.pid !== baseline.pid
    || maximumFds !== baseline.fds
    || after.fds !== baseline.fds
  ) fail("wrong_peer_backend_connection_observed");
  return {
    connected: true,
    receivedBytes: 0,
    backendProcessIdentityUnchanged: true,
    backendFdBaseline: baseline.fds,
    backendFdMaximum: maximumFds,
  };
}

function createFixture(root) {
  const runtime = join(root, "runtime");
  const bin = join(runtime, "bin");
  const workspace = join(root, "workspace");
  const config = join(root, "openclaw-config.json");
  const signing = join(root, "receipt-signing-key");
  mkdirSync(bin, { recursive: true, mode: 0o755 });
  mkdirSync(workspace, { mode: 0o755 });
  const sentinel = randomBytes(24).toString("hex");
  writeFileSync(config, `${JSON.stringify({ fixture: "a04-a05", sentinel })}\n`, { mode: 0o444 });
  writeFileSync(join(workspace, "executor-only"), `${sentinel}\n`, { mode: 0o444 });
  writeFileSync(signing, `${randomBytes(32).toString("hex")}\n`, { mode: 0o444 });
  const executable = join(bin, "openclaw");
  writeFileSync(executable, `#!/usr/bin/env node\nconst fs=require("node:fs");if(process.getuid?.()!==1001)process.exit(21);if(!fs.readFileSync(process.env.OPENCLAW_CONFIG_PATH,"utf8").includes(${JSON.stringify(sentinel)}))process.exit(22);if(fs.readFileSync("/opt/agentops-worker/workspace/executor-only","utf8").trim()!==${JSON.stringify(sentinel)})process.exit(23);process.stdout.write(JSON.stringify({result:{meta:{durationMs:5,finalAssistantVisibleText:"fixture response"},payloads:[{text:"fixture response"}]}}));\n`, { mode: 0o555 });
  chmodSync(executable, 0o555);
  return {
    runtime,
    workspace,
    config,
    signing,
    binarySha256: createHash("sha256").update(readFileSync(executable)).digest("hex"),
  };
}

function resolveImage(image, revision) {
  const inspected = JSON.parse(docker(["image", "inspect", image]))[0];
  const id = String(inspected?.Id || "");
  const label = String(inspected?.Config?.Labels?.["org.opencontainers.image.revision"] || "");
  const digests = Array.isArray(inspected?.RepoDigests) ? inspected.RepoDigests : [];
  if (!/^sha256:[0-9a-f]{64}$/.test(id)) fail("resolved_image_id_invalid");
  if (label !== revision) fail("image_source_revision_label_mismatch");
  if (!digests.includes(image)) fail("exact_image_digest_not_resolved");
  return { id, revision: label };
}

function verifySource(sourceRoot, revision) {
  const head = spawnSync("git", ["-C", sourceRoot, "rev-parse", "HEAD"], {
    encoding: "utf8",
  }).stdout.trim();
  if (head !== revision) fail("source_revision_mismatch");
  const tracked = spawnSync("git", ["-C", sourceRoot, "diff-index", "--quiet", "HEAD", "--"]);
  const untracked = spawnSync(
    "git",
    ["-C", sourceRoot, "ls-files", "--others", "--exclude-standard"],
    { encoding: "utf8" },
  ).stdout.trim();
  if (tracked.status !== 0 || untracked) fail("source_worktree_not_clean");
}

function verifyPeercredBeforeUpstreamConnect(sourceRoot) {
  const source = readFileSync(
    join(sourceRoot, "deploy/byoc/openclaw-peercred-gate.c"),
    "utf8",
  );
  const peercredCheck = source.indexOf("getsockopt(client_fd, SOL_SOCKET, SO_PEERCRED");
  const expectedUidCheck = source.indexOf("peer.uid != expected_uid", peercredCheck);
  const rejectionClose = source.indexOf("(void)close(client_fd);", expectedUidCheck);
  const upstreamConnect = source.indexOf(
    "upstream_fd = connect_upstream(upstream_path",
    peercredCheck,
  );
  if (
    peercredCheck < 0
    || expectedUidCheck < peercredCheck
    || rejectionClose < expectedUidCheck
    || upstreamConnect < rejectionClose
  ) fail("peercred_before_upstream_connect_contract_invalid");
}

function assertContainerBoundary(inspect, expected) {
  assert.equal(inspect.Config.User, expected.user);
  assert.deepEqual(inspect.HostConfig.GroupAdd, expected.groups);
  assert.equal(inspect.HostConfig.ReadonlyRootfs, true);
  assert.equal(inspect.HostConfig.NetworkMode, expected.networkMode);
  assert.equal(inspect.Image, expected.imageId);
  const destinations = new Set(inspect.Mounts.map((mount) => mount.Destination));
  for (const required of expected.requiredMounts) assert.ok(destinations.has(required));
  for (const forbidden of expected.forbiddenMounts) assert.equal(destinations.has(forbidden), false);
}

async function main() {
  const image = option("--image");
  if (!IMAGE_DIGEST.test(image)) fail("immutable_image_digest_required");
  const sourceRoot = resolve(option("--source-root"));
  const sourceRevision = option("--source-revision");
  if (!REVISION.test(sourceRevision)) fail("source_revision_invalid");
  verifySource(sourceRoot, sourceRevision);
  verifyPeercredBeforeUpstreamConnect(sourceRoot);
  const imageIdentity = resolveImage(image, sourceRevision);
  if (docker(["info", "--format", "{{.OSType}}"]).trim() !== "linux") {
    fail("linux_docker_required");
  }

  const composeFile = join(sourceRoot, "deploy/byoc/compose.openclaw-phase-a04-a05.yaml");
  const root = mkdtempSync(join(tmpdir(), "agentops-openclaw-a04-a05-"));
  chmodSync(root, 0o755);
  const composeFiles = [composeFile];
  const fixture = createFixture(root);
  if (!SHA256.test(fixture.binarySha256)) fail("fixture_binary_digest_invalid");
  const suffix = `${process.pid}-${randomBytes(4).toString("hex")}`;
  const project = `agentops-a04-a05-${suffix}`;
  const publicAttacker = `${project}-wrong-public-peer`;
  const privateAttacker = `${project}-wrong-private-peer`;
  const environment = {
    AGENTOPS_A04_A05_IMAGE: image,
    AGENTOPS_A04_A05_RUNTIME_PATH: fixture.runtime,
    AGENTOPS_A04_A05_CONFIG_PATH: fixture.config,
    AGENTOPS_A04_A05_WORKSPACE_PATH: fixture.workspace,
    AGENTOPS_A04_A05_SIGNING_KEY_PATH: fixture.signing,
    AGENTOPS_A04_A05_OPENCLAW_BIN_SHA256: fixture.binarySha256,
  };
  let receipt = null;
  let dockerCleanup = false;
  let localCleanup = false;
  try {
    const composeConfiguration = JSON.parse(compose(
      composeFiles,
      project,
      environment,
      ["config", "--format", "json"],
    ));
    if (
      composeConfiguration.services?.broker?.depends_on?.executor?.condition
        !== "service_healthy"
      || !composeConfiguration.services?.executor?.healthcheck
    ) fail("production_compose_health_ordering_invalid");
    let worker;
    let broker;
    let executor;
    try {
      compose(
        composeFiles,
        project,
        environment,
        ["up", "--detach", "--no-build"],
        { timeout: 120_000, code: "production_compose_start_failed" },
      );
      worker = serviceContainer(composeFiles, project, environment, "worker");
      broker = serviceContainer(composeFiles, project, environment, "broker");
      executor = serviceContainer(composeFiles, project, environment, "executor");
      waitFor("services_running", () => [worker, broker, executor].every((id) => (
        inspectContainer(id).State.Running === true
      )));
      waitFor("peercred_gate_sockets_ready", () => {
        docker([
          "exec", worker, "node", "-e", socketMetadataProbe,
          PUBLIC_SOCKET, "1100", "2100",
        ], { timeout: 5_000, code: "public_gate_socket_not_ready" });
        docker([
          "exec", broker, "node", "-e", socketMetadataProbe,
          PRIVATE_SOCKET, "1001", "2200",
        ], { timeout: 5_000, code: "private_gate_socket_not_ready" });
        return true;
      });
    } catch {
      boundedComposeStartupDiagnostics(composeFiles, project, environment);
      fail("production_compose_start_failed");
    }
    if (docker(["exec", worker, "uname", "-s"]).trim() !== "Linux") {
      fail("linux_container_kernel_required");
    }

    const workerInspect = inspectContainer(worker);
    const brokerInspect = inspectContainer(broker);
    const executorInspect = inspectContainer(executor);
    if (executorInspect.State.Health?.Status !== "healthy") {
      fail("production_executor_not_healthy");
    }
    const runtimePaths = [
      "/opt/agentops-provider/openclaw",
      "/run/secrets/openclaw_config",
      "/opt/agentops-worker/workspace",
      "/run/secrets/openclaw_receipt_signing_key",
    ];
    assertContainerBoundary(workerInspect, {
      user: "1000:1000",
      groups: ["2100"],
      networkMode: "none",
      imageId: imageIdentity.id,
      requiredMounts: ["/run/agentops-openclaw-public"],
      forbiddenMounts: ["/run/agentops-openclaw-private", ...runtimePaths],
    });
    assertContainerBoundary(brokerInspect, {
      user: "1100:1100",
      groups: ["2100", "2200"],
      networkMode: "none",
      imageId: imageIdentity.id,
      requiredMounts: [
        "/run/agentops-openclaw-public",
        "/run/agentops-openclaw-private",
      ],
      forbiddenMounts: runtimePaths,
    });
    assertContainerBoundary(executorInspect, {
      user: "1001:1000",
      groups: ["2200"],
      networkMode: Object.keys(executorInspect.NetworkSettings.Networks)[0],
      imageId: imageIdentity.id,
      requiredMounts: ["/run/agentops-openclaw-private", ...runtimePaths],
      forbiddenMounts: ["/run/agentops-openclaw-public"],
    });
    assert.equal(Object.keys(executorInspect.NetworkSettings.Networks).length, 1);
    assert.ok(Object.keys(executorInspect.NetworkSettings.Networks)[0].endsWith("provider-egress"));

    const workerDenials = execJson(worker, forbiddenPathProbe, {
      environment: {
        A04_A05_PATHS: JSON.stringify([
          PRIVATE_SOCKET,
          "/opt/agentops-provider/openclaw/bin/openclaw",
          "/run/secrets/openclaw_config",
          "/opt/agentops-worker/workspace/executor-only",
          "/run/secrets/openclaw_receipt_signing_key",
        ]),
      },
    });
    const brokerDenials = execJson(broker, forbiddenPathProbe, {
      environment: {
        A04_A05_PATHS: JSON.stringify([
          "/opt/agentops-provider/openclaw/bin/openclaw",
          "/run/secrets/openclaw_config",
          "/opt/agentops-worker/workspace/executor-only",
          "/run/secrets/openclaw_receipt_signing_key",
        ]),
      },
    });
    const brokerMutation = execJson(broker, mutationProbe);
    if (!workerDenials.ok || workerDenials.denied !== 5) fail("worker_path_denials_invalid");
    if (!brokerDenials.ok || brokerDenials.denied !== 4) fail("broker_path_denials_invalid");
    if (!brokerMutation.ok) fail("broker_private_directory_mutation_allowed");

    const publicAttack = await runWrongPeerAttack({
      name: publicAttacker,
      image,
      volumesFrom: worker,
      uid: WRONG_UID,
      gid: 2100,
      socket: PUBLIC_SOCKET,
      backendContainer: broker,
      backendMarker: "openclaw-broker-entrypoint.mjs",
    });
    const privateAttack = await runWrongPeerAttack({
      name: privateAttacker,
      image,
      volumesFrom: broker,
      uid: WRONG_UID,
      gid: 2200,
      socket: PRIVATE_SOCKET,
      backendContainer: executor,
      backendMarker: "openclaw-provider-entrypoint.mjs",
    });
    const protocol = execJson(worker, protocolProbe);
    if (!protocol.ok) fail("a04_a05_round_trip_failed");

    receipt = {
      ok: true,
      contract: CONTRACT,
      kernel: "Linux",
      source_commit: sourceRevision,
      image_digest: image,
      resolved_image_id: imageIdentity.id,
      image_source_revision: imageIdentity.revision,
      image_digest_verified: true,
      image_source_revision_verified: true,
      candidate_source_only: true,
      real_linux_docker_execution: true,
      real_linux_docker_compose_execution: true,
      peercred_gate_socket_metadata_ready_before_attacks: true,
      production_executor_healthcheck_verified: true,
      production_executor_before_broker_ordering_verified: true,
      phase_a04_public_peercred_verified: true,
      phase_a05_private_peercred_verified: true,
      so_peercred_verified: true,
      kernel_so_peercred_verified: true,
      public_expected_uid: 1000,
      private_expected_uid: 1100,
      wrong_public_peer_uid: WRONG_UID,
      wrong_private_peer_uid: WRONG_UID,
      wrong_public_peer_response_bytes_received: publicAttack.receivedBytes,
      wrong_private_peer_response_bytes_received: privateAttack.receivedBytes,
      public_backend_process_identity_unchanged: publicAttack.backendProcessIdentityUnchanged,
      private_backend_process_identity_unchanged: privateAttack.backendProcessIdentityUnchanged,
      public_backend_fd_delta:
        publicAttack.backendFdMaximum - publicAttack.backendFdBaseline,
      private_backend_fd_delta:
        privateAttack.backendFdMaximum - privateAttack.backendFdBaseline,
      public_wrong_uid_rejected_before_backend_connection: true,
      private_wrong_uid_rejected_before_backend_connection: true,
      peercred_check_precedes_upstream_connect_contract_verified: true,
      worker_broker_gate_broker_executor_gate_provider_round_trip_verified: true,
      provider_call_performed: protocol.provider_call_performed,
      dry_run: protocol.dry_run,
      worker_private_runtime_config_workspace_signing_denials: workerDenials.denied,
      broker_runtime_config_workspace_signing_denials: brokerDenials.denied,
      broker_private_socket_directory_mutation_denied: true,
      interim_provider_identity: true,
      runtime_receipt_verified: false,
      product_worker_started: false,
      worker_attack_probe_container: true,
      attack_probe_worker_used: true,
      real_openclaw_runtime_execution: false,
      fixture_openclaw_runtime_execution: true,
      raw_prompt_omitted: protocol.raw_prompt_omitted,
      raw_response_omitted: protocol.raw_response_omitted,
      secrets_omitted: true,
      hostile_runtime_isolation_verified: false,
      remaining_hostile_runtime_rows_verified: false,
    };
  } finally {
    for (const attacker of [publicAttacker, privateAttacker]) {
      docker(["rm", "--force", attacker], { accepted: [0, 1], code: "attacker_cleanup_failed" });
    }
    try {
      compose(
        composeFiles,
        project,
        environment,
        ["down", "--volumes", "--remove-orphans", "--timeout", "10"],
        { timeout: 90_000 },
      );
      const containers = docker([
        "container", "ls", "--all", "--quiet", "--filter",
        `label=com.docker.compose.project=${project}`,
      ]).trim();
      const volumes = docker([
        "volume", "ls", "--quiet", "--filter",
        `label=com.docker.compose.project=${project}`,
      ]).trim();
      const networks = docker([
        "network", "ls", "--quiet", "--filter",
        `label=com.docker.compose.project=${project}`,
      ]).trim();
      const attackers = docker([
        "container", "ls", "--all", "--quiet", "--filter",
        `name=^/${project}-wrong-`,
      ]).trim();
      dockerCleanup = !containers && !volumes && !networks && !attackers;
    } finally {
      rmSync(root, { recursive: true, force: true });
      localCleanup = !existsSync(root);
    }
    if (!dockerCleanup) fail("docker_cleanup_unverified");
    if (!localCleanup) fail("local_fixture_cleanup_unverified");
  }
  if (!receipt) fail("acceptance_receipt_unavailable");
  receipt.containers_cleaned = true;
  receipt.attacker_containers_cleaned = true;
  receipt.networks_cleaned = true;
  receipt.volumes_cleaned = true;
  receipt.local_fixture_cleaned = true;
  receipt.cleanup_confirmed = true;
  receipt.docker_network_cleanup_verified = true;
  receipt.docker_volume_cleanup_verified = true;
  const serialized = `${JSON.stringify(receipt)}\n`;
  if (Buffer.byteLength(serialized) > 16 * 1024) fail("receipt_too_large");
  process.stdout.write(serialized);
}

main().catch((error) => {
  const code = typeof error?.code === "string"
    && /^[a-z][a-z0-9_]{2,100}$/.test(error.code)
    ? error.code
    : "openclaw_phase_a04_a05_acceptance_failed";
  process.stderr.write(`${code}\n`);
  process.exitCode = 1;
});
