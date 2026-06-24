#!/usr/bin/env python3
"""Smoke test approval list/approve/reject CLI commands."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def run(args: list[str], base_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
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


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def secret_leaked(text: str) -> bool:
    return any(marker in text for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"])


def create_approval_gate(base_url: str, suffix: str) -> dict:
    agent_id = f"agt_approval_cli_{suffix}"
    register = run(["agent", "register", "--id", agent_id, "--name", f"Approval CLI {suffix}", "--role", "Approval CLI Smoke"], base_url)
    if register.returncode != 0:
        raise RuntimeError(register.stderr or register.stdout)
    task = run([
        "task",
        "create",
        "--title",
        f"Approval CLI smoke {suffix}",
        "--description",
        "Create a normal Gateway task with a human approval gate.",
        "--owner-agent-id",
        agent_id,
        "--acceptance",
        "Approval CLI must list and decide this gate.",
        "--risk",
        "medium",
    ], base_url)
    task_payload = load_json(task)
    if task.returncode != 0:
        raise RuntimeError(task.stderr or task.stdout)
    task_id = task_payload.get("task_id") or (task_payload.get("task") or {}).get("task_id")
    run_started = run([
        "run",
        "start",
        "--task-id",
        task_id,
        "--agent-id",
        agent_id,
        "--runtime",
        "mock",
        "--input-summary",
        "Approval CLI smoke run.",
        "--approval-required",
    ], base_url)
    run_payload = load_json(run_started)
    if run_started.returncode != 0:
        raise RuntimeError(run_started.stderr or run_started.stdout)
    run_id = (run_payload.get("run") or {}).get("run_id") or run_payload.get("run_id")
    approval = run([
        "approval",
        "request",
        "--task-id",
        task_id,
        "--run-id",
        run_id,
        "--agent-id",
        agent_id,
        "--reason",
        f"Approval CLI smoke gate {suffix}.",
    ], base_url)
    approval_payload = load_json(approval)
    if approval.returncode != 0:
        raise RuntimeError(approval.stderr or approval.stdout)
    approval_row = approval_payload.get("approval") or approval_payload
    return {
        "agent_id": agent_id,
        "task_id": task_id,
        "run_id": run_id,
        "approval_id": approval_row.get("approval_id"),
    }


def main() -> int:
    base_url = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
    failures: list[str] = []
    outputs: list[str] = []

    suffix = uuid.uuid4().hex[:8]
    first = create_approval_gate(base_url, f"{suffix}_approve")
    second = create_approval_gate(base_url, f"{suffix}_reject")
    outputs.extend([json.dumps(first), json.dumps(second)])
    first_approval = first["approval_id"]
    second_approval = second["approval_id"]

    listed = run(["approval", "list", "--decision", "pending", "--limit", "50"], base_url)
    listed_payload = load_json(listed)
    outputs.extend([listed.stdout, listed.stderr])
    pending_ids = [row.get("approval_id") for row in listed_payload.get("approvals") or []]
    require(listed.returncode == 0, f"approval list failed: {listed.stderr or listed.stdout}", failures)
    require(listed_payload.get("operation") == "approval_list", f"wrong list operation: {listed_payload}", failures)
    require(first_approval in pending_ids, f"first approval missing from pending list: {first_approval}", failures)
    require(second_approval in pending_ids, f"second approval missing from pending list: {second_approval}", failures)

    approved = run(["approval", "approve", "--approval-id", first_approval], base_url)
    approved_payload = load_json(approved)
    outputs.extend([approved.stdout, approved.stderr])
    require(approved.returncode == 0, f"approval approve failed: {approved.stderr or approved.stdout}", failures)
    require(approved_payload.get("operation") == "approval_approve", f"wrong approve operation: {approved_payload}", failures)
    require(approved_payload.get("decision") == "approved", f"approval not approved: {approved_payload}", failures)

    rejected = run(["approval", "reject", "--approval-id", second_approval], base_url)
    rejected_payload = load_json(rejected)
    outputs.extend([rejected.stdout, rejected.stderr])
    require(rejected.returncode == 0, f"approval reject failed: {rejected.stderr or rejected.stdout}", failures)
    require(rejected_payload.get("operation") == "approval_reject", f"wrong reject operation: {rejected_payload}", failures)
    require(rejected_payload.get("decision") == "rejected", f"approval not rejected: {rejected_payload}", failures)

    first_task_id = approved_payload.get("task_id")
    second_task_id = rejected_payload.get("task_id")
    first_run_id = approved_payload.get("run_id")
    second_run_id = rejected_payload.get("run_id")
    first_task = run(["task", "get", "--task-id", first_task_id], base_url)
    second_task = run(["task", "get", "--task-id", second_task_id], base_url)
    first_run = run(["run", "get", "--run-id", first_run_id], base_url)
    second_run = run(["run", "get", "--run-id", second_run_id], base_url)
    outputs.extend([first_task.stdout, second_task.stdout, first_run.stdout, second_run.stdout])
    first_task_payload = load_json(first_task)
    second_task_payload = load_json(second_task)
    first_run_payload = load_json(first_run)
    second_run_payload = load_json(second_run)
    require((first_task_payload.get("task") or {}).get("status") == "completed", f"approved task not completed: {first_task_payload}", failures)
    require((first_run_payload.get("run") or {}).get("approval_required") in (False, 0), f"approved run still requires approval: {first_run_payload}", failures)
    require((second_task_payload.get("task") or {}).get("status") == "blocked", f"rejected task not blocked: {second_task_payload}", failures)
    require((second_run_payload.get("run") or {}).get("status") == "blocked", f"rejected run not blocked: {second_run_payload}", failures)

    require(not secret_leaked("\n".join(outputs)), "approval CLI leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "approved": {
            "approval_id": first_approval,
            "task_id": first_task_id,
            "run_id": first_run_id,
            "task_status": (first_task_payload.get("task") or {}).get("status"),
        },
        "rejected": {
            "approval_id": second_approval,
            "task_id": second_task_id,
            "run_id": second_run_id,
            "task_status": (second_task_payload.get("task") or {}).get("status"),
        },
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
