#!/usr/bin/env python3
"""Verify lightweight operator loop-control and fast advance-loop readback."""

from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(text: str) -> dict:
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/dashboard/metrics", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def start_server(db_path: Path, port: int, log_path: Path) -> subprocess.Popen:
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


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=8)
    log_fh = getattr(proc, "_agentops_log_fh", None)
    if log_fh:
        log_fh.close()


def http_json(base_url: str, path: str, timeout: float = 5.0) -> tuple[int, dict]:
    req = urllib.request.Request(base_url + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def run_cli(args: list[str], base_url: str, outputs: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env.pop("AGENTOPS_API_KEY", None)
    proc = subprocess.run([str(CLI), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def fingerprint(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in [
                "runs",
                "tasks",
                "memories",
                "audit_logs",
                "operator_action_evaluations",
            ]
        }
        counts["operator_action_receipts"] = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action='operator.action_queue_receipt' AND entity_type='operator_action_receipts'"
        ).fetchone()[0]
        return counts


def seed_loop_artifact(db_path: Path, loop_id: str) -> None:
    now = "2026-06-23T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO tasks(task_id,workspace_id,title,description,status,priority,owner_agent_id,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"tsk_{loop_id}",
                "local-demo",
                "Loop control smoke",
                "Verify fast loop control.",
                "completed",
                "medium",
                "agt_operator",
                "Fast loop-control selects RECORD and proposes a reviewable loop memory.",
                "medium",
                0,
                now,
                now,
            ),
        )
        conn.execute(
            """INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,input_summary,output_summary,trace_id,approval_required,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"run_{loop_id}", "local-demo", f"tsk_{loop_id}", "agt_operator", "mock", "completed", now, now, "input omitted", "output omitted", f"trace_{loop_id}", 0, now),
        )
        conn.execute(
            """INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,uri,summary,created_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (f"art_{loop_id}", f"tsk_{loop_id}", f"run_{loop_id}", "loop_summary", "Loop artifact", f"loop://{loop_id}", "Loop evidence summary/hash only.", now),
        )
        conn.commit()


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    loop_id = f"loop_control_{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix="agentops-loop-control-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            before = fingerprint(db_path)
            status, api_payload = http_json(base_url, "/api/operator/loop-control?limit=5")
            after = fingerprint(db_path)
            require(status == 200, f"loop-control API status mismatch: {status}", failures)
            require(api_payload.get("operation") == "operator_loop_control", f"wrong operation: {api_payload}", failures)
            require(api_payload.get("safety", {}).get("read_only") is True, f"loop-control not read-only: {api_payload}", failures)
            require(before == after, f"loop-control mutated DB: {before} -> {after}", failures)
            selected = (((api_payload.get("work_order") or {}).get("advance_loop") or {}).get("selected_item") or {})
            require(selected.get("gate_id") == "runtime_doctor", f"global loop-control should select runtime doctor: {selected}", failures)

            cli = run_cli(["operator", "loop-control", "--limit", "5"], base_url, outputs)
            cli_payload = load_json(cli.stdout)
            require(cli.returncode == 0, f"loop-control CLI failed: {cli.stderr or cli.stdout}", failures)
            require((cli_payload.get("control_summary") or {}).get("copy_only") is True, f"CLI control not copy-only: {cli_payload}", failures)

            preview = run_cli(["operator", "advance-loop", "--fast-control", "--limit", "5"], base_url, outputs)
            preview_payload = load_json(preview.stdout)
            require(preview.returncode == 0, f"fast advance preview failed: {preview.stderr or preview.stdout}", failures)
            require(preview_payload.get("status") == "preview", f"fast advance should preview: {preview_payload}", failures)
            require((preview_payload.get("preview") or {}).get("gate_id") == "runtime_doctor", f"fast advance selected wrong gate: {preview_payload}", failures)
            require(fingerprint(db_path) == after, "fast advance preview mutated DB", failures)

            confirmed = run_cli(["operator", "advance-loop", "--fast-control", "--limit", "5", "--confirm-advance"], base_url, outputs, timeout=45)
            confirmed_payload = load_json(confirmed.stdout)
            post_confirm = fingerprint(db_path)
            require(confirmed.returncode == 0, f"fast advance confirm failed: {confirmed.stderr or confirmed.stdout}", failures)
            require(confirmed_payload.get("control_source") == "loop_control", f"confirm should use loop-control: {confirmed_payload}", failures)
            require(confirmed_payload.get("advanced") is True, f"fast advance did not advance: {confirmed_payload}", failures)
            require(post_confirm["operator_action_receipts"] >= after["operator_action_receipts"] + 1, f"receipt not recorded: {after} -> {post_confirm}", failures)
            require(post_confirm["operator_action_evaluations"] >= after["operator_action_evaluations"] + 1, f"receipt evaluation not recorded: {after} -> {post_confirm}", failures)
            require((confirmed_payload.get("control_readback") or {}).get("cache_bypassed") is True, f"fast control readback missing cache proof: {confirmed_payload}", failures)
            require((confirmed_payload.get("safety") or {}).get("live_execution_performed") is False, f"fast advance performed live execution: {confirmed_payload}", failures)

            seed_loop_artifact(db_path, loop_id)
            loop_preview = run_cli(["operator", "advance-loop", "--fast-control", "--loop-id", loop_id, "--limit", "5"], base_url, outputs)
            loop_preview_payload = load_json(loop_preview.stdout)
            require(loop_preview.returncode == 0, f"loop-scoped fast preview failed: {loop_preview.stderr or loop_preview.stdout}", failures)
            require((loop_preview_payload.get("preview") or {}).get("gate_id") == "record", f"loop-scoped preview should select RECORD: {loop_preview_payload}", failures)
            require("memory propose" in ((loop_preview_payload.get("preview") or {}).get("action_command") or ""), f"loop-scoped preview missing memory propose: {loop_preview_payload}", failures)

            policy_proc = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps({'loop_control': advance_loop_command_policy('agentops operator loop-control --limit 5', phase='action'), 'runtime_doctor': advance_loop_command_policy('agentops operator runtime-doctor --limit 5', phase='action'), 'memory_approve': advance_loop_command_policy('agentops memory approve --memory-id mem_x', phase='action')}))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([policy_proc.stdout, policy_proc.stderr])
            policy = load_json(policy_proc.stdout)
            require((policy.get("loop_control") or {}).get("allowed") is True, f"loop-control policy not allowed: {policy}", failures)
            require((policy.get("runtime_doctor") or {}).get("allowed") is True, f"runtime-doctor policy not allowed: {policy}", failures)
            require((policy.get("memory_approve") or {}).get("allowed") is False, f"memory approve must remain denied: {policy}", failures)
        finally:
            stop_server(server)
    combined = "\n".join(outputs)
    secret_leaked = any(pattern.search(combined) for pattern in SECRET_PATTERNS)
    require(not secret_leaked, "loop-control output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_loop_control_smoke",
        "loop_id": loop_id,
        "secret_leaked": secret_leaked,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
