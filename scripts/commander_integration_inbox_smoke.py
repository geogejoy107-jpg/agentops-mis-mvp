#!/usr/bin/env python3
"""Smoke-test the read-only Commander Integration Inbox API."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
KNOWN_BUCKETS = {"ready_for_review", "still_running", "blocked", "late_or_stale", "needs_memory_review"}
KNOWN_STATUSES = {"ready", "attention", "blocked"}


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def token_like_leak(text: str) -> bool:
    markers = [
        "Authorization:",
        "Bearer ",
        "agtok_",
        "agtsess_",
        "sk-",
        "ntn_",
        "DIFY_KB_API_KEY=",
        "AGENTOPS_API_KEY=",
        "NOTION_TOKEN=",
    ]
    return any(marker in text for marker in markers)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


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
            if not table_exists(conn, table):
                continue
            row = conn.execute(
                f"SELECT COUNT(*) AS count, COALESCE(MAX({timestamp_col}), '') AS max_ts FROM {table}"
            ).fetchone()
            result[table] = {"count": int(row["count"] or 0), "max_ts": row["max_ts"] or ""}
        return result
    finally:
        conn.close()


def db_has_inbox_data(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(db_path)
    try:
        checks = [
            ("workflow_jobs", "SELECT COUNT(*) FROM workflow_jobs WHERE status IN ('queued','running','completed','failed')"),
            ("tasks", "SELECT COUNT(*) FROM tasks WHERE status IN ('running','waiting_approval','blocked','failed')"),
            ("runs", "SELECT COUNT(*) FROM runs WHERE status IN ('queued','running','completed','blocked','failed')"),
            ("memories", "SELECT COUNT(*) FROM memories WHERE review_status IN ('candidate','stale')"),
            ("approvals", "SELECT COUNT(*) FROM approvals WHERE decision='pending'"),
        ]
        for table, sql in checks:
            if table_exists(conn, table) and int((conn.execute(sql).fetchone() or [0])[0] or 0) > 0:
                return True
        return False
    finally:
        conn.close()


def validate_item(item: dict) -> None:
    require(item.get("bucket") in KNOWN_BUCKETS, f"bad bucket: {item}")
    for key in ["item_id", "title", "status", "recommended_action", "created_at", "updated_at"]:
        require(key in item, f"item missing {key}: {item}")
    require(item.get("recommended_action"), f"item action empty: {item}")
    require(isinstance(item.get("evidence_counts"), dict), f"item evidence_counts missing: {item}")
    decision = item.get("integration_decision")
    require(isinstance(decision, dict), f"item integration_decision missing: {item}")
    for key in ["decision", "status", "reason", "safe_to_auto_apply", "ledger_decision_required", "can_advance_without_waiting", "next_command"]:
        require(key in decision, f"integration_decision missing {key}: {item}")
    require(decision.get("safe_to_auto_apply") is False, f"inbox item must not auto-apply worker output: {item}")
    require(decision.get("next_command") == item.get("recommended_action"), f"integration decision command mismatch: {item}")
    if item.get("bucket") in {"ready_for_review", "blocked", "late_or_stale", "needs_memory_review"}:
        require(decision.get("ledger_decision_required") is True, f"review bucket must require a ledger decision: {item}")
    if item.get("bucket") == "still_running":
        require(decision.get("decision") == "continue_running", f"running item should stay independent: {item}")
    require(any(item.get(key) for key in ["task_id", "run_id", "job_id", "artifact_id", "memory_id"]), f"item has no ledger id: {item}")
    age = item.get("age_sec")
    require(age is None or isinstance(age, int), f"item age_sec must be int/null: {item}")


def validate(payload: dict, has_inbox_data: bool, expected_bucket: str | None = None) -> None:
    require(payload.get("provider") == "agentops-commander", f"wrong provider: {payload}")
    require(payload.get("operation") == "integration_inbox", f"wrong operation: {payload}")
    require(payload.get("status") in KNOWN_STATUSES, f"bad status: {payload.get('status')}")
    require(payload.get("token_omitted") is True, "token omission proof missing")
    require(payload.get("live_execution_performed") is False, "endpoint must not execute live work")
    safety = payload.get("safety") or {}
    for key in ["read_only", "token_omitted", "raw_prompt_omitted"]:
        require(safety.get(key) is True, f"safety flag {key} missing")
    for key in ["ledger_mutated", "task_created", "run_created", "job_created"]:
        require(safety.get(key) is False, f"safety flag {key} must be false")

    summary = payload.get("summary") or {}
    buckets = summary.get("buckets") or {}
    require(set(buckets) == KNOWN_BUCKETS, f"bucket summary mismatch: {buckets}")
    require(all(isinstance(buckets.get(bucket), int) for bucket in KNOWN_BUCKETS), f"bucket counts must be ints: {buckets}")
    filter_payload = payload.get("filter") or {}
    require(isinstance(filter_payload, dict), "filter metadata missing")
    if expected_bucket:
        require(filter_payload.get("bucket") == expected_bucket, f"filter bucket mismatch: {filter_payload}")
    inbox_items = payload.get("inbox_items")
    require(isinstance(inbox_items, list), "inbox_items must be a list")
    require(len(inbox_items) <= 25, f"inbox_items should stay bounded, got {len(inbox_items)}")
    require(summary.get("items_returned") == len(inbox_items), "items_returned mismatch")

    for item in inbox_items:
        validate_item(item)
        if expected_bucket:
            require(item.get("bucket") == expected_bucket, f"filtered item has wrong bucket: {item}")
    if has_inbox_data:
        require(inbox_items, "database has inbox-worthy data but endpoint returned no items")
        require(any(count > 0 for count in buckets.values()), "database has data but all bucket counts are zero")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Commander Integration Inbox read-only API.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    args = parser.parse_args()
    db_path = Path(args.db_path)
    has_inbox_data = db_has_inbox_data(db_path)
    before = db_fingerprint(db_path)
    try:
        status_code, payload = http_json(args.base_url, "/api/commander/integration-inbox")
        require(status_code == 200, f"integration inbox API failed: {status_code} {payload}")
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        require(not token_like_leak(raw), "integration inbox leaked token-like material")
        validate(payload, has_inbox_data)
        filtered_status, filtered_payload = http_json(args.base_url, "/api/commander/integration-inbox?bucket=blocked&limit=5")
        require(filtered_status == 200, f"filtered integration inbox API failed: {filtered_status} {filtered_payload}")
        filtered_raw = json.dumps(filtered_payload, ensure_ascii=False, sort_keys=True)
        require(not token_like_leak(filtered_raw), "filtered integration inbox leaked token-like material")
        validate(filtered_payload, False, expected_bucket="blocked")
        require(len(filtered_payload.get("inbox_items") or []) <= 5, "filtered inbox ignored limit")
        after = db_fingerprint(db_path)
        if before is not None and after is not None:
            require(before == after, f"database fingerprint changed: before={before} after={after}")
        summary = payload.get("summary") or {}
        result = {
            "ok": True,
            "status": payload.get("status"),
            "bucket_counts": summary.get("buckets"),
            "items_returned": len(payload.get("inbox_items") or []),
            "filtered_items_returned": len(filtered_payload.get("inbox_items") or []),
            "integration_decision_checked": True,
            "db_fingerprint_checked": before is not None and after is not None,
            "secret_leaked": False,
            "has_inbox_data": has_inbox_data,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
