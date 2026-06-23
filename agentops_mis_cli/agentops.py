#!/usr/bin/env python3
"""
Dependency-free AgentOps MIS CLI wrapper.

This is the v1.4 local agent-facing CLI described in
docs/AGENT_GATEWAY_CLI_SPEC.md. It intentionally keeps auth simple:
environment variables first, then ~/.agentops/config.json. Responses are JSON
so local agents can parse them.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy, advance_loop_policy_summary
from agentops_mis_cli.redaction import redact_text


DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_WORKSPACE_ID = "local-demo"
DEFAULT_REQUEST_TIMEOUT = 30
CONFIG_PATH = Path(os.environ.get("AGENTOPS_CONFIG", "~/.agentops/config.json")).expanduser()


def eprint(*parts):
    print(*parts, file=sys.stderr)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CONFIG_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)


def resolved_context(args) -> dict:
    config = load_config()
    request_timeout_raw = (
        getattr(args, "request_timeout", None)
        or os.environ.get("AGENTOPS_REQUEST_TIMEOUT")
        or config.get("request_timeout")
        or DEFAULT_REQUEST_TIMEOUT
    )
    try:
        request_timeout = max(1, int(request_timeout_raw))
    except (TypeError, ValueError):
        request_timeout = DEFAULT_REQUEST_TIMEOUT
    return {
        "base_url": (getattr(args, "base_url", None) or os.environ.get("AGENTOPS_BASE_URL") or config.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
        "api_key": getattr(args, "api_key", None) if getattr(args, "api_key", None) is not None else os.environ.get("AGENTOPS_API_KEY", config.get("api_key", "")),
        "workspace_id": getattr(args, "workspace_id", None) or os.environ.get("AGENTOPS_WORKSPACE_ID") or config.get("workspace_id") or DEFAULT_WORKSPACE_ID,
        "agent_id": getattr(args, "agent_id", None) or os.environ.get("AGENTOPS_AGENT_ID") or config.get("agent_id") or "",
        "request_timeout": request_timeout,
    }


def context_sources(args, config: dict) -> dict:
    def source_for(flag_name: str, env_name: str, config_key: str, default_value: str = "") -> str:
        value = getattr(args, flag_name, None)
        if value:
            return "flag"
        if os.environ.get(env_name):
            return "env"
        if config.get(config_key):
            return "config"
        return "default" if default_value else "missing"

    return {
        "base_url": source_for("base_url", "AGENTOPS_BASE_URL", "base_url", DEFAULT_BASE_URL),
        "api_key": source_for("api_key", "AGENTOPS_API_KEY", "api_key"),
        "workspace_id": source_for("workspace_id", "AGENTOPS_WORKSPACE_ID", "workspace_id", DEFAULT_WORKSPACE_ID),
        "agent_id": source_for("agent_id", "AGENTOPS_AGENT_ID", "agent_id"),
        "request_timeout": source_for("request_timeout", "AGENTOPS_REQUEST_TIMEOUT", "request_timeout", str(DEFAULT_REQUEST_TIMEOUT)),
    }


def emit(data):
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def parse_json_value(raw: str | None, fallback):
    if raw is None or raw == "":
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {exc}") from exc


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def apply_limit(rows: list[dict], limit: int | None) -> list[dict]:
    if limit is None:
        return rows
    return rows[: max(0, int(limit))]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def cli_truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def cli_deployment_mode() -> str:
    return os.environ.get("AGENTOPS_DEPLOYMENT_MODE", "local").strip().lower() or "local"


def cli_host_is_loopback(url: str) -> bool:
    host = (urlparse(url).hostname or "").strip().lower()
    if host in {"", "localhost", "127.0.0.1", "::1"}:
        return True
    if host in {"0.0.0.0", "::"}:
        return False
    return host.endswith(".localhost")


class AgentOpsClient:
    def __init__(self, context: dict):
        self.base_url = context["base_url"].rstrip("/")
        self.api_key = context["api_key"] or ""
        self.workspace_id = context["workspace_id"]
        self.agent_id = context["agent_id"]
        self.request_timeout = int(context.get("request_timeout") or DEFAULT_REQUEST_TIMEOUT)

    def request(self, method: str, path: str, payload: dict | None = None, query: dict | None = None):
        url = self.base_url + path
        if query:
            url += "?" + urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
        headers = {
            "Content-Type": "application/json",
            "X-AgentOps-Workspace-Id": self.workspace_id,
        }
        if self.agent_id:
            headers["X-AgentOps-Agent-Id"] = self.agent_id
        if self.api_key:
            headers["X-AgentOps-Api-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.request_timeout) as res:
                raw = res.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: {exc.code} {redact_text(detail, 1200)}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach {redact_text(url, 500)}: {redact_text(str(exc.reason), 500)}") from exc

    def get(self, path: str, query: dict | None = None):
        return self.request("GET", path, query=query)

    def post(self, path: str, payload: dict):
        return self.request("POST", path, payload=payload)


def cmd_login(args) -> dict:
    config = load_config()
    api_key = args.api_key if args.api_key is not None else os.environ.get("AGENTOPS_API_KEY", config.get("api_key", ""))
    config.update({
        "base_url": args.base_url or os.environ.get("AGENTOPS_BASE_URL") or config.get("base_url") or DEFAULT_BASE_URL,
        "workspace_id": args.workspace_id or os.environ.get("AGENTOPS_WORKSPACE_ID") or config.get("workspace_id") or DEFAULT_WORKSPACE_ID,
    })
    if args.agent_id or os.environ.get("AGENTOPS_AGENT_ID") or config.get("agent_id"):
        config["agent_id"] = args.agent_id or os.environ.get("AGENTOPS_AGENT_ID") or config.get("agent_id")
    if api_key:
        config["api_key"] = api_key
    save_config(config)
    return {
        "ok": True,
        "config_path": str(CONFIG_PATH),
        "base_url": config["base_url"],
        "workspace_id": config["workspace_id"],
        "agent_id": config.get("agent_id", ""),
        "has_api_key": bool(config.get("api_key")),
    }


def cmd_status(args, client: AgentOpsClient) -> dict:
    return client.get("/api/agent-gateway/status")


def cmd_doctor(args, client: AgentOpsClient) -> dict:
    config = load_config()
    sources = context_sources(args, config)
    checks = []
    gateway = None
    workers = None
    mode = cli_deployment_mode()
    production_requested = mode in {"production", "prod", "shared", "hosted"} or cli_truthy_env("AGENTOPS_REQUIRE_PRODUCTION_SECURITY")
    non_loopback_target = not cli_host_is_loopback(client.base_url)
    has_token = bool(client.api_key)

    deployment_guard_ok = not ((non_loopback_target or production_requested) and not has_token)
    checks.append({
        "name": "shared_deployment_auth_guard",
        "ok": deployment_guard_ok,
        "status": "blocked" if not deployment_guard_ok else "ready",
        "deployment_mode": mode,
        "non_loopback_target": non_loopback_target,
        "has_api_key": has_token,
        "token_omitted": True,
    })

    try:
        gateway = client.get("/api/agent-gateway/status")
        checks.append({
            "name": "agent_gateway_status",
            "ok": gateway.get("status") == "ready",
            "status": gateway.get("status"),
            "auth_mode": (gateway.get("auth") or {}).get("mode"),
            "token_omitted": gateway.get("token_omitted") is True,
        })
    except RuntimeError as exc:
        checks.append({
            "name": "agent_gateway_status",
            "ok": False,
            "error": str(exc),
        })

    try:
        workers = client.get("/api/workers/status")
        checks.append({
            "name": "worker_status",
            "ok": workers.get("status") == "ready",
            "status": workers.get("status"),
            "worker_count": workers.get("worker_count"),
            "running_workers": workers.get("running_workers"),
            "stuck_worker_tasks": workers.get("stuck_worker_tasks"),
        })
    except RuntimeError as exc:
        checks.append({
            "name": "worker_status",
            "ok": False,
            "error": str(exc),
        })

    setup_hints = []
    if not has_token:
        setup_hints.append("No AGENTOPS_API_KEY/config token detected. Local dev may still work, but remote agents should use a scoped enrollment token or short-lived session.")
    if (non_loopback_target or production_requested) and not has_token:
        setup_hints.append("Unsafe shared/production target: configure AGENTOPS_API_KEY or scoped token before using this base URL.")
    if not client.agent_id:
        setup_hints.append("No agent id resolved. Set AGENTOPS_AGENT_ID or run agentops login --agent-id ... before remote worker use.")
    if gateway and not (gateway.get("auth") or {}).get("authenticated") and has_token:
        setup_hints.append("A token was provided but Agent Gateway did not authenticate it; rotate or re-enroll the agent.")
    if workers and workers.get("stuck_worker_tasks", 0):
        setup_hints.append("Stuck worker tasks detected. Run agentops worker stuck and agentops worker release after review.")

    deployment_safety = {
        "deployment_mode": mode,
        "production_requested": production_requested,
        "non_loopback_target": non_loopback_target,
        "ok": deployment_guard_ok,
        "strict_exit_code": 0 if deployment_guard_ok else 2,
        "blocks_unsafe_shared_deployment": not deployment_guard_ok,
        "token_omitted": True,
    }
    return {
        "ok": all(item.get("ok") for item in checks),
        "_exit_code": deployment_safety["strict_exit_code"],
        "command": "agentops doctor",
        "base_url": client.base_url,
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "config_path": str(CONFIG_PATH),
        "config_exists": CONFIG_PATH.exists(),
        "auth": {
            "has_api_key": has_token,
            "api_key_source": sources["api_key"],
            "base_url_source": sources["base_url"],
            "workspace_id_source": sources["workspace_id"],
            "agent_id_source": sources["agent_id"],
            "token_omitted": True,
        },
        "deployment_safety": deployment_safety,
        "checks": checks,
        "gateway": gateway,
        "worker_summary": {
            "status": workers.get("status") if workers else None,
            "worker_count": workers.get("worker_count") if workers else None,
            "running_workers": workers.get("running_workers") if workers else None,
            "pending_worker_tasks": workers.get("pending_worker_tasks") if workers else None,
            "stuck_worker_tasks": workers.get("stuck_worker_tasks") if workers else None,
        },
        "setup_hints": setup_hints,
    }


def cmd_local_readiness(args, client: AgentOpsClient) -> dict:
    return client.get("/api/local/readiness")


def cmd_demo_readiness(args, client: AgentOpsClient) -> dict:
    return client.get("/api/demo/readiness")


def cmd_command_center_overview(args, client: AgentOpsClient) -> dict:
    return client.get("/api/command-center/overview", query={
        "limit": args.limit,
        "project_id": args.project_id or None,
        "threshold_sec": args.threshold_sec,
        "refresh_cache": "true" if args.refresh_cache else None,
    })


def cmd_operator_action_plan(args, client: AgentOpsClient) -> dict:
    return client.get("/api/operator/action-plan", query={"limit": args.limit})


def cmd_operator_action_receipts(args, client: AgentOpsClient) -> dict:
    receipts = client.get("/api/operator/action-receipts", query={"limit": args.limit})
    action_plan = client.get("/api/operator/action-plan", query={"limit": args.plan_limit})
    coverage = action_plan.get("receipt_coverage") or {}
    return {
        **receipts,
        "operation": "operator_action_receipts_cli",
        "receipt_coverage": coverage,
        "action_plan_status": action_plan.get("status"),
        "action_plan_top_commands": action_plan.get("top_commands") or [],
        "contract": "read-only operator action receipt ledger plus action-plan coverage; recording receipts requires explicit POST/UI or agentops operator record-action-receipt --confirm-record",
        "safety": {
            **(receipts.get("safety") or {}),
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "token_omitted": True,
    }


def cmd_operator_record_action_receipt(args, client: AgentOpsClient) -> dict:
    action_command = str(args.action_command or "").strip()
    verify_command = str(args.verify_command or "").strip()
    payload = {
        "workspace_id": client.workspace_id,
        "actor_id": args.actor_id,
        "action_command": action_command,
        "verify_command": verify_command,
        "action_id": args.action_id,
        "action_signature": args.action_signature,
        "source": args.source,
        "status": args.status,
        "result_summary": args.result_summary,
    }
    if not args.confirm_record:
        return {
            "provider": "agentops-operator",
            "operation": "operator_action_receipt_cli_preview",
            "status": "preview",
            "recorded": False,
            "workspace_id": client.workspace_id,
            "payload_preview": {
                **{key: value for key, value in payload.items() if value not in (None, "")},
                "action_command": redact_text(action_command, 500),
                "verify_command": redact_text(verify_command, 500) if verify_command else None,
                "action_hash": hashlib.sha256(action_command.encode("utf-8")).hexdigest() if action_command else None,
                "verify_hash": hashlib.sha256(verify_command.encode("utf-8")).hexdigest() if verify_command else None,
            },
            "next_actions": [
                "rerun this command with --confirm-record to append an audited receipt",
                "agentops operator action-receipts --limit 12",
                "agentops operator loop-audit --limit 20",
            ],
            "contract": "preview-only; does not POST, does not execute action_command or verify_command, and does not mutate the ledger",
            "safety": {
                "read_only": True,
                "ledger_mutated": False,
                "live_execution_performed": False,
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "token_omitted": True,
            },
            "token_omitted": True,
        }
    result = client.post("/api/operator/action-receipts", payload)
    return {
        **result,
        "cli_operation": "operator_record_action_receipt",
        "confirm_record": True,
        "contract": "confirmed append-only receipt record; CLI never executes action_command or verify_command",
        "token_omitted": True,
    }


def cmd_operator_propose_receipt_failure_memory(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "action_hash": args.action_hash,
        "min_failures": args.min_failures,
        "memory_id": args.memory_id,
        "canonical_text": args.canonical_text,
        "actor_id": args.actor_id,
        "confirm_create": bool(args.confirm_create),
    }
    result = client.post(
        "/api/operator/receipt-failure-memories/propose",
        {key: value for key, value in payload.items() if value not in (None, "")},
    )
    return {
        **result,
        "cli_operation": "operator_propose_receipt_failure_memory",
        "confirm_create": bool(args.confirm_create),
        "contract": "preview-only unless --confirm-create is supplied; proposes a memory candidate from repeated failed Action Queue receipt evaluations without executing commands",
        "token_omitted": True,
    }


def cmd_operator_receipt_failure_memories(args, client: AgentOpsClient) -> dict:
    return client.get(
        "/api/operator/receipt-failure-memories",
        query={
            "workspace_id": client.workspace_id,
            "min_failures": args.min_failures,
            "limit": args.limit,
        },
    )


def cmd_operator_loop_audit(args, client: AgentOpsClient) -> dict:
    return client.get("/api/operator/loop-audit", query={"limit": args.limit, "loop_id": args.loop_id or None})


def cmd_operator_loop_control(args, client: AgentOpsClient) -> dict:
    return client.get("/api/operator/loop-control", query={"limit": args.limit, "loop_id": args.loop_id or None})


def cmd_operator_evidence_report(args, client: AgentOpsClient) -> dict:
    return client.get("/api/operator/evidence-report", query={
        "limit": args.limit,
        "run_id": args.run_id,
        "task_id": args.task_id,
    })


def cmd_operator_handoff(args, client: AgentOpsClient) -> dict:
    return client.get("/api/operator/handoff", query={"limit": args.limit, "loop_id": args.loop_id or None})


def cmd_operator_loop_self_check(args, client: AgentOpsClient) -> dict:
    return client.get("/api/operator/loop-self-check", query={"limit": args.limit, "loop_id": args.loop_id or None})


def cmd_operator_health(args, client: AgentOpsClient) -> dict:
    return client.get("/api/operator/health", query={"limit": args.limit, "loop_id": args.loop_id or None})


def cmd_operator_runtime_doctor(args, client: AgentOpsClient) -> dict:
    return client.get(
        "/api/operator/runtime-doctor",
        query={
            "limit": args.limit,
            "loop_id": args.loop_id or None,
            "base_url": args.runtime_base_url or None,
        },
    )


def cmd_operator_live_acceptance(args, client: AgentOpsClient) -> dict:
    return client.get(
        "/api/operator/live-acceptance",
        query={
            "freshness_hours": args.freshness_hours,
            "limit": args.limit,
        },
    )


def cmd_operator_execution_mode(args, client: AgentOpsClient) -> dict:
    return client.get(
        "/api/operator/execution-mode",
        query={
            "adapter": args.adapter,
            "confirm_run": "true" if args.confirm_run else "false",
            "limit": args.limit,
        },
    )


def cmd_operator_command_center(args, client: AgentOpsClient) -> dict:
    return client.get("/api/operator/command-center", query={"limit": args.limit, "project_id": args.project_id or None})


def cmd_operator_intake_checklist(args, client: AgentOpsClient) -> dict:
    return client.get("/api/operator/intake-checklist", query={"limit": args.limit})


def cmd_operator_loop_launch_packet(args, client: AgentOpsClient) -> dict:
    payload = client.get(
        "/api/operator/loop-launch-packet",
        query={
            "limit": args.limit,
            "task_id": args.task_id,
            "agent_id": args.agent_id,
            "q": args.query,
            "handoff_mode": args.handoff_mode,
            "full_handoff": "true" if args.full_handoff else None,
        },
    )
    if args.brief:
        return compact_loop_launch_packet(payload, adapter=args.adapter)
    return payload


def compact_loop_launch_packet(payload: dict, *, adapter: str) -> dict:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    control = payload.get("control_summary") if isinstance(payload.get("control_summary"), dict) else {}
    recommended = control.get("recommended_step") if isinstance(control.get("recommended_step"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    evaluation = payload.get("evaluation_contract") if isinstance(payload.get("evaluation_contract"), dict) else {}
    audit = payload.get("audit_contract") if isinstance(payload.get("audit_contract"), dict) else {}
    agent_plan_draft = payload.get("agent_plan_draft") if isinstance(payload.get("agent_plan_draft"), dict) else {}
    sources = payload.get("sources") if isinstance(payload.get("sources"), dict) else {}
    workflow_recovery = payload.get("workflow_job_recovery") if isinstance(payload.get("workflow_job_recovery"), dict) else {}
    if not workflow_recovery:
        workflow_recovery = sources.get("workflow_job_recovery") if isinstance(sources.get("workflow_job_recovery"), dict) else {}
    if not workflow_recovery:
        handoff = sources.get("handoff") if isinstance(sources.get("handoff"), dict) else {}
        handoff_work_order = handoff.get("work_order") if isinstance(handoff.get("work_order"), dict) else {}
        workflow_recovery = handoff_work_order.get("workflow_job_recovery") if isinstance(handoff_work_order.get("workflow_job_recovery"), dict) else {}
    workflow_recovery_summary = workflow_recovery.get("summary") if isinstance(workflow_recovery.get("summary"), dict) else {}
    workflow_recovery_items = workflow_recovery.get("items") if isinstance(workflow_recovery.get("items"), list) else []
    workflow_recovery_commands = []
    for command in [
        *(workflow_recovery.get("next_actions") if isinstance(workflow_recovery.get("next_actions"), list) else []),
        *(workflow_recovery.get("commands") if isinstance(workflow_recovery.get("commands"), list) else []),
    ]:
        command = str(command or "").strip()
        if command and command not in workflow_recovery_commands:
            workflow_recovery_commands.append(command)
    chain = payload.get("execution_chain") if isinstance(payload.get("execution_chain"), list) else []
    compact_chain = []
    for item in chain:
        if not isinstance(item, dict):
            continue
        compact_chain.append({
            "step_id": item.get("step_id"),
            "phase": item.get("phase"),
            "label": item.get("label"),
            "status": item.get("step_status"),
            "next_safe_command": item.get("next_safe_command") or item.get("command"),
            "verify_command": item.get("verify_command"),
            "receipt_command": item.get("receipt_command"),
            "confirm_required": bool(item.get("confirm_required")),
            "receipt_required": bool(item.get("receipt_required")),
            "source": item.get("source"),
            "token_omitted": item.get("token_omitted", True),
        })
    adapter_command = f"agentops worker preflight --adapter {adapter}"
    live_run_command = (
        "agentops workflow run-task "
        f"--adapter {adapter} "
        f"--confirm-run "
        f"--worker-agent-id <{adapter}_agent_id> "
        "--title '<task title>' "
        "--description '<task description>'"
    ) if adapter in {"hermes", "openclaw"} else (
        "agentops workflow run-task "
        "--adapter mock "
        "--worker-agent-id <mock_agent_id> "
        "--title '<task title>' "
        "--description '<task description>'"
    )
    readback_commands = [
        "agentops task get --task-id <task_id>",
        "agentops run get --run-id <run_id>",
        "agentops plan-evidence list --run-id <run_id>",
        "agentops operator loop-audit --limit 20",
        "agentops operator action-receipts --limit 20",
    ]
    return {
        "provider": payload.get("provider", "agentops-operator"),
        "operation": "operator_loop_launch_brief",
        "source_operation": payload.get("operation", "operator_loop_launch_packet"),
        "status": payload.get("status", "unknown"),
        "workspace_id": payload.get("workspace_id"),
        "task_id": payload.get("task_id"),
        "agent_id": payload.get("agent_id"),
        "adapter": adapter,
        "method": payload.get("method"),
        "summary": {
            "handoff_mode": summary.get("handoff_mode"),
            "control_status": control.get("status") or summary.get("control_status"),
            "control_mode": control.get("mode") or summary.get("control_mode"),
            "recommended_step": recommended.get("step_id") or summary.get("recommended_step"),
            "recommended_label": recommended.get("label"),
            "requires_human": bool(control.get("requires_human")),
            "requires_receipt": bool(control.get("requires_receipt")),
            "execution_chain_steps": len(compact_chain),
            "blocking_steps": control.get("blocking_steps") or [],
            "attention_steps": control.get("attention_steps") or [],
            "required_ledgers": evaluation.get("required_ledgers") or [],
            "agent_plan_risk": agent_plan_draft.get("risk_level"),
            "agent_plan_approval_required": bool(agent_plan_draft.get("approval_required")),
            "workflow_job_recovery_status": workflow_recovery.get("status"),
            "workflow_job_recovery_items": workflow_recovery_summary.get("items"),
            "workflow_job_recovery_stuck_jobs": workflow_recovery_summary.get("stuck_jobs"),
            "workflow_job_recovery_retryable_failed_jobs": workflow_recovery_summary.get("retryable_failed_jobs"),
            "workflow_job_recovery_receipt_missing": workflow_recovery_summary.get("receipt_missing"),
        },
        "next_command": control.get("next_command") or recommended.get("command"),
        "verify_command": control.get("verify_command") or recommended.get("verify_command"),
        "receipt_command": control.get("receipt_command") or recommended.get("receipt_command"),
        "adapter_preflight_command": adapter_command,
        "live_run_command": live_run_command,
        "readback_commands": readback_commands,
        "runtime_doctor_command": "agentops operator runtime-doctor --limit 8",
        "workflow_job_recovery": {
            "operation": workflow_recovery.get("operation"),
            "status": workflow_recovery.get("status"),
            "summary": workflow_recovery_summary,
            "next_actions": workflow_recovery.get("next_actions") or [],
            "commands": workflow_recovery_commands[:8],
            "items": [
                {
                    "job_id": item.get("job_id"),
                    "mode": item.get("mode"),
                    "status": item.get("status"),
                    "preview_command": item.get("preview_command"),
                    "confirm_command": item.get("confirm_command"),
                    "verify_command": item.get("verify_command"),
                    "receipt_verify_record_command": item.get("receipt_verify_record_command"),
                    "receipt_state": item.get("receipt_state") or {},
                    "token_omitted": True,
                }
                for item in workflow_recovery_items[:3]
                if isinstance(item, dict)
            ],
            "contract": "compact recover-job work order projection; preview first, confirm only with --confirm-recover, then record/verify receipt",
            "token_omitted": True,
        },
        "execution_chain": compact_chain,
        "policy": {
            "policy_id": control.get("policy_id") or (audit.get("bounded_runner") or {}).get("policy_id"),
            "server_executes_shell": bool(control.get("server_executes_shell") or (audit.get("bounded_runner") or {}).get("server_executes_shell")),
            "live_execution_requires_confirm_run": adapter in {"hermes", "openclaw"},
            "external_writes_require_prepared_action": adapter in {"hermes", "openclaw"},
            "copy_only": control.get("copy_only", True) is not False,
        },
        "safety": {
            "read_only": bool(safety.get("read_only", True)),
            "ledger_mutated": bool(safety.get("ledger_mutated")),
            "live_execution_performed": bool(safety.get("live_execution_performed")),
            "raw_prompt_omitted": bool(safety.get("raw_prompt_omitted", True)),
            "raw_response_omitted": bool(safety.get("raw_response_omitted", True)),
            "token_omitted": bool(safety.get("token_omitted", True)),
        },
        "commands": [
            adapter_command,
            "agentops operator loop-control --limit 8",
            "agentops operator advance-loop --fast-control --limit 8",
            live_run_command,
            *readback_commands,
            *workflow_recovery_commands[:6],
        ],
        "contract": "compact copy-only launch brief for Hermes/OpenClaw/Codex; derived from loop-launch-packet without mutating ledgers, executing runtimes, or exposing raw prompts/responses/tokens",
        "token_omitted": True,
        "live_execution_performed": False,
    }


def cmd_operator_advance_loop_policy(args, client: AgentOpsClient) -> dict:
    sample_commands = [
        "agentops memory propose --type loop_record --text example --agent-id agt_example",
        "agentops memory approve --memory-id mem_example",
        "agentops workflow hermes-openclaw-loop --loop-id loop_example",
        "agentops operator loop-audit --limit 10",
    ]
    samples = [
        {"command": command, "action_decision": advance_loop_command_policy(command, phase="action")}
        for command in sample_commands
    ]
    return {
        "provider": "agentops-operator",
        "operation": "operator_advance_loop_policy",
        "policy": advance_loop_policy_summary(),
        "samples": samples,
        "contract": "read-only bounded runner policy; does not execute commands or mutate ledgers",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "token_omitted": True,
    }


def agentops_cli_command(argv: list[str], client: AgentOpsClient) -> tuple[list[str], dict]:
    repo_cli = Path(__file__).resolve().parents[1] / "scripts" / "agentops"
    cli_entry = Path(sys.argv[0])
    if repo_cli.exists():
        executable = str(repo_cli)
    elif cli_entry.exists() and os.access(cli_entry, os.X_OK):
        executable = str(cli_entry)
    else:
        executable = "agentops"
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = client.base_url
    env["AGENTOPS_WORKSPACE_ID"] = client.workspace_id
    if client.agent_id:
        env["AGENTOPS_AGENT_ID"] = client.agent_id
    if client.api_key:
        env["AGENTOPS_API_KEY"] = client.api_key
    return [executable, "--base-url", client.base_url, *argv[1:]], env


def run_bounded_agentops_command(command: str, client: AgentOpsClient, *, timeout: int) -> dict:
    policy = advance_loop_command_policy(command, phase="action")
    if not policy.get("allowed"):
        return {
            "ok": False,
            "blocked": True,
            "policy": policy,
            "returncode": None,
            "stdout_summary": None,
            "stderr_summary": policy.get("reason"),
            "raw_output_omitted": True,
            "token_omitted": True,
        }
    argv, env = agentops_cli_command(policy["argv"], client)
    proc = subprocess.run(argv, cwd=Path.cwd(), env=env, capture_output=True, text=True, timeout=timeout, check=False)
    return {
        "ok": proc.returncode == 0,
        "blocked": False,
        "policy": {**policy, "argv": policy.get("argv", [])[:4]},
        "returncode": proc.returncode,
        "stdout_summary": redact_text(proc.stdout, 600) if proc.stdout else None,
        "stderr_summary": redact_text(proc.stderr, 600) if proc.stderr else None,
        "raw_output_omitted": True,
        "token_omitted": True,
    }


def select_advance_loop_item(handoff: dict) -> dict:
    work_order = handoff.get("work_order") or {}
    advance_loop = work_order.get("advance_loop") or {}
    selected = advance_loop.get("selected_item") or {}
    command = str(selected.get("action_command") or "").strip()
    if command:
        policy = advance_loop_command_policy(command, phase="action")
        if policy.get("allowed"):
            return {**selected, "advance_policy": policy}
    evidence_work_order = work_order.get("evidence_report") or {}
    evidence_status = str(evidence_work_order.get("status") or "").lower()
    evidence_receipt_state = evidence_work_order.get("receipt_state") or {}
    if not handoff.get("loop_id") and not evidence_receipt_state.get("verified") and evidence_status in {"blocked", "attention"}:
        for command in evidence_work_order.get("next_actions") or []:
            command = str(command or "").strip()
            if not command:
                continue
            policy = advance_loop_command_policy(command, phase="action")
            if not policy.get("allowed"):
                continue
            return {
                "package_id": "operator_evidence_report_work_order",
                "action_id": str(evidence_work_order.get("action_id") or "operator_evidence_report_work_order"),
                "action_signature": evidence_work_order.get("action_signature"),
                "gate_id": "evidence_report",
                "gate_label": "Run evidence report",
                "gate_status": evidence_status,
                "source": "operator_handoff.evidence_report",
                "action_command": command,
                "verify_command": "agentops operator handoff --limit 12",
                "receipt_verify_record_command": None,
                "evidence": {
                    "summary": evidence_work_order.get("summary") or {},
                    "runs": len(evidence_work_order.get("runs") or []),
                    "operation": evidence_work_order.get("operation"),
                    "receipt_state": evidence_receipt_state,
                },
                "advance_policy": policy,
                "token_omitted": True,
            }
    remediation_chain = evidence_work_order.get("remediation_chain") or {}
    if not handoff.get("loop_id") and remediation_chain.get("status") == "attention":
        for item in remediation_chain.get("items") or []:
            receipt_state = item.get("receipt_state") or {}
            if receipt_state.get("verified"):
                continue
            command = str(item.get("preview_command") or "").strip()
            if not command:
                continue
            policy = advance_loop_command_policy(command, phase="action")
            if not policy.get("allowed"):
                continue
            run_id = str(item.get("run_id") or "").strip()
            return {
                "package_id": str(item.get("package_id") or f"evidence_remediation:{run_id}" or "evidence_remediation"),
                "action_id": str(item.get("action_id") or f"evidence_remediation:{run_id}" or "evidence_remediation"),
                "action_signature": receipt_state.get("action_signature"),
                "gate_id": "evidence_remediation",
                "gate_label": "Evidence remediation preview",
                "gate_status": item.get("severity") or item.get("status") or remediation_chain.get("status"),
                "source": "operator_handoff.evidence_remediation",
                "action_command": command,
                "verify_command": item.get("verify_command") or (f"agentops operator evidence-report --run-id {run_id} --limit 1" if run_id else "agentops operator evidence-report --limit 8"),
                "receipt_verify_record_command": item.get("receipt_verify_record_command"),
                "receipt_source": "handoff.evidence_remediation",
                "evidence": {
                    "run_id": run_id,
                    "task_id": item.get("task_id"),
                    "failed_check_ids": item.get("failed_check_ids") or [],
                    "gap_types": item.get("gap_types") or [],
                    "missing_evidence": item.get("missing_evidence") or [],
                    "receipt_state": receipt_state,
                    "operation": item.get("operation"),
                },
                "advance_policy": policy,
                "token_omitted": True,
            }
    action_package = (work_order.get("action_package") or {})
    for item in action_package.get("items") or []:
        command = str(item.get("action_command") or "").strip()
        if not command:
            continue
        if item.get("gate_status") == "pass":
            continue
        policy = advance_loop_command_policy(command, phase="action")
        if policy.get("allowed"):
            return {**item, "advance_policy": policy}
    return {}


def compact_loop_control(payload: dict) -> dict:
    control = payload.get("control_summary") or {}
    step = control.get("recommended_step") or {}
    return {
        "operation": control.get("operation"),
        "status": control.get("status"),
        "mode": control.get("mode"),
        "selected_gate": control.get("selected_gate") or step.get("selected_gate"),
        "selected_status": control.get("selected_status"),
        "next_command": control.get("next_command") or step.get("command"),
        "verify_command": control.get("verify_command") or step.get("verify_command"),
        "receipt_command": control.get("receipt_command") or step.get("receipt_command"),
        "requires_human": control.get("requires_human"),
        "requires_receipt": control.get("requires_receipt"),
        "server_executes_shell": control.get("server_executes_shell"),
        "copy_only": control.get("copy_only"),
        "policy_id": control.get("policy_id") or step.get("policy_id"),
        "read_model_cache": payload.get("read_model_cache") or {},
        "token_omitted": True,
    }


def cmd_operator_advance_loop(args, client: AgentOpsClient) -> dict:
    control_endpoint = "/api/operator/loop-control" if args.fast_control else "/api/operator/handoff"
    handoff = client.get(control_endpoint, query={"limit": args.limit, "loop_id": args.loop_id or None})
    before_control = compact_loop_control(handoff)
    selected = select_advance_loop_item(handoff)
    policy_summary = advance_loop_policy_summary()
    if not selected:
        return {
            "provider": "agentops-operator",
            "operation": "operator_advance_loop",
            "status": "empty",
            "advanced": False,
            "message": "No allowlisted non-passing loop action is available in the handoff action package.",
            "handoff_status": handoff.get("status"),
            "control_readback": {
                "before": before_control,
                "after": None,
                "token_omitted": True,
            },
            "policy": policy_summary,
            "safety": {
                "read_only": True,
                "ledger_mutated": False,
                "live_execution_performed": False,
                "token_omitted": True,
            },
            "token_omitted": True,
        }
    action_command = str(selected.get("action_command") or "")
    verify_command = str(selected.get("verify_command") or "")
    verify_policy = advance_loop_command_policy(verify_command, phase="verify") if verify_command else {"allowed": True, "reason": "no verify command supplied", "argv": [], "token_omitted": True}
    preview = {
        "package_id": selected.get("package_id"),
        "gate_id": selected.get("gate_id"),
        "source": selected.get("source"),
        "gate_status": selected.get("gate_status"),
        "action_command": redact_text(action_command, 500),
        "verify_command": redact_text(verify_command, 500) if verify_command else None,
        "evidence": selected.get("evidence") or {},
        "action_policy": selected.get("advance_policy") or {},
        "verify_policy": verify_policy,
        "receipt_status_on_success": "verified",
        "receipt_status_on_failure": "failed",
        "token_omitted": True,
    }
    if not args.confirm_advance:
        return {
            "provider": "agentops-operator",
            "operation": "operator_advance_loop",
            "status": "preview",
            "advanced": False,
            "preview": preview,
            "control_readback": {
                "before": before_control,
                "after": None,
                "token_omitted": True,
            },
            "policy": policy_summary,
            "next_actions": ["rerun with --confirm-advance to execute exactly one allowlisted loop action"],
            "contract": "preview-only; does not execute commands and does not mutate ledgers without --confirm-advance",
            "safety": {
                "read_only": True,
                "ledger_mutated": False,
                "live_execution_performed": False,
                "token_omitted": True,
            },
            "token_omitted": True,
        }
    if not verify_policy.get("allowed"):
        return {
            "provider": "agentops-operator",
            "operation": "operator_advance_loop",
            "status": "blocked",
            "advanced": False,
            "preview": preview,
            "policy": policy_summary,
            "message": "Verify command failed bounded-runner policy.",
            "control_readback": {
                "before": before_control,
                "after": None,
                "token_omitted": True,
            },
            "safety": {
                "read_only": True,
                "ledger_mutated": False,
                "live_execution_performed": False,
                "token_omitted": True,
            },
            "token_omitted": True,
        }
    action_result = run_bounded_agentops_command(action_command, client, timeout=args.timeout)
    verify_result = None
    if action_result.get("ok") and verify_command:
        verify_policy_payload = advance_loop_command_policy(verify_command, phase="verify")
        argv, env = agentops_cli_command(verify_policy_payload["argv"], client)
        proc = subprocess.run(argv, cwd=Path.cwd(), env=env, capture_output=True, text=True, timeout=args.timeout, check=False)
        verify_result = {
            "ok": proc.returncode == 0,
            "policy": {**verify_policy_payload, "argv": verify_policy_payload.get("argv", [])[:4]},
            "returncode": proc.returncode,
            "stdout_summary": redact_text(proc.stdout, 600) if proc.stdout else None,
            "stderr_summary": redact_text(proc.stderr, 600) if proc.stderr else None,
            "raw_output_omitted": True,
            "token_omitted": True,
        }
    succeeded = bool(action_result.get("ok")) and (verify_result is None or bool(verify_result.get("ok")))
    receipt_payload = {
        "workspace_id": client.workspace_id,
        "actor_id": args.actor_id,
        "action_command": action_command,
        "verify_command": verify_command,
        "action_id": selected.get("action_id"),
        "action_signature": selected.get("action_signature"),
        "source": selected.get("receipt_source") or f"advance_loop:{selected.get('gate_id') or 'gate'}",
        "status": "verified" if succeeded else "failed",
        "result_summary": (
            f"advance-loop {'verified' if succeeded else 'failed'} gate {selected.get('gate_id') or 'unknown'}; "
            f"action_rc={action_result.get('returncode')} verify_rc={(verify_result or {}).get('returncode')}"
        ),
    }
    receipt = client.post("/api/operator/action-receipts", receipt_payload)
    refresh_query = {"limit": args.limit, "loop_id": args.loop_id or None, "refresh_cache": "true"}
    if args.fast_control:
        after_handoff = client.get("/api/operator/loop-control", query=refresh_query)
        after_self_check = after_handoff
    else:
        after_handoff = client.get("/api/operator/handoff", query=refresh_query)
        after_self_check = client.get("/api/operator/loop-self-check", query=refresh_query)
    control_readback = {
        "before": before_control,
        "after": compact_loop_control(after_handoff),
        "after_self_check": compact_loop_control(after_self_check),
        "refresh_cache_requested": True,
        "cache_bypassed": (
            ((after_handoff.get("read_model_cache") or {}).get("status") in {"bypass", "not_cached"})
            and ((after_self_check.get("read_model_cache") or {}).get("status") in {"bypass", "not_cached"})
        ),
        "token_omitted": True,
    }
    receipt_id = ((receipt.get("receipt") or {}).get("receipt_id") or receipt.get("receipt_id"))
    control_readback_receipt = None
    if receipt_id:
        control_readback_receipt = client.post("/api/operator/action-receipts/control-readback", {
            "workspace_id": client.workspace_id,
            "actor_id": args.actor_id,
            "receipt_id": receipt_id,
            "source": f"advance_loop:{selected.get('gate_id') or 'gate'}:control_readback",
            "control_readback": control_readback,
        })
    return {
        "provider": "agentops-operator",
        "operation": "operator_advance_loop",
        "status": "advanced" if succeeded else "failed",
        "control_source": "loop_control" if args.fast_control else "handoff",
        "advanced": True,
        "confirm_advance": True,
        "preview": preview,
        "policy": policy_summary,
        "action_result": action_result,
        "verify_result": verify_result,
        "receipt": receipt,
        "control_readback": control_readback,
        "control_readback_receipt": control_readback_receipt,
        "contract": "bounded CLI runner; executes at most one allowlisted local agentops action, verifies it, and records an append-only receipt; never approves memory or runs live/workflow commands",
        "safety": {
            "read_only": False,
            "ledger_mutated": True,
            "live_execution_performed": False,
            "raw_output_omitted": True,
            "token_omitted": True,
        },
        "token_omitted": True,
    }


def cmd_operator_remediate_evidence_gap(args, client: AgentOpsClient) -> dict:
    return client.post("/api/operator/execution-evidence/remediation-task", {
        "workspace_id": client.workspace_id,
        "run_id": args.run_id,
        "task_id": args.task_id,
        "title": args.title,
        "project_id": args.project_id,
        "plan_id": args.plan_id,
        "lane_id": args.lane_id,
        "owner_agent_id": args.owner_agent_id,
        "priority": args.priority,
        "risk_level": args.risk_level,
        "budget_limit_usd": args.budget_limit_usd,
        "actor_id": args.actor_id,
        "confirm_create": bool(args.confirm_create),
    })


def cmd_operator_close_evidence_gap(args, client: AgentOpsClient) -> dict:
    return client.post("/api/operator/execution-evidence/close-gap", {
        "workspace_id": client.workspace_id,
        "run_id": args.run_id,
        "decision": args.decision,
        "reason": args.reason or args.note,
        "synthesis_artifact_id": args.synthesis_artifact_id,
        "remediation_task_id": args.remediation_task_id,
        "actor_id": args.actor_id,
        "confirm_close": bool(args.confirm_close),
    })


def cmd_commander_board(args, client: AgentOpsClient) -> dict:
    return client.get("/api/commander/project-board", query={
        "project_id": getattr(args, "project_id", None),
        "plan_id": getattr(args, "plan_id", None),
        "limit": getattr(args, "limit", None),
    })


def cmd_commander_repo_map(args, client: AgentOpsClient) -> dict:
    query = args.query_flag if getattr(args, "query_flag", None) is not None else args.query
    return client.get("/api/commander/repo-map", query={
        "q": query,
        "limit": args.limit,
        "char_budget": args.char_budget,
    })


def cmd_commander_coding_template(args, client: AgentOpsClient) -> dict:
    query = args.query_flag if getattr(args, "query_flag", None) is not None else args.query
    return client.get("/api/commander/coding-project-template", query={
        "q": query,
        "project_id": args.project_id,
        "task_id": args.task_id,
        "limit": args.limit,
        "char_budget": args.char_budget,
    })


def cmd_commander_inbox(args, client: AgentOpsClient) -> dict:
    query = {}
    if getattr(args, "bucket", None):
        query["bucket"] = args.bucket
    if getattr(args, "limit", None) is not None:
        query["limit"] = str(args.limit)
    if getattr(args, "threshold_sec", None) is not None:
        query["threshold_sec"] = str(args.threshold_sec)
    path = "/api/commander/integration-inbox"
    if query:
        path = f"{path}?{urlencode(query)}"
    return client.get(path)


def cmd_commander_plan(args, client: AgentOpsClient) -> dict:
    lanes = parse_json_value(args.lanes_json, None) if getattr(args, "lanes_json", None) else None
    payload = {
        "workspace_id": client.workspace_id,
        "project_id": args.project_id,
        "plan_id": args.plan_id,
        "goal": args.goal,
        "max_packages": args.max_packages,
        "confirm_create": bool(args.confirm_create),
        "task_id_prefix": args.task_id_prefix,
    }
    if lanes is not None:
        payload["lanes"] = lanes
    return client.post("/api/commander/work-packages/plan", payload)


def cmd_commander_packages(args, client: AgentOpsClient) -> dict:
    query = {
        "project_id": args.project_id,
        "plan_id": args.plan_id,
        "status": args.status,
        "limit": args.limit,
    }
    return client.get("/api/commander/work-packages", query=query)


def cmd_commander_dispatch_package(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "adapter": args.adapter,
        "confirm_run": bool(args.confirm_run),
        "worker_agent_id": args.worker_agent_id,
        "hermes_timeout": args.hermes_timeout,
    }
    return client.post(f"/api/commander/work-packages/{args.task_id}/dispatch", payload)


def cmd_commander_coding_evidence(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "run_id": args.run_id,
        "branch": args.branch,
        "collect_from_worktree": bool(args.collect_from_worktree),
        "worktree_root": args.worktree_root,
        "worktree_path": args.worktree_path,
        "confirm_record": bool(args.confirm_record),
        "patch_summary": args.patch_summary,
        "test_summary": args.test_summary,
        "verifier_summary": args.verifier_summary,
        "merge_summary": args.merge_summary,
        "test_status": args.test_status,
        "verifier_status": args.verifier_status,
        "merge_gate_status": args.merge_gate_status,
        "changed_files": args.changed_file or [],
        "verification_commands": args.verification_command or [],
        "actor_id": args.actor_id,
    }
    return client.post(f"/api/commander/work-packages/{args.task_id}/coding-evidence", payload)


def cmd_commander_coding_workspace(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "branch": args.branch,
        "worktree_root": args.worktree_root,
        "worktree_path": args.worktree_path,
        "confirm_create": bool(args.confirm_create),
        "actor_id": args.actor_id,
    }
    return client.post(f"/api/commander/work-packages/{args.task_id}/coding-workspace", payload)


def cmd_commander_coding_workspace_cleanup(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "branch": args.branch,
        "worktree_root": args.worktree_root,
        "worktree_path": args.worktree_path,
        "delete_branch": not bool(args.keep_branch),
        "confirm_cleanup": bool(args.confirm_cleanup),
        "actor_id": args.actor_id,
    }
    return client.post(f"/api/commander/work-packages/{args.task_id}/coding-workspace/cleanup", payload)


def cmd_commander_dispatch_batch(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "project_id": args.project_id,
        "plan_id": args.plan_id,
        "task_ids": args.task_id or [],
        "status": args.status,
        "limit": args.limit,
        "adapter": args.adapter,
        "confirm_run": bool(args.confirm_run),
        "hermes_timeout": args.hermes_timeout,
    }
    return client.post("/api/commander/work-packages/dispatch-batch", payload)


def cmd_commander_synthesize(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "project_id": args.project_id,
        "plan_id": args.plan_id,
        "task_ids": args.task_id or [],
        "status": args.status,
        "limit": args.limit,
        "confirm_create": bool(args.confirm_create),
        "artifact_id": args.artifact_id,
    }
    return client.post("/api/commander/work-packages/synthesize", payload)


def cmd_commander_promote_synthesis(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "artifact_id": args.artifact_id,
        "approval_id": args.approval_id,
        "mode": args.mode,
        "confirm_promote": bool(args.confirm_promote),
        "project_id": args.project_id,
        "memory_id": args.memory_id,
        "delivery_artifact_id": args.delivery_artifact_id,
    }
    return client.post("/api/commander/work-packages/synthesis/promote", payload)


def cmd_review_queue(args, client: AgentOpsClient) -> dict:
    return client.get("/api/agent-gateway/review/queue", query={"limit": args.limit})


def cmd_security_production_readiness(args, client: AgentOpsClient) -> dict:
    return client.get("/api/security/production-readiness")


def cmd_agent_register(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.id or client.agent_id,
        "name": args.name,
        "role": args.role,
        "runtime_type": args.runtime,
        "model_provider": args.model_provider,
        "model_name": args.model_name,
        "permission_level": args.permission_level,
        "allowed_tools": split_csv(args.allowed_tools),
        "budget_limit_usd": args.budget,
        "description": args.description,
    }
    return client.post("/api/agent-gateway/register", payload)


def cmd_agent_heartbeat(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.id or client.agent_id,
        "status": args.status,
        "summary": args.summary,
        "runtime_type": args.runtime,
    }
    return client.post("/api/agent-gateway/heartbeat", payload)


def cmd_task_pull(args, client: AgentOpsClient) -> dict:
    query = {
        "agent_id": args.agent_id or client.agent_id,
        "workspace_id": client.workspace_id,
        "limit": args.limit,
        "status": args.status,
        "enforce_intake": "true" if args.enforce_intake else None,
        "task_id": args.task_id,
    }
    return client.get("/api/agent-gateway/tasks/pull", query=query)


def cmd_task_create(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "task_id": args.task_id,
        "title": args.title,
        "description": args.description,
        "requester_id": args.requester_id,
        "owner_agent_id": args.owner_agent_id or client.agent_id,
        "collaborator_agent_ids": args.collaborator_agent_id or [],
        "status": args.status,
        "priority": args.priority,
        "due_date": args.due_date,
        "acceptance_criteria": args.acceptance,
        "risk_level": args.risk,
        "budget_limit_usd": args.budget,
    }
    return client.post("/api/agent-gateway/tasks", payload)


def cmd_task_list(args, client: AgentOpsClient) -> dict:
    query = {
        "limit": args.limit,
        "status": args.status,
        "owner_agent_id": args.owner_agent_id,
        "requester_id": args.requester_id,
    }
    return client.get("/api/agent-gateway/tasks", query=query)


def cmd_task_get(args, client: AgentOpsClient) -> dict:
    payload = client.get(f"/api/agent-gateway/tasks/{args.task_id}")
    return {
        "provider": payload.get("provider") or "agentops-mis",
        "operation": "task_get",
        "task_id": args.task_id,
        "task": payload.get("task"),
        "runs": payload.get("runs") or [],
        "approvals": payload.get("approvals") or [],
        "evaluations": payload.get("evaluations") or [],
        "memories": payload.get("memories") or [],
        "artifacts": payload.get("artifacts") or [],
        "evidence": {
            "runs": len(payload.get("runs") or []),
            "approvals": len(payload.get("approvals") or []),
            "evaluations": len(payload.get("evaluations") or []),
            "memories": len(payload.get("memories") or []),
            "artifacts": len(payload.get("artifacts") or []),
        },
        "token_omitted": True,
    }


def cmd_task_claim(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id or client.agent_id,
        "runtime_type": args.runtime,
    }
    return client.post(f"/api/agent-gateway/tasks/{args.task_id}/claim", payload)


def cmd_run_start(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id or client.agent_id,
        "task_id": args.task_id,
        "runtime_type": args.runtime,
        "input_summary": args.input_summary,
        "delegation_id": args.delegation_id,
        "parent_run_id": args.parent_run_id,
        "approval_required": args.approval_required,
        "agent_plan_id": args.plan_id,
    }
    return client.post("/api/agent-gateway/runs/start", payload)


def cmd_run_list(args, client: AgentOpsClient) -> dict:
    query = {
        "task_id": args.task_id,
        "agent_id": args.agent_id,
        "status": args.status,
        "limit": args.limit,
    }
    return client.get("/api/agent-gateway/runs", query=query)


def cmd_run_get(args, client: AgentOpsClient) -> dict:
    payload = client.get(f"/api/agent-gateway/runs/{args.run_id}")
    return {
        "provider": payload.get("provider") or "agentops-mis",
        "operation": "run_get",
        "run_id": args.run_id,
        "run": payload.get("run"),
        "tool_calls": payload.get("tool_calls") or [],
        "approvals": payload.get("approvals") or [],
        "evaluations": payload.get("evaluations") or [],
        "artifacts": payload.get("artifacts") or [],
        "evidence": {
            "tool_calls": len(payload.get("tool_calls") or []),
            "approvals": len(payload.get("approvals") or []),
            "evaluations": len(payload.get("evaluations") or []),
            "artifacts": len(payload.get("artifacts") or []),
        },
        "token_omitted": True,
    }


def cmd_run_graph(args, client: AgentOpsClient) -> dict:
    payload = client.get(f"/api/agent-gateway/runs/{args.run_id}/graph")
    payload["provider"] = payload.get("provider") or "agentops-mis"
    payload["operation"] = "run_graph"
    payload["token_omitted"] = True
    return payload


def cmd_run_heartbeat(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "status": args.status,
        "output_summary": args.summary,
        "duration_ms": args.duration_ms,
        "output_tokens": args.output_tokens,
        "cost_usd": args.cost,
        "error_type": args.error_type,
        "error_message": args.error_message,
    }
    return client.post(f"/api/agent-gateway/runs/{args.run_id}/heartbeat", payload)


def cmd_runtime_connectors(args, client: AgentOpsClient) -> dict:
    return {
        "provider": "agentops-runtime",
        "operation": "runtime_connectors",
        "connectors": client.get("/api/runtime-connectors"),
        "contract": "read-only runtime connector manifest and trust registry view; use worker readiness for route selection and prepared actions for high-risk live side effects",
        "live_execution_performed": False,
        "token_omitted": True,
    }


def cmd_runtime_event_record(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id or client.agent_id,
        "run_id": args.run_id,
        "adapter": args.adapter,
        "runtime_connector_id": args.connector_id,
        "event_type": args.event_type,
        "status": args.status,
        "input_summary": args.input_summary,
        "output_summary": args.output_summary or args.summary,
        "error_message": args.error_message,
        "latency_ms": args.latency_ms,
        "model_name": args.model,
        "prompt_hash": args.prompt_hash,
        "raw_payload_hash": args.payload_hash,
        "payload": parse_json_value(args.payload_json, None) if args.payload_json else None,
        "metadata": parse_json_value(args.metadata_json, {}) if args.metadata_json else {},
        "source": args.source,
    }
    return client.post("/api/agent-gateway/runtime-events", payload)


def cmd_toolcall_record(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "run_id": args.run_id,
        "agent_id": args.agent_id or client.agent_id,
        "tool_name": args.tool,
        "tool_category": args.category,
        "risk_level": args.risk,
        "status": args.status,
        "target_resource": args.target,
        "args": parse_json_value(args.args_json, {"summary": args.args_summary or "redacted"}),
        "result_summary": args.summary,
        "prepare_action": bool(args.prepare_action),
        "action_type": args.action_type,
        "policy_version": args.policy_version,
        "checkpoint": parse_json_value(args.checkpoint_json, {}),
        "idempotency_key": args.idempotency_key,
        "approval_reason": args.approval_reason,
        "approver_user_id": args.approver,
    }
    return client.post("/api/agent-gateway/tool-calls", payload)


def cmd_artifact_record(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "run_id": args.run_id,
        "task_id": args.task_id,
        "agent_id": args.agent_id or client.agent_id,
        "artifact_id": args.artifact_id,
        "artifact_type": args.type,
        "title": args.title,
        "uri": args.uri,
        "summary": args.summary,
        "content_hash": args.content_hash,
    }
    return client.post("/api/agent-gateway/artifacts", payload)


def cmd_artifact_list(args, client: AgentOpsClient) -> dict:
    query = {
        "task_id": args.task_id,
        "run_id": args.run_id,
        "type": args.type,
        "limit": args.limit,
    }
    return client.get("/api/agent-gateway/artifacts", query=query)


def cmd_knowledge_search(args, client: AgentOpsClient) -> dict:
    return client.get("/api/agent-gateway/knowledge/search", query={
        "q": args.query,
        "limit": args.limit,
        "refresh": "true" if args.refresh else None,
    })


def cmd_knowledge_index(args, client: AgentOpsClient) -> dict:
    return client.post("/api/agent-gateway/knowledge/index", {"rebuild": bool(args.rebuild)})


def cmd_agent_plan_create(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id or client.agent_id,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "task_understanding": args.task_understanding,
        "referenced_specs": split_csv(args.referenced_specs),
        "referenced_memories": split_csv(args.referenced_memories),
        "referenced_bases": split_csv(args.referenced_bases),
        "proposed_files_to_change": split_csv(args.proposed_files_to_change),
        "risk_level": args.risk,
        "approval_required": bool(args.approval_required),
        "execution_steps": parse_json_value(args.execution_steps_json, split_csv(args.execution_steps)),
        "verification_plan": args.verification_plan,
        "rollback_plan": args.rollback_plan,
        "status": args.status,
    }
    return client.post("/api/agent-gateway/agent-plans", payload)


def cmd_agent_plan_list(args, client: AgentOpsClient) -> dict:
    return client.get("/api/agent-gateway/agent-plans", query={
        "task_id": args.task_id,
        "run_id": args.run_id,
        "agent_id": args.agent_id,
        "limit": args.limit,
    })


def cmd_agent_plan_get(args, client: AgentOpsClient) -> dict:
    return client.get(f"/api/agent-gateway/agent-plans/{args.plan_id}")


def cmd_agent_plan_verify(args, client: AgentOpsClient) -> dict:
    return client.get(f"/api/agent-gateway/agent-plans/{args.plan_id}/verify")


def cmd_agent_plan_approve(args, client: AgentOpsClient) -> dict:
    return client.post(f"/api/agent-plans/{args.plan_id}/approve", {
        "workspace_id": client.workspace_id,
        "approver_user_id": args.approver_user_id,
        "actor_type": args.actor_type,
        "reason": args.reason,
    })


def cmd_agent_plan_reject(args, client: AgentOpsClient) -> dict:
    return client.post(f"/api/agent-plans/{args.plan_id}/reject", {
        "workspace_id": client.workspace_id,
        "approver_user_id": args.approver_user_id,
        "actor_type": args.actor_type,
        "reason": args.reason,
    })


def cmd_plan_evidence_create(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id or client.agent_id,
        "manifest_id": args.manifest_id,
        "plan_id": args.plan_id,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "mismatch_policy": args.mismatch_policy,
        "expected_steps": parse_json_value(args.expected_steps_json, split_csv(args.expected_steps)),
        "tool_call_ids": split_csv(args.tool_call_ids),
        "evaluation_ids": split_csv(args.evaluation_ids),
        "artifact_ids": split_csv(args.artifact_ids),
        "audit_ids": split_csv(args.audit_ids),
        "verify_now": not args.no_verify,
    }
    return client.post("/api/agent-gateway/plan-evidence-manifests", payload)


def cmd_plan_evidence_list(args, client: AgentOpsClient) -> dict:
    return client.get("/api/agent-gateway/plan-evidence-manifests", query={
        "plan_id": args.plan_id,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "agent_id": args.agent_id,
        "limit": args.limit,
    })


def cmd_plan_evidence_get(args, client: AgentOpsClient) -> dict:
    return client.get(f"/api/agent-gateway/plan-evidence-manifests/{args.manifest_id}")


def cmd_plan_evidence_verify(args, client: AgentOpsClient) -> dict:
    return client.get(f"/api/agent-gateway/plan-evidence-manifests/{args.manifest_id}/verify")


def cmd_approval_request(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "tool_call_id": args.tool_call_id,
        "requested_by_agent_id": args.agent_id or client.agent_id,
        "reason": args.reason,
        "approver_user_id": args.approver,
    }
    return client.post("/api/agent-gateway/approvals/request", payload)


def cmd_approval_list(args, client: AgentOpsClient) -> dict:
    payload = client.get("/api/agent-gateway/approvals", query={
        "decision": args.decision,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "limit": args.limit,
    })
    rows = payload.get("approvals") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    return {
        "provider": "agentops-approval",
        "operation": "approval_list",
        "approvals": rows,
        "total": payload.get("count", len(rows)) if isinstance(payload, dict) else len(rows),
        "limit": args.limit,
        "filters": {
            "decision": args.decision,
            "task_id": args.task_id,
            "run_id": args.run_id,
        },
        "gateway_scope": payload.get("gateway_scope") if isinstance(payload, dict) else None,
        "token_omitted": True,
    }


def cmd_approval_inspect(args, client: AgentOpsClient) -> dict:
    return client.get(f"/api/agent-gateway/approvals/{args.approval_id}")


def cmd_approval_prepared_action_create(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "run_id": args.run_id,
        "tool_call_id": args.tool_call_id,
        "requested_by_agent_id": args.agent_id or client.agent_id,
        "action_type": args.action_type,
        "normalized_args_json": parse_json_value(args.args_json, {}),
        "target_resource": args.target_resource,
        "risk_level": args.risk_level,
        "policy_version": args.policy_version,
        "checkpoint": parse_json_value(args.checkpoint_json, {}),
        "idempotency_key": args.idempotency_key,
        "reason": args.reason,
        "approver_user_id": args.approver,
    }
    return client.post("/api/agent-gateway/prepared-actions", payload)


def cmd_approval_prepared_action_get(args, client: AgentOpsClient) -> dict:
    return client.get(f"/api/agent-gateway/prepared-actions/{args.action_id}")


def cmd_approval_prepared_action_resume(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id or client.agent_id,
        "provider_side_effect_id": args.provider_side_effect_id,
        "result_summary": args.result_summary,
    }
    return client.post(f"/api/agent-gateway/prepared-actions/{args.action_id}/resume", payload)


def cmd_approval_decide(args, client: AgentOpsClient) -> dict:
    action = "approve" if args.handler == "approval_approve" else "reject"
    response = client.post(f"/api/approvals/{args.approval_id}/{action}", {})
    approval = response.get("approval") if isinstance(response.get("approval"), dict) else response
    prepared_action = response.get("prepared_action") if isinstance(response.get("prepared_action"), dict) else None
    return {
        "provider": "agentops-approval",
        "operation": f"approval_{action}",
        "approval": approval,
        "prepared_action": prepared_action,
        "resume_required": bool(response.get("resume_required")) if isinstance(response, dict) else False,
        "approval_id": approval.get("approval_id") or args.approval_id,
        "decision": approval.get("decision"),
        "task_id": approval.get("task_id"),
        "run_id": approval.get("run_id"),
        "token_omitted": True,
    }


def cmd_memory_propose(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id or client.agent_id,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "scope": args.scope,
        "memory_type": args.type,
        "canonical_text": args.text,
        "source_ref": args.source_ref or args.run_id,
        "access_tags": split_csv(args.access_tags),
        "confidence": args.confidence,
    }
    return client.post("/api/agent-gateway/memories/propose", payload)


def cmd_memory_list(args, client: AgentOpsClient) -> dict:
    payload = client.get("/api/agent-gateway/memories", query={
        "status": args.status,
        "scope": args.scope,
        "type": args.type,
        "task_id": args.task_id,
        "agent_id": args.agent_id,
        "limit": args.limit,
    })
    rows = payload.get("memories") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    return {
        "provider": "agentops-memory",
        "operation": "memory_list",
        "memories": rows,
        "total": payload.get("count", len(rows)) if isinstance(payload, dict) else len(rows),
        "limit": args.limit,
        "filters": {
            "status": args.status,
            "scope": args.scope,
            "type": args.type,
            "task_id": args.task_id,
            "agent_id": args.agent_id,
        },
        "gateway_scope": payload.get("gateway_scope") if isinstance(payload, dict) else None,
        "token_omitted": True,
    }


def cmd_memory_decide(args, client: AgentOpsClient) -> dict:
    action = "approve" if args.handler == "memory_approve" else "reject"
    memory = client.post(f"/api/memories/{args.memory_id}/{action}", {})
    return {
        "provider": "agentops-memory",
        "operation": f"memory_{action}",
        "memory": memory,
        "memory_id": memory.get("memory_id") or args.memory_id,
        "review_status": memory.get("review_status"),
        "task_id": memory.get("task_id"),
        "agent_id": memory.get("agent_id"),
        "token_omitted": True,
    }


def cmd_eval_submit(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "run_id": args.run_id,
        "task_id": args.task_id,
        "agent_id": args.agent_id or client.agent_id,
        "evaluator_type": args.evaluator_type,
        "score": args.score,
        "pass_fail": "pass" if args.passed else "fail",
        "rubric": parse_json_value(args.rubric_json, {"gate": args.gate}),
        "notes": args.notes,
    }
    return client.post("/api/agent-gateway/evaluations/submit", payload)


def cmd_eval_cases(args, client: AgentOpsClient) -> dict:
    return client.get("/api/evaluation-cases", query={
        "workspace_id": client.workspace_id,
        "status": args.status,
        "limit": args.limit,
        "run_id": args.run_id,
        "task_id": args.task_id,
        "artifact_id": args.artifact_id,
    })


def cmd_eval_case_runs(args, client: AgentOpsClient) -> dict:
    return client.get("/api/evaluation-case-runs", query={
        "workspace_id": client.workspace_id,
        "limit": args.limit,
        "case_id": args.case_id,
        "run_id": args.run_id,
        "task_id": args.task_id,
        "pass_fail": args.pass_fail,
        "review_status": args.review_status,
    })


def cmd_eval_review_case_run(args, client: AgentOpsClient) -> dict:
    return client.post(f"/api/evaluation-case-runs/{args.case_run_id}/review", {
        "workspace_id": client.workspace_id,
        "review_status": args.status,
        "review_note": args.note,
        "reviewed_by_user_id": args.actor_id,
    })


def cmd_eval_remediate_case_run(args, client: AgentOpsClient) -> dict:
    return client.post(f"/api/evaluation-case-runs/{args.case_run_id}/remediation-task", {
        "workspace_id": client.workspace_id,
        "task_id": args.task_id,
        "title": args.title,
        "project_id": args.project_id,
        "plan_id": args.plan_id,
        "lane_id": args.lane_id,
        "owner_agent_id": args.owner_agent_id,
        "priority": args.priority,
        "risk_level": args.risk_level,
        "budget_limit_usd": args.budget_limit_usd,
        "actor_id": args.actor_id,
        "confirm_create": bool(args.confirm_create),
    })


def cmd_eval_propose_case(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "case_id": args.case_id,
        "source_type": args.source_type,
        "source_ref": args.source_ref,
        "evaluation_id": args.evaluation_id,
        "artifact_id": args.artifact_id,
        "run_id": args.run_id,
        "task_id": args.task_id,
        "agent_id": args.agent_id,
        "case_type": args.case_type,
        "title": args.title,
        "input_summary": args.input_summary,
        "expected_output_summary": args.expected_output_summary,
        "failure_mode": args.failure_mode,
        "confidence": args.confidence,
        "rubric": parse_json_value(args.rubric_json, None),
        "confirm_create": bool(args.confirm_create),
    }
    return client.post("/api/evaluation-cases/propose", payload)


def cmd_eval_review_case(args, client: AgentOpsClient) -> dict:
    action = "approve" if args.handler == "eval_approve_case" else "reject"
    return client.post(f"/api/evaluation-cases/{args.case_id}/{action}", {})


def cmd_eval_run_cases(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "case_ids": args.case_id or [],
        "case_type": args.case_type,
        "status": args.status,
        "runner_type": args.runner_type,
        "agent_id": args.agent_id,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "artifact_id": args.artifact_id,
        "limit": args.limit,
        "min_score": args.min_score,
        "confirm_run": bool(args.confirm_run),
    }
    return client.post("/api/evaluation-cases/run", payload)


def cmd_audit_emit(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id or client.agent_id,
        "action": args.action,
        "entity_type": args.entity_type,
        "entity_id": args.entity_id,
        "task_id": args.task_id,
        "run_id": args.run_id,
        "metadata": parse_json_value(args.metadata_json, {}),
    }
    return client.post("/api/agent-gateway/audit", payload)


def cmd_workflow_customer_worker_task(args, client: AgentOpsClient) -> dict:
    payload = {
        "adapter": args.adapter,
        "confirm_run": bool(args.confirm_run),
        "title": args.title,
        "description": args.description,
        "acceptance_criteria": args.acceptance,
        "task_id": args.task_id,
        "priority": args.priority,
        "risk_level": args.risk,
        "selected_agent_ids": args.selected_agent_id or [],
        "worker_agent_id": args.worker_agent_id,
        "hermes_timeout": args.hermes_timeout,
        "hermes_max_tokens": args.hermes_max_tokens,
        "adapter_max_attempts": args.adapter_max_attempts,
        "adapter_retry_delay_sec": args.adapter_retry_delay_sec,
        "external_write_intent": bool(args.external_write_intent),
        "target_resource": args.target_resource,
        "external_action_type": args.external_action_type,
        "approval_reason": args.approval_reason,
    }
    endpoint = "/api/workflows/customer-worker-task/submit" if args.async_job else "/api/workflows/customer-worker-task"
    return client.post(endpoint, payload)


def cmd_workflow_templates(args, client: AgentOpsClient) -> dict:
    return client.get("/api/workflows/customer-task-templates")


def cmd_workflow_delivery_board(args, client: AgentOpsClient) -> dict:
    return client.get("/api/workflows/customer-delivery-board", query={"limit": args.limit})


def cmd_workflow_hermes_openclaw_loop(args, client: AgentOpsClient) -> dict:
    if args.readback:
        return client.get("/api/workflows/hermes-openclaw-loop", query={"loop_id": args.loop_id or "", "limit": args.limit})
    payload = {
        "workspace_id": client.workspace_id,
        "topic": args.topic,
        "rounds": args.rounds,
        "mode": args.mode,
        "confirm_live": bool(args.confirm_live),
        "loop_id": args.loop_id,
        "resume": bool(args.resume),
        "order": args.order,
        "request_timeout": args.request_timeout,
        "max_agent_attempts": args.max_agent_attempts,
        "retry_delay_sec": args.retry_delay_sec,
        "simulate_failure_agent": args.simulate_failure_agent or [],
    }
    return client.post("/api/workflows/hermes-openclaw-loop", payload)


def cmd_workflow_run_template(args, client: AgentOpsClient) -> dict:
    if args.adapter in {"hermes", "openclaw"} and args.confirm_run:
        minimum_timeout = (int(args.hermes_timeout or 300) + 60) if args.adapter == "hermes" else 240
        client.request_timeout = max(client.request_timeout, minimum_timeout)
    payload = {
        "template_id": args.template_id,
        "confirm_run": bool(args.confirm_run),
        "selected_agent_ids": args.selected_agent_id or [],
    }
    if args.adapter:
        payload["adapter"] = args.adapter
    if args.title:
        payload["title"] = args.title
    if args.description:
        payload["description"] = args.description
    if args.acceptance:
        payload["acceptance_criteria"] = args.acceptance
    if args.priority:
        payload["priority"] = args.priority
    if args.risk:
        payload["risk_level"] = args.risk
    if args.owner_agent_id:
        payload["owner_agent_id"] = args.owner_agent_id
    if args.worker_agent_id:
        payload["worker_agent_id"] = args.worker_agent_id
    if args.hermes_timeout:
        payload["hermes_timeout"] = args.hermes_timeout
    endpoint = "/api/workflows/customer-task-templates/submit" if args.async_job else "/api/workflows/customer-task-templates/run"
    return client.post(endpoint, payload)


def cmd_workflow_job_status(args, client: AgentOpsClient) -> dict:
    deadline = time.time() + max(args.timeout, 1)
    result = client.get(f"/api/workflows/jobs/{args.job_id}")
    while args.wait and (result.get("job") or {}).get("status") in {"queued", "running"} and time.time() < deadline:
        time.sleep(max(args.poll_interval, 0.2))
        result = client.get(f"/api/workflows/jobs/{args.job_id}")
    job = result.get("job") or {}
    result["waited"] = bool(args.wait)
    result["done"] = job.get("status") in {"completed", "failed"}
    result["token_omitted"] = True
    return result


def cmd_workflow_jobs(args, client: AgentOpsClient) -> dict:
    query = {"limit": args.limit}
    if args.status:
        query["status"] = args.status
    if args.workflow_type:
        query["workflow_type"] = args.workflow_type
    result = client.get("/api/workflows/jobs", query=query)
    result["read_only"] = True
    result["token_omitted"] = True
    return result


def cmd_workflow_stuck_jobs(args, client: AgentOpsClient) -> dict:
    return client.get("/api/workflows/jobs/stuck", query={"threshold_sec": args.threshold_sec, "limit": args.limit})


def cmd_workflow_job_mark_failed(args, client: AgentOpsClient) -> dict:
    return client.post(
        f"/api/workflows/jobs/{args.job_id}/mark-failed",
        {"reason": args.reason, "actor_id": args.actor_id},
    )


def cmd_workflow_recover_job(args, client: AgentOpsClient) -> dict:
    payload = {
        "mode": args.mode,
        "reason": args.reason,
        "task_id": args.task_id,
        "adapter": args.adapter,
        "actor_id": args.actor_id,
        "confirm_recover": bool(args.confirm_recover),
        "record_receipt": bool(args.record_receipt),
        "confirm_run": bool(args.confirm_run),
        "hermes_timeout": args.hermes_timeout,
    }
    return client.post(f"/api/workflows/jobs/{args.job_id}/recover", payload)


def cmd_workflow_run_task(args, client: AgentOpsClient) -> dict:
    from . import worker as worker_mod

    worker_agent_id = args.worker_agent_id or client.agent_id or f"agt_cli_workflow_{args.adapter}_{now_stamp()}_{uuid.uuid4().hex[:6]}"
    register_result = None
    register_error = None
    try:
        register_result = client.post("/api/agent-gateway/register", {
            "workspace_id": client.workspace_id,
            "agent_id": worker_agent_id,
            "name": args.worker_name or f"{args.adapter} Workflow Worker",
            "role": "Workflow Task Worker",
            "runtime_type": args.adapter,
            "model_provider": args.adapter,
            "model_name": args.adapter,
            "description": "Registered by agentops workflow run-task.",
        })
    except RuntimeError as exc:
        register_error = str(exc)
    if args.adapter in {"hermes", "openclaw"} and not args.confirm_run:
        created = client.post("/api/agent-gateway/tasks", {
            "workspace_id": client.workspace_id,
            "task_id": args.task_id,
            "title": args.title,
            "description": args.description,
            "requester_id": args.requester_id,
            "owner_agent_id": worker_agent_id,
            "status": "planned",
            "priority": args.priority,
            "acceptance_criteria": args.acceptance,
            "risk_level": args.risk,
            "budget_limit_usd": args.budget,
        })
        return {
            "ok": False,
            "dry_run": True,
            "provider": "agentops-worker",
            "workflow": "run_task",
            "adapter": args.adapter,
            "task_id": created.get("task_id"),
            "agent_id": worker_agent_id,
            "reason": "confirm_run_required_for_live_adapter",
            "requires": {"confirm_run": True},
            "created_task": created,
            "agent_register": register_result,
            "agent_register_error": register_error,
            "token_omitted": True,
        }

    created = client.post("/api/agent-gateway/tasks", {
        "workspace_id": client.workspace_id,
        "task_id": args.task_id,
        "title": args.title,
        "description": args.description,
        "requester_id": args.requester_id,
        "owner_agent_id": worker_agent_id,
        "status": "planned",
        "priority": args.priority,
        "acceptance_criteria": args.acceptance,
        "risk_level": args.risk,
        "budget_limit_usd": args.budget,
    })
    task_id = created.get("task_id")
    worker_argv = [
        "--base-url",
        client.base_url,
        "--workspace-id",
        client.workspace_id,
        "--agent-id",
        worker_agent_id,
        "--task-id",
        task_id,
        "--api-key",
        client.api_key,
        "--adapter",
        args.adapter,
        "--once",
        "--no-enforce-intake",
        "--status",
        "planned",
        "--adapter-max-attempts",
        str(args.adapter_max_attempts),
        "--adapter-retry-delay-sec",
        str(args.adapter_retry_delay_sec),
    ]
    if args.confirm_run:
        worker_argv.append("--confirm-run")
    if args.use_session:
        worker_argv.extend(["--use-session", "--session-ttl-sec", str(args.session_ttl_sec)])
    if args.hermes_gateway_url:
        worker_argv.extend(["--hermes-gateway-url", args.hermes_gateway_url])
    if args.hermes_timeout is not None:
        worker_argv.extend(["--hermes-timeout", str(args.hermes_timeout)])
    if args.hermes_max_tokens is not None:
        worker_argv.extend(["--hermes-max-tokens", str(args.hermes_max_tokens)])
    if args.openclaw_bin:
        worker_argv.extend(["--openclaw-bin", args.openclaw_bin])
    if args.openclaw_timeout is not None:
        worker_argv.extend(["--openclaw-timeout", str(args.openclaw_timeout)])

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = worker_mod.main(worker_argv)
    raw_worker_output = stdout.getvalue().strip()
    try:
        worker_result = json.loads(raw_worker_output) if raw_worker_output else {}
    except json.JSONDecodeError:
        worker_result = {"raw_output_summary": raw_worker_output[:500]}

    first_result = ((worker_result.get("results") or [{}])[0] or {})
    run_id = first_result.get("run_id")
    run_detail = client.get(f"/api/agent-gateway/runs/{run_id}") if run_id else None
    task_detail = client.get(f"/api/agent-gateway/tasks/{task_id}") if task_id else None
    run = (run_detail or {}).get("run") or {}
    plan_id = first_result.get("plan_id") or run.get("agent_plan_id")
    plan_verify = client.get(f"/api/agent-gateway/agent-plans/{plan_id}/verify") if plan_id else None
    plan_verification = (plan_verify or {}).get("verification") or {}
    agent_plan = (plan_verify or {}).get("agent_plan") or {}
    manifest_id = first_result.get("plan_evidence_manifest_id")
    if not manifest_id and run_id:
        manifest_list = client.get("/api/agent-gateway/plan-evidence-manifests", query={"run_id": run_id, "limit": 1})
        manifests = manifest_list.get("manifests") or []
        manifest_id = (manifests[0] or {}).get("manifest_id") if manifests else None
    manifest_verify = client.get(f"/api/agent-gateway/plan-evidence-manifests/{manifest_id}/verify") if manifest_id else None
    manifest_verification = (manifest_verify or {}).get("verification") or {}
    manifest = (manifest_verify or {}).get("manifest") or {}
    agent_plan_readback = {
        "plan_id": plan_id,
        "status": agent_plan.get("status"),
        "verified": bool(plan_verification.get("pass")),
        "verification_status": plan_verification.get("status"),
        "failed_checks": [item.get("id") for item in plan_verification.get("failed_checks") or []],
        "token_omitted": True,
    }
    plan_evidence_readback = {
        "manifest_id": manifest_id,
        "status": manifest_verification.get("status") or manifest.get("status") or first_result.get("plan_evidence_status"),
        "verified": bool(manifest_verification.get("pass")),
        "evidence_counts": manifest_verification.get("evidence_counts") or {},
        "failed_checks": [item.get("id") for item in manifest_verification.get("failed_checks") or []],
        "token_omitted": True,
    }
    evidence = {
        "tool_calls": len((run_detail or {}).get("tool_calls") or []),
        "evaluations": len((run_detail or {}).get("evaluations") or []),
        "approvals": len((run_detail or {}).get("approvals") or []),
        "artifacts": len((run_detail or {}).get("artifacts") or []),
    }
    return {
        "ok": bool(exit_code == 0 and worker_result.get("ok") is True and run_id),
        "dry_run": False,
        "provider": "agentops-worker",
        "workflow": "run_task",
        "adapter": args.adapter,
        "agent_id": worker_agent_id,
        "task_id": task_id,
        "run_id": run_id,
        "worker_exit_code": exit_code,
        "worker_processed": worker_result.get("processed"),
        "run_status": run.get("status"),
        "task_status": ((task_detail or {}).get("task") or {}).get("status"),
        "readback": {
            "run_provider": (run_detail or {}).get("provider"),
            "task_provider": (task_detail or {}).get("provider"),
            "required_scope": "tasks:read",
            "agent_plan_id": plan_id,
            "agent_plan_verified": agent_plan_readback["verified"],
            "plan_evidence_manifest_id": manifest_id,
            "plan_evidence_verified": plan_evidence_readback["verified"],
        },
        "agent_plan": agent_plan_readback,
        "plan_evidence": plan_evidence_readback,
        "evidence": evidence,
        "created_task": created,
        "agent_register": register_result,
        "agent_register_error": register_error,
        "worker_result": worker_result,
        "raw_worker_output_omitted": True,
        "token_omitted": True,
    }


def cmd_worker_stuck(args, client: AgentOpsClient) -> dict:
    return client.get("/api/workers/stuck-tasks", query={"threshold_sec": args.threshold_sec, "limit": args.limit})


def cmd_worker_status(args, client: AgentOpsClient) -> dict:
    return client.get("/api/workers/status")


def cmd_worker_fleet(args, client: AgentOpsClient) -> dict:
    return client.get("/api/workers/fleet")


def cmd_worker_readiness(args, client: AgentOpsClient) -> dict:
    return client.get("/api/workers/adapter-readiness")


def cmd_worker_logs(args, client: AgentOpsClient) -> dict:
    return client.get("/api/workers/local/logs", query={"adapter": args.adapter})


def cmd_worker_preflight(args, client: AgentOpsClient) -> dict:
    from . import worker as worker_mod

    check_args = argparse.Namespace(
        base_url=client.base_url,
        workspace_id=client.workspace_id,
        agent_id=args.agent_id or client.agent_id or worker_mod.DEFAULT_AGENT_ID,
        api_key=client.api_key,
        adapter=args.adapter,
        timeout=args.timeout,
        hermes_gateway_url=args.hermes_gateway_url,
        openclaw_bin=args.openclaw_bin,
    )
    gateway = worker_mod.check_gateway_preflight(check_args)
    adapter = worker_mod.check_adapter_preflight(check_args)
    return {
        "provider": "agentops-worker",
        "command": "agentops worker preflight",
        "ok": bool(gateway.get("ok") and adapter.get("ok")),
        "adapter": args.adapter,
        "base_url": client.base_url,
        "workspace_id": client.workspace_id,
        "agent_id": check_args.agent_id,
        "gateway_preflight": gateway,
        "adapter_preflight": adapter,
        "live_execution_performed": False,
        "token_omitted": True,
    }


def cmd_worker_service_check(args, client: AgentOpsClient) -> dict:
    from . import worker as worker_mod

    check_args = argparse.Namespace(
        manager=args.manager,
        workspace_id=client.workspace_id,
        agent_id=args.agent_id or client.agent_id or worker_mod.DEFAULT_AGENT_ID,
        adapter=args.adapter,
        label=args.label or "",
        service_path=args.service_path or "",
        api_key_placeholder=args.api_key_placeholder,
        timeout=args.timeout,
    )
    payload = worker_mod.check_service_installation(check_args)
    payload["command"] = "agentops worker service-check"
    return payload


def cmd_worker_service_install(args, client: AgentOpsClient) -> dict:
    from . import worker as worker_mod

    install_args = argparse.Namespace(
        manager=args.manager,
        base_url=client.base_url,
        workspace_id=client.workspace_id,
        agent_id=args.agent_id or client.agent_id or worker_mod.DEFAULT_AGENT_ID,
        adapter=args.adapter,
        confirm_run=bool(args.confirm_run),
        session_ttl_sec=args.session_ttl_sec,
        session_refresh_margin_sec=args.session_refresh_margin_sec,
        poll_interval=args.poll_interval,
        label=args.label or "",
        working_directory=args.working_directory,
        runtime_dir=args.runtime_dir or "",
        log_path=args.log_path or "",
        api_key_placeholder=args.api_key_placeholder,
        service_path=args.service_path or "",
        confirm_install=bool(args.confirm_install),
        overwrite=bool(args.overwrite),
        timeout=args.timeout,
    )
    payload = worker_mod.install_service_file(install_args)
    payload["command"] = "agentops worker service-install"
    return payload


def cmd_worker_start(args, client: AgentOpsClient) -> dict:
    payload = {
        "adapter": args.adapter,
        "agent_id": args.agent_id,
        "poll_interval": args.poll_interval,
        "max_tasks": args.max_tasks,
        "max_errors": args.max_errors,
        "status": args.status or ["planned"],
        "confirm_run": bool(args.confirm_run),
    }
    if args.openclaw_timeout is not None:
        payload["openclaw_timeout"] = args.openclaw_timeout
    return client.post("/api/workers/local/start", payload)


def cmd_worker_stop(args, client: AgentOpsClient) -> dict:
    return client.post("/api/workers/local/stop", {"adapter": args.adapter})


def cmd_worker_restart(args, client: AgentOpsClient) -> dict:
    payload = {
        "adapter": args.adapter,
        "agent_id": args.agent_id,
        "poll_interval": args.poll_interval,
        "max_tasks": args.max_tasks,
        "max_errors": args.max_errors,
        "status": args.status or None,
        "confirm_run": bool(args.confirm_run),
    }
    if args.openclaw_timeout is not None:
        payload["openclaw_timeout"] = args.openclaw_timeout
    return client.post("/api/workers/local/restart", payload)


def cmd_worker_release(args, client: AgentOpsClient) -> dict:
    return client.post("/api/workers/tasks/release", {
        "task_id": args.task_id,
        "reason": args.reason,
        "force": args.force,
    })


def cmd_worker_hygiene(args, client: AgentOpsClient) -> dict:
    payload = {
        "threshold_sec": args.threshold_sec,
        "enrollment_age_sec": args.enrollment_age_sec,
        "limit": args.limit,
    }
    if args.apply:
        payload["apply"] = True
        payload["confirm_cleanup"] = bool(args.confirm_cleanup)
        payload["release_reason"] = args.reason
        return client.post("/api/workers/fleet/hygiene", payload)
    return client.get("/api/workers/fleet/hygiene", query=payload)


def cmd_enrollment_create(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id,
        "name": args.name,
        "role": args.role,
        "runtime_type": args.runtime,
        "scopes": split_csv(args.scopes),
        "ttl_days": args.ttl_days,
        "heartbeat_timeout_sec": args.heartbeat_timeout_sec,
        "label": args.label,
    }
    result = client.post("/api/agent-gateway/enrollment/create", payload)
    if args.save_token and result.get("token"):
        config = load_config()
        config.update({
            "base_url": client.base_url,
            "workspace_id": result.get("workspace_id") or client.workspace_id,
            "agent_id": result.get("agent_id") or args.agent_id,
            "api_key": result["token"],
        })
        save_config(config)
        result["saved_to"] = str(CONFIG_PATH)
    return result


def cmd_enrollment_policy_preview(args, client: AgentOpsClient) -> dict:
    return client.post("/api/agent-gateway/enrollment/policy-preview", {
        "workspace_id": args.workspace_id or client.workspace_id,
        "runtime_type": args.runtime,
        "scopes": split_csv(args.scopes),
    })


def cmd_enrollment_request(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": args.agent_id,
        "name": args.name,
        "role": args.role,
        "runtime_type": args.runtime,
        "scopes": split_csv(args.scopes),
        "reason": args.reason,
    }
    return client.post("/api/agent-gateway/enrollment/request", payload)


def cmd_enrollment_issue_approved(args, client: AgentOpsClient) -> dict:
    payload = {
        "request_id": args.request_id,
        "approval_id": args.approval_id,
        "ttl_days": args.ttl_days,
        "heartbeat_timeout_sec": args.heartbeat_timeout_sec,
        "label": args.label,
    }
    result = client.post("/api/agent-gateway/enrollment/issue-approved", payload)
    if args.save_token and result.get("token"):
        config = load_config()
        config.update({
            "base_url": client.base_url,
            "workspace_id": result.get("workspace_id") or client.workspace_id,
            "agent_id": result.get("agent_id") or client.agent_id,
            "api_key": result["token"],
        })
        save_config(config)
        result["saved_to"] = str(CONFIG_PATH)
    return result


def cmd_enrollment_list(args, client: AgentOpsClient) -> dict:
    return client.get("/api/agent-gateway/enrollments")


def cmd_enrollment_revoke(args, client: AgentOpsClient) -> dict:
    payload = {
        "token_id": args.token_id,
        "agent_id": args.agent_id,
    }
    return client.post("/api/agent-gateway/enrollment/revoke", payload)


def cmd_enrollment_rotate(args, client: AgentOpsClient) -> dict:
    payload = {
        "token_id": args.token_id,
        "agent_id": args.agent_id,
        "scopes": split_csv(args.scopes) if args.scopes else None,
        "ttl_days": args.ttl_days,
        "heartbeat_timeout_sec": args.heartbeat_timeout_sec,
        "label": args.label,
    }
    result = client.post("/api/agent-gateway/enrollment/rotate", payload)
    if args.save_token and result.get("token"):
        config = load_config()
        config.update({
            "base_url": client.base_url,
            "workspace_id": result.get("workspace_id") or client.workspace_id,
            "agent_id": result.get("agent_id") or args.agent_id,
            "api_key": result["token"],
        })
        save_config(config)
        result["saved_to"] = str(CONFIG_PATH)
    return result


def cmd_session_create(args, client: AgentOpsClient) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "ttl_sec": args.ttl_sec,
        "scopes": split_csv(args.scopes) if args.scopes else None,
    }
    result = client.post("/api/agent-gateway/session/create", payload)
    if args.save_session and result.get("session_token"):
        config = load_config()
        config.update({
            "base_url": client.base_url,
            "workspace_id": result.get("workspace_id") or client.workspace_id,
            "agent_id": result.get("agent_id") or client.agent_id,
            "api_key": result["session_token"],
        })
        save_config(config)
        result["saved_to"] = str(CONFIG_PATH)
    return result


def cmd_session_list(args, client: AgentOpsClient) -> dict:
    return client.get("/api/agent-gateway/sessions")


def cmd_session_revoke(args, client: AgentOpsClient) -> dict:
    payload = {
        "session_id": args.session_id,
        "agent_id": args.agent_id,
    }
    return client.post("/api/agent-gateway/session/revoke", payload)


def add_global_args(parser, suppress_defaults: bool = False):
    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument("--base-url", default=default, help="AgentOps MIS base URL. Defaults to env/config/http://127.0.0.1:8787.")
    parser.add_argument("--api-key", default=default, help="Local API key. Prefer AGENTOPS_API_KEY for real use.")
    parser.add_argument("--workspace-id", default=default, help="Workspace id. Defaults to env/config/local-demo.")
    parser.add_argument("--agent-id", default=default, help="Default agent id for this command.")
    parser.add_argument("--request-timeout", type=int, default=default, help="HTTP request timeout in seconds. Defaults to env/config/30.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentops", description="AgentOps MIS local Agent Gateway CLI.")
    add_global_args(parser)
    sub = parser.add_subparsers(dest="resource", required=True)

    login = sub.add_parser("login", help="Store local AgentOps MIS CLI config.")
    add_global_args(login, suppress_defaults=True)
    login.set_defaults(handler="login")

    status = sub.add_parser("status", help="Check Agent Gateway connectivity and safe auth metadata.")
    add_global_args(status, suppress_defaults=True)
    status.set_defaults(handler="status")

    doctor = sub.add_parser("doctor", help="Diagnose local/remote agent CLI setup without printing secrets.")
    add_global_args(doctor, suppress_defaults=True)
    doctor.set_defaults(handler="doctor")

    local = sub.add_parser("local", help="Single-workspace local readiness commands.")
    local_sub = local.add_subparsers(dest="action", required=True)
    local_readiness = local_sub.add_parser("readiness", help="Show end-to-end local MIS readiness and evidence closure.")
    local_readiness.set_defaults(handler="local_readiness")

    demo = sub.add_parser("demo", help="Read-only demo and recording readiness commands.")
    demo_sub = demo.add_subparsers(dest="action", required=True)
    demo_readiness = demo_sub.add_parser("readiness", help="Show the canonical v1.5 classroom recording path readiness.")
    demo_readiness.set_defaults(handler="demo_readiness")

    command_center = sub.add_parser("command-center", help="Stable read-only Command Center BFF for human UI and agent debugging.")
    command_center_sub = command_center.add_subparsers(dest="action", required=True)
    command_center_overview = command_center_sub.add_parser("overview", help="Aggregate projects, blocked runs, approvals, deliveries, stale workers, and next actions.")
    command_center_overview.add_argument("--project-id", default=None)
    command_center_overview.add_argument("--limit", type=int, default=8)
    command_center_overview.add_argument("--threshold-sec", type=int, default=900)
    command_center_overview.add_argument("--refresh-cache", action="store_true")
    command_center_overview.set_defaults(handler="command_center_overview")

    operator = sub.add_parser("operator", help="Read-only operator command-center plans.")
    operator_sub = operator.add_subparsers(dest="action", required=True)
    operator_plan = operator_sub.add_parser("action-plan", help="Show the prioritized next safe CLI/UI actions.")
    operator_plan.add_argument("--limit", type=int, default=12)
    operator_plan.set_defaults(handler="operator_action_plan")
    operator_receipts = operator_sub.add_parser("action-receipts", help="Read Action Queue receipt ledger rows plus action-plan coverage.")
    operator_receipts.add_argument("--limit", type=int, default=12)
    operator_receipts.add_argument("--plan-limit", type=int, default=12)
    operator_receipts.set_defaults(handler="operator_action_receipts")
    operator_record_receipt = operator_sub.add_parser("record-action-receipt", help="Preview or append an audited Action Queue receipt without executing commands.")
    operator_record_receipt.add_argument("--action-command", required=True, help="The exact recovery/action command that was run or inspected.")
    operator_record_receipt.add_argument("--verify-command", default="", help="The acceptance-check command paired with the action.")
    operator_record_receipt.add_argument("--status", default="recorded", choices=["recorded", "verified", "failed", "skipped"])
    operator_record_receipt.add_argument("--result-summary", default="")
    operator_record_receipt.add_argument("--action-id", default="")
    operator_record_receipt.add_argument("--action-signature", default="")
    operator_record_receipt.add_argument("--source", default="agentops_cli.operator_record_action_receipt")
    operator_record_receipt.add_argument("--actor-id", default="usr_founder")
    operator_record_receipt.add_argument("--confirm-record", action="store_true", help="Actually append runtime/audit receipt evidence. Default is preview only.")
    operator_record_receipt.set_defaults(handler="operator_record_action_receipt")
    operator_receipt_memory_lane = operator_sub.add_parser("receipt-failure-memories", help="Read repeated failed receipt evaluations that should become memory candidates.")
    operator_receipt_memory_lane.add_argument("--min-failures", type=int, default=2)
    operator_receipt_memory_lane.add_argument("--limit", type=int, default=8)
    operator_receipt_memory_lane.set_defaults(handler="operator_receipt_failure_memories")
    operator_receipt_memory = operator_sub.add_parser("propose-receipt-failure-memory", help="Preview or create a memory candidate from repeated failed Action Queue receipt evaluations.")
    operator_receipt_memory.add_argument("--action-hash", default="")
    operator_receipt_memory.add_argument("--min-failures", type=int, default=2)
    operator_receipt_memory.add_argument("--memory-id", default=None)
    operator_receipt_memory.add_argument("--canonical-text", default=None)
    operator_receipt_memory.add_argument("--actor-id", default="usr_founder")
    operator_receipt_memory.add_argument("--confirm-create", action="store_true")
    operator_receipt_memory.set_defaults(handler="operator_propose_receipt_failure_memory")
    operator_loop = operator_sub.add_parser("loop-audit", help="Audit the READ/PLAN/RETRIEVE/COMPARE/EXECUTE/VERIFY/RECORD loop contract.")
    operator_loop.add_argument("--loop-id", default=None)
    operator_loop.add_argument("--limit", type=int, default=12)
    operator_loop.set_defaults(handler="operator_loop_audit")
    operator_loop_control_parser = operator_sub.add_parser("loop-control", help="Read the lightweight loop-control next step for real local ledgers.")
    operator_loop_control_parser.add_argument("--loop-id", default=None)
    operator_loop_control_parser.add_argument("--limit", type=int, default=8)
    operator_loop_control_parser.set_defaults(handler="operator_loop_control")
    operator_evidence = operator_sub.add_parser("evidence-report", help="Read a run-by-run evidence report across Agent Plans, approvals, manifests, and ledger rows.")
    operator_evidence.add_argument("--run-id", default=None)
    operator_evidence.add_argument("--task-id", default=None)
    operator_evidence.add_argument("--limit", type=int, default=12)
    operator_evidence.set_defaults(handler="operator_evidence_report")
    operator_handoff = operator_sub.add_parser("handoff", help="Read a loop/operator handoff package with work-order, receipt, review, and safety state.")
    operator_handoff.add_argument("--loop-id", default=None)
    operator_handoff.add_argument("--limit", type=int, default=12)
    operator_handoff.set_defaults(handler="operator_handoff")
    operator_loop_self_check = operator_sub.add_parser("loop-self-check", help="Read a loop self-check across policy, receipts, evaluations, audit, and handoff health.")
    operator_loop_self_check.add_argument("--loop-id", default=None)
    operator_loop_self_check.add_argument("--limit", type=int, default=12)
    operator_loop_self_check.set_defaults(handler="operator_loop_self_check")
    operator_advance = operator_sub.add_parser("advance-loop", help="Preview or execute one bounded allowlisted loop action, verify it, and record a receipt.")
    operator_advance.add_argument("--loop-id", default=None)
    operator_advance.add_argument("--limit", type=int, default=12)
    operator_advance.add_argument("--timeout", type=int, default=90)
    operator_advance.add_argument("--actor-id", default="usr_founder")
    operator_advance.add_argument("--fast-control", action="store_true", help="Use lightweight loop-control readback instead of full handoff.")
    operator_advance.add_argument("--confirm-advance", action="store_true", help="Execute exactly one allowlisted local agentops action and record its receipt.")
    operator_advance.set_defaults(handler="operator_advance_loop")
    operator_advance_policy = operator_sub.add_parser("advance-loop-policy", help="Read the bounded advance-loop policy.")
    operator_advance_policy.set_defaults(handler="operator_advance_loop_policy")
    operator_health = operator_sub.add_parser("health", help="Read the aggregate operator health snapshot across loop, readiness, security, worker, review, and action queues.")
    operator_health.add_argument("--loop-id", default=None)
    operator_health.add_argument("--limit", type=int, default=12)
    operator_health.set_defaults(handler="operator_health")
    operator_runtime_doctor = operator_sub.add_parser("runtime-doctor", help="Read the local MIS/Hermes/OpenClaw/Codex runtime doctor with launch, safety, and evidence commands.")
    operator_runtime_doctor.add_argument("--loop-id", default=None)
    operator_runtime_doctor.add_argument("--limit", type=int, default=8)
    operator_runtime_doctor.add_argument("--runtime-base-url", default=None, help="Base URL to embed in suggested runtime commands; defaults to the server host.")
    operator_runtime_doctor.set_defaults(handler="operator_runtime_doctor")
    operator_live_acceptance = operator_sub.add_parser("live-acceptance", help="Read Hermes/OpenClaw live customer-worker acceptance freshness without running adapters.")
    operator_live_acceptance.add_argument("--freshness-hours", type=int, default=72)
    operator_live_acceptance.add_argument("--limit", type=int, default=8)
    operator_live_acceptance.set_defaults(handler="operator_live_acceptance")
    operator_execution_mode = operator_sub.add_parser("execution-mode", help="Read the current dispatch execution mode for mock/Hermes/OpenClaw without running adapters.")
    operator_execution_mode.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    operator_execution_mode.add_argument("--confirm-run", action="store_true", help="Preview the mode after explicit live confirmation; does not execute the adapter.")
    operator_execution_mode.add_argument("--limit", type=int, default=8)
    operator_execution_mode.set_defaults(handler="operator_execution_mode")
    operator_command_center = operator_sub.add_parser("command-center", help="Read the unified operator command-center BFF for projects, blockers, approvals, deliveries, stale workers, and next actions.")
    operator_command_center.add_argument("--project-id", default=None)
    operator_command_center.add_argument("--limit", type=int, default=12)
    operator_command_center.set_defaults(handler="operator_command_center")
    operator_intake = operator_sub.add_parser("intake-checklist", help="Show read-only pre-intake gates for planned/backlog tasks.")
    operator_intake.add_argument("--limit", type=int, default=12)
    operator_intake.set_defaults(handler="operator_intake_checklist")
    operator_launch = operator_sub.add_parser("loop-launch-packet", help="Build a read-only Agent Work Method launch packet for the next agent loop.")
    operator_launch.add_argument("--limit", type=int, default=8)
    operator_launch.add_argument("--task-id", default=None)
    operator_launch.add_argument("--agent-id", default=None)
    operator_launch.add_argument("--query", default="READ PLAN RETRIEVE COMPARE VERIFY RECORD")
    operator_launch.add_argument("--handoff-mode", choices=["lightweight", "full"], default="lightweight", help="Use lightweight loop-control by default; choose full for deeper operator handoff diagnostics.")
    operator_launch.add_argument("--full-handoff", action="store_true", help="Shortcut for --handoff-mode full.")
    operator_launch.add_argument("--brief", action="store_true", help="Return a compact copy-only launch brief for Hermes/OpenClaw/Codex instead of the full packet.")
    operator_launch.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock", help="Adapter context to include in --brief preflight and live-confirmation guidance.")
    operator_launch.set_defaults(handler="operator_loop_launch_packet")
    evidence_gap = operator_sub.add_parser("remediate-evidence-gap", help="Preview or create a Commander package for a run execution-evidence gap.")
    evidence_gap.add_argument("--run-id", required=True)
    evidence_gap.add_argument("--task-id", default=None)
    evidence_gap.add_argument("--title", default=None)
    evidence_gap.add_argument("--project-id", default=None)
    evidence_gap.add_argument("--plan-id", default=None)
    evidence_gap.add_argument("--lane-id", default=None)
    evidence_gap.add_argument("--owner-agent-id", default=None)
    evidence_gap.add_argument("--priority", default=None, choices=["low", "medium", "high", "critical"])
    evidence_gap.add_argument("--risk-level", default=None, choices=["low", "medium", "high", "critical"])
    evidence_gap.add_argument("--budget-limit-usd", type=float, default=None)
    evidence_gap.add_argument("--actor-id", default="usr_founder")
    evidence_gap.add_argument("--confirm-create", action="store_true")
    evidence_gap.set_defaults(handler="operator_remediate_evidence_gap")
    close_evidence_gap = operator_sub.add_parser("close-evidence-gap", help="Preview or record an operator decision closing/reopening a run execution-evidence gap.")
    close_evidence_gap.add_argument("--run-id", required=True)
    close_evidence_gap.add_argument("--decision", default="accepted_remediation", choices=["accepted_remediation", "waived", "reopen"])
    close_evidence_gap.add_argument("--reason", default=None)
    close_evidence_gap.add_argument("--note", default=None)
    close_evidence_gap.add_argument("--synthesis-artifact-id", default=None)
    close_evidence_gap.add_argument("--remediation-task-id", default=None)
    close_evidence_gap.add_argument("--actor-id", default="usr_founder")
    close_evidence_gap.add_argument("--confirm-close", action="store_true")
    close_evidence_gap.set_defaults(handler="operator_close_evidence_gap")

    commander = sub.add_parser("commander", help="Commander planning, dispatch and readback commands.")
    commander_sub = commander.add_subparsers(dest="action", required=True)
    commander_board = commander_sub.add_parser("board", help="Read the Commander project board.")
    commander_board.add_argument("--project-id", default=None, help="Optional Commander project id for a scoped team board.")
    commander_board.add_argument("--plan-id", default=None, help="Optional Commander plan id for a scoped team board.")
    commander_board.add_argument("--limit", type=int, default=25, help="Maximum scoped work packages to include in team_board.")
    commander_board.set_defaults(handler="commander_board")
    commander_repo_map = commander_sub.add_parser("repo-map", help="Localize relevant repo files for a coding work package.")
    commander_repo_map.add_argument("query", nargs="?", default="", help="Task or feature query to localize.")
    commander_repo_map.add_argument("--query", "-q", dest="query_flag", default=None, help="Task or feature query to localize.")
    commander_repo_map.add_argument("--limit", type=int, default=12)
    commander_repo_map.add_argument("--char-budget", type=int, default=8000)
    commander_repo_map.set_defaults(handler="commander_repo_map")
    commander_coding_template = commander_sub.add_parser("coding-template", help="Read the local coding project template with worktree, patch, verifier and merge-gate evidence.")
    commander_coding_template.add_argument("query", nargs="?", default="", help="Coding goal or work-package query to localize.")
    commander_coding_template.add_argument("--query", "-q", dest="query_flag", default=None, help="Coding goal or work-package query to localize.")
    commander_coding_template.add_argument("--project-id", default="proj_local_coding")
    commander_coding_template.add_argument("--task-id", default="<task_id>")
    commander_coding_template.add_argument("--limit", type=int, default=8)
    commander_coding_template.add_argument("--char-budget", type=int, default=4800)
    commander_coding_template.set_defaults(handler="commander_coding_template")
    commander_inbox = commander_sub.add_parser("inbox", help="Read the Commander integration inbox.")
    commander_inbox.add_argument("--bucket", choices=["all", "ready_for_review", "still_running", "blocked", "late_or_stale", "needs_memory_review"], default="all")
    commander_inbox.add_argument("--limit", type=int, default=20)
    commander_inbox.add_argument("--threshold-sec", type=int, default=900)
    commander_inbox.set_defaults(handler="commander_inbox")
    commander_plan = commander_sub.add_parser("plan", help="Preview or create commander work-package tasks from a project goal.")
    commander_plan.add_argument("--goal", required=True, help="Customer/project goal to decompose into work packages.")
    commander_plan.add_argument("--project-id", default=None)
    commander_plan.add_argument("--plan-id", default=None)
    commander_plan.add_argument("--max-packages", type=int, default=5)
    commander_plan.add_argument("--task-id-prefix", default=None)
    commander_plan.add_argument("--lanes-json", default=None, help="Optional JSON array overriding the default commander lanes.")
    commander_plan.add_argument("--confirm-create", action="store_true", help="Actually create MIS tasks; omitted means preview only.")
    commander_plan.set_defaults(handler="commander_plan")
    commander_packages = commander_sub.add_parser("packages", help="Read persisted commander work-package task status and evidence.")
    commander_packages.add_argument("--project-id", default=None)
    commander_packages.add_argument("--plan-id", default=None)
    commander_packages.add_argument("--status", default="all")
    commander_packages.add_argument("--limit", type=int, default=25)
    commander_packages.set_defaults(handler="commander_packages")
    commander_dispatch = commander_sub.add_parser("dispatch-package", help="Dispatch one persisted commander work package through a worker adapter.")
    commander_dispatch.add_argument("--task-id", required=True)
    commander_dispatch.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    commander_dispatch.add_argument("--confirm-run", action="store_true", help="Required for Hermes/OpenClaw live execution.")
    commander_dispatch.add_argument("--worker-agent-id", default=None)
    commander_dispatch.add_argument("--hermes-timeout", type=int, default=300)
    commander_dispatch.set_defaults(handler="commander_dispatch_package")
    commander_coding_workspace = commander_sub.add_parser("coding-workspace", help="Preview or create an isolated git worktree for one Commander coding package.")
    commander_coding_workspace.add_argument("--task-id", required=True)
    commander_coding_workspace.add_argument("--branch", default=None)
    commander_coding_workspace.add_argument("--worktree-root", default=None)
    commander_coding_workspace.add_argument("--worktree-path", default=None)
    commander_coding_workspace.add_argument("--actor-id", default="usr_founder")
    commander_coding_workspace.add_argument("--confirm-create", action="store_true", help="Actually create the git worktree and record workspace evidence.")
    commander_coding_workspace.set_defaults(handler="commander_coding_workspace")
    commander_coding_workspace_cleanup = commander_sub.add_parser("coding-workspace-cleanup", help="Preview or remove a Commander coding worktree and optional branch.")
    commander_coding_workspace_cleanup.add_argument("--task-id", required=True)
    commander_coding_workspace_cleanup.add_argument("--branch", default=None)
    commander_coding_workspace_cleanup.add_argument("--worktree-root", default=None)
    commander_coding_workspace_cleanup.add_argument("--worktree-path", default=None)
    commander_coding_workspace_cleanup.add_argument("--keep-branch", action="store_true")
    commander_coding_workspace_cleanup.add_argument("--actor-id", default="usr_founder")
    commander_coding_workspace_cleanup.add_argument("--confirm-cleanup", action="store_true", help="Actually remove the git worktree and delete the branch unless --keep-branch is set.")
    commander_coding_workspace_cleanup.set_defaults(handler="commander_coding_workspace_cleanup")
    commander_coding_evidence = commander_sub.add_parser("coding-evidence", help="Record safe patch/test/verifier evidence for a dispatched coding work package.")
    commander_coding_evidence.add_argument("--task-id", required=True)
    commander_coding_evidence.add_argument("--run-id", default="")
    commander_coding_evidence.add_argument("--branch", default=None)
    commander_coding_evidence.add_argument("--collect-from-worktree", action="store_true", help="Collect git diff/status and verifier summaries from the package worktree.")
    commander_coding_evidence.add_argument("--worktree-root", default=None)
    commander_coding_evidence.add_argument("--worktree-path", default=None)
    commander_coding_evidence.add_argument("--patch-summary", default="Patch manifest recorded as summary/hash only; raw patch omitted.")
    commander_coding_evidence.add_argument("--test-summary", default="Focused tests passed; raw logs omitted.")
    commander_coding_evidence.add_argument("--verifier-summary", default="Independent verifier evidence recorded; raw logs omitted.")
    commander_coding_evidence.add_argument("--merge-summary", default="Merge gate remains pending human approval and exact-head release checks.")
    commander_coding_evidence.add_argument("--test-status", choices=["pass", "fail", "warn"], default="pass")
    commander_coding_evidence.add_argument("--verifier-status", choices=["pass", "fail", "warn"], default="pass")
    commander_coding_evidence.add_argument("--merge-gate-status", choices=["pending_human_approval", "ready", "blocked", "not_checked"], default="pending_human_approval")
    commander_coding_evidence.add_argument("--changed-file", action="append", default=None, help="Repo-relative touched file path. Repeatable; raw file bodies are never sent.")
    commander_coding_evidence.add_argument("--verification-command", action="append", default=None, help="Verification command summary. Repeatable.")
    commander_coding_evidence.add_argument("--actor-id", default="usr_founder")
    commander_coding_evidence.add_argument("--confirm-record", action="store_true", help="Actually record artifacts/evaluation/audit. Omitted means preview only.")
    commander_coding_evidence.set_defaults(handler="commander_coding_evidence")
    commander_dispatch_batch = commander_sub.add_parser("dispatch-batch", help="Queue multiple persisted commander work packages as async workflow jobs.")
    commander_dispatch_batch.add_argument("--project-id", default=None)
    commander_dispatch_batch.add_argument("--plan-id", default=None)
    commander_dispatch_batch.add_argument("--task-id", action="append", default=None, help="Exact task id to queue. Repeatable.")
    commander_dispatch_batch.add_argument("--status", default="planned")
    commander_dispatch_batch.add_argument("--limit", type=int, default=5)
    commander_dispatch_batch.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    commander_dispatch_batch.add_argument("--confirm-run", action="store_true", help="Required for Hermes/OpenClaw live execution.")
    commander_dispatch_batch.add_argument("--hermes-timeout", type=int, default=300)
    commander_dispatch_batch.set_defaults(handler="commander_dispatch_batch")
    commander_synthesize = commander_sub.add_parser("synthesize", help="Preview or create a synthesis artifact from returned commander work packages.")
    commander_synthesize.add_argument("--project-id", default=None)
    commander_synthesize.add_argument("--plan-id", default=None)
    commander_synthesize.add_argument("--task-id", action="append", default=None, help="Exact task id to include. Repeatable.")
    commander_synthesize.add_argument("--status", default="ready_for_review")
    commander_synthesize.add_argument("--limit", type=int, default=10)
    commander_synthesize.add_argument("--artifact-id", default=None)
    commander_synthesize.add_argument("--confirm-create", action="store_true", help="Actually persist the synthesis artifact; omitted means preview only.")
    commander_synthesize.set_defaults(handler="commander_synthesize")
    commander_promote = commander_sub.add_parser("promote-synthesis", help="Promote an approved commander synthesis to memory and/or delivery artifacts.")
    commander_promote.add_argument("--artifact-id", required=True)
    commander_promote.add_argument("--approval-id", default=None)
    commander_promote.add_argument("--mode", choices=["memory", "delivery", "both"], default="both")
    commander_promote.add_argument("--project-id", default=None)
    commander_promote.add_argument("--memory-id", default=None)
    commander_promote.add_argument("--delivery-artifact-id", default=None)
    commander_promote.add_argument("--confirm-promote", action="store_true", help="Actually create memory/delivery rows; omitted means preview only.")
    commander_promote.set_defaults(handler="commander_promote_synthesis")

    review = sub.add_parser("review", help="Human review queue commands.")
    review_sub = review.add_subparsers(dest="action", required=True)
    review_queue = review_sub.add_parser("queue", help="Read pending approvals, memory candidates and customer deliveries.")
    review_queue.add_argument("--limit", type=int, default=20)
    review_queue.set_defaults(handler="review_queue")

    security = sub.add_parser("security", help="Read-only security and production-readiness checks.")
    security_sub = security.add_subparsers(dest="action", required=True)
    security_prod = security_sub.add_parser("production-readiness", help="Show whether the local Gateway is safe for shared/production use.")
    security_prod.set_defaults(handler="security_production_readiness")

    agent = sub.add_parser("agent", help="Agent identity commands.")
    agent_sub = agent.add_subparsers(dest="action", required=True)
    register = agent_sub.add_parser("register", help="Register or update an AI digital employee.")
    register.add_argument("--id", default=None)
    register.add_argument("--name", required=True)
    register.add_argument("--role", default="AI Digital Employee")
    register.add_argument("--runtime", default="mock")
    register.add_argument("--model-provider", default="local")
    register.add_argument("--model-name", default="agentops-cli")
    register.add_argument("--permission-level", default="standard")
    register.add_argument("--allowed-tools", default="agent_gateway.task,agent_gateway.run,agent_gateway.audit")
    register.add_argument("--budget", type=float, default=5.0)
    register.add_argument("--description", default="Registered through agentops CLI.")
    register.set_defaults(handler="agent_register")

    heartbeat = agent_sub.add_parser("heartbeat", help="Send agent heartbeat.")
    heartbeat.add_argument("--id", default=None)
    heartbeat.add_argument("--status", default="idle", choices=["idle", "running", "paused", "error", "disabled"])
    heartbeat.add_argument("--summary", default="CLI heartbeat.")
    heartbeat.add_argument("--runtime", default="mock")
    heartbeat.set_defaults(handler="agent_heartbeat")

    task = sub.add_parser("task", help="Task pull/claim commands.")
    task_sub = task.add_subparsers(dest="action", required=True)
    create = task_sub.add_parser("create", help="Create a normal MIS task for agents/workers.")
    create.add_argument("--task-id", default=None)
    create.add_argument("--title", required=True)
    create.add_argument("--description", default="")
    create.add_argument("--requester-id", default="usr_customer_demo")
    create.add_argument("--owner-agent-id", default=None)
    create.add_argument("--collaborator-agent-id", action="append", default=None, help="Optional collaborator agent id. Repeatable.")
    create.add_argument("--status", default="planned", choices=["backlog", "planned", "running", "waiting_approval", "blocked", "completed", "failed", "canceled"])
    create.add_argument("--priority", default="medium", choices=["low", "medium", "high", "critical"])
    create.add_argument("--due-date", default=None)
    create.add_argument("--acceptance", default="Worker must satisfy task acceptance criteria and write ledger evidence.")
    create.add_argument("--risk", default="medium", choices=["low", "medium", "high", "critical"])
    create.add_argument("--budget", type=float, default=3.0)
    create.set_defaults(handler="task_create")

    task_list = task_sub.add_parser("list", help="List normal MIS tasks with optional local filtering.")
    task_list.add_argument("--limit", type=int, default=25)
    task_list.add_argument("--status", action="append", default=None, help="Task status filter. Can be repeated.")
    task_list.add_argument("--owner-agent-id", default=None)
    task_list.add_argument("--requester-id", default=None)
    task_list.set_defaults(handler="task_list")

    task_get = task_sub.add_parser("get", help="Inspect one task plus run/evaluation/artifact evidence.")
    task_get.add_argument("--task-id", required=True)
    task_get.set_defaults(handler="task_get")

    pull = task_sub.add_parser("pull", help="Pull available tasks for an agent.")
    pull.add_argument("--agent-id", default=None)
    pull.add_argument("--task-id", default=None, help="Optional exact task id to test pull visibility.")
    pull.add_argument("--limit", type=int, default=10)
    pull.add_argument("--status", action="append", default=None, help="Task status filter. Can be repeated.")
    pull.add_argument("--enforce-intake", action="store_true", help="Exclude tasks blocked by Agent Plan, knowledge, base-reference, or risk-boundary intake gates.")
    pull.set_defaults(handler="task_pull")

    claim = task_sub.add_parser("claim", help="Claim a task.")
    claim.add_argument("--task-id", required=True)
    claim.add_argument("--agent-id", default=None)
    claim.add_argument("--runtime", default="mock")
    claim.set_defaults(handler="task_claim")

    run = sub.add_parser("run", help="Run lifecycle commands.")
    run_sub = run.add_subparsers(dest="action", required=True)
    run_list = run_sub.add_parser("list", help="List runs with optional task/agent/status filtering.")
    run_list.add_argument("--task-id", default=None)
    run_list.add_argument("--agent-id", default=None)
    run_list.add_argument("--status", action="append", default=None, help="Run status filter. Can be repeated.")
    run_list.add_argument("--limit", type=int, default=25)
    run_list.set_defaults(handler="run_list")

    run_get = run_sub.add_parser("get", help="Inspect one run plus tool/evaluation/artifact evidence.")
    run_get.add_argument("--run-id", required=True)
    run_get.set_defaults(handler="run_get")

    graph = run_sub.add_parser("graph", help="Inspect parent/child delegation graph for one run.")
    graph.add_argument("--run-id", required=True)
    graph.set_defaults(handler="run_graph")

    start = run_sub.add_parser("start", help="Start a run for a task.")
    start.add_argument("--task-id", required=True)
    start.add_argument("--agent-id", default=None)
    start.add_argument("--runtime", default="mock")
    start.add_argument("--input-summary", default="")
    start.add_argument("--delegation-id", default=None)
    start.add_argument("--parent-run-id", default=None)
    start.add_argument("--plan-id", default=None, help="Verified Agent Plan id that authorizes this run.")
    start.add_argument("--approval-required", action="store_true")
    start.set_defaults(handler="run_start")

    run_hb = run_sub.add_parser("heartbeat", help="Update run status.")
    run_hb.add_argument("--run-id", required=True)
    run_hb.add_argument("--status", default="running", choices=["running", "completed", "failed", "blocked", "waiting_approval"])
    run_hb.add_argument("--summary", default="")
    run_hb.add_argument("--duration-ms", type=int, default=None)
    run_hb.add_argument("--output-tokens", type=int, default=0)
    run_hb.add_argument("--cost", type=float, default=0.0)
    run_hb.add_argument("--error-type", default=None)
    run_hb.add_argument("--error-message", default=None)
    run_hb.set_defaults(handler="run_heartbeat")

    runtime = sub.add_parser("runtime", help="Read-only runtime connector and capability commands.")
    runtime_sub = runtime.add_subparsers(dest="action", required=True)
    runtime_connectors = runtime_sub.add_parser("connectors", help="List runtime connector capability manifests and trust states.")
    runtime_connectors.set_defaults(handler="runtime_connectors")

    runtime_event = sub.add_parser("runtime-event", help="Runtime internal event evidence commands.")
    runtime_event_sub = runtime_event.add_subparsers(dest="action", required=True)
    runtime_event_record = runtime_event_sub.add_parser("record", help="Record a redacted runtime/tool event summary for a run.")
    runtime_event_record.add_argument("--run-id", required=True)
    runtime_event_record.add_argument("--agent-id", default=None)
    runtime_event_record.add_argument("--adapter", default=None, choices=["mock", "hermes", "openclaw", "agnesfallback"])
    runtime_event_record.add_argument("--connector-id", default=None)
    runtime_event_record.add_argument("--event-type", default="runtime.tool_event")
    runtime_event_record.add_argument("--status", default="completed", choices=["planned", "running", "completed", "failed", "blocked", "waiting_approval", "unavailable"])
    runtime_event_record.add_argument("--input-summary", default=None)
    runtime_event_record.add_argument("--output-summary", "--summary", dest="output_summary", default=None)
    runtime_event_record.add_argument("--error-message", default=None)
    runtime_event_record.add_argument("--latency-ms", type=int, default=None)
    runtime_event_record.add_argument("--model", default=None)
    runtime_event_record.add_argument("--prompt-hash", default=None)
    runtime_event_record.add_argument("--payload-hash", default=None)
    runtime_event_record.add_argument("--payload-json", default=None, help="Optional raw event payload used only to compute a hash server-side; it is not stored.")
    runtime_event_record.add_argument("--metadata-json", default=None)
    runtime_event_record.add_argument("--source", default="agentops-cli.runtime-event")
    runtime_event_record.set_defaults(handler="runtime_event_record")

    toolcall = sub.add_parser("toolcall", help="Tool call evidence commands.")
    tool_sub = toolcall.add_subparsers(dest="action", required=True)
    record = tool_sub.add_parser("record", help="Record a tool call.")
    record.add_argument("--run-id", required=True)
    record.add_argument("--agent-id", default=None)
    record.add_argument("--tool", required=True)
    record.add_argument("--category", default="custom")
    record.add_argument("--risk", default="low", choices=["low", "medium", "high", "critical"])
    record.add_argument("--status", default="completed")
    record.add_argument("--target", default=None)
    record.add_argument("--args-json", default=None)
    record.add_argument("--args-summary", default=None)
    record.add_argument("--summary", default="")
    record.add_argument("--prepare-action", action="store_true", help="Create a linked prepared action and approval gate for exact resume.")
    record.add_argument("--action-type", default=None, help="Prepared action type. Defaults to --tool.")
    record.add_argument("--policy-version", default="approval-wall-v1")
    record.add_argument("--checkpoint-json", default="{}")
    record.add_argument("--idempotency-key", default=None)
    record.add_argument("--approval-reason", default=None)
    record.add_argument("--approver", default="usr_founder")
    record.set_defaults(handler="toolcall_record")

    artifact = sub.add_parser("artifact", help="Artifact evidence commands.")
    artifact_sub = artifact.add_subparsers(dest="action", required=True)
    artifact_list = artifact_sub.add_parser("list", help="List artifact summaries without fetching raw content.")
    artifact_list.add_argument("--task-id", default=None)
    artifact_list.add_argument("--run-id", default=None)
    artifact_list.add_argument("--type", default=None)
    artifact_list.add_argument("--limit", type=int, default=25)
    artifact_list.set_defaults(handler="artifact_list")

    artifact_record = artifact_sub.add_parser("record", help="Record an artifact summary without storing raw content.")
    artifact_record.add_argument("--run-id", required=True)
    artifact_record.add_argument("--task-id", default=None)
    artifact_record.add_argument("--agent-id", default=None)
    artifact_record.add_argument("--artifact-id", default=None)
    artifact_record.add_argument("--type", default="report")
    artifact_record.add_argument("--title", required=True)
    artifact_record.add_argument("--uri", default=None)
    artifact_record.add_argument("--summary", required=True)
    artifact_record.add_argument("--content-hash", default=None)
    artifact_record.set_defaults(handler="artifact_record")

    knowledge = sub.add_parser("knowledge", help="Knowledge base and Markdown index commands.")
    knowledge_sub = knowledge.add_subparsers(dest="action", required=True)
    knowledge_search = knowledge_sub.add_parser("search", help="Search indexed specs, base notes, runbooks and shared memory.")
    knowledge_search.add_argument("query", nargs="?", default="")
    knowledge_search.add_argument("--limit", type=int, default=10)
    knowledge_search.add_argument("--refresh", action="store_true")
    knowledge_search.set_defaults(handler="knowledge_search")
    knowledge_index = knowledge_sub.add_parser("index", help="Refresh the local Markdown knowledge FTS index.")
    knowledge_index.add_argument("--rebuild", action="store_true")
    knowledge_index.set_defaults(handler="knowledge_index")

    agent_plan = sub.add_parser("agent-plan", help="Agent work method plan commands.")
    agent_plan_sub = agent_plan.add_subparsers(dest="action", required=True)
    agent_plan_create = agent_plan_sub.add_parser("create", help="Submit the required READ/PLAN/RETRIEVE/COMPARE execution plan.")
    agent_plan_create.add_argument("--agent-id", default=None)
    agent_plan_create.add_argument("--task-id", default=None)
    agent_plan_create.add_argument("--run-id", default=None)
    agent_plan_create.add_argument("--task-understanding", "--understanding", dest="task_understanding", required=True)
    agent_plan_create.add_argument("--referenced-specs", default="")
    agent_plan_create.add_argument("--referenced-memories", default="")
    agent_plan_create.add_argument("--referenced-bases", default="")
    agent_plan_create.add_argument("--proposed-files-to-change", default="")
    agent_plan_create.add_argument("--risk", default="medium", choices=["low", "medium", "high", "critical"])
    agent_plan_create.add_argument("--approval-required", action="store_true")
    agent_plan_create.add_argument("--execution-steps", default="")
    agent_plan_create.add_argument("--execution-steps-json", default=None)
    agent_plan_create.add_argument("--verification-plan", default="")
    agent_plan_create.add_argument("--rollback-plan", default="")
    agent_plan_create.add_argument("--status", default="submitted", choices=["draft", "submitted"])
    agent_plan_create.set_defaults(handler="agent_plan_create")
    agent_plan_list = agent_plan_sub.add_parser("list", help="List submitted agent plans.")
    agent_plan_list.add_argument("--task-id", default=None)
    agent_plan_list.add_argument("--run-id", default=None)
    agent_plan_list.add_argument("--agent-id", default=None)
    agent_plan_list.add_argument("--limit", type=int, default=25)
    agent_plan_list.set_defaults(handler="agent_plan_list")
    agent_plan_get = agent_plan_sub.add_parser("get", help="Read one agent plan.")
    agent_plan_get.add_argument("--plan-id", required=True)
    agent_plan_get.set_defaults(handler="agent_plan_get")
    agent_plan_verify = agent_plan_sub.add_parser("verify", help="Verify one agent plan has required method-block evidence.")
    agent_plan_verify.add_argument("--plan-id", required=True)
    agent_plan_verify.set_defaults(handler="agent_plan_verify")
    agent_plan_approve = agent_plan_sub.add_parser("approve", help="Approve a verified Agent Plan through the human/admin governance API.")
    agent_plan_approve.add_argument("--plan-id", required=True)
    agent_plan_approve.add_argument("--approver-user-id", default="usr_founder")
    agent_plan_approve.add_argument("--actor-type", default="user", choices=["user", "admin", "policy"])
    agent_plan_approve.add_argument("--reason", default="CLI Agent Plan approval.")
    agent_plan_approve.set_defaults(handler="agent_plan_approve")
    agent_plan_reject = agent_plan_sub.add_parser("reject", help="Reject an Agent Plan through the human/admin governance API.")
    agent_plan_reject.add_argument("--plan-id", required=True)
    agent_plan_reject.add_argument("--approver-user-id", default="usr_founder")
    agent_plan_reject.add_argument("--actor-type", default="user", choices=["user", "admin", "policy"])
    agent_plan_reject.add_argument("--reason", default="CLI Agent Plan rejection.")
    agent_plan_reject.set_defaults(handler="agent_plan_reject")

    plan_evidence = sub.add_parser("plan-evidence", help="Bind verified agent plans to run/tool/eval/artifact/audit evidence.")
    plan_evidence_sub = plan_evidence.add_subparsers(dest="action", required=True)
    plan_evidence_create = plan_evidence_sub.add_parser("create", help="Create a plan_evidence_manifest for a run.")
    plan_evidence_create.add_argument("--agent-id", default=None)
    plan_evidence_create.add_argument("--manifest-id", default=None)
    plan_evidence_create.add_argument("--plan-id", required=True)
    plan_evidence_create.add_argument("--task-id", default=None)
    plan_evidence_create.add_argument("--run-id", required=True)
    plan_evidence_create.add_argument("--mismatch-policy", default="block", choices=["block", "warn"])
    plan_evidence_create.add_argument("--expected-steps", default="")
    plan_evidence_create.add_argument("--expected-steps-json", default=None)
    plan_evidence_create.add_argument("--tool-call-ids", default="")
    plan_evidence_create.add_argument("--evaluation-ids", default="")
    plan_evidence_create.add_argument("--artifact-ids", default="")
    plan_evidence_create.add_argument("--audit-ids", default="")
    plan_evidence_create.add_argument("--no-verify", action="store_true")
    plan_evidence_create.set_defaults(handler="plan_evidence_create")
    plan_evidence_list = plan_evidence_sub.add_parser("list", help="List plan evidence manifests.")
    plan_evidence_list.add_argument("--plan-id", default=None)
    plan_evidence_list.add_argument("--task-id", default=None)
    plan_evidence_list.add_argument("--run-id", default=None)
    plan_evidence_list.add_argument("--agent-id", default=None)
    plan_evidence_list.add_argument("--limit", type=int, default=25)
    plan_evidence_list.set_defaults(handler="plan_evidence_list")
    plan_evidence_get = plan_evidence_sub.add_parser("get", help="Read one plan evidence manifest.")
    plan_evidence_get.add_argument("--manifest-id", required=True)
    plan_evidence_get.set_defaults(handler="plan_evidence_get")
    plan_evidence_verify = plan_evidence_sub.add_parser("verify", help="Re-verify a plan evidence manifest against the ledger.")
    plan_evidence_verify.add_argument("--manifest-id", required=True)
    plan_evidence_verify.set_defaults(handler="plan_evidence_verify")

    approval = sub.add_parser("approval", help="Approval commands.")
    approval_sub = approval.add_subparsers(dest="action", required=True)
    approval_list = approval_sub.add_parser("list", help="List approvals for operator review.")
    approval_list.add_argument("--decision", choices=["pending", "approved", "rejected", "expired"], default=None)
    approval_list.add_argument("--task-id", default=None)
    approval_list.add_argument("--run-id", default=None)
    approval_list.add_argument("--limit", type=int, default=25)
    approval_list.set_defaults(handler="approval_list")
    approval_inspect = approval_sub.add_parser("inspect", help="Inspect approval evidence and risk before deciding.")
    approval_inspect.add_argument("--approval-id", required=True)
    approval_inspect.set_defaults(handler="approval_inspect")
    approval_prepared = approval_sub.add_parser("prepared-action", help="Create, inspect, and resume exact approval-gated prepared actions.")
    approval_prepared_sub = approval_prepared.add_subparsers(dest="prepared_action_action", required=True)
    prepared_create = approval_prepared_sub.add_parser("create", help="Create a prepared action and linked approval gate.")
    prepared_create.add_argument("--run-id", required=True)
    prepared_create.add_argument("--tool-call-id", default=None)
    prepared_create.add_argument("--agent-id", default=None)
    prepared_create.add_argument("--action-type", required=True)
    prepared_create.add_argument("--args-json", default="{}")
    prepared_create.add_argument("--target-resource", default=None)
    prepared_create.add_argument("--risk-level", choices=["low", "medium", "high", "critical"], default="high")
    prepared_create.add_argument("--policy-version", default="approval-wall-v1")
    prepared_create.add_argument("--checkpoint-json", default="{}")
    prepared_create.add_argument("--idempotency-key", default=None)
    prepared_create.add_argument("--approver", default="usr_founder")
    prepared_create.add_argument("--reason", default="Prepared action requires human approval before exact resume.")
    prepared_create.set_defaults(handler="approval_prepared_action_create")
    prepared_get = approval_prepared_sub.add_parser("get", help="Inspect one prepared action and verify its action hash.")
    prepared_get.add_argument("--action-id", required=True)
    prepared_get.set_defaults(handler="approval_prepared_action_get")
    prepared_resume = approval_prepared_sub.add_parser("resume", help="Resume an approved prepared action exactly once.")
    prepared_resume.add_argument("--action-id", required=True)
    prepared_resume.add_argument("--agent-id", default=None)
    prepared_resume.add_argument("--provider-side-effect-id", default=None)
    prepared_resume.add_argument("--result-summary", default=None)
    prepared_resume.set_defaults(handler="approval_prepared_action_resume")
    approval_approve = approval_sub.add_parser("approve", help="Approve an approval gate and sync linked ledger rows.")
    approval_approve.add_argument("--approval-id", required=True)
    approval_approve.set_defaults(handler="approval_approve")
    approval_reject = approval_sub.add_parser("reject", help="Reject an approval gate and block linked ledger rows.")
    approval_reject.add_argument("--approval-id", required=True)
    approval_reject.set_defaults(handler="approval_reject")
    request = approval_sub.add_parser("request", help="Request human approval.")
    request.add_argument("--task-id", required=True)
    request.add_argument("--run-id", required=True)
    request.add_argument("--tool-call-id", default=None)
    request.add_argument("--agent-id", default=None)
    request.add_argument("--approver", default="usr_founder")
    request.add_argument("--reason", required=True)
    request.set_defaults(handler="approval_request")

    memory = sub.add_parser("memory", help="Memory commands.")
    memory_sub = memory.add_subparsers(dest="action", required=True)
    memory_list = memory_sub.add_parser("list", help="List reviewable memory candidates.")
    memory_list.add_argument("--status", choices=["candidate", "approved", "rejected", "stale", "superseded"], default=None)
    memory_list.add_argument("--scope", choices=["task", "project", "org"], default=None)
    memory_list.add_argument("--type", default=None)
    memory_list.add_argument("--task-id", default=None)
    memory_list.add_argument("--agent-id", default=None)
    memory_list.add_argument("--limit", type=int, default=25)
    memory_list.set_defaults(handler="memory_list")
    memory_approve = memory_sub.add_parser("approve", help="Approve a memory candidate.")
    memory_approve.add_argument("--memory-id", required=True)
    memory_approve.set_defaults(handler="memory_approve")
    memory_reject = memory_sub.add_parser("reject", help="Reject a memory candidate.")
    memory_reject.add_argument("--memory-id", required=True)
    memory_reject.set_defaults(handler="memory_reject")
    propose = memory_sub.add_parser("propose", help="Propose reviewable memory.")
    propose.add_argument("--agent-id", default=None)
    propose.add_argument("--task-id", default=None)
    propose.add_argument("--run-id", default=None)
    propose.add_argument("--scope", default="project", choices=["task", "project", "org"])
    propose.add_argument("--type", default="artifact_summary")
    propose.add_argument("--text", required=True)
    propose.add_argument("--source-ref", default=None)
    propose.add_argument("--access-tags", default="agentops-cli,review")
    propose.add_argument("--confidence", type=float, default=0.72)
    propose.set_defaults(handler="memory_propose")

    eval_parser = sub.add_parser("eval", help="Evaluation commands.")
    eval_sub = eval_parser.add_subparsers(dest="action", required=True)
    submit = eval_sub.add_parser("submit", help="Submit evaluation result.")
    submit.add_argument("--run-id", required=True)
    submit.add_argument("--task-id", default=None)
    submit.add_argument("--agent-id", default=None)
    submit.add_argument("--gate", default="agentops_cli_gate")
    submit.add_argument("--score", type=float, default=1.0)
    submit.add_argument("--pass", dest="passed", action="store_true")
    submit.add_argument("--fail", dest="passed", action="store_false")
    submit.set_defaults(passed=True)
    submit.add_argument("--evaluator-type", default="rule", choices=["human", "rule", "llm_mock"])
    submit.add_argument("--rubric-json", default=None)
    submit.add_argument("--notes", default="Submitted through agentops CLI.")
    submit.set_defaults(handler="eval_submit")
    cases = eval_sub.add_parser("cases", help="List evaluation case candidates.")
    cases.add_argument("--status", default="candidate", choices=["candidate", "approved", "rejected", "stale", "superseded"])
    cases.add_argument("--limit", type=int, default=25)
    cases.add_argument("--run-id", default=None)
    cases.add_argument("--task-id", default=None)
    cases.add_argument("--artifact-id", default=None)
    cases.set_defaults(handler="eval_cases")
    case_runs = eval_sub.add_parser("case-runs", help="List local benchmark evidence produced from approved evaluation cases.")
    case_runs.add_argument("--limit", type=int, default=25)
    case_runs.add_argument("--case-id", default=None)
    case_runs.add_argument("--run-id", default=None)
    case_runs.add_argument("--task-id", default=None)
    case_runs.add_argument("--pass-fail", default=None, choices=["pass", "fail"])
    case_runs.add_argument("--review-status", default=None, choices=["open", "investigating", "acknowledged", "waived"])
    case_runs.set_defaults(handler="eval_case_runs")
    review_case_run = eval_sub.add_parser("review-case-run", help="Mark a failed evaluation case run as investigating, acknowledged, waived, or open.")
    review_case_run.add_argument("--case-run-id", required=True)
    review_case_run.add_argument("--status", default="acknowledged", choices=["open", "investigating", "acknowledged", "waived"])
    review_case_run.add_argument("--note", default="Reviewed from agentops CLI.")
    review_case_run.add_argument("--actor-id", default="usr_operator")
    review_case_run.set_defaults(handler="eval_review_case_run")
    remediate_case_run = eval_sub.add_parser("remediate-case-run", help="Preview or create a normal MIS task from a failed evaluation case run.")
    remediate_case_run.add_argument("--case-run-id", required=True)
    remediate_case_run.add_argument("--task-id", default=None)
    remediate_case_run.add_argument("--title", default=None)
    remediate_case_run.add_argument("--project-id", default=None)
    remediate_case_run.add_argument("--plan-id", default=None)
    remediate_case_run.add_argument("--lane-id", default=None)
    remediate_case_run.add_argument("--owner-agent-id", default=None)
    remediate_case_run.add_argument("--priority", default=None, choices=["low", "medium", "high", "critical"])
    remediate_case_run.add_argument("--risk-level", default=None, choices=["low", "medium", "high", "critical"])
    remediate_case_run.add_argument("--budget-limit-usd", type=float, default=None)
    remediate_case_run.add_argument("--actor-id", default="usr_founder")
    remediate_case_run.add_argument("--confirm-create", action="store_true")
    remediate_case_run.set_defaults(handler="eval_remediate_case_run")
    propose_case = eval_sub.add_parser("propose-case", help="Preview or create an evaluation case candidate from run/eval/artifact evidence.")
    propose_case.add_argument("--case-id", default=None)
    propose_case.add_argument("--source-type", default=None, choices=["evaluation", "customer_delivery", "run", "artifact", "manual", "commander_synthesis"])
    propose_case.add_argument("--source-ref", default=None)
    propose_case.add_argument("--evaluation-id", default=None)
    propose_case.add_argument("--artifact-id", default=None)
    propose_case.add_argument("--run-id", default=None)
    propose_case.add_argument("--task-id", default=None)
    propose_case.add_argument("--agent-id", default=None)
    propose_case.add_argument("--case-type", default=None, choices=["regression", "golden", "safety", "quality", "cost", "tool_use", "memory"])
    propose_case.add_argument("--title", default=None)
    propose_case.add_argument("--input-summary", default=None)
    propose_case.add_argument("--expected-output-summary", default=None)
    propose_case.add_argument("--failure-mode", default=None)
    propose_case.add_argument("--confidence", type=float, default=0.72)
    propose_case.add_argument("--rubric-json", default=None)
    propose_case.add_argument("--confirm-create", action="store_true")
    propose_case.set_defaults(handler="eval_propose_case")
    approve_case = eval_sub.add_parser("approve-case", help="Approve an evaluation case candidate for future regression use.")
    approve_case.add_argument("--case-id", required=True)
    approve_case.set_defaults(handler="eval_approve_case")
    reject_case = eval_sub.add_parser("reject-case", help="Reject a noisy evaluation case candidate.")
    reject_case.add_argument("--case-id", required=True)
    reject_case.set_defaults(handler="eval_reject_case")
    run_cases = eval_sub.add_parser("run-cases", help="Preview or execute approved evaluation cases through the local benchmark runner.")
    run_cases.add_argument("--case-id", action="append", default=None, help="Approved case id to run. Repeatable. Defaults to latest approved cases.")
    run_cases.add_argument("--case-type", default=None, choices=["regression", "golden", "safety", "quality", "cost", "tool_use", "memory"])
    run_cases.add_argument("--status", default="approved", choices=["candidate", "approved", "rejected", "stale", "superseded"])
    run_cases.add_argument("--runner-type", default="rule", choices=["rule", "llm_mock"])
    run_cases.add_argument("--agent-id", default=None)
    run_cases.add_argument("--task-id", default=None)
    run_cases.add_argument("--run-id", default=None)
    run_cases.add_argument("--artifact-id", default=None)
    run_cases.add_argument("--limit", type=int, default=10)
    run_cases.add_argument("--min-score", type=float, default=0.75)
    run_cases.add_argument("--confirm-run", action="store_true")
    run_cases.set_defaults(handler="eval_run_cases")

    audit_parser = sub.add_parser("audit", help="Audit commands.")
    audit_sub = audit_parser.add_subparsers(dest="action", required=True)
    audit_emit = audit_sub.add_parser("emit", help="Emit audit event.")
    audit_emit.add_argument("--agent-id", default=None)
    audit_emit.add_argument("--action", required=True)
    audit_emit.add_argument("--entity-type", required=True)
    audit_emit.add_argument("--entity-id", required=True)
    audit_emit.add_argument("--task-id", default=None)
    audit_emit.add_argument("--run-id", default=None)
    audit_emit.add_argument("--metadata-json", default=None)
    audit_emit.set_defaults(handler="audit_emit")

    workflow = sub.add_parser("workflow", help="Customer-facing workflow commands.")
    workflow_sub = workflow.add_subparsers(dest="action", required=True)
    templates_cmd = workflow_sub.add_parser("templates", help="List customer task templates.")
    templates_cmd.set_defaults(handler="workflow_templates")
    delivery_board = workflow_sub.add_parser("delivery-board", help="Read customer delivery evidence board without mutating the ledger.")
    delivery_board.add_argument("--limit", type=int, default=12)
    delivery_board.set_defaults(handler="workflow_delivery_board")
    loop_lane = workflow_sub.add_parser("hermes-openclaw-loop", help="Run or read back the supervised Hermes/OpenClaw loop lane.")
    loop_lane.add_argument("--topic", default="Review the supervised Hermes/OpenClaw loop lane.")
    loop_lane.add_argument("--rounds", type=int, default=1)
    loop_lane.add_argument("--mode", choices=["dry-run", "live-hermes", "live-openclaw", "live-both"], default="dry-run")
    loop_lane.add_argument("--confirm-live", action="store_true")
    loop_lane.add_argument("--loop-id", default="")
    loop_lane.add_argument("--resume", action="store_true")
    loop_lane.add_argument("--order", nargs="+", choices=["hermes", "openclaw"], default=["hermes", "openclaw"])
    loop_lane.add_argument("--request-timeout", type=int, default=30)
    loop_lane.add_argument("--max-agent-attempts", type=int, default=1)
    loop_lane.add_argument("--retry-delay-sec", type=float, default=1.0)
    loop_lane.add_argument("--simulate-failure-agent", action="append", choices=["hermes", "openclaw"], default=None)
    loop_lane.add_argument("--readback", action="store_true", help="Read ledger evidence for --loop-id instead of running a new loop.")
    loop_lane.add_argument("--limit", type=int, default=10)
    loop_lane.set_defaults(handler="workflow_hermes_openclaw_loop")
    run_template = workflow_sub.add_parser("run-template", help="Run a customer task template through the MIS workflow layer.")
    run_template.add_argument("--template-id", default="tpl_customer_kb_qa_bot")
    run_template.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default=None, help="Optional Agent Worker adapter. Without this, the template uses its default safe workflow.")
    run_template.add_argument("--confirm-run", action="store_true", help="Required when --adapter is hermes or openclaw.")
    run_template.add_argument("--title", default="")
    run_template.add_argument("--description", default="")
    run_template.add_argument("--acceptance", default="")
    run_template.add_argument("--priority", choices=["low", "medium", "high", "critical"], default=None)
    run_template.add_argument("--risk", choices=["low", "medium", "high", "critical"], default=None)
    run_template.add_argument("--selected-agent-id", action="append", default=None)
    run_template.add_argument("--owner-agent-id", default=None)
    run_template.add_argument("--worker-agent-id", default=None)
    run_template.add_argument("--hermes-timeout", type=int, default=None)
    run_template.add_argument("--request-timeout", type=int, default=None)
    run_template.add_argument("--async-job", action="store_true", help="Submit a workflow job and return immediately; use workflow job-status to poll.")
    run_template.set_defaults(handler="workflow_run_template")
    jobs_list = workflow_sub.add_parser("jobs", help="List async workflow jobs with read-only queue summary.")
    jobs_list.add_argument("--status", default="", help="Optional comma-separated status filter: queued,running,completed,failed.")
    jobs_list.add_argument("--workflow-type", default="", help="Optional comma-separated workflow_type filter.")
    jobs_list.add_argument("--limit", type=int, default=25)
    jobs_list.set_defaults(handler="workflow_jobs")
    job_status = workflow_sub.add_parser("job-status", help="Inspect or wait for a submitted workflow job.")
    job_status.add_argument("--job-id", required=True)
    job_status.add_argument("--wait", action="store_true")
    job_status.add_argument("--poll-interval", type=float, default=1.0)
    job_status.add_argument("--timeout", type=int, default=120)
    job_status.set_defaults(handler="workflow_job_status")
    stuck_jobs = workflow_sub.add_parser("stuck-jobs", help="List queued/running workflow jobs that exceeded a threshold.")
    stuck_jobs.add_argument("--threshold-sec", type=int, default=900)
    stuck_jobs.add_argument("--limit", type=int, default=25)
    stuck_jobs.set_defaults(handler="workflow_stuck_jobs")
    job_mark_failed = workflow_sub.add_parser("job-mark-failed", help="Mark a stale queued/running workflow job as failed after operator review.")
    job_mark_failed.add_argument("--job-id", required=True)
    job_mark_failed.add_argument("--reason", default="Operator marked stale workflow job as failed.")
    job_mark_failed.add_argument("--actor-id", default="usr_operator")
    job_mark_failed.set_defaults(handler="workflow_job_mark_failed")
    recover_job = workflow_sub.add_parser("recover-job", help="Preview or execute receipt-backed workflow job recovery.")
    recover_job.add_argument("--job-id", required=True)
    recover_job.add_argument("--mode", choices=["mark-failed", "retry"], default="mark-failed")
    recover_job.add_argument("--reason", default="workflow job recovery requested by operator.")
    recover_job.add_argument("--task-id", default=None, help="Required for retry when the failed job has no result_task_id.")
    recover_job.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default=None)
    recover_job.add_argument("--actor-id", default="usr_operator")
    recover_job.add_argument("--confirm-recover", action="store_true", help="Actually perform recovery. Omitted means preview only.")
    recover_job.add_argument("--record-receipt", action="store_true", help="Record an operator action receipt after confirmed recovery.")
    recover_job.add_argument("--confirm-run", action="store_true", help="Required for Hermes/OpenClaw retry dispatch.")
    recover_job.add_argument("--hermes-timeout", type=int, default=300)
    recover_job.set_defaults(handler="workflow_recover_job")
    customer_worker = workflow_sub.add_parser("customer-worker-task", help="Dispatch a customer task through the AgentOps worker loop.")
    customer_worker.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    customer_worker.add_argument("--confirm-run", action="store_true", help="Required for Hermes/OpenClaw live execution.")
    customer_worker.add_argument("--title", required=True)
    customer_worker.add_argument("--description", required=True)
    customer_worker.add_argument("--acceptance", default="Worker must write run, tool, evaluation, audit and artifact evidence.")
    customer_worker.add_argument("--task-id", default=None, help="Optional existing task id to execute; useful for task-bound evaluation cases.")
    customer_worker.add_argument("--priority", choices=["low", "medium", "high", "critical"], default="high")
    customer_worker.add_argument("--risk", choices=["low", "medium", "high", "critical"], default="medium")
    customer_worker.add_argument("--selected-agent-id", action="append", default=None, help="Optional business agent id to record as selected context. Repeatable.")
    customer_worker.add_argument("--worker-agent-id", default=None, help="Optional exact worker agent id. Defaults to a unique id per dispatch.")
    customer_worker.add_argument("--hermes-timeout", type=int, default=300)
    customer_worker.add_argument("--hermes-max-tokens", type=int, default=int(os.environ.get("HERMES_MAX_TOKENS", "512")))
    customer_worker.add_argument("--adapter-max-attempts", type=int, default=None, help="Maximum live adapter attempts for retryable failures.")
    customer_worker.add_argument("--adapter-retry-delay-sec", type=float, default=None, help="Delay between retryable live adapter attempts.")
    customer_worker.add_argument("--external-write-intent", action="store_true", help="Declare that the live runtime task intends to publish/upload/write to an external target; opaque runtimes will create a prepared action instead of running immediately.")
    customer_worker.add_argument("--target-resource", default=None, help="External write target resource used in the prepared action contract.")
    customer_worker.add_argument("--external-action-type", default=None, help="Prepared action type for external write governance.")
    customer_worker.add_argument("--approval-reason", default=None, help="Human-readable reason for the external-write prepared action approval.")
    customer_worker.add_argument("--async-job", action="store_true", help="Submit the customer worker task as a workflow job and return immediately.")
    customer_worker.set_defaults(handler="workflow_customer_worker_task")

    run_task = workflow_sub.add_parser("run-task", help="Create a normal MIS task and execute one local worker iteration.")
    run_task.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    run_task.add_argument("--confirm-run", action="store_true", help="Required for Hermes/OpenClaw live execution.")
    run_task.add_argument("--task-id", default=None)
    run_task.add_argument("--title", required=True)
    run_task.add_argument("--description", required=True)
    run_task.add_argument("--acceptance", default="Worker must write run, tool, evaluation and audit evidence.")
    run_task.add_argument("--requester-id", default="usr_customer_demo")
    run_task.add_argument("--worker-agent-id", default=None)
    run_task.add_argument("--worker-name", default=None)
    run_task.add_argument("--priority", choices=["low", "medium", "high", "critical"], default="high")
    run_task.add_argument("--risk", choices=["low", "medium", "high", "critical"], default="medium")
    run_task.add_argument("--budget", type=float, default=3.0)
    run_task.add_argument("--use-session", action="store_true", help="Mint a short-lived session before worker execution.")
    run_task.add_argument("--session-ttl-sec", type=int, default=900)
    run_task.add_argument("--adapter-max-attempts", type=int, default=1)
    run_task.add_argument("--adapter-retry-delay-sec", type=float, default=1.0)
    run_task.add_argument("--hermes-gateway-url", default=os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642"))
    run_task.add_argument("--hermes-timeout", type=int, default=300)
    run_task.add_argument("--hermes-max-tokens", type=int, default=int(os.environ.get("HERMES_MAX_TOKENS", "512")))
    run_task.add_argument("--openclaw-bin", default=os.environ.get("OPENCLAW_BIN", "/opt/homebrew/bin/openclaw"))
    run_task.add_argument("--openclaw-timeout", type=int, default=180)
    run_task.set_defaults(handler="workflow_run_task")

    worker = sub.add_parser("worker", help="Worker fleet recovery commands.")
    worker_sub = worker.add_subparsers(dest="action", required=True)
    worker_status = worker_sub.add_parser("status", help="Show worker fleet, daemon, pending task and stuck-task status.")
    worker_status.set_defaults(handler="worker_status")
    worker_fleet = worker_sub.add_parser("fleet", help="Show normalized local/remote worker fleet lanes.")
    worker_fleet.set_defaults(handler="worker_fleet")
    worker_readiness = worker_sub.add_parser("readiness", help="Show read-only mock/Hermes/OpenClaw adapter readiness.")
    worker_readiness.set_defaults(handler="worker_readiness")
    worker_logs = worker_sub.add_parser("logs", help="Show local worker daemon metadata and log tail.")
    worker_logs.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    worker_logs.set_defaults(handler="worker_logs")
    worker_preflight = worker_sub.add_parser("preflight", help="Run read-only Gateway and adapter readiness checks.")
    worker_preflight.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    worker_preflight.add_argument("--agent-id", default=None)
    worker_preflight.add_argument("--timeout", type=int, default=5)
    worker_preflight.add_argument("--hermes-gateway-url", default=os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642"))
    worker_preflight.add_argument("--openclaw-bin", default=os.environ.get("OPENCLAW_BIN", "/opt/homebrew/bin/openclaw"))
    worker_preflight.set_defaults(handler="worker_preflight")
    worker_service_check = worker_sub.add_parser("service-check", help="Read-only check for a launchd/systemd worker service file.")
    worker_service_check.add_argument("--manager", choices=["launchd", "systemd"], required=True)
    worker_service_check.add_argument("--agent-id", default=None)
    worker_service_check.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    worker_service_check.add_argument("--label", default="")
    worker_service_check.add_argument("--service-path", default="")
    worker_service_check.add_argument("--api-key-placeholder", default="<paste one-time token here>")
    worker_service_check.add_argument("--timeout", type=int, default=5)
    worker_service_check.set_defaults(handler="worker_service_check")
    worker_service_install = worker_sub.add_parser("service-install", help="Dry-run or write a safe launchd/systemd worker service file.")
    worker_service_install.add_argument("--manager", choices=["launchd", "systemd"], required=True)
    worker_service_install.add_argument("--agent-id", default=None)
    worker_service_install.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    worker_service_install.add_argument("--confirm-run", action="store_true")
    worker_service_install.add_argument("--session-ttl-sec", type=int, default=900)
    worker_service_install.add_argument("--session-refresh-margin-sec", type=float, default=60)
    worker_service_install.add_argument("--poll-interval", type=float, default=5.0)
    worker_service_install.add_argument("--label", default="")
    worker_service_install.add_argument("--working-directory", default=str(Path.cwd()))
    worker_service_install.add_argument("--runtime-dir", default="")
    worker_service_install.add_argument("--log-path", default="")
    worker_service_install.add_argument("--api-key-placeholder", default="<paste one-time token here>")
    worker_service_install.add_argument("--service-path", default="")
    worker_service_install.add_argument("--confirm-install", action="store_true", help="Write the service file. Default is dry-run.")
    worker_service_install.add_argument("--overwrite", action="store_true")
    worker_service_install.add_argument("--timeout", type=int, default=5)
    worker_service_install.set_defaults(handler="worker_service_install")
    worker_start = worker_sub.add_parser("start", help="Start a local worker daemon through the MIS supervisor.")
    worker_start.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    worker_start.add_argument("--agent-id", default=None)
    worker_start.add_argument("--poll-interval", type=float, default=5.0)
    worker_start.add_argument("--max-tasks", type=int, default=0)
    worker_start.add_argument("--max-errors", type=int, default=5)
    worker_start.add_argument("--status", action="append", default=None)
    worker_start.add_argument("--confirm-run", action="store_true", help="Required for Hermes/OpenClaw live daemons.")
    worker_start.add_argument("--openclaw-timeout", type=int, default=None)
    worker_start.set_defaults(handler="worker_start")
    worker_stop = worker_sub.add_parser("stop", help="Stop one local worker daemon or all daemons.")
    worker_stop.add_argument("--adapter", choices=["mock", "hermes", "openclaw", "all"], default="all")
    worker_stop.set_defaults(handler="worker_stop")
    worker_restart = worker_sub.add_parser("restart", help="Restart one local worker daemon through the MIS supervisor.")
    worker_restart.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    worker_restart.add_argument("--agent-id", default=None)
    worker_restart.add_argument("--poll-interval", type=float, default=None)
    worker_restart.add_argument("--max-tasks", type=int, default=None)
    worker_restart.add_argument("--max-errors", type=int, default=None)
    worker_restart.add_argument("--status", action="append", default=None)
    worker_restart.add_argument("--confirm-run", action="store_true", help="Required before restarting Hermes/OpenClaw live daemons.")
    worker_restart.add_argument("--openclaw-timeout", type=int, default=None)
    worker_restart.set_defaults(handler="worker_restart")
    worker_stuck = worker_sub.add_parser("stuck", help="List running worker tasks that exceeded a threshold.")
    worker_stuck.add_argument("--threshold-sec", type=int, default=900)
    worker_stuck.add_argument("--limit", type=int, default=25)
    worker_stuck.set_defaults(handler="worker_stuck")
    worker_release = worker_sub.add_parser("release", help="Release a running worker task back to planned.")
    worker_release.add_argument("--task-id", required=True)
    worker_release.add_argument("--reason", default="operator_release")
    worker_release.add_argument("--force", action="store_true")
    worker_release.set_defaults(handler="worker_release")
    worker_hygiene = worker_sub.add_parser("hygiene", help="Plan or apply fleet cleanup for stuck tasks and never-seen enrollments.")
    worker_hygiene.add_argument("--threshold-sec", type=int, default=900)
    worker_hygiene.add_argument("--enrollment-age-sec", type=int, default=900)
    worker_hygiene.add_argument("--limit", type=int, default=25)
    worker_hygiene.add_argument("--reason", default="fleet_hygiene_cleanup")
    worker_hygiene.add_argument("--apply", action="store_true", help="Apply cleanup actions. Default is read-only.")
    worker_hygiene.add_argument("--confirm-cleanup", action="store_true", help="Required with --apply.")
    worker_hygiene.set_defaults(handler="worker_hygiene")

    enrollment = sub.add_parser("enrollment", help="Remote/local agent enrollment token commands.")
    enrollment_sub = enrollment.add_subparsers(dest="action", required=True)
    enroll_policy = enrollment_sub.add_parser("policy-preview", help="Preview enrollment scope risk without issuing a token.")
    enroll_policy.add_argument("--runtime", default="mock")
    enroll_policy.add_argument("--workspace-id", default=None)
    enroll_policy.add_argument("--scopes", default="agents:heartbeat,tasks:read,audit:write")
    enroll_policy.set_defaults(handler="enrollment_policy_preview")

    enroll_create = enrollment_sub.add_parser("create", help="Create a scoped one-time-visible agent token.")
    enroll_create.add_argument("--agent-id", required=True)
    enroll_create.add_argument("--name", default="Remote Agent")
    enroll_create.add_argument("--role", default="Remote AI Digital Employee")
    enroll_create.add_argument("--runtime", default="mock")
    enroll_create.add_argument("--scopes", default="agents:write,agents:heartbeat,knowledge:read,agent_plans:read,agent_plans:write,plan_evidence:read,plan_evidence:write,tasks:create,tasks:read,tasks:claim,runs:write,runtime_events:write,toolcalls:write,artifacts:write,approvals:request,memories:propose,evaluations:submit,audit:write")
    enroll_create.add_argument("--ttl-days", type=int, default=30)
    enroll_create.add_argument("--heartbeat-timeout-sec", type=int, default=300)
    enroll_create.add_argument("--label", default="")
    enroll_create.add_argument("--save-token", action="store_true", help="Save returned token to local config for this CLI.")
    enroll_create.set_defaults(handler="enrollment_create")

    enroll_request = enrollment_sub.add_parser("request", help="Request human approval before issuing an enrollment token.")
    enroll_request.add_argument("--agent-id", required=True)
    enroll_request.add_argument("--name", default="Remote Agent")
    enroll_request.add_argument("--role", default="Remote AI Digital Employee")
    enroll_request.add_argument("--runtime", default="mock")
    enroll_request.add_argument("--scopes", default="agents:heartbeat,knowledge:read,agent_plans:read,agent_plans:write,plan_evidence:read,plan_evidence:write,tasks:create,tasks:read,tasks:claim,runs:write,runtime_events:write,toolcalls:write,artifacts:write,memories:propose,evaluations:submit,audit:write")
    enroll_request.add_argument("--reason", default="Remote worker needs scoped access to process assigned MIS tasks.")
    enroll_request.set_defaults(handler="enrollment_request")

    enroll_issue = enrollment_sub.add_parser("issue-approved", help="Issue a token for an approved enrollment request.")
    enroll_issue.add_argument("--request-id", default=None)
    enroll_issue.add_argument("--approval-id", default=None)
    enroll_issue.add_argument("--ttl-days", type=int, default=30)
    enroll_issue.add_argument("--heartbeat-timeout-sec", type=int, default=300)
    enroll_issue.add_argument("--label", default="")
    enroll_issue.add_argument("--save-token", action="store_true", help="Save returned token to local config for this CLI.")
    enroll_issue.set_defaults(handler="enrollment_issue_approved")

    enroll_list = enrollment_sub.add_parser("list", help="List token metadata without secrets.")
    enroll_list.set_defaults(handler="enrollment_list")

    enroll_revoke = enrollment_sub.add_parser("revoke", help="Revoke a token by token id or all active tokens for an agent.")
    enroll_revoke.add_argument("--token-id", default=None)
    enroll_revoke.add_argument("--agent-id", default=None)
    enroll_revoke.set_defaults(handler="enrollment_revoke")

    enroll_rotate = enrollment_sub.add_parser("rotate", help="Rotate an active enrollment token and show the new token once.")
    enroll_rotate.add_argument("--token-id", default=None)
    enroll_rotate.add_argument("--agent-id", default=None)
    enroll_rotate.add_argument("--scopes", default=None, help="Optional replacement scope list. Defaults to old token scopes.")
    enroll_rotate.add_argument("--ttl-days", type=int, default=30)
    enroll_rotate.add_argument("--heartbeat-timeout-sec", type=int, default=None)
    enroll_rotate.add_argument("--label", default="")
    enroll_rotate.add_argument("--save-token", action="store_true", help="Save returned token to local config for this CLI.")
    enroll_rotate.set_defaults(handler="enrollment_rotate")

    session = sub.add_parser("session", help="Short-lived Agent Gateway session commands.")
    session_sub = session.add_subparsers(dest="action", required=True)
    session_create = session_sub.add_parser("create", help="Mint a short-lived session from an enrollment token.")
    session_create.add_argument("--ttl-sec", type=int, default=900)
    session_create.add_argument("--scopes", default=None, help="Optional scope subset for this session.")
    session_create.add_argument("--save-session", action="store_true", help="Save returned session token to local config for this CLI.")
    session_create.set_defaults(handler="session_create")
    session_list = session_sub.add_parser("list", help="List short-lived session metadata without secrets.")
    session_list.set_defaults(handler="session_list")
    session_revoke = session_sub.add_parser("revoke", help="Revoke a session by id or all active sessions for an agent.")
    session_revoke.add_argument("--session-id", default=None)
    session_revoke.add_argument("--agent-id", default=None)
    session_revoke.set_defaults(handler="session_revoke")

    return parser


HANDLERS = {
    "login": lambda args, client: cmd_login(args),
    "status": cmd_status,
    "doctor": cmd_doctor,
    "local_readiness": cmd_local_readiness,
    "demo_readiness": cmd_demo_readiness,
    "command_center_overview": cmd_command_center_overview,
    "operator_action_plan": cmd_operator_action_plan,
    "operator_action_receipts": cmd_operator_action_receipts,
    "operator_record_action_receipt": cmd_operator_record_action_receipt,
    "operator_receipt_failure_memories": cmd_operator_receipt_failure_memories,
    "operator_propose_receipt_failure_memory": cmd_operator_propose_receipt_failure_memory,
    "operator_loop_audit": cmd_operator_loop_audit,
    "operator_loop_control": cmd_operator_loop_control,
    "operator_evidence_report": cmd_operator_evidence_report,
    "operator_handoff": cmd_operator_handoff,
    "operator_loop_self_check": cmd_operator_loop_self_check,
    "operator_advance_loop": cmd_operator_advance_loop,
    "operator_advance_loop_policy": cmd_operator_advance_loop_policy,
    "operator_health": cmd_operator_health,
    "operator_runtime_doctor": cmd_operator_runtime_doctor,
    "operator_live_acceptance": cmd_operator_live_acceptance,
    "operator_execution_mode": cmd_operator_execution_mode,
    "operator_command_center": cmd_operator_command_center,
    "operator_intake_checklist": cmd_operator_intake_checklist,
    "operator_loop_launch_packet": cmd_operator_loop_launch_packet,
    "operator_remediate_evidence_gap": cmd_operator_remediate_evidence_gap,
    "operator_close_evidence_gap": cmd_operator_close_evidence_gap,
    "commander_board": cmd_commander_board,
    "commander_repo_map": cmd_commander_repo_map,
    "commander_coding_template": cmd_commander_coding_template,
    "commander_inbox": cmd_commander_inbox,
    "commander_plan": cmd_commander_plan,
    "commander_packages": cmd_commander_packages,
    "commander_dispatch_package": cmd_commander_dispatch_package,
    "commander_coding_workspace": cmd_commander_coding_workspace,
    "commander_coding_workspace_cleanup": cmd_commander_coding_workspace_cleanup,
    "commander_coding_evidence": cmd_commander_coding_evidence,
    "commander_dispatch_batch": cmd_commander_dispatch_batch,
    "commander_synthesize": cmd_commander_synthesize,
    "commander_promote_synthesis": cmd_commander_promote_synthesis,
    "review_queue": cmd_review_queue,
    "security_production_readiness": cmd_security_production_readiness,
    "agent_register": cmd_agent_register,
    "agent_heartbeat": cmd_agent_heartbeat,
    "task_create": cmd_task_create,
    "task_list": cmd_task_list,
    "task_get": cmd_task_get,
    "task_pull": cmd_task_pull,
    "task_claim": cmd_task_claim,
    "run_list": cmd_run_list,
    "run_get": cmd_run_get,
    "run_graph": cmd_run_graph,
    "run_start": cmd_run_start,
    "run_heartbeat": cmd_run_heartbeat,
    "runtime_connectors": cmd_runtime_connectors,
    "runtime_event_record": cmd_runtime_event_record,
    "toolcall_record": cmd_toolcall_record,
    "artifact_list": cmd_artifact_list,
    "artifact_record": cmd_artifact_record,
    "knowledge_search": cmd_knowledge_search,
    "knowledge_index": cmd_knowledge_index,
    "agent_plan_create": cmd_agent_plan_create,
    "agent_plan_list": cmd_agent_plan_list,
    "agent_plan_get": cmd_agent_plan_get,
    "agent_plan_verify": cmd_agent_plan_verify,
    "agent_plan_approve": cmd_agent_plan_approve,
    "agent_plan_reject": cmd_agent_plan_reject,
    "plan_evidence_create": cmd_plan_evidence_create,
    "plan_evidence_list": cmd_plan_evidence_list,
    "plan_evidence_get": cmd_plan_evidence_get,
    "plan_evidence_verify": cmd_plan_evidence_verify,
    "approval_list": cmd_approval_list,
    "approval_inspect": cmd_approval_inspect,
    "approval_prepared_action_create": cmd_approval_prepared_action_create,
    "approval_prepared_action_get": cmd_approval_prepared_action_get,
    "approval_prepared_action_resume": cmd_approval_prepared_action_resume,
    "approval_approve": cmd_approval_decide,
    "approval_reject": cmd_approval_decide,
    "approval_request": cmd_approval_request,
    "memory_list": cmd_memory_list,
    "memory_approve": cmd_memory_decide,
    "memory_reject": cmd_memory_decide,
    "memory_propose": cmd_memory_propose,
    "eval_submit": cmd_eval_submit,
    "eval_cases": cmd_eval_cases,
    "eval_case_runs": cmd_eval_case_runs,
    "eval_review_case_run": cmd_eval_review_case_run,
    "eval_remediate_case_run": cmd_eval_remediate_case_run,
    "eval_propose_case": cmd_eval_propose_case,
    "eval_approve_case": cmd_eval_review_case,
    "eval_reject_case": cmd_eval_review_case,
    "eval_run_cases": cmd_eval_run_cases,
    "audit_emit": cmd_audit_emit,
    "workflow_templates": cmd_workflow_templates,
    "workflow_delivery_board": cmd_workflow_delivery_board,
    "workflow_hermes_openclaw_loop": cmd_workflow_hermes_openclaw_loop,
    "workflow_run_template": cmd_workflow_run_template,
    "workflow_jobs": cmd_workflow_jobs,
    "workflow_job_status": cmd_workflow_job_status,
    "workflow_stuck_jobs": cmd_workflow_stuck_jobs,
    "workflow_job_mark_failed": cmd_workflow_job_mark_failed,
    "workflow_recover_job": cmd_workflow_recover_job,
    "workflow_customer_worker_task": cmd_workflow_customer_worker_task,
    "workflow_run_task": cmd_workflow_run_task,
    "worker_status": cmd_worker_status,
    "worker_fleet": cmd_worker_fleet,
    "worker_readiness": cmd_worker_readiness,
    "worker_logs": cmd_worker_logs,
    "worker_preflight": cmd_worker_preflight,
    "worker_service_check": cmd_worker_service_check,
    "worker_service_install": cmd_worker_service_install,
    "worker_start": cmd_worker_start,
    "worker_stop": cmd_worker_stop,
    "worker_restart": cmd_worker_restart,
    "worker_stuck": cmd_worker_stuck,
    "worker_release": cmd_worker_release,
    "worker_hygiene": cmd_worker_hygiene,
    "enrollment_policy_preview": cmd_enrollment_policy_preview,
    "enrollment_create": cmd_enrollment_create,
    "enrollment_request": cmd_enrollment_request,
    "enrollment_issue_approved": cmd_enrollment_issue_approved,
    "enrollment_list": cmd_enrollment_list,
    "enrollment_revoke": cmd_enrollment_revoke,
    "enrollment_rotate": cmd_enrollment_rotate,
    "session_create": cmd_session_create,
    "session_list": cmd_session_list,
    "session_revoke": cmd_session_revoke,
}


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    context = resolved_context(args)
    client = AgentOpsClient(context)
    try:
        result = HANDLERS[args.handler](args, client)
    except RuntimeError as exc:
        eprint(redact_text(str(exc), 1200))
        return 1
    exit_code = int(result.pop("_exit_code", 0) or 0) if isinstance(result, dict) else 0
    emit(result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
