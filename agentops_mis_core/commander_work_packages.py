"""Pure Commander work-package read-model helpers."""
from __future__ import annotations

from typing import Any


def commander_work_package_status(task: dict[str, Any], latest_run: dict[str, Any] | None, evidence: dict[str, Any]) -> str:
    if task.get("status") in {"failed", "blocked", "canceled"}:
        return "blocked"
    if task.get("status") in {"running", "waiting_approval"}:
        return "still_running"
    if task.get("status") == "completed":
        return "ready_for_review" if (evidence.get("evaluations") or evidence.get("artifacts") or evidence.get("tool_calls")) else "needs_evidence"
    if latest_run and latest_run.get("status") in {"failed", "blocked"}:
        return "blocked"
    return "planned"


def commander_work_package_next_action(item: dict[str, Any]) -> str:
    status = item.get("package_status")
    if status == "planned":
        return f"agentops commander dispatch-package --task-id {item.get('task_id')} --adapter mock"
    if status == "still_running":
        latest_run = item.get("latest_run") or {}
        run_id = latest_run.get("run_id")
        return f"agentops run get --run-id {run_id}" if run_id else "agentops commander inbox --bucket still_running"
    if status == "ready_for_review":
        return f"agentops task get --task-id {item.get('task_id')}"
    if status == "blocked":
        return "agentops commander inbox --bucket blocked --limit 5"
    return "agentops commander board"


def filter_commander_work_packages(packages: list[dict[str, Any]], status_filter: str) -> list[dict[str, Any]]:
    if not status_filter or status_filter == "all":
        return packages
    return [
        item
        for item in packages
        if item.get("package_status") == status_filter or item.get("status") == status_filter
    ]


def summarize_commander_work_packages(
    packages: list[dict[str, Any]],
    *,
    localization_artifact_type: str,
    coding_evidence_artifact_types: list[str],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    project_counts: dict[str, int] = {}
    for item in packages:
        status_key = item.get("package_status") or "unknown"
        counts[status_key] = counts.get(status_key, 0) + 1
        project_key = item.get("project_id") or "unknown"
        project_counts[project_key] = project_counts.get(project_key, 0) + 1

    localization_recorded = sum(
        1
        for item in packages
        if ((item.get("localization_gate") or {}).get("status") == "recorded")
    )
    coding_recorded = sum(
        1
        for item in packages
        if ((item.get("coding_evidence_gate") or {}).get("status") == "recorded")
    )
    coding_partial = sum(
        1
        for item in packages
        if ((item.get("coding_evidence_gate") or {}).get("status") == "partial")
    )
    total = len(packages)
    return {
        "total": total,
        "by_status": counts,
        "by_project": project_counts,
        "localization": {
            "artifact_type": localization_artifact_type,
            "recorded": localization_recorded,
            "missing": max(total - localization_recorded, 0),
            "coverage_percent": round((localization_recorded / total) * 100, 1) if packages else 100.0,
            "raw_content_omitted": True,
            "snippets_omitted": True,
            "token_omitted": True,
        },
        "coding_evidence": {
            "artifact_types": coding_evidence_artifact_types,
            "recorded": coding_recorded,
            "partial": coding_partial,
            "missing": max(total - coding_recorded - coding_partial, 0),
            "coverage_percent": round((coding_recorded / total) * 100, 1) if packages else 100.0,
            "raw_source_omitted": True,
            "raw_patch_omitted": True,
            "token_omitted": True,
        },
    }


def commander_work_package_next_actions(packages: list[dict[str, Any]]) -> list[str]:
    next_actions: list[str] = []
    for item in packages:
        action = item.get("recommended_action")
        if action and action not in next_actions:
            next_actions.append(action)
    if not next_actions:
        next_actions = ["agentops commander plan --goal \"Describe the customer project\" --confirm-create"]
    return next_actions[:8]


def build_commander_work_packages_readback(
    *,
    packages: list[dict[str, Any]],
    workspace_id: str,
    project_id: str | None,
    plan_id: str | None,
    status_filter: str,
    limit: int,
    localization_artifact_type: str,
    coding_evidence_artifact_types: list[str],
) -> dict[str, Any]:
    filtered_packages = filter_commander_work_packages(packages, status_filter)
    return {
        "provider": "agentops-commander",
        "operation": "work_packages_readback",
        "status": "ready" if filtered_packages else "empty",
        "workspace_id": workspace_id,
        "filter": {
            "project_id": project_id or None,
            "plan_id": plan_id or None,
            "status": status_filter,
            "limit": limit,
        },
        "summary": summarize_commander_work_packages(
            filtered_packages,
            localization_artifact_type=localization_artifact_type,
            coding_evidence_artifact_types=coding_evidence_artifact_types,
        ),
        "work_packages": filtered_packages,
        "recommended_next_actions": commander_work_package_next_actions(filtered_packages),
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "task_created": False,
            "run_created": False,
            "live_execution_performed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }
