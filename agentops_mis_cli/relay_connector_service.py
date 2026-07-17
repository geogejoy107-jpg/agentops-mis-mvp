"""Foreground lifecycle entrypoint for the disabled-by-default Relay connector."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import ssl
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any

from agentops_mis_cli.relay_connector_supervisor import RelayConnectorSupervisor
from agentops_mis_cli.relay_epoch_store import PersistentRelayEpochStore


MAX_PRIVATE_JSON_BYTES = 16 * 1024
SERVICE_SCHEMA_VERSION = 1
_stop = threading.Event()


class RelayConnectorServiceError(RuntimeError):
    pass


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _private_directory(path: Path, *, create: bool = False) -> None:
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        metadata = path.lstat()
    except OSError as exc:
        raise RelayConnectorServiceError("private_directory_unavailable") from exc
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RelayConnectorServiceError("private_directory_invalid")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise RelayConnectorServiceError("private_directory_permissions_invalid")


def _read_private_json(path: Path) -> dict[str, Any]:
    path = _absolute(path)
    _private_directory(path.parent)
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > MAX_PRIVATE_JSON_BYTES
        ):
            raise RelayConnectorServiceError("private_json_invalid")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            payload = json.load(handle)
    except RelayConnectorServiceError:
        if "descriptor" in locals() and descriptor >= 0:
            os.close(descriptor)
        raise
    except (OSError, ValueError, TypeError) as exc:
        if "descriptor" in locals() and descriptor >= 0:
            os.close(descriptor)
        raise RelayConnectorServiceError("private_json_unreadable") from exc
    if not isinstance(payload, dict):
        raise RelayConnectorServiceError("private_json_shape_invalid")
    return payload


def _write_private_status(path: Path, payload: dict[str, Any]) -> None:
    path = _absolute(path)
    _private_directory(path.parent, create=True)
    try:
        target_metadata = path.lstat()
    except FileNotFoundError:
        target_metadata = None
    except OSError as exc:
        raise RelayConnectorServiceError("status_target_unavailable") from exc
    if target_metadata is not None and (
        path.is_symlink()
        or not stat.S_ISREG(target_metadata.st_mode)
        or target_metadata.st_uid != os.getuid()
        or stat.S_IMODE(target_metadata.st_mode) != 0o600
    ):
        raise RelayConnectorServiceError("status_target_invalid")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        handle = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _disabled_status() -> dict[str, Any]:
    return {
        "connect_attempts": 0,
        "current_epoch": None,
        "enabled": False,
        "events": [],
        "failure_code": None,
        "limitations": {
            "certificate_lifecycle": False,
            "deployed_relay": False,
            "host_lifecycle_integrated": False,
            "sni_routing": False,
            "tailscale_changed": False,
        },
        "ok": True,
        "operation": "relay_connector_service",
        "relay_tls_enabled": False,
        "state": "disabled",
        "successful_connections": 0,
        "token_omitted": True,
    }


def _failed_status(code: str) -> dict[str, Any]:
    payload = _disabled_status()
    payload.update({
        "enabled": True,
        "failure_code": code,
        "ok": False,
        "state": "failed",
    })
    return payload


def _service_status(supervisor: RelayConnectorSupervisor) -> dict[str, Any]:
    status = supervisor.status()
    return {
        "connect_attempts": status["connect_attempts"],
        "current_epoch": status["current_epoch"],
        "enabled": status["enabled"],
        "events": status["events"],
        "failure_code": status["failure_code"],
        "limitations": {
            "certificate_lifecycle": False,
            "deployed_relay": False,
            "host_lifecycle_integrated": False,
            "sni_routing": False,
            "tailscale_changed": False,
        },
        "ok": status["state"] in {
            "starting",
            "connecting",
            "connected",
            "backoff",
            "stopped",
        },
        "operation": "relay_connector_service",
        "relay_tls_enabled": status["relay_tls_enabled"],
        "state": status["state"],
        "successful_connections": status["successful_connections"],
        "token_omitted": True,
    }


def _load_enabled_configuration(config_path: Path, secrets_path: Path) -> tuple[dict[str, Any], bytes]:
    config = _read_private_json(config_path)
    if config.get("schema_version") != SERVICE_SCHEMA_VERSION:
        raise RelayConnectorServiceError("config_schema_invalid")
    enabled = config.get("enabled")
    if enabled is False:
        if set(config) != {"enabled", "schema_version"}:
            raise RelayConnectorServiceError("disabled_config_shape_invalid")
        return config, b""
    required = {
        "enabled",
        "host_tls_port",
        "relay_ca_path",
        "relay_host",
        "relay_port",
        "relay_server_hostname",
        "route",
        "schema_version",
    }
    if enabled is not True or set(config) != required:
        raise RelayConnectorServiceError("enabled_config_shape_invalid")
    if (
        not isinstance(config["relay_port"], int)
        or isinstance(config["relay_port"], bool)
        or not (1 <= config["relay_port"] <= 65535)
        or not isinstance(config["host_tls_port"], int)
        or isinstance(config["host_tls_port"], bool)
        or not (1 <= config["host_tls_port"] <= 65535)
    ):
        raise RelayConnectorServiceError("config_port_invalid")
    for key in ("relay_host", "relay_server_hostname", "route", "relay_ca_path"):
        if not isinstance(config[key], str) or not config[key]:
            raise RelayConnectorServiceError("config_value_invalid")

    secret_payload = _read_private_json(secrets_path)
    if set(secret_payload) != {"schema_version", "tunnel_key_hex"} or secret_payload.get(
        "schema_version"
    ) != SERVICE_SCHEMA_VERSION:
        raise RelayConnectorServiceError("secrets_shape_invalid")
    tunnel_key_hex = secret_payload.get("tunnel_key_hex")
    if not isinstance(tunnel_key_hex, str) or len(tunnel_key_hex) != 64:
        raise RelayConnectorServiceError("tunnel_key_invalid")
    try:
        tunnel_key = bytes.fromhex(tunnel_key_hex)
    except ValueError as exc:
        raise RelayConnectorServiceError("tunnel_key_invalid") from exc
    return config, tunnel_key


def _request_stop(_signum: int, _frame: Any) -> None:
    _stop.set()


def run_service(
    *,
    config_path: Path,
    secrets_path: Path,
    epoch_state_path: Path,
    status_path: Path,
) -> int:
    supervisor: RelayConnectorSupervisor | None = None
    try:
        config, tunnel_key = _load_enabled_configuration(config_path, secrets_path)
        if config.get("enabled") is False:
            status = _disabled_status()
            _write_private_status(status_path, status)
            print(json.dumps(status, sort_keys=True))
            return 0

        relay_context = ssl.create_default_context(cafile=config["relay_ca_path"])
        relay_context.minimum_version = ssl.TLSVersion.TLSv1_2
        identity_payload = json.dumps(
            {
                "relay_host": config["relay_host"],
                "relay_port": config["relay_port"],
                "relay_server_hostname": config["relay_server_hostname"],
                "route": config["route"],
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        epoch_store = PersistentRelayEpochStore(
            _absolute(epoch_state_path),
            connector_identity=hashlib.sha256(identity_payload + tunnel_key).digest(),
        )
        supervisor = RelayConnectorSupervisor(
            relay_address=(config["relay_host"], config["relay_port"]),
            host_tls_target=("127.0.0.1", config["host_tls_port"]),
            route=config["route"],
            key=tunnel_key,
            enabled=True,
            epoch_allocator=epoch_store,
            relay_ssl_context=relay_context,
            relay_server_hostname=config["relay_server_hostname"],
        )
        if not supervisor.start():
            raise RelayConnectorServiceError("supervisor_start_failed")

        last_status = ""
        while not _stop.wait(0.1):
            status = _service_status(supervisor)
            rendered = json.dumps(status, sort_keys=True, separators=(",", ":"))
            if rendered != last_status:
                _write_private_status(status_path, status)
                last_status = rendered
            if status["state"] == "failed":
                print(json.dumps(status, sort_keys=True))
                return 1

        supervisor.stop()
        status = _service_status(supervisor)
        _write_private_status(status_path, status)
        print(json.dumps(status, sort_keys=True))
        return 0
    except Exception:
        if supervisor is not None:
            supervisor.stop()
        status = _failed_status("service_configuration_or_runtime_failed")
        try:
            _write_private_status(status_path, status)
        except Exception:
            pass
        print(json.dumps(status, sort_keys=True))
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the AgentOps MIS Relay connector service.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--secrets", type=Path, required=True)
    parser.add_argument("--epoch-state", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    return run_service(
        config_path=args.config,
        secrets_path=args.secrets,
        epoch_state_path=args.epoch_state,
        status_path=args.status,
    )


if __name__ == "__main__":
    raise SystemExit(main())
