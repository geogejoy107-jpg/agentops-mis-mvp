#!/usr/bin/env python3
"""Verify approval inspection is read-only and evidence-first."""

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
from urllib.parse import urlencode
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
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def http_json(base_url: str, path: str, query: dict | None = None) -> tuple[int, dict]:
    suffix = path
    if query:
        suffix += "?" + urlencode({key: value for key, value in query.items() if value is not None})
    req = Request(base_url.rstrip("/") + suffix, headers={"Content-Type": "application/json"}, method="GET")
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
        raise RuntimeError(f"Cannot reach {base_url}{suffix}: {exc.reason}") from exc


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
        result = {}
        for table, timestamp_col in [
            ("approvals", "created_at"),
            ("tasks", "updated_at"),
            ("runs", "created_at"),
            ("tool_calls", "created_at"),
            ("evaluations", "created_at"),
            ("artifacts", "created_at"),
            ("audit_logs", "created_at"),
            ("runtime_events", "created_at"),
        ]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                continue
            row = conn.execute(f"SELECT COUNT(*) AS count, COALESCE(MAX({timestamp_col}), '') AS max_ts FROM {table}").fetchone()
            result[table] = {"count": int(row["count"] or 0), "max_ts": row["max_ts"] or ""}
        return result
    finally:
        conn.close()


def first_approval_id(base_url: str) -> tuple[str | None, dict]:
    for decision in ("pending", None):
        status, payload = http_json(base_url, "/api/agent-gateway/approvals", {"decision": decision, "limit": 1})
        if status != 200:
            return None, payload
        rows = payload.get("approvals") or []
        if rows:
            return rows[0].get("approval_id"), payload
    return None, {}


def validate_inspect(payload: dict, label: str, approval_id: str, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-approval", f"{label} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "approval_inspect", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"{label} bad status: {payload}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing", failures)
    approval = payload.get("approval") or {}
    require(approval.get("approval_id") == approval_id, f"{label} approval id mismatch: {approval}", failures)
    evidence = payload.get("evidence") or {}
    for key in ["tool_calls", "evaluations", "artifacts", "audit_logs", "plan_evidence_manifests", "failed_evaluations", "open_failed_case_runs"]:
        require(isinstance(evidence.get(key), int), f"{label} evidence.{key} missing: {evidence}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} ledger mutation flag mismatch: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} live execution flag mismatch: {safety}", failures)
    require(safety.get("raw_prompt_omitted") is True, f"{label} prompt omission missing: {safety}", failures)
    require(safety.get("raw_response_omitted") is True, f"{label} response omission missing: {safety}", failures)
    require(isinstance(payload.get("recommended_actions"), list), f"{label} recommended_actions missing", failures)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify read-only approval inspect API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    parser.add_argument("--approval-id", default=None)
    parser.add_argument("--skip-cli", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    outputs: list[str] = []
    db_path = Path(args.db_path)
    before = db_fingerprint(db_path)
    approval_id = args.approval_id
    list_payload = {}
    if not approval_id:
        approval_id, list_payload = first_approval_id(args.base_url)
    require(bool(approval_id), f"no approval available to inspect: {list_payload}", failures)
    if not approval_id:
        print(json.dumps({"ok": False, "failures": failures}, ensure_ascii=False, indent=2))
        return 1

    status, payload = http_json(args.base_url, f"/api/agent-gateway/approvals/{approval_id}")
    require(status == 200, f"API status mismatch: {status} {payload}", failures)
    validate_inspect(payload, "api", approval_id, failures)
    outputs.append(json.dumps(payload, ensure_ascii=False))

    cli_payload: dict = {}
    if not args.skip_cli:
        with tempfile.TemporaryDirectory(prefix="agentops-approval-inspect-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            proc = run_cli(args.base_url, ["approval", "inspect", "--approval-id", approval_id], env)
            outputs.extend([proc.stdout, proc.stderr])
            cli_payload = load_json(proc)
            require(proc.returncode == 0, f"CLI failed: {proc.stderr or proc.stdout}", failures)
            validate_inspect(cli_payload, "cli", approval_id, failures)

    after = db_fingerprint(db_path)
    db_unchanged = bool(before is not None and after is not None and before == after)
    if before is not None and after is not None:
        require(db_unchanged, "approval inspect changed database fingerprint", failures)
    secret_leaked = leaked_secret("\n".join(outputs))
    require(not secret_leaked, "approval inspect leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "approval_id": approval_id,
        "api_status": payload.get("status"),
        "approval_kind": payload.get("approval_kind"),
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
