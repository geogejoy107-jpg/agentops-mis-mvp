from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .protocol import ExperimentSpec, SpecError
from .resources import runtime_fingerprint
from .server_profiles import ServerProfileError, ServerRegistry


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _load_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {source}: {exc}") from exc


def _cmd_validate_spec(args: argparse.Namespace) -> int:
    raw = _load_json(args.spec)
    registry = ServerRegistry.load(args.servers) if args.servers else None
    spec = ExperimentSpec.from_dict(raw)
    profile = None
    if spec.executor == "ssh":
        if registry is None:
            raise SpecError("ssh specs require --servers for profile validation")
        profile = registry.get(str((spec.executor_config or {}).get("profile")))
    payload = {
        "ok": True,
        "operation": "validate_spec",
        "spec": str(Path(args.spec)),
        "name": spec.name,
        "stage": spec.stage.value,
        "executor": spec.executor,
        "trial_count": len(spec.expand_trials()),
        "protocol_hash": spec.protocol_hash,
        "provenance_hash": spec.provenance_hash,
        "server_profile": None if profile is None else {
            "name": profile.name,
            "snapshot_hash": profile.snapshot_hash,
        },
        "token_omitted": True,
    }
    _print_json(payload)
    return 0


def _cmd_server_list(args: argparse.Namespace) -> int:
    registry = ServerRegistry.load(args.servers)
    payload = {
        "ok": True,
        "operation": "server_list",
        **registry.public_payload(),
        "token_omitted": True,
    }
    _print_json(payload)
    return 0


def _cmd_server_probe(args: argparse.Namespace) -> int:
    registry = ServerRegistry.load(args.servers)
    profile = registry.get(args.profile)
    payload = {
        "ok": True,
        "operation": "server_probe",
        "profile": profile.public_snapshot(),
        "snapshot_hash": profile.snapshot_hash,
        "local_references": profile.local_reference_status(),
        "runtime_fingerprint": runtime_fingerprint(Path.cwd()) if args.local_fingerprint else None,
        "network_probe_performed": False,
        "ssh_command_executed": False,
        "token_omitted": True,
    }
    _print_json(payload)
    return 0


def _cmd_inventory(args: argparse.Namespace) -> int:
    _print_json({
        "ok": True,
        "operation": "inventory",
        "runtime_fingerprint": runtime_fingerprint(args.workdir or Path.cwd()),
        "token_omitted": True,
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-lab", description="Local-first Research Lab incubator CLI.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-spec", help="Validate an experiment JSON spec.")
    validate.add_argument("--spec", required=True)
    validate.add_argument("--servers", help="Required for ssh executor specs.")
    validate.set_defaults(func=_cmd_validate_spec)

    server_list = sub.add_parser("server-list", help="List non-secret SSH server profiles.")
    server_list.add_argument("--servers", required=True)
    server_list.set_defaults(func=_cmd_server_list)

    server_probe = sub.add_parser("server-probe", help="Inspect a server profile without opening SSH.")
    server_probe.add_argument("--servers", required=True)
    server_probe.add_argument("--profile", required=True)
    server_probe.add_argument("--local-fingerprint", action="store_true")
    server_probe.set_defaults(func=_cmd_server_probe)

    inventory = sub.add_parser("inventory", help="Print local runtime inventory.")
    inventory.add_argument("--workdir")
    inventory.set_defaults(func=_cmd_inventory)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (SpecError, ServerProfileError, ValueError) as exc:
        _print_json({
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "token_omitted": True,
        })
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
