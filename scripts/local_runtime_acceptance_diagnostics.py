#!/usr/bin/env python3
"""Build a CI-safe diagnostic packet from local_runtime_acceptance.py output."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CONTRACT_ID = "local_runtime_acceptance_diagnostics_v1"
REQUIRED_CHECKS = {
    "Agent Gateway CLI smoke": {
        "runtime": "agent_gateway",
        "run_id_prefix": "run_gw_",
    },
    "POST /api/integrations/openclaw/probe live": {
        "runtime": "openclaw",
        "run_id_prefix": "run_api_integrations_openclaw_probe_",
    },
    "POST /api/integrations/hermes/run-task live": {
        "runtime": "hermes",
        "run_id_prefix": "run_api_integrations_hermes_run_task_",
    },
}
REQUIRED_LIVE_CHECKS = {
    "POST /api/integrations/openclaw/probe live": "openclaw",
    "POST /api/integrations/hermes/run-task live": "hermes",
}
FORBIDDEN_MARKERS = [
    '"raw_prompt"',
    '"raw_prompts"',
    '"raw_response"',
    '"raw_responses"',
    '"private_transcript"',
    '"private_transcripts"',
    '"token_value"',
    '"token_values"',
    "openai_api_key",
    "anthropic_api_key",
    "notion_token",
    "dify_api_key",
]


def read_payload(path_value: str) -> tuple[dict[str, Any], str, str]:
    if path_value == "-":
        raw = sys.stdin.read()
        source = "stdin:local_runtime_acceptance_json"
    else:
        path = Path(path_value).expanduser()
        raw = path.read_text(encoding="utf-8")
        source = str(path)
    return json.loads(raw), raw, source


def has_forbidden_payload_text(raw: str) -> bool:
    lowered = raw.lower()
    return any(marker in lowered for marker in FORBIDDEN_MARKERS)


def safe_check_name(name: str) -> str:
    if name in REQUIRED_CHECKS:
        return name
    if name.startswith("Hermes default API models"):
        return "Hermes default API models"
    return name.split(":", 1)[0][:160]


def check_detail(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("detail") if isinstance(item.get("detail"), dict) else {}


def check_run_id(item: dict[str, Any]) -> str:
    return str(check_detail(item).get("run_id") or "")


def check_passed(item: dict[str, Any]) -> bool:
    detail = check_detail(item)
    if item.get("ok") is not True:
        return False
    if detail.get("runtime_failure_evidence") is True:
        return False
    if detail.get("ok") is False:
        return False
    return True


def failed_check_diagnostic(item: dict[str, Any]) -> dict[str, Any]:
    detail = check_detail(item)
    run_readback = detail.get("run_readback") if isinstance(detail.get("run_readback"), dict) else {}
    name = str(item.get("name") or "")
    runtime = REQUIRED_LIVE_CHECKS.get(name, "unknown")
    error_message = str(run_readback.get("error_message") or detail.get("error") or item.get("detail") or "")
    timeout_like = "timeout" in error_message.lower() or "timed out" in error_message.lower()
    return {
        "check_name": safe_check_name(name),
        "runtime": runtime,
        "ok": check_passed(item),
        "run_id": check_run_id(item),
        "provider_call_performed": detail.get("provider_call_performed") is True,
        "runtime_failure_evidence": detail.get("runtime_failure_evidence") is True,
        "acceptance_failure": detail.get("acceptance_failure"),
        "run_readback": {
            "status": run_readback.get("status"),
            "approval_required": run_readback.get("approval_required"),
            "error_type": run_readback.get("error_type"),
            "duration_ms": run_readback.get("duration_ms"),
            "error_message_ref": "present" if run_readback.get("error_message") else None,
        },
        "timeout_like_failure": timeout_like,
        "raw_prompt_omitted": detail.get("raw_prompt_omitted", True) is True,
        "raw_response_omitted": detail.get("raw_response_omitted", True) is True,
        "token_omitted": detail.get("token_omitted", True) is True,
    }


def build_diagnostics(payload: dict[str, Any], raw: str, source: str) -> dict[str, Any]:
    checks = [item for item in payload.get("checks") or [] if isinstance(item, dict)]
    by_name = {str(item.get("name") or ""): item for item in checks}
    live_enabled = bool(payload.get("live_openclaw") or payload.get("live_hermes"))
    required_checks = {}
    missing_required_checks = []
    invalid_required_run_ids = []
    for check_name, requirement in REQUIRED_CHECKS.items():
        item = by_name.get(check_name)
        present = item is not None
        run_id = check_run_id(item or {})
        run_id_valid = bool(run_id and run_id.startswith(str(requirement["run_id_prefix"])))
        passed = bool(present and check_passed(item or {}))
        required_checks[check_name] = {
            "runtime": requirement["runtime"],
            "present": present,
            "ok": passed,
            "run_id": run_id,
            "run_id_valid": run_id_valid,
        }
        if not present:
            missing_required_checks.append(check_name)
        elif not run_id_valid:
            invalid_required_run_ids.append(check_name)
    required_live_present = {
        runtime: required_checks[check_name]["present"]
        for check_name, runtime in REQUIRED_LIVE_CHECKS.items()
        if payload.get(f"live_{runtime}") is True
    }
    failed = [failed_check_diagnostic(item) for item in checks if not check_passed(item)]
    live_failures = [item for item in failed if item["runtime"] in {"openclaw", "hermes"}]
    succeeded_live = [
        {
            "runtime": REQUIRED_LIVE_CHECKS[name],
            "run_id": check_run_id(by_name.get(name) or {}),
        }
        for name in REQUIRED_LIVE_CHECKS
        if check_passed(by_name.get(name) or {})
    ]
    forbidden_found = has_forbidden_payload_text(raw)
    required_checks_ok = all(item["present"] and item["ok"] and item["run_id_valid"] for item in required_checks.values())
    runtime_ready = bool(
        payload.get("ok") is True
        and payload.get("live_openclaw") is True
        and payload.get("live_hermes") is True
        and payload.get("require_hermes_api") is True
        and required_checks_ok
        and not live_failures
        and not forbidden_found
    )
    next_actions: list[str] = []
    if forbidden_found:
        next_actions.append("Regenerate the acceptance JSON; forbidden raw/token material was detected.")
    if missing_required_checks:
        next_actions.append("Rerun local_runtime_acceptance.py; required Agent Gateway/OpenClaw/Hermes checks are missing.")
    if invalid_required_run_ids:
        next_actions.append("Rerun local_runtime_acceptance.py; required check run_id values are missing or invalid.")
    if any(item["timeout_like_failure"] for item in live_failures):
        next_actions.append("Inspect local Hermes/OpenClaw service health before rerunning live acceptance.")
        next_actions.append("Rerun local_runtime_acceptance.py with explicit runtime/request timeout windows after service recovery.")
    if any(item["runtime"] == "openclaw" for item in live_failures):
        next_actions.append("Check OpenClaw CLI/agent responsiveness and confirm no orphan probe process remains.")
    if any(item["runtime"] == "hermes" for item in live_failures):
        next_actions.append("Check Hermes gateway /v1/models and chat-completions responsiveness before promotion.")
    if not next_actions:
        next_actions.append("Provide this diagnostics packet with the promotion packet; do not treat it as release-grade evidence unless runtime_ready_for_promotion is true.")
    return {
        "ok": True,
        "contract": CONTRACT_ID,
        "source": source,
        "acceptance_ok": payload.get("ok") is True,
        "runtime_ready_for_promotion": runtime_ready,
        "live_execution_requested": live_enabled,
        "live_openclaw": payload.get("live_openclaw") is True,
        "live_hermes": payload.get("live_hermes") is True,
        "require_hermes_api": payload.get("require_hermes_api") is True,
        "request_timeout": payload.get("request_timeout"),
        "openclaw_timeout": payload.get("openclaw_timeout"),
        "hermes_timeout": payload.get("hermes_timeout"),
        "required_live_checks_present": required_live_present,
        "required_checks": required_checks,
        "missing_required_checks": missing_required_checks,
        "invalid_required_run_ids": invalid_required_run_ids,
        "failed_checks": failed,
        "live_failures": live_failures,
        "succeeded_live_checks": succeeded_live,
        "forbidden_payload_text_detected": forbidden_found,
        "safety": {
            "read_only": True,
            "live_execution_performed": False,
            "db_read_performed": False,
            "network_called": False,
            "raw_prompt_omitted": not forbidden_found,
            "raw_response_omitted": not forbidden_found,
            "token_values_omitted": not forbidden_found,
        },
        "next_actions": next_actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose local runtime acceptance JSON without running live runtimes.")
    parser.add_argument("--runtime-acceptance-json", required=True, help="Path to local_runtime_acceptance.py JSON output, or '-' for stdin.")
    parser.add_argument("--require-runtime-ready", action="store_true", help="Exit non-zero unless the acceptance JSON is promotion-ready.")
    args = parser.parse_args()
    payload, raw, source = read_payload(args.runtime_acceptance_json)
    diagnostics = build_diagnostics(payload, raw, source)
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if (not args.require_runtime_ready or diagnostics["runtime_ready_for_promotion"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
