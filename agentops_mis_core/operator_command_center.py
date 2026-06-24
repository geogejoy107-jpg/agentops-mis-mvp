"""Pure operator command-center read-model aggregation helpers."""
from __future__ import annotations

import shlex
from typing import Any


def _safe_text(value: Any, limit: int = 180) -> str:
    text = str(value or "")
    text = " ".join(text.split())
    return text[:limit]


def build_command_center_commander_gaps(
    commander_packages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for package in commander_packages:
        coding_gate = package.get("coding_evidence_gate") or {}
        localization_gate = package.get("localization_gate") or {}
        latest_run = package.get("latest_run") or {}
        gate_status = str(coding_gate.get("status") or "missing")
        localization_status = str(localization_gate.get("status") or "missing")
        if gate_status == "recorded" and localization_status == "recorded":
            continue
        if localization_status != "recorded":
            next_action = f"agentops commander packages --project-id {shlex.quote(str(package.get('project_id') or ''))} --limit 8"
            gap_type = "missing_localization"
        elif not latest_run.get("run_id"):
            next_action = f"agentops commander dispatch-package --task-id {shlex.quote(str(package.get('task_id') or ''))} --adapter mock"
            gap_type = "run_required"
        elif gate_status != "recorded":
            next_action = f"agentops commander coding-evidence --task-id {shlex.quote(str(package.get('task_id') or ''))} --run-id {shlex.quote(str(latest_run.get('run_id') or ''))} --confirm-record"
            gap_type = "coding_evidence_required"
        else:
            next_action = package.get("recommended_action") or "agentops commander packages --limit 8"
            gap_type = "attention"
        gaps.append({
            "task_id": package.get("task_id"),
            "project_id": package.get("project_id"),
            "plan_id": package.get("plan_id"),
            "lane_id": package.get("lane_id"),
            "title": package.get("title"),
            "package_status": package.get("package_status"),
            "gap_type": gap_type,
            "localization_status": localization_status,
            "coding_evidence_status": gate_status,
            "recorded_coding_artifact_types": coding_gate.get("recorded_artifact_types") or [],
            "required_coding_artifact_types": coding_gate.get("artifact_types") or [],
            "latest_run_id": latest_run.get("run_id"),
            "next_action": next_action,
            "raw_source_omitted": True,
            "raw_patch_omitted": True,
            "token_omitted": True,
        })
    return gaps


def build_command_center_project_rows(
    *,
    commander_packages: list[dict[str, Any]],
    deliveries: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    project_map: dict[str, dict[str, Any]] = {}

    def project_entry(project_id: str, source: str) -> dict[str, Any]:
        key = _safe_text(project_id or "unknown", 120) or "unknown"
        entry = project_map.setdefault(key, {
            "project_id": key,
            "sources": [],
            "commander_packages": 0,
            "commander_ready": 0,
            "commander_blocked": 0,
            "coding_evidence_recorded": 0,
            "coding_evidence_missing_or_partial": 0,
            "deliveries": 0,
            "pending_approvals": 0,
            "next_action": None,
            "token_omitted": True,
        })
        if source not in entry["sources"]:
            entry["sources"].append(source)
        return entry

    for package in commander_packages:
        entry = project_entry(str(package.get("project_id") or "unknown"), "commander")
        entry["commander_packages"] += 1
        if package.get("package_status") == "ready_for_review":
            entry["commander_ready"] += 1
        if package.get("package_status") == "blocked":
            entry["commander_blocked"] += 1
        if ((package.get("coding_evidence_gate") or {}).get("status") == "recorded"):
            entry["coding_evidence_recorded"] += 1
        else:
            entry["coding_evidence_missing_or_partial"] += 1
        entry["next_action"] = entry.get("next_action") or package.get("recommended_action")

    for item in deliveries:
        project_id = str(item.get("project_id") or "unknown")
        entry = project_entry(project_id, "customer_delivery")
        entry["deliveries"] += 1
        if item.get("status") == "waiting_approval":
            entry["pending_approvals"] += 1
        entry["next_action"] = entry.get("next_action") or item.get("next_action")

    return sorted(
        project_map.values(),
        key=lambda item: (
            item.get("coding_evidence_missing_or_partial", 0),
            item.get("commander_blocked", 0),
            item.get("pending_approvals", 0),
        ),
        reverse=True,
    )[:limit]


def build_command_center_stale_worker_refs(worker: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in (worker.get("stuck_tasks") or [])[:limit]:
        refs.append({
            "kind": "stuck_task",
            "task_id": row.get("task_id"),
            "owner_agent_id": row.get("owner_agent_id"),
            "status": row.get("status"),
            "title": _safe_text(row.get("title") or row.get("task_id"), 180),
            "next_action": "agentops worker status",
            "token_omitted": True,
        })
    for row in (worker.get("stuck_workflow_job_refs") or [])[:limit]:
        refs.append({
            "kind": "stuck_workflow_job",
            "job_id": row.get("job_id"),
            "workflow_type": row.get("workflow_type"),
            "status": row.get("status"),
            "age_sec": row.get("age_sec"),
            "stuck_reason": row.get("stuck_reason"),
            "next_action": f"agentops workflow jobs --limit {limit}",
            "token_omitted": True,
        })
    return refs


def command_center_status(
    *,
    blocked_runs: list[dict[str, Any]],
    action_plan_summary: dict[str, Any],
    commander_gaps: list[dict[str, Any]],
    stale_worker_refs: list[dict[str, Any]],
    pending_approvals: list[dict[str, Any]],
    next_actions: list[dict[str, Any]],
) -> str:
    blocked_count = len(blocked_runs) + int(action_plan_summary.get("blocked") or 0)
    attention_count = len(commander_gaps) + len(stale_worker_refs) + len(pending_approvals)
    if blocked_count:
        return "blocked"
    if attention_count or next_actions:
        return "attention"
    return "ready"
