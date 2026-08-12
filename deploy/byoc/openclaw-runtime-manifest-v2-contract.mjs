#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash, generateKeyPairSync } from "node:crypto";

import {
  canonicalRuntimeManifestV2Bytes,
  parseCanonicalRuntimeManifestV2Envelope,
  serializeRuntimeManifestV2Envelope,
  signRuntimeManifestV2,
  validateRuntimeManifestV2Body,
  verifyCanonicalRuntimeManifestV2,
} from "./openclaw-runtime-manifest-v2.mjs";

const digest = (character) => character.repeat(64);
const signing = generateKeyPairSync("ed25519");
const other = generateKeyPairSync("ed25519");

function fixture(overrides = {}) {
  return {
    argv: [
      { kind: "guest_path", value: "/usr/local/bin/node" },
      { kind: "guest_path", value: "/opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs" },
      { kind: "opaque", value: "--stdin-protocol=canonical_provider_request_stdin_v1" },
    ],
    cgroup_policy_sha256: digest("b"),
    claims: {
      guest_root_artifact_built: false,
      guest_root_immutability_verified: false,
      launcher_guest_root_handoff_verified: false,
      real_openclaw_execution_verified: false,
      runtime_path_toctou_closed: false,
    },
    created_at: "2026-08-12T00:00:00.000Z",
    entrypoint: "/opt/agentops/openclaw-adapter/openclaw-stdin-provider.mjs",
    environment_name_allowlist: [
      "LANG",
      "OPENCLAW_CONFIG_PATH",
      "OPENCLAW_STATE_DIR",
      "OPENCLAW_WORKSPACE",
      "PATH",
    ],
    expires_at: "2026-08-19T00:00:00.000Z",
    immutable_code_roots: ["/opt/agentops/openclaw-adapter", "/opt/openclaw", "/usr/local"],
    issuer: "agentops-release",
    key_id: "runtime-manifest-key-2026-08",
    mutable_mounts: [
      { kind: "workspace_directory", path: "/opt/agentops-worker/workspace", read_only: true },
      { kind: "state_directory", path: "/run/openclaw-state", read_only: false },
      { kind: "config_file", path: "/run/secrets/openclaw_config", read_only: true },
    ],
    oci_image: {
      digest: `sha256:${digest("c")}`,
      name: "ghcr.io/agentops/openclaw-runtime",
    },
    path_model: "guest_root_absolute_v1",
    platform: { arch: "arm64", libc: "glibc", os: "linux" },
    rootfs: {
      byte_count: 440_000_000,
      file_count: 44_670,
      merkle_sha256: digest("d"),
    },
    runtime_executable: "/usr/local/bin/node",
    runtime_gid: 1200,
    runtime_uid: 1200,
    schema_semantics: {
      artifact_kind: "openclaw_runtime_guest_root",
      identity_model: "oci_digest_and_rootfs_merkle_v1",
      manifest_version: 2,
      signature_scope: "canonical_unsigned_envelope_v1",
    },
    seccomp_profile_sha256: digest("a"),
    ...overrides,
  };
}

function expected(body) {
  return {
    body_sha256: createHash("sha256").update(canonicalRuntimeManifestV2Bytes(body)).digest("hex"),
    cgroup_policy_sha256: body.cgroup_policy_sha256,
    entrypoint: body.entrypoint,
    issuer: body.issuer,
    key_id: body.key_id,
    oci_image: body.oci_image,
    platform: body.platform,
    rootfs_merkle_sha256: body.rootfs.merkle_sha256,
    runtime_executable: body.runtime_executable,
    runtime_gid: body.runtime_gid,
    runtime_uid: body.runtime_uid,
    seccomp_profile_sha256: body.seccomp_profile_sha256,
    verification_time: "2026-08-13T00:00:00.000Z",
  };
}

function signed(body = fixture()) {
  return signRuntimeManifestV2(body, body.key_id, signing.privateKey);
}

function rejectsBody(body, pattern) {
  assert.throws(() => validateRuntimeManifestV2Body(body), pattern);
  assert.throws(() => signRuntimeManifestV2(body, body.key_id, signing.privateKey), pattern);
}

assert.equal(
  canonicalRuntimeManifestV2Bytes({ z: 1, a: { y: false, b: "value" } }).toString("utf8"),
  '{"a":{"b":"value","y":false},"z":1}',
);

const envelope = signed();
const bytes = serializeRuntimeManifestV2Envelope(envelope);
const parsed = parseCanonicalRuntimeManifestV2Envelope(bytes);
assert.deepEqual(parsed, envelope);
const verified = verifyCanonicalRuntimeManifestV2(
  bytes,
  new Map([[envelope.key_id, signing.publicKey]]),
  expected(envelope.body),
);
assert.ok(Object.isFrozen(verified));
assert.ok(Object.isFrozen(verified.argv));
assert.equal(verified.path_model, "guest_root_absolute_v1");
assert.deepEqual(Object.values(verified.claims), [false, false, false, false, false]);

for (const [body, pattern] of [
  [{ ...fixture(), unexpected: true }, /runtime_manifest_v2_body_fields_invalid/],
  [fixture({ schema_semantics: { ...fixture().schema_semantics, manifest_version: 3 } }), /runtime_manifest_v2_schema_semantics_invalid/],
  [fixture({ platform: { arch: "x64", libc: "glibc", os: "linux" } }), /runtime_manifest_v2_platform_unsupported/],
  [fixture({ platform: { arch: "arm64", libc: "musl", os: "linux" } }), /runtime_manifest_v2_platform_unsupported/],
  [fixture({ platform: { arch: "arm64", libc: "glibc", os: "darwin" } }), /runtime_manifest_v2_platform_unsupported/],
  [fixture({ path_model: "host_absolute_v1" }), /runtime_manifest_v2_path_model_invalid/],
  [fixture({ immutable_code_roots: ["/usr/local", "/opt/openclaw"] }), /runtime_manifest_v2_immutable_code_roots_order_invalid/],
  [fixture({ immutable_code_roots: ["/opt", "/opt/agentops/openclaw-adapter", "/usr/local"] }), /runtime_manifest_v2_immutable_code_roots_overlap_invalid/],
  [fixture({ immutable_code_roots: ["/opt", "/opt-escape", "/opt/openclaw", "/usr/local"] }), /runtime_manifest_v2_immutable_code_roots_overlap_invalid/],
  [fixture({ immutable_code_roots: ["/opt/../openclaw", "/usr/local"] }), /runtime_manifest_v2_immutable_code_root_invalid/],
  [fixture({ entrypoint: "/opt/agentops/openclaw-adapter/../escape.mjs" }), /runtime_manifest_v2_entrypoint_invalid/],
  [fixture({ entrypoint: "/opt/agentops/\ud800/escape.mjs" }), /runtime_manifest_v2_entrypoint_invalid/],
  [fixture({ environment_name_allowlist: ["LANG", "LANG", "OPENCLAW_STATE_DIR", "OPENCLAW_WORKSPACE", "PATH"] }), /runtime_manifest_v2_environment_name_allowlist_invalid/],
  [fixture({ mutable_mounts: [fixture().mutable_mounts[0], fixture().mutable_mounts[0], fixture().mutable_mounts[2]] }), /runtime_manifest_v2_mutable_mount_kind_duplicate|runtime_manifest_v2_mutable_mounts_order_invalid/],
  [fixture({ mutable_mounts: fixture().mutable_mounts.map((mount) => mount.kind === "config_file" ? { ...mount, read_only: false } : mount) }), /runtime_manifest_v2_mutable_mount_read_only_invalid/],
  [fixture({ argv: [{ kind: "guest_path", value: "/usr/local/bin/node" }, { kind: "guest_path", value: "/opt/agentops/openclaw-adapter/other.mjs" }] }), /runtime_manifest_v2_argv_runtime_binding_invalid/],
  [fixture({ argv: [...fixture().argv, { kind: "opaque", value: "../escape" }] }), /runtime_manifest_v2_argv_opaque_invalid/],
  [fixture({ argv: [...fixture().argv, { kind: "guest_path", value: "/run/openclaw-state/input" }] }), /runtime_manifest_v2_argv_guest_path_scope_invalid/],
  [fixture({ claims: { ...fixture().claims, runtime_path_toctou_closed: true } }), /runtime_manifest_v2_claim_scope_invalid/],
  [fixture({ claims: { ...fixture().claims, provider_call_verified: false } }), /runtime_manifest_v2_claims_fields_invalid/],
]) rejectsBody(body, pattern);

rejectsBody(fixture({
  mutable_mounts: [
    { kind: "config_file", path: "/run", read_only: true },
    { kind: "workspace_directory", path: "/run-escape", read_only: true },
    { kind: "state_directory", path: "/run/state", read_only: false },
  ],
}), /runtime_manifest_v2_mutable_mounts_overlap_invalid/);

const duplicateRoot = fixture({ immutable_code_roots: ["/opt/agentops/openclaw-adapter", "/opt/openclaw", "/opt/openclaw", "/usr/local"] });
rejectsBody(duplicateRoot, /runtime_manifest_v2_immutable_code_roots_order_invalid/);

assert.throws(
  () => verifyCanonicalRuntimeManifestV2(
    canonicalRuntimeManifestV2Bytes({ ...envelope, body: { ...envelope.body, runtime_uid: 1201 } }),
    new Map([[envelope.key_id, signing.publicKey]]),
    expected(envelope.body),
  ),
  /runtime_manifest_v2_runtime_uid_invalid/,
);

const tamperedSignature = `${envelope.signature[0] === "A" ? "B" : "A"}${envelope.signature.slice(1)}`;
assert.throws(
  () => verifyCanonicalRuntimeManifestV2(
    canonicalRuntimeManifestV2Bytes({ ...envelope, signature: tamperedSignature }),
    new Map([[envelope.key_id, signing.publicKey]]),
    expected(envelope.body),
  ),
  /runtime_manifest_v2_signature_unverified/,
);
assert.throws(
  () => verifyCanonicalRuntimeManifestV2(
    bytes,
    new Map([[envelope.key_id, other.publicKey]]),
    expected(envelope.body),
  ),
  /runtime_manifest_v2_signature_unverified/,
);
assert.throws(
  () => verifyCanonicalRuntimeManifestV2(
    Buffer.from(` ${bytes.toString("utf8")}`),
    new Map([[envelope.key_id, signing.publicKey]]),
    expected(envelope.body),
  ),
  /runtime_manifest_v2_encoding_noncanonical/,
);
assert.throws(
  () => verifyCanonicalRuntimeManifestV2(
    Buffer.from(bytes.toString("utf8").replace(
      '"algorithm":"Ed25519"',
      '"algorithm":"Ed25519","algorithm":"Ed25519"',
    )),
    new Map([[envelope.key_id, signing.publicKey]]),
    expected(envelope.body),
  ),
  /runtime_manifest_v2_encoding_noncanonical/,
);
assert.throws(
  () => verifyCanonicalRuntimeManifestV2(
    bytes,
    new Map([[envelope.key_id, signing.publicKey]]),
    { ...expected(envelope.body), platform: { arch: "amd64", libc: "glibc", os: "linux" } },
  ),
  /runtime_manifest_v2_platform_mismatch/,
);
const alternateBody = fixture({
  argv: [...fixture().argv, { kind: "opaque", value: "--alternate-mode=enabled" }],
});
const alternateEnvelope = signed(alternateBody);
assert.throws(
  () => verifyCanonicalRuntimeManifestV2(
    serializeRuntimeManifestV2Envelope(alternateEnvelope),
    new Map([[alternateEnvelope.key_id, signing.publicKey]]),
    expected(envelope.body),
  ),
  /runtime_manifest_v2_body_sha256_mismatch/,
);
assert.throws(
  () => verifyCanonicalRuntimeManifestV2(
    bytes,
    new Map([[envelope.key_id, signing.publicKey]]),
    { ...expected(envelope.body), verification_time: "2026-09-01T00:00:00.000Z" },
  ),
  /runtime_manifest_v2_verification_time_invalid/,
);
assert.throws(
  () => verifyCanonicalRuntimeManifestV2(
    bytes,
    new Map([[envelope.key_id, signing.publicKey]]),
    { ...expected(envelope.body), verification_time: envelope.body.expires_at },
  ),
  /runtime_manifest_v2_verification_time_invalid/,
);

const claims = Object.freeze({
  guest_root_artifact_built: false,
  guest_root_immutability_verified: false,
  launcher_guest_root_handoff_verified: false,
  real_openclaw_execution_verified: false,
  runtime_path_toctou_closed: false,
});
assert.ok(Object.values(claims).every((value) => value === false));

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_runtime_manifest_v2_contract_v1",
  canonical_json_verified: true,
  ed25519_envelope_verified: true,
  exact_fields_and_ordering_verified: true,
  platform_and_path_traversal_fail_closed: true,
  typed_argv_binding_verified: true,
  claims,
})}\n`);
