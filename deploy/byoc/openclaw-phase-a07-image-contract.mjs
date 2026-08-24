#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name) => readFileSync(join(here, name), "utf8");
const dockerfile = read("Dockerfile");
const a07Dockerfile = read("openclaw-phase-a07.Dockerfile");
const artifactDockerfile = read("openclaw-runtime-artifact/Dockerfile");
const a07Workflow = read("../../.github/workflows/openclaw-phase-a07-foundation.yml");
const egressConfigSource = read("openclaw-egress-config.mjs");
const egressGatewaySource = read("openclaw-egress-gateway.mjs");
const realRunner = read("openclaw-runtime-real-runner-contract.mjs");
const compose = read("compose.openclaw-phase-a07.yaml");
const defaultCompose = read("compose.openclaw-phase-a04-a05.yaml");
const artifact = JSON.parse(read("openclaw-runtime-artifact/artifact.json"));
const artifactLock = JSON.parse(read("openclaw-runtime-artifact/package-lock.json"));
const sha256 = (value) => createHash("sha256").update(value).digest("hex");

assert.equal(
  sha256(defaultCompose),
  "6fb61505fce1425457d38054f3625a94d3c54f2ef71da9b0898ba39fee6f177f",
  "default_a04_a05_topology_must_not_change",
);

assert.match(dockerfile, /FROM peercred-build AS runtime-launcher-build/);
assert.match(dockerfile, /COPY deploy\/byoc\/openclaw-runtime-launcher\.c/);
assert.match(dockerfile, /-Wl,-z,relro,-z,now,-z,noexecstack -pie/);
assert.match(
  dockerfile,
  /COPY --from=runtime-launcher-build --chmod=0555 \/agentops-openclaw-runtime-launcher \/usr\/local\/bin\/agentops-openclaw-runtime-launcher/,
);
assert.match(dockerfile, /FROM peercred-build AS runtime-path-resolver-build/);
assert.match(dockerfile, /COPY deploy\/byoc\/openclaw-runtime-path-resolver\.c/);
assert.match(
  dockerfile,
  /COPY --from=runtime-path-resolver-build --chmod=0555 \/agentops-openclaw-runtime-path-resolver \/usr\/local\/bin\/agentops-openclaw-runtime-path-resolver/,
);
assert.match(dockerfile, /FROM peercred-build AS mount-bootstrap-build/);
assert.match(dockerfile, /COPY deploy\/byoc\/openclaw-mount-bootstrap\.c/);
assert.match(
  dockerfile,
  /COPY --from=mount-bootstrap-build --chmod=0555 \/agentops-openclaw-mount-bootstrap \/usr\/local\/bin\/agentops-openclaw-mount-bootstrap/,
);
assert.match(dockerfile, /deploy\/byoc\/openclaw-runtime-path-resolver-contract\.mjs/);
assert.match(dockerfile, /install -d -o 0 -g 2200 -m 0700 \/var\/lib\/agentops-openclaw\/replay/);
assert.equal(artifact.node.version, "22.23.2");
assert.equal(
  artifact.platforms["linux/amd64"].base_image,
  "node:22.23.2-bookworm-slim@sha256:a17d50af28002a160548bd4225b3cfcb12c5efcb171f79e68758f2885fb1b066",
);
assert.equal(artifact.openclaw.version, "2026.5.4");
assert.equal(
  artifact.openclaw.npm_integrity,
  "sha512-nbLukSwhBr/wqFLKwLKMDCXJ0lIQYpKKJ4Zzp6ZoN6erLjRUkU5MyU5wbY5oChl6yM7TinBYZ3lRw9V6K07DSQ==",
);
assert.equal(artifactLock.packages["node_modules/openclaw"].version, artifact.openclaw.version);
assert.equal(artifactLock.packages["node_modules/openclaw"].integrity, artifact.openclaw.npm_integrity);
assert.match(
  a07Dockerfile,
  /FROM --platform=linux\/amd64 node:22\.23\.2-bookworm-slim@sha256:a17d50af28002a160548bd4225b3cfcb12c5efcb171f79e68758f2885fb1b066 AS openclaw-guest-root/,
);
assert.match(a07Dockerfile, /ARG COMMERCIAL_BASE_IMAGE/);
assert.ok(
  a07Dockerfile.indexOf("ARG COMMERCIAL_BASE_IMAGE") < a07Dockerfile.indexOf("FROM --platform=linux/amd64"),
  "commercial_base_arg_must_be_global_before_first_from",
);
assert.match(a07Dockerfile, /FROM \$\{COMMERCIAL_BASE_IMAGE\} AS runtime/);
assert.match(a07Dockerfile, /ARG TARGETPLATFORM/);
assert.match(a07Dockerfile, /test "\$\{TARGETPLATFORM\}" = "linux\/amd64"/);
assert.match(a07Dockerfile, /openclaw-runtime-artifact\/package-lock\.json \.\//);
assert.match(a07Dockerfile, /npm ci --ignore-scripts --omit=dev --no-audit --no-fund/);
assert.match(a07Dockerfile, /test "\$\(node --version\)" = "v22\.23\.2"/);
assert.match(a07Dockerfile, /find \/ -xdev -perm \/6000 -exec chmod a-s/);
assert.match(a07Dockerfile, /test -z "\$\(find \/ -xdev -perm \/6000 -print -quit\)"/);
assert.doesNotMatch(a07Dockerfile, /find \/ -xdev -type f -perm \/6000/);
for (const excludedPath of [
  "/opt/agentops-worker/workspace",
  "/run/openclaw-state",
  "/run/secrets/openclaw_config",
  "/tmp",
]) {
  const exclusion = new RegExp(`-path ${excludedPath.replaceAll("/", "\\/")} -prune -o`);
  assert.match(a07Dockerfile, exclusion);
  assert.match(a07Workflow, exclusion);
}
assert.match(a07Dockerfile, /\\\( -type f -o -type d \\\) \\\s+-perm \/0022 -exec chmod go-w \{\} \+/);
assert.match(a07Dockerfile, /\\\( -type f -o -type d \\\) \\\s+-perm \/0022 -print -quit\)"/);
assert.doesNotMatch(a07Dockerfile, /-path \/tmp -prune -o \\\s+-perm \/0022/);
assert.match(a07Dockerfile, /find \/ -xdev -type f -links \+1 -exec sh -ec/);
assert.match(a07Dockerfile, /test -z "\$\(find \/ -xdev -type f -links \+1 -print -quit\)"/);
const hardlinkExpansion = /find \/ -xdev -type f -links \+1 -exec sh -ec '[\s\S]*?test -z "\$\(find \/ -xdev -type f -links \+1 -print -quit\)"/;
assert.equal(
  artifactDockerfile.match(hardlinkExpansion)?.[0],
  a07Dockerfile.match(hardlinkExpansion)?.[0],
  "guest_root_hardlink_expansion_must_match_release_artifact_input",
);
function immutableRootSanitization(source) {
  const startNeedle = "find / -xdev -perm /6000 -exec chmod a-s {} + \\";
  const endNeedle = 'test -z "$(find / -xdev -perm /6000 -print -quit)"';
  const start = source.indexOf(startNeedle);
  const end = source.indexOf(endNeedle, start);
  assert.ok(start >= 0 && end >= start, "guest_root_immutable_sanitization_required");
  return source.slice(start, end + endNeedle.length);
}
assert.equal(
  immutableRootSanitization(artifactDockerfile),
  immutableRootSanitization(a07Dockerfile),
  "guest_root_immutable_sanitization_must_match_release_artifact_input",
);
assert.match(a07Workflow, /test -z "\$\(find \/ -xdev -perm \/6000 -print -quit\)"/);
assert.doesNotMatch(a07Workflow, /find \/ -xdev -type f -perm \/6000/);
assert.match(a07Workflow, /\\\( -type f -o -type d \\\) \\\s+-perm \/0022 -print -quit\)"/);
assert.doesNotMatch(a07Workflow, /-path \/tmp -prune -o \\\s+-perm \/0022/);
assert.ok(
  a07Workflow.indexOf('test -z "$(find / -xdev -perm /6000 -print -quit)"')
    < a07Workflow.indexOf("            deploy/byoc/openclaw-runtime-oci-export.mjs"),
  "guest_root_runtime_metadata_checks_must_precede_exporter",
);
assert.match(a07Dockerfile, /\.version'\)" = "2026\.5\.4"/);
assert.match(
  a07Dockerfile,
  /COPY --from=openclaw-guest-root \/ \/opt\/agentops-provider\/openclaw\//,
);
assert.match(a07Dockerfile, /install -d -o 1200 -g 1200 -m 0700 \/run\/openclaw-state/);
assert.match(a07Dockerfile, /\/opt\/agentops-worker\/workspace/);
assert.match(a07Dockerfile, /\/run\/secrets\/openclaw_config/);
assert.doesNotMatch(dockerfile, /openclaw-guest-root|COMMERCIAL_BASE_IMAGE|TARGETPLATFORM/);
for (const moduleName of [
  "openclaw-cgroup-v2.mjs",
  "openclaw-egress-config.mjs",
  "openclaw-egress-gateway.mjs",
  "openclaw-executor-request.mjs",
  "openclaw-executor-protocol.mjs",
  "openclaw-executor-receipt.mjs",
  "openclaw-executor-runner.mjs",
  "openclaw-executor-healthcheck.mjs",
  "openclaw-executor-service.mjs",
  "openclaw-runtime-manifest.mjs",
  "openclaw-runtime-manifest-v2.mjs",
  "openclaw-runtime-mount-policy.mjs",
  "openclaw-runtime-rootfs-merkle.mjs",
  "openclaw-runtime-receipt.mjs",
  "openclaw-runtime-release.mjs",
]) {
  assert.ok(dockerfile.includes(`deploy/byoc/${moduleName}`), `a07_image_module_required:${moduleName}`);
}
const runtimeStage = dockerfile.split(/ AS runtime\n/, 2)[1] || "";
assert.ok(runtimeStage, "runtime_stage_required");
assert.doesNotMatch(runtimeStage, /apt-get[^\n]*(?:gcc|libc6-dev)|(?:^|\s)(?:cc|gcc)\s/m);

const worker = compose.match(/  worker:\n([\s\S]*?)(?=\n  broker:)/)?.[1] || "";
const broker = compose.match(/  broker:\n([\s\S]*?)(?=\n  executor:)/)?.[1] || "";
const executor = compose.match(/  executor:\n([\s\S]*?)(?=\n  egress-gateway:)/)?.[1] || "";
const egressGateway = compose.match(/  egress-gateway:\n([\s\S]*?)(?=\nvolumes:)/)?.[1] || "";
assert.ok(worker && broker && executor && egressGateway, "a07_four_service_candidate_required");

assert.match(worker, /user: "1000:1000"/);
assert.match(worker, /entrypoint: \[node, \/usr\/local\/lib\/agentops\/worker-entrypoint\.mjs\]/);
assert.match(worker, /OPENCLAW_PROVIDER_PROTOCOL: v2/);
assert.match(worker, /AGENTOPS_WORKER_ADAPTER: openclaw/);
assert.doesNotMatch(worker, /setInterval\(\(\)=>\{\},1000\)/);
assert.match(worker, /phase_a07_public_socket:\/run\/agentops-openclaw-public:ro/);
assert.match(worker, /networks:\s*\n\s+- control-plane/);
assert.doesNotMatch(worker, /openclaw-private|openclaw_config|signing_key|provider-egress/);

assert.match(broker, /user: "1100:1100"/);
assert.match(broker, /network_mode: none/);
assert.match(broker, /phase_a07_public_socket:\/run\/agentops-openclaw-public:rw/);
assert.match(broker, /phase_a07_private_socket:\/run\/agentops-openclaw-private:ro/);
assert.match(broker, /AGENTOPS_OPENCLAW_BROKER_PRIVATE_SOCKET_UID: "0"/);
assert.match(broker, /AGENTOPS_OPENCLAW_BROKER_EXECUTOR_IMAGE_REFERENCE: \$\{AGENTOPS_A07_IMAGE:/);
assert.match(broker, /AGENTOPS_OPENCLAW_BROKER_SECCOMP_PROFILE_SHA256: \$\{AGENTOPS_A07_SECCOMP_PROFILE_SHA256:/);
assert.match(broker, /AGENTOPS_OPENCLAW_BROKER_RUNTIME_IMAGE_DIGEST: \$\{AGENTOPS_A07_RUNTIME_IMAGE_DIGEST:/);
assert.match(broker, /AGENTOPS_OPENCLAW_BROKER_RECEIPT_KEY_ID: \$\{AGENTOPS_A07_RECEIPT_KEY_ID:/);
assert.equal((broker.match(/create_host_path: false/g) || []).length, 1);
assert.doesNotMatch(broker, /agentops-provider\/openclaw|openclaw_config|signing_key|provider-egress/);

assert.match(executor, /user: "0:2200"/);
assert.match(executor, /init: false/);
assert.match(executor, /cap_drop: \[ALL\]/);
assert.match(executor, /cap_add:\s*\n\s+- SETUID\s*\n\s+- SETGID\s*\n\s+- SYS_CHROOT\s*\n\s+- KILL\s*\n\s+- SYS_ADMIN\s*\n\s+- SETPCAP/);
assert.match(executor, /no-new-privileges:true/);
assert.match(executor, /read_only: true/);
assert.match(executor, /entrypoint: \[\/usr\/local\/bin\/agentops-openclaw-mount-bootstrap\]/);
assert.match(executor, /healthcheck:\s*\n\s+test: \[CMD, node, \/usr\/local\/lib\/agentops\/openclaw-executor-healthcheck\.mjs\]/);
assert.match(executor, /AGENTOPS_OPENCLAW_BOUNDARY_ROLE: root-executor/);
assert.match(executor, /OPENCLAW_EXECUTOR_IMAGE_REFERENCE: \$\{AGENTOPS_A07_IMAGE:/);
assert.doesNotMatch(executor, /AGENTOPS_A07_IMAGE_DIGEST/);
assert.match(executor, /agentops-openclaw-provider-backend:rw,noexec,nosuid,nodev,size=2m,mode=0700,uid=0,gid=2200/);
assert.match(executor, /AGENTOPS_A07_REPLAY_JOURNAL_PATH:[^\n]*pre-provisioned root:2200 mode 0700 directory/);
assert.match(executor, /target: \/var\/lib\/agentops-openclaw\/replay\s*\n\s*read_only: false\s*\n\s*bind:\s*\n\s*create_host_path: false/);
assert.match(executor, /source: \/sys\/fs\/cgroup\/agentops-openclaw-executor\s*\n\s*target: \/sys\/fs\/cgroup\/agentops-openclaw-executor\s*\n\s*read_only: false/);
assert.match(executor, /\/opt\/agentops-provider\/openclaw\/run\/openclaw-state:rw,noexec,nosuid,nodev,size=32m,mode=0700,uid=1200,gid=1200/);
assert.match(executor, /\/opt\/agentops-provider\/openclaw\/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777,uid=1200,gid=1200/);
assert.match(executor, /phase_a07_private_socket:\/run\/agentops-openclaw-private:rw/);
assert.match(executor, /networks:\s*\n\s+- runtime-egress/);
assert.match(executor, /depends_on:\s*\n\s+egress-gateway:\s*\n\s+condition: service_healthy/);
assert.equal((executor.match(/create_host_path: false/g) || []).length, 9);
assert.doesNotMatch(executor, /control-plane|agentops-openclaw-public/);
assert.doesNotMatch(executor, /provider-egress/);
assert.doesNotMatch(executor, /AGENTOPS_A07_RUNTIME_PATH/);
assert.doesNotMatch(
  executor,
  /target: \/opt\/agentops-provider\/openclaw\s*\n\s*read_only:/,
  "guest_root_must_come_from_executor_image",
);

for (const target of [
  "/opt/agentops-provider/openclaw/opt/agentops-worker/workspace",
  "/opt/agentops-provider/openclaw/run/secrets/openclaw_config",
  "/run/manifests/openclaw-runtime-release",
  "/run/trust/openclaw-runtime-manifest-trust-roots.json",
  "/run/secrets/openclaw_receipt_signing_key",
  "/run/policies/openclaw-runtime-seccomp.json",
  "/run/policies/openclaw-cgroup-policy.json",
]) {
  const escaped = target.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  assert.match(executor, new RegExp(`target: ${escaped}\\s*\\n\\s*read_only: true`), `readonly_mount_required:${target}`);
}

assert.match(compose, /o: uid=1100,gid=2100,mode=0750,nosuid,nodev,noexec,size=1m/);
assert.match(compose, /o: uid=0,gid=2200,mode=0750,nosuid,nodev,noexec,size=1m/);
assert.match(compose, /runtime-egress:\s*\n\s+driver: bridge\s*\n\s+internal: true/);
assert.match(executor, /OPENCLAW_EXTERNAL_PROVIDER_EGRESS_ATTESTED: \$\{AGENTOPS_A07_EXTERNAL_PROVIDER_EGRESS_ATTESTED:/);
assert.match(executor, /OPENCLAW_CONFIG_PATH: \/run\/secrets\/openclaw_config/);
assert.match(egressGateway, /user: "1300:1300"/);
assert.match(egressGateway, /read_only: true/);
assert.match(egressGateway, /cap_drop: \[ALL\]/);
assert.match(egressGateway, /no-new-privileges:true/);
assert.match(egressGateway, /entrypoint: \[node, \/usr\/local\/lib\/agentops\/openclaw-egress-gateway\.mjs\]/);
assert.match(egressGateway, /OPENCLAW_EGRESS_GATEWAY_UPSTREAM_ORIGIN: \$\{AGENTOPS_A08_PROVIDER_ORIGIN:/);
assert.match(egressGateway, /--healthcheck/);
assert.match(egressGateway, /runtime-egress:[\s\S]*openclaw-egress-gateway[\s\S]*provider-egress: \{\}/);
assert.doesNotMatch(egressGateway, /control-plane|agent_token|signing_key|receipt_trust_root|docker\.sock/);
for (const source of [egressConfigSource, egressGatewaySource]) {
  assert.match(source, /http:\/\/openclaw-egress-gateway:18080\/v1/);
}
for (const route of ["/v1/chat/completions", "/v1/messages", "/v1/responses"]) {
  assert.match(egressGatewaySource, new RegExp(route.replaceAll("/", "\\/")));
}
for (const providerApi of ["anthropic-messages", "openai-completions", "openai-responses"]) {
  assert.match(egressConfigSource, new RegExp(providerApi));
}
assert.match(egressConfigSource, /models\.mode !== "replace"/);
assert.doesNotMatch(executor, /OPENCLAW_RUNTIME_RECEIPT_VERIFIED/);
assert.doesNotMatch(executor, /OPENCLAW_HOSTILE_RUNTIME_ISOLATION_VERIFIED/);
assert.doesNotMatch(compose, /\/var\/run\/docker\.sock|network_mode:\s*host|pid:\s*host|privileged:\s*true/);
assert.doesNotMatch(compose, /OPENCLAW_(?:RUNTIME_RECEIPT|HOSTILE_RUNTIME_ISOLATION)_VERIFIED: "true"/);
for (const sensitivePath of [
  "/run/agentops-openclaw-public/broker.sock",
  "/run/agentops-openclaw-private/executor.sock",
  "/run/secrets/agent_token",
  "/run/secrets/openclaw_receipt_signing_key",
  "/run/secrets/openclaw_receipt_trust_root",
  "/run/trust/openclaw-runtime-manifest-trust-roots.json",
  "/run/policies/openclaw-runtime-seccomp.json",
  "/run/policies/openclaw-cgroup-policy.json",
  "/var/lib/agentops-openclaw/replay",
]) assert.match(realRunner, new RegExp(sensitivePath.replaceAll("/", "\\/")));
assert.match(realRunner, /constants\.O_RDONLY \| constants\.O_NOFOLLOW/);
assert.match(realRunner, /\["EACCES", "ENOENT", "EPERM"\]/);
assert.match(a07Workflow, /\.runtime_sensitive_path_open_denials_verified == true/);

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_phase_a07_image_topology_v1",
  default_a04_a05_topology_unchanged: true,
  worker_uid: 1000,
  broker_uid: 1100,
  executor_uid: 0,
  executor_gid: 2200,
  runtime_uid: 1200,
  executor_bootstrap_capabilities: ["SETUID", "SETGID", "SYS_CHROOT", "KILL", "SYS_ADMIN", "SETPCAP"],
  executor_post_bootstrap_capabilities: ["SETUID", "SETGID", "SYS_CHROOT", "KILL"],
  mount_bootstrap_pid1_configured: true,
  delegated_cgroup_path_exact: true,
  persistent_replay_journal_present: true,
  native_openat2_resolver_foundation_packaged: true,
  digest_pinned_openclaw_guest_root_packaged: true,
  host_runtime_root_bind_required: false,
  resolved_fd_handoff_verified: false,
  runtime_path_toctou_closed: false,
  external_provider_egress_operator_attestation_required: true,
  internal_runtime_egress_network_wired: true,
  provider_egress_config_gate_wired: true,
  provider_catalog_replace_mode_required: true,
  runtime_network_policy_verified: false,
  trusted_provider_egress_gateway_wired: true,
  real_typescript_worker_entrypoint_configured: true,
  runtime_sensitive_path_open_denial_contract_wired: true,
  candidate_source_only: true,
  real_linux_acceptance_performed: false,
  runtime_receipt_verified: false,
  hostile_runtime_isolation_verified: false,
})}\n`);
