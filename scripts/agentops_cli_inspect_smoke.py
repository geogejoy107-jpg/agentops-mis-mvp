#!/usr/bin/env python3
"""Verify the agentops CLI can inspect task/run/artifact evidence."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
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


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []

    workflow = run([
        "workflow",
        "customer-worker-task",
        "--adapter",
        "mock",
        "--title",
        "CLI inspect customer worker smoke",
        "--description",
        "A customer task is dispatched through the Agent Gateway path and then inspected through CLI read commands.",
        "--acceptance",
        "CLI must retrieve task, run, and artifact evidence without browser use.",
        "--selected-agent-id",
        "agt_worker_local",
    ])
    outputs.extend([workflow.stdout, workflow.stderr])
    workflow_payload = load_json(workflow)
    task_id = workflow_payload.get("task_id")
    run_id = workflow_payload.get("run_id")
    artifact_id = workflow_payload.get("artifact_id")
    require(workflow.returncode == 0, f"workflow command failed: {workflow.stderr or workflow.stdout}", failures)
    require(workflow_payload.get("ok") is True, f"workflow did not complete: {workflow_payload}", failures)
    require(bool(task_id and run_id and artifact_id), f"missing task/run/artifact ids: {workflow_payload}", failures)

    task_get = run(["task", "get", "--task-id", str(task_id)])
    outputs.extend([task_get.stdout, task_get.stderr])
    task_payload = load_json(task_get)
    require(task_get.returncode == 0, f"task get failed: {task_get.stderr or task_get.stdout}", failures)
    require((task_payload.get("task") or {}).get("task_id") == task_id, f"task get returned wrong task: {task_payload}", failures)
    require((task_payload.get("evidence") or {}).get("runs", 0) >= 1, f"task get missing run evidence: {task_payload}", failures)
    require((task_payload.get("evidence") or {}).get("artifacts", 0) >= 1, f"task get missing artifact evidence: {task_payload}", failures)

    task_list = run(["task", "list", "--limit", "200"])
    outputs.extend([task_list.stdout, task_list.stderr])
    task_list_payload = load_json(task_list)
    listed_task_ids = {row.get("task_id") for row in task_list_payload.get("tasks") or []}
    require(task_list.returncode == 0, f"task list failed: {task_list.stderr or task_list.stdout}", failures)
    require(task_id in listed_task_ids, f"task list did not include created task: {task_list_payload}", failures)

    run_get = run(["run", "get", "--run-id", str(run_id)])
    outputs.extend([run_get.stdout, run_get.stderr])
    run_payload = load_json(run_get)
    require(run_get.returncode == 0, f"run get failed: {run_get.stderr or run_get.stdout}", failures)
    require((run_payload.get("run") or {}).get("run_id") == run_id, f"run get returned wrong run: {run_payload}", failures)
    require((run_payload.get("evidence") or {}).get("tool_calls", 0) >= 1, f"run get missing tool evidence: {run_payload}", failures)
    require((run_payload.get("evidence") or {}).get("evaluations", 0) >= 1, f"run get missing eval evidence: {run_payload}", failures)
    require((run_payload.get("evidence") or {}).get("artifacts", 0) >= 1, f"run get missing artifact evidence: {run_payload}", failures)

    run_list = run(["run", "list", "--task-id", str(task_id), "--limit", "5"])
    outputs.extend([run_list.stdout, run_list.stderr])
    run_list_payload = load_json(run_list)
    listed_run_ids = {row.get("run_id") for row in run_list_payload.get("runs") or []}
    require(run_list.returncode == 0, f"run list failed: {run_list.stderr or run_list.stdout}", failures)
    require(run_id in listed_run_ids, f"run list did not include created run: {run_list_payload}", failures)

    artifact_list = run(["artifact", "list", "--task-id", str(task_id), "--limit", "5"])
    outputs.extend([artifact_list.stdout, artifact_list.stderr])
    artifact_payload = load_json(artifact_list)
    listed_artifact_ids = {row.get("artifact_id") for row in artifact_payload.get("artifacts") or []}
    require(artifact_list.returncode == 0, f"artifact list failed: {artifact_list.stderr or artifact_list.stdout}", failures)
    require(artifact_id in listed_artifact_ids, f"artifact list did not include created artifact: {artifact_payload}", failures)

    graph = run(["run", "graph", "--run-id", str(run_id)])
    outputs.extend([graph.stdout, graph.stderr])
    graph_payload = load_json(graph)
    require(graph.returncode == 0, f"run graph failed: {graph.stderr or graph.stdout}", failures)
    require(graph_payload.get("operation") == "run_graph", f"run graph did not return CLI envelope: {graph_payload}", failures)

    require(not leaked("\n".join(outputs)), "CLI inspect output leaked secret-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "task_id": task_id,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "task_evidence": task_payload.get("evidence"),
        "run_evidence": run_payload.get("evidence"),
        "artifact_count": artifact_payload.get("count"),
        "secret_leaked": False,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
