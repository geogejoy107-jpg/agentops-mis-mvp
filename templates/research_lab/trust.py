"""Cryptographic MIS Core receipt verification for the Research domain.

The domain never treats caller-supplied booleans or a self-computed content
hash as authority.  C0 injects a bounded trust store whose keys can be revoked.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any, Mapping

from .contracts import ResearchError, canonical_hash


_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_KEY = re.compile(r"(?:^|[_-])(?:token|secret|password|passwd|api[_-]?key|private[_-]?key|credential)(?:$|[_-])", re.I)
_SECRET_VALUE = re.compile(r"(?:^|\b)(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|Bearer\s+\S+|agtok_\S+|agtsess_\S+)", re.I)


def _signed_document(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key not in {"receipt_hash", "signature"}}


@dataclass(frozen=True, slots=True)
class CoreTrustStore:
    """Process-local public trust configuration supplied by C0.

    HMAC is the initial local/private-host verifier.  A production remote Core
    can implement the same receipt envelope with an asymmetric verifier in C0;
    domain code never receives or persists the key.
    """

    keys: Mapping[str, bytes]
    revoked_key_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.keys:
            raise ResearchError("research.core_trust_empty", "at least one Core verification key is required")
        for key_id, key in self.keys.items():
            if not _KEY_ID.fullmatch(key_id) or not isinstance(key, bytes) or len(key) < 32:
                raise ResearchError("research.core_trust_invalid", "Core trust keys require a safe id and at least 256 bits")

    def verify(self, receipt: Mapping[str, Any], *, purpose: str) -> None:
        key_id = str(receipt.get("key_id") or "")
        if key_id in self.revoked_key_ids:
            raise ResearchError("research.core_key_revoked", "Core receipt verification key is revoked")
        key = self.keys.get(key_id)
        if key is None or receipt.get("signature_algorithm") != "hmac-sha256":
            raise ResearchError("research.core_signature_untrusted", "Core receipt key or algorithm is not trusted")
        signature = str(receipt.get("signature") or "")
        if not _SHA256.fullmatch(signature):
            raise ResearchError("research.core_signature_invalid", "Core receipt signature is invalid")
        message = canonical_hash({"purpose": purpose, "receipt": _signed_document(receipt)}).encode("ascii")
        expected = hmac.new(key, message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ResearchError("research.core_signature_invalid", "Core receipt signature verification failed")


def require_core_receipt(
    receipt: Mapping[str, Any],
    *,
    trust: CoreTrustStore,
    purpose: str,
    bindings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = dict(receipt)
    supplied_hash = str(value.pop("receipt_hash", ""))
    if supplied_hash != canonical_hash(value):
        raise ResearchError("research.core_receipt_noncanonical", "Core receipt content hash verification failed")
    if value.get("authority") != "mis_core" or not value.get("audit_id"):
        raise ResearchError("research.core_receipt_untrusted", "Core receipt authority and Audit ID are required")
    trust.verify(value, purpose=purpose)
    for field, expected in (bindings or {}).items():
        if value.get(field) != expected:
            raise ResearchError("research.core_receipt_mismatch", f"Core receipt does not bind {field}")
    return {**value, "receipt_hash": supplied_hash}


def attest_test_receipt(value: Mapping[str, Any], *, purpose: str, key_id: str, key: bytes) -> dict[str, Any]:
    """Deterministic test/fixture signer; never used by production adapters."""
    document = {"authority": "mis_core", "audit_id": str(value.get("audit_id") or "aud_test"), "key_id": key_id, "signature_algorithm": "hmac-sha256", **dict(value)}
    message = canonical_hash({"purpose": purpose, "receipt": document}).encode("ascii")
    signed = {**document, "signature": hmac.new(key, message, hashlib.sha256).hexdigest()}
    return {**signed, "receipt_hash": canonical_hash(signed)}


def reject_untrusted_payload(value: Any, *, path: str = "payload") -> None:
    """Reject caller attempts to persist authority flags or plaintext secrets."""
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            if key in {"canonical", "signature_verified", "authority", "verified", "executed_once"}:
                raise ResearchError("research.reserved_authority_field", f"{path}.{key} is Core-owned")
            if _SENSITIVE_KEY.search(key):
                raise ResearchError("research.secret_literal", f"{path}.{key} cannot contain credential material")
            reject_untrusted_payload(child, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reject_untrusted_payload(child, path=f"{path}[{index}]")
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        raise ResearchError("research.secret_literal", f"{path} contains credential-shaped plaintext")
