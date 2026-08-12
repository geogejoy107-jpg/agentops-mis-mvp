#define _GNU_SOURCE

#ifndef __linux__
#error "openclaw-mount-bootstrap requires Linux"
#endif

#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <linux/mount.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

#define CONFIG_TARGET "/opt/agentops-provider/openclaw/run/secrets/openclaw_config"
#define WORKSPACE_TARGET "/opt/agentops-provider/openclaw/opt/agentops-worker/workspace"
#define NODE_PATH "/usr/local/bin/node"
#define SUPERVISOR_PATH "/usr/local/lib/agentops/openclaw-boundary-supervisor.mjs"
#define MAX_MOUNTINFO_BYTES (1024U * 1024U)
#define PRIVATE_GID ((gid_t)2200)

/* Production wiring must use executor init:false so this bootstrap is PID 1. */
#define EXECUTOR_INIT_FALSE_REQUIRED 1

extern char **environ;

static const char *const allowed_prefixed_environment[] = {
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
};

static const char *const allowed_system_environment[] = {
    "LANG",
    "LC_ALL",
    "NODE_ENV",
    "PATH",
    "TZ",
};

static void fixed_error(const char *code) {
    (void)fprintf(stderr, "%s\n", code);
}

static int starts_with(const char *value, const char *prefix) {
    size_t prefix_length = strlen(prefix);
    return strncmp(value, prefix, prefix_length) == 0;
}

static int environment_name_equals(const char *entry, const char *name) {
    size_t name_length = strlen(name);
    return strncmp(entry, name, name_length) == 0 && entry[name_length] == '=';
}

static int prefixed_environment_name_allowed(const char *entry) {
    size_t index;
    for (index = 0;
         index < sizeof(allowed_prefixed_environment) / sizeof(allowed_prefixed_environment[0]);
         index += 1) {
        if (environment_name_equals(entry, allowed_prefixed_environment[index])) {
            return 1;
        }
    }
    return 0;
}

static int validate_prefixed_environment(void) {
    size_t index;
    const char *role = getenv("AGENTOPS_OPENCLAW_BOUNDARY_ROLE");
    const char *config_path = getenv("OPENCLAW_CONFIG_PATH");
    const char *state_directory = getenv("OPENCLAW_STATE_DIR");
    const char *workspace = getenv("OPENCLAW_WORKSPACE");
    if (role == NULL || strcmp(role, "root-executor") != 0
        || config_path == NULL || strcmp(config_path, "/run/secrets/openclaw_config") != 0
        || state_directory == NULL || strcmp(state_directory, "/run/openclaw-state") != 0
        || workspace == NULL || strcmp(workspace, "/opt/agentops-worker/workspace") != 0) {
        return -1;
    }
    for (index = 0; environ[index] != NULL; index += 1) {
        const char *entry = environ[index];
        if ((starts_with(entry, "AGENTOPS_") || starts_with(entry, "OPENCLAW_"))
            && !prefixed_environment_name_allowed(entry)) {
            return -1;
        }
    }
    return 0;
}

static char **build_environment(void) {
    long system_argument_limit = sysconf(_SC_ARG_MAX);
    size_t argument_limit = system_argument_limit > 0 && system_argument_limit <= (long)(16U * 1024U * 1024U)
        ? (size_t)system_argument_limit
        : (size_t)(128U * 1024U);
    size_t capacity = sizeof(allowed_prefixed_environment) / sizeof(allowed_prefixed_environment[0])
        + sizeof(allowed_system_environment) / sizeof(allowed_system_environment[0]) + 1U;
    char **clean_environment = calloc(capacity, sizeof(*clean_environment));
    size_t output_index = 0;
    size_t index;

    if (clean_environment == NULL) {
        return NULL;
    }
    for (index = 0;
         index < sizeof(allowed_system_environment) / sizeof(allowed_system_environment[0]);
         index += 1) {
        char *value = getenv(allowed_system_environment[index]);
        if (value != NULL) {
            size_t name_length = strlen(allowed_system_environment[index]);
            size_t value_length = strlen(value);
            char *entry;
            if (value_length > argument_limit
                || name_length > argument_limit - value_length - 2U) {
                free(clean_environment);
                return NULL;
            }
            entry = malloc(name_length + value_length + 2U);
            if (entry == NULL) {
                free(clean_environment);
                return NULL;
            }
            (void)memcpy(entry, allowed_system_environment[index], name_length);
            entry[name_length] = '=';
            (void)memcpy(entry + name_length + 1U, value, value_length + 1U);
            clean_environment[output_index] = entry;
            output_index += 1U;
        }
    }
    for (index = 0;
         index < sizeof(allowed_prefixed_environment) / sizeof(allowed_prefixed_environment[0]);
         index += 1) {
        char *value = getenv(allowed_prefixed_environment[index]);
        if (value != NULL) {
            size_t name_length = strlen(allowed_prefixed_environment[index]);
            size_t value_length = strlen(value);
            char *entry;
            if (value_length > argument_limit
                || name_length > argument_limit - value_length - 2U) {
                free(clean_environment);
                return NULL;
            }
            entry = malloc(name_length + value_length + 2U);
            if (entry == NULL) {
                free(clean_environment);
                return NULL;
            }
            (void)memcpy(entry, allowed_prefixed_environment[index], name_length);
            entry[name_length] = '=';
            (void)memcpy(entry + name_length + 1U, value, value_length + 1U);
            clean_environment[output_index] = entry;
            output_index += 1U;
        }
    }
    clean_environment[output_index] = NULL;
    return clean_environment;
}

static int validate_self_executable(void) {
    struct stat executable_metadata;
    struct stat path_metadata;
    int executable_fd = open("/proc/self/exe", O_PATH | O_CLOEXEC);
    int result = -1;

    if (executable_fd < 0) {
        return -1;
    }
    if (fstat(executable_fd, &executable_metadata) == 0
        && stat("/proc/self/exe", &path_metadata) == 0
        && S_ISREG(executable_metadata.st_mode)
        && executable_metadata.st_uid == (uid_t)0
        && (executable_metadata.st_mode & (S_IWGRP | S_IWOTH)) == 0
        && (executable_metadata.st_mode & 0111) != 0
        && executable_metadata.st_nlink == (nlink_t)1
        && executable_metadata.st_dev == path_metadata.st_dev
        && executable_metadata.st_ino == path_metadata.st_ino) {
        result = 0;
    }
    if (close(executable_fd) < 0) {
        return -1;
    }
    return result;
}

static int harden_mount(const char *target, int recursive_bind) {
    const unsigned long bind_flags = MS_BIND | (recursive_bind ? MS_REC : 0UL);
    const struct mount_attr attributes = {
        .attr_set = MOUNT_ATTR_RDONLY | MOUNT_ATTR_NOSUID
            | MOUNT_ATTR_NODEV | MOUNT_ATTR_NOEXEC,
    };
    const unsigned int recursive_flags = recursive_bind ? AT_RECURSIVE : 0U;

    if (syscall(
        SYS_mount_setattr,
        AT_FDCWD,
        target,
        recursive_flags,
        &attributes,
        sizeof(attributes)
    ) < 0) {
        return -1;
    }
    if (mount(target, target, NULL, bind_flags, NULL) < 0) {
        return -1;
    }
    if (mount(NULL, target, NULL, MS_PRIVATE | (recursive_bind ? MS_REC : 0UL), NULL) < 0) {
        return -1;
    }
    if (syscall(
        SYS_mount_setattr,
        AT_FDCWD,
        target,
        recursive_flags,
        &attributes,
        sizeof(attributes)
    ) < 0) {
        return -1;
    }
    return 0;
}

static int decode_mountinfo_field(const char *source, char *destination, size_t capacity) {
    size_t source_length = strlen(source);
    size_t input_index = 0;
    size_t output_index = 0;
    while (source[input_index] != '\0') {
        unsigned char value;
        if (output_index + 1U >= capacity) {
            return -1;
        }
        if (source[input_index] != '\\') {
            destination[output_index] = source[input_index];
            input_index += 1U;
            output_index += 1U;
            continue;
        }
        if (input_index + 3U >= source_length
            || source[input_index + 1U] < '0' || source[input_index + 1U] > '7'
            || source[input_index + 2U] < '0' || source[input_index + 2U] > '7'
            || source[input_index + 3U] < '0' || source[input_index + 3U] > '7') {
            return -1;
        }
        value = (unsigned char)(((unsigned int)(source[input_index + 1U] - '0') << 6U)
            | ((unsigned int)(source[input_index + 2U] - '0') << 3U)
            | (unsigned int)(source[input_index + 3U] - '0'));
        if (value != (unsigned char)' ' && value != (unsigned char)'\t'
            && value != (unsigned char)'\n' && value != (unsigned char)'\\') {
            return -1;
        }
        destination[output_index] = (char)value;
        input_index += 4U;
        output_index += 1U;
    }
    destination[output_index] = '\0';
    return 0;
}

static int option_present(const char *options, const char *expected) {
    const char *cursor = options;
    size_t expected_length = strlen(expected);
    while (*cursor != '\0') {
        const char *separator = strchr(cursor, ',');
        size_t length = separator == NULL ? strlen(cursor) : (size_t)(separator - cursor);
        if (length == expected_length && strncmp(cursor, expected, length) == 0) {
            return 1;
        }
        if (separator == NULL) {
            return 0;
        }
        cursor = separator + 1;
    }
    return 0;
}

static int mount_point_in_tree(const char *mount_point, const char *target, int recursive) {
    size_t target_length = strlen(target);
    return strcmp(mount_point, target) == 0
        || (recursive && strncmp(mount_point, target, target_length) == 0
            && mount_point[target_length] == '/');
}

static int inspect_mountinfo_line(
    char *line,
    const char *target,
    int recursive,
    unsigned long *root_mount_id
) {
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
    unsigned long parsed_parent_id;

    (void)device_text;
    (void)root_text;
    if (mount_id_text == NULL || parent_id_text == NULL || mount_point_text == NULL
        || mount_options == NULL || decode_mountinfo_field(
            mount_point_text,
            decoded_mount_point,
            sizeof(decoded_mount_point)
        ) < 0 || !mount_point_in_tree(decoded_mount_point, target, recursive)) {
        return 0;
    }
    errno = 0;
    mount_id = strtoul(mount_id_text, &end_pointer, 10);
    if (errno != 0 || end_pointer == mount_id_text || *end_pointer != '\0' || mount_id == 0UL) {
        return -1;
    }
    errno = 0;
    parsed_parent_id = strtoul(parent_id_text, &end_pointer, 10);
    if (errno != 0 || end_pointer == parent_id_text || *end_pointer != '\0'
        || parsed_parent_id == 0UL || mount_id == parsed_parent_id) {
        return -1;
    }
    if (!option_present(mount_options, "ro") || !option_present(mount_options, "nosuid")
        || !option_present(mount_options, "nodev") || !option_present(mount_options, "noexec")
        || option_present(mount_options, "rw") || option_present(mount_options, "suid")
        || option_present(mount_options, "dev") || option_present(mount_options, "exec")) {
        return -1;
    }
    if (strcmp(decoded_mount_point, target) == 0) {
        if (*root_mount_id != 0UL) {
            return -1;
        }
        *root_mount_id = mount_id;
    }
    return 1;
}

static int verify_hardened_mounts(void) {
    int descriptor = open("/proc/self/mountinfo", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    char *contents;
    size_t used = 0;
    int config_matches = 0;
    int workspace_matches = 0;
    unsigned long config_mount_id = 0UL;
    unsigned long workspace_mount_id = 0UL;
    int result = -1;

    if (descriptor < 0) {
        return -1;
    }
    contents = malloc(MAX_MOUNTINFO_BYTES + 1U);
    if (contents == NULL) {
        (void)close(descriptor);
        return -1;
    }
    while (used < MAX_MOUNTINFO_BYTES) {
        ssize_t count = read(descriptor, contents + used, MAX_MOUNTINFO_BYTES - used);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        if (count < 0) {
            goto cleanup;
        }
        if (count == 0) {
            break;
        }
        used += (size_t)count;
    }
    if (used == MAX_MOUNTINFO_BYTES) {
        char overflow_byte;
        if (read(descriptor, &overflow_byte, 1U) != 0) {
            goto cleanup;
        }
    }
    contents[used] = '\0';
    {
        char *line_save_pointer = NULL;
        char *line = strtok_r(contents, "\n", &line_save_pointer);
        while (line != NULL) {
            char *config_line = strdup(line);
            char *workspace_line = strdup(line);
            int config_result;
            int workspace_result;
            if (config_line == NULL || workspace_line == NULL) {
                free(config_line);
                free(workspace_line);
                goto cleanup;
            }
            config_result = inspect_mountinfo_line(config_line, CONFIG_TARGET, 0, &config_mount_id);
            workspace_result = inspect_mountinfo_line(
                workspace_line,
                WORKSPACE_TARGET,
                1,
                &workspace_mount_id
            );
            free(config_line);
            free(workspace_line);
            if (config_result < 0 || workspace_result < 0) {
                goto cleanup;
            }
            config_matches += config_result;
            workspace_matches += workspace_result;
            line = strtok_r(NULL, "\n", &line_save_pointer);
        }
    }
    if (config_matches == 1 && workspace_matches >= 1
        && config_mount_id != 0UL && workspace_mount_id != 0UL
        && config_mount_id != workspace_mount_id) {
        result = 0;
    }

cleanup:
    free(contents);
    if (close(descriptor) < 0) {
        return -1;
    }
    return result;
}

static int capability_bit_set(const struct __user_cap_data_struct data[2], int capability, int field) {
    unsigned int index = (unsigned int)capability / 32U;
    unsigned int mask = 1U << ((unsigned int)capability % 32U);
    if (field == 0) {
        return (data[index].effective & mask) != 0U;
    }
    if (field == 1) {
        return (data[index].permitted & mask) != 0U;
    }
    return (data[index].inheritable & mask) != 0U;
}

static void clear_capability_bit(struct __user_cap_data_struct data[2], int capability) {
    unsigned int index = (unsigned int)capability / 32U;
    unsigned int mask = ~(1U << ((unsigned int)capability % 32U));
    data[index].effective &= mask;
    data[index].permitted &= mask;
    data[index].inheritable &= mask;
}

static int retained_capability(int capability) {
    return capability == CAP_SETUID
        || capability == CAP_SETGID
        || capability == CAP_SYS_CHROOT
        || capability == CAP_KILL;
}

static int reduce_to_launcher_capabilities(void) {
    static const int retained_capabilities[] = {
        CAP_SETUID,
        CAP_SETGID,
        CAP_SYS_CHROOT,
        CAP_KILL,
    };
    struct __user_cap_header_struct header;
    struct __user_cap_data_struct data[2];
    size_t index;

    memset(&header, 0, sizeof(header));
    memset(data, 0, sizeof(data));
    header.version = _LINUX_CAPABILITY_VERSION_3;
    header.pid = 0;
    if (syscall(SYS_capget, &header, data) < 0) {
        return -1;
    }
    for (index = 0; index < sizeof(retained_capabilities) / sizeof(retained_capabilities[0]); index += 1) {
        int capability = retained_capabilities[index];
        if (!capability_bit_set(data, capability, 0)
            || !capability_bit_set(data, capability, 1)
            || prctl(PR_CAPBSET_READ, capability, 0L, 0L, 0L) != 1) {
            return -1;
        }
    }
    if (!capability_bit_set(data, CAP_SYS_ADMIN, 0)
        || !capability_bit_set(data, CAP_SYS_ADMIN, 1)
        || !capability_bit_set(data, CAP_SETPCAP, 0)
        || !capability_bit_set(data, CAP_SETPCAP, 1)) {
        return -1;
    }
    for (int capability = 0; capability <= CAP_LAST_CAP; capability += 1) {
        if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_LOWER, capability, 0L, 0L) < 0
            && errno != EINVAL) {
            return -1;
        }
        if (!retained_capability(capability)) {
            if (prctl(PR_CAPBSET_DROP, capability, 0L, 0L, 0L) < 0) {
                return -1;
            }
            clear_capability_bit(data, capability);
        }
    }
    data[0].inheritable = 0U;
    data[1].inheritable = 0U;
    if (syscall(SYS_capset, &header, data) < 0) {
        return -1;
    }
    memset(data, 0, sizeof(data));
    if (syscall(SYS_capget, &header, data) < 0) {
        return -1;
    }
    for (int capability = 0; capability <= CAP_LAST_CAP; capability += 1) {
        int retained = retained_capability(capability);
        errno = 0;
        if (capability_bit_set(data, capability, 0) != retained
            || capability_bit_set(data, capability, 1) != retained
            || capability_bit_set(data, capability, 2)
            || prctl(PR_CAPBSET_READ, capability, 0L, 0L, 0L) != retained
            || prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_IS_SET, capability, 0L, 0L) != 0) {
            return -1;
        }
    }
    for (index = 0; index < sizeof(retained_capabilities) / sizeof(retained_capabilities[0]); index += 1) {
        int capability = retained_capabilities[index];
        if (!capability_bit_set(data, capability, 0)
            || !capability_bit_set(data, capability, 1)
            || prctl(PR_CAPBSET_READ, capability, 0L, 0L, 0L) != 1) {
            return -1;
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    char **clean_environment;
    static char *const child_argv[] = {
        (char *)NODE_PATH,
        (char *)SUPERVISOR_PATH,
        NULL,
    };

    (void)argv;
    (void)EXECUTOR_INIT_FALSE_REQUIRED;
    if (argc != 1) {
        fixed_error("mount_bootstrap_arguments_forbidden");
        return 64;
    }
    if (getpid() != (pid_t)1 || getuid() != (uid_t)0 || geteuid() != (uid_t)0
        || getgid() != PRIVATE_GID || getegid() != PRIVATE_GID) {
        fixed_error("mount_bootstrap_pid1_root_required");
        return 77;
    }
    if (validate_self_executable() < 0) {
        fixed_error("mount_bootstrap_self_invalid");
        return 65;
    }
    if (validate_prefixed_environment() < 0) {
        fixed_error("mount_bootstrap_environment_forbidden");
        return 78;
    }
    clean_environment = build_environment();
    if (clean_environment == NULL) {
        fixed_error("mount_bootstrap_environment_build_failed");
        return 70;
    }
    if (harden_mount(CONFIG_TARGET, 0) < 0 || harden_mount(WORKSPACE_TARGET, 1) < 0) {
        fixed_error("mount_bootstrap_mount_hardening_failed");
        return 70;
    }
    if (verify_hardened_mounts() < 0) {
        fixed_error("mount_bootstrap_mount_verification_failed");
        return 70;
    }
    if (reduce_to_launcher_capabilities() < 0) {
        fixed_error("mount_bootstrap_capability_drop_failed");
        return 70;
    }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L) < 0
        || prctl(PR_GET_NO_NEW_PRIVS, 0L, 0L, 0L, 0L) != 1) {
        fixed_error("mount_bootstrap_no_new_privs_failed");
        return 70;
    }
    (void)execve(NODE_PATH, child_argv, clean_environment);
    fixed_error("mount_bootstrap_exec_failed");
    return 71;
}
