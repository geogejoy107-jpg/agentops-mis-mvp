#!/usr/bin/env python3
"""Verify worker-loop ledger plumbing with the mock adapter.

This is CI/offline fallback evidence. Product-readiness claims must use
customer_worker_real_runtime_acceptance.py with real Hermes/OpenClaw when
those runtimes are available and authorized.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TOKEN_PATTERNS = [
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]
ROOT = Path(__file__).resolve().parents[1]


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


def require_live_admission_packet(result: dict, adapter: str, failures: list[str]) -> None:
    packet = result.get("local_loop_admission_packet") or {}
    admission = packet.get("admission") or {}
    dispatch = ((packet.get("local_deployment") or {}).get("customer_worker_dispatch") or {})
    worker_start = ((packet.get("local_deployment") or {}).get("worker_start") or {})
    require(packet.get("operation") == "operator_local_loop_admission_packet", f"{adapter} admission packet missing: {packet}", failures)
    require(packet.get("adapter") == adapter, f"{adapter} admission adapter mismatch: {packet}", failures)
    require(admission.get("method_gate_count", 0) >= 8, f"{adapter} admission method gates missing: {packet}", failures)
    require(admission.get("live_dispatch_requires_confirm_run") is True, f"{adapter} admission confirm wall missing: {packet}", failures)
    require(dispatch.get("requires_confirm_run_flag") is True, f"{adapter} dispatch confirm flag missing: {packet}", failures)
    require("--confirm-run" in str(dispatch.get("command") or ""), f"{adapter} dispatch command missing confirm-run: {packet}", failures)
    require("--confirm-run" in str(worker_start.get("command") or ""), f"{adapter} worker start command missing confirm-run: {packet}", failures)
    require((packet.get("safety") or {}).get("read_only") is True, f"{adapter} admission read-only proof missing: {packet}", failures)
    require((packet.get("safety") or {}).get("ledger_mutated") is False, f"{adapter} admission ledger proof missing: {packet}", failures)
    require((packet.get("safety") or {}).get("server_executes_shell") is False, f"{adapter} admission server-shell proof missing: {packet}", failures)
    require(packet.get("live_execution_performed") is False, f"{adapter} admission live execution proof missing: {packet}", failures)
    require(packet.get("token_omitted") is True, f"{adapter} admission token proof missing: {packet}", failures)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urlopen(base_url.rstrip("/") + "/api/dashboard/metrics", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def start_isolated_server(db_path: Path, port: int, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
        cwd=ROOT,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._agentops_log_fh = log_fh  # type: ignore[attr-defined]
    return proc


def stop_isolated_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    log_fh = getattr(proc, "_agentops_log_fh", None)
    if log_fh:
        log_fh.close()


def run_checks(base_url: str) -> int:
    failures: list[str] = []

    status, result = http_json("POST", base_url, "/api/workflows/customer-worker-task", {
        "adapter": "mock",
        "title": "客户侧 Worker 闭环验收",
        "description": "以客户视角创建一个真实可执行的 MIS 任务，并要求本地 worker 写回账本证据。",
        "acceptance_criteria": "必须产生 run、tool call、evaluation、audit、memory candidate、delivery approval 和 customer_worker_result artifact。",
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
    worker_state = ((result.get("worker_result") or {}).get("state") or {})
    require(worker_state.get("base_url") == base_url.rstrip("/"), f"worker used wrong MIS base_url: {worker_state}", failures)
    require(evidence.get("tool_calls", 0) >= 1, f"missing tool call evidence: {evidence}", failures)
    require(evidence.get("evaluations", 0) >= 1, f"missing evaluation evidence: {evidence}", failures)
    require(evidence.get("runtime_events", 0) >= 1, f"missing runtime event evidence: {evidence}", failures)
    require(evidence.get("audit_logs", 0) >= 1, f"missing audit evidence: {evidence}", failures)
    require(evidence.get("artifacts", 0) >= 1, f"missing artifact evidence: {evidence}", failures)
    require(evidence.get("memories", 0) >= 1, f"missing memory candidate evidence: {evidence}", failures)
    require(evidence.get("approvals", 0) >= 1, f"missing delivery approval evidence: {evidence}", failures)

    if result.get("task_id"):
        status, task_detail = http_json("GET", base_url, f"/api/tasks/{result['task_id']}")
        require(status == 200, f"task detail failed: {status} {task_detail}", failures)
        require(any(row.get("artifact_id") == result.get("artifact_id") for row in task_detail.get("artifacts") or []), "task detail missing customer worker artifact", failures)
    if result.get("run_id"):
        status, run_detail = http_json("GET", base_url, f"/api/runs/{result['run_id']}")
        require(status == 200, f"run detail failed: {status} {run_detail}", failures)
        require(len(run_detail.get("tool_calls") or []) >= 1, "run detail missing tool call", failures)
        require(len(run_detail.get("evaluations") or []) >= 1, "run detail missing evaluation", failures)
        require(len(run_detail.get("approvals") or []) >= 1, "run detail missing delivery approval", failures)

    status, confirm_gate = http_json("POST", base_url, "/api/workflows/customer-worker-task", {
        "adapter": "hermes",
        "title": "Hermes customer worker confirm gate",
        "description": "This should plan the task but not execute live Hermes without confirmation.",
        "acceptance_criteria": "Must not run live without confirm_run.",
    })
    require(status == 201, f"confirm gate status mismatch: {status} {confirm_gate}", failures)
    require(confirm_gate.get("dry_run") is True, f"Hermes without confirm should be dry_run/planned: {confirm_gate}", failures)
    require(confirm_gate.get("reason") == "confirm_run_required_for_live_adapter", f"confirm gate reason missing: {confirm_gate}", failures)
    require(bool(confirm_gate.get("task_id")), f"confirm gate should still create planned task: {confirm_gate}", failures)
    require_live_admission_packet(confirm_gate, "hermes", failures)

    serialized = json.dumps({"result": result, "confirm_gate": confirm_gate}, ensure_ascii=False)
    require(not any(pattern.search(serialized) for pattern in TOKEN_PATTERNS), "workflow output leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "evidence_class": "ci_offline_fallback",
        "product_readiness_proof": False,
        "live_execution_performed": False,
        "task_id": result.get("task_id"),
        "run_id": result.get("run_id"),
        "artifact_id": result.get("artifact_id"),
        "worker_base_url": worker_state.get("base_url"),
        "evidence": evidence,
        "confirm_gate_task_id": confirm_gate.get("task_id"),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify customer worker task workflow.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--isolated-fixture", action="store_true", help="Run against a temporary server and SQLite database.")
    args = parser.parse_args()
    if args.isolated_fixture:
        with tempfile.TemporaryDirectory(prefix="agentops-customer-worker-isolated-") as tmp:
            tmp_path = Path(tmp)
            port = free_port()
            base_url = f"http://127.0.0.1:{port}"
            proc = start_isolated_server(tmp_path / "agentops_mis.db", port, tmp_path / "server.log")
            try:
                wait_for_server(base_url)
                return run_checks(base_url)
            finally:
                stop_isolated_server(proc)
    return run_checks(args.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
