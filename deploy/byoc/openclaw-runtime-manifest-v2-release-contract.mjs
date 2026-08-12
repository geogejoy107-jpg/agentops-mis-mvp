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
  unlinkSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  canonicalRuntimeManifestV2Bytes,
  parseCanonicalRuntimeManifestV2Envelope,
  verifyCanonicalRuntimeManifestV2,
} from "./openclaw-runtime-manifest-v2.mjs";
import {
  OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA,
} from "./openclaw-runtime-oci-export.mjs";
import {
  computeOpenClawRuntimeRootfsMerkle,
  OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS,
} from "./openclaw-runtime-rootfs-merkle.mjs";

const script = fileURLToPath(new URL("./openclaw-runtime-manifest-v2-release.mjs", import.meta.url));
const releaseSource = readFileSync(script, "utf8");
const readerSource = readFileSync(
  fileURLToPath(new URL("./openclaw-runtime-release.mjs", import.meta.url)),
  "utf8",
);
const digest = (character) => character.repeat(64);
const OCI_NAME = "registry.invalid/agentops/openclaw-runtime";
const OCI_DIGEST = `sha256:${digest("a")}`;
const OCI = `${OCI_NAME}@${OCI_DIGEST}`;
const CREATED = "2026-08-12T00:00:00.000Z";
const EXPIRES = "2026-08-19T00:00:00.000Z";
const KEY_ID = "runtime-manifest-key-2026-08";
const ISSUER = "agentops-release";
const FILES = [
  "openclaw-runtime-manifest-metadata-receipt.json",
  "openclaw-runtime-manifest.json",
  "openclaw-runtime-oci-export-provenance.json",
];

function sourceAudit() {
  const optionBlock = /const EXPECTED_OPTIONS = Object\.freeze\(\[([\s\S]*?)\]\);/.exec(releaseSource)?.[1] || "";
  assert.match(optionBlock, /"--provenance"/);
  assert.doesNotMatch(optionBlock, /"--guest-root"/);
  assert.doesNotMatch(optionBlock, /"--oci"/);
  assert.match(releaseSource, /readCommittedOpenClawRuntimeOciExportReceipt\(input\.provenance\)/);
  assert.match(releaseSource, /runtime_manifest_v2_release_provenance_rootfs_mismatch/);
  assert.match(releaseSource, /oci_export_provenance/);
  assert.match(readerSource, /runtime_release_receipt_provenance_invalid/);
  assert.match(readerSource, /runtime_release_receipt_manifest_binding_invalid/);
}

function stableResult(overrides = {}) {
  return {
    contract: "agentops_openclaw_runtime_manifest_v2_release_contract_v1",
    source_audit_verified: true,
    provenance_only_input_verified: true,
    independent_guest_root_and_oci_inputs_rejected: true,
    root_contract_executed: false,
    committed_provenance_remeasured: false,
    provenance_sha256_bound_to_release_receipt: false,
    oci_and_rootfs_manifest_binding_verified: false,
    provenance_tamper_rejected: false,
    deterministic_release_verified: false,
    ed25519_verification_performed: false,
    output_mode_0444_verified: false,
    private_key_not_copied: true,
    pinned_trust_root_verified: false,
    trust_root_not_copied: true,
    key_metadata_fail_closed: false,
    overwrite_and_noncanonical_inputs_rejected: false,
    ...overrides,
  };
}

function fixture(base) {
  const root = path.join(base, "guest-root");
  for (const directory of [
    "",
    "opt/agentops/openclaw-adapter",
    "opt/agentops-worker/workspace",
    "opt/openclaw",
    "run/openclaw-state",
    "run/secrets",
    "tmp",
    "usr/local/bin",
  ]) mkdirSync(path.join(root, directory), { recursive: true, mode: 0o755 });
  writeFileSync(
    path.join(root, "opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs"),
    "export const adapter = true;\n",
    { mode: 0o555 },
  );
  writeFileSync(path.join(root, "opt/openclaw/package.json"), '{"version":"2026.5.4"}\n', { mode: 0o444 });
  writeFileSync(path.join(root, "usr/local/bin/node"), "node-runtime\n", { mode: 0o555 });
  writeFileSync(path.join(root, "run/secrets/openclaw_config"), "{}\n", { mode: 0o400 });
  for (const directory of [
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
  ]) chmodSync(path.join(root, directory), 0o555);
  return root;
}

function writeProvenance(base, root) {
  const receiptPath = path.join(base, "openclaw-runtime-oci-provenance.json");
  const rootfs = computeOpenClawRuntimeRootfsMerkle(
    root,
    OPENCLAW_RUNTIME_CANONICAL_GUEST_MOUNT_PATHS,
  );
  const rootMetadata = lstatSync(root, { bigint: true });
  const toolIdentity = (toolPath, character) => ({
    ctime_ns: "1",
    dev: "1",
    gid: 0,
    ino: "1",
    mode: "0555",
    path: toolPath,
    sha256: digest(character),
    size: 1,
    uid: 0,
  });
  const receipt = {
    export_archive_sha256: digest("d"),
    export_policy: {
      archive_format: "strict_ustar_only_gnu_longname_and_pax_extensions_rejected_fail_closed",
      extraction: "two_identical_stopped_container_exports_strict_ustar_then_gnu_tar_stream",
      root_directory: "normalized_root_0_0_0555",
    },
    export_tool_identity: {
      docker: toolIdentity("/usr/bin/docker", "1"),
      mv: toolIdentity("/usr/bin/mv", "2"),
      tar: toolIdentity("/usr/bin/tar", "3"),
    },
    guest_root: root,
    guest_root_identity: {
      ctime_ns: rootMetadata.ctimeNs.toString(),
      dev: rootMetadata.dev.toString(),
      gid: Number(rootMetadata.gid),
      ino: rootMetadata.ino.toString(),
      mode: Number(rootMetadata.mode & 0o7777n).toString(8).padStart(4, "0"),
      mtime_ns: rootMetadata.mtimeNs.toString(),
      uid: Number(rootMetadata.uid),
    },
    oci: { digest: OCI_DIGEST, exact_reference: OCI, name: OCI_NAME },
    platform: { architecture: "amd64", os: "linux" },
    rootfs,
    schema: OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA,
    source_image_id: `sha256:${digest("e")}`,
  };
  const bytes = canonicalRuntimeManifestV2Bytes(receipt);
  writeFileSync(receiptPath, bytes, { flag: "wx", mode: 0o444 });
  chmodSync(receiptPath, 0o444);
  return { bytes, receiptPath, rootfs };
}

function argumentsFor(provenance, key, trustRoot, output, overrides = {}) {
  const values = {
    "cgroup-policy-sha256": digest("b"),
    created: CREATED,
    expires: EXPIRES,
    issuer: ISSUER,
    "key-id": KEY_ID,
    output,
    "private-key": key,
    provenance,
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
    assert.equal(metadata.uid, 0);
    assert.equal(metadata.gid, 0);
    assert.equal(metadata.mode & 0o777, 0o444);
  }
  assert.equal(lstatSync(directory).mode & 0o777, 0o555);
  return bytes;
}

function makeTreeRemovable(directory) {
  let metadata;
  try { metadata = lstatSync(directory); } catch { return; }
  if (!metadata.isDirectory() || metadata.isSymbolicLink()) return;
  chmodSync(directory, 0o755);
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.isSymbolicLink()) makeTreeRemovable(path.join(directory, entry.name));
  }
}

sourceAudit();
const requireRoot = process.argv.includes("--require-root");
if (process.platform !== "linux" || process.geteuid?.() !== 0) {
  if (requireRoot) {
    process.stderr.write("runtime_manifest_v2_release_root_contract_required\n");
    process.exit(1);
  }
  process.stdout.write(`${JSON.stringify(stableResult())}\n`);
  process.exit(0);
}

const base = mkdtempSync("/root/agentops-manifest-v2-release-");
try {
  const root = fixture(base);
  const provenance = writeProvenance(base, root);
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
  const firstResult = JSON.parse(run(argumentsFor(provenance.receiptPath, keyPath, trustPath, firstOutput)).stdout);
  const secondResult = JSON.parse(run(argumentsFor(provenance.receiptPath, keyPath, trustPath, secondOutput)).stdout);
  const first = readRelease(firstOutput);
  const second = readRelease(secondOutput);
  assert.deepEqual(second, first);
  assert.equal(firstResult.manifest_sha256, secondResult.manifest_sha256);
  assert.equal(firstResult.provenance_sha256, sha256(provenance.bytes));

  const manifestBytes = first["openclaw-runtime-manifest.json"];
  const receiptBytes = first["openclaw-runtime-manifest-metadata-receipt.json"];
  const envelope = parseCanonicalRuntimeManifestV2Envelope(manifestBytes);
  const receipt = JSON.parse(receiptBytes.toString("utf8"));
  assert.deepEqual(envelope.body.oci_image, { digest: OCI_DIGEST, name: OCI_NAME });
  assert.deepEqual(envelope.body.rootfs, {
    byte_count: provenance.rootfs.byte_count,
    file_count: provenance.rootfs.file_count,
    merkle_sha256: provenance.rootfs.merkle_sha256,
  });
  assert.equal(
    provenance.rootfs.schema,
    "agentops_openclaw_runtime_rootfs_merkle_v1",
  );
  assert.equal(receipt.oci_export_provenance.schema, OPENCLAW_RUNTIME_OCI_EXPORT_PROVENANCE_SCHEMA);
  assert.equal(receipt.oci_export_provenance.sha256, sha256(provenance.bytes));
  assert.deepEqual(
    first["openclaw-runtime-oci-export-provenance.json"],
    provenance.bytes,
  );
  assert.equal(receipt.files.manifest.sha256, sha256(manifestBytes));
  assert.ok(!Buffer.concat(Object.values(first)).includes(privatePem.trim()));
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
  assert.equal(verifyCanonicalRuntimeManifestV2(manifestBytes, trust.keys, expected).key_id, KEY_ID);

  const oldArguments = [
    ...argumentsFor(provenance.receiptPath, keyPath, trustPath, path.join(base, "old-input")),
    "--guest-root", root,
    "--oci", OCI,
  ];
  assert.match(run(oldArguments, 1).stderr, /runtime_manifest_v2_release_options_invalid/);

  chmodSync(provenance.receiptPath, 0o644);
  assert.match(
    run(argumentsFor(provenance.receiptPath, keyPath, trustPath, path.join(base, "writable-provenance")), 1).stderr,
    /runtime_oci_export_commit_receipt_metadata_invalid/,
  );
  chmodSync(provenance.receiptPath, 0o444);
  const provenanceLink = path.join(base, "provenance-hardlink.json");
  linkSync(provenance.receiptPath, provenanceLink);
  assert.match(
    run(argumentsFor(provenance.receiptPath, keyPath, trustPath, path.join(base, "linked-provenance")), 1).stderr,
    /runtime_oci_export_commit_receipt_metadata_invalid/,
  );
  unlinkSync(provenanceLink);

  const nodePath = path.join(root, "usr/local/bin/node");
  chmodSync(nodePath, 0o755);
  writeFileSync(nodePath, "tampered-runtime\n", { mode: 0o555 });
  chmodSync(nodePath, 0o555);
  assert.match(
    run(argumentsFor(provenance.receiptPath, keyPath, trustPath, path.join(base, "tampered-root")), 1).stderr,
    /runtime_oci_export_commit_rootfs_merkle_mismatch/,
  );

  process.stdout.write(`${JSON.stringify(stableResult({
    root_contract_executed: true,
    committed_provenance_remeasured: true,
    provenance_sha256_bound_to_release_receipt: true,
    oci_and_rootfs_manifest_binding_verified: true,
    provenance_tamper_rejected: true,
    deterministic_release_verified: true,
    ed25519_verification_performed: true,
    output_mode_0444_verified: true,
    pinned_trust_root_verified: true,
    key_metadata_fail_closed: true,
    overwrite_and_noncanonical_inputs_rejected: true,
  }))}\n`);
} finally {
  makeTreeRemovable(base);
  rmSync(base, { recursive: true, force: true });
}
