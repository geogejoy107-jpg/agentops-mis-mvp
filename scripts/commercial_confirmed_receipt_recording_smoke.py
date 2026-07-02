#!/usr/bin/env python3
"""Verify commercial receipt previews can be explicitly recorded to an isolated ledger."""
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

from commercial_receipt_recording_smoke import receipt_requests


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
INDEX = ROOT / "docs" / "COMMERCIAL_EVIDENCE_PACKET_INDEX.md"
RELEASE_PACKET = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_CONFIRMED_RECEIPT_RECORDING_ACCEPTANCE.md"
COMMAND = "python3 scripts/commercial_confirmed_receipt_recording_smoke.py"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9_]+"),
    re.compile(r"AGENTOPS_(API|ADMIN)_KEY=", re.IGNORECASE),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as res:
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
            status, _ = http_json(base_url, "/api/operator/action-receipts?limit=1")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def run_cli(env: dict[str, str], *args: str) -> tuple[int, dict, str]:
    proc = subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception:
        payload = {"raw": proc.stdout}
    return proc.returncode, payload, proc.stderr


def db_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        queries = {
            "audit_logs": "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt'",
            "runtime_events": "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type='operator.action_queue_receipt'",
            "operator_action_evaluations": "SELECT COUNT(*) AS c FROM operator_action_evaluations",
            "evaluation_audit_logs": "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_evaluation'",
        }
        return {key: int(conn.execute(sql).fetchone()["c"] or 0) for key, sql in queries.items()}
    finally:
        conn.close()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def validate_wiring(failures: list[str]) -> None:
    docs = {
        "index": read(INDEX),
        "release": read(RELEASE_PACKET),
        "ci": read(CI_WORKFLOW),
        "acceptance": read(ACCEPTANCE),
    }
    require("Confirmed Receipt Recording" in docs["index"], "index missing confirmed receipt recording row", failures)
    require(COMMAND in docs["index"], "index missing confirmed receipt recording command", failures)
    require(COMMAND in docs["release"], "release packet missing confirmed receipt recording command", failures)
    require(COMMAND in docs["ci"], "CI workflow missing confirmed receipt recording command", failures)
    require(COMMAND in docs["acceptance"], "acceptance missing confirmed receipt recording command", failures)
    joined = "\n".join(docs.values())
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in confirmed receipt docs: {secret_hits}", failures)


def action_command_for(request: dict) -> str:
    normalized = request.get("normalized_action_arguments") or {}
    parts = [
        "agentops",
        "commercial",
        "review-receipt",
        "--risk",
        str(normalized.get("risk_category") or request.get("action_id") or "unknown"),
        "--checkpoint",
        str(normalized.get("checkpoint") or "commercial_review"),
        "--action-hash",
        str(request.get("action_hash") or ""),
    ]
    return " ".join(shlex.quote(part) for part in parts)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def main() -> int:
    failures: list[str] = []
    validate_wiring(failures)
    requests = receipt_requests()
    outputs: list[str] = []
    recorded_receipts: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="agentops-commercial-confirmed-receipt-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_BASE_URL"] = base_url
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
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
            before = db_counts(db_path)
            first = requests[0]
            preview_code, preview, preview_err = run_cli(
                env,
                "operator",
                "record-action-receipt",
                "--action-command",
                action_command_for(first),
                "--verify-command",
                str(first.get("verify_command") or ""),
                "--action-id",
                str(first.get("action_id") or ""),
                "--action-signature",
                str(first.get("action_signature") or ""),
                "--source",
                "commercial.confirmed_receipt_recording.preview",
                "--status",
                "verified",
                "--result-summary",
                "Preview only; risky commercial action remains blocked.",
            )
            outputs.extend([json.dumps(preview, ensure_ascii=False), preview_err])
            after_preview = db_counts(db_path)
            require(preview_code == 0, f"preview CLI failed: {preview_code} {preview_err}", failures)
            require(preview.get("operation") == "operator_action_receipt_cli_preview", f"wrong preview operation: {preview}", failures)
            require(preview.get("recorded") is False, f"preview should not record: {preview}", failures)
            require(before == after_preview, f"preview changed ledger counts: {before} -> {after_preview}", failures)

            running_counts = after_preview
            for request in requests:
                code, payload, err = run_cli(
                    env,
                    "operator",
                    "record-action-receipt",
                    "--action-command",
                    action_command_for(request),
                    "--verify-command",
                    str(request.get("verify_command") or ""),
                    "--action-id",
                    str(request.get("action_id") or ""),
                    "--action-signature",
                    str(request.get("action_signature") or ""),
                    "--source",
                    "commercial.confirmed_receipt_recording",
                    "--status",
                    "verified",
                    "--result-summary",
                    "Human review receipt recorded; risky commercial action remains blocked.",
                    "--confirm-record",
                )
                outputs.extend([json.dumps(payload, ensure_ascii=False), err])
                require(code == 0, f"confirmed receipt CLI failed: {code} {err}", failures)
                require(payload.get("operation") == "operator_action_receipt", f"wrong receipt operation: {payload}", failures)
                require(payload.get("confirm_record") is True, f"confirm marker missing: {payload}", failures)
                safety = payload.get("safety") or {}
                require(safety.get("ledger_mutated") is True, f"confirmed receipt should mutate isolated ledger: {safety}", failures)
                require(safety.get("live_execution_performed") is False, f"receipt must not execute live work: {safety}", failures)
                receipt = payload.get("receipt") or {}
                evaluation = payload.get("evaluation") or {}
                require(receipt.get("action_signature") == request.get("action_signature"), f"action signature mismatch: {receipt}", failures)
                require(bool(receipt.get("tamper_chain_hash")), f"tamper hash missing: {receipt}", failures)
                require(evaluation.get("pass_fail") == "pass", f"verified receipt evaluation should pass: {evaluation}", failures)
                recorded_receipts.append(
                    {
                        "receipt_id": receipt.get("receipt_id"),
                        "action_id": receipt.get("action_id"),
                        "action_hash": receipt.get("action_hash"),
                        "verify_hash": receipt.get("verify_hash"),
                        "evaluation_id": evaluation.get("evaluation_id"),
                    }
                )
            after_confirm = db_counts(db_path)
            expected_delta = len(requests)
            for key in ["audit_logs", "runtime_events", "operator_action_evaluations", "evaluation_audit_logs"]:
                require(
                    after_confirm[key] == running_counts[key] + expected_delta,
                    f"{key} count mismatch: {running_counts} -> {after_confirm}",
                    failures,
                )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    output = {
        "operation": "commercial_confirmed_receipt_recording_smoke",
        "ok": not failures,
        "receipt_request_count": len(requests),
        "recorded_receipt_count": len(recorded_receipts),
        "recorded_receipts": recorded_receipts,
        "safety": {
            "isolated_temp_db": True,
            "default_db_touched": False,
            "server_started": True,
            "ledger_mutated": True,
            "ledger_mutation_scope": "isolated_temp_sqlite_only",
            "billing_call_performed": False,
            "cleanup_execution_performed": False,
            "hosted_migration_performed": False,
            "postgres_cutover_performed": False,
            "live_execution_performed": False,
            "action_command_executed": False,
            "raw_logs_omitted": True,
            "raw_prompts_omitted": True,
            "raw_responses_omitted": True,
            "token_omitted": True,
        },
        "failure_count": len(failures),
        "failures": failures,
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    if leaked_secret(rendered) or leaked_secret("\n".join(outputs)):
        output["ok"] = False
        output["failure_count"] += 1
        output["failures"].append("secret-like marker leaked in confirmed receipt smoke output")
        rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    return 1 if output["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
