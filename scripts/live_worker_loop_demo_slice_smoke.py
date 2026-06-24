#!/usr/bin/env python3
"""Offline smoke for the live worker-loop demo slice entrypoint."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bagtok_[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bagtsess_[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bntn_[A-Za-z0-9_-]{16,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in TOKEN_PATTERNS)


def load_demo_module():
    module_path = ROOT / "scripts" / "live_worker_loop_demo_slice.py"
    spec = importlib.util.spec_from_file_location("live_worker_loop_demo_slice", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    failures: list[str] = []
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/live_worker_loop_demo_slice.py",
            "--base-url",
            "http://127.0.0.1:9",
            "--probe-timeout",
            "1",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    require(proc.returncode == 0, f"plan-only command failed: {proc.stderr or proc.stdout}", failures)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        payload = {}
        failures.append(f"invalid JSON output: {exc}")
    require(payload.get("operation") == "live_worker_loop_demo_slice", f"wrong operation: {payload}", failures)
    require(payload.get("ok") is True, f"plan-only output should be ok: {payload}", failures)
    require(payload.get("mode") == "plan_only", f"plan-only mode missing: {payload}", failures)
    require(payload.get("live_execution_performed") is False, f"plan-only executed live work: {payload}", failures)
    require(payload.get("ledger_mutated") is False, f"plan-only mutated ledger: {payload}", failures)
    require(payload.get("confirm_live_required") is True, f"confirm wall missing: {payload}", failures)
    require(payload.get("confirm_service_closure_required") is True, f"service-closure confirm wall missing: {payload}", failures)
    steps = payload.get("steps") or []
    require(steps and steps[0].get("advisory") is True, f"readiness probe should be advisory: {payload}", failures)
    commands = payload.get("commands") or {}
    require("customer_worker_real_runtime_acceptance.py" in str(commands.get("real_worker_loop")), f"live command missing: {commands}", failures)
    require("--confirm-live" in str(commands.get("real_worker_loop")), f"confirm-live flag missing: {commands}", failures)
    combined = str(commands.get("service_closure_live_demo") or "")
    require("live_worker_loop_demo_slice.py" in combined, f"combined service-closure/live command missing: {commands}", failures)
    require("--confirm-live" in combined and "--confirm-service-closure" in combined, f"combined command confirmation flags missing: {combined}", failures)
    require("v1_5_live_product_readiness_smoke.py" in str(commands.get("live_readback")), f"readback command missing: {commands}", failures)
    require("operator live-product-readiness" in str(commands.get("operator_readback")), f"operator readback command missing: {commands}", failures)
    for adapter in ["hermes", "openclaw"]:
        require(f"operator start-check --adapter {adapter}" in str(commands.get(f"{adapter}_start_check")), f"{adapter} start-check command missing: {commands}", failures)
        closure = str(commands.get(f"{adapter}_service_closure") or "")
        require(f"operator service-closure --adapter {adapter}" in closure, f"{adapter} service-closure command missing: {commands}", failures)
        require("--fast" in closure and "--run-service-check" in closure and "--confirm-record" in closure, f"{adapter} service-closure flags missing: {closure}", failures)
        loop = str(commands.get(f"{adapter}_loop_driver_auto_service_closure") or "")
        require("--confirm-loop" in loop and "--auto-service-closure" in loop, f"{adapter} auto service closure loop missing: {loop}", failures)
    sequence = payload.get("recommended_sequence") or []
    require("real_worker_loop" in sequence and "live_readback" in sequence, f"recommended sequence missing run/readback: {sequence}", failures)
    require("hermes_service_closure" in sequence and "openclaw_service_closure" in sequence, f"recommended sequence missing service closure: {sequence}", failures)
    require("service_closure_live_demo" in sequence, f"recommended sequence missing combined demo command: {sequence}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("uses_saved_cli_config") is False, f"saved config should not be used: {safety}", failures)
    require(safety.get("token_omitted") is True, f"token omission proof missing: {safety}", failures)
    require(safety.get("requires_explicit_confirm_service_closure") is True, f"service-closure safety proof missing: {safety}", failures)

    demo_module = load_demo_module()
    open_gate_item = {
        "service_closure": {"required": True, "status": "attention", "step": "confirm_service_control_load"},
        "local_deployment": {
            "service_managed_loop": {
                "receipt_verified": True,
                "control_readback_attached": True,
                "service_check_ok": True,
                "service_file_exists": True,
                "service_confirm_gate_ok": True,
                "service_relaunch_policy_ok": True,
                "service_loaded": False,
                "service_managed_loop_ready": False,
                "service_active_loop_ready": False,
            }
        },
    }
    incomplete_closed_gate_item = {
        "service_closure": {"required": False, "status": "pass"},
        "local_deployment": {
            "service_managed_loop": {
                "receipt_verified": True,
                "control_readback_attached": True,
                "service_check_ok": True,
                "service_file_exists": True,
                "service_confirm_gate_ok": True,
                "service_relaunch_policy_ok": True,
                "service_loaded": False,
                "service_managed_loop_ready": True,
                "service_active_loop_ready": False,
            }
        },
    }
    closed_gate_item = {
        "service_closure": {"required": False, "status": "pass"},
        "local_deployment": {
            "service_managed_loop": {
                "receipt_verified": True,
                "control_readback_attached": True,
                "service_check_ok": True,
                "service_file_exists": True,
                "service_confirm_gate_ok": True,
                "service_relaunch_policy_ok": True,
                "service_loaded": True,
                "service_managed_loop_ready": True,
                "service_active_loop_ready": True,
            }
        },
    }
    require(demo_module.service_closure_allows_live(open_gate_item) is False, "open service-closure gate should fail closed", failures)
    require(demo_module.service_closure_allows_live(incomplete_closed_gate_item) is False, "closed-looking service-closure gate without loaded service should fail closed", failures)
    require(demo_module.service_closure_allows_live(closed_gate_item) is True, "closed service-closure gate should allow live dispatch", failures)
    require(not leaked_secret(proc.stdout + proc.stderr), "plan-only output leaked token-like material", failures)
    print(json.dumps({
        "operation": "live_worker_loop_demo_slice_smoke",
        "ok": not failures,
        "failures": failures,
        "checked": [
            "plan_only_default",
            "confirm_live_wall",
            "base_url_explicit",
            "no_saved_cli_config",
            "no_token_like_output",
            "service_closure_fail_closed_helper",
        ],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
