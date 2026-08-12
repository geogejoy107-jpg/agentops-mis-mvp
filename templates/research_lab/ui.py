"""Research UI extension contract; all panels bind typed API resources."""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import ResearchError


REQUIRED_UI_STATES = ("loading", "empty", "ready", "degraded", "error", "recovery", "permission_denied")
_PAGES = (
    ("home", "Research Home", "/api/v1/templates/research_lab/health"),
    ("projects", "Projects", "/api/v1/templates/research_lab/projects"),
    ("experiments", "Experiments", "/api/v1/templates/research_lab/experiments"),
    ("experiment-contract", "Experiment Contract", "/api/v1/templates/research_lab/experiments/{experiment_id}"),
    ("trial-matrix", "Trial Matrix", "/api/v1/templates/research_lab/experiments/{experiment_id}/trials"),
    ("job-attempt", "JobAttempt Detail", "/api/v1/templates/research_lab/attempts/{attempt_id}"),
    ("live-logs", "Live Logs", "/api/v1/templates/research_lab/attempts/{attempt_id}/logs"),
    ("metrics", "Metrics", "/api/v1/templates/research_lab/experiments/{experiment_id}/metrics"),
    ("checkpoints", "Checkpoints", "/api/v1/templates/research_lab/attempts/{attempt_id}/checkpoints"),
    ("compute-targets", "Compute Targets", "/api/v1/templates/research_lab/compute-targets"),
    ("budgets", "Budgets", "/api/v1/templates/research_lab/budgets"),
    ("approvals", "Approvals", "/api/v1/approvals?template_id=research_lab"),
    ("literature", "Literature", "/api/v1/templates/research_lab/literature"),
    ("claims-evidence", "Claims/Evidence", "/api/v1/templates/research_lab/claims"),
    ("manuscripts", "Manuscripts", "/api/v1/templates/research_lab/manuscripts"),
    ("memory", "Memory", "/api/v1/memory?template_id=research_lab"),
    ("runtime-health", "Runtime Health", "/api/v1/templates/research_lab/runtime/health"),
    ("settings", "Settings", "/api/v1/templates/research_lab/settings"),
)


def extension_pages() -> tuple[Mapping[str, Any], ...]:
    return tuple({"id": f"research_lab.ui.{slug.replace('-', '_')}", "route": f"/solutions/research_lab/{slug}", "label": label, "api_resource": api, "states": list(REQUIRED_UI_STATES), "permission": "research_lab.permission.read", "deep_link": True} for slug, label, api in _PAGES)


def app_shell_extension() -> Mapping[str, Any]:
    return {"component": "templates/research_lab/ui/ResearchLabExtension.tsx", "style": "templates/research_lab/ui/research-lab.css", "route_prefix": "/solutions/research_lab", "pages": list(extension_pages()), "api_connected": True}


def resolve_view_state(*, authorized: bool, loading: bool, data: Any, error_code: str | None, runtime_state: str | None = None) -> str:
    if not authorized:
        return "permission_denied"
    if loading:
        return "loading"
    if error_code:
        return "recovery" if error_code in {"research.runtime_unavailable", "research.stale_heartbeat"} else "error"
    if runtime_state in {"degraded", "unavailable"}:
        return "degraded"
    if data in (None, [], {}):
        return "empty"
    return "ready"


def validate_action(action: Mapping[str, Any]) -> Mapping[str, Any]:
    operation = action.get("operation")
    allowed = {"create", "configure", "pause", "resume", "cancel", "reconcile", "approve", "invalidate", "export"}
    if operation not in allowed:
        raise ResearchError("research.ui_action_invalid", "UI action is not registered")
    if operation in {"resume", "cancel", "approve", "invalidate"} and not action.get("action_hash"):
        raise ResearchError("research.ui_action_hash_missing", "privileged UI action requires a prepared action hash")
    return {"operation": operation, "endpoint": action.get("endpoint"), "idempotency_key": action.get("idempotency_key"), "action_hash": action.get("action_hash")}
