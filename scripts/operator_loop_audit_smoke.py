#!/usr/bin/env python3
"""Verify the read-only operator loop-audit API and CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
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
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]
EXPECTED_STEPS = ["read", "plan", "retrieve", "compare", "execute", "verify", "record"]


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
        result = {}
        for table, timestamp_col in [
            ("approvals", "created_at"),
            ("memories", "updated_at"),
            ("artifacts", "created_at"),
            ("tasks", "updated_at"),
            ("runs", "created_at"),
            ("tool_calls", "created_at"),
            ("evaluations", "created_at"),
            ("evaluation_case_runs", "created_at"),
            ("agent_plans", "updated_at"),
            ("plan_evidence_manifests", "updated_at"),
            ("workflow_jobs", "updated_at"),
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


def validate_payload(payload: dict, label: str, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-operator", f"{label} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "loop_audit", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") in {"blocked", "attention", "ready"}, f"{label} bad status: {payload}", failures)
    require(payload.get("method") == "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD", f"{label} method mismatch: {payload}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} must not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} must not run live work: {safety}", failures)
    require(safety.get("raw_prompt_omitted") is True, f"{label} raw prompt omission missing", failures)
    require(safety.get("raw_response_omitted") is True, f"{label} raw response omission missing", failures)
    summary = payload.get("summary") or {}
    for key in [
        "steps",
        "pass",
        "attention",
        "blocked",
        "knowledge_documents",
        "verified_agent_plans",
        "plan_bound_runs",
        "verified_plan_evidence_manifests",
        "evidence_gap_runs",
        "loop_runs",
        "loop_verified_plan_evidence_manifests",
        "loop_blocked_plan_evidence_manifests",
        "loop_memory_candidates",
        "loop_approved_memories",
        "loop_pending_approvals",
        "pending_approvals",
        "memory_candidates",
        "audit_logs",
    ]:
        require(isinstance(summary.get(key), int), f"{label} summary.{key} missing: {summary}", failures)
    steps = payload.get("steps") or []
    require([step.get("id") for step in steps] == EXPECTED_STEPS, f"{label} steps mismatch: {steps}", failures)
    for step in steps:
        require(step.get("status") in {"pass", "attention", "blocked"}, f"{label} bad step status: {step}", failures)
        require(bool(step.get("label")), f"{label} step label missing: {step}", failures)
        require(bool(step.get("command")), f"{label} step command missing: {step}", failures)
        require(isinstance(step.get("evidence"), dict), f"{label} step evidence missing: {step}", failures)
        require(step.get("token_omitted") is True, f"{label} step token omission missing: {step}", failures)
    require(bool(payload.get("next_actions")), f"{label} next_actions missing", failures)
    require(isinstance(payload.get("source_status"), dict), f"{label} source_status missing", failures)
    sources = payload.get("sources") or {}
    for key in ["action_plan", "task_intake", "execution_evidence", "dispatch_evidence", "loop_readback"]:
        require(key in sources, f"{label} sources.{key} missing: {sources}", failures)
    loop_readback = payload.get("loop_readback") or {}
    require(loop_readback.get("operation") == "hermes_openclaw_loop_readback", f"{label} loop readback missing: {loop_readback}", failures)
    require(loop_readback.get("token_omitted") is True, f"{label} loop readback token omission missing", failures)
    loop_runs = int(summary.get("loop_runs") or 0)
    loop_verified = int(summary.get("loop_verified_plan_evidence_manifests") or 0)
    loop_blocked = int(summary.get("loop_blocked_plan_evidence_manifests") or 0)
    if payload.get("loop_id") and loop_runs and loop_verified >= loop_runs and loop_blocked == 0:
        step_status = {step.get("id"): step.get("status") for step in steps}
        require(payload.get("status") != "blocked", f"{label} scoped verified loop should not be globally blocked: {payload.get('status')} {summary}", failures)
        for step_id in ["plan", "retrieve", "compare", "execute", "verify"]:
            require(step_status.get(step_id) == "pass", f"{label} scoped loop step {step_id} should pass: {step_status}", failures)
        if step_status.get("record") == "pass":
            require(int(summary.get("loop_approved_memories") or 0) > 0, f"{label} record pass requires approved loop memory: {summary}", failures)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify operator loop-audit API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--loop-id", default="")
    parser.add_argument("--skip-cli", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    outputs: list[str] = []
    db_path = Path(args.db_path)
    before = db_fingerprint(db_path)
    loop_query = f"&loop_id={args.loop_id}" if args.loop_id else ""

    status, payload = http_json(args.base_url, f"/api/operator/loop-audit?limit={args.limit}{loop_query}")
    require(status == 200, f"API status mismatch: {status} {payload}", failures)
    validate_payload(payload, "api", failures)
    outputs.append(json.dumps(payload, ensure_ascii=False))

    cli_payload: dict = {}
    if not args.skip_cli:
        with tempfile.TemporaryDirectory(prefix="agentops-loop-audit-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            cli_args = ["operator", "loop-audit", "--limit", str(args.limit)]
            if args.loop_id:
                cli_args.extend(["--loop-id", args.loop_id])
            proc = run_cli(args.base_url, cli_args, env)
            outputs.extend([proc.stdout, proc.stderr])
            cli_payload = load_json(proc)
            require(proc.returncode == 0, f"CLI failed: {proc.stderr or proc.stdout}", failures)
            validate_payload(cli_payload, "cli", failures)

    after = db_fingerprint(db_path)
    db_unchanged = bool(before is not None and after is not None and before == after)
    if before is not None and after is not None:
        require(db_unchanged, "operator loop audit changed database fingerprint", failures)
    secret_leaked = leaked_secret("\n".join(outputs))
    require(not secret_leaked, "operator loop audit leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "api_status": payload.get("status"),
        "cli_checked": not args.skip_cli,
        "cli_status": cli_payload.get("status"),
        "db_fingerprint_checked": before is not None and after is not None,
        "db_fingerprint_unchanged": db_unchanged,
        "failures": failures,
        "loop_id": payload.get("loop_id"),
        "secret_leaked": secret_leaked,
        "summary": payload.get("summary"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    if failures:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:3000])
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
