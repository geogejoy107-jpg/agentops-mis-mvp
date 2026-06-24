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


def cli_json(base_url: str, *args: str) -> tuple[int, dict, str]:
    proc = subprocess.run(
        [str(ROOT / "scripts" / "agentops"), "--base-url", base_url, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception:
        payload = {"raw": proc.stdout}
    return proc.returncode, payload, proc.stderr


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
        evaluation_row = conn.execute(
            "SELECT COUNT(*) AS c FROM operator_action_evaluations"
        ).fetchone()
        evaluation_audit_row = conn.execute(
            "SELECT COUNT(*) AS c FROM audit_logs WHERE action='operator.action_queue_evaluation'"
        ).fetchone()
        receipt_failure_memory_row = conn.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE source_ref LIKE 'operator_action_receipts://%'"
        ).fetchone()
        return {
            "audit_logs": int(audit_row["c"] or 0),
            "runtime_events": int(runtime_row["c"] or 0),
            "operator_action_evaluations": int(evaluation_row["c"] or 0),
            "evaluation_audit_logs": int(evaluation_audit_row["c"] or 0),
            "receipt_failure_memories": int(receipt_failure_memory_row["c"] or 0),
        }
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
        env["AGENTOPS_BASE_URL"] = base_url
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
            failed_seed_action = next((
                item for item in seed_plan.get("actions") or []
                if item.get("command")
                and item.get("action_signature")
                and item.get("receipt_required") is True
                and item.get("command") not in {seed_action.get("command"), stale_seed_action.get("command")}
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
            evaluation = receipt.get("evaluation") or {}
            require(evaluation.get("pass_fail") == "pass", f"verified receipt evaluation should pass: {evaluation}", failures)
            require(float(evaluation.get("score") or 0) == 1.0, f"verified receipt evaluation score wrong: {evaluation}", failures)
            require(evaluation.get("receipt_id") == item.get("receipt_id"), f"receipt evaluation id mismatch: {evaluation}", failures)

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
                stale_evaluation = stale_receipt.get("evaluation") or {}
                require(stale_evaluation.get("pass_fail") == "pass", f"stale verified receipt evaluation should pass: {stale_evaluation}", failures)

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
            require(int(summary.get("evaluated") or 0) == 0, f"recorded-only recent receipts should not be evaluated: {summary}", failures)
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
            require(int(receipt_coverage.get("stale") or 0) >= 1, f"receipt coverage lacks stale action: {receipt_coverage}", failures)
            require(int(receipt_coverage.get("missing") or 0) >= 1, f"receipt coverage lacks missing actions: {receipt_coverage}", failures)
            require(receipt_coverage.get("status") == "attention", f"receipt coverage should require attention while stale/missing exist: {receipt_coverage}", failures)
            require((action_plan.get("source_status") or {}).get("action_receipts") == "ready", f"action-plan receipt source missing: {action_plan.get('source_status')}", failures)
            plan_receipts = action_plan.get("action_receipts") or {}
            require(plan_receipts.get("operation") == "operator_action_receipts", f"action-plan receipt payload missing: {plan_receipts}", failures)
            plan_receipt_ids = {row.get("receipt_id") for row in plan_receipts.get("receipts") or []}
            require(item.get("receipt_id") not in plan_receipt_ids, f"target receipt should be outside action-plan display source: {plan_receipts}", failures)
            matched_action = next((row for row in action_plan.get("actions") or [] if row.get("command") == payload["action_command"]), {})
            if matched_action:
                require(int(receipt_coverage.get("verified") or 0) >= 1, f"receipt coverage lacks verified action: {receipt_coverage}", failures)
                require(matched_action.get("receipt_status") == "verified", f"action-plan action receipt status missing: {matched_action}", failures)
                require(matched_action.get("receipt_verified") is True, f"action-plan action receipt proof missing: {matched_action}", failures)
                require(matched_action.get("receipt_id") == item.get("receipt_id"), f"action-plan action receipt id mismatch: {matched_action}", failures)
                require(bool(matched_action.get("receipt_hash")), f"action-plan action receipt hash missing: {matched_action}", failures)
                matched_evaluation = matched_action.get("receipt_evaluation") or (matched_action.get("receipt_state") or {}).get("evaluation") or {}
                require(matched_evaluation.get("pass_fail") == "pass", f"action-plan receipt evaluation missing: {matched_action}", failures)
                require(matched_evaluation.get("receipt_id") == item.get("receipt_id"), f"action-plan receipt evaluation id mismatch: {matched_action}", failures)
            else:
                require(int(receipt_coverage.get("lookup_window") or 0) > int(receipt_coverage.get("display_receipts") or 0), f"receipt lookup should be deeper when verified target is outside queue window: {receipt_coverage}", failures)
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

            failed_payload = None
            failed_item = None
            repeated_failure_memory_id = None
            if failed_seed_action:
                failed_payload = {
                    "action_command": str(failed_seed_action.get("command") or "agentops worker status"),
                    "verify_command": str(failed_seed_action.get("verify_command") or "agentops operator action-plan --limit 20"),
                    "action_id": str(failed_seed_action.get("action_id") or "smoke:failed-action"),
                    "action_signature": str(failed_seed_action.get("action_signature") or ""),
                    "source": "smoke.operator_action_queue.failed",
                    "status": "failed",
                    "result_summary": "Smoke failed receipt should project back into action-plan recovery.",
                }
                status, failed_receipt = http_json(base_url, "/api/operator/action-receipts", "POST", failed_payload)
                outputs.append(json.dumps(failed_receipt, ensure_ascii=False))
                require(status == 201, f"failed POST status mismatch: {status} {failed_receipt}", failures)
                failed_item = failed_receipt.get("receipt") or {}
                failed_evaluation = failed_receipt.get("evaluation") or {}
                require(failed_evaluation.get("pass_fail") == "fail", f"failed receipt evaluation should fail: {failed_evaluation}", failures)
                require(float(failed_evaluation.get("score") if failed_evaluation.get("score") is not None else 1) == 0.0, f"failed receipt evaluation score wrong: {failed_evaluation}", failures)

                repeated_failed_payload = {
                    **failed_payload,
                    "source": "smoke.operator_action_queue.failed.repeat",
                    "result_summary": "Smoke repeated failed receipt should propose a memory candidate.",
                }
                status, repeated_failed_receipt = http_json(base_url, "/api/operator/action-receipts", "POST", repeated_failed_payload)
                outputs.append(json.dumps(repeated_failed_receipt, ensure_ascii=False))
                require(status == 201, f"repeated failed POST status mismatch: {status} {repeated_failed_receipt}", failures)
                repeated_failed_item = repeated_failed_receipt.get("receipt") or {}
                repeated_failed_evaluation = repeated_failed_receipt.get("evaluation") or {}
                require(repeated_failed_item.get("action_hash") == failed_item.get("action_hash"), f"repeated failed action hash mismatch: {repeated_failed_item} {failed_item}", failures)
                require(repeated_failed_evaluation.get("pass_fail") == "fail", f"repeated failed receipt evaluation should fail: {repeated_failed_evaluation}", failures)

                status, failed_plan = http_json(base_url, "/api/operator/action-plan?limit=30")
                outputs.append(json.dumps(failed_plan, ensure_ascii=False))
                require(status == 200, f"failed action-plan status mismatch: {status} {failed_plan}", failures)
                failed_plan_summary = failed_plan.get("summary") or {}
                failed_coverage = failed_plan.get("receipt_coverage") or {}
                require(int(failed_plan_summary.get("receipt_evaluation_fail_actions") or 0) >= 1, f"failed receipt evaluation not counted: {failed_plan_summary}", failures)
                require(int(failed_plan_summary.get("receipt_failure_memory_candidates") or 0) >= 1, f"receipt failure memory candidate not counted: {failed_plan_summary}", failures)
                require(failed_coverage.get("evaluation_status") == "blocked", f"failed receipt evaluation should block coverage: {failed_coverage}", failures)
                failure_memory_source = failed_plan.get("receipt_failure_memory") or {}
                require(failure_memory_source.get("operation") == "receipt_failure_memory_lane", f"receipt failure memory source missing: {failure_memory_source}", failures)
                failure_memory_candidate = next((row for row in failure_memory_source.get("candidates") or [] if row.get("action_hash") == failed_item.get("action_hash")), {})
                require(bool(failure_memory_candidate), f"receipt failure memory candidate missing for failed action: {failure_memory_source}", failures)
                require(int(failure_memory_candidate.get("failures") or 0) >= 2, f"receipt failure memory failure count wrong: {failure_memory_candidate}", failures)
                require("propose-receipt-failure-memory" in str(failure_memory_candidate.get("command") or ""), f"receipt failure memory candidate command wrong: {failure_memory_candidate}", failures)
                require(any("propose-receipt-failure-memory" in str(item) for item in (failure_memory_source.get("next_actions") or [])), f"receipt failure memory next action missing: {failure_memory_source}", failures)
                memory_action = next((row for row in failed_plan.get("actions") or [] if row.get("source") == "receipt_failure_memory"), {})
                if memory_action:
                    require("propose-receipt-failure-memory" in str(memory_action.get("command") or ""), f"receipt failure memory command wrong: {memory_action}", failures)
                recovery_action = next((row for row in failed_plan.get("actions") or [] if row.get("source") == "receipt_evaluation"), {})
                require(bool(recovery_action), f"failed receipt recovery action missing: {failed_plan.get('actions')}", failures)
                require(recovery_action.get("severity") == "blocked", f"failed receipt recovery action should be blocked: {recovery_action}", failures)
                failed_matched_action = next((row for row in failed_plan.get("actions") or [] if row.get("command") == failed_payload["action_command"]), {})
                require(failed_matched_action.get("receipt_status") == "failed", f"failed action receipt status missing: {failed_matched_action}", failures)
                failed_matched_eval = failed_matched_action.get("receipt_evaluation") or (failed_matched_action.get("receipt_state") or {}).get("evaluation") or {}
                require(failed_matched_eval.get("pass_fail") == "fail", f"failed action receipt evaluation missing: {failed_matched_action}", failures)

                cli_code, cli_lane, cli_stderr = cli_json(base_url, "operator", "receipt-failure-memories", "--min-failures", "2", "--limit", "5")
                outputs.append(json.dumps(cli_lane, ensure_ascii=False) + cli_stderr)
                require(cli_code == 0, f"receipt failure memory CLI lane failed: {cli_code} {cli_lane} {cli_stderr}", failures)
                require(cli_lane.get("operation") == "receipt_failure_memory_lane", f"receipt failure memory CLI lane operation wrong: {cli_lane}", failures)
                cli_candidate = next((row for row in cli_lane.get("candidates") or [] if row.get("action_hash") == failed_item.get("action_hash")), {})
                require(int(cli_candidate.get("failures") or 0) >= 2, f"receipt failure memory CLI candidate missing: {cli_lane}", failures)

                cli_code, cli_preview, cli_stderr = cli_json(
                    base_url,
                    "operator",
                    "propose-receipt-failure-memory",
                    "--action-hash",
                    str(failed_item.get("action_hash") or ""),
                    "--min-failures",
                    "2",
                )
                outputs.append(json.dumps(cli_preview, ensure_ascii=False) + cli_stderr)
                require(cli_code == 0, f"receipt failure memory CLI preview failed: {cli_code} {cli_preview} {cli_stderr}", failures)
                require(cli_preview.get("status") == "preview", f"receipt failure memory CLI preview wrong: {cli_preview}", failures)
                require(cli_preview.get("confirm_create") is False, f"receipt failure memory CLI preview should not confirm: {cli_preview}", failures)
                require((cli_preview.get("safety") or {}).get("ledger_mutated") is False, f"receipt failure memory CLI preview mutated ledger: {cli_preview}", failures)

                status, failure_memory_preview = http_json(
                    base_url,
                    "/api/operator/receipt-failure-memories/propose",
                    "POST",
                    {"action_hash": failed_item.get("action_hash"), "min_failures": 2},
                )
                outputs.append(json.dumps(failure_memory_preview, ensure_ascii=False))
                require(status == 200, f"receipt failure memory preview status mismatch: {status} {failure_memory_preview}", failures)
                require(failure_memory_preview.get("status") == "preview", f"receipt failure memory preview wrong: {failure_memory_preview}", failures)
                preview_safety = failure_memory_preview.get("safety") or {}
                require(preview_safety.get("read_only") is True, f"receipt failure memory preview should be read-only: {preview_safety}", failures)
                require(preview_safety.get("ledger_mutated") is False, f"receipt failure memory preview mutated ledger: {preview_safety}", failures)
                preview_memory = failure_memory_preview.get("memory") or {}
                require(preview_memory.get("review_status") == "candidate", f"receipt failure memory preview status missing: {preview_memory}", failures)

                status, failure_memory_created = http_json(
                    base_url,
                    "/api/operator/receipt-failure-memories/propose",
                    "POST",
                    {"action_hash": failed_item.get("action_hash"), "min_failures": 2, "confirm_create": True},
                )
                outputs.append(json.dumps(failure_memory_created, ensure_ascii=False))
                require(status in {200, 201}, f"receipt failure memory create status mismatch: {status} {failure_memory_created}", failures)
                require(failure_memory_created.get("status") in {"created", "updated"}, f"receipt failure memory create wrong: {failure_memory_created}", failures)
                create_safety = failure_memory_created.get("safety") or {}
                require(create_safety.get("ledger_mutated") is True, f"receipt failure memory create should mutate ledger: {create_safety}", failures)
                repeated_failure_memory_id = failure_memory_created.get("memory_id")
                require(bool(repeated_failure_memory_id), f"receipt failure memory id missing: {failure_memory_created}", failures)
                require(failure_memory_created.get("review_status") == "candidate", f"receipt failure memory review status wrong: {failure_memory_created}", failures)

                status, review_queue = http_json(base_url, "/api/review/queue?limit=20")
                outputs.append(json.dumps(review_queue, ensure_ascii=False))
                require(status == 200, f"review queue status mismatch: {status} {review_queue}", failures)
                review_item = next((row for row in review_queue.get("review_items") or [] if row.get("item_id") == repeated_failure_memory_id), {})
                require(review_item.get("item_type") == "memory_candidate", f"receipt failure memory not visible in review queue: {review_queue}", failures)
                require(review_item.get("kind") == "failure_case", f"receipt failure memory kind wrong: {review_item}", failures)

            status, loop_audit = http_json(base_url, "/api/operator/loop-audit?limit=30")
            outputs.append(json.dumps(loop_audit, ensure_ascii=False))
            require(status == 200, f"loop-audit status mismatch: {status} {loop_audit}", failures)
            loop_summary = loop_audit.get("summary") or {}
            require(int(loop_summary.get("receipt_coverage_percent") or 0) == int(receipt_coverage.get("coverage_percent") or 0), f"loop-audit receipt coverage percent mismatch: {loop_summary} {receipt_coverage}", failures)
            loop_receipts = ((loop_audit.get("sources") or {}).get("action_receipts") or {})
            loop_receipt_coverage = loop_receipts.get("coverage") or {}
            require(loop_receipt_coverage.get("status") == receipt_coverage.get("status"), f"loop-audit receipt coverage source mismatch: {loop_receipt_coverage} {receipt_coverage}", failures)
            require(loop_receipts.get("status") == "ready", f"loop-audit receipt source missing: {loop_receipts}", failures)
            record_step = next((step for step in loop_audit.get("steps") or [] if step.get("id") == "record"), {})
            record_evidence = record_step.get("evidence") or {}
            require(int(record_evidence.get("receipt_lookup_window") or 0) >= int(record_evidence.get("action_receipts") or 0), f"RECORD evidence lacks deeper receipt lookup: {record_evidence}", failures)
            if matched_action:
                require(int(loop_summary.get("receipt_verified_actions") or 0) >= 1, f"loop-audit verified action receipt count missing: {loop_summary}", failures)
                require(int(record_evidence.get("receipt_verified_actions") or 0) >= 1, f"RECORD evidence lacks verified action receipt: {record_evidence}", failures)
            if failed_payload:
                require(int(record_evidence.get("receipt_evaluation_fail_actions") or 0) >= 1, f"RECORD evidence lacks failed receipt evaluation: {record_evidence}", failures)

            after = db_counts(db_path)
            expected_writes = 1 + (1 if stale_payload else 0) + unrelated_writes + (2 if failed_payload else 0)
            require(after["audit_logs"] == before["audit_logs"] + expected_writes, f"audit count did not increase by {expected_writes}: {before} -> {after}", failures)
            expected_evaluations = 1 + (1 if stale_payload else 0) + (2 if failed_payload else 0)
            require(after["operator_action_evaluations"] == before["operator_action_evaluations"] + expected_evaluations, f"operator action evaluation count wrong: {before} -> {after}", failures)
            require(after["evaluation_audit_logs"] == before["evaluation_audit_logs"] + expected_evaluations, f"operator action evaluation audit count wrong: {before} -> {after}", failures)
            require(after["runtime_events"] == before["runtime_events"] + expected_writes, f"runtime count did not increase by {expected_writes}: {before} -> {after}", failures)
            if repeated_failure_memory_id:
                require(after["receipt_failure_memories"] == before["receipt_failure_memories"] + 1, f"receipt failure memory count wrong: {before} -> {after}", failures)
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
