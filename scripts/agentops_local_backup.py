#!/usr/bin/env python3
"""Local AgentOps MIS SQLite backup, verification, and explicit restore utility."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
DEFAULT_BACKUP_DIR = ROOT / ".agentops_runtime" / "backups"
COUNT_TABLES = [
    "agents",
    "tasks",
    "runs",
    "tool_calls",
    "approvals",
    "memories",
    "evaluations",
    "audit_logs",
    "artifacts",
    "workflow_jobs",
    "agent_gateway_tokens",
    "agent_gateway_sessions",
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def now_iso() -> str:
    return dt.datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def count_rows(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    existing = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    for table in COUNT_TABLES:
        if table not in existing:
            counts[table] = 0
            continue
        counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts


def integrity_check(path: Path) -> str:
    with connect_readonly(path) as conn:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])


def foreign_key_check(path: Path) -> str:
    with connect_readonly(path) as conn:
        return "ok" if not conn.execute("PRAGMA foreign_key_check").fetchone() else "failed"


def schema_evidence(path: Path) -> dict:
    with connect_readonly(path) as conn:
        user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        rows = conn.execute(
            "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return {
        "sqlite_user_version": user_version,
        "schema_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def backup_manifest(backup_path: Path, source_db: Path, started_at: str) -> dict:
    with connect_readonly(backup_path) as conn:
        counts = count_rows(conn)
    return {
        "manifest_schema_version": 1,
        "provider": "agentops-local-backup",
        "operation": "backup_create",
        "backup_id": backup_path.stem,
        "created_at": started_at,
        "source_db_label": source_db.name,
        "backup_file": backup_path.name,
        "backup_size_bytes": backup_path.stat().st_size,
        "backup_sha256": sha256_file(backup_path),
        "integrity_check": integrity_check(backup_path),
        "foreign_key_check": foreign_key_check(backup_path),
        **schema_evidence(backup_path),
        "counts": counts,
        "safety": {
            "local_only": True,
            "raw_rows_printed": False,
            "tokens_omitted": True,
            "secret_store_included": False,
            "hashed_auth_state_included": True,
        },
    }


def create_backup(args: argparse.Namespace) -> tuple[dict, int]:
    source = Path(args.db_path or DEFAULT_DB).expanduser().resolve()
    backup_dir = Path(args.backup_dir or DEFAULT_BACKUP_DIR).expanduser().resolve()
    if not source.exists():
        return {"ok": False, "error": "source_db_not_found", "source_db_label": source.name}, 1
    backup_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_stamp()
    backup_path = backup_dir / f"agentops-mis-{started_at}.sqlite"
    manifest_path = backup_path.with_suffix(".manifest.json")
    with sqlite3.connect(source) as src, sqlite3.connect(backup_path) as dst:
        src.backup(dst)
    backup_path.chmod(0o600)
    manifest = backup_manifest(backup_path, source, started_at)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    return {
        "ok": manifest["integrity_check"] == "ok",
        "backup_path": str(backup_path),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }, 0


def latest_backup(backup_dir: Path) -> Path | None:
    backups = sorted(backup_dir.glob("agentops-mis-*.sqlite"), key=lambda path: path.stat().st_mtime, reverse=True)
    return backups[0] if backups else None


def verify_backup(args: argparse.Namespace) -> tuple[dict, int]:
    backup_dir = Path(args.backup_dir or DEFAULT_BACKUP_DIR).expanduser().resolve()
    backup_path = Path(args.backup).expanduser().resolve() if args.backup else latest_backup(backup_dir)
    if not backup_path or not backup_path.exists():
        return {"ok": False, "error": "backup_not_found"}, 1
    manifest_path = backup_path.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        return {"ok": False, "error": "backup_manifest_missing", "backup_path": str(backup_path)}, 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ok": False, "error": "backup_manifest_unreadable", "backup_path": str(backup_path)}, 1
    required = {
        "manifest_schema_version",
        "provider",
        "backup_file",
        "backup_size_bytes",
        "backup_sha256",
        "integrity_check",
        "foreign_key_check",
        "sqlite_user_version",
        "schema_sha256",
    }
    missing = sorted(required - set(manifest))
    if missing:
        return {"ok": False, "error": "backup_manifest_incomplete", "missing_fields": missing}, 1
    try:
        with connect_readonly(backup_path) as conn:
            counts = count_rows(conn)
        actual_hash = sha256_file(backup_path)
        expected_hash = str(manifest["backup_sha256"])
        hash_ok = expected_hash == actual_hash
        file_name_ok = manifest["backup_file"] == backup_path.name
        size_ok = int(manifest["backup_size_bytes"]) == backup_path.stat().st_size
        integrity = integrity_check(backup_path)
        foreign_keys = foreign_key_check(backup_path)
        schema = schema_evidence(backup_path)
        schema_ok = (
            int(manifest["sqlite_user_version"]) == schema["sqlite_user_version"]
            and manifest["schema_sha256"] == schema["schema_sha256"]
        )
    except (OSError, TypeError, ValueError, sqlite3.DatabaseError):
        return {
            "ok": False,
            "error": "backup_verification_failed",
            "backup_path": str(backup_path),
            "failure_detail_omitted": True,
            "raw_rows_printed": False,
            "token_omitted": True,
        }, 1
    manifest_ok = (
        manifest["manifest_schema_version"] == 1
        and manifest["provider"] == "agentops-local-backup"
        and manifest["integrity_check"] == "ok"
        and manifest["foreign_key_check"] == "ok"
    )
    ok = integrity == "ok" and foreign_keys == "ok" and hash_ok and file_name_ok and size_ok and schema_ok and manifest_ok
    return {
        "ok": ok,
        "backup_path": str(backup_path),
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "integrity_check": integrity,
        "hash_ok": hash_ok,
        "file_name_ok": file_name_ok,
        "size_ok": size_ok,
        "schema_ok": schema_ok,
        "manifest_ok": manifest_ok,
        "foreign_key_check": foreign_keys,
        "backup_sha256": actual_hash,
        "counts": counts,
        "raw_rows_printed": False,
        "token_omitted": True,
    }, 0 if ok else 1


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def revoke_restored_auth_state(path: Path) -> dict[str, int]:
    revoked: dict[str, int] = {}
    stamp = now_iso()
    with sqlite3.connect(path) as conn:
        existing = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ("human_sessions", "agent_gateway_sessions", "agent_gateway_tokens"):
            columns = table_columns(conn, table) if table in existing else set()
            if {"status", "revoked_at"}.issubset(columns):
                cursor = conn.execute(
                    f"UPDATE {table} SET status='revoked', revoked_at=COALESCE(revoked_at, ?) WHERE status='active'",
                    (stamp,),
                )
                revoked[table] = int(cursor.rowcount)
            else:
                revoked[table] = 0
    return revoked


def sqlite_snapshot(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst)
    destination.chmod(0o600)


def fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def restore_backup(args: argparse.Namespace) -> tuple[dict, int]:
    if not args.confirm_restore:
        return {
            "ok": False,
            "dry_run": True,
            "error": "confirm_restore_required",
            "message": "Pass --confirm-restore to write the target DB.",
        }, 2
    backup_path = Path(args.backup).expanduser().resolve()
    target = Path(args.target).expanduser().resolve()
    if not backup_path.exists():
        return {"ok": False, "error": "backup_not_found", "backup_path": str(backup_path)}, 1
    verify_payload, verify_status = verify_backup(argparse.Namespace(backup=str(backup_path), backup_dir=None))
    if verify_status != 0:
        return {"ok": False, "error": "backup_verification_failed", "verify": verify_payload}, 1
    if target.exists() and not args.overwrite:
        return {
            "ok": False,
            "error": "target_exists",
            "target_label": target.name,
            "message": "Pass --overwrite with --confirm-restore after making a separate safety copy.",
        }, 2
    target.parent.mkdir(parents=True, exist_ok=True)
    pre_restore_copy = None
    if target.exists():
        pre_restore_copy = target.with_suffix(target.suffix + f".pre-restore-{now_stamp()}")
        sqlite_snapshot(target, pre_restore_copy)
        if integrity_check(pre_restore_copy) != "ok" or foreign_key_check(pre_restore_copy) != "ok":
            pre_restore_copy.unlink(missing_ok=True)
            return {"ok": False, "error": "pre_restore_snapshot_verification_failed"}, 1
    target.parent.mkdir(parents=True, exist_ok=True)
    stage_fd, stage_name = tempfile.mkstemp(prefix=f".{target.name}.restore-", dir=target.parent)
    os.close(stage_fd)
    stage = Path(stage_name)
    try:
        shutil.copy2(backup_path, stage)
        revoked_auth = revoke_restored_auth_state(stage)
        restored_integrity = integrity_check(stage)
        restored_foreign_keys = foreign_key_check(stage)
        if restored_integrity != "ok" or restored_foreign_keys != "ok":
            return {
                "ok": False,
                "error": "restored_database_verification_failed",
                "integrity_check": restored_integrity,
                "foreign_key_check": restored_foreign_keys,
            }, 1
        stage.chmod(0o600)
        fsync_file(stage)
        os.replace(stage, target)
        for suffix in ("-wal", "-shm"):
            Path(str(target) + suffix).unlink(missing_ok=True)
    finally:
        stage.unlink(missing_ok=True)
    return {
        "ok": True,
        "restored": True,
        "target_path": str(target),
        "backup_path": str(backup_path),
        "pre_restore_copy": str(pre_restore_copy) if pre_restore_copy else None,
        "restored_integrity_check": restored_integrity,
        "restored_foreign_key_check": restored_foreign_keys,
        "revoked_auth_state": revoked_auth,
        "auth_sessions_preserved": False,
        "atomic_replace": True,
        "verify": verify_payload,
        "raw_rows_printed": False,
        "token_omitted": True,
    }, 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentOps MIS local SQLite backup utility.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="Create a local SQLite backup and manifest.")
    create.add_argument("--db-path", default=str(DEFAULT_DB))
    create.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    create.set_defaults(func=create_backup)

    verify = sub.add_parser("verify", help="Verify a backup integrity/hash without printing rows.")
    verify.add_argument("--backup", default="")
    verify.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    verify.set_defaults(func=verify_backup)

    restore = sub.add_parser("restore", help="Restore a backup to a target DB path with explicit confirmation.")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--target", required=True)
    restore.add_argument("--confirm-restore", action="store_true")
    restore.add_argument("--overwrite", action="store_true")
    restore.set_defaults(func=restore_backup)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload, status = args.func(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
