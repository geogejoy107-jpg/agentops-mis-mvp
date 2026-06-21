#!/usr/bin/env python3
"""Verify Agent Plan hash integrity and self-approval rejection."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def run(args: list[str], base_url: str, agent_id: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_AGENT_ID"] = agent_id
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def http_json(base_url: str, path: str, body: dict) -> tuple[int, dict]:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(
        base_url.rstrip("/") + path,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as res:
            payload = res.read().decode("utf-8")
            return res.status, json.loads(payload) if payload else {}
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(payload)
        except Exception:
            return exc.code, {"raw": payload}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


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
    parser = argparse.ArgumentParser(description="Verify Agent Plan integrity hardening.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    stamp = now_stamp()
    agent_id = f"agt_plan_integrity_{stamp}"
    task_id = f"tsk_plan_integrity_{stamp}"
    failures: list[str] = []
    outputs: list[str] = []

    register = run(["agent", "register", "--id", agent_id, "--name", f"Plan Integrity {stamp}", "--role", "Builder", "--runtime", "codex"], args.base_url, agent_id)
    outputs.extend([register.stdout, register.stderr])
    require(register.returncode == 0, f"agent register failed: {register.stderr or register.stdout}", failures)

    task = run([
        "task",
        "create",
        "--task-id",
        task_id,
        "--title",
        "Agent Plan integrity smoke task",
        "--description",
        "Verify agent-created plans cannot self-approve and carry immutable hashes.",
        "--owner-agent-id",
        agent_id,
        "--requester-id",
        "usr_founder",
        "--acceptance",
        "Approved status must be rejected at create time.",
        "--risk",
        "medium",
    ], args.base_url, agent_id)
    outputs.extend([task.stdout, task.stderr])
    require(task.returncode == 0, f"task create failed: {task.stderr or task.stdout}", failures)

    rejected_status, rejected_payload = http_json(args.base_url, "/api/agent-gateway/agent-plans", {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "task_id": task_id,
        "task_understanding": "Attempt to self-approve a plan should be rejected.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["server.py"],
        "risk_level": "medium",
        "execution_steps": ["READ", "PLAN", "VERIFY"],
        "verification_plan": "This request must fail.",
        "rollback_plan": "No ledger plan should be approved by the agent.",
        "status": "approved",
    })
    outputs.append(json.dumps(rejected_payload, ensure_ascii=False))
    require(rejected_status == 400, f"approved plan create should fail: {rejected_status} {rejected_payload}", failures)
    require(rejected_payload.get("error") == "plan_status_transition_required", f"wrong rejection payload: {rejected_payload}", failures)

    created = run([
        "agent-plan",
        "create",
        "--agent-id",
        agent_id,
        "--task-id",
        task_id,
        "--task-understanding",
        "Create a submitted plan with a stable plan hash.",
        "--referenced-specs",
        "PROJECT_SPEC.md,AGENT_WORKFLOW.md",
        "--referenced-memories",
        "knowledge/shared/common_failures.md",
        "--referenced-bases",
        "base_local_tasks",
        "--proposed-files-to-change",
        "server.py",
        "--risk",
        "medium",
        "--execution-steps",
        "READ,PLAN,RETRIEVE,VERIFY",
        "--verification-plan",
        "Run agent_plan_integrity_smoke.py.",
        "--rollback-plan",
        "Reject the plan and keep the task planned if verification fails.",
    ], args.base_url, agent_id)
    outputs.extend([created.stdout, created.stderr])
    created_payload = load_json(created)
    plan = created_payload.get("agent_plan") or {}
    plan_id = plan.get("plan_id")
    plan_hash = plan.get("plan_hash")
    require(created.returncode == 0, f"submitted plan create failed: {created.stderr or created.stdout}", failures)
    require(bool(plan_id), f"missing plan id: {created_payload}", failures)
    require(plan.get("status") == "submitted", f"created plan status mismatch: {plan}", failures)
    require(isinstance(plan_hash, str) and len(plan_hash) == 64, f"plan hash missing: {plan}", failures)
    require(not plan.get("approved_by_user_id") and not plan.get("approved_at"), f"agent-created plan should not have approval metadata: {plan}", failures)

    verified = run(["agent-plan", "verify", "--plan-id", str(plan_id)], args.base_url, agent_id)
    outputs.extend([verified.stdout, verified.stderr])
    verified_payload = load_json(verified)
    verified_plan = verified_payload.get("agent_plan") or {}
    verification = verified_payload.get("verification") or {}
    require(verified.returncode == 0, f"plan verify failed: {verified.stderr or verified.stdout}", failures)
    require(verification.get("pass") is True, f"plan verification should pass: {verified_payload}", failures)
    require(verification.get("plan_hash") == plan_hash, f"verification plan_hash mismatch: {verified_payload}", failures)
    require(verified_plan.get("verified_at"), f"verified_at missing: {verified_plan}", failures)
    require(isinstance(verified_plan.get("verification_result_hash"), str) and len(verified_plan.get("verification_result_hash")) == 64, f"verification hash missing: {verified_plan}", failures)
    require(not leaked("\n".join(outputs)), "Agent Plan integrity output leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "agent_id": agent_id,
        "task_id": task_id,
        "plan_id": plan_id,
        "self_approved_rejected": rejected_status == 400,
        "plan_hash": plan_hash,
        "verification_result_hash": verified_plan.get("verification_result_hash"),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
