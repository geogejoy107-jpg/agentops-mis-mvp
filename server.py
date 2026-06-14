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
import json
import os
import random
import re
import socket
import sqlite3
import subprocess
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "agentops_mis.db"
STATIC_DIR = ROOT / "static"
ARTIFACTS_DIR = ROOT / "artifacts"
OPENCLAW_HOME = Path.home() / ".openclaw"
HERMES_HOME = Path.home() / ".hermes"
OPENCLAW_BIN = Path("/opt/homebrew/bin/openclaw")

RISKY_TOOLS = {
    "shell.exec",
    "github.push",
    "email.send",
    "file.delete",
    "database.write",
}
HIGH_RISK_CATEGORIES = {"shell", "email", "database"}


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
    replacements = [
        (r"(?i)(bearer\s+)[a-z0-9._\-]+", r"\1[REDACTED]"),
        (r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;]+", r"\1=[REDACTED]"),
        (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL_REDACTED]"),
        (r"\+?\d[\d\s().-]{7,}\d", "[PHONE_REDACTED]"),
    ]
    for pattern, repl in replacements:
        value = re.sub(pattern, repl, value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


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
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_runtime_events_connector ON runtime_events(runtime_connector_id);
CREATE INDEX IF NOT EXISTS idx_connectors_base ON connectors(base_id);
CREATE INDEX IF NOT EXISTS idx_sync_events_connector ON sync_events(connector_id);
CREATE INDEX IF NOT EXISTS idx_external_links_internal ON external_object_links(internal_object_type, internal_object_id);
"""


def audit(conn: sqlite3.Connection, actor_type: str, actor_id: str | None, action: str, entity_type: str, entity_id: str, before=None, after=None, metadata=None):
    previous = conn.execute("SELECT tamper_chain_hash FROM audit_logs ORDER BY created_at DESC LIMIT 1").fetchone()
    previous_hash = previous[0] if previous else "genesis"
    payload = {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before_hash": stable_hash(before) if before is not None else None,
        "after_hash": stable_hash(after) if after is not None else None,
        "metadata_json": metadata or {},
        "previous": previous_hash,
    }
    chain = stable_hash(payload)
    conn.execute(
        """
        INSERT INTO audit_logs(audit_id, actor_type, actor_id, action, entity_type, entity_id, before_hash, after_hash, metadata_json, tamper_chain_hash, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            new_id("aud"), actor_type, actor_id, action, entity_type, entity_id,
            payload["before_hash"], payload["after_hash"], json.dumps(metadata or {}, ensure_ascii=False), chain, now_iso()
        ),
    )


def init_schema():
    with db() as conn:
        conn.executescript(SCHEMA_SQL)
        ensure_v121_reference_data(conn)
        conn.commit()


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
    return {
        "binary_path": os.path.expanduser(os.environ.get("AGNESFALLBACK_BIN", "~/.local/bin/agnesfallback").strip()),
        "gateway_url": os.environ.get("AGNESFALLBACK_GATEWAY_URL", "http://127.0.0.1:8643").strip(),
        "profile": os.environ.get("AGNESFALLBACK_PROFILE", "agnesfallback").strip() or "agnesfallback",
    }


def runtime_connector_rows() -> list[dict]:
    now = now_iso()
    hermes = hermes_runtime_config()
    agnes = agnesfallback_config()
    return [
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
    conn.execute(
        """INSERT INTO runtime_events(runtime_event_id,runtime_connector_id,event_type,status,run_id,task_id,agent_id,model_name,latency_ms,prompt_hash,input_summary,output_summary,error_message,raw_payload_hash,created_at)
        VALUES(:runtime_event_id,:runtime_connector_id,:event_type,:status,:run_id,:task_id,:agent_id,:model_name,:latency_ms,:prompt_hash,:input_summary,:output_summary,:error_message,:raw_payload_hash,:created_at)""",
        row,
    )
    return row


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
        for table in ["audit_logs", "artifacts", "evaluations", "memories", "approvals", "tool_calls", "runs", "tasks", "agents", "users"]:
            conn.execute(f"DELETE FROM {table}")

        users = [
            ("usr_founder", "Founder", "founder@example.local", "founder", now_iso()),
            ("usr_ops", "Ops Reviewer", "ops@example.local", "reviewer", now_iso()),
            ("usr_admin", "Platform Admin", "admin@example.local", "admin", now_iso()),
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
    # artifact
    conn.execute("INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,uri,summary,created_at) VALUES(?,?,?,?,?,?,?,?)",
                 (new_id("art"), run["task_id"], run_id, "markdown", "Mock output artifact", f"artifact://{run_id}/output", "Generated by mock runtime", now_iso()))
    # evaluation
    run_after = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    evaluate_run(conn, run_after, task)
    # memory candidates
    for _ in range(random.randint(0, 2)):
        mem_id = new_id("mem")
        conn.execute(
            """INSERT INTO memories(memory_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mem_id, random.choice(["task", "project"]), random.choice(["decision", "commitment", "agent_lesson", "artifact_summary"]),
             f"Mock memory candidate from run {run_id}: preserve evidence, owner, TTL and review status.", "run_log", run_id, "proj_mvp",
             run["task_id"], run["agent_id"], round(random.uniform(0.66, 0.92), 2), "candidate", "usr_founder",
             (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).isoformat(), None, json.dumps(["mock", "review"], ensure_ascii=False), now_iso(), now_iso())
        )
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
    conn.execute(
        """INSERT INTO evaluations(evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (eval_id, run["task_id"], run["run_id"], run["agent_id"], "rule", score, "pass" if passed else "fail", json.dumps(rules, ensure_ascii=False), "Rule-based mock evaluator", now_iso()),
    )
    audit(conn, "system", "rule-evaluator", "evaluation.create", "evaluations", eval_id, None, {"score": score, "pass_fail": passed}, {"run_id": run["run_id"]})


def upsert_agent(conn, row: dict, actor_id="adapter-import") -> str:
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


def upsert_task(conn, row: dict, actor_id="adapter-import") -> str:
    before = conn.execute("SELECT * FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()
    if before:
        if row_unchanged(before, row, {"created_at", "updated_at"}):
            return "unchanged"
        conn.execute(
            """UPDATE tasks SET title=:title, description=:description, requester_id=:requester_id,
            owner_agent_id=:owner_agent_id, collaborator_agent_ids=:collaborator_agent_ids, status=:status,
            priority=:priority, due_date=:due_date, acceptance_criteria=:acceptance_criteria, risk_level=:risk_level,
            budget_limit_usd=:budget_limit_usd, updated_at=:updated_at WHERE task_id=:task_id""",
            row,
        )
        action = "task.update"
    else:
        conn.execute(
            """INSERT INTO tasks(task_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
            VALUES(:task_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)""",
            row,
        )
        action = "task.create"
    audit(conn, "system", actor_id, action, "tasks", row["task_id"], dict(before) if before else None, row, {})
    return "updated" if before else "created"


def upsert_run(conn, row: dict, actor_id="adapter-import", audit_metadata=None) -> str:
    before = conn.execute("SELECT * FROM runs WHERE run_id=?", (row["run_id"],)).fetchone()
    if before:
        if actor_id == "openclaw-import":
            return "unchanged"
        if row_unchanged(before, row, {"created_at"}):
            return "unchanged"
        conn.execute(
            """UPDATE runs SET task_id=:task_id, agent_id=:agent_id, runtime_type=:runtime_type, status=:status,
            started_at=:started_at, ended_at=:ended_at, duration_ms=:duration_ms, input_summary=:input_summary,
            output_summary=:output_summary, model_provider=:model_provider, model_name=:model_name,
            input_tokens=:input_tokens, output_tokens=:output_tokens, reasoning_tokens=:reasoning_tokens,
            cost_usd=:cost_usd, error_type=:error_type, error_message=:error_message, trace_id=:trace_id,
            parent_run_id=:parent_run_id, delegation_id=:delegation_id, approval_required=:approval_required
            WHERE run_id=:run_id""",
            row,
        )
        action = "run.update"
    else:
        conn.execute(
            """INSERT INTO runs(run_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
            VALUES(:run_id,:task_id,:agent_id,:runtime_type,:status,:started_at,:ended_at,:duration_ms,:input_summary,:output_summary,:model_provider,:model_name,:input_tokens,:output_tokens,:reasoning_tokens,:cost_usd,:error_type,:error_message,:trace_id,:parent_run_id,:delegation_id,:approval_required,:created_at)""",
            row,
        )
        action = "run.create"
    audit(conn, "system", actor_id, action, "runs", row["run_id"], dict(before) if before else None, row, audit_metadata or {})
    return "updated" if before else "created"


def upsert_tool_call(conn, row: dict, actor_id="adapter-import", audit_metadata=None) -> str:
    before = conn.execute("SELECT * FROM tool_calls WHERE tool_call_id=?", (row["tool_call_id"],)).fetchone()
    if before:
        if actor_id == "openclaw-import":
            return "unchanged"
        if row_unchanged(before, row, {"created_at"}):
            return "unchanged"
        conn.execute(
            """UPDATE tool_calls SET run_id=:run_id, agent_id=:agent_id, tool_name=:tool_name, tool_version=:tool_version,
            tool_category=:tool_category, normalized_args_json=:normalized_args_json, target_resource=:target_resource,
            risk_level=:risk_level, status=:status, result_summary=:result_summary, side_effect_id=:side_effect_id,
            started_at=:started_at, ended_at=:ended_at WHERE tool_call_id=:tool_call_id""",
            row,
        )
        action = "tool_call.update"
    else:
        conn.execute(
            """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
            VALUES(:tool_call_id,:run_id,:agent_id,:tool_name,:tool_version,:tool_category,:normalized_args_json,:target_resource,:risk_level,:status,:result_summary,:side_effect_id,:started_at,:ended_at,:created_at)""",
            row,
        )
        action = "tool_call.create"
    audit(conn, "system", actor_id, action, "tool_calls", row["tool_call_id"], dict(before) if before else None, row, audit_metadata or {})
    return "updated" if before else "created"


def upsert_evaluation(conn, row: dict, actor_id="adapter-import") -> str:
    before = conn.execute("SELECT * FROM evaluations WHERE evaluation_id=?", (row["evaluation_id"],)).fetchone()
    if before:
        if actor_id == "openclaw-import":
            return "unchanged"
        if row_unchanged(before, row, {"created_at"}):
            return "unchanged"
        conn.execute(
            """UPDATE evaluations SET task_id=:task_id, run_id=:run_id, agent_id=:agent_id, evaluator_type=:evaluator_type,
            score=:score, pass_fail=:pass_fail, rubric_json=:rubric_json, notes=:notes WHERE evaluation_id=:evaluation_id""",
            row,
        )
        action = "evaluation.update"
    else:
        conn.execute(
            """INSERT INTO evaluations(evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at)
            VALUES(:evaluation_id,:task_id,:run_id,:agent_id,:evaluator_type,:score,:pass_fail,:rubric_json,:notes,:created_at)""",
            row,
        )
        action = "evaluation.create"
    audit(conn, "system", actor_id, action, "evaluations", row["evaluation_id"], dict(before) if before else None, row, {})
    return "updated" if before else "created"


def upsert_memory_candidate(conn, row: dict, actor_id="adapter-import") -> str:
    before = conn.execute("SELECT * FROM memories WHERE memory_id=?", (row["memory_id"],)).fetchone()
    if before:
        if actor_id == "openclaw-import":
            return "unchanged"
        if row_unchanged(before, row, {"created_at", "updated_at", "ttl_review_due_at"}):
            return "unchanged"
        conn.execute(
            """UPDATE memories SET scope=:scope, memory_type=:memory_type, canonical_text=:canonical_text,
            source_type=:source_type, source_ref=:source_ref, project_id=:project_id, task_id=:task_id,
            agent_id=:agent_id, confidence=:confidence, review_status=:review_status, owner_user_id=:owner_user_id,
            ttl_review_due_at=:ttl_review_due_at, supersedes_memory_id=:supersedes_memory_id,
            access_tags=:access_tags, updated_at=:updated_at WHERE memory_id=:memory_id""",
            row,
        )
        action = "memory.update"
    else:
        conn.execute(
            """INSERT INTO memories(memory_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
            VALUES(:memory_id,:scope,:memory_type,:canonical_text,:source_type,:source_ref,:project_id,:task_id,:agent_id,:confidence,:review_status,:owner_user_id,:ttl_review_due_at,:supersedes_memory_id,:access_tags,:created_at,:updated_at)""",
            row,
        )
        action = "memory.propose"
    audit(conn, "system", actor_id, action, "memories", row["memory_id"], dict(before) if before else None, row, {})
    return "updated" if before else "created"


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


def run_openclaw_probe(conn) -> dict:
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
        "would_run": [agnes["binary_path"], "-z", "[FIXED_SAFE_PROMPT]"],
        "prompt_hash": stable_hash(prompt),
        "requires": {"HERMES_ALLOW_REAL_RUN": True, "confirm_run": True},
        "note": "--yolo is not used by default and is intentionally excluded from this code path.",
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
        proc = subprocess.run([agnes["binary_path"], "-z", prompt], capture_output=True, text=True, timeout=180, check=False)
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
        "would_run": [agnes["binary_path"], "-z", "[SAFE_STRUCTURED_MIS_BRIEF_PROMPT]"],
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
        proc = subprocess.run([agnes["binary_path"], "-z", prompt], capture_output=True, text=True, timeout=180, check=False)
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
        conn.execute(
            """INSERT OR REPLACE INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,uri,summary,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (artifact_id, task_id, run_id, "report", "Local AI Work Brief", f"run://{run_id}", visible, now_iso()),
        )
    conn.execute("UPDATE tasks SET status=?, updated_at=? WHERE task_id=?", ("completed" if ok else "blocked", now_iso(), task_id))
    audit(conn, "system", "local-ai-workflow", "workflow.local_ai_brief", "runs", run_id, None, {"status": row["status"], "artifact_id": artifact_id if ok else None}, {"prompt_hash": prompt_hash, "state_hash": state_hash, "confirmed": True})
    conn.commit()
    return {"provider": "agnesfallback", "workflow": "local_ai_brief", "dry_run": False, "ok": ok, "run_id": run_id, "task_id": task_id, "artifact_id": artifact_id if ok else None, "duration_ms": duration, "output_summary": row["output_summary"], "error": error}


def hermes_run_task(conn, body: dict) -> dict:
    risk = body.get("risk_level", "low")
    if risk not in ("low", "medium") and not body.get("confirm_run"):
        return {"created": False, "dry_run": True, "requires_confirm_run": True, "reason": "High-risk runtime tasks require confirm_run=true."}
    return {
        "created": False,
        "dry_run": True,
        "reason": "v1.2.1 MVP exposes confirmed fixed probes only; arbitrary Hermes run-task is planned but not enabled.",
        "allowed_probe_endpoints": ["/api/integrations/hermes/cli-probe", "/api/integrations/hermes/chat-completion-probe"],
    }


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


def notion_export_confirmed(conn, body: dict) -> dict:
    confirm = bool(body.get("confirm_export"))
    cfg = notion_config()
    markdown = build_notion_report(conn)
    if not confirm or not cfg["configured"]:
        event = create_sync_event(conn, "conn_notion_templates", "outbound", "report", "dry_run", {"confirm_export": confirm, "configured": cfg["configured"]})
        audit(conn, "system", "notion-export", "notion.export.skipped", "sync_events", event["sync_event_id"], None, {"dry_run": True}, {"confirm_export": confirm, "configured": cfg["configured"]})
        conn.commit()
        return {"provider": "notion", "dry_run": True, "created": False, "requires_confirm_export": not confirm, "configured": cfg["configured"], "sync_event_id": event["sync_event_id"], "markdown": markdown, "block_count": len(text_blocks(markdown))}
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
        return {**result, "sync_event_id": event["sync_event_id"]}
    except Exception as exc:
        err = redact_text(str(exc), 300)
        event = create_sync_event(conn, "conn_notion_templates", "outbound", "report", "failed", {"export_mode": cfg["export_mode"]}, error_message=err)
        audit(conn, "system", "notion-export", "notion.export_failed", "integrations", "notion", None, {"created": False}, {"error": err, "sync_event_id": event["sync_event_id"]})
        conn.commit()
        return {"provider": "notion", "created": False, "configured": cfg["configured"], "export_mode": cfg["export_mode"], "error": err, "sync_event_id": event["sync_event_id"]}


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
                rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
                return self.send_json(rows_to_dicts(rows))
            if path.startswith("/api/tasks/") and "/" not in path[len("/api/tasks/"):].strip("/"):
                task_id = path.split("/")[-1]
                task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
                if not task:
                    return self.send_json({"error": "not found"}, 404)
                data = {"task": dict(task)}
                for table in ["runs", "approvals", "evaluations", "memories", "artifacts"]:
                    data[table] = rows_to_dicts(conn.execute(f"SELECT * FROM {table} WHERE task_id=? ORDER BY created_at DESC", (task_id,)).fetchall())
                return self.send_json(data)
            if path == "/api/runs":
                where, params = [], []
                if "task_id" in qs:
                    where.append("task_id=?"); params.append(qs["task_id"][0])
                if "agent_id" in qs:
                    where.append("agent_id=?"); params.append(qs["agent_id"][0])
                sql = "SELECT * FROM runs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created_at DESC"
                return self.send_json(rows_to_dicts(conn.execute(sql, params).fetchall()))
            if path == "/api/runs/export":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()))
            if path.startswith("/api/runs/") and path.endswith("/graph"):
                run_id = path.split("/")[-2]
                data = run_graph(conn, run_id)
                if not data:
                    return self.send_json({"error": "not found"}, 404)
                return self.send_json(data)
            if path.startswith("/api/runs/"):
                run_id = path.split("/")[-1]
                run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
                if not run:
                    return self.send_json({"error": "not found"}, 404)
                return self.send_json({
                    "run": dict(run),
                    "tool_calls": rows_to_dicts(conn.execute("SELECT * FROM tool_calls WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()),
                    "approvals": rows_to_dicts(conn.execute("SELECT * FROM approvals WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()),
                    "evaluations": rows_to_dicts(conn.execute("SELECT * FROM evaluations WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()),
                    "artifacts": rows_to_dicts(conn.execute("SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()),
                })
            if path == "/api/tool-calls":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM tool_calls ORDER BY created_at DESC").fetchall()))
            if path == "/api/approvals":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM approvals ORDER BY created_at DESC").fetchall()))
            if path == "/api/memories":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM memories ORDER BY created_at DESC").fetchall()))
            if path == "/api/memories/export":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM memories ORDER BY created_at DESC").fetchall()))
            if path == "/api/evaluations":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM evaluations ORDER BY created_at DESC").fetchall()))
            if path == "/api/audit":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 200").fetchall()))
            if path == "/api/dashboard/metrics":
                return self.send_json(dashboard_metrics(conn))
            if path == "/api/runtime-connectors":
                refresh_runtime_connectors(conn)
                conn.commit()
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM runtime_connectors ORDER BY provider, connector_type, profile_name").fetchall()))
            if path == "/api/runtime-events":
                return self.send_json(rows_to_dicts(conn.execute("SELECT * FROM runtime_events ORDER BY created_at DESC LIMIT 200").fetchall()))
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
            if path == "/api/integrations/openclaw/status":
                return self.send_json(openclaw_status())
            if path == "/api/integrations/hermes/status":
                return self.send_json(hermes_status())
            if path == "/api/integrations/hermes/models":
                return self.send_json(hermes_models(conn))
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
                task_id = body.get("task_id") or new_id("tsk")
                now = now_iso()
                row = {
                    "task_id": task_id,
                    "title": body.get("title", "New Task"),
                    "description": body.get("description", ""),
                    "requester_id": body.get("requester_id", "usr_founder"),
                    "owner_agent_id": body.get("owner_agent_id", "agt_research"),
                    "collaborator_agent_ids": json.dumps(body.get("collaborator_agent_ids", []), ensure_ascii=False),
                    "status": body.get("status", "planned"),
                    "priority": body.get("priority", "medium"),
                    "due_date": body.get("due_date"),
                    "acceptance_criteria": body.get("acceptance_criteria", "Must satisfy task acceptance criteria and pass quality gate."),
                    "risk_level": body.get("risk_level", "medium"),
                    "budget_limit_usd": float(body.get("budget_limit_usd", 3.0)),
                    "created_at": now,
                    "updated_at": now,
                }
                conn.execute("""INSERT INTO tasks(task_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
                    VALUES(:task_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)""", row)
                audit(conn, "user", "usr_founder", "task.create", "tasks", task_id, None, row, {})
                conn.commit()
                return self.send_json(row, 201)
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
                return self.review_memory(conn, memory_id, "approved")
            if path.startswith("/api/memories/") and path.endswith("/reject"):
                memory_id = path.split("/")[-2]
                return self.review_memory(conn, memory_id, "rejected")
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
            if path == "/api/integrations/notion/preview":
                return self.send_json(notion_preview(conn))
            if path == "/api/integrations/notion/dry-run-export":
                return self.send_json(notion_dry_run_export(conn), 201)
            if path == "/api/integrations/notion/export-confirmed":
                return self.send_json(notion_export_confirmed(conn, body), 201)
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
        conn.execute("UPDATE approvals SET decision=?, decided_at=?, reason=? WHERE approval_id=?", (decision, now_iso(), f"Manual {decision}", approval_id))
        if before["tool_call_id"]:
            conn.execute("UPDATE tool_calls SET status=? WHERE tool_call_id=?", ("completed" if decision == "approved" else "blocked", before["tool_call_id"]))
        if decision == "approved":
            complete_run(conn, before["run_id"], "user", "usr_founder")
        else:
            run = conn.execute("SELECT * FROM runs WHERE run_id=?", (before["run_id"],)).fetchone()
            conn.execute("UPDATE runs SET status='blocked', error_type='ApprovalRejected', error_message='High-risk tool approval rejected.', ended_at=? WHERE run_id=?", (now_iso(), before["run_id"]))
            conn.execute("UPDATE tasks SET status='blocked', updated_at=? WHERE task_id=?", (now_iso(), before["task_id"]))
            audit(conn, "user", "usr_founder", "run.blocked", "runs", before["run_id"], dict(run), {"status": "blocked"}, {"approval_id": approval_id})
        after = conn.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
        audit(conn, "user", "usr_founder", f"approval.{decision}", "approvals", approval_id, dict(before), dict(after), {})
        conn.commit()
        return self.send_json(dict(after))

    def review_memory(self, conn, memory_id, status):
        before = conn.execute("SELECT * FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
        if not before:
            return self.send_json({"error": "not found"}, 404)
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
    conn.execute(
        """INSERT INTO runs(run_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, task_id, agent_id, agent["runtime_type"], "running", start, None, None, f"Mock run started for task: {task['title']}", None, agent["model_provider"], agent["model_name"], random.randint(400, 1200), random.randint(0, 600), random.randint(0, 400), round(random.uniform(0.05, 1.5), 3), None, None, trace_id, body.get("parent_run_id"), new_id("del"), 0, start)
    )
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
    lines.extend(
        [
            "",
            "## 强本地 MVP 状态",
            f"- OpenClaw cron health: {openclaw['cron_runs']} imported runs, {openclaw['failed_runs']} failed runs, {openclaw['failed_quality_gates']} failed quality gates",
            f"- Hermes probe readiness: {hermes.get('status', 'unknown')} on port {hermes.get('api_port', 8642)}",
            f"- Quality gate distribution: {', '.join(f'{row['pass_fail']}={row['count']}' for row in quality) if quality else 'none'}",
            f"- Memory review distribution: {', '.join(f'{row['review_status']}={row['count']}' for row in memory_review) if memory_review else 'none'}",
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
