#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
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

const CONTRACT = "agentops_openclaw_phase_a03_container_acceptance_v1";
const PUBLIC_SOCKET = "/run/agentops-openclaw-public/broker.sock";
const PRIVATE_SOCKET = "/run/agentops-openclaw-private/executor.sock";
const IMAGE = /^[a-z0-9][a-z0-9._:/-]*(?:@sha256:[0-9a-f]{64}|:[A-Za-z0-9._-]+)$/;
const SHA256 = /^[0-9a-f]{64}$/;

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

function compose(composeFile, project, environment, args, options = {}) {
  return docker([
    "compose",
    "-f",
    composeFile,
    "-p",
    project,
    ...args,
  ], { ...options, environment });
}

function waitFor(label, probe, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const value = probe();
      if (value) return value;
    } catch {
      // Startup races are bounded by the deadline.
    }
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 250);
  }
  fail(`${label}_timeout`);
}

function inspectContainer(name) {
  return JSON.parse(docker(["inspect", name]))[0];
}

function mountsByDestination(inspect) {
  return new Map(inspect.Mounts.map((mount) => [mount.Destination, mount]));
}

function execJson(name, source, code = "container_probe_failed") {
  const output = docker(["exec", name, "node", "-e", source], { code });
  return JSON.parse(output);
}

const healthProbe = String.raw`
const http=require("node:http");
const socket=process.argv[1];
const req=http.request({socketPath:socket,path:"/health",method:"GET"},res=>{
  const chunks=[];res.on("data",c=>chunks.push(c));res.on("end",()=>{
    let body={};try{body=JSON.parse(Buffer.concat(chunks).toString("utf8"))}catch{}
    process.stdout.write(JSON.stringify({status:res.statusCode,ok:body.ok===true,ready:body.ready===true,so_peercred_verified:body.so_peercred_verified===true}));
  });
});req.on("error",()=>process.exit(2));req.end();
`;

const forbiddenOpenProbe = String.raw`
const fs=require("node:fs");
const accepted=new Set(["ENOENT","EACCES","EPERM","EROFS","ENXIO","ENODEV"]);
const paths=JSON.parse(process.env.A03_FORBIDDEN_PATHS);
const results={};
for(const path of paths){
  let readCode="unexpected_success";let openCode="unexpected_success";
  try{fs.readFileSync(path)}catch(error){readCode=String(error.code||"UNKNOWN")}
  try{const fd=fs.openSync(path,fs.constants.O_RDONLY);fs.closeSync(fd)}catch(error){openCode=String(error.code||"UNKNOWN")}
  if(!accepted.has(readCode)||!accepted.has(openCode))process.exit(3);
  results[path]={read:readCode,open:openCode};
}
process.stdout.write(JSON.stringify({ok:true,count:paths.length,results}));
`;

const readOnlyMutationProbe = String.raw`
const fs=require("node:fs");
const path=process.env.A03_MUTATION_PATH;
let code="unexpected_success";
try{fs.writeFileSync(path,"forbidden",{flag:"wx"})}catch(error){code=String(error.code||"UNKNOWN")}
if(!new Set(["EROFS","EACCES","EPERM"]).has(code))process.exit(3);
process.stdout.write(JSON.stringify({ok:true,code}));
`;

const protocolProbe = String.raw`
const crypto=require("node:crypto");const http=require("node:http");
const prompt="A03 container topology protocol fixture.";
const body=JSON.stringify({schema:"agentops_openclaw_provider_request_v1",agent_name:"acceptance-a03",prompt,prompt_hash:crypto.createHash("sha256").update(prompt).digest("hex"),timeout_seconds:10});
const req=http.request({socketPath:"/run/agentops-openclaw-public/broker.sock",path:"/v1/execute",method:"POST",headers:{"content-type":"application/json","content-length":Buffer.byteLength(body)}},res=>{
 const chunks=[];res.on("data",c=>chunks.push(c));res.on("end",()=>{let value;try{value=JSON.parse(Buffer.concat(chunks).toString("utf8"))}catch{process.exit(3)}
 const ok=res.statusCode===200&&value.schema==="agentops_openclaw_provider_response_v1"&&value.ok===true&&value.provider_call_performed===true&&value.dry_run===false&&value.raw_prompt_omitted===true&&value.raw_response_omitted===true;
 process.stdout.write(JSON.stringify({ok,status:res.statusCode,schema:value.schema,provider_call_performed:value.provider_call_performed===true,dry_run:value.dry_run===true,raw_prompt_omitted:value.raw_prompt_omitted===true,raw_response_omitted:value.raw_response_omitted===true}));if(!ok)process.exitCode=4;
 });
});req.on("error",()=>process.exit(2));req.end(body);
`;

function createFixture(root) {
  const runtime = join(root, "runtime");
  const bin = join(runtime, "bin");
  const workspace = join(root, "workspace");
  const config = join(root, "openclaw-config.json");
  const signing = join(root, "receipt-signing-key");
  mkdirSync(bin, { recursive: true, mode: 0o755 });
  mkdirSync(workspace, { mode: 0o755 });
  const sentinel = randomBytes(24).toString("hex");
  writeFileSync(config, `${JSON.stringify({ fixture: "a03", sentinel })}\n`, { mode: 0o444 });
  writeFileSync(join(workspace, "executor-only"), `${sentinel}\n`, { mode: 0o444 });
  writeFileSync(signing, `${randomBytes(32).toString("hex")}\n`, { mode: 0o444 });
  const executable = join(bin, "openclaw");
  writeFileSync(executable, `#!/usr/bin/env node\nconst fs=require("node:fs");\nif(process.getuid?.()!==1001)process.exit(21);\nif(!fs.readFileSync(process.env.OPENCLAW_CONFIG_PATH,"utf8").includes(${JSON.stringify(sentinel)}))process.exit(22);\nif(fs.readFileSync("/opt/agentops-worker/workspace/executor-only","utf8").trim()!==${JSON.stringify(sentinel)})process.exit(23);\nif(!fs.readFileSync("/run/secrets/openclaw_receipt_signing_key","utf8").trim())process.exit(24);\nprocess.stdout.write(JSON.stringify({result:{meta:{durationMs:5,finalAssistantVisibleText:"a03 protocol fixture response"},payloads:[{text:"a03 protocol fixture response"}]}}));\n`, { mode: 0o555 });
  chmodSync(executable, 0o555);
  return {
    runtime,
    workspace,
    config,
    signing,
    binarySha256: createHash("sha256").update(readFileSync(executable)).digest("hex"),
  };
}

function verifyComposeModel(composeFile, project, environment) {
  const model = JSON.parse(compose(composeFile, project, environment, ["config", "--format", "json"]));
  const worker = model.services.worker;
  const broker = model.services.broker;
  const executor = model.services.executor;
  assert.equal(worker.user, "1000:1000");
  assert.equal(broker.user, "1100:1100");
  assert.equal(executor.user, "1001:1000");
  assert.deepEqual(worker.group_add, ["2100"]);
  assert.deepEqual(broker.group_add, ["2100", "2200"]);
  assert.deepEqual(executor.group_add, ["2200"]);
  assert.equal(worker.network_mode, "none");
  assert.equal(broker.network_mode, "none");
  assert.deepEqual(Object.keys(executor.networks), ["provider-egress"]);
  assert.equal(Object.keys(model.services).length, 3);
  return true;
}

function resolveImageIdentity(image, expectedRevision) {
  const inspected = JSON.parse(docker(["image", "inspect", image]))[0];
  const id = String(inspected?.Id || "");
  const revision = String(
    inspected?.Config?.Labels?.["org.opencontainers.image.revision"] || "",
  );
  if (!/^sha256:[0-9a-f]{64}$/.test(id)) fail("resolved_image_id_invalid");
  if (revision !== expectedRevision) fail("image_source_revision_label_mismatch");
  return { id, revision };
}

function assertMount(mounts, destination, rw) {
  const mount = mounts.get(destination);
  assert.ok(mount, `mount_missing:${destination}`);
  assert.equal(mount.RW, rw, `mount_rw_invalid:${destination}`);
}

function assertMountDestinationAllowlist(inspect, allowedDestinations) {
  const allowed = new Set(allowedDestinations);
  for (const mount of inspect.Mounts) {
    assert.ok(allowed.has(mount.Destination), `mount_destination_forbidden:${mount.Destination}`);
  }
}

function assertTmpfsAllowlist(inspect, expectedDestinations) {
  const tmpfs = inspect.HostConfig.Tmpfs || {};
  assert.deepEqual(Object.keys(tmpfs).sort(), [...expectedDestinations].sort());
  const forbidden = [
    "/run/agentops-openclaw-public",
    "/run/agentops-openclaw-private",
    "/opt/agentops-provider/openclaw",
    "/run/secrets/openclaw_config",
    "/opt/agentops-worker/workspace",
    "/run/secrets/openclaw_receipt_signing_key",
  ];
  for (const destination of forbidden) {
    assert.equal(Object.hasOwn(tmpfs, destination), false);
  }
}

async function mainAcceptance() {
  const image = option("--image");
  if (!IMAGE.test(image)) fail("image_reference_invalid");
  const sourceRoot = resolve(option("--source-root"));
  const expectedRevision = option("--source-revision");
  if (!/^[0-9a-f]{40}$/.test(expectedRevision)) fail("source_revision_invalid");
  const actualRevision = spawnSync("git", ["-C", sourceRoot, "rev-parse", "HEAD"], { encoding: "utf8" }).stdout.trim();
  if (actualRevision !== expectedRevision) fail("source_revision_mismatch");
  const imageIdentity = resolveImageIdentity(image, expectedRevision);
  const composeFile = join(sourceRoot, "deploy/byoc/compose.openclaw-phase-a03.yaml");
  const root = mkdtempSync(join(tmpdir(), "agentops-openclaw-a03-"));
  chmodSync(root, 0o755);
  const fixture = createFixture(root);
  assert.ok(SHA256.test(fixture.binarySha256));
  const suffix = `${process.pid}-${randomBytes(4).toString("hex")}`;
  const project = `agentops-a03-${suffix}`;
  const names = {
    worker: `${project}-worker-1`,
    broker: `${project}-broker-1`,
    executor: `${project}-executor-1`,
  };
  const environment = {
    AGENTOPS_A03_IMAGE: imageIdentity.id,
    AGENTOPS_A03_RUNTIME_PATH: fixture.runtime,
    AGENTOPS_A03_CONFIG_PATH: fixture.config,
    AGENTOPS_A03_WORKSPACE_PATH: fixture.workspace,
    AGENTOPS_A03_SIGNING_KEY_PATH: fixture.signing,
    AGENTOPS_A03_OPENCLAW_BIN_SHA256: fixture.binarySha256,
  };
  let cleanupVerified = false;
  let localCleanupVerified = false;
  let receipt = null;
  try {
    verifyComposeModel(composeFile, project, environment);
    compose(composeFile, project, environment, ["up", "--detach", "--no-build"], { timeout: 120_000 });
    waitFor("executor_private_health", () => {
      const output = docker([
        "exec", names.broker, "node", "-e", healthProbe, PRIVATE_SOCKET,
      ], { accepted: [0, 2], code: "executor_health_probe_failed" });
      if (!output.trim()) return null;
      const value = JSON.parse(output);
      return value.ok && value.ready && value.status === 200 ? value : null;
    });
    waitFor("broker_public_health", () => {
      const output = docker(["exec", names.worker, "node", "-e", healthProbe, PUBLIC_SOCKET], { accepted: [0, 2] });
      if (!output.trim()) return null;
      const value = JSON.parse(output);
      return value.ok
        && value.ready
        && value.status === 200
        && value.so_peercred_verified === false
        ? value
        : null;
    });

    const workerInspect = inspectContainer(names.worker);
    const brokerInspect = inspectContainer(names.broker);
    const executorInspect = inspectContainer(names.executor);
    assert.equal(workerInspect.Config.User, "1000:1000");
    assert.equal(brokerInspect.Config.User, "1100:1100");
    assert.equal(executorInspect.Config.User, "1001:1000");
    assert.deepEqual(workerInspect.HostConfig.GroupAdd, ["2100"]);
    assert.deepEqual(brokerInspect.HostConfig.GroupAdd, ["2100", "2200"]);
    assert.deepEqual(executorInspect.HostConfig.GroupAdd, ["2200"]);
    for (const inspect of [workerInspect, brokerInspect, executorInspect]) {
      assert.equal(inspect.Image, imageIdentity.id);
    }
    assert.deepEqual(brokerInspect.Config.Entrypoint, [
      "node",
      "/usr/local/lib/agentops/openclaw-broker-entrypoint.mjs",
    ]);
    assert.equal(workerInspect.HostConfig.ReadonlyRootfs, true);
    assert.equal(brokerInspect.HostConfig.ReadonlyRootfs, true);
    assert.equal(executorInspect.HostConfig.ReadonlyRootfs, true);
    assert.equal(workerInspect.HostConfig.NetworkMode, "none");
    assert.equal(brokerInspect.HostConfig.NetworkMode, "none");
    assert.equal(Object.keys(executorInspect.NetworkSettings.Networks).length, 1);
    assert.ok(Object.keys(executorInspect.NetworkSettings.Networks)[0].endsWith("provider-egress"));

    const workerMounts = mountsByDestination(workerInspect);
    const brokerMounts = mountsByDestination(brokerInspect);
    const executorMounts = mountsByDestination(executorInspect);
    assertMountDestinationAllowlist(workerInspect, [
      "/run/agentops-openclaw-public",
      "/tmp",
    ]);
    assertMountDestinationAllowlist(brokerInspect, [
      "/run/agentops-openclaw-public",
      "/run/agentops-openclaw-private",
      "/tmp",
    ]);
    assertMountDestinationAllowlist(executorInspect, [
      "/run/agentops-openclaw-private",
      "/run/openclaw-state",
      "/tmp",
      "/opt/agentops-provider/openclaw",
      "/run/secrets/openclaw_config",
      "/opt/agentops-worker/workspace",
      "/run/secrets/openclaw_receipt_signing_key",
    ]);
    assertTmpfsAllowlist(workerInspect, ["/tmp"]);
    assertTmpfsAllowlist(brokerInspect, ["/tmp"]);
    assertTmpfsAllowlist(executorInspect, ["/run/openclaw-state", "/tmp"]);
    assertMount(workerMounts, "/run/agentops-openclaw-public", false);
    assertMount(brokerMounts, "/run/agentops-openclaw-public", true);
    assertMount(brokerMounts, "/run/agentops-openclaw-private", false);
    assert.equal(
      [...brokerMounts.values()].some((mount) => mount.Type === "bind"),
      false,
    );
    assertMount(executorMounts, "/run/agentops-openclaw-private", true);
    for (const path of [
      "/opt/agentops-provider/openclaw",
      "/run/secrets/openclaw_config",
      "/opt/agentops-worker/workspace",
      "/run/secrets/openclaw_receipt_signing_key",
    ]) assertMount(executorMounts, path, false);

    const workerForbidden = [
      "/run/agentops-openclaw-private/executor.sock",
      "/opt/agentops-provider/openclaw/bin/openclaw",
      "/run/secrets/openclaw_config",
      "/opt/agentops-worker/workspace/executor-only",
      "/run/secrets/openclaw_receipt_signing_key",
    ];
    const brokerSensitivePaths = workerForbidden.slice(1);
    const workerDenials = JSON.parse(docker([
      "exec", "--env", `A03_FORBIDDEN_PATHS=${JSON.stringify(workerForbidden)}`,
      names.worker, "node", "-e", forbiddenOpenProbe,
    ]));
    const brokerSensitivePathDenials = JSON.parse(docker([
      "exec", "--env", `A03_FORBIDDEN_PATHS=${JSON.stringify(brokerSensitivePaths)}`,
      names.broker, "node", "-e", forbiddenOpenProbe,
    ]));
    const workerPublicMutation = JSON.parse(docker([
      "exec", "--env", "A03_MUTATION_PATH=/run/agentops-openclaw-public/worker-rebind",
      names.worker, "node", "-e", readOnlyMutationProbe,
    ]));
    const brokerPrivateMutation = JSON.parse(docker([
      "exec", "--env", "A03_MUTATION_PATH=/run/agentops-openclaw-private/broker-rebind",
      names.broker, "node", "-e", readOnlyMutationProbe,
    ]));
    const protocol = execJson(names.worker, protocolProbe, "a03_protocol_probe_failed");
    assert.equal(protocol.ok, true);

    receipt = {
      ok: true,
      contract: CONTRACT,
      source_commit: expectedRevision,
      resolved_image_id: imageIdentity.id,
      image_source_revision_label: imageIdentity.revision,
      image_identity_revision_bound: true,
      image_digest_verified: true,
      image_source_revision_verified: true,
      real_linux_docker_execution: true,
      phase_a03_three_service_topology_verified: true,
      phase_a03_candidate_source_only: true,
      worker_uid_1000_verified: true,
      broker_uid_1100_verified: true,
      executor_uid_1001_verified: true,
      worker_public_group_2100_verified: true,
      broker_public_private_groups_2100_2200_verified: true,
      executor_private_group_2200_verified: true,
      product_openclaw_broker_entrypoint_executed: true,
      worker_public_socket_read_only_only: true,
      broker_public_rw_private_ro_verified: true,
      broker_network_none_verified: true,
      executor_private_rw_runtime_config_workspace_signing_verified: true,
      executor_provider_egress_only_verified: true,
      worker_forbidden_path_read_open_denials: workerDenials.count,
      broker_a06_prep_sensitive_path_read_open_denials:
        brokerSensitivePathDenials.count,
      worker_public_socket_mutation_denied: workerPublicMutation.ok,
      broker_private_socket_mutation_denied: brokerPrivateMutation.ok,
      public_broker_private_executor_protocol_verified: protocol.ok,
      provider_call_performed: protocol.provider_call_performed,
      dry_run: protocol.dry_run,
      raw_prompt_omitted: protocol.raw_prompt_omitted,
      raw_response_omitted: protocol.raw_response_omitted,
      executor_implementation: "interim_current_openclaw_provider_entrypoint",
      runtime_execution_fixture: true,
      real_openclaw_runtime_execution: false,
      so_peercred_verified: false,
      hostile_runtime_isolation_verified: false,
      broker_can_read_forwarded_protocol_payload: true,
      executor_and_runtime_same_uid: true,
    };
  } finally {
    try {
      compose(composeFile, project, environment, ["down", "--volumes", "--remove-orphans", "--timeout", "10"], { timeout: 90_000 });
      const containers = docker(["container", "ls", "--all", "--quiet", "--filter", `label=com.docker.compose.project=${project}`]).trim();
      const volumes = docker(["volume", "ls", "--quiet", "--filter", `label=com.docker.compose.project=${project}`]).trim();
      cleanupVerified = !containers && !volumes;
    } finally {
      rmSync(root, { recursive: true, force: true });
      localCleanupVerified = !existsSync(root);
    }
    if (!cleanupVerified) fail("a03_docker_cleanup_unverified");
    if (!localCleanupVerified) fail("a03_local_cleanup_unverified");
  }
  if (!receipt) fail("a03_receipt_unavailable");
  receipt.docker_container_volume_cleanup_verified = true;
  receipt.local_fixture_cleanup_verified = true;
  receipt.cleanup_confirmed = true;
  process.stdout.write(`${JSON.stringify(receipt)}\n`);
}

mainAcceptance().catch((error) => {
  process.stderr.write(`${error?.code || "a03_acceptance_failed"}\n`);
  process.exitCode = 1;
});
