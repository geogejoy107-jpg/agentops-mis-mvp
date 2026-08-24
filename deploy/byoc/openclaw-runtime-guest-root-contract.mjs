#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  closeSync,
  constants,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const launcherSourcePath = fileURLToPath(new URL("./openclaw-runtime-launcher.c", import.meta.url));
const manifestSourcePath = fileURLToPath(new URL("./openclaw-runtime-manifest-v2.mjs", import.meta.url));
const runnerSourcePath = fileURLToPath(new URL("./openclaw-executor-runner.mjs", import.meta.url));
const launcherSource = readFileSync(launcherSourcePath, "utf8");
const manifestSource = readFileSync(manifestSourcePath, "utf8");
const runnerSource = readFileSync(runnerSourcePath, "utf8");
const requireIntegrated = process.argv.includes("--require-integrated");

const claimNames = Object.freeze([
  "guest_root_artifact_built",
  "guest_root_immutability_verified",
  "launcher_guest_root_handoff_verified",
  "real_openclaw_execution_verified",
  "runtime_path_toctou_closed",
]);

const requirements = Object.freeze([
  ["guest_root_argc", /argc < 15/],
  ["root_fd_argument", /strcmp\(argv\[7\], "--root-fd"\)/],
  ["cgroup_fd_argument", /strcmp\(argv\[9\], "--cgroup-procs-fd"\)/],
  ["status_fd_argument", /strcmp\(argv\[11\], "--status-fd"\)/],
  ["guest_argv_separator", /strcmp\(argv\[13\], "--"\)/],
  ["guest_argv_start", /child_argv\s*=\s*&argv\[14\]/],
  ["root_fd_parse", /parse_decimal\(argv\[8\], &\w*root\w*\)/],
  ["root_fd_assignment", /\*\w*root\w*\s*=\s*\(int\)\w*root\w*/],
  ["root_fd_validation", /validate_(?:guest_)?root_fd\(root_fd\)/],
  ["openat2_syscall", /SYS_openat2/],
  ["openat2_beneath", /RESOLVE_BENEATH/],
  ["exec_identity_device", /st_dev/],
  ["exec_identity_inode", /st_ino/],
  ["guest_root_fchdir", /fchdir\(root_fd\)/],
  ["guest_root_chroot", /chroot\("\."\)/],
  ["guest_root_chdir", /chdir\("\/"\)/],
  ["guest_root_close", /close\(root_fd\)/],
  ["runtime_gid_1200", /setresgid\(RUNTIME_GID, RUNTIME_GID, RUNTIME_GID\)/],
  ["runtime_uid_1200", /setresuid\(RUNTIME_UID, RUNTIME_UID, RUNTIME_UID\)/],
  ["capability_sets_clear", /SYS_capset/],
  ["ambient_capabilities_clear", /PR_CAP_AMBIENT_CLEAR_ALL/],
  ["fd_execution", /SYS_execveat/],
]);

for (const claim of claimNames) {
  assert.match(manifestSource, new RegExp(`"${claim}"`));
}
assert.match(manifestSource, /claims\[name\] !== false/);
assert.match(manifestSource, /body\.runtime_uid !== 1200/);
assert.match(manifestSource, /body\.runtime_gid !== 1200/);

const missingRequirements = requirements
  .filter(([, pattern]) => !pattern.test(launcherSource))
  .map(([name]) => name);
for (const [name, pattern] of [
  ["runner_retained_root_fd", /rootFd: preflight\.runtimeHandles\.rootFd/],
  ["runner_retained_exec_fd", /execFd: preflight\.runtimeHandles\.execFd/],
  ["runner_root_fd_argument", /"--root-fd", "4"/],
  ["runner_guest_argv_preserved", /const argv = assertPromptTransport\(preflight\.manifest\);/],
  ["runner_root_fd_stdio", /handles\.execFd, handles\.rootFd, handles\.cgroupFd, "pipe"/],
  ["runner_request_fd_cleanup", /handles\?\.requestOwnedFds \|\| \[\]/],
]) {
  if (!pattern.test(runnerSource)) missingRequirements.push(name);
}

function result(extra = {}) {
  return {
    contract: "agentops_openclaw_runtime_guest_root_handoff_a07_v1",
    ok: true,
    interface: "--uid 1200 --gid 1200 --exec-fd FD --root-fd FD --cgroup-procs-fd FD --status-fd FD -- GUEST_ARGV0 [ARGS...]",
    path_model: "guest_root_absolute_v1",
    source_integration_detected: missingRequirements.length === 0,
    missing_requirements: missingRequirements,
    openat2_no_magiclinks_source_audited: /RESOLVE_NO_MAGICLINKS/.test(launcherSource),
    openat2_no_symlinks_source_audited: /RESOLVE_NO_SYMLINKS/.test(launcherSource),
    openat2_no_xdev_source_audited: /RESOLVE_NO_XDEV/.test(launcherSource),
    inherited_guest_root_fd_verified: false,
    invalid_guest_root_fd_rejected: false,
    executable_fd_within_guest_root_verified: false,
    executable_path_toctou_closed_verified: false,
    escaping_guest_argv0_rejected: false,
    guest_argv_preserved_verified: false,
    fchdir_chroot_chdir_verified: false,
    runtime_uid_gid_1200_verified: false,
    runtime_capability_vectors_cleared_verified: false,
    capability_bounding_set_cleared_verified: false,
    launcher_guest_root_handoff_verified: false,
    runtime_path_toctou_closed: false,
    hostile_runtime_isolation_verified: false,
    claims: Object.fromEntries(claimNames.map((name) => [name, false])),
    ...extra,
  };
}

if (!requireIntegrated) {
  process.stdout.write(`${JSON.stringify(result())}\n`);
  process.exit(0);
}

if (missingRequirements.length > 0) {
  process.stdout.write(`${JSON.stringify(result({ ok: false }))}\n`);
  process.stderr.write(`runtime_launcher_guest_root_integration_missing:${missingRequirements.join(",")}\n`);
  process.exit(1);
}

if (process.platform !== "linux" || (typeof process.geteuid === "function" && process.geteuid() !== 0)) {
  process.stderr.write("runtime_launcher_guest_root_linux_root_required\n");
  process.exit(78);
}

const cgroupProcsPath = process.env.AGENTOPS_TEST_CGROUP_PROCS_PATH || "";
if (!cgroupProcsPath.startsWith("/") || cgroupProcsPath.includes("\0")) {
  process.stderr.write("runtime_launcher_guest_root_real_cgroup_required\n");
  process.exit(78);
}

const scratch = mkdtempSync(join(tmpdir(), "agentops-guest-root-contract-"));
const launcherBinary = join(scratch, "openclaw-runtime-launcher");
const probeSource = join(scratch, "guest-root-probe.c");
const outsideProbe = join(scratch, "outside-probe");
const guestRoot = join(scratch, "guest-root");
const guestExecutablePath = join(guestRoot, "usr", "local", "bin", "runtime-probe");
const guestArgv0 = "/usr/local/bin/runtime-probe";

const compileFlags = [
  "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wpedantic",
  "-Wformat=2", "-Wconversion", "-Wshadow", "-fstack-protector-strong",
  "-D_FORTIFY_SOURCE=3", "-fPIE", "-pie", "-Wl,-z,relro,-z,now",
  "-Wl,-z,noexecstack",
];

const probeText = String.raw`
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/capability.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

int main(int argc, char **argv) {
    struct __user_cap_header_struct header = {0};
    struct __user_cap_data_struct data[2] = {{0}};
    char cwd[PATH_MAX];
    char marker[32] = {0};
    int fd;
    int capability;
    ssize_t count;
    if (argc != 2 || strcmp(argv[0], "/usr/local/bin/runtime-probe") != 0
        || strcmp(argv[1], "guest-root") != 0) return 10;
    if (getuid() != 1200 || geteuid() != 1200 || getgid() != 1200 || getegid() != 1200) return 11;
    if (getgroups(0, NULL) != 0) return 12;
    if (getcwd(cwd, sizeof(cwd)) == NULL || strcmp(cwd, "/") != 0) return 13;
    fd = open("/guest-root-marker", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return 14;
    count = read(fd, marker, sizeof(marker) - 1U);
    if (close(fd) != 0 || count != 19 || strcmp(marker, "agentops-guest-root") != 0) return 15;
    errno = 0;
    if (open("/host-only-canary", O_RDONLY | O_CLOEXEC) != -1 || errno != ENOENT) return 16;
    header.version = _LINUX_CAPABILITY_VERSION_3;
    if (syscall(SYS_capget, &header, data) != 0) return 17;
    if (data[0].effective || data[0].permitted || data[0].inheritable
        || data[1].effective || data[1].permitted || data[1].inheritable) return 18;
    for (capability = 0; capability < 64; capability += 1) {
        errno = 0;
        if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_IS_SET, capability, 0L, 0L) > 0) return 19;
        if (errno != 0 && errno != EINVAL) return 20;
    }
    puts("runtime_guest_root_probe_ok");
    return 0;
}
`;

function compile(source, output, extra = []) {
  const compiled = spawnSync("cc", [...compileFlags, ...extra, source, "-o", output], {
    encoding: "utf8",
    env: { PATH: process.env.PATH },
  });
  return compiled;
}

function launcherArgs(execFd, rootFd, cgroupFd, statusFd, argv0 = guestArgv0) {
  return [
    "--uid", "1200",
    "--gid", "1200",
    "--exec-fd", String(execFd),
    "--root-fd", String(rootFd),
    "--cgroup-procs-fd", String(cgroupFd),
    "--status-fd", String(statusFd),
    "--", argv0, "guest-root",
  ];
}

function runLauncher(
  execPath,
  cgroupPath,
  argv0 = guestArgv0,
  rootPath = guestRoot,
  rootOpenFlags = constants.O_RDONLY | constants.O_DIRECTORY | constants.O_CLOEXEC,
) {
  const execFd = openSync(execPath, constants.O_RDONLY | constants.O_CLOEXEC);
  const rootFd = openSync(rootPath, rootOpenFlags);
  const cgroupFd = openSync(cgroupPath, constants.O_WRONLY | constants.O_CLOEXEC);
  try {
    const launched = spawnSync(launcherBinary, launcherArgs(3, 4, 5, 6, argv0), {
      encoding: "utf8",
      env: {},
      stdio: ["ignore", "pipe", "pipe", execFd, rootFd, cgroupFd, "pipe"],
    });
    launched.launcherStatus = launched.output[6];
    return launched;
  } finally {
    closeSync(execFd);
    closeSync(rootFd);
    closeSync(cgroupFd);
  }
}

try {
  chmodSync(scratch, 0o755);
  mkdirSync(join(guestRoot, "usr", "local", "bin"), { recursive: true, mode: 0o755 });
  writeFileSync(join(guestRoot, "guest-root-marker"), "agentops-guest-root", { mode: 0o444 });
  writeFileSync(probeSource, probeText, { mode: 0o600 });

  const launcherCompile = compile(launcherSourcePath, launcherBinary);
  assert.equal(launcherCompile.status, 0, launcherCompile.stderr);
  const staticCompile = compile(probeSource, guestExecutablePath, ["-static"]);
  if (staticCompile.status !== 0) {
    process.stderr.write(`runtime_launcher_guest_root_static_toolchain_required\n${staticCompile.stderr}`);
    process.exit(78);
  }
  chmodSync(guestExecutablePath, 0o555);
  writeFileSync(outsideProbe, readFileSync(guestExecutablePath), { mode: 0o555 });

  const outsideMismatch = runLauncher(outsideProbe, cgroupProcsPath);
  assert.notEqual(outsideMismatch.status, 0, `${outsideMismatch.stdout}${outsideMismatch.stderr}`);
  assert.equal(outsideMismatch.stdout, "");
  assert.equal(outsideMismatch.launcherStatus, "");

  const escape = runLauncher(guestExecutablePath, cgroupProcsPath, "/../usr/local/bin/runtime-probe");
  assert.notEqual(escape.status, 0, `${escape.stdout}${escape.stderr}`);
  assert.equal(escape.stdout, "");
  assert.equal(escape.launcherStatus, "");

  const invalidRoot = runLauncher(
    guestExecutablePath,
    cgroupProcsPath,
    guestArgv0,
    join(guestRoot, "guest-root-marker"),
    constants.O_RDONLY | constants.O_CLOEXEC,
  );
  assert.notEqual(invalidRoot.status, 0, `${invalidRoot.stdout}${invalidRoot.stderr}`);
  assert.equal(invalidRoot.stdout, "");
  assert.equal(invalidRoot.launcherStatus, "");

  const positive = runLauncher(guestExecutablePath, cgroupProcsPath);
  assert.equal(positive.status, 0, `${positive.stdout}${positive.stderr}`);
  assert.equal(positive.stdout, "runtime_guest_root_probe_ok\n");
  assert.equal(positive.stderr, "");
  assert.equal(positive.launcherStatus, "R");

  process.stdout.write(`${JSON.stringify(result({
    source_integration_detected: true,
    missing_requirements: [],
    inherited_guest_root_fd_verified: true,
    invalid_guest_root_fd_rejected: true,
    executable_fd_within_guest_root_verified: true,
    executable_path_toctou_closed_verified: true,
    escaping_guest_argv0_rejected: true,
    guest_argv_preserved_verified: true,
    fchdir_chroot_chdir_verified: true,
    runtime_uid_gid_1200_verified: true,
    runtime_capability_vectors_cleared_verified: true,
    capability_bounding_set_cleared_verified: false,
    launcher_guest_root_handoff_verified: true,
    runtime_path_toctou_closed: false,
    hostile_runtime_isolation_verified: false,
  }))}\n`);
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
