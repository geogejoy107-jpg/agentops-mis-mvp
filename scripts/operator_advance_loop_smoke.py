#!/usr/bin/env python3
"""Verify the bounded CLI loop runner advances one safe action and records a receipt."""

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
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(text: str) -> dict:
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return {}


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


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
            time.sleep(0.3)
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


def run_cli(args: list[str], base_url: str, outputs: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env.pop("AGENTOPS_API_KEY", None)
    proc = subprocess.run([str(CLI), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def db_counts(db_path: Path, loop_id: str) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        memories = conn.execute(
            "SELECT review_status, COUNT(*) AS c FROM memories WHERE source_ref=? AND memory_type='loop_record' GROUP BY review_status",
            (f"loop://{loop_id}",),
        ).fetchall()
        receipts = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt' AND metadata_json LIKE ?",
            (f"%advance_loop:record%",),
        ).fetchone()
        evaluations = conn.execute(
            "SELECT COUNT(*) AS c FROM operator_action_evaluations",
        ).fetchone()
    return {
        "memories": {row["review_status"]: int(row["c"] or 0) for row in memories},
        "advance_receipts": int(receipts["c"] if receipts else 0),
        "evaluations": int(evaluations["c"] if evaluations else 0),
    }


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    loop_id = f"loop_advance_{uuid.uuid4().hex[:10]}"
    with tempfile.TemporaryDirectory(prefix="agentops-advance-loop-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            workflow = run_cli([
                "workflow",
                "hermes-openclaw-loop",
                "--topic",
                "Advance one safe RECORD action through the bounded operator runner.",
                "--loop-id",
                loop_id,
                "--rounds",
                "1",
                "--request-timeout",
                "5",
            ], base_url, outputs)
            workflow_payload = load_json(workflow.stdout)
            require(workflow.returncode == 0 and workflow_payload.get("ok") is True, f"loop workflow failed: {workflow.stderr or workflow.stdout}", failures)

            before = db_counts(db_path, loop_id)
            first_audit = run_cli(["operator", "loop-audit", "--loop-id", loop_id, "--limit", "10"], base_url, outputs)
            first_payload = load_json(first_audit.stdout)
            record_step = next((step for step in first_payload.get("steps") or [] if step.get("id") == "record"), {})
            require(first_payload.get("status") == "attention", f"loop should require RECORD before advance: {first_payload}", failures)
            require(record_step.get("status") == "attention", f"record gate should need attention: {record_step}", failures)

            preview = run_cli(["operator", "advance-loop", "--loop-id", loop_id, "--limit", "10"], base_url, outputs)
            preview_payload = load_json(preview.stdout)
            after_preview = db_counts(db_path, loop_id)
            require(preview.returncode == 0, f"advance preview failed: {preview.stderr or preview.stdout}", failures)
            require(preview_payload.get("status") == "preview", f"advance should default to preview: {preview_payload}", failures)
            require((preview_payload.get("preview") or {}).get("gate_id") == "record", f"advance should select record gate: {preview_payload}", failures)
            require(after_preview == before, f"advance preview mutated db: {before} -> {after_preview}", failures)

            advanced = run_cli(["operator", "advance-loop", "--loop-id", loop_id, "--limit", "10", "--confirm-advance"], base_url, outputs)
            advanced_payload = load_json(advanced.stdout)
            after_advance = db_counts(db_path, loop_id)
            require(advanced.returncode == 0, f"advance confirm CLI failed: {advanced.stderr or advanced.stdout}", failures)
            require(advanced_payload.get("operation") == "operator_advance_loop", f"advance operation mismatch: {advanced_payload}", failures)
            require(advanced_payload.get("advanced") is True, f"advance did not execute: {advanced_payload}", failures)
            require(advanced_payload.get("status") == "advanced", f"advance should finish verified: {advanced_payload}", failures)
            require((advanced_payload.get("preview") or {}).get("gate_id") == "record", f"advanced wrong gate: {advanced_payload}", failures)
            require((advanced_payload.get("action_result") or {}).get("ok") is True, f"advance action failed: {advanced_payload}", failures)
            require((advanced_payload.get("verify_result") or {}).get("ok") is True, f"advance verify failed: {advanced_payload}", failures)
            require((advanced_payload.get("safety") or {}).get("ledger_mutated") is True, f"advance should record receipt: {advanced_payload}", failures)
            require((advanced_payload.get("safety") or {}).get("live_execution_performed") is False, f"advance must not run live work: {advanced_payload}", failures)
            require(after_advance["memories"].get("candidate", 0) == 1, f"advance should propose one loop memory candidate: {after_advance}", failures)
            require(after_advance["memories"].get("approved", 0) == 0, f"advance must not approve memory: {after_advance}", failures)
            require(after_advance["advance_receipts"] >= before["advance_receipts"] + 1, f"advance receipt missing: {before} -> {after_advance}", failures)
            require(after_advance["evaluations"] >= before["evaluations"] + 1, f"advance receipt evaluation missing: {before} -> {after_advance}", failures)

            review = run_cli(["review", "queue", "--limit", "20"], base_url, outputs)
            review_payload = load_json(review.stdout)
            require(review.returncode == 0, f"review queue failed: {review.stderr or review.stdout}", failures)
            require(any(item.get("item_type") == "memory_candidate" and item.get("kind") == "loop_record" for item in review_payload.get("review_items") or []), f"loop memory candidate missing from review queue: {review_payload}", failures)

            unsafe_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.agentops import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops memory approve --memory-id mem_x', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([unsafe_policy.stdout, unsafe_policy.stderr])
            unsafe_payload = load_json(unsafe_policy.stdout)
            require(unsafe_payload.get("allowed") is False, f"unsafe memory approve should be rejected: {unsafe_payload}", failures)
        finally:
            stop_server(server)
    secret_leaked = leaked("\n".join(outputs))
    require(not secret_leaked, "advance-loop output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_advance_loop_smoke",
        "loop_id": loop_id,
        "secret_leaked": secret_leaked,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
