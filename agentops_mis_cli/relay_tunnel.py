"""Bounded local fake Relay using one control socket and per-browser data sockets.

This module intentionally owns no listeners, certificates, TLS contexts, files, or
database state.  The caller supplies already-bound listeners; the Host connector
initiates every connection and may target only a literal IPv4 loopback endpoint.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import socket
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 4096
MAX_EVENTS = 64
MAX_PENDING_STREAMS = 32
MAX_CONNECTOR_HANDSHAKES = 16
MAX_REPLAY_EPOCHS = 64
IO_TIMEOUT_SECONDS = 5.0
PAIR_TIMEOUT_SECONDS = 5.0
BUFFER_BYTES = 16 * 1024
ZERO_ID = ""
HEX_ID_LENGTH = 32
_KINDS = {"register", "registered", "open", "data", "data_ready"}
_FRAME_KEYS = {
    "connection_id",
    "epoch",
    "kind",
    "mac",
    "nonce",
    "route",
    "seq",
    "version",
}


class RelayProtocolError(Exception):
    """A bounded, non-sensitive transport failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RelayFrame:
    kind: str
    route: str
    epoch: int
    seq: int
    connection_id: str = ZERO_ID
    nonce: str = ZERO_ID


def _is_hex_id(value: str) -> bool:
    return len(value) == HEX_ID_LENGTH and all(char in "0123456789abcdef" for char in value)


def _validate_frame(frame: RelayFrame) -> None:
    if not isinstance(frame.kind, str) or frame.kind not in _KINDS:
        raise RelayProtocolError("unknown_kind")
    if not isinstance(frame.route, str) or not (1 <= len(frame.route) <= 96) or not all(
        char.isascii() and (char.isalnum() or char in "-_.") for char in frame.route
    ):
        raise RelayProtocolError("invalid_route")
    if not isinstance(frame.epoch, int) or isinstance(frame.epoch, bool) or frame.epoch < 1:
        raise RelayProtocolError("invalid_epoch")
    if not isinstance(frame.seq, int) or isinstance(frame.seq, bool) or frame.seq < 1:
        raise RelayProtocolError("invalid_sequence")
    if not isinstance(frame.connection_id, str) or not isinstance(frame.nonce, str):
        raise RelayProtocolError("invalid_stream_identity")
    stream_kind = frame.kind in {"open", "data", "data_ready"}
    if stream_kind:
        if not _is_hex_id(frame.connection_id) or not _is_hex_id(frame.nonce):
            raise RelayProtocolError("invalid_stream_identity")
    elif frame.connection_id or frame.nonce:
        raise RelayProtocolError("unexpected_stream_identity")


def _unsigned_dict(frame: RelayFrame) -> dict[str, Any]:
    return {
        "connection_id": frame.connection_id,
        "epoch": frame.epoch,
        "kind": frame.kind,
        "nonce": frame.nonce,
        "route": frame.route,
        "seq": frame.seq,
        "version": PROTOCOL_VERSION,
    }


def encode_frame(frame: RelayFrame, key: bytes) -> bytes:
    """Encode one canonical authenticated control frame."""
    _validate_frame(frame)
    if len(key) < 32:
        raise RelayProtocolError("weak_tunnel_key")
    unsigned = json.dumps(
        _unsigned_dict(frame), separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    mac = hmac.new(key, unsigned, hashlib.sha256).hexdigest()
    body = json.dumps(
        {**_unsigned_dict(frame), "mac": mac},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(body) > MAX_FRAME_BYTES:
        raise RelayProtocolError("frame_too_large")
    return struct.pack("!I", len(body)) + body


def _read_exact(stream: socket.socket, size: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise RelayProtocolError("read_timeout")
        stream.settimeout(timeout)
        try:
            chunk = stream.recv(remaining)
        except socket.timeout as exc:
            raise RelayProtocolError("read_timeout") from exc
        except OSError as exc:
            raise RelayProtocolError("read_failed") from exc
        if not chunk:
            raise RelayProtocolError("unexpected_eof")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def receive_frame(
    stream: socket.socket,
    key: bytes,
    *,
    timeout_seconds: float = IO_TIMEOUT_SECONDS,
) -> RelayFrame:
    """Read and authenticate one strict bounded frame."""
    if len(key) < 32:
        raise RelayProtocolError("weak_tunnel_key")
    deadline = time.monotonic() + max(0.1, min(float(timeout_seconds), 30.0))
    size = struct.unpack("!I", _read_exact(stream, 4, deadline))[0]
    if size < 2 or size > MAX_FRAME_BYTES:
        raise RelayProtocolError("frame_size_rejected")
    body = _read_exact(stream, size, deadline)
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RelayProtocolError("invalid_json") from exc
    if not isinstance(decoded, dict) or set(decoded) != _FRAME_KEYS:
        raise RelayProtocolError("invalid_frame_shape")
    if decoded.get("version") != PROTOCOL_VERSION:
        raise RelayProtocolError("unsupported_version")
    mac = decoded.get("mac")
    if not isinstance(mac, str) or len(mac) != 64:
        raise RelayProtocolError("invalid_mac")
    unsigned_dict = {name: decoded[name] for name in decoded if name != "mac"}
    unsigned = json.dumps(unsigned_dict, separators=(",", ":"), sort_keys=True).encode("utf-8")
    expected = hmac.new(key, unsigned, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        raise RelayProtocolError("authentication_failed")
    try:
        frame = RelayFrame(
            kind=decoded["kind"],
            route=decoded["route"],
            epoch=decoded["epoch"],
            seq=decoded["seq"],
            connection_id=decoded["connection_id"],
            nonce=decoded["nonce"],
        )
    except (KeyError, TypeError) as exc:
        raise RelayProtocolError("invalid_frame_shape") from exc
    _validate_frame(frame)
    return frame


def send_frame(stream: socket.socket, frame: RelayFrame, key: bytes) -> None:
    stream.settimeout(IO_TIMEOUT_SECONDS)
    try:
        stream.sendall(encode_frame(frame, key))
    except socket.timeout as exc:
        raise RelayProtocolError("write_timeout") from exc
    except OSError as exc:
        raise RelayProtocolError("write_failed") from exc


class BoundedRelayMetadata:
    """Record only allowlisted statuses, directions, and bounded byte counts."""

    _STATUSES = {
        "accepted",
        "authenticated",
        "closed",
        "failed",
        "forwarded",
        "rejected",
        "registered",
    }
    _DIRECTIONS = {"browser_to_host", "host_to_browser", "control", "data"}

    def __init__(self) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self._lock = threading.Lock()

    def record(self, status: str, direction: str, byte_count: int = 0) -> None:
        if status not in self._STATUSES or direction not in self._DIRECTIONS:
            raise ValueError("unapproved relay metadata")
        event = {
            "byte_count": min(max(int(byte_count), 0), 1 << 30),
            "direction": direction,
            "status": status,
        }
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in self._events]


def _close_socket(stream: socket.socket | None) -> None:
    if stream is None:
        return
    try:
        stream.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        stream.close()
    except OSError:
        pass


def _pipe_direction(
    source: socket.socket,
    destination: socket.socket,
    metadata: BoundedRelayMetadata,
    direction: str,
    outcomes: list[bool | None],
    outcome_index: int,
) -> None:
    byte_count = 0
    try:
        source.settimeout(IO_TIMEOUT_SECONDS)
        destination.settimeout(IO_TIMEOUT_SECONDS)
        while True:
            chunk = source.recv(BUFFER_BYTES)
            if not chunk:
                try:
                    destination.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
                break
            destination.sendall(chunk)
            byte_count += len(chunk)
    except (OSError, socket.timeout):
        outcomes[outcome_index] = False
        metadata.record("failed", direction, byte_count)
    else:
        outcomes[outcome_index] = True
        metadata.record("forwarded", direction, byte_count)


def _forward_bidirectional(
    left: socket.socket,
    right: socket.socket,
    metadata: BoundedRelayMetadata,
) -> bool:
    outcomes: list[bool | None] = [None, None]
    threads = (
        threading.Thread(
            target=_pipe_direction,
            args=(left, right, metadata, "browser_to_host", outcomes, 0),
            daemon=True,
        ),
        threading.Thread(
            target=_pipe_direction,
            args=(right, left, metadata, "host_to_browser", outcomes, 1),
            daemon=True,
        ),
    )
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + IO_TIMEOUT_SECONDS * 2
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    _close_socket(left)
    _close_socket(right)
    for index, thread in enumerate(threads):
        if thread.is_alive() and outcomes[index] is None:
            outcomes[index] = False
            metadata.record("failed", ("browser_to_host", "host_to_browser")[index])
    return outcomes == [True, True]


@dataclass
class _PendingBrowser:
    browser: socket.socket
    nonce: str
    epoch: int
    ready: threading.Event
    data: socket.socket | None = None


class LocalFakeRelay:
    """Pair browser streams with Host-initiated data sockets on one route."""

    def __init__(
        self,
        *,
        browser_listener: socket.socket,
        connector_listener: socket.socket,
        route: str,
        key: bytes,
    ) -> None:
        _validate_frame(RelayFrame("register", route, 1, 1))
        if len(key) < 32:
            raise RelayProtocolError("weak_tunnel_key")
        self._browser_listener = browser_listener
        self._connector_listener = connector_listener
        self._route = route
        self._key = bytes(key)
        self.metadata = BoundedRelayMetadata()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._control: socket.socket | None = None
        self._control_epoch = 0
        self._control_seq = 1
        self._last_epoch = 0
        self._pending: dict[str, _PendingBrowser] = {}
        self._active_sockets: set[socket.socket] = set()
        self._reserved_data: set[tuple[int, str, str]] = set()
        self._consumed: deque[tuple[int, str, str]] = deque(maxlen=MAX_REPLAY_EPOCHS)
        self._threads: set[threading.Thread] = set()
        self._handshake_slots = threading.BoundedSemaphore(MAX_CONNECTOR_HANDSHAKES)
        self._handshake_sockets: set[socket.socket] = set()

        for listener in (browser_listener, connector_listener):
            try:
                address = listener.getsockname()
            except OSError as exc:
                raise ValueError("local fake Relay listener must be bound") from exc
            if listener.family != socket.AF_INET or address[0] != "127.0.0.1" or not (1 <= int(address[1]) <= 65535):
                raise ValueError("local fake Relay listener must use literal 127.0.0.1")

    def start(self) -> None:
        for listener in (self._browser_listener, self._connector_listener):
            listener.settimeout(0.2)
        for target in (self._accept_browsers, self._accept_connectors):
            self._spawn(target)

    def _spawn(self, target: Any, *args: Any) -> bool:
        def run() -> None:
            try:
                target(*args)
            finally:
                with self._lock:
                    self._threads.discard(threading.current_thread())

        thread = threading.Thread(target=run, daemon=True)
        with self._lock:
            if self._stop.is_set():
                return False
            self._threads.add(thread)
        thread.start()
        return True

    def _accept_browsers(self) -> None:
        while not self._stop.is_set():
            try:
                browser, _ = self._browser_listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            browser.settimeout(IO_TIMEOUT_SECONDS)
            if not self._spawn(self._handle_browser, browser):
                _close_socket(browser)

    def _accept_connectors(self) -> None:
        while not self._stop.is_set():
            try:
                connector, _ = self._connector_listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            connector.settimeout(IO_TIMEOUT_SECONDS)
            if not self._handshake_slots.acquire(blocking=False):
                self.metadata.record("rejected", "control")
                _close_socket(connector)
                continue
            with self._lock:
                if self._stop.is_set():
                    self._handshake_slots.release()
                    _close_socket(connector)
                    continue
                self._handshake_sockets.add(connector)
            if not self._spawn(self._handle_connector, connector):
                with self._lock:
                    self._handshake_sockets.discard(connector)
                self._handshake_slots.release()
                _close_socket(connector)

    def _handle_connector(self, connector: socket.socket) -> None:
        direction = "control"
        try:
            try:
                first = receive_frame(connector, self._key)
            finally:
                self._handshake_slots.release()
            direction = "data" if first.kind == "data" else "control"
            if first.route != self._route:
                raise RelayProtocolError("unknown_route")
            if first.kind == "register":
                self._register_control(connector, first)
                return
            if first.kind == "data":
                self._register_data(connector, first)
                return
            raise RelayProtocolError("unexpected_connector_kind")
        except RelayProtocolError:
            self.metadata.record("rejected", direction)
            _close_socket(connector)
        finally:
            with self._lock:
                self._handshake_sockets.discard(connector)

    def _register_control(self, connector: socket.socket, frame: RelayFrame) -> None:
        if frame.seq != 1:
            raise RelayProtocolError("replayed_sequence")
        with self._lock:
            if frame.epoch <= self._last_epoch:
                raise RelayProtocolError("replayed_epoch")
            self._last_epoch = frame.epoch
        send_frame(
            connector,
            RelayFrame("registered", self._route, frame.epoch, 1),
            self._key,
        )
        with self._lock:
            if self._stop.is_set() or frame.epoch != self._last_epoch:
                raise RelayProtocolError("registration_superseded")
            old_control = self._control
            stale_pending = [
                (connection_id, pending)
                for connection_id, pending in self._pending.items()
                if pending.epoch != frame.epoch
            ]
            for connection_id, _ in stale_pending:
                self._pending.pop(connection_id, None)
            self._control_epoch = frame.epoch
            self._control_seq = 1
            self._control = connector
        _close_socket(old_control)
        for _, pending in stale_pending:
            _close_socket(pending.browser)
            _close_socket(pending.data)
            pending.ready.set()
        self.metadata.record("registered", "control")
        try:
            connector.settimeout(0.2)
            while not self._stop.is_set():
                try:
                    unexpected = connector.recv(1)
                except socket.timeout:
                    continue
                if not unexpected:
                    break
                raise RelayProtocolError("unexpected_control_bytes")
        except OSError:
            pass
        finally:
            with self._lock:
                if self._control is connector:
                    self._control = None
            _close_socket(connector)

    def _register_data(self, connector: socket.socket, frame: RelayFrame) -> None:
        token = (frame.epoch, frame.connection_id, frame.nonce)
        with self._lock:
            if frame.epoch != self._control_epoch or self._control is None:
                raise RelayProtocolError("stale_epoch")
            if frame.seq != 1 or token in self._consumed or token in self._reserved_data:
                raise RelayProtocolError("replayed_data_connection")
            pending = self._pending.get(frame.connection_id)
            if (
                pending is None
                or pending.epoch != frame.epoch
                or pending.nonce != frame.nonce
                or pending.data is not None
            ):
                raise RelayProtocolError("unknown_stream")
            self._consumed.append(token)
            self._reserved_data.add(token)
        try:
            send_frame(
                connector,
                RelayFrame(
                    "data_ready",
                    self._route,
                    frame.epoch,
                    1,
                    frame.connection_id,
                    frame.nonce,
                ),
                self._key,
            )
            with self._lock:
                current = self._pending.get(frame.connection_id)
                if (
                    self._stop.is_set()
                    or frame.epoch != self._control_epoch
                    or self._control is None
                    or current is not pending
                    or pending.data is not None
                ):
                    raise RelayProtocolError("data_registration_superseded")
                pending.data = connector
                pending.ready.set()
        finally:
            with self._lock:
                self._reserved_data.discard(token)
        self.metadata.record("authenticated", "data")

    def _handle_browser(self, browser: socket.socket) -> None:
        connection_id = secrets.token_hex(HEX_ID_LENGTH // 2)
        nonce = secrets.token_hex(HEX_ID_LENGTH // 2)
        pending: _PendingBrowser | None = None
        data: socket.socket | None = None
        try:
            with self._lock:
                if self._control is None or len(self._pending) >= MAX_PENDING_STREAMS:
                    raise RelayProtocolError("route_unavailable")
                pending = _PendingBrowser(
                    browser=browser,
                    nonce=nonce,
                    epoch=self._control_epoch,
                    ready=threading.Event(),
                )
                self._pending[connection_id] = pending
                self._control_seq += 1
                frame = RelayFrame(
                    "open",
                    self._route,
                    self._control_epoch,
                    self._control_seq,
                    connection_id,
                    nonce,
                )
                send_frame(self._control, frame, self._key)
            self.metadata.record("accepted", "data")
            pending.ready.wait(PAIR_TIMEOUT_SECONDS)
            with self._lock:
                if self._pending.get(connection_id) is pending:
                    self._pending.pop(connection_id, None)
                data = pending.data
                if data is not None:
                    self._active_sockets.update((browser, data))
            if data is None:
                raise RelayProtocolError("data_connection_timeout")
            forwarded = _forward_bidirectional(browser, data, self.metadata)
            self.metadata.record("closed" if forwarded else "failed", "data")
        except RelayProtocolError:
            with self._lock:
                if self._pending.get(connection_id) is pending:
                    self._pending.pop(connection_id, None)
                if data is None and pending is not None:
                    data = pending.data
            self.metadata.record("rejected", "data")
            _close_socket(browser)
            _close_socket(data)
        finally:
            with self._lock:
                self._active_sockets.discard(browser)
                if data is not None:
                    self._active_sockets.discard(data)

    def has_control(self) -> bool:
        with self._lock:
            return self._control is not None

    def wait_for_control(self, timeout_seconds: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.has_control():
                return True
            time.sleep(0.01)
        return False

    def wait_for_no_control(self, timeout_seconds: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not self.has_control():
                return True
            time.sleep(0.01)
        return False

    def stop(self) -> None:
        self._stop.set()
        _close_socket(self._browser_listener)
        _close_socket(self._connector_listener)
        with self._lock:
            control = self._control
            pending = list(self._pending.values())
            handshake_sockets = list(self._handshake_sockets)
            active_sockets = list(self._active_sockets)
        _close_socket(control)
        for handshake_socket in handshake_sockets:
            _close_socket(handshake_socket)
        for active_socket in active_sockets:
            _close_socket(active_socket)
        for item in pending:
            _close_socket(item.browser)
            _close_socket(item.data)
            item.ready.set()
        deadline = time.monotonic() + 2.0
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))


class HostTunnelConnector:
    """Host-initiated control client and per-browser outbound data connector."""

    def __init__(
        self,
        *,
        relay_address: tuple[str, int],
        host_tls_target: tuple[str, int],
        route: str,
        epoch: int,
        key: bytes,
    ) -> None:
        if relay_address[0] != "127.0.0.1":
            raise ValueError("local fake Relay address must be literal 127.0.0.1")
        if host_tls_target[0] != "127.0.0.1":
            raise ValueError("Host TLS target must be literal 127.0.0.1")
        if not (1 <= int(relay_address[1]) <= 65535 and 1 <= int(host_tls_target[1]) <= 65535):
            raise ValueError("invalid TCP port")
        _validate_frame(RelayFrame("register", route, epoch, 1))
        if len(key) < 32:
            raise RelayProtocolError("weak_tunnel_key")
        self._relay_address = relay_address
        self._target = host_tls_target
        self._route = route
        self._epoch = epoch
        self._key = bytes(key)
        self.metadata = BoundedRelayMetadata()
        self._stop = threading.Event()
        self._control: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._streams: set[threading.Thread] = set()
        self._active_sockets: set[socket.socket] = set()
        self._ready = threading.Event()
        self._error = ""

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        control: socket.socket | None = None
        try:
            control = socket.create_connection(self._relay_address, timeout=IO_TIMEOUT_SECONDS)
            with self._lock:
                self._control = control
            send_frame(control, RelayFrame("register", self._route, self._epoch, 1), self._key)
            registered = receive_frame(control, self._key)
            if registered != RelayFrame("registered", self._route, self._epoch, 1):
                raise RelayProtocolError("registration_rejected")
            self.metadata.record("registered", "control")
            self._ready.set()
            expected_seq = 2
            while not self._stop.is_set():
                try:
                    control.settimeout(0.5)
                    available = control.recv(1, socket.MSG_PEEK)
                except socket.timeout:
                    continue
                except OSError as exc:
                    raise RelayProtocolError("read_failed") from exc
                if not available:
                    raise RelayProtocolError("unexpected_eof")
                opened = receive_frame(control, self._key)
                if opened.kind != "open" or opened.route != self._route or opened.epoch != self._epoch:
                    raise RelayProtocolError("invalid_open")
                if opened.seq != expected_seq:
                    raise RelayProtocolError("replayed_sequence")
                expected_seq += 1
                def run_stream(frame: RelayFrame = opened) -> None:
                    try:
                        self._open_data_stream(frame)
                    finally:
                        with self._lock:
                            self._streams.discard(threading.current_thread())

                stream = threading.Thread(target=run_stream, daemon=True)
                with self._lock:
                    if self._stop.is_set():
                        break
                    self._streams.add(stream)
                stream.start()
        except RelayProtocolError as exc:
            if exc.code not in {"read_timeout", "unexpected_eof", "read_failed"} or not self._stop.is_set():
                self._error = exc.code
        except OSError:
            if not self._stop.is_set():
                self._error = "connection_failed"
        finally:
            self._ready.set()
            with self._lock:
                if self._control is control:
                    self._control = None
            _close_socket(control)

    def _open_data_stream(self, opened: RelayFrame) -> None:
        target: socket.socket | None = None
        data: socket.socket | None = None
        try:
            target = socket.create_connection(self._target, timeout=IO_TIMEOUT_SECONDS)
            data = socket.create_connection(self._relay_address, timeout=IO_TIMEOUT_SECONDS)
            with self._lock:
                if self._stop.is_set():
                    raise RelayProtocolError("connector_stopping")
                self._active_sockets.update((target, data))
            send_frame(
                data,
                RelayFrame(
                    "data",
                    self._route,
                    self._epoch,
                    1,
                    opened.connection_id,
                    opened.nonce,
                ),
                self._key,
            )
            ready = receive_frame(data, self._key)
            if ready != RelayFrame(
                "data_ready",
                self._route,
                self._epoch,
                1,
                opened.connection_id,
                opened.nonce,
            ):
                raise RelayProtocolError("data_registration_rejected")
            self.metadata.record("authenticated", "data")
            forwarded = _forward_bidirectional(data, target, self.metadata)
            self.metadata.record("closed" if forwarded else "failed", "data")
        except (OSError, RelayProtocolError):
            self.metadata.record("rejected", "data")
            _close_socket(target)
            _close_socket(data)
        finally:
            with self._lock:
                if target is not None:
                    self._active_sockets.discard(target)
                if data is not None:
                    self._active_sockets.discard(data)

    def wait_until_ready(self, timeout_seconds: float = 5.0) -> bool:
        if not self._ready.wait(timeout_seconds):
            return False
        with self._lock:
            return not self._error and not self._stop.is_set() and self._control is not None

    @property
    def error(self) -> str:
        return self._error

    def stop(self, timeout_seconds: float = 3.0) -> None:
        deadline = time.monotonic() + max(0.0, min(float(timeout_seconds), 10.0))
        self._stop.set()
        with self._lock:
            control = self._control
            active_sockets = list(self._active_sockets)
            streams = list(self._streams)
        _close_socket(control)
        for stream_socket in active_sockets:
            _close_socket(stream_socket)
        if self._thread is not None:
            self._thread.join(max(0.0, deadline - time.monotonic()))
        for stream in streams:
            stream.join(max(0.0, deadline - time.monotonic()))
