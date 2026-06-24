#!/usr/bin/env python3
"""Smoke test local backup utility against an isolated SQLite DB."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "scripts" / "agentops_local_backup.py"


def run(cmd: list[str]) -> tuple[int, dict, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=45, check=False)
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        payload = {}
    return proc.returncode, payload, proc.stdout + proc.stderr


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in ["agtok_", "agtsess_", "Authorization:", "Bearer ", "sk-", "ntn_"])


def seed_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE agents(agent_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE tasks(task_id TEXT PRIMARY KEY, title TEXT)")
        conn.execute("CREATE TABLE runs(run_id TEXT PRIMARY KEY, task_id TEXT)")
        conn.execute("CREATE TABLE agent_gateway_tokens(token_id TEXT PRIMARY KEY, token_hash TEXT)")
        conn.execute("INSERT INTO agents(agent_id,name) VALUES('agt_backup_smoke','Backup Smoke')")
        conn.execute("INSERT INTO tasks(task_id,title) VALUES('tsk_backup_smoke','Backup smoke task')")
        conn.execute("INSERT INTO runs(run_id,task_id) VALUES('run_backup_smoke','tsk_backup_smoke')")
        conn.execute("INSERT INTO agent_gateway_tokens(token_id,token_hash) VALUES('tok_ref_backup_smoke','hash_only')")


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-backup-smoke-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops_mis.db"
        backup_dir = tmp_path / "backups"
        restore_target = tmp_path / "restored.sqlite"
        seed_db(db_path)

        code, created, create_text = run([
            sys.executable,
            str(BACKUP),
            "create",
            "--db-path",
            str(db_path),
            "--backup-dir",
            str(backup_dir),
        ])
        backup_path = Path(created.get("backup_path", ""))
        require(code == 0 and created.get("ok") is True, f"backup create failed: {created}", failures)
        require(backup_path.exists(), f"backup file missing: {backup_path}", failures)
        require(created.get("manifest", {}).get("counts", {}).get("agents") == 1, f"agent count mismatch: {created}", failures)
        require(created.get("manifest", {}).get("safety", {}).get("raw_rows_printed") is False, f"safety missing: {created}", failures)

        code, verified, verify_text = run([
            sys.executable,
            str(BACKUP),
            "verify",
            "--backup",
            str(backup_path),
        ])
        require(code == 0 and verified.get("ok") is True, f"backup verify failed: {verified}", failures)
        require(verified.get("integrity_check") == "ok", f"integrity failed: {verified}", failures)

        code, dry_restore, dry_text = run([
            sys.executable,
            str(BACKUP),
            "restore",
            "--backup",
            str(backup_path),
            "--target",
            str(restore_target),
        ])
        require(code == 2 and dry_restore.get("dry_run") is True, f"restore should require confirmation: {dry_restore}", failures)
        require(not restore_target.exists(), "restore target should not exist after dry run", failures)

        code, restored, restore_text = run([
            sys.executable,
            str(BACKUP),
            "restore",
            "--backup",
            str(backup_path),
            "--target",
            str(restore_target),
            "--confirm-restore",
        ])
        require(code == 0 and restored.get("ok") is True, f"restore failed: {restored}", failures)
        require(restore_target.exists(), "restore target missing", failures)
        with sqlite3.connect(restore_target) as conn:
            count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        require(count == 1, f"restored DB count mismatch: {count}", failures)
        require(not leaked_secret(create_text + verify_text + dry_text + restore_text), "backup smoke leaked secret-like text", failures)

    print(json.dumps({
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
