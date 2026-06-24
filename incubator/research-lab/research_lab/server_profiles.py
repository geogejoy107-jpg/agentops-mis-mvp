from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .protocol import sha256_json


class ServerProfileError(ValueError):
    pass


_PROTECTED = (
    "pass" + "word",
    "pass" + "phrase",
    "tok" + "en",
    "sec" + "ret",
    "private" + "_key",
    "private" + "key",
    "cred" + "ential",
)
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_HOST = re.compile(r"^[A-Za-z0-9._:-]+$")
_SAFE_USER = re.compile(r"^[A-Za-z0-9._-]+$")


def _reject_protected_keys(value: Any, path: str = "registry") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(fragment in normalized for fragment in _PROTECTED):
                raise ServerProfileError(f"{path}.{key} is not allowed; store only local file references or use an SSH agent")
            _reject_protected_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_protected_keys(child, f"{path}[{index}]")


def _positive_int(raw: dict[str, Any], key: str, default: int, *, maximum: int | None = None) -> int:
    value = raw.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ServerProfileError(f"{key} must be an integer >= 1")
    if maximum is not None and value > maximum:
        raise ServerProfileError(f"{key} must be <= {maximum}")
    return value


def _optional_file_reference(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or "\x00" in value or "\n" in value:
        raise ServerProfileError(f"{key} must be a local file path reference")
    return str(Path(value).expanduser())


@dataclass(frozen=True, slots=True)
class SSHServerProfile:
    name: str
    host: str
    user: str
    remote_root: str
    port: int = 22
    python: str = "python3"
    host_key_policy: str = "strict"
    connect_timeout_seconds: int = 10
    server_alive_interval: int = 15
    server_alive_count_max: int = 3
    max_parallel_jobs: int = 1
    max_stage_bytes: int = 1_073_741_824
    identity_file: str | None = None
    known_hosts_file: str | None = None
    ssh_config_file: str | None = None
    tags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SSHServerProfile":
        if not isinstance(raw, dict):
            raise ServerProfileError("server profile must be an object")
        _reject_protected_keys(raw, "profile")
        name = raw.get("name")
        host = raw.get("host")
        user = raw.get("user")
        remote_root = raw.get("remote_root")
        python = raw.get("python", "python3")
        for key, value, pattern in (("name", name, _SAFE_NAME), ("host", host, _SAFE_HOST), ("user", user, _SAFE_USER)):
            if not isinstance(value, str) or not pattern.fullmatch(value):
                raise ServerProfileError(f"{key} contains unsupported characters")
        if not isinstance(remote_root, str) or not remote_root.startswith("/"):
            raise ServerProfileError("remote_root must be an absolute POSIX path")
        if ".." in PurePosixPath(remote_root).parts or "\x00" in remote_root or "\n" in remote_root:
            raise ServerProfileError("remote_root is unsafe")
        if not isinstance(python, str) or not python.strip() or any(ch in python for ch in "\n\x00"):
            raise ServerProfileError("python must be a remote executable name or path")
        policy = raw.get("host_key_policy", "strict")
        if policy not in {"strict", "accept-new"}:
            raise ServerProfileError("host_key_policy must be strict or accept-new")
        tags = raw.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(tag, str) and _SAFE_NAME.fullmatch(tag) for tag in tags):
            raise ServerProfileError("tags must be a list of safe strings")
        return cls(
            name=name,
            host=host,
            user=user,
            remote_root=str(PurePosixPath(remote_root)),
            port=_positive_int(raw, "port", 22, maximum=65535),
            python=python,
            host_key_policy=policy,
            connect_timeout_seconds=_positive_int(raw, "connect_timeout_seconds", 10, maximum=600),
            server_alive_interval=_positive_int(raw, "server_alive_interval", 15, maximum=3600),
            server_alive_count_max=_positive_int(raw, "server_alive_count_max", 3, maximum=100),
            max_parallel_jobs=_positive_int(raw, "max_parallel_jobs", 1, maximum=1024),
            max_stage_bytes=_positive_int(raw, "max_stage_bytes", 1_073_741_824),
            identity_file=_optional_file_reference(raw, "identity_file"),
            known_hosts_file=_optional_file_reference(raw, "known_hosts_file"),
            ssh_config_file=_optional_file_reference(raw, "ssh_config_file"),
            tags=tuple(dict.fromkeys(tags)),
        )

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "host": self.host,
            "user": self.user,
            "port": self.port,
            "remote_root": self.remote_root,
            "python": self.python,
            "host_key_policy": self.host_key_policy,
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "server_alive_interval": self.server_alive_interval,
            "server_alive_count_max": self.server_alive_count_max,
            "max_parallel_jobs": self.max_parallel_jobs,
            "max_stage_bytes": self.max_stage_bytes,
            "identity_file_configured": self.identity_file is not None,
            "known_hosts_file_configured": self.known_hosts_file is not None,
            "ssh_config_file_configured": self.ssh_config_file is not None,
            "tags": list(self.tags),
        }

    @property
    def snapshot_hash(self) -> str:
        return sha256_json(self.public_snapshot())

    def local_reference_status(self) -> dict[str, Any]:
        def one(value: str | None) -> dict[str, Any]:
            if value is None:
                return {"configured": False, "exists": None, "kind": None}
            path = Path(value).expanduser()
            kind = "file" if path.is_file() else ("directory" if path.is_dir() else None)
            return {"configured": True, "exists": path.exists(), "kind": kind}
        return {
            "identity_file": one(self.identity_file),
            "known_hosts_file": one(self.known_hosts_file),
            "ssh_config_file": one(self.ssh_config_file),
        }


@dataclass(frozen=True, slots=True)
class ServerRegistry:
    path: Path | None
    profiles: dict[str, SSHServerProfile]

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, path: str | Path | None = None) -> "ServerRegistry":
        if not isinstance(raw, dict):
            raise ServerProfileError("server registry must be an object")
        _reject_protected_keys(raw)
        entries = raw.get("profiles")
        if not isinstance(entries, list) or not entries:
            raise ServerProfileError("server registry requires a non-empty profiles list")
        profiles: dict[str, SSHServerProfile] = {}
        for entry in entries:
            profile = SSHServerProfile.from_dict(entry)
            if profile.name in profiles:
                raise ServerProfileError(f"duplicate server profile: {profile.name}")
            profiles[profile.name] = profile
        return cls(path=None if path is None else Path(path), profiles=profiles)

    @classmethod
    def load(cls, path: str | Path) -> "ServerRegistry":
        source = Path(path)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ServerProfileError(f"cannot read server registry: {exc}") from exc
        return cls.from_dict(raw, path=source)

    def get(self, name: str) -> SSHServerProfile:
        try:
            return self.profiles[name]
        except KeyError as exc:
            raise ServerProfileError(f"unknown server profile: {name}") from exc

    def public_payload(self) -> dict[str, Any]:
        snapshots = []
        for name in sorted(self.profiles):
            profile = self.profiles[name]
            snapshots.append({**profile.public_snapshot(), "snapshot_hash": profile.snapshot_hash, "local_references": profile.local_reference_status()})
        return {
            "registry": None if self.path is None else str(self.path),
            "registry_hash": sha256_json([self.profiles[name].public_snapshot() for name in sorted(self.profiles)]),
            "profiles": snapshots,
        }
