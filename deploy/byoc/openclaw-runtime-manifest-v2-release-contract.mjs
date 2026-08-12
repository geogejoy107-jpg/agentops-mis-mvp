#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash, generateKeyPairSync } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  linkSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  rmSync,
  symlinkSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  canonicalRuntimeManifestV2Bytes,
  parseCanonicalRuntimeManifestV2Envelope,
  verifyCanonicalRuntimeManifestV2,
} from "./openclaw-runtime-manifest-v2.mjs";

const script = fileURLToPath(new URL("./openclaw-runtime-manifest-v2-release.mjs", import.meta.url));
const digest = (character) => character.repeat(64);
const OCI = `registry.invalid/agentops/openclaw-runtime@sha256:${digest("a")}`;
const CREATED = "2026-08-12T00:00:00.000Z";
const EXPIRES = "2026-08-19T00:00:00.000Z";
const KEY_ID = "runtime-manifest-key-2026-08";
const ISSUER = "agentops-release";
const FILES = [
  "openclaw-runtime-manifest-metadata-receipt.json",
  "openclaw-runtime-manifest.json",
];

function fixture(base) {
  const root = path.join(base, "guest-root");
  const directories = [
    "",
    "opt/agentops/openclaw-adapter",
    "opt/agentops-worker/workspace",
    "opt/openclaw",
    "run/openclaw-state",
    "run/secrets",
    "tmp",
    "usr/local/bin",
  ];
  for (const directory of directories) {
    mkdirSync(path.join(root, directory), { recursive: true, mode: 0o755 });
  }
  writeFileSync(
    path.join(root, "opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs"),
    "export const adapter = true;\n",
    { mode: 0o555 },
  );
  writeFileSync(path.join(root, "opt/openclaw/package.json"), '{"version":"2026.5.4"}\n', { mode: 0o444 });
  writeFileSync(path.join(root, "usr/local/bin/node"), "node-runtime\n", { mode: 0o555 });
  writeFileSync(path.join(root, "run/secrets/openclaw_config"), "{}\n", { mode: 0o400 });
  const allDirectories = [
    "opt/agentops/openclaw-adapter",
    "opt/agentops",
    "opt/agentops-worker/workspace",
    "opt/agentops-worker",
    "opt/openclaw",
    "opt",
    "run/openclaw-state",
    "run/secrets",
    "run",
    "tmp",
    "usr/local/bin",
    "usr/local",
    "usr",
    "",
  ];
  for (const directory of allDirectories) chmodSync(path.join(root, directory), 0o555);
  return root;
}

function argumentsFor(root, key, trustRoot, output, overrides = {}) {
  const values = {
    "cgroup-policy-sha256": digest("b"),
    created: CREATED,
    expires: EXPIRES,
    "guest-root": root,
    issuer: ISSUER,
    "key-id": KEY_ID,
    oci: OCI,
    output,
    "private-key": key,
    "seccomp-profile-sha256": digest("c"),
    "trust-root": trustRoot,
    ...overrides,
  };
  return Object.entries(values).flatMap(([name, value]) => [`--${name}`, value]);
}

function run(arguments_, expectedStatus = 0) {
  const result = spawnSync(process.execPath, [script, ...arguments_], { encoding: "utf8" });
  assert.equal(result.status, expectedStatus, result.stderr || result.stdout);
  return result;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function readRelease(directory) {
  assert.deepEqual(readdirSync(directory).sort(), FILES);
  const bytes = Object.fromEntries(FILES.map((name) => [name, readFileSync(path.join(directory, name))]));
  for (const name of FILES) {
    const metadata = lstatSync(path.join(directory, name));
    assert.ok(metadata.isFile() && !metadata.isSymbolicLink());
    assert.equal(metadata.nlink, 1);
    assert.equal(metadata.mode & 0o777, 0o444);
  }
  assert.equal(lstatSync(directory).mode & 0o777, 0o555);
  return bytes;
}

function makeTreeRemovable(directory) {
  let metadata;
  try {
    metadata = lstatSync(directory);
  } catch {
    return;
  }
  if (!metadata.isDirectory() || metadata.isSymbolicLink()) return;
  chmodSync(directory, 0o755);
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.isSymbolicLink()) {
      makeTreeRemovable(path.join(directory, entry.name));
    }
  }
}

const base = mkdtempSync(path.join(tmpdir(), "agentops-manifest-v2-release-"));
try {
  const root = fixture(base);
  const keyPath = path.join(base, "manifest-signing-key.pem");
  const signing = generateKeyPairSync("ed25519");
  const privatePem = signing.privateKey.export({ type: "pkcs8", format: "pem" });
  writeFileSync(keyPath, privatePem, { mode: 0o400 });
  chmodSync(keyPath, 0o400);
  const trustPath = path.join(base, "pinned-trust-roots.json");
  const trust = {
    keys: { [KEY_ID]: signing.publicKey.export({ type: "spki", format: "pem" }) },
    schema: "agentops_openclaw_runtime_manifest_trust_roots_v1",
  };
  const trustBytes = canonicalRuntimeManifestV2Bytes(trust);
  writeFileSync(trustPath, trustBytes, { mode: 0o444 });
  chmodSync(trustPath, 0o444);

  const firstOutput = path.join(base, "release-one");
  const secondOutput = path.join(base, "release-two");
  const firstResult = JSON.parse(run(argumentsFor(root, keyPath, trustPath, firstOutput)).stdout);
  const secondResult = JSON.parse(run(argumentsFor(root, keyPath, trustPath, secondOutput)).stdout);
  const first = readRelease(firstOutput);
  const second = readRelease(secondOutput);
  assert.deepEqual(second, first);
  assert.equal(firstResult.manifest_sha256, secondResult.manifest_sha256);
  assert.equal(firstResult.private_key_copied, false);
  assert.equal(firstResult.trust_root_copied, false);

  const manifestBytes = first["openclaw-runtime-manifest.json"];
  const receiptBytes = first["openclaw-runtime-manifest-metadata-receipt.json"];
  const envelope = parseCanonicalRuntimeManifestV2Envelope(manifestBytes);
  const receipt = JSON.parse(receiptBytes.toString("utf8"));
  assert.deepEqual(canonicalRuntimeManifestV2Bytes(receipt), receiptBytes);
  assert.deepEqual(Object.values(envelope.body.claims), [false, false, false, false, false]);
  assert.deepEqual(envelope.body.platform, { arch: "amd64", libc: "glibc", os: "linux" });
  assert.equal(receipt.private_key_copied, false);
  assert.equal(receipt.trust_root_copied, false);
  assert.equal(receipt.trust_root_sha256, sha256(trustBytes));
  assert.equal(receipt.files.manifest.sha256, sha256(manifestBytes));
  assert.ok(!Buffer.concat(Object.values(first)).includes(privatePem.trim()));
  assert.ok(!Buffer.concat(Object.values(first)).includes(Buffer.from(keyPath)));
  assert.ok(!Buffer.concat(Object.values(first)).includes(trustBytes));

  const body = envelope.body;
  const expected = {
    body_sha256: sha256(canonicalRuntimeManifestV2Bytes(body)),
    cgroup_policy_sha256: body.cgroup_policy_sha256,
    entrypoint: body.entrypoint,
    issuer: body.issuer,
    key_id: body.key_id,
    oci_image: body.oci_image,
    platform: body.platform,
    rootfs_merkle_sha256: body.rootfs.merkle_sha256,
    runtime_executable: body.runtime_executable,
    runtime_gid: 1200,
    runtime_uid: 1200,
    seccomp_profile_sha256: body.seccomp_profile_sha256,
    verification_time: "2026-08-13T00:00:00.000Z",
  };
  assert.equal(
    verifyCanonicalRuntimeManifestV2(manifestBytes, trust.keys, expected).key_id,
    KEY_ID,
  );

  const existingOutput = path.join(base, "existing");
  mkdirSync(existingOutput, { mode: 0o755 });
  const overwrite = run(argumentsFor(root, keyPath, trustPath, existingOutput), 1);
  assert.match(overwrite.stderr, /runtime_manifest_v2_release_output_exists/);
  assert.deepEqual(readdirSync(existingOutput), []);

  const reservedOutput = path.join(base, "reserved-output");
  mkdirSync(reservedOutput, { mode: 0o700 });
  const reserved = run(argumentsFor(root, keyPath, trustPath, reservedOutput), 1);
  assert.match(reserved.stderr, /runtime_manifest_v2_release_output_exists/);
  assert.deepEqual(readdirSync(reservedOutput), []);

  chmodSync(keyPath, 0o600);
  assert.match(
    run(argumentsFor(root, keyPath, trustPath, path.join(base, "wide-key-output")), 1).stderr,
    /runtime_manifest_v2_release_private_key_metadata_invalid/,
  );
  chmodSync(keyPath, 0o400);

  const keyLink = path.join(base, "key-link.pem");
  symlinkSync(keyPath, keyLink);
  assert.match(
    run(argumentsFor(root, keyLink, trustPath, path.join(base, "symlink-key-output")), 1).stderr,
    /runtime_manifest_v2_release_private_key_metadata_invalid/,
  );

  const hardKey = path.join(base, "key-hardlink.pem");
  linkSync(keyPath, hardKey);
  assert.match(
    run(argumentsFor(root, keyPath, trustPath, path.join(base, "hardlink-key-output")), 1).stderr,
    /runtime_manifest_v2_release_private_key_metadata_invalid/,
  );
  unlinkSync(hardKey);

  const attacker = generateKeyPairSync("ed25519");
  const attackerTrustPath = path.join(base, "attacker-trust-roots.json");
  writeFileSync(attackerTrustPath, canonicalRuntimeManifestV2Bytes({
    keys: { [KEY_ID]: attacker.publicKey.export({ type: "spki", format: "pem" }) },
    schema: "agentops_openclaw_runtime_manifest_trust_roots_v1",
  }), { mode: 0o444 });
  chmodSync(attackerTrustPath, 0o444);
  assert.match(
    run(argumentsFor(root, keyPath, attackerTrustPath, path.join(base, "attacker-output")), 1).stderr,
    /runtime_manifest_v2_release_signing_key_not_pinned/,
  );

  chmodSync(trustPath, 0o644);
  assert.match(
    run(argumentsFor(root, keyPath, trustPath, path.join(base, "writable-trust-output")), 1).stderr,
    /runtime_manifest_v2_release_trust_root_metadata_invalid/,
  );
  chmodSync(trustPath, 0o444);

  for (const [overrides, pattern, name] of [
    [{ created: "2026-08-12T00:00:00Z" }, /runtime_manifest_v2_release_created_invalid/, "timestamp"],
    [{ oci: `Registry.invalid/agentops/runtime@sha256:${digest("a")}` }, /runtime_manifest_v2_release_oci_invalid/, "oci"],
    [{ "guest-root": `${root}/` }, /runtime_manifest_v2_release_guest_root_noncanonical/, "root"],
    [{ output: `${path.join(base, "noncanonical-output")}/` }, /runtime_manifest_v2_release_output_noncanonical/, "output"],
  ]) {
    const result = run(argumentsFor(root, keyPath, trustPath, path.join(base, `rejected-${name}`), overrides), 1);
    assert.match(result.stderr, pattern);
  }

  process.stdout.write(`${JSON.stringify({
    contract: "agentops_openclaw_runtime_manifest_v2_release_contract_v1",
    deterministic_release_verified: true,
    ed25519_verification_performed: true,
    output_mode_0444_verified: true,
    private_key_not_copied: true,
    pinned_trust_root_verified: true,
    trust_root_not_copied: true,
    key_metadata_fail_closed: true,
    overwrite_and_noncanonical_inputs_rejected: true,
    claims: envelope.body.claims,
  })}\n`);
} finally {
  makeTreeRemovable(base);
  rmSync(base, { recursive: true, force: true });
}
