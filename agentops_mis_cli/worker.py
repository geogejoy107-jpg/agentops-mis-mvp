#!/usr/bin/env python3
"""
Local AgentOps MIS worker daemon.

This is the v1.5 bridge from "Agent Gateway protocol works" to "an agent can
actually pull a MIS task, execute it through a local adapter, and write evidence
back." It intentionally uses the HTTP Agent Gateway API instead of direct
SQLite writes so the same shape can later run on another machine.

The worker never stores full prompts, raw responses, credentials, transcripts,
or private messages. Tool evidence uses short summaries and hashes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agentops_mis_cli.http_transport import credential_opener, credential_transport_url_allowed, safe_credential_error
from agentops_mis_cli.redaction import redact_text


PACKAGE_LINK_ROOT = Path(__file__).absolute().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT if (PACKAGE_ROOT / "server.py").exists() else None
DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_WORKSPACE_ID = "local-demo"
DEFAULT_AGENT_ID = "agt_worker_local"
DEFAULT_HERMES_GATEWAY_URL = "http://127.0.0.1:8642"
DEFAULT_HERMES_MODEL = "hermes-agent"
DEFAULT_HERMES_MAX_TOKENS = int(os.environ.get("HERMES_MAX_TOKENS", "512"))
DEFAULT_OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
WORKER_SECRET_BOUNDARY_VERSION = "trusted_worker_client_v1"
DEFAULT_CONFIG_PATH = Path(os.environ.get("AGENTOPS_CONFIG", "~/.agentops/config.json")).expanduser()
LOCAL_CONFIG_WORKER_SESSION_SCOPES = (
    "agents:write",
    "agents:heartbeat",
    "agent_plans:read",
    "agent_plans:write",
    "plan_evidence:read",
    "plan_evidence:write",
    "knowledge:read",
    "knowledge:write",
    "tasks:read",
    "tasks:claim",
    "runs:write",
    "runtime_events:write",
    "toolcalls:write",
    "artifacts:write",
    "memories:propose",
    "evaluations:submit",
    "audit:write",
)


def default_runtime_dir() -> Path:
    configured = os.environ.get("AGENTOPS_WORKER_RUNTIME_DIR")
    if configured:
        return Path(configured).expanduser()
    if REPO_ROOT:
        return REPO_ROOT / ".agentops_runtime" / "workers"
    return Path(os.environ.get("AGENTOPS_HOME", "~/.agentops")).expanduser() / "workers"


def default_worker_cwd() -> Path:
    configured = os.environ.get("AGENTOPS_WORKER_CWD")
    if configured:
        return Path(configured).expanduser()
    if REPO_ROOT:
        if PACKAGE_ROOT.parent.name == "versions":
            current = PACKAGE_ROOT.parent.parent / "current"
            if current.is_symlink() and current.resolve() == PACKAGE_ROOT:
                return current
        return PACKAGE_LINK_ROOT
    return Path.cwd()


DEFAULT_RUNTIME_DIR = default_runtime_dir()
DEFAULT_WORKER_CWD = default_worker_cwd()
DEFAULT_API_KEY_PLACEHOLDER = "<paste one-time token here>"


SHOULD_STOP = False


def handle_stop_signal(_signum, _frame):
    global SHOULD_STOP
    SHOULD_STOP = True


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_iso_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception:
        return None


def stable_hash(value) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def current_process_identity() -> dict:
    """Return a non-reversible identity for this worker process."""
    pid = os.getpid()
    try:
        process = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "lstart=", "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        rendered = process.stdout.strip()
        process_group_id = os.getpgid(pid)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if process.returncode != 0 or not rendered:
        return {}
    return {
        "process_identity_schema_version": 1,
        "process_group_id": process_group_id,
        "process_identity_hash": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
    }


def json_dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def safe_error(exc: Exception | str) -> dict:
    return {
        "error_type": exc.__class__.__name__ if isinstance(exc, Exception) else "WorkerError",
        "error_message": redact_text(str(exc), 260),
    }


class WorkerCredentialError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def load_local_config_api_key(args) -> str:
    if str(getattr(args, "api_key", "") or ""):
        raise WorkerCredentialError("local_config_conflicts_with_direct_api_key")
    config_path = Path(str(getattr(args, "config_path", "") or DEFAULT_CONFIG_PATH)).expanduser()
    if config_path.is_symlink():
        raise WorkerCredentialError("local_config_symlink_rejected")
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(config_path, flags)
    except FileNotFoundError as exc:
        raise WorkerCredentialError("local_config_not_found") from exc
    except OSError as exc:
        raise WorkerCredentialError("local_config_unreadable") from exc
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise WorkerCredentialError("local_config_not_regular_file")
        if file_stat.st_mode & 0o077:
            raise WorkerCredentialError("local_config_permissions_too_open")
        if hasattr(os, "getuid") and file_stat.st_uid != os.getuid():
            raise WorkerCredentialError("local_config_owner_mismatch")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            config = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkerCredentialError("local_config_invalid") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(config, dict):
        raise WorkerCredentialError("local_config_invalid")
    requested_base_url = str(args.base_url or "").rstrip("/")
    configured_base_url = str(config.get("base_url") or "").rstrip("/")
    configured_key_origin = str(config.get("api_key_base_url") or "").rstrip("/")
    if not requested_base_url or configured_base_url != requested_base_url or configured_key_origin != requested_base_url:
        raise WorkerCredentialError("local_config_origin_mismatch")
    if str(config.get("workspace_id") or "") != str(args.workspace_id or ""):
        raise WorkerCredentialError("local_config_workspace_mismatch")
    api_key = str(config.get("api_key") or "").strip()
    if not api_key:
        raise WorkerCredentialError("local_config_api_key_missing")
    if not credential_transport_url_allowed(requested_base_url):
        raise WorkerCredentialError("local_config_transport_rejected")
    return api_key


def resolve_worker_api_key(args) -> str:
    source = str(getattr(args, "credential_source", "direct") or "direct").strip().lower()
    if source == "direct":
        return str(getattr(args, "api_key", "") or "")
    if source == "local_config":
        return load_local_config_api_key(args)
    raise WorkerCredentialError("credential_source_unsupported")


def apply_local_config_session_policy(args) -> None:
    if str(getattr(args, "credential_source", "direct") or "direct") != "local_config":
        return
    allowed = set(LOCAL_CONFIG_WORKER_SESSION_SCOPES)
    requested = split_csv(getattr(args, "session_scopes", ""))
    if requested and not set(requested).issubset(allowed):
        raise WorkerCredentialError("local_config_session_scopes_exceed_worker_policy")
    args.session_scopes = ",".join(requested or LOCAL_CONFIG_WORKER_SESSION_SCOPES)
    args.use_session = True


class WorkerState:
    def __init__(self, args):
        if args.state_path:
            self.path = Path(args.state_path)
        else:
            self.path = DEFAULT_RUNTIME_DIR / f"{args.adapter}.state.json"
        self.enabled = bool(args.write_state or args.state_path)
        management_mode = str(os.environ.get("AGENTOPS_WORKER_MANAGEMENT_MODE") or "standalone").strip().lower()
        if management_mode not in {"standalone", "daemon_api", "host_stack"}:
            management_mode = "standalone"
        self.data = {
            "adapter": args.adapter,
            "agent_id": args.agent_id,
            "workspace_id": args.workspace_id,
            "base_url": args.base_url,
            "pid": os.getpid(),
            **current_process_identity(),
            "management_mode": management_mode,
            "confirm_run": bool(args.confirm_run),
            "poll_interval": args.poll_interval,
            "max_tasks": args.max_tasks,
            "status": "starting",
            "processed": 0,
            "iterations": 0,
            "total_errors": 0,
            "consecutive_errors": 0,
            "consecutive_idle": 0,
            "max_errors": args.max_errors,
            "continue_on_error": bool(args.continue_on_error),
            "backoff_factor": args.backoff_factor,
            "idle_backoff_max": args.idle_backoff_max,
            "error_backoff_max": args.error_backoff_max,
            "last_sleep_sec": 0,
            "next_sleep_sec": 0,
            "session_refresh_count": 0,
            "adapter_max_attempts": args.adapter_max_attempts,
            "started_at": now_iso(),
            "updated_at": now_iso(),
            "last_heartbeat_at": None,
            "last_result": None,
            "last_error": None,
        }
        self.write()

    def update(self, **kwargs):
        self.data.update(kwargs)
        self.data["updated_at"] = now_iso()
        self.write()

    def record_result(self, result: dict):
        if result.get("processed"):
            self.data["processed"] = int(self.data.get("processed") or 0) + 1
            self.data["consecutive_idle"] = 0
        else:
            self.data["consecutive_idle"] = int(self.data.get("consecutive_idle") or 0) + 1
        self.data["iterations"] = int(self.data.get("iterations") or 0) + 1
        self.data["consecutive_errors"] = 0
        self.data["last_error"] = None
        self.update(
            status="idle" if not result.get("processed") else "completed" if result.get("ok", True) else "failed",
            last_result=result,
            last_task_id=result.get("task_id"),
            last_run_id=result.get("run_id"),
            last_heartbeat_at=now_iso(),
        )

    def record_error(self, exc: Exception | str):
        error = safe_error(exc)
        self.data["iterations"] = int(self.data.get("iterations") or 0) + 1
        self.data["total_errors"] = int(self.data.get("total_errors") or 0) + 1
        self.data["consecutive_errors"] = int(self.data.get("consecutive_errors") or 0) + 1
        self.update(status="error", last_error=error, last_result=None, last_heartbeat_at=now_iso())
        return error

    def stop(self, status: str = "stopped"):
        self.update(status=status, stopped_at=now_iso())

    def write(self):
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass


class AgentOpsClient:
    def __init__(self, base_url: str, workspace_id: str, agent_id: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.workspace_id = workspace_id
        self.agent_id = agent_id
        self.api_key = api_key

    def safe_error_detail(self, value: object, limit: int) -> str:
        return safe_credential_error(value, self.api_key, limit)

    def request(self, method: str, path: str, payload: dict | None = None, query: dict | None = None, timeout: int = 180):
        url = self.base_url + path
        if query:
            url += "?" + urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
        headers = {
            "Content-Type": "application/json",
            "X-AgentOps-Workspace-Id": self.workspace_id,
            "X-AgentOps-Agent-Id": self.agent_id,
        }
        if self.api_key:
            if not credential_transport_url_allowed(url):
                raise RuntimeError("Credentialed Agent Gateway requests require HTTPS or a literal loopback HTTP target")
            headers["X-AgentOps-Api-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        req = Request(url, data=data, headers=headers, method=method)
        try:
            opener = credential_opener()
            with opener.open(req, timeout=timeout) as res:
                raw = res.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: {exc.code} {self.safe_error_detail(detail, 1200)}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach {self.safe_error_detail(url, 500)}: {self.safe_error_detail(exc.reason, 500)}") from exc

    def get(self, path: str, query: dict | None = None):
        return self.request("GET", path, query=query)

    def post(self, path: str, payload: dict, timeout: int = 180):
        return self.request("POST", path, payload=payload, timeout=timeout)


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def mint_worker_session(client: AgentOpsClient, args, parent_api_key: str | None = None) -> dict:
    if parent_api_key:
        client.api_key = parent_api_key
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "ttl_sec": args.session_ttl_sec,
    }
    requested_scopes = split_csv(args.session_scopes)
    if requested_scopes:
        payload["scopes"] = requested_scopes
    session = client.post("/api/agent-gateway/session/create", payload, timeout=30)
    token = session.get("session_token")
    if not token:
        raise RuntimeError("session create did not return a one-time session token")
    client.api_key = token
    return {
        "session_id": session.get("session_id"),
        "expires_at": session.get("expires_at"),
        "ttl_sec": session.get("ttl_sec"),
        "scopes": session.get("scopes") or [],
        "token_omitted": True,
    }


def session_seconds_remaining(session_info: dict | None) -> float:
    expires = parse_iso_datetime((session_info or {}).get("expires_at"))
    if not expires:
        return 0.0
    return (expires - dt.datetime.now(dt.timezone.utc)).total_seconds()


def session_needs_refresh(session_info: dict | None, refresh_margin_sec: float) -> bool:
    if not session_info:
        return True
    return session_seconds_remaining(session_info) <= max(float(refresh_margin_sec or 0), 0.0)


def ensure_worker_session(client: AgentOpsClient, args, state: WorkerState, parent_api_key: str, session_info: dict | None, session_history: list[dict]) -> dict:
    if not session_needs_refresh(session_info, args.session_refresh_margin_sec):
        return session_info or {}
    state.update(status="refreshing_session" if session_info else "minting_session")
    next_session = mint_worker_session(client, args, parent_api_key=parent_api_key)
    session_history.append(next_session)
    refresh_count = max(len(session_history) - 1, 0)
    state.update(
        status="session_ready",
        session_id=next_session.get("session_id"),
        session_expires_at=next_session.get("expires_at"),
        session_refresh_count=refresh_count,
    )
    return next_session


@dataclass
class AdapterResult:
    ok: bool
    output_summary: str
    prompt_hash: str
    prompt_profile_id: str = "general_customer_delivery_summary"
    prompt_profile_version: str = "worker_prompt_profiles_v1"
    prompt_profile_hash: str | None = None
    raw_payload_hash: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    duration_ms: int = 0
    output_tokens: int = 0
    target_resource: str | None = None
    retryable: bool = False
    attempt_count: int = 1
    max_attempts: int = 1
    retry_history: list[dict] | None = None


PROMPT_PROFILE_VERSION = "worker_prompt_profiles_v1"


def select_task_prompt_profile(task: dict, adapter: str | None = None) -> dict:
    combined = " ".join([
        str(task.get("title") or ""),
        str(task.get("description") or ""),
        str(task.get("acceptance_criteria") or ""),
    ]).lower()
    profile_id = "general_customer_delivery_summary"
    if any(term in combined for term in [
        "coding", "code", "repo", "repository", "worktree", "branch", "patch", "test", "tsx", "typescript",
        "代码", "仓库", "分支", "补丁", "测试", "修复", "实现", "前端", "后端",
    ]):
        profile_id = "local_coding_project_summary"
    elif any(term in combined for term in [
        "knowledge", "file search", "qa bot", "q&a", "dataset", "retrieval",
        "知识库", "问答", "资料", "检索", "引用",
    ]):
        profile_id = "knowledge_base_delivery_summary"
    elif any(term in combined for term in [
        "review", "audit", "evaluate", "qa", "quality", "acceptance", "验收", "审计", "审查", "评估", "质量",
    ]):
        profile_id = "review_quality_gate_summary"
    profile_map = {
        "general_customer_delivery_summary": {
            "objective": "Turn a customer task into a concise delivery summary with risks, evidence, and next actions.",
            "output_contract": ["delivery_summary", "risks_or_blockers", "recommended_next_actions"],
        },
        "local_coding_project_summary": {
            "objective": "Analyze a coding task and return implementation guidance plus verification commands without editing files directly.",
            "output_contract": ["implementation_plan", "affected_surfaces", "verification_commands", "risks_or_blockers"],
        },
        "knowledge_base_delivery_summary": {
            "objective": "Analyze a knowledge-base or Q&A bot task and return ingestion, retrieval, evaluation, and delivery guidance.",
            "output_contract": ["source_preparation", "retrieval_design", "evaluation_questions", "delivery_report"],
        },
        "review_quality_gate_summary": {
            "objective": "Review task evidence against acceptance gates and return pass/fail risks plus remediation steps.",
            "output_contract": ["gate_assessment", "missing_evidence", "remediation_steps"],
        },
    }
    profile = dict(profile_map.get(profile_id) or profile_map["general_customer_delivery_summary"])
    profile.update({
        "profile_id": profile_id,
        "version": PROMPT_PROFILE_VERSION,
        "adapter": adapter or "worker",
        "channel": "ledger_summary_only",
        "prohibited_actions": [
            "shell_execution",
            "browser_operation",
            "filesystem_write",
            "mis_api_write",
            "external_publish_upload_or_deploy",
            "credential_request",
        ],
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "token_omitted": True,
    })
    profile["profile_hash"] = stable_hash({
        "profile_id": profile["profile_id"],
        "version": profile["version"],
        "channel": profile["channel"],
        "output_contract": profile["output_contract"],
        "prohibited_actions": profile["prohibited_actions"],
    })
    return profile


def build_task_prompt_bundle(task: dict, adapter: str | None = None) -> tuple[str, dict]:
    profile = select_task_prompt_profile(task, adapter=adapter)
    title = redact_text(task.get("title"), 180)
    description = redact_text(task.get("description"), 900)
    acceptance = redact_text(task.get("acceptance_criteria"), 500)
    risk = redact_text(task.get("risk_level") or "medium", 40)
    knowledge = task.get("_knowledge_retrieval_evidence") or {}
    knowledge_paths = [redact_text(path, 120) for path in (knowledge.get("paths") or [])[:5]]
    knowledge_metrics = knowledge.get("metrics") or {}
    knowledge_context = (
        "项目知识检索证据："
        f"status={redact_text(knowledge.get('packet_status') or knowledge.get('status') or 'unavailable', 60)}; "
        f"packet_hash={redact_text(knowledge.get('packet_hash'), 80)}; "
        f"query_hash={redact_text(knowledge.get('query_hash'), 80)}; "
        f"recall_at_5={knowledge_metrics.get('recall_at_5')}; "
        f"mrr={knowledge_metrics.get('mrr')}; "
        f"paths={', '.join(knowledge_paths) if knowledge_paths else 'none'}; "
        "raw_query/snippet/content/prompt/response/token omitted.\n"
    )
    loop = task.get("_loop_supervision_gate") if isinstance(task.get("_loop_supervision_gate"), dict) else {}
    service = loop.get("service_managed_loop") if isinstance(loop.get("service_managed_loop"), dict) else {}
    local_deployment = loop.get("local_deployment") if isinstance(loop.get("local_deployment"), dict) else {}
    service_context = ""
    if loop:
        service_context = (
            "本地服务循环证据："
            f"adapter={redact_text(loop.get('adapter') or adapter or 'worker', 40)}; "
            f"agent_id={redact_text(loop.get('agent_id'), 120)}; "
            f"task_id={redact_text(loop.get('task_id') or task.get('task_id'), 120)}; "
            f"gate_status={redact_text(loop.get('status'), 60)}; "
            f"ready_for_live_dispatch={bool(loop.get('ready_for_live_dispatch'))}; "
            f"service_managed_loop_ready={bool(service.get('service_managed_loop_ready'))}; "
            f"service_loaded={bool(service.get('service_loaded'))}; "
            f"service_active_loop_ready={bool(service.get('service_active_loop_ready'))}; "
            f"active_status={redact_text(service.get('active_loop_status') or service.get('active_status'), 60)}; "
            f"manager={redact_text(service.get('manager'), 40)}; "
            f"receipt_id={redact_text(service.get('receipt_id'), 80)}; "
            f"control_readback_id={redact_text(service.get('control_readback_id'), 80)}; "
            f"readback_status={redact_text(service.get('readback_verification_status'), 60)}; "
            f"supervision_hash={redact_text(loop.get('supervision_hash'), 80)}; "
            f"local_run_path_present={bool(local_deployment.get('local_run_path_present'))}; "
            "proof_source=/api/operator/loop-supervision; "
            "server_shell=false; raw_service_template/prompt/response/token omitted.\n"
        )
    intake_plan = task.get("_intake_plan_evidence") if isinstance(task.get("_intake_plan_evidence"), dict) else {}
    intake_plan_context = ""
    if intake_plan:
        intake_plan_context = (
            "执行前计划证据："
            f"plan_id={redact_text(intake_plan.get('plan_id'), 80)}; "
            f"plan_verified={bool(intake_plan.get('plan_verified'))}; "
            f"plan_reused_from_intake={bool(intake_plan.get('plan_reused_from_intake'))}; "
            f"source={redact_text(intake_plan.get('source'), 80)}; "
            f"verification_source={redact_text(intake_plan.get('verification_source'), 120)}; "
            f"auto_plan_intake_supported={bool(intake_plan.get('auto_plan_intake_supported'))}; "
            "raw_plan_body/prompt/response/token omitted.\n"
        )
    profile_context = (
        "执行画像："
        f"profile_id={profile['profile_id']}; "
        f"version={profile['version']}; "
        f"profile_hash={profile['profile_hash'][:16]}; "
        f"objective={profile['objective']}; "
        f"output_contract={', '.join(profile['output_contract'])}; "
        "raw profile prompt body omitted from MIS evidence.\n"
    )
    prompt = (
        "你是 AgentOps MIS 的本地 AI worker。请根据下面的任务摘要给出可交付结果。\n"
        "执行边界：本次调用是 ledger_summary_only 摘要通道，不是工具执行通道。"
        "不要调用终端、shell、浏览器、文件系统、MIS/API、外部工具或发布/上传/部署目标；"
        "不要声称已经执行了这些动作。"
        "如果任务需要这些动作，只能把它们列为下一步验证/执行建议，交给 MIS 账本流程处理。\n"
        "约束：不要请求外部凭证；不要输出隐藏推理；如果任务信息不足，给出可执行的下一步和缺口。"
        "请用中文，返回 3-6 条要点。\n\n"
        f"任务标题：{title}\n"
        f"任务风险：{risk}\n"
        f"任务描述：{description}\n"
        f"验收标准：{acceptance}\n"
        f"{profile_context}"
        f"{knowledge_context}"
        f"{service_context}"
        f"{intake_plan_context}"
    )
    return prompt, profile


def build_task_prompt(task: dict, adapter: str | None = None) -> str:
    prompt, _profile = build_task_prompt_bundle(task, adapter=adapter)
    return prompt


def adapter_result_profile_fields(profile: dict) -> dict:
    return {
        "prompt_profile_id": profile.get("profile_id") or "general_customer_delivery_summary",
        "prompt_profile_version": profile.get("version") or PROMPT_PROFILE_VERSION,
        "prompt_profile_hash": profile.get("profile_hash"),
    }


def worker_secret_boundary_metadata() -> dict:
    return {
        "secret_boundary": WORKER_SECRET_BOUNDARY_VERSION,
        "credential_transport": "trusted_worker_client_only",
        "model_visible_credentials": False,
        "secrets_in_prompt": False,
        "secrets_in_output": False,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "token_omitted": True,
    }


def execute_mock(task: dict, attempt: int = 1, fail_before_success: int = 0) -> AdapterResult:
    prompt, profile = build_task_prompt_bundle(task, adapter="mock")
    if fail_before_success and attempt <= fail_before_success:
        return AdapterResult(
            ok=False,
            output_summary=f"Mock worker simulated transient adapter failure on attempt {attempt}.",
            prompt_hash=stable_hash(prompt),
            **adapter_result_profile_fields(profile),
            raw_payload_hash=stable_hash({"adapter": "mock", "task_id": task.get("task_id"), "attempt": attempt, "simulated": True}),
            error_type="MockTransientFailure",
            error_message=f"Simulated transient adapter failure before success, attempt {attempt}.",
            target_resource="local://agentops/mock-worker",
            retryable=True,
        )
    summary = f"Mock worker completed task '{redact_text(task.get('title'), 80)}' and produced a safe local execution summary."
    return AdapterResult(
        ok=True,
        output_summary=summary,
        prompt_hash=stable_hash(prompt),
        **adapter_result_profile_fields(profile),
        raw_payload_hash=stable_hash({"adapter": "mock", "task_id": task.get("task_id"), "summary": summary}),
        target_resource="local://agentops/mock-worker",
    )


def execute_hermes(task: dict, gateway_url: str, model: str, timeout: int, confirm_run: bool, max_tokens: int) -> AdapterResult:
    prompt, profile = build_task_prompt_bundle(task, adapter="hermes")
    if not confirm_run:
        return AdapterResult(
            ok=False,
            output_summary="Hermes adapter dry-run: pass --confirm-run to execute.",
            prompt_hash=stable_hash(prompt),
            **adapter_result_profile_fields(profile),
            error_type="ConfirmRunRequired",
            error_message="Hermes live execution requires --confirm-run.",
            target_resource=gateway_url.rstrip() + "/v1/chat/completions",
            retryable=False,
        )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": min(max(int(max_tokens or DEFAULT_HERMES_MAX_TOKENS), 64), 4096),
    }
    started = time.time()
    try:
        req = Request(
            gateway_url.rstrip("/") + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=max(int(timeout or 180), 1)) as res:
            response = json.loads(res.read().decode("utf-8"))
        visible = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        usage = response.get("usage") or {}
        return AdapterResult(
            ok=bool(visible),
            output_summary=redact_text(visible, 200) if visible else "Hermes returned an empty response.",
            prompt_hash=stable_hash(prompt),
            **adapter_result_profile_fields(profile),
            raw_payload_hash=stable_hash(response),
            error_type=None if visible else "HermesEmptyResponse",
            error_message=None if visible else "Hermes returned no visible content.",
            duration_ms=int((time.time() - started) * 1000),
            output_tokens=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
            target_resource=gateway_url.rstrip("/") + "/v1/chat/completions",
            retryable=not bool(visible),
        )
    except HTTPError as exc:
        error_body = exc.read()
        status = int(exc.code or 0)
        return AdapterResult(
            ok=False,
            output_summary=f"Hermes gateway returned HTTP {status}.",
            prompt_hash=stable_hash(prompt),
            **adapter_result_profile_fields(profile),
            raw_payload_hash=hashlib.sha256(error_body).hexdigest(),
            error_type=f"HermesHTTP{status}",
            error_message=f"Hermes gateway returned HTTP {status}; response body omitted.",
            duration_ms=int((time.time() - started) * 1000),
            target_resource=gateway_url.rstrip("/") + "/v1/chat/completions",
            retryable=status in {408, 409, 425, 429} or status >= 500,
        )
    except Exception as exc:
        return AdapterResult(
            ok=False,
            output_summary="Hermes adapter execution failed.",
            prompt_hash=stable_hash(prompt),
            **adapter_result_profile_fields(profile),
            error_type="HermesExecutionFailed",
            error_message=redact_text(str(exc), 200),
            duration_ms=int((time.time() - started) * 1000),
            target_resource=gateway_url.rstrip("/") + "/v1/chat/completions",
            retryable=True,
        )


def execute_openclaw(task: dict, binary_path: str, agent_name: str, timeout: int, confirm_run: bool) -> AdapterResult:
    prompt, profile = build_task_prompt_bundle(task, adapter="openclaw")
    if not confirm_run:
        return AdapterResult(
            ok=False,
            output_summary="OpenClaw adapter dry-run: pass --confirm-run to execute.",
            prompt_hash=stable_hash(prompt),
            **adapter_result_profile_fields(profile),
            error_type="ConfirmRunRequired",
            error_message="OpenClaw live execution requires --confirm-run.",
            target_resource=f"local://openclaw/{agent_name}",
            retryable=False,
        )
    started = time.time()
    try:
        proc = subprocess.run(
            [binary_path, "agent", "--agent", agent_name, "-m", prompt, "--timeout", str(timeout), "--json"],
            cwd=DEFAULT_WORKER_CWD,
            capture_output=True,
            text=True,
            timeout=timeout + 30,
            check=False,
        )
        payload = json.loads(proc.stdout) if proc.stdout else {}
        meta = (payload.get("result") or {}).get("meta") or {}
        visible = meta.get("finalAssistantVisibleText") or (((payload.get("result") or {}).get("payloads") or [{}])[0].get("text"))
        visible = (visible or "").strip()
        ok = proc.returncode == 0 and bool(visible)
        return AdapterResult(
            ok=ok,
            output_summary=redact_text(visible, 200) if ok else "OpenClaw adapter execution failed.",
            prompt_hash=stable_hash(prompt),
            **adapter_result_profile_fields(profile),
            raw_payload_hash=stable_hash(payload or {"stderr": proc.stderr, "returncode": proc.returncode}),
            error_type=None if ok else "OpenClawExecutionFailed",
            error_message=None if ok else redact_text(proc.stderr or visible or f"exit={proc.returncode}", 200),
            duration_ms=int(meta.get("durationMs") or ((time.time() - started) * 1000)),
            target_resource=f"local://openclaw/{agent_name}",
            retryable=not ok,
        )
    except Exception as exc:
        return AdapterResult(
            ok=False,
            output_summary="OpenClaw adapter execution failed.",
            prompt_hash=stable_hash(prompt),
            **adapter_result_profile_fields(profile),
            error_type="OpenClawExecutionFailed",
            error_message=redact_text(str(exc), 200),
            duration_ms=int((time.time() - started) * 1000),
            target_resource=f"local://openclaw/{agent_name}",
            retryable=True,
        )


def execute_adapter_once(task: dict, args, attempt: int) -> AdapterResult:
    if args.adapter == "mock":
        return execute_mock(task, attempt=attempt, fail_before_success=args.mock_failures_before_success)
    if args.adapter == "hermes":
        return execute_hermes(task, args.hermes_gateway_url, args.hermes_model, args.hermes_timeout, args.confirm_run, args.hermes_max_tokens)
    if args.adapter == "openclaw":
        return execute_openclaw(task, args.openclaw_bin, args.openclaw_agent, args.openclaw_timeout, args.confirm_run)
    raise RuntimeError(f"unknown adapter: {args.adapter}")


def execute_adapter_with_retries(task: dict, args) -> AdapterResult:
    max_attempts = min(max(int(args.adapter_max_attempts or 1), 1), 5)
    retry_delay = max(float(args.adapter_retry_delay_sec or 0), 0.0)
    history = []
    result = None
    for attempt in range(1, max_attempts + 1):
        result = execute_adapter_once(task, args, attempt)
        history.append({
            "attempt": attempt,
            "ok": result.ok,
            "error_type": result.error_type,
            "retryable": result.retryable,
            "summary": redact_text(result.output_summary, 120),
        })
        if result.ok:
            break
        if not result.retryable or attempt >= max_attempts:
            break
        if retry_delay:
            time.sleep(retry_delay)
    if result is None:
        raise RuntimeError("adapter execution produced no result")
    result.attempt_count = len(history)
    result.max_attempts = max_attempts
    result.retry_history = history
    if result.attempt_count > 1:
        result.output_summary = f"{result.output_summary} Adapter attempts: {result.attempt_count}/{max_attempts}."
    return result


def risk_allowed(task: dict, allow_high_risk: bool) -> bool:
    return allow_high_risk or (task.get("risk_level") or "medium") in {"low", "medium"}


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def max_risk(*values: str | None) -> str:
    selected = "low"
    for value in values:
        risk = str(value or "low").lower()
        if risk not in RISK_ORDER:
            risk = "low"
        if RISK_ORDER[risk] > RISK_ORDER[selected]:
            selected = risk
    return selected


def adapter_capability_profile(adapter: str) -> dict:
    if adapter == "mock":
        return {
            "observation_level": "structured_ledger",
            "risk_floor": "low",
            "commercial_readiness": "local_demo_ready",
            "requires_prepared_action_for_external_write": False,
        }
    if adapter in {"hermes", "openclaw"}:
        return {
            "observation_level": "ledger_summary_only",
            "risk_floor": "medium",
            "commercial_readiness": "restricted_until_runtime_tool_events",
            "requires_prepared_action_for_external_write": True,
        }
    return {
        "observation_level": "ledger_summary_only",
        "risk_floor": "medium",
        "commercial_readiness": "unknown_runtime",
        "requires_prepared_action_for_external_write": True,
    }


EXTERNAL_WRITE_INTENT_KEYWORDS = {
    "publish",
    "upload",
    "deploy",
    "push",
    "send email",
    "webhook",
    "external write",
    "notion",
    "dify",
    "dataset",
    "file search",
    "customer portal",
    "生产发布",
    "发布",
    "上传",
    "部署",
    "推送",
    "发邮件",
    "外部写入",
    "知识库上传",
}


def worker_external_write_intent(task: dict, args, capability: dict) -> bool:
    if args.adapter not in {"hermes", "openclaw"}:
        return False
    if not args.confirm_run:
        return False
    if capability.get("requires_prepared_action_for_external_write") is not True:
        return False
    combined = " ".join([
        str(task.get("title") or ""),
        str(task.get("description") or ""),
        str(task.get("acceptance_criteria") or ""),
        str(task.get("target_resource") or ""),
        str(task.get("external_action_type") or ""),
    ]).lower()
    return any(keyword.lower() in combined for keyword in EXTERNAL_WRITE_INTENT_KEYWORDS)


def create_worker_external_write_gate(client: AgentOpsClient, task: dict, args, plan_id: str, run_id: str, capability: dict, loop_supervision_gate: dict | None = None) -> dict:
    task_id = task["task_id"]
    action_type = f"agent_worker.{args.adapter}.external_write"
    target_resource = f"{args.adapter}://external-write/{task_id}"
    tool_risk = max_risk(task.get("risk_level"), "high", capability.get("risk_floor"))
    prompt_profile = select_task_prompt_profile(task, adapter=args.adapter)
    normalized_args = {
        "task_id": task_id,
        "adapter": args.adapter,
        "prompt_profile_id": prompt_profile.get("profile_id"),
        "prompt_profile_version": prompt_profile.get("version"),
        "prompt_profile_hash": prompt_profile.get("profile_hash"),
        "title": redact_text(task.get("title"), 140),
        "external_write_intent": True,
        "target_resource": target_resource,
        "observation_level": capability.get("observation_level"),
        "commercial_readiness": capability.get("commercial_readiness"),
        "requires_prepared_action_for_external_write": True,
        **worker_secret_boundary_metadata(),
    }
    tool_payload = client.post("/api/agent-gateway/tool-calls", {
        "workspace_id": client.workspace_id,
        "run_id": run_id,
        "agent_id": client.agent_id,
        "tool_name": action_type,
        "tool_category": "custom",
        "risk_level": tool_risk,
        "status": "waiting_approval",
        "target_resource": target_resource,
        "args": normalized_args,
        "result_summary": "Live worker runtime paused before external write; prepared action approval is required.",
        "prepare_action": True,
        "action_type": action_type,
        "checkpoint": {
            "checkpoint": "before_agent_worker_external_write_runtime_execution",
            "task_id": task_id,
            "run_id": run_id,
            "adapter": args.adapter,
        },
        "idempotency_key": stable_hash({
            "task_id": task_id,
            "run_id": run_id,
            "adapter": args.adapter,
            "action_type": action_type,
            "target_resource": target_resource,
        })[:32],
        "approval_reason": f"{args.adapter} is an opaque live worker runtime and this task appears to request external write/upload/publish. Approve exact prepared action before execution resumes.",
    })
    wall = tool_payload.get("approval_wall") or {}
    approval = wall.get("approval") or {}
    prepared_action = wall.get("prepared_action") or {}
    tool_call = tool_payload.get("tool_call") or {}
    client.post("/api/agent-gateway/audit", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "action": "agent_worker.external_write_prepared_action_required",
        "entity_type": "runs",
        "entity_id": run_id,
        "task_id": task_id,
        "run_id": run_id,
        "metadata": {
            "adapter": args.adapter,
            "agent_plan_id": plan_id,
            "tool_call_id": tool_call.get("tool_call_id"),
            "approval_id": approval.get("approval_id"),
            "prepared_action_id": prepared_action.get("action_id"),
            "loop_supervision": loop_supervision_gate,
            "prompt_profile_id": prompt_profile.get("profile_id"),
            "prompt_profile_version": prompt_profile.get("version"),
            "prompt_profile_hash": prompt_profile.get("profile_hash"),
            "live_execution_performed": False,
            **worker_secret_boundary_metadata(),
        },
    })
    return {
        "processed": False,
        "ok": True,
        "task_id": task_id,
        "run_id": run_id,
        "plan_id": plan_id,
        "adapter": args.adapter,
        "reason": "external_write_prepared_action_required",
        "live_execution_performed": False,
        "tool_call_id": tool_call.get("tool_call_id"),
        "approval_id": approval.get("approval_id"),
        "prepared_action_id": prepared_action.get("action_id"),
        "prepared_action_hash": prepared_action.get("action_hash"),
        "loop_supervision_gate": loop_supervision_gate,
        "prompt_profile": {
            "profile_id": prompt_profile.get("profile_id"),
            "version": prompt_profile.get("version"),
            "profile_hash": prompt_profile.get("profile_hash"),
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
        "next_action": tool_payload.get("next_action"),
        "output_summary": "Worker paused before live runtime execution because the task appears to request an external write.",
        "secret_boundary": worker_secret_boundary_metadata(),
        "token_omitted": True,
    }


def emit_jsonl(args, payload: dict):
    if args.jsonl_log:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def safe_worker_heartbeat(client: AgentOpsClient, args, status: str, summary: str):
    try:
        client.post("/api/agent-gateway/heartbeat", {
            "workspace_id": client.workspace_id,
            "agent_id": client.agent_id,
            "status": status,
            "summary": redact_text(summary, 200),
            "runtime_type": args.adapter,
        }, timeout=20)
    except Exception:
        pass


def backoff_sleep(base_interval: float, cap: float, streak: int, factor: float) -> float:
    base = max(float(base_interval or 0), 0.0)
    if base <= 0:
        return 0.0
    capped = max(float(cap or base), base)
    multiplier = max(float(factor or 1.0), 1.0) ** max(int(streak or 1) - 1, 0)
    return min(base * multiplier, capped)


def register_worker(client: AgentOpsClient, adapter: str):
    return client.post("/api/agent-gateway/register", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "name": "Local Agent Worker",
        "role": f"Local {adapter} Adapter Worker",
        "runtime_type": "hermes" if adapter == "hermes" else "openclaw" if adapter == "openclaw" else "mock",
        "model_provider": adapter,
        "model_name": adapter,
        "permission_level": "standard",
        "allowed_tools": ["agent_gateway.task", f"{adapter}.execute", "agent_gateway.audit"],
        "budget_limit_usd": 5.0,
        "description": "Installable v1.5 worker daemon.",
    })


def unique_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def build_worker_knowledge_query(task: dict, adapter: str | None = None) -> str:
    title = redact_text(task.get("title"), 90)
    description = redact_text(task.get("description"), 220)
    acceptance = redact_text(task.get("acceptance_criteria"), 160)
    runtime = redact_text(adapter or task.get("runtime_type") or task.get("model_provider") or "worker", 40)
    risk = redact_text(task.get("risk_level") or "medium", 32)
    task_terms = " ".join(part for part in [title, description, acceptance] if part).strip()
    query = (
        f"Agent Gateway worker task evidence adapter {runtime} risk {risk}. "
        f"{task_terms} "
        "READ PLAN RETRIEVE COMPARE EXECUTE VERIFY RECORD method block "
        "run ledger tool evaluation audit approval artifact worker adapter"
    )
    return redact_text(query, 240)


def fetch_worker_knowledge_evidence(client: AgentOpsClient, task: dict, adapter: str | None = None) -> dict:
    task_id = str(task.get("task_id") or "").strip()
    query = build_worker_knowledge_query(task, adapter=adapter)
    packet_query = {
        "limit": 5,
        "baseline_limit": 5,
        "adapter": adapter,
    }
    if task_id:
        packet_query["task_id"] = task_id
    else:
        packet_query["q"] = query
    try:
        packet = client.get("/api/agent-gateway/knowledge/evidence-packet", packet_query)
        compact = compact_worker_knowledge_evidence(packet)
        if compact.get("knowledge_retrieval_evidence_consumed"):
            return compact
        try:
            indexed = client.post("/api/agent-gateway/knowledge/index", {"rebuild": False})
            packet = client.get("/api/agent-gateway/knowledge/evidence-packet", packet_query)
            compact = compact_worker_knowledge_evidence(packet)
            compact["knowledge_index_attempted"] = True
            compact["knowledge_index_status"] = indexed.get("status") or indexed.get("operation")
            compact["knowledge_indexed_documents"] = indexed.get("indexed")
            return compact
        except Exception as index_exc:
            compact["knowledge_index_attempted"] = True
            compact["knowledge_index_status"] = "unavailable"
            compact["knowledge_index_error"] = redact_text(str(index_exc), 220)
            return compact
    except Exception as exc:
        return {
            "operation": "worker_knowledge_retrieval_evidence",
            "status": "unavailable",
            "reason": redact_text(str(exc), 220),
            "packet_hash": stable_hash({"status": "unavailable", "query_hash": stable_hash(query)}),
            "query_hash": stable_hash(query),
            "query_omitted": True,
            "task_context": {
                "task_id": task_id or None,
                "task_found": False,
                "query_source": "task_id" if task_id else "fallback_query",
                "task_text_omitted": True,
                "token_omitted": True,
            },
            "knowledge_retrieval_evidence_consumed": False,
            "results": [],
            "retrieval_ids": [],
            "paths": [],
            "source_hashes": [],
            "metrics": {},
            "raw_content_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        }


def compact_worker_knowledge_evidence(packet: dict) -> dict:
    primary = packet.get("primary_search") or {}
    task_context = packet.get("task_context") if isinstance(packet.get("task_context"), dict) else {}
    rows = []
    for row in (primary.get("results") or [])[:5]:
        rows.append({
            "retrieval_id": row.get("retrieval_id"),
            "doc_id": row.get("doc_id"),
            "chunk_id": row.get("chunk_id"),
            "path": row.get("path"),
            "chunk_heading_path": row.get("chunk_heading_path"),
            "source_hash": row.get("source_hash"),
            "rank": row.get("rank"),
            "snippet_omitted": True,
            "content_summary_omitted": True,
            "raw_content_omitted": True,
            "raw_prompt_omitted": True,
            "token_omitted": True,
        })
    core = {
        "operation": "worker_knowledge_retrieval_evidence",
        "packet_operation": packet.get("operation"),
        "packet_status": packet.get("status"),
        "task_context": {
            "task_id": task_context.get("task_id"),
            "task_found": bool(task_context.get("task_found")),
            "query_source": task_context.get("query_source") or "explicit_query",
            "source_fields": task_context.get("source_fields") if isinstance(task_context.get("source_fields"), list) else [],
            "task_text_omitted": task_context.get("task_text_omitted") is not False,
            "token_omitted": True,
        },
        "query_hash": packet.get("query_hash"),
        "query_omitted": True,
        "metrics": packet.get("metrics") or {},
        "result_count": len(rows),
        "retrieval_ids": [row.get("retrieval_id") for row in rows if row.get("retrieval_id")],
        "paths": [row.get("path") for row in rows if row.get("path")],
        "source_hashes": [row.get("source_hash") for row in rows if row.get("source_hash")],
        "results": rows,
        "raw_content_omitted": True,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "token_omitted": True,
    }
    core["packet_hash"] = stable_hash({
        "packet_operation": core["packet_operation"],
        "packet_status": core["packet_status"],
        "task_context": core["task_context"],
        "query_hash": core["query_hash"],
        "metrics": core["metrics"],
        "results": rows,
    })
    core["knowledge_retrieval_evidence_consumed"] = bool(rows)
    return core


def compact_worker_loop_supervision_gate(payload: dict, *, adapter: str, task_id: str, agent_id: str) -> dict:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    item = next((row for row in items if isinstance(row, dict) and row.get("adapter") == adapter), {})
    safety = item.get("safety") if isinstance(item.get("safety"), dict) else {}
    next_commands = item.get("next_commands") if isinstance(item.get("next_commands"), dict) else {}
    commands = item.get("commands") if isinstance(item.get("commands"), dict) else {}
    local_deployment = item.get("local_deployment") if isinstance(item.get("local_deployment"), dict) else {}
    local_run_path = local_deployment.get("local_run_path") if isinstance(local_deployment.get("local_run_path"), dict) else {}
    service_managed_loop = local_deployment.get("service_managed_loop") if isinstance(local_deployment.get("service_managed_loop"), dict) else {}
    local_deployment_safety = local_run_path.get("safety") if isinstance(local_run_path.get("safety"), dict) else {}
    plan_quality = item.get("plan_quality") if isinstance(item.get("plan_quality"), dict) else {}
    raw_gates = item.get("gates") if isinstance(item.get("gates"), list) else []
    plan_quality_gate = next((gate for gate in raw_gates if isinstance(gate, dict) and gate.get("id") == "plan_quality"), {})
    plan_quality_command = plan_quality.get("command") or plan_quality_gate.get("command")
    plan_quality_issue_count = int(plan_quality.get("issue_count") or 0)
    service_closure = item.get("service_closure") if isinstance(item.get("service_closure"), dict) else {}
    service_closure_gate = next((gate for gate in raw_gates if isinstance(gate, dict) and gate.get("id") == "service_managed_loop"), {})
    service_closure_status = str(service_closure.get("status") or service_closure_gate.get("status") or "not_applicable")
    service_closure_requested = bool(
        service_closure.get("required") is True
        or service_closure_status in {"attention", "blocked", "record_first"}
        or (
            service_closure_gate
            and service_closure_gate.get("ok") is not True
            and service_closure_status not in {"pass", "not_applicable"}
        )
    )
    service_closure_hard_gate = bool(
        service_closure.get("hard_run_start_gate") is True
        or service_closure_gate.get("hard_run_start_gate") is True
    )
    service_closure_command = service_closure.get("command") or service_closure_gate.get("command")
    gates = [
        {
            "id": gate.get("id"),
            "ok": gate.get("ok") is True,
            "status": gate.get("status"),
            "confirm_required": gate.get("confirm_required") is True,
            "server_executes_shell": gate.get("server_executes_shell") is True,
            "token_omitted": True,
        }
        for gate in (item.get("gates") or [])
        if isinstance(gate, dict)
    ]
    blockers = [str(entry) for entry in (item.get("blockers") or []) if entry]
    status = str(item.get("status") or payload.get("status") or "unavailable")
    can_confirm = item.get("can_confirm_bounded_loop") is True
    server_shell = safety.get("server_executes_shell") is True
    ok = bool(
        can_confirm
        and not server_shell
        and not blockers
        and plan_quality_issue_count == 0
        and not service_closure_hard_gate
        and status not in {"blocked", "attention", "preview_only", "unavailable"}
    )
    core = {
        "operation": "worker_loop_supervision_gate",
        "source_operation": payload.get("operation"),
        "source": "/api/operator/loop-supervision",
        "adapter": adapter,
        "task_id": task_id,
        "agent_id": agent_id,
        "status": status,
        "ok": ok,
        "can_preview_loop": item.get("can_preview_loop") is True,
        "can_confirm_bounded_loop": can_confirm,
        "should_record_before_execute": item.get("should_record_before_execute") is True,
        "ready_for_live_dispatch": item.get("ready_for_live_dispatch") is True,
        "current_code_ok": ((payload.get("summary") or {}).get("current_code_ok") is True) if isinstance(payload.get("summary"), dict) else None,
        "blockers": blockers,
        "attention": [str(entry) for entry in (item.get("attention") or []) if entry],
        "review_pressure": item.get("review_pressure") if isinstance(item.get("review_pressure"), dict) else {},
        "local_deployment": {
            "local_run_path_present": bool(local_run_path),
            "service_managed_loop_present": bool(service_managed_loop),
            "recommended_adapter": local_run_path.get("recommended_adapter"),
            "service_managed_adapter": service_managed_loop.get("adapter"),
            "server_executes_shell": local_deployment_safety.get("server_executes_shell") is True,
            "token_omitted": True,
        },
        "service_managed_loop": {
            "adapter": service_managed_loop.get("adapter"),
            "manager": service_managed_loop.get("manager"),
            "status": service_managed_loop.get("status"),
            "checked_status": service_managed_loop.get("checked_status"),
            "active_status": service_managed_loop.get("active_status"),
            "active_loop_status": service_managed_loop.get("active_loop_status"),
            "service_managed_loop_ready": service_managed_loop.get("service_managed_loop_ready") is True,
            "service_loaded": service_managed_loop.get("service_loaded") is True,
            "service_active_loop_ready": service_managed_loop.get("service_active_loop_ready") is True,
            "service_check_ok": service_managed_loop.get("service_check_ok") is True,
            "service_file_exists": service_managed_loop.get("service_file_exists") is True,
            "receipt_id": service_managed_loop.get("receipt_id"),
            "receipt_verified": service_managed_loop.get("receipt_verified") is True,
            "control_readback_id": service_managed_loop.get("control_readback_id"),
            "control_readback_attached": service_managed_loop.get("control_readback_attached") is True,
            "readback_verification_status": service_managed_loop.get("readback_verification_status"),
            "token_omitted": True,
        },
        "plan_quality": {
            "status": plan_quality.get("status") or plan_quality_gate.get("quality_status") or "not_applicable",
            "issue_count": plan_quality_issue_count,
            "gate_status": plan_quality_gate.get("status"),
            "gate_ok": plan_quality_gate.get("ok") is True,
            "command": plan_quality_command,
            "hard_run_start_gate": plan_quality.get("hard_run_start_gate") is True,
            "token_omitted": True,
        },
        "service_closure": {
            "required": service_closure_requested,
            "status": service_closure_status,
            "step": service_closure.get("step") or service_closure_gate.get("step"),
            "phase": service_closure.get("phase") or service_closure_gate.get("phase"),
            "command": service_closure_command,
            "gate_status": service_closure_gate.get("status"),
            "gate_ok": service_closure_gate.get("ok") is True,
            "hard_run_start_gate": service_closure_hard_gate,
            "server_executes_shell": service_closure.get("server_executes_shell") is True or service_closure_gate.get("server_executes_shell") is True,
            "token_omitted": True,
        },
        "blocked_gate_ids": [gate.get("id") for gate in gates if gate.get("ok") is not True and gate.get("status") == "blocked"],
        "gates": gates,
        "recommended_next": commands.get("recommended_next") or next_commands.get("recommended_next"),
        "commands": {
            "recommended_next": commands.get("recommended_next") or next_commands.get("recommended_next"),
            "preview_loop": commands.get("preview_loop"),
            "confirm_loop": commands.get("confirm_loop"),
            "record_review": commands.get("record_review"),
        },
        "read_only": True,
        "live_execution_performed": False,
        "server_executes_shell": False,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "raw_content_omitted": True,
        "token_omitted": True,
    }
    core["supervision_hash"] = stable_hash({
        "operation": core["operation"],
        "adapter": adapter,
        "task_id": task_id,
        "agent_id": agent_id,
        "status": core["status"],
        "ok": core["ok"],
        "can_confirm_bounded_loop": core["can_confirm_bounded_loop"],
        "should_record_before_execute": core["should_record_before_execute"],
        "blocked_gate_ids": core["blocked_gate_ids"],
        "service_managed_loop": core["service_managed_loop"],
        "plan_quality": core["plan_quality"],
        "service_closure": core["service_closure"],
        "recommended_next": core["recommended_next"],
    })
    return core


def fetch_worker_loop_supervision_gate(client: AgentOpsClient, task: dict, args) -> dict | None:
    if args.adapter not in {"hermes", "openclaw"}:
        return None
    task_id = str(task.get("task_id") or "").strip()
    try:
        payload = client.get("/api/operator/loop-supervision", {
            "adapter": args.adapter,
            "limit": 8,
            "task_id": task_id,
            "agent_id": client.agent_id,
        })
        return compact_worker_loop_supervision_gate(payload, adapter=args.adapter, task_id=task_id, agent_id=client.agent_id)
    except Exception as exc:
        return {
            "operation": "worker_loop_supervision_gate",
            "source": "/api/operator/loop-supervision",
            "adapter": args.adapter,
            "task_id": task_id,
            "agent_id": client.agent_id,
            "status": "unavailable",
            "ok": False,
            "reason": "loop_supervision_unavailable",
            "error": redact_text(str(exc), 220),
            "read_only": True,
            "live_execution_performed": False,
            "server_executes_shell": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "raw_content_omitted": True,
            "token_omitted": True,
        }


def create_worker_agent_plan(client: AgentOpsClient, task: dict, args, knowledge_evidence: dict | None = None) -> dict:
    risk = task.get("risk_level") or "medium"
    knowledge_evidence = knowledge_evidence or {}
    retrieved_paths = [path for path in (knowledge_evidence.get("paths") or []) if isinstance(path, str)]
    referenced_specs = unique_values([
        "PROJECT_SPEC.md",
        "AGENT_WORKFLOW.md",
        "docs/AGENT_WORK_METHOD_BLOCK.md",
        *[path for path in retrieved_paths if path.endswith(".md") and not path.startswith("knowledge/")],
    ])[:8]
    referenced_memories = unique_values([
        "knowledge/shared/common_failures.md",
        *retrieved_paths,
    ])[:8]
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "task_id": task["task_id"],
        "task_understanding": (
            f"Process task '{redact_text(task.get('title'), 120)}' through the {args.adapter} worker adapter, "
            "write run/tool/evaluation/artifact/audit evidence, then bind the result to this plan."
        ),
        "referenced_specs": referenced_specs,
        "referenced_memories": referenced_memories,
        "referenced_bases": ["base_local_tasks", "base_local_memory"],
        "proposed_files_to_change": ["agentops-worker-runtime", f"adapter:{args.adapter}"],
        "risk_level": risk,
        "approval_required": risk in {"high", "critical"},
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "verification_plan": (
            "Agent worker must consume knowledge retrieval evidence before execution and submit tool, "
            "evaluation, artifact, audit and plan_evidence_manifest evidence."
        ),
        "rollback_plan": "Mark the run failed/blocked and leave the manifest blocked if execution evidence is incomplete.",
        "status": "submitted",
    }
    return client.post("/api/agent-gateway/agent-plans", payload)


def intake_blocked_task_for_agent(intake: dict, agent_id: str) -> dict | None:
    for item in intake.get("blocked_tasks") or []:
        if not isinstance(item, dict):
            continue
        assigned = item.get("assigned_agent_ids") or []
        if agent_id in assigned:
            return item
    return None


def load_task_for_intake_plan(client: AgentOpsClient, blocked_task: dict) -> dict:
    task_id = str(blocked_task.get("task_id") or "").strip()
    task = {
        "task_id": task_id,
        "title": blocked_task.get("title") or task_id,
        "description": blocked_task.get("description") or "",
        "acceptance_criteria": blocked_task.get("acceptance_criteria") or "",
        "risk_level": blocked_task.get("risk_level") or "medium",
        "status": blocked_task.get("status"),
        "priority": blocked_task.get("priority"),
    }
    if not task_id:
        return task
    try:
        detail = client.get(f"/api/agent-gateway/tasks/{task_id}")
        loaded = detail.get("task") if isinstance(detail.get("task"), dict) else {}
        if loaded:
            task.update({key: value for key, value in loaded.items() if value is not None})
    except Exception:
        pass
    return task


def audit_intake_auto_plan(client: AgentOpsClient, *, task_id: str, plan_id: str | None, status: str, metadata: dict) -> None:
    try:
        client.post("/api/agent-gateway/audit", {
            "workspace_id": client.workspace_id,
            "agent_id": client.agent_id,
            "action": "agent_worker.intake_auto_plan",
            "entity_type": "tasks",
            "entity_id": task_id,
            "task_id": task_id,
            "metadata": {
                "plan_id": plan_id,
                "status": status,
                "live_execution_performed": False,
                "run_start_attempted": False,
                "auto_plan_intake": True,
                **metadata,
                **worker_secret_boundary_metadata(),
            },
        }, timeout=20)
    except Exception:
        pass


def maybe_auto_plan_intake_block(client: AgentOpsClient, args, intake: dict) -> dict | None:
    if not getattr(args, "auto_plan_intake", True):
        return None
    blocked_task = intake_blocked_task_for_agent(intake, client.agent_id)
    if not blocked_task:
        return None
    task_id = str(blocked_task.get("task_id") or "").strip()
    failed_gate_ids = set(blocked_task.get("failed_gate_ids") or [])
    risk = str(blocked_task.get("risk_level") or "medium")
    if risk in {"high", "critical"} and not args.allow_high_risk:
        return {
            "processed": False,
            "ok": False,
            "reason": "intake_auto_plan_risk_blocked",
            "task_id": task_id,
            "risk_level": risk,
            "live_execution_performed": False,
            "run_start_attempted": False,
            "token_omitted": True,
        }
    plan_id = blocked_task.get("plan_id")
    if plan_id and "verified_agent_plan" in failed_gate_ids:
        verified_plan = client.get(f"/api/agent-gateway/agent-plans/{plan_id}/verify")
        passed = bool((verified_plan.get("verification") or {}).get("pass"))
        audit_intake_auto_plan(client, task_id=task_id, plan_id=plan_id, status="verified_existing" if passed else "verify_failed", metadata={
            "mode": "verify_existing_plan",
            "verification_pass": passed,
            "failed_gate_ids": sorted(failed_gate_ids),
            "token_omitted": True,
        })
        return {
            "processed": False,
            "ok": passed,
            "reason": "intake_plan_verified" if passed else "intake_plan_verify_failed",
            "task_id": task_id,
            "plan_id": plan_id,
            "verification_pass": passed,
            "live_execution_performed": False,
            "run_start_attempted": False,
            "token_omitted": True,
        }
    if "agent_plan" not in failed_gate_ids or not task_id:
        return None
    task = load_task_for_intake_plan(client, blocked_task)
    task["risk_level"] = task.get("risk_level") or risk
    knowledge_evidence = fetch_worker_knowledge_evidence(client, task, adapter=args.adapter)
    plan_payload = create_worker_agent_plan(client, task, args, knowledge_evidence)
    plan_id = (plan_payload.get("agent_plan") or {}).get("plan_id")
    if not plan_id:
        raise RuntimeError("intake auto-plan create did not return plan_id")
    verified_plan = client.get(f"/api/agent-gateway/agent-plans/{plan_id}/verify")
    verification = verified_plan.get("verification") or {}
    passed = bool(verification.get("pass"))
    audit_intake_auto_plan(client, task_id=task_id, plan_id=plan_id, status="created_verified" if passed else "created_verify_failed", metadata={
        "mode": "create_plan",
        "verification_pass": passed,
        "failed_gate_ids": sorted(failed_gate_ids),
        "knowledge_retrieval_evidence_consumed": bool(knowledge_evidence.get("knowledge_retrieval_evidence_consumed")),
        "knowledge_retrieval_packet_hash": knowledge_evidence.get("packet_hash"),
        "knowledge_retrieval_query_hash": knowledge_evidence.get("query_hash"),
        "knowledge_retrieval_status": knowledge_evidence.get("packet_status") or knowledge_evidence.get("status"),
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "raw_content_omitted": True,
        "token_omitted": True,
    })
    return {
        "processed": False,
        "ok": passed,
        "reason": "intake_auto_planned" if passed else "intake_auto_plan_failed",
        "task_id": task_id,
        "plan_id": plan_id,
        "verification_pass": passed,
        "failed_checks": verification.get("failed_checks") or [],
        "knowledge_retrieval_evidence": {
            "consumed": bool(knowledge_evidence.get("knowledge_retrieval_evidence_consumed")),
            "packet_hash": knowledge_evidence.get("packet_hash"),
            "query_hash": knowledge_evidence.get("query_hash"),
            "status": knowledge_evidence.get("packet_status") or knowledge_evidence.get("status"),
            "paths": knowledge_evidence.get("paths") or [],
            "query_omitted": True,
            "snippet_omitted": True,
            "raw_content_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
        "live_execution_performed": False,
        "run_start_attempted": False,
        "next_action": "Next worker iteration can pull the task once intake sees the verified Agent Plan.",
        "token_omitted": True,
    }


def verified_intake_plan_for_task(client: AgentOpsClient, task: dict) -> tuple[str | None, dict | None]:
    intake = task.get("intake") if isinstance(task.get("intake"), dict) else {}
    plan_id = str(intake.get("plan_id") or "").strip()
    if not plan_id or intake.get("plan_verified") is not True:
        return None, None
    verified_plan = client.get(f"/api/agent-gateway/agent-plans/{plan_id}/verify")
    if (verified_plan.get("verification") or {}).get("pass"):
        return plan_id, verified_plan
    return None, verified_plan


def create_worker_plan_manifest(client: AgentOpsClient, plan_id: str, run_id: str, tool_call_id: str | None, evaluation_id: str | None, artifact_id: str | None) -> dict:
    payload = {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "plan_id": plan_id,
        "run_id": run_id,
        "mismatch_policy": "block",
        "expected_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "tool_call_ids": [tool_call_id] if tool_call_id else [],
        "evaluation_ids": [evaluation_id] if evaluation_id else [],
        "artifact_ids": [artifact_id] if artifact_id else [],
    }
    return client.post("/api/agent-gateway/plan-evidence-manifests", payload)


def adapter_model_name(args) -> str:
    if args.adapter == "hermes":
        return args.hermes_model
    if args.adapter == "openclaw":
        return args.openclaw_agent
    return "agentops-mock-worker"


def record_worker_runtime_event(
    client: AgentOpsClient,
    args,
    *,
    run_id: str,
    task_id: str,
    result: AdapterResult,
    capability: dict,
) -> dict:
    event_payload = {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "run_id": run_id,
        "adapter": args.adapter,
        "event_type": "agent_worker.adapter_execution_summary",
        "status": "completed" if result.ok else "failed",
        "input_summary": (
            f"Worker adapter={args.adapter} task={redact_text(task_id, 120)} "
            f"observation={capability.get('observation_level')}"
        ),
        "output_summary": result.output_summary,
        "error_message": result.error_message,
        "latency_ms": result.duration_ms,
        "model_name": adapter_model_name(args),
        "prompt_hash": result.prompt_hash,
        "raw_payload_hash": result.raw_payload_hash or stable_hash({
            "adapter": args.adapter,
            "run_id": run_id,
            "task_id": task_id,
            "ok": result.ok,
            "error_type": result.error_type,
            "attempt_count": result.attempt_count,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        }),
        "metadata": {
            "task_id": task_id,
            "adapter": args.adapter,
            "ok": result.ok,
            "error_type": result.error_type,
            "attempt_count": result.attempt_count,
            "max_attempts": result.max_attempts,
            "observation_level": capability.get("observation_level"),
            "commercial_readiness": capability.get("commercial_readiness"),
            "requires_prepared_action_for_external_write": capability.get("requires_prepared_action_for_external_write"),
            "runtime_internal_tools_remain_opaque": capability.get("observation_level") == "ledger_summary_only",
            "event_is_worker_summary_not_raw_trace": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
        "source": "agentops-worker.adapter-execution-summary",
    }
    return client.post("/api/agent-gateway/runtime-events", event_payload)


def process_one_task(client: AgentOpsClient, args) -> dict:
    pull_query = {
        "agent_id": client.agent_id,
        "workspace_id": client.workspace_id,
        "limit": 1,
        "status": args.status,
        "enforce_intake": "true" if args.enforce_intake else "false",
    }
    if args.task_id:
        pull_query["task_id"] = args.task_id
    pulled = client.get("/api/agent-gateway/tasks/pull", pull_query)
    tasks = pulled.get("tasks") or []
    if not tasks:
        intake = pulled.get("intake") or {}
        if intake.get("blocked"):
            auto_plan_result = maybe_auto_plan_intake_block(client, args, intake)
            if auto_plan_result:
                return {
                    **auto_plan_result,
                    "intake": {
                        "blocked": intake.get("blocked", 0),
                        "next_actions": intake.get("next_actions") or [],
                        "blocked_tasks": intake.get("blocked_tasks") or [],
                        "token_omitted": True,
                    },
                }
            return {
                "processed": False,
                "reason": "intake_blocked",
                "intake": {
                    "blocked": intake.get("blocked", 0),
                    "next_actions": intake.get("next_actions") or [],
                    "blocked_tasks": intake.get("blocked_tasks") or [],
                    "token_omitted": True,
                },
            }
        client.post("/api/agent-gateway/heartbeat", {
            "workspace_id": client.workspace_id,
            "agent_id": client.agent_id,
            "status": "idle",
            "summary": "Worker found no eligible task.",
            "runtime_type": args.adapter,
        })
        return {"processed": False, "reason": "no_task"}

    task = tasks[0]
    task_id = task["task_id"]
    if not risk_allowed(task, args.allow_high_risk):
        return {"processed": False, "task_id": task_id, "reason": "risk_not_allowed", "risk_level": task.get("risk_level")}

    client.post(f"/api/agent-gateway/tasks/{task_id}/claim", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "runtime_type": args.adapter,
    })
    knowledge_evidence = fetch_worker_knowledge_evidence(client, task, adapter=args.adapter)
    task = dict(task)
    task["_knowledge_retrieval_evidence"] = knowledge_evidence
    plan_reused = False
    plan_id, verified_plan = verified_intake_plan_for_task(client, task)
    if plan_id:
        plan_reused = True
    else:
        plan_payload = create_worker_agent_plan(client, task, args, knowledge_evidence)
        plan_id = (plan_payload.get("agent_plan") or {}).get("plan_id")
        verified_plan = None
    if not plan_id:
        raise RuntimeError("agent plan create did not return plan_id")
    if verified_plan is None:
        verified_plan = client.get(f"/api/agent-gateway/agent-plans/{plan_id}/verify")
    if not (verified_plan.get("verification") or {}).get("pass"):
        raise RuntimeError(f"agent plan verification failed before run_start: {json_dumps(verified_plan.get('verification') or {})}")
    task["_intake_plan_evidence"] = {
        "plan_id": plan_id,
        "plan_verified": True,
        "plan_reused_from_intake": plan_reused,
        "source": "task_pull.intake" if plan_reused else "worker.created_plan",
        "verification_source": f"/api/agent-gateway/agent-plans/{plan_id}/verify",
        "auto_plan_intake_supported": bool(getattr(args, "auto_plan_intake", True)),
        "raw_plan_body_omitted": True,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "token_omitted": True,
    }

    capability = adapter_capability_profile(args.adapter)
    secret_boundary = worker_secret_boundary_metadata()
    loop_supervision_gate = fetch_worker_loop_supervision_gate(client, task, args) if args.confirm_run else None
    if args.adapter in {"hermes", "openclaw"} and args.confirm_run and (loop_supervision_gate or {}).get("ok") is not True:
        output_summary = redact_text(
            (loop_supervision_gate or {}).get("recommended_next")
            or (loop_supervision_gate or {}).get("reason")
            or f"{args.adapter} loop supervision blocked live worker execution.",
            260,
        )
        client.post("/api/agent-gateway/audit", {
            "workspace_id": client.workspace_id,
            "agent_id": client.agent_id,
            "action": "agent_worker.loop_supervision_blocked",
            "entity_type": "tasks",
            "entity_id": task_id,
            "task_id": task_id,
            "metadata": {
                "adapter": args.adapter,
                "agent_plan_id": plan_id,
                "loop_supervision": loop_supervision_gate,
                "live_execution_performed": False,
                "run_start_attempted": False,
                **secret_boundary,
            },
        })
        return {
            "processed": False,
            "ok": False,
            "task_id": task_id,
            "run_id": None,
            "plan_id": plan_id,
            "adapter": args.adapter,
            "reason": "loop_supervision_blocked",
            "live_execution_performed": False,
            "run_start_attempted": False,
            "loop_supervision_gate": loop_supervision_gate,
            "output_summary": output_summary,
            "secret_boundary": secret_boundary,
            "token_omitted": True,
        }
    if loop_supervision_gate:
        task["_loop_supervision_gate"] = loop_supervision_gate

    run_payload = client.post("/api/agent-gateway/runs/start", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "task_id": task_id,
        "agent_plan_id": plan_id,
        "runtime_type": args.adapter,
        "input_summary": f"Worker adapter={args.adapter} task={redact_text(task.get('title'), 120)}",
        "delegation_id": f"worker:{args.adapter}:{task_id}",
    })
    run = run_payload["run"]
    run_id = run["run_id"]

    if worker_external_write_intent(task, args, capability):
        return create_worker_external_write_gate(client, task, args, plan_id, run_id, capability, loop_supervision_gate)

    result = execute_adapter_with_retries(task, args)
    tool_risk = max_risk(task.get("risk_level"), capability.get("risk_floor"))
    runtime_event_payload = record_worker_runtime_event(
        client,
        args,
        run_id=run_id,
        task_id=task_id,
        result=result,
        capability=capability,
    )
    worker_runtime_event_id = ((runtime_event_payload.get("runtime_event") or {}).get("runtime_event_id"))

    tool_status = "completed" if result.ok else "failed"
    tool_payload = client.post("/api/agent-gateway/tool-calls", {
        "workspace_id": client.workspace_id,
        "run_id": run_id,
        "agent_id": client.agent_id,
        "tool_name": f"agent_worker.{args.adapter}",
        "tool_category": "custom",
        "risk_level": tool_risk,
        "status": tool_status,
        "target_resource": result.target_resource,
        "args": {
            "task_id": task_id,
            "adapter": args.adapter,
            "prompt_hash": result.prompt_hash,
            "prompt_profile_id": result.prompt_profile_id,
            "prompt_profile_version": result.prompt_profile_version,
            "prompt_profile_hash": result.prompt_profile_hash,
            "attempt_count": result.attempt_count,
            "max_attempts": result.max_attempts,
            "retry_history": result.retry_history or [],
            "observation_level": capability.get("observation_level"),
            "risk_floor": capability.get("risk_floor"),
            "effective_risk_level": tool_risk,
            "commercial_readiness": capability.get("commercial_readiness"),
            "requires_prepared_action_for_external_write": capability.get("requires_prepared_action_for_external_write"),
            "worker_runtime_event_id": worker_runtime_event_id,
            "worker_runtime_event_summary_recorded": bool(worker_runtime_event_id),
            "runtime_internal_tools_remain_opaque": capability.get("observation_level") == "ledger_summary_only",
            "hermes_max_tokens": args.hermes_max_tokens if args.adapter == "hermes" else None,
            "knowledge_retrieval_evidence_consumed": bool(knowledge_evidence.get("knowledge_retrieval_evidence_consumed")),
            "knowledge_retrieval_packet_hash": knowledge_evidence.get("packet_hash"),
            "knowledge_retrieval_query_hash": knowledge_evidence.get("query_hash"),
            "knowledge_retrieval_status": knowledge_evidence.get("packet_status") or knowledge_evidence.get("status"),
            "knowledge_retrieval_task_context": knowledge_evidence.get("task_context") or {},
            "knowledge_retrieval_ids": knowledge_evidence.get("retrieval_ids") or [],
            "knowledge_retrieval_paths": knowledge_evidence.get("paths") or [],
            "knowledge_retrieval_source_hashes": knowledge_evidence.get("source_hashes") or [],
            "knowledge_retrieval_metrics": knowledge_evidence.get("metrics") or {},
            "loop_supervision_gate": loop_supervision_gate,
            "knowledge_retrieval_omissions": {
                "query_omitted": True,
                "snippet_omitted": True,
                "raw_content_omitted": True,
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "token_omitted": True,
            },
            "raw_omitted": True,
            **secret_boundary,
        },
        "result_summary": result.output_summary,
    })
    tool_call_id = (tool_payload.get("tool_call") or {}).get("tool_call_id")
    final_status = "completed" if result.ok else "failed"
    client.post(f"/api/agent-gateway/runs/{run_id}/heartbeat", {
        "workspace_id": client.workspace_id,
        "status": final_status,
        "output_summary": result.output_summary,
        "duration_ms": result.duration_ms,
        "output_tokens": result.output_tokens,
        "cost_usd": 0.0,
        "error_type": result.error_type,
        "error_message": result.error_message,
    })
    knowledge_gate_pass = bool(knowledge_evidence.get("knowledge_retrieval_evidence_consumed"))
    knowledge_gate_status = (
        "pass"
        if knowledge_gate_pass
        else "unavailable"
        if (knowledge_evidence.get("packet_status") or knowledge_evidence.get("status")) == "unavailable"
        else "missing"
    )
    evaluation_pass = bool(result.ok and knowledge_gate_pass)
    if evaluation_pass:
        evaluation_notes = "Worker adapter loop completed with compact knowledge retrieval evidence."
    elif result.ok:
        evaluation_notes = "Worker adapter loop completed but failed quality gate: knowledge retrieval evidence was unavailable or missing."
    else:
        evaluation_notes = f"Worker adapter loop failed: {result.error_type}"
    eval_payload = client.post("/api/agent-gateway/evaluations/submit", {
        "workspace_id": client.workspace_id,
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": client.agent_id,
        "evaluator_type": "rule",
        "score": 1.0 if evaluation_pass else 0.0,
        "pass_fail": "pass" if evaluation_pass else "fail",
        "rubric": {
            "gate": "worker_adapter_loop",
            "adapter": args.adapter,
            "requires_completed_run": True,
            "requires_knowledge_retrieval_evidence": True,
            "prompt_profile_id": result.prompt_profile_id,
            "prompt_profile_version": result.prompt_profile_version,
            "prompt_profile_hash": result.prompt_profile_hash,
            "knowledge_retrieval_gate_pass": knowledge_gate_pass,
            "knowledge_retrieval_gate_status": knowledge_gate_status,
            "quality_gate_pass": evaluation_pass,
            "raw_prompt_response_omitted": True,
            "attempt_count": result.attempt_count,
            "max_attempts": result.max_attempts,
            "observation_level": capability.get("observation_level"),
            "risk_floor": capability.get("risk_floor"),
            "effective_risk_level": tool_risk,
            "commercial_readiness": capability.get("commercial_readiness"),
            "requires_prepared_action_for_external_write": capability.get("requires_prepared_action_for_external_write"),
            "worker_runtime_event_id": worker_runtime_event_id,
            "worker_runtime_event_summary_recorded": bool(worker_runtime_event_id),
            "runtime_internal_tools_remain_opaque": capability.get("observation_level") == "ledger_summary_only",
            "knowledge_retrieval_evidence_consumed": bool(knowledge_evidence.get("knowledge_retrieval_evidence_consumed")),
            "knowledge_retrieval_packet_hash": knowledge_evidence.get("packet_hash"),
            "knowledge_retrieval_query_hash": knowledge_evidence.get("query_hash"),
            "knowledge_retrieval_status": knowledge_evidence.get("packet_status") or knowledge_evidence.get("status"),
            "knowledge_retrieval_task_context": knowledge_evidence.get("task_context") or {},
            "knowledge_retrieval_metrics": knowledge_evidence.get("metrics") or {},
            "loop_supervision_gate": loop_supervision_gate,
            "knowledge_retrieval_omissions": {
                "query_omitted": True,
                "snippet_omitted": True,
                "raw_content_omitted": True,
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "token_omitted": True,
            },
            **secret_boundary,
        },
        "notes": evaluation_notes,
    })
    evaluation_id = (eval_payload.get("evaluation") or {}).get("evaluation_id")
    artifact_payload = client.post("/api/agent-gateway/artifacts", {
        "workspace_id": client.workspace_id,
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": client.agent_id,
        "artifact_type": "agent_worker_result",
        "title": f"Agent worker result: {redact_text(task.get('title'), 120)}",
        "uri": f"run://{run_id}",
        "summary": result.output_summary,
        "content_hash": stable_hash({
            "run_id": run_id,
            "task_id": task_id,
            "adapter": args.adapter,
            "summary": result.output_summary,
            "ok": result.ok,
            "knowledge_retrieval_packet_hash": knowledge_evidence.get("packet_hash"),
        }),
    })
    artifact_id = (artifact_payload.get("artifact") or {}).get("artifact_id")
    if result.ok:
        client.post("/api/agent-gateway/memories/propose", {
            "workspace_id": client.workspace_id,
            "agent_id": client.agent_id,
            "task_id": task_id,
            "run_id": run_id,
            "scope": "workspace",
            "memory_type": "artifact_summary",
            "canonical_text": f"Worker {client.agent_id} completed task '{redact_text(task.get('title'), 80)}' via {args.adapter}.",
            "source_ref": run_id,
            "access_tags": ["worker-loop", args.adapter, "review"],
            "confidence": 0.72,
        })
    client.post("/api/agent-gateway/audit", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "action": "agent_worker.task_processed",
        "entity_type": "runs",
        "entity_id": run_id,
        "task_id": task_id,
        "run_id": run_id,
        "metadata": {
            "adapter": args.adapter,
            "ok": result.ok,
            "prompt_hash": result.prompt_hash,
            "prompt_profile_id": result.prompt_profile_id,
            "prompt_profile_version": result.prompt_profile_version,
            "prompt_profile_hash": result.prompt_profile_hash,
            "raw_payload_hash": result.raw_payload_hash,
            "attempt_count": result.attempt_count,
            "max_attempts": result.max_attempts,
            "retryable_final": result.retryable,
            "observation_level": capability.get("observation_level"),
            "risk_floor": capability.get("risk_floor"),
            "effective_risk_level": tool_risk,
            "commercial_readiness": capability.get("commercial_readiness"),
            "requires_prepared_action_for_external_write": capability.get("requires_prepared_action_for_external_write"),
            "worker_runtime_event_id": worker_runtime_event_id,
            "worker_runtime_event_summary_recorded": bool(worker_runtime_event_id),
            "runtime_internal_tools_remain_opaque": capability.get("observation_level") == "ledger_summary_only",
            "knowledge_retrieval_evidence_consumed": bool(knowledge_evidence.get("knowledge_retrieval_evidence_consumed")),
            "knowledge_retrieval_packet_hash": knowledge_evidence.get("packet_hash"),
            "knowledge_retrieval_query_hash": knowledge_evidence.get("query_hash"),
            "knowledge_retrieval_status": knowledge_evidence.get("packet_status") or knowledge_evidence.get("status"),
            "knowledge_retrieval_task_context": knowledge_evidence.get("task_context") or {},
            "knowledge_retrieval_ids": knowledge_evidence.get("retrieval_ids") or [],
            "knowledge_retrieval_paths": knowledge_evidence.get("paths") or [],
            "knowledge_retrieval_source_hashes": knowledge_evidence.get("source_hashes") or [],
            "loop_supervision_gate": loop_supervision_gate,
            "knowledge_retrieval_omissions": {
                "query_omitted": True,
                "snippet_omitted": True,
                "raw_content_omitted": True,
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "token_omitted": True,
            },
            **secret_boundary,
        },
    })
    manifest_payload = create_worker_plan_manifest(client, plan_id, run_id, tool_call_id, evaluation_id, artifact_id)
    manifest = manifest_payload.get("manifest") or {}
    manifest_verification = manifest_payload.get("verification") or {}
    client.post("/api/agent-gateway/heartbeat", {
        "workspace_id": client.workspace_id,
        "agent_id": client.agent_id,
        "status": "idle" if result.ok else "error",
        "summary": result.output_summary,
        "runtime_type": args.adapter,
    })
    return {
        "processed": True,
        "task_id": task_id,
        "run_id": run_id,
        "plan_id": plan_id,
        "plan_reused_from_intake": plan_reused,
        "plan_evidence_manifest_id": manifest.get("manifest_id"),
        "plan_evidence_status": manifest.get("status"),
        "plan_evidence_pass": manifest_verification.get("pass"),
        "adapter": args.adapter,
        "ok": result.ok,
        "attempt_count": result.attempt_count,
        "prompt_profile": {
            "profile_id": result.prompt_profile_id,
            "version": result.prompt_profile_version,
            "profile_hash": result.prompt_profile_hash,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
        "output_summary": result.output_summary,
        "error_type": result.error_type,
        "worker_runtime_event_id": worker_runtime_event_id,
        "knowledge_retrieval_evidence": {
            "consumed": bool(knowledge_evidence.get("knowledge_retrieval_evidence_consumed")),
            "packet_hash": knowledge_evidence.get("packet_hash"),
            "query_hash": knowledge_evidence.get("query_hash"),
            "status": knowledge_evidence.get("packet_status") or knowledge_evidence.get("status"),
            "task_context": knowledge_evidence.get("task_context") or {},
            "result_count": knowledge_evidence.get("result_count") or 0,
            "retrieval_ids": knowledge_evidence.get("retrieval_ids") or [],
            "paths": knowledge_evidence.get("paths") or [],
            "source_hashes": knowledge_evidence.get("source_hashes") or [],
            "query_omitted": True,
            "snippet_omitted": True,
            "raw_content_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
        "loop_supervision_gate": loop_supervision_gate,
        "secret_boundary": secret_boundary,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an AgentOps MIS worker loop.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--api-key", default=os.environ.get("AGENTOPS_API_KEY", ""))
    parser.add_argument("--credential-source", choices=["direct", "local_config"], default=os.environ.get("AGENTOPS_WORKER_CREDENTIAL_SOURCE", "direct"), help="Load a direct API key or a locked local AgentOps CLI config at process start.")
    parser.add_argument("--config-path", default=os.environ.get("AGENTOPS_CONFIG", str(DEFAULT_CONFIG_PATH)), help="Path used only with --credential-source local_config.")
    parser.add_argument("--use-session", action="store_true", help="Mint a short-lived Agent Gateway session before running the worker.")
    parser.add_argument("--session-ttl-sec", type=int, default=int(os.environ.get("AGENTOPS_SESSION_TTL_SEC", "900")), help="Session TTL when --use-session is set.")
    parser.add_argument("--session-refresh-margin-sec", type=float, default=float(os.environ.get("AGENTOPS_SESSION_REFRESH_MARGIN_SEC", "60")), help="Refresh the short-lived session when it has this many seconds or less remaining.")
    parser.add_argument("--session-scopes", default=os.environ.get("AGENTOPS_SESSION_SCOPES", ""), help="Optional comma-separated subset for the worker session. Defaults to parent token scopes.")
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--task-id", default=os.environ.get("AGENTOPS_TASK_ID", ""), help="Optional exact task id to pull and process.")
    parser.add_argument("--status", action="append", default=["planned"], help="Task status to pull. Repeatable.")
    parser.add_argument("--enforce-intake", action=argparse.BooleanOptionalAction, default=True, help="Require Agent Plan / knowledge / base-reference / risk intake gates before pulling tasks.")
    parser.add_argument("--auto-plan-intake", action=argparse.BooleanOptionalAction, default=True, help="When intake blocks an assigned low/medium-risk task for missing/unverified Agent Plan, create or verify the plan before the next poll.")
    parser.add_argument("--once", action="store_true", help="Process at most one task and exit.")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--idle-backoff-max", type=float, default=30.0, help="Maximum sleep seconds after consecutive no-task polls.")
    parser.add_argument("--error-backoff-max", type=float, default=30.0, help="Maximum sleep seconds after consecutive worker errors.")
    parser.add_argument("--backoff-factor", type=float, default=2.0, help="Exponential backoff factor for idle/error loops.")
    parser.add_argument("--max-tasks", type=int, default=1, help="Maximum tasks to process before exit. Use 0 for no limit.")
    parser.add_argument("--confirm-run", action="store_true", help="Allow live runtime adapter execution.")
    parser.add_argument("--allow-high-risk", action="store_true", help="Allow high/critical risk tasks.")
    parser.add_argument("--adapter-max-attempts", type=int, default=int(os.environ.get("AGENTOPS_ADAPTER_MAX_ATTEMPTS", "1")), help="Maximum adapter execution attempts for retryable failures.")
    parser.add_argument("--adapter-retry-delay-sec", type=float, default=float(os.environ.get("AGENTOPS_ADAPTER_RETRY_DELAY_SEC", "1")), help="Delay between retryable adapter attempts.")
    parser.add_argument("--mock-failures-before-success", type=int, default=int(os.environ.get("AGENTOPS_MOCK_FAILURES_BEFORE_SUCCESS", "0")), help="Local test hook: make the mock adapter fail this many retryable attempts before succeeding.")
    parser.add_argument("--hermes-gateway-url", default=os.environ.get("HERMES_GATEWAY_URL", DEFAULT_HERMES_GATEWAY_URL))
    parser.add_argument("--hermes-model", default=os.environ.get("HERMES_MODEL", DEFAULT_HERMES_MODEL))
    parser.add_argument("--hermes-timeout", type=int, default=int(os.environ.get("HERMES_TIMEOUT", "180")))
    parser.add_argument("--hermes-max-tokens", type=int, default=DEFAULT_HERMES_MAX_TOKENS)
    parser.add_argument("--openclaw-bin", default=os.environ.get("OPENCLAW_BIN", DEFAULT_OPENCLAW_BIN))
    parser.add_argument("--openclaw-agent", default=os.environ.get("OPENCLAW_AGENT", "main"))
    parser.add_argument("--openclaw-timeout", type=int, default=int(os.environ.get("OPENCLAW_TIMEOUT", "180")))
    parser.add_argument("--continue-on-error", action="store_true", help="Keep polling after a loop/API/adapter error.")
    parser.add_argument("--max-errors", type=int, default=5, help="Stop after this many consecutive errors when continuing.")
    parser.add_argument("--state-path", default=os.environ.get("AGENTOPS_WORKER_STATE_PATH", ""))
    parser.add_argument("--write-state", action="store_true", help="Write local worker state under .agentops_runtime/workers.")
    parser.add_argument("--jsonl-log", action="store_true", help="Emit one JSON log line per loop iteration.")
    return parser


def service_label(agent_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", agent_id or DEFAULT_AGENT_ID).strip("-")
    return f"local.agentops.worker.{safe or 'agent'}"


def resolve_worker_entrypoint(args) -> list[str]:
    configured = str(getattr(args, "worker_command", "") or "").strip()
    if configured:
        return shlex.split(configured)
    installed = shutil.which("agentops-worker")
    if installed:
        return [installed]
    return [sys.executable, "-m", "agentops_mis_cli.worker"]


def service_env_values(args) -> dict[str, str]:
    env_values = {
        "AGENTOPS_BASE_URL": args.base_url,
        "AGENTOPS_WORKSPACE_ID": args.workspace_id,
        "AGENTOPS_AGENT_ID": args.agent_id,
        "AGENTOPS_WORKER_RUNTIME_DIR": args.runtime_dir,
        "AGENTOPS_WORKER_CWD": args.working_directory,
    }
    credential_source = str(getattr(args, "credential_source", "direct") or "direct")
    if credential_source == "local_config":
        config_path = Path(str(getattr(args, "config_path", "") or DEFAULT_CONFIG_PATH)).expanduser().resolve(strict=False)
        env_values["AGENTOPS_WORKER_CREDENTIAL_SOURCE"] = "local_config"
        env_values["AGENTOPS_CONFIG"] = str(config_path)
    api_key_placeholder = str(args.api_key_placeholder or "").strip()
    if credential_source == "direct" and api_key_placeholder and api_key_placeholder != DEFAULT_API_KEY_PLACEHOLDER:
        env_values["AGENTOPS_API_KEY"] = api_key_placeholder
    return env_values


def build_worker_command(args) -> list[str]:
    command = [
        *resolve_worker_entrypoint(args),
        "--adapter",
        args.adapter,
        "--poll-interval",
        str(args.poll_interval),
        "--max-tasks",
        "0",
        "--continue-on-error",
        "--write-state",
        "--jsonl-log",
    ]
    api_key_placeholder = str(args.api_key_placeholder or "").strip()
    if getattr(args, "use_session", False) or getattr(args, "credential_source", "direct") == "local_config" or api_key_placeholder not in {"", DEFAULT_API_KEY_PLACEHOLDER}:
        command.extend([
            "--use-session",
            "--session-ttl-sec",
            str(args.session_ttl_sec),
            "--session-refresh-margin-sec",
            str(args.session_refresh_margin_sec),
        ])
    if args.confirm_run:
        command.append("--confirm-run")
    return command


def render_launchd_template(args) -> str:
    label = args.label or service_label(args.agent_id)
    runtime_dir = args.runtime_dir or "~/Library/Application Support/AgentOpsMIS/workers"
    log_path = str(Path(args.log_path or f"~/Library/Logs/{label}.log").expanduser())
    args.runtime_dir = runtime_dir
    env_values = service_env_values(args)
    program_args = ["/usr/bin/env", *build_worker_command(args)]
    arg_items = "\n".join(f"    <string>{html.escape(item)}</string>" for item in program_args)
    env_items = "\n".join(
        f"    <key>{html.escape(key)}</key>\n    <string>{html.escape(str(value))}</string>"
        for key, value in env_values.items()
    )
    return f"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
  <key>Label</key>
  <string>{html.escape(label)}</string>
  <key>ProgramArguments</key>
  <array>
{arg_items}
  </array>
  <key>EnvironmentVariables</key>
  <dict>
{env_items}
  </dict>
  <key>WorkingDirectory</key>
  <string>{html.escape(args.working_directory)}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{html.escape(log_path)}</string>
  <key>StandardErrorPath</key>
  <string>{html.escape(log_path)}</string>
</dict>
</plist>
"""


def render_systemd_template(args) -> str:
    label = args.label or service_label(args.agent_id)
    runtime_dir = args.runtime_dir or "%h/.agentops/workers"
    log_path = args.log_path or "%h/.agentops/agentops-worker.log"
    args.runtime_dir = runtime_dir
    env_values = service_env_values(args)
    env_lines = "\n".join(f"Environment={shlex.quote(f'{key}={value}')}" for key, value in env_values.items())
    command = " ".join(shlex.quote(part) for part in build_worker_command(args))
    return f"""[Unit]
Description=AgentOps MIS Worker ({label})
After=network-online.target

[Service]
Type=simple
{env_lines}
ExecStart=/usr/bin/env {command}
WorkingDirectory={shlex.quote(args.working_directory)}
Restart=always
RestartSec=5
StandardOutput=append:{log_path}
StandardError=append:{log_path}

[Install]
WantedBy=default.target
"""


def build_service_template_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a safe launchd/systemd template for agentops-worker.")
    parser.add_argument("--manager", choices=["launchd", "systemd"], required=True)
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--use-session", action="store_true", help="Render a session-minting worker command for remote/scoped tokens. Local loopback services omit this by default.")
    parser.add_argument("--session-ttl-sec", type=int, default=900)
    parser.add_argument("--session-refresh-margin-sec", type=float, default=60)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--label", default="")
    parser.add_argument("--working-directory", default=str(DEFAULT_WORKER_CWD))
    parser.add_argument("--runtime-dir", default="")
    parser.add_argument("--log-path", default="")
    parser.add_argument("--api-key-placeholder", default=DEFAULT_API_KEY_PLACEHOLDER)
    parser.add_argument("--credential-source", choices=["direct", "local_config"], default="direct")
    parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--worker-command", default="", help="Worker executable command for service templates. Defaults to installed agentops-worker or python -m fallback.")
    return parser


def render_service_template_for_args(args) -> str:
    if args.manager == "launchd":
        return render_launchd_template(args)
    return render_systemd_template(args)


def default_service_path(manager: str, agent_id: str, label: str = "") -> Path:
    safe_agent = re.sub(r"[^A-Za-z0-9_.-]+", "-", agent_id or DEFAULT_AGENT_ID).strip("-") or "agent"
    if manager == "launchd":
        service_name = label or service_label(agent_id)
        return Path("~/Library/LaunchAgents").expanduser() / f"{service_name}.plist"
    return Path("~/.config/systemd/user").expanduser() / f"agentops-worker-{safe_agent}.service"


def service_load_commands(manager: str, path: Path, label: str) -> dict:
    if manager == "launchd":
        domain = f"gui/{os.getuid()}"
        return {
            "load": ["launchctl", "bootstrap", domain, str(path)],
            "unload": ["launchctl", "bootout", domain, str(path)],
            "status": ["launchctl", "print", f"{domain}/{label}"],
        }
    unit = path.name
    return {
        "daemon_reload": ["systemctl", "--user", "daemon-reload"],
        "enable_now": ["systemctl", "--user", "enable", "--now", unit],
        "disable_now": ["systemctl", "--user", "disable", "--now", unit],
        "status": ["systemctl", "--user", "status", unit, "--no-pager"],
    }


def service_control_sequence(manager: str, path: Path, label: str, action: str) -> list[list[str]]:
    commands = service_load_commands(manager, path, label)
    if manager == "launchd":
        if action == "load":
            return [commands["load"]]
        if action == "unload":
            return [commands["unload"]]
        return [commands["unload"], commands["load"]]
    if action == "load":
        return [commands["daemon_reload"], commands["enable_now"]]
    if action == "unload":
        return [commands["disable_now"]]
    return [commands["daemon_reload"], ["systemctl", "--user", "restart", path.name]]


def shell_join(command: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def read_service_file(path: Path) -> tuple[bool, str]:
    try:
        return True, path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return False, ""
    except Exception as exc:
        return False, f"READ_ERROR:{redact_text(str(exc), 200)}"


def launchd_status(label: str, timeout: int) -> dict:
    try:
        target = f"gui/{os.getuid()}/{label}"
        proc = subprocess.run(
            ["launchctl", "print", target],
            capture_output=True,
            text=True,
            timeout=max(1, min(timeout, 20)),
            check=False,
        )
        summary = redact_text((proc.stdout or proc.stderr or "").strip(), 600)
        return {
            "checked": True,
            "manager": "launchd",
            "label": label,
            "loaded": proc.returncode == 0,
            "returncode": proc.returncode,
            "summary": summary,
        }
    except Exception as exc:
        return {"checked": True, "manager": "launchd", "label": label, "loaded": False, **safe_error(exc)}


def systemd_status(unit: str, timeout: int) -> dict:
    if not shutil.which("systemctl"):
        return {"checked": True, "manager": "systemd", "unit": unit, "available": False, "loaded": False, "summary": "systemctl is not available."}
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "show", unit, "--property=LoadState,ActiveState,SubState,UnitFileState", "--no-pager"],
            capture_output=True,
            text=True,
            timeout=max(1, min(timeout, 20)),
            check=False,
        )
        fields = {}
        for line in (proc.stdout or "").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key] = value
        return {
            "checked": True,
            "manager": "systemd",
            "unit": unit,
            "available": True,
            "loaded": fields.get("LoadState") == "loaded",
            "active_state": fields.get("ActiveState"),
            "sub_state": fields.get("SubState"),
            "unit_file_state": fields.get("UnitFileState"),
            "returncode": proc.returncode,
            "summary": redact_text(proc.stderr or proc.stdout or "", 600),
        }
    except Exception as exc:
        return {"checked": True, "manager": "systemd", "unit": unit, "available": True, "loaded": False, **safe_error(exc)}


def check_service_installation(args) -> dict:
    label = args.label or service_label(args.agent_id)
    service_path = Path(args.service_path).expanduser() if args.service_path else default_service_path(args.manager, args.agent_id, label)
    exists, content = read_service_file(service_path)
    token_like_detected = bool(re.search(r"(agtok_|agtsess_|sk-|ntn_)", content))
    placeholder_present = args.api_key_placeholder in content if exists else False
    command_has_worker = "agentops-worker" in content or "agentops_mis_cli.worker" in content
    adapter_present = args.adapter in content
    use_session_present = "--use-session" in content
    if args.manager == "launchd":
        local_config_reference = bool(
            re.search(r"AGENTOPS_WORKER_CREDENTIAL_SOURCE</key>\s*<string>local_config</string>", content)
            and re.search(r"AGENTOPS_CONFIG</key>\s*<string>[^<]+</string>", content)
            and "AGENTOPS_API_KEY" not in content
        )
    else:
        local_config_reference = bool(
            re.search(r"(?m)^Environment=.*AGENTOPS_WORKER_CREDENTIAL_SOURCE=local_config", content)
            and re.search(r"(?m)^Environment=.*AGENTOPS_CONFIG=\S+", content)
            and "AGENTOPS_API_KEY" not in content
        )
    if args.manager == "launchd":
        local_dev_no_token = bool(
            not re.search(r"AGENTOPS_API_KEY", content)
            and re.search(r"AGENTOPS_BASE_URL</key>\s*<string>http://127\.0\.0\.1:", content)
        )
    else:
        local_dev_no_token = bool(
            not re.search(r"AGENTOPS_API_KEY", content)
            and re.search(r"(?m)^Environment=AGENTOPS_BASE_URL=http://127\.0\.0\.1:", content)
        )
    if args.manager == "launchd":
        launchd_keepalive = bool(re.search(r"<key>KeepAlive</key>\s*<true/>", content))
        relaunch_policy = {
            "manager": "launchd",
            "enabled": launchd_keepalive,
            "policy": "KeepAlive=true",
            "raw_content_omitted": True,
        }
    else:
        systemd_restart_always = bool(re.search(r"(?m)^Restart=always$", content))
        systemd_restart_sec_ok = bool(re.search(r"(?m)^RestartSec=5$", content))
        relaunch_policy = {
            "manager": "systemd",
            "enabled": bool(systemd_restart_always and systemd_restart_sec_ok),
            "policy": "Restart=always",
            "restart_sec": "5" if systemd_restart_sec_ok else None,
            "raw_content_omitted": True,
        }
    confirm_gate_ok = args.adapter == "mock" or "--confirm-run" in content
    if args.manager == "launchd":
        service_status = launchd_status(label, args.timeout)
    else:
        unit = service_path.name
        service_status = systemd_status(unit, args.timeout)
    observed_credential_source = "local_config" if local_config_reference else "direct"
    requested_credential_source = str(getattr(args, "credential_source", "auto") or "auto")
    credential_source_matches = requested_credential_source == "auto" or requested_credential_source == observed_credential_source
    credential_source_ok = credential_source_matches and bool(
        local_config_reference and use_session_present
        if local_config_reference
        else (use_session_present or local_dev_no_token)
    )
    ok = bool(exists and command_has_worker and adapter_present and credential_source_ok and confirm_gate_ok and relaunch_policy["enabled"] and not token_like_detected)
    hints = []
    if not exists:
        hints.append("Render a template with agentops-worker service-template and write it to service_path.")
    if exists and not relaunch_policy["enabled"]:
        hints.append("Service file does not expose the expected OS relaunch policy.")
    if token_like_detected:
        hints.append("Replace raw tokens with a local environment-only secret flow; do not commit service files with real tokens.")
    if args.adapter != "mock" and not confirm_gate_ok:
        hints.append("Hermes/OpenClaw services need --confirm-run only when the operator intentionally allows live execution.")
    if exists and not use_session_present and not local_dev_no_token:
        hints.append("Remote/shared service files should use --use-session with a scoped token source; local loopback can run without a session token.")
    if "AGENTOPS_WORKER_CREDENTIAL_SOURCE" in content and not local_config_reference:
        hints.append("Local config credential references must include a config path, omit raw API keys, and mint a short-lived session.")
    if exists and not credential_source_matches:
        hints.append("Installed service credential source does not match the requested check policy.")
    if exists and not service_status.get("loaded"):
        hints.append("Service file exists but does not appear loaded; load it manually on the agent machine after review.")
    return {
        "ok": ok,
        "provider": "agentops-worker",
        "command": "agentops-worker service-check",
        "manager": args.manager,
        "label": label,
        "agent_id": args.agent_id,
        "workspace_id": args.workspace_id,
        "adapter": args.adapter,
        "service_path": str(service_path),
        "service_file": {
            "exists": exists,
            "command_has_worker": command_has_worker,
            "adapter_present": adapter_present,
            "use_session_present": use_session_present,
            "credential_source": observed_credential_source,
            "credential_source_matches": credential_source_matches,
            "local_config_reference": local_config_reference,
            "local_dev_no_token": local_dev_no_token,
            "relaunch_policy_ok": relaunch_policy["enabled"],
            "confirm_gate_ok": confirm_gate_ok,
            "placeholder_present": placeholder_present,
            "token_like_detected": token_like_detected,
            "raw_content_omitted": True,
        },
        "relaunch_policy": relaunch_policy,
        "service_status": service_status,
        "setup_hints": hints,
        "live_execution_performed": False,
        "token_omitted": True,
    }


def build_service_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only check for an agentops-worker launchd/systemd service file.")
    parser.add_argument("--manager", choices=["launchd", "systemd"], required=True)
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--label", default="")
    parser.add_argument("--service-path", default="")
    parser.add_argument("--api-key-placeholder", default=DEFAULT_API_KEY_PLACEHOLDER)
    parser.add_argument("--credential-source", choices=["auto", "direct", "local_config"], default="auto")
    parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--timeout", type=int, default=5)
    return parser


def run_service_check(argv: list[str]) -> int:
    args = build_service_check_parser().parse_args(argv)
    payload = check_service_installation(args)
    print(json_dumps(payload))
    return 0 if payload.get("ok") else 1


def install_service_file(args) -> dict:
    label = args.label or service_label(args.agent_id)
    service_path = Path(args.service_path).expanduser() if args.service_path else default_service_path(args.manager, args.agent_id, label)
    template = render_service_template_for_args(args)
    token_like_detected = bool(re.search(r"(agtok_|agtsess_|sk-|ntn_)", template))
    exists_before = service_path.exists()
    safe_to_write = not token_like_detected and (not exists_before or bool(args.overwrite))
    wrote = False
    write_error = None
    if args.confirm_install and safe_to_write:
        try:
            service_path.parent.mkdir(parents=True, exist_ok=True)
            service_path.write_text(template, encoding="utf-8")
            service_path.chmod(0o600)
            wrote = True
        except Exception as exc:
            write_error = safe_error(exc)
    check_args = argparse.Namespace(
        manager=args.manager,
        workspace_id=args.workspace_id,
        agent_id=args.agent_id,
        adapter=args.adapter,
        label=label,
        service_path=str(service_path),
        api_key_placeholder=args.api_key_placeholder,
        credential_source=getattr(args, "credential_source", "direct"),
        config_path=getattr(args, "config_path", str(DEFAULT_CONFIG_PATH)),
        worker_command=args.worker_command,
        timeout=args.timeout,
    )
    service_check = check_service_installation(check_args) if service_path.exists() else {
        "ok": False,
        "service_file": {
            "exists": False,
            "raw_content_omitted": True,
            "token_like_detected": token_like_detected,
        },
    }
    setup_hints = []
    if not args.confirm_install:
        setup_hints.append("Dry-run only. Re-run with --confirm-install to write the service file.")
    if exists_before and not args.overwrite:
        setup_hints.append("Service file already exists. Pass --overwrite only after reviewing the current file.")
    if token_like_detected:
        setup_hints.append("Refusing to write a service template containing token-like values.")
    if wrote:
        setup_hints.append("Review the service file locally, configure secrets outside git, then load it manually if desired.")
    if write_error:
        setup_hints.append("Service file write failed; inspect permissions on the target directory.")
    ok = bool((not args.confirm_install and not token_like_detected) or (wrote and service_check.get("ok") is True))
    if args.confirm_install and (exists_before and not args.overwrite):
        ok = False
    if write_error:
        ok = False
    return {
        "ok": ok,
        "provider": "agentops-worker",
        "command": "agentops-worker service-install",
        "manager": args.manager,
        "dry_run": not bool(args.confirm_install),
        "confirmed_install": bool(args.confirm_install),
        "wrote": wrote,
        "overwrite": bool(args.overwrite),
        "exists_before": exists_before,
        "agent_id": args.agent_id,
        "workspace_id": args.workspace_id,
        "adapter": args.adapter,
        "credential_source": getattr(args, "credential_source", "direct"),
        "service_path": str(service_path),
        "service_file_mode": "0600" if wrote else None,
        "template_hash": stable_hash(template),
        "template_bytes": len(template.encode("utf-8")),
        "service_check": service_check,
        "load_commands": service_load_commands(args.manager, service_path, label),
        "setup_hints": setup_hints,
        "write_error": write_error,
        "live_execution_performed": False,
        "service_loaded": False,
        "raw_content_omitted": True,
        "token_omitted": True,
    }


def build_service_install_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run or write a safe agentops-worker launchd/systemd service file.")
    parser.add_argument("--manager", choices=["launchd", "systemd"], required=True)
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--use-session", action="store_true", help="Render a session-minting worker command for remote/scoped tokens. Local loopback services omit this by default.")
    parser.add_argument("--session-ttl-sec", type=int, default=900)
    parser.add_argument("--session-refresh-margin-sec", type=float, default=60)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--label", default="")
    parser.add_argument("--working-directory", default=str(DEFAULT_WORKER_CWD))
    parser.add_argument("--runtime-dir", default="")
    parser.add_argument("--log-path", default="")
    parser.add_argument("--api-key-placeholder", default=DEFAULT_API_KEY_PLACEHOLDER)
    parser.add_argument("--credential-source", choices=["direct", "local_config"], default="direct")
    parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--worker-command", default="", help="Worker executable command for service templates. Defaults to installed agentops-worker or python -m fallback.")
    parser.add_argument("--service-path", default="")
    parser.add_argument("--confirm-install", action="store_true", help="Write the service file. Default is dry-run.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing service file after local review.")
    parser.add_argument("--timeout", type=int, default=5)
    return parser


def run_service_install(argv: list[str]) -> int:
    args = build_service_install_parser().parse_args(argv)
    payload = install_service_file(args)
    print(json_dumps(payload))
    return 0 if payload.get("ok") else 1


def execute_service_command(command: list[str], timeout: int) -> dict:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(1, min(timeout, 60)),
            check=False,
        )
        return {
            "command": shell_join(command),
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "summary": redact_text(proc.stdout or proc.stderr or "", 700),
        }
    except Exception as exc:
        return {"command": shell_join(command), "ok": False, **safe_error(exc)}


def control_service(args) -> dict:
    label = args.label or service_label(args.agent_id)
    service_path = Path(args.service_path).expanduser() if args.service_path else default_service_path(args.manager, args.agent_id, label)
    check_args = argparse.Namespace(
        manager=args.manager,
        workspace_id=args.workspace_id,
        agent_id=args.agent_id,
        adapter=args.adapter,
        label=label,
        service_path=str(service_path),
        api_key_placeholder=args.api_key_placeholder,
        credential_source=getattr(args, "credential_source", "auto"),
        config_path=getattr(args, "config_path", str(DEFAULT_CONFIG_PATH)),
        timeout=args.timeout,
    )
    service_check = check_service_installation(check_args)
    service_file = service_check.get("service_file") or {}
    service_status = service_check.get("service_status") if isinstance(service_check.get("service_status"), dict) else {}
    exists = bool(service_file.get("exists"))
    token_like_detected = bool(service_file.get("token_like_detected"))
    confirm_gate_ok = bool(service_file.get("confirm_gate_ok"))
    command_has_worker = bool(service_file.get("command_has_worker"))
    already_loaded = service_status.get("loaded") is True
    planned = service_control_sequence(args.manager, service_path, label, args.action)
    failures = []
    if not exists:
        failures.append("service file is missing")
    if not command_has_worker:
        failures.append("service file does not appear to run agentops-worker")
    if args.action in {"load", "restart"} and token_like_detected:
        failures.append("refusing to load/restart a service file containing token-like values")
    if args.action in {"load", "restart"} and not confirm_gate_ok:
        failures.append("refusing to load/restart Hermes/OpenClaw service without --confirm-run in the service template")
    dry_run = not bool(args.confirm_control)
    command_results = []
    loaded_noop = bool(args.action == "load" and already_loaded and not failures)
    if not dry_run and not failures:
        if loaded_noop:
            command_results.append({
                "command": "service-control load skipped",
                "ok": True,
                "skipped": True,
                "reason": "service_already_loaded",
                "summary": "Service is already loaded; no launchd/systemd load command executed.",
            })
        else:
            for command in planned:
                result = execute_service_command(command, args.timeout)
                command_results.append(result)
                if not result.get("ok") and not (args.action == "restart" and len(command_results) == 1):
                    failures.append(f"service control command failed: {result.get('command')}")
                    break
    setup_hints = []
    if dry_run:
        setup_hints.append("Preview only. Re-run with --confirm-control on the agent machine to mutate launchd/systemd state.")
    if loaded_noop:
        setup_hints.append("Service is already loaded; confirmed load is treated as an idempotent no-op.")
    if token_like_detected:
        setup_hints.append("Move secrets out of the service file before load/restart; raw token-like content is never printed.")
    if args.adapter in {"hermes", "openclaw"} and not confirm_gate_ok:
        setup_hints.append("Live adapter services must include --confirm-run in the rendered worker command.")
    return {
        "ok": not failures,
        "provider": "agentops-worker",
        "command": "agentops-worker service-control",
        "manager": args.manager,
        "action": args.action,
        "dry_run": dry_run,
        "confirmed_control": bool(args.confirm_control),
        "service_already_loaded": already_loaded,
        "service_control_skipped": bool(not dry_run and loaded_noop),
        "service_mutated": bool(args.confirm_control and not failures and not loaded_noop),
        "service_path": str(service_path),
        "label": label,
        "agent_id": args.agent_id,
        "workspace_id": args.workspace_id,
        "adapter": args.adapter,
        "service_check": service_check,
        "planned_commands": [shell_join(command) for command in planned],
        "command_results": command_results,
        "failures": failures,
        "setup_hints": setup_hints,
        "live_execution_performed": bool(args.confirm_control and args.action in {"load", "restart"} and args.adapter in {"hermes", "openclaw"} and not failures and not loaded_noop),
        "raw_content_omitted": True,
        "token_omitted": True,
    }


def build_service_control_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview or explicitly run launchd/systemd control for an agentops-worker service.")
    parser.add_argument("--manager", choices=["launchd", "systemd"], required=True)
    parser.add_argument("--action", choices=["load", "unload", "restart"], required=True)
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--label", default="")
    parser.add_argument("--service-path", default="")
    parser.add_argument("--api-key-placeholder", default=DEFAULT_API_KEY_PLACEHOLDER)
    parser.add_argument("--credential-source", choices=["auto", "direct", "local_config"], default="auto")
    parser.add_argument("--config-path", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--confirm-control", action="store_true", help="Actually call launchctl/systemctl. Default is preview only.")
    return parser


def run_service_control(argv: list[str]) -> int:
    args = build_service_control_parser().parse_args(argv)
    payload = control_service(args)
    print(json_dumps(payload))
    return 0 if payload.get("ok") else 1


def render_service_template(argv: list[str]) -> int:
    args = build_service_template_parser().parse_args(argv)
    sys.stdout.write(render_service_template_for_args(args))
    return 0


def preflight_http_json(url: str, timeout: int = 5) -> tuple[bool, int | None, dict]:
    try:
        req = Request(url, headers={"Accept": "application/json"}, method="GET")
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"raw_summary": redact_text(raw, 200)}
            return True, res.status, payload
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {"error": redact_text(str(exc), 200)}
        return False, exc.code, payload
    except Exception as exc:
        return False, None, safe_error(exc)


def check_gateway_preflight(args) -> dict:
    client = AgentOpsClient(args.base_url, args.workspace_id, args.agent_id, args.api_key)
    try:
        status = client.get("/api/agent-gateway/status")
        return {
            "ok": True,
            "mode": ((status.get("auth") or {}).get("mode") or "local"),
            "agent_id": (status.get("auth") or {}).get("agent_id") or args.agent_id,
            "workspace_id": (status.get("auth") or {}).get("workspace_id") or args.workspace_id,
            "scope_count": len((status.get("auth") or {}).get("scopes") or []),
            "token_omitted": True,
        }
    except Exception as exc:
        return {"ok": False, **safe_error(exc), "token_omitted": True}


def check_adapter_preflight(args) -> dict:
    if args.adapter == "mock":
        return {
            "ok": True,
            "adapter": "mock",
            "target_resource": "local://agentops/mock-worker",
            "live_execution_performed": False,
        }
    if args.adapter == "hermes":
        gateway_url = args.hermes_gateway_url.rstrip("/")
        health_ok, health_status, health_payload = preflight_http_json(f"{gateway_url}/health", timeout=args.timeout)
        models_ok, models_status, models_payload = preflight_http_json(f"{gateway_url}/v1/models", timeout=args.timeout)
        return {
            "ok": bool(health_ok or models_ok),
            "adapter": "hermes",
            "target_resource": gateway_url,
            "health": {"ok": health_ok, "status": health_status, "summary": redact_text(health_payload, 200)},
            "models": {"ok": models_ok, "status": models_status, "summary": redact_text(models_payload, 200)},
            "live_execution_performed": False,
        }
    binary = Path(args.openclaw_bin).expanduser()
    exists = binary.exists()
    executable = os.access(binary, os.X_OK) if exists else False
    version_summary = ""
    version_ok = False
    if exists and executable:
        try:
            proc = subprocess.run(
                [str(binary), "--version"],
                cwd=DEFAULT_WORKER_CWD,
                capture_output=True,
                text=True,
                timeout=min(max(int(args.timeout or 5), 1), 20),
                check=False,
            )
            version_ok = proc.returncode == 0
            version_summary = redact_text(proc.stdout or proc.stderr or f"exit={proc.returncode}", 200)
        except Exception as exc:
            version_summary = redact_text(str(exc), 200)
    return {
        "ok": bool(exists and executable),
        "adapter": "openclaw",
        "binary_path": str(binary),
        "binary_exists": exists,
        "binary_executable": executable,
        "version_ok": version_ok,
        "version_summary": version_summary,
        "live_execution_performed": False,
    }


def build_preflight_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a read-only AgentOps worker adapter preflight.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--agent-id", default=os.environ.get("AGENTOPS_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--api-key", default=os.environ.get("AGENTOPS_API_KEY", ""))
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--hermes-gateway-url", default=os.environ.get("HERMES_GATEWAY_URL", DEFAULT_HERMES_GATEWAY_URL))
    parser.add_argument("--openclaw-bin", default=os.environ.get("OPENCLAW_BIN", DEFAULT_OPENCLAW_BIN))
    parser.add_argument("--timeout", type=int, default=5)
    return parser


def run_preflight(argv: list[str]) -> int:
    args = build_preflight_parser().parse_args(argv)
    gateway = check_gateway_preflight(args)
    adapter = check_adapter_preflight(args)
    ok = bool(gateway.get("ok") and adapter.get("ok"))
    payload = {
        "ok": ok,
        "provider": "agentops-worker",
        "agent_id": args.agent_id,
        "workspace_id": args.workspace_id,
        "adapter": args.adapter,
        "gateway": gateway,
        "adapter_preflight": adapter,
        "live_execution_performed": False,
        "raw_prompt_response_omitted": True,
        "token_omitted": True,
    }
    print(json_dumps(payload))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["service-template"]:
        return render_service_template(argv[1:])
    if argv[:1] == ["service-install"]:
        return run_service_install(argv[1:])
    if argv[:1] == ["service-check"]:
        return run_service_check(argv[1:])
    if argv[:1] == ["service-control"]:
        return run_service_control(argv[1:])
    if argv[:1] == ["preflight"]:
        return run_preflight(argv[1:])
    args = build_parser().parse_args(argv)
    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)
    state = WorkerState(args)
    try:
        parent_api_key = resolve_worker_api_key(args)
        apply_local_config_session_policy(args)
    except WorkerCredentialError as exc:
        state.stop("failed_credential_source")
        print(json_dumps({
            "ok": False,
            "processed": 0,
            "credential_source": str(getattr(args, "credential_source", "direct") or "direct"),
            "error": exc.code,
            "state": state.data,
            "token_omitted": True,
        }))
        return 1
    args.api_key = parent_api_key
    client = AgentOpsClient(args.base_url, args.workspace_id, args.agent_id, parent_api_key)
    processed = 0
    results = []
    registered = False
    fatal_failure = False
    session_info = None
    session_history = []
    if args.use_session:
        try:
            session_info = ensure_worker_session(client, args, state, parent_api_key, session_info, session_history)
        except Exception as exc:
            error = state.record_error(exc)
            state.stop("failed_session_create")
            print(json_dumps({"ok": False, "processed": 0, "results": [{**error, "processed": False, "ok": False}], "state": state.data, "session": {"token_omitted": True}, "sessions": session_history}))
            return 1
    while True:
        if SHOULD_STOP:
            break
        try:
            if args.use_session:
                session_info = ensure_worker_session(client, args, state, parent_api_key, session_info, session_history)
            if not registered:
                state.update(status="registering")
                register_worker(client, args.adapter)
                registered = True
            state.update(status="polling")
            result = process_one_task(client, args)
            results.append(result)
            state.record_result(result)
            emit_jsonl(args, {"event": "worker.iteration", "ok": True, "result": result, "state": state.data})
            if result.get("processed"):
                processed += 1
            if args.once:
                break
            if args.max_tasks and processed >= args.max_tasks:
                break
            if result.get("processed"):
                sleep_sec = max(args.poll_interval, 0.0)
                sleep_reason = "post_task"
            elif result.get("reason") in {"intake_auto_planned", "intake_plan_verified"}:
                sleep_sec = max(args.poll_interval, 0.0)
                sleep_reason = "post_intake_auto_plan"
            else:
                sleep_sec = backoff_sleep(args.poll_interval, args.idle_backoff_max, int(state.data.get("consecutive_idle") or 1), args.backoff_factor)
                sleep_reason = "idle_backoff"
            state.update(status="sleeping", last_sleep_sec=sleep_sec, next_sleep_sec=sleep_sec, last_sleep_reason=sleep_reason)
            time.sleep(sleep_sec)
        except Exception as exc:
            error = state.record_error(exc)
            result = {"processed": False, "ok": False, **error}
            results.append(result)
            safe_worker_heartbeat(client, args, "error", error["error_message"])
            emit_jsonl(args, {"event": "worker.error", "ok": False, "error": error, "state": state.data})
            if args.once or not args.continue_on_error:
                fatal_failure = True
                state.stop("failed")
                break
            if int(state.data.get("consecutive_errors") or 0) >= max(int(args.max_errors or 1), 1):
                fatal_failure = True
                state.stop("failed_max_errors")
                break
            sleep_sec = backoff_sleep(args.poll_interval, args.error_backoff_max, int(state.data.get("consecutive_errors") or 1), args.backoff_factor)
            state.update(status="sleeping_after_error", last_sleep_sec=sleep_sec, next_sleep_sec=sleep_sec, last_sleep_reason="error_backoff")
            time.sleep(sleep_sec)
    final_ok = (
        not fatal_failure
        and all(item.get("ok", True) for item in results if item.get("processed"))
        and not any(item.get("ok") is False for item in results if args.once)
    )
    final_status = "stopped" if SHOULD_STOP else "completed" if final_ok else "failed"
    state.stop(final_status)
    print(json_dumps({"ok": final_ok, "processed": processed, "results": results, "state": state.data, "session": session_info or {"token_omitted": True}, "sessions": session_history}))
    return 0 if final_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
