#!/usr/bin/env python3
"""Smoke test `agentops workflow customer-worker-task`."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
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
    return any(marker in text for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"])


def main() -> int:
    mock = run([
        "workflow",
        "customer-worker-task",
        "--adapter",
        "mock",
        "--title",
        "CLI customer worker smoke",
        "--description",
        "Customer sends a task through the CLI and expects a real worker ledger result.",
        "--acceptance",
        "Return run, tool, evaluation, audit and customer_worker_result artifact evidence.",
        "--selected-agent-id",
        "agt_worker_local",
    ])
    mock_payload = load_json(mock)
    evidence = mock_payload.get("evidence") or {}
    require(mock.returncode == 0, f"mock workflow CLI failed: {mock.stderr or mock.stdout}")
    require(mock_payload.get("provider") == "agentops-worker", f"wrong provider: {mock_payload}")
    require(mock_payload.get("workflow") == "customer_worker_task", f"wrong workflow: {mock_payload}")
    require(mock_payload.get("ok") is True, f"mock workflow did not complete: {mock_payload}")
    require(mock_payload.get("dry_run") is False, f"mock workflow should write real ledger evidence: {mock_payload}")
    require(bool(mock_payload.get("run_id")), f"missing run id: {mock_payload}")
    require(bool(mock_payload.get("artifact_id")), f"missing artifact id: {mock_payload}")
    require(evidence.get("tool_calls", 0) >= 1, f"missing tool evidence: {evidence}")
    require(evidence.get("evaluations", 0) >= 1, f"missing eval evidence: {evidence}")
    require(evidence.get("audit_logs", 0) >= 1, f"missing audit evidence: {evidence}")
    require(evidence.get("artifacts", 0) >= 1, f"missing artifact evidence: {evidence}")

    hermes_gate = run([
        "workflow",
        "customer-worker-task",
        "--adapter",
        "hermes",
        "--title",
        "CLI Hermes confirm gate",
        "--description",
        "This must not execute Hermes without explicit confirmation.",
    ])
    hermes_payload = load_json(hermes_gate)
    require(hermes_gate.returncode == 0, f"hermes gate command failed: {hermes_gate.stderr or hermes_gate.stdout}")
    require(hermes_payload.get("dry_run") is True, f"Hermes without confirm should be planned/dry-run: {hermes_payload}")
    require(hermes_payload.get("reason") == "confirm_run_required_for_live_adapter", f"wrong Hermes gate reason: {hermes_payload}")

    combined = "\n".join([mock.stdout, mock.stderr, hermes_gate.stdout, hermes_gate.stderr])
    require(not secret_leaked(combined), "CLI workflow output leaked a secret-like token")
    print(json.dumps({
        "ok": True,
        "mock_run_id": mock_payload.get("run_id"),
        "mock_artifact_id": mock_payload.get("artifact_id"),
        "mock_evidence": evidence,
        "hermes_gate_task_id": hermes_payload.get("task_id"),
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
