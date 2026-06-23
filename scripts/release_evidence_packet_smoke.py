#!/usr/bin/env python3
"""Verify the release evidence packet can report RC SHA, CI status and tests."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "docs" / "V1_5_MERGE_READINESS_CHECKLIST.md"
PACKET_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9_]+"),
]

TEST_COMMANDS = [
    {
        "id": "syntax_diff",
        "command": "python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py && git diff --check",
        "summary": "Python syntax, CLI/script importability and whitespace diff hygiene.",
        "ci_step": "Syntax and diff checks",
    },
    {
        "id": "release_branch_control",
        "command": "python3 scripts/release_branch_control_smoke.py",
        "summary": "Branch identity, reviewable history, unsafe tracked runtime files and upstream drift.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "release_freeze_protocol",
        "command": "python3 scripts/release_freeze_protocol_smoke.py",
        "summary": "Hardening freeze protocol, CI-backed release gates and remote required-check evidence.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "clean_machine_rc",
        "command": "python3 scripts/clean_machine_rc_smoke.py",
        "summary": "Temporary clean clone RC chain covering installable CLIs, reset server, safe closure and delivery-board evidence.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "release_evidence_packet",
        "command": "python3 scripts/release_evidence_packet_smoke.py",
        "summary": "Runtime RC SHA, CI link/status, canonical test list and release-packet boundaries.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "merge_readiness_status",
        "command": "python3 scripts/merge_readiness_status_smoke.py",
        "summary": "Checklist state consistency, explicit blockers and strict READY_TO_MERGE guard.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "v1_5_product_closure_evidence",
        "command": "python3 scripts/v1_5_product_closure_evidence_smoke.py",
        "summary": "Static CI coverage matrix for v1.5 closure items; not live product-readiness proof.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "customer_worker_real_runtime_acceptance",
        "command": "python3 scripts/customer_worker_real_runtime_acceptance.py --confirm-live --adapter hermes --adapter openclaw",
        "summary": "Manual live product-readiness dogfood gate for real Hermes/OpenClaw customer-worker execution; intentionally excluded from CI.",
        "ci_step": "manual-live-local",
        "manual_only": True,
    },
    {
        "id": "v1_5_live_product_readiness",
        "command": "python3 scripts/v1_5_live_product_readiness_smoke.py --require-adapter hermes --require-adapter openclaw",
        "summary": "Read-only manual live ledger proof that fresh Hermes/OpenClaw customer-worker runs have full run/tool/eval/runtime/audit/artifact/memory/approval/plan-evidence coverage.",
        "ci_step": "manual-live-local",
        "manual_only": True,
    },
    {
        "id": "customer_worker_hermes_retry_gateway",
        "command": "python3 scripts/customer_worker_hermes_retry_gateway_smoke.py",
        "summary": "Deterministic loopback Hermes-compatible gateway smoke proving customer-worker retry metadata is wired through the real adapter path; not live product-readiness proof.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "module_boundary",
        "command": "python3 scripts/module_boundary_smoke.py",
        "summary": "P1-05 strangler boundary gate for extracted runtime capability, connector registry/refresh projection, trust state, read-model cache, Approval Wall resume/waiting/route blocked/access/prepare-response/prepared-action-decision/high-risk-toolcall-required/risky-tool-registry/external-side-effect-intent/resume-success/provider-result gates, Agent Plan approval-decision/create-status/bound-approval/transition-error/run-start gate/rebind/success response projections, run-start binding comparison plus contract/hash/path-scope/verification-result/pending-approval/approval-run helpers, Agent Gateway run-heartbeat update projection, worker fleet remote/session/hygiene projections, workflow-job public/list/stuck/recovery response projections, Commander and Operator command-center aggregation helpers, Operator evidence-report memory/status/summary projection, Operator start-check gate/local-run-path/launch-brief/loop-driver-entry projections, Operator loop-control summary/gate projection, and Operator receipt/evaluation/control-readback public projection.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "read_model_cache",
        "command": "python3 scripts/read_model_cache_smoke.py",
        "summary": "Read-model cache scoped keying, hit/miss/bypass behavior, ledger read-only proof and token omission.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "open_source_adoption_boundary",
        "command": "python3 scripts/open_source_adoption_boundary_smoke.py",
        "summary": "Static gate proving open-source references cannot replace first-party MIS authority objects.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "external_connector_runtime_inventory",
        "command": "python3 scripts/external_connector_runtime_inventory_smoke.py",
        "summary": "High-risk external connector/runtime prepared-action inventory and guard coverage.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "sqlite_concurrency",
        "command": "python3 scripts/sqlite_concurrency_smoke.py",
        "summary": "SQLite pragma, concurrent read/write and long-subprocess transaction safety gate.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "secret_scan",
        "command": "python3 scripts/secret_scan_smoke.py",
        "summary": "Tracked files remain free of real credentials and token-like material.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "license_provenance",
        "command": "python3 scripts/license_provenance_smoke.py",
        "summary": "License, third-party notices, SBOM and Pixel Office asset boundary.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "public_claims",
        "command": "python3 scripts/public_claims_release_gate_smoke.py",
        "summary": "Public claims stay aligned with tested local-MVP / NOT_READY behavior.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "migration_rollback",
        "command": "python3 scripts/migration_rollback_smoke.py",
        "summary": "SQLite migration preview, backup, restore and rollback evidence.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "retrieval_quality",
        "command": "python3 scripts/knowledge_retrieval_quality_smoke.py",
        "summary": "Bilingual knowledge retrieval quality baseline.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "commander_repo_map",
        "command": "python3 scripts/commander_repo_map_smoke.py",
        "summary": "Commander repo-map localization returns deterministic file/symbol candidates with provenance and redacted snippets.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "commander_coding_project_template",
        "command": "python3 scripts/commander_coding_project_template_smoke.py",
        "summary": "Commander local coding project template links WorkPackage, worktree, patch, verifier and merge-gate evidence without mutating the ledger.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "commander_coding_workspace",
        "command": "python3 scripts/commander_coding_workspace_smoke.py",
        "summary": "Commander coding workspace loop creates an isolated git worktree, collects patch/test/verifier evidence, records MIS artifacts and cleans branch/worktree residue.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "operator_command_center",
        "command": "python3 scripts/operator_command_center_smoke.py",
        "summary": "Unified operator command-center BFF covers projects, blockers, approvals, deliveries, stale workers, Commander coding gates, and prioritized next actions.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "commander_work_package_plan",
        "command": "python3 scripts/commander_work_package_plan_smoke.py",
        "summary": "Commander work-package planning creates task-bound repo-map localization artifacts without live execution.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "commander_work_package_dispatch",
        "command": "python3 scripts/commander_work_package_dispatch_smoke.py",
        "summary": "Commander targeted dispatch preserves/restores repo-map localization artifacts before worker execution.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "local_coding_project_template",
        "command": "python3 scripts/local_coding_project_template_smoke.py",
        "summary": "Server-backed Local Coding Project template creates Commander packages, previews coding workspace, dispatches mock worker, and records patch/test/verifier/merge evidence.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "responsiveness",
        "command": "python3 scripts/ai_employees_responsiveness_smoke.py",
        "summary": "Agent command-center API latency and fan-out budget.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "operator_action_queue_ui",
        "command": "python3 scripts/operator_action_queue_ui_smoke.py",
        "summary": "AI Employees operator queue, loop-control readback and live API UI contract.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "commander_team_board_ui",
        "command": "python3 scripts/commander_team_board_ui_smoke.py",
        "summary": "AI Employees renders the scoped Commander team board with workflow-job evidence and safe project-board readback.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "operator_advance_loop",
        "command": "python3 scripts/operator_advance_loop_smoke.py",
        "summary": "Bounded advance-loop runner records receipts plus persisted control readback evidence.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "operator_loop_control",
        "command": "python3 scripts/operator_loop_control_smoke.py",
        "summary": "Lightweight read-only loop-control API/CLI plus fast advance-loop readback for real local ledgers.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "operator_loop_driver",
        "command": "python3 scripts/operator_loop_driver_smoke.py",
        "summary": "Hermes/OpenClaw/Codex loop driver previews compact launch briefs and confirms bounded multi-step advance-loop receipts without live execution.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "operator_loop_launch_packet",
        "command": "python3 scripts/operator_loop_launch_packet_smoke.py",
        "summary": "Agent Work Method launch packet supports default lightweight loop-control and explicit full handoff modes without mutating ledgers.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "operator_evidence_report",
        "command": "python3 scripts/operator_evidence_report_smoke.py",
        "summary": "Run-level evidence report checks Agent Plan binding, approval, verified plan evidence, tool/eval/artifact/audit rows, memory review closure, raw memory omission and read-only DB stability.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "operator_live_product_readiness",
        "command": "python3 scripts/operator_live_product_readiness_smoke.py",
        "summary": "CLI product-readiness proof reads fresh Hermes/OpenClaw live ledger evidence and fails closed without calling runtimes.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "agentops_cli_connection_hint",
        "command": "python3 scripts/agentops_cli_connection_hint_smoke.py",
        "summary": "CLI stale-base-url failures explain whether the target came from flag/env/config/default and show the local demo repair command without leaking tokens.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "task_detail_evidence_ui",
        "command": "python3 scripts/task_detail_evidence_ui_smoke.py",
        "summary": "Task detail page exposes delivery evidence state, latest run and approval links.",
        "ci_step": "Offline safety smokes",
    },
    {
        "id": "security_readiness",
        "command": "python3 scripts/security_production_readiness_smoke.py --base-url \"$AGENTOPS_BASE_URL\"",
        "summary": "Server-backed security readiness gates.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "operator_runtime_doctor",
        "command": "python3 scripts/operator_runtime_doctor_smoke.py",
        "summary": "Server-backed local runtime doctor for MIS, Hermes, OpenClaw, Codex supervision, remote Agent fleet, confirm-run walls, prepared-action walls and copyable evidence commands without live execution or ledger mutation.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "operator_start_check_api",
        "command": "python3 scripts/operator_start_check_api_smoke.py",
        "summary": "Server-backed pre-task start-check API for mock/Hermes/OpenClaw that composes local readiness, worker policy, runtime doctor, launch brief, local run path and live-ledger proof without live execution or ledger mutation.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "operator_start_check_cli",
        "command": "python3 scripts/operator_start_check_smoke.py --base-url \"$AGENTOPS_BASE_URL\" --adapter hermes --adapter openclaw",
        "summary": "CLI/API parity smoke for the pre-task start-check command used before local Hermes/OpenClaw/Codex loop work.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "operator_execution_mode",
        "command": "python3 scripts/operator_execution_mode_smoke.py",
        "summary": "Server-backed execution-mode read model for UI/CLI/agents covering adapter route, confirm-run wall, prepared-action wall, approvals and async jobs without live execution or ledger mutation.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "runtime_capability_manifest",
        "command": "python3 scripts/runtime_capability_manifest_smoke.py --base-url \"$AGENTOPS_BASE_URL\"",
        "summary": "Runtime connector capability manifests cover Agent Gateway, OpenClaw, Hermes and Agnesfallback with confirmation/trust policy fields.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "enrollment_launch_steps",
        "command": "python3 scripts/enrollment_launch_steps_smoke.py --base-url \"$AGENTOPS_BASE_URL\"",
        "summary": "Enrollment create/rotate launch packets omit raw tokens and include installable worker, short-lived session, service-template/install/check and preview-first service-control commands.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "remote_launch_packet_worker",
        "command": "python3 scripts/remote_launch_packet_worker_smoke.py --base-url \"$AGENTOPS_BASE_URL\"",
        "summary": "Remote launch packet environment can mint a short-lived session, run a scoped worker, and write run/tool/evaluation ledger evidence without token leakage.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "worker_fleet_hygiene",
        "command": "python3 scripts/worker_fleet_hygiene_smoke.py --base-url \"$AGENTOPS_BASE_URL\"",
        "summary": "Worker fleet hygiene can plan/apply stuck-task release and stale-enrollment revocation without leaking token IDs.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "agent_gateway_knowledge_scope",
        "command": "python3 scripts/agent_gateway_knowledge_scope_smoke.py",
        "summary": "Agent Gateway scoped knowledge visibility, provenance and spoof-resistance gate.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "safe_closure_packet",
        "command": "python3 scripts/safe_closure_evidence_packet_smoke.py",
        "summary": "Safe-closure packet IDs, plan hash, reviews, manifests, artifacts and audit counts.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "protected_live_runtime_ids",
        "command": "python3 scripts/protected_live_runtime_ids_smoke.py",
        "summary": "Protected planned-task, connector, prepared-action and approval IDs without pre-approval live calls.",
        "ci_step": "Server-backed smoke suite",
    },
    {
        "id": "ui_build",
        "command": "cd ui/start-building-app && npm ci && npm run build",
        "summary": "Next.js UI build for the command center and Pixel Office surfaces.",
        "ci_step": "UI build",
    },
]


def run(args: list[str], *, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False)


def git_text(args: list[str]) -> str:
    proc = run(["git", *args])
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "git command failed").strip())
    return (proc.stdout or "").strip()


def maybe_git_text(args: list[str]) -> str | None:
    proc = run(["git", *args])
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def release_status(text: str) -> str:
    match = re.search(r"Current status:\s*`([^`]+)`", text)
    return match.group(1) if match else "UNKNOWN"


def status_entries() -> list[str]:
    raw = maybe_git_text(["status", "--porcelain"]) or ""
    return [line for line in raw.splitlines() if line.strip()]


def current_branch() -> str:
    return maybe_git_text(["branch", "--show-current"]) or os.environ.get("GITHUB_REF_NAME") or "DETACHED"


def upstream_sync() -> dict[str, int | None]:
    upstream = maybe_git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if not upstream:
        return {"ahead": None, "behind": None}
    counts = maybe_git_text(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
    if not counts:
        return {"ahead": None, "behind": None}
    behind_text, ahead_text = counts.split()
    return {"ahead": int(ahead_text), "behind": int(behind_text)}


def ci_from_env(head_sha: str) -> dict[str, Any] | None:
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return None
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    github_sha = os.environ.get("GITHUB_SHA", "")
    if not repo or not run_id:
        return None
    return {
        "source": "github_actions_env",
        "status": "in_progress",
        "conclusion": None,
        "url": f"{server_url.rstrip('/')}/{repo}/actions/runs/{run_id}",
        "head_sha": github_sha,
        "head_matches": github_sha == head_sha,
        "required_before_ready": True,
    }


def ci_from_gh(head_sha: str, branch: str) -> dict[str, Any]:
    gh = shutil.which("gh")
    if not gh:
        return {
            "source": "gh_unavailable",
            "status": "not_available",
            "conclusion": None,
            "url": None,
            "head_sha": None,
            "head_matches": False,
            "required_before_ready": True,
        }
    proc = run(
        [
            gh,
            "run",
            "list",
            "--branch",
            branch,
            "--limit",
            "20",
            "--json",
            "databaseId,status,conclusion,url,headSha,workflowName,createdAt,name",
        ],
        timeout=15,
    )
    if proc.returncode != 0:
        return {
            "source": "gh_error",
            "status": "not_available",
            "conclusion": None,
            "url": None,
            "head_sha": None,
            "head_matches": False,
            "required_before_ready": True,
            "error": redact(proc.stderr or proc.stdout),
        }
    try:
        runs = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return {
            "source": "gh_parse_error",
            "status": "not_available",
            "conclusion": None,
            "url": None,
            "head_sha": None,
            "head_matches": False,
            "required_before_ready": True,
        }
    exact = [item for item in runs if item.get("headSha") == head_sha]
    if not exact:
        return {
            "source": "gh_run_list",
            "status": "not_found_for_head",
            "conclusion": None,
            "url": None,
            "head_sha": None,
            "head_matches": False,
            "recent_runs_checked": len(runs),
            "required_before_ready": True,
        }
    selected = exact[0]
    conclusion = selected.get("conclusion") or None
    return {
        "source": "gh_run_list",
        "status": selected.get("status") or "unknown",
        "conclusion": conclusion,
        "url": selected.get("url"),
        "head_sha": selected.get("headSha"),
        "head_matches": True,
        "workflow": selected.get("workflowName") or selected.get("name"),
        "created_at": selected.get("createdAt"),
        "required_before_ready": conclusion != "success",
    }


def ci_status(head_sha: str, branch: str) -> dict[str, Any]:
    return ci_from_env(head_sha) or ci_from_gh(head_sha, branch)


def redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def command_script_paths(command: str) -> list[Path]:
    paths: list[Path] = []
    for match in re.finditer(r"scripts/[A-Za-z0-9_./-]+\.py", command):
        paths.append(ROOT / match.group(0))
    return paths


def validate_test_commands(ci_text: str, failures: list[str]) -> list[dict[str, Any]]:
    manifest: list[dict[str, Any]] = []
    for item in TEST_COMMANDS:
        command = item["command"]
        manual_only = bool(item.get("manual_only"))
        scripts = command_script_paths(command)
        for path in scripts:
            require(path.exists(), f"test command references missing script: {path.relative_to(ROOT)}", failures)
        if manual_only:
            pass
        elif scripts:
            for path in scripts:
                require(path.relative_to(ROOT).as_posix() in ci_text, f"CI workflow does not run {path.relative_to(ROOT)}", failures)
        elif "py_compile" in command:
            require("python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py" in ci_text, "CI workflow missing py_compile command", failures)
            require("git diff --check" in ci_text, "CI workflow missing git diff --check", failures)
        elif "npm run build" in command:
            require("npm run build" in ci_text and "ui/start-building-app" in ci_text, "CI workflow missing UI build command", failures)
        manifest.append(
            {
                "id": item["id"],
                "command": command,
                "summary": item["summary"],
                "ci_step": item["ci_step"],
                "ci_backed": not manual_only,
                "manual_only": manual_only,
            }
        )
    return manifest


def validate_docs(checklist: str, packet_doc: str, ci_text: str, failures: list[str]) -> None:
    require(PACKET_DOC.exists(), "missing docs/RELEASE_EVIDENCE_PACKET.md", failures)
    required_packet_phrases = [
        "Exact RC SHA",
        "git rev-parse HEAD",
        "CI links and status",
        "GitHub Actions",
        "Test command list and summary",
        "scripts/release_evidence_packet_smoke.py",
        "Never include raw credentials",
        "local MVP / NOT_READY",
    ]
    for phrase in required_packet_phrases:
        require(phrase in packet_doc, f"release evidence packet doc missing phrase: {phrase}", failures)
    for item in TEST_COMMANDS:
        canonical_command = str(item["command"]).replace('\\"', '"')
        require(canonical_command in packet_doc, f"release evidence packet doc missing canonical command: {canonical_command}", failures)

    checklist_requirements = [
        "- [x] Exact RC SHA.",
        "- [x] CI links and status.",
        "- [x] Test command list and summary.",
        "scripts/release_evidence_packet_smoke.py",
        "docs/RELEASE_EVIDENCE_PACKET.md",
    ]
    for phrase in checklist_requirements:
        require(phrase in checklist, f"merge readiness checklist missing release-packet closure phrase: {phrase}", failures)
    require("python3 scripts/release_evidence_packet_smoke.py" in ci_text, "CI workflow missing release evidence packet smoke", failures)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-clean", action="store_true", help="Fail on any local working-tree change.")
    parser.add_argument("--require-green-ci", action="store_true", help="Fail unless current HEAD has a successful CI run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    checklist = read(CHECKLIST) if CHECKLIST.exists() else ""
    packet_doc = read(PACKET_DOC) if PACKET_DOC.exists() else ""
    ci_text = read(CI_WORKFLOW) if CI_WORKFLOW.exists() else ""
    head_sha = git_text(["rev-parse", "HEAD"])
    branch = current_branch()
    status = status_entries()
    status_name = release_status(checklist)
    upstream = upstream_sync()
    ci = ci_status(head_sha, branch)
    tests = validate_test_commands(ci_text, failures)
    validate_docs(checklist, packet_doc, ci_text, failures)

    green_ci = ci.get("head_matches") is True and ci.get("status") == "completed" and ci.get("conclusion") == "success"
    require(status_name != "UNKNOWN", "merge readiness checklist missing current status", failures)
    if args.require_clean:
        require(not status, "working tree must be clean for final RC evidence", failures)
    if args.require_green_ci:
        require(green_ci, f"current HEAD does not have green CI evidence: {ci}", failures)
    if args.require_clean or args.require_green_ci:
        require(upstream.get("ahead") == 0 and upstream.get("behind") == 0, f"READY checklist requires upstream sync: {upstream}", failures)
    require(not (ci.get("head_matches") is False and ci.get("head_sha")), f"CI head does not match current HEAD: {ci}", failures)

    output = {
        "ok": not failures,
        "operation": "release_evidence_packet_smoke",
        "release_status": status_name,
        "rc_sha": {
            "source": "git rev-parse HEAD",
            "value": head_sha,
            "branch": branch,
            "upstream_sync": upstream,
            "working_tree_entries": len(status),
        },
        "ci": ci,
        "test_command_summary": {
            "total": len(tests),
            "ci_backed": sum(1 for item in tests if item.get("ci_backed")),
            "commands": tests,
        },
        "contracts": [
            "Exact SHA is captured at runtime, never hard-coded into a tracked stale packet.",
            "CI status may be queued, in-progress, failed or unavailable in CI-safe default mode.",
            "Final strict evidence requires --require-clean --require-green-ci with upstream sync and successful current-head CI.",
            "Evidence output omits raw credentials, private prompts, model responses, customer bodies, local databases and unsafe logs.",
        ],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(serialized)]
    if secret_hits:
        output["ok"] = False
        output["failures"].append(f"release evidence output leaked token-like material: {secret_hits}")
        serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    print(serialized)
    return 1 if output["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
