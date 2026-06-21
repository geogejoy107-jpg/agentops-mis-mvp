#!/usr/bin/env python3
"""Smoke-test evaluation case candidate lifecycle."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
DEFAULT_DB = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
BASE_URL = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        BASE_URL.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach MIS server: {exc.reason}") from exc


def run_cli(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env["AGENTOPS_BASE_URL"] = BASE_URL
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
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


def db_counts(conn: sqlite3.Connection, case_id: str) -> dict:
    return {
        "cases": int(conn.execute("SELECT COUNT(*) FROM evaluation_case_candidates WHERE case_id=?", (case_id,)).fetchone()[0] or 0),
        "candidate": int(conn.execute("SELECT COUNT(*) FROM evaluation_case_candidates WHERE case_id=? AND review_status='candidate'", (case_id,)).fetchone()[0] or 0),
        "approved": int(conn.execute("SELECT COUNT(*) FROM evaluation_case_candidates WHERE case_id=? AND review_status='approved'", (case_id,)).fetchone()[0] or 0),
        "case_runs": int(conn.execute("SELECT COUNT(*) FROM evaluation_case_runs WHERE case_id=?", (case_id,)).fetchone()[0] or 0),
        "case_run_evaluations": int(conn.execute("""SELECT COUNT(*)
            FROM evaluation_case_runs ecr
            JOIN evaluations e ON e.evaluation_id=ecr.evaluation_id
            WHERE ecr.case_id=?""", (case_id,)).fetchone()[0] or 0),
        "case_run_artifacts": int(conn.execute("""SELECT COUNT(*)
            FROM evaluation_case_runs ecr
            JOIN artifacts a ON a.artifact_id=ecr.artifact_id
            WHERE ecr.case_id=?""", (case_id,)).fetchone()[0] or 0),
        "audit_logs": int(conn.execute("SELECT COUNT(*) FROM audit_logs WHERE entity_type='evaluation_case_candidates' AND entity_id=?", (case_id,)).fetchone()[0] or 0),
        "case_run_audit_logs": int(conn.execute("SELECT COUNT(*) FROM audit_logs WHERE entity_type='evaluation_case_runs' AND metadata_json LIKE ?", (f"%{case_id}%",)).fetchone()[0] or 0),
        "runtime_events": int(conn.execute("SELECT COUNT(*) FROM runtime_events WHERE event_type LIKE 'evaluation_case_candidate.%' OR event_type LIKE 'evaluation_case_run.%'").fetchone()[0] or 0),
    }


def remediation_task_counts(conn: sqlite3.Connection, task_id: str) -> dict:
    return {
        "tasks": int(conn.execute("SELECT COUNT(*) FROM tasks WHERE task_id=?", (task_id,)).fetchone()[0] or 0),
        "runs": int(conn.execute("SELECT COUNT(*) FROM runs WHERE task_id=?", (task_id,)).fetchone()[0] or 0),
        "tool_calls": int(conn.execute("SELECT COUNT(*) FROM tool_calls WHERE run_id IN (SELECT run_id FROM runs WHERE task_id=?)", (task_id,)).fetchone()[0] or 0),
        "evaluations": int(conn.execute("SELECT COUNT(*) FROM evaluations WHERE task_id=?", (task_id,)).fetchone()[0] or 0),
        "artifacts": int(conn.execute("SELECT COUNT(*) FROM artifacts WHERE task_id=?", (task_id,)).fetchone()[0] or 0),
        "task_audit_logs": int(conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE entity_type='tasks' AND entity_id=?",
            (task_id,),
        ).fetchone()[0] or 0),
        "remediation_audit_logs": int(conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE entity_type='tasks' AND entity_id=? AND action='evaluation_case_run.remediation_task_create'",
            (task_id,),
        ).fetchone()[0] or 0),
        "remediation_runtime_events": int(conn.execute(
            "SELECT COUNT(*) FROM runtime_events WHERE task_id=? AND event_type='evaluation_case_run.remediation_task'",
            (task_id,),
        ).fetchone()[0] or 0),
    }


def synthesis_artifact_counts(conn: sqlite3.Connection, artifact_id: str) -> dict:
    return {
        "artifacts": int(conn.execute("SELECT COUNT(*) FROM artifacts WHERE artifact_id=?", (artifact_id,)).fetchone()[0] or 0),
        "approvals": int(conn.execute("SELECT COUNT(*) FROM approvals WHERE approval_id LIKE 'ap_cmd_synthesis_%' AND reason LIKE ?", (f"%{artifact_id}%",)).fetchone()[0] or 0),
        "runtime_events": int(conn.execute("SELECT COUNT(*) FROM runtime_events WHERE event_type LIKE 'commander.work_package_synthesis%' AND raw_payload_hash IS NOT NULL").fetchone()[0] or 0),
        "audit_logs": int(conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action LIKE 'commander.work_package_synthesis%' AND metadata_json LIKE ?", (f"%{artifact_id}%",)).fetchone()[0] or 0),
    }


def source_run(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """SELECT r.run_id, r.task_id, r.agent_id, e.evaluation_id
        FROM runs r
        LEFT JOIN tasks t ON t.task_id=r.task_id
        LEFT JOIN evaluations e ON e.run_id=r.run_id
        WHERE r.status IN ('completed','failed','blocked')
          AND COALESCE(r.workspace_id, t.workspace_id, 'local-demo')='local-demo'
        ORDER BY r.created_at DESC
        LIMIT 1"""
    ).fetchone()
    require(row is not None, "no local-demo source run available")
    return dict(row)


def main() -> int:
    failures: list[str] = []
    transcripts: list[str] = []
    case_id = f"evalcase_smoke_{stamp()}"
    fail_case_id = f"evalcase_fail_smoke_{stamp()}"
    source: dict = {}
    try:
        require(DEFAULT_DB.exists(), f"database not found: {DEFAULT_DB}")
        conn = sqlite3.connect(DEFAULT_DB)
        conn.row_factory = sqlite3.Row
        try:
            source = source_run(conn)
            before = db_counts(conn, case_id)
        finally:
            conn.close()

        preview = run_cli([
            "eval",
            "propose-case",
            "--case-id",
            case_id,
            "--run-id",
            source["run_id"],
            "--case-type",
            "regression",
            "--title",
            "Smoke regression candidate from latest run",
        ])
        transcripts.extend([preview.stdout, preview.stderr])
        preview_payload = load_json(preview)
        require(preview.returncode == 0, f"preview failed: {preview.stderr or preview.stdout}")
        require(preview_payload.get("status") == "preview", f"preview status wrong: {preview_payload}")
        require(preview_payload.get("safety", {}).get("ledger_mutated") is False, f"preview mutated ledger: {preview_payload}")
        conn = sqlite3.connect(DEFAULT_DB)
        try:
            require(db_counts(conn, case_id) == before, "preview changed database")
        finally:
            conn.close()

        created = run_cli([
            "eval",
            "propose-case",
            "--case-id",
            case_id,
            "--run-id",
            source["run_id"],
            "--case-type",
            "regression",
            "--title",
            "Smoke regression candidate from latest run",
            "--confirm-create",
        ])
        transcripts.extend([created.stdout, created.stderr])
        created_payload = load_json(created)
        require(created.returncode == 0, f"create failed: {created.stderr or created.stdout}")
        require(created_payload.get("status") == "candidate", f"create status wrong: {created_payload}")
        require(created_payload.get("case", {}).get("case_id") == case_id, f"case id mismatch: {created_payload}")

        listed = run_cli(["eval", "cases", "--status", "candidate", "--limit", "20"])
        transcripts.extend([listed.stdout, listed.stderr])
        listed_payload = load_json(listed)
        require(listed.returncode == 0, f"list failed: {listed.stderr or listed.stdout}")
        require(any(item.get("case_id") == case_id for item in listed_payload.get("cases", [])), f"case missing from list: {listed_payload}")
        require(listed_payload.get("safety", {}).get("read_only") is True, f"list not read-only: {listed_payload}")

        approved = run_cli(["eval", "approve-case", "--case-id", case_id])
        transcripts.extend([approved.stdout, approved.stderr])
        approved_payload = load_json(approved)
        require(approved.returncode == 0, f"approve failed: {approved.stderr or approved.stdout}")
        require(approved_payload.get("review_status") == "approved", f"approve status wrong: {approved_payload}")

        run_preview = run_cli(["eval", "run-cases", "--case-id", case_id])
        transcripts.extend([run_preview.stdout, run_preview.stderr])
        run_preview_payload = load_json(run_preview)
        require(run_preview.returncode == 0, f"run preview failed: {run_preview.stderr or run_preview.stdout}")
        require(run_preview_payload.get("status") == "preview", f"run preview status wrong: {run_preview_payload}")
        require(run_preview_payload.get("safety", {}).get("ledger_mutated") is False, f"run preview mutated ledger: {run_preview_payload}")
        conn = sqlite3.connect(DEFAULT_DB)
        try:
            require(db_counts(conn, case_id)["case_runs"] == 0, "run preview created case run")
        finally:
            conn.close()

        run_created = run_cli(["eval", "run-cases", "--case-id", case_id, "--confirm-run"])
        transcripts.extend([run_created.stdout, run_created.stderr])
        run_created_payload = load_json(run_created)
        require(run_created.returncode == 0, f"run cases failed: {run_created.stderr or run_created.stdout}")
        require(run_created_payload.get("status") == "completed", f"run cases status wrong: {run_created_payload}")
        require(run_created_payload.get("summary", {}).get("created") == 1, f"case run missing: {run_created_payload}")
        require(run_created_payload.get("safety", {}).get("live_execution_performed") is False, f"case run performed live execution: {run_created_payload}")
        case_run_list = run_cli(["eval", "case-runs", "--case-id", case_id, "--limit", "5"])
        transcripts.extend([case_run_list.stdout, case_run_list.stderr])
        case_run_list_payload = load_json(case_run_list)
        require(case_run_list.returncode == 0, f"case run list failed: {case_run_list.stderr or case_run_list.stdout}")
        require(case_run_list_payload.get("operation") == "evaluation_case_runs", f"case run list operation wrong: {case_run_list_payload}")
        require(case_run_list_payload.get("safety", {}).get("read_only") is True, f"case run list not read-only: {case_run_list_payload}")
        require(any(item.get("case_id") == case_id for item in case_run_list_payload.get("case_runs", [])), f"case run missing from list: {case_run_list_payload}")

        fail_case = run_cli([
            "eval",
            "propose-case",
            "--case-id",
            fail_case_id,
            "--task-id",
            source["task_id"],
            "--case-type",
            "regression",
            "--title",
            "Smoke failed benchmark case without failure mode",
            "--expected-output-summary",
            "This case intentionally lacks a failure_mode so strict benchmark readiness fails.",
            "--confirm-create",
        ])
        transcripts.extend([fail_case.stdout, fail_case.stderr])
        fail_case_payload = load_json(fail_case)
        require(fail_case.returncode == 0, f"fail case create failed: {fail_case.stderr or fail_case.stdout}")
        require(fail_case_payload.get("status") == "candidate", f"fail case status wrong: {fail_case_payload}")
        fail_approved = run_cli(["eval", "approve-case", "--case-id", fail_case_id])
        transcripts.extend([fail_approved.stdout, fail_approved.stderr])
        fail_approved_payload = load_json(fail_approved)
        require(fail_approved.returncode == 0, f"fail case approve failed: {fail_approved.stderr or fail_approved.stdout}")
        require(fail_approved_payload.get("review_status") == "approved", f"fail case approve status wrong: {fail_approved_payload}")
        fail_run = run_cli(["eval", "run-cases", "--case-id", fail_case_id, "--min-score", "0.95", "--confirm-run"])
        transcripts.extend([fail_run.stdout, fail_run.stderr])
        fail_run_payload = load_json(fail_run)
        require(fail_run.returncode == 0, f"fail case run failed: {fail_run.stderr or fail_run.stdout}")
        require(fail_run_payload.get("summary", {}).get("failed", 0) >= 1, f"strict benchmark did not fail: {fail_run_payload}")
        fail_case_run_id = (fail_run_payload.get("case_runs") or [{}])[0].get("case_run_id")
        require(bool(fail_case_run_id), f"missing failed case_run_id: {fail_run_payload}")
        queue_status, queue_payload = http_json("GET", "/api/review/queue?limit=20")
        transcripts.append(json.dumps(queue_payload, ensure_ascii=False))
        require(queue_status == 200, f"review queue failed: {queue_status} {queue_payload}")
        require((queue_payload.get("summary") or {}).get("failed_evaluation_case_runs", 0) >= 1, f"failed benchmark summary missing: {queue_payload}")
        failed_queue_items = [
            item for item in queue_payload.get("review_items", [])
            if item.get("item_type") == "evaluation_case_run" and item.get("case_id") == fail_case_id
        ]
        require(failed_queue_items, f"failed benchmark item missing from review queue: {queue_payload}")
        require(
            "eval remediate-case-run" in (failed_queue_items[0].get("cli_action") or ""),
            f"failed benchmark item did not point at remediation preview: {failed_queue_items[0]}",
        )
        remediation_preview = run_cli([
            "eval",
            "remediate-case-run",
            "--case-run-id",
            fail_case_run_id,
        ])
        transcripts.extend([remediation_preview.stdout, remediation_preview.stderr])
        remediation_preview_payload = load_json(remediation_preview)
        require(remediation_preview.returncode == 0, f"remediation preview failed: {remediation_preview.stderr or remediation_preview.stdout}")
        require(remediation_preview_payload.get("status") == "preview", f"remediation preview status wrong: {remediation_preview_payload}")
        require(remediation_preview_payload.get("safety", {}).get("ledger_mutated") is False, f"remediation preview mutated ledger: {remediation_preview_payload}")
        remediation_task_id = remediation_preview_payload.get("task", {}).get("task_id")
        require(bool(remediation_task_id), f"remediation preview missing task id: {remediation_preview_payload}")
        conn = sqlite3.connect(DEFAULT_DB)
        try:
            require(remediation_task_counts(conn, remediation_task_id)["tasks"] == 0, "remediation preview created a task")
        finally:
            conn.close()

        remediation_created = run_cli([
            "eval",
            "remediate-case-run",
            "--case-run-id",
            fail_case_run_id,
            "--confirm-create",
        ])
        transcripts.extend([remediation_created.stdout, remediation_created.stderr])
        remediation_created_payload = load_json(remediation_created)
        require(remediation_created.returncode == 0, f"remediation create failed: {remediation_created.stderr or remediation_created.stdout}")
        require(remediation_created_payload.get("status") == "created", f"remediation create status wrong: {remediation_created_payload}")
        require(remediation_created_payload.get("created") is True, f"remediation create flag wrong: {remediation_created_payload}")
        require(remediation_created_payload.get("task_id") == remediation_task_id, f"remediation task id changed: {remediation_created_payload}")
        require(remediation_created_payload.get("commander_work_package") is True, f"remediation did not create commander work package: {remediation_created_payload}")
        require(remediation_created_payload.get("safety", {}).get("ledger_mutated") is True, f"remediation create did not report ledger mutation: {remediation_created_payload}")
        remediation_project_id = remediation_created_payload.get("project_id")
        require(bool(remediation_project_id), f"remediation missing project id: {remediation_created_payload}")
        conn = sqlite3.connect(DEFAULT_DB)
        try:
            remediation_counts = remediation_task_counts(conn, remediation_task_id)
            require(remediation_counts["tasks"] == 1, f"remediation task missing: {remediation_counts}")
            require(remediation_counts["task_audit_logs"] >= 2, f"remediation task audit missing: {remediation_counts}")
            require(remediation_counts["remediation_audit_logs"] >= 1, f"remediation audit missing: {remediation_counts}")
            require(remediation_counts["remediation_runtime_events"] >= 1, f"remediation runtime event missing: {remediation_counts}")
        finally:
            conn.close()

        commander_readback = run_cli([
            "commander",
            "packages",
            "--project-id",
            remediation_project_id,
            "--limit",
            "5",
        ])
        transcripts.extend([commander_readback.stdout, commander_readback.stderr])
        commander_readback_payload = load_json(commander_readback)
        require(commander_readback.returncode == 0, f"commander readback failed: {commander_readback.stderr or commander_readback.stdout}")
        require(commander_readback_payload.get("operation") == "work_packages_readback", f"commander readback operation wrong: {commander_readback_payload}")
        commander_packages = commander_readback_payload.get("work_packages") or []
        require(any(item.get("task_id") == remediation_task_id for item in commander_packages), f"remediation task missing from commander packages: {commander_readback_payload}")
        remediation_package = next(item for item in commander_packages if item.get("task_id") == remediation_task_id)
        require(remediation_package.get("package_status") == "planned", f"remediation package status wrong: {remediation_package}")
        require("commander dispatch-package" in (remediation_package.get("recommended_action") or ""), f"remediation package next action wrong: {remediation_package}")
        require(commander_readback_payload.get("safety", {}).get("ledger_mutated") is False, f"commander readback mutated ledger: {commander_readback_payload}")

        dispatch = run_cli([
            "commander",
            "dispatch-package",
            "--task-id",
            remediation_task_id,
            "--adapter",
            "mock",
        ], timeout=220)
        transcripts.extend([dispatch.stdout, dispatch.stderr])
        dispatch_payload = load_json(dispatch)
        require(dispatch.returncode == 0, f"remediation dispatch failed: {dispatch.stderr or dispatch.stdout}")
        require(dispatch_payload.get("operation") == "work_package_dispatch", f"remediation dispatch operation wrong: {dispatch_payload}")
        require(dispatch_payload.get("ok") is True, f"remediation dispatch not ok: {dispatch_payload}")
        require(dispatch_payload.get("run_id"), f"remediation dispatch missing run id: {dispatch_payload}")
        require(dispatch_payload.get("safety", {}).get("run_created") is True, f"remediation dispatch did not create run: {dispatch_payload}")
        require(dispatch_payload.get("live_execution_performed") is False, f"remediation dispatch marked live execution: {dispatch_payload}")
        conn = sqlite3.connect(DEFAULT_DB)
        try:
            remediation_after_dispatch = remediation_task_counts(conn, remediation_task_id)
            require(remediation_after_dispatch["runs"] >= 1, f"remediation dispatch missing run evidence: {remediation_after_dispatch}")
            require(remediation_after_dispatch["tool_calls"] >= 1, f"remediation dispatch missing tool evidence: {remediation_after_dispatch}")
            require(remediation_after_dispatch["evaluations"] >= 1, f"remediation dispatch missing evaluation evidence: {remediation_after_dispatch}")
            require(remediation_after_dispatch["artifacts"] >= 1, f"remediation dispatch missing artifact evidence: {remediation_after_dispatch}")
        finally:
            conn.close()

        commander_ready = run_cli([
            "commander",
            "packages",
            "--project-id",
            remediation_project_id,
            "--status",
            "ready_for_review",
            "--limit",
            "5",
        ])
        transcripts.extend([commander_ready.stdout, commander_ready.stderr])
        commander_ready_payload = load_json(commander_ready)
        require(commander_ready.returncode == 0, f"commander ready readback failed: {commander_ready.stderr or commander_ready.stdout}")
        ready_packages = commander_ready_payload.get("work_packages") or []
        require(any(item.get("task_id") == remediation_task_id for item in ready_packages), f"remediation package not ready after dispatch: {commander_ready_payload}")

        synthesis_preview = run_cli([
            "commander",
            "synthesize",
            "--project-id",
            remediation_project_id,
            "--status",
            "ready_for_review",
            "--limit",
            "5",
        ])
        transcripts.extend([synthesis_preview.stdout, synthesis_preview.stderr])
        synthesis_preview_payload = load_json(synthesis_preview)
        require(synthesis_preview.returncode == 0, f"synthesis preview failed: {synthesis_preview.stderr or synthesis_preview.stdout}")
        require(synthesis_preview_payload.get("status") == "preview", f"synthesis preview status wrong: {synthesis_preview_payload}")
        require(synthesis_preview_payload.get("package_count") == 1, f"synthesis preview package count wrong: {synthesis_preview_payload}")
        require(synthesis_preview_payload.get("safety", {}).get("ledger_mutated") is False, f"synthesis preview mutated ledger: {synthesis_preview_payload}")

        synthesis_created = run_cli([
            "commander",
            "synthesize",
            "--project-id",
            remediation_project_id,
            "--status",
            "ready_for_review",
            "--limit",
            "5",
            "--confirm-create",
        ])
        transcripts.extend([synthesis_created.stdout, synthesis_created.stderr])
        synthesis_created_payload = load_json(synthesis_created)
        require(synthesis_created.returncode == 0, f"synthesis create failed: {synthesis_created.stderr or synthesis_created.stdout}")
        require(synthesis_created_payload.get("status") == "created", f"synthesis create status wrong: {synthesis_created_payload}")
        synthesis_artifact_id = synthesis_created_payload.get("artifact_id") or ""
        require(synthesis_artifact_id.startswith("art_cmd_synthesis_"), f"synthesis artifact id wrong: {synthesis_created_payload}")
        require((synthesis_created_payload.get("approval_id") or "").startswith("ap_cmd_synthesis_"), f"synthesis approval id wrong: {synthesis_created_payload}")
        require(synthesis_created_payload.get("safety", {}).get("artifact_created") is True, f"synthesis artifact safety wrong: {synthesis_created_payload}")
        require(synthesis_created_payload.get("live_execution_performed") is False, f"synthesis marked live execution: {synthesis_created_payload}")
        conn = sqlite3.connect(DEFAULT_DB)
        try:
            synthesis_counts = synthesis_artifact_counts(conn, synthesis_artifact_id)
            require(synthesis_counts["artifacts"] == 1, f"synthesis artifact missing: {synthesis_counts}")
            require(synthesis_counts["approvals"] == 1, f"synthesis approval missing: {synthesis_counts}")
            require(synthesis_counts["runtime_events"] >= 1, f"synthesis runtime event missing: {synthesis_counts}")
            require(synthesis_counts["audit_logs"] >= 1, f"synthesis audit missing: {synthesis_counts}")
        finally:
            conn.close()

        acknowledged = run_cli([
            "eval",
            "review-case-run",
            "--case-run-id",
            fail_case_run_id,
            "--status",
            "acknowledged",
            "--note",
            "Smoke intentionally failed this benchmark and acknowledged the risk.",
        ])
        transcripts.extend([acknowledged.stdout, acknowledged.stderr])
        acknowledged_payload = load_json(acknowledged)
        require(acknowledged.returncode == 0, f"case run acknowledge failed: {acknowledged.stderr or acknowledged.stdout}")
        require(acknowledged_payload.get("case_run", {}).get("review_status") == "acknowledged", f"case run acknowledge status wrong: {acknowledged_payload}")
        acknowledged_list = run_cli(["eval", "case-runs", "--case-id", fail_case_id, "--review-status", "acknowledged", "--limit", "5"])
        transcripts.extend([acknowledged_list.stdout, acknowledged_list.stderr])
        acknowledged_list_payload = load_json(acknowledged_list)
        require(any(item.get("case_run_id") == fail_case_run_id for item in acknowledged_list_payload.get("case_runs", [])), f"acknowledged case run missing from list: {acknowledged_list_payload}")
        queue_after_status, queue_after_payload = http_json("GET", "/api/review/queue?limit=40")
        transcripts.append(json.dumps(queue_after_payload, ensure_ascii=False))
        require(queue_after_status == 200, f"review queue after acknowledge failed: {queue_after_status} {queue_after_payload}")
        require(not any(item.get("item_type") == "evaluation_case_run" and item.get("case_run_id") == fail_case_run_id for item in queue_after_payload.get("review_items", [])), f"acknowledged benchmark still in review queue: {queue_after_payload}")

        conn = sqlite3.connect(DEFAULT_DB)
        try:
            counts = db_counts(conn, case_id)
            require(counts["cases"] == 1, f"case row missing: {counts}")
            require(counts["approved"] == 1, f"case not approved: {counts}")
            require(counts["case_runs"] == 1, f"case run missing: {counts}")
            require(counts["case_run_evaluations"] == 1, f"case run evaluation missing: {counts}")
            require(counts["case_run_artifacts"] == 1, f"case run artifact missing: {counts}")
            require(counts["audit_logs"] >= 2, f"audit missing: {counts}")
            require(counts["case_run_audit_logs"] >= 1, f"case run audit missing: {counts}")
            require(counts["runtime_events"] >= 3, f"runtime events missing: {counts}")
        finally:
            conn.close()

        require(not leaked_secret("\n".join(transcripts)), "output leaked token-like material")
    except Exception as exc:
        failures.append(str(exc))

    result = {
        "ok": not failures,
        "case_id": case_id,
        "source": source,
        "secret_leaked": leaked_secret("\n".join(transcripts)),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
