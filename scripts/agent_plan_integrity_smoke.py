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


def http_json(base_url: str, path: str, body: dict, headers: dict | None = None) -> tuple[int, dict]:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = Request(
        base_url.rstrip("/") + path,
        data=raw,
        headers=req_headers,
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

    approval_plan = run([
        "agent-plan",
        "create",
        "--agent-id",
        agent_id,
        "--task-id",
        task_id,
        "--task-understanding",
        "Create an approval-required plan that must not run before human approval.",
        "--referenced-specs",
        "PROJECT_SPEC.md,AGENT_WORKFLOW.md",
        "--referenced-memories",
        str(candidate_memory_id),
        "--referenced-bases",
        "base_local_tasks",
        "--proposed-files-to-change",
        "server.py",
        "--risk",
        "high",
        "--execution-steps",
        "READ,PLAN,RETRIEVE,COMPARE,VERIFY",
        "--verification-plan",
        "High-risk work must be approved before run_start.",
        "--rollback-plan",
        "Reject plan and keep task planned if approval is not granted.",
    ], args.base_url, agent_id)
    outputs.extend([approval_plan.stdout, approval_plan.stderr])
    approval_plan_payload = load_json(approval_plan)
    approval_plan_record = approval_plan_payload.get("agent_plan") or {}
    approval_plan_id = approval_plan_record.get("plan_id")
    pending_plan_approval = approval_plan_payload.get("approval") or {}
    require(approval_plan.returncode == 0 and bool(approval_plan_id), f"approval-required plan create failed: {approval_plan.stderr or approval_plan.stdout}", failures)
    require(approval_plan_record.get("approval_required") in {1, True}, f"approval_required missing: {approval_plan_payload}", failures)
    require(bool(approval_plan_record.get("approval_id")), f"approval_id missing on high-risk plan: {approval_plan_payload}", failures)
    require(pending_plan_approval.get("approval_id") == approval_plan_record.get("approval_id"), f"pending approval not linked to plan: {approval_plan_payload}", failures)
    require(pending_plan_approval.get("decision") == "pending", f"plan approval should start pending: {approval_plan_payload}", failures)

    approval_verify = run(["agent-plan", "verify", "--plan-id", str(approval_plan_id)], args.base_url, agent_id)
    outputs.extend([approval_verify.stdout, approval_verify.stderr])
    approval_verify_payload = load_json(approval_verify)
    require(approval_verify.returncode == 0, f"approval-required plan verify failed: {approval_verify.stderr or approval_verify.stdout}", failures)
    require((approval_verify_payload.get("verification") or {}).get("pass") is True, f"approval-required plan should verify before approval: {approval_verify_payload}", failures)

    preapproval_run_status, preapproval_run_payload = http_json(args.base_url, "/api/agent-gateway/runs/start", {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "task_id": task_id,
        "runtime_type": "mock",
        "input_summary": "This run_start must be blocked until the plan is approved.",
        "agent_plan_id": approval_plan_id,
    })
    outputs.append(json.dumps(preapproval_run_payload, ensure_ascii=False))
    require(preapproval_run_status == 428, f"approval-required run_start should be blocked: {preapproval_run_status} {preapproval_run_payload}", failures)
    require(preapproval_run_payload.get("error") == "agent_plan_approval_required", f"wrong preapproval run_start error: {preapproval_run_payload}", failures)

    token_status, token_payload = http_json(args.base_url, "/api/agent-gateway/enrollment/create", {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "name": f"Plan Integrity Token {stamp}",
        "runtime_type": "mock",
        "scopes": ["agent_plans:read", "agent_plans:write"],
        "ttl_days": 1,
    })
    token = token_payload.get("token")
    require(token_status == 201 and isinstance(token, str) and token.startswith("agtok_"), f"agent token create failed: {token_status} {token_payload}", failures)

    bound_approval_status, bound_approval_payload = http_json(
        args.base_url,
        f"/api/agent-plans/{approval_plan_id}/approve",
        {"workspace_id": "local-demo", "approver_user_id": "usr_founder", "reason": "Agent token must not approve this plan."},
        headers={
            "Authorization": f"Bearer {token}",
            "X-AgentOps-Agent-Id": agent_id,
            "X-AgentOps-Workspace-Id": "local-demo",
        },
    )
    outputs.append(json.dumps(bound_approval_payload, ensure_ascii=False))
    require(bound_approval_status == 403, f"bound agent token should not approve plan: {bound_approval_status} {bound_approval_payload}", failures)
    require(bound_approval_payload.get("error") == "agent_plan_human_approval_required", f"wrong bound approval error: {bound_approval_payload}", failures)

    human_approval_status, human_approval_payload = http_json(args.base_url, f"/api/approvals/{approval_plan_record.get('approval_id')}/approve", {})
    outputs.append(json.dumps(human_approval_payload, ensure_ascii=False))
    approved_transition_plan = human_approval_payload.get("agent_plan") or {}
    approval_object = human_approval_payload.get("approval") or {}
    require(human_approval_status == 200, f"human plan approval failed: {human_approval_status} {human_approval_payload}", failures)
    require(approved_transition_plan.get("status") == "approved", f"plan not approved: {human_approval_payload}", failures)
    require(approved_transition_plan.get("approved_by_user_id") == "usr_founder", f"approver not recorded: {human_approval_payload}", failures)
    require(approval_object.get("decision") == "approved" and approval_object.get("approval_id"), f"approval object missing: {human_approval_payload}", failures)

    postapproval_run_status, postapproval_run_payload = http_json(args.base_url, "/api/agent-gateway/runs/start", {
        "workspace_id": "local-demo",
        "agent_id": agent_id,
        "task_id": task_id,
        "runtime_type": "mock",
        "input_summary": "This run_start should pass after the plan is approved.",
        "agent_plan_id": approval_plan_id,
    })
    outputs.append(json.dumps(postapproval_run_payload, ensure_ascii=False))
    require(postapproval_run_status == 201, f"approved plan run_start should pass: {postapproval_run_status} {postapproval_run_payload}", failures)
    require(((postapproval_run_payload.get("agent_plan") or {}).get("plan_id") == approval_plan_id), f"run_start did not bind approved plan: {postapproval_run_payload}", failures)

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
        "approval_required_run_blocked": preapproval_run_status == 428,
        "bound_agent_approval_rejected": bound_approval_status == 403,
        "human_plan_approved": human_approval_status == 200,
        "approved_plan_run_started": postapproval_run_status == 201,
        "approval_id": approval_object.get("approval_id"),
        "plan_hash": plan_hash,
        "verification_result_hash": verified_plan.get("verification_result_hash"),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
