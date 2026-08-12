"""Template health, readiness and external-resource preflight."""

from __future__ import annotations

import shutil
from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import canonical_hash


_PROTECTED = ("token", "secret", "password", "credential", "private_key", "prompt", "response")


def redact_nested(value: Any, *, key: str = "") -> Any:
    if any(part in key.lower().replace("-", "_") for part in _PROTECTED):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(child_key): redact_nested(child_value, key=str(child_key)) for child_key, child_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_nested(item) for item in value]
    return value


def external_preflight(*, openjiuwen_health: Mapping[str, Any] | None, gpu_inventory: Sequence[Mapping[str, Any]], ssh_targets: Sequence[Mapping[str, Any]], slurm_required: bool) -> Mapping[str, Any]:
    runtime_state = (openjiuwen_health or {}).get("state", "unavailable")
    gates = {
        "openjiuwen": {"state": runtime_state, "verified": runtime_state == "ready" and bool((openjiuwen_health or {}).get("upstream_version"))},
        "local_executor": {"state": "ready", "verified": True},
        "ssh_gpu": {"state": "ready" if gpu_inventory and ssh_targets else "unavailable", "verified": False},
        "slurm": {"state": "ready" if shutil.which("sbatch") else ("unavailable" if slurm_required else "not_applicable"), "verified": False if slurm_required else None},
    }
    blockers = [name for name, gate in gates.items() if gate["state"] == "unavailable"]
    result = {"template": "research_lab", "version": "1.0.0", "state": "ready" if not blockers else "degraded", "gates": gates, "external_blockers": blockers, "false_success": False}
    return {**result, "health_hash": canonical_hash(result)}


def queue_health(attempts: Sequence[Mapping[str, Any]], *, stale_before: str) -> Mapping[str, Any]:
    stale = [item.get("job_attempt_id") for item in attempts if item.get("state") == "running" and (not item.get("heartbeat_at") or str(item["heartbeat_at"]) < stale_before)]
    counts: dict[str, int] = {}
    for item in attempts:
        state = str(item.get("state") or "unknown")
        counts[state] = counts.get(state, 0) + 1
    result = {"counts": counts, "stale_attempt_ids": stale, "state": "degraded" if stale else "ready", "alert_threshold": stale_before}
    return {**result, "receipt_hash": canonical_hash(result)}


def structured_event(*, level: str, event: str, correlation_id: str, fields: Mapping[str, Any]) -> Mapping[str, Any]:
    """Build a compact redacted structured log event."""
    if level not in {"debug", "info", "warning", "error", "critical"}:
        raise ValueError("unsupported log level")
    safe_fields = redact_nested(fields)
    result = {"level": level, "event": event, "template_id": "research_lab", "correlation_id": correlation_id, "fields": safe_fields}
    return {**result, "event_hash": canonical_hash(result)}


def usage_metrics(*, token_input: int, token_output: int, cost_usd: float, gpu_seconds: float, artifact_bytes: int) -> Mapping[str, Any]:
    values = {"token_input": token_input, "token_output": token_output, "cost_usd": cost_usd, "gpu_seconds": gpu_seconds, "artifact_bytes": artifact_bytes}
    if any(isinstance(value, bool) or value < 0 for value in values.values()):
        raise ValueError("usage metrics must be non-negative")
    return {**values, "metric_hash": canonical_hash(values)}
