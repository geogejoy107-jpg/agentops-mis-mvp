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
    no_knowledge_token_id = None
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

            status, evidence_report, raw = http_json(
                base_url,
                "/api/operator/evidence-report",
                workspace=workspace,
                query={"run_id": run_id, "limit": 5},
            )
            outputs.append(raw)
            report_item = (evidence_report.get("runs") or [{}])[0]
            report_knowledge = report_item.get("worker_knowledge_retrieval") or {}
            report_summary = evidence_report.get("summary") or {}
            report_checks = {item.get("id"): item for item in report_item.get("checks") or []}
            require(status == 200 and evidence_report.get("operation") == "operator_evidence_report", f"evidence report failed: {status} {evidence_report}", failures)
            require(report_knowledge.get("status") == "ready", f"evidence report missing worker knowledge readiness: {report_knowledge}", failures)
            require(report_knowledge.get("consumed_tool_calls") == 1, f"evidence report consumed count wrong: {report_knowledge}", failures)
            require(bool(report_knowledge.get("packet_hashes")), f"evidence report missing packet hashes: {report_knowledge}", failures)
            require(bool(report_knowledge.get("query_hashes")), f"evidence report missing query hashes: {report_knowledge}", failures)
            require(report_knowledge.get("raw_query_omitted") is True, f"evidence report raw query omission missing: {report_knowledge}", failures)
            require(report_knowledge.get("raw_content_omitted") is True, f"evidence report raw content omission missing: {report_knowledge}", failures)
            require((report_checks.get("worker_knowledge_retrieval") or {}).get("ok") is True, f"evidence report quality gate did not pass: {report_checks}", failures)
            require(int(report_summary.get("worker_runs") or 0) >= 1, f"evidence summary missing worker run count: {report_summary}", failures)
            require(int(report_summary.get("worker_knowledge_retrieval_ready") or 0) >= 1, f"evidence summary missing worker knowledge ready count: {report_summary}", failures)
            require(int(report_summary.get("worker_knowledge_retrieval_missing") or 0) == 0, f"evidence summary should not report missing worker knowledge: {report_summary}", failures)

            referenced_specs = db_json_field(db_path, "SELECT referenced_specs_json FROM agent_plans WHERE plan_id=?", (plan_id,))
            referenced_memories = db_json_field(db_path, "SELECT referenced_memories_json FROM agent_plans WHERE plan_id=?", (plan_id,))
            require(len(referenced_specs) >= 3, f"plan missing referenced specs: {referenced_specs}", failures)
            require(any(path in referenced_memories for path in worker_evidence.get("paths") or []), f"plan did not reference retrieved knowledge paths: {referenced_memories} evidence={worker_evidence}", failures)

            scoped_payload = {
                "worker_evidence": worker_evidence,
                "tool_args": tool_args,
                "rubric": rubric,
                "audit_meta": audit_meta,
                "report_knowledge": report_knowledge,
                "report_summary": report_summary,
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

            no_knowledge_agent_id = f"agt_worker_no_knowledge_{suffix}"
            status, no_knowledge_enrollment, raw = http_json(base_url, "/api/agent-gateway/enrollment/create", "POST", {
                "workspace_id": workspace,
                "agent_id": no_knowledge_agent_id,
                "name": "Worker Missing Knowledge Evidence Gate Smoke",
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
                ],
                "ttl_days": 1,
            })
            require(status == 201, f"no-knowledge enrollment failed: {status} {no_knowledge_enrollment}", failures)
            no_knowledge_token = no_knowledge_enrollment.get("token")
            no_knowledge_token_id = no_knowledge_enrollment.get("token_id")
            require(bool(no_knowledge_token), f"no-knowledge token missing: {no_knowledge_enrollment}", failures)

            status, missing_task, raw = http_json(base_url, "/api/agent-gateway/tasks", "POST", {
                "workspace_id": workspace,
                "title": f"Worker missing knowledge evidence task {suffix}",
                "description": "The worker can execute, but missing knowledge:read scope must fail the knowledge retrieval quality gate.",
                "acceptance_criteria": "Run/tool/audit evidence is written, while evaluation and operator evidence mark retrieval evidence unavailable.",
                "risk_level": "medium",
            }, token=no_knowledge_token, workspace=workspace)
            outputs.append(raw)
            missing_task_id = missing_task.get("task_id")
            require(status == 201 and bool(missing_task_id), f"missing-knowledge task create failed: {status} {missing_task}", failures)

            missing_worker = run_worker(base_url, no_knowledge_token or "", workspace, no_knowledge_agent_id, missing_task_id or "")
            outputs.extend([missing_worker.stdout, missing_worker.stderr])
            require(missing_worker.returncode == 0, f"missing-knowledge worker failed: {missing_worker.returncode} {missing_worker.stderr or missing_worker.stdout}", failures)
            missing_worker_payload = json.loads(missing_worker.stdout or "{}")
            missing_result = next((row for row in missing_worker_payload.get("results") or [] if row.get("processed")), {})
            missing_run_id = missing_result.get("run_id")
            missing_worker_evidence = missing_result.get("knowledge_retrieval_evidence") or {}
            require(bool(missing_run_id), f"missing-knowledge worker result missing run: {missing_worker_payload}", failures)
            require(missing_result.get("ok") is True, f"missing-knowledge adapter should still complete: {missing_result}", failures)
            require(missing_worker_evidence.get("consumed") is False, f"missing-knowledge evidence should not be consumed: {missing_worker_evidence}", failures)
            require(missing_worker_evidence.get("status") == "unavailable", f"missing-knowledge evidence should be unavailable: {missing_worker_evidence}", failures)
            require(missing_worker_evidence.get("raw_prompt_omitted") is True, f"missing-knowledge raw prompt omission missing: {missing_worker_evidence}", failures)
            require(missing_result.get("plan_evidence_pass") is not True, f"missing-knowledge manifest should not pass quality gate: {missing_result}", failures)

            status, missing_run_detail, raw = http_json(base_url, f"/api/runs/{missing_run_id}")
            outputs.append(raw)
            require(status == 200, f"missing-knowledge run detail failed: {status} {missing_run_detail}", failures)
            missing_tool = next((item for item in (missing_run_detail.get("tool_calls") or []) if item.get("tool_name") == "agent_worker.mock"), {})
            missing_tool_args = parse_json_field(missing_tool.get("normalized_args_json"))
            missing_eval = (missing_run_detail.get("evaluations") or [{}])[0]
            missing_rubric = parse_json_field(missing_eval.get("rubric_json") or missing_eval.get("rubric"))
            require(missing_tool_args.get("knowledge_retrieval_evidence_consumed") is False, f"missing-knowledge tool args should show no consumption: {missing_tool_args}", failures)
            require(missing_tool_args.get("knowledge_retrieval_status") == "unavailable", f"missing-knowledge tool status should be unavailable: {missing_tool_args}", failures)
            require(missing_eval.get("pass_fail") == "fail", f"missing-knowledge evaluation should fail: {missing_eval}", failures)
            require(missing_rubric.get("requires_knowledge_retrieval_evidence") is True, f"missing-knowledge rubric missing required evidence flag: {missing_rubric}", failures)
            require(missing_rubric.get("knowledge_retrieval_gate_pass") is False, f"missing-knowledge rubric should fail gate: {missing_rubric}", failures)
            require(missing_rubric.get("knowledge_retrieval_gate_status") == "unavailable", f"missing-knowledge rubric wrong status: {missing_rubric}", failures)
            require(missing_rubric.get("quality_gate_pass") is False, f"missing-knowledge quality gate should fail: {missing_rubric}", failures)

            status, missing_report, raw = http_json(
                base_url,
                "/api/operator/evidence-report",
                workspace=workspace,
                query={"run_id": missing_run_id, "limit": 5},
            )
            outputs.append(raw)
            missing_report_item = (missing_report.get("runs") or [{}])[0]
            missing_report_knowledge = missing_report_item.get("worker_knowledge_retrieval") or {}
            missing_report_summary = missing_report.get("summary") or {}
            missing_report_checks = {item.get("id"): item for item in missing_report_item.get("checks") or []}
            require(status == 200 and missing_report.get("operation") == "operator_evidence_report", f"missing-knowledge evidence report failed: {status} {missing_report}", failures)
            require(missing_report.get("status") in {"attention", "blocked"}, f"missing-knowledge report should not be ready: {missing_report}", failures)
            require(missing_report_knowledge.get("status") == "unavailable", f"missing-knowledge report should mark unavailable: {missing_report_knowledge}", failures)
            require((missing_report_checks.get("worker_knowledge_retrieval") or {}).get("ok") is False, f"missing-knowledge report quality gate should fail: {missing_report_checks}", failures)
            require(int(missing_report_summary.get("worker_knowledge_retrieval_unavailable") or 0) >= 1, f"missing-knowledge summary missing unavailable count: {missing_report_summary}", failures)

            missing_scoped_payload = {
                "worker_evidence": missing_worker_evidence,
                "tool_args": missing_tool_args,
                "rubric": missing_rubric,
                "report_knowledge": missing_report_knowledge,
                "report_summary": missing_report_summary,
            }
            missing_raw_key_hits = forbidden_raw_key_paths(missing_scoped_payload)
            require(not missing_raw_key_hits, f"raw fields leaked in missing-knowledge metadata: {missing_raw_key_hits}", failures)
            missing_leak_scope_text = "\n".join([
                missing_worker.stdout,
                missing_worker.stderr,
                json.dumps(missing_scoped_payload, ensure_ascii=False),
                json.dumps(missing_run_detail, ensure_ascii=False),
            ])
            missing_leak_labels = secret_leak_labels(missing_leak_scope_text)
            require(not missing_leak_labels, f"missing-knowledge smoke leaked token-like material categories: {missing_leak_labels}", failures)
        except Exception as exc:
            failures.append(f"unexpected exception: {type(exc).__name__}: {exc}")
        finally:
            if no_knowledge_token_id:
                try:
                    http_json(base_url, "/api/agent-gateway/enrollment/revoke", "POST", {"token_id": no_knowledge_token_id})
                except Exception:
                    pass
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
