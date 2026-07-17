#!/usr/bin/env python3
"""Smoke local runtime acceptance diagnostics packets."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "local_runtime_acceptance_diagnostics.py"
CONTRACT_ID = "local_runtime_acceptance_diagnostics_v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_diag(path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--runtime-acceptance-json", str(path), *extra],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


def failed_fixture() -> dict:
    return {
        "ok": False,
        "live_openclaw": True,
        "live_hermes": True,
        "require_hermes_api": True,
        "openclaw_timeout": 300,
        "hermes_timeout": 600,
        "request_timeout": 720,
        "checks": [
            {"name": "Agent Gateway CLI smoke", "ok": True, "detail": {"run_id": "run_gw_diag_failed"}},
            {
                "name": "POST /api/integrations/openclaw/probe live",
                "ok": False,
                "detail": {
                    "run_id": "run_api_integrations_openclaw_probe_diag_failed",
                    "provider_call_performed": True,
                    "runtime_failure_evidence": True,
                    "acceptance_failure": "prepared_action_not_consumed",
                    "run_readback": {
                        "status": "failed",
                        "approval_required": 1,
                        "error_type": "OpenClawProbeFailed",
                        "error_message": "timed out after 330 seconds",
                        "duration_ms": None,
                    },
                    "raw_prompt_omitted": True,
                    "raw_response_omitted": True,
                    "token_omitted": True,
                },
            },
            {
                "name": "POST /api/integrations/hermes/run-task live",
                "ok": False,
                "detail": {
                    "run_id": "run_api_integrations_hermes_run_task_diag_failed",
                    "provider_call_performed": True,
                    "runtime_failure_evidence": True,
                    "acceptance_failure": "prepared_action_not_consumed",
                    "run_readback": {
                        "status": "failed",
                        "approval_required": 1,
                        "error_type": "HermesDefaultRunTaskFailed",
                        "error_message": "API call failed after 3 retries: Request timed out.",
                        "duration_ms": 366441,
                    },
                    "raw_prompt_omitted": True,
                    "raw_response_omitted": True,
                    "token_omitted": True,
                },
            },
        ],
    }


def passed_fixture() -> dict:
    return {
        "ok": True,
        "live_openclaw": True,
        "live_hermes": True,
        "require_hermes_api": True,
        "checks": [
            {"name": "Agent Gateway CLI smoke", "ok": True, "detail": {"run_id": "run_gw_diag_pass"}},
            {
                "name": "POST /api/integrations/openclaw/probe live",
                "ok": True,
                "detail": {"run_id": "run_api_integrations_openclaw_probe_diag_pass"},
            },
            {
                "name": "POST /api/integrations/hermes/run-task live",
                "ok": True,
                "detail": {"run_id": "run_api_integrations_hermes_run_task_diag_pass"},
            },
        ],
    }


def strict_false_positive_fixtures() -> dict[str, dict]:
    missing_live = passed_fixture()
    missing_live["checks"] = [item for item in missing_live["checks"] if item["name"] != "POST /api/integrations/openclaw/probe live"]

    missing_gateway = passed_fixture()
    missing_gateway["checks"] = [item for item in missing_gateway["checks"] if item["name"] != "Agent Gateway CLI smoke"]

    wrong_run_id = passed_fixture()
    wrong_run_id["checks"][1]["detail"]["run_id"] = "run_wrong_openclaw"

    plural_forbidden = passed_fixture()
    plural_forbidden["raw_prompts"] = ["must not be accepted"]
    plural_forbidden["token_values"] = ["must not be accepted"]

    runtime_failure_shape = passed_fixture()
    runtime_failure_shape["checks"][1]["detail"].update({
        "ok": False,
        "provider_call_performed": True,
        "runtime_failure_evidence": True,
        "acceptance_failure": "runtime_not_completed",
        "run_readback": {
            "status": "failed",
            "approval_required": 1,
            "error_type": "OpenClawProbeFailed",
            "error_message": "timed out after 330 seconds",
        },
    })

    return {
        "missing_live": missing_live,
        "missing_gateway": missing_gateway,
        "wrong_run_id": wrong_run_id,
        "plural_forbidden": plural_forbidden,
        "runtime_failure_shape": runtime_failure_shape,
    }


def main() -> int:
    require(SCRIPT.exists(), "diagnostics script missing")
    with tempfile.TemporaryDirectory(prefix="runtime-diagnostics-smoke-") as tmp:
        failed_path = Path(tmp) / "failed.json"
        passed_path = Path(tmp) / "passed.json"
        failed_path.write_text(json.dumps(failed_fixture()), encoding="utf-8")
        passed_path.write_text(json.dumps(passed_fixture()), encoding="utf-8")

        failed = run_diag(failed_path)
        require(failed.returncode == 0, f"failed fixture diagnostics failed: {failed.stdout}{failed.stderr}")
        failed_payload = json.loads(failed.stdout)
        require(failed_payload.get("contract") == CONTRACT_ID, "failed diagnostics contract mismatch")
        require(failed_payload.get("runtime_ready_for_promotion") is False, "failed fixture must not be promotion ready")
        require(len(failed_payload.get("live_failures") or []) == 2, "failed fixture should expose both live failures")
        require((failed_payload.get("safety") or {}).get("network_called") is False, "diagnostics must not call network")
        require(any("Hermes" in item for item in failed_payload.get("next_actions") or []), "Hermes next action missing")

        failed_strict = run_diag(failed_path, "--require-runtime-ready")
        require(failed_strict.returncode != 0, "failed fixture must fail strict runtime-ready mode")

        passed = run_diag(passed_path, "--require-runtime-ready")
        require(passed.returncode == 0, f"passed fixture strict diagnostics failed: {passed.stdout}{passed.stderr}")
        passed_payload = json.loads(passed.stdout)
        require(passed_payload.get("runtime_ready_for_promotion") is True, "passed fixture should be promotion ready")
        require(passed_payload.get("live_failures") == [], "passed fixture should have no live failures")

        for name, fixture in strict_false_positive_fixtures().items():
            fixture_path = Path(tmp) / f"{name}.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            loose = run_diag(fixture_path)
            require(loose.returncode == 0, f"{name} loose diagnostics failed: {loose.stdout}{loose.stderr}")
            loose_payload = json.loads(loose.stdout)
            require(loose_payload.get("runtime_ready_for_promotion") is False, f"{name} must not be promotion ready")
            strict = run_diag(fixture_path, "--require-runtime-ready")
            require(strict.returncode != 0, f"{name} must fail strict runtime-ready mode")
            if name == "plural_forbidden":
                require(loose_payload.get("forbidden_payload_text_detected") is True, "plural forbidden fields must be detected")
            if name == "runtime_failure_shape":
                require(len(loose_payload.get("live_failures") or []) == 1, "runtime failure evidence must surface as live failure")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "failed_fixture_ready": False,
        "passed_fixture_ready": True,
        "false_positive_fixtures_rejected": sorted(strict_false_positive_fixtures().keys()),
        "strict_failure_rejected": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
