"""Shared policy for the bounded operator loop runner."""

from __future__ import annotations

import shlex


ADVANCE_LOOP_POLICY_ID = "advance_loop_local_bounded_v1"
ADVANCE_LOOP_POLICY_VERSION = "2026-06-22"
DENIED_FLAGS = {
    "--confirm-run",
    "--confirm-live",
    "--confirm-create",
    "--confirm-upload",
    "--confirm-delete",
    "--live",
    "--async-job",
}
DENIED_NAMESPACES = {"approval", "session", "enrollment"}
DENIED_MEMORY_ACTIONS = {"approve", "reject"}
DENIED_WORKER_ACTIONS = {"start", "stop", "restart", "release-stuck"}
DENIED_OPERATOR_ACTIONS = {"close-evidence-gap", "propose-receipt-failure-memory"}
ALLOWED_READ_COMMANDS = {
    ("operator", "loop-audit"),
    ("operator", "loop-control"),
    ("operator", "action-plan"),
    ("operator", "handoff"),
    ("operator", "health"),
    ("operator", "runtime-doctor"),
    ("operator", "execution-mode"),
    ("operator", "evidence-report"),
    ("operator", "intake-checklist"),
    ("operator", "remediate-evidence-gap"),
    ("operator", "receipt-failure-memories"),
    ("knowledge", "search"),
    ("review", "queue"),
    ("security", "production-readiness"),
    ("worker", "status"),
    ("worker", "readiness"),
    ("status", ""),
    ("doctor", ""),
}
ALLOWED_MUTATING_COMMANDS = {
    ("knowledge", "index"),
    ("memory", "propose"),
}


def advance_loop_policy_summary() -> dict:
    return {
        "policy_id": ADVANCE_LOOP_POLICY_ID,
        "policy_version": ADVANCE_LOOP_POLICY_VERSION,
        "runner_location": "local_cli",
        "max_actions": 1,
        "allowed_read_commands": sorted([" ".join(item).strip() for item in ALLOWED_READ_COMMANDS]),
        "allowed_mutating_commands": sorted([" ".join(item).strip() for item in ALLOWED_MUTATING_COMMANDS]),
        "special_rules": [
            "memory propose is allowed only when --type loop_record is present",
            "operator remediate-evidence-gap is allowed only as read-only preview; --confirm-create is denied",
            "verify phase accepts read-only allowlisted commands only",
        ],
        "denied_flags": sorted(DENIED_FLAGS),
        "denied_namespaces": sorted(DENIED_NAMESPACES),
        "denied_memory_actions": sorted(DENIED_MEMORY_ACTIONS),
        "denied_worker_actions": sorted(DENIED_WORKER_ACTIONS),
        "denied_operator_actions": sorted(DENIED_OPERATOR_ACTIONS),
        "refuses": [
            "approval decisions",
            "memory approval",
            "worker lifecycle",
            "workflow dispatch",
            "live/confirm flags",
            "external-write paths",
        ],
        "server_executes_shell": False,
        "token_omitted": True,
    }


def advance_loop_command_policy(command: str, *, phase: str) -> dict:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return {
            "allowed": False,
            "reason": f"invalid shell syntax: {exc}",
            "argv": [],
            "policy_id": ADVANCE_LOOP_POLICY_ID,
            "policy_version": ADVANCE_LOOP_POLICY_VERSION,
            "token_omitted": True,
        }
    base = {
        "argv": argv,
        "policy_id": ADVANCE_LOOP_POLICY_ID,
        "policy_version": ADVANCE_LOOP_POLICY_VERSION,
        "phase": phase,
        "token_omitted": True,
    }
    if not argv or argv[0] != "agentops":
        return {**base, "allowed": False, "reason": "command must start with agentops"}
    if any(flag in argv for flag in DENIED_FLAGS):
        return {**base, "allowed": False, "reason": "command contains a confirmation/live/external-write flag", "argv": argv[:4]}
    if len(argv) < 3:
        return {**base, "allowed": False, "reason": "command is too short for bounded runner policy"}
    namespace = argv[1]
    action = argv[2]
    if namespace in DENIED_NAMESPACES:
        return {**base, "allowed": False, "reason": f"{namespace} commands require explicit human/session handling", "argv": argv[:4]}
    if namespace == "memory" and action in DENIED_MEMORY_ACTIONS:
        return {**base, "allowed": False, "reason": "memory approval/rejection remains human-review only", "argv": argv[:4]}
    if namespace == "worker" and action in DENIED_WORKER_ACTIONS:
        return {**base, "allowed": False, "reason": "worker lifecycle commands are outside bounded loop advance", "argv": argv[:4]}
    if namespace == "workflow":
        return {**base, "allowed": False, "reason": "workflow commands can dispatch substantial work and are not auto-run here", "argv": argv[:4]}
    if namespace == "task" and action in {"pull", "claim", "create"}:
        return {**base, "allowed": False, "reason": "task queue mutation is not part of this bounded operator runner", "argv": argv[:4]}
    if namespace == "operator" and action in DENIED_OPERATOR_ACTIONS:
        return {**base, "allowed": False, "reason": f"operator {action} requires a dedicated explicit confirmation path", "argv": argv[:4]}
    key = (namespace, action)
    if phase == "verify":
        if key in ALLOWED_READ_COMMANDS or namespace in {"status", "doctor"}:
            return {**base, "allowed": True, "reason": "read-only verify command is allowlisted"}
        return {**base, "allowed": False, "reason": f"verify command {namespace} {action} is not allowlisted", "argv": argv[:4]}
    if key == ("memory", "propose") and ("--type" not in argv or "loop_record" not in argv):
        return {**base, "allowed": False, "reason": "bounded runner can only auto-propose loop_record memory candidates", "argv": argv[:6]}
    if key in ALLOWED_MUTATING_COMMANDS or key in ALLOWED_READ_COMMANDS:
        return {**base, "allowed": True, "reason": f"{namespace} {action} is allowlisted for bounded loop advance"}
    return {**base, "allowed": False, "reason": f"command {namespace} {action} is not allowlisted", "argv": argv[:4]}
