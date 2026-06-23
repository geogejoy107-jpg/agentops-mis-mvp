#!/usr/bin/env python3
"""Verify operator evidence-report aggregates plan, approval, manifest and ledger evidence."""
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
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SERVER = ROOT / "server.py"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early: {proc.returncode}")
        try:
            with urlopen(base_url + "/api/agent-gateway/status", timeout=1) as res:
                if res.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("server did not become ready")


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=60) as res:
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


def run_cli(args: list[str], base_url: str, agent_id: str, outputs: list[str]) -> dict:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env["AGENTOPS_AGENT_ID"] = agent_id
    proc = subprocess.run([str(CLI), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=90, check=False)
    outputs.extend([proc.stdout, proc.stderr])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)
    return json.loads(proc.stdout or "{}")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def db_fingerprint(db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        result: dict[str, dict] = {}
        for table, timestamp_col in [
            ("approvals", "created_at"),
            ("artifacts", "created_at"),
            ("tasks", "updated_at"),
            ("runs", "created_at"),
            ("tool_calls", "created_at"),
            ("evaluations", "created_at"),
            ("agent_plans", "updated_at"),
            ("plan_evidence_manifests", "updated_at"),
            ("audit_logs", "created_at"),
            ("runtime_events", "created_at"),
            ("operator_action_receipts", "created_at"),
        ]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                continue
            row = conn.execute(f"SELECT COUNT(*) AS count, COALESCE(MAX({timestamp_col}), '') AS max_ts FROM {table}").fetchone()
            result[table] = {"count": int(row["count"] or 0), "max_ts": row["max_ts"] or ""}
        return result
    finally:
        conn.close()


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    stamp = now_stamp()
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    agent_id = f"agt_evidence_report_{stamp}"
    task_id = f"tsk_evidence_report_{stamp}"
    server: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="agentops-evidence-report-") as tmp:
        db_path = Path(tmp) / "agentops_evidence_report.db"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        server = subprocess.Popen([sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            wait_ready(base_url, server)
            run_cli(["agent", "register", "--id", agent_id, "--name", "Evidence Report Agent", "--role", "Builder", "--runtime", "mock"], base_url, agent_id, outputs)
            run_cli([
                "task", "create",
                "--task-id", task_id,
                "--title", "Operator evidence report smoke",
                "--description", "Create a complete plan/approval/manifest evidence chain.",
                "--owner-agent-id", agent_id,
                "--requester-id", "usr_founder",
                "--acceptance", "Evidence report must show a ready run with verified manifest.",
                "--risk", "high",
            ], base_url, agent_id, outputs)
            plan_payload = run_cli([
                "agent-plan", "create",
                "--agent-id", agent_id,
                "--task-id", task_id,
                "--task-understanding", "Perform a high-risk evidence-report smoke with explicit approval before run_start.",
                "--referenced-specs", "PROJECT_SPEC.md,AGENT_WORKFLOW.md",
                "--referenced-memories", "knowledge/shared/common_failures.md",
                "--referenced-bases", "base_local_tasks",
                "--proposed-files-to-change", "server.py,scripts/operator_evidence_report_smoke.py",
                "--risk", "high",
                "--execution-steps", "READ,PLAN,RETRIEVE,EXECUTE,VERIFY,RECORD",
                "--verification-plan", "Run operator_evidence_report_smoke.py.",
                "--rollback-plan", "Reject the plan and do not start the run if approval or manifest verification fails.",
            ], base_url, agent_id, outputs)
            plan = plan_payload.get("agent_plan") or {}
            plan_id = plan.get("plan_id")
            approval_id = plan.get("approval_id")
            require(bool(plan_id and approval_id), f"plan/approval missing: {plan_payload}", failures)
            run_cli(["agent-plan", "verify", "--plan-id", str(plan_id)], base_url, agent_id, outputs)
            status, approved = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
            outputs.append(json.dumps(approved, ensure_ascii=False))
            require(status == 200 and (approved.get("agent_plan") or {}).get("status") == "approved", f"plan approval failed: {status} {approved}", failures)
            run_payload = run_cli([
                "run", "start",
                "--task-id", task_id,
                "--agent-id", agent_id,
                "--plan-id", str(plan_id),
                "--input-summary", "Operator evidence report smoke run.",
            ], base_url, agent_id, outputs)
            run_id = (run_payload.get("run") or {}).get("run_id")
            require(bool(run_id), f"run id missing: {run_payload}", failures)
            tool = run_cli(["toolcall", "record", "--run-id", str(run_id), "--agent-id", agent_id, "--tool", "evidence.report.fixture", "--category", "custom", "--risk", "low", "--status", "completed", "--summary", "Fixture tool call completed."], base_url, agent_id, outputs)
            evaluation = run_cli(["eval", "submit", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--gate", "operator_evidence_report_smoke", "--score", "1", "--pass", "--notes", "Fixture evaluation passed."], base_url, agent_id, outputs)
            artifact = run_cli(["artifact", "record", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--type", "operator_evidence_report_fixture", "--title", "Operator evidence report fixture", "--summary", "Safe fixture artifact summary.", "--uri", f"run://{run_id}"], base_url, agent_id, outputs)
            run_cli(["run", "heartbeat", "--run-id", str(run_id), "--status", "completed", "--summary", "Evidence report fixture completed.", "--duration-ms", "1200"], base_url, agent_id, outputs)
            manifest = run_cli([
                "plan-evidence", "create",
                "--plan-id", str(plan_id),
                "--run-id", str(run_id),
                "--agent-id", agent_id,
                "--tool-call-ids", str((tool.get("tool_call") or {}).get("tool_call_id") or ""),
                "--evaluation-ids", str((evaluation.get("evaluation") or {}).get("evaluation_id") or ""),
                "--artifact-ids", str((artifact.get("artifact") or {}).get("artifact_id") or ""),
            ], base_url, agent_id, outputs)
            require((manifest.get("verification") or {}).get("pass") is True, f"manifest did not verify: {manifest}", failures)
            missing_memory_report = run_cli(["operator", "evidence-report", "--run-id", str(run_id), "--limit", "5"], base_url, agent_id, outputs)
            missing_memory_item = (missing_memory_report.get("runs") or [{}])[0]
            require(missing_memory_item.get("status") == "attention", f"missing memory review should require attention: {missing_memory_item}", failures)
            require((missing_memory_item.get("memory_review") or {}).get("status") == "missing", f"missing memory status not surfaced: {missing_memory_item}", failures)
            require("memory propose" in " ".join(missing_memory_item.get("recommended_commands") or []), f"missing memory command absent: {missing_memory_item}", failures)
            memory = run_cli(["memory", "propose", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--scope", "task", "--type", "artifact_summary", "--text", "Operator evidence report fixture produced reviewed closure memory."], base_url, agent_id, outputs)
            memory_id = (memory.get("memory") or {}).get("memory_id")
            require(bool(memory_id), f"memory candidate missing: {memory}", failures)
            pending_memory_report = run_cli(["operator", "evidence-report", "--run-id", str(run_id), "--limit", "5"], base_url, agent_id, outputs)
            pending_memory_item = (pending_memory_report.get("runs") or [{}])[0]
            require(pending_memory_item.get("status") == "attention", f"pending memory review should require attention: {pending_memory_item}", failures)
            require((pending_memory_item.get("memory_review") or {}).get("status") == "pending_review", f"pending memory status not surfaced: {pending_memory_item}", failures)
            require("memory list" in " ".join(pending_memory_item.get("recommended_commands") or []), f"pending memory command absent: {pending_memory_item}", failures)
            approved_memory = run_cli(["memory", "approve", "--memory-id", str(memory_id)], base_url, agent_id, outputs)
            require(approved_memory.get("review_status") == "approved", f"memory approval failed: {approved_memory}", failures)
            before_report = db_fingerprint(db_path)
            report = run_cli(["operator", "evidence-report", "--run-id", str(run_id), "--limit", "5"], base_url, agent_id, outputs)
            status, api_report = http_json("GET", base_url, f"/api/operator/evidence-report?run_id={run_id}&limit=5")
            outputs.append(json.dumps(api_report, ensure_ascii=False))
            after_report = db_fingerprint(db_path)
            item = (report.get("runs") or [{}])[0]
            require(report.get("operation") == "operator_evidence_report", f"wrong operation: {report}", failures)
            require(report.get("safety", {}).get("read_only") is True, f"report should be read-only: {report}", failures)
            require(report.get("safety", {}).get("ledger_mutated") is False, f"report should not mutate ledger: {report}", failures)
            require(before_report is not None and before_report == after_report, f"report changed database fingerprint: before={before_report} after={after_report}", failures)
            require(status == 200 and api_report.get("operation") == "operator_evidence_report", f"API report failed: {status} {api_report}", failures)
            require(item.get("run_id") == run_id, f"report run mismatch: {report}", failures)
            require(item.get("status") == "ready", f"complete run should be ready: {item}", failures)
            require(all(check.get("ok") is True for check in item.get("checks") or []), f"expected every run check to pass: {item}", failures)
            require((item.get("agent_plan") or {}).get("approval_decision") == "approved", f"plan approval missing in report: {item}", failures)
            require((item.get("plan_evidence_manifest") or {}).get("verification_pass") is True, f"manifest missing in report: {item}", failures)
            memory_review = item.get("memory_review") or {}
            require(memory_review.get("status") == "reviewed", f"memory review should be reviewed: {item}", failures)
            require(int(memory_review.get("approved") or 0) >= 1, f"approved memory count missing: {item}", failures)
            require(memory_review.get("raw_content_omitted") is True, f"memory raw content should be omitted: {item}", failures)
            require("canonical_text" not in json.dumps(memory_review, ensure_ascii=False), f"memory review leaked canonical text: {memory_review}", failures)
            summary = report.get("summary") or {}
            require(int(summary.get("memory_review_ready") or 0) >= 1, f"summary missing ready memory review: {summary}", failures)
            require(int(summary.get("pending_memory_reviews") or 0) == 0, f"summary should have no pending memory review: {summary}", failures)
            counts = item.get("evidence_counts") or {}
            for key in ["tool_calls", "evaluations", "artifacts", "audit_logs"]:
                require(int(counts.get(key) or 0) >= 1, f"missing {key} evidence count: {counts}", failures)
            require(not leaked("\n".join(outputs) + json.dumps(report, ensure_ascii=False)), "operator evidence report leaked token-like material", failures)
            print(json.dumps({
                "ok": not failures,
                "run_id": run_id,
                "plan_id": plan_id,
                "approval_id": approval_id,
                "manifest_id": (manifest.get("manifest") or {}).get("manifest_id"),
                "memory_id": memory_id,
                "report_status": report.get("status"),
                "run_report_status": item.get("status"),
                "db_fingerprint_unchanged": before_report is not None and before_report == after_report,
                "failures": failures,
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
