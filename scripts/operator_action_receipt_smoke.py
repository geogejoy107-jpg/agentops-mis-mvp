#!/usr/bin/env python3
"""Verify operator action queue receipts write runtime/audit evidence safely."""

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
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
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


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


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
        return {"audit_logs": int(audit_row["c"] or 0), "runtime_events": int(runtime_row["c"] or 0)}
    finally:
        conn.close()


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


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-action-receipt-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
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
            status, seed_plan = http_json(base_url, "/api/operator/action-plan?limit=30")
            outputs.append(json.dumps(seed_plan, ensure_ascii=False))
            require(status == 200, f"seed action-plan status mismatch: {status} {seed_plan}", failures)
            seed_action = next((item for item in seed_plan.get("actions") or [] if item.get("command") and item.get("receipt_required") is True), {})
            stale_seed_action = next((
                item for item in seed_plan.get("actions") or []
                if item.get("command")
                and item.get("action_signature")
                and item.get("receipt_required") is True
                and item.get("command") != seed_action.get("command")
            ), {})
            action_command = str(seed_action.get("command") or "agentops worker status")
            verify_command = str(seed_action.get("verify_command") or "agentops operator action-plan --limit 20")
            payload = {
                "action_command": action_command,
                "verify_command": verify_command,
                "action_id": str(seed_action.get("action_id") or "smoke:operator-action"),
                "action_signature": str(seed_action.get("action_signature") or ""),
                "source": "smoke.operator_action_queue",
                "status": "verified",
                "result_summary": "Smoke verified action queue receipt recording.",
            }
            status, receipt = http_json(base_url, "/api/operator/action-receipts", "POST", payload)
            outputs.append(json.dumps(receipt, ensure_ascii=False))
            require(status == 201, f"POST status mismatch: {status} {receipt}", failures)
            require(receipt.get("operation") == "operator_action_receipt", f"wrong operation: {receipt}", failures)
            require(receipt.get("status") == "verified", f"wrong receipt status: {receipt}", failures)
            safety = receipt.get("safety") or {}
            require(safety.get("ledger_mutated") is True, f"receipt should mutate ledger: {safety}", failures)
            require(safety.get("live_execution_performed") is False, f"receipt must not execute live work: {safety}", failures)
            item = receipt.get("receipt") or {}
            require(bool(item.get("receipt_id")), f"receipt_id missing: {receipt}", failures)
            require(bool(item.get("audit_id")), f"audit_id missing: {receipt}", failures)
            require(bool(item.get("tamper_chain_hash")), f"tamper hash missing: {receipt}", failures)
            require(item.get("action_command") == payload["action_command"], f"action command mismatch: {item}", failures)
            require(item.get("verify_command") == payload["verify_command"], f"verify command mismatch: {item}", failures)
            require(item.get("action_signature") == payload["action_signature"], f"action signature mismatch: {item}", failures)
            require(bool(item.get("action_hash")), f"action hash missing: {item}", failures)
            require(bool(item.get("verify_hash")), f"verify hash missing: {item}", failures)

            stale_payload = None
            stale_item = None
            if stale_seed_action:
                stale_payload = {
                    "action_command": f"agentops stale-receipt-placeholder --action-id {stale_seed_action.get('action_id')}",
                    "verify_command": str(stale_seed_action.get("verify_command") or "agentops operator action-plan --limit 20"),
                    "action_id": str(stale_seed_action.get("action_id") or "smoke:stale-action"),
                    "action_signature": str(stale_seed_action.get("action_signature") or ""),
                    "source": "smoke.operator_action_queue.stale",
                    "status": "verified",
                    "result_summary": "Smoke stale receipt should not verify the current action command.",
                }
                status, stale_receipt = http_json(base_url, "/api/operator/action-receipts", "POST", stale_payload)
                outputs.append(json.dumps(stale_receipt, ensure_ascii=False))
                require(status == 201, f"stale POST status mismatch: {status} {stale_receipt}", failures)
                stale_item = stale_receipt.get("receipt") or {}
                require(stale_item.get("action_signature") == stale_payload["action_signature"], f"stale action signature mismatch: {stale_item}", failures)

            unrelated_writes = 35
            for index in range(unrelated_writes):
                noise_payload = {
                    "action_command": f"agentops unrelated-receipt-noise --index {index}",
                    "verify_command": "agentops operator action-plan --limit 20",
                    "action_id": f"smoke:unrelated:{index}",
                    "action_signature": f"smoke_unrelated_signature_{index}",
                    "source": "smoke.operator_action_queue.unrelated",
                    "status": "recorded",
                    "result_summary": "Noise receipt used to prove action-plan lookup is deeper than recent display rows.",
                }
                status, noise_receipt = http_json(base_url, "/api/operator/action-receipts", "POST", noise_payload)
                outputs.append(json.dumps(noise_receipt, ensure_ascii=False))
                require(status == 201, f"noise POST status mismatch at {index}: {status} {noise_receipt}", failures)

            status, readback = http_json(base_url, "/api/operator/action-receipts?limit=5")
            outputs.append(json.dumps(readback, ensure_ascii=False))
            require(status == 200, f"GET status mismatch: {status} {readback}", failures)
            require(readback.get("operation") == "operator_action_receipts", f"wrong readback operation: {readback}", failures)
            summary = readback.get("summary") or {}
            require(int(summary.get("recorded") or 0) == 5, f"recent receipt display should contain latest noise receipts: {summary}", failures)
            receipt_ids = {row.get("receipt_id") for row in readback.get("receipts") or []}
            require(item.get("receipt_id") not in receipt_ids, f"target receipt should be older than recent display rows: {readback}", failures)

            status, action_plan = http_json(base_url, "/api/operator/action-plan?limit=30")
            outputs.append(json.dumps(action_plan, ensure_ascii=False))
            require(status == 200, f"action-plan status mismatch: {status} {action_plan}", failures)
            plan_summary = action_plan.get("summary") or {}
            receipt_coverage = action_plan.get("receipt_coverage") or {}
            coverage_action = next((row for row in action_plan.get("actions") or [] if row.get("source") == "receipt_coverage"), {})
            require(bool(coverage_action), f"receipt coverage recovery action missing: {action_plan.get('actions')}", failures)
            require(coverage_action.get("receipt_required") is False, f"coverage recovery action should not require receipt: {coverage_action}", failures)
            require(coverage_action.get("verify_command") == "agentops operator loop-audit --limit 20", f"coverage recovery verify command wrong: {coverage_action}", failures)
            require(int(plan_summary.get("receipt_lookup_window") or 0) > int((action_plan.get("action_receipts") or {}).get("summary", {}).get("receipts") or 0), f"action-plan lookup should be deeper than display receipts: {plan_summary}", failures)
            require(int(receipt_coverage.get("verified") or 0) >= 1, f"receipt coverage lacks verified action: {receipt_coverage}", failures)
            require(int(receipt_coverage.get("stale") or 0) >= 1, f"receipt coverage lacks stale action: {receipt_coverage}", failures)
            require(int(receipt_coverage.get("missing") or 0) >= 1, f"receipt coverage lacks missing actions: {receipt_coverage}", failures)
            require(receipt_coverage.get("status") == "attention", f"receipt coverage should require attention while stale/missing exist: {receipt_coverage}", failures)
            require((action_plan.get("source_status") or {}).get("action_receipts") == "ready", f"action-plan receipt source missing: {action_plan.get('source_status')}", failures)
            plan_receipts = action_plan.get("action_receipts") or {}
            require(plan_receipts.get("operation") == "operator_action_receipts", f"action-plan receipt payload missing: {plan_receipts}", failures)
            plan_receipt_ids = {row.get("receipt_id") for row in plan_receipts.get("receipts") or []}
            require(item.get("receipt_id") not in plan_receipt_ids, f"target receipt should be outside action-plan display source: {plan_receipts}", failures)
            matched_action = next((row for row in action_plan.get("actions") or [] if row.get("command") == payload["action_command"]), {})
            require(matched_action.get("receipt_status") == "verified", f"action-plan action receipt status missing: {matched_action}", failures)
            require(matched_action.get("receipt_verified") is True, f"action-plan action receipt proof missing: {matched_action}", failures)
            require(matched_action.get("receipt_id") == item.get("receipt_id"), f"action-plan action receipt id mismatch: {matched_action}", failures)
            require(bool(matched_action.get("receipt_hash")), f"action-plan action receipt hash missing: {matched_action}", failures)
            shared_verify = [
                row for row in action_plan.get("actions") or []
                if row.get("command") != payload["action_command"]
                and row.get("verify_command") == payload["verify_command"]
            ]
            for other in shared_verify:
                require(other.get("receipt_verified") is False, f"shared verify command should not verify another action: {other}", failures)
                require(other.get("receipt_match") != "current", f"shared verify command should not create current match: {other}", failures)
                require(int(other.get("receipt_priority_boost") or 0) == 8, f"shared verify action should keep receipt boost: {other}", failures)
            if stale_payload:
                stale_action = next((row for row in action_plan.get("actions") or [] if row.get("action_signature") == stale_payload["action_signature"]), {})
                require(stale_action.get("receipt_status") == "stale", f"stale receipt should not verify current action: {stale_action}", failures)
                require(stale_action.get("receipt_verified") is False, f"stale receipt verified current action: {stale_action}", failures)
                require(stale_action.get("receipt_match") == "stale", f"stale receipt match missing: {stale_action}", failures)
                require(int(stale_action.get("receipt_priority_boost") or 0) == 8, f"stale receipt should keep priority boost: {stale_action}", failures)
                require(stale_action.get("receipt_id") == stale_item.get("receipt_id"), f"stale receipt id mismatch: {stale_action}", failures)

            status, loop_audit = http_json(base_url, "/api/operator/loop-audit?limit=30")
            outputs.append(json.dumps(loop_audit, ensure_ascii=False))
            require(status == 200, f"loop-audit status mismatch: {status} {loop_audit}", failures)
            loop_summary = loop_audit.get("summary") or {}
            require(int(loop_summary.get("receipt_verified_actions") or 0) >= 1, f"loop-audit verified action receipt count missing: {loop_summary}", failures)
            require(int(loop_summary.get("receipt_coverage_percent") or 0) == int(receipt_coverage.get("coverage_percent") or 0), f"loop-audit receipt coverage percent mismatch: {loop_summary} {receipt_coverage}", failures)
            loop_receipts = ((loop_audit.get("sources") or {}).get("action_receipts") or {})
            loop_receipt_coverage = loop_receipts.get("coverage") or {}
            require(loop_receipt_coverage.get("status") == receipt_coverage.get("status"), f"loop-audit receipt coverage source mismatch: {loop_receipt_coverage} {receipt_coverage}", failures)
            require(loop_receipts.get("status") == "ready", f"loop-audit receipt source missing: {loop_receipts}", failures)
            record_step = next((step for step in loop_audit.get("steps") or [] if step.get("id") == "record"), {})
            record_evidence = record_step.get("evidence") or {}
            require(int(record_evidence.get("receipt_verified_actions") or 0) >= 1, f"RECORD evidence lacks verified action receipt: {record_evidence}", failures)
            require(int(record_evidence.get("receipt_lookup_window") or 0) >= int(record_evidence.get("action_receipts") or 0), f"RECORD evidence lacks deeper receipt lookup: {record_evidence}", failures)

            after = db_counts(db_path)
            expected_writes = 1 + (1 if stale_payload else 0) + unrelated_writes
            require(after["audit_logs"] == before["audit_logs"] + expected_writes, f"audit count did not increase by {expected_writes}: {before} -> {after}", failures)
            require(after["runtime_events"] == before["runtime_events"] + expected_writes, f"runtime count did not increase by {expected_writes}: {before} -> {after}", failures)
            require(not leaked_secret("\n".join(outputs)), "receipt output leaked token-like material", failures)
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
        "operation": "operator_action_receipt_smoke",
        "failures": failures,
        "secret_leaked": leaked_secret("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
