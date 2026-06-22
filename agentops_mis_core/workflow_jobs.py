"""Pure workflow-job public projection helpers."""
from __future__ import annotations

import json
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
