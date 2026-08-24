#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash, generateKeyPairSync } from "node:crypto";
import {
  chmodSync,
  mkdtempSync,
  mkdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  canonicalRuntimeManifestV2Bytes,
  serializeRuntimeManifestV2Envelope,
  signRuntimeManifestV2,
} from "./openclaw-runtime-manifest-v2.mjs";
import { readCommittedOpenClawRuntimeRelease } from "./openclaw-runtime-release.mjs";


const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const digest = (value) => value.repeat(64);
const base = mkdtempSync(path.join(tmpdir(), "agentops-runtime-release-contract-"));
const release = path.join(base, "release");
const owner = { uid: process.getuid(), gid: process.getgid() };
const trust = Buffer.from('{"fixture":"pinned-trust"}', "utf8");
const ociImage = { digest: `sha256:${digest("a")}`, name: "registry.invalid/agentops/openclaw" };
const rootfs = { byte_count: 1, file_count: 1, merkle_sha256: digest("c") };
const signing = generateKeyPairSync("ed25519");
const body = {
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
  environment_name_allowlist: ["LANG", "OPENCLAW_CONFIG_PATH", "OPENCLAW_STATE_DIR", "OPENCLAW_WORKSPACE", "PATH"],
  expires_at: "2026-08-19T00:00:00.000Z",
  immutable_code_roots: ["/opt/agentops/openclaw-adapter", "/opt/openclaw", "/usr/local"],
  issuer: "agentops-release",
  key_id: "manifest-key-1",
  mutable_mounts: [
    { kind: "hosts_file", path: "/etc/hosts", read_only: true, sha256: sha256("127.0.0.1 localhost\n::1 localhost\n172.31.250.3 openclaw-egress-gateway\n") },
    { kind: "resolver_config_file", path: "/etc/resolv.conf", read_only: true, sha256: sha256("nameserver 127.0.0.1\noptions timeout:1 attempts:1 ndots:0\n") },
    { kind: "workspace_directory", path: "/opt/agentops-worker/workspace", read_only: true },
    { kind: "state_directory", path: "/run/openclaw-state", read_only: false },
    { kind: "config_file", path: "/run/secrets/openclaw_config", read_only: true },
    { kind: "temp_directory", path: "/tmp", read_only: false },
  ],
  oci_image: ociImage,
  path_model: "guest_root_absolute_v1",
  platform: { arch: "amd64", libc: "glibc", os: "linux" },
  rootfs,
  runtime_executable: "/usr/local/bin/node",
  runtime_gid: 1200,
  runtime_uid: 1200,
  schema_semantics: {
    artifact_kind: "openclaw_runtime_guest_root",
    identity_model: "oci_digest_and_rootfs_merkle_v1",
    manifest_version: 2,
    signature_scope: "canonical_unsigned_envelope_v1",
  },
  seccomp_profile_sha256: digest("d"),
};
const manifest = serializeRuntimeManifestV2Envelope(
  signRuntimeManifestV2(body, body.key_id, signing.privateKey),
);
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
const provenance = canonicalRuntimeManifestV2Bytes({
  export_archive_sha256: digest("9"),
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
  guest_root: "/opt/agentops/releases/openclaw-root",
  guest_root_identity: {
    ctime_ns: "1",
    dev: "1",
    gid: 0,
    ino: "1",
    mode: "0555",
    mtime_ns: "1",
    uid: 0,
  },
  oci: { digest: ociImage.digest, exact_reference: `${ociImage.name}@${ociImage.digest}`, name: ociImage.name },
  platform: { architecture: "amd64", os: "linux" },
  rootfs: { ...rootfs, schema: "agentops_openclaw_runtime_rootfs_merkle_v1" },
  schema: "agentops_openclaw_runtime_oci_export_provenance_v2",
  source_image_id: `sha256:${digest("8")}`,
});

function receipt(overrides = {}) {
  return {
    claims: {
      guest_root_artifact_built: false,
      guest_root_immutability_verified: false,
      launcher_guest_root_handoff_verified: false,
      real_openclaw_execution_verified: false,
      runtime_path_toctou_closed: false,
    },
    cgroup_policy_sha256: digest("b"),
    created_at: "2026-08-12T00:00:00.000Z",
    expires_at: "2026-08-19T00:00:00.000Z",
    files: {
      manifest: { name: "openclaw-runtime-manifest.json", sha256: sha256(manifest) },
      provenance: {
        name: "openclaw-runtime-oci-export-provenance.json",
        sha256: sha256(provenance),
      },
    },
    issuer: "agentops-release",
    key_id: "manifest-key-1",
    oci_export_provenance: {
      schema: "agentops_openclaw_runtime_oci_export_provenance_v2",
      sha256: sha256(provenance),
    },
    oci_image: ociImage,
    platform: { arch: "amd64", libc: "glibc", os: "linux" },
    private_key_copied: false,
    rootfs,
    schema: "agentops_openclaw_runtime_manifest_v2_release_v2",
    seccomp_profile_sha256: digest("d"),
    trust_root_copied: false,
    trust_root_sha256: sha256(trust),
    ...overrides,
  };
}

function createRelease(value = receipt(), provenanceValue = provenance) {
  mkdirSync(release, { mode: 0o755 });
  writeFileSync(path.join(release, "openclaw-runtime-manifest.json"), manifest, { mode: 0o444 });
  writeFileSync(
    path.join(release, "openclaw-runtime-oci-export-provenance.json"),
    provenanceValue,
    { mode: 0o444 },
  );
  writeFileSync(
    path.join(release, "openclaw-runtime-manifest-metadata-receipt.json"),
    canonicalRuntimeManifestV2Bytes(value),
    { mode: 0o444 },
  );
  chmodSync(path.join(release, "openclaw-runtime-manifest.json"), 0o444);
  chmodSync(path.join(release, "openclaw-runtime-oci-export-provenance.json"), 0o444);
  chmodSync(path.join(release, "openclaw-runtime-manifest-metadata-receipt.json"), 0o444);
  chmodSync(release, 0o555);
}

try {
  createRelease();
  const verified = readCommittedOpenClawRuntimeRelease(release, trust, { expectedOwner: owner });
  assert.deepEqual(verified.manifestBytes, manifest);
  assert.deepEqual(verified.provenanceBytes, provenance);
  assert.equal(verified.receipt.trust_root_sha256, sha256(trust));

  chmodSync(release, 0o755);
  chmodSync(path.join(release, "openclaw-runtime-oci-export-provenance.json"), 0o644);
  writeFileSync(
    path.join(release, "openclaw-runtime-oci-export-provenance.json"),
    Buffer.from(provenance.toString("utf8").replace(digest("9"), digest("7"))),
  );
  chmodSync(path.join(release, "openclaw-runtime-oci-export-provenance.json"), 0o444);
  chmodSync(release, 0o555);
  assert.throws(
    () => readCommittedOpenClawRuntimeRelease(release, trust, { expectedOwner: owner }),
    /runtime_release_receipt_provenance_invalid/,
  );

  chmodSync(release, 0o755);
  rmSync(release, { recursive: true, force: true });
  const mismatchedProvenance = canonicalRuntimeManifestV2Bytes({
    ...JSON.parse(provenance.toString("utf8")),
    oci: {
      digest: `sha256:${digest("f")}`,
      exact_reference: `${ociImage.name}@sha256:${digest("f")}`,
      name: ociImage.name,
    },
  });
  mkdirSync(release, { mode: 0o755 });
  writeFileSync(path.join(release, "openclaw-runtime-manifest.json"), manifest, { mode: 0o444 });
  writeFileSync(path.join(release, "openclaw-runtime-oci-export-provenance.json"), mismatchedProvenance, { mode: 0o444 });
  writeFileSync(
    path.join(release, "openclaw-runtime-manifest-metadata-receipt.json"),
    canonicalRuntimeManifestV2Bytes(receipt({
      files: {
        manifest: { name: "openclaw-runtime-manifest.json", sha256: sha256(manifest) },
        provenance: {
          name: "openclaw-runtime-oci-export-provenance.json",
          sha256: sha256(mismatchedProvenance),
        },
      },
      oci_export_provenance: {
        schema: "agentops_openclaw_runtime_oci_export_provenance_v2",
        sha256: sha256(mismatchedProvenance),
      },
    })),
    { mode: 0o444 },
  );
  for (const name of [
    "openclaw-runtime-manifest.json",
    "openclaw-runtime-manifest-metadata-receipt.json",
    "openclaw-runtime-oci-export-provenance.json",
  ]) chmodSync(path.join(release, name), 0o444);
  chmodSync(release, 0o555);
  assert.throws(
    () => readCommittedOpenClawRuntimeRelease(release, trust, { expectedOwner: owner }),
    /runtime_release_receipt_manifest_binding_invalid/,
  );

  chmodSync(release, 0o755);
  rmSync(release, { recursive: true, force: true });
  createRelease(receipt({ oci_image: { ...ociImage, digest: `sha256:${digest("f")}` } }));
  assert.throws(
    () => readCommittedOpenClawRuntimeRelease(release, trust, { expectedOwner: owner }),
    /runtime_release_receipt_manifest_binding_invalid/,
  );
  chmodSync(release, 0o755);
  rmSync(release, { recursive: true, force: true });
  createRelease(receipt({ rootfs: { ...rootfs, merkle_sha256: digest("f") } }));
  assert.throws(
    () => readCommittedOpenClawRuntimeRelease(release, trust, { expectedOwner: owner }),
    /runtime_release_receipt_manifest_binding_invalid/,
  );

  chmodSync(release, 0o755);
  rmSync(release, { recursive: true, force: true });
  const loopbackName = "127.0.0.1:5000/agentops/openclaw";
  const loopbackProvenance = canonicalRuntimeManifestV2Bytes({
    ...JSON.parse(provenance.toString("utf8")),
    oci: {
      digest: ociImage.digest,
      exact_reference: `${loopbackName}@${ociImage.digest}`,
      name: loopbackName,
    },
  });
  createRelease(receipt({
    files: {
      manifest: { name: "openclaw-runtime-manifest.json", sha256: sha256(manifest) },
      provenance: {
        name: "openclaw-runtime-oci-export-provenance.json",
        sha256: sha256(loopbackProvenance),
      },
    },
    oci_export_provenance: {
      schema: "agentops_openclaw_runtime_oci_export_provenance_v2",
      sha256: sha256(loopbackProvenance),
    },
  }), loopbackProvenance);
  assert.throws(
    () => readCommittedOpenClawRuntimeRelease(release, trust, { expectedOwner: owner }),
    /runtime_release_insecure_registry_provenance_rejected/,
  );

  chmodSync(release, 0o755);
  rmSync(release, { recursive: true, force: true });
  createRelease();

  chmodSync(release, 0o755);
  assert.throws(
    () => readCommittedOpenClawRuntimeRelease(release, trust, { expectedOwner: owner }),
    /runtime_release_root_metadata_invalid/,
  );
  chmodSync(release, 0o555);
  assert.throws(
    () => readCommittedOpenClawRuntimeRelease(release, Buffer.from("attacker trust"), { expectedOwner: owner }),
    /runtime_release_receipt_invalid/,
  );
  chmodSync(release, 0o755);
  writeFileSync(path.join(release, "unexpected"), "x", { mode: 0o444 });
  chmodSync(release, 0o555);
  assert.throws(
    () => readCommittedOpenClawRuntimeRelease(release, trust, { expectedOwner: owner }),
    /runtime_release_file_set_invalid/,
  );

  process.stdout.write(`${JSON.stringify({
    contract: "agentops_openclaw_runtime_release_contract_v1",
    committed_directory_mode_verified: true,
    exact_file_set_verified: true,
    manifest_receipt_hash_verified: true,
    provenance_receipt_shape_verified: true,
    oci_and_rootfs_manifest_binding_verified: true,
    insecure_registry_provenance_rejected: true,
    independent_trust_root_hash_verified: true,
    self_signed_trust_replacement_rejected: true,
  })}\n`);
} finally {
  try { chmodSync(release, 0o755); } catch {}
  rmSync(base, { recursive: true, force: true });
}
