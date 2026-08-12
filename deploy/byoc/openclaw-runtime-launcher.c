#define _GNU_SOURCE

#ifndef __linux__
#error "openclaw-runtime-launcher requires Linux"
#endif

#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <limits.h>
#include <linux/audit.h>
#include <linux/capability.h>
#include <linux/filter.h>
#include <linux/magic.h>
#include <linux/seccomp.h>
#include <stddef.h>
#include <stdint.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>

#define RUNTIME_UID ((uid_t)1200)
#define RUNTIME_GID ((gid_t)1200)
#define SOCKET_TYPE_MASK 0x0fU
#define DENIED_ERRNO EPERM

#if defined(__x86_64__)
#define EXPECTED_AUDIT_ARCH AUDIT_ARCH_X86_64
#elif defined(__aarch64__)
#define EXPECTED_AUDIT_ARCH AUDIT_ARCH_AARCH64
#else
#error "openclaw-runtime-launcher supports x86_64 and aarch64"
#endif

#ifndef SYS_close_range
#define SYS_close_range __NR_close_range
#endif

#ifndef SYS_execveat
#define SYS_execveat __NR_execveat
#endif

#define DENY_SYSCALL(number) \
    BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, (number), 0, 1), \
    BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | (DENIED_ERRNO & SECCOMP_RET_DATA))

static void fixed_error(const char *code) {
    (void)fprintf(stderr, "%s\n", code);
}

static int parse_decimal(const char *value, unsigned long *result) {
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
    *result = parsed;
    return 0;
}

static int validate_arguments(
    int argc,
    char **argv,
    int *exec_fd,
    int *cgroup_procs_fd,
    int *status_fd,
    char ***child_argv
) {
    unsigned long uid_value;
    unsigned long gid_value;
    unsigned long fd_value;
    unsigned long cgroup_fd_value;
    unsigned long status_fd_value;

    if (argc < 13
        || strcmp(argv[1], "--uid") != 0
        || strcmp(argv[3], "--gid") != 0
        || strcmp(argv[5], "--exec-fd") != 0
        || strcmp(argv[7], "--cgroup-procs-fd") != 0
        || strcmp(argv[9], "--status-fd") != 0
        || strcmp(argv[11], "--") != 0
        || argv[12][0] == '\0'
        || parse_decimal(argv[2], &uid_value) < 0
        || parse_decimal(argv[4], &gid_value) < 0
        || parse_decimal(argv[6], &fd_value) < 0
        || parse_decimal(argv[8], &cgroup_fd_value) < 0
        || parse_decimal(argv[10], &status_fd_value) < 0
        || uid_value != (unsigned long)RUNTIME_UID
        || gid_value != (unsigned long)RUNTIME_GID
        || fd_value < 3UL
        || fd_value > (unsigned long)INT_MAX
        || cgroup_fd_value < 3UL
        || cgroup_fd_value > (unsigned long)INT_MAX
        || status_fd_value < 3UL
        || status_fd_value > (unsigned long)INT_MAX
        || cgroup_fd_value == fd_value
        || status_fd_value == fd_value
        || status_fd_value == cgroup_fd_value) {
        return -1;
    }
    *exec_fd = (int)fd_value;
    *cgroup_procs_fd = (int)cgroup_fd_value;
    *status_fd = (int)status_fd_value;
    *child_argv = &argv[12];
    return 0;
}

static int validate_status_fd(int status_fd) {
    struct stat metadata;
    int descriptor_flags;
    int open_flags;

    descriptor_flags = fcntl(status_fd, F_GETFD);
    open_flags = fcntl(status_fd, F_GETFL);
    if (descriptor_flags < 0
        || open_flags < 0
        || fstat(status_fd, &metadata) < 0
        || (!S_ISFIFO(metadata.st_mode) && !S_ISSOCK(metadata.st_mode))
        || (open_flags & O_ACCMODE) == O_RDONLY) {
        return -1;
    }
    return fcntl(status_fd, F_SETFD, descriptor_flags | FD_CLOEXEC);
}

static int write_status(int status_fd, char marker) {
    ssize_t written;
    do {
        written = write(status_fd, &marker, 1U);
    } while (written < 0 && errno == EINTR);
    return written == 1 ? 0 : -1;
}

static int enter_request_cgroup(int cgroup_procs_fd) {
    char pid_text[32];
    int length;
    ssize_t written;
    struct stat metadata;
    struct statfs filesystem;

    if (fstat(cgroup_procs_fd, &metadata) < 0
        || !S_ISREG(metadata.st_mode)
        || fstatfs(cgroup_procs_fd, &filesystem) < 0
        || (unsigned long)filesystem.f_type != (unsigned long)CGROUP2_SUPER_MAGIC) {
        return -1;
    }
    length = snprintf(pid_text, sizeof(pid_text), "%ld\n", (long)getpid());
    if (length < 2 || (size_t)length >= sizeof(pid_text)) {
        return -1;
    }
    written = write(cgroup_procs_fd, pid_text, (size_t)length);
    if (written != (ssize_t)length || close(cgroup_procs_fd) < 0) {
        return -1;
    }
    return 0;
}

static int reset_signal_state(void) {
    struct sigaction action;
    sigset_t empty;
    int signal_number;

    memset(&action, 0, sizeof(action));
    action.sa_handler = SIG_DFL;
    if (sigemptyset(&action.sa_mask) < 0 || sigemptyset(&empty) < 0) {
        return -1;
    }
    for (signal_number = 1; signal_number < NSIG; signal_number += 1) {
        if (signal_number == SIGKILL || signal_number == SIGSTOP) {
            continue;
        }
        if (sigaction(signal_number, &action, NULL) < 0 && errno != EINVAL) {
            return -1;
        }
    }
    return sigprocmask(SIG_SETMASK, &empty, NULL);
}

static int validate_executable_fd(int exec_fd) {
    struct stat metadata;
    int descriptor_flags;

    descriptor_flags = fcntl(exec_fd, F_GETFD);
    if (descriptor_flags < 0
        || fstat(exec_fd, &metadata) < 0
        || !S_ISREG(metadata.st_mode)
        || (metadata.st_mode & 0111) == 0) {
        return -1;
    }
    if (fcntl(exec_fd, F_SETFD, descriptor_flags | FD_CLOEXEC) < 0) {
        return -1;
    }
    return 0;
}

static int set_limit(int resource, rlim_t value) {
    struct rlimit limit;
    limit.rlim_cur = value;
    limit.rlim_max = value;
    return setrlimit(resource, &limit);
}

static int install_resource_limits(void) {
    if (set_limit(RLIMIT_CORE, 0) < 0
        || set_limit(RLIMIT_NOFILE, 64) < 0
        || set_limit(RLIMIT_NPROC, 64) < 0
        || set_limit(RLIMIT_FSIZE, (rlim_t)1024 * 1024 * 1024) < 0
        || set_limit(RLIMIT_AS, (rlim_t)2 * 1024 * 1024 * 1024) < 0
        || set_limit(RLIMIT_CPU, 300) < 0
        || set_limit(RLIMIT_STACK, (rlim_t)64 * 1024 * 1024) < 0
        || set_limit(RLIMIT_MEMLOCK, 0) < 0) {
        return -1;
    }
    return 0;
}

static int close_non_allowlisted_fds(int exec_fd, int status_fd) {
    int lower = exec_fd < status_fd ? exec_fd : status_fd;
    int upper = exec_fd < status_fd ? status_fd : exec_fd;
    if (lower > 3
        && syscall(SYS_close_range, (unsigned int)3, (unsigned int)(lower - 1), 0U) < 0) {
        return -1;
    }
    if (lower < upper - 1
        && syscall(SYS_close_range, (unsigned int)(lower + 1), (unsigned int)(upper - 1), 0U) < 0) {
        return -1;
    }
    if (upper < INT_MAX
        && syscall(SYS_close_range, (unsigned int)(upper + 1), UINT_MAX, 0U) < 0) {
        return -1;
    }
    return 0;
}

static int clear_capabilities(void) {
    struct __user_cap_header_struct header;
    struct __user_cap_data_struct data[2];

    memset(&header, 0, sizeof(header));
    memset(data, 0, sizeof(data));
    header.version = _LINUX_CAPABILITY_VERSION_3;
    header.pid = 0;
    if (syscall(SYS_capset, &header, data) < 0) {
        return -1;
    }
    if (prctl(PR_CAP_AMBIENT, PR_CAP_AMBIENT_CLEAR_ALL, 0L, 0L, 0L) < 0) {
        return -1;
    }
    return 0;
}

static int install_seccomp_denylist(void) {
    static const struct sock_filter filter[] = {
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, arch)),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, EXPECTED_AUDIT_ARCH, 1, 0),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
#if defined(__x86_64__)
        BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, 0x40000000U, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_KILL_PROCESS),
#endif
        DENY_SYSCALL(__NR_mount),
        DENY_SYSCALL(__NR_umount2),
#ifdef __NR_pivot_root
        DENY_SYSCALL(__NR_pivot_root),
#endif
        DENY_SYSCALL(__NR_setns),
        DENY_SYSCALL(__NR_unshare),
        DENY_SYSCALL(__NR_ptrace),
        DENY_SYSCALL(__NR_bpf),
        DENY_SYSCALL(__NR_perf_event_open),
        DENY_SYSCALL(__NR_keyctl),
        DENY_SYSCALL(__NR_init_module),
        DENY_SYSCALL(__NR_finit_module),
        DENY_SYSCALL(__NR_delete_module),
#ifdef __NR_mknod
        DENY_SYSCALL(__NR_mknod),
#endif
        DENY_SYSCALL(__NR_mknodat),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, __NR_socket, 0, 6),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[0])),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, AF_PACKET, 3, 0),
        BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[1])),
        BPF_STMT(BPF_ALU | BPF_AND | BPF_K, SOCKET_TYPE_MASK),
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SOCK_RAW, 0, 1),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | (DENIED_ERRNO & SECCOMP_RET_DATA)),
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
    };
    static const struct sock_fprog program = {
        .len = (unsigned short)(sizeof(filter) / sizeof(filter[0])),
        .filter = (struct sock_filter *)filter,
    };

    if (prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) < 0) {
        return -1;
    }
    return 0;
}

static int execute_fd(int exec_fd, char **child_argv) {
    static char *const clean_environment[] = {
        (char *)"LANG=C",
        (char *)"PATH=/usr/bin:/bin",
        NULL,
    };
    int saved_errno;

    (void)syscall(SYS_execveat, exec_fd, "", child_argv, clean_environment, AT_EMPTY_PATH);
    saved_errno = errno;
    if (saved_errno == ENOSYS) {
        (void)fexecve(exec_fd, child_argv, clean_environment);
        saved_errno = errno;
    }
    errno = saved_errno;
    return -1;
}

int main(int argc, char **argv) {
    int exec_fd;
    int cgroup_procs_fd;
    int status_fd;
    char **child_argv;

    if (geteuid() != 0) {
        fixed_error("runtime_launcher_root_required");
        return 77;
    }
    if (validate_arguments(argc, argv, &exec_fd, &cgroup_procs_fd, &status_fd, &child_argv) < 0) {
        fixed_error("runtime_launcher_arguments_invalid");
        return 64;
    }
    if (validate_executable_fd(exec_fd) < 0) {
        fixed_error("runtime_launcher_exec_fd_invalid");
        return 65;
    }
    if (validate_status_fd(status_fd) < 0) {
        fixed_error("runtime_launcher_status_fd_invalid");
        return 65;
    }
    if (enter_request_cgroup(cgroup_procs_fd) < 0) {
        fixed_error("runtime_launcher_cgroup_entry_failed");
        return 70;
    }
    if (reset_signal_state() < 0) {
        fixed_error("runtime_launcher_signal_reset_failed");
        return 70;
    }
    if (setgroups(0, NULL) < 0
        || setresgid(RUNTIME_GID, RUNTIME_GID, RUNTIME_GID) < 0
        || setresuid(RUNTIME_UID, RUNTIME_UID, RUNTIME_UID) < 0) {
        fixed_error("runtime_launcher_identity_transition_failed");
        return 70;
    }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L) < 0) {
        fixed_error("runtime_launcher_no_new_privs_failed");
        return 70;
    }
    if (prctl(PR_SET_DUMPABLE, 0L, 0L, 0L, 0L) < 0) {
        fixed_error("runtime_launcher_dump_disable_failed");
        return 70;
    }
    if (install_resource_limits() < 0) {
        fixed_error("runtime_launcher_rlimit_failed");
        return 70;
    }
    if (close_non_allowlisted_fds(exec_fd, status_fd) < 0) {
        fixed_error("runtime_launcher_fd_close_failed");
        return 70;
    }
    if (clear_capabilities() < 0) {
        fixed_error("runtime_launcher_capability_clear_failed");
        return 70;
    }
    if (install_seccomp_denylist() < 0) {
        fixed_error("runtime_launcher_seccomp_failed");
        return 70;
    }
    if (write_status(status_fd, 'R') < 0) {
        fixed_error("runtime_launcher_status_write_failed");
        return 70;
    }
    (void)execute_fd(exec_fd, child_argv);
    (void)write_status(status_fd, 'E');
    fixed_error("runtime_launcher_exec_failed");
    return 71;
}
