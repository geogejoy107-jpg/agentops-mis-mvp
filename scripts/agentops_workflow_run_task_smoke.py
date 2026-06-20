#!/usr/bin/env python3
"""Smoke-test `agentops workflow run-task` create-and-execute path."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def run_cli(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env.pop("AGENTOPS_AGENT_ID", None)
    env["AGENTOPS_BASE_URL"] = "http://127.0.0.1:8787"
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    return bool(re.search(r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,})", text))


def main() -> int:
    suffix = stamp()
    agent_id = f"agt_workflow_run_task_smoke_{suffix}"
    mock = run_cli([
        "workflow",
        "run-task",
        "--adapter",
        "mock",
        "--worker-agent-id",
        agent_id,
        "--title",
        "CLI workflow run-task smoke",
        "--description",
        "Create a normal MIS task and execute it through one worker iteration.",
        "--acceptance",
        "Return task, run, tool and evaluation evidence.",
        "--priority",
        "high",
        "--risk",
        "low",
    ])
    mock_payload = load_json(mock)
    evidence = mock_payload.get("evidence") or {}
    require(mock.returncode == 0, f"mock workflow command failed: {mock.stderr or mock.stdout}")
    require(mock_payload.get("workflow") == "run_task", f"wrong workflow: {mock_payload}")
    require(mock_payload.get("ok") is True, f"mock workflow did not complete: {mock_payload}")
    require(mock_payload.get("adapter") == "mock", f"wrong adapter: {mock_payload}")
    require(mock_payload.get("agent_id") == agent_id, f"wrong worker agent: {mock_payload}")
    require(bool(mock_payload.get("task_id")), f"missing task id: {mock_payload}")
    require(bool(mock_payload.get("run_id")), f"missing run id: {mock_payload}")
    require(mock_payload.get("run_status") == "completed", f"run not completed: {mock_payload}")
    require(mock_payload.get("task_status") == "completed", f"task not completed: {mock_payload}")
    require(evidence.get("tool_calls", 0) >= 1, f"missing tool evidence: {evidence}")
    require(evidence.get("evaluations", 0) >= 1, f"missing evaluation evidence: {evidence}")

    hermes_gate = run_cli([
        "workflow",
        "run-task",
        "--adapter",
        "hermes",
        "--worker-agent-id",
        f"{agent_id}_hermes",
        "--title",
        "Hermes gate run-task smoke",
        "--description",
        "Hermes must not execute without explicit confirmation.",
    ])
    hermes_payload = load_json(hermes_gate)
    require(hermes_gate.returncode == 0, f"Hermes gate command failed: {hermes_gate.stderr or hermes_gate.stdout}")
    require(hermes_payload.get("dry_run") is True, f"Hermes without confirm should be dry-run: {hermes_payload}")
    require(hermes_payload.get("reason") == "confirm_run_required_for_live_adapter", f"wrong Hermes gate reason: {hermes_payload}")
    require(bool(hermes_payload.get("task_id")), f"Hermes gate should create planned task: {hermes_payload}")

    combined = "\n".join([mock.stdout, mock.stderr, hermes_gate.stdout, hermes_gate.stderr])
    require(not secret_leaked(combined), "workflow output leaked a secret-like token")
    print(json.dumps({
        "ok": True,
        "mock_task_id": mock_payload.get("task_id"),
        "mock_run_id": mock_payload.get("run_id"),
        "mock_evidence": evidence,
        "hermes_gate_task_id": hermes_payload.get("task_id"),
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
