#!/usr/bin/env python3
"""Verify the AI Employees UI exposes the scoped Commander team board."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AI_EMPLOYEES = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "AIEmployees.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def extract_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start)
    if end < 0:
        return text[start:]
    return text[start:end]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    ai = AI_EMPLOYEES.read_text(encoding="utf-8")
    live_api = LIVE_API.read_text(encoding="utf-8")

    board_block = extract_block(ai, 'data-testid="commander-team-board"', "{commanderWorkPackages && (")
    project_loader = extract_block(live_api, "export async function loadCommanderProjectBoard", "export interface CommanderWorkPackageDispatchPayload")

    expected_ai_markers = {
        "scoped_board_payload_type": "CommanderProjectBoardPayload",
        "scoped_board_loader": "loadCommanderProjectBoard",
        "active_project_state": "activeCommanderProject",
        "board_test_id": 'data-testid="commander-team-board"',
        "project_scoped_copy_en": "Project-scoped lanes",
        "project_scoped_copy_zh": "按当前项目展示 lanes",
        "team_board_summary": "commanderTeamBoard.summary.total_lanes",
        "workflow_active_count": "commanderTeamBoard.summary.active_workflow_jobs",
        "workflow_failed_count": "commanderTeamBoard.summary.failed_workflow_jobs",
        "workflow_completed_count": "commanderTeamBoard.summary.workflow_job_counts.completed",
        "lane_latest_job": "lane.latest_workflow_job",
        "job_result_run_link": "lane.latest_workflow_job.result_run_id",
        "job_result_artifact": "lane.latest_workflow_job.result_artifact_id",
        "team_board_dispatch_button": 'data-testid="commander-team-board-dispatch-batch"',
        "team_board_queue_readback": "commanderLastQueueBoard",
        "batch_dispatch_result_state": "lastCommanderBatch",
        "batch_after_queue_active": "commanderLastQueueBoard.summary.active_workflow_jobs",
        "batch_jobs_created": "lastCommanderBatch?.safety.jobs_created",
        "team_board_mark_failed_button": 'data-testid="commander-team-board-mark-job-failed"',
        "team_board_retry_button": 'data-testid="commander-team-board-retry-job"',
        "team_board_mark_failed_handler": "markStuckWorkflowJobFailed(lane.latest_workflow_job.job_id)",
        "team_board_retry_handler": "retryCommanderWorkflowJob(lane.task_id",
        "team_board_retry_live_confirm": "liveAdapterConfirmMissing((lane.latest_workflow_job?.adapter || \"mock\")",
        "team_board_recovery_receipt_writer": "recordWorkflowJobRecoveryReceipt",
        "team_board_recovery_receipt_source": "ui.commander_team_board.workflow_job_recovery",
        "team_board_recovery_receipt_api": "recordOperatorActionReceipt({",
        "team_board_recovery_receipt_refresh": 'refreshPanel("operator_action_receipts")',
        "team_board_mark_failed_receipt_command": "agentops workflow job-mark-failed --job-id",
        "team_board_retry_receipt_command": "agentops commander dispatch-batch --task-id",
        "team_board_retry_verify_command": "agentops workflow job-status --job-id",
        "fallback_action_rows": "commanderActionRows",
        "scoped_refresh": "refresh({ commanderProject: nextProject })",
    }
    for label, marker in expected_ai_markers.items():
        require(marker in ai, f"AIEmployees missing {label}: {marker}", failures)

    expected_api_markers = {
        "project_board_endpoint": "/commander/project-board",
        "team_board_filter": "team_board_filter",
        "workflow_job_counts_type": "workflow_job_counts: Record<string, number>;",
        "active_job_ids_type": "active_workflow_job_task_ids: string[];",
        "failed_job_ids_type": "failed_workflow_job_task_ids: string[];",
        "latest_workflow_job_parse": "latestWorkflowJob",
        "batch_dispatch_endpoint": "/commander/work-packages/dispatch-batch",
        "batch_after_queue_type": "team_board_after_queue?: CommanderTeamBoardPayload | null;",
        "batch_after_queue_parse": "team_board_after_queue: parseCommanderTeamBoardPayload(raw.team_board_after_queue",
        "team_board_reusable_parser": "function parseCommanderTeamBoardPayload",
        "project_board_shared_parser": "team_board: parseCommanderTeamBoardPayload(raw.team_board",
        "read_only_safety": "read_only: boolValue(teamSafetyRaw.read_only)",
        "live_execution_false_fallback": "live_execution_performed: false",
    }
    for label, marker in expected_api_markers.items():
        require(marker in live_api, f"liveApi missing {label}: {marker}", failures)

    require(bool(board_block), "commander team board UI block missing", failures)
    require("commanderTeamBoard.lanes.slice(0, 8)" in board_block, "team board should render scoped lanes, not only global package rows", failures)
    require("latestWorkflowJob" in board_block, "team board should surface latest workflow job status", failures)
    require("result_artifact_id" in board_block, "team board should surface workflow delivery artifact evidence", failures)
    require("dispatchCommanderPlannedBatch()" in board_block, "team board should expose a batch dispatch control", failures)
    require("commanderLastQueueBoard" in board_block, "team board should render after-queue readback evidence", failures)
    require("commander-team-board-mark-job-failed" in board_block, "team board should expose active job mark-failed recovery", failures)
    require("commander-team-board-retry-job" in board_block, "team board should expose failed job retry recovery", failures)
    require("dispatchCommanderWorkPackageBatch" in ai and "status: \"all\"" in ai, "failed job retry should requeue the exact task through audited batch dispatch", failures)
    require("recordWorkflowJobRecoveryReceipt" in ai and "recordOperatorActionReceipt" in ai, "team board recovery should append operator action receipts", failures)
    require("operator_action_receipts" in ai and "operator_action_plan" in ai, "team board recovery should refresh receipt/action-plan panels", failures)
    require("loadCommanderProjectBoard({ project_id: nextProject.projectId" in ai, "confirmed planner create should reload scoped project board", failures)
    require("loadCommanderWorkPackages({ project_id: nextProject.projectId" in ai, "confirmed planner create should reload scoped work packages", failures)
    require("team_board: null" in project_loader, "project board fallback should be safe/null when unavailable", failures)
    require("live_execution_performed: false" in project_loader, "project board loader fallback should not claim live execution", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(f"{ai}\n{live_api}")]
    require(not secret_hits, f"secret-like marker found in UI/API source: {secret_hits}", failures)

    output = {
        "ok": not failures,
        "operation": "commander_team_board_ui_smoke",
        "files": [str(AI_EMPLOYEES.relative_to(ROOT)), str(LIVE_API.relative_to(ROOT))],
        "contract": "AI Employees renders the scoped Commander team board with workflow-job evidence instead of relying only on global recent package rows.",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
