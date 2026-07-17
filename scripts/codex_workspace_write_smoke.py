#!/usr/bin/env python3
"""Deterministic acceptance for governed Codex workspace-write and execution leases."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_cli import codex_runtime, worker
from agentops_mis_core.approval_wall import prepared_action_hash, prepared_action_resume_gate_error


ALLOWED_PATH = "result.txt"
OUTSIDE_PATH = "outside.txt"
SECRET_PATH = "new-secret.txt"
SECRET = "sk" + "-fixture-do-not-leak-123456789"
UNTRACKED_SECRET_MARKER = "github" + "_pat_fixture-do-not-leak"


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def run(command: list[str], cwd: Path, *, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)


def git(repo: Path, *args: str) -> str:
    proc = run(["git", *args], repo)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return proc.stdout.strip()


def init_repo(repo: Path) -> str:
    repo.mkdir()
    git(repo, "init", "--quiet")
    git(repo, "config", "user.name", "AgentOps Smoke")
    git(repo, "config", "user.email", "agentops-smoke@example.invalid")
    (repo / ALLOWED_PATH).write_text("baseline\n", encoding="utf-8")
    git(repo, "add", ALLOWED_PATH)
    git(repo, "commit", "--quiet", "-m", "baseline")
    return git(repo, "rev-parse", "HEAD")


def write_fake_codex(path: Path, mode: str) -> None:
    source = f'''#!/usr/bin/env python3
import json
import sys
from pathlib import Path

MODE = {mode!r}
if "--version" in sys.argv:
    print("codex-cli fixture")
    raise SystemExit(0)
cwd = Path(sys.argv[sys.argv.index("-C") + 1])
_prompt = sys.stdin.read()
if MODE != "read-only":
    content = "x" * ({codex_runtime.MAX_WORKSPACE_WRITE_BYTES} + 1) if MODE == "oversized" else "bounded fixture output\\n"
    (cwd / {ALLOWED_PATH!r}).write_text(content, encoding="utf-8")
if MODE == "outside":
    (cwd / {OUTSIDE_PATH!r}).write_text("outside scope\\n", encoding="utf-8")
if MODE == "untracked-secret":
    (cwd / {SECRET_PATH!r}).write_text({UNTRACKED_SECRET_MARKER!r}, encoding="utf-8")
events = [
    {{"type": "thread.started", "thread_id": "thr_fixture"}},
    {{"type": "turn.started"}},
]
if MODE != "read-only":
    events.append({{"type": "item.completed", "item": {{"id": "fc_1", "type": "file_change"}}}})
events.extend([
    {{"type": "item.completed", "item": {{"id": "msg_1", "type": "agent_message", "text": "fixture complete {SECRET}"}}}},
    {{"type": "turn.completed", "usage": {{"output_tokens": 8}}}},
])
for index, event in enumerate(events):
    if MODE == "invalid" and index == 2:
        print("not-json")
    print(json.dumps(event, separators=(",", ":")))
'''
    path.write_text(source, encoding="utf-8")
    path.chmod(0o700)


def safe_result_json(result) -> str:
    return json.dumps({
        "ok": result.ok,
        "output_summary": result.output_summary,
        "error_type": result.error_type,
        "error_message": result.error_message,
        "target_resource": result.target_resource,
        "observation": result.observation,
    }, ensure_ascii=False, sort_keys=True)


def runtime_contract_smoke(failures: list[str]) -> dict:
    verified: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="agentops-codex-write-") as temp_raw:
        temp = Path(temp_raw)
        repo = temp / "repo"
        head = init_repo(repo)
        worktrees = temp / "worktrees"
        binaries = {}
        for mode in ("read-only", "success", "outside", "invalid", "oversized", "untracked-secret"):
            binary = temp / f"codex-{mode}"
            write_fake_codex(binary, mode)
            binaries[mode] = binary

        defaults = worker.build_parser().parse_args(["--adapter", "codex"])
        verified["read_only_default"] = defaults.codex_mode == "read-only" and not defaults.confirm_workspace_write
        require(verified["read_only_default"], "Codex worker no longer defaults to read-only", failures)

        read_only = codex_runtime.execute_codex_read_only(
            binary_path=str(binaries["read-only"]),
            prompt=f"read-only fixture {SECRET}",
            cwd=repo,
            timeout=10,
        )
        verified["read_only_runtime"] = bool(read_only.ok and (read_only.observation or {}).get("sandbox") == "read-only")
        require(verified["read_only_runtime"], f"read-only runtime failed: {read_only.error_type}", failures)
        require(not git(repo, "status", "--porcelain"), "read-only runtime changed source repository", failures)

        unattested = codex_runtime.execute_codex_workspace_write(
            binary_path=str(binaries["success"]), prompt="fixture", source_repo=repo,
            action_id="pa_unattested", baseline_head=head, allowed_paths=[ALLOWED_PATH], timeout=10,
            worktree_root=worktrees,
        )
        verified["unattested_binary_rejected"] = unattested.error_type == "CodexWorkspaceWriteRuntimeUnattested"
        require(verified["unattested_binary_rejected"], "arbitrary binary received write authority", failures)

        success = codex_runtime.execute_codex_workspace_write(
            binary_path=str(binaries["success"]), prompt=f"fixture {SECRET}", source_repo=repo,
            action_id="pa_success", baseline_head=head, allowed_paths=[ALLOWED_PATH], timeout=10,
            worktree_root=worktrees, allow_test_fixture=True,
        )
        diff = (success.observation or {}).get("diff_evidence") or {}
        verified["bounded_write"] = bool(
            success.ok
            and diff.get("changed_paths") == [ALLOWED_PATH]
            and diff.get("git_diff_check_pass") is True
            and diff.get("secret_scan_pass") is True
            and (success.observation or {}).get("product_readiness_proof") is False
        )
        require(verified["bounded_write"], f"bounded write failed: {safe_result_json(success)}", failures)
        success_worktree = codex_runtime.managed_codex_worktree_path("pa_success", worktrees)
        require(success_worktree.is_dir(), "successful managed worktree was not retained", failures)
        verified["explicit_rollback"] = codex_runtime.remove_managed_codex_worktree(source_repo=repo, worktree=success_worktree)
        require(verified["explicit_rollback"], "successful managed worktree could not be rolled back", failures)

        outside = codex_runtime.execute_codex_workspace_write(
            binary_path=str(binaries["outside"]), prompt="fixture", source_repo=repo,
            action_id="pa_outside", baseline_head=head, allowed_paths=[ALLOWED_PATH], timeout=10,
            worktree_root=worktrees, allow_test_fixture=True,
        )
        verified["scope_fail_closed"] = bool(
            not outside.ok
            and outside.error_type == "CodexWorkspaceWriteRejected"
            and (outside.observation or {}).get("rollback_performed") is True
        )
        require(verified["scope_fail_closed"], f"out-of-scope write did not fail closed: {safe_result_json(outside)}", failures)

        invalid = codex_runtime.execute_codex_workspace_write(
            binary_path=str(binaries["invalid"]), prompt="fixture", source_repo=repo,
            action_id="pa_invalid", baseline_head=head, allowed_paths=[ALLOWED_PATH], timeout=10,
            worktree_root=worktrees, allow_test_fixture=True,
        )
        verified["protocol_fail_closed"] = bool(
            not invalid.ok
            and invalid.error_type == "CodexWorkspaceWriteRejected"
            and (invalid.observation or {}).get("rollback_performed") is True
        )
        require(verified["protocol_fail_closed"], f"invalid protocol did not fail closed: {safe_result_json(invalid)}", failures)

        oversized = codex_runtime.execute_codex_workspace_write(
            binary_path=str(binaries["oversized"]), prompt="fixture", source_repo=repo,
            action_id="pa_oversized", baseline_head=head, allowed_paths=[ALLOWED_PATH], timeout=10,
            worktree_root=worktrees, allow_test_fixture=True,
        )
        verified["oversized_diff_fail_closed"] = bool(
            not oversized.ok
            and oversized.error_type == "CodexWorkspaceWriteRejected"
            and (oversized.observation or {}).get("rollback_performed") is True
        )
        require(verified["oversized_diff_fail_closed"], f"oversized diff did not fail closed: {safe_result_json(oversized)}", failures)

        untracked_secret = codex_runtime.execute_codex_workspace_write(
            binary_path=str(binaries["untracked-secret"]), prompt="fixture", source_repo=repo,
            action_id="pa_untracked_secret", baseline_head=head, allowed_paths=[ALLOWED_PATH, SECRET_PATH], timeout=10,
            worktree_root=worktrees, allow_test_fixture=True,
        )
        verified["untracked_secret_fail_closed"] = bool(
            not untracked_secret.ok
            and untracked_secret.error_type == "CodexWorkspaceWriteRejected"
            and (untracked_secret.observation or {}).get("rollback_performed") is True
        )
        require(verified["untracked_secret_fail_closed"], f"untracked secret did not fail closed: {safe_result_json(untracked_secret)}", failures)

        dirty_path = repo / "dirty.txt"
        dirty_path.write_text("dirty\n", encoding="utf-8")
        dirty = codex_runtime.execute_codex_workspace_write(
            binary_path=str(binaries["success"]), prompt="fixture", source_repo=repo,
            action_id="pa_dirty", baseline_head=head, allowed_paths=[ALLOWED_PATH], timeout=10,
            worktree_root=worktrees, allow_test_fixture=True,
        )
        verified["dirty_preflight"] = bool(not dirty.ok and not codex_runtime.managed_codex_worktree_path("pa_dirty", worktrees).exists())
        require(verified["dirty_preflight"], "dirty source repository reached Codex execution", failures)
        dirty_path.unlink()

        evidence = "\n".join(safe_result_json(item) for item in (read_only, unattested, success, outside, invalid, oversized, untracked_secret, dirty))
        verified["secrets_omitted"] = SECRET not in evidence
        require(verified["secrets_omitted"], "runtime evidence leaked fixture secret", failures)
        require(not git(repo, "status", "--porcelain"), "source repository was mutated by managed worktrees", failures)
    return verified


def approval_expiry_contract_smoke(failures: list[str]) -> dict:
    action = {
        "action_id": "pa_expired_fixture",
        "action_type": "agent_worker.codex.workspace_write",
        "normalized_args_json": "{}",
        "target_resource": "git+local://fixture",
        "risk_level": "high",
        "policy_version": "approval-wall-codex-workspace-write-v2",
        "checkpoint_json": "{}",
        "idempotency_key": "expiry-fixture",
        "expires_at": "2000-01-01T00:00:00+00:00",
        "status": "approved",
        "consumed_at": None,
        "approval_id": "ap_expired_fixture",
    }
    first_hash = prepared_action_hash(action)
    changed_expiry = {**action, "expires_at": "2000-01-02T00:00:00+00:00"}
    gate = prepared_action_resume_gate_error(
        action_id=action["action_id"],
        row={**action, "action_hash": first_hash},
        approval={"decision": "approved", "expires_at": "2000-01-01T00:00:00+00:00"},
        expected_args={},
        expected_action_type=action["action_type"],
        comparable_fields=(),
        missing_error="prepared_action_required",
        missing_message="fixture",
        approval_message="fixture",
    )
    verified = {
        "expiry_bound_to_hash": first_hash != prepared_action_hash(changed_expiry),
        "expired_action_blocked": bool(gate and gate.get("error") == "prepared_action_expired"),
    }
    for key, passed in verified.items():
        require(passed, f"prepared-action expiry check failed: {key}", failures)
    return verified


def http_json(base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(base_url.rstrip("/") + path, data=raw, headers={"Content-Type": "application/json"}, method="POST" if payload is not None else "GET")
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def execution_lease_smoke(base_url: str, failures: list[str]) -> dict:
    stamp = str(time.time_ns())
    agent_id = f"agt_codex_lease_{stamp}"
    task_id = f"tsk_codex_lease_{stamp}"
    status, _ = http_json(base_url, "/api/agent-gateway/register", {
        "workspace_id": "local-demo", "agent_id": agent_id, "name": "Lease Smoke", "role": "Worker", "runtime_type": "codex",
    })
    require(status in {200, 201}, f"lease agent registration failed: {status}", failures)
    status, _ = http_json(base_url, "/api/tasks", {
        "task_id": task_id, "workspace_id": "local-demo", "title": "Lease smoke", "description": "CAS lease",
        "owner_agent_id": agent_id, "risk_level": "high", "acceptance_criteria": "one execution lease",
    })
    require(status in {200, 201}, f"lease task creation failed: {status}", failures)
    status, plan_payload = http_json(base_url, "/api/agent-gateway/agent-plans", {
        "workspace_id": "local-demo", "agent_id": agent_id, "task_id": task_id,
        "task_understanding": "Verify one governed workspace-write execution lease and evidence closure.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": [ALLOWED_PATH],
        "risk_level": "medium", "approval_required": False,
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "verification_plan": "Require exact lease and hash-bound manifest evidence.",
        "rollback_plan": "Fail the lease and discard the isolated worktree.",
    })
    plan_id = (plan_payload.get("agent_plan") or {}).get("plan_id")
    require(status == 201 and plan_id, f"lease agent plan failed: {status} {plan_payload}", failures)
    status, run_payload = http_json(base_url, "/api/mock-runs/start", {"task_id": task_id, "agent_id": agent_id})
    run_id = (run_payload.get("run") or {}).get("run_id") or run_payload.get("run_id")
    require(status == 201 and run_id, f"lease run start failed: {status} {run_payload}", failures)
    status, tool_payload = http_json(base_url, "/api/agent-gateway/tool-calls", {
        "workspace_id": "local-demo", "run_id": run_id, "agent_id": agent_id,
        "tool_name": "agent_worker.codex.workspace_write", "tool_category": "custom", "risk_level": "high",
        "status": "waiting_approval", "target_resource": "git+local://sha256/fixture@head",
        "args": {"task_id": task_id, "agent_plan_id": plan_id, "execution_mode": "workspace-write", "allowed_paths": [ALLOWED_PATH]},
        "prepare_action": True, "action_type": "agent_worker.codex.workspace_write",
        "checkpoint": {"task_id": task_id, "run_id": run_id}, "idempotency_key": f"lease-{stamp}",
    })
    wall = tool_payload.get("approval_wall") or {}
    action_id = (wall.get("prepared_action") or {}).get("action_id")
    approval_id = (wall.get("approval") or {}).get("approval_id")
    require(status in {200, 201} and action_id and approval_id, f"lease prepared action failed: {status} {tool_payload}", failures)
    approve = run([str(ROOT / "scripts" / "agentops"), "--base-url", base_url, "--api-key", "", "approval", "approve", "--approval-id", approval_id], ROOT)
    require(approve.returncode == 0, f"lease approval failed: {approve.stderr}", failures)
    first_status, first = http_json(base_url, f"/api/agent-gateway/prepared-actions/{action_id}/claim-execution", {
        "workspace_id": "local-demo", "agent_id": agent_id, "lease_ttl_seconds": 60,
    })
    lease_id = (first.get("execution_lease") or {}).get("lease_id")
    second_status, second = http_json(base_url, f"/api/agent-gateway/prepared-actions/{action_id}/claim-execution", {
        "workspace_id": "local-demo", "agent_id": agent_id,
    })
    no_lease_status, _ = http_json(base_url, f"/api/agent-gateway/prepared-actions/{action_id}/resume", {
        "workspace_id": "local-demo", "agent_id": agent_id, "provider_side_effect_id": "fixture-no-lease",
    })
    no_manifest_status, no_manifest = http_json(base_url, f"/api/agent-gateway/prepared-actions/{action_id}/resume", {
        "workspace_id": "local-demo", "agent_id": agent_id, "lease_id": lease_id,
        "provider_side_effect_id": "fixture-no-manifest",
    })
    status, generic_tool = http_json(base_url, "/api/agent-gateway/tool-calls", {
        "workspace_id": "local-demo", "run_id": run_id, "agent_id": agent_id,
        "tool_name": "fixture.generic.completed", "tool_category": "custom",
        "risk_level": "low", "status": "completed", "target_resource": "fixture://generic",
        "args": {"task_id": task_id}, "result_summary": "Generic evidence must not verify workspace-write.",
    })
    generic_tool_id = (generic_tool.get("tool_call") or {}).get("tool_call_id")
    require(status == 201 and generic_tool_id, f"generic tool setup failed: {status} {generic_tool}", failures)
    status, forged_manifest = http_json(base_url, "/api/agent-gateway/plan-evidence-manifests", {
        "workspace_id": "local-demo", "agent_id": agent_id, "plan_id": plan_id, "run_id": run_id,
        "mismatch_policy": "block",
        "expected_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "tool_call_ids": [generic_tool_id],
    })
    forged_failed_ids = {
        item.get("id") for item in ((forged_manifest.get("verification") or {}).get("failed_checks") or [])
    }
    forged_manifest_blocked = bool(
        status == 201
        and (forged_manifest.get("verification") or {}).get("pass") is False
        and "workspace_write_verifier_unique" in forged_failed_ids
        and "workspace_write_lease_bound" in forged_failed_ids
    )
    require(forged_manifest_blocked, f"generic manifest bypassed workspace-write gates: {status} {forged_manifest}", failures)
    evidence_hash = "a" * 64
    status, verification_tool = http_json(base_url, "/api/agent-gateway/tool-calls", {
        "workspace_id": "local-demo", "run_id": run_id, "agent_id": agent_id,
        "tool_name": "agent_worker.codex.workspace_diff_verify", "tool_category": "custom",
        "risk_level": "medium", "status": "completed", "target_resource": "worktree://fixture/diff-evidence",
        "args": {
            "task_id": task_id, "agent_plan_id": plan_id, "prepared_action_id": action_id,
            "execution_lease_id": lease_id, "diff_evidence_hash": evidence_hash,
            "changed_paths": [ALLOWED_PATH], "allowed_paths": [ALLOWED_PATH],
            "head_unchanged": True, "raw_diff_omitted": True, "raw_content_omitted": True,
        },
        "result_summary": "Fixture diff verification completed; raw diff omitted.",
    })
    verification_tool_id = (verification_tool.get("tool_call") or {}).get("tool_call_id")
    require(status == 201 and verification_tool_id, f"lease verification tool failed: {status} {verification_tool}", failures)
    status, evaluation = http_json(base_url, "/api/agent-gateway/evaluations/submit", {
        "workspace_id": "local-demo", "run_id": run_id, "task_id": task_id, "agent_id": agent_id,
        "evaluator_type": "rule", "score": 1.0, "pass_fail": "pass",
        "rubric": {"diff_evidence_hash": evidence_hash, "quality_gate_pass": True},
        "notes": "Fixture evidence hash binding.",
    })
    evaluation_id = (evaluation.get("evaluation") or {}).get("evaluation_id")
    require(status == 201 and evaluation_id, f"lease evaluation failed: {status} {evaluation}", failures)
    status, artifact = http_json(base_url, "/api/agent-gateway/artifacts", {
        "workspace_id": "local-demo", "run_id": run_id, "task_id": task_id, "agent_id": agent_id,
        "artifact_type": "codex_workspace_diff_evidence", "title": "Fixture workspace diff",
        "uri": "worktree://fixture", "summary": "Hash-only fixture evidence.", "content_hash": evidence_hash,
    })
    artifact_id = (artifact.get("artifact") or {}).get("artifact_id")
    require(status == 201 and artifact_id, f"lease artifact failed: {status} {artifact}", failures)
    status, audit = http_json(base_url, "/api/agent-gateway/audit", {
        "workspace_id": "local-demo", "agent_id": agent_id, "action": "fixture.codex_workspace_write_completed",
        "entity_type": "runs", "entity_id": run_id, "task_id": task_id, "run_id": run_id,
        "metadata": {"execution_lease_id": lease_id, "diff_evidence": {"evidence_hash": evidence_hash}},
    })
    audit_id = audit.get("audit_id")
    require(status == 201 and audit_id, f"lease audit failed: {status} {audit}", failures)
    status, manifest = http_json(base_url, "/api/agent-gateway/plan-evidence-manifests", {
        "workspace_id": "local-demo", "agent_id": agent_id, "plan_id": plan_id, "run_id": run_id,
        "mismatch_policy": "block",
        "expected_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "tool_call_ids": [verification_tool_id], "evaluation_ids": [evaluation_id],
        "artifact_ids": [artifact_id], "audit_ids": [audit_id],
    })
    manifest_id = (manifest.get("manifest") or {}).get("manifest_id")
    manifest_pass = (manifest.get("verification") or {}).get("pass") is True
    require(status == 201 and manifest_id and manifest_pass, f"lease manifest failed: {status} {manifest}", failures)
    resume_status, resumed = http_json(base_url, f"/api/agent-gateway/prepared-actions/{action_id}/resume", {
        "workspace_id": "local-demo", "agent_id": agent_id, "lease_id": lease_id,
        "plan_evidence_manifest_id": manifest_id, "provider_side_effect_id": f"fixture-diff-{stamp}",
        "result_summary": "fixture lease consumed", "output_summary": "fixture closure complete",
    })
    stale_run_status, stale_run_payload = http_json(base_url, "/api/mock-runs/start", {"task_id": task_id, "agent_id": agent_id})
    stale_run_id = (stale_run_payload.get("run") or {}).get("run_id") or stale_run_payload.get("run_id")
    require(stale_run_status == 201 and stale_run_id, f"stale lease run failed: {stale_run_status} {stale_run_payload}", failures)
    stale_status, stale_tool = http_json(base_url, "/api/agent-gateway/tool-calls", {
        "workspace_id": "local-demo", "run_id": stale_run_id, "agent_id": agent_id,
        "tool_name": "agent_worker.codex.workspace_write", "tool_category": "custom", "risk_level": "high",
        "status": "waiting_approval", "target_resource": "git+local://sha256/fixture@stale",
        "args": {"task_id": task_id, "agent_plan_id": plan_id, "execution_mode": "workspace-write", "allowed_paths": [ALLOWED_PATH]},
        "prepare_action": True, "action_type": "agent_worker.codex.workspace_write",
        "checkpoint": {"task_id": task_id, "run_id": stale_run_id}, "idempotency_key": f"stale-{stamp}",
    })
    stale_wall = stale_tool.get("approval_wall") or {}
    stale_action_id = (stale_wall.get("prepared_action") or {}).get("action_id")
    stale_approval_id = (stale_wall.get("approval") or {}).get("approval_id")
    require(stale_status in {200, 201} and stale_action_id and stale_approval_id, f"stale lease setup failed: {stale_status} {stale_tool}", failures)
    stale_approve = run([str(ROOT / "scripts" / "agentops"), "--base-url", base_url, "--api-key", "", "approval", "approve", "--approval-id", stale_approval_id], ROOT)
    require(stale_approve.returncode == 0, f"stale lease approval failed: {stale_approve.stderr}", failures)
    stale_claim_status, stale_claim = http_json(base_url, f"/api/agent-gateway/prepared-actions/{stale_action_id}/claim-execution", {
        "workspace_id": "local-demo", "agent_id": agent_id, "lease_ttl_seconds": 1,
    })
    stale_lease_id = (stale_claim.get("execution_lease") or {}).get("lease_id")
    require(stale_claim_status == 201 and stale_lease_id, f"stale lease claim failed: {stale_claim_status} {stale_claim}", failures)
    stale_hash = "b" * 64
    status, stale_verify_tool = http_json(base_url, "/api/agent-gateway/tool-calls", {
        "workspace_id": "local-demo", "run_id": stale_run_id, "agent_id": agent_id,
        "tool_name": "agent_worker.codex.workspace_diff_verify", "tool_category": "custom",
        "risk_level": "medium", "status": "completed", "target_resource": "worktree://stale/diff-evidence",
        "args": {"task_id": task_id, "agent_plan_id": plan_id, "prepared_action_id": stale_action_id,
                 "execution_lease_id": stale_lease_id, "diff_evidence_hash": stale_hash,
                 "changed_paths": [ALLOWED_PATH], "allowed_paths": [ALLOWED_PATH], "head_unchanged": True},
    })
    stale_verify_tool_id = (stale_verify_tool.get("tool_call") or {}).get("tool_call_id")
    status, stale_evaluation = http_json(base_url, "/api/agent-gateway/evaluations/submit", {
        "workspace_id": "local-demo", "run_id": stale_run_id, "task_id": task_id, "agent_id": agent_id,
        "evaluator_type": "rule", "score": 1.0, "pass_fail": "pass",
        "rubric": {"diff_evidence_hash": stale_hash, "quality_gate_pass": True},
    })
    stale_evaluation_id = (stale_evaluation.get("evaluation") or {}).get("evaluation_id")
    status, stale_artifact = http_json(base_url, "/api/agent-gateway/artifacts", {
        "workspace_id": "local-demo", "run_id": stale_run_id, "task_id": task_id, "agent_id": agent_id,
        "artifact_type": "codex_workspace_diff_evidence", "title": "Expired lease fixture",
        "uri": "worktree://stale", "summary": "Hash-only stale fixture.", "content_hash": stale_hash,
    })
    stale_artifact_id = (stale_artifact.get("artifact") or {}).get("artifact_id")
    status, stale_audit = http_json(base_url, "/api/agent-gateway/audit", {
        "workspace_id": "local-demo", "agent_id": agent_id, "action": "fixture.stale_workspace_write",
        "entity_type": "runs", "entity_id": stale_run_id, "task_id": task_id, "run_id": stale_run_id,
        "metadata": {"execution_lease_id": stale_lease_id, "diff_evidence": {"evidence_hash": stale_hash}},
    })
    stale_audit_id = stale_audit.get("audit_id")
    status, stale_manifest = http_json(base_url, "/api/agent-gateway/plan-evidence-manifests", {
        "workspace_id": "local-demo", "agent_id": agent_id, "plan_id": plan_id, "run_id": stale_run_id,
        "mismatch_policy": "block",
        "expected_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "tool_call_ids": [stale_verify_tool_id], "evaluation_ids": [stale_evaluation_id],
        "artifact_ids": [stale_artifact_id], "audit_ids": [stale_audit_id],
    })
    stale_manifest_id = (stale_manifest.get("manifest") or {}).get("manifest_id")
    require((stale_manifest.get("verification") or {}).get("pass") is True, f"stale manifest setup failed: {stale_manifest}", failures)
    time.sleep(1.1)
    expired_resume_status, expired_resume = http_json(base_url, f"/api/agent-gateway/prepared-actions/{stale_action_id}/resume", {
        "workspace_id": "local-demo", "agent_id": agent_id, "lease_id": stale_lease_id,
        "plan_evidence_manifest_id": stale_manifest_id, "provider_side_effect_id": "must-not-consume",
    })
    manifest_readback_status, manifest_readback = http_json(base_url, f"/api/agent-gateway/plan-evidence-manifests/{manifest_id}/verify")
    verified = {
        "first_claim": first_status == 201 and bool(lease_id),
        "second_claim_blocked": second_status == 409 and second.get("error") == "prepared_action_execution_already_claimed",
        "resume_requires_lease": no_lease_status == 428,
        "resume_requires_verified_manifest": no_manifest_status == 428 and no_manifest.get("error") == "verified_plan_evidence_manifest_required",
        "forged_manifest_blocked": forged_manifest_blocked,
        "manifest_verified": bool(manifest_pass),
        "lease_completed": resume_status == 200 and (resumed.get("execution_lease") or {}).get("status") == "completed",
        "run_completed_in_resume": resume_status == 200 and resumed.get("run_completed_in_resume") is True,
        "expired_lease_resume_failed_closed": expired_resume_status == 409 and expired_resume.get("error") == "prepared_action_execution_lease_expired" and expired_resume.get("retry_requires_new_prepared_action") is True,
        "manifest_readback_stable": manifest_readback_status == 200 and (manifest_readback.get("verification") or {}).get("pass") is True,
    }
    for key, passed in verified.items():
        require(passed, f"execution lease check failed: {key}", failures)
    return verified


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    failures: list[str] = []
    runtime_verified = runtime_contract_smoke(failures)
    expiry_verified = approval_expiry_contract_smoke(failures)
    lease_verified = execution_lease_smoke(args.base_url, failures)
    output = {
        "ok": not failures,
        "operation": "codex_workspace_write_smoke",
        "runtime_verified": runtime_verified,
        "approval_expiry_verified": expiry_verified,
        "execution_lease_verified": lease_verified,
        "failures": failures,
        "product_readiness_proof": False,
        "fixture_only": True,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "raw_diff_omitted": True,
        "token_omitted": True,
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    if SECRET in rendered:
        raise AssertionError("smoke output leaked fixture secret")
    print(rendered)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
