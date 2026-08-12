#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  closeSync,
  constants,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const sourcePath = fileURLToPath(new URL("./openclaw-runtime-path-resolver.c", import.meta.url));
const sourceText = readFileSync(sourcePath, "utf8");
const insideLinux = process.argv.includes("--inside-linux");
const sourceAuditOnly = process.argv.includes("--source-audit-only");
const requireRealLinux = process.env.AGENTOPS_REQUIRE_REAL_LINUX === "1" || process.env.CI === "true";

function sourceAudit() {
  assert.match(sourceText, /#ifndef __linux__/);
  assert.match(sourceText, /geteuid\(\) != \(uid_t\)0/);
  assert.match(sourceText, /strcmp\(argv\[1\], "--root-fd"\)/);
  assert.match(sourceText, /strcmp\(argv\[3\], "--guest-path"\)/);
  assert.match(sourceText, /fstat\(root_fd, &metadata\)/);
  assert.match(sourceText, /metadata\.st_uid != \(uid_t\)0/);
  assert.match(sourceText, /S_IWGRP \| S_IWOTH/);
  assert.match(sourceText, /SYS_openat2/);
  assert.match(sourceText, /RESOLVE_IN_ROOT/);
  assert.match(sourceText, /RESOLVE_BENEATH/);
  assert.match(sourceText, /RESOLVE_NO_SYMLINKS/);
  assert.match(sourceText, /RESOLVE_NO_MAGICLINKS/);
  assert.match(sourceText, /RESOLVE_NO_XDEV/);
  assert.match(sourceText, /guest_path \+ 1/);
  assert.match(sourceText, /in_root_metadata\.st_dev != beneath_metadata\.st_dev/);
  assert.match(sourceText, /in_root_metadata\.st_ino != beneath_metadata\.st_ino/);
  assert.match(sourceText, /O_RDONLY \| O_CLOEXEC \| O_NOFOLLOW \| O_NONBLOCK/);
  assert.doesNotMatch(sourceText, /\bopen\s*\(|\bopenat\s*\(|\brealpath\s*\(|\breadlink\s*\(/);
  assert.doesNotMatch(sourceText, /\bsystem\s*\(|\bpopen\s*\(|\bfork\s*\(|\bexec[lvpe]+\s*\(/);

  const mainBody = sourceText.slice(sourceText.indexOf("int main("));
  const operations = [
    "geteuid() != (uid_t)0",
    "validate_root_fd(root_fd)",
    "validate_guest_path(guest_path)",
    "guarded_openat2(root_fd, guest_path, IN_ROOT_RESOLVE_FLAGS)",
    "guarded_openat2(root_fd, guest_path + 1, BENEATH_RESOLVE_FLAGS)",
    "fstat(in_root_fd, &in_root_metadata)",
  ];
  let previous = -1;
  for (const operation of operations) {
    const position = mainBody.indexOf(operation);
    assert.ok(position > previous, `resolver_operation_order_invalid:${operation}`);
    previous = position;
  }
}

function writeSourceAudit(extra = {}) {
  process.stdout.write(`${JSON.stringify({
    contract: "agentops_openclaw_runtime_path_resolver_foundation_a07_v1",
    ok: true,
    native_openat2_source_audited: true,
    inherited_root_directory_fd_required: true,
    root_owned_non_writable_root_required: true,
    guest_absolute_path_canonicality_audited: true,
    in_root_and_beneath_identity_agreement_audited: true,
    no_symlinks_audited: true,
    no_magiclinks_audited: true,
    no_mount_crossing_audited: true,
    shell_and_path_fallback_omitted: true,
    linux_native_hardened_compile_verified: false,
    linux_openat2_positive_verified: false,
    traversal_rejection_verified: false,
    symlink_rejection_verified: false,
    proc_magiclink_rejection_verified: false,
    mount_crossing_rejection_verified: false,
    resolved_fd_handoff_verified: false,
    runtime_path_toctou_closed: false,
    real_runtime_process_spawned: false,
    runtime_receipt_verified: false,
    hostile_runtime_isolation_verified: false,
    ...extra,
  })}\n`);
}

sourceAudit();

if (sourceAuditOnly) {
  writeSourceAudit();
  process.exit(0);
}

if (process.platform !== "linux" || (typeof process.geteuid === "function" && process.geteuid() !== 0)) {
  if (insideLinux || requireRealLinux) {
    process.stderr.write("runtime_path_resolver_linux_root_contract_required\n");
    process.exit(78);
  }
  writeSourceAudit({ linux_runtime_available: false });
  process.exit(0);
}

const root = mkdtempSync(join(tmpdir(), "agentops-runtime-path-resolver-contract-"));
const runtimeRoot = join(root, "runtime-root");
const binary = join(root, "openclaw-runtime-path-resolver");
const compileFlags = [
  "-std=c11",
  "-O2",
  "-Wall",
  "-Wextra",
  "-Werror",
  "-Wpedantic",
  "-Wformat=2",
  "-Wconversion",
  "-Wshadow",
  "-fstack-protector-strong",
  "-D_FORTIFY_SOURCE=3",
  "-fPIE",
  "-pie",
  "-Wl,-z,relro,-z,now",
  "-Wl,-z,noexecstack",
];

function runResolver(rootPath, guestPath) {
  const rootFd = openSync(rootPath, constants.O_RDONLY | constants.O_DIRECTORY);
  try {
    const result = spawnSync(binary, ["--root-fd", "3", "--guest-path", guestPath], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe", rootFd],
      timeout: 10_000,
      killSignal: "SIGKILL",
    });
    assert.equal(result.error?.code, undefined, result.error?.message ?? "");
    const line = result.stdout.trim();
    assert.ok(line.length > 0, result.stderr);
    return { ...result, payload: JSON.parse(line) };
  } finally {
    closeSync(rootFd);
  }
}

function assertRejected(result, expectedCode = undefined) {
  assert.notEqual(result.status, 0, result.stdout);
  assert.equal(result.payload.schema, "agentops_openclaw_runtime_path_resolver_result_v1");
  assert.equal(result.payload.ok, false);
  assert.equal(result.payload.linux_openat2_verified, false);
  assert.equal(result.payload.scope, "resolver_primitive_only");
  assert.equal(result.payload.resolved_fd_handoff_verified, false);
  assert.equal(result.payload.runtime_path_toctou_closed, false);
  if (expectedCode !== undefined) assert.equal(result.payload.code, expectedCode);
}

try {
  const compile = spawnSync("cc", [...compileFlags, sourcePath, "-o", binary], {
    encoding: "utf8",
    timeout: 30_000,
    killSignal: "SIGKILL",
  });
  assert.equal(compile.error?.code, undefined, compile.error?.message ?? "");
  assert.equal(compile.status, 0, `${compile.stdout}${compile.stderr}`);
  assert.equal(lstatSync(binary).uid, 0);
  assert.equal(lstatSync(binary).mode & 0o022, 0);

  mkdirSync(join(runtimeRoot, "bin"), { recursive: true, mode: 0o755 });
  writeFileSync(join(runtimeRoot, "bin", "openclaw"), "signed-runtime-fixture\n", { mode: 0o555 });
  chmodSync(runtimeRoot, 0o755);
  chmodSync(join(runtimeRoot, "bin"), 0o755);
  symlinkSync("bin", join(runtimeRoot, "linked-bin"));
  symlinkSync("openclaw", join(runtimeRoot, "bin", "linked-openclaw"));

  const positive = runResolver(runtimeRoot, "/bin/openclaw");
  const expected = lstatSync(join(runtimeRoot, "bin", "openclaw"), { bigint: true });
  assert.equal(positive.status, 0, `${positive.stdout}${positive.stderr}`);
  assert.equal(positive.payload.schema, "agentops_openclaw_runtime_path_resolver_result_v1");
  assert.equal(positive.payload.scope, "resolver_primitive_only");
  assert.equal(positive.payload.ok, true);
  assert.equal(positive.payload.linux_openat2_verified, true);
  assert.equal(positive.payload.root_anchored, true);
  assert.equal(positive.payload.no_symlinks, true);
  assert.equal(positive.payload.no_magiclinks, true);
  assert.equal(positive.payload.no_mount_crossing, true);
  assert.equal(positive.payload.regular_file, true);
  assert.equal(positive.payload.device, expected.dev.toString(10));
  assert.equal(positive.payload.inode, expected.ino.toString(10));
  assert.equal(positive.payload.mode, expected.mode.toString(10));
  assert.equal(positive.payload.size, expected.size.toString(10));
  assert.equal(positive.payload.resolved_fd_handoff_verified, false);
  assert.equal(positive.payload.runtime_path_toctou_closed, false);

  for (const traversal of [
    "/bin/../bin/openclaw",
    "/../../etc/passwd",
    "/bin//openclaw",
    "/bin/./openclaw",
  ]) assertRejected(runResolver(runtimeRoot, traversal), "guest_path_rejected");

  assertRejected(runResolver(runtimeRoot, "/linked-bin/openclaw"), "path_resolution_rejected");
  assertRejected(runResolver(runtimeRoot, "/bin/linked-openclaw"), "path_resolution_rejected");

  const magiclink = runResolver("/proc", "/self/fd/0");
  assertRejected(magiclink, "path_resolution_rejected");

  const mountCrossing = runResolver("/", "/proc/version");
  assertRejected(mountCrossing, "path_resolution_rejected");

  process.stdout.write(`${JSON.stringify({
    contract: "agentops_openclaw_runtime_path_resolver_foundation_a07_v1",
    ok: true,
    native_openat2_source_audited: true,
    inherited_root_directory_fd_required: true,
    root_owned_non_writable_root_required: true,
    guest_absolute_path_canonicality_audited: true,
    in_root_and_beneath_identity_agreement_audited: true,
    no_symlinks_audited: true,
    no_magiclinks_audited: true,
    no_mount_crossing_audited: true,
    shell_and_path_fallback_omitted: true,
    linux_native_hardened_compile_verified: true,
    linux_openat2_positive_verified: true,
    traversal_rejection_verified: true,
    symlink_rejection_verified: true,
    proc_magiclink_rejection_verified: true,
    mount_crossing_rejection_verified: true,
    resolved_fd_handoff_verified: false,
    runtime_path_toctou_closed: false,
    real_runtime_process_spawned: false,
    runtime_receipt_verified: false,
    hostile_runtime_isolation_verified: false,
  })}\n`);
} finally {
  rmSync(root, { recursive: true, force: true });
}
