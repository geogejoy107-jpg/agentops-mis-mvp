#!/usr/bin/env node

import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import {
  chmod,
  link,
  mkdir,
  mkdtemp,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { createServer } from "node:net";
import os from "node:os";
import path from "node:path";
import {
  canonicalRuntimeManifestBytes,
  generateRuntimeManifest,
  MAX_RUNTIME_MANIFEST_BYTES,
  runtimeManifestSha256,
  serializeRuntimeManifestEnvelope,
  signRuntimeManifest,
  verifyCanonicalRuntimeManifest,
  verifyCanonicalRuntimeManifestAndTree,
  verifyRuntimeManifestTree,
} from "./openclaw-runtime-manifest.mjs";

const digest = (character) => character.repeat(64);
const primary = generateKeyPairSync("ed25519");
const other = generateKeyPairSync("ed25519");
const wrongAlgorithm = generateKeyPairSync("rsa", { modulusLength: 2048 });
const root = await mkdtemp(path.join(os.tmpdir(), "agentops-runtime-manifest-"));

async function addFile(relativePath, contents, mode) {
  const absolutePath = path.join(root, ...relativePath.split("/"));
  const parent = path.dirname(absolutePath);
  await mkdir(parent, { recursive: true });
  await chmod(parent, 0o755);
  await writeFile(absolutePath, contents, { mode: 0o600 });
  await chmod(absolutePath, mode);
  await chmod(parent, 0o555);
}

async function removePath(relativePath, options = {}) {
  const absolutePath = path.join(root, ...relativePath.split("/"));
  const parent = path.dirname(absolutePath);
  await chmod(parent, 0o755);
  await rm(absolutePath, options);
  await chmod(parent, 0o555);
}

async function listenUnixSocket(socketPath) {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(socketPath, resolve);
  });
  return server;
}

const metadata = {
  argv_template: ["/usr/bin/node", "/app/main.mjs", "--mode=provider"],
  cgroup_policy_sha256: digest("2"),
  created_at: "2026-08-12T00:00:00.000Z",
  entrypoint: "/app/main.mjs",
  environment_name_allowlist: [
    "LANG",
    "OPENCLAW_CONFIG_PATH",
    "OPENCLAW_STATE_DIR",
    "OPENCLAW_WORKSPACE",
    "PATH",
  ],
  expires_at: "2026-09-12T00:00:00.000Z",
  issuer: "agentops-release",
  key_id: "runtime-manifest-key-1",
  oci_image_digest: `sha256:${digest("1")}`,
  oci_image_name: "registry.example.invalid/agentops/openclaw@sha256",
  runtime_created_path_allowlist: ["/run/agentops/cache", "/run/agentops/tmp"],
  runtime_executable: "/usr/bin/node",
  runtime_gid: 1200,
  runtime_state_root: "/run/agentops",
  runtime_uid: 1200,
  seccomp_profile_sha256: digest("3"),
};
const expected = {
  cgroup_policy_sha256: metadata.cgroup_policy_sha256,
  entrypoint: metadata.entrypoint,
  issuer: metadata.issuer,
  key_id: metadata.key_id,
  oci_image_digest: metadata.oci_image_digest,
  oci_image_name: metadata.oci_image_name,
  runtime_executable: metadata.runtime_executable,
  runtime_gid: 1200,
  runtime_uid: 1200,
  seccomp_profile_sha256: metadata.seccomp_profile_sha256,
  verification_time: "2026-08-12T12:00:00.000Z",
};

try {
  await addFile("app/lib/provider.mjs", "export const provider = 'openclaw';\n", 0o444);
  await addFile("app/main.mjs", "import './lib/provider.mjs';\n", 0o444);
  await addFile("app/package.json", '{"type":"module"}\n', 0o444);
  await addFile("usr/bin/node", "contract-runtime-executable\n", 0o555);
  for (const directory of [root, path.join(root, "app"), path.join(root, "app/lib"), path.join(root, "usr"), path.join(root, "usr/bin")]) {
    await chmod(directory, 0o555);
  }

  const envelope = await generateRuntimeManifest(root, metadata, primary.privateKey);
  const bytes = serializeRuntimeManifestEnvelope(envelope);
  const roots = new Map([[metadata.key_id, primary.publicKey]]);
  const verified = verifyCanonicalRuntimeManifest(bytes, roots, expected);
  assert.equal(verified.files.length, 4);
  assert.equal(Object.isFrozen(verified), true);
  assert.equal(Object.isFrozen(verified.files), true);
  assert.equal(Object.isFrozen(verified.files[0]), true);
  assert.deepEqual(verified.files.map((file) => file.path), [
    "app/lib/provider.mjs",
    "app/main.mjs",
    "app/package.json",
    "usr/bin/node",
  ]);
  const exact = await verifyCanonicalRuntimeManifestAndTree(bytes, root, roots, expected);
  assert.equal(exact.tree.exact_tree_verified, true);
  assert.equal(exact.tree.measured_file_count, 4);
  assert.match(runtimeManifestSha256(bytes), /^[a-f0-9]{64}$/);
  assert.throws(
    () => signRuntimeManifest({
      ...envelope.body,
      environment_name_allowlist: ["HOME", "LANG", "NODE_OPTIONS", "PATH"],
    }, metadata.key_id, primary.privateKey),
    /runtime_manifest_environment_name_allowlist_mismatch/,
  );

  assert.deepEqual(
    canonicalRuntimeManifestBytes({ z: 1, a: { y: false, b: "value" } }),
    Buffer.from('{"a":{"b":"value","y":false},"z":1}'),
  );

  assert.throws(
    () => signRuntimeManifest(envelope.body, metadata.key_id, wrongAlgorithm.privateKey),
    /runtime_manifest_private_key_invalid/,
  );
  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      bytes,
      new Map([[metadata.key_id, wrongAlgorithm.publicKey]]),
      expected,
    ),
    /runtime_manifest_public_key_invalid/,
  );
  assert.throws(
    () => verifyCanonicalRuntimeManifest(bytes, new Map([[metadata.key_id, other.publicKey]]), expected),
    /runtime_manifest_signature_unverified/,
  );
  assert.throws(
    () => verifyCanonicalRuntimeManifest(bytes, new Map(), expected),
    /runtime_manifest_unknown_key/,
  );

  const tamperedFirstCharacter = envelope.signature[0] === "A" ? "B" : "A";
  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      serializeRuntimeManifestEnvelope({
        ...envelope,
        signature: `${tamperedFirstCharacter}${envelope.signature.slice(1)}`,
      }),
      roots,
      expected,
    ),
    /runtime_manifest_signature_unverified/,
  );
  const noncanonicalFinalCharacter = new Map([
    ["A", "B"],
    ["Q", "R"],
    ["g", "h"],
    ["w", "x"],
  ]).get(envelope.signature.at(-1));
  assert.ok(noncanonicalFinalCharacter);
  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      serializeRuntimeManifestEnvelope({
        ...envelope,
        signature: `${envelope.signature.slice(0, -1)}${noncanonicalFinalCharacter}`,
      }),
      roots,
      expected,
    ),
    /runtime_manifest_signature_invalid/,
  );
  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      bytes,
      roots,
      { ...expected, verification_time: "2026-10-01T00:00:00.000Z" },
    ),
    /runtime_manifest_verification_time_invalid/,
  );
  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      bytes,
      roots,
      { ...expected, cgroup_policy_sha256: digest("9") },
    ),
    /runtime_manifest_cgroup_policy_sha256_mismatch/,
  );

  const duplicatePathBody = {
    ...envelope.body,
    files: [...envelope.body.files, { ...envelope.body.files.at(-1) }],
  };
  assert.throws(
    () => signRuntimeManifest(duplicatePathBody, metadata.key_id, primary.privateKey),
    /runtime_manifest_file_path_order_invalid/,
  );
  const caseConflictBody = {
    ...envelope.body,
    files: [
      { ...envelope.body.files[0], path: "APP/lib/provider.mjs" },
      ...envelope.body.files,
    ].sort((left, right) => left.path < right.path ? -1 : left.path > right.path ? 1 : 0),
  };
  assert.throws(
    () => signRuntimeManifest(caseConflictBody, metadata.key_id, primary.privateKey),
    /runtime_manifest_file_path_case_conflict/,
  );
  const traversalBody = {
    ...envelope.body,
    files: [{ ...envelope.body.files[0], path: "../escape" }, ...envelope.body.files.slice(1)],
  };
  assert.throws(
    () => signRuntimeManifest(traversalBody, metadata.key_id, primary.privateKey),
    /runtime_manifest_file_path_invalid/,
  );

  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      Buffer.from(` ${bytes.toString("utf8")}`),
      roots,
      expected,
    ),
    /runtime_manifest_encoding_noncanonical/,
  );
  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      Buffer.from(bytes.toString("utf8").replace(
        '"algorithm":"Ed25519"',
        '"algorithm":"Ed25519","algorithm":"Ed25519"',
      )),
      roots,
      expected,
    ),
    /runtime_manifest_encoding_noncanonical/,
  );
  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      Buffer.alloc(MAX_RUNTIME_MANIFEST_BYTES + 1, 0x20),
      roots,
      expected,
    ),
    /runtime_manifest_size_invalid/,
  );
  const deeplyNested = `${"[".repeat(3_000)}0${"]".repeat(3_000)}`;
  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      Buffer.from(`{"algorithm":"Ed25519","body":${deeplyNested},"key_id":"key","schema":"schema","signature":"signature"}`),
      roots,
      expected,
    ),
    /runtime_manifest_body_invalid/,
  );
  assert.throws(
    () => verifyCanonicalRuntimeManifest(
      canonicalRuntimeManifestBytes({ ...envelope, unexpected: true }),
      roots,
      expected,
    ),
    /runtime_manifest_envelope_fields_invalid/,
  );

  await chmod(path.join(root, "app/main.mjs"), 0o644);
  await writeFile(path.join(root, "app/main.mjs"), "tampered\n");
  await chmod(path.join(root, "app/main.mjs"), 0o444);
  await assert.rejects(
    () => verifyRuntimeManifestTree(root, envelope.body),
    /runtime_manifest_tree_file_(?:size|sha256)_mismatch/,
  );
  await chmod(path.join(root, "app/main.mjs"), 0o644);
  await writeFile(path.join(root, "app/main.mjs"), "import './lib/provider.mjs';\n");
  await chmod(path.join(root, "app/main.mjs"), 0o444);

  await addFile("app/undeclared.mjs", "export default false;\n", 0o444);
  await assert.rejects(
    () => verifyRuntimeManifestTree(root, envelope.body),
    /runtime_manifest_tree_exact_set_mismatch/,
  );
  await removePath("app/undeclared.mjs");

  await chmod(path.join(root, "app"), 0o755);
  await assert.rejects(
    () => verifyRuntimeManifestTree(root, envelope.body),
    /runtime_manifest_tree_writable_directory/,
  );
  await chmod(path.join(root, "app"), 0o555);

  await chmod(path.join(root, "app"), 0o755);
  await mkdir(path.join(root, "app/empty"), { mode: 0o555 });
  await chmod(path.join(root, "app"), 0o555);
  await assert.rejects(
    () => verifyRuntimeManifestTree(root, envelope.body),
    /runtime_manifest_tree_empty_directory/,
  );
  await chmod(path.join(root, "app"), 0o755);
  await rm(path.join(root, "app/empty"), { recursive: true });
  await chmod(path.join(root, "app"), 0o555);

  await addFile("app/writable.mjs", "export default false;\n", 0o644);
  await assert.rejects(
    () => verifyRuntimeManifestTree(root, envelope.body),
    /runtime_manifest_tree_writable_file/,
  );
  await removePath("app/writable.mjs");

  await chmod(path.join(root, "app"), 0o755);
  await symlink("main.mjs", path.join(root, "app/link.mjs"));
  await chmod(path.join(root, "app"), 0o555);
  await assert.rejects(
    () => verifyRuntimeManifestTree(root, envelope.body),
    /runtime_manifest_tree_symlink_rejected/,
  );
  await removePath("app/link.mjs");

  await chmod(path.join(root, "usr/bin"), 0o755);
  await link(path.join(root, "usr/bin/node"), path.join(root, "usr/bin/node-hardlink"));
  await chmod(path.join(root, "usr/bin"), 0o555);
  await assert.rejects(
    () => verifyRuntimeManifestTree(root, envelope.body),
    /runtime_manifest_tree_hard_link_rejected/,
  );
  await removePath("usr/bin/node-hardlink");

  const socketPath = path.join(root, "app/special.sock");
  await chmod(path.join(root, "app"), 0o755);
  const server = await listenUnixSocket(socketPath);
  await chmod(path.join(root, "app"), 0o555);
  try {
    await assert.rejects(
      () => verifyRuntimeManifestTree(root, envelope.body),
      /runtime_manifest_tree_special_file/,
    );
  } finally {
    await new Promise((resolve) => server.close(resolve));
    await removePath("app/special.sock", { force: true });
  }

  process.stdout.write(`${JSON.stringify({
    contract: "agentops_openclaw_complete_runtime_manifest_a07_v1",
    canonical_wire_encoding_verified: true,
    complete_file_metadata_bound: true,
    exact_tree_remeasurement_verified: true,
    descriptor_nofollow_best_effort_verified: true,
    duplicate_case_conflict_and_traversal_rejected: true,
    undeclared_extra_file_rejected: true,
    symlink_special_and_writable_file_policy_enforced: true,
    writable_and_empty_directory_policy_enforced: true,
    hard_link_rejected: true,
    malformed_deep_and_oversized_envelope_rejected: true,
    tree_mutation_rejected: true,
    ed25519_key_confusion_rejected: true,
    noncanonical_and_tampered_signature_rejected: true,
    oci_argv_environment_runtime_paths_policy_and_identity_bound: true,
    real_runtime_manifest_loaded: false,
    runtime_manifest_verified: false,
    hostile_runtime_isolation_verified: false,
  })}\n`);
} finally {
  for (const directory of [
    path.join(root, "app/lib"),
    path.join(root, "app"),
    path.join(root, "usr/bin"),
    path.join(root, "usr"),
    root,
  ]) await chmod(directory, 0o700).catch(() => {});
  await rm(root, { recursive: true, force: true });
}
