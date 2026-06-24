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
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def backup_manifest(backup_path: Path, source_db: Path, started_at: str) -> dict:
    with connect_readonly(backup_path) as conn:
        counts = count_rows(conn)
    return {
        "provider": "agentops-local-backup",
        "operation": "backup_create",
        "backup_id": backup_path.stem,
        "created_at": started_at,
        "source_db_label": source_db.name,
        "backup_file": backup_path.name,
        "backup_size_bytes": backup_path.stat().st_size,
        "backup_sha256": sha256_file(backup_path),
        "integrity_check": integrity_check(backup_path),
        "counts": counts,
        "safety": {
            "local_only": True,
            "raw_rows_printed": False,
            "tokens_omitted": True,
            "credentials_stored": False,
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
    manifest = backup_manifest(backup_path, source, started_at)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {"error": "manifest_unreadable"}
    with connect_readonly(backup_path) as conn:
        counts = count_rows(conn)
    actual_hash = sha256_file(backup_path)
    expected_hash = manifest.get("backup_sha256")
    hash_ok = not expected_hash or expected_hash == actual_hash
    integrity = integrity_check(backup_path)
    return {
        "ok": integrity == "ok" and hash_ok,
        "backup_path": str(backup_path),
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "integrity_check": integrity,
        "hash_ok": hash_ok,
        "backup_sha256": actual_hash,
        "counts": counts,
        "raw_rows_printed": False,
        "token_omitted": True,
    }, 0 if integrity == "ok" and hash_ok else 1


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
        shutil.copy2(target, pre_restore_copy)
    shutil.copy2(backup_path, target)
    return {
        "ok": True,
        "restored": True,
        "target_path": str(target),
        "backup_path": str(backup_path),
        "pre_restore_copy": str(pre_restore_copy) if pre_restore_copy else None,
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
