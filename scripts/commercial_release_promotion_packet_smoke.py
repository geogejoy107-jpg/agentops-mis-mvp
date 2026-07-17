#!/usr/bin/env python3
"""Smoke the commercial release promotion packet contract."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKET_JSON = ROOT / "docs" / "COMMERCIAL_RELEASE_PROMOTION_PACKET.json"
PACKET_DOC = ROOT / "docs" / "COMMERCIAL_RELEASE_PROMOTION_PACKET.md"
PACKET_SCRIPT = ROOT / "scripts" / "commercial_release_promotion_packet.py"
CONTRACT_ID = "commercial_release_promotion_packet_v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def run_packet(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PACKET_SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )


def runtime_fixture(path: Path) -> None:
    payload = {
        "ok": True,
        "live_openclaw": True,
        "live_hermes": True,
        "require_hermes_api": True,
        "checks": [
            {"name": "Agent Gateway CLI smoke", "ok": True, "detail": {"run_id": "run_gw_packetfixture"}},
            {
                "name": "POST /api/integrations/openclaw/probe live",
                "ok": True,
                "detail": {"run_id": "run_api_integrations_openclaw_probe_20260625000000000000_packetfx"},
            },
            {
                "name": "POST /api/integrations/hermes/run-task live",
                "ok": True,
                "detail": {"run_id": "run_api_integrations_hermes_run_task_20260625000000000000_packetfx"},
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def failed_runtime_fixture(path: Path) -> None:
    payload = {
        "ok": False,
        "live_openclaw": True,
        "live_hermes": True,
        "require_hermes_api": True,
        "checks": [
            {"name": "Agent Gateway CLI smoke", "ok": True, "detail": {"run_id": "run_gw_failedpacketfx"}},
            {
                "name": "POST /api/integrations/openclaw/probe live",
                "ok": False,
                "detail": {
                    "run_id": "run_api_integrations_openclaw_probe_20260625000000000000_failedfx",
                    "runtime_failure_evidence": True,
                    "run_readback": {"status": "failed", "error_type": "OpenClawProbeFailed"},
                },
            },
            {
                "name": "POST /api/integrations/hermes/run-task live",
                "ok": False,
                "detail": {
                    "run_id": "run_api_integrations_hermes_run_task_20260625000000000000_failedfx",
                    "runtime_failure_evidence": True,
                    "run_readback": {"status": "failed", "error_type": "HermesDefaultRunTaskFailed"},
                },
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> int:
    spec = read_json(PACKET_JSON)
    require(spec.get("contract_id") == CONTRACT_ID, "packet contract mismatch")
    require(spec.get("status") == "blocked_release_promotion_required", "packet status mismatch")
    require(spec.get("ci_safe") is True, "packet spec must be CI-safe")
    require(spec.get("read_only") is True, "packet spec must be read-only")
    for needle in [
        "commercial_release_promotion_preflight_v1",
        "commercial_exact_head_ci_evidence_v1",
        "commercial_evidence_receipts_v1",
        "real_runtime_acceptance_verified",
        "local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api --openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720",
        "manual_receipt_promotion_without_ci",
        "raw_prompts",
        "token_values",
    ]:
        require(needle in json.dumps(spec), f"packet spec missing {needle}")
        require(needle in read_text(PACKET_DOC), f"packet doc missing {needle}")
    script_text = read_text(PACKET_SCRIPT)
    for needle in [
        CONTRACT_ID,
        "--include-external-ci-evidence",
        "--runtime-acceptance-json",
        "--require-current-runtime-evidence",
        "--require-promotion-packet-ready",
        "local_runtime_acceptance_json",
        "real_runtime_acceptance_verified",
    ]:
        require(needle in script_text, f"packet script missing {needle}")

    default = run_packet()
    require(default.returncode == 0, f"default packet failed: {default.stdout}{default.stderr}")
    default_payload = json.loads(default.stdout)
    require(default_payload.get("contract") == CONTRACT_ID, "default payload contract mismatch")
    require(default_payload.get("status") == "blocked_release_promotion_required", "default packet must stay blocked")
    require((default_payload.get("safety") or {}).get("read_only") is True, "default packet must be read-only")
    require((default_payload.get("safety") or {}).get("network_called") is False, "default packet must not call network")
    require((default_payload.get("safety") or {}).get("live_execution_performed") is False, "packet script must not run live agents")
    require((default_payload.get("packet_checks") or {}).get("current_runtime_evidence_supplied") is False, "default packet should use recorded runtime only")

    with tempfile.TemporaryDirectory() as tmp:
        runtime_path = Path(tmp) / "runtime_acceptance.json"
        runtime_fixture(runtime_path)
        fixture = run_packet("--runtime-acceptance-json", str(runtime_path), "--require-current-runtime-evidence")
        require(fixture.returncode == 0, f"runtime fixture packet failed: {fixture.stdout}{fixture.stderr}")
        fixture_payload = json.loads(fixture.stdout)
        runtime = fixture_payload.get("real_runtime_acceptance") or {}
        require(runtime.get("current_session") is True, "runtime fixture must be treated as current session evidence")
        require(runtime.get("real_runtime_acceptance_verified") is True, "runtime fixture must verify real runtime acceptance")
        require((fixture_payload.get("packet_checks") or {}).get("real_runtime_acceptance_verified") is True, "packet check must include runtime verification")
        strict = run_packet("--runtime-acceptance-json", str(runtime_path), "--require-current-runtime-evidence", "--require-promotion-packet-ready")
        require(strict.returncode != 0, "strict promotion packet must remain blocked")
        failed_runtime_path = Path(tmp) / "failed_runtime_acceptance.json"
        failed_runtime_fixture(failed_runtime_path)
        failed = run_packet("--runtime-acceptance-json", str(failed_runtime_path), "--require-current-runtime-evidence")
        require(failed.returncode != 0, "failed runtime evidence must not verify promotion packet")
        require("runtime acceptance JSON did not pass" in (failed.stderr or failed.stdout), "failed runtime rejection reason missing")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": default_payload.get("status"),
        "runtime_fixture_verified": True,
        "failed_runtime_fixture_rejected": True,
        "strict_packet_still_blocked": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
