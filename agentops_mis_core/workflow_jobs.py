"""Pure workflow-job public projection helpers."""
from __future__ import annotations

import json
import datetime as dt
from typing import Any


def workflow_job_public(row: Any | None) -> dict | None:
    if not row:
        return None
    data = dict(row)
    result = {}
    try:
        result = json.loads(data.get("result_json") or "{}")
    except Exception:
        result = {}
    return {
        "job_id": data.get("job_id"),
        "workspace_id": data.get("workspace_id"),
        "workflow_type": data.get("workflow_type"),
        "status": data.get("status"),
        "template_id": data.get("template_id"),
        "adapter": data.get("adapter"),
        "confirm_run": bool(data.get("confirm_run")),
        "title": data.get("title"),
        "input_summary": data.get("input_summary"),
        "request_hash": data.get("request_hash"),
        "result_task_id": data.get("result_task_id"),
        "result_run_id": data.get("result_run_id"),
        "result_artifact_id": data.get("result_artifact_id"),
        "error_message": data.get("error_message"),
        "created_at": data.get("created_at"),
        "started_at": data.get("started_at"),
        "completed_at": data.get("completed_at"),
        "updated_at": data.get("updated_at"),
        "result": result,
        "raw_request_omitted": True,
        "token_omitted": True,
    }


def workflow_job_parse_iso_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception:
        return None


def workflow_job_stuck_projection(
    row: Any | None,
    *,
    now_dt: dt.datetime,
    threshold_sec: int,
) -> dict | None:
    data = workflow_job_public(row) or {}
    anchor = (
        workflow_job_parse_iso_datetime(data.get("updated_at"))
        or workflow_job_parse_iso_datetime(data.get("started_at"))
        or workflow_job_parse_iso_datetime(data.get("created_at"))
        or now_dt
    )
    age_sec = max(int((now_dt - anchor).total_seconds()), 0)
    if age_sec < threshold_sec:
        return None
    data["age_sec"] = age_sec
    data["threshold_sec"] = threshold_sec
    data["stuck_reason"] = "workflow_job_exceeded_threshold"
    return data


def workflow_job_not_active_response(row: Any | None) -> dict:
    return {
        "ok": False,
        "reason": "workflow_job_not_active",
        "job": workflow_job_public(row),
        "token_omitted": True,
    }


def workflow_job_mark_failed_response(row: Any | None, job_id: str) -> dict:
    return {
        "ok": True,
        "provider": "agentops-workflow-job",
        "job": workflow_job_public(row),
        "job_id": job_id,
        "marked_failed": True,
        "token_omitted": True,
    }


def _count_map(rows: list[Any], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        data = dict(row)
        value = data.get(key)
        if value is None:
            continue
        counts[str(value)] = int(data.get("c") or 0)
    return counts


def workflow_jobs_list_response(
    *,
    rows: list[Any],
    limit: int,
    statuses: set[str],
    workflow_types: set[str],
    summary_rows: list[Any],
    workflow_type_rows: list[Any],
    active_count: int,
    stuck_count: int,
) -> dict:
    return {
        "provider": "agentops-workflow-job",
        "operation": "workflow_jobs_list",
        "jobs": [workflow_job_public(row) for row in rows],
        "count": len(rows),
        "limit": limit,
        "filters": {
            "status": sorted(statuses),
            "workflow_type": sorted(workflow_types),
        },
        "summary": {
            "by_status": _count_map(summary_rows, "status"),
            "by_workflow_type": _count_map(workflow_type_rows, "workflow_type"),
            "active_jobs": int(active_count or 0),
            "stuck_jobs": int(stuck_count or 0),
        },
        "next_actions": [
            "agentops workflow job-status --job-id <job_id> --wait",
            "agentops workflow stuck-jobs --threshold-sec 900 --limit 25",
            "agentops workflow job-mark-failed --job-id <job_id> --reason '<reason>'",
        ],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "token_omitted": True,
    }
