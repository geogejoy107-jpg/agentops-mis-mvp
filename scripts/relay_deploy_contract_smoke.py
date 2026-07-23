#!/usr/bin/env python3
"""Verify the static, credential-free Relay packaging contract."""
from __future__ import annotations

import ast
import configparser
import importlib.util
import json
import re
import shlex
import tarfile
import tempfile
import zipfile
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
BACKEND = ROOT / "agentops_mis_cli" / "_build_backend.py"
SYSTEMD_UNIT = ROOT / "packaging" / "relay" / "systemd" / "agentops-mis-relay.service"
CONFIG_EXAMPLE = ROOT / "packaging" / "relay" / "config.example.json"
ACCEPTANCE = ROOT / "docs" / "LOCAL_RELAY_DEPLOY_CONTRACT_ACCEPTANCE.md"
ENTRYPOINT_NAME = "agentops-relay"
ENTRYPOINT_TARGET = "agentops_mis_cli.relay_daemon:main"
EXPECTED_EXEC_START = [
    "/usr/local/bin/agentops-relay",
    "serve",
    "--config",
    "/etc/agentops-mis-relay/config.json",
]
EXPECTED_EXEC_START_PRE = [
    "/usr/local/bin/agentops-relay",
    "check",
    "--config",
    "/etc/agentops-mis-relay/config.json",
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def project_scripts(payload: str) -> dict[str, str]:
    scripts: dict[str, str] = {}
    active = False
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            active = line == "[project.scripts]"
            continue
        if not active or "=" not in line:
            continue
        name, raw_value = line.split("=", 1)
        value = ast.literal_eval(raw_value.strip())
        if not isinstance(value, str):
            raise ValueError("project script target must be a string")
        scripts[name.strip()] = value
    return scripts


def load_backend() -> ModuleType:
    spec = importlib.util.spec_from_file_location("agentops_mis_build_backend", BACKEND)
    if spec is None or spec.loader is None:
        raise RuntimeError("build backend is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry_points(payload: str) -> dict[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string(payload)
    return dict(parser.items("console_scripts")) if parser.has_section("console_scripts") else {}


def unit_sections(payload: str) -> dict[str, dict[str, list[str]]]:
    sections: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] | None = None
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
            continue
        if current is None or "=" not in line:
            raise ValueError("invalid systemd unit syntax")
        name, value = line.split("=", 1)
        current.setdefault(name, []).append(value)
    return sections


def one(sections: dict[str, dict[str, list[str]]], section: str, name: str) -> str:
    values = sections.get(section, {}).get(name, [])
    return values[0] if len(values) == 1 else ""


def main() -> int:
    failures: list[str] = []
    pyproject_scripts: dict[str, str] = {}
    backend_scripts: dict[str, str] = {}
    wheel_scripts: dict[str, str] = {}
    wheel_has_unit = False
    sdist_has_unit = False
    sdist_has_config_example = False
    sdist_has_acceptance = False
    unit_payload = ""
    sections: dict[str, dict[str, list[str]]] = {}
    unit_contains_forbidden_material = False

    try:
        pyproject_scripts = project_scripts(PYPROJECT.read_text(encoding="utf-8"))
    except Exception:
        failures.append("pyproject scripts could not be parsed")

    try:
        backend = load_backend()
        backend_scripts = entry_points(backend._entry_points())
        with tempfile.TemporaryDirectory(prefix="agentops-relay-deploy-contract-") as temporary:
            output = Path(temporary)
            wheel_name = backend.build_wheel(str(output))
            with zipfile.ZipFile(output / wheel_name) as wheel:
                names = wheel.namelist()
                entry_name = next(
                    (name for name in names if name.endswith(".dist-info/entry_points.txt")),
                    "",
                )
                if entry_name:
                    wheel_scripts = entry_points(wheel.read(entry_name).decode("utf-8"))
                wheel_has_unit = any(name.endswith("/agentops-mis-relay.service") for name in names)

            sdist_name = backend.build_sdist(str(output))
            with tarfile.open(output / sdist_name, "r:gz") as source:
                names = source.getnames()
                sdist_has_unit = any(
                    name.endswith("/packaging/relay/systemd/agentops-mis-relay.service")
                    for name in names
                )
                sdist_has_config_example = any(
                    name.endswith("/packaging/relay/config.example.json")
                    for name in names
                )
                sdist_has_acceptance = any(
                    name.endswith("/docs/LOCAL_RELAY_DEPLOY_CONTRACT_ACCEPTANCE.md")
                    for name in names
                )
    except Exception:
        failures.append("offline build artifacts could not be inspected")

    try:
        unit_payload = SYSTEMD_UNIT.read_text(encoding="utf-8")
        sections = unit_sections(unit_payload)
    except Exception:
        failures.append("systemd unit could not be parsed")

    require(
        pyproject_scripts.get(ENTRYPOINT_NAME) == ENTRYPOINT_TARGET,
        "pyproject entrypoint is missing or incorrect",
        failures,
    )
    require(
        backend_scripts.get(ENTRYPOINT_NAME) == ENTRYPOINT_TARGET,
        "custom build backend entrypoint is missing or incorrect",
        failures,
    )
    require(
        wheel_scripts.get(ENTRYPOINT_NAME) == ENTRYPOINT_TARGET,
        "wheel entrypoint is missing or incorrect",
        failures,
    )
    require(not wheel_has_unit, "wheel must not auto-install a systemd unit", failures)
    require(sdist_has_unit, "source distribution omits the systemd template", failures)
    require(
        sdist_has_config_example,
        "source distribution omits the credential-free config example",
        failures,
    )
    require(sdist_has_acceptance, "source distribution omits the deploy acceptance", failures)

    exec_start = one(sections, "Service", "ExecStart")
    try:
        exec_arguments = shlex.split(exec_start)
    except ValueError:
        exec_arguments = []
    require(exec_arguments == EXPECTED_EXEC_START, "systemd ExecStart contract changed", failures)
    try:
        preflight_arguments = shlex.split(one(sections, "Service", "ExecStartPre"))
    except ValueError:
        preflight_arguments = []
    require(
        preflight_arguments == EXPECTED_EXEC_START_PRE,
        "systemd ExecStartPre contract changed",
        failures,
    )
    required_service_values = {
        "Type": "simple",
        "User": "agentops-relay",
        "Group": "agentops-relay",
        "Restart": "on-failure",
        "RestartSec": "5s",
        "KillSignal": "SIGTERM",
        "RuntimeDirectoryMode": "0700",
        "StateDirectoryMode": "0700",
        "UMask": "0077",
        "NoNewPrivileges": "true",
        "PrivateTmp": "true",
        "PrivateDevices": "true",
        "ProtectSystem": "strict",
        "ProtectHome": "true",
        "RestrictAddressFamilies": "AF_UNIX AF_INET AF_INET6",
        "CapabilityBoundingSet": "CAP_NET_BIND_SERVICE",
        "AmbientCapabilities": "CAP_NET_BIND_SERVICE",
    }
    for name, expected in required_service_values.items():
        require(
            one(sections, "Service", name) == expected,
            f"systemd {name} contract changed",
            failures,
        )
    require(
        one(sections, "Install", "WantedBy") == "multi-user.target",
        "systemd install target is missing",
        failures,
    )

    forbidden_unit_patterns = (
        r"(?im)^\s*(Environment|EnvironmentFile|PassEnvironment|LoadCredential|SetCredential)=",
        r"(?i)(AGENTOPS_API_KEY|AGENTOPS_ADMIN_KEY|TOKEN=|PASSWORD=|tunnel_key|private_key)",
        r"(?i)(https?://|tailscale|acme)",
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    )
    unit_contains_forbidden_material = any(
        re.search(pattern, unit_payload) for pattern in forbidden_unit_patterns
    )
    require(
        not unit_contains_forbidden_material,
        "systemd template contains credential, endpoint, or external-infrastructure material",
        failures,
    )
    require(
        one(sections, "Service", "ReadOnlyPaths") == "/etc/agentops-mis-relay",
        "systemd config directory is not read-only",
        failures,
    )
    require(
        one(sections, "Service", "ReadWritePaths")
        == "/var/lib/agentops-mis-relay /run/agentops-mis-relay",
        "systemd writable paths are not narrowly scoped",
        failures,
    )
    try:
        config_example = json.loads(CONFIG_EXAMPLE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config_example = {}
    example_text = json.dumps(config_example, sort_keys=True)
    require(
        config_example.get("schema_version") == 1
        and isinstance(config_example.get("routes"), list)
        and len(config_example.get("routes") or []) == 1,
        "config example shape is missing or ambiguous",
        failures,
    )
    require(
        "example.invalid" in example_text,
        "config example does not use a reserved invalid hostname",
        failures,
    )
    require(
        not re.search(r"(?i)(token|password|api_key|tunnel_key)", example_text),
        "config example embeds a credential field",
        failures,
    )

    try:
        acceptance = ACCEPTANCE.read_text(encoding="utf-8")
    except OSError:
        acceptance = ""
    require("deployed_relay: false" in acceptance, "acceptance omits deployed Relay denial", failures)
    require("dns_acme: false" in acceptance, "acceptance omits DNS/ACME denial", failures)
    require(
        "does not import or execute the Relay daemon" in acceptance,
        "acceptance overstates runtime verification",
        failures,
    )

    result = {
        "operation": "relay_deploy_contract_smoke",
        "ok": not failures,
        "entrypoint": ENTRYPOINT_NAME,
        "entrypoint_target": ENTRYPOINT_TARGET,
        "wheel_entrypoint_present": wheel_scripts.get(ENTRYPOINT_NAME) == ENTRYPOINT_TARGET,
        "wheel_installs_systemd_unit": wheel_has_unit,
        "sdist_includes_systemd_unit": sdist_has_unit,
        "sdist_includes_config_example": sdist_has_config_example,
        "sdist_includes_acceptance": sdist_has_acceptance,
        "credential_or_endpoint_material_present": unit_contains_forbidden_material,
        "daemon_imported_or_executed": False,
        "network_used": False,
        "systemd_invoked": False,
        "deployed_relay": False,
        "dns_acme": False,
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
