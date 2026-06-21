#!/usr/bin/env python3
"""Verify operator task-intake checklist gates planned work before execution."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
DEFAULT_DB = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json(base_url: str, method: str, path: str, payload: dict | None = None, token: str | None = None, query: dict | None = None) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode({key: value for key, value in query.items() if value is not None}, doseq=True)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw), raw
        except Exception:
            return exc.code, {"raw": raw}, raw
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def run_cli(base_url: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def db_fingerprint(db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        result = {}
        for table, timestamp_col in [
            ("tasks", "updated_at"),
            ("agent_plans", "updated_at"),
            ("audit_logs", "created_at"),
            ("runtime_events", "created_at"),
        ]:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                continue
            row = conn.execute(f"SELECT COUNT(*) AS count, COALESCE(MAX({timestamp_col}), '') AS max_ts FROM {table}").fetchone()
            result[table] = {"count": int(row["count"] or 0), "max_ts": row["max_ts"] or ""}
        return result
    finally:
        conn.close()


def create_enrollment(base_url: str, workspace_id: str, agent_id: str) -> tuple[str, str]:
    status, created, _raw = http_json(base_url, "POST", "/api/agent-gateway/enrollment/create", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "name": f"Task Intake {agent_id}",
        "runtime_type": "mock",
        "scopes": ["agents:heartbeat", "tasks:read", "agent_plans:read", "agent_plans:write", "audit:write"],
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    if status != 201:
        raise RuntimeError(f"enrollment create failed: {status} {created}")
    return created["token"], created["token_id"]


def create_task(base_url: str, workspace_id: str, task_id: str, agent_id: str, title: str) -> None:
    status, body, _raw = http_json(base_url, "POST", "/api/tasks", {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "title": title,
        "description": "Operator task-intake smoke fixture.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "critical",
        "risk_level": "low",
        "acceptance_criteria": "Task must pass intake gates before worker execution.",
    })
    if status != 201:
        raise RuntimeError(f"task create failed: {status} {body}")


def create_verified_plan(base_url: str, workspace_id: str, token: str, agent_id: str, task_id: str, outputs: list[str]) -> str:
    status, plan, raw = http_json(base_url, "POST", "/api/agent-gateway/agent-plans", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "task_understanding": "Run the planned task only after operator intake confirms plan and knowledge gates.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks"],
        "proposed_files_to_change": ["scripts/operator_task_intake_smoke.py"],
        "risk_level": "low",
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "VERIFY"],
        "verification_plan": "Run operator_task_intake_smoke.py.",
        "rollback_plan": "Keep task planned if intake gates fail.",
        "status": "submitted",
    }, token=token)
    outputs.append(raw)
    if status != 201:
        raise RuntimeError(f"plan create failed: {status} {plan}")
    plan_id = (plan.get("agent_plan") or {}).get("plan_id")
    if not plan_id:
        raise RuntimeError(f"plan id missing: {plan}")
    status, verified, raw = http_json(base_url, "GET", f"/api/agent-gateway/agent-plans/{plan_id}/verify", token=token)
    outputs.append(raw)
    if status != 200 or (verified.get("verification") or {}).get("pass") is not True:
        raise RuntimeError(f"plan verify failed: {status} {verified}")
    return str(plan_id)


def find_item(payload: dict, task_id: str) -> dict:
    return next((item for item in payload.get("items") or [] if item.get("task_id") == task_id), {})


def main() -> int:
    base_url = os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787")
    db_path = Path(os.environ.get("AGENTOPS_DB_PATH") or DEFAULT_DB)
    stamp = now_stamp()
    workspace_id = "local-demo"
    agent_id = f"agt_task_intake_{stamp}"
    ready_task_id = f"tsk_task_intake_ready_{stamp}"
    blocked_task_id = f"tsk_task_intake_blocked_{stamp}"
    token_id = None
    outputs: list[str] = []
    failures: list[str] = []

    try:
        token, token_id = create_enrollment(base_url, workspace_id, agent_id)
        create_task(base_url, workspace_id, ready_task_id, agent_id, "Task intake ready fixture")
        create_task(base_url, workspace_id, blocked_task_id, agent_id, "Task intake blocked fixture")
        plan_id = create_verified_plan(base_url, workspace_id, token, agent_id, ready_task_id, outputs)

        before = db_fingerprint(db_path)
        status, payload, raw = http_json(base_url, "GET", "/api/operator/intake-checklist", query={"limit": 30}, token=None)
        outputs.append(raw)
        require(status == 200, f"intake checklist failed: {status} {payload}", failures)
        require(payload.get("operation") == "task_intake_checklist", f"operation mismatch: {payload}", failures)
        require((payload.get("safety") or {}).get("read_only") is True, f"intake should be read-only: {payload}", failures)
        ready_item = find_item(payload, ready_task_id)
        blocked_item = find_item(payload, blocked_task_id)
        require(ready_item.get("severity") == "ready", f"ready task not ready: {ready_item}", failures)
        require(ready_item.get("plan_id") == plan_id, f"ready task plan missing: {ready_item}", failures)
        require(blocked_item.get("severity") == "blocked", f"blocked task not blocked: {blocked_item}", failures)
        require("agent_plan" in set(blocked_item.get("failed_gate_ids") or []), f"blocked task did not fail agent_plan gate: {blocked_item}", failures)

        with tempfile.TemporaryDirectory(prefix="agentops-task-intake-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            proc = run_cli(base_url, ["operator", "intake-checklist", "--limit", "30"], env)
            outputs.extend([proc.stdout, proc.stderr])
            cli_payload = load_json(proc)
            require(proc.returncode == 0, f"CLI intake failed: {proc.stderr or proc.stdout}", failures)
            require(find_item(cli_payload, ready_task_id).get("severity") == "ready", f"CLI ready task mismatch: {cli_payload}", failures)
            require(find_item(cli_payload, blocked_task_id).get("severity") == "blocked", f"CLI blocked task mismatch: {cli_payload}", failures)

        status, action_plan, raw = http_json(base_url, "GET", "/api/operator/action-plan", query={"limit": 30})
        outputs.append(raw)
        require(status == 200, f"operator action-plan failed: {status} {action_plan}", failures)
        require("task_intake" in (action_plan.get("source_status") or {}), f"action plan missing task_intake source: {action_plan}", failures)
        require((action_plan.get("task_intake") or {}).get("operation") == "task_intake_checklist", f"action plan missing task_intake payload: {action_plan}", failures)

        after = db_fingerprint(db_path)
        if before is not None and after is not None:
            require(before == after, f"intake reads changed database fingerprint: before={before} after={after}", failures)
        require(not leaked_secret("\n".join(outputs)), "operator task intake leaked token-like material", failures)

        print(json.dumps({
            "ok": not failures,
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "ready_task_id": ready_task_id,
            "blocked_task_id": blocked_task_id,
            "plan_id": plan_id,
            "read_only": before == after if before is not None and after is not None else None,
            "secret_leaked": leaked_secret("\n".join(outputs)),
            "failures": failures,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not failures else 1
    finally:
        if token_id:
            http_json(base_url, "POST", "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


if __name__ == "__main__":
    raise SystemExit(main())
