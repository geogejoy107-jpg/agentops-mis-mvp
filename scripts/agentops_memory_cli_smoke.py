#!/usr/bin/env python3
"""Smoke test memory list/approve/reject CLI commands."""

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
        timeout=120,
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


def propose_memory(base_url: str, agent_id: str, text: str) -> dict:
    proc = run([
        "memory",
        "propose",
        "--agent-id",
        agent_id,
        "--scope",
        "project",
        "--type",
        "artifact_summary",
        "--text",
        text,
        "--source-ref",
        f"memory_cli_smoke_{uuid.uuid4().hex[:8]}",
        "--access-tags",
        "memory-cli-smoke,review",
        "--confidence",
        "0.81",
    ], base_url)
    payload = load_json(proc)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return payload


def main() -> int:
    base_url = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
    suffix = uuid.uuid4().hex[:8]
    agent_id = f"agt_memory_cli_{suffix}"
    failures: list[str] = []
    outputs: list[str] = []

    register = run(["agent", "register", "--id", agent_id, "--name", f"Memory CLI {suffix}", "--role", "Memory CLI Smoke"], base_url)
    outputs.extend([register.stdout, register.stderr])
    require(register.returncode == 0, f"agent register failed: {register.stderr or register.stdout}", failures)

    first = propose_memory(base_url, agent_id, f"Memory CLI smoke approve candidate {suffix}.")
    second = propose_memory(base_url, agent_id, f"Memory CLI smoke reject candidate {suffix}.")
    outputs.extend([json.dumps(first), json.dumps(second)])
    first_memory = (first.get("memory") or {}).get("memory_id") or first.get("memory_id")
    second_memory = (second.get("memory") or {}).get("memory_id") or second.get("memory_id")
    require(bool(first_memory and second_memory), f"missing memory ids: {first} {second}", failures)

    listed = run(["memory", "list", "--status", "candidate", "--agent-id", agent_id, "--limit", "10"], base_url)
    listed_payload = load_json(listed)
    outputs.extend([listed.stdout, listed.stderr])
    listed_ids = [row.get("memory_id") for row in listed_payload.get("memories") or []]
    require(listed.returncode == 0, f"memory list failed: {listed.stderr or listed.stdout}", failures)
    require(listed_payload.get("operation") == "memory_list", f"wrong list operation: {listed_payload}", failures)
    require(first_memory in listed_ids, f"first memory missing from candidate list: {first_memory}", failures)
    require(second_memory in listed_ids, f"second memory missing from candidate list: {second_memory}", failures)

    approved = run(["memory", "approve", "--memory-id", first_memory], base_url)
    approved_payload = load_json(approved)
    outputs.extend([approved.stdout, approved.stderr])
    require(approved.returncode == 0, f"memory approve failed: {approved.stderr or approved.stdout}", failures)
    require(approved_payload.get("operation") == "memory_approve", f"wrong approve operation: {approved_payload}", failures)
    require(approved_payload.get("review_status") == "approved", f"memory not approved: {approved_payload}", failures)

    rejected = run(["memory", "reject", "--memory-id", second_memory], base_url)
    rejected_payload = load_json(rejected)
    outputs.extend([rejected.stdout, rejected.stderr])
    require(rejected.returncode == 0, f"memory reject failed: {rejected.stderr or rejected.stdout}", failures)
    require(rejected_payload.get("operation") == "memory_reject", f"wrong reject operation: {rejected_payload}", failures)
    require(rejected_payload.get("review_status") == "rejected", f"memory not rejected: {rejected_payload}", failures)

    approved_list = run(["memory", "list", "--status", "approved", "--agent-id", agent_id, "--limit", "10"], base_url)
    rejected_list = run(["memory", "list", "--status", "rejected", "--agent-id", agent_id, "--limit", "10"], base_url)
    outputs.extend([approved_list.stdout, rejected_list.stdout])
    approved_ids = [row.get("memory_id") for row in (load_json(approved_list).get("memories") or [])]
    rejected_ids = [row.get("memory_id") for row in (load_json(rejected_list).get("memories") or [])]
    require(first_memory in approved_ids, "approved memory missing from approved list", failures)
    require(second_memory in rejected_ids, "rejected memory missing from rejected list", failures)
    require(not secret_leaked("\n".join(outputs)), "memory CLI leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "agent_id": agent_id,
        "approved_memory_id": first_memory,
        "rejected_memory_id": second_memory,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
