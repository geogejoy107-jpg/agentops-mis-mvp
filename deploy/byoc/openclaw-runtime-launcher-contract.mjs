#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  closeSync,
  mkdtempSync,
  openSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const contractPath = fileURLToPath(import.meta.url);
const sourcePath = fileURLToPath(new URL("./openclaw-runtime-launcher.c", import.meta.url));
const sourceText = readFileSync(sourcePath, "utf8");
const insideLinux = process.argv.includes("--inside-linux");
const sourceAuditOnly = process.argv.includes("--source-audit-only");
const requireRealLinux = process.env.AGENTOPS_REQUIRE_REAL_LINUX === "1" || process.env.CI === "true";

function sourceAudit() {
  assert.match(sourceText, /#ifndef __linux__/);
  assert.match(sourceText, /geteuid\(\) != 0/);
  assert.match(sourceText, /argc < 11/);
  assert.match(sourceText, /strcmp\(argv\[1\], "--uid"\)/);
  assert.match(sourceText, /strcmp\(argv\[3\], "--gid"\)/);
  assert.match(sourceText, /strcmp\(argv\[5\], "--exec-fd"\)/);
  assert.match(sourceText, /strcmp\(argv\[7\], "--cgroup-procs-fd"\)/);
  assert.match(sourceText, /strcmp\(argv\[9\], "--"\)/);
  assert.match(sourceText, /uid_value != \(unsigned long\)RUNTIME_UID/);
  assert.match(sourceText, /gid_value != \(unsigned long\)RUNTIME_GID/);
  assert.match(sourceText, /fstat\(exec_fd, &metadata\)/);
  assert.match(sourceText, /fstat\(cgroup_procs_fd, &metadata\)/);
  assert.match(sourceText, /fstatfs\(cgroup_procs_fd, &filesystem\)/);
  assert.match(sourceText, /CGROUP2_SUPER_MAGIC/);
  assert.match(sourceText, /write\(cgroup_procs_fd, pid_text/);
  assert.match(sourceText, /sigprocmask\(SIG_SETMASK, &empty, NULL\)/);
  assert.match(sourceText, /sigaction\(signal_number, &action, NULL\)/);
  assert.match(sourceText, /S_ISREG\(metadata\.st_mode\)/);
  assert.match(sourceText, /setgroups\(0, NULL\)/);
  assert.match(sourceText, /setresgid\(RUNTIME_GID, RUNTIME_GID, RUNTIME_GID\)/);
  assert.match(sourceText, /setresuid\(RUNTIME_UID, RUNTIME_UID, RUNTIME_UID\)/);
  assert.match(sourceText, /PR_SET_NO_NEW_PRIVS/);
  assert.match(sourceText, /PR_SET_DUMPABLE/);
  assert.match(sourceText, /RLIMIT_CORE/);
  assert.match(sourceText, /RLIMIT_NOFILE/);
  assert.match(sourceText, /RLIMIT_NPROC/);
  assert.match(sourceText, /RLIMIT_FSIZE/);
  assert.match(sourceText, /RLIMIT_AS/);
  assert.match(sourceText, /RLIMIT_CPU/);
  assert.match(sourceText, /RLIMIT_STACK/);
  assert.match(sourceText, /SYS_close_range/);
  assert.match(sourceText, /PR_CAP_AMBIENT_CLEAR_ALL/);
  assert.match(sourceText, /SYS_capset/);
  assert.match(sourceText, /SECCOMP_MODE_FILTER/);
  for (const syscallName of [
    "mount",
    "umount2",
    "pivot_root",
    "setns",
    "unshare",
    "ptrace",
    "bpf",
    "perf_event_open",
    "keyctl",
    "init_module",
    "finit_module",
    "delete_module",
    "mknod",
    "mknodat",
  ]) assert.match(sourceText, new RegExp(`__NR_${syscallName}\\b`));
  assert.match(sourceText, /AF_PACKET/);
  assert.match(sourceText, /SOCK_RAW/);
  assert.match(sourceText, /SYS_execveat/);
  assert.match(sourceText, /fexecve\(/);
  assert.doesNotMatch(sourceText, /\bsystem\s*\(|\bpopen\s*\(|\bfork\s*\(|\bexec[lvpe]+\s*\(/);
  assert.doesNotMatch(sourceText, /\bopen(?:at)?\s*\(/);

  const mainBody = sourceText.slice(sourceText.indexOf("int main("));
  const orderedOperations = [
    "geteuid() != 0",
    "validate_arguments(argc, argv",
    "validate_executable_fd(exec_fd)",
    "enter_request_cgroup(cgroup_procs_fd)",
    "reset_signal_state()",
    "setgroups(0, NULL)",
    "setresgid(RUNTIME_GID",
    "setresuid(RUNTIME_UID",
    "PR_SET_NO_NEW_PRIVS",
    "PR_SET_DUMPABLE",
    "install_resource_limits()",
    "close_non_allowlisted_fds(exec_fd)",
    "clear_capabilities()",
    "install_seccomp_denylist()",
    "execute_fd(exec_fd",
  ];
  let previous = -1;
  for (const operation of orderedOperations) {
    const position = mainBody.indexOf(operation);
    assert.ok(position > previous, `launcher_operation_order_invalid:${operation}`);
    previous = position;
  }
}

sourceAudit();

function writeSourceAudit(extra = {}) {
  process.stdout.write(`${JSON.stringify({
    contract: "agentops_openclaw_runtime_launcher_foundation_a07_source_audit_v1",
    ok: true,
    source_operation_order_audited: true,
    exact_named_argv_audited: "--uid 1200 --gid 1200 --exec-fd FD --cgroup-procs-fd FD -- ARGV0 [ARGS...]",
    inherited_cgroup_procs_fd_write_order_audited: true,
    cgroup2_superblock_fd_required: true,
    signal_mask_and_dispositions_reset_audited: true,
    shell_and_path_execution_omitted: true,
    required_seccomp_denylist_audited: true,
    linux_native_hardened_compile_verified: false,
    root_negative_tests_verified: false,
    real_cgroup_v2_membership_verified: false,
    runtime_receipt_verified: false,
    hostile_runtime_isolation_verified: false,
    ...extra,
  })}\n`);
}

if (sourceAuditOnly) {
  writeSourceAudit();
  process.exit(0);
}

if (process.platform !== "linux" || (typeof process.geteuid === "function" && process.geteuid() !== 0)) {
  if (insideLinux) {
    process.stderr.write("runtime_launcher_linux_root_contract_unavailable\n");
    process.exit(78);
  }
  const repoRoot = dirname(dirname(dirname(sourcePath)));
  const dockerConfig = mkdtempSync(join(tmpdir(), "agentops-launcher-docker-config-"));
  const dockerHost = process.env.DOCKER_HOST
    ?? (process.platform === "darwin" ? `unix://${process.env.HOME}/.docker/run/docker.sock` : undefined);
  const dockerEnvironment = {
    PATH: process.env.PATH,
    DOCKER_CONFIG: dockerConfig,
    ...(dockerHost ? { DOCKER_HOST: dockerHost } : {}),
  };
  const linuxTestImage = process.env.AGENTOPS_LAUNCHER_TEST_IMAGE || "node:22-bookworm";
  if (!/^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,511}$/.test(linuxTestImage)) {
    throw new Error("runtime_launcher_linux_test_image_invalid");
  }
  const dockerProbe = spawnSync("docker", ["version", "--format", "{{.Server.Version}}"], {
    encoding: "utf8",
    env: dockerEnvironment,
    timeout: 10_000,
    killSignal: "SIGKILL",
  });
  if (dockerProbe.error || dockerProbe.status !== 0) {
    rmSync(dockerConfig, { recursive: true, force: true });
    if (requireRealLinux) {
      process.stderr.write("runtime_launcher_linux_container_runtime_required\n");
      process.exit(78);
    }
    writeSourceAudit({ linux_container_runtime_available: false });
    process.exit(0);
  }
  const docker = spawnSync("docker", [
    "run",
    "--pull=never",
    "--rm",
    "--read-only",
    "--network",
    "none",
    "--security-opt",
    "seccomp=unconfined",
    "--tmpfs",
    "/tmp:rw,exec,nosuid,nodev,size=128m,mode=1777",
    "--volume",
    `${repoRoot}:/workspace:ro`,
    "--workdir",
    "/workspace",
    linuxTestImage,
    "node",
    "/workspace/deploy/byoc/openclaw-runtime-launcher-contract.mjs",
    "--inside-linux",
  ], {
    encoding: "utf8",
    env: dockerEnvironment,
    timeout: 60_000,
    killSignal: "SIGKILL",
  });
  rmSync(dockerConfig, { recursive: true, force: true });
  assert.equal(docker.error?.code, undefined, docker.error?.code ?? "");
  assert.equal(
    docker.status,
    0,
    `${docker.error?.code ?? ""}${docker.error?.message ?? ""}${docker.stdout}${docker.stderr}`,
  );
  process.stdout.write(docker.stdout);
  process.exit(0);
}

const root = mkdtempSync(join(tmpdir(), "agentops-runtime-launcher-contract-"));
const binary = join(root, "openclaw-runtime-launcher");
const probeSource = join(root, "runtime-probe.c");
const probeBinary = join(root, "runtime-probe");
const nonExecutable = join(root, "not-executable");
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

const probeText = String.raw`
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <linux/seccomp.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

static int exact_limit(int resource, rlim_t expected) {
    struct rlimit value;
    return getrlimit(resource, &value) == 0
        && value.rlim_cur == expected
        && value.rlim_max == expected;
}

static int denied(long number) {
    errno = 0;
    return syscall(number, -1, 0, 0, 0, 0, 0) == -1 && errno == EPERM;
}

static int identity_probe(void) {
    struct __user_cap_header_struct header = {0};
    struct __user_cap_data_struct data[2] = {{0}};
    int fd;
    if (getuid() != 1200 || geteuid() != 1200 || getgid() != 1200 || getegid() != 1200) return 10;
    if (getgroups(0, NULL) != 0) return 11;
    if (prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) != 1) return 12;
    if (prctl(PR_GET_SECCOMP, 0L, 0L, 0L, 0L) != SECCOMP_MODE_FILTER) return 13;
    if (prctl(PR_GET_DUMPABLE, 0L, 0L, 0L, 0L) != 0) return 19;
    if (!exact_limit(RLIMIT_CORE, 0) || !exact_limit(RLIMIT_NOFILE, 64)
        || !exact_limit(RLIMIT_NPROC, 64)
        || !exact_limit(RLIMIT_FSIZE, (rlim_t)1024 * 1024 * 1024)
        || !exact_limit(RLIMIT_AS, (rlim_t)2 * 1024 * 1024 * 1024)
        || !exact_limit(RLIMIT_CPU, 300)
        || !exact_limit(RLIMIT_STACK, (rlim_t)64 * 1024 * 1024)
        || !exact_limit(RLIMIT_MEMLOCK, 0)) return 14;
    for (fd = 3; fd < 256; fd += 1) {
        errno = 0;
        if (fcntl(fd, F_GETFD) != -1 || errno != EBADF) return 15;
    }
    header.version = _LINUX_CAPABILITY_VERSION_3;
    if (syscall(SYS_capget, &header, data) != 0) return 16;
    if (data[0].effective || data[0].permitted || data[0].inheritable
        || data[1].effective || data[1].permitted || data[1].inheritable) return 17;
    if (getenv("HOME") != NULL || strcmp(getenv("LANG"), "C") != 0
        || strcmp(getenv("PATH"), "/usr/bin:/bin") != 0) return 18;
    puts("runtime_probe_identity_ok");
    return 0;
}

static int seccomp_probe(void) {
    int ordinary;
    (void)unlink("/tmp/agentops-launcher-mknod-probe");
    if (!denied(__NR_mount) || !denied(__NR_umount2)
#ifdef __NR_pivot_root
        || !denied(__NR_pivot_root)
#endif
        || !denied(__NR_setns) || !denied(__NR_unshare) || !denied(__NR_ptrace)
        || !denied(__NR_bpf) || !denied(__NR_perf_event_open) || !denied(__NR_keyctl)
        || !denied(__NR_init_module) || !denied(__NR_finit_module) || !denied(__NR_delete_module)
#ifdef __NR_mknod
        || !denied(__NR_mknod)
#endif
        || !denied(__NR_mknodat)) return 20;
    errno = 0;
    if (mknod("/tmp/agentops-launcher-mknod-probe", S_IFREG | 0600, 0) != -1 || errno != EPERM) return 24;
    errno = 0;
    if (socket(AF_PACKET, SOCK_DGRAM, 0) != -1 || errno != EPERM) return 21;
    errno = 0;
    if (socket(AF_INET, SOCK_RAW, IPPROTO_RAW) != -1 || errno != EPERM) return 22;
    ordinary = socket(AF_UNIX, SOCK_STREAM, 0);
    if (ordinary < 0) return 23;
    close(ordinary);
    puts("runtime_probe_seccomp_ok");
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    if (strcmp(argv[1], "identity") == 0) return identity_probe();
    if (strcmp(argv[1], "seccomp") == 0) return seccomp_probe();
    return 3;
}
`;

function compile(source, output) {
  const result = spawnSync("cc", [...compileFlags, source, "-o", output], {
    encoding: "utf8",
    env: { PATH: process.env.PATH },
  });
  assert.equal(result.status, 0, result.stderr);
}

function launcherArgs(fd, childArgs = [probeBinary, "identity"], cgroupFd = 4) {
  return [
    "--uid", "1200",
    "--gid", "1200",
    "--exec-fd", String(fd),
    "--cgroup-procs-fd", String(cgroupFd),
    "--",
    ...childArgs,
  ];
}

function launchWithFd(childArgs, options = {}) {
  const executableFd = openSync(probeBinary, "r");
  const cgroupPath = join(root, `cgroup-procs-${Date.now()}-${Math.random()}`);
  writeFileSync(cgroupPath, "", { mode: 0o600 });
  const cgroupFd = openSync(cgroupPath, "w");
  try {
    const result = spawnSync(binary, launcherArgs(3, childArgs, 4), {
      encoding: "utf8",
      env: options.env ?? {},
      uid: options.uid,
      gid: options.gid,
      stdio: ["ignore", "pipe", "pipe", executableFd, cgroupFd],
    });
    result.cgroupWrite = readFileSync(cgroupPath, "utf8");
    return result;
  } finally {
    closeSync(executableFd);
    closeSync(cgroupFd);
  }
}

function launchWithRejectedFd(parentFd) {
  const cgroupPath = join(root, `cgroup-procs-${Date.now()}-${Math.random()}`);
  writeFileSync(cgroupPath, "", { mode: 0o600 });
  const cgroupFd = openSync(cgroupPath, "w");
  try {
    return spawnSync(binary, launcherArgs(3, undefined, 4), {
      encoding: "utf8",
      env: {},
      stdio: ["ignore", "pipe", "pipe", parentFd, cgroupFd],
    });
  } finally {
    closeSync(cgroupFd);
  }
}

function launchWithRealCgroup(childArgs, cgroupProcsPath) {
  const executableFd = openSync(probeBinary, "r");
  const cgroupFd = openSync(cgroupProcsPath, "w");
  try {
    return spawnSync(binary, launcherArgs(3, childArgs, 4), {
      encoding: "utf8",
      env: {},
      stdio: ["ignore", "pipe", "pipe", executableFd, cgroupFd],
    });
  } finally {
    closeSync(executableFd);
    closeSync(cgroupFd);
  }
}

try {
  chmodSync(root, 0o755);
  writeFileSync(probeSource, probeText, { mode: 0o600 });
  writeFileSync(nonExecutable, "not an executable\n", { mode: 0o600 });
  compile(sourcePath, binary);
  compile(probeSource, probeBinary);

  const nonRoot = launchWithFd([probeBinary, "identity"], { uid: 65534, gid: 65534 });
  assert.equal(
    nonRoot.status,
    77,
    `${nonRoot.error?.code ?? ""}${nonRoot.error?.message ?? ""}${nonRoot.stdout}${nonRoot.stderr}`,
  );
  assert.equal(nonRoot.stderr, "runtime_launcher_root_required\n");

  const valid = launcherArgs(3);
  for (const invalid of [
    valid.slice(0, 9),
    ["--uid", "1200", "--gid", "1200", "--exec-fd", "3", "--cgroup-procs-fd", "4", "--extra", "value", "--", probeBinary, "identity"],
    ["--gid", "1200", "--uid", "1200", "--exec-fd", "3", "--cgroup-procs-fd", "4", "--", probeBinary, "identity"],
    ["--uid", "01200", "--gid", "1200", "--exec-fd", "3", "--cgroup-procs-fd", "4", "--", probeBinary, "identity"],
    ["--uid", "1200", "--gid", "1201", "--exec-fd", "3", "--cgroup-procs-fd", "4", "--", probeBinary, "identity"],
    ["--uid", "1200", "--gid", "1200", "--exec-fd", "2", "--cgroup-procs-fd", "4", "--", probeBinary, "identity"],
    ["--uid", "1200", "--gid", "1200", "--exec-fd", "not-an-fd", "--cgroup-procs-fd", "4", "--", probeBinary, "identity"],
    ["--uid", "1200", "--gid", "1200", "--exec-fd", "3", "--cgroup-procs-fd", "03", "--", probeBinary, "identity"],
    ["--uid", "1200", "--gid", "1200", "--exec-fd", "3", "--cgroup-procs-fd", "3", "--", probeBinary, "identity"],
  ]) {
    const rejected = spawnSync(binary, invalid, { encoding: "utf8", env: {} });
    assert.equal(rejected.status, 64, `${rejected.stdout}${rejected.stderr}`);
  }

  const missingFd = spawnSync(binary, launcherArgs(63), { encoding: "utf8", env: {} });
  assert.equal(missingFd.status, 65, `${missingFd.stdout}${missingFd.stderr}`);
  const executableFd = openSync(probeBinary, "r");
  try {
    const missingCgroupFd = spawnSync(binary, launcherArgs(3, undefined, 63), {
      encoding: "utf8",
      env: {},
      stdio: ["ignore", "pipe", "pipe", executableFd],
    });
    assert.equal(missingCgroupFd.status, 70, `${missingCgroupFd.stdout}${missingCgroupFd.stderr}`);
    assert.equal(missingCgroupFd.stderr, "runtime_launcher_cgroup_entry_failed\n");
  } finally {
    closeSync(executableFd);
  }
  for (const rejectedPath of [root, nonExecutable]) {
    const rejectedFd = openSync(rejectedPath, "r");
    try {
      const rejected = launchWithRejectedFd(rejectedFd);
      assert.equal(rejected.status, 65, `${rejected.stdout}${rejected.stderr}`);
    } finally {
      closeSync(rejectedFd);
    }
  }

  const forgedCgroupFd = launchWithFd([probeBinary, "identity"], {
    env: { HOME: "/forbidden", SECRET_CANARY: "must-not-survive" },
  });
  assert.equal(forgedCgroupFd.status, 70, `${forgedCgroupFd.stdout}${forgedCgroupFd.stderr}`);
  assert.equal(forgedCgroupFd.stderr, "runtime_launcher_cgroup_entry_failed\n");
  assert.equal(forgedCgroupFd.cgroupWrite, "");

  const realCgroupProcsPath = process.env.AGENTOPS_TEST_CGROUP_PROCS_PATH || "";
  let realCgroupVerified = false;
  if (realCgroupProcsPath) {
    const identity = launchWithRealCgroup([probeBinary, "identity"], realCgroupProcsPath);
    assert.equal(identity.status, 0, `${identity.stdout}${identity.stderr}`);
    assert.equal(identity.stdout, "runtime_probe_identity_ok\n");
    assert.equal(identity.stderr, "");
    const seccomp = launchWithRealCgroup([probeBinary, "seccomp"], realCgroupProcsPath);
    assert.equal(seccomp.status, 0, `${seccomp.stdout}${seccomp.stderr}`);
    assert.equal(seccomp.stdout, "runtime_probe_seccomp_ok\n");
    assert.equal(seccomp.stderr, "");
    realCgroupVerified = true;
  }

  process.stdout.write(`${JSON.stringify({
    contract: "agentops_openclaw_runtime_launcher_foundation_a07_v1",
    ok: true,
    linux_native_hardened_compile_verified: true,
    source_operation_order_audited: true,
    exact_named_argv_audited: "--uid 1200 --gid 1200 --exec-fd FD --cgroup-procs-fd FD -- ARGV0 [ARGS...]",
    forged_non_cgroup2_procs_fd_rejected: true,
    shell_execution_omitted: true,
    inherited_executable_fd_required: true,
    non_root_rejected: true,
    wrong_identity_and_fd_inputs_rejected: true,
    root_identity_transition_probe_passed: realCgroupVerified,
    empty_supplementary_groups_probe_passed: realCgroupVerified,
    no_new_privs_probe_passed: realCgroupVerified,
    dumpable_disabled_probe_passed: realCgroupVerified,
    explicit_rlimits_probe_passed: realCgroupVerified,
    non_allowlisted_fds_closed_probe_passed: realCgroupVerified,
    capability_sets_cleared_probe_passed: realCgroupVerified,
    seccomp_denylist_negative_probes_passed: realCgroupVerified,
    raw_and_packet_socket_negative_probes_passed: realCgroupVerified,
    ordinary_unix_stream_socket_probe_passed: realCgroupVerified,
    fixed_environment_probe_passed: realCgroupVerified,
    launcher_foundation_only: true,
    real_cgroup_v2_membership_verified: realCgroupVerified,
    production_wiring_verified: false,
    runtime_receipt_verified: false,
    hostile_runtime_isolation_verified: false,
  })}\n`);
} finally {
  rmSync(root, { recursive: true, force: true });
}
