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

    memory_status, memory_payload = http_json(args.base_url, "/api/agent-gateway/memories/propose", {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "task_id": task_id,
        "canonical_text": "Candidate memory must not authorize execution until approved.",
        "memory_type": "risk",
        "source_type": "run_log",
        "source_ref": f"agent_plan_integrity:{stamp}",
        "confidence": 0.81,
    })
    outputs.append(json.dumps(memory_payload, ensure_ascii=False))
    candidate_memory_id = (memory_payload.get("memory") or {}).get("memory_id")
    require(memory_status in {200, 201}, f"memory propose failed: {memory_status} {memory_payload}", failures)
    require(bool(candidate_memory_id), f"candidate memory id missing: {memory_payload}", failures)
    require((memory_payload.get("memory") or {}).get("review_status") == "candidate", f"memory should start as candidate: {memory_payload}", failures)

    candidate_plan = run([
        "agent-plan",
        "create",
        "--agent-id",
        agent_id,
        "--task-id",
        task_id,
        "--task-understanding",
        "Create a plan that incorrectly treats candidate memory as authority.",
        "--referenced-specs",
        "PROJECT_SPEC.md,AGENT_WORKFLOW.md",
        "--referenced-memories",
        str(candidate_memory_id),
        "--referenced-bases",
        "base_local_tasks",
        "--proposed-files-to-change",
        "server.py",
        "--risk",
        "medium",
        "--execution-steps",
        "READ,PLAN,RETRIEVE,VERIFY",
        "--verification-plan",
        "Candidate memory must fail authority verification.",
        "--rollback-plan",
        "Approve the memory or use knowledge context instead.",
    ], args.base_url, agent_id)
    outputs.extend([candidate_plan.stdout, candidate_plan.stderr])
    candidate_plan_payload = load_json(candidate_plan)
    candidate_plan_id = (candidate_plan_payload.get("agent_plan") or {}).get("plan_id")
    require(candidate_plan.returncode == 0, f"candidate-memory plan create failed unexpectedly: {candidate_plan.stderr or candidate_plan.stdout}", failures)
    require(bool(candidate_plan_id), f"candidate-memory plan id missing: {candidate_plan_payload}", failures)

    candidate_verify = run(["agent-plan", "verify", "--plan-id", str(candidate_plan_id)], args.base_url, agent_id)
    outputs.extend([candidate_verify.stdout, candidate_verify.stderr])
    candidate_verify_payload = load_json(candidate_verify)
    candidate_verification = candidate_verify_payload.get("verification") or {}
    failed_ids = {check.get("id") for check in candidate_verification.get("failed_checks") or []}
    candidate_summary = candidate_verification.get("summary") or {}
    require(candidate_verify.returncode == 0, f"candidate-memory plan verify command failed: {candidate_verify.stderr or candidate_verify.stdout}", failures)
    require(candidate_verification.get("pass") is False, f"candidate memory should not verify as authority: {candidate_verify_payload}", failures)
    require("memory_authority" in failed_ids, f"memory_authority check should fail for candidate memory: {candidate_verify_payload}", failures)
    require(int(candidate_summary.get("non_authoritative_memory_refs") or 0) >= 1, f"non-authoritative memory count missing: {candidate_summary}", failures)

    approved_status, approved_memory = http_json(args.base_url, f"/api/memories/{candidate_memory_id}/approve", {})
    outputs.append(json.dumps(approved_memory, ensure_ascii=False))
    require(approved_status == 200, f"memory approve failed: {approved_status} {approved_memory}", failures)
    require(approved_memory.get("review_status") == "approved", f"memory not approved: {approved_memory}", failures)

    approved_plan = run([
        "agent-plan",
        "create",
        "--agent-id",
        agent_id,
        "--task-id",
        task_id,
        "--task-understanding",
        "Create a plan that references an approved memory authority.",
        "--referenced-specs",
        "PROJECT_SPEC.md,AGENT_WORKFLOW.md",
        "--referenced-memories",
        str(candidate_memory_id),
        "--referenced-bases",
        "base_local_tasks",
        "--proposed-files-to-change",
        "server.py",
        "--risk",
        "medium",
        "--execution-steps",
        "READ,PLAN,RETRIEVE,VERIFY",
        "--verification-plan",
        "Approved memory should pass authority verification.",
        "--rollback-plan",
        "Reopen memory review if evidence is stale.",
    ], args.base_url, agent_id)
    outputs.extend([approved_plan.stdout, approved_plan.stderr])
    approved_plan_payload = load_json(approved_plan)
    approved_plan_id = (approved_plan_payload.get("agent_plan") or {}).get("plan_id")
    require(approved_plan.returncode == 0, f"approved-memory plan create failed: {approved_plan.stderr or approved_plan.stdout}", failures)
    require(bool(approved_plan_id), f"approved-memory plan id missing: {approved_plan_payload}", failures)

    approved_verify = run(["agent-plan", "verify", "--plan-id", str(approved_plan_id)], args.base_url, agent_id)
    outputs.extend([approved_verify.stdout, approved_verify.stderr])
    approved_verify_payload = load_json(approved_verify)
    approved_verification = approved_verify_payload.get("verification") or {}
    approved_summary = approved_verification.get("summary") or {}
    require(approved_verify.returncode == 0, f"approved-memory plan verify failed: {approved_verify.stderr or approved_verify.stdout}", failures)
    require(approved_verification.get("pass") is True, f"approved memory should verify as authority: {approved_verify_payload}", failures)
    require(int(approved_summary.get("approved_memory_refs") or 0) >= 1, f"approved memory count missing: {approved_summary}", failures)

    negative_cases = [
        {
            "label": "missing_spec",
            "task_understanding": "Reference a missing spec to prove verifier blocks unreadable spec authority.",
            "referenced_specs": "docs/DOES_NOT_EXIST_AGENT_PLAN_SPEC.md",
            "referenced_bases": "base_local_tasks",
            "proposed_files": "server.py",
            "expected_failed_check": "read_specs",
        },
        {
            "label": "missing_base",
            "task_understanding": "Reference a missing base to prove verifier blocks unknown base authority.",
            "referenced_specs": "PROJECT_SPEC.md,AGENT_WORKFLOW.md",
            "referenced_bases": "base_missing_agent_plan_integrity",
            "proposed_files": "server.py",
            "expected_failed_check": "compare_bases",
        },
        {
            "label": "unsafe_file_scope",
            "task_understanding": "Reference an unsafe file path to prove verifier blocks path escape.",
            "referenced_specs": "PROJECT_SPEC.md,AGENT_WORKFLOW.md",
            "referenced_bases": "base_local_tasks",
            "proposed_files": "../outside-agentops.py",
            "expected_failed_check": "file_scope",
        },
    ]
    negative_results: dict[str, list[str]] = {}
    for case in negative_cases:
        bad_plan = run([
            "agent-plan",
            "create",
            "--agent-id",
            agent_id,
            "--task-id",
            task_id,
            "--task-understanding",
            case["task_understanding"],
            "--referenced-specs",
            case["referenced_specs"],
            "--referenced-memories",
            str(candidate_memory_id),
            "--referenced-bases",
            case["referenced_bases"],
            "--proposed-files-to-change",
            case["proposed_files"],
            "--risk",
            "medium",
            "--execution-steps",
            "READ,PLAN,VERIFY",
            "--verification-plan",
            f"{case['label']} must fail verification.",
            "--rollback-plan",
            "Fix references before execution.",
        ], args.base_url, agent_id)
        outputs.extend([bad_plan.stdout, bad_plan.stderr])
        bad_payload = load_json(bad_plan)
        bad_plan_id = (bad_payload.get("agent_plan") or {}).get("plan_id")
        require(bad_plan.returncode == 0 and bool(bad_plan_id), f"{case['label']} plan create failed unexpectedly: {bad_plan.stderr or bad_plan.stdout}", failures)
        bad_verify = run(["agent-plan", "verify", "--plan-id", str(bad_plan_id)], args.base_url, agent_id)
        outputs.extend([bad_verify.stdout, bad_verify.stderr])
        bad_verify_payload = load_json(bad_verify)
        bad_verification = bad_verify_payload.get("verification") or {}
        bad_failed_ids = {check.get("id") for check in bad_verification.get("failed_checks") or []}
        negative_results[case["label"]] = sorted(str(item) for item in bad_failed_ids)
        require(bad_verify.returncode == 0, f"{case['label']} verify command failed: {bad_verify.stderr or bad_verify.stdout}", failures)
        require(bad_verification.get("pass") is False, f"{case['label']} should fail verification: {bad_verify_payload}", failures)
        require(case["expected_failed_check"] in bad_failed_ids, f"{case['label']} missing {case['expected_failed_check']} failure: {bad_verify_payload}", failures)

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
        "candidate_memory_rejected": "memory_authority" in failed_ids,
        "approved_memory_verified": bool((approved_verify_payload.get("verification") or {}).get("pass")),
        "negative_reference_results": negative_results,
        "plan_hash": plan_hash,
        "verification_result_hash": verified_plan.get("verification_result_hash"),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
