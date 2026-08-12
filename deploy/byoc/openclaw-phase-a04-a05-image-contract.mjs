#!/usr/bin/env node

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) => readFileSync(join(here, name), "utf8");
const dockerfile = read("Dockerfile");
const compose = read("compose.openclaw-phase-a04-a05.yaml");
const gate = read("openclaw-peercred-gate.c");
const supervisor = read("openclaw-boundary-supervisor.mjs");
const acceptance = read("openclaw-phase-a04-a05-container-acceptance.mjs");

assert.match(dockerfile, /AS peercred-build/);
assert.match(dockerfile, /gcc -std=c11 -O2 -fPIE -fstack-protector-strong/);
assert.match(dockerfile, /-Wl,-z,relro,-z,now,-z,noexecstack -pie/);
assert.match(
  dockerfile,
  /COPY --from=peercred-build --chmod=0555 \/agentops-openclaw-peercred-gate \/usr\/local\/bin\/agentops-openclaw-peercred-gate/,
);
const runtimeStage = dockerfile.split(/ AS runtime\n/, 2)[1] || "";
assert.ok(runtimeStage, "runtime_stage_required");
assert.doesNotMatch(runtimeStage, /apt-get[^\n]*(?:gcc|libc6-dev)|(?:^|\s)(?:cc|gcc)\s/m);

const peerCredentialCheck = gate.indexOf("getsockopt(client_fd, SOL_SOCKET, SO_PEERCRED");
const upstreamConnect = gate.indexOf("connect_upstream(upstream_path");
const relay = gate.indexOf("relay_connection(client_fd");
assert.ok(peerCredentialCheck >= 0, "linux_so_peercred_check_required");
assert.ok(upstreamConnect > peerCredentialCheck, "peer_identity_must_precede_upstream_connect");
assert.ok(relay > peerCredentialCheck, "peer_identity_must_precede_request_relay");
for (const argument of ["--listen", "--upstream", "--expected-uid", "--listen-gid"]) {
  assert.ok(gate.includes(argument), `named_gate_argument_required:${argument}`);
}
assert.doesNotMatch(gate, /AF_INET|AF_INET6|SOCK_DGRAM/);

const worker = compose.match(/  worker:\n([\s\S]*?)(?=\n  broker:)/)?.[1] || "";
const broker = compose.match(/  broker:\n([\s\S]*?)(?=\n  executor:)/)?.[1] || "";
const executor = compose.match(/  executor:\n([\s\S]*?)(?=\nvolumes:)/)?.[1] || "";
assert.ok(worker && broker && executor, "three_service_candidate_required");
assert.match(worker, /user: "1000:1000"/);
assert.match(worker, /phase_a04_a05_public_socket:\/run\/agentops-openclaw-public:ro/);
assert.doesNotMatch(worker, /agentops-openclaw-private|openclaw_config|signing_key/);
assert.match(broker, /user: "1100:1100"/);
assert.match(broker, /network_mode: none/);
assert.match(broker, /openclaw-boundary-supervisor\.mjs/);
assert.match(broker, /AGENTOPS_OPENCLAW_BOUNDARY_ROLE: broker/);
assert.match(broker, /agentops-openclaw-broker-backend:rw,noexec,nosuid,nodev,size=1m,mode=0700,uid=1100,gid=1100/);
assert.doesNotMatch(broker, /agentops-provider\/openclaw|openclaw_config|signing_key/);
assert.match(executor, /user: "1001:1000"/);
assert.match(executor, /AGENTOPS_OPENCLAW_BOUNDARY_ROLE: executor/);
assert.match(executor, /agentops-openclaw-provider-backend:rw,noexec,nosuid,nodev,size=1m,mode=0700,uid=1001,gid=1000/);
assert.match(executor, /AGENTOPS_OPENCLAW_BOUNDARY_STATE_PATH=\/run\/agentops-openclaw-provider-backend\/supervisor-state\.json/);
assert.doesNotMatch(executor, /agentops-openclaw-public|control_plane/);

for (const boundary of [
  "/usr/local/bin/agentops-openclaw-peercred-gate",
  "/run/agentops-openclaw-public/broker.sock",
  "/run/agentops-openclaw-broker-backend",
  '`${BROKER_INTERNAL_ROOT}/broker.sock`',
  "/run/agentops-openclaw-private/executor.sock",
  "/run/agentops-openclaw-provider-backend",
  '`${EXECUTOR_INTERNAL_ROOT}/provider.sock`',
  "1000",
  "1100",
  "2100",
  "2200",
]) {
  assert.ok(supervisor.includes(boundary), `supervisor_boundary_required:${boundary}`);
}

for (const honestClaim of [
  "candidate_source_only: true",
  "interim_provider_identity: true",
  "worker_attack_probe_container: true",
  "product_worker_started: false",
  "real_openclaw_runtime_execution: false",
  "runtime_receipt_verified: false",
  "hostile_runtime_isolation_verified: false",
]) {
  assert.ok(acceptance.includes(honestClaim), `acceptance_claim_required:${honestClaim}`);
}
for (const attackClaim of [
  "wrong_public_peer_connection_rejected: true",
  "wrong_private_peer_connection_rejected: true",
]) {
  assert.ok(acceptance.includes(attackClaim), `acceptance_attack_claim_required:${attackClaim}`);
}
assert.doesNotMatch(acceptance, /hostile_runtime_isolation_verified:\s*true/);
assert.doesNotMatch(acceptance, /runtime_receipt_verified:\s*true/);

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_phase_a04_a05_image_identity_v1",
  worker_uid: 1000,
  broker_uid: 1100,
  interim_provider_uid: 1001,
  public_expected_peer_uid: 1000,
  private_expected_peer_uid: 1100,
  public_socket_gid: 2100,
  private_socket_gid: 2200,
  compiled_linux_peercred_gate_present: true,
  compiler_omitted_from_runtime_stage: true,
  source_only_candidate_present: true,
  real_linux_peercred_acceptance_performed: false,
  hostile_runtime_isolation_verified: false,
})}\n`);
