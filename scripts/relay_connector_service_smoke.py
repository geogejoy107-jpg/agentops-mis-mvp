#!/usr/bin/env python3
"""Exercise the Relay connector as a bounded foreground service process."""
from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import ssl
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_cli.relay_tunnel import LocalFakeRelay  # noqa: E402
from scripts.relay_tls_authenticated_tunnel_smoke import (  # noqa: E402
    HOST_HOSTNAME,
    RELAY_HOSTNAME,
    RESPONSE,
    ROUTE,
    TIMEOUT,
    TlsServerListener,
    bind_listener,
    browser_round_trip,
    generate_certificate,
    host_tls_server,
)


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def read_status(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def wait_status(path: Path, predicate: Any, timeout: float = TIMEOUT) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = read_status(path)
        if payload and predicate(payload):
            return payload
        time.sleep(0.05)
    return read_status(path)


def service_command(
    config_path: Path,
    secrets_path: Path,
    epoch_path: Path,
    status_path: Path,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "agentops_mis_cli.relay_connector_service",
        "--config",
        str(config_path),
        "--secrets",
        str(secrets_path),
        "--epoch-state",
        str(epoch_path),
        "--status",
        str(status_path),
    ]


def start_relay(
    *,
    browser_port: int,
    connector_port: int,
    context: ssl.SSLContext,
    tunnel_key: bytes,
) -> tuple[LocalFakeRelay, TlsServerListener, tuple[str, int]]:
    browser_listener = bind_listener(browser_port)
    connector_listener = TlsServerListener(bind_listener(connector_port), context)
    relay = LocalFakeRelay(
        browser_listener=browser_listener,
        connector_listener=connector_listener,
        route=ROUTE,
        key=tunnel_key,
    )
    relay.start()
    return relay, connector_listener, browser_listener.getsockname()


def main() -> int:
    openssl = shutil.which("openssl")
    if not openssl:
        print(json.dumps({"ok": False, "error": "openssl_unavailable"}, sort_keys=True))
        return 1

    failures: list[str] = []
    relay: LocalFakeRelay | None = None
    process: subprocess.Popen[str] | None = None

    with tempfile.TemporaryDirectory(prefix="agentops-relay-service-") as temporary:
        temporary_path = Path(temporary)
        service_home = temporary_path / "service"
        service_home.mkdir(mode=0o700)

        disabled_config = service_home / "disabled-config.json"
        disabled_status = service_home / "disabled-status.json"
        write_private_json(disabled_config, {"enabled": False, "schema_version": 1})
        disabled = subprocess.run(
            service_command(
                disabled_config,
                service_home / "absent-secrets.json",
                service_home / "disabled-epoch.json",
                disabled_status,
            ),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        disabled_payload = read_status(disabled_status)
        if (
            disabled.returncode != 0
            or disabled_payload.get("state") != "disabled"
            or disabled_payload.get("connect_attempts") != 0
            or disabled_payload.get("enabled") is not False
        ):
            failures.append("disabled service did not exit without network work")

        broad_status = service_home / "broad-status.json"
        broad_status.write_text("{}\n", encoding="utf-8")
        broad_status.chmod(0o644)
        broad = subprocess.run(
            service_command(
                disabled_config,
                service_home / "absent-secrets.json",
                service_home / "broad-epoch.json",
                broad_status,
            ),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if broad.returncode == 0 or stat.S_IMODE(broad_status.stat().st_mode) != 0o644:
            failures.append("broad status target was silently repaired")

        relay_certificate, relay_key = generate_certificate(
            openssl,
            temporary_path,
            prefix="relay-service",
            hostname=RELAY_HOSTNAME,
        )
        host_certificate, host_key = generate_certificate(
            openssl,
            temporary_path,
            prefix="host-service",
            hostname=HOST_HOSTNAME,
        )
        relay_server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        relay_server_context.minimum_version = ssl.TLSVersion.TLSv1_2
        relay_server_context.load_cert_chain(str(relay_certificate), str(relay_key))
        host_server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        host_server_context.minimum_version = ssl.TLSVersion.TLSv1_2
        host_server_context.load_cert_chain(str(host_certificate), str(host_key))
        browser_context = ssl.create_default_context(cafile=str(host_certificate))
        browser_context.minimum_version = ssl.TLSVersion.TLSv1_2

        browser_probe = bind_listener()
        connector_probe = bind_listener()
        host_probe = bind_listener()
        browser_port = browser_probe.getsockname()[1]
        connector_port = connector_probe.getsockname()[1]
        host_port = host_probe.getsockname()[1]
        browser_probe.close()
        connector_probe.close()
        host_probe.close()
        tunnel_key = os.urandom(32)

        enabled_config_payload = {
            "enabled": True,
            "host_tls_port": host_port,
            "relay_ca_path": str(relay_certificate),
            "relay_host": "127.0.0.1",
            "relay_port": connector_port,
            "relay_server_hostname": RELAY_HOSTNAME,
            "route": ROUTE,
            "schema_version": 1,
        }
        enabled_config = service_home / "enabled-config.json"
        write_private_json(enabled_config, enabled_config_payload)

        bad_secrets = service_home / "bad-secrets.json"
        bad_status = service_home / "bad-status.json"
        write_private_json(
            bad_secrets,
            {"schema_version": 1, "tunnel_key_hex": "not-a-valid-key"},
        )
        bad = subprocess.run(
            service_command(
                enabled_config,
                bad_secrets,
                service_home / "bad-epoch.json",
                bad_status,
            ),
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        bad_payload = read_status(bad_status)
        if (
            bad.returncode == 0
            or bad_payload.get("state") != "failed"
            or bad_payload.get("connect_attempts") != 0
            or "not-a-valid-key" in bad.stdout + bad.stderr + json.dumps(bad_payload)
        ):
            failures.append("invalid service secret did not fail closed before network")

        secrets_path = service_home / "secrets.json"
        epoch_path = service_home / "epoch.json"
        status_path = service_home / "status.json"
        write_private_json(
            secrets_path,
            {"schema_version": 1, "tunnel_key_hex": tunnel_key.hex()},
        )

        relay, tls_listener, browser_address = start_relay(
            browser_port=browser_port,
            connector_port=connector_port,
            context=relay_server_context,
            tunnel_key=tunnel_key,
        )
        first_host_listener = bind_listener(host_port)
        first_host_result: queue.Queue[dict[str, Any]] = queue.Queue()
        first_host_thread = threading.Thread(
            target=host_tls_server,
            args=(first_host_listener, host_server_context, first_host_result),
            daemon=True,
        )
        first_host_thread.start()

        process = subprocess.Popen(
            service_command(enabled_config, secrets_path, epoch_path, status_path),
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        connected = wait_status(
            status_path,
            lambda payload: payload.get("state") == "connected"
            and payload.get("successful_connections", 0) >= 1,
        )
        if connected.get("state") != "connected":
            failures.append("service did not establish the first authenticated tunnel")

        try:
            first_response, _peer, _version = browser_round_trip(browser_address, browser_context)
            if first_response != RESPONSE:
                failures.append("first service browser round trip mismatched")
        except Exception as exc:
            failures.append(f"first service browser round trip failed with {type(exc).__name__}")
        first_host_thread.join(TIMEOUT)
        if first_host_thread.is_alive() or first_host_result.get_nowait().get("error_type"):
            failures.append("first Host TLS endpoint did not close cleanly")

        relay.stop()
        relay = None
        disconnected = wait_status(
            status_path,
            lambda payload: payload.get("state") in {"backoff", "connecting"},
            timeout=4.0,
        )
        first_epoch = int(connected.get("current_epoch") or 0)
        if disconnected.get("state") not in {"backoff", "connecting"}:
            failures.append("service did not observe Relay disconnect")

        relay, replacement_tls_listener, replacement_browser_address = start_relay(
            browser_port=browser_port,
            connector_port=connector_port,
            context=relay_server_context,
            tunnel_key=tunnel_key,
        )
        second_host_listener = bind_listener(host_port)
        second_host_result: queue.Queue[dict[str, Any]] = queue.Queue()
        second_host_thread = threading.Thread(
            target=host_tls_server,
            args=(second_host_listener, host_server_context, second_host_result),
            daemon=True,
        )
        second_host_thread.start()
        reconnected = wait_status(
            status_path,
            lambda payload: payload.get("state") == "connected"
            and payload.get("successful_connections", 0) >= 2,
        )
        if (
            reconnected.get("state") != "connected"
            or int(reconnected.get("current_epoch") or 0) <= first_epoch
        ):
            failures.append("service reconnect did not use a higher persisted epoch")
        try:
            second_response, _peer, _version = browser_round_trip(
                replacement_browser_address,
                browser_context,
            )
            if second_response != RESPONSE:
                failures.append("second service browser round trip mismatched")
        except Exception as exc:
            failures.append(f"second service browser round trip failed with {type(exc).__name__}")
        second_host_thread.join(TIMEOUT)
        if second_host_thread.is_alive() or second_host_result.get_nowait().get("error_type"):
            failures.append("second Host TLS endpoint did not close cleanly")

        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        final_status = read_status(status_path)
        if (
            process.returncode != 0
            or final_status.get("state") != "stopped"
            or final_status.get("ok") is not True
        ):
            failures.append("service SIGTERM did not produce a clean stopped state")

        rendered = json.dumps(
            {
                "connected": connected,
                "disabled": disabled_payload,
                "final": final_status,
                "reconnected": reconnected,
            },
            sort_keys=True,
        ) + stdout + stderr
        forbidden = (
            tunnel_key.hex(),
            ROUTE,
            RELAY_HOSTNAME,
            HOST_HOSTNAME,
            str(temporary_path),
            str(browser_port),
            str(connector_port),
            str(host_port),
        )
        if any(value in rendered for value in forbidden):
            failures.append("service status or output exposed private configuration")
        if stat.S_IMODE(status_path.stat().st_mode) != 0o600:
            failures.append("service status file was not 0600")
        if stat.S_IMODE(epoch_path.stat().st_mode) != 0o600:
            failures.append("service epoch file was not 0600")
        if len(tls_listener.accepted_versions()) < 2 or len(
            replacement_tls_listener.accepted_versions()
        ) < 2:
            failures.append("service control/data connections did not all use Relay TLS")

        relay.stop()
        relay = None
        process = None

    if process is not None and process.poll() is None:
        process.terminate()
        process.wait(timeout=5)
    if relay is not None:
        relay.stop()

    result = {
        "crash_persistent_epoch": True,
        "deployed_relay": False,
        "disabled_by_default": True,
        "failures": failures,
        "host_lifecycle_integrated": False,
        "nested_tls_after_reconnect": not any("round trip" in item for item in failures),
        "ok": not failures,
        "operation": "relay_connector_service_smoke",
        "private_status_and_state": not any("0600" in item for item in failures),
        "service_process_lifecycle": not any("SIGTERM" in item for item in failures),
        "tailscale_changed": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
