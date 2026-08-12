#!/usr/bin/env node

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dockerfile = readFileSync(join(here, "Dockerfile"), "utf8");
const compose = readFileSync(join(here, "compose.openclaw-phase-a03.yaml"), "utf8");
const acceptance = readFileSync(
  join(here, "openclaw-phase-a03-container-acceptance.mjs"),
  "utf8",
);

for (const boundary of [
  "groupadd --gid 1100 agentops-broker",
  "groupadd --gid 1200 agentops-openclaw-runtime",
  "groupadd --gid 2100 agentops-openclaw-public",
  "groupadd --gid 2200 agentops-openclaw-private",
  "useradd --uid 1001 --gid 1000",
  "useradd --uid 1100 --gid 1100",
  "useradd --uid 1200 --gid 1200",
  "usermod --append --groups 2100 node",
  "usermod --append --groups 2100,2200 agentops-openclaw-broker",
  "install -d -o 1100 -g 2100 -m 0750 /run/agentops-openclaw-public",
  "install -d -o 0 -g 2200 -m 0750 /run/agentops-openclaw-private",
  "deploy/byoc/openclaw-broker-entrypoint.mjs",
  "deploy/byoc/openclaw-broker-contract.mjs",
]) {
  assert.ok(dockerfile.includes(boundary), `missing_image_boundary:${boundary}`);
}

assert.doesNotMatch(dockerfile, /(?:useradd|groupadd)[^\n]*--non-unique/);
assert.doesNotMatch(dockerfile, /chmod\s+0?77[0-7]\s+\/run\/agentops-openclaw-(?:public|private)/);

const worker = compose.match(/  worker:\n([\s\S]*?)(?=\n  broker:)/)?.[1] || "";
const broker = compose.match(/  broker:\n([\s\S]*?)(?=\n  executor:)/)?.[1] || "";
const executor = compose.match(/  executor:\n([\s\S]*?)(?=\nvolumes:)/)?.[1] || "";
assert.ok(worker && broker && executor, "phase_a03_three_services_required");
assert.match(worker, /user: "1000:1000"/);
assert.match(worker, /group_add:\s*\n\s+- "2100"/);
assert.match(worker, /phase_a03_public_socket:\/run\/agentops-openclaw-public:ro/);
assert.doesNotMatch(
  worker,
  /agentops-openclaw-private|agentops-provider|openclaw_config|agentops-worker\/workspace|signing_key/,
);
assert.match(broker, /user: "1100:1100"/);
assert.match(broker, /group_add:[\s\S]*"2100"[\s\S]*"2200"/);
assert.match(broker, /network_mode: none/);
assert.match(broker, /openclaw-broker-entrypoint\.mjs/);
assert.match(broker, /phase_a03_public_socket:\/run\/agentops-openclaw-public:rw/);
assert.match(broker, /phase_a03_private_socket:\/run\/agentops-openclaw-private:ro/);
assert.doesNotMatch(
  broker,
  /agentops-provider\/openclaw|openclaw_config|agentops-worker\/workspace|signing_key/,
);
assert.match(executor, /phase_a03_private_socket:\/run\/agentops-openclaw-private:rw/);
assert.doesNotMatch(executor, /agentops-openclaw-public|control_plane/);
assert.match(compose, /o: uid=1100,gid=2100,mode=0750/);
assert.match(compose, /o: uid=1001,gid=2200,mode=0750/);

for (const honestClaim of [
  "phase_a03_candidate_source_only: true",
  "real_openclaw_runtime_execution: false",
  "so_peercred_verified: false",
  "hostile_runtime_isolation_verified: false",
]) {
  assert.ok(acceptance.includes(honestClaim), `missing_honest_claim:${honestClaim}`);
}
assert.doesNotMatch(acceptance, /so_peercred_verified:\s*true/);
assert.doesNotMatch(acceptance, /hostile_runtime_isolation_verified:\s*true/);

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_phase_a03_image_identity_v1",
  worker_uid: 1000,
  broker_uid: 1100,
  interim_provider_uid: 1001,
  reserved_runtime_uid: 1200,
  public_socket_gid: 2100,
  private_socket_gid: 2200,
  public_socket_directory_mode: "0750",
  private_socket_directory_mode: "0750",
  phase_a03_identity_inputs_present: true,
  source_only_three_service_candidate_present: true,
  worker_private_and_runtime_mounts_omitted: true,
  broker_runtime_and_secret_mounts_omitted: true,
  so_peercred_verified: false,
  hostile_runtime_isolation_verified: false,
})}\n`);
