#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  copyFileSync,
  linkSync,
  lstatSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const sourcePath = fileURLToPath(new URL("./openclaw-mount-bootstrap.c", import.meta.url));
const sourceText = readFileSync(sourcePath, "utf8");
const dockerfileText = readFileSync(new URL("./Dockerfile", import.meta.url), "utf8");
const composeText = readFileSync(new URL("./compose.openclaw-phase-a07.yaml", import.meta.url), "utf8");
const supervisorText = readFileSync(new URL("./openclaw-boundary-supervisor.mjs", import.meta.url), "utf8");
const insideLinuxRuntime = process.argv.includes("--inside-linux-runtime");
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
const configTarget = "/opt/agentops-provider/openclaw/run/secrets/openclaw_config";
const workspaceTarget = "/opt/agentops-provider/openclaw/opt/agentops-worker/workspace";
const supervisorPath = "/usr/local/lib/agentops/openclaw-boundary-supervisor.mjs";
const expectedPrefixedEnvironment = [
  "AGENTOPS_OPENCLAW_BOUNDARY_ROLE",
  "OPENCLAW_CGROUP_POLICY_PATH",
  "OPENCLAW_CGROUP_ROOT",
  "OPENCLAW_CONFIG_PATH",
  "OPENCLAW_EXECUTOR_IMAGE_REFERENCE",
  "OPENCLAW_EXECUTOR_JOURNAL_ROOT",
  "OPENCLAW_EXECUTOR_LAUNCHER",
  "OPENCLAW_EXTERNAL_PROVIDER_EGRESS_ATTESTED",
  "OPENCLAW_RECEIPT_KEY_ID",
  "OPENCLAW_RECEIPT_SIGNING_KEY_PATH",
  "OPENCLAW_RUNTIME_GID",
  "OPENCLAW_RUNTIME_IMAGE_DIGEST",
  "OPENCLAW_RUNTIME_IMAGE_NAME",
  "OPENCLAW_RUNTIME_MANIFEST_ISSUER",
  "OPENCLAW_RUNTIME_MANIFEST_KEY_ID",
  "OPENCLAW_RUNTIME_RELEASE_ROOT",
  "OPENCLAW_RUNTIME_MANIFEST_TRUST_ROOT_PATH",
  "OPENCLAW_RUNTIME_ROOT",
  "OPENCLAW_RUNTIME_UID",
  "OPENCLAW_SECCOMP_PROFILE_PATH",
  "OPENCLAW_STATE_DIR",
  "OPENCLAW_WORKSPACE",
];

function sourceAudit() {
  assert.match(sourceText, /#ifndef __linux__/);
  assert.match(sourceText, /getpid\(\) != \(pid_t\)1/);
  assert.match(sourceText, /EXECUTOR_INIT_FALSE_REQUIRED/);
  assert.match(sourceText, /getuid\(\) != \(uid_t\)0/);
  assert.match(sourceText, /geteuid\(\) != \(uid_t\)0/);
  assert.match(sourceText, /#define PRIVATE_GID \(\(gid_t\)2200\)/);
  assert.match(sourceText, /getgid\(\) != PRIVATE_GID/);
  assert.match(sourceText, /getegid\(\) != PRIVATE_GID/);
  assert.match(sourceText, /open\("\/proc\/self\/exe", O_PATH \| O_CLOEXEC\)/);
  assert.match(sourceText, /S_ISREG\(executable_metadata\.st_mode\)/);
  assert.match(sourceText, /executable_metadata\.st_uid == \(uid_t\)0/);
  assert.match(sourceText, /S_IWGRP \| S_IWOTH/);
  assert.match(sourceText, /executable_metadata\.st_mode & 0111/);
  assert.match(sourceText, /executable_metadata\.st_nlink == \(nlink_t\)1/);
  assert.match(sourceText, new RegExp(configTarget.replaceAll("/", "\\/")));
  assert.match(sourceText, new RegExp(workspaceTarget.replaceAll("/", "\\/")));
  assert.match(sourceText, /MS_BIND \| \(recursive_bind \? MS_REC : 0UL\)/);
  assert.match(sourceText, /harden_mount\(CONFIG_TARGET, 0\)/);
  assert.match(sourceText, /harden_mount\(WORKSPACE_TARGET, 1\)/);
  assert.match(sourceText, /SYS_mount_setattr/);
  assert.match(sourceText, /AT_RECURSIVE/);
  assert.match(sourceText, /MOUNT_ATTR_RDONLY \| MOUNT_ATTR_NOSUID/);
  assert.match(sourceText, /MOUNT_ATTR_NODEV \| MOUNT_ATTR_NOEXEC/);
  assert.match(sourceText, /mount_point_in_tree/);
  assert.equal((sourceText.match(/SYS_mount_setattr/g) || []).length, 1);
  assert.match(sourceText, /MS_PRIVATE \| \(recursive_bind \? MS_REC : 0UL\)/);
  assert.match(sourceText, /open\("\/proc\/self\/mountinfo", O_RDONLY \| O_CLOEXEC \| O_NOFOLLOW\)/);
  assert.match(sourceText, /config_mount_id != workspace_mount_id/);
  for (const option of ["ro", "nosuid", "nodev", "noexec"]) {
    assert.match(sourceText, new RegExp(`option_present\\(mount_options, "${option}"\\)`));
  }
  assert.match(sourceText, /CAP_SYS_ADMIN/);
  assert.match(sourceText, /CAP_SETPCAP/);
  assert.match(sourceText, /PR_CAP_AMBIENT_LOWER/);
  assert.match(sourceText, /PR_CAPBSET_DROP/);
  assert.match(sourceText, /SYS_capset/);
  assert.match(sourceText, /capability <= CAP_LAST_CAP/);
  assert.match(sourceText, /retained_capability\(capability\)/);
  for (const capability of ["CAP_SETUID", "CAP_SETGID", "CAP_SYS_CHROOT", "CAP_KILL"]) {
    assert.match(sourceText, new RegExp(capability));
  }
  assert.match(sourceText, /PR_SET_NO_NEW_PRIVS/);
  assert.match(sourceText, /execve\(NODE_PATH, child_argv, clean_environment\)/);
  assert.match(sourceText, /#define NODE_PATH "\/usr\/local\/bin\/node"/);
  assert.match(sourceText, /#define SUPERVISOR_PATH "\/usr\/local\/lib\/agentops\/openclaw-boundary-supervisor\.mjs"/);
  assert.match(sourceText, /starts_with\(entry, "AGENTOPS_"\)/);
  assert.match(sourceText, /starts_with\(entry, "OPENCLAW_"\)/);
  assert.match(sourceText, /sysconf\(_SC_ARG_MAX\)/);
  const allowlistBody = /allowed_prefixed_environment\[\] = \{([\s\S]*?)\n\};/.exec(sourceText)?.[1];
  assert(allowlistBody);
  const actualPrefixedEnvironment = [...allowlistBody.matchAll(/"([A-Z0-9_]+)"/g)]
    .map((match) => match[1]);
  assert.deepEqual(actualPrefixedEnvironment, expectedPrefixedEnvironment);
  assert(!actualPrefixedEnvironment.includes("AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_PATH"));
  assert(!actualPrefixedEnvironment.includes("OPENCLAW_PROVIDER_SOCKET"));
  assert.doesNotMatch(sourceText, /\bsystem\s*\(/);
  assert.doesNotMatch(sourceText, /\bpopen\s*\(/);
  assert.doesNotMatch(sourceText, /\/bin\/(?:sh|bash)/);
  const stderrWrites = [...sourceText.matchAll(/fprintf\(stderr,\s*([^\n]+)\)/g)].map((match) => match[1]);
  assert.deepEqual(stderrWrites, ['"%s\\n", code']);
  const emittedCodes = [...sourceText.matchAll(/fixed_error\("([a-z0-9_]+)"\)/g)].map((match) => match[1]);
  assert.equal(emittedCodes.length, 10);
  assert.equal(new Set(emittedCodes).size, emittedCodes.length);
  assert(emittedCodes.every((code) => code.startsWith("mount_bootstrap_")));
  assert.match(dockerfileText, /FROM peercred-build AS mount-bootstrap-build/);
  assert.match(
    dockerfileText,
    /COPY --from=mount-bootstrap-build --chmod=0555 \/agentops-openclaw-mount-bootstrap \/usr\/local\/bin\/agentops-openclaw-mount-bootstrap/,
  );
  const executor = composeText.match(/  executor:\n([\s\S]*?)(?=\nvolumes:)/)?.[1] || "";
  assert.match(executor, /init: false/);
  assert.match(executor, /entrypoint: \[\/usr\/local\/bin\/agentops-openclaw-mount-bootstrap\]/);
  assert.match(executor, /cap_add:\s*\n(?:\s+- [A-Z_]+\s*\n)*\s+- SYS_ADMIN\s*\n\s+- SETPCAP/);
  assert.match(supervisorText, /const ROOT_EXECUTOR_ENTRYPOINT = "\/usr\/local\/lib\/agentops\/openclaw-executor-service\.mjs"/);
  assert.match(supervisorText, /if \(role === "root-executor"\)/);
}

function stableResult(overrides = {}) {
  return {
    contract: "agentops_openclaw_mount_bootstrap_a07_v1",
    ok: true,
    source_audit_verified: true,
    hardened_compile_flags_verified: true,
    linux_native_compile_verified: false,
    linux_runtime_executed: false,
    bind_remount_verified: false,
    mountinfo_flags_verified: false,
    capability_drop_verified: false,
    required_launcher_capabilities_retained: false,
    no_new_privs_verified: false,
    fixed_execve_verified: false,
    environment_allowlist_verified: false,
    unknown_prefixed_environment_rejected: false,
    stable_error_codes_verified: true,
    bootstrap_pid1_required: true,
    executor_init_false_required: true,
    private_gid_2200_required: true,
    temporary_cap_setpcap_required: true,
    temporary_cap_setpcap_removed: false,
    production_wiring_verified: true,
    ...overrides,
  };
}

function compile(source, output) {
  const result = spawnSync("cc", [...compileFlags, source, "-o", output], {
    encoding: "utf8",
    env: { PATH: process.env.PATH },
    timeout: 30_000,
    killSignal: "SIGKILL",
  });
  assert.equal(result.error?.code, undefined, result.error?.message ?? "");
  assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
}

function verifyNativeCompile() {
  const root = mkdtempSync(join(tmpdir(), "agentops-mount-bootstrap-compile-"));
  try {
    compile(sourcePath, join(root, "openclaw-mount-bootstrap"));
    return true;
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

sourceAudit();

if (insideLinuxRuntime) {
  assert.equal(process.platform, "linux");
  assert.equal(process.getuid(), 0);
  assert.equal(process.getgid(), 2200);
  assert.equal(process.pid, 1);
  const root = mkdtempSync(join(tmpdir(), "agentops-mount-bootstrap-runtime-"));
  const binary = join(root, "openclaw-mount-bootstrap");
  const probeSource = join(root, "node-probe.c");
  const probeBinary = join(root, "node-probe");
  const outputPath = "/tmp/agentops-mount-bootstrap-probe-result";
  const runAsPid1 = (environment, gid = 2200) => spawnSync("unshare", [
    "--mount",
    "--pid",
    "--fork",
    "--mount-proc",
    binary,
  ], {
    encoding: "utf8",
    env: environment,
    uid: 0,
    gid,
    timeout: 30_000,
    killSignal: "SIGKILL",
  });
  try {
    for (const target of ["/opt", "/usr/local"]) {
      const mounted = spawnSync("mount", ["-t", "tmpfs", "-o", "mode=755,nosuid,nodev", "tmpfs", target], {
        encoding: "utf8",
        env: { PATH: process.env.PATH },
      });
      assert.equal(mounted.status, 0, mounted.stderr);
    }
    mkdirSync(dirname(configTarget), { recursive: true, mode: 0o755 });
    mkdirSync(workspaceTarget, { recursive: true, mode: 0o555 });
    const nestedWorkspaceMount = join(workspaceTarget, "nested-mount");
    mkdirSync(nestedWorkspaceMount, { recursive: true, mode: 0o755 });
    const nestedMounted = spawnSync(
      "mount",
      ["-t", "tmpfs", "-o", "mode=755", "tmpfs", nestedWorkspaceMount],
      { encoding: "utf8", env: { PATH: process.env.PATH } },
    );
    assert.equal(nestedMounted.status, 0, nestedMounted.stderr);
    mkdirSync(dirname(supervisorPath), { recursive: true, mode: 0o755 });
    writeFileSync(configTarget, "fixture-not-a-secret\n", { mode: 0o400 });
    writeFileSync(supervisorPath, "fixture\n", { mode: 0o444 });
    writeFileSync(probeSource, String.raw`
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>

#define CONFIG_TARGET "/opt/agentops-provider/openclaw/run/secrets/openclaw_config"
#define WORKSPACE_TARGET "/opt/agentops-provider/openclaw/opt/agentops-worker/workspace"

static int bit(const struct __user_cap_data_struct data[2], int capability, int field) {
    unsigned int index = (unsigned int)capability / 32U;
    unsigned int mask = 1U << ((unsigned int)capability % 32U);
    if (field == 0) return (data[index].effective & mask) != 0U;
    if (field == 1) return (data[index].permitted & mask) != 0U;
    return (data[index].inheritable & mask) != 0U;
}

static int options_verified(const char *target, int recursive) {
    FILE *input = fopen("/proc/self/mountinfo", "r");
    char *line = NULL;
    size_t capacity = 0;
    int matches = 0;
    if (input == NULL) return 0;
    while (getline(&line, &capacity, input) >= 0) {
        char *save = NULL;
        char *field = strtok_r(line, " ", &save);
        int index = 0;
        char *mount_point = NULL;
        char *options = NULL;
        while (field != NULL && index <= 5) {
            if (index == 4) mount_point = field;
            if (index == 5) options = field;
            field = strtok_r(NULL, " ", &save);
            index += 1;
        }
        size_t target_length = strlen(target);
        if (mount_point != NULL && options != NULL
            && (strcmp(mount_point, target) == 0
                || (recursive && strncmp(mount_point, target, target_length) == 0
                    && mount_point[target_length] == '/'))) {
            char padded[512];
            int length = snprintf(padded, sizeof(padded), ",%s,", options);
            if (length <= 0 || (size_t)length >= sizeof(padded)
                || strstr(padded, ",ro,") == NULL || strstr(padded, ",nosuid,") == NULL
                || strstr(padded, ",nodev,") == NULL || strstr(padded, ",noexec,") == NULL
                || strstr(padded, ",rw,") != NULL || strstr(padded, ",suid,") != NULL
                || strstr(padded, ",dev,") != NULL || strstr(padded, ",exec,") != NULL) {
                free(line);
                fclose(input);
                return 0;
            }
            matches += 1;
        }
    }
    free(line);
    if (fclose(input) != 0) return 0;
    return recursive ? matches >= 2 : matches == 1;
}

int main(int argc, char **argv) {
    struct __user_cap_header_struct header = {0};
    struct __user_cap_data_struct data[2] = {{0}};
    const int retained[] = {CAP_SETUID, CAP_SETGID, CAP_SYS_CHROOT, CAP_KILL};
    FILE *output;
    size_t index;
    const char *role = getenv("AGENTOPS_OPENCLAW_BOUNDARY_ROLE");
    const char *config = getenv("OPENCLAW_CONFIG_PATH");
    const char *state = getenv("OPENCLAW_STATE_DIR");
    const char *workspace = getenv("OPENCLAW_WORKSPACE");
    if (getuid() != 0 || geteuid() != 0 || getgid() != 2200 || getegid() != 2200) return 9;
    if (argc != 2 || strcmp(argv[1], "/usr/local/lib/agentops/openclaw-boundary-supervisor.mjs") != 0) return 10;
    if (getenv("AGENTOPS_UNKNOWN_CANARY") != NULL || getenv("SECRET_CANARY") != NULL) return 11;
    if (role == NULL || strcmp(role, "root-executor") != 0
        || config == NULL || strcmp(config, "/run/secrets/openclaw_config") != 0
        || state == NULL || strcmp(state, "/run/openclaw-state") != 0
        || workspace == NULL || strcmp(workspace, "/opt/agentops-worker/workspace") != 0) return 21;
    if (getenv("AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_PATH") != NULL
        || getenv("OPENCLAW_PROVIDER_SOCKET") != NULL) return 22;
    if (!options_verified(CONFIG_TARGET, 0) || !options_verified(WORKSPACE_TARGET, 1)) return 20;
    header.version = _LINUX_CAPABILITY_VERSION_3;
    if (syscall(SYS_capget, &header, data) != 0) return 12;
    for (int capability = 0; capability <= CAP_LAST_CAP; capability += 1) {
        int expected = 0;
        for (index = 0; index < sizeof(retained) / sizeof(retained[0]); index += 1) {
            if (capability == retained[index]) expected = 1;
        }
        if (bit(data, capability, 0) != expected || bit(data, capability, 1) != expected
            || bit(data, capability, 2) != 0
            || prctl(PR_CAPBSET_READ, capability, 0L, 0L, 0L) != expected
            || prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_IS_SET, capability, 0L, 0L) != 0) return 16;
    }
    if (prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) != 1) return 17;
    output = fopen("/tmp/agentops-mount-bootstrap-probe-result", "w");
    if (output == NULL) return 18;
    if (fputs("bootstrap_probe_ok\n", output) < 0 || fclose(output) != 0) return 19;
    return 0;
}
`, { mode: 0o600 });
    compile(sourcePath, binary);
    compile(probeSource, probeBinary);
    chmodSync(binary, 0o555);
    chmodSync(probeBinary, 0o555);
    const metadata = lstatSync(binary);
    assert.equal(metadata.uid, 0);
    assert.equal(metadata.nlink, 1);
    assert.equal(metadata.mode & 0o022, 0);
    mkdirSync("/usr/local/bin", { recursive: true, mode: 0o755 });
    copyFileSync(probeBinary, "/usr/local/bin/node");
    chmodSync("/usr/local/bin/node", 0o555);
    const environment = {
      AGENTOPS_OPENCLAW_BOUNDARY_ROLE: "root-executor",
      LANG: "C",
      OPENCLAW_CONFIG_PATH: "/run/secrets/openclaw_config",
      OPENCLAW_STATE_DIR: "/run/openclaw-state",
      OPENCLAW_WORKSPACE: "/opt/agentops-worker/workspace",
      PATH: "/usr/bin:/bin",
      SECRET_CANARY: "must-not-survive",
    };
    rmSync(outputPath, { force: true });
    const execution = runAsPid1(environment);
    assert.equal(execution.error?.code, undefined, execution.error?.message ?? "");
    assert.equal(execution.status, 0, `${execution.stdout}${execution.stderr}`);
    assert.equal(execution.stdout, "");
    assert.equal(execution.stderr, "");
    assert.equal(readFileSync(outputPath, "utf8"), "bootstrap_probe_ok\n");
    const hardlinkedBinary = join(root, "openclaw-mount-bootstrap-hardlinked");
    linkSync(binary, hardlinkedBinary);
    const hardlinkRejection = runAsPid1(environment);
    assert.equal(hardlinkRejection.status, 65);
    assert.equal(hardlinkRejection.stderr, "mount_bootstrap_self_invalid\n");
    rmSync(hardlinkedBinary);

    const unknownEnvironment = runAsPid1({
      ...environment,
      AGENTOPS_UNKNOWN_CANARY: "value-must-not-leak",
    });
    assert.equal(unknownEnvironment.status, 78);
    assert.equal(unknownEnvironment.stderr, "mount_bootstrap_environment_forbidden\n");
    assert(!unknownEnvironment.stderr.includes("value-must-not-leak"));

    const wrongGid = runAsPid1(environment, 0);
    assert.equal(wrongGid.status, 77);
    assert.equal(wrongGid.stderr, "mount_bootstrap_pid1_root_required\n");

    const wrongGuestPath = runAsPid1({
      ...environment,
      OPENCLAW_WORKSPACE: "/wrong-workspace",
    });
    assert.equal(wrongGuestPath.status, 78);
    assert.equal(wrongGuestPath.stderr, "mount_bootstrap_environment_forbidden\n");

    process.stdout.write(`${JSON.stringify(stableResult({
      linux_native_compile_verified: true,
      linux_runtime_executed: true,
      bind_remount_verified: true,
      mountinfo_flags_verified: true,
      capability_drop_verified: true,
      required_launcher_capabilities_retained: true,
      temporary_cap_setpcap_removed: true,
      no_new_privs_verified: true,
      fixed_execve_verified: true,
      environment_allowlist_verified: true,
      unknown_prefixed_environment_rejected: true,
    }))}\n`);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
  process.exit(0);
}

if (process.platform !== "linux") {
  process.stdout.write(`${JSON.stringify(stableResult())}\n`);
  process.exit(0);
}

const linuxNativeCompileVerified = verifyNativeCompile();
if (process.getuid?.() !== 0) {
  process.stdout.write(`${JSON.stringify(stableResult({
    linux_native_compile_verified: linuxNativeCompileVerified,
  }))}\n`);
  process.exit(0);
}

const probe = spawnSync("unshare", ["--mount", "--pid", "--fork", "--mount-proc", "true"], {
  encoding: "utf8",
  env: { PATH: process.env.PATH },
  timeout: 10_000,
  killSignal: "SIGKILL",
});
if (probe.error || probe.status !== 0) {
  process.stdout.write(`${JSON.stringify(stableResult({
    linux_native_compile_verified: linuxNativeCompileVerified,
  }))}\n`);
  process.exit(0);
}

const execution = spawnSync("unshare", [
  "--mount",
  "--pid",
  "--fork",
  "--mount-proc",
  "node",
  fileURLToPath(import.meta.url),
  "--inside-linux-runtime",
], {
  encoding: "utf8",
  env: { PATH: process.env.PATH },
  uid: 0,
  gid: 2200,
  timeout: 60_000,
  killSignal: "SIGKILL",
});
assert.equal(execution.error?.code, undefined, execution.error?.message ?? "");
assert.equal(execution.status, 0, `${execution.stdout}${execution.stderr}`);
process.stdout.write(execution.stdout);
