#!/usr/bin/env python3
"""Verify commercial receipts bind to an exact prepared-action hash."""
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
INDEX = ROOT / "docs" / "COMMERCIAL_EVIDENCE_PACKET_INDEX.md"
RELEASE_PACKET = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_RECEIPT_PREPARED_ACTION_BINDING_ACCEPTANCE.md"
COMMAND = "python3 scripts/commercial_receipt_prepared_action_binding_smoke.py"

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


def http_json(base_url: str, path: str, payload: dict | None = None, method: str | None = None) -> tuple[int, dict]:
    raw = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=raw,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method or ("POST" if payload is not None else "GET"),
    )
    try:
        with urlopen(req, timeout=30) as res:
            text = res.read().decode("utf-8")
            return res.status, json.loads(text) if text else {}
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(text)
        except Exception:
            return exc.code, {"raw": text}


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
    return proc.returncode, payload, proc.stdout + proc.stderr


def db_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        queries = {
            "receipt_audit_logs": "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_receipt'",
            "receipt_runtime_events": "SELECT COUNT(*) AS c FROM runtime_events WHERE event_type='operator.action_queue_receipt'",
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
    require("Prepared Action Receipt Binding" in docs["index"], "index missing prepared-action receipt binding row", failures)
    require(COMMAND in docs["index"], "index missing prepared-action receipt binding command", failures)
    require(COMMAND in docs["release"], "release packet missing prepared-action receipt binding command", failures)
    require(COMMAND in docs["ci"], "CI workflow missing prepared-action receipt binding command", failures)
    require(COMMAND in docs["acceptance"], "acceptance missing prepared-action receipt binding command", failures)
    joined = "\n".join(docs.values())
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in prepared-action binding docs: {secret_hits}", failures)


def action_command(prepared_action_id: str, prepared_action_hash: str) -> str:
    parts = [
        "agentops",
        "approval",
        "prepared-action",
        "resume",
        "--action-id",
        prepared_action_id,
        "--expected-action-hash",
        prepared_action_hash,
        "--confirm-human-reviewed",
    ]
    return " ".join(shlex.quote(part) for part in parts)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def main() -> int:
    failures: list[str] = []
    validate_wiring(failures)
    outputs: list[str] = []
    recorded_receipt: dict = {}

    with tempfile.TemporaryDirectory(prefix="agentops-commercial-prepared-receipt-") as tmp:
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
            stamp = time.strftime("%Y%m%d%H%M%S")
            task_id = f"tsk_commercial_receipt_binding_{stamp}"
            agent_id = "agt_research"
            status, task_payload = http_json(base_url, "/api/tasks", {
                "task_id": task_id,
                "workspace_id": "local-demo",
                "title": f"Commercial prepared-action binding smoke {stamp}",
                "description": "Bind an operator receipt to a prepared action hash without executing the action.",
                "owner_agent_id": agent_id,
                "risk_level": "high",
                "acceptance_criteria": "Receipt preview must be dry-run, missing prepared action must fail, and confirmed receipt must expose prepared_action_hash_match.",
            })
            outputs.append(json.dumps(task_payload, ensure_ascii=False))
            require(status in {200, 201}, f"task create failed: {status} {task_payload}", failures)

            status, run_payload = http_json(base_url, "/api/mock-runs/start", {"task_id": task_id, "agent_id": agent_id})
            outputs.append(json.dumps(run_payload, ensure_ascii=False))
            require(status == 201, f"mock run start failed: {status} {run_payload}", failures)
            run_id = (run_payload.get("run") or {}).get("run_id") or run_payload.get("run_id")
            require(bool(run_id), f"run_id missing: {run_payload}", failures)

            prepare_status, prepare_payload = http_json(base_url, "/api/agent-gateway/prepared-actions", {
                "workspace_id": "local-demo",
                "run_id": run_id,
                "agent_id": agent_id,
                "requested_by_agent_id": agent_id,
                "action_type": "commercial.review_receipt",
                "args": {
                    "risk_category": "billing_provider_call",
                    "target_resource": "commercial_config.billing_provider",
                    "action_execution_allowed": False,
                },
                "target_resource": "commercial://billing_provider_call",
                "risk_level": "high",
                "checkpoint": {
                    "checkpoint": "commercial_review_before_billing_provider_call",
                    "raw_payload_stored": False,
                },
                "idempotency_key": f"commercial-prepared-receipt-binding-{stamp}",
                "reason": "Human review receipt must bind to this exact prepared action before any commercial side effect.",
            })
            outputs.append(json.dumps(prepare_payload, ensure_ascii=False))
            require(prepare_status in {200, 201}, f"prepared action create failed: {prepare_status} {prepare_payload}", failures)
            prepared_action = prepare_payload.get("prepared_action") or {}
            prepared_action_id = str(prepared_action.get("action_id") or "")
            prepared_action_hash = str(prepared_action.get("action_hash") or "")
            approval_id = str((prepare_payload.get("approval") or {}).get("approval_id") or "")
            require(bool(prepared_action_id and prepared_action_hash and approval_id), f"prepared action fields missing: {prepare_payload}", failures)

            before = db_counts(db_path)
            code, preview, raw = run_cli(
                env,
                "operator",
                "record-action-receipt",
                "--action-command",
                action_command(prepared_action_id, prepared_action_hash),
                "--verify-command",
                "agentops approval inspect --approval-id " + shlex.quote(approval_id),
                "--action-id",
                "commercial_review_before_billing_provider_call",
                "--action-signature",
                "prepared_action_receipt_binding_v1:billing_provider_call",
                "--prepared-action-id",
                prepared_action_id,
                "--prepared-action-hash",
                prepared_action_hash,
                "--source",
                "commercial.prepared_action_receipt_binding.preview",
                "--status",
                "verified",
                "--result-summary",
                "Preview only; no receipt or side effect has been recorded.",
            )
            outputs.append(raw)
            after_preview = db_counts(db_path)
            require(code == 0, f"preview CLI failed: {code} {raw}", failures)
            require(preview.get("operation") == "operator_action_receipt_cli_preview", f"wrong preview operation: {preview}", failures)
            preview_payload = preview.get("payload_preview") or {}
            require(preview_payload.get("prepared_action_id") == prepared_action_id, f"preview missing prepared action id: {preview}", failures)
            require(before == after_preview, f"preview changed ledger counts: {before} -> {after_preview}", failures)

            bad_status, bad_payload = http_json(base_url, "/api/operator/action-receipts", {
                "workspace_id": "local-demo",
                "actor_id": "usr_founder",
                "action_command": action_command("pa_missing_for_binding", prepared_action_hash),
                "verify_command": "agentops approval inspect --approval-id missing",
                "prepared_action_id": "pa_missing_for_binding",
                "prepared_action_hash": prepared_action_hash,
                "source": "commercial.prepared_action_receipt_binding.missing_probe",
                "status": "verified",
                "result_summary": "This missing prepared action probe must fail closed.",
            })
            outputs.append(json.dumps(bad_payload, ensure_ascii=False))
            after_bad = db_counts(db_path)
            require(bad_status == 404, f"missing prepared action should fail with 404: {bad_status} {bad_payload}", failures)
            require(bad_payload.get("error") == "prepared_action_not_found", f"wrong missing prepared action error: {bad_payload}", failures)
            require(after_bad == after_preview, f"bad bind changed ledger counts: {after_preview} -> {after_bad}", failures)

            code, confirmed, raw = run_cli(
                env,
                "operator",
                "record-action-receipt",
                "--action-command",
                action_command(prepared_action_id, prepared_action_hash),
                "--verify-command",
                "agentops approval inspect --approval-id " + shlex.quote(approval_id),
                "--action-id",
                "commercial_review_before_billing_provider_call",
                "--action-signature",
                "prepared_action_receipt_binding_v1:billing_provider_call",
                "--prepared-action-id",
                prepared_action_id,
                "--prepared-action-hash",
                prepared_action_hash,
                "--source",
                "commercial.prepared_action_receipt_binding",
                "--status",
                "verified",
                "--result-summary",
                "Human review receipt recorded against exact prepared action hash; risky action remains blocked.",
                "--confirm-record",
            )
            outputs.append(raw)
            after_confirm = db_counts(db_path)
            require(code == 0, f"confirmed receipt CLI failed: {code} {raw}", failures)
            require(confirmed.get("operation") == "operator_action_receipt", f"wrong confirmed operation: {confirmed}", failures)
            receipt = confirmed.get("receipt") or {}
            evaluation = confirmed.get("evaluation") or {}
            require(receipt.get("prepared_action_id") == prepared_action_id, f"receipt missing prepared action id: {receipt}", failures)
            require(receipt.get("prepared_action_hash") == prepared_action_hash, f"receipt prepared action hash mismatch: {receipt}", failures)
            require(receipt.get("prepared_action_hash_match") is True, f"receipt hash match not true: {receipt}", failures)
            require(receipt.get("prepared_action_approval_id") == approval_id, f"receipt approval id mismatch: {receipt}", failures)
            require(evaluation.get("pass_fail") == "pass", f"verified receipt evaluation should pass: {evaluation}", failures)
            for key in after_confirm:
                require(after_confirm[key] == after_bad[key] + 1, f"{key} count mismatch: {after_bad} -> {after_confirm}", failures)
            safety = confirmed.get("safety") or {}
            require(safety.get("ledger_mutated") is True, f"confirmed receipt must mutate isolated ledger: {safety}", failures)
            require(safety.get("live_execution_performed") is False, f"receipt must not execute live action: {safety}", failures)
            recorded_receipt = {
                "receipt_id": receipt.get("receipt_id"),
                "prepared_action_id": receipt.get("prepared_action_id"),
                "prepared_action_hash": receipt.get("prepared_action_hash"),
                "prepared_action_hash_match": receipt.get("prepared_action_hash_match"),
                "evaluation_id": evaluation.get("evaluation_id"),
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    output = {
        "operation": "commercial_receipt_prepared_action_binding_smoke",
        "ok": not failures,
        "recorded_receipt": recorded_receipt,
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
            "prepared_action_hash_verified": bool(recorded_receipt.get("prepared_action_hash_match")),
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
        output["failures"].append("secret-like marker leaked in prepared-action receipt binding smoke output")
        rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    return 1 if output["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
