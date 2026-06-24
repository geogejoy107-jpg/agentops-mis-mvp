#!/usr/bin/env python3
"""Verify SQLite connection pragmas for local concurrent control-plane use."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agentops-sqlite-pragmas-") as tmp:
        db_path = Path(tmp) / "agentops_pragmas.db"
        code = """
import json
import server
conn = server.db()
try:
    result = {
        "foreign_keys": conn.execute("PRAGMA foreign_keys").fetchone()[0],
        "busy_timeout": conn.execute("PRAGMA busy_timeout").fetchone()[0],
        "journal_mode": conn.execute("PRAGMA journal_mode").fetchone()[0],
        "synchronous": conn.execute("PRAGMA synchronous").fetchone()[0],
    }
    print(json.dumps(result, sort_keys=True))
finally:
    conn.close()
"""
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        failures: list[str] = []
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result = {}
            failures.append(f"invalid JSON output: stdout={proc.stdout!r} stderr={proc.stderr!r}")
        if proc.returncode != 0:
            failures.append(f"subprocess failed: {proc.stderr or proc.stdout}")
        if result.get("foreign_keys") != 1:
            failures.append(f"foreign_keys disabled: {result}")
        if int(result.get("busy_timeout") or 0) < 5000:
            failures.append(f"busy_timeout too low: {result}")
        if str(result.get("journal_mode") or "").lower() != "wal":
            failures.append(f"journal_mode not WAL: {result}")
        if result.get("synchronous") != 1:
            failures.append(f"synchronous not NORMAL: {result}")
        print(json.dumps({
            "ok": not failures,
            "db_path": str(db_path),
            "result": result,
            "failures": failures,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
