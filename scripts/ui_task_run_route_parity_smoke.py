#!/usr/bin/env python3
"""Route-level Gate 4 parity smoke for task and run Next.js routes."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
ARTIFACT_SAMPLE_PATHS = [
    ROOT / "artifacts" / "sample_export_runs.json",
    ROOT / "artifacts" / "sample_export_memories.json",
]
CONTRACT_ID = "ui_task_run_route_parity_v1"

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    free_port,
    http_json,
    leaked_secret,
    require,
    restore_next_env,
    run,
    start_process,
    wait_http,
)


def save_sample_exports() -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.exists() else None for path in ARTIFACT_SAMPLE_PATHS}


def restore_sample_exports(saved: dict[Path, bytes | None]) -> None:
    for path, content in saved.items():
        if content is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: clean(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


def pick(row: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys}


def normalize_task(row: dict[str, Any]) -> dict[str, Any]:
    return clean(pick(row, [
        "task_id",
        "title",
        "description",
        "status",
        "priority",
        "risk_level",
        "owner_agent_id",
        "acceptance_criteria",
        "budget_limit_usd",
        "created_at",
        "updated_at",
    ]))


def normalize_run(row: dict[str, Any]) -> dict[str, Any]:
    return clean(pick(row, [
        "run_id",
        "task_id",
        "agent_id",
        "runtime_type",
        "status",
        "duration_ms",
        "input_summary",
        "output_summary",
        "error_message",
        "cost_usd",
        "started_at",
        "created_at",
    ]))


def sorted_by_id(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: str(row.get(key) or ""))


def normalize_tasks(payload: Any) -> list[dict[str, Any]]:
    require(isinstance(payload, list), f"expected task list, got {type(payload).__name__}")
    return [normalize_task(row) for row in sorted_by_id(payload, "task_id")]


def normalize_runs(payload: Any) -> list[dict[str, Any]]:
    require(isinstance(payload, list), f"expected run list, got {type(payload).__name__}")
    return [normalize_run(row) for row in sorted_by_id(payload, "run_id")]


def normalize_task_detail(payload: Any) -> dict[str, Any]:
    require(isinstance(payload, dict), f"expected task detail object, got {type(payload).__name__}")
    task = payload.get("task") or {}
    require(isinstance(task, dict), "task detail is missing task object")
    return {
        "task": normalize_task(task),
        "run_ids": sorted(str(run.get("run_id")) for run in payload.get("runs", []) if isinstance(run, dict)),
        "approval_ids": sorted(str(item.get("approval_id")) for item in payload.get("approvals", []) if isinstance(item, dict)),
        "evaluation_count": len(payload.get("evaluations", []) or []),
        "memory_ids": sorted(str(item.get("memory_id")) for item in payload.get("memories", []) if isinstance(item, dict)),
        "artifact_ids": sorted(str(item.get("artifact_id")) for item in payload.get("artifacts", []) if isinstance(item, dict)),
        "token_omitted": payload.get("token_omitted", True),
    }


def normalize_run_detail(payload: Any) -> dict[str, Any]:
    require(isinstance(payload, dict), f"expected run detail object, got {type(payload).__name__}")
    run = payload.get("run") or {}
    require(isinstance(run, dict), "run detail is missing run object")
    return {
        "run": normalize_run(run),
        "task_id": (payload.get("task") or {}).get("task_id") if isinstance(payload.get("task"), dict) else run.get("task_id"),
        "tool_call_ids": sorted(str(item.get("tool_call_id")) for item in payload.get("tool_calls", []) if isinstance(item, dict)),
        "approval_ids": sorted(str(item.get("approval_id")) for item in payload.get("approvals", []) if isinstance(item, dict)),
        "evaluation_count": len(payload.get("evaluations", []) or []),
        "artifact_ids": sorted(str(item.get("artifact_id")) for item in payload.get("artifacts", []) if isinstance(item, dict)),
        "audit_count": len(payload.get("audit_logs", []) or []),
        "runtime_event_count": len(payload.get("runtime_events", []) or []),
        "token_omitted": payload.get("token_omitted", True),
    }


def normalize_run_graph(payload: Any) -> dict[str, Any]:
    require(isinstance(payload, dict), f"expected run graph object, got {type(payload).__name__}")
    run = payload.get("run") or {}
    task = payload.get("task") or {}
    require(isinstance(run, dict), "run graph is missing run object")
    return {
        "run": normalize_run(run),
        "task_id": task.get("task_id") if isinstance(task, dict) else run.get("task_id"),
        "children": sorted(str(item.get("run_id")) for item in payload.get("children", []) if isinstance(item, dict)),
        "siblings": sorted(str(item.get("run_id")) for item in payload.get("siblings_by_delegation", []) if isinstance(item, dict)),
        "token_omitted": payload.get("token_omitted", True),
    }


def assert_equal(label: str, direct: Any, proxied: Any) -> None:
    require(direct == proxied, f"{label} mismatch:\ndirect={json.dumps(direct, sort_keys=True)}\nproxied={json.dumps(proxied, sort_keys=True)}")


def static_link_checks() -> None:
    ledger_text = (NEXT_APP / "src" / "components" / "LedgerPages.tsx").read_text(encoding="utf-8")
    detail_text = (NEXT_APP / "src" / "components" / "LedgerDetailPages.tsx").read_text(encoding="utf-8")
    matrix_text = (ROOT / "docs" / "UI_API_PARITY_MATRIX.json").read_text(encoding="utf-8")
    require("next/link" in ledger_text, "Next task/run list page must import next/link")
    require("/workspace/tasks/${encodeURIComponent(task.task_id)}" in ledger_text, "Next task rows must link to task detail")
    require("/workspace/runs/${encodeURIComponent(run.run_id)}" in ledger_text, "Next run rows must link to run detail")
    require("/workspace/runs/${encodeURIComponent(run.run_id)}" in detail_text, "Next task detail must link related runs")
    require("taskIdForLink = task?.task_id || run?.task_id" in detail_text, "Next run detail must fall back to run.task_id for task links")
    require("/workspace/tasks/${encodeURIComponent(taskIdForLink)}" in detail_text, "Next run detail must link back to task")
    require(CONTRACT_ID in matrix_text, "UI/API parity matrix must reference the task/run route parity smoke contract")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run task/run route read-model parity smoke.")
    parser.add_argument("--api-port", type=int, default=0)
    parser.add_argument("--next-port", type=int, default=0)
    args = parser.parse_args()

    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Next.js route parity smoke"}, indent=2), file=sys.stderr)
        return 1

    static_link_checks()
    api_port = args.api_port or free_port()
    next_port = args.next_port or free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    processes: list[subprocess.Popen[str]] = []
    saved_exports = save_sample_exports()

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-task-run-parity-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/tasks")

            direct_tasks_raw = http_json(f"{api_base}/api/tasks")
            proxied_tasks_raw = http_json(f"{next_base}/api/mis/tasks")
            direct_runs_raw = http_json(f"{api_base}/api/runs")
            proxied_runs_raw = http_json(f"{next_base}/api/mis/runs")

            direct_tasks = normalize_tasks(direct_tasks_raw)
            proxied_tasks = normalize_tasks(proxied_tasks_raw)
            direct_runs = normalize_runs(direct_runs_raw)
            proxied_runs = normalize_runs(proxied_runs_raw)
            require(direct_tasks, "seeded MIS API returned no tasks")
            require(direct_runs, "seeded MIS API returned no runs")
            assert_equal("task list read model", direct_tasks, proxied_tasks)
            assert_equal("run list read model", direct_runs, proxied_runs)

            task_id = str(direct_runs[0].get("task_id") or direct_tasks[0]["task_id"])
            run_id = str(direct_runs[0]["run_id"])
            direct_task_detail = normalize_task_detail(http_json(f"{api_base}/api/tasks/{task_id}"))
            proxied_task_detail = normalize_task_detail(http_json(f"{next_base}/api/mis/tasks/{task_id}"))
            direct_run_detail = normalize_run_detail(http_json(f"{api_base}/api/runs/{run_id}"))
            proxied_run_detail = normalize_run_detail(http_json(f"{next_base}/api/mis/runs/{run_id}"))
            direct_run_graph = normalize_run_graph(http_json(f"{api_base}/api/runs/{run_id}/graph"))
            proxied_run_graph = normalize_run_graph(http_json(f"{next_base}/api/mis/runs/{run_id}/graph"))
            assert_equal("task detail read model", direct_task_detail, proxied_task_detail)
            assert_equal("run detail read model", direct_run_detail, proxied_run_detail)
            assert_equal("run graph read model", direct_run_graph, proxied_run_graph)

            checked_payload = json.dumps({
                "tasks": direct_tasks[:5],
                "runs": direct_runs[:5],
                "task_detail": direct_task_detail,
                "run_detail": direct_run_detail,
                "run_graph": direct_run_graph,
            }, ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(checked_payload), "task/run route parity payload leaked token-like material")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "task_count": len(direct_tasks),
                "run_count": len(direct_runs),
                "checked_task_id": task_id,
                "checked_run_id": run_id,
                "list_links_to_detail": True,
                "direct_api_matches_next_proxy": True,
                "secret_leaked": False,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()
        restore_sample_exports(saved_exports)


if __name__ == "__main__":
    raise SystemExit(main())
