#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  chmodSync,
  chownSync,
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

const contractPath = fileURLToPath(import.meta.url);
const contractText = readFileSync(contractPath, "utf8");
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
const hostsSource = "/run/agentops-openclaw-bootstrap/hosts";
const hostsTarget = "/opt/agentops-provider/openclaw/etc/hosts";
const resolverSource = "/run/agentops-openclaw-bootstrap/resolv.conf";
const resolverTarget = "/opt/agentops-provider/openclaw/etc/resolv.conf";
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
  "OPENCLAW_EGRESS_GATEWAY_IPV4",
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

function embeddedProbeSourceAudit() {
  const prefix = "writeFileSync(probeSource, String.raw`";
  const suffix = "\n`, { mode: 0o600 });";
  const start = contractText.indexOf(prefix);
  assert.notEqual(start, -1);
  const contentStart = start + prefix.length;
  const end = contractText.indexOf(suffix, contentStart);
  assert.notEqual(end, -1);
  const probeSourceText = contractText.slice(contentStart, end);
  assert.match(
    probeSourceText,
    /O_PATH \| O_CLOEXEC \| O_NOFOLLOW \| \(directory \? O_DIRECTORY : 0\)/,
  );
  assert.match(probeSourceText, /"\/proc\/self\/fdinfo\/%d"/);
  assert.match(probeSourceText, /sscanf\(line, "mnt_id:\\t%lu"/);
  assert.match(probeSourceText, /struct probe_mount_record/);
  assert.match(probeSourceText, /char \*mount_id_text/);
  assert.match(probeSourceText, /char \*parent_id_text/);
  assert.match(probeSourceText, /char \*mount_point_text/);
  assert.match(probeSourceText, /char \*mount_options/);
  assert.match(probeSourceText, /probe_mount_descends_from/);
  assert.match(probeSourceText, /probe_mount_options_hardened/);
  assert.match(probeSourceText, /record->mount_id == config_mount_id/);
  assert.match(probeSourceText, /record->mount_id == hosts_mount_id/);
  assert.match(probeSourceText, /record->mount_id == resolver_mount_id/);
  assert.match(probeSourceText, /workspace_visible_mounts < 2U/);
  assert.match(probeSourceText, /172\.31\.250\.3 openclaw-egress-gateway/);
  assert.match(probeSourceText, /nameserver 127\.0\.0\.1\\noptions timeout:1 attempts:1 ndots:0/);
  assert.match(probeSourceText, /metadata\.st_uid == 0 && metadata\.st_gid == 2200/);
  assert.match(probeSourceText, /\(metadata\.st_mode & 0777\) == 0444/);
  for (const comparison of [
    "config_mount_id == hosts_mount_id",
    "config_mount_id == resolver_mount_id",
    "config_mount_id == workspace_mount_id",
    "hosts_mount_id == resolver_mount_id",
    "hosts_mount_id == workspace_mount_id",
    "resolver_mount_id == workspace_mount_id",
  ]) {
    assert.match(probeSourceText, new RegExp(comparison));
  }
  for (const rejectedIpv4 of [
    "8.8.8.8",
    "127.0.0.1",
    "169.254.169.254",
    "172.31.250.3/29",
  ]) {
    assert(contractText.includes(`"${rejectedIpv4}"`));
  }
  assert.match(contractText, /rejectedGateway\.stderr, "mount_bootstrap_name_service_failed\\n"/);
  assert.doesNotMatch(probeSourceText, /\bmatches\b/);
}

function sourceAudit() {
  embeddedProbeSourceAudit();
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
  for (const path of [
    configTarget,
    hostsSource,
    hostsTarget,
    resolverSource,
    resolverTarget,
    workspaceTarget,
  ]) {
    assert.match(sourceText, new RegExp(path.replaceAll("/", "\\/")));
  }
  assert.match(sourceText, /MS_BIND \| \(recursive_bind \? MS_REC : 0UL\)/);
  assert.match(sourceText, /harden_mount\(HOSTS_SOURCE, HOSTS_TARGET, 0\)/);
  assert.match(sourceText, /harden_mount\(RESOLVER_SOURCE, RESOLVER_TARGET, 0\)/);
  assert.match(sourceText, /harden_mount\(CONFIG_TARGET, CONFIG_TARGET, 0\)/);
  assert.match(sourceText, /harden_mount\(WORKSPACE_TARGET, WORKSPACE_TARGET, 1\)/);
  assert.match(
    sourceText,
    /"nameserver 127\.0\.0\.1\\n"\s*"options timeout:1 attempts:1 ndots:0\\n"/,
  );
  assert.match(sourceText, /inet_pton\(AF_INET, value, &address\) != 1/);
  assert.match(sourceText, /final_octet == 0U \|\| final_octet == 1U \|\| final_octet == 255U/);
  assert.match(sourceText, /\(host & 0xff000000U\) == 0x0a000000U/);
  assert.match(sourceText, /\(host & 0xfff00000U\) == 0xac100000U/);
  assert.match(sourceText, /\(host & 0xffff0000U\) == 0xc0a80000U/);
  assert.match(sourceText, /O_WRONLY \| O_CREAT \| O_EXCL \| O_CLOEXEC \| O_NOFOLLOW/);
  assert.match(sourceText, /fchmod\(descriptor, 0444\)/);
  assert.match(sourceText, /metadata\.st_uid != \(uid_t\)0/);
  assert.match(sourceText, /metadata\.st_gid != PRIVATE_GID/);
  assert.match(sourceText, /metadata\.st_nlink != \(nlink_t\)1/);
  assert.match(sourceText, /\(metadata\.st_mode & 0777\) != 0444/);
  assert.match(sourceText, /SYS_mount_setattr/);
  assert.match(sourceText, /AT_RECURSIVE/);
  assert.match(sourceText, /MOUNT_ATTR_RDONLY \| MOUNT_ATTR_NOSUID/);
  assert.match(sourceText, /MOUNT_ATTR_NODEV \| MOUNT_ATTR_NOEXEC/);
  assert.match(sourceText, /mount_point_in_tree/);
  assert.match(sourceText, /\/proc\/self\/fdinfo\/%d/);
  assert.match(sourceText, /visible_mount_id\(CONFIG_TARGET, 0\)/);
  assert.match(sourceText, /visible_mount_id\(HOSTS_TARGET, 0\)/);
  assert.match(sourceText, /visible_mount_id\(RESOLVER_TARGET, 0\)/);
  assert.match(sourceText, /visible_mount_id\(WORKSPACE_TARGET, 1\)/);
  assert.match(sourceText, /mount_descends_from/);
  assert.match(sourceText, /mount_options_hardened/);
  assert.doesNotMatch(sourceText, /config_matches|workspace_matches/);
  assert.equal((sourceText.match(/SYS_mount_setattr/g) || []).length, 1);
  assert.match(sourceText, /MS_PRIVATE \| \(recursive_bind \? MS_REC : 0UL\)/);
  assert.match(sourceText, /open\("\/proc\/self\/mountinfo", O_RDONLY \| O_CLOEXEC \| O_NOFOLLOW\)/);
  for (const comparison of [
    "config_mount_id != hosts_mount_id",
    "config_mount_id != resolver_mount_id",
    "config_mount_id != workspace_mount_id",
    "hosts_mount_id != resolver_mount_id",
    "hosts_mount_id != workspace_mount_id",
    "resolver_mount_id != workspace_mount_id",
  ]) {
    assert.match(sourceText, new RegExp(comparison));
  }
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
  assert.equal(emittedCodes.length, 11);
  assert.equal(new Set(emittedCodes).size, emittedCodes.length);
  assert(emittedCodes.every((code) => code.startsWith("mount_bootstrap_")));
  assert(emittedCodes.includes("mount_bootstrap_name_service_failed"));
  assert.match(dockerfileText, /FROM peercred-build AS mount-bootstrap-build/);
  assert.match(
    dockerfileText,
    /COPY --from=mount-bootstrap-build --chmod=0555 \/agentops-openclaw-mount-bootstrap \/usr\/local\/bin\/agentops-openclaw-mount-bootstrap/,
  );
  const executor = composeText.match(/  executor:\n([\s\S]*?)(?=\nvolumes:)/)?.[1] || "";
  assert.match(executor, /init: false/);
  assert.match(executor, /entrypoint: \[\/usr\/local\/bin\/agentops-openclaw-mount-bootstrap\]/);
  assert.match(executor, /cap_add:\s*\n(?:\s+- [A-Z_]+\s*\n)*\s+- SYS_ADMIN\s*\n\s+- SETPCAP/);
  assert.match(
    executor,
    /\/run\/agentops-openclaw-bootstrap:rw,noexec,nosuid,nodev,size=1m,mode=0700,uid=0,gid=2200/,
  );
  assert.match(
    executor,
    /OPENCLAW_EGRESS_GATEWAY_IPV4: \$\{AGENTOPS_A08_RUNTIME_GATEWAY_IPV4:-172\.31\.250\.3\}/,
  );
  assert.match(
    composeText,
    /ipv4_address: \$\{AGENTOPS_A08_RUNTIME_GATEWAY_IPV4:-172\.31\.250\.3\}/,
  );
  assert.match(
    composeText,
    /subnet: \$\{AGENTOPS_A08_RUNTIME_SUBNET:-172\.31\.250\.0\/29\}/,
  );
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
    guest_name_service_files_verified: false,
    gateway_ipv4_rejections_verified: false,
    bootstrap_tmpfs_verified: false,
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
    for (const target of ["/opt", "/run", "/usr/local"]) {
      const mounted = spawnSync("mount", ["-t", "tmpfs", "-o", "mode=755,nosuid,nodev", "tmpfs", target], {
        encoding: "utf8",
        env: { PATH: process.env.PATH },
      });
      assert.equal(mounted.status, 0, mounted.stderr);
    }
    const bootstrapSourceDirectory = dirname(hostsSource);
    mkdirSync(bootstrapSourceDirectory, { recursive: true, mode: 0o700 });
    chownSync(bootstrapSourceDirectory, 0, 2200);
    const bootstrapMounted = spawnSync(
      "mount",
      [
        "-t",
        "tmpfs",
        "-o",
        "mode=0700,uid=0,gid=2200,nosuid,nodev,noexec",
        "tmpfs",
        bootstrapSourceDirectory,
      ],
      { encoding: "utf8", env: { PATH: process.env.PATH } },
    );
    assert.equal(bootstrapMounted.status, 0, bootstrapMounted.stderr);
    mkdirSync(dirname(configTarget), { recursive: true, mode: 0o755 });
    mkdirSync(dirname(hostsTarget), { recursive: true, mode: 0o755 });
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
    for (const target of [hostsTarget, resolverTarget]) {
      writeFileSync(target, "", { mode: 0o444 });
      chownSync(target, 0, 0);
      chmodSync(target, 0o444);
    }
    writeFileSync(supervisorPath, "fixture\n", { mode: 0o444 });
    writeFileSync(probeSource, String.raw`
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

#define CONFIG_TARGET "/opt/agentops-provider/openclaw/run/secrets/openclaw_config"
#define HOSTS_TARGET "/opt/agentops-provider/openclaw/etc/hosts"
#define RESOLVER_TARGET "/opt/agentops-provider/openclaw/etc/resolv.conf"
#define WORKSPACE_TARGET "/opt/agentops-provider/openclaw/opt/agentops-worker/workspace"

static int fixed_file_verified(const char *path, const char *expected) {
    int descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    struct stat metadata;
    char contents[512];
    size_t expected_length = strlen(expected);
    ssize_t count;
    int result = 0;
    if (descriptor < 0 || expected_length >= sizeof(contents)) return 0;
    do {
        count = read(descriptor, contents, sizeof(contents));
    } while (count < 0 && errno == EINTR);
    if (count >= 0 && (size_t)count == expected_length
        && memcmp(contents, expected, expected_length) == 0
        && fstat(descriptor, &metadata) == 0
        && S_ISREG(metadata.st_mode) && metadata.st_uid == 0 && metadata.st_gid == 2200
        && metadata.st_nlink == 1 && (metadata.st_mode & 0777) == 0444) result = 1;
    if (close(descriptor) != 0) result = 0;
    return result;
}

static int bit(const struct __user_cap_data_struct data[2], int capability, int field) {
    unsigned int index = (unsigned int)capability / 32U;
    unsigned int mask = 1U << ((unsigned int)capability % 32U);
    if (field == 0) return (data[index].effective & mask) != 0U;
    if (field == 1) return (data[index].permitted & mask) != 0U;
    return (data[index].inheritable & mask) != 0U;
}

struct probe_mount_record {
    unsigned long mount_id;
    unsigned long parent_id;
    char *mount_point;
    char *mount_options;
};

static int probe_decode_mountinfo_field(
    const char *source,
    char *destination,
    size_t destination_capacity
) {
    size_t source_length = strlen(source);
    size_t source_index = 0U;
    size_t destination_index = 0U;
    while (source[source_index] != '\0') {
        unsigned char value;
        if (destination_index + 1U >= destination_capacity) return 0;
        if (source[source_index] != '\\') {
            destination[destination_index] = source[source_index];
            source_index += 1U;
            destination_index += 1U;
            continue;
        }
        if (source_index + 3U >= source_length
            || source[source_index + 1U] < '0' || source[source_index + 1U] > '7'
            || source[source_index + 2U] < '0' || source[source_index + 2U] > '7'
            || source[source_index + 3U] < '0' || source[source_index + 3U] > '7') return 0;
        value = (unsigned char)(((unsigned int)(source[source_index + 1U] - '0') << 6U)
            | ((unsigned int)(source[source_index + 2U] - '0') << 3U)
            | (unsigned int)(source[source_index + 3U] - '0'));
        if (value != (unsigned char)' ' && value != (unsigned char)'\t'
            && value != (unsigned char)'\n' && value != (unsigned char)'\\') return 0;
        destination[destination_index] = (char)value;
        source_index += 4U;
        destination_index += 1U;
    }
    destination[destination_index] = '\0';
    return 1;
}

static int probe_option_present(const char *options, const char *expected) {
    const char *cursor = options;
    size_t expected_length = strlen(expected);
    while (*cursor != '\0') {
        const char *separator = strchr(cursor, ',');
        size_t option_length = separator == NULL
            ? strlen(cursor)
            : (size_t)(separator - cursor);
        if (option_length == expected_length
            && strncmp(cursor, expected, option_length) == 0) return 1;
        if (separator == NULL) return 0;
        cursor = separator + 1;
    }
    return 0;
}

static int probe_mount_options_hardened(const char *options) {
    return probe_option_present(options, "ro") && probe_option_present(options, "nosuid")
        && probe_option_present(options, "nodev") && probe_option_present(options, "noexec")
        && !probe_option_present(options, "rw") && !probe_option_present(options, "suid")
        && !probe_option_present(options, "dev") && !probe_option_present(options, "exec");
}

static int probe_mount_point_in_tree(const char *mount_point, const char *target) {
    size_t target_length = strlen(target);
    return strcmp(mount_point, target) == 0
        || (strncmp(mount_point, target, target_length) == 0
            && mount_point[target_length] == '/');
}

static int probe_parse_mountinfo_line(char *line, struct probe_mount_record *record) {
    char *save_pointer = NULL;
    char *mount_id_text = strtok_r(line, " ", &save_pointer);
    char *parent_id_text = strtok_r(NULL, " ", &save_pointer);
    char *device_text = strtok_r(NULL, " ", &save_pointer);
    char *root_text = strtok_r(NULL, " ", &save_pointer);
    char *mount_point_text = strtok_r(NULL, " ", &save_pointer);
    char *mount_options = strtok_r(NULL, " ", &save_pointer);
    char decoded_mount_point[PATH_MAX];
    char *end_pointer = NULL;
    unsigned long mount_id;
    unsigned long parent_id;
    (void)device_text;
    (void)root_text;
    if (mount_id_text == NULL || parent_id_text == NULL || mount_point_text == NULL
        || mount_options == NULL || !probe_decode_mountinfo_field(
            mount_point_text,
            decoded_mount_point,
            sizeof(decoded_mount_point)
        )) return 0;
    errno = 0;
    mount_id = strtoul(mount_id_text, &end_pointer, 10);
    if (errno != 0 || end_pointer == mount_id_text || *end_pointer != '\0'
        || mount_id == 0UL) return 0;
    errno = 0;
    parent_id = strtoul(parent_id_text, &end_pointer, 10);
    if (errno != 0 || end_pointer == parent_id_text || *end_pointer != '\0'
        || parent_id == 0UL || parent_id == mount_id) return 0;
    record->mount_id = mount_id;
    record->parent_id = parent_id;
    record->mount_point = strdup(decoded_mount_point);
    record->mount_options = strdup(mount_options);
    return record->mount_point != NULL && record->mount_options != NULL;
}

static const struct probe_mount_record *probe_find_mount_record(
    const struct probe_mount_record *records,
    size_t record_count,
    unsigned long mount_id
) {
    size_t record_index;
    for (record_index = 0U; record_index < record_count; record_index += 1U) {
        if (records[record_index].mount_id == mount_id) return &records[record_index];
    }
    return NULL;
}

static int probe_mount_descends_from(
    const struct probe_mount_record *records,
    size_t record_count,
    const struct probe_mount_record *candidate,
    unsigned long root_mount_id
) {
    unsigned long current_mount_id = candidate->mount_id;
    size_t depth;
    for (depth = 0U; depth <= record_count; depth += 1U) {
        const struct probe_mount_record *current_record;
        if (current_mount_id == root_mount_id) return 1;
        current_record = probe_find_mount_record(records, record_count, current_mount_id);
        if (current_record == NULL || current_record->parent_id == current_mount_id) return 0;
        current_mount_id = current_record->parent_id;
    }
    return 0;
}

static unsigned long probe_visible_mount_id(const char *target, int directory) {
    int descriptor = open(
        target,
        O_PATH | O_CLOEXEC | O_NOFOLLOW | (directory ? O_DIRECTORY : 0)
    );
    char fdinfo_path[64];
    FILE *fdinfo = NULL;
    char *line = NULL;
    size_t capacity = 0;
    unsigned long mount_id = 0UL;
    int path_length;
    if (descriptor < 0) return 0UL;
    path_length = snprintf(fdinfo_path, sizeof(fdinfo_path), "/proc/self/fdinfo/%d", descriptor);
    if (path_length > 0 && (size_t)path_length < sizeof(fdinfo_path)) {
        fdinfo = fopen(fdinfo_path, "r");
    }
    if (fdinfo != NULL) {
        while (getline(&line, &capacity, fdinfo) >= 0) {
            if (sscanf(line, "mnt_id:\t%lu", &mount_id) == 1 && mount_id != 0UL) break;
            mount_id = 0UL;
        }
        free(line);
        if (fclose(fdinfo) != 0) mount_id = 0UL;
    }
    if (close(descriptor) != 0) return 0UL;
    return mount_id;
}

static int options_verified(void) {
    int descriptor = open("/proc/self/mountinfo", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    FILE *input = NULL;
    struct probe_mount_record *records = NULL;
    size_t record_count = 0U;
    size_t record_capacity = 0U;
    unsigned long config_mount_id = probe_visible_mount_id(CONFIG_TARGET, 0);
    unsigned long hosts_mount_id = probe_visible_mount_id(HOSTS_TARGET, 0);
    unsigned long resolver_mount_id = probe_visible_mount_id(RESOLVER_TARGET, 0);
    unsigned long workspace_mount_id = probe_visible_mount_id(WORKSPACE_TARGET, 1);
    size_t workspace_visible_mounts = 0U;
    int config_verified = 0;
    int hosts_verified = 0;
    int resolver_verified = 0;
    int workspace_verified = 0;
    int result = 0;
    char *line = NULL;
    size_t line_capacity = 0U;
    size_t record_index;
    if (descriptor < 0 || config_mount_id == 0UL || hosts_mount_id == 0UL
        || resolver_mount_id == 0UL || workspace_mount_id == 0UL
        || config_mount_id == hosts_mount_id
        || config_mount_id == resolver_mount_id
        || config_mount_id == workspace_mount_id
        || hosts_mount_id == resolver_mount_id
        || hosts_mount_id == workspace_mount_id
        || resolver_mount_id == workspace_mount_id) goto cleanup;
    input = fdopen(descriptor, "r");
    if (input == NULL) goto cleanup;
    descriptor = -1;
    while (getline(&line, &line_capacity, input) >= 0) {
        struct probe_mount_record record = {0};
        if (record_count == record_capacity) {
            size_t next_capacity = record_capacity == 0U ? 64U : record_capacity * 2U;
            struct probe_mount_record *next_records;
            if (next_capacity < record_capacity) goto cleanup;
            next_records = realloc(records, next_capacity * sizeof(*records));
            if (next_records == NULL) goto cleanup;
            records = next_records;
            record_capacity = next_capacity;
        }
        if (!probe_parse_mountinfo_line(line, &record)) {
            free(record.mount_point);
            free(record.mount_options);
            goto cleanup;
        }
        records[record_count] = record;
        record_count += 1U;
    }
    if (ferror(input)) goto cleanup;
    for (record_index = 0U; record_index < record_count; record_index += 1U) {
        const struct probe_mount_record *record = &records[record_index];
        if (record->mount_id == config_mount_id) {
            if (config_verified || strcmp(record->mount_point, CONFIG_TARGET) != 0
                || !probe_mount_options_hardened(record->mount_options)) goto cleanup;
            config_verified = 1;
        }
        if (record->mount_id == hosts_mount_id) {
            if (hosts_verified || strcmp(record->mount_point, HOSTS_TARGET) != 0
                || !probe_mount_options_hardened(record->mount_options)) goto cleanup;
            hosts_verified = 1;
        }
        if (record->mount_id == resolver_mount_id) {
            if (resolver_verified || strcmp(record->mount_point, RESOLVER_TARGET) != 0
                || !probe_mount_options_hardened(record->mount_options)) goto cleanup;
            resolver_verified = 1;
        }
        if (probe_mount_descends_from(records, record_count, record, workspace_mount_id)) {
            if (!probe_mount_point_in_tree(record->mount_point, WORKSPACE_TARGET)
                || !probe_mount_options_hardened(record->mount_options)) goto cleanup;
            workspace_visible_mounts += 1U;
            if (record->mount_id == workspace_mount_id) workspace_verified = 1;
        }
    }
    if (!config_verified || !hosts_verified || !resolver_verified
        || !workspace_verified || workspace_visible_mounts < 2U) goto cleanup;
    result = 1;

cleanup:
    free(line);
    for (record_index = 0U; record_index < record_count; record_index += 1U) {
        free(records[record_index].mount_point);
        free(records[record_index].mount_options);
    }
    free(records);
    if (input != NULL) {
        if (fclose(input) != 0) result = 0;
    } else if (descriptor >= 0 && close(descriptor) != 0) {
        result = 0;
    }
    return result;
}

int main(int argc, char **argv) {
    struct __user_cap_header_struct header = {0};
    struct __user_cap_data_struct data[2] = {{0}};
    const int retained[] = {CAP_SETUID, CAP_SETGID, CAP_SYS_CHROOT, CAP_KILL};
    FILE *output;
    size_t index;
    const char *role = getenv("AGENTOPS_OPENCLAW_BOUNDARY_ROLE");
    const char *config = getenv("OPENCLAW_CONFIG_PATH");
    const char *gateway_ipv4 = getenv("OPENCLAW_EGRESS_GATEWAY_IPV4");
    const char *state = getenv("OPENCLAW_STATE_DIR");
    const char *workspace = getenv("OPENCLAW_WORKSPACE");
    if (getuid() != 0 || geteuid() != 0 || getgid() != 2200 || getegid() != 2200) return 9;
    if (argc != 2 || strcmp(argv[1], "/usr/local/lib/agentops/openclaw-boundary-supervisor.mjs") != 0) return 10;
    if (getenv("AGENTOPS_UNKNOWN_CANARY") != NULL || getenv("SECRET_CANARY") != NULL) return 11;
    if (role == NULL || strcmp(role, "root-executor") != 0
        || config == NULL || strcmp(config, "/run/secrets/openclaw_config") != 0
        || gateway_ipv4 == NULL || strcmp(gateway_ipv4, "172.31.250.3") != 0
        || state == NULL || strcmp(state, "/run/openclaw-state") != 0
        || workspace == NULL || strcmp(workspace, "/opt/agentops-worker/workspace") != 0) return 21;
    if (getenv("AGENTOPS_OPENCLAW_BROKER_PUBLIC_SOCKET_PATH") != NULL
        || getenv("OPENCLAW_PROVIDER_SOCKET") != NULL) return 22;
    if (!fixed_file_verified(
            HOSTS_TARGET,
            "127.0.0.1 localhost\n::1 localhost\n172.31.250.3 openclaw-egress-gateway\n"
        ) || !fixed_file_verified(
            RESOLVER_TARGET,
            "nameserver 127.0.0.1\noptions timeout:1 attempts:1 ndots:0\n"
        )) return 23;
    if (!options_verified()) return 20;
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
      OPENCLAW_EGRESS_GATEWAY_IPV4: "172.31.250.3",
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

    for (const rejectedIpv4 of [
      "8.8.8.8",
      "127.0.0.1",
      "169.254.169.254",
      "172.31.250.3/29",
    ]) {
      const rejectedGateway = runAsPid1({
        ...environment,
        OPENCLAW_EGRESS_GATEWAY_IPV4: rejectedIpv4,
      });
      assert.equal(rejectedGateway.status, 70);
      assert.equal(rejectedGateway.stderr, "mount_bootstrap_name_service_failed\n");
      assert(!rejectedGateway.stderr.includes(rejectedIpv4));
    }

    process.stdout.write(`${JSON.stringify(stableResult({
      linux_native_compile_verified: true,
      linux_runtime_executed: true,
      bind_remount_verified: true,
      mountinfo_flags_verified: true,
      guest_name_service_files_verified: true,
      gateway_ipv4_rejections_verified: true,
      bootstrap_tmpfs_verified: true,
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
