"""Pure workflow-job public projection helpers."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shlex
from typing import Any


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "::".join(str(p) for p in parts if p is not None and str(p) != "")
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()
    if slug and len(slug) <= 64:
        return f"{prefix}_{slug}"
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _safe_text(value: Any, limit: int = 180) -> str:
    text = str(value or "")
    text = " ".join(text.split())
    return text[:limit]


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


def build_workflow_job_recovery_work_order(
    *,
    workspace_id: str,
    stuck_jobs: list[dict[str, Any]],
    retryable_failed_jobs: list[dict[str, Any]],
    receipt_rows: list[dict[str, Any]],
    limit: int = 8,
) -> dict:
    limit = min(max(int(limit or 8), 1), 25)

    def receipt_state(command: str, action_id: str, action_signature: str) -> dict:
        command = command.strip()
        command_hash = _stable_hash(command) if command else ""
        receipt = next((
            item for item in receipt_rows
            if str(item.get("action_signature") or "").strip() == action_signature
            or str(item.get("action_id") or "").strip() == action_id
            or str(item.get("action_command") or "").strip() == command
            or str(item.get("action_hash") or "").strip() == command_hash
        ), None)
        status = (receipt or {}).get("status") or "missing"
        return {
            "required": True,
            "status": status,
            "verified": bool(receipt and status == "verified"),
            "current": bool(receipt),
            "receipt_id": (receipt or {}).get("receipt_id"),
            "receipt_hash": (receipt or {}).get("tamper_chain_hash"),
            "evaluation_pass_fail": (receipt or {}).get("evaluation_pass_fail"),
            "evaluation_score": (receipt or {}).get("evaluation_score"),
            "action_id": action_id,
            "action_signature": action_signature,
            "action_hash": command_hash,
            "source": "operator.workflow_job_recovery",
            "token_omitted": True,
        }

    def receipt_command(
        command: str,
        verify: str,
        action_id: str,
        action_signature: str,
        summary: str,
        *,
        status: str = "recorded",
        confirm: bool = False,
    ) -> str:
        parts = [
            "agentops", "operator", "record-action-receipt",
            "--action-command", command,
            "--verify-command", verify,
            "--action-id", action_id,
            "--action-signature", action_signature,
            "--status", status,
            "--source", "operator.workflow_job_recovery",
            "--result-summary", summary,
        ]
        if confirm:
            parts.append("--confirm-record")
        return " ".join(shlex.quote(str(part)) for part in parts)

    def item_for_job(job: dict[str, Any], mode: str) -> dict | None:
        job_id = str(job.get("job_id") or "").strip()
        if not job_id:
            return None
        if mode == "retry":
            task_id = str(job.get("result_task_id") or "").strip()
            if not task_id:
                return None
            adapter = str(job.get("adapter") or "mock").strip()
            if adapter not in {"mock", "hermes", "openclaw"}:
                adapter = "mock"
            action_id = f"workflow_job_recovery:{job_id}:retry"
            action_signature = _stable_id("op_action_sig", "workflow_job_recovery", workspace_id, job_id, "retry", task_id, adapter)[-18:]
            preview_parts = ["agentops", "workflow", "recover-job", "--job-id", job_id, "--mode", "retry", "--task-id", task_id, "--adapter", adapter]
            confirm_parts = [*preview_parts, "--confirm-recover", "--record-receipt"]
            if adapter in {"hermes", "openclaw"}:
                confirm_parts.append("--confirm-run")
            verify = "agentops workflow jobs --status queued,running,completed,failed --limit 20"
            summary = f"Workflow job {job_id} retry was queued or safely rejected with evidence."
            severity = "attention"
            reason = f"Failed workflow job can be retried through exact-task dispatch; adapter={adapter}."
            confirm_required = adapter in {"hermes", "openclaw"}
            task_id_value = task_id
        else:
            action_id = f"workflow_job_recovery:{job_id}:mark_failed"
            action_signature = _stable_id("op_action_sig", "workflow_job_recovery", workspace_id, job_id, "mark_failed")[-18:]
            reason_text = "workflow job exceeded async threshold; operator recovery from handoff"
            preview_parts = ["agentops", "workflow", "recover-job", "--job-id", job_id, "--mode", "mark-failed", "--reason", reason_text]
            confirm_parts = [*preview_parts, "--confirm-recover", "--record-receipt"]
            verify = f"agentops workflow job-status --job-id {shlex.quote(job_id)}"
            summary = f"Workflow job {job_id} marked failed after recover-job review."
            severity = "blocked"
            reason = f"Workflow job exceeded async threshold; age_sec={job.get('age_sec') or 0}."
            confirm_required = True
            task_id_value = job.get("result_task_id")
        preview_command = " ".join(shlex.quote(str(part)) for part in preview_parts)
        confirm_command = " ".join(shlex.quote(str(part)) for part in confirm_parts)
        receipt = receipt_state(confirm_command, action_id, action_signature)
        record_command = receipt_command(confirm_command, verify, action_id, action_signature, summary)
        verify_record_command = receipt_command(confirm_command, verify, action_id, action_signature, summary, status="verified", confirm=True)
        return {
            "operation": "workflow_job_recovery_item",
            "job_id": job_id,
            "mode": mode,
            "status": "verified" if receipt.get("verified") else severity,
            "severity": severity,
            "title": job.get("title") or f"Workflow job recovery: {job_id}",
            "summary": _safe_text(reason, 360),
            "preview_command": preview_command,
            "confirm_command": confirm_command,
            "verify_command": verify,
            "receipt_record_command": record_command,
            "receipt_verify_record_command": verify_record_command,
            "receipt_next_command": verify_record_command,
            "receipt_state": receipt,
            "adapter": job.get("adapter"),
            "confirm_required": confirm_required,
            "live_confirm_required": bool(job.get("adapter") in {"hermes", "openclaw"}),
            "task_id": task_id_value,
            "run_id": job.get("result_run_id"),
            "artifact_id": job.get("result_artifact_id"),
            "age_sec": job.get("age_sec"),
            "threshold_sec": job.get("threshold_sec"),
            "error_summary": _safe_text(job.get("error_message") or "", 240) if job.get("error_message") else None,
            "raw_request_omitted": True,
            "token_omitted": True,
        }

    items = [item for item in (item_for_job(job, "mark-failed") for job in stuck_jobs) if item]
    items.extend(item for item in (item_for_job(job, "retry") for job in retryable_failed_jobs) if item)
    items = items[:limit]
    blocked = [item for item in items if item.get("severity") == "blocked" and not (item.get("receipt_state") or {}).get("verified")]
    attention = [item for item in items if item.get("severity") == "attention" and not (item.get("receipt_state") or {}).get("verified")]
    verified = [item for item in items if (item.get("receipt_state") or {}).get("verified")]
    commands: list[str] = []
    for item in items:
        for key in ["preview_command", "confirm_command", "verify_command", "receipt_verify_record_command"]:
            command = str(item.get(key) or "").strip()
            if command and command not in commands:
                commands.append(command)
    return {
        "operation": "workflow_job_recovery_work_order",
        "status": "blocked" if blocked else "attention" if attention else "ready",
        "workspace_id": workspace_id,
        "summary": {
            "items": len(items),
            "stuck_jobs": len(stuck_jobs),
            "retryable_failed_jobs": len(retryable_failed_jobs),
            "blocked": len(blocked),
            "attention": len(attention),
            "receipt_required": len(items),
            "receipt_verified": len(verified),
            "receipt_missing": len(items) - len(verified),
        },
        "items": items,
        "commands": commands[: min(len(commands), 24)],
        "next_actions": [item["preview_command"] for item in items[:3]] or ["agentops workflow stuck-jobs --threshold-sec 900 --limit 25"],
        "contract": "read-only workflow-job recovery work order for Hermes/OpenClaw/Codex; preview is read-only, confirmed recovery requires explicit --confirm-recover, receipts use operator.workflow_job_recovery, and live retry still requires --confirm-run",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "token_omitted": True,
        },
        "token_omitted": True,
    }
