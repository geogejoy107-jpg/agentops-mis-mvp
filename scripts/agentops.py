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
import json
import os
import stat
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_WORKSPACE_ID = "local-demo"
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
    return {
        "base_url": (args.base_url or os.environ.get("AGENTOPS_BASE_URL") or config.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
        "api_key": args.api_key if args.api_key is not None else os.environ.get("AGENTOPS_API_KEY", config.get("api_key", "")),
        "workspace_id": args.workspace_id or os.environ.get("AGENTOPS_WORKSPACE_ID") or config.get("workspace_id") or DEFAULT_WORKSPACE_ID,
        "agent_id": args.agent_id or os.environ.get("AGENTOPS_AGENT_ID") or config.get("agent_id") or "",
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


class AgentOpsClient:
    def __init__(self, context: dict):
        self.base_url = context["base_url"].rstrip("/")
        self.api_key = context["api_key"] or ""
        self.workspace_id = context["workspace_id"]
        self.agent_id = context["agent_id"]

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
            with urlopen(req, timeout=30) as res:
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


def add_global_args(parser):
    parser.add_argument("--base-url", default=None, help="AgentOps MIS base URL. Defaults to env/config/http://127.0.0.1:8787.")
    parser.add_argument("--api-key", default=None, help="Local API key. Prefer AGENTOPS_API_KEY for real use.")
    parser.add_argument("--workspace-id", default=None, help="Workspace id. Defaults to env/config/local-demo.")
    parser.add_argument("--agent-id", default=None, help="Default agent id for this command.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentops", description="AgentOps MIS local Agent Gateway CLI.")
    add_global_args(parser)
    sub = parser.add_subparsers(dest="resource", required=True)

    login = sub.add_parser("login", help="Store local AgentOps MIS CLI config.")
    add_global_args(login)
    login.set_defaults(handler="login")

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

    approval = sub.add_parser("approval", help="Approval commands.")
    approval_sub = approval.add_subparsers(dest="action", required=True)
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

    return parser


HANDLERS = {
    "login": lambda args, client: cmd_login(args),
    "agent_register": cmd_agent_register,
    "agent_heartbeat": cmd_agent_heartbeat,
    "task_pull": cmd_task_pull,
    "task_claim": cmd_task_claim,
    "run_start": cmd_run_start,
    "run_heartbeat": cmd_run_heartbeat,
    "toolcall_record": cmd_toolcall_record,
    "approval_request": cmd_approval_request,
    "memory_propose": cmd_memory_propose,
    "eval_submit": cmd_eval_submit,
    "audit_emit": cmd_audit_emit,
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
