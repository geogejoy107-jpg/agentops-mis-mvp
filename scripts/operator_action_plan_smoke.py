#!/usr/bin/env python3
"""Verify the read-only operator action-plan API and CLI."""

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
            ("evaluation_case_candidates", "updated_at"),
            ("evaluation_case_runs", "created_at"),
            ("agent_plans", "updated_at"),
            ("plan_evidence_manifests", "updated_at"),
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


def validate_plan(payload: dict, label: str, failures: list[str], limit: int) -> None:
    require(payload.get("provider") == "agentops-operator", f"{label} provider mismatch: {payload}", failures)
    require(payload.get("operation") == "action_plan", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("status") in {"blocked", "attention", "ready"}, f"{label} bad status: {payload}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} must not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} must not run live work: {safety}", failures)
    require(safety.get("raw_prompt_omitted") is True, f"{label} raw prompt omission missing", failures)
    require(safety.get("raw_response_omitted") is True, f"{label} raw response omission missing", failures)
    summary = payload.get("summary") or {}
    for key in [
        "actions",
        "blocked",
        "attention",
        "ready",
        "review_items_total",
        "failed_evaluation_case_runs",
        "waiting_deliveries",
        "needs_attention_deliveries",
        "stuck_worker_tasks",
        "stuck_workflow_jobs",
        "remediation_packages",
        "remediation_ready_for_review",
        "remediation_pending_reviews",
        "remediation_promoted_deliveries",
        "evidence_gap_runs",
        "missing_plan_runs",
        "missing_plan_evidence_manifests",
        "unverified_plan_evidence_manifests",
        "remediated_evidence_gap_runs",
        "blocked_evidence_gap_runs",
        "evidence_synthesis_ready_runs",
        "evidence_synthesis_pending_runs",
        "evidence_synthesis_promoted_runs",
        "evidence_gap_closure_ready_runs",
        "closed_evidence_gap_runs",
        "waived_evidence_gap_runs",
        "task_intake_checked",
        "task_intake_ready",
        "task_intake_blocked",
        "task_intake_attention",
        "task_intake_missing_agent_plan",
        "dispatch_evidence_proofs",
        "dispatch_evidence_ready",
        "dispatch_evidence_waiting_approval",
        "dispatch_evidence_verified_manifests",
    ]:
        require(isinstance(summary.get(key), int), f"{label} summary.{key} missing: {summary}", failures)
    require(isinstance(summary.get("recommended_adapter"), str), f"{label} recommended_adapter missing: {summary}", failures)
    actions = payload.get("actions")
    require(isinstance(actions, list), f"{label} actions missing", failures)
    require(len(actions) <= limit, f"{label} ignored limit: {len(actions)} > {limit}", failures)
    require(bool(payload.get("top_commands")), f"{label} top_commands missing", failures)
    require(isinstance(payload.get("source_status"), dict), f"{label} source_status missing", failures)
    require("remediation_loop" in (payload.get("source_status") or {}), f"{label} remediation source status missing: {payload.get('source_status')}", failures)
    require("execution_evidence" in (payload.get("source_status") or {}), f"{label} execution evidence source status missing: {payload.get('source_status')}", failures)
    require("task_intake" in (payload.get("source_status") or {}), f"{label} task intake source status missing: {payload.get('source_status')}", failures)
    require("dispatch_evidence" in (payload.get("source_status") or {}), f"{label} dispatch evidence source status missing: {payload.get('source_status')}", failures)
    evidence_source = payload.get("execution_evidence") or {}
    require(evidence_source.get("operation") == "execution_evidence_gaps", f"{label} execution evidence payload missing: {evidence_source}", failures)
    evidence_summary = evidence_source.get("summary") or {}
    dispatch_source = payload.get("dispatch_evidence") or {}
    require(dispatch_source.get("operation") == "dispatch_evidence_lane", f"{label} dispatch evidence payload missing: {dispatch_source}", failures)
    require(isinstance(evidence_summary.get("gap_runs"), int), f"{label} execution evidence gap count missing: {evidence_summary}", failures)
    for key in [
        "synthesis_ready_runs",
        "synthesis_pending_runs",
        "synthesis_promoted_runs",
        "closure_ready_runs",
        "closed_gap_runs",
        "waived_gap_runs",
    ]:
        require(isinstance(evidence_summary.get(key), int), f"{label} execution evidence {key} missing: {evidence_summary}", failures)
    evidence_safety = evidence_source.get("safety") or {}
    require(evidence_safety.get("read_only") is True, f"{label} execution evidence read_only missing: {evidence_safety}", failures)
    require(evidence_safety.get("ledger_mutated") is False, f"{label} execution evidence must not mutate ledger: {evidence_safety}", failures)
    intake_source = payload.get("task_intake") or {}
    require(intake_source.get("operation") == "task_intake_checklist", f"{label} task intake payload missing: {intake_source}", failures)
    intake_summary = intake_source.get("summary") or {}
    for key in [
        "tasks_checked",
        "ready_for_intake",
        "blocked_for_intake",
        "attention_for_intake",
        "missing_agent_plan",
        "missing_knowledge_retrieval",
        "missing_base_reference",
        "risk_gate_blocked",
    ]:
        require(isinstance(intake_summary.get(key), int), f"{label} task intake {key} missing: {intake_summary}", failures)
    intake_safety = intake_source.get("safety") or {}
    require(intake_safety.get("read_only") is True, f"{label} task intake read_only missing: {intake_safety}", failures)
    require(intake_safety.get("ledger_mutated") is False, f"{label} task intake must not mutate ledger: {intake_safety}", failures)
    for item in intake_source.get("items") or []:
        require(bool(item.get("task_id")), f"{label} task intake item task_id missing: {item}", failures)
        require(item.get("severity") in {"blocked", "attention", "ready"}, f"{label} task intake severity wrong: {item}", failures)
        require(isinstance(item.get("gates"), list), f"{label} task intake gates missing: {item}", failures)
        for gate in item.get("gates") or []:
            require(bool(gate.get("id")), f"{label} task intake gate id missing: {gate}", failures)
            require(isinstance(gate.get("ok"), bool), f"{label} task intake gate ok missing: {gate}", failures)
    for action in actions or []:
        require(bool(action.get("action_id")), f"{label} action_id missing: {action}", failures)
        require(action.get("severity") in {"blocked", "attention", "ready", "info"}, f"{label} bad severity: {action}", failures)
        require(isinstance(action.get("priority"), int), f"{label} priority missing: {action}", failures)
        require(bool(action.get("title")), f"{label} title missing: {action}", failures)
        require(bool(action.get("command")), f"{label} command missing: {action}", failures)
        require(
            not str(action.get("command") or "").startswith("agentops approval approve --approval-id"),
            f"{label} action should inspect approval before approve: {action}",
            failures,
        )
        if action.get("source") == "execution_evidence_gaps":
            command = str(action.get("command") or "")
            require(
                command.startswith("agentops operator remediate-evidence-gap --run-id ")
                or command.startswith("agentops commander dispatch-package --task-id ")
                or command.startswith("agentops commander synthesize --project-id ")
                or command.startswith("agentops commander promote-synthesis --artifact-id ")
                or command.startswith("agentops operator close-evidence-gap --run-id ")
                or command.startswith("agentops approval inspect --approval-id ")
                or command.startswith("agentops workflow delivery-board")
                or command.startswith("agentops task get --task-id ")
                or command.startswith("agentops run get --run-id ")
                or command.startswith("agentops commander inbox"),
                f"{label} execution evidence action should preview remediation package: {action}",
                failures,
            )
        if action.get("source") == "task_intake_checklist":
            command = str(action.get("command") or "")
            require(
                command.startswith("agentops knowledge search ")
                or command.startswith("agentops agent-plan verify --plan-id ")
                or command.startswith("agentops agent-plan get --plan-id ")
                or command.startswith("agentops task pull --agent-id "),
                f"{label} task intake action should stay in read/plan/pull commands: {action}",
                failures,
            )
        require(bool(action.get("source")), f"{label} source missing: {action}", failures)
    for command in payload.get("top_commands") or []:
        require(
            not str(command or "").startswith("agentops approval approve --approval-id"),
            f"{label} top command should inspect approval before approve: {command}",
            failures,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify operator action plan API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--skip-cli", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    outputs: list[str] = []
    db_path = Path(args.db_path)
    before = db_fingerprint(db_path)

    status, payload = http_json(args.base_url, f"/api/operator/action-plan?limit={args.limit}")
    require(status == 200, f"API status mismatch: {status} {payload}", failures)
    validate_plan(payload, "api", failures, args.limit)
    outputs.append(json.dumps(payload, ensure_ascii=False))

    cli_payload: dict = {}
    if not args.skip_cli:
        with tempfile.TemporaryDirectory(prefix="agentops-operator-plan-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            proc = run_cli(args.base_url, ["operator", "action-plan", "--limit", str(args.limit)], env)
            outputs.extend([proc.stdout, proc.stderr])
            cli_payload = load_json(proc)
            require(proc.returncode == 0, f"CLI failed: {proc.stderr or proc.stdout}", failures)
            validate_plan(cli_payload, "cli", failures, args.limit)
            intake_proc = run_cli(args.base_url, ["operator", "intake-checklist", "--limit", str(args.limit)], env)
            outputs.extend([intake_proc.stdout, intake_proc.stderr])
            intake_payload = load_json(intake_proc)
            require(intake_proc.returncode == 0, f"intake-checklist CLI failed: {intake_proc.stderr or intake_proc.stdout}", failures)
            require(intake_payload.get("operation") == "task_intake_checklist", f"intake-checklist operation mismatch: {intake_payload}", failures)
            intake_safety = intake_payload.get("safety") or {}
            require(intake_safety.get("read_only") is True, f"intake-checklist CLI read_only missing: {intake_safety}", failures)
            require(intake_safety.get("ledger_mutated") is False, f"intake-checklist CLI mutated ledger: {intake_safety}", failures)
            gap_run_id = next(
                (item.get("run_id") for item in ((payload.get("execution_evidence") or {}).get("gaps") or []) if item.get("run_id")),
                None,
            )
            if gap_run_id:
                close_proc = run_cli(
                    args.base_url,
                    [
                        "operator",
                        "close-evidence-gap",
                        "--run-id",
                        str(gap_run_id),
                        "--decision",
                        "waived",
                        "--note",
                        "smoke preview only",
                    ],
                    env,
                )
                outputs.extend([close_proc.stdout, close_proc.stderr])
                close_payload = load_json(close_proc)
                require(close_proc.returncode == 0, f"close-gap preview CLI failed: {close_proc.stderr or close_proc.stdout}", failures)
                require(close_payload.get("operation") == "execution_evidence_gap_decision", f"close-gap preview operation mismatch: {close_payload}", failures)
                close_safety = close_payload.get("safety") or {}
                require(close_safety.get("read_only") is True, f"close-gap preview should be read-only: {close_safety}", failures)
                require(close_safety.get("ledger_mutated") is False, f"close-gap preview mutated ledger: {close_safety}", failures)

    after = db_fingerprint(db_path)
    db_unchanged = bool(before is not None and after is not None and before == after)
    if before is not None and after is not None:
        require(db_unchanged, "operator action plan changed database fingerprint", failures)
    secret_leaked = leaked_secret("\n".join(outputs))
    require(not secret_leaked, "operator action plan leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "api_status": payload.get("status"),
        "summary": payload.get("summary"),
        "top_commands": payload.get("top_commands", [])[:3],
        "cli_checked": not args.skip_cli,
        "cli_status": cli_payload.get("status"),
        "db_fingerprint_checked": before is not None and after is not None,
        "db_fingerprint_unchanged": db_unchanged,
        "secret_leaked": secret_leaked,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    if failures:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:3000])
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
