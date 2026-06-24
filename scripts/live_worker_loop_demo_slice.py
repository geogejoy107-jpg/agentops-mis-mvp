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
import subprocess
import sys
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


def planned_commands(base_url: str, adapters: list[str], request_timeout: int, hermes_timeout: int, hermes_max_tokens: int) -> dict[str, str]:
    adapter_flags = " ".join(f"--adapter {adapter}" for adapter in adapters)
    require_flags = " ".join(f"--require-adapter {adapter}" for adapter in adapters)
    env_prefix = f"AGENTOPS_BASE_URL={base_url}"
    commands = {
        "readiness": f"{env_prefix} ./scripts/agentops local readiness --require-current-code",
        "real_worker_loop": (
            f"{env_prefix} python3 scripts/customer_worker_real_runtime_acceptance.py "
            f"--base-url {base_url} --confirm-live {adapter_flags} "
            f"--request-timeout {request_timeout} --hermes-timeout {hermes_timeout} "
            f"--hermes-max-tokens {hermes_max_tokens}"
        ),
        "live_readback": f"{env_prefix} python3 scripts/v1_5_live_product_readiness_smoke.py --base-url {base_url} {require_flags}",
        "operator_readback": f"{env_prefix} ./scripts/agentops operator live-product-readiness {require_flags}",
    }
    for adapter in adapters:
        commands[f"{adapter}_start_check"] = f"{env_prefix} ./scripts/agentops operator start-check --adapter {adapter} --limit 8"
        commands[f"{adapter}_service_closure"] = (
            f"{env_prefix} ./scripts/agentops operator service-closure "
            f"--adapter {adapter} --fast --run-service-check --confirm-record"
        )
        commands[f"{adapter}_loop_driver_auto_service_closure"] = (
            f"{env_prefix} ./scripts/agentops operator loop-driver "
            f"--adapter {adapter} --max-steps 1 --limit 8 --confirm-loop --auto-service-closure"
        )
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
    parser.add_argument("--confirm-live", action="store_true", help="Run real local Hermes/OpenClaw customer-worker acceptance.")
    parser.add_argument("--request-timeout", type=int, default=720)
    parser.add_argument("--hermes-timeout", type=int, default=600)
    parser.add_argument("--hermes-max-tokens", type=int, default=512)
    parser.add_argument("--probe-timeout", type=int, default=5)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    adapters = args.adapter or ["hermes", "openclaw"]
    commands = planned_commands(base_url, adapters, args.request_timeout, args.hermes_timeout, args.hermes_max_tokens)
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
            "commands": commands,
            "recommended_sequence": [
                "readiness",
                *[f"{adapter}_start_check" for adapter in adapters],
                *[f"{adapter}_service_closure" for adapter in adapters],
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
            },
            "token_omitted": True,
        }
        serialized = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
        if token_leaked(serialized):
            print(json.dumps({"ok": False, "error": "token_like_output_detected"}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        print(serialized)
        return 0

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
        "ledger_mutated": live_attempted,
        "commands": commands,
        "recommended_sequence": [
            "readiness",
            *[f"{adapter}_start_check" for adapter in adapters],
            *[f"{adapter}_service_closure" for adapter in adapters],
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
