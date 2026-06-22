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


def advance_receipt_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt' AND metadata_json LIKE ?",
            ("%advance_loop:%",),
        ).fetchone()
    return int(row[0] if row else 0)


def receipt_count_for_source(db_path: Path, source: str) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt' AND metadata_json LIKE ?",
            (f"%{source}%",),
        ).fetchone()
    return int(row[0] if row else 0)


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
            policy = run_cli(["operator", "advance-loop-policy"], base_url, outputs)
            policy_payload = load_json(policy.stdout)
            policy_summary = policy_payload.get("policy") or {}
            require(policy.returncode == 0, f"advance policy CLI failed: {policy.stderr or policy.stdout}", failures)
            require(policy_payload.get("operation") == "operator_advance_loop_policy", f"advance policy operation mismatch: {policy_payload}", failures)
            require(policy_summary.get("policy_id") == "advance_loop_local_bounded_v1", f"advance policy id missing: {policy_payload}", failures)
            require((policy_payload.get("safety") or {}).get("read_only") is True, f"advance policy should be read-only: {policy_payload}", failures)

            global_preview = run_cli(["operator", "advance-loop", "--limit", "10"], base_url, outputs)
            global_preview_payload = load_json(global_preview.stdout)
            require(global_preview.returncode == 0, f"global advance preview failed: {global_preview.stderr or global_preview.stdout}", failures)
            require(global_preview_payload.get("status") == "preview", f"global advance should preview: {global_preview_payload}", failures)
            require((global_preview_payload.get("preview") or {}).get("gate_id") == "evidence_report", f"global advance should prioritize evidence report: {global_preview_payload}", failures)
            require(((global_preview_payload.get("preview") or {}).get("action_policy") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"global evidence preview policy missing: {global_preview_payload}", failures)
            global_before_receipts = advance_receipt_count(db_path)
            global_advanced = run_cli(["operator", "advance-loop", "--limit", "10", "--confirm-advance"], base_url, outputs)
            global_advanced_payload = load_json(global_advanced.stdout)
            global_after_receipts = advance_receipt_count(db_path)
            require(global_advanced.returncode == 0, f"global advance confirm failed: {global_advanced.stderr or global_advanced.stdout}", failures)
            require((global_advanced_payload.get("preview") or {}).get("gate_id") == "evidence_report", f"global advance confirmed wrong gate: {global_advanced_payload}", failures)
            require(global_advanced_payload.get("advanced") is True, f"global advance should execute evidence report: {global_advanced_payload}", failures)
            require((global_advanced_payload.get("action_result") or {}).get("ok") is True, f"global evidence action failed: {global_advanced_payload}", failures)
            require((global_advanced_payload.get("verify_result") or {}).get("ok") is True, f"global evidence verify failed: {global_advanced_payload}", failures)
            require(global_after_receipts >= global_before_receipts + 1, f"global evidence advance receipt missing: {global_before_receipts} -> {global_after_receipts}", failures)
            global_second_preview = run_cli(["operator", "advance-loop", "--limit", "10"], base_url, outputs)
            global_second_payload = load_json(global_second_preview.stdout)
            require(global_second_preview.returncode == 0, f"global second preview failed: {global_second_preview.stderr or global_second_preview.stdout}", failures)
            require((global_second_payload.get("preview") or {}).get("gate_id") != "evidence_report", f"verified evidence work order should not be selected again: {global_second_payload}", failures)
            require((global_second_payload.get("preview") or {}).get("gate_id") == "evidence_remediation", f"global second preview should continue with evidence remediation: {global_second_payload}", failures)
            require(str((global_second_payload.get("preview") or {}).get("action_command") or "").startswith("agentops operator remediate-evidence-gap --run-id "), f"remediation preview command missing: {global_second_payload}", failures)
            require(((global_second_payload.get("preview") or {}).get("action_policy") or {}).get("allowed") is True, f"remediation preview should be allowlisted: {global_second_payload}", failures)
            remediation_before_receipts = receipt_count_for_source(db_path, "handoff.evidence_remediation")
            remediation_advanced = run_cli(["operator", "advance-loop", "--limit", "10", "--confirm-advance"], base_url, outputs)
            remediation_advanced_payload = load_json(remediation_advanced.stdout)
            remediation_after_receipts = receipt_count_for_source(db_path, "handoff.evidence_remediation")
            require(remediation_advanced.returncode == 0, f"remediation advance confirm failed: {remediation_advanced.stderr or remediation_advanced.stdout}", failures)
            require((remediation_advanced_payload.get("preview") or {}).get("gate_id") == "evidence_remediation", f"remediation advance confirmed wrong gate: {remediation_advanced_payload}", failures)
            require((remediation_advanced_payload.get("action_result") or {}).get("ok") is True, f"remediation preview action failed: {remediation_advanced_payload}", failures)
            require((remediation_advanced_payload.get("verify_result") or {}).get("ok") is True, f"remediation preview verify failed: {remediation_advanced_payload}", failures)
            require(((remediation_advanced_payload.get("receipt") or {}).get("receipt") or {}).get("source") == "handoff.evidence_remediation", f"remediation receipt should preserve handoff source: {remediation_advanced_payload}", failures)
            require(remediation_after_receipts >= remediation_before_receipts + 1, f"remediation advance receipt missing: {remediation_before_receipts} -> {remediation_after_receipts}", failures)
            handoff_after_global = run_cli(["operator", "handoff", "--limit", "10"], base_url, outputs)
            handoff_after_payload = load_json(handoff_after_global.stdout)
            evidence_work_order = ((handoff_after_payload.get("work_order") or {}).get("evidence_report") or {})
            evidence_receipt_state = evidence_work_order.get("receipt_state") or {}
            require(evidence_receipt_state.get("verified") is True, f"handoff should expose verified evidence receipt state: {handoff_after_payload}", failures)
            remediation_items = (((evidence_work_order.get("remediation_chain") or {}).get("items")) or [])
            require(any((item.get("receipt_state") or {}).get("verified") is True for item in remediation_items), f"handoff should expose verified remediation receipt state: {handoff_after_payload}", failures)

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
            require((preview_payload.get("policy") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"advance preview policy id missing: {preview_payload}", failures)
            require(((preview_payload.get("preview") or {}).get("action_policy") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"advance action policy id missing: {preview_payload}", failures)
            require(after_preview == before, f"advance preview mutated db: {before} -> {after_preview}", failures)

            advanced = run_cli(["operator", "advance-loop", "--loop-id", loop_id, "--limit", "10", "--confirm-advance"], base_url, outputs)
            advanced_payload = load_json(advanced.stdout)
            after_advance = db_counts(db_path, loop_id)
            require(advanced.returncode == 0, f"advance confirm CLI failed: {advanced.stderr or advanced.stdout}", failures)
            require(advanced_payload.get("operation") == "operator_advance_loop", f"advance operation mismatch: {advanced_payload}", failures)
            require(advanced_payload.get("advanced") is True, f"advance did not execute: {advanced_payload}", failures)
            require(advanced_payload.get("status") == "advanced", f"advance should finish verified: {advanced_payload}", failures)
            require((advanced_payload.get("preview") or {}).get("gate_id") == "record", f"advanced wrong gate: {advanced_payload}", failures)
            require((advanced_payload.get("policy") or {}).get("policy_id") == "advance_loop_local_bounded_v1", f"advanced policy id missing: {advanced_payload}", failures)
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
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops memory approve --memory-id mem_x', phase='action')))",
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
            evidence_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator evidence-report --limit 8', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([evidence_policy.stdout, evidence_policy.stderr])
            evidence_policy_payload = load_json(evidence_policy.stdout)
            require(evidence_policy_payload.get("allowed") is True, f"evidence report should be allowlisted as read-only action: {evidence_policy_payload}", failures)
            remediation_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator remediate-evidence-gap --run-id run_seed_28', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([remediation_policy.stdout, remediation_policy.stderr])
            remediation_policy_payload = load_json(remediation_policy.stdout)
            require(remediation_policy_payload.get("allowed") is True, f"remediation preview should be allowlisted as read-only action: {remediation_policy_payload}", failures)
            remediation_confirm_policy = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from agentops_mis_cli.advance_loop_policy import advance_loop_command_policy; import json; print(json.dumps(advance_loop_command_policy('agentops operator remediate-evidence-gap --run-id run_seed_28 --confirm-create', phase='action')))",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            outputs.extend([remediation_confirm_policy.stdout, remediation_confirm_policy.stderr])
            remediation_confirm_payload = load_json(remediation_confirm_policy.stdout)
            require(remediation_confirm_payload.get("allowed") is False, f"remediation confirm-create must stay denied: {remediation_confirm_payload}", failures)
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
