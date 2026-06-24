from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from .redaction import is_sensitive_key


class ProvenanceError(ValueError):
    """Raised when experiment provenance is incomplete or unsafe."""


_SAFE_NAME = re.compile(r"^[A-Za-z0-9._:/+-]+$")
_DIGEST = re.compile(r"^[A-Za-z0-9._-]+:[A-Fa-f0-9]{8,}$")
_INIT_WITH_MODEL = {
    "official_checkpoint",
    "previous_checkpoint",
    "pretrained_backbone",
    "pretrained_model",
    "fine_tune",
    "finetune",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _validate_tree(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_tree(child, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise ProvenanceError(f"{path} keys must be non-empty strings")
            if is_sensitive_key(key):
                raise ProvenanceError(f"{path}.{key} is not allowed in frozen provenance")
            _validate_tree(child, f"{path}.{key}")
        return
    raise ProvenanceError(f"{path} must contain JSON-compatible values")


def _stable_uri(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProvenanceError(f"{path} must be a non-empty string")
    uri = value.strip()
    if any(ch in uri for ch in ("\x00", "\n", "\r")):
        raise ProvenanceError(f"{path} contains control characters")
    parsed = urlsplit(uri)
    if parsed.username is not None or parsed.password is not None:
        raise ProvenanceError(f"{path} must not contain URL userinfo")
    if parsed.query or parsed.fragment:
        raise ProvenanceError(f"{path} must be stable and omit query/fragment data")
    if not parsed.scheme:
        pure = PurePosixPath(uri.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts:
            raise ProvenanceError(f"{path} must be a safe relative path or URI")
    return uri


def _non_empty_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProvenanceError(f"{path} must be a non-empty string")
    result = value.strip()
    if any(ch in result for ch in ("\x00", "\n", "\r")):
        raise ProvenanceError(f"{path} contains control characters")
    return result


@dataclass(frozen=True, slots=True)
class SourceReference:
    name: str
    kind: str
    uri: str
    version: str
    digest: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, kind: str, path: str) -> "SourceReference":
        if not isinstance(raw, dict):
            raise ProvenanceError(f"{path} must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not _SAFE_NAME.fullmatch(name):
            raise ProvenanceError(f"{path}.name contains unsupported characters")
        uri = _stable_uri(raw.get("uri"), f"{path}.uri")
        version = _non_empty_text(raw.get("version"), f"{path}.version")
        digest = raw.get("digest")
        if digest is not None and (not isinstance(digest, str) or not _DIGEST.fullmatch(digest)):
            raise ProvenanceError(f"{path}.digest must look like '<algorithm>:<hex>'")
        metadata = raw.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ProvenanceError(f"{path}.metadata must be an object")
        _validate_tree(metadata, f"{path}.metadata")
        return cls(name=name, kind=kind, uri=uri, version=version, digest=digest, metadata=dict(metadata))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "kind": self.kind, "uri": self.uri, "version": self.version}
        if self.digest:
            payload["digest"] = self.digest
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass(frozen=True, slots=True)
class CodeReference:
    repository: str
    revision: str
    dirty: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, path: str) -> "CodeReference":
        if not isinstance(raw, dict):
            raise ProvenanceError(f"{path} must be an object")
        repository = _stable_uri(raw.get("repository"), f"{path}.repository")
        revision = _non_empty_text(raw.get("revision"), f"{path}.revision")
        dirty = raw.get("dirty", False)
        if not isinstance(dirty, bool):
            raise ProvenanceError(f"{path}.dirty must be a boolean")
        return cls(repository=repository, revision=revision, dirty=dirty)

    def to_dict(self) -> dict[str, Any]:
        return {"repository": self.repository, "revision": self.revision, "dirty": self.dirty}


@dataclass(frozen=True, slots=True)
class ProvenanceSpec:
    code: CodeReference | None
    datasets: tuple[SourceReference, ...]
    models: tuple[SourceReference, ...]
    environment: SourceReference | None
    resolved_config: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "ProvenanceSpec":
        if raw in (None, {}):
            return cls(None, (), (), None, {})
        if not isinstance(raw, dict):
            raise ProvenanceError("provenance must be an object")
        code_raw = raw.get("code")
        code = None if code_raw is None else CodeReference.from_dict(code_raw, path="provenance.code")
        datasets_raw = raw.get("datasets", [])
        models_raw = raw.get("models", [])
        if not isinstance(datasets_raw, list) or not isinstance(models_raw, list):
            raise ProvenanceError("provenance.datasets/models must be lists")
        datasets = tuple(SourceReference.from_dict(item, kind="dataset", path=f"provenance.datasets[{index}]") for index, item in enumerate(datasets_raw))
        models = tuple(SourceReference.from_dict(item, kind="model", path=f"provenance.models[{index}]") for index, item in enumerate(models_raw))
        if len({item.name for item in datasets}) != len(datasets):
            raise ProvenanceError("provenance dataset names must be unique")
        if len({item.name for item in models}) != len(models):
            raise ProvenanceError("provenance model names must be unique")
        environment_raw = raw.get("environment")
        environment = None if environment_raw is None else SourceReference.from_dict(environment_raw, kind="environment", path="provenance.environment")
        resolved_config = raw.get("resolved_config", {})
        if not isinstance(resolved_config, dict):
            raise ProvenanceError("provenance.resolved_config must be an object")
        _validate_tree(resolved_config, "provenance.resolved_config")
        return cls(code=code, datasets=datasets, models=models, environment=environment, resolved_config=dict(resolved_config))

    @property
    def present(self) -> bool:
        return bool(self.code or self.datasets or self.models or self.environment or self.resolved_config)

    @property
    def resolved_config_hash(self) -> str | None:
        return _sha256_json(self.resolved_config) if self.resolved_config else None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "datasets": [item.to_dict() for item in self.datasets],
            "models": [item.to_dict() for item in self.models],
            "resolved_config": self.resolved_config,
        }
        if self.code is not None:
            payload["code"] = self.code.to_dict()
        if self.environment is not None:
            payload["environment"] = self.environment.to_dict()
        if self.resolved_config_hash:
            payload["resolved_config_hash"] = self.resolved_config_hash
        return payload

    @property
    def provenance_hash(self) -> str | None:
        return _sha256_json(self.to_dict()) if self.present else None

    def validate_for_protocol(self, protocol: dict[str, Any], *, require_provenance: bool) -> None:
        if not require_provenance:
            return
        if self.code is None:
            raise ProvenanceError("strict experiment stages require provenance.code")
        if self.code.dirty:
            raise ProvenanceError("strict experiment stages require a clean code revision")
        if not self.datasets:
            raise ProvenanceError("strict experiment stages require at least one dataset reference")
        if not self.resolved_config:
            raise ProvenanceError("strict experiment stages require a fully resolved configuration")
        initialization = str(protocol.get("initialization_mode") or "").lower()
        if initialization in _INIT_WITH_MODEL and not self.models:
            raise ProvenanceError("the declared initialization mode requires at least one model reference")
