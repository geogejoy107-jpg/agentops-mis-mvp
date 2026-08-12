"""Verified literature records, source deduplication and citation guards."""

from __future__ import annotations

import re
import ipaddress
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
from urllib.parse import urlsplit, urlunsplit

from .contracts import ResearchError, canonical_hash
from .trust import CoreTrustStore, require_core_receipt

_DOI = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$", re.I)
_ARXIV = re.compile(r"^(?:arXiv:)?(\d{4}\.\d{4,5})(?:v\d+)?$", re.I)


def normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/").lower()
    if not _DOI.fullmatch(candidate):
        raise ResearchError("research.invalid_doi", "DOI has invalid syntax")
    return candidate


def normalize_arxiv(value: str | None) -> str | None:
    if value is None:
        return None
    match = _ARXIV.fullmatch(value.strip())
    if not match:
        raise ResearchError("research.invalid_arxiv", "arXiv identifier has invalid syntax")
    return match.group(1)


def normalize_source_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ResearchError("research.unsafe_source_url", "source URL must be public HTTPS without embedded credentials")
    host = parsed.hostname.lower() if parsed.hostname else ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if (
        host in {"localhost", "127.0.0.1", "::1"}
        or host.endswith((".local", ".internal", ".localhost"))
        or address is not None
        and (address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved)
    ):
        raise ResearchError("research.unsafe_source_url", "local source URLs are forbidden")
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path.rstrip("/"), parsed.query, ""))


def validate_resolved_addresses(addresses: Sequence[str]) -> tuple[str, ...]:
    if not addresses:
        raise ResearchError("research.source_dns_unverified", "source hostname requires connector DNS resolution evidence")
    normalized = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ResearchError("research.source_dns_invalid", "connector returned an invalid source address") from exc
        if address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved:
            raise ResearchError("research.source_dns_private", "source hostname resolved to a non-public address")
        normalized.append(str(address))
    return tuple(sorted(set(normalized)))


@dataclass(frozen=True, slots=True)
class LiteratureRecord:
    literature_id: str
    title: str
    authors: tuple[str, ...]
    year: int
    source_url: str
    doi: str | None
    arxiv_id: str | None
    verification_status: str
    verified_at: str
    locator: str
    source_artifact_id: str

    @classmethod
    def create(cls, *, title: str, authors: Sequence[str], year: int, source_url: str, doi: str | None, arxiv_id: str | None, verification_status: str, verified_at: str, locator: str, source_artifact_id: str) -> "LiteratureRecord":
        if not title.strip() or not authors or not all(author.strip() for author in authors):
            raise ResearchError("research.invalid_literature", "title and authors are required")
        if not 1000 <= year <= 2200 or verification_status not in {"verified", "conflicted", "unavailable"}:
            raise ResearchError("research.invalid_literature", "year or verification status is invalid")
        normalized_doi = normalize_doi(doi)
        normalized_arxiv = normalize_arxiv(arxiv_id)
        normalized_url = normalize_source_url(source_url)
        if normalized_doi is None and normalized_arxiv is None:
            raise ResearchError("research.unverifiable_source", "a DOI or arXiv identifier is required")
        identity = normalized_doi or f"arxiv:{normalized_arxiv}"
        return cls(literature_id=f"lit_{canonical_hash({'identity': identity})[:20]}", title=title.strip(), authors=tuple(author.strip() for author in authors), year=year, source_url=normalized_url, doi=normalized_doi, arxiv_id=normalized_arxiv, verification_status=verification_status, verified_at=verified_at, locator=locator, source_artifact_id=source_artifact_id)


def deduplicate(records: Sequence[LiteratureRecord]) -> tuple[LiteratureRecord, ...]:
    by_identity: dict[str, LiteratureRecord] = {}
    for record in records:
        identity = record.doi or f"arxiv:{record.arxiv_id}"
        existing = by_identity.get(identity)
        if existing and (existing.title.casefold() != record.title.casefold() or existing.year != record.year):
            raise ResearchError("research.source_identity_conflict", f"conflicting metadata for {identity}")
        if existing is None or (existing.verification_status != "verified" and record.verification_status == "verified"):
            by_identity[identity] = record
    return tuple(sorted(by_identity.values(), key=lambda item: item.literature_id))


def verify_citation_claims(claims: Sequence[Mapping[str, Any]], sources: Mapping[str, LiteratureRecord], evidence_port: "CitationEvidencePort", trust: CoreTrustStore) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(evidence_port, CitationEvidencePort):
        raise ResearchError("research.citation_core_readback_missing", "citation verification requires a MIS Core Artifact readback port")
    results = []
    for claim in claims:
        source_id = claim.get("literature_id")
        locator = claim.get("locator")
        source = sources.get(str(source_id))
        reasons = []
        if source is None:
            reasons.append("source_missing")
        elif source.verification_status != "verified":
            reasons.append("source_not_verified")
        if not isinstance(locator, str) or not locator.strip():
            reasons.append("citation_locator_missing")
        excerpt_hash = str(claim.get("source_excerpt_hash") or "")
        if not re.fullmatch(r"[0-9a-f]{64}", excerpt_hash):
            reasons.append("source_excerpt_hash_missing")
        if source is not None and not reasons:
            expected = canonical_hash({"literature_id": source.literature_id, "source_artifact_id": source.source_artifact_id, "locator": str(locator), "source_excerpt_hash": excerpt_hash})
            try:
                require_core_receipt(evidence_port.verify_citation_evidence(literature_id=source.literature_id, source_artifact_id=source.source_artifact_id, locator=str(locator), source_excerpt_hash=excerpt_hash), trust=trust, purpose="research.citation-evidence/v1", bindings={"verified": True, "reference_hash": expected, "literature_id": source.literature_id, "source_artifact_id": source.source_artifact_id})
            except ResearchError:
                reasons.append("citation_core_readback_invalid")
        results.append({"claim_id": claim.get("claim_id"), "supported": not reasons, "reasons": reasons})
    return tuple(results)


def export_bibtex(records: Sequence[LiteratureRecord]) -> str:
    entries = []
    for record in deduplicate(records):
        key = (record.authors[0].split()[-1] + str(record.year) + record.literature_id[-6:]).replace("-", "")
        identifier = f"doi = {{{record.doi}}}" if record.doi else f"eprint = {{{record.arxiv_id}}},\n  archivePrefix = {{arXiv}}"
        safe_title = record.title.replace("{", "").replace("}", "")
        safe_authors = " and ".join(author.replace("{", "").replace("}", "") for author in record.authors)
        entries.append(f"@article{{{key},\n  title = {{{safe_title}}},\n  author = {{{safe_authors}}},\n  year = {{{record.year}}},\n  {identifier}\n}}")
    return "\n\n".join(entries) + ("\n" if entries else "")


@runtime_checkable
class LiteratureSearchPort(Protocol):
    """Shared governed DeepSearch/metadata connector; not a source authority."""

    def search(self, *, query: str, cursor: str | None, limit: int) -> Mapping[str, Any]: ...

    def verify_identifier(self, *, doi: str | None, arxiv_id: str | None) -> Mapping[str, Any]: ...


@runtime_checkable
class CitationEvidencePort(Protocol):
    def verify_citation_evidence(self, *, literature_id: str, source_artifact_id: str, locator: str, source_excerpt_hash: str) -> Mapping[str, Any]: ...


class LiteratureService:
    def __init__(self, connector: LiteratureSearchPort) -> None:
        if not isinstance(connector, LiteratureSearchPort):
            raise TypeError("connector must implement LiteratureSearchPort")
        self.connector = connector

    def search_verified(self, *, query: str, limit: int = 20) -> tuple[LiteratureRecord, ...]:
        if not query.strip() or not 1 <= limit <= 100:
            raise ResearchError("research.invalid_literature_query", "query and bounded limit are required")
        response = self.connector.search(query=query, cursor=None, limit=limit)
        if response.get("state") != "ready":
            raise ResearchError("research.literature_connector_unavailable", "literature connector is unavailable")
        items = response.get("items")
        if not isinstance(items, list):
            raise ResearchError("research.literature_receipt_invalid", "literature search returned no structured items")
        records: list[LiteratureRecord] = []
        for item in items:
            if not isinstance(item, Mapping):
                raise ResearchError("research.literature_receipt_invalid", "literature item must be structured")
            verification = self.connector.verify_identifier(doi=item.get("doi"), arxiv_id=item.get("arxiv_id"))
            if verification.get("status") != "verified" or not verification.get("artifact_id"):
                continue
            validate_resolved_addresses(tuple(verification.get("resolved_addresses") or ()))
            records.append(
                LiteratureRecord.create(
                    title=str(item.get("title") or ""),
                    authors=tuple(item.get("authors") or ()),
                    year=int(item.get("year")),
                    source_url=str(verification.get("publication_url") or item.get("source_url") or ""),
                    doi=item.get("doi"),
                    arxiv_id=item.get("arxiv_id"),
                    verification_status="verified",
                    verified_at=str(verification.get("verified_at") or ""),
                    locator=str(item.get("locator") or "record"),
                    source_artifact_id=str(verification["artifact_id"]),
                )
            )
        return deduplicate(records)
