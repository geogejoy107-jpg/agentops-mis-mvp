#!/usr/bin/env python3
"""Run governed local harness proof commands with exact receipt readback.

Default mode is read-only preview. Pass --confirm-live to execute the
local-harness-proof governed launch packet for Hermes/OpenClaw, record a scoped
operator action receipt, and read it back through exact filters.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"

TOKEN_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bagtok_[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bagtsess_[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bntn_[A-Za-z0-9_-]{16,}"),
]


def token_leaked(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in TOKEN_PATTERNS)


def redact(value: str, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, timeout: int = 30) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": redact(raw)}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def parse_json(raw: str) -> dict:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def compact_failure_payload(payload: dict) -> dict:
    worker_result = payload.get("worker_result") if isinstance(payload.get("worker_result"), dict) else {}
    results = worker_result.get("results") if isinstance(worker_result.get("results"), list) else []
    first_result = results[0] if results and isinstance(results[0], dict) else {}
    loop_gate = first_result.get("loop_supervision_gate") if isinstance(first_result.get("loop_supervision_gate"), dict) else {}
    error = payload.get("error")
    error_payload = parse_json(error) if isinstance(error, str) else {}
    error_results = error_payload.get("results") if isinstance(error_payload.get("results"), list) else []
    error_first = error_results[0] if error_results and isinstance(error_results[0], dict) else {}
    error_gate = error_first.get("loop_supervision_gate") if isinstance(error_first.get("loop_supervision_gate"), dict) else {}
    return {
        "ok": payload.get("ok"),
        "reason": first_result.get("reason") or error_first.get("reason") or payload.get("reason"),
        "processed": first_result.get("processed"),
        "run_id": payload.get("run_id") or first_result.get("run_id"),
        "task_id": payload.get("task_id") or first_result.get("task_id"),
        "recommended_next": (
            loop_gate.get("recommended_next")
            or error_gate.get("recommended_next")
            or ((loop_gate.get("commands") or {}).get("recommended_next") if isinstance(loop_gate.get("commands"), dict) else None)
            or ((error_gate.get("commands") or {}).get("recommended_next") if isinstance(error_gate.get("commands"), dict) else None)
        ),
        "attention": loop_gate.get("attention") or error_gate.get("attention") or [],
        "blocked_gate_ids": loop_gate.get("blocked_gate_ids") or error_gate.get("blocked_gate_ids") or [],
        "output_summary": redact(payload.get("output_summary") or first_result.get("output_summary") or error_first.get("output_summary") or "", 260),
        "token_omitted": True,
    }


def fetch_governed_packet(base_url: str, adapter: str, timeout: int) -> tuple[dict, list[str]]:
    failures: list[str] = []
    status, payload = http_json("GET", base_url, "/api/operator/local-harness-proof?freshness_hours=72&limit=8", timeout=timeout)
    require(status == 200, f"{adapter}: local-harness-proof status mismatch: {status} {payload}", failures)
    adapter_payload = ((payload.get("adapters") or {}).get(adapter) or {})
    governed = adapter_payload.get("governed_launch") or {}
    require(governed.get("adapter") == adapter, f"{adapter}: governed adapter mismatch: {governed}", failures)
    require(governed.get("operation") == "customer_worker_task", f"{adapter}: governed operation mismatch: {governed}", failures)
    require("agentops workflow customer-worker-task" in str(governed.get("confirmed_command") or ""), f"{adapter}: missing governed confirmed command: {governed}", failures)
    require("--confirm-run" in str(governed.get("confirmed_command") or ""), f"{adapter}: live governed command must require --confirm-run: {governed}", failures)
    receipt_readback = str(governed.get("receipt_readback_command") or "")
    require("--source local_harness_proof.governed_launch" in receipt_readback, f"{adapter}: receipt source filter missing: {governed}", failures)
    require(f"--action-id local_harness_proof:{adapter}" in receipt_readback, f"{adapter}: receipt action-id filter missing: {governed}", failures)
    require("--action-signature" in receipt_readback, f"{adapter}: receipt action-signature filter missing: {governed}", failures)
    return governed, failures


def command_to_argv(command: str) -> list[str]:
    argv = shlex.split(command)
    if argv and argv[0] == "agentops":
        argv[0] = str(CLI)
    return argv


def run_governed_command(base_url: str, command: str, timeout: int) -> tuple[dict, list[str]]:
    failures: list[str] = []
    argv = command_to_argv(command)
    require(bool(argv), "governed command is empty", failures)
    require("--confirm-run" in argv, f"governed live command must include --confirm-run: {command}", failures)
    if failures:
        return {"ok": False}, failures
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url.rstrip("/")
    env["AGENTOPS_REQUEST_TIMEOUT"] = str(timeout)
    proc = subprocess.run(
        argv,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout + 30,
        check=False,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    payload = parse_json(stdout)
    require(proc.returncode == 0, f"governed command exited {proc.returncode}: {redact(stderr or stdout)}", failures)
    compact_payload = compact_failure_payload(payload)
    require(payload.get("provider") == "agentops-worker", f"governed command did not use agentops-worker: {compact_payload}", failures)
    require(payload.get("workflow") == "customer_worker_task", f"governed command wrong workflow: {compact_payload}", failures)
    require(payload.get("ok") is True, f"governed command did not complete: {compact_failure_payload(payload)}", failures)
    require(payload.get("dry_run") is False, f"governed command must not be dry-run under --confirm-live: {compact_payload}", failures)
    require(bool(payload.get("run_id")), f"governed command missing run_id: {compact_payload}", failures)
    require(bool(payload.get("artifact_id")), f"governed command missing artifact_id: {compact_payload}", failures)
    evidence = payload.get("evidence") or {}
    for key in ["tool_calls", "evaluations", "runtime_events", "audit_logs", "artifacts", "memories", "approvals", "plan_evidence_manifests"]:
        require(int(evidence.get(key) or 0) >= 1, f"governed command missing {key} evidence: {evidence}", failures)
    require(not token_leaked(stdout + stderr + json.dumps(payload, ensure_ascii=False)), "governed command output leaked token-like material", failures)
    return payload, failures


def run_service_closure(base_url: str, adapter: str, timeout: int) -> tuple[dict, list[str]]:
    failures: list[str] = []
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url.rstrip("/")
    argv = [
        str(CLI),
        "operator",
        "service-closure",
        "--adapter",
        adapter,
        "--service-check-agent-id",
        f"agt_worker_daemon_{adapter}",
        "--fast",
        "--run-service-check",
        "--confirm-record",
    ]
    proc = subprocess.run(
        argv,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    payload = parse_json(stdout)
    require(proc.returncode == 0, f"{adapter}: service-closure exited {proc.returncode}: {redact(stderr or stdout)}", failures)
    require(payload.get("operation") == "operator_service_closure", f"{adapter}: service-closure wrong operation: {payload}", failures)
    require(payload.get("recorded") is True, f"{adapter}: service-closure did not record: {payload}", failures)
    require((payload.get("safety") or {}).get("live_execution_performed") is False, f"{adapter}: service-closure must not execute live runtime: {payload}", failures)
    require((payload.get("safety") or {}).get("server_executes_shell") is False, f"{adapter}: service-closure must not run server shell: {payload}", failures)
    require(not token_leaked(stdout + stderr + json.dumps(payload, ensure_ascii=False)), f"{adapter}: service-closure leaked token-like material", failures)
    return {
        "ok": payload.get("ok"),
        "status": payload.get("status"),
        "receipt_id": payload.get("receipt_id"),
        "service_check": payload.get("service_check"),
        "safety": payload.get("safety"),
        "token_omitted": True,
    }, failures


def record_receipt(base_url: str, adapter: str, governed: dict, run_payload: dict, timeout: int) -> tuple[dict, list[str]]:
    failures: list[str] = []
    action_signature = str(governed.get("action_signature") or "")
    payload = {
        "action_command": governed.get("confirmed_command") or "",
        "verify_command": governed.get("evidence_readback_command") or "agentops operator local-harness-proof --limit 8",
        "action_id": f"local_harness_proof:{adapter}",
        "action_signature": action_signature,
        "source": "local_harness_proof.governed_launch",
        "status": "verified" if run_payload.get("ok") is True else "failed",
        "result_summary": (
            f"Governed local harness live launch recorded for {adapter}; "
            f"run_id={run_payload.get('run_id')}; artifact_id={run_payload.get('artifact_id')}."
        ),
    }
    status, receipt = http_json("POST", base_url, "/api/operator/action-receipts", payload, timeout=timeout)
    require(status == 201, f"{adapter}: receipt POST status mismatch: {status} {receipt}", failures)
    item = receipt.get("receipt") or {}
    require(item.get("source") == payload["source"], f"{adapter}: receipt source mismatch: {item}", failures)
    require(item.get("action_id") == payload["action_id"], f"{adapter}: receipt action_id mismatch: {item}", failures)
    require(item.get("action_signature") == action_signature, f"{adapter}: receipt action_signature mismatch: {item}", failures)
    require((receipt.get("evaluation") or {}).get("pass_fail") == "pass", f"{adapter}: receipt evaluation missing/pass mismatch: {receipt}", failures)
    return receipt, failures


def readback_receipt(base_url: str, adapter: str, governed: dict, timeout: int) -> tuple[dict, list[str]]:
    failures: list[str] = []
    query = urlencode({
        "limit": 20,
        "source": "local_harness_proof.governed_launch",
        "action_id": f"local_harness_proof:{adapter}",
        "action_signature": governed.get("action_signature") or "",
    })
    status, readback = http_json("GET", base_url, f"/api/operator/action-receipts?{query}", timeout=timeout)
    require(status == 200, f"{adapter}: receipt readback status mismatch: {status} {readback}", failures)
    require((readback.get("filters") or {}).get("action_id") == f"local_harness_proof:{adapter}", f"{adapter}: readback filters missing: {readback}", failures)
    receipts = readback.get("receipts") or []
    require(len(receipts) >= 1, f"{adapter}: filtered receipt readback missing: {readback}", failures)
    if receipts:
        require(receipts[0].get("action_signature") == governed.get("action_signature"), f"{adapter}: filtered receipt signature mismatch: {readback}", failures)
    return readback, failures


def run_adapter(args: argparse.Namespace, adapter: str) -> dict:
    failures: list[str] = []
    governed, packet_failures = fetch_governed_packet(args.base_url, adapter, args.read_timeout)
    failures.extend(packet_failures)
    result = {
        "adapter": adapter,
        "mode": "live" if args.confirm_live else "preview",
        "governed": {
            "confirmed_command": governed.get("confirmed_command"),
            "receipt_record_command": governed.get("receipt_record_command"),
            "receipt_readback_command": governed.get("receipt_readback_command"),
            "action_signature": governed.get("action_signature"),
            "confirm_required": governed.get("confirm_required"),
        },
        "confirm_live_required": True,
        "receipt_presence_is_runtime_success": False,
        "run_id": None,
        "artifact_id": None,
        "receipt_id": None,
        "receipt_readback_count": 0,
        "live_execution_requested": bool(args.confirm_live),
        "live_execution_performed": False,
        "failures": failures,
    }
    if failures or not args.confirm_live:
        result["ok"] = not failures
        return result
    if args.auto_service_closure:
        service_closure, service_failures = run_service_closure(args.base_url, adapter, args.read_timeout)
        failures.extend(service_failures)
        result["service_closure"] = service_closure
        if failures:
            result["failures"] = failures
            result["ok"] = False
            return result
    run_payload, run_failures = run_governed_command(args.base_url, str(governed.get("confirmed_command") or ""), args.request_timeout)
    failures.extend(run_failures)
    result["run_id"] = run_payload.get("run_id")
    result["artifact_id"] = run_payload.get("artifact_id")
    result["evidence"] = run_payload.get("evidence") or {}
    result["live_execution_performed"] = bool(run_payload.get("ok") is True and run_payload.get("run_id"))
    if not failures and not args.skip_receipt_record:
        receipt, receipt_failures = record_receipt(args.base_url, adapter, governed, run_payload, args.read_timeout)
        failures.extend(receipt_failures)
        result["receipt_id"] = ((receipt.get("receipt") or {}).get("receipt_id"))
        readback, readback_failures = readback_receipt(args.base_url, adapter, governed, args.read_timeout)
        failures.extend(readback_failures)
        result["receipt_readback_count"] = len(readback.get("receipts") or [])
        status_governed, status_failures = fetch_governed_packet(args.base_url, adapter, args.read_timeout)
        failures.extend(status_failures)
        result["receipt_status"] = (status_governed.get("receipt_status") or {})
        require((result["receipt_status"] or {}).get("match") == "current", f"{adapter}: local-harness-proof receipt status not current: {result['receipt_status']}", failures)
    result["failures"] = failures
    result["ok"] = not failures
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run governed local harness live acceptance with scoped receipt readback.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--adapter", action="append", choices=["hermes", "openclaw"], default=None)
    parser.add_argument("--request-timeout", type=int, default=720)
    parser.add_argument("--read-timeout", type=int, default=30)
    parser.add_argument("--confirm-live", action="store_true", help="Required: executes real local Hermes/OpenClaw governed commands.")
    parser.add_argument("--auto-service-closure", action="store_true", help="Before live execution, record fast local service-check receipt/readback evidence without running service-control or runtime.")
    parser.add_argument("--skip-receipt-record", action="store_true", help="Live execution only; do not record/read back the governed launch receipt.")
    args = parser.parse_args()
    adapters = args.adapter or ["hermes", "openclaw"]
    try:
        results = [run_adapter(args, adapter) for adapter in adapters]
        failures = [failure for result in results for failure in result.get("failures", [])]
    except Exception as exc:
        results = []
        failures = [f"unavailable_or_failed: {redact(str(exc), 500)}"]
    serialized = json.dumps(results, ensure_ascii=False)
    if token_leaked(serialized):
        failures.append("output leaked token-like material")
    output = {
        "ok": not failures,
        "operation": "local_harness_governed_live_acceptance",
        "base_url": args.base_url.rstrip("/"),
        "mode": "live" if args.confirm_live else "preview",
        "adapters": adapters,
        "results": results,
        "failures": failures,
        "safety": {
            "live_execution_requested": bool(args.confirm_live),
            "live_execution_performed": any(bool(result.get("live_execution_performed")) for result in results),
            "ledger_mutated": bool(args.confirm_live),
            "receipt_presence_is_runtime_success": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
        "token_omitted": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
