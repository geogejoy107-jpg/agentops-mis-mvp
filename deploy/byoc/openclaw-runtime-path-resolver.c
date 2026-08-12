#define _GNU_SOURCE

#ifndef __linux__
#error "openclaw-runtime-path-resolver requires Linux"
#endif

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <linux/openat2.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef SYS_openat2
#define SYS_openat2 __NR_openat2
#endif

#define COMMON_RESOLVE_FLAGS \
    (RESOLVE_NO_SYMLINKS | RESOLVE_NO_MAGICLINKS | RESOLVE_NO_XDEV)
#define IN_ROOT_RESOLVE_FLAGS (RESOLVE_IN_ROOT | COMMON_RESOLVE_FLAGS)
#define BENEATH_RESOLVE_FLAGS (RESOLVE_BENEATH | COMMON_RESOLVE_FLAGS)
#define MAX_OPEN_RETRIES 8

enum resolver_exit_code {
    RESOLVER_OK = 0,
    RESOLVER_ARGUMENT_ERROR = 64,
    RESOLVER_ROOT_FD_REJECTED = 65,
    RESOLVER_GUEST_PATH_REJECTED = 66,
    RESOLVER_KERNEL_UNSUPPORTED = 67,
    RESOLVER_PATH_REJECTED = 68,
    RESOLVER_IDENTITY_MISMATCH = 69
};

static void fixed_result(int ok, const char *code) {
    (void)printf(
        "{\"schema\":\"agentops_openclaw_runtime_path_resolver_result_v1\","
        "\"scope\":\"resolver_primitive_only\",\"ok\":%s,\"code\":\"%s\","
        "\"linux_openat2_verified\":%s,\"resolved_fd_handoff_verified\":false,"
        "\"runtime_path_toctou_closed\":false}\n",
        ok != 0 ? "true" : "false",
        code,
        ok != 0 ? "true" : "false"
    );
}

static void success_result(const struct stat *metadata) {
    (void)printf(
        "{\"schema\":\"agentops_openclaw_runtime_path_resolver_result_v1\","
        "\"scope\":\"resolver_primitive_only\",\"ok\":true,\"code\":\"resolved\","
        "\"linux_openat2_verified\":true,\"resolved_fd_handoff_verified\":false,"
        "\"runtime_path_toctou_closed\":false,"
        "\"root_anchored\":true,\"no_symlinks\":true,\"no_magiclinks\":true,"
        "\"no_mount_crossing\":true,\"regular_file\":true,"
        "\"device\":\"%" PRIuMAX "\",\"inode\":\"%" PRIuMAX "\","
        "\"mode\":\"%" PRIuMAX "\",\"size\":\"%" PRIdMAX "\"}\n",
        (uintmax_t)metadata->st_dev,
        (uintmax_t)metadata->st_ino,
        (uintmax_t)metadata->st_mode,
        (intmax_t)metadata->st_size
    );
}

static int parse_fd(const char *value, int *result) {
    unsigned long parsed = 0;
    size_t index;

    if (value == NULL || value[0] == '\0' || (value[0] == '0' && value[1] != '\0')) {
        return -1;
    }
    for (index = 0; value[index] != '\0'; index += 1) {
        unsigned int digit;
        if (value[index] < '0' || value[index] > '9') {
            return -1;
        }
        digit = (unsigned int)(value[index] - '0');
        if (parsed > (ULONG_MAX - digit) / 10UL) {
            return -1;
        }
        parsed = parsed * 10UL + digit;
    }
    if (parsed < 3UL || parsed > (unsigned long)INT_MAX) {
        return -1;
    }
    *result = (int)parsed;
    return 0;
}

static int validate_root_fd(int root_fd) {
    struct stat metadata;

    if (fcntl(root_fd, F_GETFD) < 0
        || fstat(root_fd, &metadata) < 0
        || !S_ISDIR(metadata.st_mode)
        || metadata.st_uid != (uid_t)0
        || (metadata.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        return -1;
    }
    return 0;
}

static int validate_guest_path(const char *path) {
    const char *component;
    size_t length;

    if (path == NULL || path[0] != '/' || path[1] == '\0') {
        return -1;
    }
    length = strnlen(path, (size_t)PATH_MAX + 1U);
    if (length == 0U || length >= (size_t)PATH_MAX || path[length - 1U] == '/') {
        return -1;
    }

    component = path + 1;
    while (*component != '\0') {
        const char *separator = strchr(component, '/');
        size_t component_length = separator == NULL
            ? strlen(component)
            : (size_t)(separator - component);
        if (component_length == 0U
            || (component_length == 1U && component[0] == '.')
            || (component_length == 2U && component[0] == '.' && component[1] == '.')) {
            return -1;
        }
        if (separator == NULL) {
            break;
        }
        component = separator + 1;
    }
    return 0;
}

static int guarded_openat2(int root_fd, const char *path, uint64_t resolve_flags) {
    struct open_how how;
    int attempt;

    memset(&how, 0, sizeof(how));
    how.flags = (uint64_t)(O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    how.resolve = resolve_flags;
    for (attempt = 0; attempt < MAX_OPEN_RETRIES; attempt += 1) {
        int opened_fd = (int)syscall(SYS_openat2, root_fd, path, &how, sizeof(how));
        if (opened_fd >= 0 || errno != EAGAIN) {
            return opened_fd;
        }
    }
    errno = EAGAIN;
    return -1;
}

static int kernel_support_failure(int error_number) {
    return error_number == ENOSYS || error_number == E2BIG || error_number == EINVAL;
}

int main(int argc, char **argv) {
    struct stat in_root_metadata;
    struct stat beneath_metadata;
    const char *guest_path;
    int root_fd;
    int in_root_fd;
    int beneath_fd;
    int first_error;

    if (geteuid() != (uid_t)0) {
        fixed_result(0, "root_identity_required");
        return RESOLVER_ROOT_FD_REJECTED;
    }
    if (argc != 5
        || strcmp(argv[1], "--root-fd") != 0
        || strcmp(argv[3], "--guest-path") != 0
        || parse_fd(argv[2], &root_fd) < 0) {
        fixed_result(0, "arguments_rejected");
        return RESOLVER_ARGUMENT_ERROR;
    }
    guest_path = argv[4];
    if (validate_root_fd(root_fd) < 0) {
        fixed_result(0, "root_fd_rejected");
        return RESOLVER_ROOT_FD_REJECTED;
    }
    if (validate_guest_path(guest_path) < 0) {
        fixed_result(0, "guest_path_rejected");
        return RESOLVER_GUEST_PATH_REJECTED;
    }

    /* Linux rejects RESOLVE_IN_ROOT and RESOLVE_BENEATH in one lookup. */
    in_root_fd = guarded_openat2(root_fd, guest_path, IN_ROOT_RESOLVE_FLAGS);
    if (in_root_fd < 0) {
        first_error = errno;
        fixed_result(0, kernel_support_failure(first_error)
            ? "openat2_kernel_unsupported"
            : "path_resolution_rejected");
        return kernel_support_failure(first_error)
            ? RESOLVER_KERNEL_UNSUPPORTED
            : RESOLVER_PATH_REJECTED;
    }
    beneath_fd = guarded_openat2(root_fd, guest_path + 1, BENEATH_RESOLVE_FLAGS);
    if (beneath_fd < 0) {
        first_error = errno;
        (void)close(in_root_fd);
        fixed_result(0, kernel_support_failure(first_error)
            ? "openat2_kernel_unsupported"
            : "path_resolution_rejected");
        return kernel_support_failure(first_error)
            ? RESOLVER_KERNEL_UNSUPPORTED
            : RESOLVER_PATH_REJECTED;
    }

    if (fstat(in_root_fd, &in_root_metadata) < 0
        || fstat(beneath_fd, &beneath_metadata) < 0
        || !S_ISREG(in_root_metadata.st_mode)
        || !S_ISREG(beneath_metadata.st_mode)
        || in_root_metadata.st_dev != beneath_metadata.st_dev
        || in_root_metadata.st_ino != beneath_metadata.st_ino) {
        (void)close(beneath_fd);
        (void)close(in_root_fd);
        fixed_result(0, "resolved_identity_rejected");
        return RESOLVER_IDENTITY_MISMATCH;
    }

    if (close(beneath_fd) < 0 || close(in_root_fd) < 0) {
        fixed_result(0, "resolved_fd_close_failed");
        return RESOLVER_IDENTITY_MISMATCH;
    }
    success_result(&in_root_metadata);
    return RESOLVER_OK;
}
