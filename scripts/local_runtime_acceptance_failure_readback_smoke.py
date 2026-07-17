#!/usr/bin/env python3
"""Verify live runtime acceptance preserves structured failed-run readback."""
from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.local_runtime_acceptance as lra  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    calls: list[tuple[str, str]] = []

    def fake_request_json(method: str, base_url: str, path: str, payload=None, query=None, timeout: int = 240):
        calls.append((method, path))
        if method == "POST" and path == "/api/integrations/openclaw/probe" and not (payload or {}).get("prepared_action_id"):
            return {
                "provider": "openclaw",
                "dry_run": False,
                "ok": False,
                "prepared_action_id": "pact_failure_smoke",
                "approval_id": "ap_failure_smoke",
                "run_id": "run_api_integrations_openclaw_probe_failure_smoke",
                "prompt_hash": "prompt_hash_smoke",
                "provider_call_performed": False,
                "raw_prompt_omitted": True,
                "token_omitted": True,
            }
        if method == "POST" and path == "/api/approvals/ap_failure_smoke/approve":
            return {"decision": "approved"}
        if method == "POST" and path == "/api/integrations/openclaw/probe" and (payload or {}).get("prepared_action_id"):
            return {
                "provider": "openclaw",
                "dry_run": False,
                "ok": False,
                "created": False,
                "prepared_action_id": "pact_failure_smoke",
                "prepared_action_status": "approved",
                "run_id": "run_api_integrations_openclaw_probe_failure_smoke",
                "provider_call_performed": True,
                "error": "runtime timed out",
                "raw_prompt_omitted": True,
                "raw_response_omitted": True,
                "token_omitted": True,
            }
        if method == "GET" and path == "/api/runs/run_api_integrations_openclaw_probe_failure_smoke":
            return {
                "run": {
                    "run_id": "run_api_integrations_openclaw_probe_failure_smoke",
                    "status": "failed",
                    "approval_required": 1,
                    "error_type": "OpenClawProbeFailed",
                    "error_message": "runtime timed out",
                    "duration_ms": None,
                }
            }
        raise AssertionError(f"unexpected request: {method} {path} payload={payload}")

    original = lra.request_json
    lra.request_json = fake_request_json
    try:
        result = lra.run_prepared_runtime_probe(
            "http://127.0.0.1:9999",
            "/api/integrations/openclaw/probe",
            openclaw_timeout=300,
            request_timeout=720,
        )
    finally:
        lra.request_json = original

    require(result.get("ok") is False, "failed runtime must not report ok=true")
    require(result.get("runtime_failure_evidence") is True, "failed runtime evidence marker missing")
    require(result.get("acceptance_failure") == "prepared_action_not_consumed", "acceptance failure reason mismatch")
    require(result.get("provider_call_performed") is True, "provider call marker missing")
    require(result.get("run_id") == "run_api_integrations_openclaw_probe_failure_smoke", "run id missing")
    require((result.get("run_readback") or {}).get("status") == "failed", "failed run readback missing")
    require((result.get("run_readback") or {}).get("error_type") == "OpenClawProbeFailed", "error type missing")
    require(result.get("request_timeout") == 720, "request timeout not preserved")
    require(("GET", "/api/runs/run_api_integrations_openclaw_probe_failure_smoke") in calls, "run readback was not fetched")

    print(json.dumps({
        "ok": True,
        "contract": "local_runtime_acceptance_failure_readback_v1",
        "run_id": result.get("run_id"),
        "acceptance_failure": result.get("acceptance_failure"),
        "runtime_failure_evidence": result.get("runtime_failure_evidence"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
