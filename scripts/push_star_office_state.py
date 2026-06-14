#!/usr/bin/env python3
"""Push a redacted AgentOps MIS state summary to local Star-Office-UI.

Default behavior is dry-run. Use --send for an actual local POST.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "agentops_mis.db"
SUPPORTED_STAR_STATES = {"idle", "planning", "researching", "writing", "coding", "executing", "syncing", "auditing", "error"}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def redact(value: str | None, limit: int = 180) -> str:
    if not value:
        return ""
    text = " ".join(str(value).replace("\n", " ").split())
    for marker in ("ntn_", "sk-", "ghp_", "gho_", "xoxb-", "Bearer "):
        text = text.replace(marker, "[redacted-prefix]")
    return text[:limit]


def connect_db(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def table_count(conn: sqlite3.Connection, table: str, where: str = "", params=()) -> int:
    try:
        sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {where}" if where else "")
        return int(conn.execute(sql, params).fetchone()[0])
    except sqlite3.Error:
        return 0


def fetch_state(conn: sqlite3.Connection) -> dict:
    latest_run = conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
    active_run = conn.execute(
        "SELECT * FROM runs WHERE status IN ('running','waiting_approval') ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    pending_approval = conn.execute(
        "SELECT * FROM approvals WHERE decision='pending' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    latest_memory = conn.execute("SELECT * FROM memories ORDER BY updated_at DESC, created_at DESC LIMIT 1").fetchone()
    latest_audit = conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 1").fetchone()
    latest_task = None
    run_for_task = active_run or latest_run
    if run_for_task:
        latest_task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (run_for_task["task_id"],)).fetchone()

    counts = {
        "agents": table_count(conn, "agents"),
        "tasks": table_count(conn, "tasks"),
        "runs": table_count(conn, "runs"),
        "pending_approvals": table_count(conn, "approvals", "decision='pending'"),
        "memory_candidates": table_count(conn, "memories", "review_status='candidate'"),
        "failed_runs": table_count(conn, "runs", "status IN ('failed','blocked')"),
        "audit_logs": table_count(conn, "audit_logs"),
    }

    return {
        "latest_run": dict(latest_run) if latest_run else None,
        "active_run": dict(active_run) if active_run else None,
        "pending_approval": dict(pending_approval) if pending_approval else None,
        "latest_memory": dict(latest_memory) if latest_memory else None,
        "latest_audit": dict(latest_audit) if latest_audit else None,
        "task": dict(latest_task) if latest_task else None,
        "counts": counts,
    }


def classify_task(task: dict | None) -> str | None:
    if not task:
        return None
    text = f"{task.get('title','')} {task.get('description','')}".lower()
    if any(word in text for word in ("research", "competitor", "market", "调查", "研究")):
        return "researching"
    if any(word in text for word in ("write", "report", "brief", "presentation", "draft", "汇报", "报告", "写")):
        return "writing"
    if any(word in text for word in ("code", "build", "implement", "deploy", "coding", "开发", "实现")):
        return "coding"
    return None


def map_state(snapshot: dict, compatible: bool = True) -> tuple[str, str, str]:
    latest_run = snapshot["latest_run"]
    active_run = snapshot["active_run"]
    pending_approval = snapshot["pending_approval"]
    latest_memory = snapshot["latest_memory"]
    latest_audit = snapshot["latest_audit"]
    task = snapshot["task"]
    counts = snapshot["counts"]

    if pending_approval or (active_run and active_run.get("approval_required")):
        approval = pending_approval or {}
        message = f"waiting approval: {redact(approval.get('reason') or 'high-risk tool call requires review')}"
        return ("waiting_approval", "executing" if compatible else "waiting_approval", message)

    if latest_run and latest_run.get("status") in ("failed", "blocked", "error", "timeout"):
        message = f"error: {redact(latest_run.get('error_type') or latest_run.get('error_message') or latest_run.get('run_id'))}"
        return ("error", "error", message)

    if active_run:
        task_state = classify_task(task)
        if task_state:
            message = f"{task_state}: {redact((task or {}).get('title'))}"
            return (task_state, task_state if task_state in SUPPORTED_STAR_STATES else "executing", message)
        message = f"executing run {active_run.get('run_id')} by {active_run.get('agent_id')}"
        return ("executing", "executing", message)

    if latest_memory and counts["memory_candidates"] > 0:
        message = f"syncing memory review: {counts['memory_candidates']} candidates"
        return ("syncing", "syncing", message)

    if latest_audit:
        message = f"audit event recorded: {redact(latest_audit.get('action'))}"
        return ("auditing", "syncing" if compatible else "auditing", message)

    return ("idle", "idle", "no active AgentOps MIS run")


def build_payload(snapshot: dict, endpoint: str, compatible: bool = True) -> dict:
    mis_state, star_state, message = map_state(snapshot, compatible=compatible)
    latest_run = snapshot["active_run"] or snapshot["latest_run"] or {}
    task = snapshot["task"] or {}
    counts = snapshot["counts"]
    summary = redact(latest_run.get("output_summary") or latest_run.get("input_summary") or message, 220)
    base = {
        "source": "agentops-mis",
        "agent_id": latest_run.get("agent_id") or "agentops_mis",
        "agent_name": "AgentOps MIS",
        "state": star_state,
        "mis_state": mis_state,
        "message": message,
        "run_id": latest_run.get("run_id"),
        "task_id": latest_run.get("task_id"),
        "task_title": redact(task.get("title"), 140),
        "summary": summary,
        "counts": counts,
        "privacy": {
            "redacted": True,
            "full_prompt_included": False,
            "full_transcript_included": False,
            "credentials_included": False,
        },
        "created_at": now_iso(),
    }
    if endpoint == "set_state":
        return {
            "state": base["state"],
            "message": base["message"],
            "source": base["source"],
            "agent_id": base["agent_id"],
            "mis_state": base["mis_state"],
            "details": base,
        }
    return base


def post_payload(base_url: str, endpoint: str, payload: dict, timeout: int = 5) -> dict:
    url = base_url.rstrip("/") + ("/set_state" if endpoint == "set_state" else "/agent-push")
    req = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {"raw": raw[:500]}
            return {"sent": True, "url": url, "status": res.status, "response": body}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {"sent": False, "url": url, "status": exc.code, "error": raw[:500]}
    except URLError as exc:
        return {"sent": False, "url": url, "error": redact(str(exc), 300)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run or push AgentOps MIS state to local Star-Office-UI.")
    parser.add_argument("--db", default=str(DB_PATH), help="Path to AgentOps MIS SQLite database.")
    parser.add_argument("--base-url", default="http://127.0.0.1:19000", help="Star-Office-UI base URL.")
    parser.add_argument("--endpoint", choices=["agent-push", "set_state"], default="agent-push")
    parser.add_argument("--send", action="store_true", help="Actually POST to Star-Office-UI. Default is dry-run.")
    parser.add_argument("--strict-mis-state", action="store_true", help="Do not downgrade MIS-specific states for Star-Office compatibility.")
    args = parser.parse_args()

    with connect_db(Path(args.db).expanduser()) as conn:
        snapshot = fetch_state(conn)
    payload = build_payload(snapshot, args.endpoint, compatible=not args.strict_mis_state)

    result = {
        "dry_run": not args.send,
        "target": args.base_url.rstrip("/") + ("/set_state" if args.endpoint == "set_state" else "/agent-push"),
        "payload": payload,
    }
    if args.send:
        result["send_result"] = post_payload(args.base_url, args.endpoint, payload)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (not args.send or result.get("send_result", {}).get("sent")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
