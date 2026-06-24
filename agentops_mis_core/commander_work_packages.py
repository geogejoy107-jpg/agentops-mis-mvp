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


def build_commander_team_board(
    *,
    packages: list[dict[str, Any]],
    workspace_id: str,
    project_id: str | None,
    plan_id: str | None,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    dependency_edges: list[dict[str, str]] = []
    lanes: list[dict[str, Any]] = []
    ready_for_review: list[str] = []
    blocked: list[str] = []
    missing_coding_evidence: list[str] = []
    workflow_job_counts: dict[str, int] = {}
    active_workflow_jobs: list[str] = []
    failed_workflow_jobs: list[str] = []

    task_ids = {str(item.get("task_id") or "") for item in packages}
    for item in packages:
        task_id = str(item.get("task_id") or "")
        package_status = str(item.get("package_status") or item.get("status") or "unknown")
        owner_agent_id = str(item.get("owner_agent_id") or "unassigned")
        status_counts[package_status] = status_counts.get(package_status, 0) + 1
        owner_counts[owner_agent_id] = owner_counts.get(owner_agent_id, 0) + 1
        dependencies = [str(dep) for dep in (item.get("dependencies") or []) if dep]
        for dep in dependencies:
            dependency_edges.append({
                "from_task_id": dep,
                "to_task_id": task_id,
                "known_in_board": dep in task_ids,
            })
        if package_status == "ready_for_review":
            ready_for_review.append(task_id)
        if package_status == "blocked":
            blocked.append(task_id)
        if ((item.get("coding_evidence_gate") or {}).get("status") in {"missing", "partial"}):
            missing_coding_evidence.append(task_id)
        latest_run = item.get("latest_run") or {}
        latest_workflow_job = item.get("latest_workflow_job") or {}
        workflow_job_status = str(latest_workflow_job.get("status") or "")
        if workflow_job_status:
            workflow_job_counts[workflow_job_status] = workflow_job_counts.get(workflow_job_status, 0) + 1
        if workflow_job_status in {"queued", "running"}:
            active_workflow_jobs.append(task_id)
        if workflow_job_status == "failed":
            failed_workflow_jobs.append(task_id)
        lanes.append({
            "task_id": task_id,
            "lane_id": item.get("lane_id"),
            "title": item.get("title"),
            "owner_agent_id": item.get("owner_agent_id"),
            "collaborator_agent_ids": item.get("collaborator_agent_ids") or [],
            "status": item.get("status"),
            "package_status": package_status,
            "priority": item.get("priority"),
            "risk_level": item.get("risk_level"),
            "dependencies": dependencies,
            "dependency_count": len(dependencies),
            "latest_run": {
                "run_id": latest_run.get("run_id"),
                "status": latest_run.get("status"),
                "created_at": latest_run.get("created_at"),
            } if latest_run else None,
            "latest_workflow_job": {
                "job_id": latest_workflow_job.get("job_id"),
                "workflow_type": latest_workflow_job.get("workflow_type"),
                "status": latest_workflow_job.get("status"),
                "adapter": latest_workflow_job.get("adapter"),
                "confirm_run": bool(latest_workflow_job.get("confirm_run")),
                "result_run_id": latest_workflow_job.get("result_run_id"),
                "result_artifact_id": latest_workflow_job.get("result_artifact_id"),
                "created_at": latest_workflow_job.get("created_at"),
                "started_at": latest_workflow_job.get("started_at"),
                "completed_at": latest_workflow_job.get("completed_at"),
                "updated_at": latest_workflow_job.get("updated_at"),
            } if latest_workflow_job else None,
            "evidence_counts": item.get("evidence_counts") or {},
            "localization_gate": item.get("localization_gate") or {},
            "coding_evidence_gate": item.get("coding_evidence_gate") or {},
            "recommended_action": item.get("recommended_action"),
        })

    if blocked or failed_workflow_jobs:
        board_status = "blocked"
    elif ready_for_review or missing_coding_evidence or active_workflow_jobs or status_counts.get("still_running") or status_counts.get("planned"):
        board_status = "attention"
    else:
        board_status = "ready" if lanes else "empty"

    return {
        "status": board_status,
        "workspace_id": workspace_id,
        "project_id": project_id or None,
        "plan_id": plan_id or None,
        "summary": {
            "total_lanes": len(lanes),
            "status_counts": status_counts,
            "owner_counts": owner_counts,
            "ready_for_review": len(ready_for_review),
            "blocked": len(blocked),
            "missing_coding_evidence": len(missing_coding_evidence),
            "dependency_edges": len(dependency_edges),
            "workflow_job_counts": workflow_job_counts,
            "active_workflow_jobs": len(active_workflow_jobs),
            "failed_workflow_jobs": len(failed_workflow_jobs),
        },
        "lanes": lanes,
        "dependency_edges": dependency_edges,
        "ready_for_review_task_ids": ready_for_review,
        "blocked_task_ids": blocked,
        "missing_coding_evidence_task_ids": missing_coding_evidence,
        "active_workflow_job_task_ids": active_workflow_jobs,
        "failed_workflow_job_task_ids": failed_workflow_jobs,
        "next_actions": commander_work_package_next_actions(packages),
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
            "raw_source_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }


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


def build_commander_project_board_gates(
    *,
    closed_loop_runs: int,
    worker_status: dict[str, Any],
    worker_fleet: dict[str, Any],
    pending_approval_count: int,
    memory_candidate_count: int,
    approved_memory_count: int,
    synthesis_lifecycle: dict[str, Any],
    adapter_status: str,
    adapter_summary: dict[str, Any],
    live_acceptance_status: str,
    live_acceptance_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    synthesis_summary = synthesis_lifecycle.get("summary") or {}
    live_fresh = int(live_acceptance_summary.get("fresh") or 0)
    live_failed = int(live_acceptance_summary.get("latest_failed") or 0)
    live_incomplete = int(live_acceptance_summary.get("latest_incomplete") or 0)
    live_missing = int(live_acceptance_summary.get("missing") or 0)
    live_stale = int(live_acceptance_summary.get("stale") or 0)
    if live_acceptance_status == "ready":
        live_gate_status = "pass"
    elif live_failed:
        live_gate_status = "fail"
    else:
        live_gate_status = "warn"
    return [
        {
            "id": "evidence_chain",
            "status": "pass" if closed_loop_runs else "warn",
            "summary": f"{closed_loop_runs} closed-loop run(s) with task/run/tool/eval/audit/artifact evidence",
            "next_action": "Run a mock customer-worker task to create fresh evidence." if not closed_loop_runs else "Review recent run graph before delivery.",
        },
        {
            "id": "worker_fleet_health",
            "status": "pass" if worker_fleet.get("overall") == "ready" else "fail" if worker_fleet.get("overall") == "blocked" else "warn",
            "summary": f"fleet={worker_fleet.get('overall') or worker_status.get('status') or 'unknown'}; running_workers={worker_status.get('running_workers', 0)}; stuck_tasks={worker_status.get('stuck_worker_tasks', 0)}",
            "next_action": (worker_fleet.get("recommended_actions") or ["agentops worker status"])[0],
        },
        {
            "id": "approvals_pending",
            "status": "warn" if pending_approval_count else "pass",
            "summary": f"{pending_approval_count} pending approval(s)",
            "next_action": "Open /workspace/approvals and approve or reject pending gates." if pending_approval_count else "No approval action needed.",
        },
        {
            "id": "memory_review",
            "status": "warn" if memory_candidate_count else "pass" if approved_memory_count else "warn",
            "summary": f"{memory_candidate_count} candidate memory item(s), {approved_memory_count} approved",
            "next_action": "Review candidate memories before using them as project context." if memory_candidate_count else "Capture durable project lessons after the next delivery.",
        },
        {
            "id": "synthesis_lifecycle",
            "status": (
                "warn" if synthesis_summary.get("pending_reviews")
                else "warn" if synthesis_lifecycle.get("status") == "promotion_available"
                else "pass" if synthesis_summary.get("promoted_delivery_artifacts")
                else "warn"
            ),
            "summary": (
                f"{synthesis_summary.get('synthesis_artifacts', 0)} synthesis report(s), "
                f"{synthesis_summary.get('pending_reviews', 0)} pending review(s), "
                f"{synthesis_summary.get('promoted_delivery_artifacts', 0)} promoted delivery artifact(s)"
            ),
            "next_action": (
                synthesis_lifecycle.get("next_actions")
                or ['agentops commander plan --goal "Prepare next customer delivery work packages" --confirm-create']
            )[0],
        },
        {
            "id": "adapter_readiness",
            "status": "pass" if adapter_status == "ready" else "warn" if adapter_status == "degraded" else "fail",
            "summary": f"recommended_adapter={adapter_summary.get('recommended_adapter') or 'unknown'}; ready={','.join(adapter_summary.get('ready_adapters') or []) or 'none'}",
            "next_action": "agentops worker readiness",
        },
        {
            "id": "live_acceptance_freshness",
            "status": live_gate_status,
            "summary": (
                f"{live_fresh} fresh, {live_failed} latest failed, "
                f"{live_incomplete} in flight/incomplete, {live_stale} stale, {live_missing} missing"
            ),
            "next_action": "agentops operator live-acceptance --limit 8",
        },
    ]


def commander_project_board_status(integration_gates: list[dict[str, Any]]) -> str:
    if any(gate.get("status") == "fail" for gate in integration_gates):
        return "blocked"
    if any(gate.get("status") == "warn" for gate in integration_gates):
        return "attention"
    return "ready"


def commander_project_board_next_actions(
    integration_gates: list[dict[str, Any]],
    readiness_next_actions: list[str] | None = None,
) -> list[str]:
    recommended_next_actions: list[str] = []
    for gate in integration_gates:
        action = gate.get("next_action")
        if gate.get("status") in {"fail", "warn"} and action and action not in recommended_next_actions:
            recommended_next_actions.append(action)
    for action in readiness_next_actions or []:
        if action not in recommended_next_actions:
            recommended_next_actions.append(action)
    if not recommended_next_actions:
        recommended_next_actions = [
            "Select the highest-priority planned task and dispatch a mock worker.",
            "Review recent artifacts and approve customer-facing delivery evidence.",
            "Run agentops worker readiness before using live Hermes/OpenClaw adapters.",
        ]
    return recommended_next_actions[:8]
