#!/usr/bin/env python3
"""Measure AI Employees initial API fan-out and useful-panel readiness budget."""
from __future__ import annotations

import concurrent.futures
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
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
AI_EMPLOYEES_TSX = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "AIEmployees.tsx"

CORE_ENDPOINTS = [
    ("/api/dashboard/metrics", "dashboard"),
    ("/api/workers/status", "worker_status"),
    ("/api/workers/fleet", "worker_fleet"),
    ("/api/local/readiness", "local_readiness"),
    ("/api/operator/action-plan?limit=12", "operator_action_plan"),
    ("/api/operator/evidence-report?limit=8", "operator_evidence_report"),
    ("/api/agent-gateway/status", "agent_gateway_status"),
    ("/api/operator/health?limit=12", "operator_health"),
]
DEFERRED_ENDPOINTS = [
    ("/api/demo/readiness", "demo_readiness"),
    ("/api/workers/fleet/hygiene?limit=5", "worker_hygiene"),
    ("/api/workers/adapter-readiness", "adapter_readiness"),
    ("/api/operator/action-receipts?limit=8", "operator_action_receipts"),
    ("/api/security/production-readiness", "security_readiness"),
    ("/api/commander/integration-inbox?limit=20", "integration_inbox"),
    ("/api/commander/work-packages?limit=8", "commander_work_packages"),
    ("/api/review/queue?limit=12", "review_queue"),
    ("/api/workflows/customer-delivery-board?limit=8", "customer_delivery_board"),
    ("/api/workflows/hermes-openclaw-loop?limit=6", "loop_lane_readback"),
    ("/api/agent-gateway/enrollments", "agent_gateway_enrollments"),
    ("/api/agent-gateway/sessions", "agent_gateway_sessions"),
    ("/api/approvals", "approvals"),
    ("/api/workflows/jobs?limit=8", "workflow_jobs"),
    ("/api/workflows/jobs/stuck?threshold_sec=30&limit=8", "stuck_workflow_jobs"),
]
SCOPED_DEFERRED_ENDPOINTS = [
    ("/api/operator/loop-audit?limit=12", "operator_loop_audit"),
    ("/api/operator/handoff?limit=12", "operator_handoff"),
    ("/api/operator/health?limit=12", "operator_health"),
    ("/api/operator/loop-self-check?limit=12", "operator_loop_self_check"),
]
AGENT_ENDPOINTS = [
    ("/api/agents", "agents"),
]
ALL_ENDPOINTS = CORE_ENDPOINTS + DEFERRED_ENDPOINTS + SCOPED_DEFERRED_ENDPOINTS + AGENT_ENDPOINTS
CRITICAL_COMMAND_CENTER_LABELS = {"dashboard", "worker_status", "worker_fleet", "operator_health"}
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_get(base_url: str, path: str, label: str) -> dict:
    start = time.perf_counter()
    req = Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"}, method="GET")
    raw = ""
    status = 0
    ok = False
    error = None
    try:
        with urlopen(req, timeout=45) as res:
            raw = res.read().decode("utf-8", errors="replace")
            status = int(res.status)
            ok = 200 <= status < 300
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = int(exc.code)
        error = raw[:300]
    except Exception as exc:
        error = str(exc)
    duration_ms = int((time.perf_counter() - start) * 1000)
    return {
        "label": label,
        "path": path,
        "status": status,
        "ok": ok,
        "duration_ms": duration_ms,
        "raw_size": len(raw),
        "error": error,
    }


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            result = http_get(base_url, "/api/agent-gateway/status", "status")
            if result["ok"]:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def run_phase(base_url: str, endpoints: list[tuple[str, str]], max_workers: int = 12) -> tuple[list[dict], int]:
    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(http_get, base_url, path, label) for path, label in endpoints]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    label_order = {label: index for index, (_path, label) in enumerate(endpoints)}
    results.sort(key=lambda item: label_order.get(item["label"], 999))
    return results, elapsed_ms


def db_fingerprint(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        result = {}
        for table in ["agents", "tasks", "runs", "tool_calls", "runtime_events", "evaluations", "audit_logs", "approvals", "memories"]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return result
    finally:
        conn.close()


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def static_contract() -> dict:
    text = AI_EMPLOYEES_TSX.read_text(encoding="utf-8")
    return {
        "has_initial_daemon_log_prefetch": "WORKER_ADAPTERS.map(loadWorkerDaemonLogs)" in text,
        "has_lazy_daemon_log_effect": "if (!daemonLogsOpen) return;" in text and "loadSelectedDaemonLog(selectedLogAdapter)" in text,
        "has_panel_loader_manifest": "AI_EMPLOYEES_PANEL_LOADERS" in text and "AI_EMPLOYEES_SCOPED_PANEL_LOADERS" in text,
        "has_core_panel_loader_manifest": "AI_EMPLOYEES_CORE_PANEL_LOADERS" in text,
        "has_deferred_panel_loader_manifest": "AI_EMPLOYEES_DEFERRED_PANEL_LOADERS" in text,
        "has_deferred_loading_state": "setDeferredLoading(true)" in text and "deferredLoading" in text,
        "has_independent_panel_settling": "Promise.allSettled(loaders.map" in text and "panelLoadState" in text,
        "has_visible_panel_status": "panelStatusBadge" in text and "panelLoadReady" in text and "panelLoadUnavailable" in text,
        "has_panel_local_refresh": "const refreshPanel = useCallback" in text and "panelRefreshButton" in text and "localPanelRefreshing" in text,
        "has_panel_retry_evidence": all(marker in text for marker in ["attempts", "updated_at", "last_error", "panelDiagnosticJson", "panel_diagnostics_json", "token_omitted"]),
        "has_use_live_data_loader": "useLiveData(" in text,
        "has_monolithic_initial_loader": "const [metrics, demoReadiness, workerStatus" in text,
        "has_monolithic_scoped_loader": "const [operatorLoopAudit, operatorHandoff, operatorHealth, operatorLoopSelfCheck]" in text,
        "initial_loader_mentions": len(re.findall(r"load[A-Za-z0-9_]+\(", text[: text.find("const loadSelectedDaemonLog")])),
    }


def percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * pct))))
    return ordered[index]


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-ai-employees-perf-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_READ_MODEL_CACHE_TTL_SEC"] = "5"
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
            before = db_fingerprint(db_path)
            core_results, core_ms = run_phase(base_url, CORE_ENDPOINTS)
            deferred_results, deferred_ms = run_phase(base_url, DEFERRED_ENDPOINTS)
            scoped_results, scoped_ms = run_phase(base_url, SCOPED_DEFERRED_ENDPOINTS)
            agent_results, agent_ms = run_phase(base_url, AGENT_ENDPOINTS, max_workers=2)
            after = db_fingerprint(db_path)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    results = core_results + deferred_results + scoped_results + agent_results
    status_failures = [item for item in results if not item["ok"]]
    for item in status_failures:
        failures.append(f"{item['label']} failed: status={item['status']} error={item.get('error')}")
    duration_by_label = {item["label"]: int(item["duration_ms"]) for item in results}
    critical_ms = max(duration_by_label.get(label, 0) for label in CRITICAL_COMMAND_CENTER_LABELS)
    current_first_useful_panel_ms = core_ms
    background_panels_ms = deferred_ms + scoped_ms + agent_ms
    durations = [int(item["duration_ms"]) for item in results]
    contract = static_contract()
    request_paths = [path for path, _label in ALL_ENDPOINTS]
    daemon_log_prefetch_paths = [path for path in request_paths if "/workers/local/logs" in path]
    output = {
        "ok": not failures,
        "operation": "ai_employees_responsiveness_smoke",
        "page": "/workspace/agents",
        "initial_api_request_count": len(ALL_ENDPOINTS),
        "phase_counts": {
            "core_parallel": len(CORE_ENDPOINTS),
            "deferred_governance": len(DEFERRED_ENDPOINTS),
            "scoped_loop_deferred": len(SCOPED_DEFERRED_ENDPOINTS),
            "agents_deferred": len(AGENT_ENDPOINTS),
        },
        "budgets": {
            "max_initial_api_requests": 32,
            "critical_command_center_ms": 1000,
            "current_first_useful_panel_ms": 1500,
            "background_panels_ms": 2000,
        },
        "measurements": {
            "core_parallel_ms": core_ms,
            "deferred_governance_ms": deferred_ms,
            "scoped_loop_deferred_ms": scoped_ms,
            "agents_deferred_ms": agent_ms,
            "critical_command_center_ms": critical_ms,
            "current_first_useful_panel_ms": current_first_useful_panel_ms,
            "background_panels_ms": background_panels_ms,
            "endpoint_p95_ms": percentile(durations, 0.95),
            "slowest": sorted(results, key=lambda item: int(item["duration_ms"]), reverse=True)[:6],
        },
        "static_contract": contract,
        "daemon_log_prefetch_paths": daemon_log_prefetch_paths,
        "db_fingerprint_unchanged": before == after,
        "token_omitted": True,
        "failures": failures,
    }
    if len(ALL_ENDPOINTS) > output["budgets"]["max_initial_api_requests"]:
        failures.append(f"initial API request count too high: {len(ALL_ENDPOINTS)}")
    if critical_ms > output["budgets"]["critical_command_center_ms"]:
        failures.append(f"critical command-center API readiness too slow: {critical_ms}ms")
    if current_first_useful_panel_ms > output["budgets"]["current_first_useful_panel_ms"]:
        failures.append(f"current first useful panel budget exceeded: {current_first_useful_panel_ms}ms")
    if background_panels_ms > output["budgets"]["background_panels_ms"]:
        failures.append(f"background panel budget exceeded: {background_panels_ms}ms")
    if daemon_log_prefetch_paths or contract["has_initial_daemon_log_prefetch"]:
        failures.append("AI Employees initial load includes daemon log prefetch")
    if not contract["has_lazy_daemon_log_effect"]:
        failures.append("AI Employees lazy daemon log effect is missing")
    if not contract["has_panel_loader_manifest"] or not contract["has_independent_panel_settling"]:
        failures.append(f"AI Employees panels are not independently loadable: {contract}")
    if not contract["has_core_panel_loader_manifest"] or not contract["has_deferred_panel_loader_manifest"] or not contract["has_deferred_loading_state"]:
        failures.append(f"AI Employees panels are not split into core and deferred loaders: {contract}")
    if not contract["has_visible_panel_status"]:
        failures.append(f"AI Employees panel load state is not visible to operators: {contract}")
    if not contract["has_panel_local_refresh"]:
        failures.append(f"AI Employees key panels do not have local refresh controls: {contract}")
    if not contract["has_panel_retry_evidence"]:
        failures.append(f"AI Employees panel refreshes do not expose retry/error diagnostics: {contract}")
    if contract["has_use_live_data_loader"]:
        failures.append(f"AI Employees still uses one page-level useLiveData loader: {contract}")
    if contract["has_monolithic_initial_loader"] or contract["has_monolithic_scoped_loader"]:
        failures.append(f"AI Employees still has a monolithic panel loader: {contract}")
    if before != after:
        failures.append(f"responsiveness smoke mutated ledger: before={before} after={after}")
    output["failures"] = failures
    output["ok"] = not failures
    if leaked_secret(json.dumps(output, ensure_ascii=False)):
        output["ok"] = False
        output["secret_leaked"] = True
        output["failures"].append("secret-like value leaked in output")
    else:
        output["secret_leaked"] = False
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
