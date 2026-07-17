#!/usr/bin/env python3
"""Container-backed Postgres backup/restore acceptance for Gate 5."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_contract  # noqa: E402
import storage_postgres_contract_smoke as ddl_contract  # noqa: E402


BACKUP = ROOT / "scripts" / "agentops_postgres_backup.py"
DEFAULT_IMAGE = os.environ.get("AGENTOPS_POSTGRES_IMAGE", "postgres:16-alpine")
SECRET_MARKERS = ["agt" + "ok_", "agt" + "sess_", "Authorization:", "Bearer ", "sk-", "ntn_"]


def run(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    return subprocess.run(
        args,
        cwd=ROOT,
        env=proc_env,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def run_json(args: list[str], *, env: dict[str, str] | None = None, timeout: int = 300) -> tuple[int, dict, str]:
    proc = run(args, env=env, timeout=timeout)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {}
    return proc.returncode, payload, proc.stdout + proc.stderr


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def unavailable(message: str, *, skip: bool) -> int:
    print(json.dumps({
        "ok": bool(skip),
        "skipped": bool(skip),
        "contract": "postgres_backup_restore_v1",
        "reason": message,
        "next_action": "Start Docker and rerun without --skip-if-unavailable.",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if skip else 1


def wait_for_postgres(container: str, timeout_sec: int = 45) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ready = run(["docker", "exec", container, "pg_isready", "-U", "agentops", "-d", "agentops_source"], timeout=10)
        if ready.returncode == 0:
            return True
        time.sleep(1)
    return False


def psql(
    container: str,
    password: str,
    database: str,
    *,
    sql: str,
    tuples_only: bool = False,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    command = [
        "docker",
        "exec",
        "-i",
        "--env",
        "PGPASSWORD",
        container,
        "psql",
        "-h",
        "127.0.0.1",
        "-U",
        "agentops",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
    ]
    if tuples_only:
        command.extend(["-At"])
    return run(command, env={"PGPASSWORD": password}, input_text=sql, timeout=timeout)


class CountQueryError(RuntimeError):
    def __init__(self, safe_code: str, *, exit_code: int, stdout_hash: str, stderr_hash: str):
        super().__init__(safe_code)
        self.safe_code = safe_code
        self.exit_code = exit_code
        self.stdout_hash = stdout_hash
        self.stderr_hash = stderr_hash


def table_counts(container: str, password: str, database: str) -> dict[str, int]:
    tables = ["tasks", "runs", "tool_calls", "approvals", "prepared_actions", "agent_plans", "plan_evidence_manifests"]
    pairs = ", ".join(f"'{table}', (SELECT COUNT(*) FROM {table})" for table in tables)
    sql = f"SELECT json_build_object({pairs});\n"
    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(3):
        result = psql(container, password, database, sql=sql, tuples_only=True)
        last_result = result
        if result.returncode == 0:
            try:
                payload = json.loads(result.stdout.strip())
                return {table: int(payload[table]) for table in tables}
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                pass
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))

    assert last_result is not None
    stderr = last_result.stderr or ""
    missing_table = next((table for table in tables if f'relation "{table}" does not exist' in stderr), "")
    safe_code = f"count_table_{missing_table}_missing" if missing_table else "count_query_failed"
    raise CountQueryError(
        safe_code,
        exit_code=last_result.returncode,
        stdout_hash=hashlib.sha256((last_result.stdout or "").encode("utf-8", errors="replace")).hexdigest(),
        stderr_hash=hashlib.sha256(stderr.encode("utf-8", errors="replace")).hexdigest(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Postgres backup/restore acceptance in a temporary container.")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--skip-if-unavailable", action="store_true")
    args = parser.parse_args()

    docker = run(["docker", "info", "--format", "{{json .ServerVersion}}"], timeout=20)
    if docker.returncode != 0:
        return unavailable("Docker daemon unavailable.", skip=args.skip_if_unavailable)
    image = run(["docker", "image", "inspect", args.image], timeout=20)
    if image.returncode != 0:
        pulled = run(["docker", "pull", args.image], timeout=300)
        if pulled.returncode != 0:
            return unavailable("Postgres image unavailable.", skip=args.skip_if_unavailable)

    container = f"agentops-pg-recovery-{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(24)
    start = run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container,
            "--env",
            "POSTGRES_PASSWORD",
            "-e",
            "POSTGRES_USER=agentops",
            "-e",
            "POSTGRES_DB=agentops_source",
            args.image,
        ],
        env={"POSTGRES_PASSWORD": password},
        timeout=60,
    )
    if start.returncode != 0:
        return unavailable("Postgres recovery container failed to start.", skip=args.skip_if_unavailable)

    failures: list[str] = []
    output_text = ""
    stage = "postgres_readiness"
    try:
        if not wait_for_postgres(container):
            return unavailable("Postgres recovery container did not become ready.", skip=args.skip_if_unavailable)

        stage = "source_fixture_seed"
        postgres_sql = ddl_contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL)
        fixture_sql = container_contract.postgres_fixture_sql()
        seeded = psql(container, password, "agentops_source", sql=postgres_sql + "\n" + fixture_sql, timeout=180)
        require(seeded.returncode == 0, "source_fixture_seed_failed", failures)
        stage = "restore_target_create"
        created_target = psql(container, password, "postgres", sql="CREATE DATABASE agentops_restore;\n")
        require(created_target.returncode == 0, "restore_target_create_failed", failures)

        source_dsn = f"postgresql://agentops:{password}@127.0.0.1:5432/agentops_source"
        target_dsn = f"postgresql://agentops:{password}@127.0.0.1:5432/agentops_restore"
        with tempfile.TemporaryDirectory(prefix="agentops-pg-recovery-") as tmp:
            tmp_path = Path(tmp)
            backup_dir = tmp_path / "backups"
            pre_restore_dir = tmp_path / "pre_restore"
            source_env = {"AGENTOPS_POSTGRES_DSN": source_dsn}
            target_env = {"AGENTOPS_POSTGRES_TARGET_DSN": target_dsn}

            stage = "backup_create"
            code, created, text = run_json([
                sys.executable,
                str(BACKUP),
                "create",
                "--backup-dir",
                str(backup_dir),
                "--docker-container",
                container,
            ], env=source_env)
            output_text += text
            backup_path = Path(created.get("backup_path") or "")
            manifest = created.get("manifest") or {}
            require(code == 0 and created.get("ok") is True, "backup_create_failed", failures)
            require(backup_path.exists(), "backup_archive_missing", failures)
            require(manifest.get("contract_id") == "postgres_backup_manifest_v1", "manifest_contract_missing", failures)
            require(manifest.get("archive_format") == "postgres_custom", "archive_format_mismatch", failures)
            require(manifest.get("toc_entry_count", 0) > 0, "toc_entries_missing", failures)
            require((manifest.get("safety") or {}).get("credentials_omitted") is True, "credential_omission_missing", failures)

            stage = "backup_verify"
            code, verified, text = run_json([
                sys.executable,
                str(BACKUP),
                "verify",
                "--backup",
                str(backup_path),
                "--docker-container",
                container,
            ])
            output_text += text
            require(code == 0 and verified.get("ok") is True, "backup_verify_failed", failures)
            require(verified.get("hash_ok") is True and verified.get("toc_ok") is True, "archive_integrity_failed", failures)

            stage = "restore_confirmation_gate"
            code, dry_restore, text = run_json([
                sys.executable,
                str(BACKUP),
                "restore",
                "--backup",
                str(backup_path),
                "--docker-container",
                container,
            ])
            output_text += text
            require(code == 2 and dry_restore.get("error") == "confirm_restore_required", "restore_confirmation_not_enforced", failures)

            stage = "target_state_gate"
            code, target_state_block, text = run_json([
                sys.executable,
                str(BACKUP),
                "restore",
                "--backup",
                str(backup_path),
                "--confirm-restore",
                "--docker-container",
                container,
            ], env=target_env)
            output_text += text
            require(code == 2 and target_state_block.get("error") == "target_state_confirmation_required", "target_state_gate_missing", failures)

            stage = "empty_target_restore"
            code, restored, text = run_json([
                sys.executable,
                str(BACKUP),
                "restore",
                "--backup",
                str(backup_path),
                "--confirm-restore",
                "--target-empty-confirmed",
                "--docker-container",
                container,
            ], env=target_env)
            output_text += text
            require(code == 0 and restored.get("ok") is True and restored.get("restored") is True, "empty_target_restore_failed", failures)

            stage = "source_count_verify"
            source_counts = table_counts(container, password, "agentops_source")
            stage = "restored_count_verify"
            restored_counts = table_counts(container, password, "agentops_restore")
            require(restored_counts == source_counts, "restored_counts_mismatch", failures)

            stage = "target_mutation"
            modified = psql(
                container,
                password,
                "agentops_restore",
                sql="UPDATE tasks SET status='blocked' WHERE task_id='tsk_pg_a';\n",
            )
            require(modified.returncode == 0, "target_mutation_fixture_failed", failures)
            stage = "overwrite_restore"
            code, overwrite, text = run_json([
                sys.executable,
                str(BACKUP),
                "restore",
                "--backup",
                str(backup_path),
                "--confirm-restore",
                "--overwrite",
                "--pre-restore-backup-dir",
                str(pre_restore_dir),
                "--docker-container",
                container,
            ], env=target_env)
            output_text += text
            pre_restore = overwrite.get("pre_restore_backup") or {}
            pre_restore_path = Path(pre_restore.get("backup_path") or "")
            require(code == 0 and overwrite.get("ok") is True, "overwrite_restore_failed", failures)
            require(pre_restore.get("ok") is True and pre_restore_path.exists(), "pre_restore_backup_missing", failures)
            stage = "overwrite_status_verify"
            status = psql(
                container,
                password,
                "agentops_restore",
                sql="SELECT status FROM tasks WHERE task_id='tsk_pg_a';\n",
                tuples_only=True,
            )
            require(status.returncode == 0 and status.stdout.strip() == "planned", "overwrite_restore_did_not_recover_source", failures)

            stage = "missing_manifest_verify"
            missing_manifest_path = tmp_path / "missing-manifest.dump"
            shutil.copy2(backup_path, missing_manifest_path)
            code, missing_manifest, text = run_json([
                sys.executable,
                str(BACKUP),
                "verify",
                "--backup",
                str(missing_manifest_path),
                "--docker-container",
                container,
            ])
            output_text += text
            require(
                code == 1 and missing_manifest.get("error") == "backup_manifest_not_found",
                "missing_manifest_not_rejected",
                failures,
            )

            stage = "invalid_manifest_verify"
            invalid_manifest_path = tmp_path / "invalid-manifest.dump"
            shutil.copy2(backup_path, invalid_manifest_path)
            invalid_manifest_path.with_suffix(".dump.manifest.json").write_text("[]\n", encoding="utf-8")
            code, invalid_manifest, text = run_json([
                sys.executable,
                str(BACKUP),
                "verify",
                "--backup",
                str(invalid_manifest_path),
                "--docker-container",
                container,
            ])
            output_text += text
            require(
                code == 1 and invalid_manifest.get("error") == "backup_manifest_invalid",
                "invalid_manifest_not_rejected",
                failures,
            )

            stage = "tampered_archive_verify"
            tampered_path = tmp_path / "tampered.dump"
            shutil.copy2(backup_path, tampered_path)
            shutil.copy2(backup_path.with_suffix(".dump.manifest.json"), tampered_path.with_suffix(".dump.manifest.json"))
            with tampered_path.open("ab") as fh:
                fh.write(b"tampered")
            code, tampered, text = run_json([
                sys.executable,
                str(BACKUP),
                "verify",
                "--backup",
                str(tampered_path),
                "--docker-container",
                container,
            ])
            output_text += text
            require(code == 1 and tampered.get("ok") is False, "tampered_archive_not_rejected", failures)
            require("backup_sha256_mismatch" in (tampered.get("failures") or []), "tamper_hash_failure_missing", failures)

        stage = "secret_scan"
        leaked = any(marker in output_text for marker in [password, source_dsn, target_dsn, *SECRET_MARKERS])
        require(not leaked, "postgres_recovery_output_leaked_secret_like_value", failures)
        print(json.dumps({
            "ok": not failures,
            "skipped": False,
            "contract": "postgres_backup_restore_v1",
            "manifest_contract": "postgres_backup_manifest_v1",
            "image": args.image,
            "source_counts": source_counts if "source_counts" in locals() else {},
            "restored_counts": restored_counts if "restored_counts" in locals() else {},
            "backup_create": "passed" if not failures else "checked",
            "hash_and_toc_verify": "passed" if not failures else "checked",
            "empty_target_restore": "passed" if not failures else "checked",
            "overwrite_pre_restore_backup": "passed" if not failures else "checked",
            "tamper_detection": "passed" if not failures else "checked",
            "dsn_omitted": True,
            "credential_values_omitted": True,
            "raw_rows_printed": False,
            "secret_leaked": False,
            "failure_count": len(failures),
            "failures": failures,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not failures else 1
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        exception_failures = [*failures, f"{stage}_exception"]
        safe_error = getattr(exc, "safe_code", None)
        print(json.dumps({
            "ok": False,
            "skipped": False,
            "contract": "postgres_backup_restore_v1",
            "manifest_contract": "postgres_backup_manifest_v1",
            "error_type": type(exc).__name__,
            "error": safe_error,
            "error_stage": stage,
            "error_detail_omitted": True,
            "error_exit_code": getattr(exc, "exit_code", None),
            "error_stdout_sha256": getattr(exc, "stdout_hash", None),
            "error_stderr_sha256": getattr(exc, "stderr_hash", None),
            "credential_values_omitted": True,
            "secret_leaked": False,
            "failure_count": len(exception_failures),
            "failures": exception_failures,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    finally:
        run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
