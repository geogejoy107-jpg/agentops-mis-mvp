#!/usr/bin/env python3
"""Offline smoke for the live worker-loop demo slice entrypoint."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import importlib.util
import tempfile
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


def write_launchd_service_fixture(path: Path, adapter: str, base_url: str) -> None:
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.agentops.worker.{adapter}</string>
  <key>ProgramArguments</key>
  <array>
    <string>agentops-worker</string>
    <string>--adapter</string>
    <string>{adapter}</string>
    <string>--confirm-run</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>AGENTOPS_BASE_URL</key>
    <string>{base_url}</string>
  </dict>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
""",
        encoding="utf-8",
    )


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
            "--service-control-timeout",
            "12",
            "--service-control-service-path-template",
            "/tmp/agentops-live/{adapter}.plist",
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
    require(payload.get("confirm_service_control_required") is True, f"service-control confirm wall missing: {payload}", failures)
    require(payload.get("confirm_service_closure_required") is True, f"service-closure confirm wall missing: {payload}", failures)
    steps = payload.get("steps") or []
    require(steps and steps[0].get("advisory") is True, f"readiness probe should be advisory: {payload}", failures)
    commands = payload.get("commands") or {}
    require("customer_worker_real_runtime_acceptance.py" in str(commands.get("real_worker_loop")), f"live command missing: {commands}", failures)
    require("--confirm-live" in str(commands.get("real_worker_loop")), f"confirm-live flag missing: {commands}", failures)
    combined = str(commands.get("service_closure_live_demo") or "")
    require("live_worker_loop_demo_slice.py" in combined, f"combined service-closure/live command missing: {commands}", failures)
    require("--confirm-live" in combined and "--confirm-service-control" in combined and "--confirm-service-closure" in combined, f"combined command confirmation flags missing: {combined}", failures)
    require("--service-control-timeout 12" in combined, f"combined service-control timeout missing: {combined}", failures)
    require("--service-control-service-path-template '/tmp/agentops-live/{adapter}.plist'" in combined, f"combined service-path template missing or unquoted: {combined}", failures)
    require("v1_5_live_product_readiness_smoke.py" in str(commands.get("live_readback")), f"readback command missing: {commands}", failures)
    require("operator live-product-readiness" in str(commands.get("operator_readback")), f"operator readback command missing: {commands}", failures)
    for adapter in ["hermes", "openclaw"]:
        require(f"operator start-check --adapter {adapter}" in str(commands.get(f"{adapter}_start_check")), f"{adapter} start-check command missing: {commands}", failures)
        control = str(commands.get(f"{adapter}_service_control") or "")
        require(f"worker service-control --manager launchd --action load --adapter {adapter}" in control, f"{adapter} service-control command missing: {commands}", failures)
        require("--confirm-control" in control and f"--agent-id agt_worker_daemon_{adapter}" in control, f"{adapter} service-control flags missing: {control}", failures)
        require(f"--service-path /tmp/agentops-live/{adapter}.plist" in control, f"{adapter} service path not rendered: {control}", failures)
        closure = str(commands.get(f"{adapter}_service_closure") or "")
        require(f"operator service-closure --adapter {adapter}" in closure, f"{adapter} service-closure command missing: {commands}", failures)
        require("--fast" in closure and "--run-service-check" in closure and "--confirm-record" in closure, f"{adapter} service-closure flags missing: {closure}", failures)
        loop = str(commands.get(f"{adapter}_loop_driver_auto_service_closure") or "")
        require("--confirm-loop" in loop and "--auto-service-closure" in loop, f"{adapter} auto service closure loop missing: {loop}", failures)
    sequence = payload.get("recommended_sequence") or []
    require("real_worker_loop" in sequence and "live_readback" in sequence, f"recommended sequence missing run/readback: {sequence}", failures)
    require("hermes_service_control" in sequence and "openclaw_service_control" in sequence, f"recommended sequence missing service control: {sequence}", failures)
    require("hermes_service_closure" in sequence and "openclaw_service_closure" in sequence, f"recommended sequence missing service closure: {sequence}", failures)
    require("service_closure_live_demo" in sequence, f"recommended sequence missing combined demo command: {sequence}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("uses_saved_cli_config") is False, f"saved config should not be used: {safety}", failures)
    require(safety.get("token_omitted") is True, f"token omission proof missing: {safety}", failures)
    require(safety.get("requires_explicit_confirm_service_control") is True, f"service-control safety proof missing: {safety}", failures)
    require(safety.get("requires_explicit_confirm_service_closure") is True, f"service-closure safety proof missing: {safety}", failures)

    stale_proc = subprocess.run(
        [
            sys.executable,
            "scripts/live_worker_loop_demo_slice.py",
            "--base-url",
            "http://127.0.0.1:9",
            "--probe-timeout",
            "1",
            "--confirm-live",
            "--adapter",
            "hermes",
            "--service-control-timeout",
            "1",
            "--request-timeout",
            "1",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    require(stale_proc.returncode == 1, f"stale current-code gate should fail closed: {stale_proc.stdout} {stale_proc.stderr}", failures)
    try:
        stale_payload = json.loads(stale_proc.stdout)
    except json.JSONDecodeError as exc:
        stale_payload = {}
        failures.append(f"invalid stale gate JSON output: {exc}")
    require(stale_payload.get("failures") == ["local_readiness_current_code_required"], f"stale gate failure mismatch: {stale_payload}", failures)
    require(stale_payload.get("live_execution_performed") is False, f"stale gate attempted live runtime: {stale_payload}", failures)
    require(stale_payload.get("service_control_attempted") is False, f"stale gate attempted service-control: {stale_payload}", failures)
    require(stale_payload.get("service_closure_attempted") is False, f"stale gate attempted service-closure: {stale_payload}", failures)
    require(stale_payload.get("ledger_mutated") is False, f"stale gate mutated ledger: {stale_payload}", failures)
    stale_safety = stale_payload.get("safety") or {}
    require(stale_safety.get("requires_current_code_server") is True, f"stale gate safety proof missing: {stale_safety}", failures)
    require(stale_safety.get("failed_before_live_runtime") is True, f"stale gate live proof missing: {stale_safety}", failures)
    require(not leaked_secret(stale_proc.stdout + stale_proc.stderr), "stale gate output leaked token-like material", failures)

    with tempfile.TemporaryDirectory(prefix="agentops-live-demo-preflight-") as tmp:
        tmp_path = Path(tmp)
        for adapter in ["hermes", "openclaw"]:
            write_launchd_service_fixture(tmp_path / f"{adapter}.plist", adapter, "http://127.0.0.1:9")
        preflight_proc = subprocess.run(
            [
                sys.executable,
                "scripts/live_worker_loop_demo_slice.py",
                "--base-url",
                "http://127.0.0.1:9",
                "--probe-timeout",
                "1",
                "--preflight",
                "--service-control-timeout",
                "12",
                "--service-control-service-path-template",
                str(tmp_path / "{adapter}.plist"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        require(preflight_proc.returncode == 0, f"preflight command failed: {preflight_proc.stderr or preflight_proc.stdout}", failures)
        try:
            preflight = json.loads(preflight_proc.stdout)
        except json.JSONDecodeError as exc:
            preflight = {}
            failures.append(f"invalid preflight JSON output: {exc}")
        require(preflight.get("mode") == "preflight", f"preflight mode missing: {preflight}", failures)
        require(preflight.get("ok") is True, f"preflight should be ok with local fixtures: {preflight}", failures)
        require(preflight.get("live_execution_performed") is False, f"preflight executed live work: {preflight}", failures)
        require(preflight.get("service_control_mutated") is False, f"preflight mutated service-control: {preflight}", failures)
        require(preflight.get("service_closure_attempted") is False, f"preflight wrote service closure: {preflight}", failures)
        require(preflight.get("ledger_mutated") is False, f"preflight mutated ledger: {preflight}", failures)
        preflight_safety = preflight.get("safety") or {}
        require(preflight_safety.get("preflight_only") is True, f"preflight safety proof missing: {preflight_safety}", failures)
        preflight_steps = preflight.get("steps") or []
        for adapter in ["hermes", "openclaw"]:
            control_step = next((step for step in preflight_steps if step.get("name") == f"{adapter}_service_control_preflight"), {})
            require(bool(control_step), f"{adapter} service-control preflight step missing: {preflight_steps}", failures)
            control_summary = control_step.get("summary") if isinstance(control_step.get("summary"), dict) else {}
            require(control_summary.get("dry_run") is True, f"{adapter} preflight should be dry-run: {control_summary}", failures)
            require(control_summary.get("confirmed_control") is False, f"{adapter} preflight should not confirm control: {control_summary}", failures)
            require(control_summary.get("service_mutated") is False, f"{adapter} preflight mutated service: {control_summary}", failures)
            require(control_summary.get("live_execution_performed") is False, f"{adapter} preflight ran live runtime: {control_summary}", failures)
            require(control_summary.get("service_file_exists") is True, f"{adapter} preflight did not inspect fixture service file: {control_summary}", failures)
            readback_step = next((step for step in preflight_steps if step.get("name") == f"{adapter}_service_closure_readback_preflight"), {})
            require(bool(readback_step), f"{adapter} service-closure readback preflight missing: {preflight_steps}", failures)
            require(readback_step.get("advisory") is True, f"{adapter} readback preflight should be advisory without server: {readback_step}", failures)
        require(not leaked_secret(preflight_proc.stdout + preflight_proc.stderr), "preflight output leaked token-like material", failures)

    demo_module = load_demo_module()
    service_command = demo_module.service_control_command_args(
        "http://127.0.0.1:9",
        "hermes",
        "launchd",
        "load",
        "/tmp/agentops-live/{adapter}.plist",
        confirm_control=True,
    )
    command_text = " ".join(service_command)
    require("--adapter hermes" in command_text, f"service-control helper adapter order regressed: {service_command}", failures)
    require("--manager launchd" in command_text, f"service-control helper manager order regressed: {service_command}", failures)
    require("--action load" in command_text, f"service-control helper action order regressed: {service_command}", failures)
    require("--service-path /tmp/agentops-live/hermes.plist" in command_text, f"service-control helper service path regressed: {service_command}", failures)
    require("--confirm-control" in service_command, f"service-control helper confirm flag missing: {service_command}", failures)

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
            "service_control_confirm_wall",
            "service_closure_fail_closed_helper",
            "preflight_service_control_preview",
            "current_code_gate_before_live",
            "service_control_command_helper_order",
        ],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
