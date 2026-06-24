#!/usr/bin/env python3
"""Smoke the commercial release-grade receipt promotion plan."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN_JSON = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RECEIPT_PLAN.json"
PLAN_DOC = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RECEIPT_PLAN.md"
PLAN_SCRIPT = ROOT / "scripts" / "commercial_release_grade_receipt_plan.py"
CONTRACT_ID = "commercial_release_grade_receipt_plan_v1"
REQUIRED_GATE_IDS = [
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def run_plan(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PLAN_SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )


def runtime_fixture(path: Path) -> None:
    path.write_text(json.dumps({
        "ok": True,
        "live_openclaw": True,
        "live_hermes": True,
        "require_hermes_api": True,
        "checks": [
            {"name": "Agent Gateway CLI smoke", "ok": True, "detail": {"run_id": "run_gw_planfixture"}},
            {"name": "POST /api/integrations/openclaw/probe live", "ok": True, "detail": {"run_id": "run_api_integrations_openclaw_probe_20260625000000000000_planfx"}},
            {"name": "POST /api/integrations/hermes/run-task live", "ok": True, "detail": {"run_id": "run_api_integrations_hermes_run_task_20260625000000000000_planfx"}},
        ],
    }), encoding="utf-8")


def main() -> int:
    spec = read_json(PLAN_JSON)
    require(spec.get("contract_id") == CONTRACT_ID, "plan contract mismatch")
    require(spec.get("status") == "blocked_receipt_promotion_preview", "plan status mismatch")
    require(spec.get("ci_safe") is True and spec.get("read_only") is True, "plan spec must be CI-safe/read-only")
    for needle in [
        CONTRACT_ID,
        "commercial_release_promotion_packet_v1",
        "all_gate_receipts_current_head",
        "local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api",
        "manual_receipt_promotion_without_ci",
        "raw_prompts",
        "token_values",
    ]:
        require(needle in json.dumps(spec), f"plan spec missing {needle}")
        require(needle in read_text(PLAN_DOC), f"plan doc missing {needle}")
    script_text = read_text(PLAN_SCRIPT)
    for needle in [
        CONTRACT_ID,
        "phase_gate_receipt_plan",
        "rerun_local_receipts_for_current_head",
        "--include-external-ci-evidence",
        "--runtime-acceptance-json",
        "--require-plan-ready",
    ]:
        require(needle in script_text, f"plan script missing {needle}")

    default = run_plan()
    require(default.returncode == 0, f"default plan failed: {default.stdout}{default.stderr}")
    default_payload = json.loads(default.stdout)
    require(default_payload.get("contract") == CONTRACT_ID, "default payload contract mismatch")
    require(default_payload.get("status") == "blocked_receipt_promotion_preview", "default plan must stay blocked")
    require((default_payload.get("safety") or {}).get("network_called") is False, "default plan must not call network")
    require((default_payload.get("safety") or {}).get("mutates_receipts") is False, "plan must not mutate receipts")
    gate_ids = [item.get("gate_id") for item in default_payload.get("phase_gate_receipt_plan") or []]
    require(gate_ids == REQUIRED_GATE_IDS, "gate plan coverage mismatch")
    require("gate_receipts_not_current_head" in set(default_payload.get("blockers") or []), "current-head receipt blocker missing")
    for item in default_payload.get("phase_gate_receipt_plan") or []:
        require(item.get("eligible_for_release_grade_update") is False, "preview plan must not mark gate eligible")
        require(item.get("rerun_commands"), f"{item.get('gate_id')} rerun commands missing")

    with tempfile.TemporaryDirectory() as tmp:
        runtime_path = Path(tmp) / "runtime_acceptance.json"
        runtime_fixture(runtime_path)
        fixture = run_plan("--runtime-acceptance-json", str(runtime_path), "--require-current-runtime-evidence")
        require(fixture.returncode == 0, f"runtime fixture plan failed: {fixture.stdout}{fixture.stderr}")
        fixture_payload = json.loads(fixture.stdout)
        checks = fixture_payload.get("plan_checks") or {}
        require(checks.get("real_runtime_acceptance_verified") is True, "runtime fixture must verify real runtime acceptance")
        require(checks.get("current_runtime_evidence_supplied") is True, "runtime fixture must be current-session evidence")
        strict = run_plan("--runtime-acceptance-json", str(runtime_path), "--require-current-runtime-evidence", "--require-plan-ready")
        require(strict.returncode != 0, "strict plan must remain blocked")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": default_payload.get("status"),
        "gate_count": len(default_payload.get("phase_gate_receipt_plan") or []),
        "strict_plan_still_blocked": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
