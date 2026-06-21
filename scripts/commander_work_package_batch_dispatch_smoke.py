#!/usr/bin/env python3
"""Smoke-test async batch dispatch for Commander work packages."""
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


def task_evidence(db_path: Path, task_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        return {
            "runs": count_rows(conn, "SELECT COUNT(*) FROM runs WHERE task_id=?", (task_id,)),
            "tool_calls": count_rows(conn, "SELECT COUNT(*) FROM tool_calls WHERE run_id IN (SELECT run_id FROM runs WHERE task_id=?)", (task_id,)),
            "evaluations": count_rows(conn, "SELECT COUNT(*) FROM evaluations WHERE task_id=?", (task_id,)),
            "workflow_jobs": count_rows(conn, "SELECT COUNT(*) FROM workflow_jobs WHERE result_task_id=?", (task_id,)),
        }
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
    project_id = f"proj_commander_batch_smoke_{suffix}"
    plan_id = f"cmdplan_batch_smoke_{suffix}"
    goal = "Use AgentOps MIS commander batch dispatch to run parallel work packages asynchronously."
    transcripts: list[str] = []
    failures: list[str] = []
    task_ids: list[str] = []
    job_ids: list[str] = []
    try:
        status, created = http_json("POST", "/api/commander/work-packages/plan", {
            "project_id": project_id,
            "plan_id": plan_id,
            "goal": goal,
            "max_packages": 3,
            "confirm_create": True,
        })
        transcripts.append(json.dumps(created, ensure_ascii=False))
        require(status == 201, f"create failed: {status} {created}")
        task_ids = created.get("created_task_ids") or []
        require(len(task_ids) == 3, f"expected 3 task ids: {created}")

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
        payload = load_json(batch)
        require(batch.returncode == 0, f"CLI batch failed: {batch.stderr or batch.stdout}")
        require(payload.get("ok") is True, f"batch not ok: {payload}")
        require(payload.get("status") == "queued", f"batch not queued: {payload}")
        require(payload.get("safety", {}).get("jobs_created") == 2, f"wrong jobs_created: {payload}")
        require(payload.get("live_execution_performed") is False, "mock batch marked live")
        job_ids = payload.get("job_ids") or []
        require(len(job_ids) == 2, f"expected 2 job ids: {payload}")

        jobs = [wait_job(job_id) for job_id in job_ids]
        transcripts.append(json.dumps(jobs, ensure_ascii=False))
        require(all(job.get("status") == "completed" for job in jobs), f"jobs not completed: {jobs}")
        require({job.get("result_task_id") for job in jobs} == set(task_ids[:2]), f"job task mismatch: {jobs}")
        require(all(job.get("result_run_id") for job in jobs), f"jobs missing run ids: {jobs}")

        gate_status, gate_payload = http_json("POST", "/api/commander/work-packages/dispatch-batch", {
            "task_ids": [task_ids[2]],
            "adapter": "openclaw",
        })
        transcripts.append(json.dumps(gate_payload, ensure_ascii=False))
        require(gate_status == 409, f"OpenClaw no-confirm should return 409: {gate_status} {gate_payload}")
        require(gate_payload.get("reason") == "confirm_run_required_for_live_adapter", f"wrong gate reason: {gate_payload}")
        require(gate_payload.get("safety", {}).get("jobs_created") == 0, f"gate created jobs: {gate_payload}")

        readback_status, readback = http_json("GET", f"/api/commander/work-packages?project_id={project_id}&limit=10")
        transcripts.append(json.dumps(readback, ensure_ascii=False))
        require(readback_status == 200, f"readback failed: {readback_status} {readback}")
        packages = {item.get("task_id"): item for item in readback.get("work_packages") or []}
        require(packages.get(task_ids[0], {}).get("package_status") == "ready_for_review", f"package 0 not ready: {packages.get(task_ids[0])}")
        require(packages.get(task_ids[1], {}).get("package_status") == "ready_for_review", f"package 1 not ready: {packages.get(task_ids[1])}")
        require(packages.get(task_ids[2], {}).get("package_status") == "planned", f"package 2 should remain planned: {packages.get(task_ids[2])}")

        if DEFAULT_DB.exists():
            for task_id in task_ids[:2]:
                counts = task_evidence(DEFAULT_DB, task_id)
                require(counts["workflow_jobs"] >= 1, f"{task_id} missing workflow job: {counts}")
                require(counts["runs"] >= 1, f"{task_id} missing run: {counts}")
                require(counts["tool_calls"] >= 1, f"{task_id} missing tool call: {counts}")
                require(counts["evaluations"] >= 1, f"{task_id} missing evaluation: {counts}")
            gated_counts = task_evidence(DEFAULT_DB, task_ids[2])
            require(gated_counts["workflow_jobs"] == 0, f"gated task should not have workflow job: {gated_counts}")

        require(not leaked_secret("\n".join(transcripts)), "batch dispatch output leaked token-like material")
    except Exception as exc:
        failures.append(str(exc))

    result = {
        "ok": not failures,
        "project_id": project_id,
        "plan_id": plan_id,
        "task_ids": task_ids,
        "job_ids": job_ids,
        "evidence": {task_id: task_evidence(DEFAULT_DB, task_id) for task_id in task_ids} if DEFAULT_DB.exists() else {},
        "secret_leaked": leaked_secret("\n".join(transcripts)),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
