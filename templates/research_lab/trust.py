"""Opaque MIS Core receipt verification for the Research domain.

The domain owns no signing key and implements no signature algorithm. C0
injects a public-key-only verifier through this narrow structural protocol.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Protocol

from .contracts import ResearchError, canonical_hash


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SENSITIVE_KEY = re.compile(r"(?:^|[_-])(?:token|secret|password|passwd|api[_-]?key|private[_-]?key|credential)(?:$|[_-])", re.I)
_SECRET_VALUE = re.compile(r"(?:^|\b)(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|Bearer\s+\S+|agtok_\S+|agtsess_\S+)", re.I)


def receipt_purpose(value: str) -> str:
    """Map the domain's version separator onto C0's strict purpose grammar."""
    normalized = value.replace("/", ".")
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{2,127}", normalized):
        raise ResearchError("research.core_receipt_purpose_invalid", "Core receipt purpose is invalid")
    return normalized


def core_receipt_payload(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read the untrusted payload for routing only; callers must then verify it."""
    payload = receipt.get("payload")
    return payload if isinstance(payload, Mapping) else {}


class CoreReceiptVerifier(Protocol):
    """C0-owned receipt verifier; implementations contain public keys only."""

    def verify(
        self,
        payload: Mapping[str, Any],
        proof: Mapping[str, Any],
        *,
        purpose: str,
        expected_bindings: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


def build_production_core_receipt_verifier() -> CoreReceiptVerifier:
    """Bind production composition to C0's public-key-only implementation."""
    try:
        from template_runtime.trust import (
            TrustedCoreReceiptVerifier,
            build_core_receipt_verifier,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise ResearchError("research.core_verifier_unavailable", "C0 TrustedCoreReceiptVerifier is unavailable") from exc
    verifier = build_core_receipt_verifier(required=True)
    if type(verifier) is not TrustedCoreReceiptVerifier:
        raise ResearchError("research.core_verifier_untrusted", "production composition requires C0 TrustedCoreReceiptVerifier")
    return verifier


def require_core_receipt(
    receipt: Mapping[str, Any],
    *,
    trust: CoreReceiptVerifier,
    purpose: str,
    bindings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    envelope = dict(receipt)
    if set(envelope) != {"payload", "proof", "receipt_hash"}:
        raise ResearchError("research.core_receipt_envelope_invalid", "Core receipt envelope must contain only payload, proof, and receipt_hash")
    payload = envelope.get("payload")
    proof = envelope.get("proof")
    if not isinstance(payload, Mapping) or not isinstance(proof, Mapping):
        raise ResearchError("research.core_receipt_envelope_invalid", "Core receipt payload and proof must be objects")
    supplied_hash = str(envelope.get("receipt_hash") or "")
    unsigned = {"payload": dict(payload), "proof": dict(proof)}
    if not _SHA256.fullmatch(supplied_hash) or supplied_hash != canonical_hash(unsigned):
        raise ResearchError("research.core_receipt_noncanonical", "Core receipt envelope hash verification failed")
    if payload.get("authority") != "mis_core" or not payload.get("audit_id"):
        raise ResearchError("research.core_receipt_untrusted", "Core receipt authority and Audit ID are required")
    expected = dict(bindings or {})
    for field, required in expected.items():
        if payload.get(field) != required:
            raise ResearchError("research.core_receipt_mismatch", f"Core receipt does not bind {field}")
    try:
        verification = trust.verify(
            payload,
            proof,
            purpose=receipt_purpose(purpose),
            expected_bindings=expected,
        )
    except Exception as exc:
        raise ResearchError("research.core_receipt_untrusted", "Core receipt signature, purpose, revocation, or authority binding verification failed") from exc
    if verification.get("verified") is not True:
        raise ResearchError("research.core_receipt_untrusted", "Core receipt verifier did not return verified evidence")
    return {**dict(payload), "receipt_hash": supplied_hash}


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
