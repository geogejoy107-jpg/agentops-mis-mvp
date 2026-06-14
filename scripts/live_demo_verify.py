#!/usr/bin/env python3
"""Print local ledger counts before or after a live recording probe."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "agentops_mis.db"


COUNT_SQL = {
    "agents": "SELECT COUNT(*) FROM agents",
    "tasks": "SELECT COUNT(*) FROM tasks",
    "runs": "SELECT COUNT(*) FROM runs",
    "runtime_events": "SELECT COUNT(*) FROM runtime_events",
    "tool_calls": "SELECT COUNT(*) FROM tool_calls",
    "evaluations": "SELECT COUNT(*) FROM evaluations",
    "audit_logs": "SELECT COUNT(*) FROM audit_logs",
}


def read_counts() -> dict:
    if not DB_PATH.exists():
        return {key: 0 for key in COUNT_SQL}
    with sqlite3.connect(DB_PATH) as conn:
        counts = {}
        for key, sql in COUNT_SQL.items():
            try:
                counts[key] = conn.execute(sql).fetchone()[0]
            except sqlite3.Error:
                counts[key] = None
        return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["before", "after"])
    args = parser.parse_args()

    payload = {
        "mode": args.mode,
        "db_path": str(DB_PATH),
        "counts": read_counts(),
    }
    if args.mode == "before":
        payload["note"] = "Run the explicit confirmed live probe, then run this script again with 'after'."
    else:
        payload["note"] = "Compare with the before output. runs, runtime_events, evaluations and audit_logs should grow after a confirmed live probe."
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
