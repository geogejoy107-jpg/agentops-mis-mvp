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
