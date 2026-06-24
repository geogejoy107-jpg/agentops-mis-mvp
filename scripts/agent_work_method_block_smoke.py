#!/usr/bin/env python3
"""Verify Agent Work Method knowledge search and agent-plan CLI/API loop."""
from __future__ import annotations

import argparse
import datetime as dt
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


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def run(args: list[str], base_url: str, agent_id: str = "", timeout: int = 90) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    if agent_id:
        env["AGENTOPS_AGENT_ID"] = agent_id
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
    parser = argparse.ArgumentParser(description="Verify Agent Work Method Block.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    stamp = now_stamp()
    agent_id = f"agt_work_method_{stamp}"
    task_id = f"tsk_work_method_{stamp}"
    failures: list[str] = []
    outputs: list[str] = []

    index = run(["knowledge", "index", "--rebuild"], args.base_url, agent_id)
    outputs.extend([index.stdout, index.stderr])
    index_payload = load_json(index)
    require(index.returncode == 0, f"knowledge index failed: {index.stderr or index.stdout}", failures)
    require(index_payload.get("operation") == "knowledge_index", f"wrong index payload: {index_payload}", failures)
    require(index_payload.get("indexed", 0) >= 5, f"too few indexed docs: {index_payload}", failures)
    require(index_payload.get("token_omitted") is True, f"knowledge index token omission missing: {index_payload}", failures)

    search = run(["knowledge", "search", "READ PLAN RETRIEVE", "--refresh", "--limit", "20"], args.base_url, agent_id)
    outputs.extend([search.stdout, search.stderr])
    search_payload = load_json(search)
    search_index = search_payload.get("index") or {}
    require(search.returncode == 0, f"knowledge search failed: {search.stderr or search.stdout}", failures)
    require(search_payload.get("operation") == "knowledge_search", f"wrong search payload: {search_payload}", failures)
    require(search_index.get("read_only") is True, f"Gateway knowledge search should be read-only: {search_payload}", failures)
    require(search_index.get("refresh_performed") is False, f"knowledge:read must not refresh index: {search_payload}", failures)
    require(search_index.get("refresh_skipped_reason") == "knowledge_read_is_non_mutating", f"missing refresh skip reason: {search_payload}", failures)
    paths = {row.get("path") for row in search_payload.get("results") or []}
    require("AGENT_WORKFLOW.md" in paths or "docs/AGENT_WORK_METHOD_BLOCK.md" in paths, f"workflow docs missing from search: {paths}", failures)

    register = run(["agent", "register", "--id", agent_id, "--name", f"Work Method {stamp}", "--role", "Builder", "--runtime", "codex"], args.base_url, agent_id)
    outputs.extend([register.stdout, register.stderr])
    require(register.returncode == 0, f"agent register failed: {register.stderr or register.stdout}", failures)

    task = run([
        "task",
        "create",
        "--task-id",
        task_id,
        "--title",
        "Agent Work Method Block smoke task",
        "--description",
        "Verify that an agent can search knowledge and submit an agent plan before execution.",
        "--owner-agent-id",
        agent_id,
        "--requester-id",
        "usr_founder",
        "--acceptance",
        "Agent plan must reference specs, memories, bases, files, verification and rollback.",
        "--risk",
        "medium",
    ], args.base_url, agent_id)
    outputs.extend([task.stdout, task.stderr])
    require(task.returncode == 0, f"task create failed: {task.stderr or task.stdout}", failures)

    plan = run([
        "agent-plan",
        "create",
        "--agent-id",
        agent_id,
        "--task-id",
        task_id,
        "--task-understanding",
        "Search the local knowledge base, compare base constraints, then execute only after a recorded plan.",
        "--referenced-specs",
        "PROJECT_SPEC.md,AGENT_WORKFLOW.md,BASE_INDEX.md",
        "--referenced-memories",
        "knowledge/shared/common_failures.md",
        "--referenced-bases",
        "base_local_memory,base_local_tasks",
        "--proposed-files-to-change",
        "server.py,agentops_mis_cli/agentops.py",
        "--risk",
        "medium",
        "--execution-steps",
        "READ,PLAN,RETRIEVE,COMPARE,EXECUTE,VERIFY,RECORD",
        "--verification-plan",
        "Run this smoke script and inspect CLI JSON outputs.",
        "--rollback-plan",
        "Remove agent plan routes and knowledge index tables before release if verification fails.",
    ], args.base_url, agent_id)
    outputs.extend([plan.stdout, plan.stderr])
    plan_payload = load_json(plan)
    plan_id = (plan_payload.get("agent_plan") or {}).get("plan_id")
    require(plan.returncode == 0, f"agent plan create failed: {plan.stderr or plan.stdout}", failures)
    require(bool(plan_id), f"missing plan id: {plan_payload}", failures)
    require((plan_payload.get("agent_plan") or {}).get("task_id") == task_id, f"plan task mismatch: {plan_payload}", failures)

    listed = run(["agent-plan", "list", "--task-id", task_id, "--limit", "10"], args.base_url, agent_id)
    outputs.extend([listed.stdout, listed.stderr])
    listed_payload = load_json(listed)
    listed_ids = {row.get("plan_id") for row in listed_payload.get("agent_plans") or []}
    require(listed.returncode == 0, f"agent plan list failed: {listed.stderr or listed.stdout}", failures)
    require(plan_id in listed_ids, f"plan missing from list: {listed_payload}", failures)

    got = run(["agent-plan", "get", "--plan-id", str(plan_id)], args.base_url, agent_id)
    outputs.extend([got.stdout, got.stderr])
    got_payload = load_json(got)
    require(got.returncode == 0, f"agent plan get failed: {got.stderr or got.stdout}", failures)
    require((got_payload.get("agent_plan") or {}).get("plan_id") == plan_id, f"wrong plan get payload: {got_payload}", failures)

    verified = run(["agent-plan", "verify", "--plan-id", str(plan_id)], args.base_url, agent_id)
    outputs.extend([verified.stdout, verified.stderr])
    verified_payload = load_json(verified)
    verification = verified_payload.get("verification") or {}
    require(verified.returncode == 0, f"agent plan verify failed: {verified.stderr or verified.stdout}", failures)
    require(verified_payload.get("operation") == "agent_plan_verify", f"wrong verify payload: {verified_payload}", failures)
    require(verification.get("pass") is True, f"agent plan verification did not pass: {verified_payload}", failures)
    require(not leaked("\n".join(outputs)), "Agent Work Method output leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "indexed": index_payload.get("indexed"),
        "knowledge_results": search_payload.get("count"),
        "task_id": task_id,
        "agent_id": agent_id,
        "plan_id": plan_id,
        "plan_verified": verification.get("pass") is True,
        "secret_leaked": False,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
