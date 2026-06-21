#!/usr/bin/env python3
"""Smoke test the Hermes/OpenClaw loop controller without live runtime calls."""
from __future__ import annotations

import json
import os
import re
import shutil
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
LOOP = ROOT / "scripts" / "hermes_openclaw_loop.py"
RUNTIME_DIR = ROOT / ".agentops_runtime" / "loops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, timeout: float = 10.0) -> None:
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


def count_rows(db_path: Path, table: str, column: str, values: list[str]) -> int:
    if not values:
        return 0
    placeholders = ",".join("?" for _ in values)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} IN ({placeholders})", values).fetchone()
    return int(row[0] if row else 0)


def count_where(db_path: Path, sql: str, params: tuple = ()) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row[0] if row else 0)


def count_manifest_status(db_path: Path, manifest_ids: list[str], status: str) -> int:
    if not manifest_ids:
        return 0
    placeholders = ",".join("?" for _ in manifest_ids)
    return count_where(db_path, f"SELECT COUNT(*) FROM plan_evidence_manifests WHERE manifest_id IN ({placeholders}) AND status=?", (*manifest_ids, status))


def cleanup_loop_runtime(loop_id: str) -> None:
    for suffix in [".jsonl", ".audit.jsonl", ".next_action.json"]:
        try:
            (RUNTIME_DIR / f"{loop_id}{suffix}").unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    proc = subprocess.run(
        [
            sys.executable,
            str(LOOP),
            "--topic",
            "Verify Hermes/OpenClaw can loop under Codex supervision without touching project files.",
            "--rounds",
            "2",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    outputs.extend([proc.stdout, proc.stderr])
    payload = load_json(proc.stdout)
    require(proc.returncode == 0, f"loop dry-run failed: {proc.stderr or proc.stdout}", failures)
    require(payload.get("ok") is True, f"loop payload not ok: {payload}", failures)
    require(payload.get("mode") == "dry-run", f"loop should default to dry-run: {payload}", failures)
    require(payload.get("rounds") == 2, f"wrong round count: {payload}", failures)
    require(len(payload.get("outputs") or []) == 4, f"expected two agents x two rounds: {payload}", failures)
    require(all(row.get("status") == "dry_run" for row in payload.get("outputs") or []), f"live call happened in dry-run: {payload}", failures)
    require(all((row.get("evaluation") or {}).get("pass") is True for row in payload.get("outputs") or []), f"evaluation did not pass: {payload}", failures)
    require(all((row.get("evaluation") or {}).get("score") == 1.0 for row in payload.get("outputs") or []), f"evaluation score not perfect in smoke: {payload}", failures)
    log_path = Path(payload.get("log_path") or "")
    audit_path = Path(payload.get("audit_path") or "")
    artifact_path = Path(payload.get("next_action_artifact_path") or "")
    require(log_path.exists(), f"missing loop log: {payload}", failures)
    require(audit_path.exists(), f"missing audit log: {payload}", failures)
    require(artifact_path.exists(), f"missing next action artifact: {payload}", failures)
    require(str(log_path).startswith(str(RUNTIME_DIR)), f"loop log should live under gitignored runtime dir: {payload}", failures)
    for path in [log_path, audit_path, artifact_path]:
        ignored = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT, check=False)
        require(ignored.returncode == 0, f"loop runtime artifact is not gitignored: {path}", failures)
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(len(rows) == 4, f"wrong JSONL rows: {rows}", failures)
    require(all(row.get("raw_omitted") is True for row in rows), f"raw omission missing: {rows}", failures)
    audit_rows = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    audit_actions = {row.get("action") for row in audit_rows}
    require("loop.started" in audit_actions, f"missing loop.started audit: {audit_rows}", failures)
    require("loop.agent_output_recorded" in audit_actions, f"missing output audit: {audit_rows}", failures)
    require("loop.next_action_artifact_written" in audit_actions, f"missing artifact audit: {audit_rows}", failures)
    require("loop.completed" in audit_actions, f"missing completion audit: {audit_rows}", failures)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    require(artifact.get("status") == "ready_for_codex_review", f"wrong artifact status: {artifact}", failures)
    require(artifact.get("raw_omitted") is True and artifact.get("token_omitted") is True, f"artifact omission proof missing: {artifact}", failures)
    require(
        not leaked("\n".join(outputs) + log_path.read_text(encoding="utf-8") + audit_path.read_text(encoding="utf-8") + artifact_path.read_text(encoding="utf-8")),
        "loop smoke leaked token-like material",
        failures,
    )

    gate = subprocess.run(
        [
            sys.executable,
            str(LOOP),
            "--topic",
            "This live request must be rejected without confirmation.",
            "--mode",
            "live-both",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    outputs.extend([gate.stdout, gate.stderr])
    gate_payload = load_json(gate.stdout)
    require(gate.returncode == 1, f"unconfirmed live loop should fail closed: {gate.stdout}", failures)
    require(gate_payload.get("error") == "confirm_live_required", f"wrong live gate error: {gate_payload}", failures)
    require(gate_payload.get("token_omitted") is True, f"live gate token omission missing: {gate_payload}", failures)

    resume_loop_id = f"loop_smoke_resume_{uuid.uuid4().hex[:10]}"
    cleanup_loop_runtime(resume_loop_id)
    first_resume = subprocess.run(
        [
            sys.executable,
            str(LOOP),
            "--topic",
            "Resume smoke should preserve completed Hermes output and continue OpenClaw.",
            "--loop-id",
            resume_loop_id,
            "--rounds",
            "1",
            "--order",
            "hermes",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    outputs.extend([first_resume.stdout, first_resume.stderr])
    require(first_resume.returncode == 0, f"first resume seed loop failed: {first_resume.stderr or first_resume.stdout}", failures)
    resumed = subprocess.run(
        [
            sys.executable,
            str(LOOP),
            "--topic",
            "Resume smoke should preserve completed Hermes output and continue OpenClaw.",
            "--loop-id",
            resume_loop_id,
            "--rounds",
            "1",
            "--order",
            "hermes",
            "openclaw",
            "--resume",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    outputs.extend([resumed.stdout, resumed.stderr])
    resumed_payload = load_json(resumed.stdout)
    resumed_audit = Path(resumed_payload.get("audit_path") or "")
    resumed_log = Path(resumed_payload.get("log_path") or "")
    require(resumed.returncode == 0, f"resume loop failed: {resumed.stderr or resumed.stdout}", failures)
    require(len(resumed_payload.get("outputs") or []) == 2, f"resume should have two outputs after continuation: {resumed_payload}", failures)
    require(any(row.get("resumed_from_existing") for row in resumed_payload.get("outputs") or []), f"resume did not mark reused output: {resumed_payload}", failures)
    require(resumed_log.exists() and len([line for line in resumed_log.read_text(encoding="utf-8").splitlines() if line.strip()]) == 2, f"resume log should contain two rows: {resumed_payload}", failures)
    if resumed_audit.exists():
        resume_actions = {json.loads(line).get("action") for line in resumed_audit.read_text(encoding="utf-8").splitlines() if line.strip()}
        require("loop.resumed" in resume_actions and "loop.output_reused" in resume_actions, f"resume audit missing actions: {resume_actions}", failures)

    with tempfile.TemporaryDirectory(prefix="agentops-loop-ledger-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        shutil.copy(ROOT / "agentops_mis.db", db_path)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            ledger = subprocess.run(
                [
                    sys.executable,
                    str(LOOP),
                    "--topic",
                    "Record a dry-run Hermes/OpenClaw collaboration loop into the MIS ledger.",
                    "--rounds",
                    "1",
                    "--mis-ledger",
                    "--base-url",
                    base_url,
                    "--request-timeout",
                    "5",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        finally:
            stop_server(server)
        outputs.extend([ledger.stdout, ledger.stderr])
        ledger_payload = load_json(ledger.stdout)
        mis_ledger = ledger_payload.get("mis_ledger") or {}
        require(ledger.returncode == 0, f"MIS ledger loop failed: {ledger.stderr or ledger.stdout}", failures)
        require(mis_ledger.get("ok") is True, f"MIS ledger payload not ok: {ledger_payload}", failures)
        child_run_ids = mis_ledger.get("child_run_ids") or []
        child_task_ids = mis_ledger.get("child_task_ids") or []
        parent_run_id = mis_ledger.get("parent_run_id")
        parent_task_id = mis_ledger.get("parent_task_id")
        artifact_id = mis_ledger.get("artifact_id")
        plan_ids = mis_ledger.get("plan_ids") or []
        manifest_ids = mis_ledger.get("plan_evidence_manifest_ids") or []
        require(count_rows(db_path, "tasks", "task_id", [parent_task_id, *child_task_ids]) == 3, f"expected parent+child tasks in ledger: {mis_ledger}", failures)
        require(count_rows(db_path, "runs", "run_id", [parent_run_id, *child_run_ids]) == 3, f"expected parent+child runs in ledger: {mis_ledger}", failures)
        require(count_rows(db_path, "tool_calls", "run_id", [parent_run_id, *child_run_ids]) == 3, f"expected parent+child tool calls in ledger: {mis_ledger}", failures)
        require(count_rows(db_path, "evaluations", "run_id", [parent_run_id, *child_run_ids]) == 3, f"expected evaluations in ledger: {mis_ledger}", failures)
        require(count_rows(db_path, "artifacts", "artifact_id", [artifact_id, *(mis_ledger.get("artifact_ids") or [])]) >= 3, f"expected final+child artifacts in ledger: {mis_ledger}", failures)
        require(count_rows(db_path, "audit_logs", "entity_id", [parent_run_id, *child_run_ids]) >= 3, f"expected audit evidence in ledger: {mis_ledger}", failures)
        require(count_rows(db_path, "agent_plans", "plan_id", plan_ids) == 3, f"expected parent+child plans in ledger: {mis_ledger}", failures)
        require(count_rows(db_path, "plan_evidence_manifests", "manifest_id", manifest_ids) == 3, f"expected parent+child manifests in ledger: {mis_ledger}", failures)
        require(count_manifest_status(db_path, manifest_ids, "verified") == 3, f"expected verified manifests: {mis_ledger}", failures)
        require(mis_ledger.get("raw_omitted") is True and mis_ledger.get("token_omitted") is True, f"MIS ledger omission proof missing: {mis_ledger}", failures)

    with tempfile.TemporaryDirectory(prefix="agentops-loop-block-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        shutil.copy(ROOT / "agentops_mis.db", db_path)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            blocked = subprocess.run(
                [
                    sys.executable,
                    str(LOOP),
                    "--topic",
                    "Record a blocked Hermes/OpenClaw loop lane into MIS.",
                    "--rounds",
                    "1",
                    "--order",
                    "hermes",
                    "--simulate-failure-agent",
                    "hermes",
                    "--mis-ledger",
                    "--base-url",
                    base_url,
                    "--request-timeout",
                    "5",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        finally:
            stop_server(server)
        outputs.extend([blocked.stdout, blocked.stderr])
        blocked_payload = load_json(blocked.stdout)
        blocked_ledger = blocked_payload.get("mis_ledger") or {}
        blocked_manifests = blocked_ledger.get("plan_evidence_manifest_ids") or []
        require(blocked.returncode == 1, f"forced-failure loop should return blocked/nonzero: {blocked.stdout}", failures)
        require(blocked_payload.get("next_action_artifact", {}).get("status") == "blocked", f"forced-failure artifact should be blocked: {blocked_payload}", failures)
        require(blocked_ledger.get("ok") is True, f"blocked loop should still write MIS ledger evidence: {blocked_payload}", failures)
        require(count_where(db_path, "SELECT COUNT(*) FROM plan_evidence_manifests WHERE status='blocked'") >= 1, f"blocked loop should persist blocked manifest: {blocked_ledger}", failures)
        require(len(blocked_manifests) >= 2, f"blocked loop should have child+parent manifests: {blocked_ledger}", failures)

    print(json.dumps({
        "ok": not failures,
        "failures": failures,
        "dry_run_outputs": len(payload.get("outputs") or []) if "payload" in locals() else 0,
        "audit_checked": True,
        "evaluation_checked": True,
        "mis_ledger_checked": True,
        "next_action_artifact_checked": True,
        "plan_evidence_checked": True,
        "resume_checked": True,
        "block_checked": True,
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
