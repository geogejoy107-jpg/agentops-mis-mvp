#!/usr/bin/env python3
"""Verify local ledger list pagination keeps legacy array responses compatible."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
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


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str, query: dict | None = None) -> tuple[int, object, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode({key: value for key, value in query.items() if value is not None})
    req = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(req, timeout=30) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw), raw
        except Exception:
            return exc.code, {"raw": raw}, raw


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _, _ = http_json(base_url, "/api/agent-gateway/status")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def seed_ledger_rows(db_path: Path, stamp: str) -> dict:
    workspace_id = f"ws_pagination_{stamp}"
    agent_id = f"agt_pagination_{stamp}"
    task_id = f"tsk_pagination_{stamp}"
    run_ids: list[str] = []
    tool_ids: list[str] = []
    audit_ids: list[str] = []
    base_time = dt.datetime(2026, 6, 22, 12, 0, tzinfo=dt.timezone.utc)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        now = base_time.isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO users(user_id,name,email,role,created_at)
            VALUES(?,?,?,?,?)""",
            ("usr_pagination", "Pagination Smoke", "pagination@example.local", "admin", now),
        )
        conn.execute(
            """INSERT OR REPLACE INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (agent_id, "Pagination Agent", "Verifier", "Ledger pagination verifier.", "mock", "mock", "mock", "idle", "worker", "[]", 0, "usr_pagination", now, now),
        )
        conn.execute(
            """INSERT OR REPLACE INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,status,priority,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (task_id, workspace_id, "Ledger pagination smoke", "Seed rows for paginated ledger APIs.", "usr_pagination", agent_id, "completed", "medium", "Pagination APIs return bounded pages.", "low", 0, now, now),
        )
        for index in range(12):
            created_at = (base_time + dt.timedelta(seconds=index)).isoformat()
            run_id = f"run_page_{stamp}_{index:02d}"
            tool_id = f"tool_page_{stamp}_{index:02d}"
            audit_id = f"aud_page_{stamp}_{index:02d}"
            run_ids.append(run_id)
            tool_ids.append(tool_id)
            audit_ids.append(audit_id)
            conn.execute(
                """INSERT OR REPLACE INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, workspace_id, task_id, agent_id, "mock", "completed", created_at, created_at, 10, f"input {index}", f"output {index}", "mock", "mock", 0, 0, 0, 0, created_at),
            )
            conn.execute(
                """INSERT OR REPLACE INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,started_at,ended_at,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tool_id, run_id, agent_id, "pagination.tool", "v1", "custom", "{}", None, "low", "completed", f"tool {index}", created_at, created_at, created_at),
            )
            conn.execute(
                """INSERT OR REPLACE INTO audit_logs(audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (audit_id, "system", "pagination-smoke", "pagination.seed", "run", run_id, None, None, json.dumps({"index": index}), f"hash_{index}", created_at),
            )
        conn.commit()
    return {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "run_ids": run_ids,
        "tool_ids": tool_ids,
        "audit_ids": audit_ids,
    }


def page_ids(payload: object, key: str, id_key: str) -> list[str]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get(key) or payload.get("items") or []
    else:
        rows = []
    return [str(row.get(id_key) or "") for row in rows if isinstance(row, dict)]


def validate_page(payload: object, key: str, expected_total: int, expected_returned: int, failures: list[str]) -> None:
    require(isinstance(payload, dict), f"{key} page payload should be object: {payload}", failures)
    data = payload if isinstance(payload, dict) else {}
    page = data.get("page") or {}
    require(page.get("total", 0) >= expected_total, f"{key} total too low: {page}", failures)
    require(page.get("returned") == expected_returned, f"{key} returned wrong: {page}", failures)
    require((data.get("safety") or {}).get("read_only") is True, f"{key} safety missing: {payload}", failures)
    require(data.get("token_omitted") is True, f"{key} token omission missing: {payload}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    stamp = now_stamp()
    with tempfile.TemporaryDirectory(prefix="agentops-ledger-pagination-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env.pop("AGENTOPS_API_KEY", None)
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            seeded = seed_ledger_rows(db_path, stamp)

            status, legacy_runs, raw = http_json(base_url, "/api/runs", {"agent_id": seeded["agent_id"], "limit": 4})
            outputs.append(raw)
            require(status == 200 and isinstance(legacy_runs, list), f"legacy runs list failed: {status} {legacy_runs}", failures)
            require(len(legacy_runs) == 4, f"legacy runs limit ignored: {legacy_runs}", failures)

            status, runs_page, raw = http_json(base_url, "/api/runs", {"agent_id": seeded["agent_id"], "limit": 5, "offset": 5, "include_page": "true"})
            outputs.append(raw)
            validate_page(runs_page, "runs", 12, 5, failures)
            run_page_ids = page_ids(runs_page, "runs", "run_id")
            require(seeded["run_ids"][6] in run_page_ids, f"runs offset page missing expected row: {run_page_ids}", failures)

            status, tool_page, raw = http_json(base_url, "/api/tool-calls", {"agent_id": seeded["agent_id"], "limit": 6, "offset": 6, "include_page": "true"})
            outputs.append(raw)
            validate_page(tool_page, "tool_calls", 12, 6, failures)
            tool_page_ids = page_ids(tool_page, "tool_calls", "tool_call_id")
            require(seeded["tool_ids"][5] in tool_page_ids, f"tool offset page missing expected row: {tool_page_ids}", failures)

            status, audit_page, raw = http_json(base_url, "/api/audit", {"limit": 7, "offset": 7, "include_page": "true"})
            outputs.append(raw)
            validate_page(audit_page, "audit_logs", 12, 7, failures)
            audit_page_ids = page_ids(audit_page, "audit_logs", "audit_id")
            require(any(audit_id in audit_page_ids for audit_id in seeded["audit_ids"]), f"audit offset page missing seeded rows: {audit_page_ids}", failures)

            status, legacy_audit, raw = http_json(base_url, "/api/audit")
            outputs.append(raw)
            require(status == 200 and isinstance(legacy_audit, list), f"legacy audit list failed: {status} {legacy_audit}", failures)
            require(len(legacy_audit) <= 200, f"legacy audit default cap missing: {len(legacy_audit)}", failures)
            live_api = (ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts").read_text(encoding="utf-8")
            require('ledgerListPath("/runs", query, 100)' in live_api, "UI runs loader does not use bounded ledger pagination", failures)
            require('ledgerListPath("/tool-calls", "", 150)' in live_api, "UI tool-call loader does not use bounded ledger pagination", failures)
            require('ledgerListPath("/audit", "", 150)' in live_api, "UI audit loader does not use bounded ledger pagination", failures)
            require(not leaked_secret("\n".join(outputs)), "ledger pagination smoke leaked token-like material", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])

    result = {
        "ok": not failures,
        "operation": "ledger_pagination_smoke",
        "failures": failures,
        "secret_leaked": leaked_secret("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
