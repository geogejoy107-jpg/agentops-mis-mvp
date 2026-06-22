#!/usr/bin/env python3
"""Verify the local SQLite reliability baseline with isolated concurrency."""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agentops-sqlite-reliability-") as tmp:
        db_path = Path(tmp) / "agentops_reliability.db"
        os.environ["AGENTOPS_DB_PATH"] = str(db_path)
        sys.path.insert(0, str(ROOT))

        import server  # noqa: PLC0415

        failures: list[str] = []
        server.init_schema()

        conn = server.db()
        try:
            pragmas = {
                "foreign_keys": conn.execute("PRAGMA foreign_keys").fetchone()[0],
                "busy_timeout": conn.execute("PRAGMA busy_timeout").fetchone()[0],
                "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
                "synchronous": conn.execute("PRAGMA synchronous").fetchone()[0],
            }
            migration = conn.execute(
                "SELECT migration_id, description FROM schema_migrations WHERE migration_id=?",
                (server.SQLITE_SCHEMA_BASELINE_ID,),
            ).fetchone()
            if not migration:
                failures.append("schema_migrations baseline row missing")
        finally:
            conn.close()

        if pragmas.get("foreign_keys") != 1:
            failures.append(f"foreign_keys disabled: {pragmas}")
        if int(pragmas.get("busy_timeout") or 0) < 5000:
            failures.append(f"busy_timeout too low: {pragmas}")
        if str(pragmas.get("journal_mode") or "").lower() != "wal":
            failures.append(f"journal_mode not WAL: {pragmas}")
        if pragmas.get("synchronous") != 1:
            failures.append(f"synchronous not NORMAL: {pragmas}")

        def read_once(index: int) -> dict:
            conn = server.db()
            try:
                row = conn.execute("SELECT COUNT(*) AS count FROM tasks").fetchone()
                return {"index": index, "count": int(row["count"] or 0)}
            finally:
                conn.close()

        def write_once(index: int) -> str:
            conn = server.db()
            try:
                with conn:
                    audit_id = f"aud_sqlite_reliability_{index:03d}"
                    conn.execute(
                        """INSERT INTO audit_logs(
                            audit_id, actor_type, actor_id, action, entity_type, entity_id,
                            before_hash, after_hash, metadata_json, tamper_chain_hash, created_at
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            audit_id,
                            "system",
                            "sqlite_reliability_smoke",
                            "sqlite.reliability.short_write",
                            "sqlite",
                            audit_id,
                            None,
                            server.stable_hash({"index": index}),
                            json.dumps({"index": index, "raw_omitted": True}, sort_keys=True),
                            server.stable_hash({"audit_id": audit_id}),
                            server.now_iso(),
                        ),
                    )
                    return audit_id
            finally:
                conn.close()

        read_errors: list[str] = []
        write_errors: list[str] = []
        read_results: list[dict] = []
        write_results: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
            futures = [pool.submit(read_once, index) for index in range(100)]
            futures += [pool.submit(write_once, index) for index in range(20)]
            for future in concurrent.futures.as_completed(futures, timeout=60):
                try:
                    result = future.result()
                    if isinstance(result, dict):
                        read_results.append(result)
                    else:
                        write_results.append(result)
                except Exception:
                    detail = traceback.format_exc()
                    if "database is locked" in detail.lower() or "database is busy" in detail.lower():
                        write_errors.append(detail)
                    else:
                        read_errors.append(detail)

        conn = server.db()
        try:
            written = conn.execute(
                "SELECT COUNT(*) AS count FROM audit_logs WHERE action='sqlite.reliability.short_write'"
            ).fetchone()["count"]
        finally:
            conn.close()

        if len(read_results) != 100:
            failures.append(f"concurrent reads incomplete: {len(read_results)}/100")
        if len(write_results) != 20:
            failures.append(f"concurrent writes incomplete: {len(write_results)}/20")
        if int(written or 0) != 20:
            failures.append(f"committed write count mismatch: {written}/20")
        if read_errors or write_errors:
            failures.append(f"concurrency errors read={len(read_errors)} write={len(write_errors)}")

        result = {
            "ok": not failures,
            "operation": "sqlite_reliability_smoke",
            "db_path": str(db_path),
            "pragmas": pragmas,
            "schema_migration_id": server.SQLITE_SCHEMA_BASELINE_ID,
            "concurrency": {
                "reads": len(read_results),
                "writes": len(write_results),
                "committed_writes": int(written or 0),
                "read_errors": len(read_errors),
                "write_errors": len(write_errors),
            },
            "failures": failures,
            "token_omitted": True,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
