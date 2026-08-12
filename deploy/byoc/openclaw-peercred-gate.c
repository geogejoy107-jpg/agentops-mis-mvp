#define _GNU_SOURCE

#ifndef __linux__
#error "openclaw-peercred-gate requires Linux SO_PEERCRED"
#endif

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#define RELAY_BUFFER_BYTES (64U * 1024U)
#define CONNECT_TIMEOUT_MS 5000
#define SESSION_TIMEOUT_MS (5 * 60 * 1000)
#define POLL_SLICE_MS 1000
#define LISTEN_BACKLOG 8

static volatile sig_atomic_t stopping = 0;
static int signal_write_fd = -1;

struct buffer {
    unsigned char data[RELAY_BUFFER_BYTES];
    size_t offset;
    size_t length;
};

struct relay_direction {
    int source_fd;
    int destination_fd;
    struct buffer buffer;
    bool source_eof;
    bool destination_shutdown;
};

struct socket_identity {
    dev_t device;
    ino_t inode;
    uid_t uid;
    gid_t gid;
    mode_t mode;
};

static void fixed_error(const char *code) {
    (void)fprintf(stderr, "%s\n", code);
}

static void handle_signal(int signal_number) {
    unsigned char byte = (unsigned char)signal_number;
    ssize_t written;
    stopping = 1;
    if (signal_write_fd >= 0) {
        written = write(signal_write_fd, &byte, sizeof(byte));
        (void)written;
    }
}

static bool valid_absolute_socket_path(const char *path) {
    size_t length;
    size_t component_start;
    size_t index;
    if (path == NULL || path[0] != '/') {
        return false;
    }
    length = strlen(path);
    if (length < 2 || length >= sizeof(((struct sockaddr_un *)0)->sun_path)) {
        return false;
    }
    if (path[length - 1] == '/') {
        return false;
    }
    component_start = 1;
    for (index = 1; index <= length; index += 1) {
        unsigned char byte = (unsigned char)path[index];
        if (index < length && (byte < 0x21U || byte > 0x7eU || byte == '\\')) {
            return false;
        }
        if (index == length || path[index] == '/') {
            size_t component_length = index - component_start;
            if (component_length == 0
                || (component_length == 1 && path[component_start] == '.')
                || (component_length == 2
                    && path[component_start] == '.'
                    && path[component_start + 1] == '.')) {
                return false;
            }
            component_start = index + 1;
        }
    }
    return true;
}

static int parse_uid(const char *value, uid_t *uid) {
    unsigned long long parsed = 0;
    size_t index;
    if (value == NULL || value[0] == '\0') {
        return -1;
    }
    if (value[0] == '0' && value[1] != '\0') {
        return -1;
    }
    for (index = 0; value[index] != '\0'; index += 1) {
        unsigned int digit;
        if (value[index] < '0' || value[index] > '9') {
            return -1;
        }
        digit = (unsigned int)(value[index] - '0');
        if (parsed > (ULLONG_MAX - digit) / 10ULL) {
            return -1;
        }
        parsed = parsed * 10ULL + digit;
    }
    *uid = (uid_t)parsed;
    if ((unsigned long long)*uid != parsed) {
        return -1;
    }
    return 0;
}

static int parse_gid(const char *value, gid_t *gid) {
    uid_t parsed;
    if (parse_uid(value, &parsed) < 0) {
        return -1;
    }
    *gid = (gid_t)parsed;
    if ((uid_t)*gid != parsed) {
        return -1;
    }
    return 0;
}

static int parent_path(const char *path, char *parent, size_t parent_size) {
    const char *separator = strrchr(path, '/');
    size_t length;
    if (separator == NULL || separator == path) {
        if (parent_size < 2) {
            return -1;
        }
        parent[0] = '/';
        parent[1] = '\0';
        return 0;
    }
    length = (size_t)(separator - path);
    if (length + 1 > parent_size) {
        return -1;
    }
    (void)memcpy(parent, path, length);
    parent[length] = '\0';
    return 0;
}

static int verify_listen_parent(const char *path, uid_t uid, gid_t gid) {
    char parent[sizeof(((struct sockaddr_un *)0)->sun_path)];
    struct stat metadata;
    if (parent_path(path, parent, sizeof(parent)) < 0
        || lstat(parent, &metadata) < 0
        || !S_ISDIR(metadata.st_mode)
        || metadata.st_uid != uid
        || metadata.st_gid != gid
        || (metadata.st_mode & 0777) != 0750) {
        return -1;
    }
    return 0;
}

static int inspect_upstream_socket(const char *path,
                                   const struct socket_identity *expected,
                                   struct socket_identity *observed) {
    struct stat metadata;
    if (lstat(path, &metadata) < 0
        || !S_ISSOCK(metadata.st_mode)
        || (metadata.st_mode & 0777) != 0660) {
        return -1;
    }
    observed->device = metadata.st_dev;
    observed->inode = metadata.st_ino;
    observed->uid = metadata.st_uid;
    observed->gid = metadata.st_gid;
    observed->mode = metadata.st_mode & 0777;
    if (expected != NULL
        && (observed->device != expected->device
            || observed->inode != expected->inode
            || observed->uid != expected->uid
            || observed->gid != expected->gid
            || observed->mode != expected->mode)) {
        return -1;
    }
    return 0;
}

static void fill_unix_address(struct sockaddr_un *address, const char *path) {
    memset(address, 0, sizeof(*address));
    address->sun_family = AF_UNIX;
    (void)memcpy(address->sun_path, path, strlen(path) + 1);
}

static int monotonic_milliseconds(int64_t *value) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
        return -1;
    }
    *value = (int64_t)now.tv_sec * 1000LL + (int64_t)now.tv_nsec / 1000000LL;
    return 0;
}

static void drain_signal_pipe(int fd) {
    unsigned char bytes[32];
    while (read(fd, bytes, sizeof(bytes)) > 0) {
    }
}

static int connect_upstream(const char *path,
                            const struct socket_identity *expected_identity,
                            int signal_fd) {
    struct sockaddr_un address;
    struct pollfd descriptors[2];
    int socket_fd;
    int connection_error = 0;
    socklen_t error_length = sizeof(connection_error);
    int poll_result;

    struct socket_identity observed;
    if (inspect_upstream_socket(path, expected_identity, &observed) < 0) {
        return -1;
    }
    socket_fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (socket_fd < 0) {
        return -1;
    }
    fill_unix_address(&address, path);
    if (connect(socket_fd, (struct sockaddr *)&address, sizeof(address)) == 0) {
        if (inspect_upstream_socket(path, expected_identity, &observed) < 0) {
            (void)close(socket_fd);
            return -1;
        }
        return socket_fd;
    }
    if (errno != EINPROGRESS) {
        (void)close(socket_fd);
        return -1;
    }
    descriptors[0].fd = signal_fd;
    descriptors[0].events = POLLIN;
    descriptors[0].revents = 0;
    descriptors[1].fd = socket_fd;
    descriptors[1].events = POLLOUT;
    descriptors[1].revents = 0;
    do {
        poll_result = poll(descriptors, 2, CONNECT_TIMEOUT_MS);
    } while (poll_result < 0 && errno == EINTR && !stopping);
    if (poll_result <= 0 || stopping || (descriptors[0].revents & POLLIN) != 0) {
        (void)close(socket_fd);
        return -1;
    }
    if (getsockopt(socket_fd, SOL_SOCKET, SO_ERROR, &connection_error, &error_length) < 0
        || connection_error != 0) {
        (void)close(socket_fd);
        return -1;
    }
    if (inspect_upstream_socket(path, expected_identity, &observed) < 0) {
        (void)close(socket_fd);
        return -1;
    }
    return socket_fd;
}

static int read_direction(struct relay_direction *direction) {
    ssize_t received;
    size_t available;
    if (direction->source_eof || direction->buffer.length == RELAY_BUFFER_BYTES) {
        return 0;
    }
    if (direction->buffer.offset > 0
        && direction->buffer.offset + direction->buffer.length == RELAY_BUFFER_BYTES) {
        memmove(direction->buffer.data,
                direction->buffer.data + direction->buffer.offset,
                direction->buffer.length);
        direction->buffer.offset = 0;
    }
    available = RELAY_BUFFER_BYTES - direction->buffer.offset - direction->buffer.length;
    received = recv(direction->source_fd,
                    direction->buffer.data + direction->buffer.offset + direction->buffer.length,
                    available,
                    0);
    if (received > 0) {
        direction->buffer.length += (size_t)received;
        return 0;
    }
    if (received == 0) {
        direction->source_eof = true;
        return 0;
    }
    if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
        return 0;
    }
    return -1;
}

static int write_direction(struct relay_direction *direction) {
    ssize_t written;
    if (direction->buffer.length == 0) {
        return 0;
    }
    written = send(direction->destination_fd,
                   direction->buffer.data + direction->buffer.offset,
                   direction->buffer.length,
                   MSG_NOSIGNAL);
    if (written > 0) {
        direction->buffer.offset += (size_t)written;
        direction->buffer.length -= (size_t)written;
        if (direction->buffer.length == 0) {
            direction->buffer.offset = 0;
        }
        return 0;
    }
    if (written < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) {
        return 0;
    }
    return -1;
}

static int propagate_half_close(struct relay_direction *direction) {
    if (direction->source_eof
        && direction->buffer.length == 0
        && !direction->destination_shutdown) {
        if (shutdown(direction->destination_fd, SHUT_WR) < 0
            && errno != ENOTCONN && errno != EPIPE) {
            return -1;
        }
        direction->destination_shutdown = true;
    }
    return 0;
}

static int relay_connection(int client_fd, int upstream_fd, int signal_fd) {
    struct relay_direction client_to_upstream;
    struct relay_direction upstream_to_client;
    int64_t started;
    int64_t now;

    memset(&client_to_upstream, 0, sizeof(client_to_upstream));
    memset(&upstream_to_client, 0, sizeof(upstream_to_client));
    client_to_upstream.source_fd = client_fd;
    client_to_upstream.destination_fd = upstream_fd;
    upstream_to_client.source_fd = upstream_fd;
    upstream_to_client.destination_fd = client_fd;
    if (monotonic_milliseconds(&started) < 0) {
        return -1;
    }

    while (!stopping) {
        struct pollfd descriptors[3];
        short client_events = 0;
        short upstream_events = 0;
        int poll_result;

        if (!client_to_upstream.source_eof
            && client_to_upstream.buffer.length < RELAY_BUFFER_BYTES) {
            client_events |= POLLIN;
        }
        if (upstream_to_client.buffer.length > 0) {
            client_events |= POLLOUT;
        }
        if (!upstream_to_client.source_eof
            && upstream_to_client.buffer.length < RELAY_BUFFER_BYTES) {
            upstream_events |= POLLIN;
        }
        if (client_to_upstream.buffer.length > 0) {
            upstream_events |= POLLOUT;
        }
        descriptors[0] = (struct pollfd){ .fd = signal_fd, .events = POLLIN, .revents = 0 };
        descriptors[1] = (struct pollfd){ .fd = client_fd, .events = client_events, .revents = 0 };
        descriptors[2] = (struct pollfd){ .fd = upstream_fd, .events = upstream_events, .revents = 0 };
        do {
            poll_result = poll(descriptors, 3, POLL_SLICE_MS);
        } while (poll_result < 0 && errno == EINTR && !stopping);
        if (poll_result < 0) {
            return -1;
        }
        if (stopping || (descriptors[0].revents & POLLIN) != 0) {
            drain_signal_pipe(signal_fd);
            return 0;
        }
        if (monotonic_milliseconds(&now) < 0 || now - started >= SESSION_TIMEOUT_MS) {
            return -1;
        }
        if ((descriptors[1].revents & (POLLERR | POLLNVAL)) != 0
            || (descriptors[2].revents & (POLLERR | POLLNVAL)) != 0) {
            return 0;
        }
        if ((descriptors[1].revents & (POLLIN | POLLHUP)) != 0
            && read_direction(&client_to_upstream) < 0) {
            return 0;
        }
        if ((descriptors[2].revents & (POLLIN | POLLHUP)) != 0
            && read_direction(&upstream_to_client) < 0) {
            return 0;
        }
        if ((descriptors[2].revents & POLLOUT) != 0
            && write_direction(&client_to_upstream) < 0) {
            return 0;
        }
        if ((descriptors[1].revents & POLLOUT) != 0
            && write_direction(&upstream_to_client) < 0) {
            return 0;
        }
        if (propagate_half_close(&client_to_upstream) < 0
            || propagate_half_close(&upstream_to_client) < 0) {
            return 0;
        }
        if (client_to_upstream.destination_shutdown
            && upstream_to_client.destination_shutdown) {
            return 0;
        }
    }
    return 0;
}

static int create_listener(const char *path,
                           gid_t socket_gid,
                           struct stat *identity) {
    struct sockaddr_un address;
    struct stat existing;
    int listener;
    mode_t previous_mask;

    if (lstat(path, &existing) == 0 || errno != ENOENT) {
        return -1;
    }
    listener = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (listener < 0) {
        return -1;
    }
    fill_unix_address(&address, path);
    previous_mask = umask(0777);
    if (bind(listener, (struct sockaddr *)&address, sizeof(address)) < 0) {
        (void)umask(previous_mask);
        (void)close(listener);
        return -1;
    }
    (void)umask(previous_mask);
    if (chown(path, getuid(), socket_gid) < 0
        || chmod(path, 0660) < 0
        || lstat(path, identity) < 0
        || !S_ISSOCK(identity->st_mode)
        || identity->st_uid != getuid()
        || identity->st_gid != socket_gid
        || (identity->st_mode & 0777) != 0660
        || listen(listener, LISTEN_BACKLOG) < 0) {
        (void)close(listener);
        (void)unlink(path);
        return -1;
    }
    return listener;
}

static void unlink_listener_if_owned(const char *path, const struct stat *identity) {
    struct stat current;
    if (lstat(path, &current) == 0
        && S_ISSOCK(current.st_mode)
        && current.st_dev == identity->st_dev
        && current.st_ino == identity->st_ino) {
        (void)unlink(path);
    }
}

static int install_signal_handlers(int pipe_fds[2]) {
    struct sigaction action;
    if (pipe2(pipe_fds, O_NONBLOCK | O_CLOEXEC) < 0) {
        return -1;
    }
    memset(&action, 0, sizeof(action));
    action.sa_handler = handle_signal;
    (void)sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) < 0
        || sigaction(SIGTERM, &action, NULL) < 0
        || sigaction(SIGHUP, &action, NULL) < 0) {
        (void)close(pipe_fds[0]);
        (void)close(pipe_fds[1]);
        return -1;
    }
    signal_write_fd = pipe_fds[1];
    return 0;
}

int main(int argc, char **argv) {
    const char *listen_path;
    const char *upstream_path;
    uid_t expected_uid;
    gid_t listen_gid;
    int signal_pipe[2] = { -1, -1 };
    int listener = -1;
    struct stat listener_identity;
    struct socket_identity upstream_identity;
    int exit_code = 0;

    if (argc != 9
        || strcmp(argv[1], "--listen") != 0
        || strcmp(argv[3], "--upstream") != 0
        || strcmp(argv[5], "--expected-uid") != 0
        || strcmp(argv[7], "--listen-gid") != 0
        || !valid_absolute_socket_path(argv[2])
        || !valid_absolute_socket_path(argv[4])
        || strcmp(argv[2], argv[4]) == 0
        || parse_uid(argv[6], &expected_uid) < 0
        || parse_gid(argv[8], &listen_gid) < 0) {
        fixed_error("peercred_gate_arguments_invalid");
        return 64;
    }
    listen_path = argv[2];
    upstream_path = argv[4];
    if (verify_listen_parent(listen_path, getuid(), listen_gid) < 0) {
        fixed_error("peercred_gate_listen_parent_invalid");
        return 78;
    }
    if (inspect_upstream_socket(upstream_path, NULL, &upstream_identity) < 0) {
        fixed_error("peercred_gate_upstream_invalid");
        return 78;
    }
    if (install_signal_handlers(signal_pipe) < 0) {
        fixed_error("peercred_gate_signal_setup_failed");
        return 70;
    }
    listener = create_listener(
        listen_path,
        listen_gid,
        &listener_identity
    );
    if (listener < 0) {
        fixed_error("peercred_gate_listen_failed");
        exit_code = 78;
        goto cleanup;
    }

    while (!stopping) {
        struct pollfd descriptors[2];
        int poll_result;
        int client_fd;
        struct ucred peer;
        socklen_t peer_length = sizeof(peer);
        int upstream_fd;

        descriptors[0] = (struct pollfd){ .fd = signal_pipe[0], .events = POLLIN, .revents = 0 };
        descriptors[1] = (struct pollfd){ .fd = listener, .events = POLLIN, .revents = 0 };
        do {
            poll_result = poll(descriptors, 2, -1);
        } while (poll_result < 0 && errno == EINTR && !stopping);
        if (stopping) {
            drain_signal_pipe(signal_pipe[0]);
            break;
        }
        if (poll_result < 0) {
            fixed_error("peercred_gate_poll_failed");
            exit_code = 70;
            break;
        }
        if ((descriptors[0].revents & POLLIN) != 0) {
            drain_signal_pipe(signal_pipe[0]);
            break;
        }
        if ((descriptors[1].revents & POLLIN) == 0) {
            continue;
        }
        client_fd = accept4(listener, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
        if (client_fd < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
                continue;
            }
            fixed_error("peercred_gate_accept_failed");
            exit_code = 70;
            break;
        }
        if (getsockopt(client_fd, SOL_SOCKET, SO_PEERCRED, &peer, &peer_length) < 0
            || peer_length != sizeof(peer)
            || peer.uid != expected_uid) {
            (void)close(client_fd);
            continue;
        }
        upstream_fd = connect_upstream(upstream_path, &upstream_identity, signal_pipe[0]);
        if (upstream_fd < 0) {
            (void)close(client_fd);
            if (stopping) {
                break;
            }
            continue;
        }
        (void)relay_connection(client_fd, upstream_fd, signal_pipe[0]);
        (void)shutdown(client_fd, SHUT_RDWR);
        (void)shutdown(upstream_fd, SHUT_RDWR);
        (void)close(client_fd);
        (void)close(upstream_fd);
    }

cleanup:
    if (listener >= 0) {
        (void)close(listener);
        unlink_listener_if_owned(listen_path, &listener_identity);
    }
    signal_write_fd = -1;
    if (signal_pipe[0] >= 0) {
        (void)close(signal_pipe[0]);
    }
    if (signal_pipe[1] >= 0) {
        (void)close(signal_pipe[1]);
    }
    return exit_code;
}
