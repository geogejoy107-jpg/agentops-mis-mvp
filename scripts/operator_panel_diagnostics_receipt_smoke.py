#!/usr/bin/env python3
"""Verify UI panel diagnostics can enter the operator receipt/audit loop."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(req, timeout=45) as res:
            return int(res.status), json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw)
        except json.JSONDecodeError:
            return int(exc.code), {"error": raw[:300]}


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, payload = http_json(base_url, "/api/agent-gateway/status")
            if status == 200 and payload.get("token_omitted") is True:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("server did not become ready")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-panel-diagnostics-receipt-") as tmp:
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
            receipt_body = {
                "action_command": "ui://workspace/agents/panel/operator_action_plan:refresh",
                "verify_command": "agentops operator action-receipts --limit 20",
                "action_id": "ui_panel_diagnostics:operator_action_plan",
                "action_signature": "ui_panel_diagnostics:operator_action_plan",
                "source": "ui.panel_diagnostics",
                "status": "failed",
                "result_summary": "panel=operator_action_plan; status=unavailable; attempts=2; token_omitted=true",
            }
            status, receipt = http_json(base_url, "/api/operator/action-receipts", "POST", receipt_body)
            outputs.append(json.dumps(receipt, ensure_ascii=False))
            require(status == 201, f"panel diagnostic receipt POST failed: {status} {receipt}", failures)
            require(((receipt.get("receipt") or {}).get("source") == "ui.panel_diagnostics"), f"panel source not preserved: {receipt}", failures)
            require(((receipt.get("evaluation") or {}).get("pass_fail") == "fail"), f"failed panel receipt should create failed evaluation: {receipt}", failures)
            action_hash = ((receipt.get("receipt") or {}).get("action_hash") or "")
            repeated_body = {
                **receipt_body,
                "result_summary": "panel=operator_action_plan; status=unavailable; attempts=3; token_omitted=true",
            }
            status, repeated_receipt = http_json(base_url, "/api/operator/action-receipts", "POST", repeated_body)
            outputs.append(json.dumps(repeated_receipt, ensure_ascii=False))
            require(status == 201, f"repeated panel diagnostic receipt POST failed: {status} {repeated_receipt}", failures)
            require(((repeated_receipt.get("receipt") or {}).get("action_hash") == action_hash), f"repeated panel receipt should share action hash: {repeated_receipt}", failures)
            require(((repeated_receipt.get("evaluation") or {}).get("pass_fail") == "fail"), f"repeated failed panel receipt should fail evaluation: {repeated_receipt}", failures)

            status, readback = http_json(base_url, "/api/operator/action-receipts?limit=8")
            outputs.append(json.dumps(readback, ensure_ascii=False))
            require(status == 200, f"receipt readback failed: {status} {readback}", failures)
            recent_sources = [item.get("source") for item in readback.get("receipts") or []]
            require("ui.panel_diagnostics" in recent_sources, f"panel receipt missing from recent receipts: {readback}", failures)

            status, action_plan = http_json(base_url, "/api/operator/action-plan?limit=30")
            outputs.append(json.dumps(action_plan, ensure_ascii=False))
            require(status == 200, f"action-plan failed: {status} {action_plan}", failures)
            failure_memory = action_plan.get("receipt_failure_memory") or {}
            failure_candidate = next((item for item in failure_memory.get("candidates") or [] if item.get("action_hash") == action_hash), {})
            require(failure_memory.get("operation") == "receipt_failure_memory_lane", f"action-plan failure-memory lane missing: {failure_memory}", failures)
            require(int(failure_candidate.get("failures") or 0) >= 2, f"panel failures did not become failure-memory candidate: {failure_memory}", failures)
            require("ui.panel_diagnostics" in (failure_candidate.get("sources") or []), f"panel failure-memory source missing: {failure_candidate}", failures)
            memory_action = next((item for item in action_plan.get("actions") or [] if item.get("source") == "receipt_failure_memory"), {})
            require("propose-receipt-failure-memory" in str(memory_action.get("command") or ""), f"action-plan memory action missing: {memory_action}", failures)

            status, loop_audit = http_json(base_url, "/api/operator/loop-audit?limit=12")
            outputs.append(json.dumps(loop_audit, ensure_ascii=False))
            receipt_summary = (((loop_audit.get("sources") or {}).get("action_receipts") or {}).get("summary") or {})
            require(status == 200, f"loop audit failed: {status} {loop_audit}", failures)
            require(int(receipt_summary.get("failed") or 0) >= 1, f"loop audit did not inherit failed panel receipt: {receipt_summary}", failures)

            status, handoff = http_json(base_url, "/api/operator/handoff?limit=12")
            outputs.append(json.dumps(handoff, ensure_ascii=False))
            recent = ((handoff.get("receipt_state") or {}).get("recent") or [])
            failure_work_order = (((handoff.get("work_order") or {}).get("receipt_failure_memory") or {}).get("items") or [])
            require(status == 200, f"handoff failed: {status} {handoff}", failures)
            require(any(item.get("source") == "ui.panel_diagnostics" for item in recent), f"handoff did not package panel receipt: {recent}", failures)
            require(any(item.get("action_hash") == action_hash for item in failure_work_order), f"handoff did not package panel failure-memory work item: {failure_work_order}", failures)
            require((handoff.get("safety") or {}).get("token_omitted") is True, f"handoff token omission proof missing: {handoff.get('safety')}", failures)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    output = {
        "ok": not failures,
        "operation": "operator_panel_diagnostics_receipt_smoke",
        "receipt_source": "ui.panel_diagnostics",
        "safety": {
            "read_path_read_only": False,
            "ledger_mutated_by_receipt": True,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    if leaked_secret("\n".join(outputs) + json.dumps(output, ensure_ascii=False)):
        output["ok"] = False
        output["failures"].append("secret-like value leaked in smoke output")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
