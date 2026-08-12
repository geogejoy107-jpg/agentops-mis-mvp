#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  chmodSync,
  mkdtempSync,
  mkdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { canonicalRuntimeManifestV2Bytes } from "./openclaw-runtime-manifest-v2.mjs";
import { readCommittedOpenClawRuntimeRelease } from "./openclaw-runtime-release.mjs";

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const digest = (value) => value.repeat(64);
const base = mkdtempSync(path.join(tmpdir(), "agentops-runtime-release-contract-"));
const release = path.join(base, "release");
const owner = { uid: process.getuid(), gid: process.getgid() };
const manifest = Buffer.from('{"fixture":"signed-manifest"}', "utf8");
const trust = Buffer.from('{"fixture":"pinned-trust"}', "utf8");

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
    },
    issuer: "agentops-release",
    key_id: "manifest-key-1",
    oci_image: { digest: `sha256:${digest("a")}`, name: "registry.invalid/agentops/openclaw" },
    platform: { arch: "amd64", libc: "glibc", os: "linux" },
    private_key_copied: false,
    rootfs: { byte_count: 1, file_count: 1, merkle_sha256: digest("c") },
    schema: "agentops_openclaw_runtime_manifest_v2_release_v1",
    seccomp_profile_sha256: digest("d"),
    trust_root_copied: false,
    trust_root_sha256: sha256(trust),
    ...overrides,
  };
}

function createRelease(value = receipt()) {
  mkdirSync(release, { mode: 0o755 });
  writeFileSync(path.join(release, "openclaw-runtime-manifest.json"), manifest, { mode: 0o444 });
  writeFileSync(
    path.join(release, "openclaw-runtime-manifest-metadata-receipt.json"),
    canonicalRuntimeManifestV2Bytes(value),
    { mode: 0o444 },
  );
  chmodSync(path.join(release, "openclaw-runtime-manifest.json"), 0o444);
  chmodSync(path.join(release, "openclaw-runtime-manifest-metadata-receipt.json"), 0o444);
  chmodSync(release, 0o555);
}

try {
  createRelease();
  const verified = readCommittedOpenClawRuntimeRelease(release, trust, { expectedOwner: owner });
  assert.deepEqual(verified.manifestBytes, manifest);
  assert.equal(verified.receipt.trust_root_sha256, sha256(trust));

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
    independent_trust_root_hash_verified: true,
    self_signed_trust_replacement_rejected: true,
  })}\n`);
} finally {
  try { chmodSync(release, 0o755); } catch {}
  rmSync(base, { recursive: true, force: true });
}
