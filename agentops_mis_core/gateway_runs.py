"""Pure Agent Gateway run helpers."""
from __future__ import annotations

from typing import Any


def row_field(row: Any | None, field: str, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[field]
    except Exception:
        return row.get(field, default) if hasattr(row, "get") else default


def build_run_heartbeat_update(
    before: Any,
    *,
    status: str,
    ended_at: Any,
    duration_ms: Any,
    output_summary: Any,
    error_type: Any,
    error_message: Any,
    output_tokens: int,
    cost_usd: float,
) -> dict[str, Any]:
    return {
        "run_id": row_field(before, "run_id"),
        "status": status,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "output_summary": output_summary,
        "error_type": error_type,
        "error_message": error_message,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "token_omitted": True,
    }


def run_heartbeat_terminal_task_status(status: str) -> str | None:
    if status == "completed":
        return "completed"
    if status == "blocked":
        return "blocked"
    if status == "failed":
        return "failed"
    return None
