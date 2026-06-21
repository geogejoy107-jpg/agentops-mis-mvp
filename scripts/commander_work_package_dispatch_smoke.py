#!/usr/bin/env python3
"""Smoke-test targeted Commander work-package dispatch through API and CLI."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
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


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = 180) -> tuple[int, dict]:
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


def run_cli(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
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


def count_rows(conn: sqlite3.Connection, sql: str, params=()) -> int:
    return int((conn.execute(sql, params).fetchone() or [0])[0] or 0)


def task_evidence(db_path: Path, task_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        return {
            "runs": count_rows(conn, "SELECT COUNT(*) FROM runs WHERE task_id=?", (task_id,)),
            "tool_calls": count_rows(conn, "SELECT COUNT(*) FROM tool_calls WHERE run_id IN (SELECT run_id FROM runs WHERE task_id=?)", (task_id,)),
            "evaluations": count_rows(conn, "SELECT COUNT(*) FROM evaluations WHERE task_id=?", (task_id,)),
            "runtime_events": count_rows(conn, "SELECT COUNT(*) FROM runtime_events WHERE task_id=?", (task_id,)),
            "audit_logs": count_rows(conn, "SELECT COUNT(*) FROM audit_logs WHERE entity_id=?", (task_id,)),
            "artifacts": count_rows(conn, "SELECT COUNT(*) FROM artifacts WHERE task_id=?", (task_id,)),
            "plan_evidence_manifests": count_rows(conn, "SELECT COUNT(*) FROM plan_evidence_manifests WHERE task_id=?", (task_id,)),
        }
    finally:
        conn.close()


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    suffix = stamp()
    project_id = f"proj_commander_dispatch_smoke_{suffix}"
    plan_id = f"cmdplan_dispatch_smoke_{suffix}"
    goal = "Use AgentOps MIS commander to dispatch targeted work packages and verify ledger evidence."
    transcripts: list[str] = []
    failures: list[str] = []
    task_ids: list[str] = []
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

        api_status, api_dispatch = http_json("POST", f"/api/commander/work-packages/{task_ids[0]}/dispatch", {
            "adapter": "mock",
            "confirm_run": False,
        }, timeout=220)
        transcripts.append(json.dumps(api_dispatch, ensure_ascii=False))
        require(api_status == 201, f"API dispatch failed: {api_status} {api_dispatch}")
        require(api_dispatch.get("ok") is True, f"API dispatch not ok: {api_dispatch}")
        require(api_dispatch.get("run_id"), f"API dispatch missing run: {api_dispatch}")
        require(api_dispatch.get("safety", {}).get("run_created") is True, f"API dispatch safety missing run: {api_dispatch}")
        require(api_dispatch.get("live_execution_performed") is False, "mock dispatch marked live execution")
        evidence_api = api_dispatch.get("evidence") or {}
        require(evidence_api.get("tool_calls", 0) >= 1, f"API evidence missing tool call: {evidence_api}")
        require(evidence_api.get("evaluations", 0) >= 1, f"API evidence missing eval: {evidence_api}")
        require(evidence_api.get("runtime_events", 0) >= 1, f"API evidence missing runtime event: {evidence_api}")
        require(evidence_api.get("audit_logs", 0) >= 1, f"API evidence missing audit: {evidence_api}")

        cli_dispatch = run_cli([
            "commander",
            "dispatch-package",
            "--task-id",
            task_ids[1],
            "--adapter",
            "mock",
        ], timeout=220)
        transcripts.extend([cli_dispatch.stdout, cli_dispatch.stderr])
        cli_dispatch_payload = load_json(cli_dispatch)
        require(cli_dispatch.returncode == 0, f"CLI dispatch failed: {cli_dispatch.stderr or cli_dispatch.stdout}")
        require(cli_dispatch_payload.get("ok") is True, f"CLI dispatch not ok: {cli_dispatch_payload}")
        require(cli_dispatch_payload.get("run_id"), f"CLI dispatch missing run: {cli_dispatch_payload}")

        hermes_gate = run_cli([
            "commander",
            "dispatch-package",
            "--task-id",
            task_ids[2],
            "--adapter",
            "hermes",
        ], timeout=90)
        transcripts.extend([hermes_gate.stdout, hermes_gate.stderr])
        hermes_gate_payload = load_json(hermes_gate)
        require(hermes_gate.returncode == 0, f"Hermes no-confirm gate failed: {hermes_gate.stderr or hermes_gate.stdout}")
        require(hermes_gate_payload.get("ok") is False, f"Hermes no-confirm should not run: {hermes_gate_payload}")
        require(hermes_gate_payload.get("reason") == "confirm_run_required_for_live_adapter", f"Hermes gate reason wrong: {hermes_gate_payload}")
        require(hermes_gate_payload.get("safety", {}).get("run_created") is False, f"Hermes gate created run: {hermes_gate_payload}")
        require(hermes_gate_payload.get("live_execution_performed") is False, f"Hermes gate marked live: {hermes_gate_payload}")

        readback_status, readback = http_json("GET", f"/api/commander/work-packages?project_id={project_id}&limit=10")
        transcripts.append(json.dumps(readback, ensure_ascii=False))
        require(readback_status == 200, f"readback failed: {readback_status} {readback}")
        packages = {item.get("task_id"): item for item in readback.get("work_packages") or []}
        require(packages.get(task_ids[0], {}).get("package_status") == "ready_for_review", f"API package not ready: {packages.get(task_ids[0])}")
        require(packages.get(task_ids[1], {}).get("package_status") == "ready_for_review", f"CLI package not ready: {packages.get(task_ids[1])}")
        require(packages.get(task_ids[2], {}).get("package_status") == "planned", f"Hermes gated package should remain planned: {packages.get(task_ids[2])}")

        if DEFAULT_DB.exists():
            for task_id in task_ids[:2]:
                counts = task_evidence(DEFAULT_DB, task_id)
                require(counts["runs"] >= 1, f"{task_id} missing run evidence: {counts}")
                require(counts["tool_calls"] >= 1, f"{task_id} missing tool evidence: {counts}")
                require(counts["evaluations"] >= 1, f"{task_id} missing eval evidence: {counts}")
                require(counts["runtime_events"] >= 1, f"{task_id} missing runtime evidence: {counts}")
                require(counts["audit_logs"] >= 1, f"{task_id} missing audit evidence: {counts}")
            gated_counts = task_evidence(DEFAULT_DB, task_ids[2])
            require(gated_counts["runs"] == 0, f"gated Hermes task unexpectedly ran: {gated_counts}")
            require(gated_counts["runtime_events"] >= 1, f"gated Hermes task missing gate runtime event: {gated_counts}")

        require(not leaked_secret("\n".join(transcripts)), "dispatch output leaked token-like material")
    except Exception as exc:
        failures.append(str(exc))

    result = {
        "ok": not failures,
        "project_id": project_id,
        "plan_id": plan_id,
        "task_ids": task_ids,
        "evidence": {task_id: task_evidence(DEFAULT_DB, task_id) for task_id in task_ids} if DEFAULT_DB.exists() else {},
        "secret_leaked": leaked_secret("\n".join(transcripts)),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
