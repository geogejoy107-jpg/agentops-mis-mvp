#!/usr/bin/env python3
"""
AgentOps MIS MVP - dependency-free local prototype.
Run:
  python3 server.py --reset
  python3 server.py
Open:
  http://127.0.0.1:8787/dashboard
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import os
import random
import re
import secrets
import signal
import shlex
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
STATIC_DIR = ROOT / "static"
ARTIFACTS_DIR = ROOT / "artifacts"
RUNTIME_DIR = ROOT / ".agentops_runtime"
WORKER_RUNTIME_DIR = RUNTIME_DIR / "workers"
KNOWLEDGE_DIR = ROOT / "knowledge"
OPENCLAW_HOME = Path.home() / ".openclaw"
HERMES_HOME = Path.home() / ".hermes"
OPENCLAW_BIN = Path("/opt/homebrew/bin/openclaw")
DEFAULT_ENTITLEMENTS_PATH = ROOT / "config" / "entitlements.local.json"

RISKY_TOOLS = {
    "shell.exec",
    "github.push",
    "email.send",
    "file.delete",
    "database.write",
    "dify.knowledge.upload",
    "openai.file_search.upload",
}
HIGH_RISK_CATEGORIES = {"shell", "email", "database"}
VALID_TASK_STATUSES = {"backlog", "planned", "running", "waiting_approval", "blocked", "completed", "failed", "canceled"}
VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}
VALID_TOOL_CATEGORIES = {"browser", "github", "file", "shell", "email", "notion", "discord", "database", "mcp", "custom"}
VALID_RUNTIME_TYPES = {"mock", "claude_code", "codex", "openhands", "crewai", "langgraph", "openclaw", "hermes"}

ENTITLEMENT_EDITIONS = {
    "free_local": {
        "label": "Free Local",
        "capabilities": {
            "single_workspace": True,
            "sqlite_ledger": True,
            "mock_runtime": True,
            "openclaw_import": True,
            "hermes_health": True,
            "notion_dry_run": True,
            "manual_export": True,
            "local_dev_admin": True,
            "multi_project": False,
            "runtime_connector_profiles": False,
            "notion_confirmed_export": False,
            "report_templates": False,
            "longer_audit_retention": False,
            "rbac": False,
            "approval_policies": False,
            "connector_scopes": False,
            "agent_performance_reviews": False,
            "quality_gate_dashboards": False,
            "shared_memory_review": False,
            "sso_hooks": False,
            "postgres_adapter": False,
            "signed_audit_exports": False,
            "custom_connector_sdk": False,
        },
    },
    "pro_workspace": {
        "label": "Pro Workspace",
        "inherits": "free_local",
        "capabilities": {
            "multi_project": True,
            "runtime_connector_profiles": True,
            "notion_confirmed_export": True,
            "report_templates": True,
            "longer_audit_retention": True,
        },
    },
    "team_governance": {
        "label": "Team Governance",
        "inherits": "pro_workspace",
        "capabilities": {
            "rbac": True,
            "approval_policies": True,
            "connector_scopes": True,
            "agent_performance_reviews": True,
            "quality_gate_dashboards": True,
            "shared_memory_review": True,
        },
    },
    "enterprise_byoc": {
        "label": "Enterprise / BYOC",
        "inherits": "team_governance",
        "capabilities": {
            "sso_hooks": True,
            "postgres_adapter": True,
            "signed_audit_exports": True,
            "custom_connector_sdk": True,
        },
    },
}

COMMERCIAL_CAPABILITY_GATES = {
    "multi_project": "pro_workspace",
    "runtime_connector_profiles": "pro_workspace",
    "notion_confirmed_export": "pro_workspace",
    "report_templates": "pro_workspace",
    "longer_audit_retention": "pro_workspace",
    "rbac": "team_governance",
    "approval_policies": "team_governance",
    "connector_scopes": "team_governance",
    "agent_performance_reviews": "team_governance",
    "quality_gate_dashboards": "team_governance",
    "shared_memory_review": "team_governance",
    "sso_hooks": "enterprise_byoc",
    "postgres_adapter": "enterprise_byoc",
    "signed_audit_exports": "enterprise_byoc",
    "custom_connector_sdk": "enterprise_byoc",
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def stable_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts) -> str:
    raw = "::".join(str(p) for p in parts if p is not None and str(p) != "")
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()
    if slug and len(slug) <= 64:
        return f"{prefix}_{slug}"
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


def read_json_file(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def normalized_edition(value: str | None) -> str:
    candidate = (value or "").strip().lower().replace("-", "_")
    return candidate if candidate in ENTITLEMENT_EDITIONS else "free_local"


def inherited_capabilities(edition: str) -> dict:
    config = ENTITLEMENT_EDITIONS.get(edition) or ENTITLEMENT_EDITIONS["free_local"]
    inherited = inherited_capabilities(config["inherits"]) if config.get("inherits") else {}
    merged = dict(inherited)
    merged.update(config.get("capabilities") or {})
    return merged


def entitlement_status(headers) -> dict:
    config_path = Path(os.environ.get("AGENTOPS_ENTITLEMENTS_PATH") or DEFAULT_ENTITLEMENTS_PATH).expanduser()
    config = read_json_file(config_path, {}) if config_path.exists() else {}
    env_edition = os.environ.get("AGENTOPS_EDITION")
    edition = normalized_edition(env_edition or config.get("edition"))
    edition_source = "env" if env_edition else "config" if config.get("edition") else "default"
    capabilities = inherited_capabilities(edition)
    overrides = config.get("overrides") if isinstance(config.get("overrides"), dict) else {}
    for key, value in overrides.items():
        if key in capabilities and isinstance(value, bool):
            capabilities[key] = value
    gates = []
    for capability, required_edition in sorted(COMMERCIAL_CAPABILITY_GATES.items()):
        enabled = bool(capabilities.get(capability))
        gates.append({
            "capability": capability,
            "required_edition": required_edition,
            "enabled": enabled,
            "status": "enabled" if enabled else "disabled",
            "enforcement": "read_only_preview",
        })
    return {
        "provider": "agentops-commercial",
        "operation": "entitlement_status",
        "status": "ready",
        "edition": edition,
        "edition_label": ENTITLEMENT_EDITIONS[edition]["label"],
        "edition_source": edition_source,
        "workspace_id": normalize_workspace_id(headers.get("X-AgentOps-Workspace-Id") or "local-demo") if headers else "local-demo",
        "config": {
            "path": str(config_path),
            "loaded": bool(config),
            "overrides_loaded": bool(overrides),
            "example_path": str(ROOT / "config" / "entitlements.example.json"),
        },
        "capabilities": capabilities,
        "gates": gates,
        "next_actions": [
            "Keep this surface read-only until entitlement smoke tests cover fail-closed behavior.",
            "Add enforcement only at explicit product boundaries, not inside low-level ledger writes.",
            "Do not add billing-provider calls until local edition gates are stable.",
        ],
        "contract": "Entitlements are local read-only capability gates first; billing integration comes after product gates are stable.",
        "safety": {
            "read_only": True,
            "live_execution_performed": False,
            "token_omitted": True,
            "billing_call_performed": False,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }


def commercial_capability_enabled(capability: str) -> bool:
    return bool(entitlement_status(None).get("capabilities", {}).get(capability))


def commercial_entitlement_block(conn, capability: str, operation: str, actor: str = "commercial-gate") -> dict:
    status = entitlement_status(None)
    required_edition = COMMERCIAL_CAPABILITY_GATES.get(capability, "pro_workspace")
    payload = {
        "error": "entitlement_required",
        "provider": "agentops-commercial",
        "operation": operation,
        "capability": capability,
        "required_edition": required_edition,
        "current_edition": status.get("edition"),
        "current_edition_label": status.get("edition_label"),
        "created": False,
        "dry_run": False,
        "live_execution_performed": False,
        "billing_call_performed": False,
        "token_omitted": True,
        "message": f"{capability} requires {required_edition}; current edition is {status.get('edition')}.",
    }
    audit(
        conn,
        "system",
        actor,
        "commercial.entitlement_blocked",
        "commercial_capabilities",
        capability,
        None,
        {"blocked": True, "operation": operation, "required_edition": required_edition},
        {"current_edition": status.get("edition"), "billing_call_performed": False},
    )
    conn.commit()
    return payload


def split_provider_model(model, default_provider="unknown"):
    if isinstance(model, dict):
        model = model.get("primary") or model.get("model") or model.get("name")
    if isinstance(model, list):
        model = model[0] if model else None
    value = str(model or "")
    if "/" in value:
        provider, name = value.split("/", 1)
        return provider or default_provider, name or value
    return default_provider, value or "unknown"


def redact_text(text: str | None, limit=200) -> str:
    value = str(text or "")
    value = redact_full_text(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def redact_full_text(text: str | None) -> str:
    value = str(text or "")
    replacements = [
        (r"(?i)(bearer\s+)[a-z0-9._\-]+", r"\1[REDACTED]"),
        (r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;]+", r"\1=[REDACTED]"),
        (r"(?i)\b(?:sk-[a-z0-9._\-]+|ntn_[a-z0-9._\-]+)\b", "[SECRET_REDACTED]"),
        (r"\b(?:agtok|agtsess)_[A-Za-z0-9_-]+\b", "[AGENT_TOKEN_REF_REDACTED]"),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL_REDACTED]"),
        (r"(?<![\w])(?:\+\d{1,3}[\s.-]*)?(?:\(?\d{2,4}\)?[\s.-]+){2,4}\d{2,4}(?![\w])", "[PHONE_REDACTED]"),
    ]
    for pattern, repl in replacements:
        value = re.sub(pattern, repl, value)
    return value


def parse_ms(value):
    try:
        return int(value)
    except Exception:
        return None


def iso_from_ms(value):
    ms = parse_ms(value)
    if ms is None:
        return now_iso()
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat()


def socket_listening(host: str, port: int, timeout=0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def url_listening(url: str, timeout=0.5) -> bool:
    parsed = urlparse(url)
    if not parsed.hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return socket_listening(parsed.hostname, port, timeout)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def row_unchanged(before, row: dict, ignore=None) -> bool:
    ignore = set(ignore or [])
    before_dict = dict(before)
    for key, value in row.items():
        if key in ignore:
            continue
        if key not in before_dict:
            continue
        if before_dict[key] != value:
            return False
    return True


def ensure_default_user(conn: sqlite3.Connection, user_id: str | None = None) -> None:
    if user_id != "usr_founder":
        return
    conn.execute(
        """INSERT OR IGNORE INTO users(user_id,name,email,role,created_at)
        VALUES(?,?,?,?,?)""",
        ("usr_founder", "Founder", "founder@example.local", "founder", now_iso()),
    )


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    body = handler.rfile.read(length)
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


def notion_config() -> dict:
    token = os.environ.get("NOTION_TOKEN", "").strip()
    parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID", "").strip()
    database_id = os.environ.get("NOTION_DATABASE_ID", "").strip()
    workspace_private_export = os.environ.get("NOTION_WORKSPACE_PRIVATE_EXPORT", "").strip().lower() in ("1", "true", "yes")
    export_mode = "page_parent" if parent_page_id else "database_parent" if database_id else "workspace_private" if workspace_private_export else "dry_run_only"
    return {
        "configured": bool(token and export_mode != "dry_run_only"),
        "has_token": bool(token),
        "parent_page_id": parent_page_id,
        "database_id": database_id,
        "workspace_private_export": workspace_private_export,
        "export_mode": export_mode,
        "notion_version": os.environ.get("NOTION_VERSION", "2022-06-28"),
    }


def text_blocks(markdown: str) -> list[dict]:
    blocks = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append(notion_rich_block("heading_1", line[2:]))
        elif line.startswith("## "):
            blocks.append(notion_rich_block("heading_2", line[3:]))
        elif line.startswith("### "):
            blocks.append(notion_rich_block("heading_3", line[4:]))
        elif line.startswith("- "):
            blocks.append(notion_rich_block("bulleted_list_item", line[2:]))
        elif line.startswith("```"):
            continue
        else:
            blocks.append(notion_rich_block("paragraph", line))
    return blocks[:90]


def notion_rich_block(kind: str, text: str) -> dict:
    return {
        "object": "block",
        "type": kind,
        kind: {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": text[:1900]},
                }
            ]
        },
    }


SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    description TEXT,
    runtime_type TEXT NOT NULL CHECK(runtime_type IN ('mock','claude_code','codex','openhands','crewai','langgraph','openclaw','hermes')),
    model_provider TEXT,
    model_name TEXT,
    status TEXT NOT NULL CHECK(status IN ('idle','running','paused','error','disabled')),
    permission_level TEXT NOT NULL,
    allowed_tools TEXT NOT NULL,
    budget_limit_usd REAL NOT NULL DEFAULT 0,
    owner_user_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(owner_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    title TEXT NOT NULL,
    description TEXT,
    requester_id TEXT,
    owner_agent_id TEXT,
    collaborator_agent_ids TEXT DEFAULT '[]',
    status TEXT NOT NULL CHECK(status IN ('backlog','planned','running','waiting_approval','blocked','completed','failed','canceled')),
    priority TEXT NOT NULL DEFAULT 'medium',
    due_date TEXT,
    acceptance_criteria TEXT,
    risk_level TEXT NOT NULL CHECK(risk_level IN ('low','medium','high','critical')),
    budget_limit_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(requester_id) REFERENCES users(user_id),
    FOREIGN KEY(owner_agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    runtime_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_ms INTEGER,
    input_summary TEXT,
    output_summary TEXT,
    model_provider TEXT,
    model_name TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    error_type TEXT,
    error_message TEXT,
    trace_id TEXT,
    parent_run_id TEXT,
    delegation_id TEXT,
    approval_required INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY(parent_run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT NOT NULL DEFAULT 'v1',
    tool_category TEXT NOT NULL CHECK(tool_category IN ('browser','github','file','shell','email','notion','discord','database','mcp','custom')),
    normalized_args_json TEXT NOT NULL DEFAULT '{}',
    target_resource TEXT,
    risk_level TEXT NOT NULL CHECK(risk_level IN ('low','medium','high','critical')),
    status TEXT NOT NULL,
    result_summary TEXT,
    side_effect_id TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(run_id),
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    tool_call_id TEXT,
    requested_by_agent_id TEXT,
    approver_user_id TEXT,
    decision TEXT NOT NULL CHECK(decision IN ('pending','approved','rejected','expired')),
    reason TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id),
    FOREIGN KEY(tool_call_id) REFERENCES tool_calls(tool_call_id),
    FOREIGN KEY(requested_by_agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY(approver_user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    scope TEXT NOT NULL CHECK(scope IN ('task','project','org')),
    memory_type TEXT NOT NULL CHECK(memory_type IN ('policy','sop','decision','commitment','risk','failure_case','project_context','customer_preference','agent_lesson','artifact_summary')),
    canonical_text TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('chat','email','meeting','github','notion','run_log','manual')),
    source_ref TEXT,
    project_id TEXT,
    task_id TEXT,
    agent_id TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    review_status TEXT NOT NULL CHECK(review_status IN ('candidate','approved','rejected','stale','superseded')),
    owner_user_id TEXT,
    ttl_review_due_at TEXT,
    supersedes_memory_id TEXT,
    access_tags TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY(owner_user_id) REFERENCES users(user_id),
    FOREIGN KEY(supersedes_memory_id) REFERENCES memories(memory_id)
);

CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    evaluator_type TEXT NOT NULL CHECK(evaluator_type IN ('human','rule','llm_mock')),
    score REAL NOT NULL,
    pass_fail TEXT NOT NULL CHECK(pass_fail IN ('pass','fail')),
    rubric_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id),
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    task_id TEXT,
    run_id TEXT,
    artifact_type TEXT NOT NULL,
    title TEXT NOT NULL,
    uri TEXT,
    summary TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    audit_id TEXT PRIMARY KEY,
    actor_type TEXT NOT NULL CHECK(actor_type IN ('user','agent','system')),
    actor_id TEXT,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    before_hash TEXT,
    after_hash TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    tamper_chain_hash TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_connectors (
    runtime_connector_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    profile_name TEXT,
    base_url TEXT,
    binary_path TEXT,
    status TEXT NOT NULL,
    allow_real_run INTEGER NOT NULL DEFAULT 0,
    require_confirm_run INTEGER NOT NULL DEFAULT 1,
    trust_status TEXT NOT NULL DEFAULT 'trusted',
    trust_note TEXT,
    trust_updated_at TEXT,
    last_health_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_events (
    runtime_event_id TEXT PRIMARY KEY,
    runtime_connector_id TEXT,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    run_id TEXT,
    task_id TEXT,
    agent_id TEXT,
    model_name TEXT,
    latency_ms INTEGER,
    prompt_hash TEXT,
    input_summary TEXT,
    output_summary TEXT,
    error_message TEXT,
    raw_payload_hash TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(runtime_connector_id) REFERENCES runtime_connectors(runtime_connector_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS workflow_jobs (
    job_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    workflow_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
    template_id TEXT,
    adapter TEXT,
    confirm_run INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    input_summary TEXT,
    request_hash TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
    result_task_id TEXT,
    result_run_id TEXT,
    result_artifact_id TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_gateway_tokens (
    token_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK(status IN ('active','revoked','expired')),
    label TEXT,
    heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    revoked_at TEXT,
    last_used_at TEXT,
    last_heartbeat_at TEXT,
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS agent_gateway_sessions (
    session_id TEXT PRIMARY KEY,
    session_hash TEXT NOT NULL UNIQUE,
    parent_token_id TEXT,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK(status IN ('active','revoked','expired')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    last_used_at TEXT,
    FOREIGN KEY(parent_token_id) REFERENCES agent_gateway_tokens(token_id),
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS agent_gateway_enrollment_requests (
    request_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT,
    runtime_type TEXT NOT NULL,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    reason TEXT,
    status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','issued')),
    token_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decided_at TEXT,
    FOREIGN KEY(approval_id) REFERENCES approvals(approval_id),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id),
    FOREIGN KEY(token_id) REFERENCES agent_gateway_tokens(token_id)
);

CREATE TABLE IF NOT EXISTS bases (
    base_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    category TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS base_capabilities (
    capability_id TEXT PRIMARY KEY,
    base_id TEXT NOT NULL,
    supports_tasks INTEGER DEFAULT 0,
    supports_comments INTEGER DEFAULT 0,
    supports_artifacts INTEGER DEFAULT 0,
    supports_metrics INTEGER DEFAULT 0,
    supports_webhooks INTEGER DEFAULT 0,
    supports_oauth INTEGER DEFAULT 0,
    supports_writeback INTEGER DEFAULT 0,
    supports_permissions INTEGER DEFAULT 0,
    supports_audit_export INTEGER DEFAULT 0,
    supports_realtime_sync INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(base_id) REFERENCES bases(base_id)
);

CREATE TABLE IF NOT EXISTS connectors (
    connector_id TEXT PRIMARY KEY,
    base_id TEXT,
    provider TEXT NOT NULL,
    auth_type TEXT NOT NULL,
    status TEXT NOT NULL,
    last_checked_at TEXT,
    last_error TEXT,
    dry_run_default INTEGER NOT NULL DEFAULT 1,
    writeback_allowed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(base_id) REFERENCES bases(base_id)
);

CREATE TABLE IF NOT EXISTS connector_scopes (
    scope_id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL,
    scope_name TEXT NOT NULL,
    granted INTEGER NOT NULL DEFAULT 0,
    required_for TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(connector_id) REFERENCES connectors(connector_id)
);

CREATE TABLE IF NOT EXISTS external_object_links (
    link_id TEXT PRIMARY KEY,
    internal_object_type TEXT NOT NULL,
    internal_object_id TEXT NOT NULL,
    external_provider TEXT NOT NULL,
    external_object_type TEXT NOT NULL,
    external_object_id TEXT,
    external_url TEXT,
    sync_direction TEXT NOT NULL,
    sync_status TEXT NOT NULL,
    last_synced_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_jobs (
    sync_job_id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(connector_id) REFERENCES connectors(connector_id)
);

CREATE TABLE IF NOT EXISTS sync_events (
    sync_event_id TEXT PRIMARY KEY,
    connector_id TEXT,
    direction TEXT NOT NULL,
    object_type TEXT NOT NULL,
    internal_object_id TEXT,
    external_object_id TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    payload_hash TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(connector_id) REFERENCES connectors(connector_id)
);

CREATE TABLE IF NOT EXISTS field_mappings (
    field_mapping_id TEXT PRIMARY KEY,
    base_id TEXT NOT NULL,
    internal_object_type TEXT NOT NULL,
    internal_field TEXT NOT NULL,
    external_field TEXT NOT NULL,
    transform_rule TEXT,
    required INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(base_id) REFERENCES bases(base_id)
);

CREATE TABLE IF NOT EXISTS template_packages (
    template_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    scenario TEXT NOT NULL,
    description TEXT,
    default_bases_json TEXT NOT NULL DEFAULT '{}',
    swappable_bases_json TEXT NOT NULL DEFAULT '{}',
    agent_roles_json TEXT NOT NULL DEFAULT '[]',
    task_schema_json TEXT NOT NULL DEFAULT '{}',
    memory_schema_json TEXT NOT NULL DEFAULT '{}',
    quality_gates_json TEXT NOT NULL DEFAULT '{}',
    approval_policy_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS template_bindings (
    binding_id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    base_id TEXT NOT NULL,
    workspace_id TEXT,
    status TEXT NOT NULL,
    mapping_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(template_id) REFERENCES template_packages(template_id),
    FOREIGN KEY(base_id) REFERENCES bases(base_id)
);

CREATE TABLE IF NOT EXISTS migration_runs (
    migration_run_id TEXT PRIMARY KEY,
    template_id TEXT,
    from_base_id TEXT,
    to_base_id TEXT,
    status TEXT NOT NULL,
    preview_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(template_id) REFERENCES template_packages(template_id),
    FOREIGN KEY(from_base_id) REFERENCES bases(base_id),
    FOREIGN KEY(to_base_id) REFERENCES bases(base_id)
);

CREATE TABLE IF NOT EXISTS agent_plans (
    plan_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    task_id TEXT,
    run_id TEXT,
    agent_id TEXT NOT NULL,
    task_understanding TEXT NOT NULL,
    referenced_specs_json TEXT NOT NULL DEFAULT '[]',
    referenced_memories_json TEXT NOT NULL DEFAULT '[]',
    referenced_bases_json TEXT NOT NULL DEFAULT '[]',
    proposed_files_to_change_json TEXT NOT NULL DEFAULT '[]',
    risk_level TEXT NOT NULL CHECK(risk_level IN ('low','medium','high','critical')),
    approval_required INTEGER NOT NULL DEFAULT 0,
    execution_steps_json TEXT NOT NULL DEFAULT '[]',
    verification_plan TEXT,
    rollback_plan TEXT,
    status TEXT NOT NULL CHECK(status IN ('draft','submitted','approved','rejected','superseded')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id),
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS plan_evidence_manifests (
    manifest_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    plan_id TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    mismatch_policy TEXT NOT NULL CHECK(mismatch_policy IN ('block','warn')),
    expected_steps_json TEXT NOT NULL DEFAULT '[]',
    tool_call_ids_json TEXT NOT NULL DEFAULT '[]',
    evaluation_ids_json TEXT NOT NULL DEFAULT '[]',
    artifact_ids_json TEXT NOT NULL DEFAULT '[]',
    audit_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL CHECK(status IN ('submitted','verified','warning','blocked')),
    verification_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES agent_plans(plan_id),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id),
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    doc_id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    scope TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    content_summary TEXT,
    indexed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner_agent_id);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON runs(agent_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_tool_calls_run ON tool_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_risk ON tool_calls(risk_level);
CREATE INDEX IF NOT EXISTS idx_approvals_decision ON approvals(decision);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(review_status);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope);
CREATE INDEX IF NOT EXISTS idx_memories_workspace ON memories(workspace_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_runtime_events_connector ON runtime_events(runtime_connector_id);
CREATE INDEX IF NOT EXISTS idx_agent_gateway_tokens_agent ON agent_gateway_tokens(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_gateway_tokens_status ON agent_gateway_tokens(status);
CREATE INDEX IF NOT EXISTS idx_connectors_base ON connectors(base_id);
CREATE INDEX IF NOT EXISTS idx_sync_events_connector ON sync_events(connector_id);
CREATE INDEX IF NOT EXISTS idx_external_links_internal ON external_object_links(internal_object_type, internal_object_id);
CREATE INDEX IF NOT EXISTS idx_agent_plans_task ON agent_plans(task_id);
CREATE INDEX IF NOT EXISTS idx_agent_plans_agent ON agent_plans(agent_id);
CREATE INDEX IF NOT EXISTS idx_plan_evidence_plan ON plan_evidence_manifests(plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_evidence_run ON plan_evidence_manifests(run_id);
CREATE INDEX IF NOT EXISTS idx_plan_evidence_agent ON plan_evidence_manifests(agent_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_category ON knowledge_documents(category);
"""


def repo_insert_audit_log(conn: sqlite3.Connection, row: dict, metadata: dict | None = None) -> dict:
    previous = conn.execute("SELECT tamper_chain_hash FROM audit_logs ORDER BY created_at DESC LIMIT 1").fetchone()
    previous_hash = previous[0] if previous else "genesis"
    payload = {
        "actor_type": row["actor_type"],
        "actor_id": row.get("actor_id"),
        "action": row["action"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "before_hash": row.get("before_hash"),
        "after_hash": row.get("after_hash"),
        "metadata_json": metadata or {},
        "previous": previous_hash,
    }
    row = {
        **row,
        "audit_id": row.get("audit_id") or new_id("aud"),
        "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
        "tamper_chain_hash": stable_hash(payload),
        "created_at": row.get("created_at") or now_iso(),
    }
    conn.execute(
        """
        INSERT INTO audit_logs(audit_id, actor_type, actor_id, action, entity_type, entity_id, before_hash, after_hash, metadata_json, tamper_chain_hash, created_at)
        VALUES(:audit_id,:actor_type,:actor_id,:action,:entity_type,:entity_id,:before_hash,:after_hash,:metadata_json,:tamper_chain_hash,:created_at)
        """,
        row,
    )
    return row


def audit(conn: sqlite3.Connection, actor_type: str, actor_id: str | None, action: str, entity_type: str, entity_id: str, before=None, after=None, metadata=None):
    repo_insert_audit_log(conn, {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before_hash": stable_hash(before) if before is not None else None,
        "after_hash": stable_hash(after) if after is not None else None,
    }, metadata or {})


def init_schema():
    with db() as conn:
        conn.executescript(SCHEMA_SQL)
        ensure_schema_migrations(conn)
        ensure_v121_reference_data(conn)
        conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str):
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def ensure_schema_migrations(conn: sqlite3.Connection):
    ensure_column(conn, "tasks", "workspace_id", "workspace_id TEXT NOT NULL DEFAULT 'local-demo'")
    ensure_column(conn, "runs", "workspace_id", "workspace_id TEXT NOT NULL DEFAULT 'local-demo'")
    ensure_column(conn, "memories", "workspace_id", "workspace_id TEXT NOT NULL DEFAULT 'local-demo'")
    ensure_column(conn, "runtime_connectors", "trust_status", "trust_status TEXT NOT NULL DEFAULT 'trusted'")
    ensure_column(conn, "runtime_connectors", "trust_note", "trust_note TEXT")
    ensure_column(conn, "runtime_connectors", "trust_updated_at", "trust_updated_at TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks(workspace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_workspace ON runs(workspace_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_workspace ON memories(workspace_id, updated_at)")
    conn.execute(
        """UPDATE memories
        SET workspace_id=(
            SELECT COALESCE(tasks.workspace_id,'local-demo') FROM tasks WHERE tasks.task_id=memories.task_id
        )
        WHERE task_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM tasks WHERE tasks.task_id=memories.task_id)
          AND COALESCE(workspace_id,'local-demo')='local-demo'"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_jobs_status ON workflow_jobs(status, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_plans_workspace ON agent_plans(workspace_id, created_at)")
    ensure_knowledge_fts(conn)


def ensure_knowledge_fts(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
            USING fts5(doc_id UNINDEXED, path UNINDEXED, title, content)"""
        )
        return True
    except sqlite3.OperationalError:
        return False


def ensure_v121_reference_data(conn: sqlite3.Connection):
    now = now_iso()
    bases = [
        ("base_local_tasks", "agent-mis", "task", "managed", "active", "Agent-MIS Local Task Base", "Canonical managed task base for demo and core ledger."),
        ("base_local_memory", "agent-mis", "memory", "managed", "active", "Agent-MIS Local Memory Base", "Canonical managed memory review base."),
        ("base_local_templates", "agent-mis", "template", "managed", "active", "Agent-MIS Local Template Base", "Canonical managed template package base."),
        ("base_notion_memory", "notion", "memory", "external", "dry_run", "Notion External Memory Base", "External Notion pages for reviewed memory and knowledge capture."),
        ("base_notion_tasks", "notion", "task", "external", "dry_run", "Notion External Task Base", "External Notion database/pages for task previews and writeback."),
        ("base_notion_templates", "notion", "template", "external", "dry_run", "Notion External Template Base", "External Notion pages for template presentation."),
        ("base_wandb_observability", "wandb", "observability", "external", "planned", "W&B External Observability Base", "Planned observability base for evals and experiments."),
        ("base_plane_tasks", "plane", "task", "external", "planned", "Plane External Task Base", "Planned issue/task base for software teams."),
        ("base_docmost_docs", "docmost", "memory", "external", "planned", "Docmost External Knowledge Base", "Planned open-source documentation base."),
        ("base_mattermost_ops", "mattermost", "communication", "external", "planned", "Mattermost External Ops Base", "Planned team communication base."),
        ("base_dify_knowledge", "dify", "knowledge", "external", "planned", "Dify Knowledge Base", "Planned low-code AI assistant base for document ingestion, workflows and chat apps."),
        ("base_openai_file_search", "openai", "knowledge", "external", "planned", "OpenAI File Search Base", "Planned developer API base for file retrieval, citations and assistant workflows."),
        ("base_anythingllm_knowledge", "anythingllm", "knowledge", "external", "planned", "AnythingLLM Knowledge Base", "Planned self-hosted knowledge base target for local/private document Q&A."),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO bases(base_id,provider,category,mode,status,display_name,description,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        [(base_id, provider, category, mode, status, name, desc, now, now) for base_id, provider, category, mode, status, name, desc in bases],
    )
    caps = {
        "base_local_tasks": dict(tasks=1, comments=1, artifacts=1, metrics=1, webhooks=0, oauth=0, writeback=1, permissions=1, audit=1, realtime=0, notes="Core task authority remains local."),
        "base_local_memory": dict(tasks=0, comments=1, artifacts=1, metrics=1, webhooks=0, oauth=0, writeback=1, permissions=1, audit=1, realtime=0, notes="Core memory review and TTL remain local."),
        "base_local_templates": dict(tasks=0, comments=0, artifacts=1, metrics=0, webhooks=0, oauth=0, writeback=1, permissions=1, audit=1, realtime=0, notes="Canonical template packages remain local."),
        "base_notion_memory": dict(tasks=0, comments=1, artifacts=1, metrics=0, webhooks=0, oauth=1, writeback=0, permissions=1, audit=0, realtime=0, notes="Notion is external memory presentation, not audit authority."),
        "base_notion_tasks": dict(tasks=1, comments=1, artifacts=1, metrics=0, webhooks=0, oauth=1, writeback=0, permissions=1, audit=0, realtime=0, notes="Notion task sync defaults to dry-run."),
        "base_notion_templates": dict(tasks=0, comments=1, artifacts=1, metrics=0, webhooks=0, oauth=1, writeback=0, permissions=1, audit=0, realtime=0, notes="Notion can present templates but core package stays local."),
        "base_dify_knowledge": dict(tasks=0, comments=0, artifacts=1, metrics=1, webhooks=1, oauth=1, writeback=0, permissions=1, audit=0, realtime=0, notes="Dify upload is an external write and requires approval before any real connector action."),
        "base_openai_file_search": dict(tasks=0, comments=0, artifacts=1, metrics=1, webhooks=0, oauth=1, writeback=0, permissions=1, audit=0, realtime=0, notes="OpenAI File Search upload is approval-gated; MIS stores summaries, hashes and audit evidence only."),
        "base_anythingllm_knowledge": dict(tasks=0, comments=0, artifacts=1, metrics=1, webhooks=1, oauth=0, writeback=0, permissions=1, audit=0, realtime=0, notes="AnythingLLM can be self-hosted; external ingestion remains approval-gated."),
    }
    for base_id, c in caps.items():
        conn.execute(
            """INSERT OR IGNORE INTO base_capabilities(capability_id,base_id,supports_tasks,supports_comments,supports_artifacts,supports_metrics,supports_webhooks,supports_oauth,supports_writeback,supports_permissions,supports_audit_export,supports_realtime_sync,notes,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (stable_id("cap", base_id), base_id, c["tasks"], c["comments"], c["artifacts"], c["metrics"], c["webhooks"], c["oauth"], c["writeback"], c["permissions"], c["audit"], c["realtime"], c["notes"], now),
        )
    connectors = [
        ("conn_notion_memory", "base_notion_memory", "notion", "token", "dry_run", None, None, 1, 0),
        ("conn_notion_tasks", "base_notion_tasks", "notion", "token", "dry_run", None, None, 1, 0),
        ("conn_notion_templates", "base_notion_templates", "notion", "token", "dry_run", None, None, 1, 0),
        ("conn_dify_knowledge", "base_dify_knowledge", "dify", "api_key", "planned", None, None, 1, 0),
        ("conn_openai_file_search", "base_openai_file_search", "openai", "api_key", "planned", None, None, 1, 0),
        ("conn_anythingllm_knowledge", "base_anythingllm_knowledge", "anythingllm", "local_token", "planned", None, None, 1, 0),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO connectors(connector_id,base_id,provider,auth_type,status,last_checked_at,last_error,dry_run_default,writeback_allowed,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        [(cid, bid, provider, auth_type, status, checked, err, dry, write, now, now) for cid, bid, provider, auth_type, status, checked, err, dry, write in connectors],
    )
    for connector_id in ["conn_notion_memory", "conn_notion_tasks", "conn_notion_templates"]:
        for scope_name, required_for in [("read_content", "preview/import-preview"), ("insert_content", "export-confirmed"), ("update_content", "future writeback")]:
            conn.execute(
                "INSERT OR IGNORE INTO connector_scopes(scope_id,connector_id,scope_name,granted,required_for,created_at) VALUES(?,?,?,?,?,?)",
                (stable_id("scope", connector_id, scope_name), connector_id, scope_name, 0, required_for, now),
            )
    for connector_id in ["conn_dify_knowledge", "conn_openai_file_search", "conn_anythingllm_knowledge"]:
        for scope_name, required_for in [("read_metadata", "status/probe"), ("upload_documents", "approval-gated ingestion"), ("query_documents", "future assistant retrieval")]:
            conn.execute(
                "INSERT OR IGNORE INTO connector_scopes(scope_id,connector_id,scope_name,granted,required_for,created_at) VALUES(?,?,?,?,?,?)",
                (stable_id("scope", connector_id, scope_name), connector_id, scope_name, 0, required_for, now),
            )
    for row in runtime_connector_rows():
        upsert_runtime_connector(conn, row)
    for template in default_template_packages():
        conn.execute(
            """INSERT OR IGNORE INTO template_packages(template_id,name,scenario,description,default_bases_json,swappable_bases_json,agent_roles_json,task_schema_json,memory_schema_json,quality_gates_json,approval_policy_json,created_at,updated_at)
            VALUES(:template_id,:name,:scenario,:description,:default_bases_json,:swappable_bases_json,:agent_roles_json,:task_schema_json,:memory_schema_json,:quality_gates_json,:approval_policy_json,:created_at,:updated_at)""",
            template,
        )
        for base_id in json.loads(template["default_bases_json"]).values():
            conn.execute(
                "INSERT OR IGNORE INTO template_bindings(binding_id,template_id,base_id,workspace_id,status,mapping_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (stable_id("bind", template["template_id"], base_id), template["template_id"], base_id, "local-demo", "active", json.dumps({"mode": "canonical"}, ensure_ascii=False), now),
            )


def hermes_runtime_config() -> dict:
    return {
        "gateway_url": os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642").strip(),
        "profile": os.environ.get("HERMES_PROFILE", "default").strip() or "default",
        "runtime_mode": os.environ.get("HERMES_RUNTIME_MODE", "health_only").strip() or "health_only",
        "allow_real_run": os.environ.get("HERMES_ALLOW_REAL_RUN", "").strip().lower() in ("1", "true", "yes"),
        "require_confirm_run": os.environ.get("HERMES_REQUIRE_CONFIRM_RUN", "true").strip().lower() not in ("0", "false", "no"),
    }


def agnesfallback_config() -> dict:
    extra_args = shlex.split(os.environ.get("AGNESFALLBACK_CLI_EXTRA_ARGS", "").strip())
    return {
        "binary_path": os.path.expanduser(os.environ.get("AGNESFALLBACK_BIN", "~/.local/bin/agnesfallback").strip()),
        "gateway_url": os.environ.get("AGNESFALLBACK_GATEWAY_URL", "http://127.0.0.1:8643").strip(),
        "profile": os.environ.get("AGNESFALLBACK_PROFILE", "agnesfallback").strip() or "agnesfallback",
        "extra_args": extra_args,
    }


def agnesfallback_cli_command(agnes: dict, prompt: str) -> list[str]:
    return [agnes["binary_path"], "-z", prompt, *agnes.get("extra_args", [])]


def runtime_connector_rows() -> list[dict]:
    now = now_iso()
    hermes = hermes_runtime_config()
    agnes = agnesfallback_config()
    return [
        {
            "runtime_connector_id": "rtc_agent_gateway_local",
            "provider": "agent-gateway",
            "connector_type": "local_cli_api_mcp",
            "profile_name": "local-demo",
            "base_url": "http://127.0.0.1:8787/api/agent-gateway",
            "binary_path": None,
            "status": "available",
            "allow_real_run": 1,
            "require_confirm_run": 1,
            "trust_status": "trusted",
            "trust_note": None,
            "trust_updated_at": now,
            "last_health_at": now,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
        {
            "runtime_connector_id": "rtc_openclaw_local",
            "provider": "openclaw",
            "connector_type": "local_cli",
            "profile_name": "main",
            "base_url": None,
            "binary_path": str(OPENCLAW_BIN),
            "status": "available" if OPENCLAW_BIN.exists() else "unavailable",
            "allow_real_run": 1,
            "require_confirm_run": 1,
            "trust_status": "trusted",
            "trust_note": None,
            "trust_updated_at": now,
            "last_health_at": now,
            "last_error": None if OPENCLAW_BIN.exists() else f"missing {OPENCLAW_BIN}",
            "created_at": now,
            "updated_at": now,
        },
        {
            "runtime_connector_id": "rtc_hermes_default_gateway",
            "provider": "hermes",
            "connector_type": "health_probe",
            "profile_name": hermes["profile"],
            "base_url": hermes["gateway_url"],
            "binary_path": None,
            "status": "unknown",
            "allow_real_run": 1 if hermes["allow_real_run"] else 0,
            "require_confirm_run": 1 if hermes["require_confirm_run"] else 0,
            "trust_status": "trusted",
            "trust_note": None,
            "trust_updated_at": now,
            "last_health_at": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
        {
            "runtime_connector_id": "rtc_agnesfallback_cli",
            "provider": "agnesfallback",
            "connector_type": "cli_probe",
            "profile_name": agnes["profile"],
            "base_url": None,
            "binary_path": agnes["binary_path"],
            "status": "available" if Path(agnes["binary_path"]).exists() else "unavailable",
            "allow_real_run": 1 if hermes["allow_real_run"] else 0,
            "require_confirm_run": 1 if hermes["require_confirm_run"] else 0,
            "trust_status": "trusted",
            "trust_note": None,
            "trust_updated_at": now,
            "last_health_at": None,
            "last_error": None if Path(agnes["binary_path"]).exists() else "AGNESFALLBACK_BIN not found.",
            "created_at": now,
            "updated_at": now,
        },
        {
            "runtime_connector_id": "rtc_agnesfallback_openai_api",
            "provider": "agnesfallback",
            "connector_type": "openai_compatible",
            "profile_name": agnes["profile"],
            "base_url": agnes["gateway_url"],
            "binary_path": None,
            "status": "unknown",
            "allow_real_run": 1 if hermes["allow_real_run"] else 0,
            "require_confirm_run": 1 if hermes["require_confirm_run"] else 0,
            "trust_status": "trusted",
            "trust_note": None,
            "trust_updated_at": now,
            "last_health_at": None,
            "last_error": None,
            "created_at": now,
            "updated_at": now,
        },
    ]


def upsert_runtime_connector(conn, row: dict):
    before = conn.execute("SELECT * FROM runtime_connectors WHERE runtime_connector_id=?", (row["runtime_connector_id"],)).fetchone()
    if before:
        conn.execute(
            """UPDATE runtime_connectors SET provider=:provider, connector_type=:connector_type, profile_name=:profile_name,
            base_url=:base_url, binary_path=:binary_path, status=:status, allow_real_run=:allow_real_run,
            require_confirm_run=:require_confirm_run, last_health_at=:last_health_at, last_error=:last_error,
            updated_at=:updated_at WHERE runtime_connector_id=:runtime_connector_id""",
            row,
        )
    else:
        conn.execute(
            """INSERT INTO runtime_connectors(runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,require_confirm_run,last_health_at,last_error,created_at,updated_at)
            VALUES(:runtime_connector_id,:provider,:connector_type,:profile_name,:base_url,:binary_path,:status,:allow_real_run,:require_confirm_run,:last_health_at,:last_error,:created_at,:updated_at)""",
            row,
        )


def runtime_connector_for_adapter(adapter: str) -> str | None:
    if adapter == "hermes":
        return "rtc_hermes_default_gateway"
    if adapter == "openclaw":
        return "rtc_openclaw_local"
    if adapter == "mock":
        return "rtc_agent_gateway_local"
    return None


def runtime_connector_trust(conn, connector_id: str | None, refresh: bool = True) -> dict | None:
    if not connector_id:
        return None
    if refresh:
        refresh_runtime_connectors(conn)
    row = conn.execute("SELECT * FROM runtime_connectors WHERE runtime_connector_id=?", (connector_id,)).fetchone()
    return dict(row) if row else None


def update_runtime_connector_trust(conn, connector_id: str, body: dict) -> tuple[dict, int]:
    refresh_runtime_connectors(conn)
    before = conn.execute("SELECT * FROM runtime_connectors WHERE runtime_connector_id=?", (connector_id,)).fetchone()
    if not before:
        return {"error": "not_found", "message": f"Runtime connector {connector_id} was not found."}, 404
    trust_status = coerce_choice(body.get("trust_status") or body.get("status"), {"trusted", "review_required", "blocked"}, "review_required")
    trust_note = redact_text(body.get("trust_note") or body.get("note") or f"Runtime connector marked {trust_status}.", 300)
    now = now_iso()
    conn.execute(
        """UPDATE runtime_connectors
        SET trust_status=?, trust_note=?, trust_updated_at=?, updated_at=?
        WHERE runtime_connector_id=?""",
        (trust_status, trust_note, now, now, connector_id),
    )
    after = conn.execute("SELECT * FROM runtime_connectors WHERE runtime_connector_id=?", (connector_id,)).fetchone()
    runtime_event(conn, connector_id, "runtime_connector.trust_update", trust_status, output_summary=trust_note)
    audit(conn, "user", "usr_founder", "runtime_connector.trust_update", "runtime_connectors", connector_id, dict(before), dict(after), {"trust_status": trust_status, "raw_secret_omitted": True})
    return {"connector": dict(after), "token_omitted": True}, 200


def repo_insert_runtime_event(conn: sqlite3.Connection, row: dict) -> dict:
    conn.execute(
        """INSERT INTO runtime_events(runtime_event_id,runtime_connector_id,event_type,status,run_id,task_id,agent_id,model_name,latency_ms,prompt_hash,input_summary,output_summary,error_message,raw_payload_hash,created_at)
        VALUES(:runtime_event_id,:runtime_connector_id,:event_type,:status,:run_id,:task_id,:agent_id,:model_name,:latency_ms,:prompt_hash,:input_summary,:output_summary,:error_message,:raw_payload_hash,:created_at)""",
        row,
    )
    return row


def runtime_event(conn, connector_id, event_type, status, **kwargs):
    row = {
        "runtime_event_id": new_id("rte"),
        "runtime_connector_id": connector_id,
        "event_type": event_type,
        "status": status,
        "run_id": kwargs.get("run_id"),
        "task_id": kwargs.get("task_id"),
        "agent_id": kwargs.get("agent_id"),
        "model_name": kwargs.get("model_name"),
        "latency_ms": kwargs.get("latency_ms"),
        "prompt_hash": kwargs.get("prompt_hash"),
        "input_summary": redact_text(kwargs.get("input_summary"), 200) if kwargs.get("input_summary") else None,
        "output_summary": redact_text(kwargs.get("output_summary"), 200) if kwargs.get("output_summary") else None,
        "error_message": redact_text(kwargs.get("error_message"), 200) if kwargs.get("error_message") else None,
        "raw_payload_hash": kwargs.get("raw_payload_hash"),
        "created_at": now_iso(),
    }
    return repo_insert_runtime_event(conn, row)


def default_template_packages() -> list[dict]:
    now = now_iso()
    def pack(template_id, name, scenario, description, roles, quality, approvals, swappable):
        return {
            "template_id": template_id,
            "name": name,
            "scenario": scenario,
            "description": description,
            "default_bases_json": json.dumps({"tasks": "base_local_tasks", "memory": "base_local_memory", "templates": "base_local_templates"}, ensure_ascii=False),
            "swappable_bases_json": json.dumps(swappable, ensure_ascii=False),
            "agent_roles_json": json.dumps(roles, ensure_ascii=False),
            "task_schema_json": json.dumps({"fields": ["goal", "owner_agent", "risk_level", "acceptance_criteria", "due_date", "artifact_ref"]}, ensure_ascii=False),
            "memory_schema_json": json.dumps({"types": ["decision", "sop", "failure_case", "risk", "artifact_summary"], "required": ["source_ref", "confidence", "review_status", "ttl_review_due_at"]}, ensure_ascii=False),
            "quality_gates_json": json.dumps(quality, ensure_ascii=False),
            "approval_policy_json": json.dumps(approvals, ensure_ascii=False),
            "created_at": now,
            "updated_at": now,
        }
    return [
        pack(
            "tpl_ai_software_team",
            "AI Software Team Template",
            "software_delivery",
            "CoS, Builder, Reviewer and Ops agents deliver code/docs with core ledger retained in Agent-MIS.",
            ["CoS", "Architect", "Builder", "QA Reviewer", "Release Ops"],
            {"required": ["tests_pass", "no_high_risk_without_approval", "audit_written"], "warn": ["duration_over_180s"]},
            {"high_risk_tools": ["shell.exec", "github.push", "database.write"], "confirm_real_runtime": True},
            {"tasks": ["Plane", "Notion"], "memory": ["Notion", "Docmost"], "observability": ["W&B", "Langfuse", "Helicone"], "communication": ["Mattermost"]},
        ),
        pack(
            "tpl_ai_experiment_evaluation",
            "AI Experiment Evaluation Template",
            "experiment_eval",
            "Run model/runtime experiments with repeatable evaluation, cost-quality tracking and audit.",
            ["Experiment Planner", "Runtime Runner", "Evaluator", "Report Writer"],
            {"required": ["dataset_defined", "eval_score_recorded", "cost_recorded"], "warn": ["unexplained_regression"]},
            {"real_runtime_probe": "confirm_run", "external_write": "confirm_export"},
            {"tasks": ["Notion"], "memory": ["Docmost"], "observability": ["W&B", "Langfuse", "AgentOps"]},
        ),
        pack(
            "tpl_content_studio",
            "Content Studio Template",
            "content_ops",
            "Plan, draft, review and publish content while retaining approvals and memory provenance.",
            ["Editor", "Researcher", "Writer", "Fact Checker", "Publisher"],
            {"required": ["source_links", "fact_check_pass", "human_publish_approval"], "warn": ["missing_style_memory"]},
            {"publish_actions": "human_approval", "external_posts": "confirm_export"},
            {"tasks": ["Notion", "Plane"], "memory": ["Notion", "Docmost"], "communication": ["Mattermost"]},
        ),
        pack(
            "tpl_ai_knowledge_base_bot",
            "AI Knowledge Base / Q&A Bot Template",
            "knowledge_base_bot",
            "Plan document cleaning, choose Dify/OpenAI File Search/AnythingLLM, design chunking, retrieval, citations, evaluation and approval-gated ingestion.",
            ["Project Planner", "Document Cleaner", "Knowledge Base Builder", "Q&A Evaluator", "Customer Report Writer"],
            {"required": ["source_inventory", "chunking_strategy", "citation_plan", "no_external_upload_without_approval", "evaluation_recorded"], "warn": ["missing_fallback_connector"]},
            {"document_upload": "human_approval", "external_vector_write": "human_approval", "connector_credentials": "never_store"},
            {"tasks": ["Notion", "Plane"], "memory": ["Notion", "Docmost"], "knowledge": ["Dify", "OpenAI File Search", "AnythingLLM"], "observability": ["Agent-MIS Local"]},
        ),
        pack(
            "tpl_one_person_company_ops",
            "One-Person Company Ops Template",
            "solo_company_ops",
            "Operate a small AI workforce with CoS, Research, Builder, QA and Ops roles.",
            ["Founder", "CoS", "Research", "Builder", "QA", "Ops"],
            {"required": ["weekly_review", "risk_scan", "memory_review"], "warn": ["approval_backlog", "cost_spike"]},
            {"critical_actions": "fail_closed", "new_connector": "manual_review"},
            {"tasks": ["Notion", "Plane"], "memory": ["Notion", "Docmost"], "observability": ["W&B", "Langfuse"], "communication": ["Mattermost"]},
        ),
    ]


def seed(reset=False):
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    init_schema()
    with db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        if count and not reset:
            return
        # clear in dependency order
        for table in ["audit_logs", "artifacts", "evaluations", "memories", "approvals", "tool_calls", "runs", "tasks", "agent_gateway_tokens", "agents", "users"]:
            conn.execute(f"DELETE FROM {table}")

        users = [
            ("usr_founder", "Founder", "founder@example.local", "founder", now_iso()),
            ("usr_ops", "Ops Reviewer", "ops@example.local", "reviewer", now_iso()),
            ("usr_admin", "Platform Admin", "admin@example.local", "admin", now_iso()),
            ("usr_customer_demo", "Customer Demo", "customer@example.local", "customer", now_iso()),
        ]
        conn.executemany("INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)", users)

        agents = [
            ("agt_cos", "CoS Agent", "Chief of Staff", "Clarifies intent, decomposes work, assigns tasks and coordinates approvals.", "mock", "openai", "gpt-5.5-pro", "idle", "manager", ["notion.read", "task.write", "approval.request", "memory.propose"], 20.0, "usr_founder"),
            ("agt_research", "Research Agent", "Researcher", "Searches GitHub, HN, docs and papers; produces sourced research briefs.", "mock", "anthropic", "claude-sonnet-4.5", "idle", "standard", ["browser.search", "github.read", "notion.read", "memory.propose"], 12.0, "usr_founder"),
            ("agt_builder", "Builder Agent", "Builder", "Creates code, docs and artifacts in a sandboxed mock runtime.", "mock", "openai", "gpt-5.5-codex", "idle", "elevated", ["file.write", "github.read", "shell.exec", "memory.propose"], 18.0, "usr_founder"),
            ("agt_qa", "QA Agent", "QA Reviewer", "Runs rule checks, identifies regressions, and scores outputs against rubrics.", "mock", "google", "gemini-3-pro", "idle", "standard", ["file.read", "github.read", "eval.run"], 8.0, "usr_ops"),
            ("agt_ops", "Ops Agent", "Operations", "Handles release checklists, incident notes, costs and routine ops work.", "mock", "openai", "gpt-5.5-mini", "idle", "restricted", ["notion.write", "discord.post", "email.draft", "cost.read"], 10.0, "usr_ops"),
        ]
        for a in agents:
            conn.execute(
                """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (*a[:9], json.dumps(a[9], ensure_ascii=False), a[10], a[11], now_iso(), now_iso()),
            )

        task_specs = [
            ("tsk_competitor", "竞品调研", "Research Agent-MIS / AI workforce control-plane competitors using GitHub, HN and docs.", "agt_research", "At least 10 competitors, sources, gaps and MVP implications.", "high", 6.0),
            ("tsk_prd", "生成 PRD", "Write PRD for AgentOps MIS MVP.", "agt_cos", "Includes problem, personas, requirements, non-goals and acceptance criteria.", "medium", 4.0),
            ("tsk_code", "写代码", "Implement mock runtime and dashboard prototype.", "agt_builder", "Local app runs without external API keys and exposes required API endpoints.", "high", 8.0),
            ("tsk_issue", "审查 GitHub issue", "Review issue patterns from OpenHands, CrewAI, Dify and Langflow.", "agt_research", "Summarize engineering risks and mitigation controls.", "medium", 3.5),
            ("tsk_meeting", "整理会议纪要", "Turn a mock meeting note into decisions and action items.", "agt_ops", "Extract decisions, commitments, owners, deadlines and evidence refs.", "low", 2.0),
            ("tsk_commitments", "抽取承诺", "Extract commitments from mock email and chat sources.", "agt_ops", "Create at least 3 memory candidates with TTL and owners.", "low", 2.0),
            ("tsk_cost", "成本分析", "Analyze agent costs and identify high-cost agents.", "agt_qa", "Dashboard includes total cost, average cost and top cost agents.", "medium", 2.5),
            ("tsk_risk", "风险扫描", "Scan tool calls and approvals for high-risk actions.", "agt_qa", "Flag high-risk calls without approvals and produce gate result.", "critical", 3.0),
            ("tsk_report", "生成报告", "Generate course-style MIS report outline and architecture diagrams.", "agt_cos", "Report includes planning, analysis, design, implementation and evaluation.", "medium", 5.0),
            ("tsk_release", "发布前 QA", "Run release readiness checks.", "agt_qa", "All tasks have acceptance criteria and high-risk approvals are resolved.", "high", 3.0),
        ]
        statuses = ["planned", "running", "waiting_approval", "completed", "blocked", "backlog"]
        for i, spec in enumerate(task_specs):
            conn.execute(
                """INSERT INTO tasks(task_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    spec[0], spec[1], spec[2], "usr_founder", spec[3], json.dumps(["agt_qa"] if i % 2 else ["agt_cos", "agt_qa"], ensure_ascii=False),
                    statuses[i % len(statuses)], ["low", "medium", "high"][i % 3],
                    (dt.date.today() + dt.timedelta(days=i + 2)).isoformat(), spec[4], spec[5], spec[6], now_iso(), now_iso()
                ),
            )

        tool_templates = [
            ("browser.search", "browser", "low"),
            ("github.read", "github", "low"),
            ("file.write", "file", "medium"),
            ("shell.exec", "shell", "high"),
            ("email.send", "email", "high"),
            ("notion.write", "notion", "medium"),
            ("database.write", "database", "critical"),
            ("discord.post", "discord", "medium"),
            ("mcp.invoke", "mcp", "high"),
        ]
        run_statuses = ["completed", "completed", "waiting_approval", "failed", "completed", "blocked"]
        run_ids = []
        random.seed(42)
        for i in range(30):
            task = task_specs[i % len(task_specs)]
            agent_id = task[3]
            run_id = f"run_seed_{i+1:02d}"
            run_ids.append(run_id)
            start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=random.randint(0, 12), hours=random.randint(0, 8))
            status = run_statuses[i % len(run_statuses)]
            ended = start + dt.timedelta(minutes=random.randint(2, 28)) if status in ("completed", "failed", "blocked") else None
            cost = round(random.uniform(0.08, 2.80), 3)
            error_type = "RuntimeError" if status == "failed" else None
            error_message = "Mock runtime hit simulated tool timeout." if status == "failed" else None
            approval_required = 1 if status in ("waiting_approval", "blocked") else 0
            conn.execute(
                """INSERT INTO runs(run_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, task[0], agent_id, "mock", status, start.isoformat(), ended.isoformat() if ended else None,
                    int((ended - start).total_seconds() * 1000) if ended else None,
                    f"Seed input for {task[1]}", f"Seed output summary for {task[1]}" if status == "completed" else None,
                    "mock-provider", "mock-model", random.randint(500, 2400), random.randint(300, 1600), random.randint(0, 900), cost,
                    error_type, error_message, f"trace_{i+1:02d}", None, f"del_seed_{i+1:02d}", approval_required, start.isoformat()
                ),
            )
            for j in range(1 if i < 20 else 2):
                tool_name, cat, risk = tool_templates[(i + j) % len(tool_templates)]
                tc_id = f"tc_seed_{i+1:02d}_{j+1}"
                conn.execute(
                    """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tc_id, run_id, agent_id, tool_name, "v1", cat,
                        json.dumps({"query": task[1], "dry_run": True}, ensure_ascii=False),
                        f"mock://{cat}/{task[0]}", risk,
                        "waiting_approval" if risk in ("high", "critical") and status == "waiting_approval" else "completed",
                        f"Mock {tool_name} result", f"se_seed_{i+1:02d}_{j+1}" if risk in ("high", "critical") else None,
                        start.isoformat(), (start + dt.timedelta(minutes=random.randint(1, 4))).isoformat(), start.isoformat()
                    ),
                )

        # approvals, at least 8
        pending_tool_calls = conn.execute("SELECT tool_call_id, run_id, agent_id FROM tool_calls WHERE risk_level IN ('high','critical') LIMIT 12").fetchall()
        for i, tc in enumerate(pending_tool_calls[:8]):
            run = conn.execute("SELECT task_id FROM runs WHERE run_id=?", (tc["run_id"],)).fetchone()
            decision = ["pending", "approved", "rejected", "pending"][i % 4]
            conn.execute(
                """INSERT INTO approvals(approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,decision,reason,expires_at,created_at,decided_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"ap_seed_{i+1:02d}", run["task_id"], tc["run_id"], tc["tool_call_id"], tc["agent_id"], "usr_founder", decision,
                    "Seed approval for high-risk tool call", (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat(),
                    now_iso(), now_iso() if decision != "pending" else None
                ),
            )

        memory_examples = [
            ("org", "sop", "All external claims in competitor research must include a URL and source type.", "manual", None, None, "agt_research", 0.92, "approved"),
            ("project", "decision", "MVP uses mock runtime first; real Claude Code/OpenHands adapters are phase 2.", "meeting", "mtg://planning/001", "tsk_prd", "agt_cos", 0.88, "approved"),
            ("task", "commitment", "QA Agent must block any high-risk tool call that lacks approval.", "run_log", "run_seed_03", "tsk_risk", "agt_qa", 0.84, "candidate"),
            ("org", "risk", "Hidden telemetry is not allowed; outbound telemetry must be documented and opt-in.", "github", "crewai-telemetry-issue", None, None, 0.86, "candidate"),
            ("project", "failure_case", "Self-hosted plugin marketplaces can fail with 404/500; cache plugin manifests locally for demos.", "github", "dify-plugin-404", "tsk_issue", "agt_research", 0.81, "candidate"),
            ("org", "policy", "Production agents may not hold broad long-lived tokens.", "manual", None, None, None, 0.91, "approved"),
            ("task", "artifact_summary", "Competitor matrix should cover task model, cost, memory, audit and approvals.", "run_log", "run_seed_01", "tsk_competitor", "agt_research", 0.78, "candidate"),
            ("project", "customer_preference", "Founder prefers GitHub/HN/community evidence over vendor-only docs.", "chat", "chat://pref/001", None, "agt_cos", 0.87, "approved"),
            ("org", "agent_lesson", "Research Agent must expand keywords and not only search exact product names.", "chat", "chat://lesson/search", None, "agt_research", 0.9, "candidate"),
            ("project", "project_context", "AgentOps MIS should be vendor-neutral and not replace execution runtimes.", "manual", None, "tsk_prd", "agt_cos", 0.95, "approved"),
        ]
        for i, m in enumerate(memory_examples):
            due = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30 + i)).isoformat()
            conn.execute(
                """INSERT INTO memories(memory_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f"mem_seed_{i+1:02d}", m[0], m[1], m[2], m[3], m[4], "proj_mvp", m[5], m[6], m[7], m[8], "usr_founder", due, None, json.dumps(["mvp", "agentops"], ensure_ascii=False), now_iso(), now_iso())
            )

        # evaluations, at least 10
        for i, run_id in enumerate(run_ids[:12]):
            run = conn.execute("SELECT task_id, agent_id, status, cost_usd, error_message FROM runs WHERE run_id=?", (run_id,)).fetchone()
            passed = "pass" if run["status"] == "completed" and not run["error_message"] else "fail"
            score = round(random.uniform(0.72, 0.98) if passed == "pass" else random.uniform(0.2, 0.65), 2)
            conn.execute(
                """INSERT INTO evaluations(evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (f"eval_seed_{i+1:02d}", run["task_id"], run_id, run["agent_id"], "rule", score, passed,
                 json.dumps({"acceptance_criteria": True, "budget": True, "high_risk_approval": passed == "pass", "error_free": passed == "pass"}, ensure_ascii=False),
                 "Seed rule evaluation", now_iso())
            )

        # artifacts
        for i, run_id in enumerate(run_ids[:10]):
            run = conn.execute("SELECT task_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
            conn.execute("INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,uri,summary,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (f"art_seed_{i+1:02d}", run["task_id"], run_id, "markdown", f"Artifact {i+1}", f"artifact://seed/{i+1}", "Seed artifact summary", now_iso()))

        # many audit logs
        for table, entity_col in [("agents", "agent_id"), ("tasks", "task_id"), ("runs", "run_id"), ("tool_calls", "tool_call_id"), ("memories", "memory_id"), ("approvals", "approval_id")]:
            for row in conn.execute(f"SELECT {entity_col} AS id FROM {table} LIMIT 12").fetchall():
                audit(conn, "system", "seed", "seed.create", table, row["id"], None, {"id": row["id"]}, {"seed": True})
        conn.commit()
    export_seed_artifacts()


def export_seed_artifacts():
    if os.environ.get("AGENTOPS_SKIP_SEED_EXPORTS") == "1":
        return
    ARTIFACTS_DIR.mkdir(exist_ok=True)
    with db() as conn:
        runs = rows_to_dicts(conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 30").fetchall())
        memories = rows_to_dicts(conn.execute("SELECT * FROM memories ORDER BY created_at DESC").fetchall())
    (ARTIFACTS_DIR / "sample_export_runs.json").write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
    (ARTIFACTS_DIR / "sample_export_memories.json").write_text(json.dumps(memories, ensure_ascii=False, indent=2), encoding="utf-8")


def complete_run(conn: sqlite3.Connection, run_id: str, actor_type="system", actor_id="mock-runtime"):
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        return False
    task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (run["task_id"],)).fetchone()
    pending = conn.execute("SELECT COUNT(*) FROM approvals WHERE run_id=? AND decision='pending'", (run_id,)).fetchone()[0]
    rejected = conn.execute("SELECT COUNT(*) FROM approvals WHERE run_id=? AND decision='rejected'", (run_id,)).fetchone()[0]
    if rejected:
        before = dict(run)
        conn.execute("UPDATE runs SET status='blocked', ended_at=?, duration_ms=?, error_type=?, error_message=? WHERE run_id=?",
                     (now_iso(), 1, "ApprovalRejected", "A required high-risk tool call was rejected.", run_id))
        conn.execute("UPDATE tasks SET status='blocked', updated_at=? WHERE task_id=?", (now_iso(), run["task_id"]))
        audit(conn, actor_type, actor_id, "run.blocked", "runs", run_id, before, {"status": "blocked"}, {})
        return False
    if pending:
        return False
    before = dict(run)
    ended = dt.datetime.now(dt.timezone.utc)
    started = dt.datetime.fromisoformat(run["started_at"])
    duration = int((ended - started).total_seconds() * 1000)
    input_tokens = run["input_tokens"] or random.randint(400, 1200)
    output_tokens = run["output_tokens"] or random.randint(300, 1100)
    reasoning_tokens = run["reasoning_tokens"] or random.randint(100, 800)
    cost = run["cost_usd"] or round((input_tokens * 0.00001) + (output_tokens * 0.00003) + (reasoning_tokens * 0.000015), 4)
    conn.execute(
        """UPDATE runs SET status='completed', ended_at=?, duration_ms=?, output_summary=?, input_tokens=?, output_tokens=?, reasoning_tokens=?, cost_usd=?, approval_required=0 WHERE run_id=?""",
        (ended.isoformat(), duration, f"Completed mock run for task {run['task_id']}; produced artifact and candidate memory.", input_tokens, output_tokens, reasoning_tokens, cost, run_id),
    )
    conn.execute("UPDATE tasks SET status='completed', updated_at=? WHERE task_id=?", (now_iso(), run["task_id"]))
    conn.execute("UPDATE agents SET status='idle', updated_at=? WHERE agent_id=?", (now_iso(), run["agent_id"]))
    artifact_row = {
        "artifact_id": new_id("art"),
        "task_id": run["task_id"],
        "run_id": run_id,
        "artifact_type": "markdown",
        "title": "Mock output artifact",
        "uri": f"artifact://{run_id}/output",
        "summary": "Generated by mock runtime",
        "created_at": now_iso(),
    }
    repo_upsert_artifact(conn, artifact_row)
    # evaluation
    run_after = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    evaluate_run(conn, run_after, task)
    # memory candidates
    for _ in range(random.randint(0, 2)):
        mem_id = new_id("mem")
        memory_row = {
            "memory_id": mem_id,
            "workspace_id": row_workspace(task) if task else row_workspace(run),
            "scope": random.choice(["task", "project"]),
            "memory_type": random.choice(["decision", "commitment", "agent_lesson", "artifact_summary"]),
            "canonical_text": f"Mock memory candidate from run {run_id}: preserve evidence, owner, TTL and review status.",
            "source_type": "run_log",
            "source_ref": run_id,
            "project_id": "proj_mvp",
            "task_id": run["task_id"],
            "agent_id": run["agent_id"],
            "confidence": round(random.uniform(0.66, 0.92), 2),
            "review_status": "candidate",
            "owner_user_id": "usr_founder",
            "ttl_review_due_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).isoformat(),
            "supersedes_memory_id": None,
            "access_tags": json.dumps(["mock", "review"], ensure_ascii=False),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        repo_upsert_memory_candidate(conn, memory_row)
        audit(conn, "agent", run["agent_id"], "memory.propose", "memories", mem_id, None, {"memory_id": mem_id}, {"run_id": run_id})
    audit(conn, actor_type, actor_id, "run.completed", "runs", run_id, before, dict(run_after), {})
    return True


def evaluate_run(conn: sqlite3.Connection, run, task):
    if not task:
        task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (run["task_id"],)).fetchone()
    rules = {
        "has_acceptance_criteria": bool(task["acceptance_criteria"]),
        "within_budget": (run["cost_usd"] or 0) <= (task["budget_limit_usd"] or 999999),
        "no_error": not run["error_message"],
        "high_risk_approved": True,
    }
    high_unapproved = conn.execute(
        """SELECT COUNT(*) FROM tool_calls tc LEFT JOIN approvals ap ON ap.tool_call_id=tc.tool_call_id AND ap.decision='approved'
        WHERE tc.run_id=? AND tc.risk_level IN ('high','critical') AND ap.approval_id IS NULL""",
        (run["run_id"],),
    ).fetchone()[0]
    rules["high_risk_approved"] = high_unapproved == 0
    passed = all(rules.values())
    score = round(sum(1 for v in rules.values() if v) / len(rules), 2)
    eval_id = new_id("eval")
    eval_row = {
        "evaluation_id": eval_id,
        "task_id": run["task_id"],
        "run_id": run["run_id"],
        "agent_id": run["agent_id"],
        "evaluator_type": "rule",
        "score": score,
        "pass_fail": "pass" if passed else "fail",
        "rubric_json": json.dumps(rules, ensure_ascii=False),
        "notes": "Rule-based mock evaluator",
        "created_at": now_iso(),
    }
    repo_upsert_evaluation(conn, eval_row)
    audit(conn, "system", "rule-evaluator", "evaluation.create", "evaluations", eval_id, None, {"score": score, "pass_fail": passed}, {"run_id": run["run_id"]})


def upsert_agent(conn, row: dict, actor_id="adapter-import") -> str:
    ensure_default_user(conn, row.get("owner_user_id"))
    before = conn.execute("SELECT * FROM agents WHERE agent_id=?", (row["agent_id"],)).fetchone()
    if before:
        if row_unchanged(before, row, {"created_at", "updated_at"}):
            return "unchanged"
        conn.execute(
            """UPDATE agents SET name=:name, role=:role, description=:description, runtime_type=:runtime_type,
            model_provider=:model_provider, model_name=:model_name, status=:status, permission_level=:permission_level,
            allowed_tools=:allowed_tools, budget_limit_usd=:budget_limit_usd, owner_user_id=:owner_user_id, updated_at=:updated_at
            WHERE agent_id=:agent_id""",
            row,
        )
        action = "agent.update"
    else:
        conn.execute(
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""",
            row,
        )
        action = "agent.create"
    audit(conn, "system", actor_id, action, "agents", row["agent_id"], dict(before) if before else None, row, {})
    return "updated" if before else "created"


def repo_upsert_task(conn: sqlite3.Connection, row: dict) -> tuple[sqlite3.Row | None, str]:
    ensure_default_user(conn, row.get("requester_id"))
    row.setdefault("workspace_id", "local-demo")
    before = conn.execute("SELECT * FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()
    if before:
        if row_unchanged(before, row, {"created_at", "updated_at"}):
            return before, "unchanged"
        conn.execute(
            """UPDATE tasks SET title=:title, description=:description, requester_id=:requester_id,
            owner_agent_id=:owner_agent_id, collaborator_agent_ids=:collaborator_agent_ids, status=:status,
            priority=:priority, due_date=:due_date, acceptance_criteria=:acceptance_criteria, risk_level=:risk_level,
            budget_limit_usd=:budget_limit_usd, workspace_id=:workspace_id, updated_at=:updated_at WHERE task_id=:task_id""",
            row,
        )
        return before, "updated"
    else:
        conn.execute(
            """INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
            VALUES(:task_id,:workspace_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)""",
            row,
        )
        return before, "created"


def upsert_task(conn, row: dict, actor_id="adapter-import") -> str:
    before, outcome = repo_upsert_task(conn, row)
    if outcome == "unchanged":
        return outcome
    action = "task.update" if before else "task.create"
    audit(conn, "system", actor_id, action, "tasks", row["task_id"], dict(before) if before else None, row, {})
    return outcome


def repo_upsert_run(conn: sqlite3.Connection, row: dict, allow_update: bool = True) -> tuple[sqlite3.Row | None, str]:
    if not row.get("workspace_id"):
        task = conn.execute("SELECT workspace_id FROM tasks WHERE task_id=?", (row.get("task_id"),)).fetchone()
        row["workspace_id"] = (task["workspace_id"] if task else None) or "local-demo"
    before = conn.execute("SELECT * FROM runs WHERE run_id=?", (row["run_id"],)).fetchone()
    if before:
        if not allow_update:
            return before, "unchanged"
        if row_unchanged(before, row, {"created_at"}):
            return before, "unchanged"
        conn.execute(
            """UPDATE runs SET task_id=:task_id, agent_id=:agent_id, runtime_type=:runtime_type, status=:status,
            started_at=:started_at, ended_at=:ended_at, duration_ms=:duration_ms, input_summary=:input_summary,
            output_summary=:output_summary, model_provider=:model_provider, model_name=:model_name,
            input_tokens=:input_tokens, output_tokens=:output_tokens, reasoning_tokens=:reasoning_tokens,
            cost_usd=:cost_usd, error_type=:error_type, error_message=:error_message, trace_id=:trace_id,
            parent_run_id=:parent_run_id, delegation_id=:delegation_id, approval_required=:approval_required,
            workspace_id=:workspace_id
            WHERE run_id=:run_id""",
            row,
        )
        return before, "updated"
    else:
        conn.execute(
            """INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
            VALUES(:run_id,:workspace_id,:task_id,:agent_id,:runtime_type,:status,:started_at,:ended_at,:duration_ms,:input_summary,:output_summary,:model_provider,:model_name,:input_tokens,:output_tokens,:reasoning_tokens,:cost_usd,:error_type,:error_message,:trace_id,:parent_run_id,:delegation_id,:approval_required,:created_at)""",
            row,
        )
        return before, "created"


def repo_upsert_tool_call(conn: sqlite3.Connection, row: dict, allow_update: bool = True) -> tuple[sqlite3.Row | None, str]:
    before = conn.execute("SELECT * FROM tool_calls WHERE tool_call_id=?", (row["tool_call_id"],)).fetchone()
    if before:
        if not allow_update or row_unchanged(before, row, {"created_at"}):
            return before, "unchanged"
        conn.execute(
            """UPDATE tool_calls SET run_id=:run_id, agent_id=:agent_id, tool_name=:tool_name, tool_version=:tool_version,
            tool_category=:tool_category, normalized_args_json=:normalized_args_json, target_resource=:target_resource,
            risk_level=:risk_level, status=:status, result_summary=:result_summary, side_effect_id=:side_effect_id,
            started_at=:started_at, ended_at=:ended_at WHERE tool_call_id=:tool_call_id""",
            row,
        )
        return before, "updated"
    conn.execute(
        """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
        VALUES(:tool_call_id,:run_id,:agent_id,:tool_name,:tool_version,:tool_category,:normalized_args_json,:target_resource,:risk_level,:status,:result_summary,:side_effect_id,:started_at,:ended_at,:created_at)""",
        row,
    )
    return before, "created"


def repo_upsert_approval(conn: sqlite3.Connection, row: dict, allow_update: bool = True) -> tuple[sqlite3.Row | None, str]:
    ensure_default_user(conn, row.get("approver_user_id"))
    before = conn.execute("SELECT * FROM approvals WHERE approval_id=?", (row["approval_id"],)).fetchone()
    if before:
        if not allow_update or row_unchanged(before, row, {"created_at"}):
            return before, "unchanged"
        conn.execute(
            """UPDATE approvals SET task_id=:task_id, run_id=:run_id, tool_call_id=:tool_call_id,
            requested_by_agent_id=:requested_by_agent_id, approver_user_id=:approver_user_id,
            decision=:decision, reason=:reason, expires_at=:expires_at, decided_at=:decided_at
            WHERE approval_id=:approval_id""",
            row,
        )
        return before, "updated"
    conn.execute(
        """INSERT INTO approvals(approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,decision,reason,expires_at,created_at,decided_at)
        VALUES(:approval_id,:task_id,:run_id,:tool_call_id,:requested_by_agent_id,:approver_user_id,:decision,:reason,:expires_at,:created_at,:decided_at)""",
        row,
    )
    return before, "created"


def repo_upsert_evaluation(conn: sqlite3.Connection, row: dict, allow_update: bool = True) -> tuple[sqlite3.Row | None, str]:
    before = conn.execute("SELECT * FROM evaluations WHERE evaluation_id=?", (row["evaluation_id"],)).fetchone()
    if before:
        if not allow_update or row_unchanged(before, row, {"created_at"}):
            return before, "unchanged"
        conn.execute(
            """UPDATE evaluations SET task_id=:task_id, run_id=:run_id, agent_id=:agent_id, evaluator_type=:evaluator_type,
            score=:score, pass_fail=:pass_fail, rubric_json=:rubric_json, notes=:notes WHERE evaluation_id=:evaluation_id""",
            row,
        )
        return before, "updated"
    conn.execute(
        """INSERT INTO evaluations(evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at)
        VALUES(:evaluation_id,:task_id,:run_id,:agent_id,:evaluator_type,:score,:pass_fail,:rubric_json,:notes,:created_at)""",
        row,
    )
    return before, "created"


def repo_upsert_memory_candidate(conn: sqlite3.Connection, row: dict, allow_update: bool = True) -> tuple[sqlite3.Row | None, str]:
    ensure_default_user(conn, row.get("owner_user_id"))
    if not row.get("workspace_id"):
        workspace_id = "local-demo"
        if row.get("task_id"):
            task = conn.execute("SELECT workspace_id FROM tasks WHERE task_id=?", (row.get("task_id"),)).fetchone()
            workspace_id = row_workspace(task) if task else workspace_id
        row["workspace_id"] = workspace_id
    else:
        row["workspace_id"] = normalize_workspace_id(row.get("workspace_id"))
    before = conn.execute("SELECT * FROM memories WHERE memory_id=?", (row["memory_id"],)).fetchone()
    if before:
        if not allow_update or row_unchanged(before, row, {"created_at", "updated_at", "ttl_review_due_at"}):
            return before, "unchanged"
        conn.execute(
            """UPDATE memories SET workspace_id=:workspace_id, scope=:scope, memory_type=:memory_type, canonical_text=:canonical_text,
            source_type=:source_type, source_ref=:source_ref, project_id=:project_id, task_id=:task_id,
            agent_id=:agent_id, confidence=:confidence, review_status=:review_status, owner_user_id=:owner_user_id,
            ttl_review_due_at=:ttl_review_due_at, supersedes_memory_id=:supersedes_memory_id,
            access_tags=:access_tags, updated_at=:updated_at WHERE memory_id=:memory_id""",
            row,
        )
        return before, "updated"
    conn.execute(
        """INSERT INTO memories(memory_id,workspace_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
        VALUES(:memory_id,:workspace_id,:scope,:memory_type,:canonical_text,:source_type,:source_ref,:project_id,:task_id,:agent_id,:confidence,:review_status,:owner_user_id,:ttl_review_due_at,:supersedes_memory_id,:access_tags,:created_at,:updated_at)""",
        row,
    )
    return before, "created"


def repo_upsert_artifact(conn: sqlite3.Connection, row: dict, allow_update: bool = True) -> tuple[sqlite3.Row | None, str]:
    before = conn.execute("SELECT * FROM artifacts WHERE artifact_id=?", (row["artifact_id"],)).fetchone()
    if before:
        if not allow_update or row_unchanged(before, row, {"created_at"}):
            return before, "unchanged"
        conn.execute(
            """UPDATE artifacts SET task_id=:task_id, run_id=:run_id, artifact_type=:artifact_type,
            title=:title, uri=:uri, summary=:summary WHERE artifact_id=:artifact_id""",
            row,
        )
        return before, "updated"
    conn.execute(
        """INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,uri,summary,created_at)
        VALUES(:artifact_id,:task_id,:run_id,:artifact_type,:title,:uri,:summary,:created_at)""",
        row,
    )
    return before, "created"


def upsert_run(conn, row: dict, actor_id="adapter-import", audit_metadata=None) -> str:
    before, outcome = repo_upsert_run(conn, row, allow_update=actor_id != "openclaw-import")
    if outcome == "unchanged":
        return outcome
    action = "run.update" if before else "run.create"
    audit(conn, "system", actor_id, action, "runs", row["run_id"], dict(before) if before else None, row, audit_metadata or {})
    return outcome


def upsert_tool_call(conn, row: dict, actor_id="adapter-import", audit_metadata=None) -> str:
    before, outcome = repo_upsert_tool_call(conn, row, allow_update=actor_id != "openclaw-import")
    if outcome == "unchanged":
        return outcome
    action = "tool_call.update" if before else "tool_call.create"
    audit(conn, "system", actor_id, action, "tool_calls", row["tool_call_id"], dict(before) if before else None, row, audit_metadata or {})
    return outcome


def upsert_evaluation(conn, row: dict, actor_id="adapter-import") -> str:
    before, outcome = repo_upsert_evaluation(conn, row, allow_update=actor_id != "openclaw-import")
    if outcome == "unchanged":
        return outcome
    action = "evaluation.update" if before else "evaluation.create"
    audit(conn, "system", actor_id, action, "evaluations", row["evaluation_id"], dict(before) if before else None, row, {})
    return outcome


def upsert_memory_candidate(conn, row: dict, actor_id="adapter-import") -> str:
    before, outcome = repo_upsert_memory_candidate(conn, row, allow_update=actor_id != "openclaw-import")
    if outcome == "unchanged":
        return outcome
    action = "memory.update" if before else "memory.propose"
    audit(conn, "system", actor_id, action, "memories", row["memory_id"], dict(before) if before else None, row, {})
    return outcome


def openclaw_status() -> dict:
    config = read_json_file(OPENCLAW_HOME / "openclaw.json", {})
    jobs = read_json_file(OPENCLAW_HOME / "cron" / "jobs.json", {}).get("jobs", [])
    subagents = read_json_file(OPENCLAW_HOME / "subagents" / "runs.json", {})
    agents = config.get("agents", {}).get("list", []) if isinstance(config, dict) else []
    run_files = list((OPENCLAW_HOME / "cron" / "runs").glob("*.jsonl")) if (OPENCLAW_HOME / "cron" / "runs").exists() else []
    return {
        "provider": "openclaw",
        "home": str(OPENCLAW_HOME),
        "config_exists": (OPENCLAW_HOME / "openclaw.json").exists(),
        "cli_exists": OPENCLAW_BIN.exists(),
        "agents_count": len(agents) if isinstance(agents, list) else 0,
        "cron_jobs_count": len(jobs),
        "enabled_cron_jobs_count": sum(1 for job in jobs if job.get("enabled")),
        "cron_run_files_count": len(run_files),
        "subagent_runs_count": len(subagents.get("runs", {})) if isinstance(subagents, dict) else 0,
    }


def import_openclaw(conn) -> dict:
    created = {"agents": 0, "tasks": 0, "runs": 0, "tool_calls": 0, "evaluations": 0, "memories": 0}
    updated = {key: 0 for key in created}
    cfg = read_json_file(OPENCLAW_HOME / "openclaw.json", {})
    jobs_doc = read_json_file(OPENCLAW_HOME / "cron" / "jobs.json", {})
    agents = cfg.get("agents", {}).get("list", []) if isinstance(cfg, dict) else []
    defaults = cfg.get("agents", {}).get("defaults", {}) if isinstance(cfg, dict) else {}
    default_model = defaults.get("model", {}).get("primary") if isinstance(defaults.get("model"), dict) else defaults.get("model")

    agent_ids = set()
    for agent in agents if isinstance(agents, list) else []:
        source_id = agent.get("id") or agent.get("name") or "main"
        agent_id = stable_id("agt_oc", source_id)
        provider, model_name = split_provider_model(agent.get("model") or default_model, "openclaw")
        row = {
            "agent_id": agent_id,
            "name": f"OpenClaw {source_id}",
            "role": agent.get("role") or "OpenClaw Agent",
            "description": f"Imported OpenClaw agent metadata from {OPENCLAW_HOME / 'openclaw.json'}",
            "runtime_type": "openclaw",
            "model_provider": provider,
            "model_name": model_name,
            "status": "idle",
            "permission_level": "manager" if source_id == "main" else "standard",
            "allowed_tools": json.dumps(["openclaw.agent", "cron.read", "run_log.read"], ensure_ascii=False),
            "budget_limit_usd": 10.0,
            "owner_user_id": "usr_founder",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        outcome = upsert_agent(conn, row, "openclaw-import")
        created["agents"] += 1 if outcome == "created" else 0
        updated["agents"] += 1 if outcome == "updated" else 0
        agent_ids.add(source_id)

    if not agent_ids:
        row = {
            "agent_id": "agt_oc_main",
            "name": "OpenClaw main",
            "role": "OpenClaw Agent",
            "description": "Fallback OpenClaw main agent imported from local metadata.",
            "runtime_type": "openclaw",
            "model_provider": split_provider_model(default_model, "openclaw")[0],
            "model_name": split_provider_model(default_model, "openclaw")[1],
            "status": "idle",
            "permission_level": "manager",
            "allowed_tools": json.dumps(["openclaw.agent", "cron.read", "run_log.read"], ensure_ascii=False),
            "budget_limit_usd": 10.0,
            "owner_user_id": "usr_founder",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        outcome = upsert_agent(conn, row, "openclaw-import")
        created["agents"] += 1 if outcome == "created" else 0
        updated["agents"] += 1 if outcome == "updated" else 0

    jobs = jobs_doc.get("jobs", []) if isinstance(jobs_doc, dict) else []
    for job in jobs:
        job_id = job.get("id") or stable_hash(job)[:12]
        source_agent_id = job.get("agentId") or "main"
        owner_agent_id = stable_id("agt_oc", source_agent_id)
        if not conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (owner_agent_id,)).fetchone():
            provider, model_name = split_provider_model((job.get("payload") or {}).get("model") or default_model, "openclaw")
            upsert_agent(conn, {
                "agent_id": owner_agent_id,
                "name": f"OpenClaw {source_agent_id}",
                "role": "OpenClaw Agent",
                "description": "OpenClaw agent inferred from cron job metadata.",
                "runtime_type": "openclaw",
                "model_provider": provider,
                "model_name": model_name,
                "status": "idle",
                "permission_level": "standard",
                "allowed_tools": json.dumps(["openclaw.agent", "cron.read", "run_log.read"], ensure_ascii=False),
                "budget_limit_usd": 10.0,
                "owner_user_id": "usr_founder",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }, "openclaw-import")
        payload = job.get("payload") or {}
        schedule = job.get("schedule") or {}
        row = {
            "task_id": stable_id("tsk_oc_cron", job_id),
            "title": f"OpenClaw cron: {job.get('name') or job_id}",
            "description": redact_text(job.get("description") or payload.get("message") or "Imported OpenClaw cron job.", 200),
            "requester_id": "usr_founder",
            "owner_agent_id": owner_agent_id,
            "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
            "status": "planned" if job.get("enabled") else "backlog",
            "priority": "medium",
            "due_date": None,
            "acceptance_criteria": f"Schedule {schedule.get('kind', 'unknown')} {schedule.get('expr', '')} in {schedule.get('tz', '')}; imported as managed AgentOps MIS task.",
            "risk_level": "medium",
            "budget_limit_usd": 2.0,
            "created_at": iso_from_ms(job.get("createdAtMs")),
            "updated_at": now_iso(),
        }
        outcome = upsert_task(conn, row, "openclaw-import")
        created["tasks"] += 1 if outcome == "created" else 0
        updated["tasks"] += 1 if outcome == "updated" else 0

    run_files = sorted((OPENCLAW_HOME / "cron" / "runs").glob("*.jsonl")) if (OPENCLAW_HOME / "cron" / "runs").exists() else []
    job_by_id = {job.get("id"): job for job in jobs}
    for path in run_files:
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("action") not in (None, "finished"):
                continue
            job_id = event.get("jobId") or path.stem
            job = job_by_id.get(job_id, {})
            source_agent_id = job.get("agentId") or "main"
            agent_id = stable_id("agt_oc", source_agent_id)
            task_id = stable_id("tsk_oc_cron", job_id)
            if not conn.execute("SELECT 1 FROM tasks WHERE task_id=?", (task_id,)).fetchone():
                upsert_task(conn, {
                    "task_id": task_id,
                    "title": f"OpenClaw cron: {job_id}",
                    "description": "OpenClaw cron task inferred from run log.",
                    "requester_id": "usr_founder",
                    "owner_agent_id": agent_id if conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (agent_id,)).fetchone() else "agt_oc_main",
                    "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
                    "status": "planned",
                    "priority": "medium",
                    "due_date": None,
                    "acceptance_criteria": "Imported from OpenClaw cron run log.",
                    "risk_level": "medium",
                    "budget_limit_usd": 2.0,
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                }, "openclaw-import")
            if not conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (agent_id,)).fetchone():
                agent_id = "agt_oc_main"
            sid = event.get("sessionId") or event.get("runId") or event.get("ts") or line_no
            run_id = stable_id("run_oc_cron", job_id, sid)
            provider = event.get("provider") or split_provider_model(event.get("model"), "openclaw")[0]
            model_name = event.get("model") or split_provider_model(job.get("payload", {}).get("model"), "openclaw")[1]
            usage = event.get("usage") or {}
            summary_hash = stable_hash(event.get("summary") or "")
            output_summary = redact_text(event.get("summary"), 200) if event.get("summary") else None
            error_message = redact_text(event.get("error"), 200) if event.get("error") else None
            status = "completed" if event.get("status") == "ok" else "failed" if event.get("status") == "error" else "completed"
            started_at = iso_from_ms(event.get("runAtMs") or event.get("ts"))
            ended_at = iso_from_ms(event.get("ts")) if event.get("ts") else started_at
            duration_ms = parse_ms(event.get("durationMs"))
            row = {
                "run_id": run_id,
                "task_id": task_id,
                "agent_id": agent_id,
                "runtime_type": "openclaw",
                "status": status,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_ms": duration_ms,
                "input_summary": f"OpenClaw cron run for job {job_id}",
                "output_summary": output_summary,
                "model_provider": provider or "openclaw",
                "model_name": model_name or "unknown",
                "input_tokens": int(usage.get("input_tokens") or usage.get("input") or 0),
                "output_tokens": int(usage.get("output_tokens") or usage.get("output") or 0),
                "reasoning_tokens": int(usage.get("reasoning_tokens") or 0),
                "cost_usd": 0.0,
                "error_type": "OpenClawCronError" if status == "failed" else None,
                "error_message": error_message,
                "trace_id": event.get("sessionId") or event.get("runId"),
                "parent_run_id": None,
                "delegation_id": event.get("sessionKey"),
                "approval_required": 0,
                "created_at": started_at,
            }
            outcome = upsert_run(conn, row, "openclaw-import", {"source_path": str(path), "line": line_no, "job_id": job_id, "summary_hash": summary_hash})
            created["runs"] += 1 if outcome == "created" else 0
            updated["runs"] += 1 if outcome == "updated" else 0
            tc_row = {
                "tool_call_id": stable_id("tc_oc_cron", run_id),
                "run_id": run_id,
                "agent_id": agent_id,
                "tool_name": "openclaw.cron.run",
                "tool_version": "v1",
                "tool_category": "custom",
                "normalized_args_json": json.dumps({
                    "job_id": job_id,
                    "action": event.get("action"),
                    "delivery_status": event.get("deliveryStatus"),
                    "delivered": event.get("delivered"),
                    "summary_hash": summary_hash,
                    "source_path": str(path),
                }, ensure_ascii=False),
                "target_resource": f"openclaw://cron/{job_id}",
                "risk_level": "medium" if status == "failed" else "low",
                "status": status,
                "result_summary": output_summary or error_message or status,
                "side_effect_id": stable_hash({"job_id": job_id, "session": sid})[:16],
                "started_at": started_at,
                "ended_at": ended_at,
                "created_at": started_at,
            }
            outcome = upsert_tool_call(conn, tc_row, "openclaw-import", {"summary_hash": summary_hash})
            created["tool_calls"] += 1 if outcome == "created" else 0
            updated["tool_calls"] += 1 if outcome == "updated" else 0
            eval_row = quality_gate_for_run(row)
            outcome = upsert_evaluation(conn, eval_row, "openclaw-import")
            created["evaluations"] += 1 if outcome == "created" else 0
            updated["evaluations"] += 1 if outcome == "updated" else 0

            if status == "failed":
                mem_id = stable_id("mem_oc_failure", job_id, sid)
                mem_row = memory_candidate_row(
                    mem_id,
                    "risk",
                    f"OpenClaw cron job {job.get('name') or job_id} failed: {error_message or 'unknown error'}",
                    task_id,
                    agent_id,
                    run_id,
                    confidence=0.72,
                )
                outcome = upsert_memory_candidate(conn, mem_row, "openclaw-import")
                created["memories"] += 1 if outcome == "created" else 0
                updated["memories"] += 1 if outcome == "updated" else 0

    import_subagent_runs(conn, created, updated)
    audit(conn, "system", "openclaw-import", "openclaw.import.complete", "integrations", "openclaw", None, {"created": created, "updated": updated}, openclaw_status())
    return {"provider": "openclaw", "created": created, "updated": updated, "status": openclaw_status()}


def import_subagent_runs(conn, created: dict, updated: dict):
    doc = read_json_file(OPENCLAW_HOME / "subagents" / "runs.json", {})
    runs = doc.get("runs", {}) if isinstance(doc, dict) else {}
    if isinstance(runs, dict):
        items = runs.values()
    elif isinstance(runs, list):
        items = runs
    else:
        items = []
    for event in items:
        if not isinstance(event, dict):
            continue
        agent_id = stable_id("agt_oc", event.get("agentId") or event.get("agent_id") or "subagent")
        if not conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (agent_id,)).fetchone():
            outcome = upsert_agent(conn, {
                "agent_id": agent_id,
                "name": f"OpenClaw {event.get('agentId') or 'subagent'}",
                "role": "OpenClaw Subagent",
                "description": "Imported OpenClaw subagent metadata.",
                "runtime_type": "openclaw",
                "model_provider": event.get("provider") or "openclaw",
                "model_name": event.get("model") or "unknown",
                "status": "idle",
                "permission_level": "standard",
                "allowed_tools": json.dumps(["subagents.read", "run_log.read"], ensure_ascii=False),
                "budget_limit_usd": 8.0,
                "owner_user_id": "usr_founder",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }, "openclaw-import")
            created["agents"] += 1 if outcome == "created" else 0
            updated["agents"] += 1 if outcome == "updated" else 0
        task_id = stable_id("tsk_oc_subagent", event.get("taskId") or event.get("runId") or event.get("id") or "subagent")
        outcome = upsert_task(conn, {
            "task_id": task_id,
            "title": f"OpenClaw subagent run {event.get('name') or event.get('runId') or event.get('id') or ''}".strip(),
            "description": redact_text(event.get("summary") or "Imported OpenClaw subagent run.", 200),
            "requester_id": "usr_founder",
            "owner_agent_id": agent_id,
            "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
            "status": "completed" if event.get("status") in ("ok", "completed") else "failed" if event.get("status") == "error" else "planned",
            "priority": "medium",
            "due_date": None,
            "acceptance_criteria": "Imported from OpenClaw subagent run index.",
            "risk_level": "medium",
            "budget_limit_usd": 2.0,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }, "openclaw-import")
        created["tasks"] += 1 if outcome == "created" else 0
        updated["tasks"] += 1 if outcome == "updated" else 0
        run_id = stable_id("run_oc_subagent", event.get("runId") or event.get("id") or event.get("startedAt") or task_id)
        summary = event.get("summary") or event.get("result") or ""
        row = {
            "run_id": run_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "runtime_type": "openclaw",
            "status": "completed" if event.get("status") in ("ok", "completed") else "failed" if event.get("status") in ("error", "failed") else "completed",
            "started_at": event.get("startedAt") or now_iso(),
            "ended_at": event.get("endedAt") or now_iso(),
            "duration_ms": parse_ms(event.get("durationMs")),
            "input_summary": "OpenClaw subagent run imported from local index.",
            "output_summary": redact_text(summary, 200) if summary else None,
            "model_provider": event.get("provider") or split_provider_model(event.get("model"), "openclaw")[0],
            "model_name": event.get("model") or "unknown",
            "input_tokens": int((event.get("usage") or {}).get("input_tokens") or 0),
            "output_tokens": int((event.get("usage") or {}).get("output_tokens") or 0),
            "reasoning_tokens": int((event.get("usage") or {}).get("reasoning_tokens") or 0),
            "cost_usd": 0.0,
            "error_type": event.get("errorType"),
            "error_message": redact_text(event.get("error"), 200) if event.get("error") else None,
            "trace_id": event.get("traceId") or event.get("runId"),
            "parent_run_id": event.get("parentRunId"),
            "delegation_id": event.get("delegationId"),
            "approval_required": 1 if event.get("approvalRequired") else 0,
            "created_at": event.get("startedAt") or now_iso(),
        }
        outcome = upsert_run(conn, row, "openclaw-import", {"source_path": str(OPENCLAW_HOME / "subagents" / "runs.json"), "summary_hash": stable_hash(summary)})
        created["runs"] += 1 if outcome == "created" else 0
        updated["runs"] += 1 if outcome == "updated" else 0
        outcome = upsert_evaluation(conn, quality_gate_for_run(row), "openclaw-import")
        created["evaluations"] += 1 if outcome == "created" else 0
        updated["evaluations"] += 1 if outcome == "updated" else 0


def quality_gate_for_run(run: dict) -> dict:
    duration = run.get("duration_ms") or 0
    error = (run.get("error_message") or "") + " " + (run.get("error_type") or "")
    failed = run.get("status") in ("failed", "blocked", "error") or bool(re.search(r"timeout|model_not_found|unknown model|failed", error, re.I))
    over_duration = duration > 180000
    passed = not failed and not over_duration and run.get("status") == "completed"
    rules = {
        "completed": run.get("status") == "completed",
        "no_critical_error": not failed,
        "duration_under_180s": not over_duration,
        "approval_ok": not bool(run.get("approval_required")),
    }
    score = round(sum(1 for value in rules.values() if value) / len(rules), 2)
    return {
        "evaluation_id": stable_id("eval_gate", run["run_id"]),
        "task_id": run["task_id"],
        "run_id": run["run_id"],
        "agent_id": run["agent_id"],
        "evaluator_type": "rule",
        "score": score,
        "pass_fail": "pass" if passed else "fail",
        "rubric_json": json.dumps(rules, ensure_ascii=False),
        "notes": "Runtime quality gate: pass requires completed, no critical error, duration <= 180s.",
        "created_at": now_iso(),
    }


def memory_candidate_row(memory_id, memory_type, text, task_id, agent_id, source_ref, confidence=0.7):
    return {
        "memory_id": memory_id,
        "scope": "project",
        "memory_type": memory_type,
        "canonical_text": redact_text(text, 360),
        "source_type": "run_log",
        "source_ref": source_ref,
        "project_id": "proj_mvp",
        "task_id": task_id,
        "agent_id": agent_id,
        "confidence": confidence,
        "review_status": "candidate",
        "owner_user_id": "usr_founder",
        "ttl_review_due_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).isoformat(),
        "supersedes_memory_id": None,
        "access_tags": json.dumps(["openclaw", "runtime", "review"], ensure_ascii=False),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def coerce_choice(value, allowed: set[str], fallback: str) -> str:
    value = str(value or "").strip()
    return value if value in allowed else fallback


def safe_json_metadata(value):
    if isinstance(value, dict):
        return {str(k)[:80]: safe_json_metadata(v) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        return [safe_json_metadata(item) for item in value[:40]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(str(value), 240)


def safe_json_list(value, limit=40) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            parsed = [item.strip() for item in value.split(",") if item.strip()]
    else:
        parsed = value
    if not isinstance(parsed, list):
        parsed = [parsed]
    return [safe_json_metadata(item) for item in parsed[:limit]]


VALID_AGENT_GATEWAY_SCOPES = {
    "agents:write",
    "agents:heartbeat",
    "agent_plans:read",
    "agent_plans:write",
    "plan_evidence:read",
    "plan_evidence:write",
    "knowledge:read",
    "knowledge:write",
    "tasks:create",
    "tasks:read",
    "tasks:claim",
    "runs:write",
    "toolcalls:write",
    "artifacts:write",
    "approvals:request",
    "memories:propose",
    "evaluations:submit",
    "audit:write",
}

AGENT_GATEWAY_OBSERVER_SCOPES = {
    "agents:heartbeat",
    "knowledge:read",
    "agent_plans:read",
    "plan_evidence:read",
    "tasks:read",
    "audit:write",
}

AGENT_GATEWAY_WORKER_WRITE_SCOPES = {
    "agent_plans:write",
    "plan_evidence:write",
    "tasks:create",
    "tasks:claim",
    "runs:write",
    "toolcalls:write",
    "artifacts:write",
    "memories:propose",
    "evaluations:submit",
}

AGENT_GATEWAY_PRIVILEGED_SCOPES = {
    "agents:write",
    "knowledge:write",
    "approvals:request",
}


def parse_scope_list(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            raw = parsed if isinstance(parsed, list) else value.split(",")
        except Exception:
            raw = value.split(",")
    else:
        raw = []
    scopes = []
    for item in raw:
        scope = str(item).strip()
        if scope and scope in VALID_AGENT_GATEWAY_SCOPES and scope not in scopes:
            scopes.append(scope)
    return scopes


def agent_gateway_enrollment_policy_preview(body) -> tuple[dict, int]:
    raw_scopes = body.get("scopes") or body.get("allowed_scopes") or []
    scopes = parse_scope_list(raw_scopes)
    invalid_scopes: list[str] = []
    if isinstance(raw_scopes, str):
        raw_items = raw_scopes.split(",")
    elif isinstance(raw_scopes, list):
        raw_items = raw_scopes
    else:
        raw_items = []
    for item in raw_items:
        scope = str(item).strip()
        if scope and scope not in VALID_AGENT_GATEWAY_SCOPES and scope not in invalid_scopes:
            invalid_scopes.append(scope)
    runtime_type = coerce_choice(body.get("runtime_type") or body.get("runtime"), VALID_RUNTIME_TYPES, "mock")
    workspace_id = normalize_workspace_id(body.get("workspace_id") or "local-demo")
    privileged = [scope for scope in scopes if scope in AGENT_GATEWAY_PRIVILEGED_SCOPES]
    worker_writes = [scope for scope in scopes if scope in AGENT_GATEWAY_WORKER_WRITE_SCOPES]
    observer_only = bool(scopes) and set(scopes).issubset(AGENT_GATEWAY_OBSERVER_SCOPES)
    missing_worker_scopes = [
        scope for scope in [
            "agents:heartbeat",
            "tasks:read",
            "tasks:claim",
            "runs:write",
            "toolcalls:write",
            "evaluations:submit",
            "audit:write",
        ] if scope not in scopes
    ]
    if invalid_scopes:
        risk_level = "blocked"
        policy = "invalid"
        approval_recommended = True
        recommended_path = "fix_scopes"
    elif not scopes:
        risk_level = "blocked"
        policy = "invalid"
        approval_recommended = True
        recommended_path = "fix_scopes"
    elif privileged:
        risk_level = "high"
        policy = "privileged"
        approval_recommended = True
        recommended_path = "request_approval"
    elif worker_writes:
        risk_level = "medium"
        policy = "worker"
        approval_recommended = runtime_type != "mock" or workspace_id != "local-demo"
        recommended_path = "request_approval" if approval_recommended else "create_token"
    elif observer_only:
        risk_level = "low"
        policy = "observer"
        approval_recommended = False
        recommended_path = "create_token"
    else:
        risk_level = "medium"
        policy = "custom"
        approval_recommended = True
        recommended_path = "request_approval"
    gates = [
        {
            "id": "valid_scopes",
            "ok": bool(scopes) and not invalid_scopes,
            "status": "pass" if bool(scopes) and not invalid_scopes else "fail",
            "summary": "All requested scopes are recognized." if not invalid_scopes else f"Invalid scopes: {', '.join(invalid_scopes[:5])}",
        },
        {
            "id": "least_privilege",
            "ok": not privileged,
            "status": "pass" if not privileged else "warn",
            "summary": "No privileged enrollment scopes requested." if not privileged else f"Privileged scopes requested: {', '.join(privileged)}",
        },
        {
            "id": "worker_viability",
            "ok": not worker_writes or not missing_worker_scopes,
            "status": "pass" if not worker_writes or not missing_worker_scopes else "warn",
            "summary": "Worker scope set can claim and write task evidence." if worker_writes and not missing_worker_scopes else "Observer/custom scope set does not need full worker write coverage." if not worker_writes else f"Worker execution may be incomplete without: {', '.join(missing_worker_scopes)}",
        },
        {
            "id": "approval_path",
            "ok": True,
            "status": "warn" if approval_recommended else "pass",
            "summary": "Use approval-gated request before issuing this token." if approval_recommended else "Direct token creation is acceptable for this local/low-risk scope set.",
        },
    ]
    return {
        "provider": "agent_gateway",
        "operation": "enrollment_policy_preview",
        "status": "blocked" if risk_level == "blocked" else "attention" if approval_recommended or privileged else "ready",
        "workspace_id": workspace_id,
        "runtime_type": runtime_type,
        "policy": policy,
        "risk_level": risk_level,
        "approval_recommended": approval_recommended,
        "recommended_path": recommended_path,
        "scope_count": len(scopes),
        "scopes": scopes,
        "invalid_scopes": invalid_scopes,
        "privileged_scopes": privileged,
        "worker_write_scopes": worker_writes,
        "missing_worker_scopes": missing_worker_scopes if worker_writes else [],
        "gates": gates,
        "next_actions": [action for action in [
            "Fix invalid scopes before creating a token." if invalid_scopes else "",
            "Use agentops enrollment request before issuing this token." if approval_recommended else "Use agentops enrollment create for this low-risk/local scope set.",
            "Use short-lived sessions for worker loops after enrollment.",
        ] if action],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }, 200


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bearer_token(headers) -> str:
    supplied = (headers.get("X-AgentOps-Api-Key") or "").strip()
    auth = (headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        supplied = auth.split(" ", 1)[1].strip()
    return supplied


def production_security_requested() -> bool:
    return (
        os.environ.get("AGENTOPS_DEPLOYMENT_MODE", "").strip().lower() == "production"
        or os.environ.get("AGENTOPS_REQUIRE_PRODUCTION_SECURITY", "").strip().lower() in {"1", "true", "yes", "on"}
    )


def agent_gateway_admin_auth_error(headers) -> dict | None:
    expected = os.environ.get("AGENTOPS_ADMIN_KEY", "").strip()
    if not expected:
        if production_security_requested():
            return {"error": "unauthorized", "message": "AGENTOPS_ADMIN_KEY is required for Agent Gateway enrollment management in production mode."}
        return None
    supplied = (headers.get("X-AgentOps-Admin-Key") or "").strip()
    auth = (headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        supplied = auth.split(" ", 1)[1].strip()
    if hmac.compare_digest(supplied, expected):
        return None
    return {"error": "unauthorized", "message": "Admin token is required for Agent Gateway enrollment management."}


def agent_gateway_auth_context(conn, headers, required_scope: str | None = None, allow_session: bool = True) -> tuple[dict | None, dict | None]:
    expected = os.environ.get("AGENTOPS_API_KEY", "").strip()
    supplied = bearer_token(headers)
    if expected and hmac.compare_digest(supplied, expected):
        return {
            "mode": "global_api_key",
            "agent_id": headers.get("X-AgentOps-Agent-Id"),
            "workspace_id": headers.get("X-AgentOps-Workspace-Id") or "local-demo",
            "scopes": sorted(VALID_AGENT_GATEWAY_SCOPES),
        }, None

    if supplied:
        row = conn.execute("SELECT * FROM agent_gateway_tokens WHERE token_hash=?", (token_hash(supplied),)).fetchone()
        if row:
            if row["status"] != "active":
                return None, {"error": "unauthorized", "message": f"Agent Gateway token is {row['status']}."}
            if row["expires_at"] and row["expires_at"] < now_iso():
                conn.execute("UPDATE agent_gateway_tokens SET status='expired' WHERE token_id=?", (row["token_id"],))
                audit(conn, "system", "agent-gateway-auth", "agent_gateway.token_expired", "agent_gateway_tokens", row["token_id"], dict(row), {"status": "expired"}, {})
                return None, {"error": "unauthorized", "message": "Agent Gateway token is expired."}
            scopes = parse_scope_list(row["scopes_json"])
            if required_scope and required_scope not in scopes:
                return None, {"error": "forbidden", "message": f"Agent token is missing required scope: {required_scope}"}
            conn.execute("UPDATE agent_gateway_tokens SET last_used_at=? WHERE token_id=?", (now_iso(), row["token_id"]))
            return {
                "mode": "agent_token",
                "token_id": row["token_id"],
                "agent_id": row["agent_id"],
                "workspace_id": row["workspace_id"],
                "scopes": scopes,
            }, None

        session = conn.execute("SELECT * FROM agent_gateway_sessions WHERE session_hash=?", (token_hash(supplied),)).fetchone() if allow_session else None
        if session:
            if session["status"] != "active":
                return None, {"error": "unauthorized", "message": f"Agent Gateway session is {session['status']}."}
            if session["expires_at"] < now_iso():
                conn.execute("UPDATE agent_gateway_sessions SET status='expired' WHERE session_id=?", (session["session_id"],))
                audit(conn, "system", "agent-gateway-auth", "agent_gateway.session_expired", "agent_gateway_sessions", session["session_id"], dict(session), {"status": "expired"}, {"token_omitted": True})
                return None, {"error": "unauthorized", "message": "Agent Gateway session is expired."}
            if session["parent_token_id"]:
                parent = conn.execute(
                    "SELECT token_id,workspace_id,agent_id,status,expires_at FROM agent_gateway_tokens WHERE token_id=?",
                    (session["parent_token_id"],),
                ).fetchone()
                if not parent:
                    conn.execute("UPDATE agent_gateway_sessions SET status='revoked', revoked_at=? WHERE session_id=?", (now_iso(), session["session_id"]))
                    audit(conn, "system", "agent-gateway-auth", "agent_gateway.session_parent_missing", "agent_gateway_sessions", session["session_id"], dict(session), {"status": "revoked"}, {"parent_token_id": session["parent_token_id"], "token_omitted": True})
                    return None, {"error": "unauthorized", "message": "Agent Gateway session parent token is missing."}
                if parent["status"] != "active":
                    conn.execute("UPDATE agent_gateway_sessions SET status='revoked', revoked_at=? WHERE session_id=?", (now_iso(), session["session_id"]))
                    audit(conn, "system", "agent-gateway-auth", "agent_gateway.session_parent_revoked", "agent_gateway_sessions", session["session_id"], dict(session), {"status": "revoked"}, {"parent_token_id": parent["token_id"], "parent_status": parent["status"], "token_omitted": True})
                    return None, {"error": "unauthorized", "message": f"Agent Gateway session parent token is {parent['status']}."}
                if parent["expires_at"] and parent["expires_at"] < now_iso():
                    conn.execute("UPDATE agent_gateway_tokens SET status='expired' WHERE token_id=?", (parent["token_id"],))
                    conn.execute("UPDATE agent_gateway_sessions SET status='expired' WHERE session_id=?", (session["session_id"],))
                    audit(conn, "system", "agent-gateway-auth", "agent_gateway.session_parent_expired", "agent_gateway_sessions", session["session_id"], dict(session), {"status": "expired"}, {"parent_token_id": parent["token_id"], "token_omitted": True})
                    return None, {"error": "unauthorized", "message": "Agent Gateway session parent token is expired."}
                if normalize_workspace_id(parent["workspace_id"]) != normalize_workspace_id(session["workspace_id"]) or parent["agent_id"] != session["agent_id"]:
                    conn.execute("UPDATE agent_gateway_sessions SET status='revoked', revoked_at=? WHERE session_id=?", (now_iso(), session["session_id"]))
                    audit(conn, "system", "agent-gateway-auth", "agent_gateway.session_parent_binding_mismatch", "agent_gateway_sessions", session["session_id"], dict(session), {"status": "revoked"}, {"parent_token_id": parent["token_id"], "token_omitted": True})
                    return None, {"error": "unauthorized", "message": "Agent Gateway session binding no longer matches its parent token."}
            scopes = parse_scope_list(session["scopes_json"])
            if required_scope and required_scope not in scopes:
                return None, {"error": "forbidden", "message": f"Agent session is missing required scope: {required_scope}"}
            conn.execute("UPDATE agent_gateway_sessions SET last_used_at=? WHERE session_id=?", (now_iso(), session["session_id"]))
            return {
                "mode": "agent_session",
                "session_id": session["session_id"],
                "token_id": session["parent_token_id"],
                "agent_id": session["agent_id"],
                "workspace_id": session["workspace_id"],
                "scopes": scopes,
                "expires_at": session["expires_at"],
            }, None

        if not allow_session and conn.execute("SELECT 1 FROM agent_gateway_sessions WHERE session_hash=?", (token_hash(supplied),)).fetchone():
            return None, {"error": "unauthorized", "message": "Agent Gateway session tokens cannot mint new sessions."}
        return None, {"error": "unauthorized", "message": "Agent Gateway token is not recognized."}

    if expected:
        return None, {
            "error": "unauthorized",
            "message": "Agent Gateway local token is required when AGENTOPS_API_KEY is configured. Token values are never logged.",
        }
    if production_security_requested():
        return None, {
            "error": "unauthorized",
            "message": "Agent Gateway token, session, or configured API key is required in production mode.",
        }
    return {
        "mode": "local_dev_no_token",
        "agent_id": headers.get("X-AgentOps-Agent-Id"),
        "workspace_id": headers.get("X-AgentOps-Workspace-Id") or "local-demo",
        "scopes": sorted(VALID_AGENT_GATEWAY_SCOPES),
    }, None


def agent_gateway_is_bound_auth(auth_ctx: dict | None) -> bool:
    return bool(auth_ctx and auth_ctx.get("mode") in {"agent_token", "agent_session"})


def agent_gateway_auth_error(headers) -> dict | None:
    with db() as conn:
        _ctx, error = agent_gateway_auth_context(conn, headers)
        return error


def agent_gateway_error_status(error: dict | None) -> int:
    return 403 if error and error.get("error") == "forbidden" else 401


def agent_gateway_identity(headers, body=None, qs=None, auth_ctx=None) -> dict:
    body = body or {}
    qs = qs or {}
    if agent_gateway_is_bound_auth(auth_ctx):
        agent_id = auth_ctx.get("agent_id")
        workspace_id = auth_ctx.get("workspace_id")
    else:
        agent_id = body.get("agent_id") or headers.get("X-AgentOps-Agent-Id") or (qs.get("agent_id") or [None])[0] or (auth_ctx or {}).get("agent_id")
        workspace_id = body.get("workspace_id") or headers.get("X-AgentOps-Workspace-Id") or (qs.get("workspace_id") or ["local-demo"])[0] or (auth_ctx or {}).get("workspace_id")
    scope = body.get("scope") or headers.get("X-AgentOps-Scope") or "local:agent"
    return {
        "agent_id": str(agent_id or "").strip(),
        "workspace_id": normalize_workspace_id(workspace_id),
        "scope": redact_text(str(scope), 120),
    }


def requested_workspace_from_qs(qs: dict, fallback="local-demo") -> str:
    value = (qs.get("workspace_id") or [fallback])[0]
    return normalize_workspace_id(value or fallback)


def request_workspace(headers, qs: dict | None = None, fallback: str = "local-demo") -> str:
    qs = qs or {}
    value = (qs.get("workspace_id") or [None])[0] or (headers.get("X-AgentOps-Workspace-Id") if headers else None) or fallback
    return normalize_workspace_id(value)


def optional_request_workspace(headers, qs: dict | None = None) -> str | None:
    qs = qs or {}
    value = (qs.get("workspace_id") or [None])[0] or (headers.get("X-AgentOps-Workspace-Id") if headers else None)
    return normalize_workspace_id(value) if value else None


def workspace_hidden(entity_type: str, entity_id: str) -> dict:
    return {"error": "not found", "message": f"{entity_type} not found in requested workspace.", "entity_id": entity_id}


def row_workspace(row) -> str:
    try:
        return normalize_workspace_id(row["workspace_id"] or "local-demo")
    except Exception:
        return "local-demo"


def repo_list_workspace_tasks(conn: sqlite3.Connection, workspace_id: str):
    return conn.execute(
        "SELECT * FROM tasks WHERE COALESCE(workspace_id,'local-demo')=? ORDER BY created_at DESC",
        (normalize_workspace_id(workspace_id),),
    ).fetchall()


def repo_get_workspace_task(conn: sqlite3.Connection, workspace_id: str, task_id: str):
    return conn.execute(
        "SELECT * FROM tasks WHERE task_id=? AND COALESCE(workspace_id,'local-demo')=?",
        (task_id, normalize_workspace_id(workspace_id)),
    ).fetchone()


def repo_task_detail(conn: sqlite3.Connection, task) -> dict:
    task_id = task["task_id"]
    data = {"task": dict(task)}
    for table in ["runs", "approvals", "evaluations", "memories", "artifacts"]:
        data[table] = rows_to_dicts(conn.execute(f"SELECT * FROM {table} WHERE task_id=? ORDER BY created_at DESC", (task_id,)).fetchall())
    return data


def repo_list_workspace_runs(conn: sqlite3.Connection, workspace_id: str, task_id: str | None = None, agent_id: str | None = None):
    where = ["COALESCE(workspace_id,'local-demo')=?"]
    params: list[str] = [normalize_workspace_id(workspace_id)]
    if task_id:
        where.append("task_id=?")
        params.append(task_id)
    if agent_id:
        where.append("agent_id=?")
        params.append(agent_id)
    sql = "SELECT * FROM runs WHERE " + " AND ".join(where) + " ORDER BY created_at DESC"
    return conn.execute(sql, params).fetchall()


def repo_get_workspace_run(conn: sqlite3.Connection, workspace_id: str, run_id: str):
    return conn.execute(
        "SELECT * FROM runs WHERE run_id=? AND COALESCE(workspace_id,'local-demo')=?",
        (run_id, normalize_workspace_id(workspace_id)),
    ).fetchone()


def repo_pull_agent_gateway_tasks(conn: sqlite3.Connection, workspace_id: str, agent_id: str | None = None, statuses: list[str] | None = None, limit: int = 10):
    statuses = statuses or ["planned", "backlog"]
    placeholders = ",".join("?" for _ in statuses)
    params: list = [*statuses, normalize_workspace_id(workspace_id)]
    sql = f"SELECT * FROM tasks WHERE status IN ({placeholders}) AND COALESCE(workspace_id,'local-demo')=?"
    if agent_id:
        sql += " AND (owner_agent_id=? OR collaborator_agent_ids LIKE ? OR owner_agent_id IS NULL OR owner_agent_id='')"
        params.extend([agent_id, f"%{agent_id}%"])
    sql += " ORDER BY created_at ASC LIMIT ?"
    params.append(min(max(int(limit or 10), 1), 50))
    return conn.execute(sql, params).fetchall()


def repo_list_agent_gateway_tasks(
    conn: sqlite3.Connection,
    workspace_id: str,
    agent_id: str | None = None,
    bound_visibility: bool = False,
    statuses: list[str] | None = None,
    owner_agent_id: str | None = None,
    requester_id: str | None = None,
    limit: int = 25,
):
    where = ["COALESCE(workspace_id,'local-demo')=?"]
    params: list = [normalize_workspace_id(workspace_id)]
    if bound_visibility:
        where.append("(owner_agent_id=? OR collaborator_agent_ids LIKE ? OR owner_agent_id IS NULL OR owner_agent_id='')")
        params.extend([agent_id or "", f"%{agent_id or ''}%"])
    if statuses:
        where.append("status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    if owner_agent_id and not bound_visibility:
        where.append("owner_agent_id=?")
        params.append(owner_agent_id)
    if requester_id:
        where.append("requester_id=?")
        params.append(requester_id)
    sql = "SELECT * FROM tasks WHERE " + " AND ".join(where) + " ORDER BY created_at DESC LIMIT ?"
    params.append(min(max(int(limit or 25), 1), 200))
    return conn.execute(sql, params).fetchall()


def repo_get_agent_gateway_task(conn: sqlite3.Connection, workspace_id: str, task_id: str):
    return repo_get_workspace_task(conn, workspace_id, task_id)


def repo_list_agent_gateway_runs(
    conn: sqlite3.Connection,
    workspace_id: str,
    agent_id: str | None = None,
    bound_visibility: bool = False,
    task_id: str | None = None,
    run_agent_id: str | None = None,
    statuses: list[str] | None = None,
    limit: int = 25,
):
    where = ["COALESCE(r.workspace_id,'local-demo')=?"]
    params: list = [normalize_workspace_id(workspace_id)]
    if task_id:
        where.append("r.task_id=?")
        params.append(task_id)
    if run_agent_id and not bound_visibility:
        where.append("r.agent_id=?")
        params.append(run_agent_id)
    if bound_visibility:
        where.append("(t.owner_agent_id=? OR t.collaborator_agent_ids LIKE ? OR t.owner_agent_id IS NULL OR t.owner_agent_id='' OR r.agent_id=?)")
        params.extend([agent_id or "", f"%{agent_id or ''}%", agent_id or ""])
    if statuses:
        where.append("r.status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    sql = "SELECT r.* FROM runs r LEFT JOIN tasks t ON t.task_id=r.task_id WHERE " + " AND ".join(where) + " ORDER BY r.created_at DESC LIMIT ?"
    params.append(min(max(int(limit or 25), 1), 200))
    return conn.execute(sql, params).fetchall()


def repo_get_agent_gateway_run(conn: sqlite3.Connection, workspace_id: str, run_id: str):
    return repo_get_workspace_run(conn, workspace_id, run_id)


def repo_list_agent_gateway_artifacts(
    conn: sqlite3.Connection,
    workspace_id: str,
    agent_id: str | None = None,
    bound_visibility: bool = False,
    task_id: str | None = None,
    run_id: str | None = None,
    artifact_type: str | None = None,
    limit: int = 25,
):
    where = ["COALESCE(t.workspace_id,r.workspace_id,'local-demo')=?"]
    params: list = [normalize_workspace_id(workspace_id)]
    if task_id:
        where.append("a.task_id=?")
        params.append(task_id)
    if run_id:
        where.append("a.run_id=?")
        params.append(run_id)
    if artifact_type:
        where.append("a.artifact_type=?")
        params.append(artifact_type)
    if bound_visibility:
        where.append("(a.task_id IS NOT NULL OR a.run_id IS NOT NULL)")
        where.append("(t.owner_agent_id=? OR t.collaborator_agent_ids LIKE ? OR t.owner_agent_id IS NULL OR t.owner_agent_id='' OR r.agent_id=?)")
        params.extend([agent_id or "", f"%{agent_id or ''}%", agent_id or ""])
    sql = """SELECT a.* FROM artifacts a
        LEFT JOIN tasks t ON t.task_id=a.task_id
        LEFT JOIN runs r ON r.run_id=a.run_id
        WHERE """ + " AND ".join(where) + " ORDER BY a.created_at DESC LIMIT ?"
    params.append(min(max(int(limit or 25), 1), 200))
    return conn.execute(sql, params).fetchall()


def repo_list_agent_gateway_approvals(
    conn: sqlite3.Connection,
    workspace_id: str,
    agent_id: str | None = None,
    bound_visibility: bool = False,
    task_id: str | None = None,
    run_id: str | None = None,
    decisions: list[str] | None = None,
    requested_by_agent_id: str | None = None,
    limit: int = 25,
):
    where = ["COALESCE(t.workspace_id,r.workspace_id,'local-demo')=?"]
    params: list = [normalize_workspace_id(workspace_id)]
    if task_id:
        where.append("ap.task_id=?")
        params.append(task_id)
    if run_id:
        where.append("ap.run_id=?")
        params.append(run_id)
    if decisions:
        where.append("ap.decision IN (" + ",".join("?" for _ in decisions) + ")")
        params.extend(decisions)
    if bound_visibility:
        where.append(
            """(
                t.owner_agent_id=?
                OR t.collaborator_agent_ids LIKE ?
                OR t.owner_agent_id IS NULL
                OR t.owner_agent_id=''
                OR r.agent_id=?
                OR ap.requested_by_agent_id=?
            )"""
        )
        params.extend([agent_id or "", f"%{agent_id or ''}%", agent_id or "", agent_id or ""])
    if requested_by_agent_id and not bound_visibility:
        where.append("ap.requested_by_agent_id=?")
        params.append(requested_by_agent_id)
    sql = """SELECT ap.* FROM approvals ap
        LEFT JOIN tasks t ON t.task_id=ap.task_id
        LEFT JOIN runs r ON r.run_id=ap.run_id
        WHERE """ + " AND ".join(where) + " ORDER BY ap.created_at DESC LIMIT ?"
    params.append(min(max(int(limit or 25), 1), 200))
    return conn.execute(sql, params).fetchall()


def repo_list_agent_gateway_memories(
    conn: sqlite3.Connection,
    workspace_id: str,
    agent_id: str | None = None,
    bound_visibility: bool = False,
    task_id: str | None = None,
    statuses: list[str] | None = None,
    scopes: list[str] | None = None,
    memory_types: list[str] | None = None,
    memory_agent_id: str | None = None,
    limit: int = 25,
):
    where = ["COALESCE(m.workspace_id,t.workspace_id,'local-demo')=?"]
    params: list = [normalize_workspace_id(workspace_id)]
    if task_id:
        where.append("m.task_id=?")
        params.append(task_id)
    if statuses:
        where.append("m.review_status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    if scopes:
        where.append("m.scope IN (" + ",".join("?" for _ in scopes) + ")")
        params.extend(scopes)
    if memory_types:
        where.append("m.memory_type IN (" + ",".join("?" for _ in memory_types) + ")")
        params.extend(memory_types)
    if bound_visibility:
        where.append(
            """(
                (m.task_id IS NOT NULL AND (
                    t.owner_agent_id=?
                    OR t.collaborator_agent_ids LIKE ?
                    OR t.owner_agent_id IS NULL
                    OR t.owner_agent_id=''
                ))
                OR (m.task_id IS NULL AND m.agent_id=?)
                OR m.agent_id=?
            )"""
        )
        params.extend([agent_id or "", f"%{agent_id or ''}%", agent_id or "", agent_id or ""])
    if memory_agent_id and not bound_visibility:
        where.append("m.agent_id=?")
        params.append(memory_agent_id)
    sql = """SELECT m.* FROM memories m
        LEFT JOIN tasks t ON t.task_id=m.task_id
        WHERE """ + " AND ".join(where) + " ORDER BY m.updated_at DESC LIMIT ?"
    params.append(min(max(int(limit or 25), 1), 200))
    return conn.execute(sql, params).fetchall()


def repo_run_detail(conn: sqlite3.Connection, run) -> dict:
    run_id = run["run_id"]
    return {
        "run": dict(run),
        "tool_calls": rows_to_dicts(conn.execute("SELECT * FROM tool_calls WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()),
        "approvals": rows_to_dicts(conn.execute("SELECT * FROM approvals WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()),
        "evaluations": rows_to_dicts(conn.execute("SELECT * FROM evaluations WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()),
        "artifacts": rows_to_dicts(conn.execute("SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()),
    }


def repo_list_workspace_memories(conn: sqlite3.Connection, workspace_id: str):
    return conn.execute(
        "SELECT * FROM memories WHERE COALESCE(workspace_id,'local-demo')=? ORDER BY created_at DESC",
        (normalize_workspace_id(workspace_id),),
    ).fetchall()


def repo_get_workspace_memory(conn: sqlite3.Connection, workspace_id: str, memory_id: str):
    return conn.execute(
        "SELECT * FROM memories WHERE memory_id=? AND COALESCE(workspace_id,'local-demo')=?",
        (memory_id, normalize_workspace_id(workspace_id)),
    ).fetchone()


def repo_list_workspace_approvals(conn: sqlite3.Connection, workspace_id: str):
    return conn.execute(
        """SELECT ap.* FROM approvals ap
        LEFT JOIN tasks t ON t.task_id=ap.task_id
        LEFT JOIN runs r ON r.run_id=ap.run_id
        WHERE COALESCE(t.workspace_id,r.workspace_id,'local-demo')=?
        ORDER BY ap.created_at DESC""",
        (normalize_workspace_id(workspace_id),),
    ).fetchall()


def repo_list_workspace_evaluations(conn: sqlite3.Connection, workspace_id: str):
    return conn.execute(
        """SELECT ev.* FROM evaluations ev
        LEFT JOIN tasks t ON t.task_id=ev.task_id
        LEFT JOIN runs r ON r.run_id=ev.run_id
        WHERE COALESCE(t.workspace_id,r.workspace_id,'local-demo')=?
        ORDER BY ev.created_at DESC""",
        (normalize_workspace_id(workspace_id),),
    ).fetchall()


def repo_list_workspace_artifacts(conn: sqlite3.Connection, workspace_id: str):
    return conn.execute(
        """SELECT art.* FROM artifacts art
        LEFT JOIN tasks t ON t.task_id=art.task_id
        LEFT JOIN runs r ON r.run_id=art.run_id
        WHERE COALESCE(t.workspace_id,r.workspace_id,'local-demo')=?
        ORDER BY art.created_at DESC""",
        (normalize_workspace_id(workspace_id),),
    ).fetchall()


def repo_list_workspace_audit(conn: sqlite3.Connection, workspace_id: str, limit: int = 200):
    workspace_id = normalize_workspace_id(workspace_id)
    return conn.execute(
        """SELECT a.* FROM audit_logs a
        WHERE
          (a.entity_type='tasks' AND EXISTS (
            SELECT 1 FROM tasks t WHERE t.task_id=a.entity_id AND COALESCE(t.workspace_id,'local-demo')=?
          ))
          OR (a.entity_type='runs' AND EXISTS (
            SELECT 1 FROM runs r WHERE r.run_id=a.entity_id AND COALESCE(r.workspace_id,'local-demo')=?
          ))
          OR (a.entity_type='workflow_jobs' AND EXISTS (
            SELECT 1 FROM workflow_jobs j WHERE j.job_id=a.entity_id AND COALESCE(j.workspace_id,'local-demo')=?
          ))
          OR a.metadata_json LIKE ?
        ORDER BY a.created_at DESC LIMIT ?""",
        (workspace_id, workspace_id, workspace_id, f'%"workspace_id": "{workspace_id}"%', int(limit)),
    ).fetchall()


def repo_list_workspace_workflow_jobs(conn: sqlite3.Connection, workspace_id: str, limit: int = 50):
    return conn.execute(
        "SELECT * FROM workflow_jobs WHERE COALESCE(workspace_id,'local-demo')=? ORDER BY created_at DESC LIMIT ?",
        (normalize_workspace_id(workspace_id), min(max(int(limit or 50), 1), 200)),
    ).fetchall()


def repo_get_workspace_workflow_job(conn: sqlite3.Connection, workspace_id: str, job_id: str):
    return conn.execute(
        "SELECT * FROM workflow_jobs WHERE job_id=? AND COALESCE(workspace_id,'local-demo')=?",
        (job_id, normalize_workspace_id(workspace_id)),
    ).fetchone()


def repo_list_workspace_stuck_workflow_jobs(conn: sqlite3.Connection, workspace_id: str, threshold_sec: int = 900, limit: int = 25) -> list[dict]:
    threshold_sec = max(int(threshold_sec or 900), 30)
    limit = min(max(int(limit or 25), 1), 200)
    now_dt = dt.datetime.now(dt.timezone.utc)
    rows = conn.execute(
        """SELECT * FROM workflow_jobs
        WHERE COALESCE(workspace_id,'local-demo')=?
          AND status IN ('queued','running')
        ORDER BY updated_at ASC LIMIT 500""",
        (normalize_workspace_id(workspace_id),),
    ).fetchall()
    stuck: list[dict] = []
    for row in rows:
        data = workflow_job_public(row) or {}
        anchor = (
            _parse_iso_datetime(data.get("updated_at"))
            or _parse_iso_datetime(data.get("started_at"))
            or _parse_iso_datetime(data.get("created_at"))
            or now_dt
        )
        age_sec = max(int((now_dt - anchor).total_seconds()), 0)
        if age_sec >= threshold_sec:
            data["age_sec"] = age_sec
            data["threshold_sec"] = threshold_sec
            data["stuck_reason"] = "workflow_job_exceeded_threshold"
            stuck.append(data)
        if len(stuck) >= limit:
            break
    return stuck


def repo_list_gateway_enrollments(conn: sqlite3.Connection, workspace_id: str | None = None, limit: int = 200):
    where = ""
    params: list = []
    if workspace_id:
        where = " WHERE COALESCE(workspace_id,'local-demo')=?"
        params.append(normalize_workspace_id(workspace_id))
    params.append(min(max(int(limit or 200), 1), 500))
    return conn.execute(
        """SELECT token_id,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at
        FROM agent_gateway_tokens"""
        + where
        + " ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()


def repo_list_gateway_sessions(conn: sqlite3.Connection, workspace_id: str | None = None, limit: int = 200):
    where = ""
    params: list = []
    if workspace_id:
        where = " WHERE COALESCE(workspace_id,'local-demo')=?"
        params.append(normalize_workspace_id(workspace_id))
    params.append(min(max(int(limit or 200), 1), 500))
    return conn.execute(
        """SELECT session_id,parent_token_id,workspace_id,agent_id,scopes_json,status,created_at,expires_at,revoked_at,last_used_at
        FROM agent_gateway_sessions"""
        + where
        + " ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()


def normalize_workspace_id(value) -> str:
    raw = str(value or "local-demo").strip()[:120]
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw).strip("_")
    return normalized or "local-demo"


def workspace_forbidden(entity_type: str, entity_id: str, requested_workspace: str, actual_workspace: str) -> tuple[dict, int]:
    return {
        "error": "forbidden",
        "message": f"{entity_type} {entity_id} belongs to workspace '{actual_workspace}', not '{requested_workspace}'.",
    }, 403


def ensure_run_access(conn: sqlite3.Connection, run_id: str, ident: dict) -> tuple[sqlite3.Row | None, tuple[dict, int] | None]:
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        return None, ({"error": "run not found"}, 404)
    actual_workspace = row_workspace(run)
    if actual_workspace != ident["workspace_id"]:
        return run, workspace_forbidden("run", run_id, ident["workspace_id"], actual_workspace)
    if ident.get("agent_id") and run["agent_id"] != ident["agent_id"]:
        return run, ({"error": "forbidden", "message": "Agent token cannot write another agent's run."}, 403)
    return run, None


def ensure_gateway_agent(conn, agent_id: str, name: str | None = None, role: str | None = None, runtime_type: str | None = None):
    if conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (agent_id,)).fetchone():
        return
    now = now_iso()
    upsert_agent(conn, {
        "agent_id": agent_id,
        "name": name or agent_id.replace("_", " ").title(),
        "role": role or "External Runtime Agent",
        "description": "Registered lazily through Agent Gateway. Browser UI is for humans; this API is for CLI/API/MCP agents.",
        "runtime_type": coerce_choice(runtime_type, VALID_RUNTIME_TYPES, "mock"),
        "model_provider": "external",
        "model_name": "gateway-client",
        "status": "idle",
        "permission_level": "standard",
        "allowed_tools": json.dumps(["agent_gateway.task", "agent_gateway.run", "agent_gateway.audit"], ensure_ascii=False),
        "budget_limit_usd": 5.0,
        "owner_user_id": "usr_founder",
        "created_at": now,
        "updated_at": now,
    }, "agent-gateway")


def agent_gateway_register(conn, body) -> tuple[dict, int]:
    now = now_iso()
    name = body.get("name") or body.get("agent_name") or "Gateway Agent"
    agent_id = body.get("agent_id") or stable_id("agt_gw", name, body.get("runtime_profile") or body.get("workspace_id") or "local")
    runtime_type = coerce_choice(body.get("runtime_type"), VALID_RUNTIME_TYPES, "mock")
    tools = body.get("allowed_tools") or body.get("scopes") or ["agent_gateway.task", "agent_gateway.run", "agent_gateway.audit"]
    if not isinstance(tools, list):
        tools = [str(tools)]
    row = {
        "agent_id": agent_id,
        "name": redact_text(name, 120) or "Gateway Agent",
        "role": redact_text(body.get("role") or "AI Digital Employee", 120),
        "description": redact_text(body.get("description") or "Agent registered through local Agent Gateway.", 360),
        "runtime_type": runtime_type,
        "model_provider": redact_text(body.get("model_provider") or body.get("provider") or "external", 80),
        "model_name": redact_text(body.get("model_name") or body.get("model") or "gateway-client", 120),
        "status": coerce_choice(body.get("status"), {"idle", "running", "paused", "error", "disabled"}, "idle"),
        "permission_level": redact_text(body.get("permission_level") or "standard", 80),
        "allowed_tools": json.dumps([redact_text(item, 120) for item in tools], ensure_ascii=False),
        "budget_limit_usd": float(body.get("budget_limit_usd", 5.0) or 0),
        "owner_user_id": body.get("owner_user_id") or "usr_founder",
        "created_at": now,
        "updated_at": now,
    }
    outcome = upsert_agent(conn, row, "agent-gateway")
    runtime_event(conn, "rtc_agent_gateway_local", "agent.register", "completed", agent_id=agent_id, output_summary=f"{outcome}: {row['name']}")
    return {"agent": row, "outcome": outcome}, 201 if outcome == "created" else 200


def agent_gateway_launch_steps(agent_id: str, workspace_id: str, runtime_type: str, base_url: str | None = None) -> dict:
    base_url = redact_text(base_url or "http://127.0.0.1:8787", 180)
    safe_agent_id = redact_text(agent_id, 120)
    safe_workspace_id = normalize_workspace_id(workspace_id)
    adapter = coerce_choice(runtime_type, {"mock", "hermes", "openclaw"}, "mock")
    env = [
        f"export AGENTOPS_BASE_URL={shlex.quote(base_url)}",
        f"export AGENTOPS_WORKSPACE_ID={shlex.quote(safe_workspace_id)}",
        f"export AGENTOPS_AGENT_ID={shlex.quote(safe_agent_id)}",
        "export AGENTOPS_API_KEY='<paste one-time token here>'",
    ]
    confirm_flag = " --confirm-run" if adapter in {"hermes", "openclaw"} else ""
    run_once = f"agentops-worker --once --adapter {adapter}{confirm_flag} --use-session --session-ttl-sec 900"
    run_loop = f"agentops-worker --adapter {adapter}{confirm_flag} --use-session --session-ttl-sec 900 --poll-interval 5 --max-tasks 0 --continue-on-error --write-state --jsonl-log"
    template_args = (
        f"--adapter {adapter}{confirm_flag} "
        f"--base-url {shlex.quote(base_url)} "
        f"--workspace-id {shlex.quote(safe_workspace_id)} "
        f"--agent-id {shlex.quote(safe_agent_id)}"
    )
    return {
        "token_policy": "Token is shown once. Store it on the agent machine only; MIS stores only a hash.",
        "base_url": base_url,
        "agent_id": safe_agent_id,
        "workspace_id": safe_workspace_id,
        "adapter": adapter,
        "install": "python3 -m pip install .",
        "env": env,
        "verify": "agentops status",
        "preflight": f"agentops-worker preflight --adapter {adapter} --base-url {shlex.quote(base_url)} --workspace-id {shlex.quote(safe_workspace_id)} --agent-id {shlex.quote(safe_agent_id)}",
        "heartbeat": "agentops agent heartbeat --status idle --summary 'remote worker connected'",
        "session": "agentops session create --ttl-sec 900 --save-session",
        "run_once": run_once,
        "run_loop": run_loop,
        "launchd_template": f"agentops-worker service-template --manager launchd {template_args} > ~/Library/LaunchAgents/local.agentops.worker.{safe_agent_id}.plist",
        "systemd_template": f"agentops-worker service-template --manager systemd {template_args} > ~/.config/systemd/user/agentops-worker-{safe_agent_id}.service",
        "launchd_service_install_preview": f"agentops-worker service-install --manager launchd {template_args}",
        "launchd_service_install_confirm": f"agentops-worker service-install --manager launchd {template_args} --confirm-install",
        "systemd_service_install_preview": f"agentops-worker service-install --manager systemd {template_args}",
        "systemd_service_install_confirm": f"agentops-worker service-install --manager systemd {template_args} --confirm-install",
        "service_check_launchd": f"agentops-worker service-check --manager launchd --adapter {adapter} --agent-id {shlex.quote(safe_agent_id)}",
        "service_check_systemd": f"agentops-worker service-check --manager systemd --adapter {adapter} --agent-id {shlex.quote(safe_agent_id)}",
        "repo_fallback_run_once": f"python3 scripts/agent_worker.py --once --adapter {adapter}{confirm_flag} --use-session --session-ttl-sec 900",
        "repo_fallback_run_loop": f"python3 scripts/agent_worker.py --adapter {adapter}{confirm_flag} --use-session --session-ttl-sec 900 --poll-interval 5 --max-tasks 0 --continue-on-error --write-state --jsonl-log",
        "notes": [
            "Do not commit AGENTOPS_API_KEY or paste it into issue trackers.",
            "Install the source package on the agent machine first; the product command is agentops-worker.",
            "Use agentops status before pulling tasks.",
            "Use agentops-worker preflight before a live worker loop; it checks adapter readiness without executing a task.",
            "Worker launch commands mint a short-lived session before processing tasks; the enrollment token should remain local and revocable.",
            "Service template commands render launchd/systemd files with a token placeholder; replace it only on the agent machine.",
            "Service install commands are dry-run by default; --confirm-install writes a placeholder service file but does not load or execute it.",
            "Run service-check after writing a service file and before manually loading launchd/systemd.",
            "Repo-local scripts/agent_worker.py commands are included only as development fallbacks.",
            "Hermes/OpenClaw launch commands include --confirm-run because the selected runtime is intended to execute.",
        ],
        "token_omitted": True,
    }


def agent_gateway_create_enrollment(conn, body) -> tuple[dict, int]:
    agent_id = body.get("agent_id") or stable_id("agt_remote", body.get("name") or "remote-agent", body.get("workspace_id") or "local-demo")
    workspace_id = normalize_workspace_id(body.get("workspace_id") or "local-demo")
    runtime_type = coerce_choice(body.get("runtime_type"), VALID_RUNTIME_TYPES, "mock")
    scopes = parse_scope_list(body.get("scopes") or body.get("allowed_scopes") or [
        "agents:write",
        "agents:heartbeat",
        "knowledge:read",
        "agent_plans:read",
        "agent_plans:write",
        "plan_evidence:read",
        "plan_evidence:write",
        "tasks:create",
        "tasks:read",
        "tasks:claim",
        "runs:write",
        "toolcalls:write",
        "artifacts:write",
        "approvals:request",
        "memories:propose",
        "evaluations:submit",
        "audit:write",
    ])
    if not scopes:
        return {"error": "at least one valid scope is required", "valid_scopes": sorted(VALID_AGENT_GATEWAY_SCOPES)}, 400
    ensure_gateway_agent(
        conn,
        agent_id,
        name=redact_text(body.get("name") or agent_id, 120),
        role=redact_text(body.get("role") or "Remote AI Digital Employee", 120),
        runtime_type=runtime_type,
    )
    token = "agtok_" + secrets.token_urlsafe(32)
    now = now_iso()
    ttl_days = int(body.get("ttl_days") or 30)
    expires_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=max(ttl_days, 1))).isoformat()
    row = {
        "token_id": stable_id("agtok", agent_id, workspace_id, stable_hash(token)[:12]),
        "token_hash": token_hash(token),
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "scopes_json": json.dumps(scopes, ensure_ascii=False),
        "status": "active",
        "label": redact_text(body.get("label") or f"{agent_id} token", 120),
        "heartbeat_timeout_sec": max(int(body.get("heartbeat_timeout_sec") or 300), 30),
        "created_at": now,
        "expires_at": expires_at,
        "revoked_at": None,
        "last_used_at": None,
        "last_heartbeat_at": None,
    }
    conn.execute(
        """INSERT INTO agent_gateway_tokens(token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at)
        VALUES(:token_id,:token_hash,:workspace_id,:agent_id,:scopes_json,:status,:label,:heartbeat_timeout_sec,:created_at,:expires_at,:revoked_at,:last_used_at,:last_heartbeat_at)""",
        row,
    )
    runtime_event(conn, "rtc_agent_gateway_local", "agent.enrollment.create", "completed", agent_id=agent_id, output_summary=f"Created scoped token ref {stable_id('token_ref', row['token_id'])[-12:]}.")
    audit(conn, "user", "usr_founder", "agent_gateway.enrollment_create", "agent_gateway_tokens", row["token_id"], None, {k: v for k, v in row.items() if k != "token_hash"}, {"scopes": scopes, "token_omitted": True})
    return {
        "created": True,
        "token_id": row["token_id"],
        "agent_id": agent_id,
        "workspace_id": workspace_id,
        "scopes": scopes,
        "expires_at": expires_at,
        "heartbeat_timeout_sec": row["heartbeat_timeout_sec"],
        "token": token,
        "note": "Store this token locally on the agent machine. MIS stores only a hash and will not show it again.",
        "next_steps": agent_gateway_launch_steps(agent_id, workspace_id, runtime_type, body.get("base_url")),
    }, 201


def agent_gateway_request_enrollment(conn, body) -> tuple[dict, int]:
    workspace_id = normalize_workspace_id(body.get("workspace_id") or "local-demo")
    agent_id = body.get("agent_id") or stable_id("agt_remote", body.get("name") or "remote-agent", workspace_id)
    runtime_type = coerce_choice(body.get("runtime_type") or body.get("runtime"), VALID_RUNTIME_TYPES, "mock")
    scopes = parse_scope_list(body.get("scopes") or body.get("allowed_scopes") or [
        "agents:heartbeat",
        "knowledge:read",
        "agent_plans:read",
        "agent_plans:write",
        "plan_evidence:read",
        "plan_evidence:write",
        "tasks:create",
        "tasks:read",
        "tasks:claim",
        "runs:write",
        "toolcalls:write",
        "artifacts:write",
        "evaluations:submit",
        "memories:propose",
        "audit:write",
    ])
    if not scopes:
        return {"error": "at least one valid scope is required", "valid_scopes": sorted(VALID_AGENT_GATEWAY_SCOPES)}, 400
    name = redact_text(body.get("name") or agent_id, 120)
    role = redact_text(body.get("role") or "Remote AI Digital Employee", 120)
    reason = redact_text(body.get("reason") or "Remote agent enrollment request.", 360)
    now = now_iso()
    request_id = body.get("request_id") or stable_id("enroll_req", workspace_id, agent_id, now)
    task_id = stable_id("tsk_enroll_req", request_id)
    run_id = stable_id("run_enroll_req", request_id)
    approval_id = stable_id("ap_enroll_req", request_id)
    ensure_gateway_agent(conn, agent_id, name=name, role=role, runtime_type=runtime_type)
    upsert_task(conn, {
        "task_id": task_id,
        "workspace_id": workspace_id,
        "title": f"Remote agent enrollment request: {name}",
        "description": reason,
        "requester_id": body.get("requester_id") or "usr_founder",
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
        "status": "waiting_approval",
        "priority": "high",
        "due_date": body.get("due_date"),
        "acceptance_criteria": "Human approver must approve before any enrollment token is issued.",
        "risk_level": "high",
        "budget_limit_usd": 0,
        "created_at": now,
        "updated_at": now,
    }, "agent-gateway-enrollment")
    upsert_run(conn, {
        "run_id": run_id,
        "workspace_id": workspace_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": runtime_type,
        "status": "waiting_approval",
        "started_at": now,
        "ended_at": None,
        "duration_ms": None,
        "input_summary": f"Enrollment request for {agent_id} with {len(scopes)} scope(s).",
        "output_summary": None,
        "model_provider": "agent-gateway",
        "model_name": "enrollment-request",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0,
        "error_type": None,
        "error_message": None,
        "trace_id": new_id("trace"),
        "parent_run_id": None,
        "delegation_id": stable_id("del_enroll_req", request_id),
        "approval_required": 1,
        "created_at": now,
    }, "agent-gateway-enrollment", {"scopes": scopes, "token_omitted": True})
    approval = {
        "approval_id": approval_id,
        "task_id": task_id,
        "run_id": run_id,
        "tool_call_id": None,
        "requested_by_agent_id": agent_id,
        "approver_user_id": body.get("approver_user_id") or "usr_founder",
        "decision": "pending",
        "reason": f"Approve scoped enrollment for {agent_id}: {reason}",
        "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat(),
        "created_at": now,
        "decided_at": None,
    }
    repo_upsert_approval(conn, approval)
    request = {
        "request_id": request_id,
        "approval_id": approval_id,
        "task_id": task_id,
        "run_id": run_id,
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "name": name,
        "role": role,
        "runtime_type": runtime_type,
        "scopes_json": json.dumps(scopes, ensure_ascii=False),
        "reason": reason,
        "status": "pending",
        "token_id": None,
        "created_at": now,
        "updated_at": now,
        "decided_at": None,
    }
    conn.execute(
        """INSERT OR REPLACE INTO agent_gateway_enrollment_requests(request_id,approval_id,task_id,run_id,workspace_id,agent_id,name,role,runtime_type,scopes_json,reason,status,token_id,created_at,updated_at,decided_at)
        VALUES(:request_id,:approval_id,:task_id,:run_id,:workspace_id,:agent_id,:name,:role,:runtime_type,:scopes_json,:reason,:status,:token_id,:created_at,:updated_at,:decided_at)""",
        request,
    )
    runtime_event(conn, "rtc_agent_gateway_local", "agent.enrollment.request", "waiting_approval", run_id=run_id, task_id=task_id, agent_id=agent_id, output_summary=f"Enrollment request {request_id} is pending approval.")
    audit(conn, "agent", agent_id, "agent_gateway.enrollment_request", "agent_gateway_enrollment_requests", request_id, None, {k: v for k, v in request.items() if k != "scopes_json"}, {"scopes": scopes, "token_omitted": True})
    return {
        "request": {**{k: v for k, v in request.items() if k != "scopes_json"}, "scopes": scopes},
        "approval": approval,
        "token_issued": False,
        "token_omitted": True,
    }, 201


def sync_enrollment_request_decision(conn, approval_id: str, decision: str):
    row = conn.execute("SELECT * FROM agent_gateway_enrollment_requests WHERE approval_id=?", (approval_id,)).fetchone()
    if not row:
        return
    status = "approved" if decision == "approved" else "rejected" if decision == "rejected" else row["status"]
    conn.execute(
        "UPDATE agent_gateway_enrollment_requests SET status=?, decided_at=?, updated_at=? WHERE request_id=?",
        (status, now_iso(), now_iso(), row["request_id"]),
    )
    audit(conn, "user", "usr_founder", f"agent_gateway.enrollment_request_{decision}", "agent_gateway_enrollment_requests", row["request_id"], dict(row), {"status": status}, {"approval_id": approval_id, "token_omitted": True})


def agent_gateway_issue_approved_enrollment(conn, body) -> tuple[dict, int]:
    request_id = body.get("request_id")
    approval_id = body.get("approval_id")
    if not request_id and not approval_id:
        return {"error": "request_id or approval_id is required"}, 400
    if request_id:
        request = conn.execute("SELECT * FROM agent_gateway_enrollment_requests WHERE request_id=?", (request_id,)).fetchone()
    else:
        request = conn.execute("SELECT * FROM agent_gateway_enrollment_requests WHERE approval_id=?", (approval_id,)).fetchone()
    if not request:
        return {"error": "not found", "message": "Enrollment request not found."}, 404
    approval = conn.execute("SELECT * FROM approvals WHERE approval_id=?", (request["approval_id"],)).fetchone()
    if not approval or approval["decision"] != "approved":
        return {"error": "approval_required", "message": "Enrollment request must be approved before issuing a token.", "approval_id": request["approval_id"]}, 409
    if request["status"] == "issued":
        return {"issued": False, "token_id": request["token_id"], "request_id": request["request_id"], "token_omitted": True}, 200
    scopes = parse_scope_list(request["scopes_json"])
    created, status = agent_gateway_create_enrollment(conn, {
        "agent_id": request["agent_id"],
        "workspace_id": request["workspace_id"],
        "name": request["name"],
        "role": request["role"],
        "runtime_type": request["runtime_type"],
        "scopes": scopes,
        "ttl_days": body.get("ttl_days") or 30,
        "heartbeat_timeout_sec": body.get("heartbeat_timeout_sec") or 300,
        "label": body.get("label") or f"{request['agent_id']} approved enrollment",
        "base_url": body.get("base_url"),
    })
    if status >= 400:
        return created, status
    now = now_iso()
    before = dict(request)
    conn.execute(
        "UPDATE agent_gateway_enrollment_requests SET status='issued', token_id=?, updated_at=?, decided_at=? WHERE request_id=?",
        (created["token_id"], now, now, request["request_id"]),
    )
    after = conn.execute("SELECT * FROM agent_gateway_enrollment_requests WHERE request_id=?", (request["request_id"],)).fetchone()
    audit(conn, "user", "usr_founder", "agent_gateway.enrollment_issue_approved", "agent_gateway_enrollment_requests", request["request_id"], before, dict(after), {"approval_id": request["approval_id"], "token_id": created["token_id"], "token_omitted": True})
    created["issued_from_request_id"] = request["request_id"]
    created["approval_id"] = request["approval_id"]
    return created, 201


def agent_gateway_create_session(conn, headers, body) -> tuple[dict, int]:
    auth_ctx, auth_error = agent_gateway_auth_context(conn, headers, allow_session=False)
    if auth_error:
        return auth_error, agent_gateway_error_status(auth_error)
    auth_ctx = auth_ctx or {}
    if auth_ctx.get("mode") == "local_dev_no_token":
        return {"error": "unauthorized", "message": "A real enrollment token or local API key is required to mint a session."}, 401
    requested_scopes = parse_scope_list(body.get("scopes"))
    parent_scopes = parse_scope_list(auth_ctx.get("scopes") or [])
    scopes = [scope for scope in (requested_scopes or parent_scopes) if scope in parent_scopes]
    if requested_scopes and len(scopes) != len(requested_scopes):
        return {"error": "forbidden", "message": "Requested session scopes must be a subset of the parent token scopes."}, 403
    if not scopes:
        return {"error": "at least one valid scope is required", "valid_scopes": sorted(VALID_AGENT_GATEWAY_SCOPES)}, 400
    ttl_sec = int(body.get("ttl_sec") or body.get("ttl_seconds") or 900)
    ttl_sec = min(max(ttl_sec, 1), 3600)
    now = now_iso()
    expires_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=ttl_sec)).isoformat()
    session_token = "agtsess_" + secrets.token_urlsafe(32)
    session_id = stable_id("agtsess", auth_ctx.get("agent_id") or "agent", auth_ctx.get("workspace_id") or "local-demo", stable_hash(session_token)[:12])
    row = {
        "session_id": session_id,
        "session_hash": token_hash(session_token),
        "parent_token_id": auth_ctx.get("token_id"),
        "workspace_id": normalize_workspace_id(auth_ctx.get("workspace_id") or body.get("workspace_id") or "local-demo"),
        "agent_id": auth_ctx.get("agent_id") or body.get("agent_id"),
        "scopes_json": json.dumps(scopes, ensure_ascii=False),
        "status": "active",
        "created_at": now,
        "expires_at": expires_at,
        "revoked_at": None,
        "last_used_at": None,
    }
    if not row["agent_id"]:
        return {"error": "agent_id is required"}, 400
    ensure_gateway_agent(conn, row["agent_id"], runtime_type=body.get("runtime_type"))
    conn.execute(
        """INSERT INTO agent_gateway_sessions(session_id,session_hash,parent_token_id,workspace_id,agent_id,scopes_json,status,created_at,expires_at,revoked_at,last_used_at)
        VALUES(:session_id,:session_hash,:parent_token_id,:workspace_id,:agent_id,:scopes_json,:status,:created_at,:expires_at,:revoked_at,:last_used_at)""",
        row,
    )
    runtime_event(conn, "rtc_agent_gateway_local", "agent.session.create", "completed", agent_id=row["agent_id"], output_summary=f"Created short-lived session ref {stable_id('session_ref', session_id)[-12:]}.")
    audit(conn, "agent", row["agent_id"], "agent_gateway.session_create", "agent_gateway_sessions", session_id, None, {k: v for k, v in row.items() if k != "session_hash"}, {"scopes": scopes, "token_omitted": True})
    return {
        "created": True,
        "session_id": session_id,
        "agent_id": row["agent_id"],
        "workspace_id": row["workspace_id"],
        "scopes": scopes,
        "expires_at": expires_at,
        "ttl_sec": ttl_sec,
        "session_token": session_token,
        "note": "Session token is shown once. Use it for worker calls, then discard it; MIS stores only a hash.",
        "token_omitted": False,
    }, 201


def agent_gateway_token_heartbeat_state(row, now_dt: dt.datetime | None = None) -> str:
    now_dt = now_dt or dt.datetime.now(dt.timezone.utc)
    status = row.get("status") if hasattr(row, "get") else row["status"]
    if status != "active":
        return status or "inactive"
    heartbeat_at = row.get("last_heartbeat_at") if hasattr(row, "get") else row["last_heartbeat_at"]
    if not heartbeat_at:
        return "never_seen"
    try:
        seen = dt.datetime.fromisoformat(heartbeat_at)
        timeout = int((row.get("heartbeat_timeout_sec") if hasattr(row, "get") else row["heartbeat_timeout_sec"]) or 300)
        stale = (now_dt - seen).total_seconds() > timeout
    except Exception:
        stale = False
    return "stale" if stale else "fresh"


def agent_gateway_enrollment_rows(conn, workspace_id: str | None = None) -> list[dict]:
    rows = rows_to_dicts(repo_list_gateway_enrollments(conn, workspace_id))
    now_dt = dt.datetime.now(dt.timezone.utc)
    for row in rows:
        scopes = parse_scope_list(row.get("scopes_json"))
        row["scopes"] = scopes
        row.pop("scopes_json", None)
        row["heartbeat_state"] = agent_gateway_token_heartbeat_state(row, now_dt)
    return rows


def agent_gateway_session_state(row, now_dt: dt.datetime | None = None) -> str:
    now_dt = now_dt or dt.datetime.now(dt.timezone.utc)
    status = row.get("status") if hasattr(row, "get") else row["status"]
    if status != "active":
        return status or "inactive"
    expires_at = row.get("expires_at") if hasattr(row, "get") else row["expires_at"]
    try:
        if expires_at and dt.datetime.fromisoformat(expires_at) < now_dt:
            return "expired"
    except Exception:
        return status
    return "active"


def agent_gateway_session_rows(conn, workspace_id: str | None = None) -> list[dict]:
    rows = rows_to_dicts(repo_list_gateway_sessions(conn, workspace_id))
    now_dt = dt.datetime.now(dt.timezone.utc)
    for row in rows:
        row["scopes"] = parse_scope_list(row.get("scopes_json"))
        row.pop("scopes_json", None)
        row["session_state"] = agent_gateway_session_state(row, now_dt)
    return rows


def worker_remote_fleet_summary(conn) -> dict:
    enrollments = agent_gateway_enrollment_rows(conn)
    sessions = agent_gateway_session_rows(conn)
    remote_agent_ids = sorted({row.get("agent_id") for row in enrollments if row.get("agent_id")})
    agents = {}
    if remote_agent_ids:
        placeholders = ",".join("?" for _ in remote_agent_ids)
        agents = {
            row["agent_id"]: row
            for row in rows_to_dicts(conn.execute(
                f"SELECT agent_id,name,role,runtime_type,status,updated_at FROM agents WHERE agent_id IN ({placeholders})",
                tuple(remote_agent_ids),
            ).fetchall())
        }
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
        agent = agents.get(enrollment.get("agent_id")) or {}
        remote_workers.append({
            "token_ref": stable_id("token_ref", enrollment.get("token_id") or "")[-12:] if enrollment.get("token_id") else "",
            "token_id_omitted": True,
            "workspace_id": enrollment.get("workspace_id"),
            "agent_id": enrollment.get("agent_id"),
            "agent_name": agent.get("name") or enrollment.get("label") or enrollment.get("agent_id"),
            "runtime_type": agent.get("runtime_type") or "external",
            "agent_status": agent.get("status"),
            "token_status": token_status,
            "heartbeat_state": heartbeat_state,
            "heartbeat_timeout_sec": enrollment.get("heartbeat_timeout_sec"),
            "last_heartbeat_at": enrollment.get("last_heartbeat_at"),
            "last_used_at": enrollment.get("last_used_at"),
            "expires_at": enrollment.get("expires_at"),
            "scope_count": len(enrollment.get("scopes") or []),
            "active_session_count": active_sessions_by_agent.get(enrollment.get("agent_id"), 0),
        })
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
        "recent_sessions": [{
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
        } for session in sessions[:25]],
        "token_omitted": True,
    }


def agent_gateway_status(conn, headers) -> tuple[dict, int]:
    auth_ctx, auth_error = agent_gateway_auth_context(conn, headers)
    if auth_error:
        return auth_error, 401
    auth_ctx = auth_ctx or {}
    payload = {
        "provider": "agent_gateway",
        "status": "ready",
        "auth": {
            "mode": auth_ctx.get("mode", "unknown"),
            "authenticated": auth_ctx.get("mode") != "local_dev_no_token",
            "agent_id": auth_ctx.get("agent_id") or "",
            "workspace_id": normalize_workspace_id(auth_ctx.get("workspace_id") or "local-demo"),
            "scopes": auth_ctx.get("scopes") or [],
        },
        "valid_scopes": sorted(VALID_AGENT_GATEWAY_SCOPES),
        "token_omitted": True,
    }
    if auth_ctx.get("mode") == "agent_token":
        token_id = auth_ctx.get("token_id")
        row = conn.execute("SELECT token_id,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at FROM agent_gateway_tokens WHERE token_id=?", (token_id,)).fetchone()
        if row:
            safe_row = dict(row)
            payload["auth"].update({
                "token_id": safe_row.get("token_id"),
                "token_status": safe_row.get("status"),
                "heartbeat_state": agent_gateway_token_heartbeat_state(safe_row),
                "heartbeat_timeout_sec": safe_row.get("heartbeat_timeout_sec"),
                "expires_at": safe_row.get("expires_at"),
                "last_used_at": safe_row.get("last_used_at"),
                "last_heartbeat_at": safe_row.get("last_heartbeat_at"),
            })
    if auth_ctx.get("mode") == "agent_session":
        payload["auth"].update({
            "session_id": auth_ctx.get("session_id"),
            "parent_token_id": auth_ctx.get("token_id"),
            "session_expires_at": auth_ctx.get("expires_at"),
        })
    return payload, 200


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def security_production_readiness(conn: sqlite3.Connection, headers) -> dict:
    gateway, gateway_status_code = agent_gateway_status(conn, headers)
    auth = gateway.get("auth") or {}
    auth_mode = auth.get("mode") or ("unauthorized" if gateway_status_code == 401 else "unknown")
    api_key_configured = bool(os.environ.get("AGENTOPS_API_KEY", "").strip())
    admin_key_configured = bool(os.environ.get("AGENTOPS_ADMIN_KEY", "").strip())
    production_requested = production_security_requested()
    bound_or_global_auth = auth_mode in {"global_api_key", "agent_token", "agent_session"}
    dev_no_token = auth_mode == "local_dev_no_token"
    gates = [
        {
            "id": "agent_gateway_auth",
            "label": "Agent Gateway authenticated mode",
            "status": "pass" if bound_or_global_auth else "fail" if production_requested else "warn",
            "ok": bound_or_global_auth,
            "detail": f"auth_mode={auth_mode}",
            "next_action": "Configure a local Gateway API key or use scoped enrollment/session tokens for non-local use.",
        },
        {
            "id": "admin_key",
            "label": "Admin enrollment key",
            "status": "pass" if admin_key_configured else "fail" if production_requested else "warn",
            "ok": admin_key_configured,
            "detail": "AGENTOPS_ADMIN_KEY configured" if admin_key_configured else "Agent enrollment admin endpoints are open in local-dev mode.",
            "next_action": "Set AGENTOPS_ADMIN_KEY before shared or hosted deployment.",
        },
        {
            "id": "scoped_agent_tokens",
            "label": "Scoped agent token/session model",
            "status": "pass",
            "ok": True,
            "detail": "Agent tokens and short-lived sessions are available; raw token hashes are not exposed by status APIs.",
            "next_action": "Use agentops enrollment request/create and agentops session create for remote workers.",
        },
        {
            "id": "local_dev_boundary",
            "label": "Local-dev boundary",
            "status": "fail" if production_requested and dev_no_token else "warn" if dev_no_token else "pass",
            "ok": not dev_no_token,
            "detail": "local_dev_no_token is allowed for local demos only." if dev_no_token else "local-dev no-token fallback is disabled." if auth_mode == "unauthorized" else "request uses authenticated Agent Gateway mode.",
            "next_action": "Do not expose this service beyond 127.0.0.1 until authenticated mode is configured.",
        },
    ]
    failures = [gate for gate in gates if gate["status"] == "fail"]
    warnings = [gate for gate in gates if gate["status"] == "warn"]
    status = "blocked" if failures else "attention" if warnings else "ready"
    return {
        "provider": "agentops-security",
        "operation": "production_readiness",
        "status": status,
        "production_ready": status == "ready",
        "production_requested": production_requested,
        "auth_mode": auth_mode,
        "gateway_status_code": gateway_status_code,
        "gates": gates,
        "next_actions": [gate["next_action"] for gate in gates if gate["status"] in {"fail", "warn"}] or [
            "Keep using scoped tokens/sessions for remote workers and rotate credentials regularly.",
        ],
        "contract": "local_dev_no_token is acceptable for local classroom/demo use only; production/shared deployment must use authenticated Agent Gateway and admin keys",
        "safety": {
            "read_only": True,
            "live_execution_performed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }


def agent_gateway_revoke_enrollment(conn, body) -> tuple[dict, int]:
    token_id = body.get("token_id")
    agent_id = body.get("agent_id")
    if not token_id and not agent_id:
        return {"error": "token_id or agent_id is required"}, 400
    where = "token_id=?" if token_id else "agent_id=? AND status='active'"
    param = token_id or agent_id
    before = rows_to_dicts(conn.execute(f"SELECT token_id,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at FROM agent_gateway_tokens WHERE {where}", (param,)).fetchall())
    now = now_iso()
    conn.execute(f"UPDATE agent_gateway_tokens SET status='revoked', revoked_at=? WHERE {where}", (now, param))
    revoked_session_ids: list[str] = []
    for row in before:
        sessions = rows_to_dicts(conn.execute(
            "SELECT session_id,parent_token_id,workspace_id,agent_id,scopes_json,status,created_at,expires_at,revoked_at,last_used_at FROM agent_gateway_sessions WHERE parent_token_id=? AND status='active'",
            (row["token_id"],),
        ).fetchall())
        if sessions:
            conn.execute("UPDATE agent_gateway_sessions SET status='revoked', revoked_at=? WHERE parent_token_id=? AND status='active'", (now, row["token_id"]))
            revoked_session_ids.extend(session["session_id"] for session in sessions)
            for session in sessions:
                audit(conn, "user", "usr_founder", "agent_gateway.session_revoke_cascade", "agent_gateway_sessions", session["session_id"], session, {"status": "revoked", "revoked_at": now}, {"parent_token_id": row["token_id"], "token_omitted": True})
        runtime_event(conn, "rtc_agent_gateway_local", "agent.enrollment.revoke", "completed", agent_id=row["agent_id"], output_summary=f"Revoked token ref {stable_id('token_ref', row['token_id'])[-12:]}.")
        audit(conn, "user", "usr_founder", "agent_gateway.enrollment_revoke", "agent_gateway_tokens", row["token_id"], row, {"status": "revoked", "revoked_at": now}, {"token_omitted": True})
    return {"revoked": len(before), "changed": len(before) + len(revoked_session_ids), "tokens": [row["token_id"] for row in before], "sessions_revoked": len(revoked_session_ids), "sessions": revoked_session_ids}, 200


def agent_gateway_revoke_session(conn, body) -> tuple[dict, int]:
    session_id = body.get("session_id")
    agent_id = body.get("agent_id")
    if not session_id and not agent_id:
        return {"error": "session_id or agent_id is required"}, 400
    where = "session_id=?" if session_id else "agent_id=? AND status='active'"
    param = session_id or agent_id
    before = rows_to_dicts(conn.execute(
        f"""SELECT session_id,parent_token_id,workspace_id,agent_id,scopes_json,status,created_at,expires_at,revoked_at,last_used_at
        FROM agent_gateway_sessions WHERE {where}""",
        (param,),
    ).fetchall())
    now = now_iso()
    conn.execute(f"UPDATE agent_gateway_sessions SET status='revoked', revoked_at=? WHERE {where}", (now, param))
    for row in before:
        runtime_event(conn, "rtc_agent_gateway_local", "agent.session.revoke", "completed", agent_id=row["agent_id"], output_summary=f"Revoked short-lived session ref {stable_id('session_ref', row['session_id'])[-12:]}.")
        audit(conn, "user", "usr_founder", "agent_gateway.session_revoke", "agent_gateway_sessions", row["session_id"], row, {"status": "revoked", "revoked_at": now}, {"token_omitted": True})
    return {"revoked": len(before), "sessions": [row["session_id"] for row in before], "token_omitted": True}, 200


def agent_gateway_rotate_enrollment(conn, body) -> tuple[dict, int]:
    token_id = body.get("token_id")
    agent_id = body.get("agent_id")
    if not token_id and not agent_id:
        return {"error": "token_id or agent_id is required"}, 400

    if token_id:
        row = conn.execute(
            "SELECT * FROM agent_gateway_tokens WHERE token_id=?",
            (token_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM agent_gateway_tokens WHERE agent_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
            (agent_id,),
        ).fetchone()
    if not row:
        return {"error": "not found", "message": "No enrollment token matched the rotation request."}, 404
    old = dict(row)
    if old.get("status") != "active":
        return {"error": "not active", "message": "Only active enrollment tokens can be rotated."}, 409

    agent = conn.execute("SELECT * FROM agents WHERE agent_id=?", (old["agent_id"],)).fetchone()
    replacement_scopes = parse_scope_list(body.get("scopes") or old.get("scopes_json"))
    if not replacement_scopes:
        return {"error": "at least one valid scope is required", "valid_scopes": sorted(VALID_AGENT_GATEWAY_SCOPES)}, 400
    now = now_iso()
    conn.execute("UPDATE agent_gateway_tokens SET status='revoked', revoked_at=? WHERE token_id=?", (now, old["token_id"]))
    runtime_event(conn, "rtc_agent_gateway_local", "agent.enrollment.rotate_revoke", "completed", agent_id=old["agent_id"], output_summary=f"Revoked old token ref {stable_id('token_ref', old['token_id'])[-12:]} during rotation.")
    audit(conn, "user", "usr_founder", "agent_gateway.enrollment_rotate_revoke", "agent_gateway_tokens", old["token_id"], old, {"status": "revoked", "revoked_at": now}, {"token_omitted": True})

    create_body = {
        "workspace_id": body.get("workspace_id") or old.get("workspace_id") or "local-demo",
        "agent_id": old["agent_id"],
        "name": body.get("name") or (agent["name"] if agent else old["agent_id"]),
        "role": body.get("role") or (agent["role"] if agent else "Remote AI Digital Employee"),
        "runtime_type": body.get("runtime_type") or (agent["runtime_type"] if agent else "mock"),
        "scopes": replacement_scopes,
        "ttl_days": body.get("ttl_days") or 30,
        "heartbeat_timeout_sec": body.get("heartbeat_timeout_sec") or old.get("heartbeat_timeout_sec") or 300,
        "label": body.get("label") or f"{old['agent_id']} rotated token",
    }
    created, status = agent_gateway_create_enrollment(conn, create_body)
    if status >= 400:
        return created, status
    created["rotated"] = True
    created["rotated_from_token_id"] = old["token_id"]
    created["revoked"] = 1
    runtime_event(conn, "rtc_agent_gateway_local", "agent.enrollment.rotate", "completed", agent_id=old["agent_id"], output_summary=f"Rotated enrollment token refs {stable_id('token_ref', old['token_id'])[-12:]} -> {stable_id('token_ref', created['token_id'])[-12:]}.")
    audit(conn, "user", "usr_founder", "agent_gateway.enrollment_rotate", "agent_gateway_tokens", created["token_id"], {"token_id": old["token_id"], "status": "active"}, {"token_id": created["token_id"], "status": "active"}, {"token_omitted": True, "rotated_from_token_id": old["token_id"]})
    return created, 201


def agent_gateway_heartbeat(conn, body) -> tuple[dict, int]:
    ident = agent_gateway_identity({}, body)
    agent_id = ident["agent_id"]
    if not agent_id:
        return {"error": "agent_id is required"}, 400
    ensure_gateway_agent(conn, agent_id, runtime_type=body.get("runtime_type"))
    before = conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
    status = coerce_choice(body.get("status"), {"idle", "running", "paused", "error", "disabled"}, "idle")
    conn.execute("UPDATE agents SET status=?, updated_at=? WHERE agent_id=?", (status, now_iso(), agent_id))
    after = conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
    if body.get("_auth_token_id"):
        conn.execute("UPDATE agent_gateway_tokens SET last_heartbeat_at=?, last_used_at=? WHERE token_id=?", (now_iso(), now_iso(), body.get("_auth_token_id")))
    runtime_event(conn, "rtc_agent_gateway_local", "agent.heartbeat", status, agent_id=agent_id, output_summary=body.get("summary") or "Heartbeat recorded.")
    audit(conn, "agent", agent_id, "agent_gateway.heartbeat", "agents", agent_id, dict(before) if before else None, dict(after) if after else None, {"workspace_id": body.get("workspace_id", "local-demo")})
    return {"agent_id": agent_id, "status": status, "recorded_at": now_iso()}, 200


def agent_gateway_pull_tasks(conn, qs, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, qs=qs, auth_ctx=auth_ctx)
    agent_id = ident["agent_id"]
    limit = min(max(int((qs.get("limit") or ["10"])[0]), 1), 50)
    statuses = qs.get("status") or ["planned", "backlog"]
    statuses = [coerce_choice(status, VALID_TASK_STATUSES, "planned") for status in statuses]
    rows = rows_to_dicts(repo_pull_agent_gateway_tasks(conn, ident["workspace_id"], agent_id or None, statuses, limit))
    if agent_id:
        runtime_event(conn, "rtc_agent_gateway_local", "task.pull", "completed", agent_id=agent_id, output_summary=f"Pulled {len(rows)} task(s).")
        audit(conn, "agent", agent_id, "agent_gateway.task_pull", "tasks", agent_id, None, {"count": len(rows)}, {"workspace_id": ident["workspace_id"]})
    return {"tasks": rows, "count": len(rows), "workspace_id": ident["workspace_id"]}, 200


def create_task_api(conn, body: dict) -> tuple[dict, int]:
    now = now_iso()
    title = redact_text(body.get("title") or "New MIS task", 160)
    description = redact_text(body.get("description") or "", 1200)
    acceptance = redact_text(
        body.get("acceptance_criteria") or body.get("acceptance") or "Worker must satisfy task acceptance criteria and write ledger evidence.",
        600,
    )
    if "owner_agent_id" in body:
        owner_agent_id = body.get("owner_agent_id")
    else:
        owner_agent_id = body.get("agent_id") or "agt_research"
    owner_agent_id = str(owner_agent_id).strip() if owner_agent_id is not None else None
    if owner_agent_id == "":
        owner_agent_id = None
    if owner_agent_id:
        owner_exists = conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (owner_agent_id,)).fetchone()
        if not owner_exists:
            return {
                "error": "owner_agent_not_found",
                "message": f"Task owner agent does not exist: {owner_agent_id}",
                "owner_agent_id": owner_agent_id,
                "hint": "Register the agent first or choose an existing agent before creating the task.",
            }, 400

    collaborators = body.get("collaborator_agent_ids") or []
    if isinstance(collaborators, str):
        try:
            parsed_collaborators = json.loads(collaborators)
        except Exception:
            parsed_collaborators = None
        if isinstance(parsed_collaborators, list):
            collaborators = parsed_collaborators
        else:
            collaborators = [item.strip() for item in collaborators.split(",") if item.strip()]
    elif not isinstance(collaborators, list):
        collaborators = []
    collaborators = [redact_text(str(item), 120) for item in collaborators if str(item).strip()]

    task_id = body.get("task_id") or new_id("tsk")
    before = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    row = {
        "task_id": task_id,
        "workspace_id": normalize_workspace_id(body.get("workspace_id") or "local-demo"),
        "title": title,
        "description": description,
        "requester_id": redact_text(body.get("requester_id") or "usr_customer_demo", 120),
        "owner_agent_id": owner_agent_id,
        "collaborator_agent_ids": json.dumps(collaborators, ensure_ascii=False),
        "status": coerce_choice(body.get("status"), VALID_TASK_STATUSES, "planned"),
        "priority": coerce_choice(body.get("priority"), VALID_PRIORITIES, "medium"),
        "due_date": body.get("due_date"),
        "acceptance_criteria": acceptance,
        "risk_level": coerce_choice(body.get("risk_level"), VALID_RISK_LEVELS, "medium"),
        "budget_limit_usd": float(body.get("budget_limit_usd") or 3.0),
        "created_at": before["created_at"] if before else now,
        "updated_at": now,
    }
    outcome = upsert_task(conn, row, "task-api")
    runtime_event(
        conn,
        "rtc_agent_gateway_local",
        "task.create" if outcome == "created" else "task.update",
        row["status"],
        task_id=task_id,
        agent_id=owner_agent_id or None,
        input_summary=f"Task {outcome} through API/CLI: {title}",
        raw_payload_hash=stable_hash({"task_id": task_id, "title": title, "owner_agent_id": owner_agent_id}),
    )
    audit(
        conn,
        "user",
        row["requester_id"],
        "task.api_create" if outcome == "created" else "task.api_update",
        "tasks",
        task_id,
        dict(before) if before else None,
        row,
        {"workspace_id": row["workspace_id"], "source": body.get("source") or "api", "raw_payload_omitted": True},
    )
    return {
        "ok": True,
        "provider": "agentops-mis",
        "operation": "task_create",
        "outcome": outcome,
        "task": row,
        "task_id": task_id,
        "workspace_id": row["workspace_id"],
        "token_omitted": True,
    }, 200 if before else 201


def task_collaborators(task) -> list[str]:
    try:
        raw = task["collaborator_agent_ids"]
    except Exception:
        raw = task.get("collaborator_agent_ids") if hasattr(task, "get") else None
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except Exception:
        return [item.strip() for item in str(raw).split(",") if item.strip()]


def agent_can_access_task(task, agent_id: str) -> bool:
    try:
        owner = task["owner_agent_id"]
    except Exception:
        owner = task.get("owner_agent_id") if hasattr(task, "get") else None
    return not owner or owner == agent_id or agent_id in task_collaborators(task)


def agent_gateway_task_read_access(conn: sqlite3.Connection, task_id: str, ident: dict, auth_ctx: dict | None) -> tuple[sqlite3.Row | None, tuple[dict, int] | None]:
    task = repo_get_agent_gateway_task(conn, ident["workspace_id"], task_id)
    if not task:
        other = conn.execute("SELECT task_id,workspace_id FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if other:
            return other, workspace_forbidden("task", task_id, ident["workspace_id"], row_workspace(other))
        return None, ({"error": "task not found"}, 404)
    if agent_gateway_is_bound_auth(auth_ctx) and not agent_can_access_task(task, ident["agent_id"]):
        return task, ({"error": "forbidden", "message": f"Task {task_id} is not visible to this agent."}, 403)
    return task, None


def agent_gateway_run_read_access(conn: sqlite3.Connection, run_id: str, ident: dict, auth_ctx: dict | None) -> tuple[sqlite3.Row | None, tuple[dict, int] | None]:
    run = repo_get_agent_gateway_run(conn, ident["workspace_id"], run_id)
    if not run:
        other = conn.execute("SELECT run_id,workspace_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if other:
            return other, workspace_forbidden("run", run_id, ident["workspace_id"], row_workspace(other))
        return None, ({"error": "run not found"}, 404)
    if agent_gateway_is_bound_auth(auth_ctx):
        task_id = run["task_id"]
        if task_id:
            _task, access_error = agent_gateway_task_read_access(conn, task_id, ident, auth_ctx)
            if access_error:
                return run, access_error
        elif run["agent_id"] != ident["agent_id"]:
            return run, ({"error": "forbidden", "message": "Run is not visible to this agent."}, 403)
    return run, None


def agent_gateway_list_tasks(conn: sqlite3.Connection, qs: dict, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, qs=qs, auth_ctx=auth_ctx)
    limit = min(max(int((qs.get("limit") or ["25"])[0]), 1), 200)
    statuses = qs.get("status") or []
    statuses = [coerce_choice(status, VALID_TASK_STATUSES, "planned") for status in statuses]
    owner = (qs.get("owner_agent_id") or [None])[0]
    requester = (qs.get("requester_id") or [None])[0]
    rows = rows_to_dicts(repo_list_agent_gateway_tasks(
        conn,
        ident["workspace_id"],
        agent_id=ident.get("agent_id"),
        bound_visibility=agent_gateway_is_bound_auth(auth_ctx),
        statuses=statuses,
        owner_agent_id=owner,
        requester_id=requester,
        limit=limit,
    ))
    return {"provider": "agent_gateway", "operation": "task_list", "tasks": rows, "count": len(rows), "workspace_id": ident["workspace_id"], "token_omitted": True}, 200


def agent_gateway_get_task(conn: sqlite3.Connection, task_id: str, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, auth_ctx=auth_ctx)
    _task, access_error = agent_gateway_task_read_access(conn, task_id, ident, auth_ctx)
    if access_error:
        return access_error
    data = repo_task_detail(conn, _task) if _task else {}
    data.update({"provider": "agent_gateway", "operation": "task_get", "workspace_id": ident["workspace_id"], "token_omitted": True})
    return data, 200


def agent_gateway_list_runs(conn: sqlite3.Connection, qs: dict, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, qs=qs, auth_ctx=auth_ctx)
    limit = min(max(int((qs.get("limit") or ["25"])[0]), 1), 200)
    task_id = None
    if "task_id" in qs:
        task_id = qs["task_id"][0]
        _task, access_error = agent_gateway_task_read_access(conn, task_id, ident, auth_ctx)
        if access_error:
            return access_error
    run_agent_id = (qs.get("agent_id") or [None])[0]
    statuses = qs.get("status") or []
    statuses = [coerce_choice(status, {"running", "completed", "failed", "blocked", "waiting_approval"}, "running") for status in statuses]
    rows = rows_to_dicts(repo_list_agent_gateway_runs(
        conn,
        ident["workspace_id"],
        agent_id=ident.get("agent_id"),
        bound_visibility=agent_gateway_is_bound_auth(auth_ctx),
        task_id=task_id,
        run_agent_id=run_agent_id,
        statuses=statuses,
        limit=limit,
    ))
    return {"provider": "agent_gateway", "operation": "run_list", "runs": rows, "count": len(rows), "workspace_id": ident["workspace_id"], "token_omitted": True}, 200


def agent_gateway_get_run(conn: sqlite3.Connection, run_id: str, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, auth_ctx=auth_ctx)
    _run, access_error = agent_gateway_run_read_access(conn, run_id, ident, auth_ctx)
    if access_error:
        return access_error
    data = repo_run_detail(conn, _run) if _run else {}
    data.update({"provider": "agent_gateway", "operation": "run_get", "workspace_id": ident["workspace_id"], "token_omitted": True})
    return data, 200


def agent_gateway_get_run_graph(conn: sqlite3.Connection, run_id: str, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, auth_ctx=auth_ctx)
    _run, access_error = agent_gateway_run_read_access(conn, run_id, ident, auth_ctx)
    if access_error:
        return access_error
    data = run_graph(conn, run_id)
    if not data:
        return {"error": "not found"}, 404
    data.update({"provider": "agent_gateway", "operation": "run_graph", "workspace_id": ident["workspace_id"], "token_omitted": True})
    return data, 200


def agent_gateway_list_artifacts(conn: sqlite3.Connection, qs: dict, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, qs=qs, auth_ctx=auth_ctx)
    limit = min(max(int((qs.get("limit") or ["25"])[0]), 1), 200)
    task_id = None
    if "task_id" in qs:
        task_id = qs["task_id"][0]
        _task, access_error = agent_gateway_task_read_access(conn, task_id, ident, auth_ctx)
        if access_error:
            return access_error
    run_id = None
    if "run_id" in qs:
        run_id = qs["run_id"][0]
        _run, access_error = agent_gateway_run_read_access(conn, run_id, ident, auth_ctx)
        if access_error:
            return access_error
    artifact_type = (qs.get("type") or [None])[0]
    rows = rows_to_dicts(repo_list_agent_gateway_artifacts(
        conn,
        ident["workspace_id"],
        agent_id=ident.get("agent_id"),
        bound_visibility=agent_gateway_is_bound_auth(auth_ctx),
        task_id=task_id,
        run_id=run_id,
        artifact_type=artifact_type,
        limit=limit,
    ))
    return {"provider": "agent_gateway", "operation": "artifact_list", "artifacts": rows, "count": len(rows), "workspace_id": ident["workspace_id"], "token_omitted": True}, 200


def agent_gateway_list_approvals(conn: sqlite3.Connection, qs: dict, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, qs=qs, auth_ctx=auth_ctx)
    limit = min(max(int((qs.get("limit") or ["25"])[0]), 1), 200)
    task_id = None
    if "task_id" in qs:
        task_id = qs["task_id"][0]
        _task, access_error = agent_gateway_task_read_access(conn, task_id, ident, auth_ctx)
        if access_error:
            return access_error
    run_id = None
    if "run_id" in qs:
        run_id = qs["run_id"][0]
        _run, access_error = agent_gateway_run_read_access(conn, run_id, ident, auth_ctx)
        if access_error:
            return access_error
    decisions = qs.get("decision") or []
    decisions = [coerce_choice(decision, {"pending", "approved", "rejected"}, "pending") for decision in decisions]
    requested_by = (qs.get("requested_by_agent_id") or [None])[0]
    rows = rows_to_dicts(repo_list_agent_gateway_approvals(
        conn,
        ident["workspace_id"],
        agent_id=ident.get("agent_id"),
        bound_visibility=agent_gateway_is_bound_auth(auth_ctx),
        task_id=task_id,
        run_id=run_id,
        decisions=decisions,
        requested_by_agent_id=requested_by,
        limit=limit,
    ))
    return {
        "provider": "agent_gateway",
        "operation": "approval_list",
        "approvals": rows,
        "count": len(rows),
        "workspace_id": ident["workspace_id"],
        "gateway_scope": {
            "required_scope": "tasks:read",
            "workspace_id": ident["workspace_id"],
            "agent_id": ident["agent_id"],
            "auth_mode": (auth_ctx or {}).get("mode") or "unknown",
            "bound_visibility_enforced": agent_gateway_is_bound_auth(auth_ctx),
            "token_omitted": True,
        },
        "token_omitted": True,
    }, 200


def agent_gateway_list_memories(conn: sqlite3.Connection, qs: dict, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, qs=qs, auth_ctx=auth_ctx)
    limit = min(max(int((qs.get("limit") or ["25"])[0]), 1), 200)
    task_id = None
    if "task_id" in qs:
        task_id = qs["task_id"][0]
        _task, access_error = agent_gateway_task_read_access(conn, task_id, ident, auth_ctx)
        if access_error:
            return access_error
    statuses = qs.get("status") or []
    statuses = [coerce_choice(status, {"candidate", "approved", "rejected"}, "candidate") for status in statuses]
    scopes = qs.get("scope") or []
    scopes = [coerce_choice(scope, {"task", "project", "org"}, "project") for scope in scopes]
    types = qs.get("type") or qs.get("memory_type") or []
    cleaned_types: list[str] = []
    if types:
        allowed = {"policy", "sop", "decision", "commitment", "risk", "failure_case", "project_context", "customer_preference", "agent_lesson", "artifact_summary"}
        cleaned_types = [coerce_choice(memory_type, allowed, "artifact_summary") for memory_type in types]
    agent_id = (qs.get("agent_id") or [None])[0]
    rows = rows_to_dicts(repo_list_agent_gateway_memories(
        conn,
        ident["workspace_id"],
        agent_id=ident.get("agent_id"),
        bound_visibility=agent_gateway_is_bound_auth(auth_ctx),
        task_id=task_id,
        statuses=statuses,
        scopes=scopes,
        memory_types=cleaned_types,
        memory_agent_id=agent_id,
        limit=limit,
    ))
    return {
        "provider": "agent_gateway",
        "operation": "memory_list",
        "memories": rows,
        "count": len(rows),
        "workspace_id": ident["workspace_id"],
        "gateway_scope": {
            "required_scope": "tasks:read",
            "workspace_id": ident["workspace_id"],
            "agent_id": ident["agent_id"],
            "auth_mode": (auth_ctx or {}).get("mode") or "unknown",
            "bound_visibility_enforced": agent_gateway_is_bound_auth(auth_ctx),
            "token_omitted": True,
        },
        "token_omitted": True,
    }, 200


def markdown_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return redact_text(stripped[2:], 160) or fallback
    return fallback


def knowledge_category(path: Path) -> str:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return "external"
    parts = rel.parts
    if not parts:
        return "root"
    if parts[0] == "knowledge" and len(parts) > 1:
        return parts[1]
    if parts[0] == "docs":
        return "docs"
    return "root"


def knowledge_scope(path: Path) -> str:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        return "project"
    if rel.parts[:2] == ("knowledge", "shared"):
        return "org"
    if rel.parts[:2] == ("knowledge", "bases"):
        return "base"
    if rel.parts[:2] == ("knowledge", "runbooks"):
        return "runbook"
    return "project"


def iter_knowledge_markdown_files() -> list[Path]:
    candidates: list[Path] = []
    for name in ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md", "BASE_INDEX.md", "secret_registry.md"]:
        path = ROOT / name
        if path.exists():
            candidates.append(path)
    for base in [ROOT / "docs", KNOWLEDGE_DIR]:
        if base.exists():
            candidates.extend(sorted(base.rglob("*.md")))
    unique = []
    seen = set()
    for path in candidates:
        try:
            resolved = path.resolve()
            resolved.relative_to(ROOT)
        except Exception:
            continue
        if resolved not in seen and ".git" not in resolved.parts and "node_modules" not in resolved.parts:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def sync_knowledge_index(conn: sqlite3.Connection, rebuild: bool = False) -> dict:
    fts_available = ensure_knowledge_fts(conn)
    if rebuild:
        conn.execute("DELETE FROM knowledge_documents")
        if fts_available:
            conn.execute("DELETE FROM knowledge_fts")
    indexed = 0
    changed = 0
    deleted = 0
    seen_doc_ids = set()
    for path in iter_knowledge_markdown_files():
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        rel = str(path.relative_to(ROOT))
        doc_id = stable_id("kdoc", rel)
        seen_doc_ids.add(doc_id)
        source_hash = stable_hash({"path": rel, "content": content})
        indexed_content = redact_full_text(content)
        existing = conn.execute("SELECT source_hash FROM knowledge_documents WHERE doc_id=?", (doc_id,)).fetchone()
        indexed += 1
        if existing and existing["source_hash"] == source_hash and not rebuild:
            continue
        title = markdown_title(content, path.stem.replace("_", " ").replace("-", " ").title())
        now = now_iso()
        row = {
            "doc_id": doc_id,
            "path": rel,
            "title": title,
            "category": knowledge_category(path),
            "scope": knowledge_scope(path),
            "source_hash": source_hash,
            "content_summary": redact_text(indexed_content, 360),
            "indexed_at": now,
            "updated_at": now,
        }
        conn.execute(
            """INSERT INTO knowledge_documents(doc_id,path,title,category,scope,source_hash,content_summary,indexed_at,updated_at)
            VALUES(:doc_id,:path,:title,:category,:scope,:source_hash,:content_summary,:indexed_at,:updated_at)
            ON CONFLICT(doc_id) DO UPDATE SET
                path=excluded.path,title=excluded.title,category=excluded.category,scope=excluded.scope,
                source_hash=excluded.source_hash,content_summary=excluded.content_summary,updated_at=excluded.updated_at""",
            row,
        )
        if fts_available:
            conn.execute("DELETE FROM knowledge_fts WHERE doc_id=?", (doc_id,))
            conn.execute(
                "INSERT INTO knowledge_fts(doc_id,path,title,content) VALUES(?,?,?,?)",
                (doc_id, rel, title, indexed_content),
            )
        changed += 1
    existing_ids = {row["doc_id"] for row in conn.execute("SELECT doc_id FROM knowledge_documents").fetchall()}
    for stale_id in sorted(existing_ids - seen_doc_ids):
        conn.execute("DELETE FROM knowledge_documents WHERE doc_id=?", (stale_id,))
        if fts_available:
            conn.execute("DELETE FROM knowledge_fts WHERE doc_id=?", (stale_id,))
        deleted += 1
    return {"indexed": indexed, "changed": changed, "deleted": deleted, "fts_available": fts_available}


def fts_query(raw: str) -> str:
    terms = re.findall(r"[\w\u4e00-\u9fff]+", raw or "", flags=re.UNICODE)
    terms = [term for term in terms if term.strip()]
    return " OR ".join(terms[:8])


def knowledge_search(conn: sqlite3.Connection, qs: dict, headers=None, auth_ctx=None) -> tuple[dict, int]:
    query = (qs.get("q") or qs.get("query") or [""])[0].strip()
    limit = min(max(int((qs.get("limit") or ["10"])[0]), 1), 50)
    refresh = (qs.get("refresh") or ["false"])[0].lower() in {"1", "true", "yes"}
    has_index = bool(conn.execute("SELECT 1 FROM knowledge_documents LIMIT 1").fetchone())
    gateway_read = auth_ctx is not None
    index_result = None
    if not gateway_read and (refresh or not has_index):
        index_result = sync_knowledge_index(conn, rebuild=False)
        has_index = bool(conn.execute("SELECT 1 FROM knowledge_documents LIMIT 1").fetchone())
    index_state = {
        "indexed": has_index,
        "refresh_requested": refresh,
        "refresh_performed": bool(index_result),
        "read_only": gateway_read,
        "refresh_skipped_reason": "knowledge_read_is_non_mutating" if gateway_read and refresh else None,
    }
    rows = []
    search_mode = "recent"
    if query:
        search_mode = "fts5" if ensure_knowledge_fts(conn) else "like"
        try:
            match = fts_query(query)
            if not match:
                raise sqlite3.OperationalError("empty fts query")
            rows = rows_to_dicts(conn.execute(
                """SELECT kd.*, snippet(knowledge_fts, 3, '', '', ' ... ', 18) AS snippet, bm25(knowledge_fts) AS rank
                FROM knowledge_fts
                JOIN knowledge_documents kd ON kd.doc_id=knowledge_fts.doc_id
                WHERE knowledge_fts MATCH ?
                ORDER BY rank LIMIT ?""",
                (match, limit),
            ).fetchall())
        except sqlite3.OperationalError:
            like = f"%{query}%"
            search_mode = "like"
            rows = rows_to_dicts(conn.execute(
                """SELECT *, content_summary AS snippet, 0 AS rank FROM knowledge_documents
                WHERE title LIKE ? OR path LIKE ? OR content_summary LIKE ?
                ORDER BY updated_at DESC LIMIT ?""",
                (like, like, like, limit),
            ).fetchall())
    else:
        rows = rows_to_dicts(conn.execute(
            "SELECT *, content_summary AS snippet, 0 AS rank FROM knowledge_documents ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall())
    return {
        "provider": "agentops-knowledge",
        "operation": "knowledge_search",
        "query": query,
        "search_mode": search_mode,
        "results": rows,
        "count": len(rows),
        "index": index_result or index_state,
        "token_omitted": True,
    }, 200


def list_agent_plans(conn: sqlite3.Connection, qs: dict, headers=None, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers or {}, qs=qs, auth_ctx=auth_ctx)
    limit = min(max(int((qs.get("limit") or ["25"])[0]), 1), 100)
    where = ["COALESCE(ap.workspace_id,'local-demo')=?"]
    params: list = [ident["workspace_id"]]
    if "task_id" in qs:
        task_id = qs["task_id"][0]
        _task, access_error = agent_gateway_task_read_access(conn, task_id, ident, auth_ctx)
        if access_error:
            return access_error
        where.append("ap.task_id=?")
        params.append(task_id)
    if "run_id" in qs:
        run_id = qs["run_id"][0]
        _run, access_error = agent_gateway_run_read_access(conn, run_id, ident, auth_ctx)
        if access_error:
            return access_error
        where.append("ap.run_id=?")
        params.append(run_id)
    if agent_gateway_is_bound_auth(auth_ctx):
        where.append("ap.agent_id=?")
        params.append(ident["agent_id"])
    elif "agent_id" in qs:
        where.append("ap.agent_id=?")
        params.append(qs["agent_id"][0])
    rows = rows_to_dicts(conn.execute(
        "SELECT ap.* FROM agent_plans ap WHERE " + " AND ".join(where) + " ORDER BY ap.created_at DESC LIMIT ?",
        [*params, limit],
    ).fetchall())
    return {
        "provider": "agentops-agent-plan",
        "operation": "agent_plan_list",
        "agent_plans": rows,
        "count": len(rows),
        "workspace_id": ident["workspace_id"],
        "token_omitted": True,
    }, 200


def get_agent_plan(conn: sqlite3.Connection, plan_id: str, headers=None, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers or {}, auth_ctx=auth_ctx)
    row = conn.execute("SELECT * FROM agent_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if not row:
        return {"error": "agent plan not found"}, 404
    if row["workspace_id"] != ident["workspace_id"]:
        return workspace_forbidden("agent_plan", plan_id, ident["workspace_id"], row["workspace_id"])
    if agent_gateway_is_bound_auth(auth_ctx) and row["agent_id"] != ident["agent_id"]:
        return {"error": "forbidden", "message": "Agent token cannot read another agent's plan."}, 403
    return {"provider": "agentops-agent-plan", "operation": "agent_plan_get", "agent_plan": dict(row), "token_omitted": True}, 200


def load_json_list_field(row: sqlite3.Row | dict, field: str) -> list:
    try:
        value = row[field]
    except Exception:
        value = "[]"
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        parsed = []
    return parsed if isinstance(parsed, list) else []


def verify_agent_plan_row(row: sqlite3.Row | dict) -> dict:
    specs = load_json_list_field(row, "referenced_specs_json")
    memories = load_json_list_field(row, "referenced_memories_json")
    bases = load_json_list_field(row, "referenced_bases_json")
    files = load_json_list_field(row, "proposed_files_to_change_json")
    steps = load_json_list_field(row, "execution_steps_json")
    risk = row["risk_level"]
    approval_required = bool(row["approval_required"])
    checks = [
        {"id": "read_specs", "ok": bool(specs), "message": "Plan references specs or workflow docs."},
        {"id": "retrieve_memory", "ok": bool(memories), "message": "Plan references memory, knowledge, or failure-case context."},
        {"id": "compare_bases", "ok": bool(bases), "message": "Plan references base constraints or reusable foundations."},
        {"id": "execution_steps", "ok": len(steps) >= 3, "message": "Plan includes concrete execution steps."},
        {"id": "verification_plan", "ok": bool(str(row["verification_plan"] or "").strip()), "message": "Plan includes verification path."},
        {"id": "rollback_plan", "ok": bool(str(row["rollback_plan"] or "").strip()), "message": "Plan includes rollback path."},
        {"id": "risk_gate", "ok": risk not in {"high", "critical"} or approval_required, "message": "High/critical risk requires approval."},
        {"id": "file_scope", "ok": bool(files) or risk == "low", "message": "Non-low work names proposed files or surfaces."},
    ]
    failed = [check for check in checks if not check["ok"]]
    return {
        "pass": not failed,
        "checks": checks,
        "failed_checks": failed,
        "summary": {
            "referenced_specs": len(specs),
            "referenced_memories": len(memories),
            "referenced_bases": len(bases),
            "proposed_files_to_change": len(files),
            "execution_steps": len(steps),
            "risk_level": risk,
            "approval_required": approval_required,
        },
        "token_omitted": True,
    }


def verify_agent_plan(conn: sqlite3.Connection, plan_id: str, headers=None, auth_ctx=None) -> tuple[dict, int]:
    payload, status = get_agent_plan(conn, plan_id, headers, auth_ctx)
    if status != 200:
        return payload, status
    row = payload["agent_plan"]
    verification = verify_agent_plan_row(row)
    return {
        "provider": "agentops-agent-plan",
        "operation": "agent_plan_verify",
        "plan_id": plan_id,
        "agent_plan": row,
        "verification": verification,
        "token_omitted": True,
    }, 200


def agent_gateway_create_agent_plan(conn: sqlite3.Connection, body) -> tuple[dict, int]:
    ident = agent_gateway_identity({}, body)
    agent_id = ident["agent_id"]
    if not agent_id:
        return {"error": "agent_id is required"}, 400
    task_id = body.get("task_id")
    run_id = body.get("run_id")
    if run_id:
        run, access_error = ensure_run_access(conn, run_id, ident)
        if access_error:
            return access_error
        task_id = task_id or run["task_id"]
    elif task_id:
        task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not task:
            return {"error": "task not found"}, 404
        actual_workspace = row_workspace(task)
        if actual_workspace != ident["workspace_id"]:
            return workspace_forbidden("task", task_id, ident["workspace_id"], actual_workspace)
        if not agent_can_access_task(task, agent_id):
            return {"error": "forbidden", "message": f"Task {task_id} is assigned to another agent.", "owner_agent_id": task["owner_agent_id"]}, 403
    understanding = redact_text(body.get("task_understanding") or body.get("understanding") or "", 800)
    if not understanding:
        return {"error": "task_understanding is required"}, 400
    risk = coerce_choice(body.get("risk_level"), VALID_RISK_LEVELS, "medium")
    row = {
        "plan_id": body.get("plan_id") or stable_id("plan", agent_id, task_id or run_id or stable_hash(understanding)[:12], now_iso()),
        "workspace_id": ident["workspace_id"],
        "task_id": task_id,
        "run_id": run_id,
        "agent_id": agent_id,
        "task_understanding": understanding,
        "referenced_specs_json": json.dumps(safe_json_list(body.get("referenced_specs")), ensure_ascii=False),
        "referenced_memories_json": json.dumps(safe_json_list(body.get("referenced_memories")), ensure_ascii=False),
        "referenced_bases_json": json.dumps(safe_json_list(body.get("referenced_bases")), ensure_ascii=False),
        "proposed_files_to_change_json": json.dumps(safe_json_list(body.get("proposed_files_to_change")), ensure_ascii=False),
        "risk_level": risk,
        "approval_required": 1 if body.get("approval_required") or risk in {"high", "critical"} else 0,
        "execution_steps_json": json.dumps(safe_json_list(body.get("execution_steps")), ensure_ascii=False),
        "verification_plan": redact_text(body.get("verification_plan"), 800) if body.get("verification_plan") else None,
        "rollback_plan": redact_text(body.get("rollback_plan"), 800) if body.get("rollback_plan") else None,
        "status": coerce_choice(body.get("status"), {"draft", "submitted", "approved", "rejected", "superseded"}, "submitted"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    conn.execute(
        """INSERT INTO agent_plans(plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,referenced_specs_json,
        referenced_memories_json,referenced_bases_json,proposed_files_to_change_json,risk_level,approval_required,
        execution_steps_json,verification_plan,rollback_plan,status,created_at,updated_at)
        VALUES(:plan_id,:workspace_id,:task_id,:run_id,:agent_id,:task_understanding,:referenced_specs_json,
        :referenced_memories_json,:referenced_bases_json,:proposed_files_to_change_json,:risk_level,:approval_required,
        :execution_steps_json,:verification_plan,:rollback_plan,:status,:created_at,:updated_at)""",
        row,
    )
    audit(conn, "agent", agent_id, "agent_gateway.agent_plan_create", "agent_plans", row["plan_id"], None, row, {"raw_omitted": True})
    runtime_event(conn, "rtc_agent_gateway_local", "agent_plan.create", "completed", run_id=run_id, task_id=task_id, agent_id=agent_id, output_summary=understanding)
    return {"agent_plan": row, "token_omitted": True}, 201


def load_plan_evidence_manifest(conn: sqlite3.Connection, manifest_id: str, ident: dict, auth_ctx=None) -> tuple[sqlite3.Row | None, tuple[dict, int] | None]:
    row = conn.execute("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", (manifest_id,)).fetchone()
    if not row:
        return None, ({"error": "plan evidence manifest not found"}, 404)
    if row["workspace_id"] != ident["workspace_id"]:
        return None, workspace_forbidden("plan_evidence_manifest", manifest_id, ident["workspace_id"], row["workspace_id"])
    if agent_gateway_is_bound_auth(auth_ctx) and row["agent_id"] != ident["agent_id"]:
        return None, ({"error": "forbidden", "message": "Agent token cannot read another agent's plan evidence manifest."}, 403)
    return row, None


def list_plan_evidence_manifests(conn: sqlite3.Connection, qs: dict, headers=None, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers or {}, qs=qs, auth_ctx=auth_ctx)
    limit = min(max(int((qs.get("limit") or ["25"])[0]), 1), 100)
    where = ["workspace_id=?"]
    params: list = [ident["workspace_id"]]
    for field in ["plan_id", "task_id", "run_id"]:
        if field in qs:
            where.append(f"{field}=?")
            params.append(qs[field][0])
    if agent_gateway_is_bound_auth(auth_ctx):
        where.append("agent_id=?")
        params.append(ident["agent_id"])
    elif "agent_id" in qs:
        where.append("agent_id=?")
        params.append(qs["agent_id"][0])
    rows = rows_to_dicts(conn.execute(
        "SELECT * FROM plan_evidence_manifests WHERE " + " AND ".join(where) + " ORDER BY created_at DESC LIMIT ?",
        [*params, limit],
    ).fetchall())
    return {
        "provider": "agentops-plan-evidence",
        "operation": "plan_evidence_manifest_list",
        "manifests": rows,
        "count": len(rows),
        "workspace_id": ident["workspace_id"],
        "token_omitted": True,
    }, 200


def get_plan_evidence_manifest(conn: sqlite3.Connection, manifest_id: str, headers=None, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers or {}, auth_ctx=auth_ctx)
    row, access_error = load_plan_evidence_manifest(conn, manifest_id, ident, auth_ctx)
    if access_error:
        return access_error
    return {
        "provider": "agentops-plan-evidence",
        "operation": "plan_evidence_manifest_get",
        "manifest": dict(row),
        "token_omitted": True,
    }, 200


def existing_id_rows(conn: sqlite3.Connection, table: str, id_col: str, ids: list) -> dict:
    clean = [str(item) for item in ids if item]
    if not clean:
        return {}
    placeholders = ",".join("?" for _ in clean)
    rows = conn.execute(f"SELECT * FROM {table} WHERE {id_col} IN ({placeholders})", clean).fetchall()
    return {row[id_col]: row for row in rows}


def plan_evidence_rows(conn: sqlite3.Connection, manifest: sqlite3.Row) -> dict:
    run_id = manifest["run_id"]
    task_id = manifest["task_id"]
    supplied_tool_ids = load_json_list_field(manifest, "tool_call_ids_json")
    supplied_eval_ids = load_json_list_field(manifest, "evaluation_ids_json")
    supplied_artifact_ids = load_json_list_field(manifest, "artifact_ids_json")
    supplied_audit_ids = load_json_list_field(manifest, "audit_ids_json")
    tool_rows = existing_id_rows(conn, "tool_calls", "tool_call_id", supplied_tool_ids) if supplied_tool_ids else {
        row["tool_call_id"]: row for row in conn.execute("SELECT * FROM tool_calls WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
    }
    evaluation_rows = existing_id_rows(conn, "evaluations", "evaluation_id", supplied_eval_ids) if supplied_eval_ids else {
        row["evaluation_id"]: row for row in conn.execute("SELECT * FROM evaluations WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()
    }
    artifact_rows = existing_id_rows(conn, "artifacts", "artifact_id", supplied_artifact_ids) if supplied_artifact_ids else {
        row["artifact_id"]: row for row in conn.execute("SELECT * FROM artifacts WHERE run_id=? OR task_id=? ORDER BY created_at", (run_id, task_id)).fetchall()
    }
    audit_rows = existing_id_rows(conn, "audit_logs", "audit_id", supplied_audit_ids) if supplied_audit_ids else {}
    if not audit_rows:
        entity_ids = [manifest["manifest_id"], manifest["plan_id"], run_id, task_id, *tool_rows.keys(), *evaluation_rows.keys(), *artifact_rows.keys()]
        clean_entity_ids = [str(item) for item in entity_ids if item]
        if clean_entity_ids:
            placeholders = ",".join("?" for _ in clean_entity_ids)
            audit_rows = {
                row["audit_id"]: row
                for row in conn.execute(f"SELECT * FROM audit_logs WHERE entity_id IN ({placeholders}) ORDER BY created_at", clean_entity_ids).fetchall()
            }
    return {
        "tool_calls": list(tool_rows.values()),
        "evaluations": list(evaluation_rows.values()),
        "artifacts": list(artifact_rows.values()),
        "audit_logs": list(audit_rows.values()),
        "supplied": {
            "tool_call_ids": supplied_tool_ids,
            "evaluation_ids": supplied_eval_ids,
            "artifact_ids": supplied_artifact_ids,
            "audit_ids": supplied_audit_ids,
        },
    }


def verify_plan_evidence_manifest_row(conn: sqlite3.Connection, manifest: sqlite3.Row | dict) -> dict:
    plan = conn.execute("SELECT * FROM agent_plans WHERE plan_id=?", (manifest["plan_id"],)).fetchone()
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (manifest["run_id"],)).fetchone()
    task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (manifest["task_id"],)).fetchone() if manifest["task_id"] else None
    evidence = plan_evidence_rows(conn, manifest)
    plan_verification = verify_agent_plan_row(plan) if plan else {"pass": False, "checks": []}
    expected_steps = load_json_list_field(manifest, "expected_steps_json")
    tool_rows = evidence["tool_calls"]
    eval_rows = evidence["evaluations"]
    artifact_rows = evidence["artifacts"]
    audit_rows = evidence["audit_logs"]
    supplied = evidence["supplied"]
    supplied_tool_count = len(supplied["tool_call_ids"])
    supplied_eval_count = len(supplied["evaluation_ids"])
    supplied_artifact_count = len(supplied["artifact_ids"])
    supplied_audit_count = len(supplied["audit_ids"])

    def all_supplied_found(rows: list, supplied_key: str, id_col: str) -> bool:
        supplied_ids = supplied[supplied_key]
        if not supplied_ids:
            return True
        found = {row[id_col] for row in rows}
        return all(item in found for item in supplied_ids)

    checks = [
        {"id": "plan_exists", "ok": bool(plan), "message": "Manifest references an existing agent_plan."},
        {"id": "plan_verifies", "ok": bool(plan_verification.get("pass")), "message": "Referenced agent_plan passes method-block verification."},
        {"id": "run_exists", "ok": bool(run), "message": "Manifest references an existing run."},
        {"id": "task_exists", "ok": bool(task), "message": "Manifest task exists."},
        {"id": "workspace_match", "ok": bool(plan and run and plan["workspace_id"] == manifest["workspace_id"] == run["workspace_id"]), "message": "Plan, manifest and run are in the same workspace."},
        {"id": "task_match", "ok": bool(plan and run and (not plan["task_id"] or plan["task_id"] == manifest["task_id"] == run["task_id"])), "message": "Plan, manifest and run bind to the same task."},
        {"id": "run_match", "ok": bool(plan and (not plan["run_id"] or plan["run_id"] == manifest["run_id"])), "message": "Manifest run matches any run pinned by the plan."},
        {"id": "agent_match", "ok": bool(plan and run and plan["agent_id"] == manifest["agent_id"] == run["agent_id"]), "message": "Plan, manifest and run bind to the same agent."},
        {"id": "expected_steps", "ok": len(expected_steps) >= 3, "message": "Manifest carries the approved execution steps."},
        {"id": "tool_evidence_present", "ok": len(tool_rows) >= 1, "message": "Run has at least one tool_call evidence row."},
        {"id": "tool_evidence_completed", "ok": bool(tool_rows) and all(row["run_id"] == manifest["run_id"] and row["status"] == "completed" for row in tool_rows), "message": "Tool evidence belongs to the run and is completed."},
        {"id": "tool_ids_found", "ok": all_supplied_found(tool_rows, "tool_call_ids", "tool_call_id"), "message": "All declared tool_call_ids exist."},
        {"id": "evaluation_evidence_present", "ok": len(eval_rows) >= 1, "message": "Run has at least one evaluation evidence row."},
        {"id": "evaluation_evidence_passed", "ok": bool(eval_rows) and all(row["run_id"] == manifest["run_id"] and row["pass_fail"] == "pass" for row in eval_rows), "message": "Evaluation evidence belongs to the run and passes."},
        {"id": "evaluation_ids_found", "ok": all_supplied_found(eval_rows, "evaluation_ids", "evaluation_id"), "message": "All declared evaluation_ids exist."},
        {"id": "artifact_evidence_present", "ok": len(artifact_rows) >= 1, "message": "Run or task has at least one artifact evidence row."},
        {"id": "artifact_evidence_bound", "ok": bool(artifact_rows) and all(row["run_id"] == manifest["run_id"] or row["task_id"] == manifest["task_id"] for row in artifact_rows), "message": "Artifact evidence is bound to the run or task."},
        {"id": "artifact_ids_found", "ok": all_supplied_found(artifact_rows, "artifact_ids", "artifact_id"), "message": "All declared artifact_ids exist."},
        {"id": "audit_evidence_present", "ok": len(audit_rows) >= 1, "message": "Ledger has audit evidence for the plan/run/tool/eval/artifact chain."},
        {"id": "audit_ids_found", "ok": all_supplied_found(audit_rows, "audit_ids", "audit_id"), "message": "All declared audit_ids exist."},
    ]
    failed = [check for check in checks if not check["ok"]]
    status = "verified" if not failed else ("blocked" if manifest["mismatch_policy"] == "block" else "warning")
    return {
        "pass": not failed,
        "status": status,
        "mismatch_policy": manifest["mismatch_policy"],
        "checks": checks,
        "failed_checks": failed,
        "plan_verification": plan_verification,
        "evidence_counts": {
            "tool_calls": len(tool_rows),
            "evaluations": len(eval_rows),
            "artifacts": len(artifact_rows),
            "audit_logs": len(audit_rows),
        },
        "declared_counts": {
            "tool_call_ids": supplied_tool_count,
            "evaluation_ids": supplied_eval_count,
            "artifact_ids": supplied_artifact_count,
            "audit_ids": supplied_audit_count,
        },
        "token_omitted": True,
    }


def persist_plan_evidence_verification(conn: sqlite3.Connection, manifest_id: str, verification: dict) -> None:
    conn.execute(
        "UPDATE plan_evidence_manifests SET status=?, verification_json=?, updated_at=? WHERE manifest_id=?",
        (verification["status"], json.dumps(verification, ensure_ascii=False), now_iso(), manifest_id),
    )


def verify_plan_evidence_manifest(conn: sqlite3.Connection, manifest_id: str, headers=None, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers or {}, auth_ctx=auth_ctx)
    row, access_error = load_plan_evidence_manifest(conn, manifest_id, ident, auth_ctx)
    if access_error:
        return access_error
    verification = verify_plan_evidence_manifest_row(conn, row)
    return {
        "provider": "agentops-plan-evidence",
        "operation": "plan_evidence_manifest_verify",
        "manifest": dict(row),
        "verification": verification,
        "token_omitted": True,
    }, 200


def latest_plan_evidence_manifest_for_run(conn: sqlite3.Connection, run_id: str | None) -> sqlite3.Row | None:
    if not run_id:
        return None
    return conn.execute(
        "SELECT * FROM plan_evidence_manifests WHERE run_id=? ORDER BY updated_at DESC, created_at DESC LIMIT 1",
        (run_id,),
    ).fetchone()


def customer_delivery_approval_requires_manifest(approval: sqlite3.Row | dict) -> bool:
    approval_id = str(approval["approval_id"] or "")
    reason = str(approval["reason"] or "").lower()
    return approval_id.startswith("ap_customer_worker_delivery") or "customer delivery" in reason


def delivery_manifest_gate(conn: sqlite3.Connection, run_id: str | None) -> dict:
    manifest = latest_plan_evidence_manifest_for_run(conn, run_id)
    if not manifest:
        return {
            "required": True,
            "pass": False,
            "status": "blocked_missing_verified_manifest",
            "manifest_id": None,
            "message": "Customer delivery requires a verified plan_evidence_manifest for this run.",
            "token_omitted": True,
        }
    verification = verify_plan_evidence_manifest_row(conn, manifest)
    return {
        "required": True,
        "pass": bool(verification.get("pass")),
        "status": verification.get("status"),
        "manifest_id": manifest["manifest_id"],
        "evidence_counts": verification.get("evidence_counts") or {},
        "failed_checks": [item.get("id") for item in verification.get("failed_checks") or []],
        "message": "Verified plan_evidence_manifest found." if verification.get("pass") else "Latest plan_evidence_manifest is not verified.",
        "token_omitted": True,
    }


def latest_agent_plan_for_run(conn: sqlite3.Connection, run: sqlite3.Row) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT * FROM agent_plans
        WHERE workspace_id=? AND agent_id=? AND (run_id=? OR task_id=?)
        ORDER BY CASE WHEN run_id=? THEN 0 ELSE 1 END, updated_at DESC, created_at DESC
        LIMIT 1""",
        (run["workspace_id"], run["agent_id"], run["run_id"], run["task_id"], run["run_id"]),
    ).fetchone()


def ensure_run_plan_evidence_manifest(conn: sqlite3.Connection, run_id: str, reason: str = "auto") -> dict:
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        return {"ok": False, "error": "run_not_found", "run_id": run_id}
    existing_manifest = latest_plan_evidence_manifest_for_run(conn, run_id)
    if existing_manifest:
        existing_verification = verify_plan_evidence_manifest_row(conn, existing_manifest)
        if existing_verification.get("pass"):
            return {
                "ok": True,
                "plan_id": existing_manifest["plan_id"],
                "manifest_id": existing_manifest["manifest_id"],
                "status": existing_verification.get("status"),
                "verification": existing_verification,
                "reused": True,
                "token_omitted": True,
            }
    plan = latest_agent_plan_for_run(conn, run)
    if not plan:
        task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (run["task_id"],)).fetchone() if run["task_id"] else None
        plan_payload, plan_status = agent_gateway_create_agent_plan(conn, {
            "workspace_id": run["workspace_id"],
            "agent_id": run["agent_id"],
            "task_id": run["task_id"],
            "run_id": run["run_id"],
            "task_understanding": (
                f"Auto-plan for run {run['run_id']} before customer delivery approval. "
                "Bind worker output to READ/PLAN/RETRIEVE/COMPARE/EXECUTE/VERIFY/RECORD evidence."
            ),
            "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md", "docs/AGENT_WORK_METHOD_BLOCK.md"],
            "referenced_memories": ["knowledge/shared/common_failures.md", "project_memory"],
            "referenced_bases": ["base_local_tasks", "base_local_memory", "agent_gateway_ledger"],
            "proposed_files_to_change": ["agentops-worker-runtime", "customer-delivery-approval-gate"],
            "risk_level": task["risk_level"] if task else "medium",
            "approval_required": bool(task and task["risk_level"] in {"high", "critical"}),
            "execution_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
            "verification_plan": "Require run/tool/evaluation/artifact/audit evidence and a verified plan_evidence_manifest before delivery approval.",
            "rollback_plan": "Block customer delivery approval and record an audit event if evidence verification fails.",
            "status": "submitted",
        })
        if plan_status >= 400:
            return {"ok": False, "error": "agent_plan_create_failed", "details": plan_payload, "token_omitted": True}
        plan = conn.execute("SELECT * FROM agent_plans WHERE plan_id=?", (plan_payload["agent_plan"]["plan_id"],)).fetchone()
    manifest_payload, manifest_status = agent_gateway_create_plan_evidence_manifest(conn, {
        "workspace_id": run["workspace_id"],
        "agent_id": run["agent_id"],
        "plan_id": plan["plan_id"],
        "run_id": run["run_id"],
        "mismatch_policy": "block",
        "verify_now": True,
    })
    if manifest_status >= 400:
        return {"ok": False, "plan_id": plan["plan_id"], "error": "plan_evidence_manifest_create_failed", "details": manifest_payload, "token_omitted": True}
    manifest = manifest_payload.get("manifest") or {}
    verification = manifest_payload.get("verification") or {}
    return {
        "ok": bool(verification.get("pass")),
        "plan_id": plan["plan_id"],
        "manifest_id": manifest.get("manifest_id"),
        "status": verification.get("status") or manifest.get("status"),
        "verification": verification,
        "reused": False,
        "reason": reason,
        "token_omitted": True,
    }


def agent_gateway_create_plan_evidence_manifest(conn: sqlite3.Connection, body) -> tuple[dict, int]:
    ident = agent_gateway_identity({}, body)
    plan_id = body.get("plan_id")
    run_id = body.get("run_id")
    if not plan_id or not run_id:
        return {"error": "plan_id and run_id are required"}, 400
    plan = conn.execute("SELECT * FROM agent_plans WHERE plan_id=?", (plan_id,)).fetchone()
    if not plan:
        return {"error": "agent plan not found"}, 404
    if plan["workspace_id"] != ident["workspace_id"]:
        return workspace_forbidden("agent_plan", plan_id, ident["workspace_id"], plan["workspace_id"])
    run, access_error = ensure_run_access(conn, run_id, ident)
    if access_error:
        return access_error
    task_id = body.get("task_id") or run["task_id"] or plan["task_id"]
    if plan["task_id"] and task_id != plan["task_id"]:
        return {"error": "forbidden", "message": "Manifest task_id must match the referenced agent_plan."}, 403
    if run["task_id"] and task_id != run["task_id"]:
        return {"error": "forbidden", "message": "Manifest task_id must match the referenced run."}, 403
    if plan["run_id"] and plan["run_id"] != run_id:
        return {"error": "forbidden", "message": "Manifest run_id must match the run pinned by the agent_plan."}, 403
    if plan["agent_id"] != run["agent_id"]:
        return {"error": "forbidden", "message": "Manifest requires agent_plan.agent_id to match run.agent_id."}, 403
    expected_steps = safe_json_list(body.get("expected_steps")) or load_json_list_field(plan, "execution_steps_json")
    row = {
        "manifest_id": body.get("manifest_id") or stable_id("pem", plan_id, run_id, now_iso()),
        "workspace_id": ident["workspace_id"],
        "plan_id": plan_id,
        "task_id": task_id,
        "run_id": run_id,
        "agent_id": run["agent_id"],
        "mismatch_policy": coerce_choice(body.get("mismatch_policy"), {"block", "warn"}, "block"),
        "expected_steps_json": json.dumps(expected_steps, ensure_ascii=False),
        "tool_call_ids_json": json.dumps(safe_json_list(body.get("tool_call_ids")), ensure_ascii=False),
        "evaluation_ids_json": json.dumps(safe_json_list(body.get("evaluation_ids")), ensure_ascii=False),
        "artifact_ids_json": json.dumps(safe_json_list(body.get("artifact_ids")), ensure_ascii=False),
        "audit_ids_json": json.dumps(safe_json_list(body.get("audit_ids")), ensure_ascii=False),
        "status": "submitted",
        "verification_json": "{}",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    conn.execute(
        """INSERT INTO plan_evidence_manifests(manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,
        expected_steps_json,tool_call_ids_json,evaluation_ids_json,artifact_ids_json,audit_ids_json,status,verification_json,created_at,updated_at)
        VALUES(:manifest_id,:workspace_id,:plan_id,:task_id,:run_id,:agent_id,:mismatch_policy,
        :expected_steps_json,:tool_call_ids_json,:evaluation_ids_json,:artifact_ids_json,:audit_ids_json,:status,:verification_json,:created_at,:updated_at)""",
        row,
    )
    audit(conn, "agent", row["agent_id"], "agent_gateway.plan_evidence_manifest_create", "plan_evidence_manifests", row["manifest_id"], None, row, {"raw_omitted": True})
    runtime_event(conn, "rtc_agent_gateway_local", "plan_evidence_manifest.create", "completed", run_id=run_id, task_id=task_id, agent_id=row["agent_id"], output_summary=f"Plan evidence manifest {row['manifest_id']} submitted.")
    verification = verify_plan_evidence_manifest_row(conn, row) if body.get("verify_now", True) is not False else None
    if verification:
        persist_plan_evidence_verification(conn, row["manifest_id"], verification)
        row = dict(conn.execute("SELECT * FROM plan_evidence_manifests WHERE manifest_id=?", (row["manifest_id"],)).fetchone())
    return {
        "provider": "agentops-plan-evidence",
        "operation": "plan_evidence_manifest_create",
        "manifest": row,
        "verification": verification,
        "token_omitted": True,
    }, 201


def agent_gateway_review_queue(conn: sqlite3.Connection, qs: dict, headers, auth_ctx=None) -> tuple[dict, int]:
    ident = agent_gateway_identity(headers, qs=qs, auth_ctx=auth_ctx)
    limit = min(max(int((qs.get("limit") or ["20"])[0]), 1), 100)
    fetch_limit = min(max(limit * 5, 50), 100) if agent_gateway_is_bound_auth(auth_ctx) else limit
    payload = human_review_queue(conn, fetch_limit)

    def visible(row: dict) -> bool:
        if not agent_gateway_is_bound_auth(auth_ctx):
            return True
        task_id = row.get("task_id")
        run_id = row.get("run_id")
        if task_id:
            _task, access_error = agent_gateway_task_read_access(conn, str(task_id), ident, auth_ctx)
            return access_error is None
        if run_id:
            _run, access_error = agent_gateway_run_read_access(conn, str(run_id), ident, auth_ctx)
            return access_error is None
        agent_id = row.get("agent_id") or row.get("requested_by_agent_id") or row.get("owner_agent_id")
        return bool(agent_id and agent_id == ident["agent_id"])

    visible_review_items = [item for item in payload.get("review_items", []) if visible(item)]
    lanes = payload.get("lanes") or {}
    pending_approvals = [item for item in lanes.get("pending_approvals", []) if visible(item)]
    memory_candidates = [item for item in lanes.get("memory_candidates", []) if visible(item)]
    customer_deliveries = [item for item in lanes.get("customer_deliveries", []) if visible(item)]
    review_items = visible_review_items[:limit]
    payload["limit"] = limit
    payload["review_items"] = review_items
    payload["lanes"] = {
        "pending_approvals": pending_approvals[:limit],
        "memory_candidates": memory_candidates[:limit],
        "customer_deliveries": customer_deliveries[:limit],
    }
    payload["summary"] = {
        "pending_approvals": len(pending_approvals),
        "memory_candidates": len(memory_candidates),
        "ready_deliveries": len([item for item in customer_deliveries if item.get("status") == "ready"]),
        "waiting_deliveries": len([item for item in customer_deliveries if item.get("status") == "waiting_approval"]),
        "needs_attention_deliveries": len([item for item in customer_deliveries if item.get("status") == "needs_attention"]),
        "review_items_total": len(visible_review_items),
        "returned_items": len(review_items),
        "retrieved_pending_approvals": len(pending_approvals[:limit]),
        "retrieved_memory_candidates": len(memory_candidates[:limit]),
    }
    if any(payload["summary"].get(key, 0) for key in ["pending_approvals", "memory_candidates", "waiting_deliveries", "needs_attention_deliveries"]):
        payload["status"] = "attention"
    elif payload["summary"].get("ready_deliveries"):
        payload["status"] = "ready"
    else:
        payload["status"] = "empty"
    payload["gateway_scope"] = {
        "required_scope": "tasks:read",
        "workspace_id": ident["workspace_id"],
        "agent_id": ident["agent_id"],
        "auth_mode": (auth_ctx or {}).get("mode") or "unknown",
        "bound_visibility_enforced": agent_gateway_is_bound_auth(auth_ctx),
        "token_omitted": True,
    }
    payload["token_omitted"] = True
    return payload, 200


def agent_gateway_claim_task(conn, task_id: str, body) -> tuple[dict, int]:
    ident = agent_gateway_identity({}, body)
    agent_id = ident["agent_id"]
    if not agent_id:
        return {"error": "agent_id is required"}, 400
    task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not task:
        return {"error": "task not found"}, 404
    actual_workspace = row_workspace(task)
    if actual_workspace != ident["workspace_id"]:
        return workspace_forbidden("task", task_id, ident["workspace_id"], actual_workspace)
    ensure_gateway_agent(conn, agent_id, runtime_type=body.get("runtime_type"))
    before = dict(task)
    if not agent_can_access_task(task, agent_id):
        return {"error": "forbidden", "message": f"Task {task_id} is assigned to another agent.", "owner_agent_id": task["owner_agent_id"]}, 403
    if task["status"] == "running":
        if task["owner_agent_id"] == agent_id:
            return {"task": before, "claimed_by": agent_id, "already_claimed": True}, 200
        return {"error": "conflict", "message": f"Task {task_id} is already running.", "status": task["status"], "owner_agent_id": task["owner_agent_id"]}, 409
    if task["status"] not in {"planned", "backlog"}:
        return {"error": "conflict", "message": f"Task {task_id} cannot be claimed from status {task['status']}.", "status": task["status"], "owner_agent_id": task["owner_agent_id"]}, 409
    cursor = conn.execute(
        """UPDATE tasks SET owner_agent_id=?, status='running', updated_at=?
        WHERE task_id=? AND COALESCE(workspace_id,'local-demo')=? AND status IN ('planned','backlog')""",
        (agent_id, now_iso(), task_id, ident["workspace_id"]),
    )
    if cursor.rowcount != 1:
        current = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return {"error": "conflict", "message": f"Task {task_id} was claimed or changed before this claim completed.", "task": dict(current) if current else None}, 409
    after = dict(conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone())
    runtime_event(conn, "rtc_agent_gateway_local", "task.claim", "completed", task_id=task_id, agent_id=agent_id, output_summary=f"{agent_id} claimed {task_id}.")
    audit(conn, "agent", agent_id, "agent_gateway.task_claim", "tasks", task_id, before, after, {"workspace_id": ident["workspace_id"]})
    return {"task": after, "claimed_by": agent_id}, 200


def agent_gateway_start_run(conn, body) -> tuple[dict, int]:
    task_id = body.get("task_id")
    ident = agent_gateway_identity({}, body)
    agent_id = ident["agent_id"]
    if not task_id or not agent_id:
        return {"error": "task_id and agent_id are required"}, 400
    task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not task:
        return {"error": "task not found"}, 404
    actual_workspace = row_workspace(task)
    if actual_workspace != ident["workspace_id"]:
        return workspace_forbidden("task", task_id, ident["workspace_id"], actual_workspace)
    if not agent_can_access_task(task, agent_id):
        return {"error": "forbidden", "message": f"Task {task_id} is assigned to another agent.", "owner_agent_id": task["owner_agent_id"]}, 403
    if task["status"] == "running" and task["owner_agent_id"] != agent_id:
        return {"error": "conflict", "message": f"Task {task_id} is already running.", "status": task["status"], "owner_agent_id": task["owner_agent_id"]}, 409
    if task["status"] not in {"planned", "backlog", "running"}:
        return {"error": "conflict", "message": f"Task {task_id} cannot start a run from status {task['status']}.", "status": task["status"], "owner_agent_id": task["owner_agent_id"]}, 409
    ensure_gateway_agent(conn, agent_id, runtime_type=body.get("runtime_type"))
    agent = conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
    started = now_iso()
    run_id = body.get("run_id") or new_id("run_gw")
    row = {
        "run_id": run_id,
        "workspace_id": ident["workspace_id"],
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": coerce_choice(body.get("runtime_type") or agent["runtime_type"], VALID_RUNTIME_TYPES, "mock"),
        "status": coerce_choice(body.get("status"), {"running", "completed", "failed", "blocked", "waiting_approval"}, "running"),
        "started_at": body.get("started_at") or started,
        "ended_at": body.get("ended_at"),
        "duration_ms": parse_ms(body.get("duration_ms")),
        "input_summary": redact_text(body.get("input_summary") or task["title"], 200),
        "output_summary": redact_text(body.get("output_summary"), 200) if body.get("output_summary") else None,
        "model_provider": redact_text(body.get("model_provider") or agent["model_provider"] or "external", 80),
        "model_name": redact_text(body.get("model_name") or agent["model_name"] or "gateway-client", 120),
        "input_tokens": int(body.get("input_tokens") or 0),
        "output_tokens": int(body.get("output_tokens") or 0),
        "reasoning_tokens": int(body.get("reasoning_tokens") or 0),
        "cost_usd": float(body.get("cost_usd") or 0),
        "error_type": redact_text(body.get("error_type"), 80) if body.get("error_type") else None,
        "error_message": redact_text(body.get("error_message"), 200) if body.get("error_message") else None,
        "trace_id": body.get("trace_id") or new_id("trace"),
        "parent_run_id": body.get("parent_run_id"),
        "delegation_id": body.get("delegation_id") or stable_id("del", "agent_gateway", task_id, agent_id),
        "approval_required": 1 if body.get("approval_required") else 0,
        "created_at": started,
    }
    outcome = upsert_run(conn, row, "agent-gateway", {"workspace_id": ident["workspace_id"], "input_hash": stable_hash(body.get("input_summary") or task["title"])})
    conn.execute("UPDATE tasks SET status='running', owner_agent_id=COALESCE(NULLIF(owner_agent_id,''), ?), updated_at=? WHERE task_id=?", (agent_id, now_iso(), task_id))
    conn.execute("UPDATE agents SET status='running', updated_at=? WHERE agent_id=?", (now_iso(), agent_id))
    runtime_event(conn, "rtc_agent_gateway_local", "run.start", "running", task_id=task_id, run_id=run_id, agent_id=agent_id, input_summary=row["input_summary"])
    return {"run": row, "outcome": outcome}, 201 if outcome == "created" else 200


def agent_gateway_run_heartbeat(conn, run_id: str, body) -> tuple[dict, int]:
    ident = agent_gateway_identity({}, body)
    before, access_error = ensure_run_access(conn, run_id, ident)
    if access_error:
        return access_error
    status = coerce_choice(body.get("status"), {"running", "completed", "failed", "blocked", "waiting_approval"}, before["status"])
    ended_at = body.get("ended_at")
    if status in {"completed", "failed", "blocked"} and not ended_at:
        ended_at = now_iso()
    output_summary = redact_text(body.get("output_summary"), 200) if body.get("output_summary") else before["output_summary"]
    duration_ms = parse_ms(body.get("duration_ms"))
    if duration_ms is None:
        duration_ms = before["duration_ms"]
    conn.execute(
        """UPDATE runs SET status=?, ended_at=?, duration_ms=?, output_summary=?, error_type=?, error_message=?, output_tokens=?, cost_usd=?
        WHERE run_id=?""",
        (
            status,
            ended_at,
            duration_ms,
            output_summary,
            redact_text(body.get("error_type"), 80) if body.get("error_type") else before["error_type"],
            redact_text(body.get("error_message"), 200) if body.get("error_message") else before["error_message"],
            int(body.get("output_tokens") or before["output_tokens"] or 0),
            float(body.get("cost_usd") if body.get("cost_usd") is not None else before["cost_usd"] or 0),
            run_id,
        ),
    )
    if status in {"completed", "failed", "blocked"}:
        task_status = "completed" if status == "completed" else "blocked" if status == "blocked" else "failed"
        conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE task_id=?", (task_status, now_iso(), before["task_id"]))
        conn.execute("UPDATE agents SET status='idle', updated_at=? WHERE agent_id=?", (now_iso(), before["agent_id"]))
    after = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    runtime_event(conn, "rtc_agent_gateway_local", "run.heartbeat", status, run_id=run_id, task_id=before["task_id"], agent_id=before["agent_id"], output_summary=output_summary, error_message=body.get("error_message"))
    audit(conn, "agent", before["agent_id"], "agent_gateway.run_heartbeat", "runs", run_id, dict(before), dict(after), {"status": status})
    return {"run": dict(after)}, 200


def agent_gateway_record_tool_call(conn, body) -> tuple[dict, int]:
    run_id = body.get("run_id")
    ident = agent_gateway_identity({}, body)
    run, access_error = ensure_run_access(conn, run_id, ident)
    if access_error:
        return access_error
    agent_id = body.get("agent_id")
    if not agent_id:
        agent_id = run["agent_id"]
    ensure_gateway_agent(conn, agent_id, runtime_type=body.get("runtime_type"))
    tool_name = redact_text(body.get("tool_name") or "agent_gateway.note", 120)
    risk = coerce_choice(body.get("risk_level") or ("high" if tool_name in RISKY_TOOLS else "low"), VALID_RISK_LEVELS, "low")
    category = coerce_choice(body.get("tool_category"), VALID_TOOL_CATEGORIES, "custom")
    status = coerce_choice(body.get("status"), {"planned", "running", "completed", "failed", "blocked", "waiting_approval"}, "completed" if risk in {"low", "medium"} else "waiting_approval")
    args = safe_json_metadata(body.get("normalized_args_json") or body.get("args") or {"summary": body.get("args_summary") or "redacted"})
    row = {
        "tool_call_id": body.get("tool_call_id") or new_id("tc_gw"),
        "run_id": run_id,
        "agent_id": agent_id,
        "tool_name": tool_name,
        "tool_version": redact_text(body.get("tool_version") or "v1", 40),
        "tool_category": category,
        "normalized_args_json": json.dumps(args, ensure_ascii=False),
        "target_resource": redact_text(body.get("target_resource"), 200) if body.get("target_resource") else None,
        "risk_level": risk,
        "status": status,
        "result_summary": redact_text(body.get("result_summary"), 200) if body.get("result_summary") else None,
        "side_effect_id": body.get("side_effect_id"),
        "started_at": body.get("started_at") or now_iso(),
        "ended_at": body.get("ended_at") or (now_iso() if status in {"completed", "failed", "blocked"} else None),
        "created_at": now_iso(),
    }
    outcome = upsert_tool_call(conn, row, "agent-gateway", {"args_hash": stable_hash(args), "raw_omitted": True})
    if risk in {"high", "critical"} or status == "waiting_approval":
        conn.execute("UPDATE runs SET approval_required=1, status='waiting_approval' WHERE run_id=?", (run_id,))
        conn.execute("UPDATE tasks SET status='waiting_approval', updated_at=? WHERE task_id=?", (now_iso(), run["task_id"]))
    runtime_event(conn, "rtc_agent_gateway_local", "tool_call.record", status, run_id=run_id, task_id=run["task_id"], agent_id=agent_id, output_summary=f"{tool_name}: {row['result_summary'] or status}", raw_payload_hash=stable_hash(args))
    return {"tool_call": row, "outcome": outcome}, 201 if outcome == "created" else 200


def agent_gateway_request_approval(conn, body) -> tuple[dict, int]:
    run_id = body.get("run_id")
    ident = agent_gateway_identity({}, body)
    run, access_error = ensure_run_access(conn, run_id, ident)
    if access_error:
        return access_error
    approval_id = body.get("approval_id") or new_id("ap_gw")
    tool_call_id = body.get("tool_call_id")
    if body.get("task_id") and body.get("task_id") != run["task_id"]:
        return {"error": "forbidden", "message": "Approval task_id must match the target run."}, 403
    if tool_call_id:
        tool_call = conn.execute("SELECT run_id FROM tool_calls WHERE tool_call_id=?", (tool_call_id,)).fetchone()
        if not tool_call:
            return {"error": "tool call not found"}, 404
        if tool_call["run_id"] != run_id:
            return {"error": "forbidden", "message": "Approval tool_call_id must belong to the target run."}, 403
    reason = redact_text(body.get("reason") or "Agent requested approval for an external or high-risk action.", 260)
    row = {
        "approval_id": approval_id,
        "task_id": run["task_id"],
        "run_id": run_id,
        "tool_call_id": tool_call_id,
        "requested_by_agent_id": body.get("requested_by_agent_id") or body.get("agent_id") or run["agent_id"],
        "approver_user_id": body.get("approver_user_id") or "usr_founder",
        "decision": "pending",
        "reason": reason,
        "expires_at": body.get("expires_at") or (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat(),
        "created_at": now_iso(),
        "decided_at": None,
    }
    before_approval, _approval_outcome = repo_upsert_approval(conn, row)
    conn.execute("UPDATE runs SET approval_required=1, status='waiting_approval' WHERE run_id=?", (run_id,))
    conn.execute("UPDATE tasks SET status='waiting_approval', updated_at=? WHERE task_id=?", (now_iso(), row["task_id"]))
    runtime_event(conn, "rtc_agent_gateway_local", "approval.request", "waiting_approval", run_id=run_id, task_id=row["task_id"], agent_id=row["requested_by_agent_id"], output_summary=reason)
    audit(conn, "agent", row["requested_by_agent_id"], "agent_gateway.approval_request", "approvals", approval_id, dict(before_approval) if before_approval else None, row, {"raw_omitted": True})
    return {"approval": row}, 201


def agent_gateway_memory_propose(conn, body) -> tuple[dict, int]:
    agent_id = body.get("agent_id")
    task_id = body.get("task_id")
    text = body.get("canonical_text") or body.get("text")
    if not agent_id or not text:
        return {"error": "agent_id and canonical_text are required"}, 400
    ident = agent_gateway_identity({}, body)
    if body.get("run_id"):
        _run, access_error = ensure_run_access(conn, body["run_id"], ident)
        if access_error:
            return access_error
    elif task_id:
        task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if task and row_workspace(task) != ident["workspace_id"]:
            return workspace_forbidden("task", task_id, ident["workspace_id"], row_workspace(task))
    ensure_gateway_agent(conn, agent_id, runtime_type=body.get("runtime_type"))
    memory_id = body.get("memory_id") or stable_id("mem_gw", agent_id, task_id or "project", stable_hash(text)[:12])
    row = {
        "memory_id": memory_id,
        "workspace_id": ident["workspace_id"],
        "scope": coerce_choice(body.get("scope"), {"task", "project", "org"}, "project"),
        "memory_type": coerce_choice(body.get("memory_type"), {"policy", "sop", "decision", "commitment", "risk", "failure_case", "project_context", "customer_preference", "agent_lesson", "artifact_summary"}, "artifact_summary"),
        "canonical_text": redact_text(text, 360),
        "source_type": coerce_choice(body.get("source_type"), {"chat", "email", "meeting", "github", "notion", "run_log", "manual"}, "run_log"),
        "source_ref": redact_text(body.get("source_ref") or body.get("run_id") or "agent-gateway", 200),
        "project_id": body.get("project_id") or "proj_mvp",
        "task_id": task_id,
        "agent_id": agent_id,
        "confidence": float(body.get("confidence") or 0.72),
        "review_status": "candidate",
        "owner_user_id": body.get("owner_user_id") or "usr_founder",
        "ttl_review_due_at": body.get("ttl_review_due_at") or (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).isoformat(),
        "supersedes_memory_id": body.get("supersedes_memory_id"),
        "access_tags": json.dumps([redact_text(item, 80) for item in (body.get("access_tags") or ["agent-gateway", "review"])], ensure_ascii=False),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    outcome = upsert_memory_candidate(conn, row, "agent-gateway")
    runtime_event(conn, "rtc_agent_gateway_local", "memory.propose", "completed", task_id=task_id, agent_id=agent_id, output_summary=row["canonical_text"])
    return {"memory": row, "outcome": outcome}, 201 if outcome == "created" else 200


def agent_gateway_eval_submit(conn, body) -> tuple[dict, int]:
    run_id = body.get("run_id")
    ident = agent_gateway_identity({}, body)
    run, access_error = ensure_run_access(conn, run_id, ident)
    if access_error:
        return access_error
    if body.get("task_id") and body.get("task_id") != run["task_id"]:
        return {"error": "forbidden", "message": "Evaluation task_id must match the target run."}, 403
    score = float(body.get("score") if body.get("score") is not None else 1.0)
    score = max(0.0, min(score, 1.0))
    pass_fail = "pass" if body.get("pass_fail", "pass") == "pass" and score >= 0.5 else "fail"
    rubric = safe_json_metadata(body.get("rubric") or body.get("rubric_json") or {"submitted_by": "agent_gateway"})
    row = {
        "evaluation_id": body.get("evaluation_id") or stable_id("eval_gw", run_id, body.get("evaluator_type") or "rule"),
        "task_id": run["task_id"],
        "run_id": run_id,
        "agent_id": body.get("agent_id") or run["agent_id"],
        "evaluator_type": coerce_choice(body.get("evaluator_type"), {"human", "rule", "llm_mock"}, "rule"),
        "score": score,
        "pass_fail": pass_fail,
        "rubric_json": json.dumps(rubric, ensure_ascii=False),
        "notes": redact_text(body.get("notes") or "Submitted through Agent Gateway.", 260),
        "created_at": now_iso(),
    }
    outcome = upsert_evaluation(conn, row, "agent-gateway")
    runtime_event(conn, "rtc_agent_gateway_local", "evaluation.submit", pass_fail, run_id=run_id, task_id=row["task_id"], agent_id=row["agent_id"], output_summary=row["notes"])
    return {"evaluation": row, "outcome": outcome}, 201 if outcome == "created" else 200


def agent_gateway_record_artifact(conn, body) -> tuple[dict, int]:
    run_id = body.get("run_id")
    ident = agent_gateway_identity({}, body)
    run, access_error = ensure_run_access(conn, run_id, ident)
    if access_error:
        return access_error
    artifact_id = body.get("artifact_id") or stable_id("art_gw", run_id, body.get("title") or body.get("artifact_type") or "artifact")
    row = {
        "artifact_id": artifact_id,
        "task_id": run["task_id"],
        "run_id": run_id,
        "artifact_type": redact_text(body.get("artifact_type") or "report", 80),
        "title": redact_text(body.get("title") or "Agent Gateway Artifact", 160),
        "uri": redact_text(body.get("uri") or f"run://{run_id}", 240),
        "summary": redact_text(body.get("summary") or body.get("content_summary") or "Artifact summary recorded through Agent Gateway.", 360),
        "created_at": body.get("created_at") or now_iso(),
    }
    before_artifact, _artifact_outcome = repo_upsert_artifact(conn, row)
    metadata = safe_json_metadata({
        "workspace_id": ident["workspace_id"],
        "content_hash": body.get("content_hash"),
        "raw_content_omitted": True,
    })
    runtime_event(conn, "rtc_agent_gateway_local", "artifact.record", "completed", run_id=run_id, task_id=row["task_id"], agent_id=run["agent_id"], output_summary=row["summary"], raw_payload_hash=body.get("content_hash"))
    audit(conn, "agent", run["agent_id"], "agent_gateway.artifact_record", "artifacts", artifact_id, dict(before_artifact) if before_artifact else None, row, metadata)
    return {"artifact": row}, 201


def agent_gateway_emit_audit(conn, body) -> tuple[dict, int]:
    agent_id = body.get("agent_id") or "agent-gateway"
    if body.get("run_id"):
        ident = agent_gateway_identity({}, body)
        _run, access_error = ensure_run_access(conn, body["run_id"], ident)
        if access_error:
            return access_error
    entity_type = body.get("entity_type") or "agent_gateway"
    entity_id = body.get("entity_id") or body.get("run_id") or agent_id
    action = body.get("action") or "agent_gateway.audit_emit"
    metadata = safe_json_metadata(body.get("metadata") or {})
    audit(conn, "agent", agent_id, redact_text(action, 160), redact_text(entity_type, 80), redact_text(entity_id, 160), None, safe_json_metadata(body.get("after") or {"status": "emitted"}), metadata)
    runtime_event(conn, "rtc_agent_gateway_local", "audit.emit", "completed", run_id=body.get("run_id"), task_id=body.get("task_id"), agent_id=agent_id, output_summary=f"Audit emitted: {redact_text(action, 120)}")
    return {"emitted": True, "entity_type": entity_type, "entity_id": entity_id}, 201


def run_openclaw_probe(conn) -> dict:
    for connector in runtime_connector_rows():
        if connector["runtime_connector_id"] == "rtc_openclaw_local":
            upsert_runtime_connector(conn, connector)
            break
    agent_id = "agt_oc_main"
    cfg = read_json_file(OPENCLAW_HOME / "openclaw.json", {})
    defaults = cfg.get("agents", {}).get("defaults", {}) if isinstance(cfg, dict) else {}
    model_cfg = defaults.get("model") if isinstance(defaults, dict) else None
    default_model = model_cfg.get("primary") if isinstance(model_cfg, dict) else model_cfg
    provider, model_name = split_provider_model(default_model, "openclaw")
    upsert_agent(conn, {
        "agent_id": agent_id,
        "name": "OpenClaw main",
        "role": "Runtime Orchestrator",
        "description": "Manual OpenClaw live probe agent.",
        "runtime_type": "openclaw",
        "model_provider": provider,
        "model_name": model_name,
        "status": "idle",
        "permission_level": "manager",
        "allowed_tools": json.dumps(["openclaw.agent", "probe.run"], ensure_ascii=False),
        "budget_limit_usd": 10.0,
        "owner_user_id": "usr_founder",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, "openclaw-probe")
    task_id = "tsk_openclaw_manual_probe"
    upsert_task(conn, {
        "task_id": task_id,
        "title": "OpenClaw manual live probe",
        "description": "Manual probe that asks OpenClaw main agent to return a fixed health marker.",
        "requester_id": "usr_founder",
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
        "status": "running",
        "priority": "high",
        "due_date": None,
        "acceptance_criteria": "OpenClaw returns OPENCLAW_MIS_PROBE_OK.",
        "risk_level": "low",
        "budget_limit_usd": 1.0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, "openclaw-probe")
    started = now_iso()
    probe = {"ok": False, "error": None}
    if not OPENCLAW_BIN.exists():
        probe["error"] = f"missing {OPENCLAW_BIN}"
    else:
        try:
            proc = subprocess.run(
                [str(OPENCLAW_BIN), "agent", "--agent", "main", "-m", "请只回复 OPENCLAW_MIS_PROBE_OK", "--timeout", "180", "--json"],
                capture_output=True, text=True, timeout=210, check=False,
            )
            payload = json.loads(proc.stdout) if proc.stdout else {}
            meta = (payload.get("result") or {}).get("meta") or {}
            visible = meta.get("finalAssistantVisibleText") or (((payload.get("result") or {}).get("payloads") or [{}])[0].get("text"))
            agent_meta = meta.get("agentMeta") or {}
            probe.update({
                "ok": proc.returncode == 0 and visible == "OPENCLAW_MIS_PROBE_OK",
                "run_id": payload.get("runId"),
                "visible": visible,
                "duration_ms": meta.get("durationMs"),
                "provider": agent_meta.get("provider"),
                "model": agent_meta.get("model"),
                "usage": agent_meta.get("usage") or {},
            })
            if not probe["ok"]:
                probe["error"] = redact_text(proc.stderr or visible or "probe failed", 200)
        except Exception as exc:
            probe["error"] = redact_text(str(exc), 200)
    run_id = stable_id("run_oc_probe", dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))
    usage = probe.get("usage") or {}
    row = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": "openclaw",
        "status": "completed" if probe["ok"] else "failed",
        "started_at": started,
        "ended_at": now_iso(),
        "duration_ms": parse_ms(probe.get("duration_ms")),
        "input_summary": "Manual OpenClaw live probe.",
        "output_summary": "OpenClaw returned OPENCLAW_MIS_PROBE_OK." if probe["ok"] else "OpenClaw probe failed.",
        "model_provider": probe.get("provider") or provider,
        "model_name": probe.get("model") or model_name,
        "input_tokens": int(usage.get("input") or usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("output") or usage.get("output_tokens") or 0),
        "reasoning_tokens": int(usage.get("reasoning_tokens") or 0),
        "cost_usd": 0.0,
        "error_type": None if probe["ok"] else "OpenClawProbeFailed",
        "error_message": probe.get("error"),
        "trace_id": probe.get("run_id"),
        "parent_run_id": None,
        "delegation_id": None,
        "approval_required": 0,
        "created_at": started,
    }
    upsert_run(conn, row, "openclaw-probe", {"manual_probe": True})
    upsert_evaluation(conn, quality_gate_for_run(row), "openclaw-probe")
    runtime_event(conn, "rtc_openclaw_local", "agent_probe", "completed" if probe["ok"] else "failed", run_id=run_id, task_id=task_id, agent_id=agent_id, model_name=row["model_name"], latency_ms=row["duration_ms"], output_summary=probe.get("visible"), error_message=probe.get("error"), raw_payload_hash=stable_hash({"trace_id": probe.get("run_id"), "visible": probe.get("visible"), "error": probe.get("error")}))
    audit(conn, "system", "openclaw-probe", "runtime.openclaw_probe", "runs", run_id, None, {"status": row["status"]}, {"manual_probe": True, "trace_id": probe.get("run_id")})
    return {"provider": "openclaw", "probe": probe, "run_id": run_id}


def hermes_status() -> dict:
    hermes = hermes_runtime_config()
    agnes = agnesfallback_config()
    default_api_listening = url_listening(hermes["gateway_url"])
    agnes_api_listening = url_listening(agnes["gateway_url"])
    agnes_bin_exists = Path(agnes["binary_path"]).exists()
    return {
        "provider": "hermes",
        "home": str(HERMES_HOME),
        "home_exists": HERMES_HOME.exists(),
        "gateway_pid_file": (HERMES_HOME / "gateway.pid").exists(),
        "launch_agent_hint": "ai.hermes.gateway",
        "profile": hermes["profile"],
        "gateway_url": hermes["gateway_url"],
        "runtime_mode": hermes["runtime_mode"],
        "real_run_enabled": hermes["allow_real_run"],
        "requires_confirm_run": hermes["require_confirm_run"],
        "api_port": urlparse(hermes["gateway_url"]).port or 8642,
        "api_listening": default_api_listening,
        "config_exists": (HERMES_HOME / "config.yaml").exists(),
        "auth_exists": (HERMES_HOME / "auth.json").exists(),
        "default_gateway": {
            "connector_id": "rtc_hermes_default_gateway",
            "profile": hermes["profile"],
            "gateway_url": hermes["gateway_url"],
            "api_server_listening": default_api_listening,
            "mode": hermes["runtime_mode"],
            "last_error": None if default_api_listening else "Default Hermes API gateway is not listening.",
        },
        "agnesfallback": {
            "cli_connector_id": "rtc_agnesfallback_cli",
            "api_connector_id": "rtc_agnesfallback_openai_api",
            "profile": agnes["profile"],
            "binary_path": agnes["binary_path"],
            "binary_exists": agnes_bin_exists,
            "gateway_url": agnes["gateway_url"],
            "api_server_listening": agnes_api_listening,
            "real_run_enabled": hermes["allow_real_run"],
            "requires_confirm_run": hermes["require_confirm_run"],
            "last_error": None if (agnes_bin_exists or agnes_api_listening) else "Agnesfallback CLI/API are unavailable in the current environment.",
        },
    }


def refresh_runtime_connectors(conn, status: dict | None = None):
    status = status or hermes_status()
    for row in runtime_connector_rows():
        if row["runtime_connector_id"] == "rtc_hermes_default_gateway":
            row["status"] = "available" if status["default_gateway"]["api_server_listening"] else "unavailable"
            row["last_health_at"] = now_iso()
            row["last_error"] = status["default_gateway"]["last_error"]
        elif row["runtime_connector_id"] == "rtc_agnesfallback_cli":
            row["status"] = "available" if status["agnesfallback"]["binary_exists"] else "unavailable"
            row["last_health_at"] = now_iso()
            row["last_error"] = None if status["agnesfallback"]["binary_exists"] else "AGNESFALLBACK_BIN not found."
        elif row["runtime_connector_id"] == "rtc_agnesfallback_openai_api":
            row["status"] = "available" if status["agnesfallback"]["api_server_listening"] else "unavailable"
            row["last_health_at"] = now_iso()
            row["last_error"] = None if status["agnesfallback"]["api_server_listening"] else "Agnesfallback OpenAI-compatible API is not listening."
        upsert_runtime_connector(conn, row)


def run_hermes_probe(conn) -> dict:
    status = hermes_status()
    refresh_runtime_connectors(conn, status)
    agent_id = "agt_hermes_gateway"
    upsert_agent(conn, {
        "agent_id": agent_id,
        "name": "Hermes Gateway",
        "role": "Hermes Runtime Gateway",
        "description": "Local Hermes gateway health probe target.",
        "runtime_type": "hermes",
        "model_provider": "hermes",
        "model_name": "gateway",
        "status": "idle" if status["api_listening"] else "error",
        "permission_level": "manager",
        "allowed_tools": json.dumps(["hermes.gateway", "health.probe"], ensure_ascii=False),
        "budget_limit_usd": 10.0,
        "owner_user_id": "usr_founder",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, "hermes-probe")
    task_id = "tsk_hermes_health_probe"
    upsert_task(conn, {
        "task_id": task_id,
        "title": "Hermes gateway health probe",
        "description": "Manual Hermes probe that records local gateway availability.",
        "requester_id": "usr_founder",
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
        "status": "completed" if status["api_listening"] else "failed",
        "priority": "high",
        "due_date": None,
        "acceptance_criteria": "Hermes API server listens on 127.0.0.1:8642.",
        "risk_level": "low",
        "budget_limit_usd": 1.0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, "hermes-probe")
    run_id = stable_id("run_hermes_probe", dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))
    started = now_iso()
    row = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": "hermes",
        "status": "completed" if status["api_listening"] else "failed",
        "started_at": started,
        "ended_at": now_iso(),
        "duration_ms": 1,
        "input_summary": "Manual Hermes gateway health probe.",
        "output_summary": "Hermes API is listening." if status["api_listening"] else "Hermes API unavailable on 127.0.0.1:8642.",
        "model_provider": "hermes",
        "model_name": "gateway",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.0,
        "error_type": None if status["api_listening"] else "HermesUnavailable",
        "error_message": None if status["api_listening"] else "Hermes launch agent may be running, but API port 8642 is not listening.",
        "trace_id": None,
        "parent_run_id": None,
        "delegation_id": "ai.hermes.gateway",
        "approval_required": 0,
        "created_at": started,
    }
    upsert_run(conn, row, "hermes-probe", status)
    upsert_evaluation(conn, quality_gate_for_run(row), "hermes-probe")
    runtime_event(
        conn,
        "rtc_hermes_default_gateway",
        "health_probe",
        "completed" if status["api_listening"] else "unavailable",
        run_id=run_id,
        task_id=task_id,
        agent_id=agent_id,
        latency_ms=1,
        output_summary=row["output_summary"],
        error_message=row["error_message"],
        raw_payload_hash=stable_hash(status),
    )
    return {"provider": "hermes", "status": status, "run_id": run_id}


def hermes_models(conn) -> dict:
    status = hermes_status()
    refresh_runtime_connectors(conn, status)
    agnes = status["agnesfallback"]
    url = agnes["gateway_url"].rstrip("/") + "/v1/models"
    started = dt.datetime.now(dt.timezone.utc)
    try:
        with urlopen(Request(url, method="GET"), timeout=8) as res:
            payload = json.loads(res.read().decode("utf-8"))
        latency = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
        runtime_event(conn, "rtc_agnesfallback_openai_api", "models_probe", "completed", model_name="agnesfallback", latency_ms=latency, output_summary="Agnesfallback models endpoint responded.", raw_payload_hash=stable_hash(payload))
        audit(conn, "system", "hermes-models", "runtime.models", "runtime_connectors", "rtc_agnesfallback_openai_api", None, {"status": "completed"}, {"payload_hash": stable_hash(payload)})
        conn.commit()
        return {"provider": "agnesfallback", "status": "available", "gateway_url": agnes["gateway_url"], "models": payload.get("data", payload)}
    except Exception as exc:
        err = redact_text(str(exc), 240)
        runtime_event(conn, "rtc_agnesfallback_openai_api", "models_probe", "unavailable", error_message=err)
        audit(conn, "system", "hermes-models", "runtime.models.unavailable", "runtime_connectors", "rtc_agnesfallback_openai_api", None, {"status": "unavailable"}, {"error": err})
        conn.commit()
        return {"provider": "agnesfallback", "status": "unavailable", "gateway_url": agnes["gateway_url"], "models": [], "error": err}


def is_local_or_private_url(value: str) -> bool:
    parsed = urlparse(value or "")
    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return host.endswith(".local") or host.endswith(".internal")


def dify_config() -> dict:
    base_url = os.environ.get("DIFY_API_BASE_URL", os.environ.get("DIFY_BASE_URL", "http://127.0.0.1:8088/v1")).strip().rstrip("/")
    mode = os.environ.get("DIFY_TRUST_MODE", "").strip()
    if not mode:
        mode = "local_dify" if is_local_or_private_url(base_url) else "cloud_dify"
    api_key = os.environ.get("DIFY_KB_API_KEY", os.environ.get("DIFY_API_KEY", "")).strip()
    dataset_id = os.environ.get("DIFY_DATASET_ID", "").strip()
    allow_real_upload = os.environ.get("DIFY_ALLOW_REAL_UPLOAD", "").strip().lower() in ("1", "true", "yes")
    require_approval_env = os.environ.get("DIFY_REQUIRE_APPROVAL", "").strip().lower()
    if require_approval_env:
        require_approval = require_approval_env not in ("0", "false", "no")
    else:
        require_approval = mode != "local_dify"
    return {
        "provider": "dify",
        "api_base_url": base_url,
        "trust_mode": coerce_choice(mode, {"local_dify", "customer_server_dify", "cloud_dify"}, "cloud_dify"),
        "has_api_key": bool(api_key),
        "api_key": api_key,
        "dataset_id": dataset_id,
        "has_dataset_id": bool(dataset_id),
        "allow_real_upload": allow_real_upload,
        "require_approval": require_approval,
        "same_trust_domain": is_local_or_private_url(base_url),
        "api_listening": url_listening(base_url),
    }


def dify_status(conn=None) -> dict:
    cfg = dify_config()
    status = "available" if cfg["api_listening"] and cfg["has_api_key"] else "dry_run" if cfg["api_listening"] else "unavailable"
    payload = {
        "provider": "dify",
        "connector_id": "conn_dify_knowledge",
        "api_base_url": cfg["api_base_url"],
        "trust_mode": cfg["trust_mode"],
        "same_trust_domain": cfg["same_trust_domain"],
        "api_listening": cfg["api_listening"],
        "configured": cfg["api_listening"] and cfg["has_api_key"] and cfg["has_dataset_id"],
        "has_api_key": cfg["has_api_key"],
        "has_dataset_id": cfg["has_dataset_id"],
        "allow_real_upload": cfg["allow_real_upload"],
        "require_approval": cfg["require_approval"],
        "dry_run_default": not cfg["allow_real_upload"],
        "write_behavior": "local/private Dify may run with confirm_upload; cloud or cross-domain upload requires approval.",
    }
    if conn:
        conn.execute(
            "UPDATE connectors SET status=?, last_checked_at=?, last_error=?, writeback_allowed=?, updated_at=? WHERE connector_id='conn_dify_knowledge'",
            (
                status,
                now_iso(),
                None if payload["configured"] else "Dify needs reachable API, API key and dataset id for live upload.",
                1 if cfg["allow_real_upload"] else 0,
                now_iso(),
            ),
        )
    return payload


def ensure_dify_agent_task(conn, body: dict):
    now = now_iso()
    agent_id = body.get("agent_id") or "agt_gw_kb_builder"
    ensure_gateway_agent(conn, agent_id, name="Knowledge Base Builder Agent", role="Knowledge Base Builder", runtime_type="mock")
    task_id = body.get("task_id") or stable_id("tsk_dify_upload", body.get("dataset_id") or dify_config()["dataset_id"] or "local", body.get("document_name") or "document")
    if not conn.execute("SELECT 1 FROM tasks WHERE task_id=?", (task_id,)).fetchone():
        upsert_task(conn, {
            "task_id": task_id,
            "title": body.get("task_title") or "Dify knowledge base ingestion",
            "description": "Agent-managed Dify document ingestion. MIS stores only summary, hashes, ids and audit evidence.",
            "requester_id": body.get("requester_id") or "usr_founder",
            "owner_agent_id": agent_id,
            "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
            "status": "planned",
            "priority": coerce_choice(body.get("priority"), VALID_PRIORITIES, "high"),
            "due_date": None,
            "acceptance_criteria": "Dify receives the approved document, and MIS records run/tool/eval/audit without storing raw credentials or full source text.",
            "risk_level": coerce_choice(body.get("risk_level"), VALID_RISK_LEVELS, "high"),
            "budget_limit_usd": float(body.get("budget_limit_usd") or 1.0),
            "created_at": now,
            "updated_at": now,
        }, "dify-connector")
    return agent_id, task_id


def approval_is_approved(conn, approval_id: str | None) -> bool:
    if not approval_id:
        return False
    row = conn.execute("SELECT decision FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
    return bool(row and row["decision"] == "approved")


def dify_create_document_by_text(conn, body: dict) -> dict:
    cfg = dify_config()
    status_payload = dify_status(conn)
    confirm = bool(body.get("confirm_upload"))
    dataset_id = body.get("dataset_id") or cfg["dataset_id"]
    document_name = redact_text(body.get("document_name") or body.get("name") or "AgentOps MIS document", 120)
    text = body.get("text") or body.get("document_text") or ""
    text_hash = stable_hash(text)
    text_preview = redact_text(text, 200)
    agent_id, task_id = ensure_dify_agent_task(conn, {**body, "dataset_id": dataset_id, "document_name": document_name})
    approval_ok = not cfg["require_approval"] or approval_is_approved(conn, body.get("approval_id"))
    can_upload = bool(cfg["allow_real_upload"] and confirm and cfg["has_api_key"] and dataset_id and text and approval_ok)
    plan = {
        "provider": "dify",
        "mode": cfg["trust_mode"],
        "dry_run": True,
        "configured": status_payload["configured"],
        "would_post": f"{cfg['api_base_url']}/datasets/{dataset_id or '[dataset_id]'}/document/create-by-text",
        "document_name": document_name,
        "text_preview": text_preview,
        "text_hash": text_hash,
        "requires": {
            "DIFY_ALLOW_REAL_UPLOAD": True,
            "confirm_upload": True,
            "DIFY_KB_API_KEY": True,
            "DIFY_DATASET_ID_or_body_dataset_id": True,
            "approved_approval_id": cfg["require_approval"],
        },
        "trust_boundary": {
            "same_trust_domain": cfg["same_trust_domain"],
            "require_approval": cfg["require_approval"],
            "approval_ok": approval_ok,
        },
        "note": "MIS never stores the full document text or API key. Live upload sends the provided text to Dify only when explicitly allowed.",
    }
    if not can_upload:
        runtime_event(conn, "rtc_agent_gateway_local", "dify.upload_text.dry_run", "planned", task_id=task_id, agent_id=agent_id, input_summary=f"Dify upload dry-run text_hash={text_hash[:16]}", raw_payload_hash=text_hash)
        audit(conn, "agent", agent_id, "dify.upload_text.dry_run", "connectors", "conn_dify_knowledge", None, plan, {"confirm_upload": confirm, "approval_id": body.get("approval_id"), "text_hash": text_hash})
        conn.commit()
        return plan

    started_iso = now_iso()
    started = dt.datetime.now(dt.timezone.utc)
    run_id = body.get("run_id") or stable_id("run_dify_upload", dataset_id, document_name, dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))
    payload = {
        "name": document_name,
        "text": text,
        "indexing_technique": body.get("indexing_technique") or "high_quality",
        "process_rule": body.get("process_rule") or {"mode": "automatic"},
    }
    ok = False
    error = None
    response_hash = None
    document_id = None
    try:
        req = Request(
            f"{cfg['api_base_url']}/datasets/{dataset_id}/document/create-by-text",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {cfg['api_key']}"},
        )
        with urlopen(req, timeout=60) as res:
            response = json.loads(res.read().decode("utf-8"))
        response_hash = stable_hash(response)
        document = response.get("document") or response.get("data") or response
        document_id = document.get("id") if isinstance(document, dict) else None
        ok = True
    except Exception as exc:
        error = redact_text(str(exc), 240)

    duration = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    row = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": "mock",
        "status": "completed" if ok else "failed",
        "started_at": started_iso,
        "ended_at": now_iso(),
        "duration_ms": duration,
        "input_summary": f"Dify upload text_hash={text_hash[:16]} dataset_id={redact_text(dataset_id, 80)}",
        "output_summary": f"Dify document created: {document_id}" if ok else "Dify document upload failed.",
        "model_provider": "dify",
        "model_name": "knowledge-api",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.0,
        "error_type": None if ok else "DifyUploadFailed",
        "error_message": error,
        "trace_id": body.get("trace_id"),
        "parent_run_id": body.get("parent_run_id"),
        "delegation_id": body.get("delegation_id") or "dify:knowledge-upload",
        "approval_required": 1 if cfg["require_approval"] else 0,
        "created_at": started_iso,
    }
    upsert_run(conn, row, "dify-connector", {"text_hash": text_hash, "response_hash": response_hash, "document_id": document_id, "dataset_id": redact_text(dataset_id, 80)})
    tool_row = {
        "tool_call_id": body.get("tool_call_id") or stable_id("tc_dify_upload", run_id),
        "run_id": run_id,
        "agent_id": agent_id,
        "tool_name": "dify.knowledge.upload",
        "tool_version": "v1",
        "tool_category": "custom",
        "normalized_args_json": json.dumps({"dataset_id": redact_text(dataset_id, 80), "document_name": document_name, "text_hash": text_hash, "approval_id": body.get("approval_id")}, ensure_ascii=False),
        "target_resource": f"dify://datasets/{redact_text(dataset_id, 80)}/documents/{document_id or 'unknown'}",
        "risk_level": "medium" if cfg["trust_mode"] == "local_dify" else "high",
        "status": "completed" if ok else "failed",
        "result_summary": row["output_summary"],
        "side_effect_id": document_id,
        "started_at": started_iso,
        "ended_at": row["ended_at"],
        "created_at": started_iso,
    }
    upsert_tool_call(conn, tool_row, "dify-connector", {"text_hash": text_hash, "response_hash": response_hash, "raw_text_omitted": True})
    upsert_evaluation(conn, quality_gate_for_run(row), "dify-connector")
    runtime_event(conn, "rtc_agent_gateway_local", "dify.upload_text", "completed" if ok else "failed", run_id=run_id, task_id=task_id, agent_id=agent_id, latency_ms=duration, input_summary=f"Dify text upload text_hash={text_hash[:16]}", output_summary=row["output_summary"], error_message=error, raw_payload_hash=response_hash or text_hash)
    audit(conn, "agent", agent_id, "dify.upload_text", "runs", run_id, None, {"status": row["status"], "document_id": document_id}, {"text_hash": text_hash, "dataset_id": redact_text(dataset_id, 80), "approval_id": body.get("approval_id"), "trust_mode": cfg["trust_mode"]})
    conn.commit()
    return {
        "provider": "dify",
        "mode": cfg["trust_mode"],
        "dry_run": False,
        "ok": ok,
        "task_id": task_id,
        "run_id": run_id,
        "tool_call_id": tool_row["tool_call_id"],
        "document_id": document_id,
        "dataset_id": redact_text(dataset_id, 80),
        "duration_ms": duration,
        "text_hash": text_hash,
        "output_summary": row["output_summary"],
        "error": error,
    }


def ensure_agnesfallback_agent_task(conn, mode: str):
    agent_id = "agt_agnesfallback_runtime"
    upsert_agent(conn, {
        "agent_id": agent_id,
        "name": "Agnesfallback Runtime",
        "role": "Profile-aware Hermes/Agnesfallback Runtime",
        "description": "Agnesfallback CLI/API runtime connector. Real runs require explicit confirmation.",
        "runtime_type": "hermes",
        "model_provider": "agnesfallback",
        "model_name": "agnesfallback",
        "status": "idle",
        "permission_level": "manager",
        "allowed_tools": json.dumps(["agnesfallback.cli", "openai_compatible.chat", "runtime.probe"], ensure_ascii=False),
        "budget_limit_usd": 10.0,
        "owner_user_id": "usr_founder",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, "runtime-connector")
    task_id = f"tsk_agnesfallback_{mode}_probe"
    upsert_task(conn, {
        "task_id": task_id,
        "title": f"Agnesfallback {mode} probe",
        "description": "Fixed low-risk runtime connector probe. Full prompt and raw response are not stored.",
        "requester_id": "usr_founder",
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
        "status": "planned",
        "priority": "high",
        "due_date": None,
        "acceptance_criteria": "Connector returns the fixed health marker and writes run/evaluation/audit.",
        "risk_level": "low",
        "budget_limit_usd": 1.0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, "runtime-connector")
    return agent_id, task_id


def agnesfallback_cli_probe(conn, body: dict) -> dict:
    cfg = hermes_runtime_config()
    agnes = agnesfallback_config()
    prompt = "请只回复 AGNESFALLBACK_OK，不要解释。"
    connector_id = "rtc_agnesfallback_cli"
    confirm = bool(body.get("confirm_run"))
    plan = {
        "provider": "agnesfallback",
        "mode": "cli_probe",
        "dry_run": True,
        "would_run": agnesfallback_cli_command(agnes, "[FIXED_SAFE_PROMPT]"),
        "prompt_hash": stable_hash(prompt),
        "requires": {"HERMES_ALLOW_REAL_RUN": True, "confirm_run": True},
        "note": "Extra CLI args are empty by default. Use AGNESFALLBACK_CLI_EXTRA_ARGS only for explicit local recording mode.",
    }
    refresh_runtime_connectors(conn)
    if not (cfg["allow_real_run"] and confirm):
        runtime_event(conn, connector_id, "cli_probe_dry_run", "planned", prompt_hash=stable_hash(prompt), input_summary="Agnesfallback CLI fixed probe dry-run.")
        audit(conn, "system", "agnesfallback-cli", "runtime.cli_probe.dry_run", "runtime_connectors", connector_id, None, plan, {"confirm_run": confirm})
        conn.commit()
        return plan
    agent_id, task_id = ensure_agnesfallback_agent_task(conn, "cli")
    started_iso = now_iso()
    started = dt.datetime.now(dt.timezone.utc)
    ok = False
    visible = None
    error = None
    try:
        proc = subprocess.run(agnesfallback_cli_command(agnes, prompt), capture_output=True, text=True, timeout=180, check=False)
        visible = redact_text((proc.stdout or "").strip(), 200)
        ok = proc.returncode == 0 and visible == "AGNESFALLBACK_OK"
        if not ok:
            error = redact_text(proc.stderr or visible or f"exit={proc.returncode}", 240)
    except Exception as exc:
        error = redact_text(str(exc), 240)
    duration = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    run_id = stable_id("run_agnes_cli_probe", dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))
    row = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": "hermes",
        "status": "completed" if ok else "failed",
        "started_at": started_iso,
        "ended_at": now_iso(),
        "duration_ms": duration,
        "input_summary": f"Agnesfallback CLI fixed probe prompt_hash={stable_hash(prompt)[:16]}",
        "output_summary": "Agnesfallback CLI returned AGNESFALLBACK_OK." if ok else "Agnesfallback CLI probe failed.",
        "model_provider": "agnesfallback",
        "model_name": "agnesfallback",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.0,
        "error_type": None if ok else "AgnesfallbackCliProbeFailed",
        "error_message": error,
        "trace_id": None,
        "parent_run_id": None,
        "delegation_id": "agnesfallback:cli",
        "approval_required": 0,
        "created_at": started_iso,
    }
    upsert_run(conn, row, "agnesfallback-cli", {"prompt_hash": stable_hash(prompt)})
    upsert_evaluation(conn, quality_gate_for_run(row), "agnesfallback-cli")
    runtime_event(conn, connector_id, "cli_probe", "completed" if ok else "failed", run_id=run_id, task_id=task_id, agent_id=agent_id, model_name="agnesfallback", latency_ms=duration, prompt_hash=stable_hash(prompt), output_summary=visible, error_message=error, raw_payload_hash=stable_hash({"visible": visible, "error": error}))
    audit(conn, "system", "agnesfallback-cli", "runtime.cli_probe", "runs", run_id, None, {"status": row["status"]}, {"prompt_hash": stable_hash(prompt), "confirmed": True})
    conn.commit()
    return {"provider": "agnesfallback", "mode": "cli_probe", "dry_run": False, "ok": ok, "run_id": run_id, "duration_ms": duration, "output_summary": row["output_summary"], "error": error}


def agnesfallback_chat_completion_probe(conn, body: dict) -> dict:
    cfg = hermes_runtime_config()
    agnes = agnesfallback_config()
    prompt = "请只回复 HERMES_AGNES_API_OK，不要解释。"
    connector_id = "rtc_agnesfallback_openai_api"
    confirm = bool(body.get("confirm_run"))
    plan = {
        "provider": "agnesfallback",
        "mode": "openai_compatible",
        "dry_run": True,
        "would_post": agnes["gateway_url"].rstrip("/") + "/v1/chat/completions",
        "prompt_hash": stable_hash(prompt),
        "requires": {"HERMES_ALLOW_REAL_RUN": True, "confirm_run": True},
    }
    refresh_runtime_connectors(conn)
    if not (cfg["allow_real_run"] and confirm):
        runtime_event(conn, connector_id, "chat_completion_probe_dry_run", "planned", prompt_hash=stable_hash(prompt), input_summary="Agnesfallback API fixed probe dry-run.")
        audit(conn, "system", "agnesfallback-api", "runtime.chat_completion_probe.dry_run", "runtime_connectors", connector_id, None, plan, {"confirm_run": confirm})
        conn.commit()
        return plan
    agent_id, task_id = ensure_agnesfallback_agent_task(conn, "api")
    started_iso = now_iso()
    started = dt.datetime.now(dt.timezone.utc)
    payload = {"model": "agnesfallback", "messages": [{"role": "user", "content": prompt}], "temperature": 0}
    ok = False
    visible = None
    error = None
    response_hash = None
    try:
        req = Request(
            agnes["gateway_url"].rstrip("/") + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=180) as res:
            response = json.loads(res.read().decode("utf-8"))
        response_hash = stable_hash(response)
        visible = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        visible = redact_text(visible, 200)
        ok = visible == "HERMES_AGNES_API_OK"
        if not ok:
            error = redact_text(visible or "unexpected response", 240)
    except Exception as exc:
        error = redact_text(str(exc), 240)
    duration = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    run_id = stable_id("run_agnes_api_probe", dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))
    row = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": "hermes",
        "status": "completed" if ok else "failed",
        "started_at": started_iso,
        "ended_at": now_iso(),
        "duration_ms": duration,
        "input_summary": f"Agnesfallback OpenAI-compatible fixed probe prompt_hash={stable_hash(prompt)[:16]}",
        "output_summary": "Agnesfallback API returned HERMES_AGNES_API_OK." if ok else "Agnesfallback API probe failed.",
        "model_provider": "agnesfallback",
        "model_name": "agnesfallback",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.0,
        "error_type": None if ok else "AgnesfallbackApiProbeFailed",
        "error_message": error,
        "trace_id": None,
        "parent_run_id": None,
        "delegation_id": "agnesfallback:openai-compatible",
        "approval_required": 0,
        "created_at": started_iso,
    }
    upsert_run(conn, row, "agnesfallback-api", {"prompt_hash": stable_hash(prompt), "raw_payload_hash": response_hash})
    upsert_evaluation(conn, quality_gate_for_run(row), "agnesfallback-api")
    runtime_event(conn, connector_id, "chat_completion_probe", "completed" if ok else "failed", run_id=run_id, task_id=task_id, agent_id=agent_id, model_name="agnesfallback", latency_ms=duration, prompt_hash=stable_hash(prompt), output_summary=visible, error_message=error, raw_payload_hash=response_hash)
    audit(conn, "system", "agnesfallback-api", "runtime.chat_completion_probe", "runs", run_id, None, {"status": row["status"]}, {"prompt_hash": stable_hash(prompt), "confirmed": True})
    conn.commit()
    return {"provider": "agnesfallback", "mode": "openai_compatible", "dry_run": False, "ok": ok, "run_id": run_id, "duration_ms": duration, "output_summary": row["output_summary"], "error": error}


def ensure_local_ai_brief_agent_task(conn):
    now = now_iso()
    agent_id = "agt_local_ai_brief"
    upsert_agent(conn, {
        "agent_id": agent_id,
        "name": "Local AI Brief Assistant",
        "role": "Local Operations Assistant",
        "description": "Uses Agnesfallback locally to turn safe MIS ledger metrics into a Chinese project brief.",
        "runtime_type": "hermes",
        "model_provider": "agnesfallback",
        "model_name": "agnesfallback",
        "status": "idle",
        "permission_level": "manager",
        "allowed_tools": json.dumps(["agnesfallback.cli", "mis.sqlite.read", "report.write"], ensure_ascii=False),
        "budget_limit_usd": 10.0,
        "owner_user_id": "usr_founder",
        "created_at": now,
        "updated_at": now,
    }, "local-ai-workflow")
    task_id = "tsk_local_ai_daily_brief"
    upsert_task(conn, {
        "task_id": task_id,
        "title": "Generate local AgentOps MIS work brief",
        "description": "Generate a useful local project/ops brief from structured MIS counts and recent sanitized ledger summaries.",
        "requester_id": "usr_founder",
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
        "status": "planned",
        "priority": "high",
        "due_date": None,
        "acceptance_criteria": "Brief identifies real capabilities, demo/mock boundaries, next actions, and risks; output is recorded in the ledger.",
        "risk_level": "low",
        "budget_limit_usd": 1.0,
        "created_at": now,
        "updated_at": now,
    }, "local-ai-workflow")
    return agent_id, task_id


def local_ai_brief_state(conn) -> dict:
    metrics = dashboard_metrics(conn)
    recent_runs = rows_to_dicts(conn.execute(
        """SELECT run_id, task_id, agent_id, runtime_type, status, duration_ms, output_summary, error_type, error_message, created_at
        FROM runs
        ORDER BY created_at DESC
        LIMIT 10"""
    ).fetchall())
    latest_real_runs = rows_to_dicts(conn.execute(
        """SELECT run_id, task_id, agent_id, runtime_type, status, output_summary, error_type, created_at
        FROM runs
        WHERE runtime_type IN ('hermes','openclaw','claude_code','codex','openhands','crewai','langgraph')
        ORDER BY created_at DESC
        LIMIT 10"""
    ).fetchall())
    memory_review = dict(conn.execute(
        """SELECT
        SUM(CASE WHEN review_status='candidate' THEN 1 ELSE 0 END) AS candidates,
        SUM(CASE WHEN review_status='approved' THEN 1 ELSE 0 END) AS approved,
        SUM(CASE WHEN review_status IN ('stale','superseded') THEN 1 ELSE 0 END) AS needs_review
        FROM memories"""
    ).fetchone())
    runtime_events = rows_to_dicts(conn.execute(
        """SELECT runtime_connector_id, event_type, status, output_summary, error_message, created_at
        FROM runtime_events
        ORDER BY created_at DESC
        LIMIT 8"""
    ).fetchall())
    return {
        "generated_at": now_iso(),
        "purpose": "local_ai_brief_safe_structured_state",
        "privacy": "Only structured counts and sanitized summaries are included. No credentials, private messages, or full transcripts.",
        "metrics": {
            "agents_total": metrics["agents_total"],
            "tasks_completed_total": metrics["tasks_completed_total"],
            "failure_rate": metrics["failure_rate"],
            "pending_approvals": metrics["pending_approvals"],
            "stale_or_due_memories": metrics["stale_or_due_memories"],
            "runtime_health": metrics["runtime_health"],
            "openclaw_import": metrics["openclaw_import"],
            "agent_performance_summary": metrics["agent_performance_summary"][:5],
        },
        "memory_review": memory_review,
        "recent_runs": recent_runs,
        "latest_real_runtime_runs": latest_real_runs,
        "recent_runtime_events": runtime_events,
        "known_boundaries": [
            "The static MIS UI is the live local control plane.",
            "OpenClaw imported data may be real metadata but does not prove a fresh task was executed now.",
            "Agnesfallback live mode requires HERMES_ALLOW_REAL_RUN=true plus confirm_run:true.",
            "Default cloned demo remains safe and dry-run first.",
        ],
    }


def build_local_ai_brief_prompt(state: dict) -> str:
    payload = json.dumps(state, ensure_ascii=False, indent=2, default=str)
    return (
        "你是 AgentOps MIS 的本地运营助理。请只基于下面 JSON 结构化状态，生成一份中文工作简报。"
        "不要编造外部事实，不要提到没有证据的能力。控制在 8 条以内，要求有真实用途。\n\n"
        "必须包含：\n"
        "1. 现在系统已经真实能做什么。\n"
        "2. 哪些内容仍然是 demo/mock/imported metadata，不要夸大。\n"
        "3. 用户今天最该处理的 3 个工作项。\n"
        "4. 当前风险或阻塞。\n"
        "5. 下一步如何让它更像产品。\n\n"
        f"JSON 状态：\n{payload}"
    )


def run_local_ai_brief(conn, body: dict) -> dict:
    cfg = hermes_runtime_config()
    agnes = agnesfallback_config()
    connector_id = "rtc_agnesfallback_cli"
    confirm = bool(body.get("confirm_run"))
    refresh_runtime_connectors(conn)
    agent_id, task_id = ensure_local_ai_brief_agent_task(conn)
    state = local_ai_brief_state(conn)
    prompt = build_local_ai_brief_prompt(state)
    prompt_hash = stable_hash(prompt)
    state_hash = stable_hash(state)
    plan = {
        "provider": "agnesfallback",
        "workflow": "local_ai_brief",
        "dry_run": True,
        "would_run": agnesfallback_cli_command(agnes, "[SAFE_STRUCTURED_MIS_BRIEF_PROMPT]"),
        "requires": {"HERMES_ALLOW_REAL_RUN": True, "confirm_run": True},
        "prompt_hash": prompt_hash,
        "state_hash": state_hash,
        "state_preview": {
            "agents_total": state["metrics"]["agents_total"],
            "pending_approvals": state["metrics"]["pending_approvals"],
            "openclaw_cron_runs": state["metrics"]["openclaw_import"]["cron_runs"],
            "recent_real_runs": len(state["latest_real_runtime_runs"]),
        },
        "note": "Dry-run only. No prompt body, credentials, private messages, or full transcripts are stored.",
    }
    if not (cfg["allow_real_run"] and confirm):
        runtime_event(conn, connector_id, "local_ai_brief_dry_run", "planned", task_id=task_id, agent_id=agent_id, prompt_hash=prompt_hash, input_summary=f"Local AI brief dry-run state_hash={state_hash[:16]}")
        audit(conn, "system", "local-ai-workflow", "workflow.local_ai_brief.dry_run", "tasks", task_id, None, plan, {"confirm_run": confirm, "state_hash": state_hash})
        conn.commit()
        return plan

    started_iso = now_iso()
    started = dt.datetime.now(dt.timezone.utc)
    ok = False
    visible = None
    error = None
    try:
        proc = subprocess.run(agnesfallback_cli_command(agnes, prompt), capture_output=True, text=True, timeout=180, check=False)
        visible = redact_text((proc.stdout or "").strip(), 1600)
        ok = proc.returncode == 0 and bool(visible)
        if not ok:
            error = redact_text(proc.stderr or visible or f"exit={proc.returncode}", 300)
    except Exception as exc:
        error = redact_text(str(exc), 300)

    duration = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    run_id = stable_id("run_local_ai_brief", dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))
    row = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": "hermes",
        "status": "completed" if ok else "failed",
        "started_at": started_iso,
        "ended_at": now_iso(),
        "duration_ms": duration,
        "input_summary": f"Local MIS structured-state brief prompt_hash={prompt_hash[:16]} state_hash={state_hash[:16]}",
        "output_summary": visible if ok else "Local AI brief generation failed.",
        "model_provider": "agnesfallback",
        "model_name": "agnesfallback",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.0,
        "error_type": None if ok else "LocalAiBriefFailed",
        "error_message": error,
        "trace_id": None,
        "parent_run_id": None,
        "delegation_id": "agnesfallback:local-ai-brief",
        "approval_required": 0,
        "created_at": started_iso,
    }
    upsert_run(conn, row, "local-ai-workflow", {"prompt_hash": prompt_hash, "state_hash": state_hash, "confirmed": True})
    upsert_evaluation(conn, quality_gate_for_run(row), "local-ai-workflow")
    runtime_event(conn, connector_id, "local_ai_brief", "completed" if ok else "failed", run_id=run_id, task_id=task_id, agent_id=agent_id, model_name="agnesfallback", latency_ms=duration, prompt_hash=prompt_hash, input_summary=f"Structured MIS state_hash={state_hash[:16]}", output_summary=visible, error_message=error, raw_payload_hash=stable_hash({"visible": visible, "error": error, "state_hash": state_hash}))
    artifact_id = stable_id("art_local_ai_brief", run_id)
    if ok:
        repo_upsert_artifact(conn, {
            "artifact_id": artifact_id,
            "task_id": task_id,
            "run_id": run_id,
            "artifact_type": "report",
            "title": "Local AI Work Brief",
            "uri": f"run://{run_id}",
            "summary": visible,
            "created_at": now_iso(),
        })
    conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE task_id=?", ("completed" if ok else "blocked", now_iso(), task_id))
    audit(conn, "system", "local-ai-workflow", "workflow.local_ai_brief", "runs", run_id, None, {"status": row["status"], "artifact_id": artifact_id if ok else None}, {"prompt_hash": prompt_hash, "state_hash": state_hash, "confirmed": True})
    conn.commit()
    return {"provider": "agnesfallback", "workflow": "local_ai_brief", "dry_run": False, "ok": ok, "run_id": run_id, "task_id": task_id, "artifact_id": artifact_id if ok else None, "duration_ms": duration, "output_summary": row["output_summary"], "error": error}


def ensure_customer_task_runner(conn):
    now = now_iso()
    conn.execute(
        """INSERT OR IGNORE INTO users(user_id,name,email,role,created_at)
        VALUES(?,?,?,?,?)""",
        ("usr_customer_demo", "Customer Demo User", "customer-demo@example.local", "requester", now),
    )
    agent_id = "agt_customer_task_runner"
    upsert_agent(conn, {
        "agent_id": agent_id,
        "name": "Customer Task Runner",
        "role": "Customer-Facing Execution Agent",
        "description": "Runs explicit customer tasks through the local Hermes/Agnesfallback connector and records evidence in MIS.",
        "runtime_type": "hermes",
        "model_provider": "agnesfallback",
        "model_name": "agnesfallback",
        "status": "idle",
        "permission_level": "manager",
        "allowed_tools": json.dumps(["agnesfallback.cli", "mis.ledger.write", "quality_gate.run"], ensure_ascii=False),
        "budget_limit_usd": 10.0,
        "owner_user_id": "usr_founder",
        "created_at": now,
        "updated_at": now,
    }, "customer-task-workflow")
    return agent_id


def build_customer_task_prompt(task: dict, selected_agents: list[str], confirmed_real_run=False) -> str:
    payload = {
        "privacy": "Customer provided this task intentionally. Do not request or reveal credentials, private messages, or full transcripts.",
        "execution_context": {
            "workflow": "customer_task",
            "confirmed_real_run": bool(confirmed_real_run),
            "runtime": "agnesfallback.cli" if confirmed_real_run else "dry_run_plan",
            "ledger_policy": "Store sanitized summaries and hashes only; do not store full prompt or raw response.",
        },
        "task": {
            "title": redact_text(task.get("title"), 300),
            "description": redact_text(task.get("description"), 1200),
            "acceptance_criteria": redact_text(task.get("acceptance_criteria"), 800),
            "priority": task.get("priority"),
            "risk_level": task.get("risk_level"),
            "selected_agents": selected_agents,
        },
        "required_output": [
            "用中文给出可执行结果，而不是泛泛建议。",
            "说明哪些事情由 agent 解决，哪些事情需要 MIS 前台/权限/审计解决。",
            "给出 3-5 条下一步行动，每条有负责人或系统模块。",
            "指出风险、阻塞和需要人工确认的地方。",
        ],
    }
    return (
        "你是 AgentOps MIS 中面向客户任务的本地执行代理。"
        "请只基于下面 JSON 任务说明工作，不要编造外部事实。"
        "输出应像一个可以交付给客户的任务结果简报，控制在 900 字以内。\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def run_customer_task_workflow(conn, body: dict) -> dict:
    cfg = hermes_runtime_config()
    agnes = agnesfallback_config()
    refresh_runtime_connectors(conn)

    title = redact_text(body.get("title") or "客户任务", 180)
    description = redact_text(body.get("description") or "", 1600)
    acceptance = redact_text(body.get("acceptance_criteria") or "输出必须进入 MIS 运行账本、质量门和审计记录。", 900)
    risk = body.get("risk_level", "medium")
    if risk not in ("low", "medium", "high", "critical"):
        risk = "medium"
    priority = body.get("priority", "high")
    if priority not in ("low", "medium", "high", "urgent"):
        priority = "high"
    selected_agents = [str(item) for item in body.get("selected_agent_ids", []) if item]
    runner_agent_id = ensure_customer_task_runner(conn)
    owner_agent_id = body.get("owner_agent_id") or (selected_agents[0] if selected_agents else runner_agent_id)
    if not conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (owner_agent_id,)).fetchone():
        owner_agent_id = runner_agent_id

    task_id = body.get("task_id") or stable_id("tsk_customer_workflow", title, description, now_iso())
    task_row = {
        "task_id": task_id,
        "title": title,
        "description": description,
        "requester_id": body.get("requester_id", "usr_customer_demo"),
        "owner_agent_id": owner_agent_id,
        "collaborator_agent_ids": json.dumps(selected_agents, ensure_ascii=False),
        "status": "running" if body.get("confirm_run") else "planned",
        "priority": priority,
        "due_date": body.get("due_date"),
        "acceptance_criteria": acceptance,
        "risk_level": risk,
        "budget_limit_usd": float(body.get("budget_limit_usd", 1.0) or 1.0),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    upsert_task(conn, task_row, "customer-task-workflow")

    confirm = bool(body.get("confirm_run"))
    prompt = build_customer_task_prompt(task_row, selected_agents, confirmed_real_run=confirm and cfg["allow_real_run"])
    prompt_hash = stable_hash(prompt)
    plan = {
        "provider": "agnesfallback",
        "workflow": "customer_task",
        "dry_run": True,
        "task_id": task_id,
        "would_run": agnesfallback_cli_command(agnes, "[CUSTOMER_TASK_PROMPT]"),
        "requires": {"HERMES_ALLOW_REAL_RUN": True, "confirm_run": True},
        "prompt_hash": prompt_hash,
        "selected_agent_ids": selected_agents,
        "note": "Task was created in MIS. Real execution requires explicit confirmation; full prompt/raw response are not stored.",
    }
    if not (cfg["allow_real_run"] and confirm):
        runtime_event(conn, "rtc_agnesfallback_cli", "customer_task_dry_run", "planned", task_id=task_id, agent_id=runner_agent_id, prompt_hash=prompt_hash, input_summary=f"Customer task dry-run prompt_hash={prompt_hash[:16]}")
        audit(conn, "user", "usr_customer_demo", "workflow.customer_task.dry_run", "tasks", task_id, None, plan, {"confirm_run": confirm})
        conn.commit()
        return plan

    started_iso = now_iso()
    started = dt.datetime.now(dt.timezone.utc)
    ok = False
    visible = None
    error = None
    try:
        proc = subprocess.run(agnesfallback_cli_command(agnes, prompt), capture_output=True, text=True, timeout=180, check=False)
        visible = redact_text((proc.stdout or "").strip(), 1600)
        ok = proc.returncode == 0 and bool(visible)
        if not ok:
            error = redact_text(proc.stderr or visible or f"exit={proc.returncode}", 300)
    except Exception as exc:
        error = redact_text(str(exc), 300)

    duration = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    run_id = stable_id("run_customer_task", task_id, started_iso)
    row = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": runner_agent_id,
        "runtime_type": "hermes",
        "status": "completed" if ok else "failed",
        "started_at": started_iso,
        "ended_at": now_iso(),
        "duration_ms": duration,
        "input_summary": f"Customer task prompt_hash={prompt_hash[:16]}; title={title}",
        "output_summary": visible if ok else "Customer task execution failed.",
        "model_provider": "agnesfallback",
        "model_name": "agnesfallback",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.0,
        "error_type": None if ok else "CustomerTaskFailed",
        "error_message": error,
        "trace_id": None,
        "parent_run_id": None,
        "delegation_id": "customer-task:agnesfallback",
        "approval_required": 0,
        "created_at": started_iso,
    }
    upsert_run(conn, row, "customer-task-workflow", {"prompt_hash": prompt_hash, "confirmed": True, "selected_agent_ids": selected_agents})
    upsert_tool_call(conn, {
        "tool_call_id": stable_id("tc_customer_task", run_id, "agnesfallback-cli"),
        "run_id": run_id,
        "agent_id": runner_agent_id,
        "tool_name": "agnesfallback.cli",
        "tool_version": "v1",
        "tool_category": "custom",
        "normalized_args_json": json.dumps({"task_id": task_id, "prompt_policy": "summary_hash_only"}, ensure_ascii=False),
        "target_resource": "local://agnesfallback/cli",
        "risk_level": risk if risk in ("low", "medium") else "medium",
        "status": "completed" if ok else "failed",
        "result_summary": visible if ok else error,
        "side_effect_id": run_id,
        "started_at": started_iso,
        "ended_at": now_iso(),
        "created_at": started_iso,
    }, "customer-task-workflow", {"prompt_hash": prompt_hash})
    upsert_evaluation(conn, quality_gate_for_run(row), "customer-task-workflow")
    runtime_event(conn, "rtc_agnesfallback_cli", "customer_task", "completed" if ok else "failed", run_id=run_id, task_id=task_id, agent_id=runner_agent_id, model_name="agnesfallback", latency_ms=duration, prompt_hash=prompt_hash, input_summary=f"Customer task title={title}", output_summary=visible, error_message=error, raw_payload_hash=stable_hash({"visible": visible, "error": error, "prompt_hash": prompt_hash}))
    artifact_id = stable_id("art_customer_task", run_id)
    if ok:
        repo_upsert_artifact(conn, {
            "artifact_id": artifact_id,
            "task_id": task_id,
            "run_id": run_id,
            "artifact_type": "customer_result",
            "title": f"客户任务结果：{title}",
            "uri": f"run://{run_id}",
            "summary": visible,
            "created_at": now_iso(),
        })
    conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE task_id=?", ("completed" if ok else "blocked", now_iso(), task_id))
    audit(conn, "system", "customer-task-workflow", "workflow.customer_task", "runs", run_id, None, {"status": row["status"], "artifact_id": artifact_id if ok else None}, {"prompt_hash": prompt_hash, "confirmed": True, "selected_agent_ids": selected_agents})
    conn.commit()
    return {"provider": "agnesfallback", "workflow": "customer_task", "dry_run": False, "ok": ok, "run_id": run_id, "task_id": task_id, "artifact_id": artifact_id if ok else None, "duration_ms": duration, "output_summary": row["output_summary"], "error": error}


def run_kb_bot_project_workflow(conn, body: dict) -> dict:
    base_url = str(body.get("base_url") or body.get("_base_url") or os.environ.get("AGENTOPS_BASE_URL") or "http://127.0.0.1:8787").rstrip("/")
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_kb_bot_demo.py"),
        "--base-url",
        base_url,
        "--db-path",
        str(DB_PATH),
    ]
    api_key = os.environ.get("AGENTOPS_API_KEY", "")
    if api_key:
        cmd.extend(["--api-key", api_key])
    started = now_iso()
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=150, check=False)
        if proc.returncode != 0:
            error = redact_text(proc.stderr or proc.stdout or f"exit={proc.returncode}", 360)
            audit(conn, "system", "kb-bot-workflow", "workflow.kb_bot_project.failed", "workflows", "kb_bot_project", None, {"status": "failed"}, {"error": error, "started_at": started})
            conn.commit()
            return {"provider": "agent-gateway", "workflow": "formal_ai_knowledge_base_qa_bot", "dry_run": False, "ok": False, "error": error}
        payload = json.loads(proc.stdout or "{}")
        audit(conn, "system", "kb-bot-workflow", "workflow.kb_bot_project", "projects", payload.get("project_id", "kb_bot_project"), None, {"status": "completed", "artifact_id": (payload.get("results") or [{}])[-1].get("artifact_id") if payload.get("results") else None}, {"external_upload_performed": False, "raw_documents_stored": False, "credentials_stored": False})
        conn.commit()
        payload["provider"] = "agent-gateway"
        payload["workflow"] = "formal_ai_knowledge_base_qa_bot"
        payload["dry_run"] = False
        payload["ok"] = True
        if payload.get("results"):
            payload["task_id"] = payload["results"][-1].get("task_id")
            payload["run_id"] = payload["results"][-1].get("run_id")
            payload["artifact_id"] = payload["results"][-1].get("artifact_id")
            payload["approval_ids"] = [item.get("approval_id") for item in payload["results"] if item.get("approval_id")]
        return payload
    except Exception as exc:
        error = redact_text(str(exc), 360)
        audit(conn, "system", "kb-bot-workflow", "workflow.kb_bot_project.failed", "workflows", "kb_bot_project", None, {"status": "failed"}, {"error": error, "started_at": started})
        conn.commit()
        return {"provider": "agent-gateway", "workflow": "formal_ai_knowledge_base_qa_bot", "dry_run": False, "ok": False, "error": error}


def customer_task_templates() -> list[dict]:
    return [
        {
            "template_id": "tpl_customer_kb_qa_bot",
            "name": "AI 知识库 / 问答机器人",
            "name_en": "AI Knowledge Base / Q&A Bot",
            "workflow": "formal_ai_knowledge_base_qa_bot",
            "scenario": "customer_delivery",
            "status": "ready",
            "risk_level": "high",
            "priority": "high",
            "description": "把客户资料清洗成 Markdown/PDF/DOCX，设计 Dify / OpenAI File Search / AnythingLLM 知识库与问答机器人。",
            "default_title": "搭建正式 AI 知识库 / 问答机器人",
            "default_description": "客户任务：把原始资料清洗成 Markdown / PDF / DOCX，选择 Dify、OpenAI File Search 或 AnythingLLM，设计分块、Embedding、向量库、来源引用和 AI 问答工作流。",
            "default_acceptance": "MIS 必须生成任务拆解、运行账本、工具调用、外部上传审批、记忆候选、质量评估和审计证据；不能保存凭证、完整私聊或原始资料全文。",
            "agent_roles": ["Project Planner", "Document Cleaner", "Knowledge Base Builder", "Q&A Evaluator", "Customer Report Writer"],
            "required_approvals": ["external_knowledge_upload"],
            "safe_defaults": {
                "external_upload_performed": False,
                "credentials_stored": False,
                "raw_documents_stored": False,
                "summary_hash_only": True,
            },
            "entrypoint": "POST /api/workflows/customer-task-templates/run",
        },
        {
            "template_id": "tpl_customer_ui_review",
            "name": "产品 UI 评审与优化建议",
            "name_en": "Product UI Review and Improvement Brief",
            "workflow": "customer_task",
            "scenario": "customer_delivery",
            "status": "dry_run_or_confirmed_local",
            "risk_level": "medium",
            "priority": "high",
            "description": "让 AI 团队评审一个工作台/页面，输出信息架构、交互、视觉层级和下一步改进清单。",
            "default_title": "产品工作台 UI 评审与优化建议",
            "default_description": "请评审当前 AgentOps MIS 工作台：信息架构是否清晰、客户是否知道下一步怎么操作、AI 团队运行证据是否可信，并给出可执行改进建议。",
            "default_acceptance": "输出客户可读评审摘要、3-5 个优先级改进项、需要人工确认的设计/权限事项，并写入 MIS 任务、运行、评估和审计。",
            "agent_roles": ["Researcher", "Product Designer", "Evaluator", "Report Writer"],
            "required_approvals": ["confirmed_local_ai_run"],
            "safe_defaults": {
                "external_upload_performed": False,
                "credentials_stored": False,
                "raw_documents_stored": False,
                "summary_hash_only": True,
            },
            "entrypoint": "POST /api/workflows/customer-task-templates/run",
        },
        {
            "template_id": "tpl_customer_competitor_research",
            "name": "竞品调研与产品定位报告",
            "name_en": "Competitor Research and Product Positioning",
            "workflow": "customer_task",
            "scenario": "customer_delivery",
            "status": "dry_run_or_confirmed_local",
            "risk_level": "medium",
            "priority": "medium",
            "description": "把客户问题拆成调研、对比矩阵、差异化定位、风险和下一步方案。",
            "default_title": "竞品调研与产品定位报告",
            "default_description": "请围绕一个产品方向完成结构化竞品调研：竞品列表、核心能力、差异化、风险、MVP 建议和证据要求。",
            "default_acceptance": "输出结构化报告摘要、对比维度、证据来源要求、可交付物清单，并写入 MIS 账本；需要联网或外部 API 时必须标记为人工审批。",
            "agent_roles": ["Researcher", "Product Strategist", "Evaluator", "Report Writer"],
            "required_approvals": ["external_research_or_api_access"],
            "safe_defaults": {
                "external_upload_performed": False,
                "credentials_stored": False,
                "raw_documents_stored": False,
                "summary_hash_only": True,
            },
            "entrypoint": "POST /api/workflows/customer-task-templates/run",
        },
    ]


def run_customer_task_template_workflow(conn, body: dict) -> tuple[dict, int]:
    templates = {template["template_id"]: template for template in customer_task_templates()}
    template_id = body.get("template_id") or "tpl_customer_kb_qa_bot"
    template = templates.get(template_id)
    if not template:
        return {"error": "template not found", "template_id": template_id, "templates": list(templates)}, 404
    if not commercial_capability_enabled("report_templates"):
        return commercial_entitlement_block(conn, "report_templates", "workflow.customer_task_template.run", "customer-template-workflow"), 403
    adapter = body.get("adapter")
    use_worker_adapter = adapter in {"mock", "hermes", "openclaw"}
    if use_worker_adapter:
        worker_payload = {
            "adapter": adapter,
            "confirm_run": bool(body.get("confirm_run")),
            "title": body.get("title") or template["default_title"],
            "description": body.get("description") or template["default_description"],
            "acceptance_criteria": body.get("acceptance_criteria") or template["default_acceptance"],
            "priority": body.get("priority") or template["priority"],
            "risk_level": body.get("risk_level") or template["risk_level"],
            "template_id": template_id,
            "workflow_kind": template["workflow"],
            "selected_agent_ids": body.get("selected_agent_ids") or [],
            "worker_agent_id": body.get("worker_agent_id") or body.get("owner_agent_id"),
            "requester_id": body.get("requester_id", "usr_customer_demo"),
            "hermes_timeout": body.get("hermes_timeout") or 300,
        }
        result, _status = run_customer_worker_task_workflow(conn, worker_payload)
        result["template_execution"] = {
            "mode": "agent_worker_adapter",
            "adapter": adapter,
            "confirm_run": bool(body.get("confirm_run")),
        }
    elif template["workflow"] == "formal_ai_knowledge_base_qa_bot":
        result = run_kb_bot_project_workflow(conn, {**body, "template_id": template_id})
    else:
        payload = {
            "title": body.get("title") or template["default_title"],
            "description": body.get("description") or template["default_description"],
            "acceptance_criteria": body.get("acceptance_criteria") or template["default_acceptance"],
            "priority": body.get("priority") or template["priority"],
            "risk_level": body.get("risk_level") or template["risk_level"],
            "template_id": template_id,
            "workflow_kind": template["workflow"],
            "selected_agent_ids": body.get("selected_agent_ids") or [],
            "owner_agent_id": body.get("owner_agent_id"),
            "confirm_run": bool(body.get("confirm_run")),
        }
        result = run_customer_task_workflow(conn, payload)
    result["template"] = {
        "template_id": template["template_id"],
        "name": template["name"],
        "workflow": template["workflow"],
        "safe_defaults": template["safe_defaults"],
    }
    if use_worker_adapter:
        result["template"]["agent_worker_adapter_enabled"] = True
    if result.get("project_id"):
        result["report_url"] = f"/api/workflows/customer-projects/{result['project_id']}/report"
    audit(conn, "user", "usr_customer_demo", "workflow.customer_template.run", "template_packages", template_id, None, {"status": "completed" if result.get("ok", True) else "failed", "workflow": template["workflow"]}, {"template_id": template_id, "dry_run": result.get("dry_run"), "adapter": adapter if use_worker_adapter else None, "raw_documents_stored": False, "credentials_stored": False})
    conn.commit()
    return result, 201


def workflow_job_public(row: sqlite3.Row | dict | None) -> dict | None:
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


def _parse_iso_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception:
        return None


def workflow_stuck_jobs(conn, threshold_sec: int = 900, limit: int = 25) -> list[dict]:
    threshold_sec = max(int(threshold_sec or 900), 30)
    limit = min(max(int(limit or 25), 1), 200)
    now_dt = dt.datetime.now(dt.timezone.utc)
    rows = conn.execute(
        "SELECT * FROM workflow_jobs WHERE status IN ('queued','running') ORDER BY updated_at ASC LIMIT 500"
    ).fetchall()
    stuck: list[dict] = []
    for row in rows:
        data = workflow_job_public(row) or {}
        anchor = (
            _parse_iso_datetime(data.get("updated_at"))
            or _parse_iso_datetime(data.get("started_at"))
            or _parse_iso_datetime(data.get("created_at"))
            or now_dt
        )
        age_sec = max(int((now_dt - anchor).total_seconds()), 0)
        if age_sec >= threshold_sec:
            data["age_sec"] = age_sec
            data["threshold_sec"] = threshold_sec
            data["stuck_reason"] = "workflow_job_exceeded_threshold"
            stuck.append(data)
        if len(stuck) >= limit:
            break
    return stuck


def mark_workflow_job_failed(conn, job_id: str, body: dict, workspace_id: str | None = None) -> tuple[dict, int]:
    job_id = redact_text(job_id, 120)
    workspace_id = normalize_workspace_id(workspace_id or body.get("workspace_id") or "local-demo")
    before = repo_get_workspace_workflow_job(conn, workspace_id, job_id)
    if not before:
        return {"error": "not found", "job_id": job_id}, 404
    if before["status"] not in {"queued", "running"}:
        return {
            "ok": False,
            "reason": "workflow_job_not_active",
            "job": workflow_job_public(before),
            "token_omitted": True,
        }, 409
    reason = redact_text(body.get("reason") or "Operator marked stale workflow job as failed.", 300)
    now = now_iso()
    conn.execute(
        """UPDATE workflow_jobs
        SET status='failed', error_message=?, completed_at=?, updated_at=?
        WHERE job_id=?""",
        (reason, now, now, job_id),
    )
    runtime_event(conn, "rtc_agent_gateway_local", "workflow_job.operator_failed", "failed", output_summary=f"Workflow job {job_id} marked failed.", error_message=reason)
    after = conn.execute("SELECT * FROM workflow_jobs WHERE job_id=?", (job_id,)).fetchone()
    audit(conn, "user", body.get("actor_id") or "usr_operator", "workflow.job.mark_failed", "workflow_jobs", job_id, dict(before), dict(after) if after else {"status": "failed"}, {"raw_request_omitted": True, "reason": reason})
    conn.commit()
    return {
        "ok": True,
        "provider": "agentops-workflow-job",
        "job": workflow_job_public(after),
        "job_id": job_id,
        "marked_failed": True,
        "token_omitted": True,
    }, 200


def run_workflow_job_background(job_id: str, body: dict) -> None:
    started = now_iso()
    try:
        with db() as conn:
            before = conn.execute("SELECT * FROM workflow_jobs WHERE job_id=?", (job_id,)).fetchone()
            workflow_type = dict(before).get("workflow_type") if before else "customer_task_template"
            conn.execute(
                "UPDATE workflow_jobs SET status='running', started_at=?, updated_at=? WHERE job_id=?",
                (started, started, job_id),
            )
            runtime_event(conn, "rtc_agent_gateway_local", "workflow_job.running", "running", input_summary=f"Workflow job {job_id} started.")
            audit(conn, "system", "workflow-job", "workflow.job.running", "workflow_jobs", job_id, dict(before) if before else None, {"status": "running"}, {"raw_request_omitted": True})
            conn.commit()
            if workflow_type == "customer_worker_task":
                result, _status = run_customer_worker_task_workflow(conn, {**body, "async_job": False})
            else:
                result, _status = run_customer_task_template_workflow(conn, {**body, "async_job": False})
            status = "completed" if result.get("ok", True) else "failed"
            completed = now_iso()
            safe_result = json.dumps(result, ensure_ascii=False)
            before = conn.execute("SELECT * FROM workflow_jobs WHERE job_id=?", (job_id,)).fetchone()
            conn.execute(
                """UPDATE workflow_jobs
                SET status=?, result_json=?, result_task_id=?, result_run_id=?, result_artifact_id=?,
                    error_message=?, completed_at=?, updated_at=?
                WHERE job_id=?""",
                (
                    status,
                    safe_result,
                    result.get("task_id"),
                    result.get("run_id"),
                    result.get("artifact_id"),
                    redact_text(result.get("error"), 300) if result.get("error") else None,
                    completed,
                    completed,
                    job_id,
                ),
            )
            runtime_event(conn, "rtc_agent_gateway_local", "workflow_job.completed" if status == "completed" else "workflow_job.failed", status, run_id=result.get("run_id"), task_id=result.get("task_id"), output_summary=f"Workflow job {job_id} {status}.", raw_payload_hash=stable_hash(result))
            after = conn.execute("SELECT * FROM workflow_jobs WHERE job_id=?", (job_id,)).fetchone()
            audit(conn, "system", "workflow-job", f"workflow.job.{status}", "workflow_jobs", job_id, dict(before) if before else None, dict(after) if after else {"status": status}, {"raw_request_omitted": True, "raw_result_omitted": True, "safe_result_stored": True})
            conn.commit()
    except Exception as exc:
        error = redact_text(str(exc), 360)
        with db() as conn:
            before = conn.execute("SELECT * FROM workflow_jobs WHERE job_id=?", (job_id,)).fetchone()
            now = now_iso()
            conn.execute(
                """UPDATE workflow_jobs
                SET status='failed', error_message=?, completed_at=?, updated_at=?
                WHERE job_id=?""",
                (error, now, now, job_id),
            )
            runtime_event(conn, "rtc_agent_gateway_local", "workflow_job.failed", "failed", output_summary=f"Workflow job {job_id} failed.", error_message=error)
            after = conn.execute("SELECT * FROM workflow_jobs WHERE job_id=?", (job_id,)).fetchone()
            audit(conn, "system", "workflow-job", "workflow.job.failed", "workflow_jobs", job_id, dict(before) if before else None, dict(after) if after else {"status": "failed"}, {"raw_request_omitted": True})
            conn.commit()


def submit_customer_task_template_job(conn, body: dict) -> tuple[dict, int]:
    templates = {template["template_id"]: template for template in customer_task_templates()}
    template_id = body.get("template_id") or "tpl_customer_kb_qa_bot"
    template = templates.get(template_id)
    if not template:
        return {"error": "template not found", "template_id": template_id, "templates": list(templates)}, 404
    if not commercial_capability_enabled("report_templates"):
        return commercial_entitlement_block(conn, "report_templates", "workflow.customer_task_template.submit", "customer-template-workflow"), 403
    adapter = body.get("adapter") if body.get("adapter") in {"mock", "hermes", "openclaw"} else None
    now = now_iso()
    title = redact_text(body.get("title") or template["default_title"], 180)
    input_summary = redact_text(body.get("description") or template["default_description"], 300)
    confirm_run = bool(body.get("confirm_run"))
    if adapter in {"hermes", "openclaw"} and confirm_run:
        connector_id = runtime_connector_for_adapter(adapter)
        connector_trust = runtime_connector_trust(conn, connector_id)
        adapter_readiness = (worker_adapter_readiness(conn).get("adapters") or {}).get(adapter) or {}
        should_reject = (
            (connector_trust and connector_trust.get("trust_status") == "blocked")
            or adapter_readiness.get("readiness") in {"unavailable", "blocked"}
        )
        if should_reject:
            result, status = run_customer_task_template_workflow(conn, {**body, "async_job": False})
            now = now_iso()
            job_id = new_id("wfjob")
            row = {
                "job_id": job_id,
                "workspace_id": normalize_workspace_id(body.get("workspace_id") or "local-demo"),
                "workflow_type": "customer_task_template",
                "status": "failed",
                "template_id": template_id,
                "adapter": adapter,
                "confirm_run": 1,
                "title": title,
                "input_summary": input_summary,
                "request_hash": stable_hash({
                    "template_id": template_id,
                    "adapter": adapter,
                    "confirm_run": True,
                    "title": title,
                    "description": input_summary,
                    "early_reject": result.get("reason"),
                }),
                "result_json": json.dumps(result, ensure_ascii=False),
                "result_task_id": result.get("task_id"),
                "result_run_id": result.get("run_id"),
                "result_artifact_id": result.get("artifact_id"),
                "error_message": redact_text(result.get("note") or result.get("reason") or "Template adapter not ready for async live execution.", 300),
                "created_at": now,
                "started_at": None,
                "completed_at": now,
                "updated_at": now,
            }
            conn.execute(
                """INSERT INTO workflow_jobs(job_id,workspace_id,workflow_type,status,template_id,adapter,confirm_run,title,input_summary,request_hash,result_json,result_task_id,result_run_id,result_artifact_id,error_message,created_at,started_at,completed_at,updated_at)
                VALUES(:job_id,:workspace_id,:workflow_type,:status,:template_id,:adapter,:confirm_run,:title,:input_summary,:request_hash,:result_json,:result_task_id,:result_run_id,:result_artifact_id,:error_message,:created_at,:started_at,:completed_at,:updated_at)""",
                row,
            )
            runtime_event(conn, "rtc_agent_gateway_local", "workflow_job.rejected", "failed", task_id=result.get("task_id"), input_summary=f"Template job {job_id} rejected before async execution.", output_summary=row["error_message"], raw_payload_hash=row["request_hash"])
            audit(conn, "system", "worker-adapter-readiness", "workflow.job.rejected", "workflow_jobs", job_id, None, row, {
                "template_id": template_id,
                "adapter": adapter,
                "reason": result.get("reason"),
                "readiness": result.get("readiness"),
                "status": status,
                "raw_request_omitted": True,
                "raw_result_omitted": True,
            })
            conn.commit()
            return {
                "ok": False,
                "provider": "agentops-workflow-job",
                "workflow": "customer_task_template",
                "job": workflow_job_public(row),
                "job_id": job_id,
                "status_url": f"/api/workflows/jobs/{job_id}",
                "reason": result.get("reason") or "adapter_not_ready",
                "readiness": result.get("readiness"),
                "result": result,
                "raw_request_omitted": True,
                "token_omitted": True,
            }, 409
    job_id = new_id("wfjob")
    row = {
        "job_id": job_id,
        "workspace_id": normalize_workspace_id(body.get("workspace_id") or "local-demo"),
        "workflow_type": "customer_task_template",
        "status": "queued",
        "template_id": template_id,
        "adapter": adapter,
        "confirm_run": 1 if confirm_run else 0,
        "title": title,
        "input_summary": input_summary,
        "request_hash": stable_hash({
            "template_id": template_id,
            "adapter": adapter,
            "confirm_run": confirm_run,
            "title": title,
            "description": input_summary,
        }),
        "result_json": "{}",
        "result_task_id": None,
        "result_run_id": None,
        "result_artifact_id": None,
        "error_message": None,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "updated_at": now,
    }
    conn.execute(
        """INSERT INTO workflow_jobs(job_id,workspace_id,workflow_type,status,template_id,adapter,confirm_run,title,input_summary,request_hash,result_json,result_task_id,result_run_id,result_artifact_id,error_message,created_at,started_at,completed_at,updated_at)
        VALUES(:job_id,:workspace_id,:workflow_type,:status,:template_id,:adapter,:confirm_run,:title,:input_summary,:request_hash,:result_json,:result_task_id,:result_run_id,:result_artifact_id,:error_message,:created_at,:started_at,:completed_at,:updated_at)""",
        row,
    )
    runtime_event(conn, "rtc_agent_gateway_local", "workflow_job.submitted", "queued", input_summary=f"Template job {template_id} submitted.", raw_payload_hash=row["request_hash"])
    audit(conn, "user", "usr_customer_demo", "workflow.job.submitted", "workflow_jobs", job_id, None, row, {"template_id": template_id, "adapter": adapter, "raw_request_omitted": True})
    conn.commit()
    threading.Thread(target=run_workflow_job_background, args=(job_id, dict(body)), daemon=True).start()
    return {
        "ok": True,
        "provider": "agentops-workflow-job",
        "job": workflow_job_public(row),
        "job_id": job_id,
        "status_url": f"/api/workflows/jobs/{job_id}",
        "raw_request_omitted": True,
        "token_omitted": True,
    }, 202


def submit_customer_worker_task_job(conn, body: dict) -> tuple[dict, int]:
    adapter = coerce_choice(body.get("adapter"), {"mock", "hermes", "openclaw"}, "mock")
    now = now_iso()
    title = redact_text(body.get("title") or "客户 Worker 任务", 180)
    input_summary = redact_text(body.get("description") or "Customer task should be processed by an AgentOps worker.", 300)
    confirm_run = bool(body.get("confirm_run"))
    if adapter in {"hermes", "openclaw"} and confirm_run:
        connector_id = runtime_connector_for_adapter(adapter)
        connector_trust = runtime_connector_trust(conn, connector_id)
        adapter_readiness = (worker_adapter_readiness(conn).get("adapters") or {}).get(adapter) or {}
        should_reject = (
            (connector_trust and connector_trust.get("trust_status") == "blocked")
            or adapter_readiness.get("readiness") in {"unavailable", "blocked"}
        )
        if should_reject:
            result, status = run_customer_worker_task_workflow(conn, {**body, "async_job": False})
            now = now_iso()
            job_id = new_id("wfjob")
            row = {
                "job_id": job_id,
                "workspace_id": normalize_workspace_id(body.get("workspace_id") or "local-demo"),
                "workflow_type": "customer_worker_task",
                "status": "failed",
                "template_id": body.get("template_id"),
                "adapter": adapter,
                "confirm_run": 1,
                "title": title,
                "input_summary": input_summary,
                "request_hash": stable_hash({
                    "workflow_type": "customer_worker_task",
                    "adapter": adapter,
                    "confirm_run": True,
                    "title": title,
                    "description": input_summary,
                    "worker_agent_id": body.get("worker_agent_id"),
                    "early_reject": result.get("reason"),
                }),
                "result_json": json.dumps(result, ensure_ascii=False),
                "result_task_id": result.get("task_id"),
                "result_run_id": result.get("run_id"),
                "result_artifact_id": result.get("artifact_id"),
                "error_message": redact_text(result.get("note") or result.get("reason") or "Adapter not ready for async live execution.", 300),
                "created_at": now,
                "started_at": None,
                "completed_at": now,
                "updated_at": now,
            }
            conn.execute(
                """INSERT INTO workflow_jobs(job_id,workspace_id,workflow_type,status,template_id,adapter,confirm_run,title,input_summary,request_hash,result_json,result_task_id,result_run_id,result_artifact_id,error_message,created_at,started_at,completed_at,updated_at)
                VALUES(:job_id,:workspace_id,:workflow_type,:status,:template_id,:adapter,:confirm_run,:title,:input_summary,:request_hash,:result_json,:result_task_id,:result_run_id,:result_artifact_id,:error_message,:created_at,:started_at,:completed_at,:updated_at)""",
                row,
            )
            runtime_event(conn, "rtc_agent_gateway_local", "workflow_job.rejected", "failed", task_id=result.get("task_id"), input_summary=f"Customer worker job {job_id} rejected before async execution.", output_summary=row["error_message"], raw_payload_hash=row["request_hash"])
            audit(conn, "system", "worker-adapter-readiness", "workflow.job.rejected", "workflow_jobs", job_id, None, row, {
                "adapter": adapter,
                "reason": result.get("reason"),
                "readiness": result.get("readiness"),
                "status": status,
                "raw_request_omitted": True,
                "raw_result_omitted": True,
            })
            conn.commit()
            return {
                "ok": False,
                "provider": "agentops-workflow-job",
                "workflow": "customer_worker_task",
                "job": workflow_job_public(row),
                "job_id": job_id,
                "status_url": f"/api/workflows/jobs/{job_id}",
                "reason": result.get("reason") or "adapter_not_ready",
                "readiness": result.get("readiness"),
                "result": result,
                "raw_request_omitted": True,
                "token_omitted": True,
            }, 409
    job_id = new_id("wfjob")
    row = {
        "job_id": job_id,
        "workspace_id": normalize_workspace_id(body.get("workspace_id") or "local-demo"),
        "workflow_type": "customer_worker_task",
        "status": "queued",
        "template_id": body.get("template_id"),
        "adapter": adapter,
        "confirm_run": 1 if confirm_run else 0,
        "title": title,
        "input_summary": input_summary,
        "request_hash": stable_hash({
            "workflow_type": "customer_worker_task",
            "adapter": adapter,
            "confirm_run": confirm_run,
            "title": title,
            "description": input_summary,
            "worker_agent_id": body.get("worker_agent_id"),
        }),
        "result_json": "{}",
        "result_task_id": None,
        "result_run_id": None,
        "result_artifact_id": None,
        "error_message": None,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "updated_at": now,
    }
    conn.execute(
        """INSERT INTO workflow_jobs(job_id,workspace_id,workflow_type,status,template_id,adapter,confirm_run,title,input_summary,request_hash,result_json,result_task_id,result_run_id,result_artifact_id,error_message,created_at,started_at,completed_at,updated_at)
        VALUES(:job_id,:workspace_id,:workflow_type,:status,:template_id,:adapter,:confirm_run,:title,:input_summary,:request_hash,:result_json,:result_task_id,:result_run_id,:result_artifact_id,:error_message,:created_at,:started_at,:completed_at,:updated_at)""",
        row,
    )
    runtime_event(conn, "rtc_agent_gateway_local", "workflow_job.submitted", "queued", input_summary=f"Customer worker job {job_id} submitted.", raw_payload_hash=row["request_hash"])
    audit(conn, "user", "usr_customer_demo", "workflow.job.submitted", "workflow_jobs", job_id, None, row, {"workflow_type": "customer_worker_task", "adapter": adapter, "raw_request_omitted": True})
    conn.commit()
    threading.Thread(target=run_workflow_job_background, args=(job_id, dict(body)), daemon=True).start()
    return {
        "ok": True,
        "provider": "agentops-workflow-job",
        "workflow": "customer_worker_task",
        "job": workflow_job_public(row),
        "job_id": job_id,
        "status_url": f"/api/workflows/jobs/{job_id}",
        "raw_request_omitted": True,
        "token_omitted": True,
    }, 202


def customer_project_report(conn, project_id: str) -> tuple[dict, int]:
    project_id = redact_text(project_id, 80)
    tasks = rows_to_dicts(conn.execute(
        "SELECT * FROM tasks WHERE task_id LIKE ? ORDER BY task_id",
        (f"tsk_kb_bot_{project_id}_%",),
    ).fetchall())
    if not tasks:
        return {"error": "project not found", "project_id": project_id}, 404
    task_ids = [task["task_id"] for task in tasks]
    placeholders = ",".join("?" for _ in task_ids)
    runs = rows_to_dicts(conn.execute(
        f"SELECT * FROM runs WHERE task_id IN ({placeholders}) ORDER BY started_at, run_id",
        task_ids,
    ).fetchall())
    run_ids = [run["run_id"] for run in runs]
    run_placeholders = ",".join("?" for _ in run_ids) if run_ids else "''"
    agent_plans = rows_to_dicts(conn.execute(
        f"SELECT * FROM agent_plans WHERE task_id IN ({placeholders}) ORDER BY created_at",
        task_ids,
    ).fetchall())
    plan_evidence_manifests = rows_to_dicts(conn.execute(
        f"SELECT * FROM plan_evidence_manifests WHERE task_id IN ({placeholders}) ORDER BY created_at",
        task_ids,
    ).fetchall())
    tool_calls = rows_to_dicts(conn.execute(
        f"SELECT * FROM tool_calls WHERE run_id IN ({run_placeholders}) ORDER BY created_at",
        run_ids,
    ).fetchall()) if run_ids else []
    approvals = rows_to_dicts(conn.execute(
        f"SELECT * FROM approvals WHERE task_id IN ({placeholders}) ORDER BY created_at",
        task_ids,
    ).fetchall())
    evaluations = rows_to_dicts(conn.execute(
        f"SELECT * FROM evaluations WHERE task_id IN ({placeholders}) ORDER BY created_at",
        task_ids,
    ).fetchall())
    memories = rows_to_dicts(conn.execute(
        f"SELECT * FROM memories WHERE task_id IN ({placeholders}) ORDER BY created_at",
        task_ids,
    ).fetchall())
    artifacts = rows_to_dicts(conn.execute(
        f"SELECT * FROM artifacts WHERE task_id IN ({placeholders}) ORDER BY created_at",
        task_ids,
    ).fetchall())
    completed_runs = [run for run in runs if run.get("status") == "completed"]
    pending_approvals = [approval for approval in approvals if approval.get("decision") == "pending"]
    failed_runs = [run for run in runs if run.get("status") in {"failed", "blocked"}]
    delivery_artifacts = [artifact for artifact in artifacts if artifact.get("artifact_type") != "customer_project_report"]
    report_artifacts = [artifact for artifact in artifacts if artifact.get("artifact_type") == "customer_project_report"]
    final_artifact = delivery_artifacts[-1] if delivery_artifacts else None
    verified_plan_evidence = [manifest for manifest in plan_evidence_manifests if manifest.get("status") == "verified"]
    blocked_plan_evidence = [manifest for manifest in plan_evidence_manifests if manifest.get("status") == "blocked"]
    warning_plan_evidence = [manifest for manifest in plan_evidence_manifests if manifest.get("status") == "warning"]
    tasks_with_plans = {plan.get("task_id") for plan in agent_plans if plan.get("task_id")}
    tasks_with_verified_plan_evidence = {manifest.get("task_id") for manifest in verified_plan_evidence if manifest.get("task_id")}
    missing_plan_tasks = [task["task_id"] for task in tasks if task["task_id"] not in tasks_with_plans]
    missing_verified_plan_evidence_tasks = [
        task["task_id"]
        for task in tasks
        if task["risk_level"] not in {"high", "critical"} and task["task_id"] not in tasks_with_verified_plan_evidence
    ]
    execution_evidence = {
        "agent_plans": len(agent_plans),
        "plan_evidence_manifests": len(plan_evidence_manifests),
        "verified_plan_evidence_manifests": len(verified_plan_evidence),
        "blocked_plan_evidence_manifests": len(blocked_plan_evidence),
        "warning_plan_evidence_manifests": len(warning_plan_evidence),
        "tasks_missing_agent_plan": len(missing_plan_tasks),
        "low_risk_tasks_missing_verified_plan_evidence": len(missing_verified_plan_evidence_tasks),
        "approval_gated_tasks": len([task for task in tasks if task["risk_level"] in {"high", "critical"}]),
        "manifest_ids": [manifest["manifest_id"] for manifest in plan_evidence_manifests],
        "verified_manifest_ids": [manifest["manifest_id"] for manifest in verified_plan_evidence],
        "recent_manifests": [
            {
                "manifest_id": manifest.get("manifest_id"),
                "plan_id": manifest.get("plan_id"),
                "task_id": manifest.get("task_id"),
                "run_id": manifest.get("run_id"),
                "agent_id": manifest.get("agent_id"),
                "status": manifest.get("status"),
                "mismatch_policy": manifest.get("mismatch_policy"),
            }
            for manifest in plan_evidence_manifests[-8:]
        ],
        "contract": "Agent Gateway runs require Agent Plans; customer delivery evidence records verified plan-evidence manifests when the step is completed rather than approval-gated.",
    }

    lines = [
        f"# AI 知识库 / 问答机器人交付报告",
        "",
        f"- Project ID: `{project_id}`",
        f"- Tasks: {len(tasks)}",
        f"- Runs: {len(runs)} total, {len(completed_runs)} completed, {len(failed_runs)} failed/blocked",
        f"- Tool calls: {len(tool_calls)}",
        f"- Evaluations: {len(evaluations)}",
        f"- Memory candidates: {len(memories)}",
        f"- Artifacts: {len(artifacts)}",
        f"- Pending approvals: {len(pending_approvals)}",
        "",
        "## Safety Boundary",
        "",
        "- External upload performed: false",
        "- Credentials stored in MIS: false",
        "- Raw documents stored in MIS: false",
        "- MIS stores summary/hash/ledger evidence only.",
        "",
        "## Agent Gateway Evidence",
        "",
        f"- Agent Plans: {execution_evidence['agent_plans']}",
        f"- Plan evidence manifests: {execution_evidence['plan_evidence_manifests']}",
        f"- Verified plan evidence manifests: {execution_evidence['verified_plan_evidence_manifests']}",
        f"- Approval-gated tasks: {execution_evidence['approval_gated_tasks']}",
        f"- Tasks missing Agent Plan: {execution_evidence['tasks_missing_agent_plan']}",
        f"- Low-risk tasks missing verified plan evidence: {execution_evidence['low_risk_tasks_missing_verified_plan_evidence']}",
        "",
        "## Delivery Artifact",
        "",
    ]
    if final_artifact:
        lines.extend([
            f"- Artifact ID: `{final_artifact['artifact_id']}`",
            f"- Title: {final_artifact['title']}",
            f"- URI: `{final_artifact['uri']}`",
            f"- Summary: {final_artifact['summary']}",
            "",
        ])
    else:
        lines.extend(["- No delivery artifact recorded.", ""])
    lines.extend(["## Task Ledger", ""])
    runs_by_task: dict[str, list[dict]] = {}
    for run in runs:
        runs_by_task.setdefault(run["task_id"], []).append(run)
    approvals_by_task: dict[str, list[dict]] = {}
    for approval in approvals:
        approvals_by_task.setdefault(approval["task_id"], []).append(approval)
    for task in tasks:
        task_runs = runs_by_task.get(task["task_id"], [])
        task_approvals = approvals_by_task.get(task["task_id"], [])
        lines.extend([
            f"### {task['title']}",
            f"- Task ID: `{task['task_id']}`",
            f"- Owner: `{task['owner_agent_id']}`",
            f"- Status: `{task['status']}`",
            f"- Risk: `{task['risk_level']}`",
            f"- Runs: {', '.join(f'`{run['run_id']}`' for run in task_runs) if task_runs else 'none'}",
            f"- Approvals: {', '.join(f'`{approval['approval_id']}` ({approval['decision']})' for approval in task_approvals) if task_approvals else 'none'}",
            f"- Output: {redact_text((task_runs[-1].get('output_summary') if task_runs else task.get('description')) or '', 260)}",
            "",
        ])
    markdown = "\n".join(lines)
    return {
        "project_id": project_id,
        "status": "ready",
        "markdown": markdown,
        "counts": {
            "tasks": len(tasks),
            "runs": len(runs),
            "completed_runs": len(completed_runs),
            "failed_runs": len(failed_runs),
            "tool_calls": len(tool_calls),
            "approvals": len(approvals),
            "pending_approvals": len(pending_approvals),
            "evaluations": len(evaluations),
            "memories": len(memories),
            "artifacts": len(artifacts),
            "agent_plans": len(agent_plans),
            "plan_evidence_manifests": len(plan_evidence_manifests),
            "verified_plan_evidence_manifests": len(verified_plan_evidence),
        },
        "execution_evidence": execution_evidence,
        "artifact_id": final_artifact["artifact_id"] if final_artifact else None,
        "report_artifact_id": report_artifacts[-1]["artifact_id"] if report_artifacts else None,
        "approval_ids": [approval["approval_id"] for approval in approvals],
        "safe_defaults": {
            "external_upload_performed": False,
            "credentials_stored": False,
            "raw_documents_stored": False,
            "summary_hash_only": True,
        },
    }, 200


def customer_projects_index(conn, limit: int = 25) -> dict:
    tasks = rows_to_dicts(conn.execute(
        "SELECT * FROM tasks WHERE task_id LIKE 'tsk_kb_bot_%' ORDER BY created_at DESC, task_id DESC"
    ).fetchall())
    projects: dict[str, dict] = {}
    for task in tasks:
        match = re.match(r"^tsk_kb_bot_(.+)_\d{2}$", task["task_id"])
        if not match:
            continue
        project_id = match.group(1)
        project = projects.setdefault(project_id, {
            "project_id": project_id,
            "title": "AI 知识库 / 问答机器人",
            "task_ids": [],
            "task_count": 0,
            "completed_tasks": 0,
            "failed_or_blocked_tasks": 0,
            "last_task_id": None,
            "last_run_id": None,
            "delivery_artifact_id": None,
            "report_artifact_id": None,
            "approval_ids": [],
            "pending_approvals": 0,
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at") or task.get("created_at"),
            "report_url": f"/api/workflows/customer-projects/{project_id}/report",
            "ui_report_url": f"/workspace/customer-projects/{project_id}/report",
            "safe_defaults": {
                "external_upload_performed": False,
                "credentials_stored": False,
                "raw_documents_stored": False,
                "summary_hash_only": True,
            },
        })
        project["task_ids"].append(task["task_id"])
        project["task_count"] += 1
        project["last_task_id"] = max(project["last_task_id"] or task["task_id"], task["task_id"])
        if task.get("status") == "completed":
            project["completed_tasks"] += 1
        if task.get("status") in {"failed", "blocked"}:
            project["failed_or_blocked_tasks"] += 1
        created_at = task.get("created_at")
        updated_at = task.get("updated_at") or created_at
        if created_at and (not project.get("created_at") or created_at < project["created_at"]):
            project["created_at"] = created_at
        if updated_at and (not project.get("updated_at") or updated_at > project["updated_at"]):
            project["updated_at"] = updated_at

    for project in projects.values():
        task_ids = project.pop("task_ids")
        placeholders = ",".join("?" for _ in task_ids)
        runs = rows_to_dicts(conn.execute(
            f"SELECT * FROM runs WHERE task_id IN ({placeholders}) ORDER BY started_at DESC, run_id DESC",
            task_ids,
        ).fetchall())
        approvals = rows_to_dicts(conn.execute(
            f"SELECT * FROM approvals WHERE task_id IN ({placeholders}) ORDER BY created_at DESC",
            task_ids,
        ).fetchall())
        artifacts = rows_to_dicts(conn.execute(
            f"SELECT * FROM artifacts WHERE task_id IN ({placeholders}) ORDER BY created_at DESC",
            task_ids,
        ).fetchall())
        delivery_artifact = next((artifact for artifact in artifacts if artifact.get("artifact_type") != "customer_project_report"), None)
        report_artifact = next((artifact for artifact in artifacts if artifact.get("artifact_type") == "customer_project_report"), None)
        project["run_count"] = len(runs)
        project["completed_runs"] = len([run for run in runs if run.get("status") == "completed"])
        project["last_run_id"] = runs[0]["run_id"] if runs else None
        project["approval_ids"] = [approval["approval_id"] for approval in approvals]
        project["pending_approvals"] = len([approval for approval in approvals if approval.get("decision") == "pending"])
        project["artifact_count"] = len(artifacts)
        project["delivery_artifact_id"] = delivery_artifact["artifact_id"] if delivery_artifact else None
        project["report_artifact_id"] = report_artifact["artifact_id"] if report_artifact else None
        if project["failed_or_blocked_tasks"]:
            project["status"] = "needs_attention"
        elif project["pending_approvals"]:
            project["status"] = "waiting_approval"
        elif project["completed_tasks"] >= project["task_count"]:
            project["status"] = "ready"
        else:
            project["status"] = "in_progress"

    ordered = sorted(projects.values(), key=lambda row: row.get("updated_at") or "", reverse=True)
    limit = max(1, min(int(limit or 25), 100))
    return {
        "projects": ordered[:limit],
        "total": len(ordered),
        "limit": limit,
        "safe_defaults": {
            "external_upload_performed": False,
            "credentials_stored": False,
            "raw_documents_stored": False,
            "summary_hash_only": True,
        },
    }


def customer_delivery_board(conn, limit: int = 12) -> dict:
    limit = max(1, min(int(limit or 12), 50))
    artifact_rows = rows_to_dicts(conn.execute(
        """SELECT
            a.*,
            t.title AS task_title,
            t.status AS task_status,
            t.owner_agent_id AS owner_agent_id,
            t.priority AS task_priority,
            t.risk_level AS task_risk_level,
            r.agent_id AS run_agent_id,
            r.status AS run_status,
            r.output_summary AS run_output_summary,
            r.created_at AS run_created_at
        FROM artifacts a
        LEFT JOIN tasks t ON t.task_id = a.task_id
        LEFT JOIN runs r ON r.run_id = a.run_id
        WHERE
            a.artifact_type IN ('customer_worker_result', 'customer_delivery_report', 'customer_project_report')
            OR a.artifact_id LIKE 'art_customer_%'
            OR a.artifact_id LIKE 'art_kb_bot_delivery_%'
        ORDER BY a.created_at DESC
        LIMIT ?""",
        (limit,),
    ).fetchall())
    deliveries: list[dict] = []
    seen_worker_run_ids: set[str] = set()
    totals = {
        "deliveries": 0,
        "ready": 0,
        "waiting_approval": 0,
        "in_progress": 0,
        "needs_attention": 0,
        "pending_approvals": 0,
        "artifacts": 0,
        "verified_plan_evidence_manifests": 0,
        "missing_plan_evidence_manifests": 0,
    }
    for artifact in artifact_rows:
        task_id = artifact.get("task_id")
        run_id = artifact.get("run_id")
        artifact_id = artifact.get("artifact_id")
        if artifact.get("artifact_type") == "customer_worker_result" and run_id:
            if run_id in seen_worker_run_ids:
                continue
            seen_worker_run_ids.add(run_id)
        approvals = rows_to_dicts(conn.execute(
            "SELECT approval_id, decision, reason, created_at, decided_at FROM approvals WHERE task_id=? OR run_id=? ORDER BY created_at DESC LIMIT 8",
            (task_id or "", run_id or ""),
        ).fetchall()) if task_id or run_id else []
        evaluations = rows_to_dicts(conn.execute(
            "SELECT evaluation_id, score, pass_fail, evaluator_type, created_at FROM evaluations WHERE task_id=? OR run_id=? ORDER BY created_at DESC LIMIT 8",
            (task_id or "", run_id or ""),
        ).fetchall()) if task_id or run_id else []
        evidence = {
            "tool_calls": conn.execute("SELECT COUNT(*) c FROM tool_calls WHERE run_id=?", (run_id or "",)).fetchone()["c"] if run_id else 0,
            "evaluations": len(evaluations),
            "runtime_events": conn.execute("SELECT COUNT(*) c FROM runtime_events WHERE run_id=? OR task_id=?", (run_id or "", task_id or "")).fetchone()["c"] if task_id or run_id else 0,
            "audit_logs": conn.execute(
                "SELECT COUNT(*) c FROM audit_logs WHERE entity_id IN (?,?,?)",
                (artifact_id or "", task_id or "", run_id or ""),
            ).fetchone()["c"],
            "approvals": len(approvals),
            "artifacts": 1,
        }
        pending_approvals = [row for row in approvals if row.get("decision") == "pending"]
        failed_eval = [row for row in evaluations if row.get("pass_fail") == "fail"]
        run_status = artifact.get("run_status")
        task_status = artifact.get("task_status")
        delivery_gate = delivery_manifest_gate(conn, run_id) if run_id else {
            "required": True,
            "pass": False,
            "status": "blocked_missing_run",
            "manifest_id": None,
            "message": "Customer delivery requires a run-linked verified plan_evidence_manifest.",
            "token_omitted": True,
        }
        evidence["plan_evidence_manifests"] = 1 if delivery_gate.get("manifest_id") else 0
        if delivery_gate.get("pass"):
            totals["verified_plan_evidence_manifests"] += 1
        else:
            totals["missing_plan_evidence_manifests"] += 1
        if not delivery_gate.get("pass"):
            status = "needs_attention"
            next_action = "Create and verify a plan_evidence_manifest before approving customer delivery."
        elif run_status in {"failed", "blocked", "timeout", "error"} or task_status in {"failed", "blocked"} or failed_eval:
            status = "needs_attention"
            next_action = "Review failed evaluation/run evidence before delivery."
        elif pending_approvals or task_status == "waiting_approval":
            status = "waiting_approval"
            next_action = "Open Approvals and decide the customer delivery gate."
        elif run_status == "completed" and task_status in {"completed", "waiting_approval"}:
            status = "ready"
            next_action = "Open the task/run evidence and package the delivery report."
        else:
            status = "in_progress"
            next_action = "Check the linked run and async job status."
        totals["deliveries"] += 1
        totals[status] += 1
        totals["pending_approvals"] += len(pending_approvals)
        totals["artifacts"] += 1
        title = artifact.get("task_title") or artifact.get("title") or "Customer delivery"
        project_id = None
        match = re.match(r"^art_kb_bot_delivery_(.+)$", artifact_id or "")
        if match:
            project_id = match.group(1)
        if not project_id and task_id:
            task_match = re.match(r"^tsk_kb_bot_(.+)_\d{2}$", task_id)
            if task_match:
                project_id = task_match.group(1)
        deliveries.append({
            "delivery_id": artifact_id,
            "status": status,
            "title": redact_text(title, 160),
            "task_id": task_id,
            "run_id": run_id,
            "artifact_id": artifact_id,
            "artifact_type": artifact.get("artifact_type"),
            "project_id": project_id,
            "owner_agent_id": artifact.get("owner_agent_id") or artifact.get("run_agent_id"),
            "run_status": run_status,
            "task_status": task_status,
            "priority": artifact.get("task_priority"),
            "risk_level": artifact.get("task_risk_level"),
            "summary": redact_text(artifact.get("summary") or artifact.get("run_output_summary") or "", 360),
            "created_at": artifact.get("created_at"),
            "report_url": f"/api/workflows/customer-projects/{project_id}/report" if project_id else None,
            "ui_report_url": f"/workspace/customer-projects/{project_id}/report" if project_id else None,
            "task_url": f"/admin/tasks/{task_id}" if task_id else None,
            "run_url": f"/admin/runs/{run_id}" if run_id else None,
            "approval_ids": [row["approval_id"] for row in approvals],
            "pending_approval_ids": [row["approval_id"] for row in pending_approvals],
            "evaluation_summary": {
                "count": len(evaluations),
                "failed": len(failed_eval),
                "latest_score": evaluations[0]["score"] if evaluations else None,
                "latest_pass_fail": evaluations[0]["pass_fail"] if evaluations else None,
            },
            "delivery_approval_gate": delivery_gate,
            "evidence": evidence,
            "next_action": next_action,
        })
    gates = [
        {"id": "delivery_artifacts", "label": "Customer delivery artifacts", "ok": totals["artifacts"] > 0, "value": totals["artifacts"]},
        {"id": "approval_visibility", "label": "Approval state visible", "ok": True, "value": totals["pending_approvals"]},
        {"id": "plan_evidence_manifest", "label": "Verified plan evidence manifests", "ok": totals["deliveries"] > 0 and totals["missing_plan_evidence_manifests"] == 0, "value": totals["verified_plan_evidence_manifests"]},
        {"id": "evidence_chain", "label": "Run/tool/eval/audit evidence summarized", "ok": all((row.get("evidence") or {}).get("audit_logs", 0) >= 1 for row in deliveries) if deliveries else False, "value": totals["deliveries"]},
        {"id": "safe_readback", "label": "Read-only safe readback", "ok": True, "value": "summary/hash only"},
    ]
    status = "ready" if totals["ready"] > 0 and totals["needs_attention"] == 0 else "attention" if deliveries else "empty"
    return {
        "provider": "agentops-customer",
        "operation": "customer_delivery_board",
        "status": status,
        "summary": totals,
        "deliveries": deliveries,
        "gates": gates,
        "next_actions": [
            "Open waiting approvals before publishing customer-facing results." if totals["pending_approvals"] else "Open the latest ready delivery and review run evidence.",
            "Use `agentops workflow customer-worker-task` for a new customer request.",
            "Use `agentops workflow delivery-board` to inspect this board from CLI/API.",
        ],
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


def hermes_openclaw_loop_readback(conn, loop_id: str | None = None, limit: int = 10) -> dict:
    loop_id = redact_text(loop_id or "", 120)
    limit = max(1, min(int(limit or 10), 50))
    if loop_id:
        artifacts = rows_to_dicts(conn.execute(
            "SELECT * FROM artifacts WHERE uri=? OR uri LIKE ? ORDER BY created_at DESC",
            (f"loop://{loop_id}", f"loop://{loop_id}/%"),
        ).fetchall())
    else:
        artifacts = rows_to_dicts(conn.execute(
            "SELECT * FROM artifacts WHERE uri LIKE 'loop://%' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall())
    run_ids = sorted({row.get("run_id") for row in artifacts if row.get("run_id")})
    task_ids = sorted({row.get("task_id") for row in artifacts if row.get("task_id")})
    if not run_ids:
        return {
            "provider": "agentops-loop-lane",
            "operation": "hermes_openclaw_loop_readback",
            "loop_id": loop_id or None,
            "status": "empty",
            "runs": [],
            "tasks": [],
            "artifacts": artifacts,
            "agent_plans": [],
            "plan_evidence_manifests": [],
            "summary": {"runs": 0, "verified_plan_evidence_manifests": 0, "blocked_plan_evidence_manifests": 0},
            "token_omitted": True,
        }
    run_placeholders = ",".join("?" for _ in run_ids)
    task_placeholders = ",".join("?" for _ in task_ids) if task_ids else "''"
    runs = rows_to_dicts(conn.execute(f"SELECT * FROM runs WHERE run_id IN ({run_placeholders}) ORDER BY created_at", run_ids).fetchall())
    tasks = rows_to_dicts(conn.execute(f"SELECT * FROM tasks WHERE task_id IN ({task_placeholders}) ORDER BY created_at", task_ids).fetchall()) if task_ids else []
    plans = rows_to_dicts(conn.execute(
        f"SELECT * FROM agent_plans WHERE run_id IN ({run_placeholders}) OR task_id IN ({task_placeholders}) ORDER BY created_at",
        [*run_ids, *task_ids],
    ).fetchall())
    manifests = rows_to_dicts(conn.execute(
        f"SELECT * FROM plan_evidence_manifests WHERE run_id IN ({run_placeholders}) ORDER BY created_at",
        run_ids,
    ).fetchall())
    audits = rows_to_dicts(conn.execute(
        f"SELECT * FROM audit_logs WHERE entity_id IN ({run_placeholders}) ORDER BY created_at",
        run_ids,
    ).fetchall())
    verified = [row for row in manifests if row.get("status") == "verified"]
    blocked = [row for row in manifests if row.get("status") == "blocked"]
    failed_runs = [row for row in runs if row.get("status") in {"failed", "blocked", "error", "timeout"}]
    status = "blocked" if failed_runs or blocked else "ready" if verified else "attention"
    return {
        "provider": "agentops-loop-lane",
        "operation": "hermes_openclaw_loop_readback",
        "loop_id": loop_id or None,
        "status": status,
        "runs": runs,
        "tasks": tasks,
        "artifacts": artifacts,
        "agent_plans": plans,
        "plan_evidence_manifests": manifests,
        "audit_logs": audits,
        "summary": {
            "runs": len(runs),
            "tasks": len(tasks),
            "artifacts": len(artifacts),
            "agent_plans": len(plans),
            "plan_evidence_manifests": len(manifests),
            "verified_plan_evidence_manifests": len(verified),
            "blocked_plan_evidence_manifests": len(blocked),
            "failed_runs": len(failed_runs),
        },
        "token_omitted": True,
    }


def run_hermes_openclaw_loop_workflow(body: dict, host_header: str | None = None) -> tuple[dict, int]:
    topic = redact_text(body.get("topic") or "Review the supervised Hermes/OpenClaw loop lane.", 500)
    mode = coerce_choice(body.get("mode"), {"dry-run", "live-hermes", "live-openclaw", "live-both"}, "dry-run")
    rounds = max(1, min(int(body.get("rounds") or 1), 8))
    order = [item for item in safe_json_list(body.get("order")) if item in {"hermes", "openclaw"}] or ["hermes", "openclaw"]
    loop_id = redact_text(body.get("loop_id") or "", 120)
    base_url = body.get("_base_url") or body.get("base_url") or os.environ.get("AGENTOPS_BASE_URL")
    if not base_url and host_header:
        base_url = f"http://{host_header}"
    base_url = base_url or "http://127.0.0.1:8787"
    request_timeout = str(max(1, min(int(body.get("request_timeout") or 30), 300)))
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "hermes_openclaw_loop.py"),
        "--topic",
        topic,
        "--rounds",
        str(rounds),
        "--mode",
        mode,
        "--mis-ledger",
        "--base-url",
        base_url,
        "--workspace-id",
        normalize_workspace_id(body.get("workspace_id") or "local-demo"),
        "--request-timeout",
        request_timeout,
        "--max-agent-attempts",
        str(max(1, min(int(body.get("max_agent_attempts") or 1), 5))),
        "--retry-delay-sec",
        str(max(0.0, min(float(body.get("retry_delay_sec") or 1.0), 30.0))),
        "--order",
        *order,
    ]
    if loop_id:
        cmd.extend(["--loop-id", loop_id])
    if body.get("resume"):
        cmd.append("--resume")
    if body.get("confirm_live"):
        cmd.append("--confirm-live")
    for agent in safe_json_list(body.get("simulate_failure_agent")):
        if agent in {"hermes", "openclaw"}:
            cmd.extend(["--simulate-failure-agent", agent])
    for key, flag in [
        ("runtime_dir", "--runtime-dir"),
        ("hermes_url", "--hermes-url"),
        ("hermes_model", "--hermes-model"),
        ("hermes_timeout", "--hermes-timeout"),
        ("openclaw_bin", "--openclaw-bin"),
        ("openclaw_agent", "--openclaw-agent"),
        ("openclaw_timeout", "--openclaw-timeout"),
    ]:
        if body.get(key):
            cmd.extend([flag, str(body[key])])
    env = os.environ.copy()
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    started = dt.datetime.now(dt.timezone.utc)
    timeout = max(60, int(request_timeout) * max(rounds, 1) * max(len(order), 1) + 30)
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False, env=env)
    duration_ms = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"raw": redact_text(proc.stdout, 1000)}
    payload["provider"] = "agentops-loop-lane"
    payload["workflow"] = "hermes_openclaw_loop"
    payload["duration_ms"] = duration_ms
    payload["stderr_summary"] = redact_text(proc.stderr, 500) if proc.stderr else None
    payload["token_omitted"] = True
    return payload, 201 if proc.returncode == 0 else 409


def human_review_queue(conn, limit: int = 20) -> dict:
    limit = max(1, min(int(limit or 20), 100))
    per_lane_limit = max(limit, 10)
    approval_total = conn.execute("SELECT COUNT(*) c FROM approvals WHERE decision='pending'").fetchone()["c"]
    memory_total = conn.execute("SELECT COUNT(*) c FROM memories WHERE review_status='candidate'").fetchone()["c"]
    approvals = rows_to_dicts(conn.execute(
        """SELECT approval_id, task_id, run_id, tool_call_id, requested_by_agent_id,
                  approver_user_id, decision, reason, expires_at, created_at, decided_at
           FROM approvals
           WHERE decision='pending'
           ORDER BY created_at DESC
           LIMIT ?""",
        (per_lane_limit,),
    ).fetchall())
    memories = rows_to_dicts(conn.execute(
        """SELECT memory_id, scope, memory_type, canonical_text, source_type, source_ref,
                  project_id, task_id, agent_id, confidence, review_status, access_tags,
                  created_at, updated_at
           FROM memories
           WHERE review_status='candidate'
           ORDER BY updated_at DESC
           LIMIT ?""",
        (per_lane_limit,),
    ).fetchall())
    delivery_board = customer_delivery_board(conn, min(per_lane_limit, 50))
    delivery_focus = [
        row for row in delivery_board.get("deliveries", [])
        if row.get("status") in {"waiting_approval", "needs_attention", "ready"}
    ][:per_lane_limit]

    items: list[dict] = []
    for row in approvals:
        approval_id = row.get("approval_id")
        if (approval_id or "").startswith("ap_gw_enroll_") or "enrollment" in (row.get("reason") or "").lower():
            approval_kind = "agent_enrollment"
        elif row.get("tool_call_id"):
            approval_kind = "tool_call"
        else:
            approval_kind = "delivery_or_run"
        items.append({
            "item_type": "approval",
            "item_id": approval_id,
            "status": row.get("decision"),
            "kind": approval_kind,
            "title": f"Approval required: {approval_kind}",
            "summary": redact_text(row.get("reason") or "Pending approval requires human decision.", 260),
            "task_id": row.get("task_id"),
            "run_id": row.get("run_id"),
            "agent_id": row.get("requested_by_agent_id"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("decided_at") or row.get("created_at"),
            "expires_at": row.get("expires_at"),
            "links": {
                "task_url": f"/admin/tasks/{row.get('task_id')}" if row.get("task_id") else None,
                "run_url": f"/admin/runs/{row.get('run_id')}" if row.get("run_id") else None,
                "approvals_url": "/workspace/approvals",
            },
            "next_action": "Approve or reject this gate before the linked work is delivered.",
            "cli_action": f"agentops approval approve --approval-id {approval_id}",
            "alternate_cli_action": f"agentops approval reject --approval-id {approval_id}",
        })

    for row in memories:
        memory_id = row.get("memory_id")
        try:
            access_tags = json.loads(row.get("access_tags") or "[]")
        except Exception:
            access_tags = []
        if not isinstance(access_tags, list):
            access_tags = []
        items.append({
            "item_type": "memory_candidate",
            "item_id": memory_id,
            "status": row.get("review_status"),
            "kind": row.get("memory_type"),
            "title": f"Memory candidate: {row.get('memory_type')}",
            "summary": redact_text(row.get("canonical_text") or "", 260),
            "task_id": row.get("task_id"),
            "run_id": row.get("source_ref") if (row.get("source_ref") or "").startswith("run_") else None,
            "agent_id": row.get("agent_id"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at") or row.get("created_at"),
            "confidence": row.get("confidence"),
            "scope": row.get("scope"),
            "access_tags": access_tags[:8],
            "links": {
                "task_url": f"/admin/tasks/{row.get('task_id')}" if row.get("task_id") else None,
                "memory_url": "/memory",
            },
            "next_action": "Approve useful reusable knowledge or reject noisy memory.",
            "cli_action": f"agentops memory approve --memory-id {memory_id}",
            "alternate_cli_action": f"agentops memory reject --memory-id {memory_id}",
        })

    for row in delivery_focus:
        delivery_id = row.get("delivery_id") or row.get("artifact_id")
        if row.get("status") == "waiting_approval":
            next_action = "Resolve pending delivery approval before sending this to the customer."
        elif row.get("status") == "needs_attention":
            next_action = "Inspect failed/blocked evidence before approving delivery."
        else:
            next_action = "Review the evidence package and archive/share the customer report."
        pending_ids = row.get("pending_approval_ids") or []
        items.append({
            "item_type": "customer_delivery",
            "item_id": delivery_id,
            "status": row.get("status"),
            "kind": row.get("artifact_type"),
            "title": row.get("title") or "Customer delivery",
            "summary": redact_text(row.get("summary") or "", 260),
            "task_id": row.get("task_id"),
            "run_id": row.get("run_id"),
            "agent_id": row.get("owner_agent_id"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("created_at"),
            "artifact_id": row.get("artifact_id"),
            "approval_ids": row.get("approval_ids") or [],
            "pending_approval_ids": pending_ids,
            "links": {
                "task_url": row.get("task_url"),
                "run_url": row.get("run_url"),
                "report_url": row.get("ui_report_url") or row.get("report_url"),
            },
            "next_action": next_action,
            "cli_action": (
                f"agentops approval approve --approval-id {pending_ids[0]}"
                if pending_ids else f"agentops workflow delivery-board --limit {min(limit, 20)}"
            ),
            "alternate_cli_action": (
                f"agentops approval reject --approval-id {pending_ids[0]}"
                if pending_ids else None
            ),
        })

    def sort_key(item: dict) -> str:
        return item.get("updated_at") or item.get("created_at") or ""

    review_items = sorted(items, key=sort_key, reverse=True)[:limit]
    delivery_summary = delivery_board.get("summary") or {}
    summary = {
        "pending_approvals": int(approval_total or 0),
        "memory_candidates": int(memory_total or 0),
        "ready_deliveries": int(delivery_summary.get("ready") or 0),
        "waiting_deliveries": int(delivery_summary.get("waiting_approval") or 0),
        "needs_attention_deliveries": int(delivery_summary.get("needs_attention") or 0),
        "review_items_total": len(items),
        "returned_items": len(review_items),
        "retrieved_pending_approvals": len(approvals),
        "retrieved_memory_candidates": len(memories),
    }
    if summary["pending_approvals"] or summary["memory_candidates"] or summary["waiting_deliveries"] or summary["needs_attention_deliveries"]:
        status = "attention"
    elif summary["ready_deliveries"]:
        status = "ready"
    else:
        status = "empty"
    safe_approvals = []
    for row in approvals:
        safe_row = dict(row)
        safe_row["reason"] = redact_text(safe_row.get("reason") or "", 260)
        safe_approvals.append(safe_row)
    safe_memories = []
    for row in memories:
        safe_row = dict(row)
        safe_row["canonical_text"] = redact_text(safe_row.get("canonical_text") or "", 260)
        safe_memories.append(safe_row)
    return {
        "provider": "agentops-review",
        "operation": "human_review_queue",
        "status": status,
        "limit": limit,
        "summary": summary,
        "review_items": review_items,
        "lanes": {
            "pending_approvals": safe_approvals,
            "memory_candidates": safe_memories,
            "customer_deliveries": delivery_focus,
        },
        "gates": [
            {"id": "pending_approvals_visible", "label": "Pending approvals visible", "ok": True, "value": summary["pending_approvals"]},
            {"id": "memory_candidates_visible", "label": "Memory candidates visible", "ok": True, "value": summary["memory_candidates"]},
            {"id": "delivery_board_visible", "label": "Delivery board visible", "ok": True, "value": len(delivery_focus)},
            {"id": "safe_readback", "label": "Read-only safe readback", "ok": True, "value": "summary/hash only"},
        ],
        "next_actions": [
            "Start with the first review item; do not wait for slower workers if this item is ready.",
            "Use `agentops review queue` for the combined queue, then approve/reject individual gates.",
            "Use `agentops commander inbox` for async worker lane state and `agentops workflow delivery-board` for customer handoff.",
        ],
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


def customer_project_report_artifact(conn, project_id: str) -> tuple[dict, int]:
    report, status = customer_project_report(conn, project_id)
    if status != 200:
        return report, status
    project_id = report["project_id"]
    tasks = rows_to_dicts(conn.execute(
        "SELECT * FROM tasks WHERE task_id LIKE ? ORDER BY task_id",
        (f"tsk_kb_bot_{project_id}_%",),
    ).fetchall())
    final_task = tasks[-1] if tasks else {}
    final_run = None
    if final_task:
        final_run = conn.execute(
            "SELECT * FROM runs WHERE task_id=? ORDER BY started_at DESC, run_id DESC LIMIT 1",
            (final_task["task_id"],),
        ).fetchone()
    markdown = report.get("markdown") or ""
    content_hash = stable_hash(markdown)
    counts = report.get("counts") or {}
    artifact_id = stable_id("art_customer_project_report", project_id)
    summary = redact_text(
        (
            f"客户项目 {project_id} 交付报告："
            f"{counts.get('tasks', 0)} tasks, {counts.get('runs', 0)} runs, "
            f"{counts.get('tool_calls', 0)} tool calls, "
            f"{counts.get('pending_approvals', 0)} pending approvals. "
            "Stored as summary/hash ledger evidence only."
        ),
        520,
    )
    row = {
        "artifact_id": artifact_id,
        "task_id": final_task.get("task_id"),
        "run_id": final_run["run_id"] if final_run else None,
        "artifact_type": "customer_project_report",
        "title": f"客户项目交付报告：{project_id}",
        "uri": f"agentops://customer-projects/{project_id}/report",
        "summary": summary,
        "created_at": now_iso(),
    }
    before, _artifact_outcome = repo_upsert_artifact(conn, row)
    runtime_event(
        conn,
        "rtc_agent_gateway_local",
        "customer_project.report_artifact",
        "completed",
        run_id=row["run_id"],
        task_id=row["task_id"],
        agent_id=final_task.get("owner_agent_id"),
        output_summary=summary,
        raw_payload_hash=content_hash,
    )
    metadata = safe_json_metadata({
        "project_id": project_id,
        "content_hash": content_hash,
        "report_url": f"/api/workflows/customer-projects/{project_id}/report",
        "raw_report_omitted": True,
        "external_upload_performed": False,
        "credentials_stored": False,
        "raw_documents_stored": False,
    })
    audit(conn, "system", "customer_project_report", "workflow.customer_project.report_artifact", "artifacts", artifact_id, dict(before) if before else None, row, metadata)
    return {
        "ok": True,
        "created": before is None,
        "artifact": row,
        "project_id": project_id,
        "report_url": f"/api/workflows/customer-projects/{project_id}/report",
        "content_hash": content_hash,
        "raw_report_omitted": True,
        "token_omitted": True,
        "safe_defaults": report.get("safe_defaults"),
    }, 201 if before is None else 200


def hermes_run_task(conn, body: dict) -> dict:
    cfg = hermes_runtime_config()
    status = hermes_status()
    refresh_runtime_connectors(conn, status)
    confirm = bool(body.get("confirm_run"))
    prompt = "请只回复 HERMES_DEFAULT_RUN_OK，不要解释。"
    prompt_hash = stable_hash(prompt)
    plan = {
        "created": False,
        "dry_run": True,
        "provider": "hermes",
        "mode": "default_gateway_fixed_probe",
        "would_post": status["gateway_url"].rstrip("/") + "/v1/chat/completions",
        "prompt_hash": prompt_hash,
        "requires": {"HERMES_ALLOW_REAL_RUN": True, "confirm_run": True, "api_listening": True},
        "note": "Only a fixed safe probe is enabled here. Arbitrary Hermes task prompts remain disabled.",
    }
    risk = body.get("risk_level", "low")
    if risk not in ("low", "medium") and not body.get("confirm_run"):
        return {"created": False, "dry_run": True, "requires_confirm_run": True, "reason": "High-risk runtime tasks require confirm_run=true."}
    if not (cfg["allow_real_run"] and confirm and status["api_listening"]):
        runtime_event(conn, "rtc_hermes_default_gateway", "run_task_dry_run", "planned", prompt_hash=prompt_hash, input_summary="Hermes default fixed run-task dry-run.")
        audit(conn, "system", "hermes-run-task", "runtime.run_task.dry_run", "runtime_connectors", "rtc_hermes_default_gateway", None, plan, {"confirm_run": confirm, "api_listening": status["api_listening"]})
        conn.commit()
        return plan

    agent_id = "agt_hermes_gateway"
    upsert_agent(conn, {
        "agent_id": agent_id,
        "name": "Hermes Gateway",
        "role": "Hermes Runtime Gateway",
        "description": "Local Hermes gateway fixed runtime task target.",
        "runtime_type": "hermes",
        "model_provider": "hermes",
        "model_name": "hermes-agent",
        "status": "idle",
        "permission_level": "manager",
        "allowed_tools": json.dumps(["hermes.gateway", "openai_compatible.chat", "runtime.probe"], ensure_ascii=False),
        "budget_limit_usd": 10.0,
        "owner_user_id": "usr_founder",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, "hermes-run-task")
    task_id = "tsk_hermes_default_run_task"
    upsert_task(conn, {
        "task_id": task_id,
        "title": "Hermes default gateway fixed runtime task",
        "description": "Confirmed low-risk Hermes default gateway run. Full prompt and raw response are not stored.",
        "requester_id": "usr_founder",
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
        "status": "planned",
        "priority": "high",
        "due_date": None,
        "acceptance_criteria": "Hermes default gateway returns the fixed marker and writes run/evaluation/audit evidence.",
        "risk_level": "low",
        "budget_limit_usd": 1.0,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }, "hermes-run-task")

    started_iso = now_iso()
    started = dt.datetime.now(dt.timezone.utc)
    payload = {"model": "hermes-agent", "messages": [{"role": "user", "content": prompt}], "temperature": 0}
    ok = False
    visible = None
    error = None
    response_hash = None
    try:
        req = Request(
            status["gateway_url"].rstrip("/") + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(req, timeout=180) as res:
            response = json.loads(res.read().decode("utf-8"))
        response_hash = stable_hash(response)
        visible = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        visible = redact_text(visible, 200)
        ok = visible == "HERMES_DEFAULT_RUN_OK"
        if not ok:
            error = redact_text(visible or "unexpected response", 240)
    except Exception as exc:
        error = redact_text(str(exc), 240)

    duration = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    run_id = stable_id("run_hermes_default_task", dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))
    row = {
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": "hermes",
        "status": "completed" if ok else "failed",
        "started_at": started_iso,
        "ended_at": now_iso(),
        "duration_ms": duration,
        "input_summary": f"Hermes default fixed probe prompt_hash={prompt_hash[:16]}",
        "output_summary": "Hermes default gateway returned HERMES_DEFAULT_RUN_OK." if ok else "Hermes default gateway fixed probe failed.",
        "model_provider": "hermes",
        "model_name": "hermes-agent",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.0,
        "error_type": None if ok else "HermesDefaultRunTaskFailed",
        "error_message": error,
        "trace_id": None,
        "parent_run_id": None,
        "delegation_id": "hermes:default-gateway",
        "approval_required": 0,
        "created_at": started_iso,
    }
    upsert_run(conn, row, "hermes-run-task", {"prompt_hash": prompt_hash, "raw_payload_hash": response_hash})
    upsert_evaluation(conn, quality_gate_for_run(row), "hermes-run-task")
    runtime_event(conn, "rtc_hermes_default_gateway", "run_task", "completed" if ok else "failed", run_id=run_id, task_id=task_id, agent_id=agent_id, model_name="hermes-agent", latency_ms=duration, prompt_hash=prompt_hash, output_summary=visible, error_message=error, raw_payload_hash=response_hash)
    audit(conn, "system", "hermes-run-task", "runtime.run_task", "runs", run_id, None, {"status": row["status"]}, {"prompt_hash": prompt_hash, "confirmed": True})
    conn.commit()
    return {"created": True, "dry_run": False, "provider": "hermes", "mode": "default_gateway_fixed_probe", "ok": ok, "run_id": run_id, "task_id": task_id, "duration_ms": duration, "output_summary": row["output_summary"], "error": error}


def worker_runtime_path(adapter: str, suffix: str) -> Path:
    safe = coerce_choice(adapter, {"mock", "hermes", "openclaw"}, "mock")
    return WORKER_RUNTIME_DIR / f"{safe}.{suffix}"


def pid_is_alive(pid) -> bool:
    try:
        value = int(pid)
    except Exception:
        return False
    if value <= 0:
        return False
    try:
        waited_pid, _status = os.waitpid(value, os.WNOHANG)
        if waited_pid == value:
            return False
    except ChildProcessError:
        pass
    except Exception:
        pass
    try:
        stat = subprocess.run(["ps", "-o", "stat=", "-p", str(value)], capture_output=True, text=True, timeout=2, check=False)
        if stat.returncode == 0 and stat.stdout.strip().startswith("Z"):
            return False
    except Exception:
        pass
    try:
        os.kill(value, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def tail_text(path: Path, max_lines: int = 30) -> list[str]:
    try:
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except Exception as exc:
        return [f"[log unavailable] {redact_text(str(exc), 120)}"]


def read_worker_daemon(adapter: str, include_log: bool = False) -> dict:
    pid_path = worker_runtime_path(adapter, "json")
    log_path = worker_runtime_path(adapter, "log")
    state_path = worker_runtime_path(adapter, "state.json")
    meta = read_json_file(pid_path, {}) if pid_path.exists() else {}
    state = read_json_file(state_path, {}) if state_path.exists() else {}
    pid = meta.get("pid")
    alive = pid_is_alive(pid)
    status = "running" if alive else "stopped" if meta.get("stopped_at") else "dead" if meta else "not_started"
    worker_status = state.get("status")
    if alive and worker_status in {"error", "failed", "failed_max_errors"}:
        status = "degraded"
    payload = {
        "adapter": adapter,
        "status": status,
        "running": alive,
        "pid": pid,
        "agent_id": meta.get("agent_id"),
        "started_at": meta.get("started_at"),
        "stopped_at": meta.get("stopped_at"),
        "last_exit_note": meta.get("last_exit_note"),
        "poll_interval": meta.get("poll_interval"),
        "max_tasks": meta.get("max_tasks"),
        "confirm_run": bool(meta.get("confirm_run")),
        "log_path": str(log_path),
        "state_path": str(state_path),
        "worker_status": worker_status,
        "state_updated_at": state.get("updated_at"),
        "processed": int(state.get("processed") or 0),
        "iterations": int(state.get("iterations") or 0),
        "total_errors": int(state.get("total_errors") or 0),
        "consecutive_errors": int(state.get("consecutive_errors") or 0),
        "last_sleep_reason": state.get("last_sleep_reason"),
        "last_sleep_sec": state.get("last_sleep_sec"),
        "last_error": state.get("last_error"),
        "last_result": state.get("last_result"),
        "continue_on_error": bool(state.get("continue_on_error")),
    }
    if include_log:
        payload["log_tail"] = tail_text(log_path, 80)
    return payload


def worker_daemon_status(include_log: bool = False) -> list[dict]:
    return [read_worker_daemon(adapter, include_log=include_log) for adapter in ("mock", "hermes", "openclaw")]


def start_local_worker_daemon(conn, body: dict) -> tuple[dict, int]:
    adapter = coerce_choice(body.get("adapter"), {"mock", "hermes", "openclaw"}, "mock")
    confirm_run = bool(body.get("confirm_run"))
    if adapter in {"hermes", "openclaw"} and not confirm_run:
        return {
            "provider": "agentops-worker",
            "ok": False,
            "adapter": adapter,
            "error": "confirm_run:true is required for Hermes/OpenClaw live worker daemons.",
        }, 400

    existing = read_worker_daemon(adapter)
    if existing["running"]:
        return {"provider": "agentops-worker", "ok": True, "already_running": True, "daemon": existing}, 200

    WORKER_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    agent_id = body.get("agent_id") or f"agt_worker_daemon_{adapter}"
    poll_interval = min(max(float(body.get("poll_interval") or 5.0), 1.0), 300.0)
    max_tasks = max(int(body.get("max_tasks") or 0), 0)
    status_filters = body.get("status") if isinstance(body.get("status"), list) else ["planned"]
    status_filters = [coerce_choice(str(item), VALID_TASK_STATUSES, "planned") for item in status_filters if item]
    if not status_filters:
        status_filters = ["planned"]

    ensure_gateway_agent(
        conn,
        agent_id,
        name=f"Daemon {adapter} Worker",
        role=f"Local {adapter} Adapter Daemon",
        runtime_type=adapter,
    )
    conn.execute("UPDATE agents SET status=?, updated_at=? WHERE agent_id=?", ("running", now_iso(), agent_id))
    conn.commit()

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "agent_worker.py"),
        "--adapter",
        adapter,
        "--agent-id",
        agent_id,
        "--base-url",
        os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"),
        "--poll-interval",
        str(poll_interval),
        "--max-tasks",
        str(max_tasks),
        "--continue-on-error",
        "--max-errors",
        str(max(int(body.get("max_errors") or 5), 1)),
        "--state-path",
        str(worker_runtime_path(adapter, "state.json")),
        "--jsonl-log",
    ]
    for status in status_filters:
        cmd.extend(["--status", status])
    if confirm_run:
        cmd.append("--confirm-run")
    if adapter == "hermes":
        cmd.extend(["--hermes-gateway-url", os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642")])
    if adapter == "openclaw":
        cmd.extend(["--openclaw-bin", str(OPENCLAW_BIN), "--openclaw-timeout", str(int(body.get("openclaw_timeout") or 180))])

    log_path = worker_runtime_path(adapter, "log")
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{now_iso()}] starting {' '.join(shlex.quote(part) for part in cmd)}\n")
        log.flush()
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True)

    meta = {
        "adapter": adapter,
        "agent_id": agent_id,
        "pid": proc.pid,
        "started_at": now_iso(),
        "stopped_at": None,
        "poll_interval": poll_interval,
        "max_tasks": max_tasks,
        "status_filters": status_filters,
        "confirm_run": confirm_run,
        "cmd": [part if "key" not in part.lower() and "token" not in part.lower() else "[REDACTED]" for part in cmd],
        "continue_on_error": True,
        "max_errors": max(int(body.get("max_errors") or 5), 1),
        "state_path": str(worker_runtime_path(adapter, "state.json")),
    }
    worker_runtime_path(adapter, "json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    runtime_event(conn, "rtc_agent_gateway_local", "worker.daemon.start", "running", agent_id=agent_id, output_summary=f"Started {adapter} local worker daemon pid={proc.pid}.")
    audit(conn, "user", "usr_founder", "worker.daemon.start", "agents", agent_id, None, {"pid": proc.pid, "adapter": adapter}, {"poll_interval": poll_interval, "max_tasks": max_tasks, "confirm_run": confirm_run})
    conn.commit()
    return {"provider": "agentops-worker", "ok": True, "daemon": read_worker_daemon(adapter, include_log=True)}, 201


def stop_local_worker_daemon(conn, body: dict) -> tuple[dict, int]:
    requested = body.get("adapter")
    adapters = ["mock", "hermes", "openclaw"] if requested in (None, "", "all") else [coerce_choice(requested, {"mock", "hermes", "openclaw"}, "mock")]
    stopped = []
    for adapter in adapters:
        pid_path = worker_runtime_path(adapter, "json")
        meta = read_json_file(pid_path, {}) if pid_path.exists() else {}
        pid = meta.get("pid")
        was_alive = pid_is_alive(pid)
        note = "not_running"
        if was_alive:
            try:
                os.killpg(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except Exception:
                    pass
            time_waited = 0.0
            while pid_is_alive(pid) and time_waited < 2.0:
                time.sleep(0.2)
                time_waited += 0.2
            if pid_is_alive(pid):
                try:
                    os.killpg(int(pid), signal.SIGKILL)
                except Exception:
                    try:
                        os.kill(int(pid), signal.SIGKILL)
                    except Exception:
                        pass
                note = "killed_after_timeout"
            else:
                note = "terminated"
        meta.update({"stopped_at": now_iso(), "last_exit_note": note})
        WORKER_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        state_path = worker_runtime_path(adapter, "state.json")
        state = read_json_file(state_path, {}) if state_path.exists() else {}
        state.update({"status": "stopped", "stopped_at": now_iso(), "updated_at": now_iso(), "last_exit_note": note})
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        agent_id = meta.get("agent_id") or f"agt_worker_daemon_{adapter}"
        agent_exists = conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
        if agent_exists:
            conn.execute("UPDATE agents SET status=?, updated_at=? WHERE agent_id=?", ("paused", now_iso(), agent_id))
        runtime_event(conn, "rtc_agent_gateway_local", "worker.daemon.stop", "completed", agent_id=agent_id if agent_exists else None, output_summary=f"Stopped {adapter} local worker daemon: {note}.")
        audit(conn, "user", "usr_founder", "worker.daemon.stop", "agents", agent_id, None, {"adapter": adapter, "note": note}, {"pid": pid})
        stopped.append(read_worker_daemon(adapter, include_log=True))
    conn.commit()
    return {"provider": "agentops-worker", "ok": True, "daemons": stopped}, 200


def restart_local_worker_daemon(conn, body: dict) -> tuple[dict, int]:
    adapter = coerce_choice(body.get("adapter"), {"mock", "hermes", "openclaw"}, "mock")
    confirm_run = bool(body.get("confirm_run"))
    if adapter in {"hermes", "openclaw"} and not confirm_run:
        return {
            "provider": "agentops-worker",
            "ok": False,
            "adapter": adapter,
            "error": "confirm_run:true is required before restarting Hermes/OpenClaw live worker daemons.",
        }, 400
    meta_path = worker_runtime_path(adapter, "json")
    meta = read_json_file(meta_path, {}) if meta_path.exists() else {}
    previous = read_worker_daemon(adapter, include_log=True)
    restart_body = {
        "adapter": adapter,
        "agent_id": body.get("agent_id") or meta.get("agent_id") or f"agt_worker_daemon_{adapter}",
        "poll_interval": body.get("poll_interval") if body.get("poll_interval") is not None else meta.get("poll_interval") or 5.0,
        "max_tasks": body.get("max_tasks") if body.get("max_tasks") is not None else meta.get("max_tasks") or 0,
        "max_errors": body.get("max_errors") if body.get("max_errors") is not None else meta.get("max_errors") or 5,
        "status": body.get("status") if isinstance(body.get("status"), list) else meta.get("status_filters") or ["planned"],
        "confirm_run": confirm_run,
    }
    if body.get("openclaw_timeout") is not None:
        restart_body["openclaw_timeout"] = body.get("openclaw_timeout")
    stopped, _stop_status = stop_local_worker_daemon(conn, {"adapter": adapter})
    started, start_status = start_local_worker_daemon(conn, restart_body)
    ok = bool(started.get("ok"))
    daemon = started.get("daemon") or read_worker_daemon(adapter, include_log=True)
    agent_id = daemon.get("agent_id") or restart_body["agent_id"]
    runtime_event(conn, "rtc_agent_gateway_local", "worker.daemon.restart", "running" if ok else "failed", agent_id=agent_id, output_summary=f"Restarted {adapter} local worker daemon." if ok else f"Failed to restart {adapter} local worker daemon.")
    audit(conn, "user", "usr_founder", "worker.daemon.restart", "agents", agent_id, previous, daemon, {"adapter": adapter, "confirm_run": confirm_run, "token_omitted": True})
    conn.commit()
    return {
        "provider": "agentops-worker",
        "ok": ok,
        "adapter": adapter,
        "previous": previous,
        "stopped": stopped,
        "daemon": daemon,
        "start_result": started,
        "token_omitted": True,
        "live_execution_performed": False,
    }, start_status


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


def worker_stuck_tasks(conn, threshold_sec: int = 900, limit: int = 25) -> list[dict]:
    threshold_sec = max(int(threshold_sec or 900), 30)
    limit = min(max(int(limit or 25), 1), 100)
    now_dt = dt.datetime.now(dt.timezone.utc)
    cutoff = now_dt - dt.timedelta(seconds=threshold_sec)
    tasks = rows_to_dicts(conn.execute(
        """SELECT * FROM tasks
        WHERE status='running' AND (owner_agent_id LIKE 'agt_worker_%' OR owner_agent_id LIKE 'agt_remote_%' OR owner_agent_id LIKE 'agt_launch_%')
        ORDER BY updated_at ASC LIMIT ?""",
        (limit,),
    ).fetchall())
    stuck = []
    for task in tasks:
        updated = parse_iso_datetime(task.get("updated_at") or task.get("created_at"))
        age_sec = int((now_dt - updated).total_seconds()) if updated else 0
        running_run = conn.execute(
            """SELECT * FROM runs WHERE task_id=? AND status='running' ORDER BY started_at DESC LIMIT 1""",
            (task["task_id"],),
        ).fetchone()
        run_started = parse_iso_datetime(running_run["started_at"]) if running_run else None
        run_age_sec = int((now_dt - run_started).total_seconds()) if run_started else 0
        if (updated and updated < cutoff) or (run_started and run_started < cutoff):
            item = dict(task)
            item["age_sec"] = max(age_sec, run_age_sec)
            item["threshold_sec"] = threshold_sec
            item["running_run_id"] = running_run["run_id"] if running_run else None
            item["running_run_started_at"] = running_run["started_at"] if running_run else None
            item["stuck_reason"] = "running_task_exceeded_threshold"
            stuck.append(item)
    return stuck


def release_worker_task(conn, body: dict) -> tuple[dict, int]:
    task_id = body.get("task_id")
    if not task_id:
        return {"error": "task_id is required"}, 400
    task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not task:
        return {"error": "task not found"}, 404
    if task["status"] != "running" and not body.get("force"):
        return {"error": "conflict", "message": f"Task {task_id} is not running.", "status": task["status"]}, 409
    now = now_iso()
    before = dict(task)
    running_runs = rows_to_dicts(conn.execute(
        "SELECT * FROM runs WHERE task_id=? AND status='running' ORDER BY started_at DESC",
        (task_id,),
    ).fetchall())
    for run in running_runs:
        conn.execute(
            """UPDATE runs SET status='blocked', ended_at=?, error_type=?, error_message=?
            WHERE run_id=? AND status='running'""",
            (now, "WorkerTaskReleased", "Task was released back to the worker queue by an operator.", run["run_id"]),
        )
        runtime_event(conn, "rtc_agent_gateway_local", "worker.task.release_run", "blocked", run_id=run["run_id"], task_id=task_id, agent_id=run["agent_id"], output_summary="Running run blocked because the task was released for recovery.")
    conn.execute("UPDATE tasks SET status='planned', owner_agent_id=NULL, updated_at=? WHERE task_id=?", (now, task_id))
    after = dict(conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone())
    runtime_event(conn, "rtc_agent_gateway_local", "worker.task.release", "completed", task_id=task_id, agent_id=before.get("owner_agent_id"), output_summary=f"Released {task_id} back to planned worker queue.")
    audit(conn, "user", "usr_founder", "worker.task.release", "tasks", task_id, before, after, {"released_runs": [run["run_id"] for run in running_runs], "reason": redact_text(body.get("reason") or "operator_release", 200)})
    return {"released": True, "task": after, "released_runs": [run["run_id"] for run in running_runs], "token_omitted": True}, 200


def worker_stale_never_seen_enrollments(conn, enrollment_age_sec: int = 900, limit: int = 25) -> list[dict]:
    enrollment_age_sec = max(int(enrollment_age_sec or 900), 0)
    limit = min(max(int(limit or 25), 1), 100)
    now_dt = dt.datetime.now(dt.timezone.utc)
    cutoff = now_dt - dt.timedelta(seconds=enrollment_age_sec)
    rows = agent_gateway_enrollment_rows(conn)
    stale: list[dict] = []
    for row in rows:
        if row.get("status") != "active" or row.get("heartbeat_state") != "never_seen":
            continue
        created = parse_iso_datetime(row.get("created_at"))
        age_sec = int((now_dt - created).total_seconds()) if created else 0
        if created and created <= cutoff:
            item = dict(row)
            item["age_sec"] = age_sec
            item["threshold_sec"] = enrollment_age_sec
            item["stale_reason"] = "active_enrollment_never_heartbeated"
            stale.append(item)
        if len(stale) >= limit:
            break
    return stale


def worker_fleet_hygiene(conn, body: dict | None = None, *, apply: bool = False) -> tuple[dict, int]:
    body = body or {}
    threshold_raw = body.get("threshold_sec")
    enrollment_age_raw = body.get("enrollment_age_sec")
    limit_raw = body.get("limit")
    threshold_sec = max(int(threshold_raw if threshold_raw is not None else 900), 30)
    enrollment_age_sec = max(int(enrollment_age_raw if enrollment_age_raw is not None else 900), 0)
    limit = min(max(int(limit_raw if limit_raw is not None else 25), 1), 100)
    stuck_tasks = worker_stuck_tasks(conn, threshold_sec, limit)
    stale_enrollments = worker_stale_never_seen_enrollments(conn, enrollment_age_sec, limit)
    plan = {
        "provider": "agentops-worker",
        "operation": "fleet_hygiene",
        "status": "actionable" if stuck_tasks or stale_enrollments else "ready",
        "threshold_sec": threshold_sec,
        "enrollment_age_sec": enrollment_age_sec,
        "summary": {
            "stuck_tasks": len(stuck_tasks),
            "stale_never_seen_enrollments": len(stale_enrollments),
            "actions_available": len(stuck_tasks) + len(stale_enrollments),
        },
        "stuck_tasks": stuck_tasks,
        "stale_never_seen_enrollments": stale_enrollments,
        "recommended_actions": [
            "agentops worker hygiene --apply --confirm-cleanup",
        ] if stuck_tasks or stale_enrollments else ["agentops worker status"],
        "safety": {
            "read_only": not apply,
            "requires_confirm_cleanup": True,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }
    if not apply:
        return plan, 200
    if body.get("confirm_cleanup") is not True:
        plan["applied"] = False
        plan["error"] = "confirm_cleanup_required"
        return plan, 409

    released: list[dict] = []
    revoked: list[dict] = []
    errors: list[dict] = []
    for task in stuck_tasks:
        payload, status = release_worker_task(conn, {
            "task_id": task["task_id"],
            "reason": body.get("release_reason") or "fleet_hygiene_cleanup",
        })
        if status == 200:
            released.append({"task_id": task["task_id"], "released_runs": payload.get("released_runs", [])})
        else:
            errors.append({"kind": "task_release", "task_id": task.get("task_id"), "status": status, "error": payload})
    for enrollment in stale_enrollments:
        payload, status = agent_gateway_revoke_enrollment(conn, {"token_id": enrollment["token_id"]})
        if status == 200:
            revoked.append({
                "token_id": enrollment["token_id"],
                "agent_id": enrollment.get("agent_id"),
                "sessions_revoked": payload.get("sessions_revoked", 0),
            })
        else:
            errors.append({"kind": "enrollment_revoke", "token_id": enrollment.get("token_id"), "status": status, "error": payload})

    applied = {
        **plan,
        "status": "completed" if not errors else "attention",
        "applied": True,
        "released_tasks": released,
        "revoked_enrollments": revoked,
        "errors": errors,
    }
    applied["summary"] = {
        **plan["summary"],
        "released_tasks": len(released),
        "revoked_enrollments": len(revoked),
        "errors": len(errors),
    }
    applied["safety"] = {**plan["safety"], "read_only": False}
    runtime_event(conn, "rtc_agent_gateway_local", "worker.fleet_hygiene", applied["status"], output_summary=f"Fleet hygiene released {len(released)} task(s) and revoked {len(revoked)} enrollment(s).")
    audit(conn, "user", "usr_founder", "worker.fleet_hygiene", "workers", "fleet", None, {"summary": applied["summary"]}, {"token_omitted": True, "live_execution_performed": False})
    return applied, 200 if not errors else 207


def worker_fleet_health(payload: dict) -> dict:
    remote = payload.get("remote_worker_health") or {}
    daemons = payload.get("daemons") or []
    active_daemons = [daemon for daemon in daemons if daemon.get("running")]
    running_workers = int(payload.get("running_workers") or 0)
    pending_tasks = int(payload.get("pending_worker_tasks") or 0)
    stuck_tasks = int(payload.get("stuck_worker_tasks") or 0)
    workflow_stuck_jobs = int(payload.get("stuck_workflow_jobs") or 0)
    active_remote = int(payload.get("active_remote_enrollments") or 0)
    fresh_remote = int(payload.get("fresh_remote_enrollments") or 0)
    stale_remote = int(payload.get("stale_remote_enrollments") or 0)
    never_seen_remote = int(payload.get("never_seen_remote_enrollments") or 0)
    active_sessions = int(payload.get("active_remote_sessions") or 0)

    gates = []

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
            "agentops worker stuck && agentops worker release --task-id <task_id>",
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


def worker_adapter_readiness(conn, refresh: bool = True) -> dict:
    if refresh:
        refresh_runtime_connectors(conn)
    hermes = hermes_status()
    openclaw = openclaw_status()

    def trust_for(adapter: str) -> dict:
        connector_id = runtime_connector_for_adapter(adapter)
        trust = runtime_connector_trust(conn, connector_id, refresh=refresh) if connector_id else None
        return {
            "connector_id": connector_id,
            "trust_status": (trust or {}).get("trust_status") or "trusted",
            "trust_note": redact_text((trust or {}).get("trust_note"), 160) if (trust or {}).get("trust_note") else None,
            "require_confirm_run": bool((trust or {}).get("require_confirm_run", 1)),
        }

    def readiness_from_checks(available: bool, trust: dict) -> tuple[str, bool]:
        if trust.get("trust_status") == "blocked":
            return "blocked", False
        if not available:
            return "unavailable", False
        if trust.get("trust_status") == "review_required":
            return "review_required", True
        return "ready", True

    adapters = {}

    mock_trust = trust_for("mock")
    mock_readiness, mock_ok = readiness_from_checks(True, mock_trust)
    adapters["mock"] = {
        "adapter": "mock",
        "ok": mock_ok,
        "readiness": mock_readiness,
        "connector_id": mock_trust.get("connector_id"),
        "trust_status": mock_trust.get("trust_status"),
        "requires_confirm_run": False,
        "target_resource": "local://agentops/mock-worker",
        "checks": {"available": True, "live_execution_performed": False},
        "recommended_action": "agentops workflow run-task --adapter mock",
        "token_omitted": True,
    }

    hermes_trust = trust_for("hermes")
    hermes_available = bool(hermes.get("api_listening"))
    hermes_readiness, hermes_ok = readiness_from_checks(hermes_available, hermes_trust)
    adapters["hermes"] = {
        "adapter": "hermes",
        "ok": hermes_ok,
        "readiness": hermes_readiness,
        "connector_id": hermes_trust.get("connector_id"),
        "trust_status": hermes_trust.get("trust_status"),
        "requires_confirm_run": True,
        "target_resource": hermes.get("gateway_url"),
        "checks": {
            "api_listening": hermes_available,
            "api_port": hermes.get("api_port"),
            "config_exists": bool(hermes.get("config_exists")),
            "auth_exists": bool(hermes.get("auth_exists")),
            "live_execution_performed": False,
        },
        "recommended_action": "agentops worker preflight --adapter hermes" if not hermes_available else "agentops workflow run-task --adapter hermes --confirm-run",
        "last_error": None if hermes_available else "Hermes API gateway is not listening.",
        "token_omitted": True,
    }

    openclaw_trust = trust_for("openclaw")
    openclaw_available = bool(openclaw.get("cli_exists")) and os.access(OPENCLAW_BIN, os.X_OK)
    openclaw_readiness, openclaw_ok = readiness_from_checks(openclaw_available, openclaw_trust)
    adapters["openclaw"] = {
        "adapter": "openclaw",
        "ok": openclaw_ok,
        "readiness": openclaw_readiness,
        "connector_id": openclaw_trust.get("connector_id"),
        "trust_status": openclaw_trust.get("trust_status"),
        "requires_confirm_run": True,
        "target_resource": str(OPENCLAW_BIN),
        "checks": {
            "binary_exists": bool(openclaw.get("cli_exists")),
            "binary_executable": os.access(OPENCLAW_BIN, os.X_OK) if OPENCLAW_BIN.exists() else False,
            "config_exists": bool(openclaw.get("config_exists")),
            "agents_count": int(openclaw.get("agents_count") or 0),
            "cron_jobs_count": int(openclaw.get("cron_jobs_count") or 0),
            "live_execution_performed": False,
        },
        "recommended_action": "agentops worker preflight --adapter openclaw" if not openclaw_available else "agentops workflow run-task --adapter openclaw --confirm-run",
        "last_error": None if openclaw_available else f"OpenClaw binary unavailable at {OPENCLAW_BIN}.",
        "token_omitted": True,
    }

    ready = [name for name, item in adapters.items() if item.get("readiness") == "ready"]
    review_required = [name for name, item in adapters.items() if item.get("readiness") == "review_required"]
    blocked = [name for name, item in adapters.items() if item.get("readiness") == "blocked"]
    unavailable = [name for name, item in adapters.items() if item.get("readiness") == "unavailable"]
    live_ready = [name for name in ready if name != "mock"]
    recommended_adapter = "openclaw" if "openclaw" in ready else "hermes" if "hermes" in ready else "mock"
    summary_status = "ready" if live_ready else "degraded" if ready else "blocked"
    return {
        "provider": "agentops-worker",
        "status": summary_status,
        "summary": {
            "ready_adapters": ready,
            "live_ready_adapters": live_ready,
            "review_required_adapters": review_required,
            "blocked_adapters": blocked,
            "unavailable_adapters": unavailable,
            "recommended_adapter": recommended_adapter,
        },
        "adapters": adapters,
        "contract": "read-only adapter readiness; use Agent Gateway CLI/API for execution and confirm live Hermes/OpenClaw runs explicitly",
        "live_execution_performed": False,
        "token_omitted": True,
    }


def worker_status(conn) -> dict:
    worker_agents = rows_to_dicts(conn.execute(
        """SELECT * FROM agents
        WHERE agent_id LIKE 'agt_worker_%' OR allowed_tools LIKE '%agent_worker%'
        ORDER BY updated_at DESC LIMIT 25"""
    ).fetchall())
    worker_runs = rows_to_dicts(conn.execute(
        """SELECT * FROM runs
        WHERE agent_id LIKE 'agt_worker_%' OR delegation_id LIKE 'worker:%'
        ORDER BY created_at DESC LIMIT 25"""
    ).fetchall())
    worker_tasks = rows_to_dicts(conn.execute(
        """SELECT * FROM tasks
        WHERE owner_agent_id LIKE 'agt_worker_%'
        ORDER BY created_at DESC LIMIT 25"""
    ).fetchall())
    worker_events = rows_to_dicts(conn.execute(
        """SELECT * FROM runtime_events
        WHERE agent_id LIKE 'agt_worker_%' OR event_type IN ('task.pull','task.claim','run.start','run.heartbeat','tool_call.record','evaluation.submit','audit.emit')
        ORDER BY created_at DESC LIMIT 40"""
    ).fetchall())
    for event in worker_events:
        for key in ("input_summary", "output_summary", "error_message", "metadata_json"):
            if event.get(key):
                event[key] = redact_full_text(event[key])
    daemons = worker_daemon_status(include_log=False)
    active_daemons = [daemon for daemon in daemons if daemon["running"]]
    stuck_tasks = worker_stuck_tasks(conn)
    remote_fleet = worker_remote_fleet_summary(conn)
    stuck_workflow_jobs = workflow_stuck_jobs(conn, threshold_sec=900, limit=5)
    adapter_readiness = worker_adapter_readiness(conn)
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


def worker_fleet_view(conn) -> dict:
    daemons = worker_daemon_status(include_log=False)
    remote_fleet = worker_remote_fleet_summary(conn)
    adapter_readiness = worker_adapter_readiness(conn, refresh=False).get("summary") or {}
    stuck_tasks = worker_stuck_tasks(conn)
    stuck_workflow_jobs = workflow_stuck_jobs(conn, threshold_sec=900, limit=5)
    worker_agents = rows_to_dicts(conn.execute(
        """SELECT agent_id,name,role,runtime_type,status,updated_at
        FROM agents
        WHERE agent_id LIKE 'agt_worker_%' OR allowed_tools LIKE '%agent_worker%'
        ORDER BY updated_at DESC LIMIT 50"""
    ).fetchall())
    lanes: list[dict] = []
    seen_agents: set[str] = set()

    def add_lane(lane: dict) -> None:
        lane["token_omitted"] = True
        lane["session_id_omitted"] = True
        lanes.append(lane)
        if lane.get("agent_id"):
            seen_agents.add(lane["agent_id"])

    for daemon in daemons:
        running = bool(daemon.get("running"))
        status = daemon.get("worker_status") or daemon.get("status") or "unknown"
        health = "pass" if running else "info"
        if running and int(daemon.get("consecutive_errors") or 0) > 0:
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
                "processed": int(daemon.get("processed") or 0),
                "iterations": int(daemon.get("iterations") or 0),
                "consecutive_errors": int(daemon.get("consecutive_errors") or 0),
                "total_errors": int(daemon.get("total_errors") or 0),
            },
            "next_action": "agentops worker logs --adapter " + str(daemon.get("adapter") or "mock") if running else "agentops worker start --adapter " + str(daemon.get("adapter") or "mock"),
            "safe_ref": stable_id("fleet_lane", "local_daemon", daemon.get("adapter") or "mock")[-12:],
        })

    for worker in (remote_fleet.get("remote_workers") or []):
        token_status = worker.get("token_status") or "unknown"
        heartbeat_state = worker.get("heartbeat_state") or "unknown"
        active_sessions = int(worker.get("active_session_count") or 0)
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
            "scope_count": int(worker.get("scope_count") or 0),
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


def demo_readiness(conn: sqlite3.Connection, headers) -> dict:
    local = local_readiness(conn, headers)
    conn.rollback()
    security = security_production_readiness(conn, headers)
    conn.rollback()
    fleet = worker_fleet_view(conn)
    conn.rollback()
    inbox = commander_integration_inbox(conn, headers, {"bucket": ["ready_for_review"], "limit": ["5"]})
    conn.rollback()
    board = commander_project_board(conn, headers)
    conn.rollback()
    evidence = local.get("evidence") or {}
    inbox_summary = inbox.get("summary") or {}
    fleet_summary = fleet.get("summary") or {}

    shots = [
        {
            "id": "local_readiness",
            "label": "Local readiness",
            "route": "/workspace/agents",
            "command": "agentops local readiness",
            "status": local.get("status"),
            "ok": local.get("status") in {"ready", "attention"},
            "detail": f"{evidence.get('closed_loop_runs', 0)} closed-loop run(s); token omitted={local.get('token_omitted') is True}",
            "next_action": "Open /workspace/agents and show Local Readiness.",
        },
        {
            "id": "security_boundary",
            "label": "Security boundary",
            "route": "/workspace/agents",
            "command": "agentops security production-readiness",
            "status": security.get("status"),
            "ok": security.get("status") in {"ready", "attention"},
            "detail": f"auth_mode={security.get('auth_mode')}; production_ready={security.get('production_ready')}",
            "next_action": "Explain local demo mode versus production/shared deployment.",
        },
        {
            "id": "worker_fleet",
            "label": "Worker fleet lanes",
            "route": "/workspace/agents",
            "command": "agentops worker fleet",
            "status": fleet.get("status"),
            "ok": fleet.get("status") in {"ready", "attention"},
            "detail": f"{fleet_summary.get('lane_count', 0)} lane(s); {fleet_summary.get('running_local_daemons', 0)} local daemon(s) running",
            "next_action": "Show normalized local/remote worker lanes and next actions.",
        },
        {
            "id": "commander_inbox",
            "label": "Async integration inbox",
            "route": "/workspace/agents",
            "command": "agentops commander inbox --bucket ready_for_review --limit 5",
            "status": inbox.get("status"),
            "ok": isinstance(inbox.get("inbox_items"), list),
            "detail": f"{inbox_summary.get('items_returned', 0)} ready item(s) returned; total={inbox_summary.get('total', 0)}",
            "next_action": "Show ready/blocked/stale/memory queue filtering.",
        },
        {
            "id": "customer_task_loop",
            "label": "Customer worker loop",
            "route": "/workspace/agents",
            "command": "agentops workflow customer-worker-task --adapter mock --title ... --description ...",
            "status": "ready" if int(evidence.get("customer_worker_artifacts") or 0) > 0 else "attention",
            "ok": int(evidence.get("customer_worker_artifacts") or 0) > 0 and int(evidence.get("closed_loop_runs") or 0) > 0,
            "detail": f"{evidence.get('customer_worker_artifacts', 0)} customer worker artifact(s)",
            "next_action": "Run mock for safe recording, then explain confirmed Hermes/OpenClaw mode.",
        },
        {
            "id": "run_ledger_evidence",
            "label": "Run ledger evidence",
            "route": "/admin/runs",
            "command": "agentops run list --limit 5",
            "status": "ready" if int(evidence.get("closed_loop_runs") or 0) > 0 else "attention",
            "ok": int(evidence.get("closed_loop_runs") or 0) > 0,
            "detail": f"{evidence.get('runs', 0)} run(s), {evidence.get('tool_calls', 0)} tool call(s), {evidence.get('evaluations', 0)} eval(s), {evidence.get('audit_logs', 0)} audit log(s)",
            "next_action": "Open a recent worker run and show task/tool/eval/audit/artifact chain.",
        },
    ]
    demo_ready = all(shot["ok"] for shot in shots)
    blockers = [shot for shot in shots if not shot["ok"]]
    warning_count = len([shot for shot in shots if shot.get("status") == "attention"])
    return {
        "provider": "agentops-demo",
        "operation": "v1_5_demo_readiness",
        "status": "ready" if demo_ready else "attention",
        "demo_ready": demo_ready,
        "production_ready": bool(security.get("production_ready")),
        "summary": {
            "shot_count": len(shots),
            "ready_shots": len([shot for shot in shots if shot["ok"]]),
            "blocker_count": len(blockers),
            "warning_count": warning_count,
            "closed_loop_runs": evidence.get("closed_loop_runs", 0),
            "customer_worker_artifacts": evidence.get("customer_worker_artifacts", 0),
            "fleet_lanes": fleet_summary.get("lane_count", 0),
            "ready_inbox_items": inbox_summary.get("items_returned", 0),
        },
        "shots": shots,
        "next_actions": [shot["next_action"] for shot in blockers] or [
            "Open /workspace/agents and record local readiness, security boundary, fleet lanes, async inbox, and customer worker dispatch.",
            "Keep Hermes/OpenClaw live execution behind explicit confirm_run.",
        ],
        "references": {
            "video_script": "docs/DEMO_VIDEO_SCRIPT.md",
            "runbook": "docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md",
            "acceptance": "python3 scripts/v1_5_local_product_acceptance.py --base-url http://127.0.0.1:8787",
        },
        "contract": "read-only canonical v1.5 demo readiness; does not start workers, call live runtimes, create tasks, or store prompts/tokens",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }


def scalar_count(conn: sqlite3.Connection, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int((row[0] if row else 0) or 0)


def status_counts(conn: sqlite3.Connection, table: str, valid_statuses: set[str] | None = None) -> dict:
    if table not in {"tasks", "runs", "workflow_jobs"}:
        return {}
    rows = rows_to_dicts(conn.execute(f"SELECT status, COUNT(*) AS count FROM {table} GROUP BY status").fetchall())
    counts = {str(row.get("status") or "unknown"): int(row.get("count") or 0) for row in rows}
    if valid_statuses:
        for status in valid_statuses:
            counts.setdefault(status, 0)
    return dict(sorted(counts.items()))


def safe_commander_readiness_snapshot(conn: sqlite3.Connection, headers) -> tuple[dict, dict]:
    readiness: dict = {}
    worker: dict = {}
    try:
        readiness = local_readiness(conn, headers)
    except Exception as exc:
        readiness = {"status": "unknown", "error": redact_text(str(exc), 160)}
    finally:
        conn.rollback()
    try:
        worker = worker_status(conn)
    except Exception as exc:
        worker = {"status": "unknown", "error": redact_text(str(exc), 160)}
    finally:
        conn.rollback()
    return readiness, worker


def commander_safe_text(value, limit=180) -> str:
    redacted = redact_text(value, limit)
    redacted = re.sub(r"(?i)bearer\s+\[REDACTED\]", "[SECRET_REDACTED]", redacted)
    redacted = re.sub(r"(?i)\b(?:agtok|agtsess)_[a-z0-9._\-]+\b", "[SECRET_REDACTED]", redacted)
    return redacted[:limit]


def commander_project_board(conn: sqlite3.Connection, headers) -> dict:
    readiness, worker = safe_commander_readiness_snapshot(conn, headers)
    adapter_payload = worker_adapter_readiness(conn, refresh=False)
    conn.rollback()

    task_counts = status_counts(conn, "tasks", VALID_TASK_STATUSES)
    run_counts = status_counts(conn, "runs")
    workflow_counts = status_counts(conn, "workflow_jobs", {"queued", "running", "completed", "failed"})
    active_workflow_jobs = scalar_count(conn, "SELECT COUNT(*) FROM workflow_jobs WHERE status IN ('queued','running')")
    stuck_jobs = workflow_stuck_jobs(conn, threshold_sec=900, limit=10)
    recent_artifact_rows = rows_to_dicts(conn.execute(
        """SELECT artifact_id, task_id, run_id, artifact_type, title, created_at
        FROM artifacts
        ORDER BY created_at DESC
        LIMIT 8"""
    ).fetchall())
    for artifact in recent_artifact_rows:
        artifact["title"] = commander_safe_text(artifact.get("title"), 160)
    memory_candidate_count = scalar_count(conn, "SELECT COUNT(*) FROM memories WHERE review_status='candidate'")
    memory_review_counts = {
        str(row["review_status"]): int(row["count"] or 0)
        for row in conn.execute("SELECT review_status, COUNT(*) AS count FROM memories GROUP BY review_status").fetchall()
    }
    pending_approval_count = scalar_count(conn, "SELECT COUNT(*) FROM approvals WHERE decision='pending'")

    recent_tasks = rows_to_dicts(conn.execute(
        """SELECT task_id, title, status, owner_agent_id, priority, risk_level, created_at
        FROM tasks
        ORDER BY created_at DESC
        LIMIT 12"""
    ).fetchall())
    recent_work_packages = []
    for task in recent_tasks:
        latest_run = conn.execute(
            """SELECT run_id, status, created_at
            FROM runs
            WHERE task_id=?
            ORDER BY created_at DESC
            LIMIT 1""",
            (task["task_id"],),
        ).fetchone()
        recent_work_packages.append({
            "task_id": task.get("task_id"),
            "title": commander_safe_text(task.get("title"), 180),
            "status": task.get("status"),
            "owner_agent_id": task.get("owner_agent_id"),
            "priority": task.get("priority"),
            "risk": task.get("risk_level"),
            "created_at": task.get("created_at"),
            "latest_run": {
                "run_id": latest_run["run_id"],
                "status": latest_run["status"],
                "created_at": latest_run["created_at"],
            } if latest_run else None,
        })

    readiness_gates = {gate.get("id"): gate for gate in (readiness.get("gates") or []) if isinstance(gate, dict)}
    worker_fleet = worker.get("fleet_health") or readiness.get("worker_fleet_health") or {}
    adapter_summary = adapter_payload.get("summary") or readiness.get("adapter_readiness") or {}
    closed_loop_runs = int(((readiness.get("evidence") or {}).get("closed_loop_runs") or 0))
    approved_memory = int(memory_review_counts.get("approved") or 0)

    integration_gates = [
        {
            "id": "evidence_chain",
            "status": "pass" if closed_loop_runs else "warn",
            "summary": f"{closed_loop_runs} closed-loop run(s) with task/run/tool/eval/audit/artifact evidence",
            "next_action": "Run a mock customer-worker task to create fresh evidence." if not closed_loop_runs else "Review recent run graph before delivery.",
        },
        {
            "id": "worker_fleet_health",
            "status": "pass" if worker_fleet.get("overall") == "ready" else "fail" if worker_fleet.get("overall") == "blocked" else "warn",
            "summary": f"fleet={worker_fleet.get('overall') or worker.get('status') or 'unknown'}; running_workers={worker.get('running_workers', 0)}; stuck_tasks={worker.get('stuck_worker_tasks', 0)}",
            "next_action": (worker_fleet.get("recommended_actions") or ["agentops worker status"])[0],
        },
        {
            "id": "approvals_pending",
            "status": "warn" if pending_approval_count else "pass",
            "summary": f"{pending_approval_count} pending approval(s)",
            "next_action": "Open /workspace/approvals and approve or reject pending gates." if pending_approval_count else "No approval action needed.",
        },
        {
            "id": "memory_review",
            "status": "warn" if memory_candidate_count else "pass" if approved_memory else "warn",
            "summary": f"{memory_candidate_count} candidate memory item(s), {approved_memory} approved",
            "next_action": "Review candidate memories before using them as project context." if memory_candidate_count else "Capture durable project lessons after the next delivery.",
        },
        {
            "id": "adapter_readiness",
            "status": "pass" if adapter_payload.get("status") == "ready" else "warn" if adapter_payload.get("status") == "degraded" else "fail",
            "summary": f"recommended_adapter={adapter_summary.get('recommended_adapter') or 'unknown'}; ready={','.join(adapter_summary.get('ready_adapters') or []) or 'none'}",
            "next_action": "agentops worker readiness",
        },
    ]

    recommended_next_actions = []
    for gate in integration_gates:
        if gate["status"] in {"fail", "warn"} and gate.get("next_action") not in recommended_next_actions:
            recommended_next_actions.append(gate["next_action"])
    for action in readiness.get("next_actions") or []:
        if action not in recommended_next_actions:
            recommended_next_actions.append(action)
    if not recommended_next_actions:
        recommended_next_actions = [
            "Select the highest-priority planned task and dispatch a mock worker.",
            "Review recent artifacts and approve customer-facing delivery evidence.",
            "Run agentops worker readiness before using live Hermes/OpenClaw adapters.",
        ]

    board_status = "blocked" if any(gate["status"] == "fail" for gate in integration_gates) else "attention" if any(gate["status"] == "warn" for gate in integration_gates) else "ready"
    return {
        "provider": "agentops-commander",
        "operation": "project_board",
        "status": board_status,
        "token_omitted": True,
        "live_execution_performed": False,
        "workspace_id": normalize_workspace_id(headers.get("X-AgentOps-Workspace-Id") or "local-demo"),
        "local_readiness": {
            "status": readiness.get("status") or "unknown",
            "ok": bool(readiness.get("ok")) if "ok" in readiness else None,
            "gate_count": len(readiness.get("gates") or []),
            "blocked_gates": [gate_id for gate_id, gate in readiness_gates.items() if not gate.get("ok")][:8],
        },
        "worker_status": {
            "status": worker.get("status") or "unknown",
            "running_workers": int(worker.get("running_workers") or 0),
            "pending_worker_tasks": int(worker.get("pending_worker_tasks") or 0),
            "stuck_worker_tasks": int(worker.get("stuck_worker_tasks") or 0),
            "remote_worker_count": int(worker.get("remote_worker_count") or 0),
            "fleet_overall": worker_fleet.get("overall"),
        },
        "counts": {
            "tasks_by_status": task_counts,
            "runs_by_status": run_counts,
            "workflow_jobs_by_status": workflow_counts,
            "pending_approvals": pending_approval_count,
            "active_workflow_jobs": active_workflow_jobs,
            "stuck_workflow_jobs": len(stuck_jobs),
            "recent_artifacts": len(recent_artifact_rows),
            "memory_candidates": memory_candidate_count,
        },
        "recent_artifacts": recent_artifact_rows,
        "stuck_workflow_jobs": [{
            "job_id": job.get("job_id"),
            "workflow_type": job.get("workflow_type"),
            "status": job.get("status"),
            "age_sec": job.get("age_sec"),
            "result_task_id": job.get("result_task_id"),
            "result_run_id": job.get("result_run_id"),
        } for job in stuck_jobs],
        "recent_work_packages": recent_work_packages,
        "integration_gates": integration_gates,
        "recommended_next_actions": recommended_next_actions[:8],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "task_created": False,
            "run_created": False,
            "job_created": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
        },
    }


COMMANDER_DEFAULT_WORK_PACKAGE_LANES = [
    {
        "lane_id": "strategy",
        "title": "Clarify product goal and acceptance gates",
        "owner_agent_id": "agt_cos",
        "priority": "high",
        "risk_level": "medium",
        "scope": "problem framing, success criteria, owner decisions, approval checkpoints",
        "avoid_scope": "do not execute live adapters or rewrite implementation details",
        "verification": ["agentops commander board", "agentops commander inbox --bucket ready_for_review --limit 5"],
    },
    {
        "lane_id": "research",
        "title": "Gather grounded product and implementation evidence",
        "owner_agent_id": "agt_research",
        "priority": "high",
        "risk_level": "low",
        "scope": "current repo evidence, relevant docs, comparable product patterns, source-backed gaps",
        "avoid_scope": "do not ingest private transcripts, credentials, or unsupported external claims",
        "verification": ["agentops local readiness", "agentops review queue --limit 5"],
    },
    {
        "lane_id": "implementation",
        "title": "Implement the smallest useful product increment",
        "owner_agent_id": "agt_builder",
        "priority": "high",
        "risk_level": "medium",
        "scope": "bounded code/docs changes required by the accepted work package",
        "avoid_scope": "do not touch unrelated UI/backend surfaces or local databases",
        "verification": ["python3 -m py_compile server.py scripts/*.py agentops_mis_cli/*.py", "git diff --check"],
    },
    {
        "lane_id": "qa",
        "title": "Verify ledger evidence and regression gates",
        "owner_agent_id": "agt_qa",
        "priority": "medium",
        "risk_level": "medium",
        "scope": "smoke tests, build checks, evidence counts, safety/readiness gates",
        "avoid_scope": "do not approve customer delivery without verified evidence",
        "verification": ["python3 scripts/v1_5_demo_readiness_smoke.py --base-url http://127.0.0.1:8787", "cd ui/start-building-app && npm run build"],
    },
    {
        "lane_id": "ops",
        "title": "Prepare customer-facing handoff and operations notes",
        "owner_agent_id": "agt_ops",
        "priority": "medium",
        "risk_level": "low",
        "scope": "runbook updates, delivery report outline, next actions, backup/restore notes",
        "avoid_scope": "do not export to external systems or include raw prompts/responses",
        "verification": ["agentops workflow delivery-board", "agentops worker status"],
    },
]


def commander_normalize_lane(raw_lane: dict, index: int) -> dict:
    lane = raw_lane if isinstance(raw_lane, dict) else {}
    default = COMMANDER_DEFAULT_WORK_PACKAGE_LANES[index % len(COMMANDER_DEFAULT_WORK_PACKAGE_LANES)]
    lane_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(lane.get("lane_id") or lane.get("id") or default["lane_id"]).strip()).strip("-").lower()
    if not lane_id:
        lane_id = f"lane-{index + 1}"
    verification = lane.get("verification") or lane.get("verification_commands") or default.get("verification") or []
    if isinstance(verification, str):
        verification = [item.strip() for item in verification.splitlines() if item.strip()]
    if not isinstance(verification, list):
        verification = []
    return {
        "lane_id": commander_safe_text(lane_id, 80),
        "title": commander_safe_text(lane.get("title") or default["title"], 160),
        "owner_agent_id": commander_safe_text(lane.get("owner_agent_id") or lane.get("agent_id") or default["owner_agent_id"], 120),
        "priority": coerce_choice(lane.get("priority"), VALID_PRIORITIES, default["priority"]),
        "risk_level": coerce_choice(lane.get("risk_level") or lane.get("risk"), VALID_RISK_LEVELS, default["risk_level"]),
        "scope": commander_safe_text(lane.get("scope") or default["scope"], 360),
        "avoid_scope": commander_safe_text(lane.get("avoid_scope") or lane.get("avoid") or default["avoid_scope"], 360),
        "verification": [commander_safe_text(item, 180) for item in verification[:8]],
    }


def commander_work_package_description(goal: str, lane: dict, dependencies: list[str], project_id: str, plan_id: str) -> str:
    verification = "\n".join(f"- {item}" for item in lane.get("verification") or [])
    deps = ", ".join(dependencies) if dependencies else "none"
    return redact_text(
        "\n".join([
            f"Commander project: {project_id}",
            f"Plan: {plan_id}",
            f"Goal: {goal}",
            f"Lane: {lane['lane_id']}",
            f"Scope: {lane['scope']}",
            f"Avoid scope: {lane['avoid_scope']}",
            f"Dependencies: {deps}",
            "Return checklist: changed files or artifacts, evidence ids, verification result, known limits, next action.",
            "Verification commands:",
            verification or "- agentops commander board",
        ]),
        1200,
    )


def commander_plan_work_packages(conn: sqlite3.Connection, body: dict, headers) -> tuple[dict, int]:
    goal = commander_safe_text(body.get("goal") or body.get("objective") or "Plan the next AgentOps MIS product increment.", 500)
    if len(goal.strip()) < 8:
        return {"error": "goal_required", "message": "A concrete goal/objective of at least 8 characters is required."}, 400
    workspace_id = normalize_workspace_id(body.get("workspace_id") or headers.get("X-AgentOps-Workspace-Id") or "local-demo")
    project_id = commander_safe_text(body.get("project_id") or stable_id("proj_cmd", workspace_id, goal)[:32], 80)
    plan_id = commander_safe_text(body.get("plan_id") or stable_id("cmdplan", workspace_id, project_id, goal)[:40], 80)
    max_packages = min(max(int(body.get("max_packages") or 5), 1), 8)
    confirm_create = bool(body.get("confirm_create"))
    raw_lanes = body.get("lanes")
    if not isinstance(raw_lanes, list) or not raw_lanes:
        raw_lanes = COMMANDER_DEFAULT_WORK_PACKAGE_LANES
    lanes = [commander_normalize_lane(item, idx) for idx, item in enumerate(raw_lanes[:max_packages])]

    planned_packages = []
    created_packages = []
    errors = []
    for idx, lane in enumerate(lanes):
        owner_exists = conn.execute("SELECT 1 FROM agents WHERE agent_id=?", (lane["owner_agent_id"],)).fetchone()
        if not owner_exists:
            errors.append({"lane_id": lane["lane_id"], "error": "owner_agent_not_found", "owner_agent_id": lane["owner_agent_id"]})
            lane["owner_agent_id"] = "agt_cos"
        dependencies = [pkg["task_id"] for pkg in planned_packages[:1]] if idx > 0 else []
        task_id = commander_safe_text(body.get("task_id_prefix") or stable_id("tsk_cmd", plan_id, lane["lane_id"]), 80)
        if body.get("task_id_prefix"):
            task_id = f"{task_id}_{idx + 1:02d}_{lane['lane_id']}"[:80]
        title = commander_safe_text(f"{lane['title']}: {goal}", 180)
        acceptance = redact_text(
            "Work package is ready for commander review when it returns evidence ids, verification output, scope deviations, and a recommended next action.",
            600,
        )
        package = {
            "plan_id": plan_id,
            "project_id": project_id,
            "lane_id": lane["lane_id"],
            "task_id": task_id,
            "title": title,
            "description": commander_work_package_description(goal, lane, dependencies, project_id, plan_id),
            "owner_agent_id": lane["owner_agent_id"],
            "collaborator_agent_ids": ["agt_qa"] if lane["owner_agent_id"] != "agt_qa" else ["agt_cos"],
            "status": "planned",
            "priority": lane["priority"],
            "risk_level": lane["risk_level"],
            "acceptance_criteria": acceptance,
            "dependencies": dependencies,
            "verification_commands": lane.get("verification") or [],
            "scope": lane["scope"],
            "avoid_scope": lane["avoid_scope"],
        }
        planned_packages.append(package)
        if confirm_create:
            payload, status = create_task_api(conn, {
                "task_id": task_id,
                "workspace_id": workspace_id,
                "title": title,
                "description": package["description"],
                "owner_agent_id": package["owner_agent_id"],
                "collaborator_agent_ids": package["collaborator_agent_ids"],
                "status": "planned",
                "priority": package["priority"],
                "risk_level": package["risk_level"],
                "acceptance_criteria": acceptance,
                "budget_limit_usd": float(body.get("budget_limit_usd") or 3.0),
                "requester_id": "usr_founder",
                "source": "commander-work-package-plan",
            })
            if status >= 400:
                errors.append({"lane_id": lane["lane_id"], "task_id": task_id, "error": payload.get("error"), "message": payload.get("message")})
            else:
                created_packages.append(payload.get("task") or package)

    if confirm_create and created_packages:
        runtime_event(
            conn,
            "rtc_agent_gateway_local",
            "commander.work_package_plan",
            "completed",
            input_summary=f"Commander planned {len(created_packages)} work package(s) for {project_id}.",
            output_summary=f"Created work packages for: {goal}",
            raw_payload_hash=stable_hash({"goal": goal, "project_id": project_id, "plan_id": plan_id, "count": len(created_packages)}),
        )
        audit(
            conn,
            "user",
            "usr_founder",
            "commander.work_package_plan_create",
            "tasks",
            plan_id,
            None,
            {"created_task_ids": [item.get("task_id") for item in created_packages], "workspace_id": workspace_id},
            {"project_id": project_id, "raw_goal_hash": stable_hash(goal), "raw_prompt_omitted": True},
        )
    status_code = 201 if confirm_create and created_packages else 200
    return {
        "provider": "agentops-commander",
        "operation": "work_package_plan",
        "status": "created" if confirm_create and created_packages else "preview",
        "ok": not errors or bool(created_packages),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "plan_id": plan_id,
        "goal_summary": goal,
        "confirm_create": confirm_create,
        "created": bool(confirm_create and created_packages),
        "created_count": len(created_packages),
        "planned_count": len(planned_packages),
        "work_packages": planned_packages,
        "created_task_ids": [item.get("task_id") for item in created_packages],
        "errors": errors,
        "recommended_next_actions": [
            "agentops commander board",
            "agentops task pull --agent-id agt_builder --status planned --limit 3",
            "agentops worker start --adapter mock",
            "agentops commander inbox --bucket ready_for_review --limit 5",
        ],
        "safety": {
            "live_execution_performed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
            "dry_run": not confirm_create,
            "ledger_mutated": bool(confirm_create and created_packages),
            "task_created": bool(confirm_create and created_packages),
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }, status_code


def commander_extract_line(description: str, label: str) -> str:
    labels = ["Commander project", "Plan", "Goal", "Lane", "Scope", "Avoid scope", "Dependencies", "Return checklist", "Verification commands"]
    next_labels = "|".join(re.escape(item) for item in labels if item != label)
    pattern = rf"(?:^|\s){re.escape(label)}:\s*(.*?)(?=\s(?:{next_labels}):|$)"
    match = re.search(pattern, description or "", flags=re.DOTALL)
    return commander_safe_text(match.group(1).strip(), 360) if match else ""


def commander_extract_verification(description: str) -> list[str]:
    if "Verification commands:" not in (description or ""):
        return []
    tail = description.split("Verification commands:", 1)[1]
    commands = []
    for line in tail.splitlines():
        line = line.strip()
        if line.startswith("- "):
            commands.append(commander_safe_text(line[2:].strip(), 180))
    if len(commands) <= 1 and " - " in tail:
        commands = [commander_safe_text(item.strip(), 180) for item in tail.split(" - ") if item.strip()]
    return commands[:8]


def commander_extract_dependencies(description: str) -> list[str]:
    raw = commander_extract_line(description, "Dependencies")
    if not raw or raw.lower() == "none":
        return []
    return [commander_safe_text(item.strip(), 100) for item in raw.split(",") if item.strip()][:12]


def commander_plan_id_from_task(task_id: str, description: str) -> str:
    explicit = commander_extract_line(description, "Plan")
    if explicit:
        return explicit
    match = re.match(r"tsk_cmd_(.+)_(strategy|research|implementation|qa|ops|lane-[0-9]+)$", task_id or "")
    return commander_safe_text(match.group(1), 120) if match else ""


def commander_work_package_status(task: dict, latest_run: dict | None, evidence: dict) -> str:
    if task.get("status") in {"failed", "blocked", "canceled"}:
        return "blocked"
    if task.get("status") in {"running", "waiting_approval"}:
        return "still_running"
    if task.get("status") == "completed":
        return "ready_for_review" if (evidence.get("evaluations") or evidence.get("artifacts") or evidence.get("tool_calls")) else "needs_evidence"
    if latest_run and latest_run.get("status") in {"failed", "blocked"}:
        return "blocked"
    return "planned"


def commander_work_package_next_action(item: dict) -> str:
    owner = item.get("owner_agent_id") or "agt_worker_local"
    status = item.get("package_status")
    if status == "planned":
        return f"agentops-worker --once --adapter mock --agent-id {owner}"
    if status == "still_running":
        run_id = item.get("latest_run", {}).get("run_id") if item.get("latest_run") else ""
        return f"agentops run get --run-id {run_id}" if run_id else "agentops commander inbox --bucket still_running"
    if status == "ready_for_review":
        return f"agentops task get --task-id {item.get('task_id')}"
    if status == "blocked":
        return "agentops commander inbox --bucket blocked --limit 5"
    return "agentops commander board"


def commander_work_package_from_task(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    task = dict(row)
    description = task.get("description") or ""
    latest_run_row = conn.execute(
        """SELECT run_id,status,agent_id,runtime_type,created_at,ended_at,error_type,error_message
        FROM runs WHERE task_id=? ORDER BY created_at DESC LIMIT 1""",
        (task["task_id"],),
    ).fetchone()
    latest_run = dict(latest_run_row) if latest_run_row else None
    evidence = commander_evidence_counts(conn, task_id=task["task_id"], run_id=(latest_run or {}).get("run_id"))
    item = {
        "work_package_id": task["task_id"],
        "task_id": task["task_id"],
        "workspace_id": row_workspace(task),
        "project_id": commander_extract_line(description, "Commander project"),
        "plan_id": commander_plan_id_from_task(task["task_id"], description),
        "goal": commander_extract_line(description, "Goal"),
        "lane_id": commander_extract_line(description, "Lane") or "unknown",
        "title": commander_safe_text(task.get("title"), 180),
        "status": task.get("status"),
        "owner_agent_id": task.get("owner_agent_id"),
        "collaborator_agent_ids": task_collaborators(task),
        "priority": task.get("priority"),
        "risk_level": task.get("risk_level"),
        "scope": commander_extract_line(description, "Scope"),
        "avoid_scope": commander_extract_line(description, "Avoid scope"),
        "dependencies": commander_extract_dependencies(description),
        "verification_commands": commander_extract_verification(description),
        "acceptance_criteria": commander_safe_text(task.get("acceptance_criteria"), 360),
        "latest_run": latest_run,
        "evidence_counts": evidence,
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
    }
    item["package_status"] = commander_work_package_status(task, latest_run, evidence)
    item["recommended_action"] = commander_work_package_next_action(item)
    return item


def commander_work_packages_readback(conn: sqlite3.Connection, qs=None, headers=None) -> dict:
    qs = qs or {}
    workspace_id = normalize_workspace_id((qs.get("workspace_id") or [headers.get("X-AgentOps-Workspace-Id") if headers else "local-demo"])[0] or "local-demo")
    project_id = commander_safe_text((qs.get("project_id") or [""])[0], 120)
    plan_id = commander_safe_text((qs.get("plan_id") or [""])[0], 120)
    status_filter = commander_safe_text((qs.get("status") or ["all"])[0], 80)
    limit = min(max(int((qs.get("limit") or ["25"])[0]), 1), 100)
    sql = """SELECT * FROM tasks
        WHERE COALESCE(workspace_id,'local-demo')=?
        AND description LIKE 'Commander project:%'"""
    params: list = [workspace_id]
    if project_id:
        sql += " AND description LIKE ?"
        params.append(f"%Commander project: {project_id}%")
    if plan_id:
        sql += " AND (description LIKE ? OR task_id LIKE ?)"
        params.extend([f"%Plan: {plan_id}%", f"%{plan_id}%"])
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    packages = [commander_work_package_from_task(conn, row) for row in rows]
    if status_filter and status_filter != "all":
        packages = [item for item in packages if item.get("package_status") == status_filter or item.get("status") == status_filter]
    counts: dict[str, int] = {}
    for item in packages:
        key = item.get("package_status") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    project_counts: dict[str, int] = {}
    for item in packages:
        key = item.get("project_id") or "unknown"
        project_counts[key] = project_counts.get(key, 0) + 1
    next_actions = []
    for item in packages:
        action = item.get("recommended_action")
        if action and action not in next_actions:
            next_actions.append(action)
    if not next_actions:
        next_actions = ["agentops commander plan --goal \"Describe the customer project\" --confirm-create"]
    return {
        "provider": "agentops-commander",
        "operation": "work_packages_readback",
        "status": "ready" if packages else "empty",
        "workspace_id": workspace_id,
        "filter": {
            "project_id": project_id or None,
            "plan_id": plan_id or None,
            "status": status_filter,
            "limit": limit,
        },
        "summary": {
            "total": len(packages),
            "by_status": counts,
            "by_project": project_counts,
        },
        "work_packages": packages,
        "recommended_next_actions": next_actions[:8],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "task_created": False,
            "run_created": False,
            "live_execution_performed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
        },
        "token_omitted": True,
        "live_execution_performed": False,
    }


COMMANDER_INBOX_BUCKETS = ["ready_for_review", "still_running", "blocked", "late_or_stale", "needs_memory_review"]


def commander_age_sec(*values) -> int | None:
    now_dt = dt.datetime.now(dt.timezone.utc)
    for value in values:
        parsed = parse_iso_datetime(value)
        if parsed:
            return max(int((now_dt - parsed).total_seconds()), 0)
    return None


def commander_count(conn: sqlite3.Connection, sql: str, params=()) -> int:
    return int((conn.execute(sql, params).fetchone() or [0])[0] or 0)


def commander_evidence_counts(conn: sqlite3.Connection, task_id=None, run_id=None, artifact_id=None) -> dict:
    counts = {
        "artifacts": 0,
        "evaluations": 0,
        "audit_logs": 0,
        "approvals": 0,
        "pending_approvals": 0,
        "tool_calls": 0,
        "runtime_events": 0,
        "memories": 0,
    }
    if run_id:
        counts["artifacts"] += commander_count(conn, "SELECT COUNT(*) FROM artifacts WHERE run_id=?", (run_id,))
        counts["evaluations"] += commander_count(conn, "SELECT COUNT(*) FROM evaluations WHERE run_id=?", (run_id,))
        counts["tool_calls"] += commander_count(conn, "SELECT COUNT(*) FROM tool_calls WHERE run_id=?", (run_id,))
        counts["runtime_events"] += commander_count(conn, "SELECT COUNT(*) FROM runtime_events WHERE run_id=?", (run_id,))
    if task_id:
        counts["artifacts"] += commander_count(conn, "SELECT COUNT(*) FROM artifacts WHERE task_id=? AND (run_id IS NULL OR run_id<>?)", (task_id, run_id or ""))
        counts["evaluations"] += commander_count(conn, "SELECT COUNT(*) FROM evaluations WHERE task_id=? AND (run_id IS NULL OR run_id<>?)", (task_id, run_id or ""))
        counts["runtime_events"] += commander_count(conn, "SELECT COUNT(*) FROM runtime_events WHERE task_id=? AND (run_id IS NULL OR run_id<>?)", (task_id, run_id or ""))
        counts["memories"] += commander_count(conn, "SELECT COUNT(*) FROM memories WHERE task_id=?", (task_id,))
    if run_id or task_id:
        counts["approvals"] = commander_count(
            conn,
            "SELECT COUNT(*) FROM approvals WHERE (? IS NOT NULL AND run_id=?) OR (? IS NOT NULL AND task_id=?)",
            (run_id, run_id, task_id, task_id),
        )
        counts["pending_approvals"] = commander_count(
            conn,
            "SELECT COUNT(*) FROM approvals WHERE decision='pending' AND ((? IS NOT NULL AND run_id=?) OR (? IS NOT NULL AND task_id=?))",
            (run_id, run_id, task_id, task_id),
        )
    audit_terms = []
    audit_params = []
    for entity_type, entity_id in [("tasks", task_id), ("runs", run_id), ("artifacts", artifact_id)]:
        if entity_id:
            audit_terms.append("(entity_type=? AND entity_id=?)")
            audit_params.extend([entity_type, entity_id])
    if audit_terms:
        counts["audit_logs"] = commander_count(conn, f"SELECT COUNT(*) FROM audit_logs WHERE {' OR '.join(audit_terms)}", audit_params)
    return counts


def commander_inbox_item(bucket: str, row: dict, title: str, recommended_action: str, conn: sqlite3.Connection, artifact_id=None) -> dict:
    task_id = row.get("task_id") or row.get("result_task_id")
    run_id = row.get("run_id") or row.get("result_run_id")
    job_id = row.get("job_id")
    artifact_id = artifact_id or row.get("artifact_id") or row.get("result_artifact_id")
    item_id = f"{bucket}:{job_id or run_id or task_id or artifact_id or row.get('memory_id')}"
    return {
        "item_id": item_id,
        "bucket": bucket,
        "title": commander_safe_text(title, 180),
        "status": row.get("status") or row.get("task_status") or row.get("review_status"),
        "task_id": task_id,
        "run_id": run_id,
        "job_id": job_id,
        "artifact_id": artifact_id,
        "agent_id": row.get("agent_id"),
        "owner_agent_id": row.get("owner_agent_id") or row.get("agent_id"),
        "age_sec": commander_age_sec(row.get("updated_at"), row.get("started_at"), row.get("created_at")),
        "evidence_counts": commander_evidence_counts(conn, task_id=task_id, run_id=run_id, artifact_id=artifact_id),
        "recommended_action": recommended_action,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at") or row.get("completed_at") or row.get("ended_at") or row.get("created_at"),
    }


def commander_integration_inbox(conn: sqlite3.Connection, headers, qs=None) -> dict:
    qs = qs or {}

    def query_value(name: str, default: str = "") -> str:
        value = qs.get(name, default)
        if isinstance(value, list):
            return str(value[0]) if value else default
        return str(value)

    bucket_filter = query_value("bucket", "all").strip()
    if bucket_filter in ("", "all", "*"):
        bucket_filter = ""
    if bucket_filter and bucket_filter not in COMMANDER_INBOX_BUCKETS:
        bucket_filter = ""
    try:
        threshold_sec = max(60, min(86400, int(query_value("threshold_sec", "900"))))
    except (TypeError, ValueError):
        threshold_sec = 900
    try:
        item_limit = max(1, min(50, int(query_value("limit", "20"))))
    except (TypeError, ValueError):
        item_limit = 20
    per_bucket_limit = item_limit if bucket_filter else 8
    cutoff_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=threshold_sec)).isoformat()
    items: list[dict] = []
    seen: set[str] = set()

    def add(item: dict) -> None:
        item_id = item.get("item_id")
        if bucket_filter and item.get("bucket") != bucket_filter:
            return
        if item_id in seen or len(items) >= item_limit:
            return
        seen.add(item_id)
        items.append(item)

    ready_run_rows = rows_to_dicts(conn.execute(
        """SELECT r.run_id, r.task_id, r.agent_id, r.status, r.started_at, r.ended_at, r.created_at,
                  COALESCE(r.ended_at, r.created_at) AS updated_at, r.output_summary,
                  t.title AS task_title, t.status AS task_status, t.owner_agent_id,
                  (SELECT artifact_id FROM artifacts a WHERE a.run_id=r.run_id ORDER BY a.created_at DESC LIMIT 1) AS artifact_id
        FROM runs r
        JOIN tasks t ON t.task_id=r.task_id
        WHERE r.status='completed'
          AND (r.approval_required=1 OR t.status='waiting_approval'
               OR EXISTS (SELECT 1 FROM approvals ap WHERE ap.run_id=r.run_id AND ap.decision='pending'))
          AND (EXISTS (SELECT 1 FROM artifacts a WHERE a.run_id=r.run_id)
               OR EXISTS (SELECT 1 FROM evaluations e WHERE e.run_id=r.run_id)
               OR EXISTS (SELECT 1 FROM audit_logs al WHERE al.entity_type='runs' AND al.entity_id=r.run_id))
        ORDER BY r.created_at DESC
        LIMIT ?""",
        (per_bucket_limit,),
    ).fetchall())
    for row in ready_run_rows:
        add(commander_inbox_item(
            "ready_for_review",
            row,
            row.get("task_title") or row.get("output_summary") or row.get("run_id"),
            "Review evidence, resolve pending approval, and decide whether this worker output is ready for delivery.",
            conn,
            artifact_id=row.get("artifact_id"),
        ))

    ready_job_rows = rows_to_dicts(conn.execute(
        """SELECT j.job_id, j.workflow_type, j.status, j.title, j.result_task_id, j.result_run_id, j.result_artifact_id,
                  j.created_at, j.updated_at, j.completed_at, t.owner_agent_id, r.agent_id
        FROM workflow_jobs j
        LEFT JOIN tasks t ON t.task_id=j.result_task_id
        LEFT JOIN runs r ON r.run_id=j.result_run_id
        WHERE j.status='completed'
          AND j.result_artifact_id IS NOT NULL
          AND (t.status='waiting_approval'
               OR EXISTS (SELECT 1 FROM approvals ap WHERE ap.task_id=j.result_task_id AND ap.decision='pending')
               OR EXISTS (SELECT 1 FROM approvals ap WHERE ap.run_id=j.result_run_id AND ap.decision='pending'))
        ORDER BY j.updated_at DESC
        LIMIT ?""",
        (per_bucket_limit,),
    ).fetchall())
    for row in ready_job_rows:
        add(commander_inbox_item(
            "ready_for_review",
            row,
            row.get("title") or f"Completed workflow job {row.get('job_id')}",
            "Open the completed job result, inspect the linked artifact, and approve or reject delivery.",
            conn,
        ))

    running_job_rows = rows_to_dicts(conn.execute(
        """SELECT job_id, workflow_type, status, title, result_task_id, result_run_id, result_artifact_id,
                  adapter, created_at, started_at, updated_at
        FROM workflow_jobs
        WHERE status IN ('queued','running') AND updated_at>=?
        ORDER BY updated_at ASC
        LIMIT ?""",
        (cutoff_iso, per_bucket_limit),
    ).fetchall())
    for row in running_job_rows:
        add(commander_inbox_item(
            "still_running",
            row,
            row.get("title") or f"{row.get('workflow_type')} job {row.get('job_id')}",
            "Let the async workflow continue, or check job status if the commander needs a delivery ETA.",
            conn,
        ))

    running_task_rows = rows_to_dicts(conn.execute(
        """SELECT task_id, title, status, owner_agent_id, created_at, updated_at
        FROM tasks
        WHERE status='running' AND updated_at>=?
        ORDER BY updated_at ASC
        LIMIT ?""",
        (cutoff_iso, per_bucket_limit),
    ).fetchall())
    for row in running_task_rows:
        add(commander_inbox_item(
            "still_running",
            row,
            row.get("title") or row.get("task_id"),
            "Monitor the assigned worker and wait for run or artifact evidence before reviewing.",
            conn,
        ))

    running_run_rows = rows_to_dicts(conn.execute(
        """SELECT r.run_id, r.task_id, r.agent_id, r.status, r.started_at, r.created_at,
                  COALESCE(r.started_at, r.created_at) AS updated_at, t.title AS task_title, t.owner_agent_id
        FROM runs r
        JOIN tasks t ON t.task_id=r.task_id
        WHERE r.status IN ('queued','running') AND COALESCE(r.started_at, r.created_at)>=?
        ORDER BY COALESCE(r.started_at, r.created_at) ASC
        LIMIT ?""",
        (cutoff_iso, per_bucket_limit),
    ).fetchall())
    for row in running_run_rows:
        add(commander_inbox_item(
            "still_running",
            row,
            row.get("task_title") or row.get("run_id"),
            "Wait for the run to finish, then review its evidence chain.",
            conn,
        ))

    blocked_job_rows = rows_to_dicts(conn.execute(
        """SELECT job_id, workflow_type, status, title, result_task_id, result_run_id, result_artifact_id,
                  error_message, created_at, started_at, completed_at, updated_at
        FROM workflow_jobs
        WHERE status='failed'
        ORDER BY updated_at DESC
        LIMIT ?""",
        (per_bucket_limit,),
    ).fetchall())
    for row in blocked_job_rows:
        add(commander_inbox_item(
            "blocked",
            row,
            row.get("title") or row.get("error_message") or f"Failed job {row.get('job_id')}",
            "Inspect the job error, choose retry or mark-failed recovery, and assign a follow-up worker if needed.",
            conn,
        ))

    blocked_task_rows = rows_to_dicts(conn.execute(
        """SELECT task_id, title, status, owner_agent_id, created_at, updated_at
        FROM tasks
        WHERE status IN ('blocked','failed')
        ORDER BY updated_at DESC
        LIMIT ?""",
        (per_bucket_limit,),
    ).fetchall())
    for row in blocked_task_rows:
        add(commander_inbox_item(
            "blocked",
            row,
            row.get("title") or row.get("task_id"),
            "Review failure evidence, unblock requirements, or reassign the task.",
            conn,
        ))

    blocked_run_rows = rows_to_dicts(conn.execute(
        """SELECT r.run_id, r.task_id, r.agent_id, r.status, r.error_message, r.started_at, r.ended_at, r.created_at,
                  COALESCE(r.ended_at, r.created_at) AS updated_at, t.title AS task_title, t.owner_agent_id
        FROM runs r
        JOIN tasks t ON t.task_id=r.task_id
        WHERE r.status IN ('blocked','failed')
        ORDER BY COALESCE(r.ended_at, r.created_at) DESC
        LIMIT ?""",
        (per_bucket_limit,),
    ).fetchall())
    for row in blocked_run_rows:
        add(commander_inbox_item(
            "blocked",
            row,
            row.get("task_title") or row.get("error_message") or row.get("run_id"),
            "Inspect run error evidence and decide whether to retry, reject, or create a recovery task.",
            conn,
        ))

    stale_job_rows = rows_to_dicts(conn.execute(
        """SELECT job_id, workflow_type, status, title, result_task_id, result_run_id, result_artifact_id,
                  created_at, started_at, updated_at
        FROM workflow_jobs
        WHERE status IN ('queued','running') AND updated_at<?
        ORDER BY updated_at ASC
        LIMIT ?""",
        (cutoff_iso, per_bucket_limit),
    ).fetchall())
    for row in stale_job_rows:
        add(commander_inbox_item(
            "late_or_stale",
            row,
            row.get("title") or f"Stale workflow job {row.get('job_id')}",
            "Check job status and use workflow stuck recovery if it has exceeded the async threshold.",
            conn,
        ))

    stale_task_rows = rows_to_dicts(conn.execute(
        """SELECT task_id, title, status, owner_agent_id, created_at, updated_at
        FROM tasks
        WHERE status='running' AND updated_at<?
        ORDER BY updated_at ASC
        LIMIT ?""",
        (cutoff_iso, per_bucket_limit),
    ).fetchall())
    for row in stale_task_rows:
        add(commander_inbox_item(
            "late_or_stale",
            row,
            row.get("title") or row.get("task_id"),
            "Contact or release the worker because the running task exceeded the freshness threshold.",
            conn,
        ))

    stale_run_rows = rows_to_dicts(conn.execute(
        """SELECT r.run_id, r.task_id, r.agent_id, r.status, r.started_at, r.created_at,
                  COALESCE(r.started_at, r.created_at) AS updated_at, t.title AS task_title, t.owner_agent_id
        FROM runs r
        JOIN tasks t ON t.task_id=r.task_id
        WHERE r.status IN ('queued','running') AND COALESCE(r.started_at, r.created_at)<?
        ORDER BY COALESCE(r.started_at, r.created_at) ASC
        LIMIT ?""",
        (cutoff_iso, per_bucket_limit),
    ).fetchall())
    for row in stale_run_rows:
        add(commander_inbox_item(
            "late_or_stale",
            row,
            row.get("task_title") or f"Stale run {row.get('run_id')}",
            "Investigate the runtime, then block or recover the run if no worker is still active.",
            conn,
        ))

    memory_rows = rows_to_dicts(conn.execute(
        """SELECT memory_id, task_id, agent_id, review_status, memory_type, canonical_text,
                  source_ref, created_at, updated_at
        FROM memories
        WHERE review_status IN ('candidate','stale') OR (ttl_review_due_at IS NOT NULL AND ttl_review_due_at<?)
        ORDER BY updated_at DESC
        LIMIT ?""",
        (now_iso(), per_bucket_limit),
    ).fetchall())
    for row in memory_rows:
        item = commander_inbox_item(
            "needs_memory_review",
            row,
            f"{row.get('memory_type')}: {row.get('canonical_text')}",
            "Review the memory candidate before allowing it to become durable commander context.",
            conn,
        )
        item["memory_id"] = row.get("memory_id")
        add(item)

    returned_summary = {bucket: 0 for bucket in COMMANDER_INBOX_BUCKETS}
    for item in items:
        returned_summary[item["bucket"]] += 1

    ready_total = commander_count(
        conn,
        """SELECT COUNT(*)
        FROM runs r
        JOIN tasks t ON t.task_id=r.task_id
        WHERE r.status='completed'
          AND (r.approval_required=1 OR t.status='waiting_approval'
               OR EXISTS (SELECT 1 FROM approvals ap WHERE ap.run_id=r.run_id AND ap.decision='pending'))
          AND (EXISTS (SELECT 1 FROM artifacts a WHERE a.run_id=r.run_id)
               OR EXISTS (SELECT 1 FROM evaluations e WHERE e.run_id=r.run_id)
               OR EXISTS (SELECT 1 FROM audit_logs al WHERE al.entity_type='runs' AND al.entity_id=r.run_id))"""
    )
    ready_total += commander_count(
        conn,
        """SELECT COUNT(*)
        FROM workflow_jobs j
        LEFT JOIN tasks t ON t.task_id=j.result_task_id
        WHERE j.status='completed'
          AND j.result_artifact_id IS NOT NULL
          AND (t.status='waiting_approval'
               OR EXISTS (SELECT 1 FROM approvals ap WHERE ap.task_id=j.result_task_id AND ap.decision='pending')
               OR EXISTS (SELECT 1 FROM approvals ap WHERE ap.run_id=j.result_run_id AND ap.decision='pending'))"""
    )

    still_running_total = commander_count(conn, "SELECT COUNT(*) FROM workflow_jobs WHERE status IN ('queued','running') AND updated_at>=?", (cutoff_iso,))
    still_running_total += commander_count(conn, "SELECT COUNT(*) FROM tasks WHERE status='running' AND updated_at>=?", (cutoff_iso,))
    still_running_total += commander_count(conn, "SELECT COUNT(*) FROM runs WHERE status IN ('queued','running') AND COALESCE(started_at, created_at)>=?", (cutoff_iso,))

    blocked_total = commander_count(conn, "SELECT COUNT(*) FROM workflow_jobs WHERE status='failed'")
    blocked_total += commander_count(conn, "SELECT COUNT(*) FROM tasks WHERE status IN ('blocked','failed')")
    blocked_total += commander_count(conn, "SELECT COUNT(*) FROM runs WHERE status IN ('blocked','failed')")
    late_total = commander_count(conn, "SELECT COUNT(*) FROM workflow_jobs WHERE status IN ('queued','running') AND updated_at<?", (cutoff_iso,))
    late_total += commander_count(conn, "SELECT COUNT(*) FROM tasks WHERE status='running' AND updated_at<?", (cutoff_iso,))
    late_total += commander_count(conn, "SELECT COUNT(*) FROM runs WHERE status IN ('queued','running') AND COALESCE(started_at, created_at)<?", (cutoff_iso,))
    memory_review_total = commander_count(
        conn,
        "SELECT COUNT(*) FROM memories WHERE review_status IN ('candidate','stale') OR (ttl_review_due_at IS NOT NULL AND ttl_review_due_at<?)",
        (now_iso(),),
    )
    bucket_totals = {
        "ready_for_review": ready_total,
        "still_running": still_running_total,
        "blocked": blocked_total,
        "late_or_stale": late_total,
        "needs_memory_review": memory_review_total,
    }
    recommended_next_actions = []
    if ready_total:
        recommended_next_actions.append("Review ready worker results and resolve pending delivery approvals.")
    if late_total:
        recommended_next_actions.append("Open stuck workflow recovery and mark stale jobs failed or reassign them.")
    if blocked_total:
        recommended_next_actions.append("Inspect blocked tasks/runs, then retry, reject, or create a recovery package.")
    if memory_review_total:
        recommended_next_actions.append("Review memory candidates before promoting them into durable project context.")
    if still_running_total:
        recommended_next_actions.append("Let active worker lanes continue while reviewing completed inbox items.")
    if not recommended_next_actions:
        recommended_next_actions = ["Dispatch the next customer worker task or review the commander project board."]

    status = "blocked" if blocked_total or late_total else "attention" if items else "ready"
    return {
        "provider": "agentops-commander",
        "operation": "integration_inbox",
        "status": status,
        "token_omitted": True,
        "live_execution_performed": False,
        "workspace_id": normalize_workspace_id(headers.get("X-AgentOps-Workspace-Id") or "local-demo"),
        "threshold_sec": threshold_sec,
        "filter": {
            "bucket": bucket_filter or "all",
            "limit": item_limit,
            "threshold_sec": threshold_sec,
        },
        "summary": {
            **bucket_totals,
            "buckets": bucket_totals,
            "returned_buckets": returned_summary,
            "items_returned": len(items),
            "item_limit": item_limit,
            "total": sum(bucket_totals.values()),
            "blocked_total": blocked_total,
            "late_or_stale_total": late_total,
        },
        "inbox_items": items,
        "recommended_next_actions": recommended_next_actions[:8],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "task_created": False,
            "run_created": False,
            "job_created": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
        },
    }


def recent_closed_loop_run_count(conn: sqlite3.Connection, limit: int = 250) -> int:
    candidate_rows = conn.execute(
        """SELECT r.run_id FROM runs r
        WHERE EXISTS (SELECT 1 FROM tool_calls tc WHERE tc.run_id=r.run_id)
          AND EXISTS (SELECT 1 FROM evaluations e WHERE e.run_id=r.run_id)
          AND EXISTS (SELECT 1 FROM artifacts a WHERE a.run_id=r.run_id)
        ORDER BY r.created_at DESC
        LIMIT ?""",
        (limit,),
    ).fetchall()
    count = 0
    for row in candidate_rows:
        run_id = row["run_id"]
        audit_row = conn.execute(
            """SELECT 1 FROM audit_logs
            WHERE entity_id=?
               OR metadata_json LIKE ?
            LIMIT 1""",
            (run_id, f"%{run_id}%"),
        ).fetchone()
        if audit_row:
            count += 1
    return count


def local_readiness(conn: sqlite3.Connection, headers) -> dict:
    gateway, gateway_status_code = agent_gateway_status(conn, headers)
    security = security_production_readiness(conn, headers)
    worker = worker_status(conn)
    adapter_summary = worker.get("adapter_readiness") or {}
    adapter_payload = worker_adapter_readiness(conn)
    docs = [
        ("README", ROOT / "README.md"),
        ("remote_worker_runbook", ROOT / "docs" / "REMOTE_WORKER_OPERATIONS_RUNBOOK.md"),
        ("agent_gateway_cli_spec", ROOT / "docs" / "AGENT_GATEWAY_CLI_SPEC.md"),
        ("customer_local_deployment_runbook", ROOT / "docs" / "CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md"),
        ("commercial_migration_closed_loop", ROOT / "docs" / "COMMERCIAL_MIGRATION_CLOSED_LOOP.md"),
        ("local_runtime_acceptance", ROOT / "scripts" / "local_runtime_acceptance.py"),
        ("worker_adapter_readiness_smoke", ROOT / "scripts" / "worker_adapter_readiness_smoke.py"),
        ("local_backup_utility", ROOT / "scripts" / "agentops_local_backup.py"),
        ("local_backup_smoke", ROOT / "scripts" / "agentops_local_backup_smoke.py"),
    ]
    doc_status = [{"id": doc_id, "path": str(path.relative_to(ROOT)), "exists": path.exists()} for doc_id, path in docs]
    evidence = {
        "tasks": scalar_count(conn, "SELECT COUNT(*) FROM tasks"),
        "planned_tasks": scalar_count(conn, "SELECT COUNT(*) FROM tasks WHERE status IN ('planned','backlog')"),
        "completed_tasks": scalar_count(conn, "SELECT COUNT(*) FROM tasks WHERE status='completed'"),
        "runs": scalar_count(conn, "SELECT COUNT(*) FROM runs"),
        "completed_runs": scalar_count(conn, "SELECT COUNT(*) FROM runs WHERE status='completed'"),
        "tool_calls": scalar_count(conn, "SELECT COUNT(*) FROM tool_calls"),
        "evaluations": scalar_count(conn, "SELECT COUNT(*) FROM evaluations"),
        "audit_logs": scalar_count(conn, "SELECT COUNT(*) FROM audit_logs"),
        "artifacts": scalar_count(conn, "SELECT COUNT(*) FROM artifacts"),
        "memories": scalar_count(conn, "SELECT COUNT(*) FROM memories"),
        "memory_candidates": scalar_count(conn, "SELECT COUNT(*) FROM memories WHERE review_status='candidate'"),
        "approved_memories": scalar_count(conn, "SELECT COUNT(*) FROM memories WHERE review_status='approved'"),
        "pending_approvals": scalar_count(conn, "SELECT COUNT(*) FROM approvals WHERE decision='pending'"),
        "approvals": scalar_count(conn, "SELECT COUNT(*) FROM approvals"),
        "workflow_jobs": scalar_count(conn, "SELECT COUNT(*) FROM workflow_jobs"),
        "customer_worker_artifacts": scalar_count(conn, "SELECT COUNT(*) FROM artifacts WHERE artifact_type='customer_worker_result'"),
        "closed_loop_runs": recent_closed_loop_run_count(conn),
    }
    evidence["has_task_run_tool_eval_audit_artifact_chain"] = evidence["closed_loop_runs"] > 0
    evidence["has_memory_or_knowledge"] = evidence["memories"] > 0
    evidence["has_approval_flow"] = evidence["approvals"] > 0
    gates = [
        {
            "id": "agent_gateway",
            "label": "Agent Gateway CLI/API",
            "ok": gateway_status_code == 200 and gateway.get("status") == "ready",
            "status": gateway.get("status") or gateway.get("error") or "unknown",
            "detail": gateway.get("message") or (gateway.get("auth") or {}).get("mode") or "ready",
            "next_action": "agentops status",
        },
        {
            "id": "worker_fleet",
            "label": "Local/remote worker readiness",
            "ok": (worker.get("fleet_health") or {}).get("overall") != "blocked",
            "status": (worker.get("fleet_health") or {}).get("overall") or worker.get("status"),
            "detail": (worker.get("fleet_health") or {}).get("contract") or "worker status available",
            "next_action": "agentops worker status",
        },
        {
            "id": "production_security",
            "label": "Production security boundary",
            "ok": security.get("production_ready") is True,
            "status": security.get("status") or "unknown",
            "detail": security.get("contract") or f"auth_mode={security.get('auth_mode')}",
            "next_action": "agentops security production-readiness",
        },
        {
            "id": "adapter_route",
            "label": "Mock/Hermes/OpenClaw route selection",
            "ok": adapter_summary.get("recommended_adapter") in {"mock", "hermes", "openclaw"},
            "status": adapter_payload.get("status"),
            "detail": f"recommended_adapter={adapter_summary.get('recommended_adapter') or 'unknown'}",
            "next_action": "agentops worker readiness",
        },
        {
            "id": "knowledge_memory",
            "label": "Memory/knowledge sedimentation",
            "ok": evidence["has_memory_or_knowledge"],
            "status": "ready" if evidence["has_memory_or_knowledge"] else "needs_seed_or_run",
            "detail": f"{evidence['memories']} memories, {evidence['memory_candidates']} candidates",
            "next_action": "agentops memory propose --text '...' --type artifact_summary",
        },
        {
            "id": "evidence_chain",
            "label": "task -> run -> tool/eval/audit/artifact",
            "ok": evidence["has_task_run_tool_eval_audit_artifact_chain"],
            "status": "ready" if evidence["has_task_run_tool_eval_audit_artifact_chain"] else "needs_demo_run",
            "detail": f"{evidence['closed_loop_runs']} closed-loop run(s)",
            "next_action": "agentops workflow customer-worker-task --adapter mock --title 'Local readiness demo' --description 'Write full MIS evidence.'",
        },
        {
            "id": "runbook",
            "label": "Local demo/runbook",
            "ok": all(item["exists"] for item in doc_status),
            "status": "ready" if all(item["exists"] for item in doc_status) else "missing_docs",
            "detail": ", ".join(item["id"] for item in doc_status if not item["exists"]) or "README and worker runbook present",
            "next_action": "open docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md",
        },
    ]
    blockers = [gate for gate in gates if not gate["ok"] and gate["id"] in {"agent_gateway", "worker_fleet", "adapter_route", "runbook"}]
    warnings = [gate for gate in gates if not gate["ok"] and gate not in blockers]
    overall = "blocked" if blockers else "attention" if warnings else "ready"
    return {
        "provider": "agentops-local",
        "operation": "local_readiness",
        "status": overall,
        "ok": overall != "blocked",
        "workspace_id": normalize_workspace_id(headers.get("X-AgentOps-Workspace-Id") or "local-demo"),
        "gates": gates,
        "evidence": evidence,
        "adapter_readiness": adapter_payload.get("summary"),
        "worker_fleet_health": worker.get("fleet_health"),
        "security_production_readiness": security,
        "gateway": gateway,
        "docs": doc_status,
        "ui_routes": {
            "worker_console": "/workspace/agents",
            "memory": "/workspace/memory",
            "approvals": "/workspace/approvals",
            "tool_calls": "/admin/toolcalls",
            "reports": "/workspace/reports",
        },
        "next_actions": [gate["next_action"] for gate in gates if not gate["ok"]] or [
            "agentops workflow customer-worker-task --adapter mock --title 'Local smoke task' --description 'Verify full ledger evidence.'",
            "agentops worker readiness",
            "open http://127.0.0.1:19001/workspace/agents",
        ],
        "contract": "single local/open-source workspace; CLI/API for agents, UI for humans; no SaaS multi-tenant, no Notion/Dify live sync by default",
        "live_execution_performed": False,
        "token_omitted": True,
    }


def dispatch_local_worker_once(conn, body: dict) -> dict:
    adapter = coerce_choice(body.get("adapter"), {"mock", "hermes", "openclaw"}, "mock")
    confirm_run = bool(body.get("confirm_run"))
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    task_id = body.get("task_id") or stable_id("tsk_worker_ui", adapter, stamp, uuid.uuid4().hex[:8])
    agent_id = body.get("agent_id") or stable_id("agt_worker_ui", adapter, stamp, uuid.uuid4().hex[:8])
    now = now_iso()
    title = redact_text(body.get("title") or f"{adapter} worker UI dispatch", 140)
    description = redact_text(
        body.get("description")
        or "Run one local AgentOps worker loop from the UI and write run/tool/eval/audit evidence.",
        600,
    )
    acceptance = redact_text(
        body.get("acceptance_criteria")
        or "Worker must complete one normal MIS task and write evidence through Agent Gateway.",
        400,
    )
    ensure_gateway_agent(
        conn,
        agent_id,
        name=f"UI {adapter} Worker",
        role=f"Local {adapter} Adapter Worker",
        runtime_type=adapter,
    )
    row = {
        "task_id": task_id,
        "title": title,
        "description": description,
        "requester_id": body.get("requester_id", "usr_founder"),
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": json.dumps([], ensure_ascii=False),
        "status": "planned",
        "priority": coerce_choice(body.get("priority"), VALID_PRIORITIES, "high"),
        "due_date": None,
        "acceptance_criteria": acceptance,
        "risk_level": "low",
        "budget_limit_usd": float(body.get("budget_limit_usd") or 1.0),
        "created_at": now,
        "updated_at": now,
    }
    upsert_task(conn, row, "worker-ui-dispatch")
    audit(conn, "user", "usr_founder", "worker.dispatch_task.create", "tasks", task_id, None, row, {"adapter": adapter, "confirm_run": confirm_run})
    conn.commit()

    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "agent_worker.py"),
        "--once",
        "--adapter",
        adapter,
        "--agent-id",
        agent_id,
        "--base-url",
        os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"),
    ]
    if confirm_run:
        cmd.append("--confirm-run")
    worker_timeout = 260
    if adapter == "hermes":
        hermes_timeout = int(body.get("hermes_timeout") or os.environ.get("HERMES_TIMEOUT", "300"))
        worker_timeout = max(hermes_timeout + 80, worker_timeout)
        cmd.extend([
            "--hermes-gateway-url",
            os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642"),
            "--hermes-timeout",
            str(hermes_timeout),
        ])
    if adapter == "openclaw":
        cmd.extend(["--openclaw-bin", str(OPENCLAW_BIN), "--openclaw-timeout", "180"])

    started = dt.datetime.now(dt.timezone.utc)
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=worker_timeout, check=False)
        stdout = proc.stdout.strip()
        parsed = json.loads(stdout) if stdout else {}
        ok = proc.returncode == 0 and bool(parsed.get("ok", True))
        error = None if ok else redact_text(proc.stderr or stdout or f"exit={proc.returncode}", 240)
    except Exception as exc:
        parsed = {}
        ok = False
        error = redact_text(str(exc), 240)
    duration = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
    audit(conn, "system", "worker-dispatch", "worker.dispatch_once", "tasks", task_id, None, {"ok": ok}, {"adapter": adapter, "agent_id": agent_id, "duration_ms": duration, "error": error})
    conn.commit()
    return {
        "provider": "agentops-worker",
        "dry_run": adapter in {"hermes", "openclaw"} and not confirm_run,
        "ok": ok,
        "adapter": adapter,
        "agent_id": agent_id,
        "task_id": task_id,
        "duration_ms": duration,
        "worker_result": parsed,
        "error": error,
    }


def run_customer_worker_task_workflow(conn, body: dict) -> tuple[dict, int]:
    adapter = coerce_choice(body.get("adapter"), {"mock", "hermes", "openclaw"}, "mock")
    confirm_run = bool(body.get("confirm_run"))
    title = redact_text(body.get("title") or "客户 Worker 任务", 160)
    description = redact_text(body.get("description") or "Customer task should be processed by an AgentOps worker.", 800)
    acceptance = redact_text(body.get("acceptance_criteria") or "Worker must write run, tool, evaluation and audit evidence.", 500)
    conn.execute(
        """INSERT OR IGNORE INTO users(user_id,name,email,role,created_at)
        VALUES(?,?,?,?,?)""",
        ("usr_customer_demo", "Customer Demo User", "customer-demo@example.local", "requester", now_iso()),
    )
    call_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")
    worker_agent_id = body.get("worker_agent_id") or stable_id("agt_customer_worker", adapter, call_id, uuid.uuid4().hex[:8])
    connector_id = runtime_connector_for_adapter(adapter)
    connector_trust = runtime_connector_trust(conn, connector_id)
    adapter_readiness = (worker_adapter_readiness(conn).get("adapters") or {}).get(adapter) or {}
    if adapter in {"hermes", "openclaw"} and confirm_run and connector_trust and connector_trust.get("trust_status") == "blocked":
        task_id = body.get("task_id") or stable_id("tsk_customer_worker_trust_blocked", adapter, title, now_iso())
        agent_id = worker_agent_id
        ensure_gateway_agent(conn, agent_id, name=f"Customer {adapter} Worker", role="Customer Task Worker", runtime_type=adapter)
        now = now_iso()
        row = {
            "task_id": task_id,
            "title": title,
            "description": description,
            "requester_id": body.get("requester_id", "usr_customer_demo"),
            "owner_agent_id": agent_id,
            "collaborator_agent_ids": json.dumps(body.get("selected_agent_ids") or [], ensure_ascii=False),
            "status": "blocked",
            "priority": coerce_choice(body.get("priority"), VALID_PRIORITIES, "high"),
            "due_date": body.get("due_date"),
            "acceptance_criteria": acceptance,
            "risk_level": coerce_choice(body.get("risk_level"), VALID_RISK_LEVELS, "medium"),
            "budget_limit_usd": float(body.get("budget_limit_usd") or 1.0),
            "created_at": now,
            "updated_at": now,
        }
        upsert_task(conn, row, "customer-worker-task")
        reason = redact_text(
            connector_trust.get("trust_note")
            or f"{adapter} live execution is blocked by runtime connector trust policy.",
            260,
        )
        runtime_event(conn, connector_id, "customer_worker_task.trust_blocked", "blocked", task_id=task_id, agent_id=agent_id, input_summary=f"{adapter} worker live execution blocked by trust registry.", output_summary=reason)
        audit(conn, "system", "runtime-trust-registry", "workflow.customer_worker_task.trust_blocked", "tasks", task_id, None, row, {"adapter": adapter, "connector_id": connector_id, "trust_status": "blocked", "raw_output_omitted": True})
        conn.commit()
        return {
            "provider": "agentops-worker",
            "workflow": "customer_worker_task",
            "dry_run": True,
            "ok": False,
            "adapter": adapter,
            "task_id": task_id,
            "agent_id": agent_id,
            "connector_id": connector_id,
            "trust_status": "blocked",
            "reason": "runtime_connector_trust_blocked",
            "note": reason,
        }, 409
    if adapter in {"hermes", "openclaw"} and confirm_run and adapter_readiness.get("readiness") in {"unavailable", "blocked"}:
        task_id = body.get("task_id") or stable_id("tsk_customer_worker_adapter_not_ready", adapter, title, now_iso())
        agent_id = worker_agent_id
        ensure_gateway_agent(conn, agent_id, name=f"Customer {adapter} Worker", role="Customer Task Worker", runtime_type=adapter)
        now = now_iso()
        row = {
            "task_id": task_id,
            "title": title,
            "description": description,
            "requester_id": body.get("requester_id", "usr_customer_demo"),
            "owner_agent_id": agent_id,
            "collaborator_agent_ids": json.dumps(body.get("selected_agent_ids") or [], ensure_ascii=False),
            "status": "blocked",
            "priority": coerce_choice(body.get("priority"), VALID_PRIORITIES, "high"),
            "due_date": body.get("due_date"),
            "acceptance_criteria": acceptance,
            "risk_level": coerce_choice(body.get("risk_level"), VALID_RISK_LEVELS, "medium"),
            "budget_limit_usd": float(body.get("budget_limit_usd") or 1.0),
            "created_at": now,
            "updated_at": now,
        }
        upsert_task(conn, row, "customer-worker-task")
        reason = redact_text(
            adapter_readiness.get("last_error")
            or f"{adapter} adapter is not ready for confirmed live execution.",
            260,
        )
        runtime_event(conn, connector_id, "customer_worker_task.adapter_not_ready", "blocked", task_id=task_id, agent_id=agent_id, input_summary=f"{adapter} worker live execution blocked by adapter readiness.", output_summary=reason)
        audit(conn, "system", "worker-adapter-readiness", "workflow.customer_worker_task.adapter_not_ready", "tasks", task_id, None, row, {
            "adapter": adapter,
            "connector_id": connector_id,
            "readiness": adapter_readiness.get("readiness"),
            "recommended_action": adapter_readiness.get("recommended_action"),
            "raw_output_omitted": True,
        })
        conn.commit()
        return {
            "provider": "agentops-worker",
            "workflow": "customer_worker_task",
            "dry_run": True,
            "ok": False,
            "adapter": adapter,
            "task_id": task_id,
            "agent_id": agent_id,
            "connector_id": connector_id,
            "reason": "adapter_not_ready",
            "readiness": adapter_readiness.get("readiness"),
            "recommended_action": adapter_readiness.get("recommended_action"),
            "note": reason,
            "token_omitted": True,
        }, 409
    if adapter in {"hermes", "openclaw"} and not confirm_run:
        task_id = body.get("task_id") or stable_id("tsk_customer_worker_plan", adapter, title, now_iso())
        agent_id = worker_agent_id
        ensure_gateway_agent(conn, agent_id, name=f"Customer {adapter} Worker", role="Customer Task Worker", runtime_type=adapter)
        now = now_iso()
        row = {
            "task_id": task_id,
            "title": title,
            "description": description,
            "requester_id": body.get("requester_id", "usr_customer_demo"),
            "owner_agent_id": agent_id,
            "collaborator_agent_ids": json.dumps(body.get("selected_agent_ids") or [], ensure_ascii=False),
            "status": "planned",
            "priority": coerce_choice(body.get("priority"), VALID_PRIORITIES, "high"),
            "due_date": body.get("due_date"),
            "acceptance_criteria": acceptance,
            "risk_level": coerce_choice(body.get("risk_level"), VALID_RISK_LEVELS, "medium"),
            "budget_limit_usd": float(body.get("budget_limit_usd") or 1.0),
            "created_at": now,
            "updated_at": now,
        }
        upsert_task(conn, row, "customer-worker-task")
        runtime_event(conn, "rtc_agent_gateway_local", "customer_worker_task.confirm_required", "planned", task_id=task_id, agent_id=agent_id, input_summary=f"{adapter} worker requires confirm_run before live execution.")
        audit(conn, "user", "usr_customer_demo", "workflow.customer_worker_task.confirm_required", "tasks", task_id, None, row, {"adapter": adapter, "confirm_run": False})
        conn.commit()
        return {
            "provider": "agentops-worker",
            "workflow": "customer_worker_task",
            "dry_run": True,
            "ok": False,
            "adapter": adapter,
            "task_id": task_id,
            "agent_id": agent_id,
            "requires": {"confirm_run": True},
            "reason": "confirm_run_required_for_live_adapter",
            "note": "Task was planned but live Hermes/OpenClaw worker execution requires explicit confirmation.",
        }, 201

    dispatch = dispatch_local_worker_once(conn, {
        "adapter": adapter,
        "confirm_run": confirm_run,
        "title": title,
        "description": description,
        "acceptance_criteria": acceptance,
        "priority": body.get("priority") or "high",
        "risk_level": body.get("risk_level") or "medium",
        "budget_limit_usd": body.get("budget_limit_usd") or 1.0,
        "requester_id": body.get("requester_id", "usr_customer_demo"),
        "agent_id": worker_agent_id,
        "hermes_timeout": body.get("hermes_timeout") or 300,
    })
    worker_results = ((dispatch.get("worker_result") or {}).get("results") or [])
    processed = next((item for item in worker_results if item.get("processed")), worker_results[0] if worker_results else {})
    run_id = processed.get("run_id")
    task_id = dispatch.get("task_id") or processed.get("task_id")
    output_summary = redact_text(processed.get("output_summary") or dispatch.get("error") or "Worker task dispatched.", 1000)
    artifact_id = None
    evidence = {
        "tool_calls": 0,
        "evaluations": 0,
        "runtime_events": 0,
        "audit_logs": 0,
        "artifacts": 0,
        "memories": 0,
        "approvals": 0,
    }
    if run_id and task_id:
        artifact_id = stable_id("art_customer_worker_task", run_id)
        artifact = {
            "artifact_id": artifact_id,
            "task_id": task_id,
            "run_id": run_id,
            "artifact_type": "customer_worker_result",
            "title": f"客户 Worker 交付：{title}",
            "uri": f"run://{run_id}",
            "summary": output_summary,
            "created_at": now_iso(),
        }
        before_artifact, _artifact_outcome = repo_upsert_artifact(conn, artifact)
        runtime_event(conn, "rtc_agent_gateway_local", "customer_worker_task.artifact", "completed" if dispatch.get("ok") else "failed", run_id=run_id, task_id=task_id, agent_id=dispatch.get("agent_id"), output_summary=output_summary, raw_payload_hash=stable_hash({"run_id": run_id, "summary": output_summary}))
        audit(conn, "system", "customer-worker-task", "workflow.customer_worker_task", "artifacts", artifact_id, dict(before_artifact) if before_artifact else None, artifact, {"adapter": adapter, "raw_output_omitted": True})
        memory_id = stable_id("mem_customer_worker_task", run_id)
        memory_text = (
            f"Customer worker task '{title}' produced artifact {artifact_id}. "
            f"Review the summarized result before reusing it as a project pattern: {output_summary}"
        )
        memory_outcome = upsert_memory_candidate(
            conn,
            {
                "memory_id": memory_id,
                "scope": "project",
                "memory_type": "artifact_summary",
                "canonical_text": redact_text(memory_text, 360),
                "source_type": "run_log",
                "source_ref": run_id,
                "project_id": body.get("project_id") or "proj_mvp",
                "task_id": task_id,
                "agent_id": dispatch.get("agent_id"),
                "confidence": 0.72 if dispatch.get("ok") else 0.48,
                "review_status": "candidate",
                "owner_user_id": "usr_founder",
                "ttl_review_due_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).isoformat(),
                "supersedes_memory_id": None,
                "access_tags": json.dumps(["customer-worker", adapter, "review"], ensure_ascii=False),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
            "customer-worker-task",
        )
        runtime_event(conn, "rtc_agent_gateway_local", "customer_worker_task.memory", "completed", run_id=run_id, task_id=task_id, agent_id=dispatch.get("agent_id"), output_summary=f"Memory candidate {memory_id} {memory_outcome}.")
        plan_evidence = ensure_run_plan_evidence_manifest(conn, run_id, reason="customer_worker_delivery_approval")
        if not plan_evidence.get("ok"):
            runtime_event(
                conn,
                "rtc_agent_gateway_local",
                "customer_worker_task.delivery_approval_blocked_missing_plan_evidence",
                "blocked",
                run_id=run_id,
                task_id=task_id,
                agent_id=dispatch.get("agent_id"),
                output_summary="Customer delivery approval blocked until plan_evidence_manifest verifies.",
            )
            audit(conn, "system", "customer-worker-task", "workflow.customer_worker_task.delivery_approval_blocked_missing_plan_evidence", "runs", run_id, None, {"status": "blocked"}, {
                "adapter": adapter,
                "plan_id": plan_evidence.get("plan_id"),
                "manifest_id": plan_evidence.get("manifest_id"),
                "failed_checks": [item.get("id") for item in ((plan_evidence.get("verification") or {}).get("failed_checks") or [])],
                "raw_output_omitted": True,
            })
            conn.commit()
            evidence = {
                "tool_calls": conn.execute("SELECT COUNT(*) c FROM tool_calls WHERE run_id=?", (run_id,)).fetchone()["c"],
                "evaluations": conn.execute("SELECT COUNT(*) c FROM evaluations WHERE run_id=?", (run_id,)).fetchone()["c"],
                "runtime_events": conn.execute("SELECT COUNT(*) c FROM runtime_events WHERE run_id=? OR task_id=?", (run_id, task_id)).fetchone()["c"],
                "audit_logs": conn.execute("SELECT COUNT(*) c FROM audit_logs WHERE entity_id IN (?,?,?,?,?)", (run_id, task_id, artifact_id, memory_id, plan_evidence.get("manifest_id"))).fetchone()["c"],
                "artifacts": conn.execute("SELECT COUNT(*) c FROM artifacts WHERE run_id=?", (run_id,)).fetchone()["c"],
                "memories": conn.execute("SELECT COUNT(*) c FROM memories WHERE source_ref=? OR task_id=?", (run_id, task_id)).fetchone()["c"],
                "approvals": conn.execute("SELECT COUNT(*) c FROM approvals WHERE run_id=? OR task_id=?", (run_id, task_id)).fetchone()["c"],
                "plan_evidence_manifests": conn.execute("SELECT COUNT(*) c FROM plan_evidence_manifests WHERE run_id=?", (run_id,)).fetchone()["c"],
            }
            return {
                "provider": "agentops-worker",
                "workflow": "customer_worker_task",
                "dry_run": False,
                "ok": False,
                "adapter": adapter,
                "task_id": task_id,
                "run_id": run_id,
                "artifact_id": artifact_id,
                "plan_id": plan_evidence.get("plan_id"),
                "plan_evidence_manifest_id": plan_evidence.get("manifest_id"),
                "plan_evidence_status": plan_evidence.get("status"),
                "plan_evidence_pass": False,
                "reason": "verified_plan_evidence_manifest_required",
                "duration_ms": dispatch.get("duration_ms"),
                "output_summary": output_summary,
                "evidence": evidence,
                "plan_evidence": plan_evidence,
                "worker_result": dispatch.get("worker_result"),
                "error": dispatch.get("error") or "Customer delivery approval blocked by plan evidence manifest gate.",
                "token_omitted": True,
            }, 409
        delivery_approval_id = stable_id("ap_customer_worker_delivery", run_id)
        delivery_approval = {
            "approval_id": delivery_approval_id,
            "task_id": task_id,
            "run_id": run_id,
            "tool_call_id": None,
            "requested_by_agent_id": dispatch.get("agent_id"),
            "approver_user_id": body.get("approver_user_id") or "usr_founder",
            "decision": "pending",
            "reason": redact_text(
                body.get("delivery_approval_reason")
                or "Customer delivery acceptance is required before publishing, external upload, or treating this worker result as approved.",
                260,
            ),
            "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=2)).isoformat(),
            "created_at": now_iso(),
            "decided_at": None,
        }
        existing_approval, _approval_outcome = repo_upsert_approval(conn, delivery_approval)
        conn.execute("UPDATE tasks SET status='waiting_approval', updated_at=? WHERE task_id=? AND status='completed'", (now_iso(), task_id))
        runtime_event(conn, "rtc_agent_gateway_local", "customer_worker_task.delivery_approval", "waiting_approval", run_id=run_id, task_id=task_id, agent_id=dispatch.get("agent_id"), output_summary=delivery_approval["reason"])
        audit(conn, "system", "customer-worker-task", "workflow.customer_worker_task.delivery_approval", "approvals", delivery_approval_id, dict(existing_approval) if existing_approval else None, delivery_approval, {"adapter": adapter, "raw_output_omitted": True})
        conn.commit()
        evidence = {
            "tool_calls": conn.execute("SELECT COUNT(*) c FROM tool_calls WHERE run_id=?", (run_id,)).fetchone()["c"],
            "evaluations": conn.execute("SELECT COUNT(*) c FROM evaluations WHERE run_id=?", (run_id,)).fetchone()["c"],
            "runtime_events": conn.execute("SELECT COUNT(*) c FROM runtime_events WHERE run_id=? OR task_id=?", (run_id, task_id)).fetchone()["c"],
            "audit_logs": conn.execute("SELECT COUNT(*) c FROM audit_logs WHERE entity_id IN (?,?,?,?,?,?,?)", (run_id, task_id, artifact_id, memory_id, delivery_approval_id, plan_evidence.get("plan_id"), plan_evidence.get("manifest_id"))).fetchone()["c"],
            "artifacts": conn.execute("SELECT COUNT(*) c FROM artifacts WHERE run_id=?", (run_id,)).fetchone()["c"],
            "memories": conn.execute("SELECT COUNT(*) c FROM memories WHERE source_ref=? OR task_id=?", (run_id, task_id)).fetchone()["c"],
            "approvals": conn.execute("SELECT COUNT(*) c FROM approvals WHERE run_id=? OR task_id=?", (run_id, task_id)).fetchone()["c"],
            "plan_evidence_manifests": conn.execute("SELECT COUNT(*) c FROM plan_evidence_manifests WHERE run_id=?", (run_id,)).fetchone()["c"],
        }
    return {
        "provider": "agentops-worker",
        "workflow": "customer_worker_task",
        "dry_run": False,
        "ok": bool(dispatch.get("ok") and run_id),
        "adapter": adapter,
        "task_id": task_id,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "approval_id": delivery_approval_id if run_id and task_id and artifact_id else None,
        "plan_id": plan_evidence.get("plan_id") if run_id and task_id and artifact_id else processed.get("plan_id"),
        "plan_evidence_manifest_id": plan_evidence.get("manifest_id") if run_id and task_id and artifact_id else processed.get("plan_evidence_manifest_id"),
        "plan_evidence_status": plan_evidence.get("status") if run_id and task_id and artifact_id else processed.get("plan_evidence_status"),
        "plan_evidence_pass": plan_evidence.get("ok") if run_id and task_id and artifact_id else processed.get("plan_evidence_pass"),
        "duration_ms": dispatch.get("duration_ms"),
        "output_summary": output_summary,
        "evidence": evidence,
        "worker_result": dispatch.get("worker_result"),
        "error": dispatch.get("error"),
    }, 201


def run_graph(conn, run_id: str) -> dict | None:
    run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not run:
        return None
    parent = conn.execute("SELECT * FROM runs WHERE run_id=?", (run["parent_run_id"],)).fetchone() if run["parent_run_id"] else None
    children = rows_to_dicts(conn.execute("SELECT * FROM runs WHERE parent_run_id=? ORDER BY created_at", (run_id,)).fetchall())
    siblings = rows_to_dicts(conn.execute("SELECT * FROM runs WHERE delegation_id=? AND run_id<>? ORDER BY created_at", (run["delegation_id"], run_id)).fetchall()) if run["delegation_id"] else []
    return {"run": dict(run), "parent": dict(parent) if parent else None, "children": children, "siblings_by_delegation": siblings}


def agent_performance(conn, agent_id: str) -> dict | None:
    agent = conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
    if not agent:
        return None
    row = conn.execute(
        """SELECT COUNT(*) total_runs,
        SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed_runs,
        SUM(CASE WHEN status IN ('failed','blocked') THEN 1 ELSE 0 END) failures,
        AVG(duration_ms) avg_duration_ms,
        COALESCE(SUM(cost_usd),0) total_cost_usd,
        SUM(CASE WHEN approval_required=1 THEN 1 ELSE 0 END) approval_required_count
        FROM runs WHERE agent_id=?""",
        (agent_id,),
    ).fetchone()
    total = row["total_runs"] or 0
    errors = rows_to_dicts(conn.execute(
        "SELECT error_type, COUNT(*) count FROM runs WHERE agent_id=? AND error_type IS NOT NULL GROUP BY error_type ORDER BY count DESC LIMIT 5",
        (agent_id,),
    ).fetchall())
    recent = rows_to_dicts(conn.execute("SELECT * FROM runs WHERE agent_id=? ORDER BY created_at DESC LIMIT 10", (agent_id,)).fetchall())
    return {
        "agent": dict(agent),
        "total_runs": total,
        "completed_runs": row["completed_runs"] or 0,
        "failures": row["failures"] or 0,
        "success_rate": round(((row["completed_runs"] or 0) / total), 3) if total else 0,
        "avg_duration_ms": int(row["avg_duration_ms"] or 0),
        "total_cost_usd": round(row["total_cost_usd"] or 0, 4),
        "approval_required_count": row["approval_required_count"] or 0,
        "recent_error_types": errors,
        "recent_runs": recent,
    }


def create_sync_event(conn, connector_id, direction, object_type, status, payload=None, internal_object_id=None, external_object_id=None, error_message=None):
    row = {
        "sync_event_id": new_id("syn"),
        "connector_id": connector_id,
        "direction": direction,
        "object_type": object_type,
        "internal_object_id": internal_object_id,
        "external_object_id": external_object_id,
        "status": status,
        "error_message": redact_text(error_message, 240) if error_message else None,
        "payload_hash": stable_hash(payload or {}),
        "created_at": now_iso(),
    }
    conn.execute(
        """INSERT INTO sync_events(sync_event_id,connector_id,direction,object_type,internal_object_id,external_object_id,status,error_message,payload_hash,created_at)
        VALUES(:sync_event_id,:connector_id,:direction,:object_type,:internal_object_id,:external_object_id,:status,:error_message,:payload_hash,:created_at)""",
        row,
    )
    return row


def notion_status_payload(conn) -> dict:
    cfg = notion_config()
    last_sync = conn.execute("SELECT created_at FROM sync_events WHERE connector_id LIKE 'conn_notion_%' ORDER BY created_at DESC LIMIT 1").fetchone()
    last_error = conn.execute("SELECT error_message FROM sync_events WHERE connector_id LIKE 'conn_notion_%' AND error_message IS NOT NULL ORDER BY created_at DESC LIMIT 1").fetchone()
    connectors = rows_to_dicts(conn.execute("SELECT * FROM connectors WHERE provider='notion' ORDER BY connector_id").fetchall())
    return {
        "provider": "notion",
        "configured": cfg["configured"],
        "has_token": cfg["has_token"],
        "has_parent_page_id": bool(cfg["parent_page_id"]),
        "has_database_id": bool(cfg["database_id"]),
        "workspace_private_export": cfg["workspace_private_export"],
        "export_mode": cfg["export_mode"],
        "dry_run_default": True,
        "writeback_allowed": False,
        "last_sync": last_sync["created_at"] if last_sync else None,
        "last_error": last_error["error_message"] if last_error else None,
        "notion_version": cfg["notion_version"],
        "connectors": connectors,
    }


def notion_preview(conn) -> dict:
    markdown = build_notion_report(conn)
    tasks = rows_to_dicts(conn.execute("SELECT task_id,title,status,priority,risk_level,owner_agent_id,updated_at FROM tasks ORDER BY updated_at DESC LIMIT 20").fetchall())
    memories = rows_to_dicts(conn.execute("SELECT memory_id,scope,memory_type,canonical_text,confidence,review_status,source_ref FROM memories WHERE review_status IN ('candidate','approved') ORDER BY updated_at DESC LIMIT 20").fetchall())
    return {
        "provider": "notion",
        "status": notion_status_payload(conn),
        "report": {"title": "AgentOps MIS 项目汇报工作台", "markdown": markdown, "block_count": len(text_blocks(markdown))},
        "tasks": tasks,
        "memory_candidates": memories,
        "write_behavior": "preview only; no external write",
    }


def notion_dry_run_export(conn, actor="notion-dry-run") -> dict:
    preview = notion_preview(conn)
    event = create_sync_event(conn, "conn_notion_templates", "outbound", "report", "dry_run", preview)
    audit(conn, "system", actor, "notion.dry_run_export", "sync_events", event["sync_event_id"], None, {"status": "dry_run"}, {"payload_hash": event["payload_hash"]})
    conn.commit()
    return {"provider": "notion", "dry_run": True, "created": False, "sync_event_id": event["sync_event_id"], "preview": preview}


def notion_export_confirmed(conn, body: dict) -> tuple[dict, int]:
    confirm = bool(body.get("confirm_export"))
    cfg = notion_config()
    markdown = build_notion_report(conn)
    if confirm and not commercial_capability_enabled("notion_confirmed_export"):
        return commercial_entitlement_block(conn, "notion_confirmed_export", "notion.export_confirmed", "notion-export"), 403
    if not confirm or not cfg["configured"]:
        event = create_sync_event(conn, "conn_notion_templates", "outbound", "report", "dry_run", {"confirm_export": confirm, "configured": cfg["configured"]})
        audit(conn, "system", "notion-export", "notion.export.skipped", "sync_events", event["sync_event_id"], None, {"dry_run": True}, {"confirm_export": confirm, "configured": cfg["configured"]})
        conn.commit()
        return {"provider": "notion", "dry_run": True, "created": False, "requires_confirm_export": not confirm, "configured": cfg["configured"], "sync_event_id": event["sync_event_id"], "markdown": markdown, "block_count": len(text_blocks(markdown))}, 201
    try:
        result = post_notion_page(markdown, body.get("title", "AgentOps MIS 项目汇报工作台"))
        event = create_sync_event(conn, "conn_notion_templates", "outbound", "report", "created", result, external_object_id=result.get("notion_page_id"))
        if result.get("notion_page_id"):
            conn.execute(
                "INSERT INTO external_object_links(link_id,internal_object_type,internal_object_id,external_provider,external_object_type,external_object_id,external_url,sync_direction,sync_status,last_synced_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (stable_id("lnk", "report", event["sync_event_id"]), "report", "agentops_mis_project_report", "notion", "page", result.get("notion_page_id"), result.get("url"), "outbound", "created", now_iso(), now_iso()),
        )
        audit(conn, "user", "usr_founder", "notion.export_confirmed", "integrations", "notion", None, result, {"sync_event_id": event["sync_event_id"]})
        conn.commit()
        return {**result, "sync_event_id": event["sync_event_id"]}, 201
    except Exception as exc:
        err = redact_text(str(exc), 300)
        event = create_sync_event(conn, "conn_notion_templates", "outbound", "report", "failed", {"export_mode": cfg["export_mode"]}, error_message=err)
        audit(conn, "system", "notion-export", "notion.export_failed", "integrations", "notion", None, {"created": False}, {"error": err, "sync_event_id": event["sync_event_id"]})
        conn.commit()
        return {"provider": "notion", "created": False, "configured": cfg["configured"], "export_mode": cfg["export_mode"], "error": err, "sync_event_id": event["sync_event_id"]}, 200


def notion_import_preview(conn, body: dict) -> dict:
    base_id = body.get("base_id") or "base_notion_tasks"
    mappings = rows_to_dicts(conn.execute("SELECT * FROM field_mappings WHERE base_id=? ORDER BY internal_object_type, internal_field", (base_id,)).fetchall())
    if not mappings:
        mappings = [
            {"internal_object_type": "task", "internal_field": "title", "external_field": "Name", "required": 1},
            {"internal_object_type": "task", "internal_field": "status", "external_field": "Status", "required": 1},
            {"internal_object_type": "memory", "internal_field": "canonical_text", "external_field": "Content", "required": 1},
            {"internal_object_type": "memory", "internal_field": "review_status", "external_field": "Review", "required": 1},
        ]
    return {"provider": "notion", "base_id": base_id, "write_database": False, "field_mapping_suggestions": mappings, "notes": ["Preview only. No Notion content is read or written.", "Use external_object_links for future reconciliation."]}


def notion_sync_memory_candidates(conn) -> dict:
    rows = rows_to_dicts(conn.execute("SELECT * FROM memories WHERE review_status IN ('candidate','approved') ORDER BY updated_at DESC LIMIT 50").fetchall())
    payloads = [
        {
            "parent": "[configured notion target]",
            "properties": {"Name": {"title": [{"text": {"content": f"{row['memory_type']}: {row['memory_id']}"}}]}, "Review": {"select": {"name": row["review_status"]}}},
            "children": [{"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": redact_text(row["canonical_text"], 500)}}]}}],
        }
        for row in rows
    ]
    event = create_sync_event(conn, "conn_notion_memory", "outbound", "memory", "dry_run", payloads)
    audit(conn, "system", "notion-memory-sync", "notion.sync_memory_candidates.dry_run", "sync_events", event["sync_event_id"], None, {"count": len(payloads)}, {"payload_hash": event["payload_hash"]})
    conn.commit()
    return {"provider": "notion", "dry_run": True, "count": len(payloads), "sync_event_id": event["sync_event_id"], "payload_preview": payloads[:5]}


def notion_sync_tasks(conn) -> dict:
    rows = rows_to_dicts(conn.execute("SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 50").fetchall())
    payloads = [
        {
            "parent": "[configured notion database/page]",
            "properties": {
                "Name": {"title": [{"text": {"content": row["title"]}}]},
                "Status": {"select": {"name": row["status"]}},
                "Risk": {"select": {"name": row["risk_level"]}},
            },
        }
        for row in rows
    ]
    event = create_sync_event(conn, "conn_notion_tasks", "outbound", "task", "dry_run", payloads)
    audit(conn, "system", "notion-task-sync", "notion.sync_tasks.dry_run", "sync_events", event["sync_event_id"], None, {"count": len(payloads)}, {"payload_hash": event["payload_hash"]})
    conn.commit()
    return {"provider": "notion", "dry_run": True, "count": len(payloads), "sync_event_id": event["sync_event_id"], "payload_preview": payloads[:5]}


def migration_preview(conn, body: dict) -> dict:
    template_id = body.get("template_id") or "tpl_ai_software_team"
    from_base_id = body.get("from_base_id") or "base_local_tasks"
    to_base_id = body.get("to_base_id") or "base_notion_tasks"
    from_base = conn.execute("SELECT * FROM bases WHERE base_id=?", (from_base_id,)).fetchone()
    to_base = conn.execute("SELECT * FROM bases WHERE base_id=?", (to_base_id,)).fetchone()
    template = conn.execute("SELECT * FROM template_packages WHERE template_id=?", (template_id,)).fetchone()
    preview = {
        "template_id": template_id,
        "from_base": dict(from_base) if from_base else None,
        "to_base": dict(to_base) if to_base else None,
        "template": dict(template) if template else None,
        "migratable_objects": ["tasks.title", "tasks.status", "tasks.priority", "tasks.risk_level", "memories.canonical_text", "memories.review_status"],
        "non_migratable_objects": ["runs.raw ledger", "tool_calls.normalized_args_json", "approvals.authority", "audit_logs.tamper_chain_hash"],
        "field_downgrades": [
            {"field": "risk_level", "strategy": "Notion select; Agent-MIS remains authority."},
            {"field": "audit_logs", "strategy": "Export summary/link only; canonical audit stays local."},
            {"field": "tool_calls", "strategy": "External base receives count/summary, not raw args."},
        ],
        "permission_changes": ["External base permissions are not equivalent to Agent-MIS approval authority."],
        "requires_human_confirmation": ["writeback_allowed", "external credential scope", "field mapping review"],
        "rollback": ["Keep Agent-MIS local base canonical.", "Delete external links created in this preview batch.", "Replay sync_events if needed."],
    }
    conn.execute(
        "INSERT INTO migration_runs(migration_run_id,template_id,from_base_id,to_base_id,status,preview_json,result_json,created_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (new_id("mig"), template_id, from_base_id, to_base_id, "preview", json.dumps(preview, ensure_ascii=False), "{}", now_iso(), None),
    )
    audit(conn, "system", "migration-preview", "migration.preview", "template_packages", template_id, None, {"status": "preview"}, {"from_base_id": from_base_id, "to_base_id": to_base_id})
    conn.commit()
    return preview


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentOpsMIS/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, text, content_type="text/plain; charset=utf-8", status=200):
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        try:
            if path.startswith("/api/"):
                return self.handle_get_api(path, qs)
            return self.serve_static(path)
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = parse_json_body(self)
        try:
            return self.handle_post_api(parsed.path, body)
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        body = parse_json_body(self)
        try:
            return self.handle_patch_api(parsed.path, body)
        except Exception as e:
            self.send_json({"error": str(e)}, status=500)

    def serve_static(self, path):
        if path in ("/", ""):
            path = "/dashboard"
        if path.startswith("/static/"):
            file_path = STATIC_DIR / path.replace("/static/", "", 1)
        else:
            file_path = STATIC_DIR / "index.html"
        if not file_path.exists() or not file_path.is_file():
            return self.send_text("Not found", status=404)
        content_type = "text/html; charset=utf-8"
        if file_path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif file_path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif file_path.suffix == ".json":
            content_type = "application/json; charset=utf-8"
        self.send_text(file_path.read_text(encoding="utf-8"), content_type=content_type)

    def handle_get_api(self, path, qs):
        with db() as conn:
            if path == "/api/agent-gateway/status":
                payload, status = agent_gateway_status(conn, self.headers)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/local/readiness":
                payload = local_readiness(conn, self.headers)
                conn.commit()
                return self.send_json(payload)
            if path == "/api/security/production-readiness":
                payload = security_production_readiness(conn, self.headers)
                conn.rollback()
                return self.send_json(payload)
            if path == "/api/commercial/entitlements":
                payload = entitlement_status(self.headers)
                conn.rollback()
                return self.send_json(payload)
            if path == "/api/demo/readiness":
                payload = demo_readiness(conn, self.headers)
                conn.rollback()
                return self.send_json(payload)
            if path == "/api/commander/project-board":
                payload = commander_project_board(conn, self.headers)
                conn.rollback()
                return self.send_json(payload)
            if path == "/api/commander/work-packages":
                payload = commander_work_packages_readback(conn, qs, self.headers)
                conn.rollback()
                return self.send_json(payload)
            if path == "/api/commander/integration-inbox":
                payload = commander_integration_inbox(conn, self.headers, qs)
                conn.rollback()
                return self.send_json(payload)
            if path == "/api/agent-gateway/enrollments":
                auth_error = agent_gateway_admin_auth_error(self.headers)
                if auth_error:
                    return self.send_json(auth_error, 401)
                workspace_id = optional_request_workspace(self.headers, qs)
                return self.send_json({
                    "enrollments": agent_gateway_enrollment_rows(conn, workspace_id),
                    "workspace_id": workspace_id,
                    "valid_scopes": sorted(VALID_AGENT_GATEWAY_SCOPES),
                    "token_omitted": True,
                })
            if path == "/api/agent-gateway/sessions":
                auth_error = agent_gateway_admin_auth_error(self.headers)
                if auth_error:
                    return self.send_json(auth_error, 401)
                workspace_id = optional_request_workspace(self.headers, qs)
                return self.send_json({
                    "sessions": agent_gateway_session_rows(conn, workspace_id),
                    "workspace_id": workspace_id,
                    "valid_scopes": sorted(VALID_AGENT_GATEWAY_SCOPES),
                    "token_omitted": True,
                })
            if path == "/api/agent-gateway/tasks/pull":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                query = dict(qs)
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_workspace = requested_workspace_from_qs(query, auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot pull tasks from another workspace."}, 403)
                    requested_agent = (query.get("agent_id") or [auth_ctx["agent_id"]])[0]
                    if requested_agent and requested_agent != auth_ctx["agent_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot pull tasks as another agent."}, 403)
                    query["agent_id"] = [auth_ctx["agent_id"]]
                    query["workspace_id"] = [auth_ctx["workspace_id"]]
                else:
                    if auth_ctx and auth_ctx.get("agent_id") and not query.get("agent_id"):
                        query["agent_id"] = [auth_ctx["agent_id"]]
                    if auth_ctx and auth_ctx.get("workspace_id") and not query.get("workspace_id"):
                        query["workspace_id"] = [auth_ctx["workspace_id"]]
                payload, status = agent_gateway_pull_tasks(conn, query, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-gateway/tasks":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                query = dict(qs)
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_workspace = requested_workspace_from_qs(query, auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot list tasks from another workspace."}, 403)
                    query["workspace_id"] = [auth_ctx["workspace_id"]]
                payload, status = agent_gateway_list_tasks(conn, query, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path.startswith("/api/agent-gateway/tasks/") and "/" not in path[len("/api/agent-gateway/tasks/"):].strip("/"):
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                task_id = path.split("/")[-1]
                payload, status = agent_gateway_get_task(conn, task_id, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-gateway/runs":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                query = dict(qs)
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_workspace = requested_workspace_from_qs(query, auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot list runs from another workspace."}, 403)
                    query["workspace_id"] = [auth_ctx["workspace_id"]]
                payload, status = agent_gateway_list_runs(conn, query, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path.startswith("/api/agent-gateway/runs/") and path.endswith("/graph"):
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                run_id = path.split("/")[-2]
                payload, status = agent_gateway_get_run_graph(conn, run_id, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path.startswith("/api/agent-gateway/runs/") and "/" not in path[len("/api/agent-gateway/runs/"):].strip("/"):
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                run_id = path.split("/")[-1]
                payload, status = agent_gateway_get_run(conn, run_id, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-gateway/artifacts":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                query = dict(qs)
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_workspace = requested_workspace_from_qs(query, auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot list artifacts from another workspace."}, 403)
                    query["workspace_id"] = [auth_ctx["workspace_id"]]
                payload, status = agent_gateway_list_artifacts(conn, query, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-gateway/knowledge/search":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "knowledge:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                payload, status = knowledge_search(conn, dict(qs), self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-gateway/agent-plans":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "agent_plans:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                query = dict(qs)
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_workspace = requested_workspace_from_qs(query, auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot list agent plans from another workspace."}, 403)
                    query["workspace_id"] = [auth_ctx["workspace_id"]]
                payload, status = list_agent_plans(conn, query, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path.startswith("/api/agent-gateway/agent-plans/"):
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "agent_plans:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                if path.endswith("/verify"):
                    plan_id = path.split("/")[-2]
                    payload, status = verify_agent_plan(conn, plan_id, self.headers, auth_ctx)
                else:
                    plan_id = path.split("/")[-1]
                    payload, status = get_agent_plan(conn, plan_id, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-gateway/plan-evidence-manifests":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "plan_evidence:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                query = dict(qs)
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_workspace = requested_workspace_from_qs(query, auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot list plan evidence manifests from another workspace."}, 403)
                    query["workspace_id"] = [auth_ctx["workspace_id"]]
                payload, status = list_plan_evidence_manifests(conn, query, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path.startswith("/api/agent-gateway/plan-evidence-manifests/"):
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "plan_evidence:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                if path.endswith("/verify"):
                    manifest_id = path.split("/")[-2]
                    payload, status = verify_plan_evidence_manifest(conn, manifest_id, self.headers, auth_ctx)
                else:
                    manifest_id = path.split("/")[-1]
                    payload, status = get_plan_evidence_manifest(conn, manifest_id, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-gateway/approvals":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                query = dict(qs)
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_workspace = requested_workspace_from_qs(query, auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot list approvals from another workspace."}, 403)
                    query["workspace_id"] = [auth_ctx["workspace_id"]]
                payload, status = agent_gateway_list_approvals(conn, query, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-gateway/memories":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                query = dict(qs)
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_workspace = requested_workspace_from_qs(query, auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot list memories from another workspace."}, 403)
                    query["workspace_id"] = [auth_ctx["workspace_id"]]
                payload, status = agent_gateway_list_memories(conn, query, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-gateway/review/queue":
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, "tasks:read")
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                query = dict(qs)
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_workspace = requested_workspace_from_qs(query, auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot read review queue from another workspace."}, 403)
                    query["workspace_id"] = [auth_ctx["workspace_id"]]
                payload, status = agent_gateway_review_queue(conn, query, self.headers, auth_ctx)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agents":
                rows = conn.execute("SELECT * FROM agents ORDER BY created_at DESC").fetchall()
                return self.send_json(rows_to_dicts(rows))
            if path.startswith("/api/agents/") and path.endswith("/performance"):
                agent_id = path.split("/")[-2]
                data = agent_performance(conn, agent_id)
                if not data:
                    return self.send_json({"error": "not found"}, 404)
                return self.send_json(data)
            if path.startswith("/api/agents/"):
                agent_id = path.split("/")[-1]
                agent = conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
                if not agent:
                    return self.send_json({"error": "not found"}, 404)
                runs = rows_to_dicts(conn.execute("SELECT * FROM runs WHERE agent_id=? ORDER BY created_at DESC", (agent_id,)).fetchall())
                tasks = rows_to_dicts(conn.execute("SELECT * FROM tasks WHERE owner_agent_id=? ORDER BY created_at DESC", (agent_id,)).fetchall())
                return self.send_json({"agent": dict(agent), "runs": runs, "tasks": tasks})
            if path == "/api/tasks":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(repo_list_workspace_tasks(conn, workspace_id)))
            if path.startswith("/api/tasks/") and "/" not in path[len("/api/tasks/"):].strip("/"):
                workspace_id = request_workspace(self.headers, qs)
                task_id = path.split("/")[-1]
                task = repo_get_workspace_task(conn, workspace_id, task_id)
                if not task:
                    return self.send_json(workspace_hidden("task", task_id), 404)
                return self.send_json(repo_task_detail(conn, task))
            if path == "/api/runs":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(repo_list_workspace_runs(
                    conn,
                    workspace_id,
                    task_id=(qs.get("task_id") or [None])[0],
                    agent_id=(qs.get("agent_id") or [None])[0],
                )))
            if path == "/api/runs/export":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(repo_list_workspace_runs(conn, workspace_id)))
            if path.startswith("/api/runs/") and path.endswith("/graph"):
                workspace_id = request_workspace(self.headers, qs)
                run_id = path.split("/")[-2]
                run = repo_get_workspace_run(conn, workspace_id, run_id)
                data = run_graph(conn, run_id) if run else None
                if not data:
                    return self.send_json(workspace_hidden("run", run_id), 404)
                return self.send_json(data)
            if path.startswith("/api/runs/"):
                workspace_id = request_workspace(self.headers, qs)
                run_id = path.split("/")[-1]
                run = repo_get_workspace_run(conn, workspace_id, run_id)
                if not run:
                    return self.send_json(workspace_hidden("run", run_id), 404)
                return self.send_json(repo_run_detail(conn, run))
            if path == "/api/tool-calls":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(conn.execute(
                    """SELECT tc.* FROM tool_calls tc
                    JOIN runs r ON r.run_id=tc.run_id
                    WHERE COALESCE(r.workspace_id,'local-demo')=?
                    ORDER BY tc.created_at DESC""",
                    (workspace_id,),
                ).fetchall()))
            if path == "/api/knowledge/search":
                payload, status = knowledge_search(conn, dict(qs), self.headers)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agent-plans":
                payload, status = list_agent_plans(conn, dict(qs), self.headers)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/approvals":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(repo_list_workspace_approvals(conn, workspace_id)))
            if path == "/api/memories":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(repo_list_workspace_memories(conn, workspace_id)))
            if path == "/api/memories/export":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(repo_list_workspace_memories(conn, workspace_id)))
            if path == "/api/evaluations":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(repo_list_workspace_evaluations(conn, workspace_id)))
            if path == "/api/artifacts":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(repo_list_workspace_artifacts(conn, workspace_id)))
            if path == "/api/audit":
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json(rows_to_dicts(repo_list_workspace_audit(conn, workspace_id)))
            if path == "/api/review/queue":
                limit = int((qs.get("limit") or ["20"])[0])
                return self.send_json(human_review_queue(conn, limit))
            if path == "/api/dashboard/metrics":
                return self.send_json(dashboard_metrics(conn))
            if path == "/api/runtime-connectors":
                refresh_runtime_connectors(conn)
                conn.commit()
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM runtime_connectors ORDER BY provider, connector_type, profile_name").fetchall()))
            if path == "/api/runtime-events":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM runtime_events ORDER BY created_at DESC LIMIT 200").fetchall()))
            if path == "/api/workers/status":
                return self.send_json(worker_status(conn))
            if path == "/api/workers/fleet":
                return self.send_json(worker_fleet_view(conn))
            if path == "/api/workers/adapter-readiness":
                payload = worker_adapter_readiness(conn)
                conn.commit()
                return self.send_json(payload)
            if path == "/api/workers/stuck-tasks":
                threshold = int((qs.get("threshold_sec") or ["900"])[0])
                limit = int((qs.get("limit") or ["25"])[0])
                return self.send_json({"provider": "agentops-worker", "threshold_sec": max(threshold, 30), "stuck_tasks": worker_stuck_tasks(conn, threshold, limit), "token_omitted": True})
            if path == "/api/workers/fleet/hygiene":
                threshold = int((qs.get("threshold_sec") or ["900"])[0])
                enrollment_age = int((qs.get("enrollment_age_sec") or ["900"])[0])
                limit = int((qs.get("limit") or ["25"])[0])
                payload, status = worker_fleet_hygiene(conn, {
                    "threshold_sec": threshold,
                    "enrollment_age_sec": enrollment_age,
                    "limit": limit,
                }, apply=False)
                return self.send_json(payload, status)
            if path == "/api/workers/local/logs":
                adapter = coerce_choice((qs.get("adapter") or ["mock"])[0], {"mock", "hermes", "openclaw"}, "mock")
                return self.send_json({"provider": "agentops-worker", "daemon": read_worker_daemon(adapter, include_log=True)})
            if path == "/api/workflows/jobs":
                limit = min(int((qs.get("limit") or ["50"])[0]), 200)
                workspace_id = request_workspace(self.headers, qs)
                rows = repo_list_workspace_workflow_jobs(conn, workspace_id, limit)
                return self.send_json({"jobs": [workflow_job_public(row) for row in rows], "workspace_id": workspace_id, "token_omitted": True})
            if path == "/api/workflows/jobs/stuck":
                threshold = int((qs.get("threshold_sec") or ["900"])[0])
                limit = int((qs.get("limit") or ["25"])[0])
                workspace_id = request_workspace(self.headers, qs)
                return self.send_json({
                    "provider": "agentops-workflow-job",
                    "workspace_id": workspace_id,
                    "threshold_sec": max(threshold, 30),
                    "stuck_jobs": repo_list_workspace_stuck_workflow_jobs(conn, workspace_id, threshold, limit),
                    "token_omitted": True,
                })
            if path.startswith("/api/workflows/jobs/"):
                job_id = path.split("/")[-1]
                workspace_id = request_workspace(self.headers, qs)
                row = repo_get_workspace_workflow_job(conn, workspace_id, job_id)
                if not row:
                    return self.send_json({"error": "not found", "job_id": job_id}, 404)
                return self.send_json({"job": workflow_job_public(row), "workspace_id": workspace_id, "token_omitted": True})
            if path == "/api/bases":
                bases = rows_to_dicts(conn.execute("SELECT * FROM bases ORDER BY provider, category, display_name").fetchall())
                capabilities = rows_to_dicts(conn.execute("SELECT * FROM base_capabilities ORDER BY base_id").fetchall())
                return self.send_json({"bases": bases, "capabilities": capabilities})
            if path == "/api/connectors":
                connectors = rows_to_dicts(conn.execute("SELECT * FROM connectors ORDER BY provider, connector_id").fetchall())
                scopes = rows_to_dicts(conn.execute("SELECT * FROM connector_scopes ORDER BY connector_id, scope_name").fetchall())
                return self.send_json({"connectors": connectors, "scopes": scopes})
            if path == "/api/external-links":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM external_object_links ORDER BY created_at DESC LIMIT 200").fetchall()))
            if path == "/api/sync-events":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM sync_events ORDER BY created_at DESC LIMIT 200").fetchall()))
            if path == "/api/template-packages":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM template_packages ORDER BY scenario, name").fetchall()))
            if path == "/api/template-bindings":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM template_bindings ORDER BY template_id, base_id").fetchall()))
            if path == "/api/workflows/customer-task-templates":
                return self.send_json({"templates": customer_task_templates(), "safe_defaults": {"raw_documents_stored": False, "credentials_stored": False, "external_upload_requires_approval": True}})
            if path == "/api/workflows/customer-delivery-board":
                limit = int((qs.get("limit") or ["12"])[0])
                return self.send_json(customer_delivery_board(conn, limit))
            if path == "/api/workflows/hermes-openclaw-loop":
                limit = int((qs.get("limit") or ["10"])[0])
                loop_id = (qs.get("loop_id") or [""])[0]
                return self.send_json(hermes_openclaw_loop_readback(conn, loop_id, limit))
            if path == "/api/workflows/customer-projects":
                limit = int((qs.get("limit") or ["25"])[0])
                return self.send_json(customer_projects_index(conn, limit))
            if path.startswith("/api/workflows/customer-projects/") and path.endswith("/report"):
                project_id = path.split("/")[-2]
                payload, status = customer_project_report(conn, project_id)
                return self.send_json(payload, status)
            if path == "/api/integrations/openclaw/status":
                return self.send_json(openclaw_status())
            if path == "/api/integrations/hermes/status":
                return self.send_json(hermes_status())
            if path == "/api/integrations/hermes/models":
                return self.send_json(hermes_models(conn))
            if path == "/api/integrations/dify/status":
                payload = dify_status(conn)
                conn.commit()
                return self.send_json(payload)
            if path == "/api/integrations/notion/status":
                return self.send_json(notion_status_payload(conn))
            if path == "/api/integrations/notion/export-preview":
                markdown = build_notion_report(conn)
                return self.send_json({
                    "provider": "notion",
                    "configured": notion_config()["configured"],
                    "title": "AgentOps MIS 项目汇报工作台",
                    "markdown": markdown,
                    "block_count": len(text_blocks(markdown)),
                })
        return self.send_json({"error": "unknown endpoint"}, 404)

    def handle_post_api(self, path, body):
        with db() as conn:
            if path.startswith("/api/agent-gateway/"):
                if path == "/api/agent-gateway/enrollment/policy-preview":
                    payload, status = agent_gateway_enrollment_policy_preview(body)
                    return self.send_json(payload, status)
                if path == "/api/agent-gateway/enrollment/request":
                    payload, status = agent_gateway_request_enrollment(conn, body)
                    conn.commit()
                    return self.send_json(payload, status)
                if path == "/api/agent-gateway/session/create":
                    payload, status = agent_gateway_create_session(conn, self.headers, body)
                    conn.commit()
                    return self.send_json(payload, status)
                if path == "/api/agent-gateway/session/revoke":
                    auth_error = agent_gateway_admin_auth_error(self.headers)
                    if auth_error:
                        return self.send_json(auth_error, 401)
                    payload, status = agent_gateway_revoke_session(conn, body)
                    conn.commit()
                    return self.send_json(payload, status)
                if path == "/api/agent-gateway/enrollment/issue-approved":
                    auth_error = agent_gateway_admin_auth_error(self.headers)
                    if auth_error:
                        return self.send_json(auth_error, 401)
                    payload, status = agent_gateway_issue_approved_enrollment(conn, body)
                    conn.commit()
                    return self.send_json(payload, status)
                if path == "/api/agent-gateway/enrollment/create":
                    auth_error = agent_gateway_admin_auth_error(self.headers)
                    if auth_error:
                        return self.send_json(auth_error, 401)
                    payload, status = agent_gateway_create_enrollment(conn, body)
                    conn.commit()
                    return self.send_json(payload, status)
                if path == "/api/agent-gateway/enrollment/revoke":
                    auth_error = agent_gateway_admin_auth_error(self.headers)
                    if auth_error:
                        return self.send_json(auth_error, 401)
                    payload, status = agent_gateway_revoke_enrollment(conn, body)
                    conn.commit()
                    return self.send_json(payload, status)
                if path == "/api/agent-gateway/enrollment/rotate":
                    auth_error = agent_gateway_admin_auth_error(self.headers)
                    if auth_error:
                        return self.send_json(auth_error, 401)
                    payload, status = agent_gateway_rotate_enrollment(conn, body)
                    conn.commit()
                    return self.send_json(payload, status)
                scope_by_path = {
                    "/api/agent-gateway/register": "agents:write",
                    "/api/agent-gateway/heartbeat": "agents:heartbeat",
                    "/api/agent-gateway/tasks": "tasks:create",
                    "/api/agent-gateway/runs/start": "runs:write",
                    "/api/agent-gateway/tool-calls": "toolcalls:write",
                    "/api/agent-gateway/artifacts": "artifacts:write",
                    "/api/agent-gateway/knowledge/index": "knowledge:write",
                    "/api/agent-gateway/agent-plans": "agent_plans:write",
                    "/api/agent-gateway/plan-evidence-manifests": "plan_evidence:write",
                    "/api/agent-gateway/approvals/request": "approvals:request",
                    "/api/agent-gateway/memories/propose": "memories:propose",
                    "/api/agent-gateway/evaluations/submit": "evaluations:submit",
                    "/api/agent-gateway/audit": "audit:write",
                }
                required_scope = scope_by_path.get(path)
                if path.startswith("/api/agent-gateway/tasks/") and path.endswith("/claim"):
                    required_scope = "tasks:claim"
                elif path.startswith("/api/agent-gateway/runs/") and path.endswith("/heartbeat"):
                    required_scope = "runs:write"
                auth_ctx, auth_error = agent_gateway_auth_context(conn, self.headers, required_scope)
                if auth_error:
                    return self.send_json(auth_error, agent_gateway_error_status(auth_error))
                if agent_gateway_is_bound_auth(auth_ctx):
                    requested_header_workspace = normalize_workspace_id(self.headers.get("X-AgentOps-Workspace-Id") or auth_ctx["workspace_id"])
                    if requested_header_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot use another workspace header."}, 403)
                    requested_agent = body.get("agent_id") or body.get("requested_by_agent_id")
                    if path == "/api/agent-gateway/tasks":
                        requested_agent = body.get("owner_agent_id") or requested_agent
                    if requested_agent and requested_agent != auth_ctx["agent_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot act as another agent."}, 403)
                    requested_workspace = normalize_workspace_id(body.get("workspace_id") or auth_ctx["workspace_id"])
                    if requested_workspace != auth_ctx["workspace_id"]:
                        return self.send_json({"error": "forbidden", "message": "Agent token cannot act in another workspace."}, 403)
                    body["agent_id"] = auth_ctx["agent_id"]
                    body["workspace_id"] = auth_ctx["workspace_id"]
                    if path == "/api/agent-gateway/tasks":
                        body["owner_agent_id"] = auth_ctx["agent_id"]
                    body["_auth_token_id"] = auth_ctx.get("token_id")
                    body["_auth_session_id"] = auth_ctx.get("session_id")
                if path == "/api/agent-gateway/register":
                    payload, status = agent_gateway_register(conn, body)
                elif path == "/api/agent-gateway/heartbeat":
                    payload, status = agent_gateway_heartbeat(conn, body)
                elif path == "/api/agent-gateway/tasks":
                    body["source"] = "agent-gateway"
                    payload, status = create_task_api(conn, body)
                elif path.startswith("/api/agent-gateway/tasks/") and path.endswith("/claim"):
                    task_id = path.split("/")[-2]
                    payload, status = agent_gateway_claim_task(conn, task_id, body)
                elif path == "/api/agent-gateway/runs/start":
                    payload, status = agent_gateway_start_run(conn, body)
                elif path.startswith("/api/agent-gateway/runs/") and path.endswith("/heartbeat"):
                    run_id = path.split("/")[-2]
                    payload, status = agent_gateway_run_heartbeat(conn, run_id, body)
                elif path == "/api/agent-gateway/tool-calls":
                    payload, status = agent_gateway_record_tool_call(conn, body)
                elif path == "/api/agent-gateway/artifacts":
                    payload, status = agent_gateway_record_artifact(conn, body)
                elif path == "/api/agent-gateway/knowledge/index":
                    payload = sync_knowledge_index(conn, rebuild=bool(body.get("rebuild")))
                    audit(conn, "agent", (auth_ctx or {}).get("agent_id") or "knowledge-index", "agent_gateway.knowledge_index", "knowledge_documents", "index", None, {"operation": "knowledge_index", **payload}, {"raw_content_omitted": True})
                    status = 200
                    payload = {"provider": "agentops-knowledge", "operation": "knowledge_index", **payload, "token_omitted": True}
                elif path == "/api/agent-gateway/agent-plans":
                    payload, status = agent_gateway_create_agent_plan(conn, body)
                elif path == "/api/agent-gateway/plan-evidence-manifests":
                    payload, status = agent_gateway_create_plan_evidence_manifest(conn, body)
                elif path == "/api/agent-gateway/approvals/request":
                    payload, status = agent_gateway_request_approval(conn, body)
                elif path == "/api/agent-gateway/memories/propose":
                    payload, status = agent_gateway_memory_propose(conn, body)
                elif path == "/api/agent-gateway/evaluations/submit":
                    payload, status = agent_gateway_eval_submit(conn, body)
                elif path == "/api/agent-gateway/audit":
                    payload, status = agent_gateway_emit_audit(conn, body)
                else:
                    return self.send_json({"error": "unknown agent gateway endpoint"}, 404)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/knowledge/index":
                payload = sync_knowledge_index(conn, rebuild=bool(body.get("rebuild")))
                conn.commit()
                return self.send_json({"provider": "agentops-knowledge", "operation": "knowledge_index", **payload, "token_omitted": True}, 200)
            if path == "/api/commander/work-packages/plan":
                payload, status = commander_plan_work_packages(conn, body, self.headers)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/agents":
                agent_id = body.get("agent_id") or new_id("agt")
                now = now_iso()
                row = {
                    "agent_id": agent_id,
                    "name": body.get("name", "New Agent"),
                    "role": body.get("role", "Worker"),
                    "description": body.get("description", ""),
                    "runtime_type": body.get("runtime_type", "mock"),
                    "model_provider": body.get("model_provider", "mock-provider"),
                    "model_name": body.get("model_name", "mock-model"),
                    "status": body.get("status", "idle"),
                    "permission_level": body.get("permission_level", "standard"),
                    "allowed_tools": json.dumps(body.get("allowed_tools", ["browser.search"]), ensure_ascii=False),
                    "budget_limit_usd": float(body.get("budget_limit_usd", 5.0)),
                    "owner_user_id": body.get("owner_user_id", "usr_founder"),
                    "created_at": now,
                    "updated_at": now,
                }
                conn.execute("""INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
                    VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""", row)
                audit(conn, "user", "usr_founder", "agent.create", "agents", agent_id, None, row, {})
                conn.commit()
                return self.send_json(row, 201)
            if path == "/api/tasks":
                payload, status = create_task_api(conn, body)
                conn.commit()
                return self.send_json(payload, status)
            if path.startswith("/api/runtime-connectors/") and path.endswith("/trust"):
                connector_id = path.split("/")[-2]
                payload, status = update_runtime_connector_trust(conn, connector_id, body)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/mock-runs/start":
                result = start_mock_run(conn, body)
                conn.commit()
                return self.send_json(result, 201)
            if path.startswith("/api/mock-runs/") and path.endswith("/complete"):
                run_id = path.split("/")[-2]
                ok = complete_run(conn, run_id, "user", "usr_founder")
                conn.commit()
                return self.send_json({"completed": ok, "run_id": run_id})
            if path.endswith("/request-approval") and path.startswith("/api/tool-calls/"):
                tc_id = path.split("/")[-2]
                tc = conn.execute("SELECT * FROM tool_calls WHERE tool_call_id=?", (tc_id,)).fetchone()
                if not tc:
                    return self.send_json({"error": "not found"}, 404)
                run = conn.execute("SELECT * FROM runs WHERE run_id=?", (tc["run_id"],)).fetchone()
                approval_id = new_id("ap")
                conn.execute("INSERT INTO approvals(approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,decision,reason,expires_at,created_at,decided_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                             (approval_id, run["task_id"], tc["run_id"], tc_id, tc["agent_id"], "usr_founder", "pending", "Manual approval requested", (dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=2)).isoformat(), now_iso(), None))
                audit(conn, "user", "usr_founder", "approval.request", "approvals", approval_id, None, {"tool_call_id": tc_id}, {})
                conn.commit()
                return self.send_json({"approval_id": approval_id}, 201)
            if path.startswith("/api/approvals/") and path.endswith("/approve"):
                approval_id = path.split("/")[-2]
                return self.decide_approval(conn, approval_id, "approved")
            if path.startswith("/api/approvals/") and path.endswith("/reject"):
                approval_id = path.split("/")[-2]
                return self.decide_approval(conn, approval_id, "rejected")
            if path.startswith("/api/memories/") and path.endswith("/approve"):
                memory_id = path.split("/")[-2]
                return self.review_memory(conn, memory_id, "approved", request_workspace(self.headers, {"workspace_id": [body.get("workspace_id")]} if body.get("workspace_id") else None))
            if path.startswith("/api/memories/") and path.endswith("/reject"):
                memory_id = path.split("/")[-2]
                return self.review_memory(conn, memory_id, "rejected", request_workspace(self.headers, {"workspace_id": [body.get("workspace_id")]} if body.get("workspace_id") else None))
            if path == "/api/evaluations/run-rule-check":
                run_id = body.get("run_id")
                run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
                if not run:
                    return self.send_json({"error": "run not found"}, 404)
                task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (run["task_id"],)).fetchone()
                evaluate_run(conn, run, task)
                conn.commit()
                return self.send_json({"created": True})
            if path == "/api/workflows/local-brief":
                return self.send_json(run_local_ai_brief(conn, body), 201)
            if path == "/api/workflows/customer-task":
                return self.send_json(run_customer_task_workflow(conn, body), 201)
            if path == "/api/workflows/customer-worker-task":
                payload, status = run_customer_worker_task_workflow(conn, body)
                return self.send_json(payload, status)
            if path == "/api/workflows/customer-worker-task/submit":
                payload, status = submit_customer_worker_task_job(conn, body)
                return self.send_json(payload, status)
            if path == "/api/workflows/hermes-openclaw-loop":
                body["_base_url"] = body.get("base_url") or f"http://{self.headers.get('Host')}"
                payload, status = run_hermes_openclaw_loop_workflow(body, self.headers.get("Host"))
                return self.send_json(payload, status)
            if path == "/api/workflows/kb-bot-project":
                body["_base_url"] = body.get("base_url") or f"http://{self.headers.get('Host')}"
                return self.send_json(run_kb_bot_project_workflow(conn, body), 201)
            if path == "/api/workflows/customer-task-templates/run":
                body["_base_url"] = body.get("base_url") or f"http://{self.headers.get('Host')}"
                payload, status = run_customer_task_template_workflow(conn, body)
                return self.send_json(payload, status)
            if path == "/api/workflows/customer-task-templates/submit":
                payload, status = submit_customer_task_template_job(conn, body)
                return self.send_json(payload, status)
            if path.startswith("/api/workflows/jobs/") and path.endswith("/mark-failed"):
                job_id = path.split("/")[-2]
                workspace_id = request_workspace(self.headers, {"workspace_id": [body.get("workspace_id")]} if body.get("workspace_id") else None)
                payload, status = mark_workflow_job_failed(conn, job_id, body, workspace_id)
                return self.send_json(payload, status)
            if path.startswith("/api/workflows/customer-projects/") and path.endswith("/report-artifact"):
                project_id = path.split("/")[-2]
                payload, status = customer_project_report_artifact(conn, project_id)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/workers/local/dispatch-once":
                return self.send_json(dispatch_local_worker_once(conn, body), 201)
            if path == "/api/workers/local/start":
                payload, status = start_local_worker_daemon(conn, body)
                return self.send_json(payload, status)
            if path == "/api/workers/local/stop":
                payload, status = stop_local_worker_daemon(conn, body)
                return self.send_json(payload, status)
            if path == "/api/workers/local/restart":
                payload, status = restart_local_worker_daemon(conn, body)
                return self.send_json(payload, status)
            if path == "/api/workers/tasks/release":
                payload, status = release_worker_task(conn, body)
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/workers/fleet/hygiene":
                payload, status = worker_fleet_hygiene(conn, body, apply=bool(body.get("apply")))
                conn.commit()
                return self.send_json(payload, status)
            if path == "/api/integrations/openclaw/import":
                result = import_openclaw(conn)
                conn.commit()
                return self.send_json(result, 201)
            if path == "/api/integrations/openclaw/probe":
                result = run_openclaw_probe(conn)
                conn.commit()
                return self.send_json(result, 201)
            if path == "/api/integrations/hermes/probe":
                result = run_hermes_probe(conn)
                conn.commit()
                return self.send_json(result, 201)
            if path == "/api/integrations/hermes/cli-probe":
                return self.send_json(agnesfallback_cli_probe(conn, body), 201)
            if path == "/api/integrations/hermes/chat-completion-probe":
                return self.send_json(agnesfallback_chat_completion_probe(conn, body), 201)
            if path == "/api/integrations/hermes/run-task":
                result = hermes_run_task(conn, body)
                audit(conn, "user", "usr_founder", "runtime.run_task.preview", "runtime_connectors", "rtc_hermes_default_gateway", None, result, {"dry_run": result.get("dry_run", True)})
                conn.commit()
                return self.send_json(result, 201)
            if path == "/api/integrations/dify/upload-text":
                return self.send_json(dify_create_document_by_text(conn, body), 201)
            if path == "/api/integrations/notion/preview":
                return self.send_json(notion_preview(conn))
            if path == "/api/integrations/notion/dry-run-export":
                return self.send_json(notion_dry_run_export(conn), 201)
            if path == "/api/integrations/notion/export-confirmed":
                payload, status = notion_export_confirmed(conn, body)
                return self.send_json(payload, status)
            if path == "/api/integrations/notion/import-preview":
                return self.send_json(notion_import_preview(conn, body))
            if path == "/api/integrations/notion/sync-memory-candidates":
                return self.send_json(notion_sync_memory_candidates(conn), 201)
            if path == "/api/integrations/notion/sync-tasks":
                return self.send_json(notion_sync_tasks(conn), 201)
            if path == "/api/migration/preview":
                return self.send_json(migration_preview(conn, body), 201)
            if path == "/api/integrations/notion/export-report":
                markdown = build_notion_report(conn)
                dry_run = body.get("dry_run", True) is not False
                confirm_export = bool(body.get("confirm_export", False))
                cfg = notion_config()
                if confirm_export and not commercial_capability_enabled("notion_confirmed_export"):
                    payload = commercial_entitlement_block(conn, "notion_confirmed_export", "notion.export_report", "notion-export")
                    return self.send_json(payload, 403)
                if dry_run or not confirm_export or not cfg["configured"]:
                    return self.send_json({
                        "provider": "notion",
                        "configured": cfg["configured"],
                        "dry_run": True,
                        "created": False,
                        "requires_confirm_export": cfg["configured"] and not confirm_export,
                        "title": body.get("title", "AgentOps MIS 项目汇报工作台"),
                        "markdown": markdown,
                        "block_count": len(text_blocks(markdown)),
                    })
                result = post_notion_page(markdown, body.get("title", "AgentOps MIS 项目汇报工作台"))
                audit(conn, "user", "usr_founder", "notion.export", "integrations", "notion", None, result, {"dry_run": False})
                conn.commit()
                return self.send_json(result, 201)
        return self.send_json({"error": "unknown endpoint"}, 404)

    def handle_patch_api(self, path, body):
        with db() as conn:
            if path.startswith("/api/tasks/") and path.endswith("/status"):
                task_id = path.split("/")[-2]
                before = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
                status = body.get("status")
                conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE task_id=?", (status, now_iso(), task_id))
                after = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
                audit(conn, "user", "usr_founder", "task.status.update", "tasks", task_id, dict(before) if before else None, dict(after) if after else None, {})
                conn.commit()
                return self.send_json(dict(after))
            if path.startswith("/api/tasks/") and path.endswith("/assign"):
                task_id = path.split("/")[-2]
                before = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
                agent_id = body.get("owner_agent_id")
                conn.execute("UPDATE tasks SET owner_agent_id=?, updated_at=? WHERE task_id=?", (agent_id, now_iso(), task_id))
                after = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
                audit(conn, "user", "usr_founder", "task.assign", "tasks", task_id, dict(before) if before else None, dict(after) if after else None, {})
                conn.commit()
                return self.send_json(dict(after))
        return self.send_json({"error": "unknown endpoint"}, 404)

    def decide_approval(self, conn, approval_id, decision):
        before = conn.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        if not before:
            return self.send_json({"error": "not found"}, 404)
        if decision == "approved" and customer_delivery_approval_requires_manifest(before):
            gate = delivery_manifest_gate(conn, before["run_id"])
            if not gate.get("pass"):
                audit(conn, "user", "usr_founder", "approval.blocked_missing_plan_evidence", "approvals", approval_id, dict(before), dict(before), gate)
                conn.commit()
                return self.send_json({
                    "error": "verified_plan_evidence_manifest_required",
                    "message": "Customer delivery approval is blocked until the run has a verified plan_evidence_manifest.",
                    "approval": dict(before),
                    "delivery_approval_gate": gate,
                    "token_omitted": True,
                }, 409)
        conn.execute("UPDATE approvals SET decision=?, decided_at=? WHERE approval_id=?", (decision, now_iso(), approval_id))
        if before["tool_call_id"]:
            tool_before = conn.execute("SELECT * FROM tool_calls WHERE tool_call_id=?", (before["tool_call_id"],)).fetchone()
            conn.execute("UPDATE tool_calls SET status=? WHERE tool_call_id=?", ("completed" if decision == "approved" else "blocked", before["tool_call_id"]))
            tool_after = conn.execute("SELECT * FROM tool_calls WHERE tool_call_id=?", (before["tool_call_id"],)).fetchone()
            audit(conn, "user", "usr_founder", f"tool_call.approval_{decision}", "tool_calls", before["tool_call_id"], dict(tool_before) if tool_before else None, dict(tool_after) if tool_after else None, {"approval_id": approval_id})
        if decision == "approved":
            run = conn.execute("SELECT * FROM runs WHERE run_id=?", (before["run_id"],)).fetchone()
            if run and run["status"] in {"running", "waiting_approval", "planned"}:
                complete_run(conn, before["run_id"], "user", "usr_founder")
            elif run:
                run_before = dict(run)
                conn.execute("UPDATE runs SET approval_required=0 WHERE run_id=?", (before["run_id"],))
                conn.execute("UPDATE tasks SET status=CASE WHEN status='waiting_approval' THEN 'completed' ELSE status END, updated_at=? WHERE task_id=?", (now_iso(), before["task_id"]))
                run_after = conn.execute("SELECT * FROM runs WHERE run_id=?", (before["run_id"],)).fetchone()
                audit(conn, "user", "usr_founder", "run.approval_resolved", "runs", before["run_id"], run_before, dict(run_after), {"approval_id": approval_id, "decision": decision})
        else:
            run = conn.execute("SELECT * FROM runs WHERE run_id=?", (before["run_id"],)).fetchone()
            conn.execute("UPDATE runs SET status='blocked', error_type='ApprovalRejected', error_message='High-risk tool approval rejected.', ended_at=? WHERE run_id=?", (now_iso(), before["run_id"]))
            conn.execute("UPDATE tasks SET status='blocked', updated_at=? WHERE task_id=?", (now_iso(), before["task_id"]))
            audit(conn, "user", "usr_founder", "run.blocked", "runs", before["run_id"], dict(run), {"status": "blocked"}, {"approval_id": approval_id})
        after = conn.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        sync_enrollment_request_decision(conn, approval_id, decision)
        audit(conn, "user", "usr_founder", f"approval.{decision}", "approvals", approval_id, dict(before), dict(after), {})
        conn.commit()
        return self.send_json(dict(after))

    def review_memory(self, conn, memory_id, status, workspace_id=None):
        workspace_id = normalize_workspace_id(workspace_id or "local-demo")
        before = repo_get_workspace_memory(conn, workspace_id, memory_id)
        if not before:
            return self.send_json(workspace_hidden("memory", memory_id), 404)
        conn.execute("UPDATE memories SET review_status=?, updated_at=? WHERE memory_id=?", (status, now_iso(), memory_id))
        after = conn.execute("SELECT * FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
        audit(conn, "user", "usr_founder", f"memory.{status}", "memories", memory_id, dict(before), dict(after), {})
        conn.commit()
        return self.send_json(dict(after))


def start_mock_run(conn, body):
    task_id = body.get("task_id") or "tsk_competitor"
    task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
    if not task:
        raise ValueError("task not found")
    agent_id = body.get("agent_id") or task["owner_agent_id"] or "agt_research"
    agent = conn.execute("SELECT * FROM agents WHERE agent_id=?", (agent_id,)).fetchone()
    if not agent:
        raise ValueError("agent not found")
    run_id = new_id("run")
    trace_id = new_id("trace")
    start = now_iso()
    workspace_id = row_workspace(task)
    row = {
        "run_id": run_id,
        "workspace_id": workspace_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": agent["runtime_type"],
        "status": "running",
        "started_at": start,
        "ended_at": None,
        "duration_ms": None,
        "input_summary": f"Mock run started for task: {task['title']}",
        "output_summary": None,
        "model_provider": agent["model_provider"],
        "model_name": agent["model_name"],
        "input_tokens": random.randint(400, 1200),
        "output_tokens": random.randint(0, 600),
        "reasoning_tokens": random.randint(0, 400),
        "cost_usd": round(random.uniform(0.05, 1.5), 3),
        "error_type": None,
        "error_message": None,
        "trace_id": trace_id,
        "parent_run_id": body.get("parent_run_id"),
        "delegation_id": new_id("del"),
        "approval_required": 0,
        "created_at": start,
    }
    upsert_run(conn, row, "mock-run", {"workspace_id": workspace_id})
    conn.execute("UPDATE tasks SET status='running', updated_at=? WHERE task_id=?", (now_iso(), task_id))
    conn.execute("UPDATE agents SET status='running', updated_at=? WHERE agent_id=?", (now_iso(), agent_id))
    audit(conn, "user", "usr_founder", "run.start", "runs", run_id, None, {"run_id": run_id, "task_id": task_id, "agent_id": agent_id}, {})

    tool_pool = [
        ("browser.search", "browser", "low"),
        ("github.read", "github", "low"),
        ("file.write", "file", "medium"),
        ("shell.exec", "shell", "high"),
        ("email.send", "email", "high"),
        ("notion.write", "notion", "medium"),
        ("database.write", "database", "critical"),
        ("discord.post", "discord", "medium"),
        ("mcp.invoke", "mcp", "high"),
    ]
    n = random.randint(2, 5)
    high_risk = []
    tool_calls = []
    for i in range(n):
        tool_name, category, risk = random.choice(tool_pool)
        tc_id = new_id("tc")
        args = {"task_id": task_id, "dry_run": True, "input_ref": f"run://{run_id}"}
        status = "waiting_approval" if risk in ("high", "critical") else "completed"
        conn.execute(
            """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tc_id, run_id, agent_id, tool_name, "v1", category, json.dumps(args, ensure_ascii=False), f"mock://{category}/{task_id}", risk, status, f"Mocked {tool_name}", new_id("se") if risk in ("high", "critical") else None, now_iso(), now_iso() if status == "completed" else None, now_iso())
        )
        audit(conn, "agent", agent_id, "tool_call.create", "tool_calls", tc_id, None, {"tool_name": tool_name, "risk": risk}, {"run_id": run_id})
        tool_calls.append(tc_id)
        if risk in ("high", "critical"):
            high_risk.append(tc_id)
    if high_risk:
        conn.execute("UPDATE runs SET status='waiting_approval', approval_required=1 WHERE run_id=?", (run_id,))
        conn.execute("UPDATE tasks SET status='waiting_approval', updated_at=? WHERE task_id=?", (now_iso(), task_id))
        for tc_id in high_risk:
            approval_id = new_id("ap")
            conn.execute("INSERT INTO approvals(approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,decision,reason,expires_at,created_at,decided_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         (approval_id, task_id, run_id, tc_id, agent_id, "usr_founder", "pending", "High-risk tool call requires approval", (dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=2)).isoformat(), now_iso(), None))
            audit(conn, "agent", agent_id, "approval.request", "approvals", approval_id, None, {"tool_call_id": tc_id}, {"run_id": run_id})
    else:
        complete_run(conn, run_id)
    return {"run_id": run_id, "tool_calls": tool_calls, "approval_required": bool(high_risk), "high_risk_tool_calls": high_risk}


def dashboard_metrics(conn):
    agents_total = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    agents_running = conn.execute("SELECT COUNT(*) FROM agents WHERE status='running'").fetchone()[0]
    total_cost = conn.execute("SELECT COALESCE(SUM(cost_usd),0) FROM runs").fetchone()[0]
    completed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='completed'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('failed','blocked')").fetchone()[0]
    tasks_total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    avg_cost = conn.execute("SELECT COALESCE(AVG(cost_usd),0) FROM runs WHERE status='completed'").fetchone()[0]
    pending_approvals = conn.execute("SELECT COUNT(*) FROM approvals WHERE decision='pending'").fetchone()[0]
    stale_memories = conn.execute("SELECT COUNT(*) FROM memories WHERE review_status='stale' OR ttl_review_due_at < ?", (now_iso(),)).fetchone()[0]
    task_status = rows_to_dicts(conn.execute("SELECT status, COUNT(*) AS count FROM tasks GROUP BY status").fetchall())
    top_cost_agents = rows_to_dicts(conn.execute("SELECT a.agent_id, a.name, ROUND(COALESCE(SUM(r.cost_usd),0),3) AS cost_usd FROM agents a LEFT JOIN runs r ON a.agent_id=r.agent_id GROUP BY a.agent_id ORDER BY cost_usd DESC LIMIT 5").fetchall())
    top_failing_agents = rows_to_dicts(conn.execute("SELECT a.agent_id, a.name, SUM(CASE WHEN r.status IN ('failed','blocked') THEN 1 ELSE 0 END) AS failures FROM agents a LEFT JOIN runs r ON a.agent_id=r.agent_id GROUP BY a.agent_id ORDER BY failures DESC LIMIT 5").fetchall())
    recent_runs = rows_to_dicts(conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 20").fetchall())
    openclaw_counts = dict(conn.execute(
        """SELECT
        (SELECT COUNT(*) FROM agents WHERE runtime_type='openclaw') AS agents,
        (SELECT COUNT(*) FROM tasks WHERE task_id LIKE 'tsk_oc_cron_%') AS cron_tasks,
        (SELECT COUNT(*) FROM tasks WHERE task_id LIKE 'tsk_oc_cron_%' AND status='planned') AS enabled_cron_tasks,
        (SELECT COUNT(*) FROM runs WHERE run_id LIKE 'run_oc_cron_%') AS cron_runs,
        (SELECT COUNT(*) FROM runs WHERE runtime_type='openclaw' AND status='failed') AS failed_runs,
        (SELECT COUNT(*) FROM evaluations WHERE evaluation_id LIKE 'eval_gate_run_oc_%' AND pass_fail='fail') AS failed_quality_gates"""
    ).fetchone())
    agent_performance_summary = rows_to_dicts(conn.execute(
        """SELECT a.agent_id, a.name, a.runtime_type, COUNT(r.run_id) AS total_runs,
        ROUND(CASE WHEN COUNT(r.run_id)=0 THEN 0 ELSE 1.0 * SUM(CASE WHEN r.status='completed' THEN 1 ELSE 0 END) / COUNT(r.run_id) END, 3) AS success_rate,
        CAST(COALESCE(AVG(r.duration_ms),0) AS INTEGER) AS avg_duration_ms,
        ROUND(COALESCE(SUM(r.cost_usd),0), 4) AS total_cost_usd,
        SUM(CASE WHEN r.status IN ('failed','blocked') THEN 1 ELSE 0 END) AS failures,
        SUM(CASE WHEN r.approval_required=1 THEN 1 ELSE 0 END) AS approval_required_count
        FROM agents a LEFT JOIN runs r ON a.agent_id=r.agent_id
        GROUP BY a.agent_id
        ORDER BY total_runs DESC, success_rate DESC
        LIMIT 8"""
    ).fetchall())
    openclaw_runtime = openclaw_status()
    hermes_runtime = hermes_status()
    notion_runtime = notion_config()
    runtime_health = [
        {
            "provider": "openclaw",
            "status": "ready" if openclaw_runtime["config_exists"] else "missing_config",
            "agents": openclaw_runtime["agents_count"],
            "cron_jobs": openclaw_runtime["cron_jobs_count"],
            "run_files": openclaw_runtime["cron_run_files_count"],
        },
        {
            "provider": "hermes",
            "status": "ready" if hermes_runtime["api_listening"] else "unavailable",
            "home_exists": hermes_runtime["home_exists"],
            "api_port": hermes_runtime["api_port"],
        },
        {
            "provider": "notion",
            "status": "configured" if notion_runtime["configured"] else "dry_run_only",
            "has_token": notion_runtime["has_token"],
            "has_parent": bool(notion_runtime["parent_page_id"] or notion_runtime["database_id"]),
        },
    ]
    return {
        "agents_total": agents_total,
        "agents_running": agents_running,
        "tasks_completed_total": completed,
        "total_cost_usd": round(total_cost, 3),
        "avg_task_cost_usd": round(avg_cost or 0, 3),
        "failure_rate": round((failed / tasks_total) if tasks_total else 0, 3),
        "pending_approvals": pending_approvals,
        "stale_or_due_memories": stale_memories,
        "task_status_distribution": task_status,
        "top_cost_agents": top_cost_agents,
        "top_failing_agents": top_failing_agents,
        "runtime_health": runtime_health,
        "openclaw_import": openclaw_counts,
        "agent_performance_summary": agent_performance_summary,
        "recent_runs": recent_runs,
    }


def build_notion_report(conn) -> str:
    metrics = dashboard_metrics(conn)
    openclaw_run = conn.execute(
        "SELECT * FROM runs WHERE runtime_type='openclaw' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    pending_memory = conn.execute("SELECT COUNT(*) FROM memories WHERE review_status='candidate'").fetchone()[0]
    evaluations = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
    tool_calls = conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0]
    audit_logs = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    openclaw = metrics["openclaw_import"]
    hermes = next((item for item in metrics["runtime_health"] if item["provider"] == "hermes"), {})
    quality = conn.execute("SELECT pass_fail, COUNT(*) AS count FROM evaluations GROUP BY pass_fail").fetchall()
    memory_review = rows_to_dicts(conn.execute("SELECT review_status, COUNT(*) AS count FROM memories GROUP BY review_status").fetchall())
    lines = [
        "# AgentOps MIS 项目汇报工作台",
        "",
        "## 一句话定位",
        "AgentOps MIS 是面向一人公司和小型 AI 团队的 AI 数字员工管理信息系统，用于统一管理 Agent 的身份、任务、工具、运行、审批、记忆、质量和审计。",
        "",
        "## 当前 Demo 能力",
        f"- Agent registry: {metrics['agents_total']} agents",
        f"- Running agents: {metrics['agents_running']}",
        f"- Completed tasks: {metrics['tasks_completed_total']}",
        f"- Pending approvals: {metrics['pending_approvals']}",
        f"- Tool calls recorded: {tool_calls}",
        f"- Evaluations recorded: {evaluations}",
        f"- Memory candidates pending review: {pending_memory}",
        f"- Audit logs recorded: {audit_logs}",
        f"- OpenClaw imported agents/tasks/runs: {openclaw['agents']} / {openclaw['cron_tasks']} / {openclaw['cron_runs']}",
        f"- Hermes gateway status: {hermes.get('status', 'unknown')}",
        "",
        "## 核心闭环",
        "Agent Registry -> Task Assignment -> Run Ledger -> Tool Call Ledger -> Approval Workflow -> Evaluation -> Organizational Memory -> Audit Log -> Dashboard",
        "",
        "## OpenClaw v1 实验",
    ]
    if openclaw_run:
        lines.extend(
            [
                f"- Run id: {openclaw_run['run_id']}",
                f"- Status: {openclaw_run['status']}",
                f"- Runtime: {openclaw_run['runtime_type']}",
                f"- Model: {openclaw_run['model_provider']} / {openclaw_run['model_name']}",
                f"- Duration ms: {openclaw_run['duration_ms']}",
                f"- Trace id: {openclaw_run['trace_id']}",
            ]
        )
    else:
        lines.append("- No OpenClaw run recorded yet.")
    quality_distribution = ", ".join(f"{row['pass_fail']}={row['count']}" for row in quality) if quality else "none"
    memory_review_distribution = ", ".join(f"{row['review_status']}={row['count']}" for row in memory_review) if memory_review else "none"
    lines.extend(
        [
            "",
            "## 强本地 MVP 状态",
            f"- OpenClaw cron health: {openclaw['cron_runs']} imported runs, {openclaw['failed_runs']} failed runs, {openclaw['failed_quality_gates']} failed quality gates",
            f"- Hermes probe readiness: {hermes.get('status', 'unknown')} on port {hermes.get('api_port', 8642)}",
            f"- Quality gate distribution: {quality_distribution}",
            f"- Memory review distribution: {memory_review_distribution}",
            "",
            "## Agent 绩效摘要",
        ]
    )
    for perf in metrics["agent_performance_summary"][:5]:
        lines.append(
            f"- {perf['name']}: runs={perf['total_runs']}, success={round((perf['success_rate'] or 0) * 100)}%, failures={perf['failures']}, avg_ms={perf['avg_duration_ms']}"
        )
    lines.extend(
        [
            "",
            "## 10 分钟汇报结构",
            "- 项目简介：背景和目标，2 分钟",
            "- 系统规划、分析与设计：业务、功能、数据、架构，3 分钟",
            "- 商业价值与商业模式：1 分钟",
            "- 项目亮点：1 分钟",
            "- 前后台 demo 展示：2 分钟",
            "",
            "## 今日优先级",
            "- 保持本地 demo 可运行",
            "- 完成汇报内容与架构说明",
            "- 做好 Notion 连接和导出基础",
            "- UI/Figma 后续再专项优化",
            "",
            "## 隐私边界",
            "Notion 导出只包含项目汇报摘要和结构化指标，不导出 credentials、私聊正文、完整 session transcript 或原始命令体。",
        ]
    )
    return "\n".join(lines) + "\n"


def post_notion_page(markdown: str, title: str = "AgentOps MIS 项目汇报工作台") -> dict:
    cfg = notion_config()
    if not cfg["configured"]:
        return {"configured": False, "created": False, "reason": "NOTION_TOKEN plus a parent/database target, or NOTION_WORKSPACE_PRIVATE_EXPORT=true, is required."}

    if cfg["parent_page_id"]:
        parent = {"page_id": cfg["parent_page_id"]}
        properties = {"title": {"title": [{"type": "text", "text": {"content": title}}]}}
    elif cfg["database_id"]:
        parent = {"database_id": cfg["database_id"]}
        properties = {"Name": {"title": [{"type": "text", "text": {"content": title}}]}}
    else:
        parent = {"workspace": True}
        properties = {"title": {"title": [{"type": "text", "text": {"content": title}}]}}

    payload = {
        "parent": parent,
        "properties": properties,
        "children": text_blocks(markdown),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        "https://api.notion.com/v1/pages",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['NOTION_TOKEN'].strip()}",
            "Content-Type": "application/json",
            "Notion-Version": cfg["notion_version"],
        },
    )
    with urlopen(req, timeout=30) as res:
        data = json.loads(res.read().decode("utf-8"))
    return {"configured": True, "created": True, "export_mode": cfg["export_mode"], "notion_page_id": data.get("id"), "url": data.get("url")}


def main():
    parser = argparse.ArgumentParser(description="AgentOps MIS MVP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    parser.add_argument("--reset", action="store_true", help="Reset SQLite database and seed data, then exit unless --serve is also set")
    parser.add_argument("--serve", action="store_true", help="Serve after reset")
    args = parser.parse_args()
    if args.reset:
        seed(reset=True)
        print(f"Reset and seeded {DB_PATH}")
        if not args.serve:
            return
    else:
        seed(reset=False)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AgentOps MIS MVP running at http://{args.host}:{args.port}/dashboard")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")


if __name__ == "__main__":
    main()
