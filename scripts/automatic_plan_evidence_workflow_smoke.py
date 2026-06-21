#!/usr/bin/env python3
"""Verify worker/customer-worker paths automatically create verified plan evidence."""
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
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SERVER = ROOT / "server.py"
WORKER = ROOT / "scripts" / "agent_worker.py"
SEED_EXPORTS = [
    ROOT / "artifacts" / "sample_export_runs.json",
    ROOT / "artifacts" / "sample_export_memories.json",
]
SECRET_RE = re.compile(r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,})")


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def snapshot_seed_exports() -> dict[Path, str | None]:
    return {path: path.read_text(encoding="utf-8") if path.exists() else None for path in SEED_EXPORTS}


def restore_seed_exports(snapshot: dict[Path, str | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        else:
            path.write_text(content, encoding="utf-8")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def run_cli(args: list[str], base_url: str, agent_id: str, workspace_id: str, outputs: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_AGENT_ID"] = agent_id
    env["AGENTOPS_WORKSPACE_ID"] = workspace_id
    proc = subprocess.run([str(CLI), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def run_worker(base_url: str, agent_id: str, workspace_id: str, outputs: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(WORKER),
            "--once",
            "--adapter",
            "mock",
            "--agent-id",
            agent_id,
            "--workspace-id",
            workspace_id,
            "--base-url",
            base_url,
            "--no-enforce-intake",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=80,
        check=False,
    )
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict, str]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method != "GET" else None
    req = urllib.request.Request(base_url + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body, raw


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout: float = 20.0) -> bool:
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
    return subprocess.Popen(
        [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def db_count(db_path: Path, sql: str, params: tuple = ()) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row[0] if row else 0)


def main() -> int:
    suffix = stamp()
    port = choose_port()
    base_url = f"http://127.0.0.1:{port}"
    workspace_id = f"ws_auto_plan_{suffix}"
    worker_agent_id = f"agt_auto_worker_{suffix}"
    worker_task_id = f"tsk_auto_worker_{suffix}"
    failures: list[str] = []
    outputs: list[str] = []
    seed_snapshot = snapshot_seed_exports()
    server: subprocess.Popen[str] | None = None

    with tempfile.TemporaryDirectory(prefix="agentops-auto-plan-evidence-") as tmp:
        db_path = Path(tmp) / "agentops_auto_plan_evidence.db"
        try:
            server = start_server(db_path, port, base_url)
            require(wait_ready(base_url, server), "isolated server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            register = run_cli(["agent", "register", "--id", worker_agent_id, "--name", "Automatic Worker Smoke", "--role", "Builder", "--runtime", "mock"], base_url, worker_agent_id, workspace_id, outputs)
            require(register.returncode == 0, f"agent register failed: {register.stderr or register.stdout}", failures)

            task = run_cli([
                "task",
                "create",
                "--task-id",
                worker_task_id,
                "--title",
                "Automatic worker plan evidence smoke",
                "--description",
                "A normal worker loop must create agent_plan and verified plan_evidence_manifest evidence automatically.",
                "--owner-agent-id",
                worker_agent_id,
                "--requester-id",
                "usr_founder",
                "--acceptance",
                "Worker output includes verified plan evidence manifest.",
                "--risk",
                "medium",
            ], base_url, worker_agent_id, workspace_id, outputs)
            require(task.returncode == 0, f"task create failed: {task.stderr or task.stdout}", failures)

            worker = run_worker(base_url, worker_agent_id, workspace_id, outputs)
            worker_payload = load_json(worker)
            worker_result = next((row for row in worker_payload.get("results") or [] if row.get("processed")), {})
            run_id = worker_result.get("run_id")
            require(worker.returncode == 0 and worker_payload.get("ok") is True, f"worker failed: {worker.stderr or worker.stdout}", failures)
            require(worker_result.get("plan_id"), f"worker result missing plan_id: {worker_payload}", failures)
            require(worker_result.get("plan_evidence_manifest_id"), f"worker result missing manifest id: {worker_payload}", failures)
            require(worker_result.get("plan_evidence_status") == "verified", f"worker manifest not verified: {worker_payload}", failures)
            require(worker_result.get("plan_evidence_pass") is True, f"worker manifest did not pass: {worker_payload}", failures)
            require(db_count(db_path, "SELECT COUNT(*) FROM agent_plans WHERE task_id=? AND agent_id=?", (worker_task_id, worker_agent_id)) >= 1, "worker did not persist an agent_plan", failures)
            require(db_count(db_path, "SELECT COUNT(*) FROM plan_evidence_manifests WHERE run_id=? AND status='verified'", (run_id,)) >= 1, "worker did not persist a verified manifest", failures)

            status, direct_dispatch, raw = http_json("POST", base_url, "/api/workers/local/dispatch-once", {
                "adapter": "mock",
                "title": "Direct worker dispatch evidence summary",
                "description": "UI direct dispatch must surface Agent Plan, intake and plan evidence ledger proof.",
                "acceptance_criteria": "Dispatch result includes top-level plan and manifest evidence summary.",
            })
            outputs.append(raw)
            direct_evidence = direct_dispatch.get("evidence") or {}
            direct_counts = direct_evidence.get("evidence_counts") or {}
            require(status == 201, f"direct worker dispatch failed: {status} {direct_dispatch}", failures)
            require(direct_dispatch.get("ok") is True, f"direct dispatch not ok: {direct_dispatch}", failures)
            require(direct_dispatch.get("run_id"), f"direct dispatch missing top-level run_id: {direct_dispatch}", failures)
            require(direct_dispatch.get("agent_plan_id"), f"direct dispatch missing top-level agent_plan_id: {direct_dispatch}", failures)
            require(direct_dispatch.get("plan_evidence_manifest_id"), f"direct dispatch missing top-level manifest id: {direct_dispatch}", failures)
            require(direct_dispatch.get("plan_evidence_pass") is True, f"direct dispatch manifest did not pass: {direct_dispatch}", failures)
            require(direct_evidence.get("agent_plan_verified") is True, f"direct dispatch evidence missing verified plan: {direct_evidence}", failures)
            require((direct_evidence.get("intake") or {}).get("severity") in {"ready", "attention"}, f"direct dispatch intake summary missing: {direct_evidence}", failures)
            require(direct_counts.get("plan_evidence_manifests", 0) >= 1, f"direct dispatch evidence counts missing manifest: {direct_counts}", failures)

            status, workflow, raw = http_json("POST", base_url, "/api/workflows/customer-worker-task", {
                "adapter": "mock",
                "title": "Automatic customer worker delivery evidence",
                "description": "Customer workflow must verify plan evidence before creating delivery approval.",
                "acceptance_criteria": "Plan evidence manifest is verified before approval exists.",
                "priority": "high",
                "risk_level": "medium",
                "worker_agent_id": f"agt_customer_auto_{suffix}",
            })
            outputs.append(raw)
            evidence = workflow.get("evidence") or {}
            approval_id = workflow.get("approval_id")
            customer_run_id = workflow.get("run_id")
            customer_manifest_id = workflow.get("plan_evidence_manifest_id")
            require(status == 201, f"customer workflow failed: {status} {workflow}", failures)
            require(workflow.get("ok") is True, f"customer workflow not ok: {workflow}", failures)
            require(workflow.get("plan_id"), f"customer workflow missing plan_id: {workflow}", failures)
            require(customer_manifest_id, f"customer workflow missing manifest id: {workflow}", failures)
            require(workflow.get("plan_evidence_status") == "verified", f"customer manifest not verified: {workflow}", failures)
            require(workflow.get("plan_evidence_pass") is True, f"customer manifest did not pass: {workflow}", failures)
            require(evidence.get("plan_evidence_manifests", 0) >= 1, f"customer evidence missing manifest count: {evidence}", failures)
            require(approval_id and db_count(db_path, "SELECT COUNT(*) FROM approvals WHERE approval_id=? AND run_id=?", (approval_id, customer_run_id)) == 1, f"delivery approval missing after verified manifest: {workflow}", failures)

            status, approved, raw = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
            outputs.append(raw)
            require(status == 200 and approved.get("decision") == "approved", f"approval should pass after automatic manifest: {status} {approved}", failures)

            status, board, raw = http_json("GET", base_url, "/api/workflows/customer-delivery-board?limit=10")
            outputs.append(raw)
            delivery = next((row for row in board.get("deliveries") or [] if row.get("run_id") == customer_run_id), {})
            gate = delivery.get("delivery_approval_gate") or {}
            summary = board.get("summary") or {}
            require(status == 200, f"delivery board failed: {status} {board}", failures)
            require(gate.get("pass") is True and gate.get("manifest_id") == customer_manifest_id, f"board did not surface verified manifest: {delivery}", failures)
            require(summary.get("verified_plan_evidence_manifests", 0) >= 1, f"board summary missing verified manifest count: {summary}", failures)
            require(not SECRET_RE.search("\n".join(outputs)), "automatic plan evidence smoke leaked token-like material", failures)
        except Exception as exc:
            failures.append(f"unexpected exception: {type(exc).__name__}: {exc}")
        finally:
            if server:
                server.terminate()
                try:
                    out, err = server.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    out, err = server.communicate(timeout=5)
                outputs.extend([out or "", err or ""])
            restore_seed_exports(seed_snapshot)

    print(json.dumps({
        "ok": not failures,
        "failures": failures,
        "base_url": base_url,
        "worker_task_id": worker_task_id,
        "secret_leaked": False if not SECRET_RE.search("\n".join(outputs)) else True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
