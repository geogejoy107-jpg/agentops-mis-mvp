#!/usr/bin/env python3
"""Verify agent worker execution consumes knowledge retrieval evidence safely."""
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
WORKER = ROOT / "scripts" / "agent_worker.py"
SERVER = ROOT / "server.py"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]
FORBIDDEN_RAW_KEYS = {"query", "snippet", "content", "prompt", "response", "token"}


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def http_json(
    base_url: str,
    path: str,
    method: str = "GET",
    body: dict | None = None,
    token: str | None = None,
    workspace: str | None = None,
    query: dict | None = None,
) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode({key: value for key, value in query.items() if value is not None}, doseq=True)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if workspace:
        headers["X-AgentOps-Workspace-Id"] = workspace
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = Request(url, data=data, method=method, headers=headers)
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


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _payload, _raw = http_json(base_url, "/api/agent-gateway/status")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.4)
    raise RuntimeError(f"server did not become ready: {last_error}")


def parse_json_field(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def forbidden_raw_key_paths(value, prefix: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_RAW_KEYS:
                hits.append(f"{prefix}.{key_text}")
            hits.extend(forbidden_raw_key_paths(child, f"{prefix}.{key_text}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(forbidden_raw_key_paths(child, f"{prefix}[{index}]"))
    return hits


def secret_leak_labels(text: str) -> list[str]:
    labels = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            labels.append(pattern.pattern)
    return labels


def run_worker(base_url: str, token: str, workspace: str, agent_id: str, task_id: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({
        "AGENTOPS_BASE_URL": base_url,
        "AGENTOPS_WORKSPACE_ID": workspace,
        "AGENTOPS_AGENT_ID": agent_id,
        "AGENTOPS_API_KEY": token,
    })
    return subprocess.run(
        [
            sys.executable,
            str(WORKER),
            "--once",
            "--adapter",
            "mock",
            "--task-id",
            task_id,
            "--no-enforce-intake",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def db_json_field(db_path: Path, sql: str, params: tuple = ()) -> list:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
    if not row:
        return []
    try:
        return json.loads(row[0] or "[]")
    except Exception:
        return []


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    suffix = stamp()
    workspace = f"ws_worker_knowledge_{suffix}"
    agent_id = f"agt_worker_knowledge_{suffix}"
    token_id = None
    proc: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="agentops-worker-knowledge-") as tmp:
        db_path = Path(tmp) / "agentops_worker_knowledge.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_BASE_URL"] = base_url
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env.pop("AGENTOPS_API_KEY", None)
        proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            status, enrollment, raw = http_json(base_url, "/api/agent-gateway/enrollment/create", "POST", {
                "workspace_id": workspace,
                "agent_id": agent_id,
                "name": "Worker Knowledge Evidence Consumption Smoke",
                "runtime_type": "mock",
                "scopes": [
                    "agents:write",
                    "agents:heartbeat",
                    "agent_plans:read",
                    "agent_plans:write",
                    "plan_evidence:read",
                    "plan_evidence:write",
                    "tasks:create",
                    "tasks:read",
                    "tasks:claim",
                    "runs:write",
                    "runtime_events:write",
                    "toolcalls:write",
                    "artifacts:write",
                    "memories:propose",
                    "evaluations:submit",
                    "audit:write",
                    "knowledge:read",
                    "knowledge:write",
                ],
                "ttl_days": 1,
            })
            require(status == 201, f"enrollment failed: {status} {enrollment}", failures)
            token = enrollment.get("token")
            token_id = enrollment.get("token_id")
            require(bool(token), f"token missing: {enrollment}", failures)

            status, indexed, raw = http_json(
                base_url,
                "/api/agent-gateway/knowledge/index",
                "POST",
                {"rebuild": True},
                token=token,
                workspace=workspace,
            )
            outputs.append(raw)
            require(status == 200 and int(indexed.get("indexed") or 0) >= 20, f"knowledge index failed: {status} {indexed}", failures)

            status, task, raw = http_json(base_url, "/api/agent-gateway/tasks", "POST", {
                "workspace_id": workspace,
                "title": f"Worker knowledge evidence task {suffix}",
                "description": "The worker must use the project method block and Agent Gateway evidence before writing the run ledger.",
                "acceptance_criteria": "Tool, evaluation, audit and worker result must include safe knowledge retrieval evidence identifiers.",
                "risk_level": "medium",
            }, token=token, workspace=workspace)
            outputs.append(raw)
            task_id = task.get("task_id")
            require(status == 201 and bool(task_id), f"task create failed: {status} {task}", failures)

            worker = run_worker(base_url, token, workspace, agent_id, task_id or "")
            outputs.extend([worker.stdout, worker.stderr])
            require(worker.returncode == 0, f"worker failed: {worker.returncode} {worker.stderr or worker.stdout}", failures)
            worker_payload = json.loads(worker.stdout or "{}")
            result = next((row for row in worker_payload.get("results") or [] if row.get("processed")), {})
            run_id = result.get("run_id")
            plan_id = result.get("plan_id")
            worker_evidence = result.get("knowledge_retrieval_evidence") or {}
            require(bool(run_id and plan_id), f"worker result missing run/plan: {worker_payload}", failures)
            require(worker_evidence.get("consumed") is True, f"worker result did not consume evidence: {worker_evidence}", failures)
            require(bool(worker_evidence.get("packet_hash")), f"worker result missing packet hash: {worker_evidence}", failures)
            require(bool(worker_evidence.get("query_hash")), f"worker result missing query hash: {worker_evidence}", failures)
            require(worker_evidence.get("query_omitted") is True, f"worker result query should be omitted: {worker_evidence}", failures)
            require(worker_evidence.get("raw_content_omitted") is True, f"worker result raw content should be omitted: {worker_evidence}", failures)

            status, run_detail, raw = http_json(base_url, f"/api/runs/{run_id}")
            outputs.append(raw)
            require(status == 200, f"run detail failed: {status} {run_detail}", failures)
            tool = next((item for item in (run_detail.get("tool_calls") or []) if item.get("tool_name") == "agent_worker.mock"), {})
            tool_args = parse_json_field(tool.get("normalized_args_json"))
            eval_row = (run_detail.get("evaluations") or [{}])[0]
            rubric = parse_json_field(eval_row.get("rubric_json") or eval_row.get("rubric"))
            require(tool_args.get("knowledge_retrieval_evidence_consumed") is True, f"tool args missing consumption proof: {tool_args}", failures)
            require(bool(tool_args.get("knowledge_retrieval_packet_hash")), f"tool args missing packet hash: {tool_args}", failures)
            require(bool(tool_args.get("knowledge_retrieval_query_hash")), f"tool args missing query hash: {tool_args}", failures)
            require((tool_args.get("knowledge_retrieval_omissions") or {}).get("raw_prompt_omitted") is True, f"tool args omission proof missing: {tool_args}", failures)
            require(rubric.get("knowledge_retrieval_evidence_consumed") is True, f"eval rubric missing consumption proof: {rubric}", failures)
            require(bool(rubric.get("knowledge_retrieval_packet_hash")), f"eval rubric missing packet hash: {rubric}", failures)

            status, audit_page, raw = http_json(base_url, "/api/audit", query={"limit": 120})
            outputs.append(raw)
            audit_rows = audit_page if isinstance(audit_page, list) else audit_page.get("audit_logs") or audit_page.get("items") or []
            audit_match = next((item for item in audit_rows if item.get("action") == "agent_worker.task_processed" and item.get("entity_id") == run_id), {})
            audit_meta = parse_json_field(audit_match.get("metadata_json"))
            require(audit_meta.get("knowledge_retrieval_evidence_consumed") is True, f"audit metadata missing consumption proof: {audit_meta}", failures)
            require(bool(audit_meta.get("knowledge_retrieval_packet_hash")), f"audit metadata missing packet hash: {audit_meta}", failures)

            referenced_specs = db_json_field(db_path, "SELECT referenced_specs_json FROM agent_plans WHERE plan_id=?", (plan_id,))
            referenced_memories = db_json_field(db_path, "SELECT referenced_memories_json FROM agent_plans WHERE plan_id=?", (plan_id,))
            require(len(referenced_specs) >= 3, f"plan missing referenced specs: {referenced_specs}", failures)
            require(any(path in referenced_memories for path in worker_evidence.get("paths") or []), f"plan did not reference retrieved knowledge paths: {referenced_memories} evidence={worker_evidence}", failures)

            scoped_payload = {
                "worker_evidence": worker_evidence,
                "tool_args": tool_args,
                "rubric": rubric,
                "audit_meta": audit_meta,
            }
            raw_key_hits = forbidden_raw_key_paths(scoped_payload)
            require(not raw_key_hits, f"raw fields leaked in evidence metadata: {raw_key_hits}", failures)
            leak_scope_text = "\n".join([
                worker.stdout,
                worker.stderr,
                json.dumps(scoped_payload, ensure_ascii=False),
                json.dumps(run_detail, ensure_ascii=False),
                json.dumps(audit_match, ensure_ascii=False),
            ])
            leak_labels = secret_leak_labels(leak_scope_text)
            require(not leak_labels, f"worker knowledge evidence smoke leaked token-like material categories: {leak_labels}", failures)
        except Exception as exc:
            failures.append(f"unexpected exception: {type(exc).__name__}: {exc}")
        finally:
            if token_id:
                try:
                    http_json(base_url, "/api/agent-gateway/enrollment/revoke", "POST", {"token_id": token_id})
                except Exception:
                    pass
            if proc:
                proc.terminate()
                try:
                    out, err = proc.communicate(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    out, err = proc.communicate(timeout=8)
                outputs.extend([out or "", err or ""])
    result = {
        "ok": not failures,
        "operation": "worker_knowledge_evidence_consumption_smoke",
        "workspace_id": workspace,
        "agent_id": agent_id,
        "failures": failures,
        "token_omitted": True,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
