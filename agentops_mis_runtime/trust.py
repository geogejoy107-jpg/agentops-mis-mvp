"""Runtime connector trust registry helpers.

This module owns the connector trust read/update state transition. HTTP
handlers, runtime events, and audit-log writes stay in ``server.py``.
"""
from __future__ import annotations

from collections.abc import Callable


TRUST_STATUSES = {"trusted", "review_required", "blocked"}


def normalize_trust_status(value: object, default: str = "review_required") -> str:
    candidate = str(value or "").strip()
    if candidate in TRUST_STATUSES:
        return candidate
    return default


def trust_update_from_body(body: dict, redact_text: Callable[[object, int], str | None]) -> dict:
    trust_status = normalize_trust_status(body.get("trust_status") or body.get("status"))
    trust_note = redact_text(body.get("trust_note") or body.get("note") or f"Runtime connector marked {trust_status}.", 300)
    return {
        "trust_status": trust_status,
        "trust_note": trust_note,
    }


def runtime_connector_trust(
    conn,
    connector_id: str | None,
    *,
    refresh: bool = True,
    refresh_connectors: Callable[[object], None] | None = None,
) -> dict | None:
    if not connector_id:
        return None
    if refresh and refresh_connectors:
        refresh_connectors(conn)
    row = conn.execute("SELECT * FROM runtime_connectors WHERE runtime_connector_id=?", (connector_id,)).fetchone()
    return dict(row) if row else None


def apply_runtime_connector_trust_update(
    conn,
    connector_id: str,
    body: dict,
    *,
    now: str,
    redact_text: Callable[[object, int], str | None],
    refresh_connectors: Callable[[object], None] | None = None,
) -> dict | None:
    if refresh_connectors:
        refresh_connectors(conn)
    before = conn.execute("SELECT * FROM runtime_connectors WHERE runtime_connector_id=?", (connector_id,)).fetchone()
    if not before:
        return None
    update = trust_update_from_body(body, redact_text)
    conn.execute(
        """UPDATE runtime_connectors
        SET trust_status=?, trust_note=?, trust_updated_at=?, updated_at=?
        WHERE runtime_connector_id=?""",
        (update["trust_status"], update["trust_note"], now, now, connector_id),
    )
    after = conn.execute("SELECT * FROM runtime_connectors WHERE runtime_connector_id=?", (connector_id,)).fetchone()
    return {
        "before": dict(before),
        "after": dict(after),
        "trust_status": update["trust_status"],
        "trust_note": update["trust_note"],
    }
