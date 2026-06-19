#!/usr/bin/env python3
"""Verify a customer task can run through the real AgentOps worker loop."""
from __future__ import annotations

import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def http_json(method: str, base_url: str, path: str, payload: dict | None = None):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=180) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify customer worker task workflow.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    failures: list[str] = []

    status, result = http_json("POST", args.base_url, "/api/workflows/customer-worker-task", {
        "adapter": "mock",
        "title": "客户侧 Worker 闭环验收",
        "description": "以客户视角创建一个真实可执行的 MIS 任务，并要求本地 worker 写回账本证据。",
        "acceptance_criteria": "必须产生 run、tool call、evaluation、audit 和 customer_worker_result artifact。",
        "priority": "high",
        "risk_level": "medium",
        "selected_agent_ids": ["agt_worker_local"],
    })
    evidence = result.get("evidence") or {}
    require(status == 201, f"customer worker task status mismatch: {status} {result}", failures)
    require(result.get("provider") == "agentops-worker", f"wrong provider: {result}", failures)
    require(result.get("workflow") == "customer_worker_task", f"wrong workflow: {result}", failures)
    require(result.get("ok") is True, f"mock worker task did not complete: {result}", failures)
    require(result.get("dry_run") is False, f"mock worker task should be real ledger execution: {result}", failures)
    require(bool(result.get("task_id")), f"missing task id: {result}", failures)
    require(bool(result.get("run_id")), f"missing run id: {result}", failures)
    require(bool(result.get("artifact_id")), f"missing artifact id: {result}", failures)
    require(evidence.get("tool_calls", 0) >= 1, f"missing tool call evidence: {evidence}", failures)
    require(evidence.get("evaluations", 0) >= 1, f"missing evaluation evidence: {evidence}", failures)
    require(evidence.get("runtime_events", 0) >= 1, f"missing runtime event evidence: {evidence}", failures)
    require(evidence.get("audit_logs", 0) >= 1, f"missing audit evidence: {evidence}", failures)
    require(evidence.get("artifacts", 0) >= 1, f"missing artifact evidence: {evidence}", failures)

    if result.get("task_id"):
        status, task_detail = http_json("GET", args.base_url, f"/api/tasks/{result['task_id']}")
        require(status == 200, f"task detail failed: {status} {task_detail}", failures)
        require(any(row.get("artifact_id") == result.get("artifact_id") for row in task_detail.get("artifacts") or []), "task detail missing customer worker artifact", failures)
    if result.get("run_id"):
        status, run_detail = http_json("GET", args.base_url, f"/api/runs/{result['run_id']}")
        require(status == 200, f"run detail failed: {status} {run_detail}", failures)
        require(len(run_detail.get("tool_calls") or []) >= 1, "run detail missing tool call", failures)
        require(len(run_detail.get("evaluations") or []) >= 1, "run detail missing evaluation", failures)

    status, confirm_gate = http_json("POST", args.base_url, "/api/workflows/customer-worker-task", {
        "adapter": "hermes",
        "title": "Hermes customer worker confirm gate",
        "description": "This should plan the task but not execute live Hermes without confirmation.",
        "acceptance_criteria": "Must not run live without confirm_run.",
    })
    require(status == 201, f"confirm gate status mismatch: {status} {confirm_gate}", failures)
    require(confirm_gate.get("dry_run") is True, f"Hermes without confirm should be dry_run/planned: {confirm_gate}", failures)
    require(confirm_gate.get("reason") == "confirm_run_required_for_live_adapter", f"confirm gate reason missing: {confirm_gate}", failures)
    require(bool(confirm_gate.get("task_id")), f"confirm gate should still create planned task: {confirm_gate}", failures)

    serialized = json.dumps({"result": result, "confirm_gate": confirm_gate}, ensure_ascii=False)
    require("agtok_" not in serialized and "agtsess_" not in serialized and "sk-" not in serialized and "ntn_" not in serialized, "workflow output leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "task_id": result.get("task_id"),
        "run_id": result.get("run_id"),
        "artifact_id": result.get("artifact_id"),
        "evidence": evidence,
        "confirm_gate_task_id": confirm_gate.get("task_id"),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
