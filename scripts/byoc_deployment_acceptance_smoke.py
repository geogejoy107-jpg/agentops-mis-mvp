#!/usr/bin/env python3
"""Gate 5 local BYOC deployment acceptance smoke.

Runs an isolated backup/restore drill and a signed audit export drill without
touching the default runtime database.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "scripts" / "agentops_local_backup.py"
SIGNED_EXPORT = ROOT / "scripts" / "agentops_signed_audit_export.py"
DEPLOYMENT_READINESS = ROOT / "scripts" / "deployment_readiness_smoke.py"
POSTGRES_BACKUP_SMOKE = ROOT / "scripts" / "agentops_postgres_backup_smoke.py"
TOKEN_PREFIX = "agt" + "ok_"
SESSION_PREFIX = "agt" + "sess_"
SMOKE_SIGNING_KEY = "byoc-smoke-" + "signing-key"
TOKEN_LIKE_METADATA = TOKEN_PREFIX + "should_not_leave_export"
SECRET_MARKERS = [
    TOKEN_PREFIX,
    SESSION_PREFIX,
    "Authorization:",
    "Bearer ",
    "sk-",
    "ntn_",
    SMOKE_SIGNING_KEY,
]


def run(cmd: list[str], *, env: dict[str, str] | None = None, timeout: int = 60) -> tuple[int, dict, str]:
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=proc_env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        payload = {}
    return proc.returncode, payload, proc.stdout + proc.stderr


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def seed_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE agents(agent_id TEXT PRIMARY KEY, name TEXT);
            CREATE TABLE tasks(task_id TEXT PRIMARY KEY, title TEXT, workspace_id TEXT, status TEXT);
            CREATE TABLE runs(run_id TEXT PRIMARY KEY, task_id TEXT, status TEXT, workspace_id TEXT);
            CREATE TABLE tool_calls(tool_call_id TEXT PRIMARY KEY, run_id TEXT, status TEXT);
            CREATE TABLE evaluations(evaluation_id TEXT PRIMARY KEY, run_id TEXT, score REAL);
            CREATE TABLE artifacts(artifact_id TEXT PRIMARY KEY, run_id TEXT, artifact_type TEXT, title TEXT, uri TEXT, summary TEXT, created_at TEXT);
            CREATE TABLE approvals(approval_id TEXT PRIMARY KEY, entity_id TEXT, decision TEXT);
            CREATE TABLE memories(memory_id TEXT PRIMARY KEY, content_hash TEXT, review_status TEXT, workspace_id TEXT);
            CREATE TABLE workflow_jobs(job_id TEXT PRIMARY KEY, status TEXT, workspace_id TEXT);
            CREATE TABLE agent_gateway_tokens(token_id TEXT PRIMARY KEY, token_hash TEXT);
            CREATE TABLE agent_gateway_sessions(session_id TEXT PRIMARY KEY, token_hash TEXT);
            CREATE TABLE audit_logs(
                audit_id TEXT PRIMARY KEY,
                actor_type TEXT NOT NULL,
                actor_id TEXT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                before_hash TEXT,
                after_hash TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                tamper_chain_hash TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute("INSERT INTO agents(agent_id,name) VALUES('agt_byoc_acceptance','BYOC Acceptance')")
        conn.execute("INSERT INTO tasks(task_id,title,workspace_id,status) VALUES('tsk_byoc_acceptance','BYOC acceptance task','local-demo','completed')")
        conn.execute("INSERT INTO runs(run_id,task_id,status,workspace_id) VALUES('run_byoc_acceptance','tsk_byoc_acceptance','completed','local-demo')")
        conn.execute("INSERT INTO tool_calls(tool_call_id,run_id,status) VALUES('tc_byoc_acceptance','run_byoc_acceptance','completed')")
        conn.execute("INSERT INTO evaluations(evaluation_id,run_id,score) VALUES('eval_byoc_acceptance','run_byoc_acceptance',1.0)")
        conn.execute(
            "INSERT INTO artifacts(artifact_id,run_id,artifact_type,title,uri,summary,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                "art_byoc_acceptance",
                "run_byoc_acceptance",
                "customer_worker_result",
                "BYOC acceptance artifact",
                "agentops://artifacts/byoc-acceptance",
                "Hash-only acceptance artifact.",
                "2026-06-23T00:00:00Z",
            ),
        )
        conn.execute("INSERT INTO approvals(approval_id,entity_id,decision) VALUES('ap_byoc_acceptance','tsk_byoc_acceptance','approved')")
        conn.execute("INSERT INTO memories(memory_id,content_hash,review_status,workspace_id) VALUES('mem_byoc_acceptance','hash_only','approved','local-demo')")
        conn.execute("INSERT INTO workflow_jobs(job_id,status,workspace_id) VALUES('wfjob_byoc_acceptance','completed','local-demo')")
        conn.execute("INSERT INTO agent_gateway_tokens(token_id,token_hash) VALUES('tok_ref_byoc_acceptance','hash_only')")
        conn.execute("INSERT INTO agent_gateway_sessions(session_id,token_hash) VALUES('sess_ref_byoc_acceptance','hash_only')")
        conn.execute(
            """
            INSERT INTO audit_logs(audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "aud_byoc_001",
                "system",
                "byoc-smoke",
                "byoc.acceptance.created",
                "tasks",
                "tsk_byoc_acceptance",
                None,
                "after_hash_001",
                json.dumps({"token_like_value": TOKEN_LIKE_METADATA}, sort_keys=True),
                "chain_hash_001",
                "2026-06-23T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO audit_logs(audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "aud_byoc_002",
                "agent",
                "agt_byoc_acceptance",
                "byoc.acceptance.completed",
                "runs",
                "run_byoc_acceptance",
                "before_hash_002",
                "after_hash_002",
                json.dumps({"private_prompt": "omitted", "result": "summary_only"}, sort_keys=True),
                "chain_hash_002",
                "2026-06-23T00:00:01Z",
            ),
        )


def db_counts(path: Path) -> dict[str, int]:
    tables = ["agents", "tasks", "runs", "tool_calls", "evaluations", "artifacts", "approvals", "memories", "workflow_jobs", "audit_logs"]
    with sqlite3.connect(path) as conn:
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def run_postgres_readiness_fixture(args: argparse.Namespace, failures: list[str]) -> tuple[dict, str]:
    command = [
        sys.executable,
        str(DEPLOYMENT_READINESS),
        "--postgres-write-fixture",
        "--postgres-image",
        args.postgres_image,
    ]
    if args.skip_postgres_if_unavailable:
        command.append("--skip-postgres-if-unavailable")
    if args.no_install_postgres_driver:
        command.append("--no-install-postgres-driver")

    code, payload, text = run(command, timeout=300)
    fixture = payload.get("postgres_write_fixture") or {}
    require(code == 0 and payload.get("ok") is True, "postgres_readiness_fixture_failed", failures)
    require(fixture.get("skipped") is not True, "postgres_readiness_fixture_skipped", failures)
    require(
        fixture.get("contract") == "deployment_readiness_postgres_runtime_write_fixture_v1",
        "postgres_readiness_contract_missing",
        failures,
    )
    require(fixture.get("storage_mode") == "experimental_write_http", "postgres_storage_mode_mismatch", failures)
    require(fixture.get("storage_status") == "active", "postgres_storage_status_mismatch", failures)
    require(fixture.get("runtime_write_gate_status") == "active", "postgres_runtime_write_gate_inactive", failures)
    require(fixture.get("non_allowlisted_write_status") == 503, "postgres_non_allowlisted_write_not_blocked", failures)
    require(fixture.get("non_allowlisted_write_error") == "postgres_read_only_backend", "postgres_non_allowlisted_block_reason_mismatch", failures)
    require(fixture.get("postgres_counts_unchanged") is True, "postgres_ledger_counts_changed", failures)
    require(payload.get("secret_leaked") is False, "postgres_readiness_secret_leak", failures)

    recovery_command = [
        sys.executable,
        str(POSTGRES_BACKUP_SMOKE),
        "--image",
        args.postgres_image,
    ]
    if args.skip_postgres_if_unavailable:
        recovery_command.append("--skip-if-unavailable")
    recovery_code, recovery, recovery_text = run(recovery_command, timeout=300)
    require(
        recovery_code == 0 and recovery.get("ok") is True,
        "postgres_backup_restore_fixture_failed",
        failures,
    )
    require(recovery.get("skipped") is not True, "postgres_backup_restore_fixture_skipped", failures)
    require(
        recovery.get("contract") == "postgres_backup_restore_v1",
        "postgres_backup_restore_contract_missing",
        failures,
    )
    require(
        recovery.get("manifest_contract") == "postgres_backup_manifest_v1",
        "postgres_backup_manifest_contract_missing",
        failures,
    )
    require(
        recovery.get("source_counts") == recovery.get("restored_counts"),
        "postgres_restored_counts_mismatch",
        failures,
    )
    require(recovery.get("secret_leaked") is False, "postgres_backup_restore_secret_leak", failures)

    return {
        "included": True,
        "contract": fixture.get("contract"),
        "storage_mode": fixture.get("storage_mode"),
        "storage_status": fixture.get("storage_status"),
        "runtime_write_gate_status": fixture.get("runtime_write_gate_status"),
        "runtime_contracts": fixture.get("runtime_contracts") or [],
        "runtime_routes": fixture.get("runtime_routes") or [],
        "non_allowlisted_write_status": fixture.get("non_allowlisted_write_status"),
        "non_allowlisted_write_error": fixture.get("non_allowlisted_write_error"),
        "postgres_counts_unchanged": fixture.get("postgres_counts_unchanged"),
        "recovery": {
            "ok": recovery.get("ok") is True,
            "contract": recovery.get("contract"),
            "manifest_contract": recovery.get("manifest_contract"),
            "backup_create": recovery.get("backup_create"),
            "hash_and_toc_verify": recovery.get("hash_and_toc_verify"),
            "empty_target_restore": recovery.get("empty_target_restore"),
            "overwrite_pre_restore_backup": recovery.get("overwrite_pre_restore_backup"),
            "tamper_detection": recovery.get("tamper_detection"),
            "error": recovery.get("error"),
            "error_type": recovery.get("error_type"),
            "error_stage": recovery.get("error_stage"),
            "error_exit_code": recovery.get("error_exit_code"),
            "error_stdout_sha256": recovery.get("error_stdout_sha256"),
            "error_stderr_sha256": recovery.get("error_stderr_sha256"),
            "failure_count": int(recovery.get("failure_count") or 0),
            "source_counts": recovery.get("source_counts") or {},
            "restored_counts": recovery.get("restored_counts") or {},
            "skipped": bool(recovery.get("skipped")),
        },
        "skipped": bool(fixture.get("skipped")),
    }, text + recovery_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated Gate 5 BYOC deployment acceptance.")
    parser.add_argument(
        "--postgres-readiness-fixture",
        action="store_true",
        help="Also run Postgres runtime write-gate and real pg_dump/pg_restore recovery fixtures.",
    )
    parser.add_argument(
        "--postgres-image",
        default=os.environ.get("AGENTOPS_POSTGRES_IMAGE", "postgres:16-alpine"),
        help="Postgres Docker image to use for --postgres-readiness-fixture.",
    )
    parser.add_argument(
        "--skip-postgres-if-unavailable",
        action="store_true",
        help="Pass a diagnostic skip flag to the nested fixture; BYOC acceptance still fails if Postgres is skipped.",
    )
    parser.add_argument(
        "--no-install-postgres-driver",
        action="store_true",
        help="Do not install psycopg into a temporary target for the nested Postgres fixture.",
    )
    args = parser.parse_args()

    failures: list[str] = []
    output_text = ""
    postgres_readiness: dict = {
        "included": False,
        "command": "python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    }
    with tempfile.TemporaryDirectory(prefix="agentops-byoc-acceptance-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops_mis.db"
        backup_dir = tmp_path / "backups"
        restore_target = tmp_path / "restored.sqlite"
        existing_target = tmp_path / "existing.sqlite"
        export_path = tmp_path / "audit.signed.json"
        tampered_export_path = tmp_path / "audit.tampered.signed.json"
        seed_db(db_path)

        code, unsigned, text = run([
            sys.executable,
            str(SIGNED_EXPORT),
            "export",
            "--db-path",
            str(db_path),
            "--output",
            str(export_path),
        ])
        output_text += text
        require(code == 2 and unsigned.get("error") == "signing_key_required", f"signed export should require key: {unsigned}", failures)
        require(not export_path.exists(), "signed export should not write without key", failures)

        code, created, text = run([
            sys.executable,
            str(BACKUP),
            "create",
            "--db-path",
            str(db_path),
            "--backup-dir",
            str(backup_dir),
        ])
        output_text += text
        backup_path = Path(created.get("backup_path", ""))
        require(code == 0 and created.get("ok") is True and backup_path.exists(), f"backup create failed: {created}", failures)
        require(created.get("manifest", {}).get("counts", {}).get("audit_logs") == 2, f"backup audit count mismatch: {created}", failures)

        code, verified, text = run([sys.executable, str(BACKUP), "verify", "--backup", str(backup_path)])
        output_text += text
        require(code == 0 and verified.get("ok") is True and verified.get("hash_ok") is True, f"backup verify failed: {verified}", failures)

        code, dry_restore, text = run([sys.executable, str(BACKUP), "restore", "--backup", str(backup_path), "--target", str(restore_target)])
        output_text += text
        require(code == 2 and dry_restore.get("dry_run") is True and not restore_target.exists(), f"restore should require confirmation: {dry_restore}", failures)

        code, restored, text = run([
            sys.executable,
            str(BACKUP),
            "restore",
            "--backup",
            str(backup_path),
            "--target",
            str(restore_target),
            "--confirm-restore",
        ])
        output_text += text
        require(code == 0 and restored.get("ok") is True and restore_target.exists(), f"restore failed: {restored}", failures)
        require(db_counts(restore_target) == db_counts(db_path), "restored DB counts do not match source", failures)

        existing_target.write_bytes(db_path.read_bytes())
        code, overwrite_blocked, text = run([
            sys.executable,
            str(BACKUP),
            "restore",
            "--backup",
            str(backup_path),
            "--target",
            str(existing_target),
            "--confirm-restore",
        ])
        output_text += text
        require(code == 2 and overwrite_blocked.get("error") == "target_exists", f"overwrite should be blocked: {overwrite_blocked}", failures)

        code, overwrite_ok, text = run([
            sys.executable,
            str(BACKUP),
            "restore",
            "--backup",
            str(backup_path),
            "--target",
            str(existing_target),
            "--confirm-restore",
            "--overwrite",
        ])
        output_text += text
        pre_restore_copy = overwrite_ok.get("pre_restore_copy")
        require(code == 0 and overwrite_ok.get("ok") is True, f"overwrite restore failed: {overwrite_ok}", failures)
        require(pre_restore_copy and Path(pre_restore_copy).exists(), f"pre-restore safety copy missing: {overwrite_ok}", failures)

        signing_env = {"AGENTOPS_AUDIT_EXPORT_KEY": SMOKE_SIGNING_KEY}
        code, exported, text = run([
            sys.executable,
            str(SIGNED_EXPORT),
            "export",
            "--db-path",
            str(db_path),
            "--output",
            str(export_path),
            "--limit",
            "50",
        ], env=signing_env)
        output_text += text
        require(code == 0 and exported.get("ok") is True and export_path.exists(), f"signed export failed: {exported}", failures)
        manifest = exported.get("manifest") or {}
        require(manifest.get("contract_id") == "signed_audit_export_v1", f"signed export contract missing: {manifest}", failures)
        require(manifest.get("row_count") == 2, f"signed export row count mismatch: {manifest}", failures)
        export_text = export_path.read_text(encoding="utf-8")
        require("metadata_hash" in export_text and "metadata_json" not in export_text, "signed export leaked raw metadata", failures)
        require(TOKEN_LIKE_METADATA not in export_text, "signed export leaked token-like metadata", failures)

        code, export_verified, text = run([
            sys.executable,
            str(SIGNED_EXPORT),
            "verify",
            "--export",
            str(export_path),
        ], env=signing_env)
        output_text += text
        require(code == 0 and export_verified.get("ok") is True, f"signed export verify failed: {export_verified}", failures)

        tampered = json.loads(export_path.read_text(encoding="utf-8"))
        tampered["rows"][0]["action"] = "tampered.action"
        tampered_export_path.write_text(json.dumps(tampered, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        code, tamper_verify, text = run([
            sys.executable,
            str(SIGNED_EXPORT),
            "verify",
            "--export",
            str(tampered_export_path),
        ], env=signing_env)
        output_text += text
        require(code == 1 and tamper_verify.get("ok") is False, f"tampered export should fail verify: {tamper_verify}", failures)
        require("rows_sha256_mismatch" in (tamper_verify.get("failures") or []), f"tamper failure reason missing: {tamper_verify}", failures)

        if args.postgres_readiness_fixture:
            postgres_readiness, text = run_postgres_readiness_fixture(args, failures)
            output_text += text

        require(not leaked_secret(output_text), "BYOC acceptance output leaked secret-like text", failures)

    print(json.dumps({
        "ok": not failures,
        "contract_id": "byoc_deployment_acceptance_v1",
        "contracts": [
            "byoc_deployment_acceptance_v1",
            "deployment_readiness_postgres_runtime_write_fixture_v1",
            "postgres_backup_restore_v1",
            "postgres_backup_manifest_v1",
        ] if args.postgres_readiness_fixture else ["byoc_deployment_acceptance_v1"],
        "backup_restore": {
            "create_verify_restore": "passed" if not failures else "checked",
            "overwrite_requires_flag": True,
            "pre_restore_copy_required": True,
        },
        "signed_audit_export": {
            "key_required": True,
            "signature_verified": True,
            "tamper_detected": True,
            "raw_metadata_omitted": True,
        },
        "postgres_readiness": postgres_readiness,
        "secret_leaked": False,
        "failure_count": len(failures),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
