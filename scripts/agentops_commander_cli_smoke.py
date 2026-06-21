#!/usr/bin/env python3
"""Smoke-test Commander readback through the agentops CLI."""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
DEFAULT_DB = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"DIFY_KB_API_KEY=", re.IGNORECASE),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def run_cli(base_url: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def db_fingerprint(db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        tables = [
            ("tasks", "updated_at"),
            ("runs", "created_at"),
            ("workflow_jobs", "updated_at"),
            ("artifacts", "created_at"),
            ("memories", "updated_at"),
            ("approvals", "decided_at"),
            ("audit_logs", "created_at"),
            ("runtime_connectors", "updated_at"),
            ("agent_gateway_tokens", "last_used_at"),
            ("agent_gateway_sessions", "last_used_at"),
        ]
        result = {}
        for table, timestamp_col in tables:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not exists:
                continue
            row = conn.execute(
                f"SELECT COUNT(*) AS count, COALESCE(MAX({timestamp_col}), '') AS max_ts FROM {table}"
            ).fetchone()
            result[table] = {"count": int(row["count"] or 0), "max_ts": row["max_ts"] or ""}
        return result
    finally:
        conn.close()


def validate_safety(payload: dict, label: str) -> None:
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("token_omitted") is True, f"{label} safety.token_omitted missing")
    if "raw_prompt_omitted" in safety:
        require(safety.get("raw_prompt_omitted") is True, f"{label} safety.raw_prompt_omitted must be true")
    for key in ["ledger_mutated", "task_created", "run_created", "job_created"]:
        if key in safety:
            require(safety.get(key) is False, f"{label} safety.{key} must be false")


def validate_board(payload: dict) -> None:
    require(payload.get("provider") == "agentops-commander", f"board wrong provider: {payload}")
    require(payload.get("operation") == "project_board", f"board wrong operation: {payload}")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"board bad status: {payload.get('status')}")
    validate_safety(payload, "board")
    counts = payload.get("counts") or {}
    require(isinstance(counts.get("tasks_by_status"), dict), "board tasks_by_status missing")
    require(isinstance(counts.get("runs_by_status"), dict), "board runs_by_status missing")
    require(isinstance(payload.get("integration_gates"), list), "board integration_gates missing")
    require(bool(payload.get("recommended_next_actions")), "board recommended_next_actions missing")
    require(isinstance(payload.get("recent_work_packages"), list), "board recent_work_packages missing")


def validate_inbox(payload: dict, expected_bucket: str | None = None) -> None:
    require(payload.get("provider") == "agentops-commander", f"inbox wrong provider: {payload}")
    require(payload.get("operation") == "integration_inbox", f"inbox wrong operation: {payload}")
    validate_safety(payload, "inbox")
    require(
        any(isinstance(payload.get(key), list) for key in ["inbox_items", "items", "inbox", "integration_items", "entries"]),
        f"inbox must expose a list of readback items: {payload}",
    )
    summary = payload.get("summary") or {}
    buckets = summary.get("buckets") or {}
    require(isinstance(buckets, dict) and buckets, f"inbox bucket summary missing: {payload}")
    filter_payload = payload.get("filter") or {}
    require(isinstance(filter_payload, dict), "inbox filter metadata missing")
    if expected_bucket:
        require(filter_payload.get("bucket") == expected_bucket, f"inbox filter mismatch: {filter_payload}")
        for item in payload.get("inbox_items") or []:
            require(item.get("bucket") == expected_bucket, f"filtered inbox item has wrong bucket: {item}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Commander board/inbox CLI readback commands.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    args = parser.parse_args()

    failures: list[str] = []
    outputs: list[str] = []
    inbox_endpoint_available = False
    inbox_status = "unknown"
    db_path = Path(args.db_path)
    before = db_fingerprint(db_path)

    with tempfile.TemporaryDirectory(prefix="agentops-commander-cli-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env.pop("AGENTOPS_API_KEY", None)

        board = run_cli(args.base_url, ["commander", "board"], env)
        outputs.extend([board.stdout, board.stderr])
        board_payload = load_json(board)
        try:
            require(board.returncode == 0, f"commander board failed: {board.stderr or board.stdout}")
            validate_board(board_payload)
        except Exception as exc:
            failures.append(str(exc))

        inbox = run_cli(args.base_url, ["commander", "inbox"], env)
        outputs.extend([inbox.stdout, inbox.stderr])
        inbox_payload = load_json(inbox)
        if inbox.returncode != 0 and "404" in inbox.stderr:
            inbox_status = "inbox_endpoint_unavailable"
        else:
            try:
                require(inbox.returncode == 0, f"commander inbox failed: {inbox.stderr or inbox.stdout}")
                validate_inbox(inbox_payload)
                filtered_inbox = run_cli(args.base_url, ["commander", "inbox", "--bucket", "blocked", "--limit", "5"], env)
                outputs.extend([filtered_inbox.stdout, filtered_inbox.stderr])
                filtered_payload = load_json(filtered_inbox)
                require(filtered_inbox.returncode == 0, f"filtered commander inbox failed: {filtered_inbox.stderr or filtered_inbox.stdout}")
                validate_inbox(filtered_payload, expected_bucket="blocked")
                require(len(filtered_payload.get("inbox_items") or []) <= 5, "filtered commander inbox ignored limit")
                inbox_endpoint_available = True
                inbox_status = "available"
            except Exception as exc:
                failures.append(str(exc))
                inbox_status = "failed"

    after = db_fingerprint(db_path)
    db_fingerprint_unchanged = bool(before is not None and after is not None and before == after)
    secret_leaked = leaked_secret("\n".join(outputs))
    if secret_leaked:
        failures.append("Commander CLI output leaked token-like material")

    result = {
        "ok": not failures,
        "board_status": board_payload.get("status"),
        "board_gate_count": len(board_payload.get("integration_gates") or []),
        "board_recent_work_packages": len(board_payload.get("recent_work_packages") or []),
        "inbox_endpoint_available": inbox_endpoint_available,
        "inbox_status": inbox_status,
        "db_fingerprint_checked": before is not None and after is not None,
        "db_fingerprint_unchanged": db_fingerprint_unchanged,
        "secret_leaked": secret_leaked,
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if failures:
        print("board stdout:", board.stdout[-1600:], file=sys.stderr)
        print("board stderr:", board.stderr[-1600:], file=sys.stderr)
        print("inbox stdout:", inbox.stdout[-1600:], file=sys.stderr)
        print("inbox stderr:", inbox.stderr[-1600:], file=sys.stderr)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
