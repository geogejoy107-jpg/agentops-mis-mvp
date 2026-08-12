#!/usr/bin/env node

import assert from "node:assert/strict";
import { chmodSync, linkSync, lstatSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { inspectExecutorLauncher, loadExecutorConfiguration } from "./openclaw-executor-service.mjs";

const digest = (character) => character.repeat(64);
const environment = {
  OPENCLAW_EXECUTOR_SOCKET: "/run/test/executor.sock",
  OPENCLAW_EXECUTOR_SOCKET_GID: "2200",
  OPENCLAW_EXECUTOR_JOURNAL_ROOT: "/var/lib/test/replay",
  OPENCLAW_EXECUTOR_LAUNCHER: "/usr/local/bin/launcher",
  OPENCLAW_CGROUP_ROOT: "/sys/fs/cgroup/agentops-openclaw-executor",
  OPENCLAW_CGROUP_POLICY_PATH: "/run/policy/cgroup.json",
  OPENCLAW_SECCOMP_PROFILE_PATH: "/run/policy/seccomp.json",
  OPENCLAW_RUNTIME_MANIFEST_PATH: "/run/manifest/runtime.json",
  OPENCLAW_RUNTIME_MANIFEST_TRUST_ROOT_PATH: "/run/manifest/roots.json",
  OPENCLAW_RUNTIME_MANIFEST_ISSUER: "agentops-release",
  OPENCLAW_RUNTIME_MANIFEST_KEY_ID: "manifest-key-1",
  OPENCLAW_RECEIPT_SIGNING_KEY_PATH: "/run/secret/receipt-key",
  OPENCLAW_RECEIPT_KEY_ID: "receipt-key-1",
  OPENCLAW_EXECUTOR_IMAGE_REFERENCE: `registry.invalid/agentops/a07@sha256:${digest("1")}`,
  OPENCLAW_RUNTIME_IMAGE_DIGEST: `sha256:${digest("2")}`,
  OPENCLAW_RUNTIME_IMAGE_NAME: "registry.invalid/openclaw-runtime",
  OPENCLAW_RUNTIME_ROOT: "/opt/openclaw",
  OPENCLAW_RUNTIME_UID: "1200",
  OPENCLAW_RUNTIME_GID: "1200",
  OPENCLAW_EXTERNAL_PROVIDER_EGRESS_ATTESTED: "true",
};
const configuration = loadExecutorConfiguration(environment);
assert.equal(configuration.runtimeUid, 1200);
assert.equal(configuration.runtimeGid, 1200);
assert.equal(configuration.providerEgressOperatorAttested, true);
assert.equal(configuration.executorImageDigest, `sha256:${digest("1")}`);
for (const [name, value] of [
  ["OPENCLAW_RUNTIME_UID", "1001"],
  ["OPENCLAW_EXECUTOR_SOCKET_GID", "0"],
  ["OPENCLAW_EXECUTOR_IMAGE_REFERENCE", `registry.invalid/agentops/a07:mutable@sha256:${digest("1")}`],
  ["OPENCLAW_EXECUTOR_SOCKET", "relative.sock"],
  ["OPENCLAW_EXTERNAL_PROVIDER_EGRESS_ATTESTED", "false"],
]) {
  assert.throws(() => loadExecutorConfiguration({ ...environment, [name]: value }), /executor_/);
}
const launcherRoot = mkdtempSync(path.join(os.tmpdir(), "agentops-executor-launcher-"));
try {
  const launcherPath = path.join(launcherRoot, "launcher");
  const launcherLinkPath = path.join(launcherRoot, "launcher-link");
  const launcherSymlinkPath = path.join(launcherRoot, "launcher-symlink");
  writeFileSync(launcherPath, "contract launcher\n", { mode: 0o555 });
  chmodSync(launcherPath, 0o555);
  const metadata = lstatSync(launcherPath);
  assert.deepEqual(
    inspectExecutorLauncher(launcherPath, { expectedUid: metadata.uid, expectedGid: metadata.gid }),
    { dev: metadata.dev, ino: metadata.ino },
  );
  chmodSync(launcherPath, 0o755);
  assert.throws(
    () => inspectExecutorLauncher(launcherPath, { expectedUid: metadata.uid, expectedGid: metadata.gid }),
    /executor_launcher_metadata_invalid/,
  );
  chmodSync(launcherPath, 0o555);
  linkSync(launcherPath, launcherLinkPath);
  assert.throws(
    () => inspectExecutorLauncher(launcherPath, { expectedUid: metadata.uid, expectedGid: metadata.gid }),
    /executor_launcher_metadata_invalid/,
  );
  rmSync(launcherLinkPath);
  symlinkSync(launcherPath, launcherSymlinkPath);
  assert.throws(
    () => inspectExecutorLauncher(launcherSymlinkPath, { expectedUid: metadata.uid, expectedGid: metadata.gid }),
    /executor_launcher_metadata_invalid/,
  );
} finally {
  rmSync(launcherRoot, { recursive: true, force: true });
}
const source = readFileSync(fileURLToPath(new URL("./openclaw-executor-service.mjs", import.meta.url)), "utf8");
assert.match(source, /verifyCanonicalRuntimeManifestAndTree/);
assert.match(source, /inspectDelegatedCgroupRoot/);
assert.match(source, /ExecutorReplayJournal\.open/);
assert.match(source, /ExecutorLaunchIntegrationIncomplete/);
assert.match(source, /ready: false/);
assert.match(source, /writeJson\(response, 503/);
assert.match(source, /runtime_process_spawned: false/);
assert.match(source, /runtime_receipt_verified: false/);
assert.doesNotMatch(source, /runtime_receipt_verified: true/);
console.log(JSON.stringify({
  contract: "agentops_openclaw_root_executor_service_foundation_a07_v1",
  strict_configuration_verified: true,
  immutable_executor_image_reference_bound: true,
  root_owned_single_link_launcher_metadata_required: true,
  signed_manifest_and_exact_tree_preflight_present: true,
  cgroup_delegation_preflight_present: true,
  crash_recovery_preflight_present: true,
  execute_route_fail_closed_until_launch_integration: true,
  health_ready: false,
  runtime_process_spawned: false,
  runtime_receipt_verified: false,
  hostile_runtime_isolation_verified: false,
}));
