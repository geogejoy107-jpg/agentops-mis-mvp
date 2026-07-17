#!/usr/bin/env python3
"""Smoke-test `agentops workflow run-task` create-and-execute path."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def run_cli(args: list[str], timeout: int = 180, env_override: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env.pop("AGENTOPS_AGENT_ID", None)
    env["AGENTOPS_BASE_URL"] = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    if env_override:
        env.update(env_override)
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
    readback = mock_payload.get("readback") or {}
    agent_plan = mock_payload.get("agent_plan") or {}
    plan_evidence = mock_payload.get("plan_evidence") or {}
    require(mock.returncode == 0, f"mock workflow command failed: {mock.stderr or mock.stdout}")
    require(mock_payload.get("workflow") == "run_task", f"wrong workflow: {mock_payload}")
    require(mock_payload.get("ok") is True, f"mock workflow did not complete: {mock_payload}")
    require(mock_payload.get("adapter") == "mock", f"wrong adapter: {mock_payload}")
    require(mock_payload.get("agent_id") == agent_id, f"wrong worker agent: {mock_payload}")
    require(bool(mock_payload.get("task_id")), f"missing task id: {mock_payload}")
    require(bool(mock_payload.get("run_id")), f"missing run id: {mock_payload}")
    require(mock_payload.get("run_status") == "completed", f"run not completed: {mock_payload}")
    require(mock_payload.get("task_status") == "completed", f"task not completed: {mock_payload}")
    require(readback.get("run_provider") == "agent_gateway", f"run readback should use Agent Gateway: {mock_payload}")
    require(readback.get("task_provider") == "agent_gateway", f"task readback should use Agent Gateway: {mock_payload}")
    require(readback.get("required_scope") == "tasks:read", f"readback scope missing: {mock_payload}")
    require(bool(readback.get("agent_plan_id")), f"readback missing agent plan id: {mock_payload}")
    require(readback.get("agent_plan_verified") is True, f"readback agent plan should verify: {mock_payload}")
    require(bool(readback.get("plan_evidence_manifest_id")), f"readback missing plan evidence manifest id: {mock_payload}")
    require(readback.get("plan_evidence_verified") is True, f"readback plan evidence should verify: {mock_payload}")
    require(agent_plan.get("plan_id") == readback.get("agent_plan_id"), f"agent plan readback mismatch: {mock_payload}")
    require(agent_plan.get("verified") is True, f"agent plan should verify: {agent_plan}")
    require(plan_evidence.get("manifest_id") == readback.get("plan_evidence_manifest_id"), f"plan evidence readback mismatch: {mock_payload}")
    require(plan_evidence.get("verified") is True, f"plan evidence should verify: {plan_evidence}")
    require(evidence.get("tool_calls", 0) >= 1, f"missing tool evidence: {evidence}")
    require(evidence.get("evaluations", 0) >= 1, f"missing evaluation evidence: {evidence}")
    require((plan_evidence.get("evidence_counts") or {}).get("tool_calls", 0) >= 1, f"manifest missing tool evidence: {plan_evidence}")
    require((plan_evidence.get("evidence_counts") or {}).get("evaluations", 0) >= 1, f"manifest missing evaluation evidence: {plan_evidence}")

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

    stale_config_payload = {}
    stale_config_returncode = None
    with tempfile.TemporaryDirectory(prefix="agentops-run-task-stale-config-") as tmp:
        config_path = Path(tmp) / "config.json"
        config_path.write_text(json.dumps({
            "base_url": os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"),
            "workspace_id": "local-demo",
            "api_key": "stale-config-token-for-run-task-smoke",
        }), encoding="utf-8")
        stale_agent_id = f"agt_workflow_run_task_stale_config_{suffix}"
        stale_config = run_cli([
            "workflow",
            "run-task",
            "--adapter",
            "mock",
            "--worker-agent-id",
            stale_agent_id,
            "--title",
            "CLI workflow run-task stale config smoke",
            "--description",
            "A stale saved local config token must not break the worker child process on loopback.",
            "--acceptance",
            "Return task, run, tool and evaluation evidence despite stale saved config token.",
            "--priority",
            "high",
            "--risk",
            "low",
        ], env_override={"AGENTOPS_CONFIG": str(config_path)})
        stale_config_returncode = stale_config.returncode
        stale_config_payload = load_json(stale_config)
        require(stale_config.returncode == 0, f"stale config workflow command failed: {stale_config.stderr or stale_config.stdout}")
        require(stale_config_payload.get("ok") is True, f"stale config workflow did not complete: {stale_config_payload}")
        require(bool(stale_config_payload.get("run_id")), f"stale config workflow missing run id: {stale_config_payload}")
        require(((stale_config_payload.get("worker_result") or {}).get("state") or {}).get("status") in {"completed", "stopped"}, f"stale config worker did not finish cleanly: {stale_config_payload}")

    combined = "\n".join([mock.stdout, mock.stderr, hermes_gate.stdout, hermes_gate.stderr, json.dumps(stale_config_payload, ensure_ascii=False)])
    require(not secret_leaked(combined), "workflow output leaked a secret-like token")
    print(json.dumps({
        "ok": True,
        "mock_task_id": mock_payload.get("task_id"),
        "mock_run_id": mock_payload.get("run_id"),
        "mock_evidence": evidence,
        "agent_plan": agent_plan,
        "plan_evidence": plan_evidence,
        "readback": readback,
        "hermes_gate_task_id": hermes_payload.get("task_id"),
        "stale_config_returncode": stale_config_returncode,
        "stale_config_run_id": stale_config_payload.get("run_id"),
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
