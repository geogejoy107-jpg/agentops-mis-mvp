#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const byocRoot = dirname(root);
const packageJson = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const lock = JSON.parse(readFileSync(join(root, "package-lock.json"), "utf8"));
const artifact = JSON.parse(readFileSync(join(root, "artifact.json"), "utf8"));
const dockerfile = readFileSync(join(root, "Dockerfile"), "utf8");
const adapter = readFileSync(join(byocRoot, "openclaw-stdin-provider.mjs"), "utf8");
const readme = readFileSync(join(root, "README.md"), "utf8");

const EXPECTED_FILES = [
  "Dockerfile",
  "README.md",
  "artifact.json",
  "contract.mjs",
  "package-lock.json",
  "package.json",
];
const OPENCLAW_INTEGRITY = "sha512-nbLukSwhBr/wqFLKwLKMDCXJ0lIQYpKKJ4Zzp6ZoN6erLjRUkU5MyU5wbY5oChl6yM7TinBYZ3lRw9V6K07DSQ==";
const NODE_INDEX = "sha256:d649c27dae7ba0137b3cef5dd75baa422c08dc3d9e3fc0c23dfb172dc3cc6436";
const FALSE_CLAIMS = [
  "artifact_built",
  "artifact_published",
  "exact_platform_image_verified",
  "guest_root_manifest_signed",
  "resolved_fd_handoff_verified",
  "runtime_path_toctou_closed",
  "real_runtime_process_spawned",
  "provider_call_verified",
  "runtime_receipt_verified",
  "hostile_runtime_isolation_verified",
];

assert.deepEqual(readdirSync(root).sort(), EXPECTED_FILES);
assert.equal(packageJson.dependencies.openclaw, "2026.5.4");
assert.equal(packageJson.engines.node, "22.23.2");
assert.equal(lock.lockfileVersion, 3);
assert.equal(lock.packages[""].dependencies.openclaw, "2026.5.4");
assert.equal(lock.packages["node_modules/openclaw"].version, "2026.5.4");
assert.equal(lock.packages["node_modules/openclaw"].license, "MIT");
assert.equal(lock.packages["node_modules/openclaw"].integrity, OPENCLAW_INTEGRITY);
for (const [name, entry] of Object.entries(lock.packages)) {
  if (name === "") continue;
  assert.match(entry.resolved, /^https:\/\/registry\.npmjs\.org\//, `non_registry_dependency:${name}`);
  assert.match(entry.integrity, /^sha512-[A-Za-z0-9+/]+={0,2}$/, `integrity_missing:${name}`);
  assert.ok(typeof entry.license === "string" && entry.license.length > 0, `license_missing:${name}`);
}

assert.equal(artifact.openclaw.version, "2026.5.4");
assert.equal(artifact.openclaw.license, "MIT");
assert.equal(artifact.openclaw.npm_integrity, OPENCLAW_INTEGRITY);
assert.equal(artifact.node.version, "22.23.2");
assert.equal(artifact.node.index_digest, NODE_INDEX);
assert.equal(artifact.node.image, `node:22.23.2-bookworm-slim@${NODE_INDEX}`);
assert.deepEqual(Object.keys(artifact.platforms).sort(), ["linux/amd64", "linux/arm64/v8"]);
assert.equal(artifact.platforms["linux/amd64"].manifest_digest, "sha256:a17d50af28002a160548bd4225b3cfcb12c5efcb171f79e68758f2885fb1b066");
assert.equal(artifact.platforms["linux/amd64"].base_image, `node:22.23.2-bookworm-slim@${artifact.platforms["linux/amd64"].manifest_digest}`);
assert.equal(artifact.platforms["linux/arm64/v8"].manifest_digest, "sha256:253da19867dd03e2f817f433d7782adefd2a2bac8729fcd4ebc6770665167a24");
assert.equal(artifact.platforms["linux/arm64/v8"].base_image, `node:22.23.2-bookworm-slim@${artifact.platforms["linux/arm64/v8"].manifest_digest}`);
assert.equal(artifact.adapter.source, "deploy/byoc/openclaw-stdin-provider.mjs");
assert.equal(artifact.adapter.guest_path, "/opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs");
for (const claim of FALSE_CLAIMS) assert.equal(artifact.claims[claim], false, `claim_must_be_false:${claim}`);
assert.deepEqual(Object.keys(artifact.claims).sort(), FALSE_CLAIMS.sort());

assert.match(dockerfile, /^# syntax=docker\/dockerfile:1\.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e$/m);
assert.match(dockerfile, /^ARG NODE_IMAGE$/m);
assert.match(dockerfile, /^FROM \$\{NODE_IMAGE\}$/m);
assert.doesNotMatch(dockerfile, /^ARG NODE_IMAGE=/m);
assert.match(dockerfile, /npm ci --ignore-scripts --omit=dev --no-audit --no-fund/);
assert.match(dockerfile, /node -p 'require\("openclaw\/package\.json"\)\.version'/);
assert.match(dockerfile, /COPY --chown=0:0 --chmod=0555 deploy\/byoc\/openclaw-stdin-provider\.mjs/);
assert.match(dockerfile, /ENTRYPOINT \["\/usr\/local\/bin\/node", "\/opt\/agentops\/openclaw-adapter\/openclaw-stdin-provider\.mjs"\]/);
assert.doesNotMatch(dockerfile, /npm install\s+-g|COPY\s+\/usr|\.npmrc|ARG\s+.*(?:TOKEN|KEY|SECRET)|ENV\s+.*(?:TOKEN|KEY|SECRET)/i);
assert.match(dockerfile, /useradd --uid 1200 --gid 1200 --home-dir \/run\/openclaw-state/);
assert.match(dockerfile, /find \/ -xdev -type f -perm \/6000 -exec chmod a-s/);

assert.match(adapter, /import\("openclaw\/plugin-sdk\/agent-runtime"\)/);
assert.match(adapter, /for await \(const chunk of stdin\)/);
assert.match(adapter, /process\.argv\.length !== 3/);
assert.match(adapter, /--stdin-protocol=\$\{STDIN_PROTOCOL\}/);
assert.doesNotMatch(adapter, /--message|child_process|spawn\s*\(|exec(?:File)?\s*\(/);
assert.doesNotMatch(adapter, /console\.(?:log|error)/);
assert.match(adapter, /modelRun: true/);
assert.match(adapter, /provider_call_performed: !failed && outputPresent/);
assert.match(adapter, /readdirSync\(baseStateRoot\)\.length !== 0/);
assert.match(adapter, /for \(const name of readdirSync\(base\)\)/);
assert.match(readme, /All runtime and product claims remain `false`/);

const inputsDigest = createHash("sha256")
  .update([
    ...["Dockerfile", "artifact.json", "package-lock.json", "package.json"]
      .map((name) => `${name}\0${readFileSync(join(root, name))}\0`),
    `deploy/byoc/openclaw-stdin-provider.mjs\0${adapter}\0`,
  ].join(""))
  .digest("hex");

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_guest_root_artifact_input_a07_v1",
  ok: true,
  inputs_sha256: inputsDigest,
  exact_openclaw_version_locked: true,
  npm_lock_integrity_verified: true,
  dependency_license_metadata_complete: true,
  node_22_index_digest_declared: true,
  linux_amd64_digest_declared: true,
  linux_arm64_v8_digest_declared: true,
  checked_in_adapter_guest_path_verified: true,
  global_install_copy_forbidden: true,
  credential_material_absent: true,
  artifact_built: false,
  artifact_published: false,
  exact_platform_image_verified: false,
  guest_root_manifest_signed: false,
  resolved_fd_handoff_verified: false,
  runtime_path_toctou_closed: false,
  real_runtime_process_spawned: false,
  provider_call_verified: false,
  runtime_receipt_verified: false,
  hostile_runtime_isolation_verified: false,
})}\n`);
