#!/usr/bin/env python3
"""Smoke-test Commander work-package planning through API and CLI."""
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


def run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env["AGENTOPS_BASE_URL"] = BASE_URL
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def db_counts(db_path: Path, project_id: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        like_project = f"%Commander project: {project_id}%"
        return {
            "tasks": int(conn.execute("SELECT COUNT(*) FROM tasks WHERE description LIKE ?", (like_project,)).fetchone()[0] or 0),
            "localization_artifacts": int(conn.execute(
                """SELECT COUNT(*) FROM artifacts
                WHERE artifact_type='commander_repo_map_localization'
                AND task_id IN (SELECT task_id FROM tasks WHERE description LIKE ?)""",
                (like_project,),
            ).fetchone()[0] or 0),
            "localization_events": int(conn.execute(
                """SELECT COUNT(*) FROM runtime_events
                WHERE event_type='commander.repo_map_localization'
                AND task_id IN (SELECT task_id FROM tasks WHERE description LIKE ?)""",
                (like_project,),
            ).fetchone()[0] or 0),
            "localization_audits": int(conn.execute(
                """SELECT COUNT(*) FROM audit_logs
                WHERE action='commander.repo_map_localization_artifact'
                AND entity_id IN (
                    SELECT artifact_id FROM artifacts
                    WHERE artifact_type='commander_repo_map_localization'
                    AND task_id IN (SELECT task_id FROM tasks WHERE description LIKE ?)
                )""",
                (like_project,),
            ).fetchone()[0] or 0),
            "runtime_events": int(conn.execute("SELECT COUNT(*) FROM runtime_events WHERE event_type='commander.work_package_plan'").fetchone()[0] or 0),
            "audit_logs": int(conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='commander.work_package_plan_create'").fetchone()[0] or 0),
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
    project_id = f"proj_commander_plan_smoke_{suffix}"
    plan_id = f"cmdplan_smoke_{suffix}"
    goal = "Use AgentOps MIS to coordinate a customer AI-team project, split lanes, and prepare worker execution evidence."
    transcripts: list[str] = []
    failures: list[str] = []
    before = db_counts(DEFAULT_DB, project_id) if DEFAULT_DB.exists() else None
    try:
        status, preview = http_json("POST", "/api/commander/work-packages/plan", {
            "project_id": project_id,
            "plan_id": plan_id,
            "goal": goal,
            "max_packages": 4,
        })
        transcripts.append(json.dumps(preview, ensure_ascii=False))
        require(status == 200, f"preview failed: {status} {preview}")
        require(preview.get("status") == "preview", f"preview status wrong: {preview}")
        require(preview.get("created") is False, f"preview created tasks: {preview}")
        require(preview.get("safety", {}).get("ledger_mutated") is False, f"preview safety wrong: {preview}")
        preview_packages = preview.get("work_packages") or []
        require(len(preview_packages) == 4, f"preview missing packages: {preview}")
        require(all((item.get("repo_map_localization") or {}).get("raw_content_omitted") is True for item in preview_packages), f"preview missing safe repo-map localization: {preview_packages}")
        require((preview.get("localization_summary") or {}).get("artifacts_recorded") == 0, f"preview should not record localization artifacts: {preview}")
        if before is not None:
            after_preview = db_counts(DEFAULT_DB, project_id)
            require(before == after_preview, f"preview mutated database: before={before} after={after_preview}")

        cli_preview = run_cli([
            "commander",
            "plan",
            "--project-id",
            project_id,
            "--plan-id",
            plan_id,
            "--goal",
            goal,
            "--max-packages",
            "4",
        ])
        transcripts.extend([cli_preview.stdout, cli_preview.stderr])
        cli_preview_payload = load_json(cli_preview)
        require(cli_preview.returncode == 0, f"CLI preview failed: {cli_preview.stderr or cli_preview.stdout}")
        require(cli_preview_payload.get("status") == "preview", f"CLI preview status wrong: {cli_preview_payload}")

        cli_create = run_cli([
            "commander",
            "plan",
            "--project-id",
            project_id,
            "--plan-id",
            plan_id,
            "--goal",
            goal,
            "--max-packages",
            "4",
            "--confirm-create",
        ])
        transcripts.extend([cli_create.stdout, cli_create.stderr])
        create_payload = load_json(cli_create)
        require(cli_create.returncode == 0, f"CLI create failed: {cli_create.stderr or cli_create.stdout}")
        require(create_payload.get("status") == "created", f"create status wrong: {create_payload}")
        require(create_payload.get("created_count") == 4, f"wrong created count: {create_payload}")
        require(create_payload.get("live_execution_performed") is False, "planner executed live work")
        require(create_payload.get("token_omitted") is True, "token omission proof missing")
        task_ids = create_payload.get("created_task_ids") or []
        require(len(task_ids) == 4, f"wrong task ids: {create_payload}")
        created_packages = create_payload.get("work_packages") or []
        require(len(created_packages) == 4, f"created response missing work packages: {create_payload}")
        for item in created_packages:
            localization = item.get("localization_artifact") or {}
            repo_map = item.get("repo_map_localization") or {}
            require(localization.get("artifact_type") == "commander_repo_map_localization", f"package missing localization artifact: {item}")
            require(str(localization.get("uri") or "").startswith("repo-map://"), f"localization artifact URI wrong: {localization}")
            require(repo_map.get("raw_content_omitted") is True and repo_map.get("snippets_omitted") is True, f"repo-map localization should omit raw content: {repo_map}")
            require(repo_map.get("manifest_hash"), f"repo-map localization missing manifest hash: {repo_map}")

        for task_id in task_ids:
            detail_status, detail = http_json("GET", f"/api/tasks/{task_id}")
            require(detail_status == 200, f"task detail failed for {task_id}: {detail_status} {detail}")
            task = detail.get("task") or {}
            require(task.get("status") == "planned", f"task not planned: {task}")
            require(task.get("description", "").find(project_id) >= 0, f"task lacks project provenance: {task}")
            require(task.get("owner_agent_id"), f"task missing owner: {task}")
            artifacts = detail.get("artifacts") or []
            require(any(artifact.get("artifact_type") == "commander_repo_map_localization" for artifact in artifacts), f"task detail missing localization artifact: {detail}")

        after_create = db_counts(DEFAULT_DB, project_id) if DEFAULT_DB.exists() else None
        if after_create is not None:
            require(after_create["tasks"] >= 4, f"created tasks not found by provenance: {after_create}")
            require(after_create["localization_artifacts"] >= (before or {}).get("localization_artifacts", 0) + 4, f"localization artifacts missing: {after_create}")
            require(after_create["localization_events"] >= (before or {}).get("localization_events", 0) + 4, f"localization runtime events missing: {after_create}")
            require(after_create["localization_audits"] >= (before or {}).get("localization_audits", 0) + 4, f"localization audits missing: {after_create}")
            require(after_create["runtime_events"] >= (before or {}).get("runtime_events", 0) + 1, f"commander runtime event missing: {after_create}")
            require(after_create["audit_logs"] >= (before or {}).get("audit_logs", 0) + 1, f"commander audit log missing: {after_create}")

        readback_status, readback = http_json("GET", f"/api/commander/work-packages?project_id={project_id}&limit=10")
        transcripts.append(json.dumps(readback, ensure_ascii=False))
        require(readback_status == 200, f"readback API failed: {readback_status} {readback}")
        require(readback.get("operation") == "work_packages_readback", f"wrong readback operation: {readback}")
        require(readback.get("summary", {}).get("total") == 4, f"wrong readback total: {readback}")
        require((readback.get("summary", {}).get("localization") or {}).get("recorded") == 4, f"readback localization coverage wrong: {readback}")
        require((readback.get("summary", {}).get("localization") or {}).get("coverage_percent") == 100.0, f"readback localization coverage percent wrong: {readback}")
        require(readback.get("safety", {}).get("read_only") is True, f"readback not read-only: {readback}")
        require(readback.get("safety", {}).get("ledger_mutated") is False, f"readback mutated ledger flag: {readback}")
        readback_items = readback.get("work_packages") or []
        require({item.get("task_id") for item in readback_items} == set(task_ids), f"readback task mismatch: {readback_items}")
        require(all(item.get("project_id") == project_id for item in readback_items), f"readback project mismatch: {readback_items}")
        require(all(item.get("plan_id") == plan_id for item in readback_items), f"readback plan mismatch: {readback_items}")
        require(all(item.get("recommended_action") for item in readback_items), f"readback missing next action: {readback_items}")
        require(all((item.get("localization_artifact") or {}).get("artifact_type") == "commander_repo_map_localization" for item in readback_items), f"readback missing localization artifacts: {readback_items}")
        require(all(int((item.get("evidence_counts") or {}).get("artifacts") or 0) >= 1 for item in readback_items), f"readback evidence counts missing artifacts: {readback_items}")

        cli_readback = run_cli([
            "commander",
            "packages",
            "--project-id",
            project_id,
            "--limit",
            "10",
        ])
        transcripts.extend([cli_readback.stdout, cli_readback.stderr])
        cli_readback_payload = load_json(cli_readback)
        require(cli_readback.returncode == 0, f"CLI readback failed: {cli_readback.stderr or cli_readback.stdout}")
        require(cli_readback_payload.get("summary", {}).get("total") == 4, f"CLI readback total wrong: {cli_readback_payload}")
        require(all((item.get("localization_artifact") or {}).get("artifact_type") == "commander_repo_map_localization" for item in cli_readback_payload.get("work_packages") or []), f"CLI readback missing localization artifacts: {cli_readback_payload}")

        after_readback = db_counts(DEFAULT_DB, project_id) if DEFAULT_DB.exists() else None
        if after_create is not None and after_readback is not None:
            require(after_create == after_readback, f"readback mutated database: before={after_create} after={after_readback}")

        require(not leaked_secret("\n".join(transcripts)), "planner output leaked token-like material")
    except Exception as exc:
        failures.append(str(exc))

    result = {
        "ok": not failures,
        "project_id": project_id,
        "plan_id": plan_id,
        "created_count": 0 if failures else 4,
        "db_counts_before": before,
        "db_counts_after": db_counts(DEFAULT_DB, project_id) if DEFAULT_DB.exists() else None,
        "secret_leaked": leaked_secret("\n".join(transcripts)),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
