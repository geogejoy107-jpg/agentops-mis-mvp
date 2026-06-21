#!/usr/bin/env python3
"""Verify Agent Gateway run_start is bound to a verified Agent Plan."""

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
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
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
    req = Request(
        base_url.rstrip("/") + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-AgentOps-Workspace-Id": "local-demo"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}
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


def create_task(base_url: str, agent_id: str, task_id: str, title: str) -> dict:
    status, payload = http_json(base_url, "/api/tasks", {
        "task_id": task_id,
        "title": title,
        "description": "Verify run_start plan gate.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "medium",
        "risk_level": "low",
        "acceptance_criteria": "run_start must be bound to a verified agent plan.",
    })
    if status not in {200, 201}:
        raise RuntimeError(f"task create failed: {status} {payload}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify run_start Agent Plan gate.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    stamp = now_stamp()
    agent_id = f"agt_plan_gate_{stamp}"
    task_without_plan = f"tsk_plan_gate_missing_{stamp}"
    task_with_plan = f"tsk_plan_gate_ok_{stamp}"
    failures: list[str] = []
    outputs: list[str] = []

    register = run(["agent", "register", "--id", agent_id, "--name", f"Plan Gate {stamp}", "--role", "Builder", "--runtime", "mock"], args.base_url, agent_id)
    outputs.extend([register.stdout, register.stderr])
    require(register.returncode == 0, f"register failed: {register.stderr or register.stdout}", failures)
    create_task(args.base_url, agent_id, task_without_plan, "Missing plan gate task")
    create_task(args.base_url, agent_id, task_with_plan, "Verified plan gate task")

    missing_status, missing_payload = http_json(args.base_url, "/api/agent-gateway/runs/start", {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "task_id": task_without_plan,
        "runtime_type": "mock",
        "input_summary": "This run should be rejected because it has no plan.",
    })
    outputs.append(json.dumps(missing_payload, ensure_ascii=False))
    require(missing_status == 428, f"run_start without plan should fail: {missing_status} {missing_payload}", failures)
    require(missing_payload.get("error") == "agent_plan_required", f"wrong missing-plan error: {missing_payload}", failures)

    plan = run([
        "agent-plan",
        "create",
        "--agent-id",
        agent_id,
        "--task-id",
        task_with_plan,
        "--task-understanding",
        "Use a verified plan to authorize run_start.",
        "--referenced-specs",
        "PROJECT_SPEC.md,AGENT_WORKFLOW.md",
        "--referenced-memories",
        "knowledge/shared/common_failures.md",
        "--referenced-bases",
        "base_local_tasks",
        "--proposed-files-to-change",
        "server.py",
        "--risk",
        "low",
        "--execution-steps",
        "READ,PLAN,RETRIEVE,VERIFY",
        "--verification-plan",
        "Run run_start_plan_gate_smoke.py.",
        "--rollback-plan",
        "Keep task planned if run_start plan binding fails.",
    ], args.base_url, agent_id)
    outputs.extend([plan.stdout, plan.stderr])
    plan_payload = load_json(plan)
    plan_row = plan_payload.get("agent_plan") or {}
    plan_id = plan_row.get("plan_id")
    plan_hash = plan_row.get("plan_hash")
    require(plan.returncode == 0 and bool(plan_id), f"plan create failed: {plan.stderr or plan.stdout}", failures)

    verify = run(["agent-plan", "verify", "--plan-id", str(plan_id)], args.base_url, agent_id)
    outputs.extend([verify.stdout, verify.stderr])
    verify_payload = load_json(verify)
    require(verify.returncode == 0, f"plan verify failed: {verify.stderr or verify.stdout}", failures)
    require((verify_payload.get("verification") or {}).get("pass") is True, f"plan did not verify: {verify_payload}", failures)

    started = run([
        "run",
        "start",
        "--task-id",
        task_with_plan,
        "--agent-id",
        agent_id,
        "--plan-id",
        str(plan_id),
        "--input-summary",
        "Plan-bound run_start smoke.",
    ], args.base_url, agent_id)
    outputs.extend([started.stdout, started.stderr])
    started_payload = load_json(started)
    run_row = started_payload.get("run") or {}
    bound = started_payload.get("agent_plan") or {}
    require(started.returncode == 0, f"plan-bound run start failed: {started.stderr or started.stdout}", failures)
    require(run_row.get("agent_plan_id") == plan_id, f"run missing agent_plan_id: {started_payload}", failures)
    require(run_row.get("plan_hash") == plan_hash, f"run plan_hash mismatch: {started_payload}", failures)
    require(bound.get("plan_id") == plan_id and bound.get("verification_pass") is True, f"response missing plan binding: {started_payload}", failures)
    require(not leaked("\n".join(outputs)), "run_start plan gate leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "agent_id": agent_id,
        "missing_plan_rejected": missing_status == 428,
        "plan_id": plan_id,
        "run_id": run_row.get("run_id"),
        "plan_hash": plan_hash,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
