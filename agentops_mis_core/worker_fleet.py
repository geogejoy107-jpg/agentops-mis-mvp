"""Pure worker fleet read-model aggregation helpers."""
from __future__ import annotations

import hashlib
import re
from typing import Any


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "::".join(str(part) for part in parts if part is not None and str(part) != "")
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()
    if slug and len(slug) <= 64:
        return f"{prefix}_{slug}"
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def worker_fleet_health(payload: dict[str, Any]) -> dict[str, Any]:
    remote = payload.get("remote_worker_health") or {}
    daemons = payload.get("daemons") or []
    active_daemons = [daemon for daemon in daemons if daemon.get("running")]
    running_workers = _int(payload.get("running_workers"))
    pending_tasks = _int(payload.get("pending_worker_tasks"))
    stuck_tasks = _int(payload.get("stuck_worker_tasks"))
    workflow_stuck_jobs = _int(payload.get("stuck_workflow_jobs"))
    active_remote = _int(payload.get("active_remote_enrollments"))
    fresh_remote = _int(payload.get("fresh_remote_enrollments"))
    stale_remote = _int(payload.get("stale_remote_enrollments"))
    never_seen_remote = _int(payload.get("never_seen_remote_enrollments"))
    active_sessions = _int(payload.get("active_remote_sessions"))

    gates: list[dict[str, Any]] = []

    def add_gate(gate_id: str, status: str, summary: str, action: str = "") -> None:
        gates.append({
            "id": gate_id,
            "status": status,
            "summary": summary,
            "action": action,
        })

    if stuck_tasks:
        add_gate(
            "worker_task_recovery",
            "fail",
            f"{stuck_tasks} running worker task(s) exceeded the recovery threshold.",
            "Review agentops worker stuck, then release the selected task.",
        )
    else:
        add_gate("worker_task_recovery", "pass", "No stale running worker tasks detected.", "agentops worker stuck")

    if workflow_stuck_jobs:
        add_gate(
            "workflow_job_recovery",
            "fail",
            f"{workflow_stuck_jobs} async workflow job(s) appear stuck.",
            "agentops workflow stuck-jobs",
        )
    else:
        add_gate("workflow_job_recovery", "pass", "No stuck async workflow jobs detected.", "agentops workflow stuck-jobs")

    if running_workers:
        add_gate(
            "execution_capacity",
            "pass",
            f"{running_workers} worker execution path(s) are currently available.",
            "agentops worker status",
        )
    elif pending_tasks:
        add_gate(
            "execution_capacity",
            "warn",
            f"{pending_tasks} worker task(s) are waiting but no active worker is visible.",
            "agentops worker start --adapter mock",
        )
    else:
        add_gate(
            "execution_capacity",
            "warn",
            "No active worker daemon or running worker agent is visible.",
            "agentops worker preflight --adapter mock",
        )

    if active_remote and stale_remote:
        add_gate(
            "remote_heartbeats",
            "warn",
            f"{stale_remote} remote enrollment(s) have stale heartbeats.",
            "agentops enrollment list && agentops doctor",
        )
    elif active_remote and fresh_remote:
        add_gate(
            "remote_heartbeats",
            "pass",
            f"{fresh_remote} remote enrollment(s) have fresh heartbeats.",
            "agentops agent heartbeat",
        )
    elif active_remote and never_seen_remote:
        add_gate(
            "remote_heartbeats",
            "warn",
            f"{never_seen_remote} active enrollment(s) have not heartbeated yet.",
            "agentops agent heartbeat",
        )
    else:
        add_gate(
            "remote_heartbeats",
            "info",
            "No remote agent enrollments are active; local-only operation is allowed.",
            "agentops enrollment create --agent-id <agent_id>",
        )

    if active_remote and active_sessions:
        add_gate(
            "session_hygiene",
            "pass",
            f"{active_sessions} short-lived remote session(s) are active.",
            "agentops session list",
        )
    elif active_remote:
        add_gate(
            "session_hygiene",
            "warn",
            "Remote enrollments exist but no short-lived worker session is active.",
            "agentops session create",
        )
    else:
        add_gate("session_hygiene", "info", "No remote sessions are required for local-only mode.", "agentops session list")

    if active_daemons:
        daemon_summaries = [
            f"{daemon.get('adapter')} pid={daemon.get('pid')}"
            for daemon in active_daemons
            if daemon.get("adapter")
        ]
        add_gate(
            "local_daemons",
            "pass",
            "Local worker daemon(s) running: " + ", ".join(daemon_summaries[:3]),
            "agentops worker logs --adapter mock",
        )
    else:
        add_gate(
            "local_daemons",
            "info",
            "No repo-local daemon is running; one-shot or remote workers can still execute tasks.",
            "agentops worker start --adapter mock",
        )

    statuses = {gate["status"] for gate in gates}
    overall = "blocked" if "fail" in statuses else "attention" if "warn" in statuses else "ready"
    actions = []
    for gate in gates:
        action = gate.get("action")
        if action and action not in actions and gate.get("status") in {"fail", "warn"}:
            actions.append(action)
    if not actions:
        actions = ["agentops worker status", "agentops workflow run-task --help"]

    return {
        "overall": overall,
        "contract": "agents execute through Agent Gateway CLI/API; browser UI is an operator console only",
        "gates": gates,
        "recommended_actions": actions[:6],
        "remote_status": remote.get("status"),
        "token_omitted": True,
    }


def public_worker_stale_enrollment(enrollment: dict[str, Any]) -> dict[str, Any]:
    token_id = enrollment.get("token_id") or ""
    public = dict(enrollment)
    public.pop("token_id", None)
    public["token_ref"] = stable_id("token_ref", token_id)[-12:] if token_id else ""
    public["token_id_omitted"] = True
    return public


def build_worker_fleet_hygiene_plan(
    *,
    stuck_tasks: list[dict[str, Any]],
    stale_enrollments: list[dict[str, Any]],
    stale_heartbeat_enrollments: list[dict[str, Any]] | None = None,
    threshold_sec: int,
    enrollment_age_sec: int,
    apply: bool = False,
) -> dict[str, Any]:
    stale_heartbeat_enrollments = stale_heartbeat_enrollments or []
    actions_available = len(stuck_tasks) + len(stale_enrollments) + len(stale_heartbeat_enrollments)
    return {
        "provider": "agentops-worker",
        "operation": "fleet_hygiene",
        "status": "actionable" if actions_available else "ready",
        "threshold_sec": threshold_sec,
        "enrollment_age_sec": enrollment_age_sec,
        "summary": {
            "stuck_tasks": len(stuck_tasks),
            "stale_never_seen_enrollments": len(stale_enrollments),
            "stale_heartbeat_enrollments": len(stale_heartbeat_enrollments),
            "actions_available": actions_available,
        },
        "stuck_tasks": stuck_tasks,
        "stale_never_seen_enrollments": [public_worker_stale_enrollment(enrollment) for enrollment in stale_enrollments],
        "stale_heartbeat_enrollments": [
            public_worker_stale_enrollment(enrollment) for enrollment in stale_heartbeat_enrollments
        ],
        "recommended_actions": [
            "agentops worker hygiene --apply --confirm-cleanup",
        ] if actions_available else ["agentops worker status"],
        "safety": {
            "read_only": not apply,
            "requires_confirm_cleanup": True,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }


def public_worker_revoked_enrollment(enrollment: dict[str, Any], sessions_revoked: int = 0) -> dict[str, Any]:
    return {
        "token_ref": stable_id("token_ref", enrollment.get("token_id") or "")[-12:],
        "token_id_omitted": True,
        "agent_id": enrollment.get("agent_id"),
        "sessions_revoked": sessions_revoked,
    }


def public_worker_enrollment_error(enrollment: dict[str, Any], *, status: int, error: Any) -> dict[str, Any]:
    return {
        "kind": "enrollment_revoke",
        "token_ref": stable_id("token_ref", enrollment.get("token_id") or "")[-12:],
        "token_id_omitted": True,
        "status": status,
        "error": error,
    }


def public_remote_worker(
    enrollment: dict[str, Any],
    *,
    agent: dict[str, Any] | None = None,
    active_session_count: int = 0,
) -> dict[str, Any]:
    agent = agent or {}
    return {
        "token_ref": stable_id("token_ref", enrollment.get("token_id") or "")[-12:] if enrollment.get("token_id") else "",
        "token_id_omitted": True,
        "workspace_id": enrollment.get("workspace_id"),
        "agent_id": enrollment.get("agent_id"),
        "agent_name": agent.get("name") or enrollment.get("label") or enrollment.get("agent_id"),
        "runtime_type": agent.get("runtime_type") or "external",
        "agent_status": agent.get("status"),
        "token_status": enrollment.get("status") or "unknown",
        "heartbeat_state": enrollment.get("heartbeat_state") or "unknown",
        "heartbeat_timeout_sec": enrollment.get("heartbeat_timeout_sec"),
        "last_heartbeat_at": enrollment.get("last_heartbeat_at"),
        "last_used_at": enrollment.get("last_used_at"),
        "expires_at": enrollment.get("expires_at"),
        "scope_count": len(enrollment.get("scopes") or []),
        "active_session_count": active_session_count,
    }


def public_remote_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_ref": stable_id("session_ref", session.get("session_id") or "")[-12:] if session.get("session_id") else "",
        "session_id_omitted": True,
        "parent_token_ref": stable_id("token_ref", session.get("parent_token_id") or "")[-12:] if session.get("parent_token_id") else "",
        "workspace_id": session.get("workspace_id"),
        "agent_id": session.get("agent_id"),
        "status": session.get("status"),
        "session_state": session.get("session_state"),
        "created_at": session.get("created_at"),
        "expires_at": session.get("expires_at"),
        "last_used_at": session.get("last_used_at"),
        "scope_count": len(session.get("scopes") or []),
    }


def build_worker_remote_fleet_summary(
    *,
    enrollments: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    agents_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    active_sessions_by_agent: dict[str, int] = {}
    session_state_counts: dict[str, int] = {}
    for session in sessions:
        state = session.get("session_state") or session.get("status") or "unknown"
        session_state_counts[state] = session_state_counts.get(state, 0) + 1
        if state == "active" and session.get("agent_id"):
            active_sessions_by_agent[session["agent_id"]] = active_sessions_by_agent.get(session["agent_id"], 0) + 1

    heartbeat_counts: dict[str, int] = {}
    token_status_counts: dict[str, int] = {}
    remote_workers = []
    for enrollment in enrollments:
        heartbeat_state = enrollment.get("heartbeat_state") or "unknown"
        token_status = enrollment.get("status") or "unknown"
        heartbeat_counts[heartbeat_state] = heartbeat_counts.get(heartbeat_state, 0) + 1
        token_status_counts[token_status] = token_status_counts.get(token_status, 0) + 1
        agent = agents_by_id.get(enrollment.get("agent_id") or "") or {}
        remote_workers.append(public_remote_worker(
            enrollment,
            agent=agent,
            active_session_count=active_sessions_by_agent.get(enrollment.get("agent_id"), 0),
        ))

    active_enrollments = [item for item in remote_workers if item.get("token_status") == "active"]
    stale_enrollments = [item for item in remote_workers if item.get("heartbeat_state") == "stale"]
    never_seen_enrollments = [item for item in remote_workers if item.get("heartbeat_state") == "never_seen"]
    fresh_enrollments = [item for item in remote_workers if item.get("heartbeat_state") == "fresh"]
    health_status = "attention" if stale_enrollments else "ready"
    if active_enrollments and not fresh_enrollments and len(never_seen_enrollments) == len(active_enrollments):
        health_status = "waiting_for_heartbeat"

    return {
        "status": health_status,
        "remote_worker_count": len(active_enrollments),
        "total_remote_enrollments": len(remote_workers),
        "active_enrollments": len(active_enrollments),
        "fresh_enrollments": len(fresh_enrollments),
        "stale_enrollments": len(stale_enrollments),
        "never_seen_enrollments": len(never_seen_enrollments),
        "active_sessions": session_state_counts.get("active", 0),
        "expired_sessions": session_state_counts.get("expired", 0),
        "revoked_sessions": session_state_counts.get("revoked", 0),
        "heartbeat_state_counts": heartbeat_counts,
        "token_status_counts": token_status_counts,
        "session_state_counts": session_state_counts,
        "remote_workers": remote_workers[:50],
        "recent_sessions": [public_remote_session(session) for session in sessions[:25]],
        "token_omitted": True,
    }


def build_worker_status_payload(
    *,
    worker_agents: list[dict[str, Any]],
    worker_runs: list[dict[str, Any]],
    worker_tasks: list[dict[str, Any]],
    worker_events: list[dict[str, Any]],
    daemons: list[dict[str, Any]],
    stuck_tasks: list[dict[str, Any]],
    remote_fleet: dict[str, Any],
    stuck_workflow_jobs: list[dict[str, Any]],
    adapter_readiness: dict[str, Any],
) -> dict[str, Any]:
    active_daemons = [daemon for daemon in daemons if daemon.get("running")]
    payload = {
        "provider": "agentops-worker",
        "status": "attention" if remote_fleet.get("stale_enrollments") else "running" if active_daemons else "ready",
        "worker_count": len(worker_agents),
        "running_workers": len([agent for agent in worker_agents if agent.get("status") == "running"]) + len(active_daemons),
        "recent_completed_runs": len([run for run in worker_runs if run.get("status") == "completed"]),
        "pending_worker_tasks": len([task for task in worker_tasks if task.get("status") in ("planned", "backlog")]),
        "stuck_worker_tasks": len(stuck_tasks),
        "stuck_workflow_jobs": len(stuck_workflow_jobs),
        "remote_worker_count": remote_fleet.get("remote_worker_count", 0),
        "total_remote_enrollments": remote_fleet.get("total_remote_enrollments", 0),
        "active_remote_enrollments": remote_fleet.get("active_enrollments", 0),
        "fresh_remote_enrollments": remote_fleet.get("fresh_enrollments", 0),
        "stale_remote_enrollments": remote_fleet.get("stale_enrollments", 0),
        "never_seen_remote_enrollments": remote_fleet.get("never_seen_enrollments", 0),
        "active_remote_sessions": remote_fleet.get("active_sessions", 0),
        "remote_worker_health": remote_fleet,
        "adapter_readiness": adapter_readiness.get("summary"),
        "daemons": daemons,
        "workers": worker_agents,
        "recent_runs": worker_runs,
        "recent_tasks": worker_tasks,
        "stuck_tasks": stuck_tasks,
        "stuck_workflow_job_refs": [{
            "job_id": job.get("job_id"),
            "workflow_type": job.get("workflow_type"),
            "status": job.get("status"),
            "age_sec": job.get("age_sec"),
            "stuck_reason": job.get("stuck_reason"),
        } for job in stuck_workflow_jobs],
        "recent_events": worker_events,
    }
    payload["fleet_health"] = worker_fleet_health(payload)
    return payload


def build_worker_fleet_view(
    *,
    daemons: list[dict[str, Any]],
    remote_fleet: dict[str, Any],
    adapter_readiness: dict[str, Any],
    stuck_tasks: list[dict[str, Any]],
    stuck_workflow_jobs: list[dict[str, Any]],
    worker_agents: list[dict[str, Any]],
) -> dict[str, Any]:
    lanes: list[dict[str, Any]] = []
    seen_agents: set[str] = set()

    def add_lane(lane: dict[str, Any]) -> None:
        lane["token_omitted"] = True
        lane["session_id_omitted"] = True
        lanes.append(lane)
        if lane.get("agent_id"):
            seen_agents.add(lane["agent_id"])

    for daemon in daemons:
        running = bool(daemon.get("running"))
        status = daemon.get("worker_status") or daemon.get("status") or "unknown"
        health = "pass" if running else "info"
        if running and _int(daemon.get("consecutive_errors")) > 0:
            health = "warn"
        add_lane({
            "lane_id": f"local_daemon:{daemon.get('adapter')}",
            "lane_type": "local_daemon",
            "adapter": daemon.get("adapter"),
            "agent_id": daemon.get("agent_id"),
            "workspace_id": "local-demo",
            "runtime_type": daemon.get("adapter") or "mock",
            "status": status,
            "health": health,
            "heartbeat_state": "local_process" if running else "not_running",
            "session_state": "not_required",
            "active_session_count": 0,
            "last_seen_at": daemon.get("state_updated_at") or daemon.get("started_at") or daemon.get("stopped_at"),
            "workload": {
                "processed": _int(daemon.get("processed")),
                "iterations": _int(daemon.get("iterations")),
                "consecutive_errors": _int(daemon.get("consecutive_errors")),
                "total_errors": _int(daemon.get("total_errors")),
            },
            "next_action": "agentops worker logs --adapter " + str(daemon.get("adapter") or "mock") if running else "agentops worker start --adapter " + str(daemon.get("adapter") or "mock"),
            "safe_ref": stable_id("fleet_lane", "local_daemon", daemon.get("adapter") or "mock")[-12:],
        })

    for worker in (remote_fleet.get("remote_workers") or []):
        token_status = worker.get("token_status") or "unknown"
        heartbeat_state = worker.get("heartbeat_state") or "unknown"
        active_sessions = _int(worker.get("active_session_count"))
        if token_status != "active":
            health = "info"
            next_action = "agentops enrollment create --agent-id <agent_id>"
        elif heartbeat_state == "stale":
            health = "warn"
            next_action = "agentops doctor && agentops agent heartbeat"
        elif heartbeat_state == "never_seen":
            health = "warn"
            next_action = "agentops agent heartbeat"
        elif active_sessions <= 0:
            health = "warn"
            next_action = "agentops session create --ttl-sec 900 --save-session"
        else:
            health = "pass"
            next_action = "agentops-worker --once --adapter mock --use-session"
        add_lane({
            "lane_id": f"remote_worker:{worker.get('agent_id')}:{worker.get('token_ref')}",
            "lane_type": "remote_worker",
            "adapter": worker.get("runtime_type") or "external",
            "agent_id": worker.get("agent_id"),
            "agent_name": worker.get("agent_name"),
            "workspace_id": worker.get("workspace_id"),
            "runtime_type": worker.get("runtime_type") or "external",
            "status": token_status,
            "health": health,
            "heartbeat_state": heartbeat_state,
            "session_state": "active" if active_sessions else "missing",
            "active_session_count": active_sessions,
            "last_seen_at": worker.get("last_heartbeat_at") or worker.get("last_used_at"),
            "expires_at": worker.get("expires_at"),
            "scope_count": _int(worker.get("scope_count")),
            "next_action": next_action,
            "safe_ref": worker.get("token_ref"),
            "token_id_omitted": True,
        })

    for agent in worker_agents:
        if agent.get("agent_id") in seen_agents:
            continue
        status = agent.get("status") or "unknown"
        add_lane({
            "lane_id": f"registered_worker:{agent.get('agent_id')}",
            "lane_type": "registered_worker",
            "adapter": agent.get("runtime_type") or "mock",
            "agent_id": agent.get("agent_id"),
            "agent_name": agent.get("name"),
            "workspace_id": "local-demo",
            "runtime_type": agent.get("runtime_type") or "mock",
            "status": status,
            "health": "pass" if status == "running" else "info",
            "heartbeat_state": "registered",
            "session_state": "unknown",
            "active_session_count": 0,
            "last_seen_at": agent.get("updated_at"),
            "next_action": "agentops worker status",
            "safe_ref": stable_id("fleet_lane", "registered_worker", agent.get("agent_id") or "")[-12:],
        })

    lane_counts: dict[str, int] = {}
    health_counts: dict[str, int] = {}
    for lane in lanes:
        lane_counts[lane["lane_type"]] = lane_counts.get(lane["lane_type"], 0) + 1
        health_counts[lane["health"]] = health_counts.get(lane["health"], 0) + 1
    overall = "blocked" if health_counts.get("fail") else "attention" if health_counts.get("warn") else "ready"
    next_actions = []
    for lane in lanes:
        action = lane.get("next_action")
        if action and lane.get("health") in {"fail", "warn"} and action not in next_actions:
            next_actions.append(action)
    if stuck_tasks and "agentops worker stuck" not in next_actions:
        next_actions.append("agentops worker stuck")
    if stuck_workflow_jobs and "agentops workflow stuck-jobs" not in next_actions:
        next_actions.append("agentops workflow stuck-jobs")
    if not next_actions:
        next_actions = ["agentops worker status", "agentops commander inbox --bucket ready_for_review"]

    return {
        "provider": "agentops-worker",
        "operation": "fleet_view",
        "status": overall,
        "summary": {
            "lane_count": len(lanes),
            "lane_counts": lane_counts,
            "health_counts": health_counts,
            "local_daemon_count": len(daemons),
            "running_local_daemons": len([daemon for daemon in daemons if daemon.get("running")]),
            "remote_worker_count": remote_fleet.get("remote_worker_count", 0),
            "fresh_remote_enrollments": remote_fleet.get("fresh_enrollments", 0),
            "stale_remote_enrollments": remote_fleet.get("stale_enrollments", 0),
            "never_seen_remote_enrollments": remote_fleet.get("never_seen_enrollments", 0),
            "active_remote_sessions": remote_fleet.get("active_sessions", 0),
            "stuck_worker_tasks": len(stuck_tasks),
            "stuck_workflow_jobs": len(stuck_workflow_jobs),
            "recommended_adapter": adapter_readiness.get("recommended_adapter"),
        },
        "lanes": lanes[:80],
        "next_actions": next_actions[:8],
        "contract": "read-only fleet management view; agents execute through Agent Gateway CLI/API and live adapters require explicit confirmation",
        "safety": {
            "read_only": True,
            "live_execution_performed": False,
            "token_omitted": True,
            "session_id_omitted": True,
            "raw_prompt_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }
