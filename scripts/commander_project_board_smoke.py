#!/usr/bin/env python3
"""Smoke-test the read-only Commander Project Board API."""
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
    ]
    return any(marker in text for marker in markers)


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


def validate(payload: dict) -> None:
    require(payload.get("provider") == "agentops-commander", f"wrong provider: {payload}")
    require(payload.get("operation") == "project_board", f"wrong operation: {payload}")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"bad status: {payload.get('status')}")
    require(payload.get("token_omitted") is True, "token omission proof missing")
    require(payload.get("live_execution_performed") is False, "endpoint must not execute live work")
    safety = payload.get("safety") or {}
    for key in ["read_only", "token_omitted", "raw_prompt_omitted"]:
        require(safety.get(key) is True, f"safety flag {key} missing")
    for key in ["ledger_mutated", "task_created", "run_created", "job_created"]:
        require(safety.get(key) is False, f"safety flag {key} must be false")
    counts = payload.get("counts") or {}
    require(isinstance(counts.get("tasks_by_status"), dict), "tasks_by_status missing")
    require(isinstance(counts.get("runs_by_status"), dict), "runs_by_status missing")
    for key in ["pending_approvals", "active_workflow_jobs", "stuck_workflow_jobs", "recent_artifacts", "memory_candidates", "synthesis_artifacts", "synthesis_pending_reviews", "synthesis_promoted_deliveries"]:
        require(isinstance(counts.get(key), int), f"count {key} missing")
    gate_ids = {gate.get("id") for gate in payload.get("integration_gates") or []}
    for gate_id in {"evidence_chain", "worker_fleet_health", "approvals_pending", "memory_review", "synthesis_lifecycle", "adapter_readiness"}:
        require(gate_id in gate_ids, f"missing integration gate {gate_id}")
    lifecycle = payload.get("synthesis_lifecycle") or {}
    require(lifecycle.get("status") in {"empty", "created", "review_pending", "promotion_available", "promoted"}, f"bad synthesis lifecycle: {lifecycle}")
    require((lifecycle.get("safety") or {}).get("read_only") is True, f"synthesis lifecycle not read-only: {lifecycle}")
    require(payload.get("recommended_next_actions"), "recommended_next_actions must be nonempty")
    require(isinstance(payload.get("recent_work_packages"), list), "recent_work_packages must be a list")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Commander Project Board read-only API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    args = parser.parse_args()
    db_path = Path(args.db_path)
    before = db_fingerprint(db_path)
    try:
        status_code, payload = http_json(args.base_url, "/api/commander/project-board")
        require(status_code == 200, f"project board API failed: {status_code} {payload}")
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        require(not token_like_leak(raw), "project board leaked token-like material")
        validate(payload)
        after = db_fingerprint(db_path)
        if before is not None and after is not None:
            require(before == after, f"database fingerprint changed: before={before} after={after}")
        result = {
            "ok": True,
            "status": payload.get("status"),
            "gate_count": len(payload.get("integration_gates") or []),
            "action_count": len(payload.get("recommended_next_actions") or []),
            "recent_work_packages": len(payload.get("recent_work_packages") or []),
            "db_fingerprint_checked": before is not None and after is not None,
            "secret_leaked": False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
