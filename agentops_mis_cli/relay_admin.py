"""Fail-closed offline installer for AgentOps MIS Relay release bundles."""
from __future__ import annotations

import argparse
import base64
import configparser
import csv
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


sys.dont_write_bytecode = True

BUNDLE_SCHEMA = "agentops.relay.release-bundle.v1"
PLAN_SCHEMA = "agentops.relay.offline-install-plan.v0"
INSTALLED_SCHEMA = "agentops.relay.installed-release.v0"
TRANSACTION_SCHEMA = "agentops.relay.install-transaction.v0"
STATUS_SCHEMA = "agentops.relay.offline-status.v0"
VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
WHEEL_PATTERN = re.compile(r"wheel/[A-Za-z0-9_.-]+-py3-none-any\.whl\Z")
RELEASE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}-[0-9a-f]{12}\Z")
PACKAGE_MEMBER_PATTERN = re.compile(
    r"(?:agentops_mis_cli|agentops_mis_core)/[A-Za-z_][A-Za-z0-9_]*\.py\Z"
)
EXPECTED_WHEEL_MODULES = frozenset(
    {
        "agentops_mis_cli/__init__.py",
        "agentops_mis_cli/__main__.py",
        "agentops_mis_cli/_build_backend.py",
        "agentops_mis_cli/advance_loop_policy.py",
        "agentops_mis_cli/agentops.py",
        "agentops_mis_cli/cli.py",
        "agentops_mis_cli/codex_runtime.py",
        "agentops_mis_cli/host.py",
        "agentops_mis_cli/host_log.py",
        "agentops_mis_cli/http_transport.py",
        "agentops_mis_cli/redaction.py",
        "agentops_mis_cli/relay_activation.py",
        "agentops_mis_cli/relay_admin.py",
        "agentops_mis_cli/relay_connector_service.py",
        "agentops_mis_cli/relay_connector_supervisor.py",
        "agentops_mis_cli/relay_control.py",
        "agentops_mis_cli/relay_daemon.py",
        "agentops_mis_cli/relay_epoch_store.py",
        "agentops_mis_cli/relay_host_tls_proxy.py",
        "agentops_mis_cli/relay_restart.py",
        "agentops_mis_cli/relay_sni_router.py",
        "agentops_mis_cli/relay_tunnel.py",
        "agentops_mis_cli/runtime_lock.py",
        "agentops_mis_cli/worker.py",
        "agentops_mis_core/__init__.py",
        "agentops_mis_core/agent_plans.py",
        "agentops_mis_core/approval_wall.py",
        "agentops_mis_core/commander_work_packages.py",
        "agentops_mis_core/evaluation_cases.py",
        "agentops_mis_core/gateway_runs.py",
        "agentops_mis_core/human_auth.py",
        "agentops_mis_core/operator_command_center.py",
        "agentops_mis_core/operator_evidence.py",
        "agentops_mis_core/operator_loop_control.py",
        "agentops_mis_core/operator_receipts.py",
        "agentops_mis_core/operator_start_check.py",
        "agentops_mis_core/private_host_acceptance.py",
        "agentops_mis_core/read_model_cache.py",
        "agentops_mis_core/relay_transport.py",
        "agentops_mis_core/worker_fleet.py",
        "agentops_mis_core/workflow_jobs.py",
    }
)

MAX_ARCHIVE_SIZE = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 32
MAX_ARCHIVE_MEMBER_SIZE = 192 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_SIZE = 320 * 1024 * 1024
MAX_WHEEL_MEMBERS = 4096
MAX_WHEEL_MEMBER_SIZE = 32 * 1024 * 1024
MAX_WHEEL_EXPANDED_SIZE = 256 * 1024 * 1024
MAX_METADATA_SIZE = 1024 * 1024
MAX_STATUS_DIRECTORY_ENTRIES = 4096
MAX_STATUS_RELEASE_FILES = 4096
MAX_STATUS_RELEASE_DIRECTORIES = 512
MAX_STATUS_RELEASE_BYTES = 256 * 1024 * 1024

CONFIG_PATH = "config/config.example.json"
UNIT_PATH = "systemd/agentops-mis-relay.service"
MANIFEST_PATH = "manifest.json"
CHECKSUMS_PATH = "SHA256SUMS"
UNIT_NAME = "agentops-mis-relay.service"
LAUNCHER_NAME = "agentops-relay"


class RelayAdminError(Exception):
    """Expected failure represented by a non-sensitive identifier."""

    def __init__(self, error_id: str, *, future_operation_id: str | None = None):
        super().__init__(error_id)
        self.error_id = error_id
        self.future_operation_id = future_operation_id


class RelayStatusInvalid(Exception):
    """Internal sentinel for a bounded, redacted invalid status."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise RelayAdminError("invalid_arguments")


@dataclass(frozen=True)
class WheelEntry:
    name: str
    data: bytes


@dataclass(frozen=True)
class RelayBundle:
    archive_sha256: str
    archive_member_count: int
    bundle_file_count: int
    git_commit: str
    manifest_sha256: str
    release_id: str
    schema: str
    unit_data: bytes
    version: str
    wheel_data: bytes
    wheel_entries: tuple[WheelEntry, ...]
    wheel_member_count: int
    wheel_path: str
    wheel_sha256: str


@dataclass(frozen=True)
class InstallPaths:
    root: Path
    opt_base: Path
    releases: Path
    release: Path
    current: Path
    controller: Path
    stable_launcher: Path
    unit: Path
    admin_state: Path
    lifecycle_lock: Path
    transaction: Path

    @classmethod
    def for_bundle(cls, root: Path, bundle: RelayBundle) -> "InstallPaths":
        opt_base = root / "opt" / "agentops-mis-relay"
        admin_state = root / "var" / "lib" / "agentops-relayctl"
        return cls(
            root=root,
            opt_base=opt_base,
            releases=opt_base / "releases",
            release=opt_base / "releases" / bundle.release_id,
            current=opt_base / "current",
            controller=opt_base / "controller",
            stable_launcher=root / "usr" / "local" / "bin" / LAUNCHER_NAME,
            unit=root / "etc" / "systemd" / "system" / UNIT_NAME,
            admin_state=admin_state,
            lifecycle_lock=admin_state / "lifecycle.lock",
            transaction=admin_state / "transaction.json",
        )


@dataclass(frozen=True)
class InstallPlan:
    bundle: RelayBundle
    paths: InstallPaths
    plan_sha256: str
    root_fingerprint: str
    no_op: bool


@dataclass(frozen=True)
class StatusFile:
    data: bytes
    gid: int
    mode: int
    nlink: int
    uid: int


def _status_file_fingerprint(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RelayAdminError("invalid_json")
        result[key] = value
    return result


def _parse_json(data: bytes, *, maximum: int = MAX_METADATA_SIZE) -> Any:
    if len(data) > maximum:
        raise RelayAdminError("metadata_too_large")
    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                RelayAdminError("invalid_json")
            ),
        )
    except RelayAdminError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        raise RelayAdminError("invalid_json") from exc


def _safe_posix_name(name: str) -> str:
    if not name or "\x00" in name or "\\" in name or len(name) > 240:
        raise RelayAdminError("unsafe_archive_member")
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RelayAdminError("unsafe_archive_member") from exc
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or not path.parts
        or "." in path.parts
        or ".." in path.parts
        or path.as_posix() != name
    ):
        raise RelayAdminError("unsafe_archive_member")
    return name


def _read_archive(path: Path, expected_sha256: str) -> tuple[bytes, str]:
    expected = expected_sha256.strip().lower()
    if not SHA256_PATTERN.fullmatch(expected):
        raise RelayAdminError("invalid_archive_sha256")
    if not path.is_absolute():
        raise RelayAdminError("bundle_path_not_absolute")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RelayAdminError("bundle_unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RelayAdminError("bundle_not_regular")
        if before.st_size <= 0 or before.st_size > MAX_ARCHIVE_SIZE:
            raise RelayAdminError("bundle_size_invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise RelayAdminError("bundle_changed_during_read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise RelayAdminError("bundle_changed_during_read")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise RelayAdminError("bundle_changed_during_read")
    finally:
        os.close(descriptor)
    data = b"".join(chunks)
    actual = _sha256(data)
    if actual != expected:
        raise RelayAdminError("archive_sha256_mismatch")
    return data, actual


def _read_tar_files(data: bytes) -> tuple[str, dict[str, bytes], set[str], int]:
    files: dict[str, bytes] = {}
    directories: set[str] = set()
    names: set[str] = set()
    roots: set[str] = set()
    member_count = 0
    expanded_size = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            while True:
                member = archive.next()
                if member is None:
                    break
                member_count += 1
                if member_count > MAX_ARCHIVE_MEMBERS:
                    raise RelayAdminError("archive_member_limit_exceeded")
                name = _safe_posix_name(member.name)
                if name in names:
                    raise RelayAdminError("duplicate_archive_member")
                names.add(name)
                path = PurePosixPath(name)
                roots.add(path.parts[0])
                if (
                    member.uid != 0
                    or member.gid != 0
                    or member.uname
                    or member.gname
                    or member.mtime != 0
                    or member.pax_headers
                ):
                    raise RelayAdminError("archive_metadata_invalid")
                if member.isdir():
                    if member.size != 0 or stat.S_IMODE(member.mode) != 0o755:
                        raise RelayAdminError("archive_metadata_invalid")
                    directories.add(name)
                    continue
                if not member.isreg():
                    raise RelayAdminError("archive_special_member_rejected")
                if stat.S_IMODE(member.mode) != 0o644:
                    raise RelayAdminError("archive_metadata_invalid")
                if member.size < 0 or member.size > MAX_ARCHIVE_MEMBER_SIZE:
                    raise RelayAdminError("archive_member_size_invalid")
                expanded_size += member.size
                if expanded_size > MAX_ARCHIVE_EXPANDED_SIZE:
                    raise RelayAdminError("archive_expanded_size_invalid")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise RelayAdminError("archive_member_unreadable")
                payload = extracted.read(member.size + 1)
                if len(payload) != member.size:
                    raise RelayAdminError("archive_member_size_mismatch")
                files[name] = payload
    except RelayAdminError:
        raise
    except (OSError, EOFError, tarfile.TarError) as exc:
        raise RelayAdminError("archive_invalid") from exc
    if len(roots) != 1:
        raise RelayAdminError("archive_root_invalid")
    return roots.pop(), files, directories, member_count


def _parse_manifest(data: bytes) -> dict[str, Any]:
    manifest = _parse_json(data)
    if not isinstance(manifest, dict) or set(manifest) != {
        "files",
        "git_commit",
        "schema",
        "version",
    }:
        raise RelayAdminError("manifest_shape_invalid")
    if manifest["schema"] != BUNDLE_SCHEMA:
        raise RelayAdminError("bundle_schema_unsupported")
    version = manifest["version"]
    commit = manifest["git_commit"]
    records = manifest["files"]
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise RelayAdminError("bundle_version_invalid")
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        raise RelayAdminError("bundle_commit_invalid")
    if not isinstance(records, list) or len(records) != 3:
        raise RelayAdminError("manifest_files_invalid")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "sha256", "size"}:
            raise RelayAdminError("manifest_files_invalid")
        path = record["path"]
        digest = record["sha256"]
        size = record["size"]
        if not isinstance(path, str):
            raise RelayAdminError("manifest_files_invalid")
        _safe_posix_name(path)
        if path in seen:
            raise RelayAdminError("manifest_files_invalid")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise RelayAdminError("manifest_files_invalid")
        if type(size) is not int or size < 0 or size > MAX_ARCHIVE_MEMBER_SIZE:
            raise RelayAdminError("manifest_files_invalid")
        seen.add(path)
        normalized.append({"path": path, "sha256": digest, "size": size})
    if [record["path"] for record in normalized] != sorted(seen):
        raise RelayAdminError("manifest_files_invalid")
    if data != _canonical_json(manifest):
        raise RelayAdminError("manifest_not_canonical")
    return manifest


def _parse_checksums(data: bytes) -> dict[str, str]:
    if len(data) > MAX_METADATA_SIZE:
        raise RelayAdminError("checksums_invalid")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RelayAdminError("checksums_invalid") from exc
    if not text.endswith("\n") or "\r" in text:
        raise RelayAdminError("checksums_invalid")
    result: dict[str, str] = {}
    for line in text.splitlines():
        digest, separator, path = line.partition("  ")
        if (
            not separator
            or not SHA256_PATTERN.fullmatch(digest)
            or path in result
        ):
            raise RelayAdminError("checksums_invalid")
        _safe_posix_name(path)
        result[path] = digest
    canonical = "".join(
        f"{digest}  {path}\n" for path, digest in sorted(result.items())
    ).encode("ascii")
    if canonical != data:
        raise RelayAdminError("checksums_invalid")
    return result


def _metadata_fields(data: bytes, error_id: str) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RelayAdminError(error_id) from exc
    if not text.endswith("\n") or "\r" in text:
        raise RelayAdminError(error_id)
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line:
            break
        name, separator, value = line.partition(": ")
        if (
            not separator
            or not name
            or name in fields
            or not name.replace("-", "").isalnum()
        ):
            raise RelayAdminError(error_id)
        fields[name] = value
    return fields


def _validate_wheel_record(
    entries: tuple[WheelEntry, ...],
    record_name: str,
) -> None:
    by_name = {entry.name: entry.data for entry in entries}
    try:
        record = by_name[record_name]
        text = record.decode("utf-8")
        rows = list(csv.reader(io.StringIO(text)))
    except (KeyError, UnicodeDecodeError, csv.Error) as exc:
        raise RelayAdminError("wheel_record_invalid") from exc
    if not record.endswith(b"\n"):
        raise RelayAdminError("wheel_record_invalid")
    recorded: set[str] = set()
    for row in rows:
        if len(row) != 3:
            raise RelayAdminError("wheel_record_invalid")
        name, digest, size = row
        try:
            _safe_posix_name(name)
        except RelayAdminError as exc:
            raise RelayAdminError("wheel_record_invalid") from exc
        if name in recorded or name not in by_name:
            raise RelayAdminError("wheel_record_invalid")
        recorded.add(name)
        if name == record_name:
            if digest or size:
                raise RelayAdminError("wheel_record_invalid")
            continue
        payload = by_name[name]
        expected_digest = (
            "sha256="
            + base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        if digest != expected_digest or size != str(len(payload)):
            raise RelayAdminError("wheel_record_invalid")
    if recorded != set(by_name):
        raise RelayAdminError("wheel_record_invalid")


def _read_wheel(
    data: bytes,
    expected_version: str,
) -> tuple[tuple[WheelEntry, ...], int]:
    if not data or len(data) > MAX_ARCHIVE_MEMBER_SIZE:
        raise RelayAdminError("wheel_size_invalid")
    entries: list[WheelEntry] = []
    names: set[str] = set()
    expanded = 0
    dist_info_roots: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as wheel:
            infos = wheel.infolist()
            if not infos or len(infos) > MAX_WHEEL_MEMBERS:
                raise RelayAdminError("wheel_member_limit_exceeded")
            for info in infos:
                name = _safe_posix_name(info.filename)
                if name in names:
                    raise RelayAdminError("duplicate_wheel_member")
                names.add(name)
                if info.flag_bits & 0x1:
                    raise RelayAdminError("wheel_member_invalid")
                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if info.is_dir():
                    raise RelayAdminError("wheel_member_invalid")
                if file_type not in {0, stat.S_IFREG}:
                    raise RelayAdminError("wheel_special_member_rejected")
                if info.file_size < 0 or info.file_size > MAX_WHEEL_MEMBER_SIZE:
                    raise RelayAdminError("wheel_member_size_invalid")
                expanded += info.file_size
                if expanded > MAX_WHEEL_EXPANDED_SIZE:
                    raise RelayAdminError("wheel_expanded_size_invalid")
                top = PurePosixPath(name).parts[0]
                if top.endswith(".dist-info"):
                    dist_info_roots.add(top)
                elif not PACKAGE_MEMBER_PATTERN.fullmatch(name):
                    raise RelayAdminError("wheel_member_invalid")
                payload = wheel.read(info)
                if len(payload) != info.file_size:
                    raise RelayAdminError("wheel_member_size_mismatch")
                entries.append(WheelEntry(name=name, data=payload))
    except RelayAdminError:
        raise
    except (OSError, EOFError, RuntimeError, zipfile.BadZipFile) as exc:
        raise RelayAdminError("wheel_invalid") from exc
    if len(dist_info_roots) != 1:
        raise RelayAdminError("wheel_metadata_invalid")
    dist_info = next(iter(dist_info_roots))
    if dist_info != f"agentops_mis_cli-{expected_version}.dist-info":
        raise RelayAdminError("wheel_metadata_invalid")
    required = {
        *EXPECTED_WHEEL_MODULES,
        f"{dist_info}/METADATA",
        f"{dist_info}/WHEEL",
        f"{dist_info}/RECORD",
        f"{dist_info}/entry_points.txt",
    }
    dist_info_members = {
        name for name in names if PurePosixPath(name).parts[0] == dist_info
    }
    package_members = {
        name for name in names if PACKAGE_MEMBER_PATTERN.fullmatch(name)
    }
    if (
        package_members != EXPECTED_WHEEL_MODULES
        or not required.issubset(names)
        or dist_info_members != {
            f"{dist_info}/METADATA",
            f"{dist_info}/WHEEL",
            f"{dist_info}/RECORD",
            f"{dist_info}/entry_points.txt",
        }
    ):
        raise RelayAdminError("wheel_metadata_invalid")
    entry_map = {entry.name: entry.data for entry in entries}
    metadata = _metadata_fields(
        entry_map[f"{dist_info}/METADATA"],
        "wheel_metadata_invalid",
    )
    if (
        metadata.get("Metadata-Version") != "2.2"
        or metadata.get("Name") != "agentops-mis-cli"
        or metadata.get("Version") != expected_version
    ):
        raise RelayAdminError("wheel_metadata_invalid")
    wheel_metadata = _metadata_fields(
        entry_map[f"{dist_info}/WHEEL"],
        "wheel_metadata_invalid",
    )
    if (
        wheel_metadata.get("Wheel-Version") != "1.0"
        or wheel_metadata.get("Root-Is-Purelib") != "true"
        or wheel_metadata.get("Tag") != "py3-none-any"
    ):
        raise RelayAdminError("wheel_metadata_invalid")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    try:
        parser.read_string(
            entry_map[f"{dist_info}/entry_points.txt"].decode("utf-8")
        )
        scripts = dict(parser.items("console_scripts"))
    except (
        UnicodeDecodeError,
        configparser.Error,
        configparser.NoSectionError,
    ) as exc:
        raise RelayAdminError("wheel_entrypoint_invalid") from exc
    expected_scripts = {
        "agentops": "agentops_mis_cli.cli:main",
        "agentops-relay": "agentops_mis_cli.relay_daemon:main",
        "agentops-relayctl": "agentops_mis_cli.relay_admin:main",
        "agentops-worker": "agentops_mis_cli.worker:main",
    }
    if parser.sections() != ["console_scripts"] or scripts != expected_scripts:
        raise RelayAdminError("wheel_entrypoint_invalid")
    frozen_entries = tuple(entries)
    _validate_wheel_record(frozen_entries, f"{dist_info}/RECORD")
    return frozen_entries, len(infos)


def inspect_bundle(bundle_path: Path, expected_sha256: str) -> RelayBundle:
    archive_data, archive_sha256 = _read_archive(bundle_path, expected_sha256)
    root, archived, directories, archive_member_count = _read_tar_files(archive_data)
    relative_files: dict[str, bytes] = {}
    relative_directories: set[str] = set()
    root_prefix = root + "/"
    for name, payload in archived.items():
        if not name.startswith(root_prefix):
            raise RelayAdminError("archive_root_invalid")
        relative_files[name[len(root_prefix) :]] = payload
    for name in directories:
        if name == root:
            relative_directories.add("")
        elif name.startswith(root_prefix):
            relative_directories.add(name[len(root_prefix) :])
        else:
            raise RelayAdminError("archive_root_invalid")
    if set(relative_files) < {MANIFEST_PATH, CHECKSUMS_PATH}:
        raise RelayAdminError("bundle_files_invalid")
    manifest_data = relative_files[MANIFEST_PATH]
    manifest = _parse_manifest(manifest_data)
    version = manifest["version"]
    commit = manifest["git_commit"]
    expected_root = f"agentops-mis-relay-{version}"
    if root != expected_root:
        raise RelayAdminError("archive_root_invalid")
    manifest_records = {record["path"]: record for record in manifest["files"]}
    wheel_paths = sorted(path for path in manifest_records if WHEEL_PATTERN.fullmatch(path))
    expected_wheel_path = (
        f"wheel/agentops_mis_cli-{version}-py3-none-any.whl"
    )
    expected_payload = {CONFIG_PATH, UNIT_PATH, expected_wheel_path}
    if wheel_paths != [expected_wheel_path] or set(manifest_records) != expected_payload:
        raise RelayAdminError("manifest_files_invalid")
    expected_files = expected_payload | {MANIFEST_PATH, CHECKSUMS_PATH}
    if set(relative_files) != expected_files:
        raise RelayAdminError("bundle_files_invalid")
    if relative_directories != {"", "config", "systemd", "wheel"}:
        raise RelayAdminError("bundle_directories_invalid")
    for path, record in manifest_records.items():
        payload = relative_files[path]
        if len(payload) != record["size"] or _sha256(payload) != record["sha256"]:
            raise RelayAdminError("manifest_file_mismatch")
    checksums = _parse_checksums(relative_files[CHECKSUMS_PATH])
    checksum_paths = expected_payload | {MANIFEST_PATH}
    if set(checksums) != checksum_paths:
        raise RelayAdminError("checksums_invalid")
    for path in checksum_paths:
        if _sha256(relative_files[path]) != checksums[path]:
            raise RelayAdminError("checksum_mismatch")
    wheel_path = wheel_paths[0]
    wheel_data = relative_files[wheel_path]
    wheel_entries, wheel_member_count = _read_wheel(wheel_data, version)
    release_id = f"{version}-{commit[:12]}"
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise RelayAdminError("release_id_invalid")
    return RelayBundle(
        archive_sha256=archive_sha256,
        archive_member_count=archive_member_count,
        bundle_file_count=len(relative_files),
        git_commit=commit,
        manifest_sha256=_sha256(manifest_data),
        release_id=release_id,
        schema=BUNDLE_SCHEMA,
        unit_data=relative_files[UNIT_PATH],
        version=version,
        wheel_data=wheel_data,
        wheel_entries=wheel_entries,
        wheel_member_count=wheel_member_count,
        wheel_path=wheel_path,
        wheel_sha256=_sha256(wheel_data),
    )


def _resolve_root(value: Path) -> Path:
    if not value.is_absolute():
        raise RelayAdminError("root_not_absolute")
    try:
        supplied_metadata = value.lstat()
        if stat.S_ISLNK(supplied_metadata.st_mode):
            raise RelayAdminError("root_not_directory")
        root = value.resolve(strict=True)
        metadata = root.lstat()
    except RelayAdminError:
        raise
    except OSError as exc:
        raise RelayAdminError("root_unavailable") from exc
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise RelayAdminError("root_not_directory")
    if metadata.st_uid not in {0, os.geteuid()}:
        raise RelayAdminError("root_owner_invalid")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise RelayAdminError("root_mode_invalid")
    return root


def _relative_to_root(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError as exc:
        raise RelayAdminError("install_path_escape") from exc


def _validate_existing_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RelayAdminError("install_parent_invalid") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RelayAdminError("install_parent_invalid")
    if metadata.st_uid not in {0, os.geteuid()}:
        raise RelayAdminError("install_parent_owner_invalid")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise RelayAdminError("install_parent_mode_invalid")


def _validate_parent_chain(root: Path, target: Path) -> None:
    current = root
    for part in _relative_to_root(target, root):
        current = current / part
        if not os.path.lexists(current):
            return
        _validate_existing_directory(current)


def _safe_read_regular(path: Path, maximum: int = MAX_METADATA_SIZE) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RelayAdminError("installed_state_invalid") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size < 0
            or metadata.st_size > maximum
            or metadata.st_uid not in {0, os.geteuid()}
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise RelayAdminError("installed_state_invalid")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise RelayAdminError("installed_state_invalid")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise RelayAdminError("installed_state_invalid")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _readlink_exact(path: Path) -> str:
    try:
        metadata = path.lstat()
        if not stat.S_ISLNK(metadata.st_mode):
            raise RelayAdminError("installed_state_invalid")
        return os.readlink(path)
    except OSError as exc:
        raise RelayAdminError("installed_state_invalid") from exc


def _launcher_data() -> bytes:
    return (
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        "import sys\n"
        "\n"
        "release = Path(__file__).resolve().parents[1]\n"
        "sys.path.insert(0, str(release / 'private' / 'site-packages'))\n"
        "from agentops_mis_cli.relay_daemon import main\n"
        "\n"
        "raise SystemExit(main())\n"
    ).encode("ascii")


def _release_metadata(bundle: RelayBundle) -> bytes:
    return _canonical_json(
        {
            "archive_sha256": bundle.archive_sha256,
            "bundle_schema": bundle.schema,
            "git_commit": bundle.git_commit,
            "installed_file_count": len(bundle.wheel_entries) + 3,
            "launcher_sha256": _sha256(_launcher_data()),
            "manifest_sha256": bundle.manifest_sha256,
            "release_id": bundle.release_id,
            "schema": INSTALLED_SCHEMA,
            "unit_sha256": _sha256(bundle.unit_data),
            "version": bundle.version,
            "wheel_member_count": bundle.wheel_member_count,
            "wheel_sha256": bundle.wheel_sha256,
        }
    )


def _stable_launcher_target(paths: InstallPaths) -> str:
    logical_target = paths.current / "bin" / LAUNCHER_NAME
    return os.path.relpath(logical_target, paths.stable_launcher.parent)


def _expected_release_files(bundle: RelayBundle) -> dict[str, bytes]:
    files = {
        "bin/agentops-relay": _launcher_data(),
        "release.json": _release_metadata(bundle),
        f"systemd/{UNIT_NAME}": bundle.unit_data,
    }
    for entry in bundle.wheel_entries:
        files[f"private/site-packages/{entry.name}"] = entry.data
    return files


def _validate_installed_release(paths: InstallPaths, bundle: RelayBundle) -> None:
    _validate_existing_directory(paths.release)
    expected_files = _expected_release_files(bundle)
    observed_files: set[str] = set()
    for directory, directory_names, file_names in os.walk(paths.release, followlinks=False):
        directory_path = Path(directory)
        _validate_existing_directory(directory_path)
        for name in directory_names:
            child = directory_path / name
            metadata = child.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise RelayAdminError("installed_state_invalid")
        for name in file_names:
            child = directory_path / name
            relative = child.relative_to(paths.release).as_posix()
            observed_files.add(relative)
            expected = expected_files.get(relative)
            if expected is None or _safe_read_regular(
                child, max(MAX_WHEEL_MEMBER_SIZE, len(expected))
            ) != expected:
                raise RelayAdminError("installed_state_invalid")
    if observed_files != set(expected_files):
        raise RelayAdminError("installed_state_invalid")
    if _safe_read_regular(paths.unit) != bundle.unit_data:
        raise RelayAdminError("installed_state_invalid")
    expected_release_target = f"releases/{bundle.release_id}"
    if (
        _readlink_exact(paths.current) != expected_release_target
        or _readlink_exact(paths.controller) != expected_release_target
        or _readlink_exact(paths.stable_launcher) != _stable_launcher_target(paths)
    ):
        raise RelayAdminError("installed_state_invalid")


def _existing_release_metadata(paths: InstallPaths) -> dict[str, Any]:
    if not os.path.lexists(paths.current):
        raise RelayAdminError("installed_state_invalid")
    target = _readlink_exact(paths.current)
    target_path = PurePosixPath(target)
    if (
        target_path.is_absolute()
        or len(target_path.parts) != 2
        or target_path.parts[0] != "releases"
        or not RELEASE_ID_PATTERN.fullmatch(target_path.parts[1])
    ):
        raise RelayAdminError("installed_state_invalid")
    release = paths.opt_base / target_path.parts[0] / target_path.parts[1]
    _validate_existing_directory(release)
    metadata_data = _safe_read_regular(release / "release.json")
    metadata = _parse_json(metadata_data)
    required = {
        "archive_sha256",
        "bundle_schema",
        "git_commit",
        "installed_file_count",
        "launcher_sha256",
        "manifest_sha256",
        "release_id",
        "schema",
        "unit_sha256",
        "version",
        "wheel_member_count",
        "wheel_sha256",
    }
    if (
        not isinstance(metadata, dict)
        or set(metadata) != required
        or metadata.get("schema") != INSTALLED_SCHEMA
        or metadata_data != _canonical_json(metadata)
    ):
        raise RelayAdminError("installed_state_invalid")
    return metadata


def _path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def _metadata_fingerprint(metadata: os.stat_result) -> str:
    return _sha256(
        _canonical_json(
            {
                "device_id": metadata.st_dev,
                "group_id": metadata.st_gid,
                "inode": metadata.st_ino,
                "mode": stat.S_IMODE(metadata.st_mode),
                "owner_id": metadata.st_uid,
            }
        )
    )


def _root_fingerprint(root: Path) -> str:
    try:
        metadata = root.stat(follow_symlinks=False)
    except OSError as exc:
        raise RelayAdminError("root_unavailable") from exc
    return _metadata_fingerprint(metadata)


def _root_path_matches(root: Path, expected: str) -> bool:
    try:
        return _root_fingerprint(root) == expected
    except RelayAdminError:
        return False


def _recovery_artifact_present(paths: InstallPaths) -> bool:
    if _path_exists(paths.transaction):
        return True
    if not _path_exists(paths.admin_state):
        return False
    _validate_existing_directory(paths.admin_state)
    try:
        return any(
            entry.name.startswith(".transaction-")
            and entry.name.endswith(".tmp")
            for entry in paths.admin_state.iterdir()
        )
    except OSError as exc:
        raise RelayAdminError("installed_state_invalid") from exc


def _check_install_state(paths: InstallPaths, bundle: RelayBundle) -> bool:
    for parent in (
        paths.opt_base,
        paths.releases,
        paths.stable_launcher.parent,
        paths.unit.parent,
        paths.admin_state,
    ):
        _validate_parent_chain(paths.root, parent)
    target_paths = (
        paths.release,
        paths.current,
        paths.controller,
        paths.stable_launcher,
        paths.unit,
    )
    present = [_path_exists(path) for path in target_paths]
    if not any(present):
        if paths.releases.exists():
            _validate_existing_directory(paths.releases)
            try:
                if any(paths.releases.iterdir()):
                    raise RelayAdminError("installed_state_conflict")
            except OSError as exc:
                raise RelayAdminError("installed_state_invalid") from exc
        if paths.opt_base.exists():
            _validate_existing_directory(paths.opt_base)
            allowed = {"releases"} if paths.releases.exists() else set()
            try:
                if {entry.name for entry in paths.opt_base.iterdir()} != allowed:
                    raise RelayAdminError("installed_state_conflict")
            except OSError as exc:
                raise RelayAdminError("installed_state_invalid") from exc
        return False
    metadata = _existing_release_metadata(paths)
    existing_version = metadata.get("version")
    existing_release_id = metadata.get("release_id")
    if existing_version != bundle.version:
        raise RelayAdminError(
            "upgrade_required",
            future_operation_id="upgrade",
        )
    if existing_release_id != bundle.release_id:
        raise RelayAdminError("same_version_release_conflict")
    if not all(present):
        raise RelayAdminError("installed_state_conflict")
    if _release_metadata(bundle) != _canonical_json(metadata):
        raise RelayAdminError("installed_state_conflict")
    _validate_installed_release(paths, bundle)
    return True


def _plan_for_install(root: Path, bundle: RelayBundle) -> InstallPlan:
    paths = InstallPaths.for_bundle(root, bundle)
    if _recovery_artifact_present(paths):
        raise RelayAdminError("recovery_required")
    no_op = _check_install_state(paths, bundle)
    plan_data = {
        "action_id": "install",
        "archive_sha256": bundle.archive_sha256,
        "bundle_schema": bundle.schema,
        "current_state_id": bundle.release_id if no_op else "absent",
        "git_commit": bundle.git_commit,
        "launcher_sha256": _sha256(_launcher_data()),
        "manifest_sha256": bundle.manifest_sha256,
        "no_op": no_op,
        "release_id": bundle.release_id,
        "root_sha256": _root_fingerprint(root),
        "schema": PLAN_SCHEMA,
        "unit_sha256": _sha256(bundle.unit_data),
        "version": bundle.version,
        "wheel_sha256": bundle.wheel_sha256,
    }
    return InstallPlan(
        bundle=bundle,
        paths=paths,
        plan_sha256=_sha256(_canonical_json(plan_data)),
        root_fingerprint=plan_data["root_sha256"],
        no_op=no_op,
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_chain(root: Path, target: Path, mode: int = 0o755) -> None:
    current = root
    for part in _relative_to_root(target, root):
        current = current / part
        if os.path.lexists(current):
            _validate_existing_directory(current)
            continue
        parent = current.parent
        try:
            os.mkdir(current, mode)
            os.chmod(current, mode, follow_symlinks=False)
            _fsync_directory(parent)
        except OSError as exc:
            raise RelayAdminError("install_directory_failed") from exc
        _validate_existing_directory(current)


def _write_new_file(path: Path, data: bytes, mode: int) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, mode)
    except OSError as exc:
        raise RelayAdminError("install_file_conflict") from exc
    try:
        os.fchmod(descriptor, mode)
        view = memoryview(data)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise RelayAdminError("install_write_failed")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _mkdir_fresh(path: Path, mode: int = 0o755) -> None:
    try:
        os.mkdir(path, mode)
        os.chmod(path, mode, follow_symlinks=False)
    except OSError as exc:
        raise RelayAdminError("install_staging_conflict") from exc


def _populate_release(stage: Path, bundle: RelayBundle) -> None:
    _mkdir_fresh(stage)
    for relative, data in sorted(_expected_release_files(bundle).items()):
        target = stage / PurePosixPath(relative)
        current = stage
        for part in target.relative_to(stage).parts[:-1]:
            current = current / part
            if not current.exists():
                _mkdir_fresh(current)
            else:
                _validate_existing_directory(current)
        mode = 0o755 if relative == "bin/agentops-relay" else 0o644
        _write_new_file(target, data, mode)
    for directory, directory_names, _file_names in os.walk(stage, topdown=False):
        for name in directory_names:
            _fsync_directory(Path(directory) / name)
        _fsync_directory(Path(directory))


def _write_transaction(path: Path, plan: InstallPlan) -> None:
    data = _canonical_json(
        {
            "archive_sha256": plan.bundle.archive_sha256,
            "plan_sha256": plan.plan_sha256,
            "release_id": plan.bundle.release_id,
            "schema": TRANSACTION_SCHEMA,
            "state_id": "prepared",
        }
    )
    temporary = path.parent / f".transaction-{plan.plan_sha256[:16]}.tmp"
    if _path_exists(temporary):
        raise RelayAdminError("recovery_required")
    _write_new_file(temporary, data, 0o600)
    try:
        os.link(temporary, path)
    except OSError as exc:
        raise RelayAdminError("recovery_required") from exc
    finally:
        temporary.unlink(missing_ok=True)
    _fsync_directory(path.parent)


def _remove_exact_symlink(path: Path, target: str) -> None:
    if os.path.lexists(path) and _readlink_exact(path) == target:
        path.unlink()
        _fsync_directory(path.parent)


def _rollback_install(plan: InstallPlan, stage: Path, unit_stage: Path) -> bool:
    paths = plan.paths
    try:
        _remove_exact_symlink(paths.stable_launcher, _stable_launcher_target(paths))
        expected_release_target = f"releases/{plan.bundle.release_id}"
        _remove_exact_symlink(paths.controller, expected_release_target)
        _remove_exact_symlink(paths.current, expected_release_target)
        if paths.unit.exists() and _safe_read_regular(paths.unit) == plan.bundle.unit_data:
            paths.unit.unlink()
            _fsync_directory(paths.unit.parent)
        if paths.release.exists():
            metadata = _safe_read_regular(paths.release / "release.json")
            if metadata != _release_metadata(plan.bundle):
                return False
            shutil.rmtree(paths.release)
            _fsync_directory(paths.releases)
        if stage.exists():
            shutil.rmtree(stage)
        unit_stage.unlink(missing_ok=True)
        if paths.transaction.exists():
            paths.transaction.unlink()
            _fsync_directory(paths.transaction.parent)
        return True
    except (OSError, RelayAdminError):
        return False


def _publish_install_anchored(
    plan: InstallPlan,
    original_root: Path,
) -> None:
    paths = plan.paths
    if plan.no_op:
        return
    for directory in (
        paths.releases,
        paths.stable_launcher.parent,
        paths.unit.parent,
        paths.admin_state,
    ):
        _mkdir_chain(paths.root, directory, 0o700 if directory == paths.admin_state else 0o755)
    lock_flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        lock_descriptor = os.open(paths.lifecycle_lock, lock_flags, 0o600)
        os.fchmod(lock_descriptor, 0o600)
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
    except OSError as exc:
        raise RelayAdminError("lifecycle_lock_failed") from exc
    stage = paths.releases / f".installing-{plan.plan_sha256[:16]}"
    unit_stage = paths.unit.parent / f".{UNIT_NAME}.{plan.plan_sha256[:16]}.tmp"
    try:
        refreshed = _plan_for_install(paths.root, plan.bundle)
        if refreshed.plan_sha256 != plan.plan_sha256 or refreshed.no_op:
            raise RelayAdminError("plan_stale")
        if paths.transaction.exists():
            raise RelayAdminError("recovery_required")
        _write_transaction(paths.transaction, plan)
        try:
            _populate_release(stage, plan.bundle)
            _write_new_file(unit_stage, plan.bundle.unit_data, 0o644)
            os.rename(stage, paths.release)
            _fsync_directory(paths.releases)
            try:
                os.link(unit_stage, paths.unit)
            except OSError as exc:
                raise RelayAdminError("install_unit_conflict") from exc
            unit_stage.unlink()
            _fsync_directory(paths.unit.parent)
            release_target = f"releases/{plan.bundle.release_id}"
            os.symlink(release_target, paths.current)
            _fsync_directory(paths.current.parent)
            os.symlink(release_target, paths.controller)
            _fsync_directory(paths.controller.parent)
            os.symlink(_stable_launcher_target(paths), paths.stable_launcher)
            _fsync_directory(paths.stable_launcher.parent)
            _validate_installed_release(paths, plan.bundle)
            if not _root_path_matches(original_root, plan.root_fingerprint):
                raise RelayAdminError("plan_stale")
            paths.transaction.unlink()
            _fsync_directory(paths.transaction.parent)
        except (OSError, RelayAdminError) as exc:
            if not _rollback_install(plan, stage, unit_stage):
                raise RelayAdminError("recovery_required") from exc
            if isinstance(exc, RelayAdminError):
                raise
            raise RelayAdminError("install_publish_failed") from exc
    finally:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)


def _publish_install(plan: InstallPlan) -> None:
    if plan.no_op:
        return
    root_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        root_descriptor = os.open(plan.paths.root, root_flags)
    except OSError as exc:
        raise RelayAdminError("plan_stale") from exc
    cwd_descriptor = -1
    try:
        if _metadata_fingerprint(os.fstat(root_descriptor)) != plan.root_fingerprint:
            raise RelayAdminError("plan_stale")
        cwd_descriptor = os.open(".", root_flags)
        os.fchdir(root_descriptor)
        anchored_plan = _plan_for_install(Path("."), plan.bundle)
        if (
            anchored_plan.plan_sha256 != plan.plan_sha256
            or anchored_plan.root_fingerprint != plan.root_fingerprint
            or anchored_plan.no_op
        ):
            raise RelayAdminError("plan_stale")
        _publish_install_anchored(anchored_plan, plan.paths.root)
    except OSError as exc:
        raise RelayAdminError("install_publish_failed") from exc
    finally:
        if cwd_descriptor >= 0:
            try:
                os.fchdir(cwd_descriptor)
            finally:
                os.close(cwd_descriptor)
        os.close(root_descriptor)


def _status_directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _status_file_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _status_safe_native_name(name: str) -> None:
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\x00" in name
        or len(name) > 240
    ):
        raise RelayStatusInvalid
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RelayStatusInvalid from exc


def _status_open_directory_at(
    root_descriptor: int,
    parts: tuple[str, ...],
    *,
    missing_ok: bool,
) -> int | None:
    descriptor = os.dup(root_descriptor)
    try:
        for part in parts:
            _status_safe_native_name(part)
            try:
                child = os.open(
                    part,
                    _status_directory_flags(),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if missing_ok:
                    os.close(descriptor)
                    return None
                raise RelayStatusInvalid
            except OSError as exc:
                raise RelayStatusInvalid from exc
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _status_list_directory(descriptor: int) -> tuple[str, ...]:
    try:
        names = os.listdir(descriptor)
    except OSError as exc:
        raise RelayStatusInvalid from exc
    if len(names) > MAX_STATUS_DIRECTORY_ENTRIES:
        raise RelayStatusInvalid
    for name in names:
        _status_safe_native_name(name)
    return tuple(sorted(names))


def _status_lstat_at(
    root_descriptor: int,
    parts: tuple[str, ...],
) -> os.stat_result | None:
    if not parts:
        try:
            return os.fstat(root_descriptor)
        except OSError as exc:
            raise RelayStatusInvalid from exc
    parent = _status_open_directory_at(
        root_descriptor,
        parts[:-1],
        missing_ok=True,
    )
    if parent is None:
        return None
    try:
        _status_safe_native_name(parts[-1])
        try:
            return os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RelayStatusInvalid from exc
    finally:
        os.close(parent)


def _status_read_file_at(
    root_descriptor: int,
    parts: tuple[str, ...],
    *,
    maximum: int,
) -> StatusFile:
    parent = _status_open_directory_at(
        root_descriptor,
        parts[:-1],
        missing_ok=False,
    )
    if parent is None:
        raise RelayStatusInvalid
    descriptor = -1
    try:
        _status_safe_native_name(parts[-1])
        before = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise RelayStatusInvalid
        descriptor = os.open(parts[-1], _status_file_flags(), dir_fd=parent)
        opened = os.fstat(descriptor)
        if _status_file_fingerprint(before) != _status_file_fingerprint(opened):
            raise RelayStatusInvalid
        if opened.st_size < 0 or opened.st_size > maximum:
            raise RelayStatusInvalid
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise RelayStatusInvalid
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise RelayStatusInvalid
        after = os.fstat(descriptor)
        if _status_file_fingerprint(opened) != _status_file_fingerprint(after):
            raise RelayStatusInvalid
        return StatusFile(
            data=b"".join(chunks),
            gid=opened.st_gid,
            mode=stat.S_IMODE(opened.st_mode),
            nlink=opened.st_nlink,
            uid=opened.st_uid,
        )
    except RelayStatusInvalid:
        raise
    except OSError as exc:
        raise RelayStatusInvalid from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent)


def _status_read_symlink_at(
    root_descriptor: int,
    parts: tuple[str, ...],
    *,
    expected_uid: int,
    expected_gid: int,
) -> str:
    parent = _status_open_directory_at(
        root_descriptor,
        parts[:-1],
        missing_ok=False,
    )
    if parent is None:
        raise RelayStatusInvalid
    try:
        _status_safe_native_name(parts[-1])
        metadata = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or metadata.st_gid != expected_gid
        ):
            raise RelayStatusInvalid
        target = os.readlink(parts[-1], dir_fd=parent)
        if len(target) > 240 or "\x00" in target:
            raise RelayStatusInvalid
        after = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if _status_file_fingerprint(metadata) != _status_file_fingerprint(after):
            raise RelayStatusInvalid
        return target
    except RelayStatusInvalid:
        raise
    except OSError as exc:
        raise RelayStatusInvalid from exc
    finally:
        os.close(parent)


def _status_validate_directory_at(
    root_descriptor: int,
    parts: tuple[str, ...],
    *,
    expected_uid: int,
    expected_gid: int,
    expected_mode: int,
    expected_names: set[str] | None = None,
) -> tuple[str, ...]:
    descriptor = _status_open_directory_at(
        root_descriptor,
        parts,
        missing_ok=False,
    )
    if descriptor is None:
        raise RelayStatusInvalid
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != expected_uid
            or metadata.st_gid != expected_gid
            or stat.S_IMODE(metadata.st_mode) != expected_mode
        ):
            raise RelayStatusInvalid
        names = _status_list_directory(descriptor)
        if expected_names is not None and set(names) != expected_names:
            raise RelayStatusInvalid
        return names
    finally:
        os.close(descriptor)


def _status_validate_safe_parent_chain(
    root_descriptor: int,
    parts: tuple[str, ...],
    *,
    expected_uid: int,
    expected_gid: int,
) -> None:
    descriptor = os.dup(root_descriptor)
    try:
        for part in parts:
            _status_safe_native_name(part)
            try:
                child = os.open(
                    part,
                    _status_directory_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise RelayStatusInvalid from exc
            try:
                metadata = os.fstat(child)
                if (
                    not stat.S_ISDIR(metadata.st_mode)
                    or metadata.st_uid != expected_uid
                    or metadata.st_gid != expected_gid
                    or stat.S_IMODE(metadata.st_mode) & 0o022
                ):
                    raise RelayStatusInvalid
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
    finally:
        os.close(descriptor)


def _status_recovery_marker_count(root_descriptor: int) -> int:
    scans = (
        (
            ("var", "lib", "agentops-relayctl"),
            lambda name: name == "transaction.json"
            or (name.startswith(".transaction-") and name.endswith(".tmp")),
        ),
        (
            ("opt", "agentops-mis-relay", "releases"),
            lambda name: name.startswith(".installing-"),
        ),
        (
            ("etc", "systemd", "system"),
            lambda name: name.startswith(f".{UNIT_NAME}.")
            and name.endswith(".tmp"),
        ),
    )
    count = 0
    invalid_parent = False
    for parts, predicate in scans:
        try:
            descriptor = _status_open_directory_at(
                root_descriptor,
                parts,
                missing_ok=True,
            )
            if descriptor is None:
                continue
            try:
                names = _status_list_directory(descriptor)
            finally:
                os.close(descriptor)
            count += sum(1 for name in names if predicate(name))
        except RelayStatusInvalid:
            invalid_parent = True
    if count:
        return count
    if invalid_parent:
        raise RelayStatusInvalid
    return 0


def _status_scan_release_tree(
    root_descriptor: int,
    release_parts: tuple[str, ...],
    *,
    expected_uid: int,
    expected_gid: int,
) -> tuple[dict[str, StatusFile], set[str]]:
    root = _status_open_directory_at(
        root_descriptor,
        release_parts,
        missing_ok=False,
    )
    if root is None:
        raise RelayStatusInvalid
    files: dict[str, StatusFile] = {}
    directories: set[str] = set()
    total_bytes = 0

    def scan(descriptor: int, relative: tuple[str, ...]) -> None:
        nonlocal total_bytes
        metadata = os.fstat(descriptor)
        if (
            metadata.st_uid != expected_uid
            or metadata.st_gid != expected_gid
            or stat.S_IMODE(metadata.st_mode) != 0o755
        ):
            raise RelayStatusInvalid
        relative_name = PurePosixPath(*relative).as_posix() if relative else ""
        directories.add(relative_name)
        if len(directories) > MAX_STATUS_RELEASE_DIRECTORIES:
            raise RelayStatusInvalid
        names = _status_list_directory(descriptor)
        for name in names:
            observed = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            child_relative = (*relative, name)
            child_name = PurePosixPath(*child_relative).as_posix()
            if stat.S_ISDIR(observed.st_mode):
                try:
                    child = os.open(
                        name,
                        _status_directory_flags(),
                        dir_fd=descriptor,
                    )
                except OSError as exc:
                    raise RelayStatusInvalid from exc
                try:
                    opened = os.fstat(child)
                    if (observed.st_dev, observed.st_ino) != (
                        opened.st_dev,
                        opened.st_ino,
                    ):
                        raise RelayStatusInvalid
                    scan(child, child_relative)
                finally:
                    os.close(child)
                continue
            if not stat.S_ISREG(observed.st_mode):
                raise RelayStatusInvalid
            expected_mode = 0o755 if child_name == "bin/agentops-relay" else 0o644
            if (
                observed.st_uid != expected_uid
                or observed.st_gid != expected_gid
                or stat.S_IMODE(observed.st_mode) != expected_mode
                or observed.st_nlink != 1
            ):
                raise RelayStatusInvalid
            if len(files) >= MAX_STATUS_RELEASE_FILES:
                raise RelayStatusInvalid
            try:
                child = os.open(
                    name,
                    _status_file_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise RelayStatusInvalid from exc
            try:
                opened = os.fstat(child)
                if _status_file_fingerprint(observed) != _status_file_fingerprint(
                    opened
                ):
                    raise RelayStatusInvalid
                if (
                    opened.st_size < 0
                    or opened.st_size > MAX_WHEEL_MEMBER_SIZE
                    or total_bytes + opened.st_size > MAX_STATUS_RELEASE_BYTES
                ):
                    raise RelayStatusInvalid
                chunks: list[bytes] = []
                remaining = opened.st_size
                while remaining:
                    chunk = os.read(child, min(1024 * 1024, remaining))
                    if not chunk:
                        raise RelayStatusInvalid
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(child, 1):
                    raise RelayStatusInvalid
                after = os.fstat(child)
                if _status_file_fingerprint(opened) != _status_file_fingerprint(
                    after
                ):
                    raise RelayStatusInvalid
                data = b"".join(chunks)
            finally:
                os.close(child)
            total_bytes += len(data)
            files[child_name] = StatusFile(
                data=data,
                gid=opened.st_gid,
                mode=stat.S_IMODE(opened.st_mode),
                nlink=opened.st_nlink,
                uid=opened.st_uid,
            )

    try:
        scan(root, ())
    finally:
        os.close(root)
    return files, directories


def _status_release_metadata(data: bytes) -> dict[str, Any]:
    try:
        metadata = _parse_json(data)
    except RelayAdminError as exc:
        raise RelayStatusInvalid from exc
    required = {
        "archive_sha256",
        "bundle_schema",
        "git_commit",
        "installed_file_count",
        "launcher_sha256",
        "manifest_sha256",
        "release_id",
        "schema",
        "unit_sha256",
        "version",
        "wheel_member_count",
        "wheel_sha256",
    }
    if (
        not isinstance(metadata, dict)
        or set(metadata) != required
        or data != _canonical_json(metadata)
        or metadata.get("schema") != INSTALLED_SCHEMA
        or metadata.get("bundle_schema") != BUNDLE_SCHEMA
    ):
        raise RelayStatusInvalid
    version = metadata.get("version")
    commit = metadata.get("git_commit")
    release_id = metadata.get("release_id")
    if (
        not isinstance(version, str)
        or not VERSION_PATTERN.fullmatch(version)
        or not isinstance(commit, str)
        or not COMMIT_PATTERN.fullmatch(commit)
        or not isinstance(release_id, str)
        or release_id != f"{version}-{commit[:12]}"
        or not RELEASE_ID_PATTERN.fullmatch(release_id)
    ):
        raise RelayStatusInvalid
    for name in (
        "archive_sha256",
        "launcher_sha256",
        "manifest_sha256",
        "unit_sha256",
        "wheel_sha256",
    ):
        value = metadata.get(name)
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            raise RelayStatusInvalid
    for name in ("installed_file_count", "wheel_member_count"):
        value = metadata.get(name)
        if type(value) is not int or value <= 0 or value > MAX_STATUS_RELEASE_FILES:
            raise RelayStatusInvalid
    if metadata["launcher_sha256"] != _sha256(_launcher_data()):
        raise RelayStatusInvalid
    return metadata


def _status_validate_site_packages(
    site_files: dict[str, bytes],
    *,
    version: str,
    wheel_member_count: int,
) -> None:
    dist_info = f"agentops_mis_cli-{version}.dist-info"
    expected_dist_info = {
        f"{dist_info}/METADATA",
        f"{dist_info}/RECORD",
        f"{dist_info}/WHEEL",
        f"{dist_info}/entry_points.txt",
    }
    package_members = {
        name for name in site_files if PACKAGE_MEMBER_PATTERN.fullmatch(name)
    }
    dist_info_members = {
        name
        for name in site_files
        if PurePosixPath(name).parts[0] == dist_info
    }
    if (
        package_members != EXPECTED_WHEEL_MODULES
        or dist_info_members != expected_dist_info
        or set(site_files) != EXPECTED_WHEEL_MODULES | expected_dist_info
        or wheel_member_count != len(site_files)
        or any(
            len(site_files[name]) > MAX_METADATA_SIZE
            for name in expected_dist_info
        )
    ):
        raise RelayStatusInvalid
    entries = tuple(
        WheelEntry(name=name, data=data)
        for name, data in sorted(site_files.items())
    )
    expected_metadata = "\n".join(
        [
            "Metadata-Version: 2.2",
            "Name: agentops-mis-cli",
            f"Version: {version}",
            "Summary: Installable AgentOps MIS Agent Gateway CLI wrapper.",
            "Requires-Python: >=3.10",
            "License: Proprietary local MVP",
            "",
        ]
    ).encode("utf-8")
    expected_wheel_metadata = "\n".join(
        [
            "Wheel-Version: 1.0",
            "Generator: agentops-mis-cli offline backend",
            "Root-Is-Purelib: true",
            "Tag: py3-none-any",
            "",
        ]
    ).encode("utf-8")
    expected_entry_points = "\n".join(
        [
            "[console_scripts]",
            "agentops = agentops_mis_cli.cli:main",
            "agentops-relay = agentops_mis_cli.relay_daemon:main",
            "agentops-relayctl = agentops_mis_cli.relay_admin:main",
            "agentops-worker = agentops_mis_cli.worker:main",
            "",
        ]
    ).encode("utf-8")
    try:
        metadata = _metadata_fields(
            site_files[f"{dist_info}/METADATA"],
            "installed_state_invalid",
        )
        wheel_metadata = _metadata_fields(
            site_files[f"{dist_info}/WHEEL"],
            "installed_state_invalid",
        )
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.optionxform = str
        parser.read_string(
            site_files[f"{dist_info}/entry_points.txt"].decode("utf-8")
        )
        scripts = dict(parser.items("console_scripts"))
        _validate_wheel_record(entries, f"{dist_info}/RECORD")
    except (
        KeyError,
        UnicodeDecodeError,
        configparser.Error,
        configparser.NoSectionError,
        RelayAdminError,
    ) as exc:
        raise RelayStatusInvalid from exc
    if (
        metadata.get("Metadata-Version") != "2.2"
        or metadata.get("Name") != "agentops-mis-cli"
        or metadata.get("Version") != version
        or site_files[f"{dist_info}/METADATA"] != expected_metadata
        or wheel_metadata.get("Wheel-Version") != "1.0"
        or wheel_metadata.get("Root-Is-Purelib") != "true"
        or wheel_metadata.get("Tag") != "py3-none-any"
        or site_files[f"{dist_info}/WHEEL"] != expected_wheel_metadata
        or site_files[f"{dist_info}/entry_points.txt"] != expected_entry_points
        or parser.sections() != ["console_scripts"]
        or scripts
        != {
            "agentops": "agentops_mis_cli.cli:main",
            "agentops-relay": "agentops_mis_cli.relay_daemon:main",
            "agentops-relayctl": "agentops_mis_cli.relay_admin:main",
            "agentops-worker": "agentops_mis_cli.worker:main",
        }
    ):
        raise RelayStatusInvalid


def _status_expected_directories(file_names: set[str]) -> set[str]:
    directories = {""}
    for name in file_names:
        path = PurePosixPath(name)
        for parent in path.parents:
            if parent != PurePosixPath("."):
                directories.add(parent.as_posix())
    return directories


def _status_installed_valid(
    root_descriptor: int,
    *,
    expected_uid: int,
    expected_gid: int,
) -> dict[str, object]:
    opt_parts = ("opt", "agentops-mis-relay")
    releases_parts = (*opt_parts, "releases")
    for chain in (
        releases_parts,
        ("usr", "local", "bin"),
        ("etc", "systemd", "system"),
        ("var", "lib", "agentops-relayctl"),
    ):
        _status_validate_safe_parent_chain(
            root_descriptor,
            chain,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    opt_names = _status_validate_directory_at(
        root_descriptor,
        opt_parts,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_mode=0o755,
        expected_names={"controller", "current", "releases"},
    )
    del opt_names
    releases_descriptor = _status_open_directory_at(
        root_descriptor,
        releases_parts,
        missing_ok=False,
    )
    if releases_descriptor is None:
        raise RelayStatusInvalid
    try:
        releases_metadata = os.fstat(releases_descriptor)
        release_names = _status_list_directory(releases_descriptor)
    finally:
        os.close(releases_descriptor)
    if (
        releases_metadata.st_uid != expected_uid
        or releases_metadata.st_gid != expected_gid
        or stat.S_IMODE(releases_metadata.st_mode) != 0o755
        or len(release_names) != 1
        or not RELEASE_ID_PATTERN.fullmatch(release_names[0])
    ):
        raise RelayStatusInvalid
    release_id = release_names[0]
    expected_release_target = f"releases/{release_id}"
    if (
        _status_read_symlink_at(
            root_descriptor,
            (*opt_parts, "current"),
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        != expected_release_target
        or _status_read_symlink_at(
            root_descriptor,
            (*opt_parts, "controller"),
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        != expected_release_target
    ):
        raise RelayStatusInvalid
    stable_parts = ("usr", "local", "bin", LAUNCHER_NAME)
    stable_target = "../../../opt/agentops-mis-relay/current/bin/agentops-relay"
    if (
        _status_read_symlink_at(
            root_descriptor,
            stable_parts,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        != stable_target
    ):
        raise RelayStatusInvalid
    admin_parts = ("var", "lib", "agentops-relayctl")
    _status_validate_directory_at(
        root_descriptor,
        admin_parts,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        expected_mode=0o700,
        expected_names={"lifecycle.lock"},
    )
    lifecycle = _status_read_file_at(
        root_descriptor,
        (*admin_parts, "lifecycle.lock"),
        maximum=0,
    )
    if (
        lifecycle.data
        or lifecycle.mode != 0o600
        or lifecycle.uid != expected_uid
        or lifecycle.gid != expected_gid
        or lifecycle.nlink != 1
    ):
        raise RelayStatusInvalid
    release_parts = (*releases_parts, release_id)
    release_files, release_directories = _status_scan_release_tree(
        root_descriptor,
        release_parts,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    try:
        release_json = release_files["release.json"].data
        launcher = release_files["bin/agentops-relay"].data
        release_unit = release_files[f"systemd/{UNIT_NAME}"].data
    except KeyError as exc:
        raise RelayStatusInvalid from exc
    metadata = _status_release_metadata(release_json)
    if metadata["release_id"] != release_id:
        raise RelayStatusInvalid
    site_prefix = "private/site-packages/"
    site_files = {
        name[len(site_prefix) :]: observed.data
        for name, observed in release_files.items()
        if name.startswith(site_prefix)
    }
    _status_validate_site_packages(
        site_files,
        version=metadata["version"],
        wheel_member_count=metadata["wheel_member_count"],
    )
    expected_release_files = {
        "bin/agentops-relay",
        "release.json",
        f"systemd/{UNIT_NAME}",
        *(f"{site_prefix}{name}" for name in site_files),
    }
    if (
        set(release_files) != expected_release_files
        or release_directories
        != _status_expected_directories(expected_release_files)
        or metadata["installed_file_count"] != len(release_files)
        or metadata["installed_file_count"] != len(site_files) + 3
        or launcher != _launcher_data()
        or _sha256(launcher) != metadata["launcher_sha256"]
        or _sha256(release_unit) != metadata["unit_sha256"]
    ):
        raise RelayStatusInvalid
    installed_unit = _status_read_file_at(
        root_descriptor,
        ("etc", "systemd", "system", UNIT_NAME),
        maximum=MAX_METADATA_SIZE,
    )
    if (
        installed_unit.data != release_unit
        or _sha256(installed_unit.data) != metadata["unit_sha256"]
        or installed_unit.mode != 0o644
        or installed_unit.uid != expected_uid
        or installed_unit.gid != expected_gid
        or installed_unit.nlink != 1
    ):
        raise RelayStatusInvalid
    return {
        "installed": True,
        "ok": True,
        "operation_id": "status",
        "provenance_archive_sha256": metadata["archive_sha256"],
        "provenance_git_commit": metadata["git_commit"],
        "provenance_manifest_sha256": metadata["manifest_sha256"],
        "provenance_only": True,
        "provenance_wheel_sha256": metadata["wheel_sha256"],
        "record_integrity_valid": True,
        "relationships_valid": True,
        "release_directory_count": len(release_directories),
        "release_file_count": len(release_files),
        "release_id": release_id,
        "schema_id": STATUS_SCHEMA,
        "site_package_file_count": len(site_files),
        "state_id": "installed_valid",
        "version_id": metadata["version"],
    }


def _status_absent_or_scaffolding(
    root_descriptor: int,
    *,
    expected_uid: int,
    expected_gid: int,
) -> bool:
    stable = _status_lstat_at(
        root_descriptor,
        ("usr", "local", "bin", LAUNCHER_NAME),
    )
    unit = _status_lstat_at(
        root_descriptor,
        ("etc", "systemd", "system", UNIT_NAME),
    )
    if stable is not None or unit is not None:
        return False
    opt_parts = ("opt", "agentops-mis-relay")
    opt = _status_lstat_at(root_descriptor, opt_parts)
    if opt is not None:
        if not stat.S_ISDIR(opt.st_mode):
            return False
        _status_validate_safe_parent_chain(
            root_descriptor,
            opt_parts,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        opt_names = _status_validate_directory_at(
            root_descriptor,
            opt_parts,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_mode=0o755,
        )
        if set(opt_names) not in (set(), {"releases"}):
            return False
        if "releases" in opt_names:
            _status_validate_safe_parent_chain(
                root_descriptor,
                (*opt_parts, "releases"),
                expected_uid=expected_uid,
                expected_gid=expected_gid,
            )
            _status_validate_directory_at(
                root_descriptor,
                (*opt_parts, "releases"),
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_mode=0o755,
                expected_names=set(),
            )
    admin_parts = ("var", "lib", "agentops-relayctl")
    admin = _status_lstat_at(root_descriptor, admin_parts)
    if admin is not None:
        if not stat.S_ISDIR(admin.st_mode):
            return False
        _status_validate_safe_parent_chain(
            root_descriptor,
            admin_parts,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
        admin_names = _status_validate_directory_at(
            root_descriptor,
            admin_parts,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_mode=0o700,
        )
        if set(admin_names) not in (set(), {"lifecycle.lock"}):
            return False
        if "lifecycle.lock" in admin_names:
            lifecycle = _status_read_file_at(
                root_descriptor,
                (*admin_parts, "lifecycle.lock"),
                maximum=0,
            )
            if (
                lifecycle.data
                or lifecycle.mode != 0o600
                or lifecycle.uid != expected_uid
                or lifecycle.gid != expected_gid
                or lifecycle.nlink != 1
            ):
                raise RelayStatusInvalid
    return True


def _status_scan_anchored(root_descriptor: int) -> tuple[dict[str, object], int]:
    root_metadata = os.fstat(root_descriptor)
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(root_metadata.st_mode) & 0o022
    ):
        raise RelayStatusInvalid
    marker_count = _status_recovery_marker_count(root_descriptor)
    if marker_count:
        return (
            {
                "installed": False,
                "ok": False,
                "operation_id": "status",
                "recovery_marker_count": marker_count,
                "recovery_required": True,
                "schema_id": STATUS_SCHEMA,
                "state_id": "recovery_required",
            },
            1,
        )
    if _status_absent_or_scaffolding(
        root_descriptor,
        expected_uid=root_metadata.st_uid,
        expected_gid=root_metadata.st_gid,
    ):
        return (
            {
                "installed": False,
                "ok": True,
                "operation_id": "status",
                "recovery_required": False,
                "schema_id": STATUS_SCHEMA,
                "state_id": "absent",
            },
            0,
        )
    return (
        _status_installed_valid(
            root_descriptor,
            expected_uid=root_metadata.st_uid,
            expected_gid=root_metadata.st_gid,
        ),
        0,
    )


def relay_status(root: Path) -> tuple[dict[str, object], int]:
    if not root.is_absolute():
        return (
            {
                "installed": False,
                "ok": False,
                "operation_id": "status",
                "schema_id": STATUS_SCHEMA,
                "state_id": "invalid",
            },
            1,
        )
    cwd_descriptor = -1
    root_descriptor = -1
    result: tuple[dict[str, object], int] | None = None
    restore_failed = False
    try:
        cwd_descriptor = os.open(".", _status_directory_flags())
        root_descriptor = os.open(root, _status_directory_flags())
        root_fingerprint = _metadata_fingerprint(os.fstat(root_descriptor))
        os.fchdir(root_descriptor)
        result = _status_scan_anchored(root_descriptor)
        held_root = os.fstat(root_descriptor)
        current_root = os.stat(root, follow_symlinks=False)
        if (
            not stat.S_ISDIR(current_root.st_mode)
            or _metadata_fingerprint(held_root) != root_fingerprint
            or _metadata_fingerprint(current_root) != root_fingerprint
        ):
            raise RelayStatusInvalid
    except Exception:
        result = (
            {
                "installed": False,
                "ok": False,
                "operation_id": "status",
                "schema_id": STATUS_SCHEMA,
                "state_id": "invalid",
            },
            1,
        )
    finally:
        if cwd_descriptor >= 0:
            try:
                os.fchdir(cwd_descriptor)
            except OSError:
                restore_failed = True
            finally:
                try:
                    os.close(cwd_descriptor)
                except OSError:
                    restore_failed = True
        if root_descriptor >= 0:
            try:
                os.close(root_descriptor)
            except OSError:
                restore_failed = True
    if restore_failed or result is None:
        return (
            {
                "installed": False,
                "ok": False,
                "operation_id": "status",
                "schema_id": STATUS_SCHEMA,
                "state_id": "invalid",
            },
            1,
        )
    return result


def _inspect_output(bundle: RelayBundle) -> dict[str, object]:
    return {
        "archive_member_count": bundle.archive_member_count,
        "archive_safe": True,
        "bundle_file_count": bundle.bundle_file_count,
        "bundle_sha256": bundle.archive_sha256,
        "checksums_verified": True,
        "git_commit": bundle.git_commit,
        "manifest_sha256": bundle.manifest_sha256,
        "ok": True,
        "operation_id": "inspect",
        "release_id": bundle.release_id,
        "schema_id": bundle.schema,
        "version_id": bundle.version,
        "wheel_member_count": bundle.wheel_member_count,
        "wheel_safe": True,
        "wheel_sha256": bundle.wheel_sha256,
    }


def _install_output(
    plan: InstallPlan,
    *,
    confirmed: bool,
) -> dict[str, object]:
    return {
        "bundle_file_count": plan.bundle.bundle_file_count,
        "bundle_sha256": plan.bundle.archive_sha256,
        "confirmed": confirmed,
        "dry_run": not confirmed,
        "git_commit": plan.bundle.git_commit,
        "installed": confirmed and not plan.no_op,
        "no_op": plan.no_op,
        "ok": True,
        "operation_id": "install",
        "plan_sha256": plan.plan_sha256,
        "release_id": plan.bundle.release_id,
        "schema_id": PLAN_SCHEMA,
        "version_id": plan.bundle.version,
    }


def _build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="agentops-relayctl", description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"))
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("status")
    for name in ("inspect", "install"):
        command = subparsers.add_parser(name)
        command.add_argument("--bundle", type=Path, required=True)
        command.add_argument("--expect-sha256", required=True)
        if name == "install":
            command.add_argument("--confirm-install", action="store_true")
            command.add_argument("--plan-sha256")
    return parser


def _operation_id(argv: list[str]) -> str:
    for value in argv:
        if value in {"inspect", "install", "status"}:
            return value
    return "cli"


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    operation_id = _operation_id(arguments)
    try:
        args = _build_parser().parse_args(arguments)
        operation_id = args.operation
        if args.operation == "status":
            output, status_code = relay_status(args.root)
            print(
                json.dumps(output, ensure_ascii=True, indent=2, sort_keys=True),
                file=sys.stdout,
            )
            return status_code
        bundle = inspect_bundle(args.bundle, args.expect_sha256)
        if args.operation == "inspect":
            _resolve_root(args.root)
            output = _inspect_output(bundle)
        else:
            root = _resolve_root(args.root)
            supplied_plan = args.plan_sha256
            if args.confirm_install:
                if not isinstance(supplied_plan, str) or not SHA256_PATTERN.fullmatch(
                    supplied_plan
                ):
                    raise RelayAdminError("plan_sha256_required")
            elif supplied_plan is not None:
                raise RelayAdminError("confirmation_required")
            plan = _plan_for_install(root, bundle)
            if args.confirm_install:
                if supplied_plan != plan.plan_sha256:
                    raise RelayAdminError("plan_sha256_mismatch")
                _publish_install(plan)
            output = _install_output(plan, confirmed=args.confirm_install)
    except RelayAdminError as exc:
        output = {
            "error_id": exc.error_id,
            "ok": False,
            "operation_id": operation_id,
        }
        if exc.future_operation_id is not None:
            output["future_operation_id"] = exc.future_operation_id
        print(json.dumps(output, ensure_ascii=True, sort_keys=True), file=sys.stderr)
        return 1
    except Exception:
        # The root-facing CLI is a redaction boundary; never print exception text.
        output = {
            "error_id": "internal_error",
            "ok": False,
            "operation_id": operation_id,
        }
        print(json.dumps(output, ensure_ascii=True, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(output, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
