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
import io
import json
import os
import stat
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
            raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc

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

    has_token = bool(client.api_key)
    setup_hints = []
    if not has_token:
        setup_hints.append("No AGENTOPS_API_KEY/config token detected. Local dev may still work, but remote agents should use a scoped enrollment token or short-lived session.")
    if not client.agent_id:
        setup_hints.append("No agent id resolved. Set AGENTOPS_AGENT_ID or run agentops login --agent-id ... before remote worker use.")
    if gateway and not (gateway.get("auth") or {}).get("authenticated") and has_token:
        setup_hints.append("A token was provided but Agent Gateway did not authenticate it; rotate or re-enroll the agent.")
    if workers and workers.get("stuck_worker_tasks", 0):
        setup_hints.append("Stuck worker tasks detected. Run agentops worker stuck and agentops worker release after review.")

    return {
        "ok": all(item.get("ok") for item in checks),
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


def cmd_commander_board(args, client: AgentOpsClient) -> dict:
    return client.get("/api/commander/project-board")


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


def cmd_approval_decide(args, client: AgentOpsClient) -> dict:
    action = "approve" if args.handler == "approval_approve" else "reject"
    response = client.post(f"/api/approvals/{args.approval_id}/{action}", {})
    approval = response.get("approval") if isinstance(response.get("approval"), dict) else response
    return {
        "provider": "agentops-approval",
        "operation": f"approval_{action}",
        "approval": approval,
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
        "priority": args.priority,
        "risk_level": args.risk,
        "selected_agent_ids": args.selected_agent_id or [],
        "worker_agent_id": args.worker_agent_id,
        "hermes_timeout": args.hermes_timeout,
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


def cmd_workflow_stuck_jobs(args, client: AgentOpsClient) -> dict:
    return client.get("/api/workflows/jobs/stuck", query={"threshold_sec": args.threshold_sec, "limit": args.limit})


def cmd_workflow_job_mark_failed(args, client: AgentOpsClient) -> dict:
    return client.post(
        f"/api/workflows/jobs/{args.job_id}/mark-failed",
        {"reason": args.reason, "actor_id": args.actor_id},
    )


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
        "--api-key",
        client.api_key,
        "--adapter",
        args.adapter,
        "--once",
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
    evidence = {
        "tool_calls": len((run_detail or {}).get("tool_calls") or []),
        "evaluations": len((run_detail or {}).get("evaluations") or []),
        "approvals": len((run_detail or {}).get("approvals") or []),
        "artifacts": len((run_detail or {}).get("artifacts") or []),
    }
    run = (run_detail or {}).get("run") or {}
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
        },
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

    commander = sub.add_parser("commander", help="Read-only commander surface readback commands.")
    commander_sub = commander.add_subparsers(dest="action", required=True)
    commander_board = commander_sub.add_parser("board", help="Read the Commander project board.")
    commander_board.set_defaults(handler="commander_board")
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
    pull.add_argument("--limit", type=int, default=10)
    pull.add_argument("--status", action="append", default=None, help="Task status filter. Can be repeated.")
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
    agent_plan_create.add_argument("--task-understanding", required=True)
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
    agent_plan_create.add_argument("--status", default="submitted", choices=["draft", "submitted", "approved", "rejected", "superseded"])
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
    customer_worker = workflow_sub.add_parser("customer-worker-task", help="Dispatch a customer task through the AgentOps worker loop.")
    customer_worker.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    customer_worker.add_argument("--confirm-run", action="store_true", help="Required for Hermes/OpenClaw live execution.")
    customer_worker.add_argument("--title", required=True)
    customer_worker.add_argument("--description", required=True)
    customer_worker.add_argument("--acceptance", default="Worker must write run, tool, evaluation, audit and artifact evidence.")
    customer_worker.add_argument("--priority", choices=["low", "medium", "high", "critical"], default="high")
    customer_worker.add_argument("--risk", choices=["low", "medium", "high", "critical"], default="medium")
    customer_worker.add_argument("--selected-agent-id", action="append", default=None, help="Optional business agent id to record as selected context. Repeatable.")
    customer_worker.add_argument("--worker-agent-id", default=None, help="Optional exact worker agent id. Defaults to a unique id per dispatch.")
    customer_worker.add_argument("--hermes-timeout", type=int, default=300)
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
    enroll_create.add_argument("--scopes", default="agents:write,agents:heartbeat,knowledge:read,agent_plans:read,agent_plans:write,plan_evidence:read,plan_evidence:write,tasks:create,tasks:read,tasks:claim,runs:write,toolcalls:write,artifacts:write,approvals:request,memories:propose,evaluations:submit,audit:write")
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
    enroll_request.add_argument("--scopes", default="agents:heartbeat,knowledge:read,agent_plans:read,agent_plans:write,plan_evidence:read,plan_evidence:write,tasks:create,tasks:read,tasks:claim,runs:write,toolcalls:write,artifacts:write,memories:propose,evaluations:submit,audit:write")
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
    "commander_board": cmd_commander_board,
    "commander_inbox": cmd_commander_inbox,
    "commander_plan": cmd_commander_plan,
    "commander_packages": cmd_commander_packages,
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
    "toolcall_record": cmd_toolcall_record,
    "artifact_list": cmd_artifact_list,
    "artifact_record": cmd_artifact_record,
    "knowledge_search": cmd_knowledge_search,
    "knowledge_index": cmd_knowledge_index,
    "agent_plan_create": cmd_agent_plan_create,
    "agent_plan_list": cmd_agent_plan_list,
    "agent_plan_get": cmd_agent_plan_get,
    "agent_plan_verify": cmd_agent_plan_verify,
    "plan_evidence_create": cmd_plan_evidence_create,
    "plan_evidence_list": cmd_plan_evidence_list,
    "plan_evidence_get": cmd_plan_evidence_get,
    "plan_evidence_verify": cmd_plan_evidence_verify,
    "approval_list": cmd_approval_list,
    "approval_approve": cmd_approval_decide,
    "approval_reject": cmd_approval_decide,
    "approval_request": cmd_approval_request,
    "memory_list": cmd_memory_list,
    "memory_approve": cmd_memory_decide,
    "memory_reject": cmd_memory_decide,
    "memory_propose": cmd_memory_propose,
    "eval_submit": cmd_eval_submit,
    "audit_emit": cmd_audit_emit,
    "workflow_templates": cmd_workflow_templates,
    "workflow_delivery_board": cmd_workflow_delivery_board,
    "workflow_hermes_openclaw_loop": cmd_workflow_hermes_openclaw_loop,
    "workflow_run_template": cmd_workflow_run_template,
    "workflow_job_status": cmd_workflow_job_status,
    "workflow_stuck_jobs": cmd_workflow_stuck_jobs,
    "workflow_job_mark_failed": cmd_workflow_job_mark_failed,
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
        eprint(str(exc))
        return 1
    emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
