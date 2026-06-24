#!/usr/bin/env python3
"""One-command local demo slice for the real Agent Worker loop.

Default mode is read-only and plan-only. Pass ``--confirm-live`` only on a
local machine where Hermes/OpenClaw are explicitly authorized and available.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

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


def http_get_json(base_url: str, path: str, timeout: int) -> tuple[bool, dict[str, Any]]:
    url = base_url.rstrip("/") + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return True, json.loads(raw or "{}")
    except Exception as exc:
        return False, {"error": str(exc), "url": url, "token_omitted": True}


def http_get_json_query(base_url: str, path: str, query: dict[str, Any], timeout: int) -> tuple[bool, dict[str, Any]]:
    clean_query = {
        key: str(value)
        for key, value in query.items()
        if value is not None
    }
    suffix = urllib.parse.urlencode(clean_query)
    return http_get_json(base_url, f"{path}?{suffix}" if suffix else path, timeout)


def run_json(command: list[str], env: dict[str, str], timeout: int) -> tuple[bool, dict[str, Any]]:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    raw = proc.stdout.strip() or proc.stderr.strip()
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw_tail": raw[-1600:]}
    return proc.returncode == 0 and payload.get("ok", True) is not False, {"returncode": proc.returncode, "payload": payload}


def shell_join(parts: list[Any]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def env_command(base_url: str, parts: list[Any]) -> str:
    return f"AGENTOPS_BASE_URL={shlex.quote(base_url)} {shell_join(parts)}"


def service_path_from_template(template: str, adapter: str) -> str:
    return template.format(adapter=adapter) if template else ""


def planned_commands(
    base_url: str,
    adapters: list[str],
    request_timeout: int,
    hermes_timeout: int,
    hermes_max_tokens: int,
    service_control_manager: str,
    service_control_action: str,
    service_control_timeout: int,
    service_control_service_path_template: str,
) -> dict[str, str]:
    adapter_flags = [item for adapter in adapters for item in ["--adapter", adapter]]
    require_flags = [item for adapter in adapters for item in ["--require-adapter", adapter]]
    service_control_flags: list[Any] = [
        "--service-control-manager",
        service_control_manager,
        "--service-control-action",
        service_control_action,
        "--service-control-timeout",
        service_control_timeout,
    ]
    if service_control_service_path_template:
        service_control_flags.extend(["--service-control-service-path-template", service_control_service_path_template])
    commands = {
        "readiness": env_command(base_url, ["./scripts/agentops", "local", "readiness", "--require-current-code"]),
        "service_closure_live_demo": env_command(base_url, [
            "python3",
            "scripts/live_worker_loop_demo_slice.py",
            "--base-url",
            base_url,
            "--confirm-live",
            "--confirm-service-control",
            "--confirm-service-closure",
            *adapter_flags,
            "--request-timeout",
            request_timeout,
            "--hermes-timeout",
            hermes_timeout,
            "--hermes-max-tokens",
            hermes_max_tokens,
            *service_control_flags,
        ]),
        "real_worker_loop": env_command(base_url, [
            "python3",
            "scripts/customer_worker_real_runtime_acceptance.py",
            "--base-url",
            base_url,
            "--confirm-live",
            *adapter_flags,
            "--request-timeout",
            request_timeout,
            "--hermes-timeout",
            hermes_timeout,
            "--hermes-max-tokens",
            hermes_max_tokens,
        ]),
        "live_readback": env_command(base_url, [
            "python3",
            "scripts/v1_5_live_product_readiness_smoke.py",
            "--base-url",
            base_url,
            *require_flags,
        ]),
        "operator_readback": env_command(base_url, [
            "./scripts/agentops",
            "operator",
            "live-product-readiness",
            *require_flags,
        ]),
    }
    for adapter in adapters:
        service_control_command: list[Any] = [
            "./scripts/agentops",
            "worker",
            "service-control",
            "--manager",
            service_control_manager,
            "--action",
            service_control_action,
            "--adapter",
            adapter,
            "--agent-id",
            f"agt_worker_daemon_{adapter}",
            "--confirm-control",
        ]
        service_path = service_path_from_template(service_control_service_path_template, adapter)
        if service_path:
            service_control_command.extend(["--service-path", service_path])
        commands[f"{adapter}_start_check"] = env_command(base_url, ["./scripts/agentops", "operator", "start-check", "--adapter", adapter, "--limit", 8])
        commands[f"{adapter}_service_control"] = env_command(base_url, service_control_command)
        commands[f"{adapter}_service_closure"] = env_command(base_url, [
            "./scripts/agentops",
            "operator",
            "service-closure",
            "--adapter",
            adapter,
            "--fast",
            "--run-service-check",
            "--confirm-record",
        ])
        commands[f"{adapter}_loop_driver_auto_service_closure"] = env_command(base_url, [
            "./scripts/agentops",
            "operator",
            "loop-driver",
            "--adapter",
            adapter,
            "--max-steps",
            1,
            "--limit",
            8,
            "--confirm-loop",
            "--auto-service-closure",
        ])
    return commands


def compact_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    return {
        "operation": payload.get("operation"),
        "status": payload.get("status"),
        "local_demo_ready": payload.get("local_demo_ready"),
        "running_instance_current": evidence.get("running_instance_current"),
        "live_acceptance_fresh_adapters": evidence.get("live_acceptance_fresh_adapters"),
        "closed_loop_runs": evidence.get("closed_loop_runs"),
        "knowledge_documents": evidence.get("knowledge_documents"),
        "knowledge_chunks": evidence.get("knowledge_chunks"),
        "token_omitted": payload.get("token_omitted") is True,
    }


def readiness_current_code_ok(payload: dict[str, Any]) -> bool:
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    return evidence.get("running_instance_current") is True


def compact_live_acceptance(payload: dict[str, Any]) -> dict[str, Any]:
    failures = [str(item)[:360] for item in (payload.get("failures") or [])[:3]]
    return {
        "operation": payload.get("operation"),
        "ok": payload.get("ok"),
        "results": [
            {
                "adapter": item.get("adapter"),
                "ok": item.get("ok"),
                "task_id": item.get("task_id"),
                "run_id": item.get("run_id"),
                "artifact_id": item.get("artifact_id"),
                "approval_id": item.get("approval_id"),
                "plan_evidence_manifest_id": item.get("plan_evidence_manifest_id"),
                "evidence": item.get("evidence"),
            }
            for item in payload.get("results") or []
            if isinstance(item, dict)
        ],
        "failure_count": len(payload.get("failures") or []),
        "failures": failures,
        "token_omitted": payload.get("token_omitted") is True,
    }


def compact_service_closure(adapter: str, payload: dict[str, Any]) -> dict[str, Any]:
    service_closure = payload.get("service_closure") if isinstance(payload.get("service_closure"), dict) else {}
    receipt = payload.get("receipt") if isinstance(payload.get("receipt"), dict) else {}
    control_readback = payload.get("control_readback") if isinstance(payload.get("control_readback"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    return {
        "adapter": adapter,
        "operation": payload.get("operation"),
        "ok": payload.get("ok"),
        "status": payload.get("status"),
        "service_closure": {
            "required": service_closure.get("required"),
            "status": service_closure.get("status"),
            "step": service_closure.get("step"),
            "phase": service_closure.get("phase"),
        },
        "receipt_id": ((receipt.get("receipt") or {}) if isinstance(receipt.get("receipt"), dict) else receipt).get("receipt_id"),
        "control_readback_id": control_readback.get("control_readback_id") or control_readback.get("receipt_id"),
        "local_cli_service_check_performed": safety.get("local_cli_service_check_performed") is True,
        "live_execution_performed": safety.get("live_execution_performed") is True,
        "ledger_mutated": safety.get("ledger_mutated") is True,
        "token_omitted": payload.get("token_omitted") is True,
    }


def compact_service_control(adapter: str, payload: dict[str, Any]) -> dict[str, Any]:
    service_check = payload.get("service_check") if isinstance(payload.get("service_check"), dict) else {}
    service_file = service_check.get("service_file") if isinstance(service_check.get("service_file"), dict) else {}
    service_status = service_check.get("service_status") if isinstance(service_check.get("service_status"), dict) else {}
    return {
        "adapter": adapter,
        "provider": payload.get("provider"),
        "command": payload.get("command"),
        "ok": payload.get("ok"),
        "action": payload.get("action"),
        "manager": payload.get("manager"),
        "dry_run": payload.get("dry_run"),
        "confirmed_control": payload.get("confirmed_control") is True,
        "service_mutated": payload.get("service_mutated") is True,
        "live_execution_performed": payload.get("live_execution_performed") is True,
        "service_path": payload.get("service_path"),
        "service_file_exists": service_file.get("exists") is True,
        "service_loaded": service_status.get("loaded") is True,
        "failures": [str(item)[:240] for item in (payload.get("failures") or [])[:3]],
        "raw_content_omitted": payload.get("raw_content_omitted") is True,
        "token_omitted": payload.get("token_omitted") is True,
    }


def service_closure_item(payload: dict[str, Any], adapter: str) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return next((item for item in items if isinstance(item, dict) and item.get("adapter") == adapter), {})


def service_closure_allows_live(item: dict[str, Any]) -> bool:
    closure = item.get("service_closure") if isinstance(item.get("service_closure"), dict) else {}
    local_deployment = item.get("local_deployment") if isinstance(item.get("local_deployment"), dict) else {}
    service_loop = local_deployment.get("service_managed_loop") if isinstance(local_deployment.get("service_managed_loop"), dict) else {}
    return (
        closure.get("required") is False
        and closure.get("status") == "pass"
        and service_loop.get("receipt_verified") is True
        and service_loop.get("control_readback_attached") is True
        and service_loop.get("service_check_ok") is True
        and service_loop.get("service_file_exists") is True
        and service_loop.get("service_confirm_gate_ok") is True
        and service_loop.get("service_relaunch_policy_ok") is True
        and service_loop.get("service_loaded") is True
        and service_loop.get("service_managed_loop_ready") is True
        and service_loop.get("service_active_loop_ready") is True
    )


def service_control_command_args(
    base_url: str,
    adapter: str,
    manager: str,
    action: str,
    service_path_template: str,
    *,
    confirm_control: bool,
) -> list[str]:
    command = [
        str(ROOT / "scripts" / "agentops"),
        "--base-url",
        base_url,
        "worker",
        "service-control",
        "--manager",
        manager,
        "--action",
        action,
        "--adapter",
        adapter,
        "--agent-id",
        f"agt_worker_daemon_{adapter}",
    ]
    if confirm_control:
        command.append("--confirm-control")
    service_path = service_path_from_template(service_path_template, adapter)
    if service_path:
        command.extend(["--service-path", service_path])
    return command


def service_closure_readback_step(base_url: str, adapter: str, timeout: int) -> tuple[bool, bool, dict[str, Any]]:
    readback_ok, readback = http_get_json_query(
        base_url,
        "/api/operator/loop-supervision",
        {
            "adapter": adapter,
            "limit": 8,
            "include_codex": "false",
        },
        timeout,
    )
    if not readback_ok:
        return False, False, readback
    return True, service_closure_allows_live(service_closure_item(readback, adapter)), compact_service_closure_readback(adapter, readback)


def compact_service_closure_readback(adapter: str, payload: dict[str, Any]) -> dict[str, Any]:
    item = service_closure_item(payload, adapter)
    closure = item.get("service_closure") if isinstance(item.get("service_closure"), dict) else {}
    local_deployment = item.get("local_deployment") if isinstance(item.get("local_deployment"), dict) else {}
    service_loop = local_deployment.get("service_managed_loop") if isinstance(local_deployment.get("service_managed_loop"), dict) else {}
    return {
        "adapter": adapter,
        "operation": payload.get("operation"),
        "status": payload.get("status"),
        "allows_live": service_closure_allows_live(item),
        "service_closure": {
            "required": closure.get("required"),
            "status": closure.get("status"),
            "step": closure.get("step"),
            "phase": closure.get("phase"),
        },
        "service_managed_loop": {
            "status": service_loop.get("status"),
            "receipt_verified": service_loop.get("receipt_verified") is True,
            "control_readback_attached": service_loop.get("control_readback_attached") is True,
            "service_check_ok": service_loop.get("service_check_ok") is True,
            "service_file_exists": service_loop.get("service_file_exists") is True,
            "service_confirm_gate_ok": service_loop.get("service_confirm_gate_ok") is True,
            "service_relaunch_policy_ok": service_loop.get("service_relaunch_policy_ok") is True,
            "service_loaded": service_loop.get("service_loaded") is True,
            "service_managed_loop_ready": service_loop.get("service_managed_loop_ready") is True,
            "service_active_loop_ready": service_loop.get("service_active_loop_ready") is True,
        },
        "next_action": item.get("next_action"),
        "token_omitted": payload.get("token_omitted") is True,
    }


def compact_live_readback(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": payload.get("operation"),
        "ok": payload.get("ok"),
        "product_readiness_proof": payload.get("product_readiness_proof"),
        "live_acceptance_status": payload.get("live_acceptance_status"),
        "local_readiness_status": payload.get("local_readiness_status"),
        "adapters": [
            {
                "adapter": item.get("adapter"),
                "status": item.get("status"),
                "run_id": item.get("run_id"),
                "task_id": item.get("task_id"),
                "artifact_id": item.get("artifact_id"),
                "plan_evidence_manifest_id": item.get("plan_evidence_manifest_id"),
            }
            for item in payload.get("adapters") or []
            if isinstance(item, dict)
        ],
        "failures": payload.get("failures") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or preview the local Hermes/OpenClaw worker-loop demo slice.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--adapter", action="append", choices=["hermes", "openclaw"], default=None)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Run non-mutating service-control preview and loop-supervision readback before any live confirmation.",
    )
    parser.add_argument("--confirm-live", action="store_true", help="Run real local Hermes/OpenClaw customer-worker acceptance.")
    parser.add_argument(
        "--confirm-service-control",
        action="store_true",
        help="Before service-closure, explicitly run local worker service-control for each adapter. This may mutate local OS service state.",
    )
    parser.add_argument(
        "--confirm-service-closure",
        action="store_true",
        help="Before the live worker run, record fast service-closure receipt/readback evidence for each selected adapter.",
    )
    parser.add_argument("--request-timeout", type=int, default=720)
    parser.add_argument("--hermes-timeout", type=int, default=600)
    parser.add_argument("--hermes-max-tokens", type=int, default=512)
    parser.add_argument("--service-control-manager", choices=["launchd", "systemd"], default="launchd")
    parser.add_argument("--service-control-action", choices=["load", "restart"], default="load")
    parser.add_argument("--service-control-timeout", type=int, default=30)
    parser.add_argument(
        "--service-control-service-path-template",
        default="",
        help="Optional service path template for service-control. Use {adapter} to render adapter-specific paths.",
    )
    parser.add_argument("--service-closure-timeout", type=int, default=30)
    parser.add_argument("--probe-timeout", type=int, default=5)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    adapters = args.adapter or ["hermes", "openclaw"]
    commands = planned_commands(
        base_url,
        adapters,
        args.request_timeout,
        args.hermes_timeout,
        args.hermes_max_tokens,
        args.service_control_manager,
        args.service_control_action,
        args.service_control_timeout,
        args.service_control_service_path_template,
    )
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url

    readiness_ok, readiness = http_get_json(base_url, "/api/local/readiness", args.probe_timeout)
    steps: list[dict[str, Any]] = [{
        "name": "local_readiness_probe",
        "ok": readiness_ok,
        "advisory": True,
        "summary": compact_readiness(readiness) if readiness_ok else readiness,
    }]
    failures: list[str] = []
    live_attempted = False

    if args.preflight and not args.confirm_live:
        failures: list[str] = []
        for adapter in adapters:
            control_command = service_control_command_args(
                base_url,
                adapter,
                args.service_control_manager,
                args.service_control_action,
                args.service_control_service_path_template,
                confirm_control=False,
            )
            ok, result = run_json(control_command, env, args.service_control_timeout)
            payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
            steps.append({
                "name": f"{adapter}_service_control_preflight",
                "ok": ok,
                "summary": compact_service_control(adapter, payload),
            })
            if not ok:
                failures.append(f"{adapter}_service_control_preflight_failed")
            readback_request_ok, _readback_allows_live, readback_summary = service_closure_readback_step(base_url, adapter, args.probe_timeout)
            steps.append({
                "name": f"{adapter}_service_closure_readback_preflight",
                "ok": readback_request_ok,
                "advisory": True,
                "summary": readback_summary,
            })

        output = {
            "operation": "live_worker_loop_demo_slice",
            "ok": not failures,
            "mode": "preflight",
            "base_url": base_url,
            "adapters": adapters,
            "live_execution_performed": False,
            "service_control_attempted": True,
            "service_control_mutated": False,
            "service_closure_attempted": False,
            "ledger_mutated": False,
            "confirm_live_required": True,
            "confirm_service_control_required": True,
            "confirm_service_closure_required": True,
            "commands": commands,
            "recommended_sequence": [
                "readiness",
                *[f"{adapter}_start_check" for adapter in adapters],
                *[f"{adapter}_service_control" for adapter in adapters],
                *[f"{adapter}_service_closure" for adapter in adapters],
                "service_closure_live_demo",
                "real_worker_loop",
                "live_readback",
                "operator_readback",
            ],
            "steps": steps,
            "failures": failures,
            "safety": {
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "token_omitted": True,
                "uses_saved_cli_config": False,
                "requires_explicit_confirm_live": True,
                "requires_explicit_confirm_service_control": True,
                "requires_explicit_confirm_service_closure": True,
                "preflight_only": True,
            },
            "token_omitted": True,
        }
        serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
        if token_leaked(serialized):
            print(json.dumps({"ok": False, "error": "token_like_output_detected"}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        print(serialized)
        return 0

    if not args.confirm_live:
        output = {
            "operation": "live_worker_loop_demo_slice",
            "ok": True,
            "mode": "plan_only",
            "base_url": base_url,
            "adapters": adapters,
            "live_execution_performed": False,
            "ledger_mutated": False,
            "confirm_live_required": True,
            "confirm_service_control_required": True,
            "confirm_service_closure_required": True,
            "commands": commands,
            "recommended_sequence": [
                "readiness",
                *[f"{adapter}_start_check" for adapter in adapters],
                *[f"{adapter}_service_control" for adapter in adapters],
                *[f"{adapter}_service_closure" for adapter in adapters],
                "service_closure_live_demo",
                "real_worker_loop",
                "live_readback",
                "operator_readback",
            ],
            "steps": steps,
            "failures": [],
            "safety": {
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "token_omitted": True,
                "uses_saved_cli_config": False,
                "requires_explicit_confirm_live": True,
                "requires_explicit_confirm_service_control": True,
                "requires_explicit_confirm_service_closure": True,
            },
            "token_omitted": True,
        }
        serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
        if token_leaked(serialized):
            print(json.dumps({"ok": False, "error": "token_like_output_detected"}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        print(serialized)
        return 0

    if not readiness_ok or not readiness_current_code_ok(readiness):
        output = {
            "operation": "live_worker_loop_demo_slice",
            "ok": False,
            "mode": "confirmed_live",
            "base_url": base_url,
            "adapters": adapters,
            "live_execution_performed": False,
            "service_control_attempted": False,
            "service_control_mutated": False,
            "service_closure_attempted": False,
            "ledger_mutated": False,
            "commands": commands,
            "steps": steps,
            "failures": ["local_readiness_current_code_required"],
            "safety": {
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "token_omitted": True,
                "uses_saved_cli_config": False,
                "requires_explicit_confirm_live": True,
                "requires_current_code_server": True,
                "failed_before_service_control": True,
                "failed_before_service_closure": True,
                "failed_before_live_runtime": True,
            },
            "token_omitted": True,
        }
        serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
        if token_leaked(serialized):
            print(json.dumps({"ok": False, "error": "token_like_output_detected"}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        print(serialized)
        return 1

    service_control_attempted = False
    service_control_mutated = False
    if args.confirm_service_control:
        for adapter in adapters:
            control_command = service_control_command_args(
                base_url,
                adapter,
                args.service_control_manager,
                args.service_control_action,
                args.service_control_service_path_template,
                confirm_control=True,
            )
            service_control_attempted = True
            ok, result = run_json(control_command, env, args.service_control_timeout)
            payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
            summary = compact_service_control(adapter, payload)
            service_control_mutated = service_control_mutated or summary.get("service_mutated") is True
            steps.append({
                "name": f"{adapter}_service_control",
                "ok": ok,
                "summary": summary,
            })
            if not ok:
                failures.append(f"{adapter}_service_control_failed")

    service_closure_attempted = False
    if args.confirm_service_closure and not failures:
        for adapter in adapters:
            closure_command = [
                str(ROOT / "scripts" / "agentops"),
                "--base-url",
                base_url,
                "operator",
                "service-closure",
                "--adapter",
                adapter,
                "--fast",
                "--run-service-check",
                "--confirm-record",
            ]
            service_closure_attempted = True
            ok, result = run_json(closure_command, env, args.service_closure_timeout)
            payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
            steps.append({
                "name": f"{adapter}_service_closure",
                "ok": ok,
                "summary": compact_service_closure(adapter, payload),
            })
            if not ok:
                failures.append(f"{adapter}_service_closure_failed")
                continue
            readback_ok, readback_allows_live, readback_summary = service_closure_readback_step(base_url, adapter, args.probe_timeout)
            steps.append({
                "name": f"{adapter}_service_closure_readback",
                "ok": readback_ok and readback_allows_live,
                "summary": readback_summary,
            })
            if not readback_ok:
                failures.append(f"{adapter}_service_closure_readback_failed")
            elif not readback_allows_live:
                failures.append(f"{adapter}_service_closure_still_required")

    if not failures:
        live_command = [
            sys.executable,
            "scripts/customer_worker_real_runtime_acceptance.py",
            "--base-url",
            base_url,
            "--confirm-live",
            "--request-timeout",
            str(args.request_timeout),
            "--hermes-timeout",
            str(args.hermes_timeout),
            "--hermes-max-tokens",
            str(args.hermes_max_tokens),
        ]
        for adapter in adapters:
            live_command.extend(["--adapter", adapter])
        live_attempted = True
        ok, result = run_json(live_command, env, args.request_timeout + 90)
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        steps.append({"name": "real_worker_loop", "ok": ok, "summary": compact_live_acceptance(payload)})
        if not ok:
            failures.append("real_worker_loop_failed")

    if not failures:
        readback_command = [sys.executable, "scripts/v1_5_live_product_readiness_smoke.py", "--base-url", base_url]
        for adapter in adapters:
            readback_command.extend(["--require-adapter", adapter])
        ok, result = run_json(readback_command, env, 120)
        payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
        steps.append({"name": "live_product_readback", "ok": ok, "summary": compact_live_readback(payload)})
        if not ok:
            failures.append("live_product_readback_failed")

    after_ok, after = http_get_json(base_url, "/api/local/readiness", args.probe_timeout)
    steps.append({
        "name": "post_run_local_readiness_probe",
        "ok": after_ok,
        "advisory": True,
        "summary": compact_readiness(after) if after_ok else after,
    })
    blocking_steps_ok = all(step.get("ok") for step in steps if not step.get("advisory"))

    output = {
        "operation": "live_worker_loop_demo_slice",
        "ok": not failures and blocking_steps_ok,
        "mode": "confirmed_live",
        "base_url": base_url,
        "adapters": adapters,
        "live_execution_performed": live_attempted,
        "service_control_attempted": service_control_attempted,
        "service_control_mutated": service_control_mutated,
        "service_closure_attempted": service_closure_attempted,
        "ledger_mutated": live_attempted or service_closure_attempted,
        "commands": commands,
        "recommended_sequence": [
            "readiness",
            *[f"{adapter}_start_check" for adapter in adapters],
            *[f"{adapter}_service_control" for adapter in adapters],
            *[f"{adapter}_service_closure" for adapter in adapters],
            "service_closure_live_demo",
            "real_worker_loop",
            "live_readback",
            "operator_readback",
        ],
        "steps": steps,
        "failures": failures,
        "safety": {
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
            "uses_saved_cli_config": False,
            "requires_explicit_confirm_live": True,
            "requires_explicit_confirm_service_control": True,
            "requires_explicit_confirm_service_closure": True,
            "summary_hash_only_ledger": True,
        },
        "token_omitted": True,
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    if token_leaked(serialized):
        output["ok"] = False
        output["failures"].append("token_like_output_detected")
        serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    print(serialized)
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
