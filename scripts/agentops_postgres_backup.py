#!/usr/bin/env python3
"""Postgres backup, verification, and explicit restore utility for BYOC."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIR = ROOT / ".agentops_runtime" / "postgres_backups"
MANIFEST_CONTRACT = "postgres_backup_manifest_v1"
RECOVERY_CONTRACT = "postgres_backup_restore_v1"
PG_ENV_KEYS = (
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSWORD",
    "PGDATABASE",
    "PGSSLMODE",
    "PGSSLROOTCERT",
    "PGSSLCERT",
    "PGSSLKEY",
    "PGCONNECT_TIMEOUT",
)
QUERY_ENV_MAP = {
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "connect_timeout": "PGCONNECT_TIMEOUT",
}


class BackupError(RuntimeError):
    def __init__(self, error: str, *, status: int = 1, detail: dict | None = None):
        super().__init__(error)
        self.error = error
        self.status = status
        self.detail = detail or {}


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def database_ref(database: str) -> str:
    return "pgdb_" + hashlib.sha256(database.encode("utf-8")).hexdigest()[:16]


def manifest_path_for(backup_path: Path) -> Path:
    return backup_path.with_suffix(backup_path.suffix + ".manifest.json")


def parse_postgres_dsn(value: str) -> tuple[dict[str, str], str, str]:
    if not value:
        raise BackupError("postgres_dsn_required", status=2)
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise BackupError("postgres_url_dsn_required", status=2)
    database = unquote(parsed.path.lstrip("/"))
    if not database or "/" in database:
        raise BackupError("postgres_database_required", status=2)
    env = {
        "PGHOST": parsed.hostname or "127.0.0.1",
        "PGPORT": str(parsed.port or 5432),
        "PGDATABASE": database,
    }
    if parsed.username:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    query = parse_qs(parsed.query, keep_blank_values=False)
    for query_key, env_key in QUERY_ENV_MAP.items():
        values = query.get(query_key) or []
        if values:
            env[env_key] = str(values[-1])
    return env, database, database_ref(database)


def command_for(
    args: argparse.Namespace,
    tool: str,
    tool_args: list[str],
    *,
    process_env: dict[str, str],
    interactive: bool = False,
) -> list[str]:
    docker_container = str(getattr(args, "docker_container", "") or "").strip()
    if docker_container:
        command = ["docker", "exec"]
        if interactive:
            command.append("-i")
        for key in PG_ENV_KEYS:
            if key in process_env:
                command.extend(["--env", key])
        return [*command, docker_container, tool, *tool_args]

    explicit = str(getattr(args, f"{tool.replace('-', '_')}_bin", "") or "").strip()
    binary = explicit or shutil.which(tool)
    if not binary:
        raise BackupError(f"{tool.replace('-', '_')}_not_found", status=2)
    return [binary, *tool_args]


def run_tool(
    args: argparse.Namespace,
    tool: str,
    tool_args: list[str],
    *,
    connection_env: dict[str, str] | None = None,
    stdin_path: Path | None = None,
    stdout_path: Path | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[bytes]:
    proc_env = os.environ.copy()
    if connection_env:
        proc_env.update(connection_env)
    command = command_for(
        args,
        tool,
        tool_args,
        process_env=proc_env,
        interactive=stdin_path is not None,
    )

    stdin_handle = None
    stdout_handle = None
    try:
        stdin_handle = stdin_path.open("rb") if stdin_path else None
        stdout_handle = stdout_path.open("wb") if stdout_path else None
        return subprocess.run(
            command,
            cwd=ROOT,
            env=proc_env,
            stdin=stdin_handle,
            stdout=stdout_handle if stdout_handle else subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackupError(
            f"{tool.replace('-', '_')}_execution_failed",
            detail={"exception_type": type(exc).__name__},
        ) from exc
    finally:
        if stdin_handle:
            stdin_handle.close()
        if stdout_handle:
            stdout_handle.close()


def tool_failure(tool: str, result: subprocess.CompletedProcess[bytes]) -> BackupError:
    stderr = bytes(result.stderr or b"")
    return BackupError(
        f"{tool.replace('-', '_')}_failed",
        detail={
            "exit_code": result.returncode,
            "stderr_sha256": sha256_bytes(stderr),
            "stderr_omitted": True,
        },
    )


def tool_version(args: argparse.Namespace, tool: str) -> str:
    result = run_tool(args, tool, ["--version"], timeout=30)
    if result.returncode != 0:
        raise tool_failure(tool, result)
    return bytes(result.stdout or b"").decode("utf-8", errors="replace").strip()[:160]


def archive_toc(args: argparse.Namespace, backup_path: Path) -> dict:
    result = run_tool(args, "pg_restore", ["--list"], stdin_path=backup_path, timeout=120)
    if result.returncode != 0:
        raise tool_failure("pg_restore", result)
    text = bytes(result.stdout or b"").decode("utf-8", errors="replace")
    entries = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith(";")]
    if not entries:
        raise BackupError("postgres_backup_toc_empty")
    return {
        "toc_entry_count": len(entries),
        "toc_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "toc_text_omitted": True,
    }


def write_manifest(path: Path, payload: dict) -> None:
    temp_path = path.with_suffix(path.suffix + ".partial")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp_path.chmod(0o600)
        os.replace(temp_path, path)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        raise BackupError(
            "backup_manifest_write_failed",
            detail={"exception_type": type(exc).__name__},
        ) from exc


def create_archive(
    args: argparse.Namespace,
    dsn: str,
    backup_dir: Path,
    *,
    prefix: str = "agentops-postgres",
) -> tuple[dict, int]:
    connection_env, _database, source_ref = parse_postgres_dsn(dsn)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_id = f"{prefix}-{now_stamp()}-{secrets.token_hex(4)}"
    backup_path = backup_dir / f"{backup_id}.dump"
    partial_path = backup_path.with_suffix(".dump.partial")
    manifest_path = manifest_path_for(backup_path)
    try:
        result = run_tool(
            args,
            "pg_dump",
            ["--format=custom", "--no-owner", "--no-privileges", "--compress=6"],
            connection_env=connection_env,
            stdout_path=partial_path,
            timeout=int(getattr(args, "timeout", 300)),
        )
        if result.returncode != 0:
            raise tool_failure("pg_dump", result)
        if not partial_path.exists() or partial_path.stat().st_size == 0:
            raise BackupError("postgres_backup_empty")
        partial_path.chmod(0o600)
        os.replace(partial_path, backup_path)
        toc = archive_toc(args, backup_path)
        manifest = {
            "contract_id": MANIFEST_CONTRACT,
            "recovery_contract": RECOVERY_CONTRACT,
            "provider": "agentops-postgres-backup",
            "operation": "backup_create",
            "backup_id": backup_id,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "archive_format": "postgres_custom",
            "backup_file": backup_path.name,
            "backup_size_bytes": backup_path.stat().st_size,
            "backup_sha256": sha256_file(backup_path),
            "source_database_ref": source_ref,
            "pg_dump_version": tool_version(args, "pg_dump"),
            "pg_restore_version": tool_version(args, "pg_restore"),
            **toc,
            "safety": {
                "credentials_omitted": True,
                "dsn_omitted": True,
                "raw_rows_printed": False,
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "private_transcript_omitted": True,
                "token_omitted": True,
            },
        }
        write_manifest(manifest_path, manifest)
        return {
            "ok": True,
            "contract_id": RECOVERY_CONTRACT,
            "backup_path": str(backup_path),
            "manifest_path": str(manifest_path),
            "manifest": manifest,
            "credential_values_omitted": True,
        }, 0
    except BackupError as exc:
        partial_path.unlink(missing_ok=True)
        backup_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        return {"ok": False, "error": exc.error, **exc.detail, "credential_values_omitted": True}, exc.status


def create_backup(args: argparse.Namespace) -> tuple[dict, int]:
    dsn = str(args.dsn or os.environ.get("AGENTOPS_POSTGRES_DSN") or os.environ.get("DATABASE_URL") or "")
    backup_dir = Path(args.backup_dir or DEFAULT_BACKUP_DIR).expanduser().resolve()
    try:
        return create_archive(args, dsn, backup_dir)
    except BackupError as exc:
        return {"ok": False, "error": exc.error, **exc.detail, "credential_values_omitted": True}, exc.status


def latest_backup(backup_dir: Path) -> Path | None:
    backups = sorted(backup_dir.glob("agentops-postgres-*.dump"), key=lambda path: path.stat().st_mtime, reverse=True)
    return backups[0] if backups else None


def verify_archive(args: argparse.Namespace, backup_path: Path) -> tuple[dict, int]:
    if not backup_path.exists():
        return {"ok": False, "error": "backup_not_found", "credential_values_omitted": True}, 1
    manifest_path = manifest_path_for(backup_path)
    if not manifest_path.exists():
        return {"ok": False, "error": "backup_manifest_not_found", "credential_values_omitted": True}, 1
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "error": "backup_manifest_unreadable", "credential_values_omitted": True}, 1
    if not isinstance(manifest, dict):
        return {"ok": False, "error": "backup_manifest_invalid", "credential_values_omitted": True}, 1
    failures: list[str] = []
    if manifest.get("contract_id") != MANIFEST_CONTRACT:
        failures.append("manifest_contract_mismatch")
    if manifest.get("recovery_contract") != RECOVERY_CONTRACT:
        failures.append("manifest_recovery_contract_mismatch")
    if manifest.get("provider") != "agentops-postgres-backup":
        failures.append("manifest_provider_mismatch")
    if manifest.get("operation") != "backup_create":
        failures.append("manifest_operation_mismatch")
    actual_hash = sha256_file(backup_path)
    if manifest.get("backup_sha256") != actual_hash:
        failures.append("backup_sha256_mismatch")
    if manifest.get("backup_size_bytes") != backup_path.stat().st_size:
        failures.append("backup_size_mismatch")
    toc: dict = {}
    try:
        toc = archive_toc(args, backup_path)
        if manifest.get("toc_sha256") != toc.get("toc_sha256"):
            failures.append("backup_toc_mismatch")
    except BackupError as exc:
        failures.append(exc.error)
    return {
        "ok": not failures,
        "contract_id": RECOVERY_CONTRACT,
        "backup_path": str(backup_path),
        "manifest_path": str(manifest_path),
        "backup_sha256": actual_hash,
        "hash_ok": "backup_sha256_mismatch" not in failures,
        "toc_ok": not any(item in failures for item in {"backup_toc_mismatch", "pg_restore_failed", "postgres_backup_toc_empty"}),
        "toc_entry_count": toc.get("toc_entry_count", 0),
        "failures": failures,
        "raw_rows_printed": False,
        "credential_values_omitted": True,
        "token_omitted": True,
    }, 0 if not failures else 1


def verify_backup(args: argparse.Namespace) -> tuple[dict, int]:
    backup_dir = Path(args.backup_dir or DEFAULT_BACKUP_DIR).expanduser().resolve()
    backup_path = Path(args.backup).expanduser().resolve() if args.backup else latest_backup(backup_dir)
    if not backup_path:
        return {"ok": False, "error": "backup_not_found", "credential_values_omitted": True}, 1
    return verify_archive(args, backup_path)


def restore_backup(args: argparse.Namespace) -> tuple[dict, int]:
    if not args.confirm_restore:
        return {
            "ok": False,
            "dry_run": True,
            "error": "confirm_restore_required",
            "message": "Pass --confirm-restore before restoring a Postgres archive.",
            "credential_values_omitted": True,
        }, 2
    if not args.target_empty_confirmed and not args.overwrite:
        return {
            "ok": False,
            "error": "target_state_confirmation_required",
            "message": "Pass --target-empty-confirmed for a new database or --overwrite for a guarded replacement.",
            "credential_values_omitted": True,
        }, 2
    backup_path = Path(args.backup).expanduser().resolve()
    verified, verify_status = verify_archive(args, backup_path)
    if verify_status != 0:
        return {"ok": False, "error": "backup_verification_failed", "verify": verified, "credential_values_omitted": True}, 1
    target_dsn = str(args.target_dsn or os.environ.get("AGENTOPS_POSTGRES_TARGET_DSN") or "")
    try:
        connection_env, target_database, target_ref = parse_postgres_dsn(target_dsn)
    except BackupError as exc:
        return {"ok": False, "error": exc.error, **exc.detail, "credential_values_omitted": True}, exc.status

    pre_restore: dict | None = None
    if args.overwrite:
        pre_restore_dir = Path(args.pre_restore_backup_dir or backup_path.parent / "pre_restore").expanduser().resolve()
        pre_restore, pre_status = create_archive(
            args,
            target_dsn,
            pre_restore_dir,
            prefix="agentops-postgres-pre-restore",
        )
        if pre_status != 0:
            return {
                "ok": False,
                "error": "pre_restore_backup_failed",
                "pre_restore_backup": pre_restore,
                "credential_values_omitted": True,
            }, 1

    restore_args = [
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-privileges",
        f"--dbname={target_database}",
    ]
    if args.overwrite:
        restore_args[0:0] = ["--clean", "--if-exists"]
    try:
        result = run_tool(
            args,
            "pg_restore",
            restore_args,
            connection_env=connection_env,
            stdin_path=backup_path,
            timeout=int(args.timeout),
        )
        if result.returncode != 0:
            raise tool_failure("pg_restore", result)
    except BackupError as exc:
        return {
            "ok": False,
            "error": exc.error,
            **exc.detail,
            "pre_restore_backup": pre_restore,
            "target_database_ref": target_ref,
            "credential_values_omitted": True,
        }, exc.status

    return {
        "ok": True,
        "contract_id": RECOVERY_CONTRACT,
        "restored": True,
        "backup_path": str(backup_path),
        "target_database_ref": target_ref,
        "target_database_name_omitted": True,
        "overwrite": bool(args.overwrite),
        "target_empty_confirmed": bool(args.target_empty_confirmed),
        "pre_restore_backup": pre_restore,
        "verify": verified,
        "raw_rows_printed": False,
        "credential_values_omitted": True,
        "token_omitted": True,
    }, 0


def add_tool_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--docker-container", default="", help="Run pg_dump/pg_restore inside an existing container.")
    parser.add_argument("--pg-dump-bin", default="", help="Explicit local pg_dump binary path.")
    parser.add_argument("--pg-restore-bin", default="", help="Explicit local pg_restore binary path.")
    parser.add_argument("--timeout", type=int, default=300)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentOps MIS Postgres BYOC backup utility.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a custom-format Postgres archive and hash manifest.")
    create.add_argument("--dsn", default="", help="Postgres URL; prefer AGENTOPS_POSTGRES_DSN to keep it out of shell history.")
    create.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    add_tool_options(create)
    create.set_defaults(func=create_backup)

    verify = sub.add_parser("verify", help="Verify archive hash and pg_restore table-of-contents without printing rows.")
    verify.add_argument("--backup", default="")
    verify.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    add_tool_options(verify)
    verify.set_defaults(func=verify_backup)

    restore = sub.add_parser("restore", help="Restore only after explicit confirmation and target-state acknowledgement.")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--target-dsn", default="", help="Postgres URL; prefer AGENTOPS_POSTGRES_TARGET_DSN.")
    restore.add_argument("--confirm-restore", action="store_true")
    restore.add_argument("--target-empty-confirmed", action="store_true")
    restore.add_argument("--overwrite", action="store_true")
    restore.add_argument("--pre-restore-backup-dir", default="")
    add_tool_options(restore)
    restore.set_defaults(func=restore_backup)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload, status = args.func(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
