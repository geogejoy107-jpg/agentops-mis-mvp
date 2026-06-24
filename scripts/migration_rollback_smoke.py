#!/usr/bin/env python3
"""Verify migration preview and local rollback/restore evidence on an isolated DB."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "scripts" / "agentops_local_backup.py"
SECRET_MARKERS = ("Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, method: str, path: str, payload: dict | None = None) -> tuple[int, dict, str]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(req, timeout=30) as res:
            raw = res.read().decode("utf-8")
            return int(res.status), json.loads(raw) if raw else {}, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw), raw
        except Exception:
            return int(exc.code), {"raw": raw}, raw


def run_json(cmd: list[str]) -> tuple[int, dict, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    text = (proc.stdout or "") + (proc.stderr or "")
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception:
        payload = {}
    return int(proc.returncode), payload, text


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _, _ = http_json(base_url, "GET", "/api/agent-gateway/status")
            if status == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError("server did not become ready")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def count_rows(db_path: Path, sql: str, args: tuple = ()) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute(sql, args).fetchone()[0] or 0)


def latest_preview(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, preview_json FROM migration_runs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return {}
    try:
        preview = json.loads(row[1] or "{}")
    except Exception:
        preview = {}
    return {"status": row[0], "preview": preview}


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-migration-rollback-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops_mis.db"
        backup_dir = tmp_path / "backups"
        restore_target = tmp_path / "restored.sqlite"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            status, preview, raw = http_json(base_url, "POST", "/api/migration/preview", {})
            outputs.append(raw)
            require(status in {200, 201}, f"migration preview failed: {status} {preview}", failures)
            require(isinstance(preview.get("rollback"), list) and len(preview["rollback"]) >= 2, f"rollback steps missing: {preview}", failures)
            require(preview.get("from_base") and preview.get("to_base"), f"base evidence missing: {preview}", failures)
            require(preview.get("requires_human_confirmation"), f"human confirmation gate missing: {preview}", failures)
            require("audit_logs.tamper_chain_hash" in preview.get("non_migratable_objects", []), f"audit authority boundary missing: {preview}", failures)

            db_preview = latest_preview(db_path)
            require(db_preview.get("status") == "preview", f"migration_runs preview row missing: {db_preview}", failures)
            require((db_preview.get("preview") or {}).get("rollback") == preview.get("rollback"), "stored rollback preview mismatch", failures)
            migration_count = count_rows(db_path, "SELECT COUNT(*) FROM migration_runs WHERE status='preview'")
            audit_count = count_rows(db_path, "SELECT COUNT(*) FROM audit_logs WHERE action='migration.preview'")
            require(migration_count >= 1, "migration preview row count missing", failures)
            require(audit_count >= 1, "migration preview audit missing", failures)

            code, created, text = run_json([
                sys.executable,
                str(BACKUP),
                "create",
                "--db-path",
                str(db_path),
                "--backup-dir",
                str(backup_dir),
            ])
            outputs.append(text)
            backup_path = Path(created.get("backup_path", ""))
            manifest = created.get("manifest") or {}
            require(code == 0 and created.get("ok") is True and backup_path.exists(), f"backup create failed: {created}", failures)
            require(manifest.get("integrity_check") == "ok", f"backup manifest integrity missing: {created}", failures)
            require((manifest.get("safety") or {}).get("raw_rows_printed") is False, f"backup manifest safety missing: {created}", failures)

            code, verified, text = run_json([sys.executable, str(BACKUP), "verify", "--backup", str(backup_path)])
            outputs.append(text)
            require(code == 0 and verified.get("ok") is True and verified.get("integrity_check") == "ok", f"backup verify failed: {verified}", failures)

            code, dry_restore, text = run_json([
                sys.executable,
                str(BACKUP),
                "restore",
                "--backup",
                str(backup_path),
                "--target",
                str(restore_target),
            ])
            outputs.append(text)
            require(code == 2 and dry_restore.get("dry_run") is True, f"restore should require confirmation: {dry_restore}", failures)
            require(not restore_target.exists(), "dry-run restore unexpectedly wrote target DB", failures)

            code, restored, text = run_json([
                sys.executable,
                str(BACKUP),
                "restore",
                "--backup",
                str(backup_path),
                "--target",
                str(restore_target),
                "--confirm-restore",
            ])
            outputs.append(text)
            require(code == 0 and restored.get("ok") is True and restore_target.exists(), f"restore failed: {restored}", failures)
            restored_migrations = count_rows(restore_target, "SELECT COUNT(*) FROM migration_runs WHERE status='preview'")
            restored_audits = count_rows(restore_target, "SELECT COUNT(*) FROM audit_logs WHERE action='migration.preview'")
            require(restored_migrations == migration_count, f"restored migration count mismatch: {restored_migrations}/{migration_count}", failures)
            require(restored_audits == audit_count, f"restored audit count mismatch: {restored_audits}/{audit_count}", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])

    secret_leaked = leaked_secret("\n".join(outputs))
    if secret_leaked:
        failures.append("migration rollback smoke leaked token-like material")
    print(json.dumps({
        "ok": not failures,
        "operation": "migration_rollback_smoke",
        "migration_preview_rows": migration_count if "migration_count" in locals() else 0,
        "migration_audit_rows": audit_count if "audit_count" in locals() else 0,
        "restore_confirm_required": True,
        "restore_verified": bool("restored_migrations" in locals() and restored_migrations == migration_count),
        "secret_leaked": secret_leaked,
        "failures": failures,
        "token_omitted": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
