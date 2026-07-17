"""Dependency-free transport primitives for the browser-only Relay tunnel.

The deployed Relay is deliberately not implemented here.  This module defines
the bounded envelope and replay rules used by the deterministic loopback
transport harness.  Application bytes remain opaque to the Relay and are never
included in event evidence.
"""
from __future__ import annotations

import json
import re
import socket
import struct
from collections import deque
from dataclasses import dataclass


PROTOCOL_VERSION = 1
MAX_CONTROL_BYTES = 4096
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_EVENT_COUNT = 256
MAX_REQUEST_HISTORY = 4096
MAX_REPLAY_STREAMS = 256
_LENGTHS = struct.Struct("!II")
_REFERENCE = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
_DIRECTIONS = {"console_to_host", "host_to_console"}


class RelayProtocolError(ValueError):
    """A bounded, non-secret Relay protocol failure."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RelayFrame:
    route_ref: str
    epoch: int
    message_id: int
    request_id: str
    direction: str
    payload: bytes

    def validate(self) -> None:
        if not isinstance(self.route_ref, str) or not _REFERENCE.fullmatch(self.route_ref):
            raise RelayProtocolError("invalid_route_ref")
        if not isinstance(self.request_id, str) or not _REFERENCE.fullmatch(self.request_id):
            raise RelayProtocolError("invalid_request_id")
        if not isinstance(self.direction, str) or self.direction not in _DIRECTIONS:
            raise RelayProtocolError("invalid_direction")
        if not isinstance(self.epoch, int) or isinstance(self.epoch, bool) or self.epoch < 1:
            raise RelayProtocolError("invalid_epoch")
        if not isinstance(self.message_id, int) or isinstance(self.message_id, bool) or self.message_id < 1:
            raise RelayProtocolError("invalid_message_id")
        if not isinstance(self.payload, bytes):
            raise RelayProtocolError("invalid_payload")
        if len(self.payload) > MAX_PAYLOAD_BYTES:
            raise RelayProtocolError("payload_too_large")

    def control(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "epoch": self.epoch,
            "message_id": self.message_id,
            "request_id": self.request_id,
            "route_ref": self.route_ref,
            "version": PROTOCOL_VERSION,
        }


def _read_exact(stream: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        try:
            chunk = stream.recv(remaining)
        except OSError:
            raise RelayProtocolError("read_failed") from None
        if not chunk:
            raise RelayProtocolError("unexpected_eof")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def encode_frame(frame: RelayFrame) -> bytes:
    frame.validate()
    control = json.dumps(
        frame.control(),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    if len(control) > MAX_CONTROL_BYTES:
        raise RelayProtocolError("control_too_large")
    return _LENGTHS.pack(len(control), len(frame.payload)) + control + frame.payload


def receive_frame(stream: socket.socket) -> RelayFrame:
    control_size, payload_size = _LENGTHS.unpack(_read_exact(stream, _LENGTHS.size))
    if control_size < 2 or control_size > MAX_CONTROL_BYTES:
        raise RelayProtocolError("invalid_control_size")
    if payload_size > MAX_PAYLOAD_BYTES:
        raise RelayProtocolError("payload_too_large")
    try:
        control = json.loads(_read_exact(stream, control_size).decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RelayProtocolError("invalid_control") from None
    if not isinstance(control, dict) or set(control) != {
        "direction",
        "epoch",
        "message_id",
        "request_id",
        "route_ref",
        "version",
    }:
        raise RelayProtocolError("invalid_control_shape")
    version = control.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != PROTOCOL_VERSION:
        raise RelayProtocolError("unsupported_version")
    frame = RelayFrame(
        route_ref=control.get("route_ref"),
        epoch=control.get("epoch"),
        message_id=control.get("message_id"),
        request_id=control.get("request_id"),
        direction=control.get("direction"),
        payload=_read_exact(stream, payload_size),
    )
    frame.validate()
    return frame


class ReplayWindow:
    """Enforce one monotonically increasing stream per route and direction."""

    def __init__(
        self,
        max_request_history: int = MAX_REQUEST_HISTORY,
        max_streams: int = MAX_REPLAY_STREAMS,
    ) -> None:
        if max_request_history < 1 or max_request_history > MAX_REQUEST_HISTORY:
            raise RelayProtocolError("invalid_request_history_limit")
        if max_streams < 1 or max_streams > MAX_REPLAY_STREAMS:
            raise RelayProtocolError("invalid_stream_limit")
        self._state: dict[tuple[str, str], tuple[int, int]] = {}
        self._requests: set[tuple[str, str, str]] = set()
        self._request_order: deque[tuple[str, str, str]] = deque()
        self._max_request_history = max_request_history
        self._max_streams = max_streams

    def accept(self, frame: RelayFrame) -> None:
        frame.validate()
        key = (frame.route_ref, frame.direction)
        previous = self._state.get(key)
        if previous is None:
            if len(self._state) >= self._max_streams:
                raise RelayProtocolError("stream_capacity_exceeded")
            if frame.message_id != 1:
                raise RelayProtocolError("message_gap")
        else:
            previous_epoch, previous_message_id = previous
            if frame.epoch < previous_epoch:
                raise RelayProtocolError("stale_epoch")
            if frame.epoch == previous_epoch:
                if frame.message_id <= previous_message_id:
                    raise RelayProtocolError("replayed_message")
                if frame.message_id != previous_message_id + 1:
                    raise RelayProtocolError("message_gap")
            elif frame.message_id != 1:
                raise RelayProtocolError("new_epoch_must_restart_sequence")
        request_key = (frame.route_ref, frame.direction, frame.request_id)
        if request_key in self._requests:
            raise RelayProtocolError("replayed_request")
        self._state[key] = (frame.epoch, frame.message_id)
        if len(self._request_order) >= self._max_request_history:
            self._requests.discard(self._request_order.popleft())
        self._requests.add(request_key)
        self._request_order.append(request_key)


class BoundedRelayEvents:
    """In-memory operational evidence containing no application bytes."""

    def __init__(self, max_events: int = MAX_EVENT_COUNT) -> None:
        if max_events < 1 or max_events > MAX_EVENT_COUNT:
            raise RelayProtocolError("invalid_event_limit")
        self._events: deque[dict[str, object]] = deque(maxlen=max_events)

    def record(self, frame: RelayFrame, *, status: str, error_class: str | None = None) -> None:
        event = {
            "byte_count": len(frame.payload),
            "direction": frame.direction,
            "epoch": frame.epoch,
            "message_id": frame.message_id,
            "request_id": frame.request_id,
            "route_ref": frame.route_ref,
            "status": status,
            "version": PROTOCOL_VERSION,
        }
        if error_class:
            event["error_class"] = error_class
        self._events.append(event)

    def snapshot(self) -> list[dict[str, object]]:
        return [dict(event) for event in self._events]


def relay_one_frame(
    source: socket.socket,
    destination: socket.socket,
    *,
    replay_window: ReplayWindow,
    events: BoundedRelayEvents,
) -> RelayFrame:
    """Validate and forward exactly one opaque frame with socket backpressure."""

    frame = receive_frame(source)
    try:
        replay_window.accept(frame)
    except RelayProtocolError as exc:
        events.record(frame, status="rejected", error_class=exc.code)
        raise
    try:
        destination.sendall(encode_frame(frame))
    except OSError:
        events.record(frame, status="failed", error_class="destination_unavailable")
        raise RelayProtocolError("destination_unavailable") from None
    events.record(frame, status="forwarded")
    return frame
