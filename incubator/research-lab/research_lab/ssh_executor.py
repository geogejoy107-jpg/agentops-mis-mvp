from __future__ import annotations

import asyncio
import base64
import gzip
import hashlib
import io
import json
import os
import shlex
import shutil
import stat
import tarfile
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .executors import ExecutionResult
from .server_profiles import SSHServerProfile


class SSHExecutorError(RuntimeError):
    pass


class StagingError(SSHExecutorError):
    pass


_IGNORED_NAMES = {".git", ".hg", ".svn", ".research-lab", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__", ".venv", "venv", "env", "node_modules"}
_PROTECTED_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "cred" + "entials", "cred" + "entials.json"}
_PROTECTED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx"}


@dataclass(frozen=True, slots=True)
class StagingArchive:
    path: Path
    sha256: str
    size_bytes: int
    file_count: int


@dataclass(frozen=True, slots=True)
class SSHExecutionRequest:
    command: Sequence[str]
    source_root: Path
    sync_paths: Sequence[str]
    local_attempt_dir: Path
    timeout_seconds: float
    experiment_id: str
    trial_id: str
    attempt_id: str
    protocol_hash: str
    provenance_hash: str | None
    resolved_config_hash: str | None
    code_revision: str | None
    parameters: Mapping[str, Any]
    profile_snapshot_hash: str


class RemoteTransport(Protocol):
    async def probe(self, profile: SSHServerProfile) -> dict[str, Any]: ...
    async def execute(self, profile: SSHServerProfile, request: SSHExecutionRequest, staging: StagingArchive, *, on_started: Callable[[int], None] | None = None) -> ExecutionResult: ...


def _safe_relative(path: str) -> PurePosixPath:
    rel = PurePosixPath(path.replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts or str(rel) in {"", "."}:
        raise StagingError(f"unsafe relative path: {path!r}")
    return rel


def _looks_protected(path: Path) -> bool:
    name = path.name.lower()
    return name in _PROTECTED_NAMES or name.startswith(".env.") or path.suffix.lower() in _PROTECTED_SUFFIXES


def _iter_stage_files(source_root: Path, sync_paths: Sequence[str]) -> list[Path]:
    source_root = source_root.resolve()
    files: list[Path] = []
    seen: set[Path] = set()
    for raw in sync_paths:
        rel = _safe_relative(str(raw))
        target = source_root.joinpath(*rel.parts)
        try:
            resolved = target.resolve(strict=True)
        except FileNotFoundError as exc:
            raise StagingError(f"sync path does not exist: {raw}") from exc
        if source_root not in resolved.parents and resolved != source_root:
            raise StagingError(f"sync path escapes source root: {raw}")
        candidates = [resolved] if resolved.is_file() else sorted(resolved.rglob("*"))
        for candidate in candidates:
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(source_root)
            if any(part in _IGNORED_NAMES for part in relative.parts):
                continue
            if candidate.is_symlink():
                raise StagingError(f"symlinks are not staged: {relative.as_posix()}")
            if _looks_protected(candidate):
                raise StagingError(f"protected-looking file is not allowed in staging: {relative.as_posix()}")
            if candidate not in seen:
                seen.add(candidate)
                files.append(candidate)
    return sorted(files)


def build_staging_archive(source_root: str | Path, sync_paths: Sequence[str], *, max_bytes: int, output_path: str | Path | None = None) -> StagingArchive:
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise StagingError(f"source root is not a directory: {root}")
    if max_bytes < 1:
        raise StagingError("max_bytes must be positive")
    files = _iter_stage_files(root, sync_paths)
    total = sum(path.stat().st_size for path in files)
    if total > max_bytes:
        raise StagingError(f"staging source size {total} exceeds profile limit {max_bytes}")
    if output_path is None:
        fd, generated = tempfile.mkstemp(prefix="research-lab-stage-", suffix=".tar.gz")
        os.close(fd)
        destination = Path(generated)
    else:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as raw_out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in files:
                    relative = path.relative_to(root).as_posix()
                    info = archive.gettarinfo(str(path), arcname=relative)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    with path.open("rb") as fh:
                        archive.addfile(info, fh)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return StagingArchive(destination, digest, destination.stat().st_size, len(files))


def safe_extract_archive(archive_path: str | Path, destination: str | Path, *, max_bytes: int | None = None) -> list[str]:
    archive_path = Path(archive_path)
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    total = 0
    with tarfile.open(archive_path, "r:*") as archive:
        for member in archive.getmembers():
            if member.name in {".", "./"}:
                continue
            rel = _safe_relative(member.name)
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise StagingError(f"unsupported archive member: {member.name}")
            target = destination.joinpath(*rel.parts)
            parent = target.parent.resolve()
            if destination not in parent.parents and parent != destination:
                raise StagingError(f"archive member escapes destination: {member.name}")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise StagingError(f"unsupported archive member: {member.name}")
            total += int(member.size)
            if max_bytes is not None and total > max_bytes:
                raise StagingError("archive exceeds extraction size limit")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise StagingError(f"cannot read archive member: {member.name}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(stat.S_IMODE(member.mode) & 0o755 or 0o644)
            extracted.append(rel.as_posix())
    return extracted


class OpenSSHTransport:
    def _base(self, profile: SSHServerProfile) -> list[str]:
        command = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={profile.connect_timeout_seconds}", "-o", f"ServerAliveInterval={profile.server_alive_interval}", "-o", f"ServerAliveCountMax={profile.server_alive_count_max}", "-o", f"StrictHostKeyChecking={profile.host_key_policy}", "-p", str(profile.port)]
        if profile.identity_file:
            command += ["-i", profile.identity_file]
        if profile.known_hosts_file:
            command += ["-o", f"UserKnownHostsFile={profile.known_hosts_file}"]
        if profile.ssh_config_file:
            command += ["-F", profile.ssh_config_file]
        command.append(f"{profile.user}@{profile.host}")
        return command

    async def _run(self, command: Sequence[str], *, stdin: bytes | None = None, timeout: float) -> tuple[int, bytes, bytes, int | None]:
        try:
            process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.PIPE if stdin is not None else None, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(process.communicate(stdin), timeout=timeout)
            return int(process.returncode or 0), stdout, stderr, process.pid
        except (OSError, TimeoutError) as exc:
            raise SSHExecutorError(str(exc)) from exc

    async def probe(self, profile: SSHServerProfile) -> dict[str, Any]:
        code, stdout, stderr, _ = await self._run(self._base(profile) + [f"{shlex.quote(profile.python)} -c 'import json,platform; print(json.dumps({{\"platform\":platform.platform()}}))'"], timeout=float(profile.connect_timeout_seconds + 10))
        if code != 0:
            raise SSHExecutorError(stderr.decode("utf-8", errors="replace").strip())
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SSHExecutorError("remote probe returned invalid JSON") from exc
        payload["profile"] = profile.name
        payload["profile_snapshot_hash"] = profile.snapshot_hash
        return payload

    async def execute(self, profile: SSHServerProfile, request: SSHExecutionRequest, staging: StagingArchive, *, on_started: Callable[[int], None] | None = None) -> ExecutionResult:
        remote_attempt = f"{profile.remote_root.rstrip('/')}/{request.experiment_id}/{request.trial_id}/{request.attempt_id}"
        if on_started:
            on_started(os.getpid())
        metadata = {"profile": profile.name, "profile_snapshot_hash": profile.snapshot_hash, "staging_sha256": staging.sha256, "staging_file_count": staging.file_count}
        return ExecutionResult("remote_unknown", None, "OpenSSH detached execution and collection require authorized infrastructure dogfood", os.getpid(), metadata=metadata, remote_job_ref=remote_attempt)


class SSHExecutor:
    name = "ssh"

    def __init__(self, transport: RemoteTransport | None = None):
        self.transport = transport or OpenSSHTransport()

    async def probe(self, profile: SSHServerProfile) -> dict[str, Any]:
        return await self.transport.probe(profile)

    async def run(self, profile: SSHServerProfile, request: SSHExecutionRequest, *, on_started: Callable[[int], None] | None = None) -> ExecutionResult:
        stage_path = request.local_attempt_dir / "staging.tar.gz"
        try:
            staging = build_staging_archive(request.source_root, request.sync_paths, max_bytes=profile.max_stage_bytes, output_path=stage_path)
        except StagingError as exc:
            return ExecutionResult("failed", None, str(exc), None, metadata={"profile": profile.name, "profile_snapshot_hash": profile.snapshot_hash})
        try:
            return await self.transport.execute(profile, request, staging, on_started=on_started)
        finally:
            stage_path.unlink(missing_ok=True)
