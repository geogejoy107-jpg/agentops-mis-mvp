#!/usr/bin/env python3
"""Verify the read-only human review queue API and CLI."""

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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = Request(base_url.rstrip("/") + path, headers={"Content-Type": "application/json"}, method="GET")
    try:
        with urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def run_cli(base_url: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def db_fingerprint(db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        tables = [
            ("approvals", "created_at"),
            ("memories", "updated_at"),
            ("artifacts", "created_at"),
            ("tasks", "updated_at"),
            ("runs", "created_at"),
            ("tool_calls", "created_at"),
            ("evaluations", "created_at"),
            ("evaluation_case_candidates", "updated_at"),
            ("evaluation_case_runs", "created_at"),
            ("audit_logs", "created_at"),
            ("runtime_events", "created_at"),
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


def validate_queue(payload: dict, label: str, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-review", f"{label} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "human_review_queue", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") in {"attention", "ready", "empty"}, f"{label} bad status: {payload}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} must not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} must not run live work: {safety}", failures)
    require(safety.get("raw_prompt_omitted") is True, f"{label} raw prompt omission missing", failures)
    require(safety.get("raw_response_omitted") is True, f"{label} raw response omission missing", failures)
    summary = payload.get("summary") or {}
    for key in [
        "pending_approvals",
        "memory_candidates",
        "evaluation_case_candidates",
        "ready_deliveries",
        "waiting_deliveries",
        "needs_attention_deliveries",
        "commander_synthesis_pending_reviews",
        "commander_synthesis_promotion_available",
        "commander_synthesis_memory_reviews",
        "retrieved_evaluation_case_candidates",
        "review_items_total",
        "returned_items",
    ]:
        require(isinstance(summary.get(key), int), f"{label} summary.{key} missing: {summary}", failures)
    require(isinstance(payload.get("review_items"), list), f"{label} review_items missing", failures)
    require(isinstance(payload.get("lanes"), dict), f"{label} lanes missing", failures)
    require(isinstance(payload.get("gates"), list) and payload.get("gates"), f"{label} gates missing", failures)
    require(isinstance(payload.get("next_actions"), list) and payload.get("next_actions"), f"{label} next_actions missing", failures)
    gate_ids = {gate.get("id") for gate in payload.get("gates") or []}
    require("commander_synthesis_lifecycle_visible" in gate_ids, f"{label} commander synthesis gate missing: {payload.get('gates')}", failures)
    require("evaluation_case_candidates_visible" in gate_ids, f"{label} evaluation case gate missing: {payload.get('gates')}", failures)
    lanes = payload.get("lanes") or {}
    require(isinstance(lanes.get("commander_synthesis"), list), f"{label} commander synthesis lane missing: {lanes}", failures)
    require(isinstance(lanes.get("evaluation_case_candidates"), list), f"{label} evaluation case lane missing: {lanes}", failures)
    for item in payload.get("review_items") or []:
        require(item.get("item_type") in {"approval", "memory_candidate", "customer_delivery", "commander_synthesis", "evaluation_case_candidate"}, f"{label} bad item type: {item}", failures)
        require(bool(item.get("item_id")), f"{label} item id missing: {item}", failures)
        require(bool(item.get("next_action")), f"{label} next action missing: {item}", failures)
        require(bool(item.get("cli_action")), f"{label} cli action missing: {item}", failures)
        require(isinstance(item.get("priority"), int), f"{label} item priority missing: {item}", failures)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify human review queue API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    parser.add_argument("--skip-cli", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    outputs: list[str] = []
    db_path = Path(args.db_path)
    before = db_fingerprint(db_path)

    status, payload = http_json(args.base_url, "/api/review/queue?limit=12")
    require(status == 200, f"API status mismatch: {status} {payload}", failures)
    validate_queue(payload, "api", failures)
    outputs.append(json.dumps(payload, ensure_ascii=False))

    cli_payload: dict = {}
    if not args.skip_cli:
        with tempfile.TemporaryDirectory(prefix="agentops-review-queue-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            proc = run_cli(args.base_url, ["review", "queue", "--limit", "8"], env)
            outputs.extend([proc.stdout, proc.stderr])
            cli_payload = load_json(proc)
            require(proc.returncode == 0, f"CLI failed: {proc.stderr or proc.stdout}", failures)
            validate_queue(cli_payload, "cli", failures)
            require(len(cli_payload.get("review_items") or []) <= 8, "CLI ignored limit", failures)

    after = db_fingerprint(db_path)
    db_unchanged = bool(before is not None and after is not None and before == after)
    if before is not None and after is not None:
        require(db_unchanged, "review queue changed database fingerprint", failures)
    secret_leaked = leaked_secret("\n".join(outputs))
    require(not secret_leaked, "review queue leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "api_status": payload.get("status"),
        "summary": payload.get("summary"),
        "cli_checked": not args.skip_cli,
        "cli_status": cli_payload.get("status"),
        "db_fingerprint_checked": before is not None and after is not None,
        "db_fingerprint_unchanged": db_unchanged,
        "secret_leaked": secret_leaked,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    if failures:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:3000], file=sys.stderr)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
