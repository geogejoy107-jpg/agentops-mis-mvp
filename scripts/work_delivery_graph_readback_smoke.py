#!/usr/bin/env python3
"""Verify the CLI/API work-delivery evidence graph readback for one run."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server.py"
CLI = ROOT / "scripts" / "agentops"

SECRET_PATTERNS = [
    re.compile(r"Authorization:\s*(Bearer|Basic|Token)\s+", re.IGNORECASE),
    re.compile(r"Bearer\s+(?!\\[REDACTED\\])[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"agtok_[A-Za-z0-9_-]{16,}"),
    re.compile(r"agtsess_[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9_-]{8,}"),
]


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(base_url + "/api/dashboard/metrics", timeout=1) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    return False


def start_server(db_path: Path, port: int, base_url: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    env["HERMES_ALLOW_REAL_RUN"] = "false"
    env["DIFY_ALLOW_REAL_UPLOAD"] = "false"
    return subprocess.Popen(
        [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_cli(base_url: str, args: list[str], outputs: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env["AGENTOPS_BASE_URL"] = base_url
    proc = subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    port = choose_port()
    base_url = f"http://127.0.0.1:{port}"
    server: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="agentops-work-delivery-graph-") as tmp:
        db_path = Path(tmp) / "agentops_work_delivery_graph.db"
        try:
            server = start_server(db_path, port, base_url)
            require(wait_ready(base_url, server), "isolated server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            workflow = run_cli(base_url, [
                "workflow",
                "customer-worker-task",
                "--adapter",
                "mock",
                "--title",
                "Work delivery graph readback smoke",
                "--description",
                "Create one safe mock customer-worker run and inspect it through the work delivery evidence graph.",
                "--acceptance",
                "Evidence graph must show task, agent, plan, run, tool, evaluation, artifact, audit and manifest counts.",
                "--selected-agent-id",
                "agt_worker_local",
            ], outputs)
            workflow_payload = load_json(workflow)
            run_id = workflow_payload.get("run_id")
            task_id = workflow_payload.get("task_id")
            require(workflow.returncode == 0, f"workflow failed: {workflow.stderr or workflow.stdout}", failures)
            require(workflow_payload.get("ok") is True, f"workflow not ok: {workflow_payload}", failures)
            require(bool(run_id and task_id), f"workflow missing run/task ids: {workflow_payload}", failures)

            evidence_graph = run_cli(base_url, ["run", "evidence-graph", "--run-id", str(run_id)], outputs)
            graph_payload = load_json(evidence_graph)
            counts = graph_payload.get("evidence_counts") or {}
            safety = graph_payload.get("safety") or {}
            require(evidence_graph.returncode == 0, f"evidence graph failed: {evidence_graph.stderr or evidence_graph.stdout}", failures)
            require(graph_payload.get("operation") == "work_delivery_graph_readback", f"wrong graph operation: {graph_payload}", failures)
            require(graph_payload.get("schema_version") == "work_delivery_graph_v1", f"schema version missing: {graph_payload}", failures)
            require(graph_payload.get("run_id") == run_id, f"run id mismatch: {graph_payload}", failures)
            require(graph_payload.get("task_id") == task_id, f"task id mismatch: {graph_payload}", failures)
            for key in ["tool_calls", "runtime_events", "evaluations", "artifacts", "audit_logs", "plan_evidence_manifests"]:
                require(int(counts.get(key) or 0) >= 1, f"evidence graph missing {key}: {counts}", failures)
            require(len(graph_payload.get("nodes") or []) >= 8, f"graph nodes missing: {graph_payload}", failures)
            require(len(graph_payload.get("edges") or []) >= 8, f"graph edges missing: {graph_payload}", failures)
            require(graph_payload.get("graph_hash"), f"graph hash missing: {graph_payload}", failures)
            require(safety.get("read_only") is True, f"read-only proof missing: {safety}", failures)
            require(safety.get("ledger_mutated") is False, f"ledger mutation proof missing: {safety}", failures)
            require(safety.get("live_execution_performed") is False, f"live execution proof missing: {safety}", failures)
            require(safety.get("raw_prompt_omitted") is True, f"raw prompt omission missing: {safety}", failures)
            require(safety.get("raw_response_omitted") is True, f"raw response omission missing: {safety}", failures)
            require(safety.get("token_omitted") is True, f"token omission missing: {safety}", failures)

            legacy_graph = run_cli(base_url, ["run", "graph", "--run-id", str(run_id)], outputs)
            legacy_payload = load_json(legacy_graph)
            require(legacy_graph.returncode == 0, f"legacy run graph failed: {legacy_graph.stderr or legacy_graph.stdout}", failures)
            require(legacy_payload.get("operation") == "run_graph", f"legacy graph operation changed: {legacy_payload}", failures)
            require("work_delivery_graph" not in legacy_payload, "legacy run graph should remain delegation-only", failures)

            require(not leaked("\n".join(outputs)), "work delivery graph smoke leaked token-like material", failures)
            print(json.dumps({
                "operation": "work_delivery_graph_readback_smoke",
                "ok": not failures,
                "failures": failures,
                "task_id": task_id,
                "run_id": run_id,
                "evidence_counts": counts,
                "graph_hash": graph_payload.get("graph_hash"),
                "legacy_graph_preserved": True,
                "secret_leaked": False,
                "safety": {
                    "isolated_db": True,
                    "live_execution_performed": False,
                    "token_omitted": True,
                },
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not failures else 1
        finally:
            if server and server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
