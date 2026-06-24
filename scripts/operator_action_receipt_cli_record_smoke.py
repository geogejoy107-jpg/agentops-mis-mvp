#!/usr/bin/env python3
"""Verify CLI action receipt recording is explicit, audited, and non-executing."""

from __future__ import annotations

import json
import os
import re
import shlex
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
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=30) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _ = http_json(base_url, "/api/operator/action-plan?limit=1")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_counts(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        audit_row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt'"
        ).fetchone()
        runtime_row = conn.execute(
            "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type='operator.action_queue_receipt'"
        ).fetchone()
        evaluation_row = conn.execute(
            "SELECT COUNT(*) AS c FROM operator_action_evaluations"
        ).fetchone()
        evaluation_audit_row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_evaluation'"
        ).fetchone()
        return {
            "audit_logs": int(audit_row["c"] or 0),
            "runtime_events": int(runtime_row["c"] or 0),
            "operator_action_evaluations": int(evaluation_row["c"] or 0),
            "evaluation_audit_logs": int(evaluation_audit_row["c"] or 0),
        }
    finally:
        conn.close()


def db_control_readback_counts(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        audit_row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_control_readback'"
        ).fetchone()
        runtime_row = conn.execute(
            "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type='operator.action_queue_control_readback'"
        ).fetchone()
        return {
            "audit_logs": int(audit_row["c"] or 0),
            "runtime_events": int(runtime_row["c"] or 0),
        }
    finally:
        conn.close()


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-action-receipt-cli-record-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_BASE_URL"] = base_url
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
            status, plan = http_json(base_url, "/api/operator/action-plan?limit=20")
            outputs.append(json.dumps(plan, ensure_ascii=False))
            require(status == 200, f"action-plan status mismatch: {status} {plan}", failures)
            action = next(
                (
                    row for row in plan.get("actions") or []
                    if row.get("command") and row.get("receipt_required") is True
                ),
                {},
            )
            action_command = str(action.get("command") or "agentops worker status")
            verify_command = str(action.get("verify_command") or "agentops operator action-plan --limit 20")
            action_id = str(action.get("action_id") or "smoke:cli-record-action")
            action_signature = str(action.get("action_signature") or "smoke_cli_record_signature")
            generated_preview_command = str(action.get("receipt_record_command") or "")
            generated_verify_command = str(action.get("receipt_verify_record_command") or "")
            require(generated_preview_command.startswith("agentops operator record-action-receipt "), f"action-plan generated preview command missing: {action}", failures)
            require("--confirm-record" not in generated_preview_command, f"generated preview command should not confirm: {generated_preview_command}", failures)
            require(generated_verify_command.startswith("agentops operator record-action-receipt "), f"action-plan generated verify command missing: {action}", failures)
            require("--confirm-record" in generated_verify_command, f"generated verify command lacks confirmation: {generated_verify_command}", failures)
            preview_argv = shlex.split(generated_preview_command)
            verify_argv = shlex.split(generated_verify_command)
            if preview_argv:
                preview_argv[0] = str(CLI)
            if verify_argv:
                verify_argv[0] = str(CLI)

            before_preview = db_counts(db_path)
            preview_proc = subprocess.run(
                preview_argv,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            outputs.extend([preview_proc.stdout, preview_proc.stderr])
            preview = load_json(preview_proc.stdout)
            after_preview = db_counts(db_path)
            require(preview_proc.returncode == 0, f"preview CLI failed: {preview_proc.returncode} {preview_proc.stderr}", failures)
            require(preview.get("operation") == "operator_action_receipt_cli_preview", f"wrong preview operation: {preview}", failures)
            require(preview.get("recorded") is False, f"preview should not record: {preview}", failures)
            require((preview.get("safety") or {}).get("read_only") is True, f"preview read_only missing: {preview}", failures)
            require((preview.get("safety") or {}).get("ledger_mutated") is False, f"preview mutated ledger: {preview}", failures)
            require(before_preview == after_preview, f"preview changed receipt counts: {before_preview} -> {after_preview}", failures)

            record_proc = subprocess.run(
                verify_argv,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            outputs.extend([record_proc.stdout, record_proc.stderr])
            record = load_json(record_proc.stdout)
            after_record = db_counts(db_path)
            require(record_proc.returncode == 0, f"record CLI failed: {record_proc.returncode} {record_proc.stderr}", failures)
            require(record.get("operation") == "operator_action_receipt", f"wrong record operation: {record}", failures)
            require(record.get("cli_operation") == "operator_record_action_receipt", f"CLI operation marker missing: {record}", failures)
            require(record.get("confirm_record") is True, f"confirm_record marker missing: {record}", failures)
            safety = record.get("safety") or {}
            require(safety.get("ledger_mutated") is True, f"record should mutate ledger: {safety}", failures)
            require(safety.get("live_execution_performed") is False, f"record must not execute commands: {safety}", failures)
            require(after_record["audit_logs"] == after_preview["audit_logs"] + 1, f"audit count mismatch: {after_preview} -> {after_record}", failures)
            require(after_record["runtime_events"] == after_preview["runtime_events"] + 1, f"runtime count mismatch: {after_preview} -> {after_record}", failures)
            require(after_record["operator_action_evaluations"] == after_preview["operator_action_evaluations"] + 1, f"operator action evaluation count mismatch: {after_preview} -> {after_record}", failures)
            require(after_record["evaluation_audit_logs"] == after_preview["evaluation_audit_logs"] + 1, f"operator action evaluation audit count mismatch: {after_preview} -> {after_record}", failures)

            receipt = record.get("receipt") or {}
            receipt_id = receipt.get("receipt_id")
            evaluation = record.get("evaluation") or {}
            require(bool(receipt_id), f"receipt_id missing: {record}", failures)
            require(receipt.get("action_command") == action_command, f"recorded action mismatch: {receipt}", failures)
            require(receipt.get("verify_command") == verify_command, f"recorded verify mismatch: {receipt}", failures)
            require(receipt.get("action_signature") == action_signature, f"recorded signature mismatch: {receipt}", failures)
            require(bool(receipt.get("tamper_chain_hash")), f"tamper hash missing: {receipt}", failures)
            require(evaluation.get("receipt_id") == receipt_id, f"record evaluation receipt mismatch: {evaluation}", failures)
            require(evaluation.get("pass_fail") == "pass", f"record evaluation should pass: {evaluation}", failures)
            require(float(evaluation.get("score") or 0) == 1.0, f"record evaluation score wrong: {evaluation}", failures)

            control_payload = {
                "before": {
                    "selected_gate": "cli_record_control_readback",
                    "receipt_id": receipt_id,
                    "status": receipt.get("status"),
                },
                "after": {
                    "selected_gate": "cli_record_control_readback",
                    "receipt_recorded": True,
                    "verify_command": verify_command,
                },
                "self_check": {
                    "server_executes_shell": False,
                    "live_execution_performed": False,
                    "token_omitted": True,
                },
                "token_omitted": True,
            }
            control_preview_argv = [
                str(CLI), "operator", "record-control-readback",
                "--receipt-id", str(receipt_id),
                "--source", "smoke.operator_action_receipt_cli_record.control_readback",
                "--control-readback-json", json.dumps(control_payload, separators=(",", ":")),
            ]
            before_control_preview = db_control_readback_counts(db_path)
            control_preview_proc = subprocess.run(
                control_preview_argv,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            outputs.extend([control_preview_proc.stdout, control_preview_proc.stderr])
            control_preview = load_json(control_preview_proc.stdout)
            after_control_preview = db_control_readback_counts(db_path)
            require(control_preview_proc.returncode == 0, f"control-readback preview CLI failed: {control_preview_proc.returncode} {control_preview_proc.stderr}", failures)
            require(control_preview.get("operation") == "operator_control_readback_cli_preview", f"wrong control preview operation: {control_preview}", failures)
            require(control_preview.get("recorded") is False, f"control preview should not record: {control_preview}", failures)
            require((control_preview.get("safety") or {}).get("ledger_mutated") is False, f"control preview mutated ledger: {control_preview}", failures)
            require(before_control_preview == after_control_preview, f"control preview changed counts: {before_control_preview} -> {after_control_preview}", failures)

            control_record_proc = subprocess.run(
                [*control_preview_argv, "--confirm-record"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            outputs.extend([control_record_proc.stdout, control_record_proc.stderr])
            control_record = load_json(control_record_proc.stdout)
            after_control_record = db_control_readback_counts(db_path)
            require(control_record_proc.returncode == 0, f"control-readback record CLI failed: {control_record_proc.returncode} {control_record_proc.stderr}", failures)
            require(control_record.get("operation") == "operator_action_control_readback", f"wrong control record operation: {control_record}", failures)
            require(control_record.get("cli_operation") == "operator_record_control_readback", f"control CLI operation marker missing: {control_record}", failures)
            require(control_record.get("confirm_record") is True, f"control confirm marker missing: {control_record}", failures)
            control_safety = control_record.get("safety") or {}
            require(control_safety.get("ledger_mutated") is True, f"control record should mutate ledger: {control_safety}", failures)
            require(control_safety.get("live_execution_performed") is False, f"control record must not execute commands: {control_safety}", failures)
            require(after_control_record["audit_logs"] == after_control_preview["audit_logs"] + 1, f"control audit count mismatch: {after_control_preview} -> {after_control_record}", failures)
            require(after_control_record["runtime_events"] == after_control_preview["runtime_events"] + 1, f"control runtime count mismatch: {after_control_preview} -> {after_control_record}", failures)
            control_readback = control_record.get("readback") or {}
            require(control_readback.get("receipt_id") == receipt_id, f"control readback receipt mismatch: {control_readback}", failures)
            require(bool(control_readback.get("tamper_chain_hash")), f"control readback tamper hash missing: {control_readback}", failures)

            status, readback = http_json(base_url, "/api/operator/action-receipts?limit=5")
            outputs.append(json.dumps(readback, ensure_ascii=False))
            require(status == 200, f"readback status mismatch: {status} {readback}", failures)
            readback_receipt = next((row for row in readback.get("receipts") or [] if row.get("receipt_id") == receipt_id), {})
            require(bool(readback_receipt), f"readback missing CLI receipt: {readback}", failures)
            require((readback_receipt.get("evaluation") or {}).get("pass_fail") == "pass", f"readback receipt evaluation missing: {readback_receipt}", failures)
            require(bool(readback_receipt.get("control_readback")), f"readback receipt missing control readback: {readback_receipt}", failures)
            require(bool(readback_receipt.get("control_readback_id")), f"readback receipt missing control readback id: {readback_receipt}", failures)

            status, verified_plan = http_json(base_url, "/api/operator/action-plan?limit=30")
            outputs.append(json.dumps(verified_plan, ensure_ascii=False))
            require(status == 200, f"verified action-plan status mismatch: {status} {verified_plan}", failures)
            matched_action = next((row for row in verified_plan.get("actions") or [] if row.get("command") == action_command), {})
            plan_summary = verified_plan.get("summary") or {}
            if matched_action:
                require(matched_action.get("receipt_status") == "verified", f"action-plan did not verify CLI receipt: {matched_action}", failures)
                require(matched_action.get("receipt_id") == receipt_id, f"action-plan receipt id mismatch: {matched_action}", failures)
                matched_evaluation = matched_action.get("receipt_evaluation") or (matched_action.get("receipt_state") or {}).get("evaluation") or {}
                require(matched_evaluation.get("pass_fail") == "pass", f"action-plan receipt evaluation missing: {matched_action}", failures)
            else:
                require(int(plan_summary.get("action_receipts_verified") or 0) >= 1, f"action-plan summary lacks verified CLI receipt: {plan_summary}", failures)
                require(int(plan_summary.get("action_receipts_evaluated") or 0) >= 1, f"action-plan summary lacks receipt evaluation: {plan_summary}", failures)
                require(int(plan_summary.get("action_receipts_evaluation_fail") or 0) == 0, f"action-plan summary reports receipt evaluation failure: {plan_summary}", failures)

            status, loop_audit = http_json(base_url, "/api/operator/loop-audit?limit=30")
            outputs.append(json.dumps(loop_audit, ensure_ascii=False))
            require(status == 200, f"loop-audit status mismatch: {status} {loop_audit}", failures)
            loop_summary = loop_audit.get("summary") or {}
            require(int(loop_summary.get("action_receipts_verified") or 0) >= 1, f"loop-audit lacks verified CLI receipt proof: {loop_summary}", failures)
            require(int(loop_summary.get("action_receipts_evaluated") or 0) >= 1, f"loop-audit lacks CLI receipt evaluation proof: {loop_summary}", failures)
            require(int(loop_summary.get("action_receipts_evaluation_fail") or 0) == 0, f"loop-audit reports CLI receipt evaluation failure: {loop_summary}", failures)
            require(not leaked_secret("\n".join(outputs)), "CLI record receipt output leaked token-like material", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])

    result = {
        "ok": not failures,
        "operation": "operator_action_receipt_cli_record_smoke",
        "failures": failures,
        "secret_leaked": leaked_secret("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
