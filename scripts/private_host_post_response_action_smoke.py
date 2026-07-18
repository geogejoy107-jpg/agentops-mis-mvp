#!/usr/bin/env python3
"""Prove restart actions can run only after an accepted JSON response flushes."""
from __future__ import annotations

import json
import io
import sys
from contextlib import redirect_stderr
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import Handler, private_host_relay_public_payload  # noqa: E402


class OrderedWriter:
    def __init__(self, events: list[str], *, fail_write: bool = False) -> None:
        self.events = events
        self.fail_write = fail_write
        self.payload = b""

    def write(self, payload: bytes) -> None:
        self.events.append("body_write")
        if self.fail_write:
            raise BrokenPipeError("fixture_write_failed")
        self.payload += payload

    def flush(self) -> None:
        self.events.append("body_flush")


class FakeHandler:
    send_json = Handler.send_json

    def __init__(self, events: list[str], *, fail_write: bool = False) -> None:
        self.events = events
        self.wfile = OrderedWriter(events, fail_write=fail_write)
        self.headers: list[tuple[str, str]] = []
        self.close_connection = False

    def send_response(self, status: int) -> None:
        self.events.append(f"status:{status}")

    def send_header(self, name: str, value: str) -> None:
        self.headers.append((name, value))

    def end_headers(self) -> None:
        self.events.append("headers_complete")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    success_events: list[str] = []
    success = FakeHandler(success_events)
    success.send_json(
        {"ok": True, "state": "restart_scheduled", "sensitive_values_omitted": True},
        202,
        after_send=lambda: success_events.append("restart_request"),
        on_send_error=lambda: success_events.append("rollback"),
    )
    require(
        success_events == [
            "status:202",
            "headers_complete",
            "body_write",
            "body_flush",
            "restart_request",
        ],
        f"post-response action order changed: {success_events}",
        failures,
    )
    require(success.close_connection is True, "accepted response did not close the connection", failures)
    require(("Connection", "close") in success.headers, "accepted response omitted Connection: close", failures)
    require(json.loads(success.wfile.payload).get("state") == "restart_scheduled", "response body was incomplete", failures)

    failure_events: list[str] = []
    broken = FakeHandler(failure_events, fail_write=True)
    try:
        broken.send_json(
            {"ok": True},
            202,
            after_send=lambda: failure_events.append("restart_request"),
            on_send_error=lambda: failure_events.append("rollback"),
        )
    except BrokenPipeError:
        pass
    else:
        failures.append("broken response did not propagate the write failure")
    require("rollback" in failure_events, "broken response did not invoke rollback", failures)
    require("restart_request" not in failure_events, "broken response requested a restart", failures)
    require("body_flush" not in failure_events, "broken response claimed a flush", failures)

    callback_events: list[str] = []
    callback_failure = FakeHandler(callback_events)
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        callback_failure.send_json(
            {"ok": True},
            202,
            after_send=lambda: (_ for _ in ()).throw(RuntimeError("private_fixture_value")),
        )
    require(callback_failure.close_connection is True, "callback failure reopened the response", failures)
    require("post-response action failed" in stderr.getvalue(), "callback failure omitted bounded operator notice", failures)
    require("private_fixture_value" not in stderr.getvalue(), "callback failure leaked exception detail", failures)

    projected = private_host_relay_public_payload(
        {
            "ok": True,
            "state": "restart_scheduled",
            "action": "enable",
            "restart_required": True,
            "restart_pending": True,
            "rollback_armed": True,
            "private_receipt": {"original_config": "private_fixture_value"},
        }
    )
    require(projected.get("state") == "restart_scheduled", "restart state was flattened", failures)
    require(projected.get("restart_pending") is True, "restart pending flag was omitted", failures)
    require(projected.get("rollback_armed") is True, "rollback armed flag was omitted", failures)
    require(projected.get("remote_ready") is False, "restart response claimed remote readiness", failures)
    require(projected.get("tailscale_changed") is False, "restart response claimed a Tailscale mutation", failures)
    require(projected.get("workers_affected") is False, "restart response claimed Worker mutation", failures)
    require("private_receipt" not in projected, "private restart receipt entered the public response", failures)
    require("private_fixture_value" not in json.dumps(projected), "private restart material leaked", failures)

    result = {
        "ok": not failures,
        "failures": failures,
        "accepted_status": 202,
        "flush_precedes_restart_request": True,
        "broken_response_blocks_restart": True,
        "callback_failure_keeps_single_response": True,
        "connection_close_for_restart": True,
        "bounded_restart_projection": True,
        "network_used": False,
        "installed_host_mutated": False,
        "sensitive_values_omitted": True,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
