"""Restart-safe SQLite coordination journal for the C1 migration adapter.

This is not migration authority.  C0 stores already verified, signed receipts
here so a process crash cannot create a second backup or reapply a request.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping

from .contracts import ResearchError, require_sha256


class MigrationRestartJournal:
    def __init__(self, path: Path) -> None:
        if not path.is_absolute() or (path.exists() and path.is_symlink()):
            raise ResearchError("research.migration_journal_invalid", "migration journal requires an absolute non-symlink path")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with closing(self._db()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS migration_requests (request_hash TEXT PRIMARY KEY, backup_receipt TEXT, apply_receipt TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def record_backup_once(self, request_hash: str, receipt: Mapping[str, Any]) -> Mapping[str, Any]:
        require_sha256(request_hash, "request_hash")
        encoded = json.dumps(dict(receipt), sort_keys=True, separators=(",", ":"), allow_nan=False)
        with closing(self._db()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT backup_receipt FROM migration_requests WHERE request_hash=?", (request_hash,)).fetchone()
            if row and row[0]:
                db.execute("COMMIT")
                return json.loads(row[0])
            db.execute("INSERT INTO migration_requests(request_hash,backup_receipt) VALUES(?,?) ON CONFLICT(request_hash) DO UPDATE SET backup_receipt=excluded.backup_receipt,updated_at=CURRENT_TIMESTAMP", (request_hash, encoded))
            db.execute("COMMIT")
        return dict(receipt)

    def record_apply_once(self, request_hash: str, receipt: Mapping[str, Any]) -> Mapping[str, Any]:
        require_sha256(request_hash, "request_hash")
        encoded = json.dumps(dict(receipt), sort_keys=True, separators=(",", ":"), allow_nan=False)
        with closing(self._db()) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT backup_receipt,apply_receipt FROM migration_requests WHERE request_hash=?", (request_hash,)).fetchone()
            if not row or not row[0]:
                db.execute("ROLLBACK")
                raise ResearchError("research.migration_backup_missing", "apply cannot be journaled before the durable backup")
            if row[1]:
                db.execute("COMMIT")
                return json.loads(row[1])
            db.execute("UPDATE migration_requests SET apply_receipt=?,updated_at=CURRENT_TIMESTAMP WHERE request_hash=?", (encoded, request_hash))
            db.execute("COMMIT")
        return dict(receipt)

    def read(self, request_hash: str) -> Mapping[str, Any] | None:
        require_sha256(request_hash, "request_hash")
        with closing(self._db()) as db:
            row = db.execute("SELECT backup_receipt,apply_receipt FROM migration_requests WHERE request_hash=?", (request_hash,)).fetchone()
        if not row:
            return None
        return {"backup": json.loads(row[0]) if row[0] else None, "apply": json.loads(row[1]) if row[1] else None}
