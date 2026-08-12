#!/usr/bin/env node

import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
  chmodSync,
  closeSync,
  constants,
  existsSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import {
  inspectOpenClawRuntimeTarArchive,
  parseCanonicalOpenClawRuntimeOciExportProvenance,
  readCommittedOpenClawRuntimeOciExportReceipt,
} from "./openclaw-runtime-oci-export.mjs";

const sourcePath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "openclaw-runtime-oci-export.mjs");
const source = readFileSync(sourcePath, "utf8");
const DOCKER = "/usr/bin/docker";
const TAR = "/usr/bin/tar";
const MV = "/usr/bin/mv";
const SAFE_ENV = { HOME: "/root", LANG: "C.UTF-8", LC_ALL: "C.UTF-8", PATH: "/usr/bin:/bin" };

function octal(value, bytes) {
  return Buffer.from(`${value.toString(8).padStart(bytes - 1, "0")}\0`, "ascii");
}

function tarHeader(name, type = "0", link = "", size = 0, prefix = "", metadata = {}) {
  const header = Buffer.alloc(512);
  header.write(name, 0, 100, "utf8");
  octal(metadata.mode ?? 0o444, 8).copy(header, 100);
  octal(metadata.uid ?? 0, 8).copy(header, 108);
  octal(metadata.gid ?? 0, 8).copy(header, 116);
  octal(size, 12).copy(header, 124);
  octal(0, 12).copy(header, 136);
  header.fill(0x20, 148, 156);
  header.write(type, 156, 1, "ascii");
  header.write(link, 157, 100, "utf8");
  header.write("ustar\0", 257, 6, "latin1");
  header.write("00", 263, 2, "ascii");
  header.write(prefix, 345, 155, "utf8");
  let checksum = 0;
  for (const value of header) checksum += value;
  Buffer.from(`${checksum.toString(8).padStart(6, "0")}\0 `, "ascii").subarray(0, 8).copy(header, 148);
  return header;
}

function archive(entries) {
  const blocks = [];
  for (const entry of entries) {
    const body = entry.body ?? Buffer.alloc(0);
    blocks.push(tarHeader(
      entry.name, entry.type, entry.link, body.length, entry.prefix, entry.metadata,
    ), body);
    if (body.length % 512) blocks.push(Buffer.alloc(512 - (body.length % 512)));
  }
  blocks.push(Buffer.alloc(1024));
  return Buffer.concat(blocks);
}

function inspectFixture(base, name, bytes) {
  const target = path.join(base, `${name}.tar`);
  writeFileSync(target, bytes, { mode: 0o600 });
  return () => inspectOpenClawRuntimeTarArchive(target);
}

for (const required of [
  'const DOCKER_PATH = "/usr/bin/docker"',
  'const TAR_PATH = "/usr/bin/tar"',
  'const MV_PATH = "/usr/bin/mv"',
  'const execPath = `/proc/${process.pid}/fd/${descriptor}`',
  'procOpened = statSync(tool.exec_path, { bigint: true })',
  'spawnSync(tool.exec_path, args',
  'spawn(docker.exec_path, ["export", containerId]',
  'spawn(tar.exec_path, [',
  'runPinned(mv, "mv", ["--no-clobber", "--no-target-directory", stagingRoot, destination])',
  'process.platform !== "linux"',
  'process.geteuid() !== 0',
  '["manifest", "inspect", "--verbose", reference.exact]',
  'value?.Ref !== reference.exact',
  'value?.Descriptor?.digest !== reference.digest',
  'value?.Descriptor?.platform?.os !== "linux"',
  'value?.Descriptor?.platform?.architecture !== "amd64"',
  '["pull", "--platform", "linux/amd64", reference.exact]',
  'value.RepoDigests.includes(reference.exact)',
  '"create", "--platform", "linux/amd64", "--network", "none", reference.exact',
  'computeOpenClawRuntimeRootfsMerkle',
  'const stagingRoot = path.join(working, "guest-root")',
  'syncTree(stagingRoot)',
  'linkSync(staging, destination)',
  'fchownSync(descriptor, 0, 0)',
  'fchmodSync(descriptor, 0o444)',
  'fsyncSync(descriptor)',
  'syncDirectory(path.dirname(destination))',
  'provenance_output: destinations.provenance.path',
  'provenance_sha256: receipt.sha256',
  'guest_root_identity: guestRootIdentity',
  'provenance_bytes: Buffer.from(bytes)',
  'parseCanonicalOpenClawRuntimeOciExportProvenance(bytes)',
  'const guestDescriptor = openSync(',
  'const descriptorAfter = fstatSync(guestDescriptor, { bigint: true })',
  'const publishedGuestDescriptor = openSync(',
  'receipt = publishProvenanceReceipt(',
  'const guestDescriptorAfter = fstatSync(publishedGuestDescriptor, { bigint: true })',
]) assert.ok(source.includes(required), `missing static boundary: ${required}`);

assert.equal(/shell\s*:\s*true/.test(source), false);
assert.equal(/exec(?:File)?Sync\s*\(/.test(source), false);
assert.equal(/\/bin\/(?:ba)?sh/.test(source), false);
assert.equal(/spawnSync\(tool\.identity\.path/.test(source), false);
assert.equal(/spawn\((?:docker|tar)\.identity\.path/.test(source), false);
assert.ok(
  source.indexOf("publishGuestRoot(mv, stagingRoot, destinations.guest.path)")
    < source.indexOf("receipt = publishProvenanceReceipt("),
  "provenance must be the commit marker after guest publication",
);
assert.ok(
  source.indexOf("syncTree(stagingRoot)")
    < source.indexOf("publishGuestRoot(mv, stagingRoot, destinations.guest.path)"),
  "tree must be durable before guest publication",
);

const pathValidationBase = mkdtempSync(path.join(tmpdir(), "agentops-oci-export-path-contract-"));
try {
  const digest = "a".repeat(64);
  const existing = path.join(pathValidationBase, "existing-receipt.json");
  writeFileSync(existing, "occupied\n", { mode: 0o600 });
  for (const [name, args, code] of [
    ["noncanonical-guest", [
      "--oci", `registry.invalid/agentops/openclaw@sha256:${digest}`,
      "--output", `${pathValidationBase}/nested/../guest`,
      "--provenance-output", path.join(pathValidationBase, "receipt.json"),
    ], "runtime_oci_export_output_path_invalid"],
    ["noncanonical-provenance", [
      "--oci", `registry.invalid/agentops/openclaw@sha256:${digest}`,
      "--output", path.join(pathValidationBase, "guest"),
      "--provenance-output", `${pathValidationBase}/nested/../receipt.json`,
    ], "runtime_oci_export_provenance_output_path_invalid"],
    ["provenance-overwrite", [
      "--oci", `registry.invalid/agentops/openclaw@sha256:${digest}`,
      "--output", path.join(pathValidationBase, "guest"),
      "--provenance-output", existing,
    ], "runtime_oci_export_provenance_output_exists"],
  ]) {
    const rejected = spawnSync(process.execPath, [sourcePath, ...args], {
      encoding: "utf8", env: { PATH: "/usr/bin:/bin" },
    });
    assert.equal(rejected.status, 1, name);
    assert.equal(rejected.stderr.trim(), code, name);
  }
} finally {
  rmSync(pathValidationBase, { recursive: true, force: true });
}

const base = mkdtempSync(path.join(tmpdir(), "agentops-oci-export-contract-"));
try {
  const valid = inspectFixture(base, "valid", archive([
    { name: "bin", type: "5" },
    { name: "bin/runtime", body: Buffer.from("runtime\n") },
    { name: "usr", type: "5" },
    { name: "usr/bin", type: "5" },
    { name: "usr/bin/runtime", type: "2", link: "../../bin/runtime" },
  ]))();
  assert.match(valid.archive_sha256, /^[a-f0-9]{64}$/);
  assert.equal(valid.entry_count, 5);
  const prefixed = inspectFixture(base, "ustar-prefix", archive([{
    name: "runtime",
    prefix: `usr/share/${"long-segment/".repeat(8)}agentops`.replace(/\/$/, ""),
    body: Buffer.from("prefix-path\n"),
  }]))();
  assert.equal(prefixed.entry_count, 1);

  for (const [name, bytes, pattern] of [
    ["traversal", archive([{ name: "../escape", body: Buffer.from("x") }]), /runtime_oci_export_tar_path_rejected/],
    ["absolute", archive([{ name: "/escape", body: Buffer.from("x") }]), /runtime_oci_export_tar_path_rejected/],
    ["hardlink", archive([{ name: "hard", type: "1", link: "target" }]), /runtime_oci_export_tar_hardlink_rejected/],
    ["device", archive([{ name: "device", type: "3" }]), /runtime_oci_export_tar_special_or_extension_rejected/],
    ["pax", archive([{ name: "pax", type: "x" }]), /runtime_oci_export_tar_special_or_extension_rejected/],
    ["pax-global", archive([{ name: "pax-global", type: "g" }]), /runtime_oci_export_tar_special_or_extension_rejected/],
    ["gnu-longname", archive([{ name: "gnu-longname", type: "L" }]), /runtime_oci_export_tar_special_or_extension_rejected/],
    ["gnu-longlink", archive([{ name: "gnu-longlink", type: "K" }]), /runtime_oci_export_tar_special_or_extension_rejected/],
    ["suid", archive([{ name: "suid", body: Buffer.from("x"), metadata: { mode: 0o4555 } }]), /runtime_oci_export_tar_owner_or_mode_rejected/],
    ["sgid", archive([{ name: "sgid", body: Buffer.from("x"), metadata: { mode: 0o2555 } }]), /runtime_oci_export_tar_owner_or_mode_rejected/],
    ["uid-range", archive([{ name: "uid", body: Buffer.from("x"), metadata: { uid: 65_536 } }]), /runtime_oci_export_tar_owner_or_mode_rejected/],
    ["gid-range", archive([{ name: "gid", body: Buffer.from("x"), metadata: { gid: 65_536 } }]), /runtime_oci_export_tar_owner_or_mode_rejected/],
    ["symlink-up", archive([{ name: "escape", type: "2", link: "../../host" }]), /runtime_oci_export_tar_symlink_rejected/],
    ["symlink-ancestor", archive([
      { name: "outside", type: "2", link: "/tmp" },
      { name: "outside/file", body: Buffer.from("x") },
    ]), /runtime_oci_export_tar_symlink_ancestor_rejected/],
    ["late-symlink-ancestor", archive([
      { name: "outside/file", body: Buffer.from("x") },
      { name: "outside", type: "2", link: "/tmp" },
    ]), /runtime_oci_export_tar_symlink_ancestor_rejected/],
  ]) assert.throws(inspectFixture(base, name, bytes), pattern);
} finally {
  rmSync(base, { recursive: true, force: true });
}

const syntax = spawnSync(process.execPath, ["--check", sourcePath], { encoding: "utf8" });
assert.equal(syntax.status, 0, syntax.stderr);

const fakeDigest = "a".repeat(64);
const nonReleaseHost = spawnSync(process.execPath, [
  sourcePath,
  "--oci", `registry.invalid/agentops/openclaw@sha256:${fakeDigest}`,
  "--output", path.join("/tmp", `agentops-oci-export-contract-output-${process.pid}`),
  "--provenance-output", path.join("/tmp", `agentops-oci-export-contract-provenance-${process.pid}.json`),
], { encoding: "utf8", env: { PATH: "/usr/bin:/bin" } });

let hostGateVerified = false;
if (process.platform !== "linux") {
  assert.equal(nonReleaseHost.status, 1);
  assert.equal(nonReleaseHost.stderr.trim(), "runtime_oci_export_linux_required");
  hostGateVerified = true;
} else if (typeof process.geteuid === "function" && process.geteuid() !== 0) {
  assert.equal(nonReleaseHost.status, 1);
  assert.equal(nonReleaseHost.stderr.trim(), "runtime_oci_export_root_required");
  hostGateVerified = true;
}

function command(executable, args, options = {}) {
  return spawnSync(executable, args, {
    cwd: options.cwd,
    encoding: "utf8",
    env: SAFE_ENV,
    maxBuffer: 4 * 1024 * 1024,
    stdio: options.stdio,
    timeout: options.timeout ?? 300_000,
  });
}

function commandAsync(executable, args) {
  return new Promise((resolve) => {
    const child = spawn(executable, args, {
      env: SAFE_ENV,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.once("close", (status, signal) => resolve({ signal, status, stderr, stdout }));
  });
}

function canonicalJson(value) {
  if (value === null || typeof value === "string" || typeof value === "boolean" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  return `{${Object.keys(value).sort().map((key) => (
    `${JSON.stringify(key)}:${canonicalJson(value[key])}`
  )).join(",")}}`;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function syntheticToolIdentity(toolPath, marker) {
  return {
    ctime_ns: "1",
    dev: "1",
    gid: 0,
    ino: marker,
    mode: "0755",
    path: toolPath,
    sha256: marker.padStart(64, "0"),
    size: 1,
    uid: 0,
  };
}

function syntheticProvenance() {
  const digest = "a".repeat(64);
  return {
    export_archive_sha256: "b".repeat(64),
    export_policy: {
      archive_format: "strict_ustar_only_gnu_longname_and_pax_extensions_rejected_fail_closed",
      extraction: "two_identical_stopped_container_exports_strict_ustar_then_gnu_tar_stream",
      root_directory: "normalized_root_0_0_0555",
    },
    export_tool_identity: {
      docker: syntheticToolIdentity(DOCKER, "1"),
      mv: syntheticToolIdentity(MV, "2"),
      tar: syntheticToolIdentity(TAR, "3"),
    },
    guest_root: "/opt/agentops-export/guest-root",
    guest_root_identity: {
      ctime_ns: "10",
      dev: "11",
      gid: 0,
      ino: "12",
      mode: "0555",
      mtime_ns: "13",
      uid: 0,
    },
    oci: {
      digest: `sha256:${digest}`,
      exact_reference: `registry.invalid/agentops/openclaw@sha256:${digest}`,
      name: "registry.invalid/agentops/openclaw",
    },
    platform: { architecture: "amd64", os: "linux" },
    rootfs: {
      byte_count: 1,
      file_count: 1,
      merkle_sha256: "c".repeat(64),
      schema: "agentops_openclaw_runtime_rootfs_merkle_v1",
    },
    schema: "agentops_openclaw_runtime_oci_export_provenance_v2",
    source_image_id: `sha256:${"d".repeat(64)}`,
  };
}

const synthetic = syntheticProvenance();
const syntheticBytes = Buffer.from(canonicalJson(synthetic), "utf8");
assert.deepEqual(parseCanonicalOpenClawRuntimeOciExportProvenance(syntheticBytes), synthetic);
const structurallyValidDifferentIdentity = structuredClone(synthetic);
structurallyValidDifferentIdentity.guest_root_identity.ino = "99";
assert.deepEqual(
  parseCanonicalOpenClawRuntimeOciExportProvenance(
    Buffer.from(canonicalJson(structurallyValidDifferentIdentity), "utf8"),
  ),
  structurallyValidDifferentIdentity,
);
assert.throws(
  () => parseCanonicalOpenClawRuntimeOciExportProvenance(Buffer.from(
    `${JSON.stringify(synthetic, null, 2)}\n`, "utf8",
  )),
  /runtime_oci_export_provenance_noncanonical/,
);
for (const mutate of [
  (value) => { value.schema = "agentops_openclaw_runtime_oci_export_provenance_v1"; },
  (value) => { delete value.rootfs.byte_count; },
  (value) => { value.extra = true; },
  (value) => { value.oci.extra = true; },
  (value) => { value.platform.extra = true; },
  (value) => { value.rootfs.extra = true; },
  (value) => { value.export_policy.extra = true; },
  (value) => { value.export_tool_identity.extra = true; },
  (value) => { value.export_tool_identity.docker.extra = true; },
  (value) => { value.export_tool_identity.docker.mode = "0777"; },
  (value) => { value.guest_root_identity.extra = true; },
  (value) => { value.guest_root_identity.ino = 12; },
]) {
  const invalid = structuredClone(synthetic);
  mutate(invalid);
  assert.throws(
    () => parseCanonicalOpenClawRuntimeOciExportProvenance(
      Buffer.from(canonicalJson(invalid), "utf8"),
    ),
    /runtime_oci_export_provenance_/,
  );
}

function verifyProcFdExecution() {
  if (process.platform !== "linux" || !existsSync(TAR)) return false;
  const descriptor = openSync(TAR, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_CLOEXEC);
  try {
    const procPath = `/proc/${process.pid}/fd/${descriptor}`;
    const original = statSync(TAR, { bigint: true });
    const pinned = statSync(procPath, { bigint: true });
    assert.equal(pinned.dev, original.dev);
    assert.equal(pinned.ino, original.ino);
    const result = command(procPath, ["--version"], { timeout: 10_000 });
    assert.equal(result.status, 0);
    return true;
  } finally {
    closeSync(descriptor);
  }
}

function mustCommand(executable, args, options = {}) {
  const result = command(executable, args, options);
  assert.equal(result.status, 0, `contract command failed: ${path.basename(executable)} ${args[0]}`);
  return result;
}

async function freePort() {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const port = server.address().port;
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  return port;
}

async function waitForRegistry(port) {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/v2/`, { signal: AbortSignal.timeout(500) });
      if (response.status === 200) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.fail("local registry did not become ready");
}

function createImageContext(context) {
  const root = path.join(context, "rootfs");
  for (const directory of [
    "bin",
    "opt/agentops-worker/workspace",
    "run/openclaw-state",
    "run/secrets",
    "tmp",
  ]) mkdirSync(path.join(root, directory), { recursive: true, mode: 0o755 });
  chmodSync(path.join(root, "tmp"), 0o1777);
  writeFileSync(path.join(root, "bin/runtime"), "runtime-contract-v1\n", { mode: 0o555 });
  chmodSync(path.join(root, "bin/runtime"), 0o555);
  const ustarPrefix = path.join(root, "usr/share", ...Array.from({ length: 6 }, () => "agentops-long-segment"));
  mkdirSync(ustarPrefix, { recursive: true, mode: 0o555 });
  writeFileSync(path.join(ustarPrefix, "runtime-metadata.json"), "{}\n", { mode: 0o444 });
  chmodSync(path.join(ustarPrefix, "runtime-metadata.json"), 0o444);
  writeFileSync(path.join(root, "run/secrets/openclaw_config"), "", { mode: 0o400 });
  chmodSync(path.join(root, "run/secrets/openclaw_config"), 0o400);
  writeFileSync(path.join(context, "Dockerfile"), [
    "FROM scratch",
    "COPY rootfs /",
    "COPY --chown=1234:2345 --chmod=0555 rootfs/bin/runtime /bin/runtime",
    'CMD [\"/bin/runtime\"]',
    "",
  ].join("\n"), { mode: 0o444 });
}

function createExtensionRequiredContext(context) {
  const root = path.join(context, "rootfs");
  const longPath = path.join(root, ...Array.from({ length: 24 }, () => "segment1234"));
  mkdirSync(longPath, { recursive: true, mode: 0o555 });
  writeFileSync(path.join(longPath, "beyond-ustar.txt"), "extension-required\n", { mode: 0o444 });
  chmodSync(path.join(longPath, "beyond-ustar.txt"), 0o444);
  writeFileSync(path.join(context, "Dockerfile"), "FROM scratch\nCOPY rootfs /\n", { mode: 0o444 });
}

function pushedDigest(reference) {
  const inspected = mustCommand(DOCKER, [
    "image", "inspect", "--format", "{{json .RepoDigests}}", reference,
  ]);
  const values = JSON.parse(inspected.stdout);
  const expectedPrefix = `${reference.split(":").slice(0, -1).join(":")}@sha256:`;
  const exact = values.find((value) => value.startsWith(expectedPrefix));
  assert.match(exact, /@sha256:[a-f0-9]{64}$/);
  return exact;
}

async function realOciContract() {
  const dockerInfo = command(DOCKER, ["info", "--format", "{{.ServerVersion}}"], { timeout: 10_000 });
  const tarVersion = command(TAR, ["--version"], { timeout: 10_000 });
  const available = process.platform === "linux"
    && typeof process.geteuid === "function"
    && process.geteuid() === 0
    && existsSync(DOCKER)
    && existsSync(TAR)
    && dockerInfo.status === 0
    && tarVersion.status === 0
    && tarVersion.stdout.startsWith("tar (GNU tar) ");
  if (!available) return null;

  const working = mkdtempSync("/root/agentops-oci-export-real-contract-");
  chmodSync(working, 0o700);
  const registryName = `agentops-oci-export-registry-${process.pid}`;
  const port = await freePort();
  const registry = `127.0.0.1:${port}`;
  try {
    mustCommand(DOCKER, [
      "run", "--detach", "--rm", "--name", registryName,
      "--publish", `127.0.0.1:${port}:5000`, "registry:2",
    ], { stdio: ["ignore", "ignore", "ignore"] });
    await waitForRegistry(port);
    const context = path.join(working, "image");
    mkdirSync(context, { mode: 0o700 });
    createImageContext(context);
    const amdTag = `${registry}/agentops/openclaw-export:amd64`;
    const armTag = `${registry}/agentops/openclaw-export:arm64`;
    for (const [platform, tag] of [["linux/amd64", amdTag], ["linux/arm64", armTag]]) {
      mustCommand(DOCKER, ["build", "--platform", platform, "--tag", tag, "."], {
        cwd: context, stdio: ["ignore", "ignore", "ignore"],
      });
      mustCommand(DOCKER, ["push", tag], { stdio: ["ignore", "ignore", "ignore"] });
    }
    const amdExact = pushedDigest(amdTag);
    const armExact = pushedDigest(armTag);
    const firstOutput = path.join(working, "guest-one");
    const secondOutput = path.join(working, "guest-two");
    const firstProvenance = path.join(working, "guest-one-provenance.json");
    const secondProvenance = path.join(working, "guest-two-provenance.json");
    const first = command(process.execPath, [
      sourcePath, "--oci", amdExact, "--output", firstOutput,
      "--provenance-output", firstProvenance,
    ]);
    const second = command(process.execPath, [
      sourcePath, "--oci", amdExact, "--output", secondOutput,
      "--provenance-output", secondProvenance,
    ]);
    assert.equal(first.status, 0, first.stderr.trim());
    assert.equal(second.status, 0, second.stderr.trim());
    const firstSummary = JSON.parse(first.stdout);
    const secondSummary = JSON.parse(second.stdout);
    const firstBytes = readFileSync(firstProvenance);
    const secondBytes = readFileSync(secondProvenance);
    const firstReceipt = JSON.parse(firstBytes);
    const secondReceipt = JSON.parse(secondBytes);
    assert.equal(firstBytes.toString("utf8"), canonicalJson(firstReceipt));
    assert.equal(secondBytes.toString("utf8"), canonicalJson(secondReceipt));
    assert.equal(firstSummary.provenance_output, firstProvenance);
    assert.equal(firstSummary.provenance_sha256, sha256(firstBytes));
    assert.equal(secondSummary.provenance_sha256, sha256(secondBytes));
    assert.equal(Object.hasOwn(firstSummary, "provenance"), false);
    assert.equal(firstReceipt.guest_root, firstOutput);
    assert.equal(firstReceipt.schema, "agentops_openclaw_runtime_oci_export_provenance_v2");
    assert.equal(firstReceipt.oci.exact_reference, amdExact);
    assert.equal(firstReceipt.oci.name, amdExact.split("@")[0]);
    assert.equal(firstReceipt.oci.digest, amdExact.split("@")[1]);
    assert.equal(firstReceipt.source_image_id.startsWith("sha256:"), true);
    assert.equal(firstReceipt.platform.os, "linux");
    assert.equal(firstReceipt.platform.architecture, "amd64");
    assert.match(firstReceipt.export_archive_sha256, /^[a-f0-9]{64}$/);
    assert.match(firstReceipt.export_tool_identity.docker.sha256, /^[a-f0-9]{64}$/);
    assert.match(firstReceipt.export_tool_identity.mv.sha256, /^[a-f0-9]{64}$/);
    assert.match(firstReceipt.export_tool_identity.tar.sha256, /^[a-f0-9]{64}$/);
    assert.equal(firstReceipt.rootfs.merkle_sha256, secondReceipt.rootfs.merkle_sha256);
    assert.equal(firstReceipt.rootfs.file_count, secondReceipt.rootfs.file_count);
    assert.equal(firstReceipt.rootfs.byte_count, secondReceipt.rootfs.byte_count);
    const ownedRuntime = statSync(path.join(firstOutput, "bin/runtime"), { bigint: true });
    assert.equal(ownedRuntime.uid, 1234n);
    assert.equal(ownedRuntime.gid, 2345n);
    for (const receiptPath of [firstProvenance, secondProvenance]) {
      const metadata = statSync(receiptPath, { bigint: true });
      assert.equal(metadata.isFile(), true);
      assert.equal(metadata.uid, 0n);
      assert.equal(metadata.gid, 0n);
      assert.equal(metadata.mode & 0o7777n, 0o444n);
      assert.equal(metadata.nlink, 1n);
    }
    const committed = readCommittedOpenClawRuntimeOciExportReceipt(firstProvenance);
    assert.equal(committed.committed, true);
    assert.equal(committed.guest_root, firstOutput);
    assert.equal(committed.provenance_sha256, firstSummary.provenance_sha256);
    assert.deepEqual(committed.provenance_bytes, firstBytes);
    assert.deepEqual(
      parseCanonicalOpenClawRuntimeOciExportProvenance(committed.provenance_bytes),
      firstReceipt,
    );
    const identityMismatchPath = path.join(working, "identity-mismatch.json");
    const identityMismatch = structuredClone(firstReceipt);
    identityMismatch.guest_root_identity.ino = (
      BigInt(identityMismatch.guest_root_identity.ino) + 1n
    ).toString();
    writeFileSync(identityMismatchPath, canonicalJson(identityMismatch), { mode: 0o444 });
    chmodSync(identityMismatchPath, 0o444);
    assert.throws(
      () => readCommittedOpenClawRuntimeOciExportReceipt(identityMismatchPath),
      /runtime_oci_export_commit_guest_root_identity_mismatch/,
    );
    assert.throws(
      () => readCommittedOpenClawRuntimeOciExportReceipt(path.join(working, "missing.json")),
      /runtime_oci_export_commit_receipt_missing/,
    );
    const uncommittedRoot = path.join(working, "uncommitted-root");
    mkdirSync(uncommittedRoot, { mode: 0o555 });
    assert.throws(
      () => readCommittedOpenClawRuntimeOciExportReceipt(
        path.join(working, "uncommitted-root-provenance.json"),
      ),
      /runtime_oci_export_commit_receipt_missing/,
    );

    const extensionContext = path.join(working, "extension-image");
    mkdirSync(extensionContext, { mode: 0o700 });
    createExtensionRequiredContext(extensionContext);
    const extensionTag = `${registry}/agentops/openclaw-export:extension-required`;
    mustCommand(DOCKER, ["build", "--platform", "linux/amd64", "--tag", extensionTag, "."], {
      cwd: extensionContext, stdio: ["ignore", "ignore", "ignore"],
    });
    mustCommand(DOCKER, ["push", extensionTag], { stdio: ["ignore", "ignore", "ignore"] });
    const extensionExact = pushedDigest(extensionTag);
    const extensionRejected = command(process.execPath, [
      sourcePath, "--oci", extensionExact, "--output", path.join(working, "extension-output"),
      "--provenance-output", path.join(working, "extension-provenance.json"),
    ]);
    assert.equal(extensionRejected.status, 1);
    assert.match(extensionRejected.stderr, /runtime_oci_export_tar_(?:special_or_extension|path)_rejected/);

    const wrongDigest = `${amdExact.split("@")[0]}@sha256:${"b".repeat(64)}`;
    const wrongName = `${registry}/agentops/not-the-image@${amdExact.split("@")[1]}`;
    for (const [name, oci, output, provenanceOutput, pattern] of [
      ["wrong-digest", wrongDigest, path.join(working, "wrong-digest"), path.join(working, "wrong-digest.json"), /runtime_oci_export_docker_command_failed/],
      ["wrong-name", wrongName, path.join(working, "wrong-name"), path.join(working, "wrong-name.json"), /runtime_oci_export_docker_command_failed/],
      ["wrong-platform", armExact, path.join(working, "wrong-platform"), path.join(working, "wrong-platform.json"), /runtime_oci_export_(?:docker_command_failed|manifest_list_or_platform_rejected)/],
      ["noncanonical-output", amdExact, `${working}/nested/../escape`, path.join(working, "bad-output.json"), /runtime_oci_export_output_path_invalid/],
      ["noncanonical-provenance", amdExact, path.join(working, "bad-provenance-guest"), `${working}/nested/../receipt.json`, /runtime_oci_export_provenance_output_path_invalid/],
    ]) {
      const rejected = command(process.execPath, [
        sourcePath, "--oci", oci, "--output", output,
        "--provenance-output", provenanceOutput,
      ]);
      assert.equal(rejected.status, 1, name);
      assert.match(rejected.stderr, pattern, name);
      assert.equal(existsSync(output), false, name);
      assert.equal(existsSync(provenanceOutput), false, name);
    }

    const overwriteGuest = path.join(working, "overwrite-guest");
    const overwriteRejected = command(process.execPath, [
      sourcePath, "--oci", amdExact, "--output", overwriteGuest,
      "--provenance-output", firstProvenance,
    ]);
    assert.equal(overwriteRejected.status, 1);
    assert.equal(overwriteRejected.stderr.trim(), "runtime_oci_export_provenance_output_exists");
    assert.equal(existsSync(overwriteGuest), false);

    const otherParent = path.join(working, "other-parent");
    mkdirSync(otherParent, { mode: 0o700 });
    const parentRejected = command(process.execPath, [
      sourcePath, "--oci", amdExact, "--output", path.join(working, "parent-guest"),
      "--provenance-output", path.join(otherParent, "receipt.json"),
    ]);
    assert.equal(parentRejected.status, 1);
    assert.equal(parentRejected.stderr.trim(), "runtime_oci_export_provenance_output_parent_mismatch");

    const racedGuest = path.join(working, "raced-guest");
    const racedReceiptOne = path.join(working, "raced-one.json");
    const racedReceiptTwo = path.join(working, "raced-two.json");
    const raceArguments = (receipt) => [
      sourcePath, "--oci", amdExact, "--output", racedGuest,
      "--provenance-output", receipt,
    ];
    const [raceOne, raceTwo] = await Promise.all([
      commandAsync(process.execPath, raceArguments(racedReceiptOne)),
      commandAsync(process.execPath, raceArguments(racedReceiptTwo)),
    ]);
    assert.deepEqual([raceOne.status, raceTwo.status].sort(), [0, 1]);
    const winningReceipt = existsSync(racedReceiptOne) ? racedReceiptOne : racedReceiptTwo;
    const losingReceipt = winningReceipt === racedReceiptOne ? racedReceiptTwo : racedReceiptOne;
    assert.equal(existsSync(losingReceipt), false);
    assert.equal(readCommittedOpenClawRuntimeOciExportReceipt(winningReceipt).committed, true);

    const listTag = `${registry}/agentops/openclaw-export:list`;
    mustCommand(DOCKER, ["manifest", "create", "--insecure", listTag, amdExact, armExact]);
    const listPush = mustCommand(DOCKER, ["manifest", "push", "--insecure", listTag]);
    const listDigest = listPush.stdout.match(/sha256:[a-f0-9]{64}/)?.[0];
    assert.match(listDigest, /^sha256:[a-f0-9]{64}$/);
    const listRejected = command(process.execPath, [
      sourcePath, "--oci", `${listTag.split(":").slice(0, -1).join(":")}@${listDigest}`,
      "--output", path.join(working, "manifest-list"),
      "--provenance-output", path.join(working, "manifest-list.json"),
    ]);
    assert.equal(listRejected.status, 1);
    assert.match(listRejected.stderr, /runtime_oci_export_manifest_list_or_platform_rejected/);
    return Object.freeze({
      digest_root_merkle_binding_verified: true,
      actual_docker_ustar_prefix_accepted_and_extension_required_path_rejected: true,
      manifest_list_rejected: true,
      provenance_canonical_metadata_no_clobber_and_path_policy_verified: true,
      provenance_commit_marker_consumer_verified: true,
      provenance_v2_guest_root_identity_mismatch_rejected: true,
      wrong_digest_name_platform_and_path_rejected: true,
    });
  } finally {
    command(DOCKER, ["container", "rm", "--force", registryName], { stdio: ["ignore", "ignore", "ignore"] });
    rmSync(working, { recursive: true, force: true });
  }
}

const real = await realOciContract();
const procFdExecutionPerformed = verifyProcFdExecution();

process.stdout.write(`${JSON.stringify({
  contract: "agentops_openclaw_runtime_oci_export_contract_v2",
  exact_child_manifest_and_platform_static_boundary_verified: true,
  fixed_absolute_tool_paths_and_metadata_pin_verified: true,
  proc_fd_execution_static_boundary_verified: true,
  proc_fd_execution_performed: procFdExecutionPerformed,
  linux_root_gate_verified: hostGateVerified,
  no_shell_execution_verified: true,
  no_overwrite_private_staging_publish_static_boundary_verified: true,
  provenance_commit_marker_publish_order_static_boundary_verified: true,
  provenance_canonical_json_fsync_root_metadata_static_boundary_verified: true,
  provenance_noncanonical_and_overwrite_paths_executed: true,
  provenance_metadata_and_no_clobber_performed: real !== null,
  provenance_v2_pure_canonical_parser_verified: true,
  provenance_v2_nested_extra_fields_rejected: true,
  provenance_v2_guest_identity_fd_merkle_static_boundary_verified: true,
  provenance_v2_pure_parser_has_no_filesystem_identity_dependency: true,
  strict_ustar_path_hardlink_special_symlink_policy_verified: true,
  ustar_prefix_long_path_accepted_gnu_pax_extensions_fail_closed: true,
  two_export_header_and_full_stream_binding_static_boundary_verified: true,
  real_oci_export_performed: real !== null,
  real_oci_export_reason: real === null
    ? "requires_linux_root_gnu_tar_and_docker_daemon_with_digest_registry"
    : null,
  real_oci_verification: real,
})}\n`);
