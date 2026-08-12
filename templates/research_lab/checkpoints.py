"""Framework-neutral checkpoints plus a safe PyTorch adapter."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import ResearchError, canonical_hash


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class CheckpointDescriptor:
    checkpoint_id: str
    path: str
    framework: str
    sha256: str
    size_bytes: int
    protocol_hash: str
    code_commit: str
    step: int
    compatibility: Mapping[str, str]

    @property
    def receipt_hash(self) -> str:
        return canonical_hash({field: getattr(self, field) for field in self.__dataclass_fields__})


class CheckpointCatalog:
    def discover(self, root: Path, *, suffixes: Sequence[str] = (".pt", ".pth", ".ckpt")) -> tuple[Path, ...]:
        if not root.is_absolute() or not root.is_dir():
            raise ResearchError("research.checkpoint_root_invalid", "checkpoint root must be an existing absolute directory")
        found = []
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ResearchError("research.checkpoint_symlink", "checkpoint symlinks are forbidden")
            if path.is_file() and path.suffix.lower() in suffixes:
                found.append(path)
        return tuple(sorted(found))

    def describe(self, path: Path, *, protocol_hash: str, code_commit: str, step: int, compatibility: Mapping[str, str]) -> CheckpointDescriptor:
        if not path.is_file() or path.is_symlink() or step < 0:
            raise ResearchError("research.checkpoint_invalid", "checkpoint must be a regular file and step non-negative")
        required = {"torch_version", "python_version", "model_schema_hash", "optimizer_schema_hash"}
        if required - compatibility.keys() or any(not str(compatibility[key]).strip() for key in required):
            raise ResearchError("research.checkpoint_compatibility_incomplete", "checkpoint compatibility must bind framework, Python, model and optimizer schemas")
        digest = hash_file(path)
        return CheckpointDescriptor(checkpoint_id=f"ckp_{digest[:20]}", path=str(path.resolve(strict=True)), framework="pytorch", sha256=digest, size_bytes=path.stat().st_size, protocol_hash=protocol_hash, code_commit=code_commit, step=step, compatibility=dict(compatibility))

    def latest_valid(self, descriptors: Sequence[CheckpointDescriptor], *, protocol_hash: str, code_commit: str, expected_compatibility: Mapping[str, str] | None = None) -> CheckpointDescriptor:
        compatible = []
        for item in descriptors:
            path = Path(item.path)
            if item.protocol_hash != protocol_hash or item.code_commit != code_commit or not path.is_absolute() or not path.is_file() or path.is_symlink():
                continue
            if path.stat().st_size != item.size_bytes or hash_file(path) != item.sha256:
                continue
            if expected_compatibility is not None and any(item.compatibility.get(key) != value for key, value in expected_compatibility.items()):
                continue
            try:
                observed = PyTorchCheckpointAdapter.validate_container(path)
            except ResearchError:
                continue
            if observed.get("sha256") != item.sha256:
                continue
            compatible.append(item)
        if not compatible:
            raise ResearchError("research.checkpoint_incompatible", "no valid checkpoint matches protocol and code commit")
        return max(compatible, key=lambda item: item.step)

    @staticmethod
    def resume_command(descriptor: CheckpointDescriptor, base_argv: Sequence[str]) -> tuple[str, ...]:
        if any(part in {"--resume", "--checkpoint"} for part in base_argv):
            raise ResearchError("research.resume_conflict", "base command already specifies resume state")
        return (*base_argv, "--resume", descriptor.path, "--checkpoint-sha256", descriptor.sha256)


class PyTorchCheckpointAdapter:
    """Validate modern zip checkpoints without executing pickle payloads."""

    @staticmethod
    def validate_container(path: Path, *, maximum_bytes: int = 10 * 1024**3) -> Mapping[str, Any]:
        if not path.is_file() or path.is_symlink():
            raise ResearchError("research.checkpoint_invalid", "checkpoint must be a regular file")
        if path.stat().st_size > maximum_bytes:
            raise ResearchError("research.checkpoint_too_large", "checkpoint exceeds configured limit")
        if not zipfile.is_zipfile(path):
            raise ResearchError("research.checkpoint_legacy_pickle_denied", "legacy pickle checkpoints require a separately approved sandbox conversion")
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if not names or any(name.startswith("/") or ".." in Path(name).parts for name in names):
                    raise ResearchError("research.checkpoint_corrupt", "checkpoint archive contains unsafe members")
                uncompressed = sum(item.file_size for item in archive.infolist())
                compressed = max(1, sum(item.compress_size for item in archive.infolist()))
                if uncompressed > maximum_bytes or uncompressed / compressed > 1000:
                    raise ResearchError("research.checkpoint_archive_bomb", "checkpoint archive exceeds expansion limits")
                bad = archive.testzip()
                if bad is not None:
                    raise ResearchError("research.checkpoint_corrupt", f"checkpoint archive failed CRC at {bad}")
        except (OSError, zipfile.BadZipFile) as exc:
            raise ResearchError("research.checkpoint_corrupt", "checkpoint archive cannot be read") from exc
        receipt = {"framework": "pytorch", "format": "zip", "sha256": hash_file(path), "size_bytes": path.stat().st_size, "uncompressed_bytes": uncompressed, "member_count": len(names), "deserialization_performed": False}
        return {**receipt, "receipt_hash": canonical_hash(receipt)}

    @staticmethod
    def compatibility(metadata: Mapping[str, Any], expected: Mapping[str, str]) -> Mapping[str, Any]:
        mismatches = {key: {"expected": value, "actual": metadata.get(key)} for key, value in expected.items() if metadata.get(key) != value}
        result = {"compatible": not mismatches, "mismatches": mismatches}
        return {**result, "receipt_hash": canonical_hash(result)}
