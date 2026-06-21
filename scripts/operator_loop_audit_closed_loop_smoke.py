#!/usr/bin/env python3
"""Verify loop-audit RECORD closure from loop run to approved loop memory."""

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
RUNTIME_DIR = ROOT / ".agentops_runtime" / "loops"
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
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/dashboard/metrics", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.2)
    raise RuntimeError(f"server did not become ready: {last_error}")


def start_server(db_path: Path, port: int, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
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
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    log_fh = getattr(proc, "_agentops_log_fh", None)
    if log_fh:
        log_fh.close()


def run_cli(args: list[str], base_url: str, outputs: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env.pop("AGENTOPS_API_KEY", None)
    proc = subprocess.run([str(CLI), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def record_step(payload: dict) -> dict:
    for step in payload.get("steps") or []:
        if step.get("id") == "record":
            return step
    return {}


def loop_runtime_paths(loop_id: str) -> list[Path]:
    return [RUNTIME_DIR / f"{loop_id}{suffix}" for suffix in [".jsonl", ".audit.jsonl", ".next_action.json"]]


def count_loop_records(db_path: Path, loop_id: str) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE source_ref=? AND memory_type='loop_record'",
            (f"loop://{loop_id}",),
        ).fetchone()
    return int(row[0] if row else 0)


def seed_legacy_memory_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE memories (
                memory_id TEXT PRIMARY KEY,
                scope TEXT NOT NULL CHECK(scope IN ('task','project','org')),
                memory_type TEXT NOT NULL CHECK(memory_type IN ('policy','sop','decision','commitment','risk','failure_case','project_context','customer_preference','agent_lesson','artifact_summary')),
                canonical_text TEXT NOT NULL,
                source_type TEXT NOT NULL CHECK(source_type IN ('chat','email','meeting','github','notion','run_log','manual')),
                source_ref TEXT,
                project_id TEXT,
                task_id TEXT,
                agent_id TEXT,
                confidence REAL NOT NULL DEFAULT 0.5,
                review_status TEXT NOT NULL CHECK(review_status IN ('candidate','approved','rejected','stale','superseded')),
                owner_user_id TEXT,
                ttl_review_due_at TEXT,
                supersedes_memory_id TEXT,
                access_tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO memories(memory_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
            VALUES('mem_legacy_loop_smoke','project','artifact_summary','Legacy memory row should survive loop_record migration.','manual','legacy://loop-smoke','proj_mvp',NULL,NULL,0.8,'approved',NULL,NULL,NULL,'["legacy"]','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00');
            """
        )


def memory_schema_allows_loop_record(db_path: Path) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='memories'").fetchone()
    return bool(row and "'loop_record'" in str(row[0] or ""))


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    loop_id = f"loop_closed_{uuid.uuid4().hex[:10]}"
    with tempfile.TemporaryDirectory(prefix="agentops-loop-closed-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        seed_legacy_memory_schema(db_path)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            require(memory_schema_allows_loop_record(db_path), "legacy memory schema was not migrated to allow loop_record", failures)
            run = run_cli([
                "workflow",
                "hermes-openclaw-loop",
                "--topic",
                "Close the loop-audit RECORD gate after a dry-run Hermes/OpenClaw loop.",
                "--loop-id",
                loop_id,
                "--rounds",
                "1",
                "--request-timeout",
                "5",
            ], base_url, outputs, timeout=90)
            run_payload = load_json(run.stdout)
            ledger = run_payload.get("mis_ledger") or {}
            require(run.returncode == 0 and run_payload.get("ok") is True, f"loop workflow failed: {run.stderr or run.stdout}", failures)
            require(ledger.get("ok") is True, f"loop did not write MIS ledger: {run_payload}", failures)
            require(len(ledger.get("verified_plan_evidence_manifest_ids") or []) == 3, f"expected three verified manifests: {ledger}", failures)

            readback = run_cli(["workflow", "hermes-openclaw-loop", "--readback", "--loop-id", loop_id], base_url, outputs)
            readback_payload = load_json(readback.stdout)
            readback_summary = readback_payload.get("summary") or {}
            require(readback.returncode == 0 and readback_payload.get("status") == "ready", f"readback not ready: {readback.stdout}", failures)
            require(readback_summary.get("runs") == 3, f"readback should include parent+child runs: {readback_payload}", failures)
            require(readback_summary.get("verified_plan_evidence_manifests") == 3, f"readback missing verified manifests: {readback_payload}", failures)

            first_audit = run_cli(["operator", "loop-audit", "--loop-id", loop_id, "--limit", "10"], base_url, outputs)
            first_payload = load_json(first_audit.stdout)
            first_record = record_step(first_payload)
            first_loop_record = first_payload.get("loop_record") or {}
            require(first_audit.returncode == 0, f"first loop-audit failed: {first_audit.stderr or first_audit.stdout}", failures)
            require(first_payload.get("status") == "attention", f"loop without memory should need RECORD attention: {first_payload}", failures)
            require(first_record.get("status") == "attention", f"record should wait for loop memory: {first_record}", failures)
            require((first_payload.get("summary") or {}).get("loop_approved_memories") == 0, f"unexpected approved loop memory: {first_payload}", failures)
            require(first_loop_record.get("status") == "missing_memory", f"loop_record should report missing memory before proposal: {first_loop_record}", failures)
            require("--type loop_record" in (first_record.get("command") or ""), f"record command should request loop_record: {first_record}", failures)

            agent_id = (ledger.get("registered_agents") or ["agt_loop_supervisor_local_demo_hermes_openclaw"])[0]
            parent_task_id = ledger.get("parent_task_id")
            parent_run_id = ledger.get("parent_run_id")
            proposed = run_cli([
                "memory",
                "propose",
                "--agent-id",
                agent_id,
                "--task-id",
                parent_task_id,
                "--run-id",
                parent_run_id,
                "--scope",
                "project",
                "--type",
                "loop_record",
                "--source-ref",
                f"loop://{loop_id}",
                "--access-tags",
                "agentops-loop,review,closed-loop-smoke",
                "--confidence",
                "0.91",
                "--text",
                f"Dry-run Hermes/OpenClaw loop {loop_id} completed with three plan-bound runs and three verified plan-evidence manifests.",
            ], base_url, outputs)
            proposed_payload = load_json(proposed.stdout)
            memory = proposed_payload.get("memory") or proposed_payload
            memory_id = memory.get("memory_id")
            require(proposed.returncode == 0, f"memory propose failed: {proposed.stderr or proposed.stdout}", failures)
            require(memory_id, f"memory id missing: {proposed_payload}", failures)
            require(memory.get("memory_type") == "loop_record", f"loop_record type was not preserved: {proposed_payload}", failures)
            require(memory.get("review_status") == "candidate", f"loop memory should start as candidate: {proposed_payload}", failures)
            require(count_loop_records(db_path, loop_id) == 1, "loop_record row was not persisted in SQLite", failures)

            candidate_audit = run_cli(["operator", "loop-audit", "--loop-id", loop_id, "--limit", "10"], base_url, outputs)
            candidate_payload = load_json(candidate_audit.stdout)
            candidate_record = record_step(candidate_payload)
            candidate_loop_record = candidate_payload.get("loop_record") or {}
            require(candidate_payload.get("status") == "attention", f"candidate loop memory should still require review: {candidate_payload}", failures)
            require(candidate_record.get("status") == "attention", f"record should not pass while memory is candidate: {candidate_record}", failures)
            require((candidate_payload.get("summary") or {}).get("loop_memory_candidates") == 1, f"candidate should be counted: {candidate_payload}", failures)
            require(candidate_loop_record.get("status") == "waiting_memory_review", f"loop_record should wait on memory review: {candidate_loop_record}", failures)
            require(any(row.get("memory_id") == memory_id for row in (candidate_loop_record.get("memory_reviews") or [])), f"candidate memory row missing from loop_record: {candidate_loop_record}", failures)

            approved = run_cli(["memory", "approve", "--memory-id", memory_id], base_url, outputs)
            approved_payload = load_json(approved.stdout)
            require(approved.returncode == 0, f"memory approve failed: {approved.stderr or approved.stdout}", failures)
            require(approved_payload.get("review_status") == "approved", f"memory not approved: {approved_payload}", failures)

            final_audit = run_cli(["operator", "loop-audit", "--loop-id", loop_id, "--limit", "10"], base_url, outputs)
            final_payload = load_json(final_audit.stdout)
            final_summary = final_payload.get("summary") or {}
            final_record = record_step(final_payload)
            final_loop_record = final_payload.get("loop_record") or {}
            require(final_audit.returncode == 0, f"final loop-audit failed: {final_audit.stderr or final_audit.stdout}", failures)
            require(final_payload.get("status") == "ready", f"approved loop memory should close audit: {final_payload}", failures)
            require(final_summary.get("pass") == 7, f"expected 7/7 gates passing: {final_summary}", failures)
            require(final_record.get("status") == "pass", f"record gate should pass: {final_record}", failures)
            require(final_summary.get("loop_approved_memories") == 1, f"approved loop memory should be counted: {final_summary}", failures)
            require(final_summary.get("loop_memory_candidates") == 0, f"no loop candidates should remain: {final_summary}", failures)
            require(final_loop_record.get("status") == "ready", f"loop_record should be ready after approval: {final_loop_record}", failures)
            require(any(row.get("memory_id") == memory_id and row.get("review_status") == "approved" for row in (final_loop_record.get("memory_reviews") or [])), f"approved memory row missing from loop_record: {final_loop_record}", failures)

            for path in loop_runtime_paths(loop_id):
                require(path.exists(), f"missing loop runtime artifact: {path}", failures)
                ignored = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT, check=False)
                require(ignored.returncode == 0, f"loop runtime artifact is not gitignored: {path}", failures)
        finally:
            stop_server(server)

    secret_leaked = leaked("\n".join(outputs))
    require(not secret_leaked, "closed-loop smoke leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "loop_id": loop_id,
        "record_closed": not failures,
        "secret_leaked": secret_leaked,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
