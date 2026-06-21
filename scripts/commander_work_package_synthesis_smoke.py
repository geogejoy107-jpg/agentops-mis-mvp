#!/usr/bin/env python3
"""Smoke-test Commander synthesis artifact creation after work-package dispatch."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import time
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


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = 120) -> tuple[int, dict]:
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


def run_cli(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
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


def count_rows(conn: sqlite3.Connection, sql: str, params=()) -> int:
    return int((conn.execute(sql, params).fetchone() or [0])[0] or 0)


def artifact_evidence(db_path: Path, artifact_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        return {
            "artifacts": count_rows(conn, "SELECT COUNT(*) FROM artifacts WHERE artifact_id=?", (artifact_id,)),
            "runtime_events": count_rows(conn, "SELECT COUNT(*) FROM runtime_events WHERE event_type='commander.work_package_synthesis' AND raw_payload_hash IS NOT NULL"),
            "audit_logs": count_rows(conn, "SELECT COUNT(*) FROM audit_logs WHERE entity_type='artifacts' AND entity_id=?", (artifact_id,)),
            "review_approvals": count_rows(conn, "SELECT COUNT(*) FROM approvals WHERE reason LIKE ?", (f"%artifact_id={artifact_id}%",)),
        }
    finally:
        conn.close()


def promotion_evidence(db_path: Path, artifact_id: str, delivery_artifact_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        return {
            "memory_candidates": count_rows(conn, "SELECT COUNT(*) FROM memories WHERE source_ref=? AND review_status='candidate'", (artifact_id,)),
            "delivery_artifacts": count_rows(conn, "SELECT COUNT(*) FROM artifacts WHERE artifact_id=? AND artifact_type='customer_delivery_report'", (delivery_artifact_id,)),
            "promotion_audits": count_rows(conn, "SELECT COUNT(*) FROM audit_logs WHERE action LIKE 'commander.work_package_synthesis_promote_%'"),
            "promotion_events": count_rows(conn, "SELECT COUNT(*) FROM runtime_events WHERE event_type LIKE 'commander.work_package_synthesis.promote_%'"),
        }
    finally:
        conn.close()


def task_statuses(db_path: Path, task_ids: list[str]) -> dict[str, str]:
    if not task_ids:
        return {}
    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" for _ in task_ids)
        rows = conn.execute(f"SELECT task_id,status FROM tasks WHERE task_id IN ({placeholders})", task_ids).fetchall()
        return {row[0]: row[1] for row in rows}
    finally:
        conn.close()


def wait_job(job_id: str, timeout_sec: int = 45) -> dict:
    deadline = time.time() + timeout_sec
    last = {}
    while time.time() < deadline:
        status, payload = http_json("GET", f"/api/workflows/jobs/{job_id}")
        require(status == 200, f"job read failed {job_id}: {status} {payload}")
        last = payload.get("job") or {}
        if last.get("status") in {"completed", "failed"}:
            return last
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} did not finish: {last}")


def main() -> int:
    suffix = stamp()
    project_id = f"proj_commander_synthesis_smoke_{suffix}"
    plan_id = f"cmdplan_synthesis_smoke_{suffix}"
    goal = "Use AgentOps MIS commander to merge returned work packages into a synthesis report."
    transcripts: list[str] = []
    failures: list[str] = []
    task_ids: list[str] = []
    artifact_id = ""
    approval_id = ""
    delivery_artifact_id = ""
    try:
        status, created = http_json("POST", "/api/commander/work-packages/plan", {
            "project_id": project_id,
            "plan_id": plan_id,
            "goal": goal,
            "max_packages": 2,
            "confirm_create": True,
        })
        transcripts.append(json.dumps(created, ensure_ascii=False))
        require(status == 201, f"create failed: {status} {created}")
        task_ids = created.get("created_task_ids") or []
        require(len(task_ids) == 2, f"expected 2 task ids: {created}")

        batch = run_cli([
            "commander",
            "dispatch-batch",
            "--task-id",
            task_ids[0],
            "--task-id",
            task_ids[1],
            "--adapter",
            "mock",
            "--limit",
            "2",
        ])
        transcripts.extend([batch.stdout, batch.stderr])
        batch_payload = load_json(batch)
        require(batch.returncode == 0, f"batch failed: {batch.stderr or batch.stdout}")
        job_ids = batch_payload.get("job_ids") or []
        require(len(job_ids) == 2, f"expected 2 jobs: {batch_payload}")
        jobs = [wait_job(job_id) for job_id in job_ids]
        require(all(job.get("status") == "completed" for job in jobs), f"jobs not completed: {jobs}")

        preview = run_cli([
            "commander",
            "synthesize",
            "--project-id",
            project_id,
            "--status",
            "ready_for_review",
            "--limit",
            "5",
        ])
        transcripts.extend([preview.stdout, preview.stderr])
        preview_payload = load_json(preview)
        require(preview.returncode == 0, f"preview failed: {preview.stderr or preview.stdout}")
        require(preview_payload.get("status") == "preview", f"preview status wrong: {preview_payload}")
        require(preview_payload.get("safety", {}).get("ledger_mutated") is False, f"preview mutated ledger: {preview_payload}")
        require(preview_payload.get("artifact_id") is None, f"preview created artifact: {preview_payload}")
        require(preview_payload.get("package_count") == 2, f"preview package count wrong: {preview_payload}")
        require("Commander Work Package Synthesis" in (preview_payload.get("markdown") or ""), "preview markdown missing title")

        created_report = run_cli([
            "commander",
            "synthesize",
            "--project-id",
            project_id,
            "--status",
            "ready_for_review",
            "--limit",
            "5",
            "--confirm-create",
        ])
        transcripts.extend([created_report.stdout, created_report.stderr])
        report_payload = load_json(created_report)
        require(created_report.returncode == 0, f"create synthesis failed: {created_report.stderr or created_report.stdout}")
        require(report_payload.get("status") == "created", f"synthesis not created: {report_payload}")
        require(report_payload.get("safety", {}).get("artifact_created") is True, f"artifact safety missing: {report_payload}")
        require(report_payload.get("live_execution_performed") is False, "synthesis marked live execution")
        artifact_id = report_payload.get("artifact_id") or ""
        require(artifact_id.startswith("art_cmd_synthesis_"), f"unexpected artifact id: {artifact_id}")
        approval_id = report_payload.get("approval_id") or ""
        require(approval_id.startswith("ap_cmd_synthesis_"), f"unexpected approval id: {report_payload}")
        require((report_payload.get("review_approval") or {}).get("decision") == "pending", f"review approval not pending: {report_payload}")
        require(report_payload.get("content_hash"), f"missing content hash: {report_payload}")

        if DEFAULT_DB.exists():
            counts = artifact_evidence(DEFAULT_DB, artifact_id)
            require(counts["artifacts"] == 1, f"synthesis artifact missing: {counts}")
            require(counts["runtime_events"] >= 1, f"synthesis runtime event missing: {counts}")
            require(counts["audit_logs"] >= 1, f"synthesis audit missing: {counts}")
            require(counts["review_approvals"] == 1, f"synthesis approval missing: {counts}")

        queue_status, queue = http_json("GET", "/api/review/queue?limit=20")
        transcripts.append(json.dumps(queue, ensure_ascii=False))
        require(queue_status == 200, f"review queue failed: {queue_status} {queue}")
        review_items = queue.get("review_items") or []
        synthesis_items = [item for item in review_items if item.get("item_id") == approval_id and item.get("kind") == "commander_synthesis"]
        require(synthesis_items, f"synthesis approval missing from review queue: {queue}")
        require(synthesis_items[0].get("artifact_id") == artifact_id, f"review item missing artifact id: {synthesis_items[0]}")

        blocked_status, blocked = http_json("POST", "/api/commander/work-packages/synthesis/promote", {
            "artifact_id": artifact_id,
            "approval_id": approval_id,
            "mode": "both",
            "confirm_promote": True,
        })
        transcripts.append(json.dumps(blocked, ensure_ascii=False))
        require(blocked_status == 409, f"unapproved promotion should fail closed: {blocked_status} {blocked}")
        require(blocked.get("status") == "approval_required", f"wrong blocked promotion status: {blocked}")

        approve_status, approved = http_json("POST", f"/api/approvals/{approval_id}/approve", {})
        transcripts.append(json.dumps(approved, ensure_ascii=False))
        require(approve_status == 200, f"synthesis approval decision failed: {approve_status} {approved}")
        require(approved.get("decision") == "approved", f"synthesis approval not approved: {approved}")
        if DEFAULT_DB.exists():
            statuses = task_statuses(DEFAULT_DB, task_ids)
            require(all(status == "completed" for status in statuses.values()), f"synthesis approval mutated task statuses: {statuses}")

        promote_preview = run_cli([
            "commander",
            "promote-synthesis",
            "--artifact-id",
            artifact_id,
            "--approval-id",
            approval_id,
            "--mode",
            "both",
        ])
        transcripts.extend([promote_preview.stdout, promote_preview.stderr])
        preview_payload = load_json(promote_preview)
        require(promote_preview.returncode == 0, f"promote preview failed: {promote_preview.stderr or promote_preview.stdout}")
        require(preview_payload.get("status") == "preview", f"promote preview status wrong: {preview_payload}")
        require(preview_payload.get("safety", {}).get("ledger_mutated") is False, f"promote preview mutated ledger: {preview_payload}")

        promote = run_cli([
            "commander",
            "promote-synthesis",
            "--artifact-id",
            artifact_id,
            "--approval-id",
            approval_id,
            "--mode",
            "both",
            "--confirm-promote",
        ])
        transcripts.extend([promote.stdout, promote.stderr])
        promote_payload = load_json(promote)
        require(promote.returncode == 0, f"promote failed: {promote.stderr or promote.stdout}")
        require(promote_payload.get("status") == "promoted", f"promote status wrong: {promote_payload}")
        require(promote_payload.get("safety", {}).get("memory_candidate_created") is True, f"memory promotion missing: {promote_payload}")
        require(promote_payload.get("safety", {}).get("customer_delivery_artifact_created") is True, f"delivery promotion missing: {promote_payload}")
        delivery_artifact_id = promote_payload.get("delivery_artifact_id") or ""
        require(delivery_artifact_id.startswith("art_customer_cmd_synthesis_"), f"bad delivery artifact id: {promote_payload}")

        delivery_status, delivery_board = http_json("GET", "/api/workflows/customer-delivery-board?limit=20")
        transcripts.append(json.dumps(delivery_board, ensure_ascii=False))
        require(delivery_status == 200, f"delivery board failed: {delivery_status} {delivery_board}")
        deliveries = delivery_board.get("deliveries") or []
        require(any(row.get("artifact_id") == delivery_artifact_id for row in deliveries), f"delivery artifact missing from board: {delivery_board}")

        queue_status, queue_after = http_json("GET", "/api/review/queue?limit=20")
        transcripts.append(json.dumps(queue_after, ensure_ascii=False))
        require(queue_status == 200, f"review queue after promote failed: {queue_status} {queue_after}")
        require(any(item.get("item_type") == "memory_candidate" and item.get("summary") for item in (queue_after.get("review_items") or [])), f"memory candidate missing after promote: {queue_after}")

        if DEFAULT_DB.exists():
            promoted_counts = promotion_evidence(DEFAULT_DB, artifact_id, delivery_artifact_id)
            require(promoted_counts["memory_candidates"] >= 1, f"memory candidate missing: {promoted_counts}")
            require(promoted_counts["delivery_artifacts"] == 1, f"delivery artifact missing: {promoted_counts}")
            require(promoted_counts["promotion_audits"] >= 2, f"promotion audit missing: {promoted_counts}")
            require(promoted_counts["promotion_events"] >= 2, f"promotion events missing: {promoted_counts}")

        require(not leaked_secret("\n".join(transcripts)), "synthesis output leaked token-like material")
    except Exception as exc:
        failures.append(str(exc))

    result = {
        "ok": not failures,
        "project_id": project_id,
        "plan_id": plan_id,
        "task_ids": task_ids,
        "artifact_id": artifact_id,
        "approval_id": approval_id,
        "delivery_artifact_id": delivery_artifact_id,
        "evidence": artifact_evidence(DEFAULT_DB, artifact_id) if artifact_id and DEFAULT_DB.exists() else {},
        "promotion_evidence": promotion_evidence(DEFAULT_DB, artifact_id, delivery_artifact_id) if artifact_id and delivery_artifact_id and DEFAULT_DB.exists() else {},
        "secret_leaked": leaked_secret("\n".join(transcripts)),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
