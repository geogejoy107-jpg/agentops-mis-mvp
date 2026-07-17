#!/usr/bin/env python3
"""Smoke the commercial release-grade receipt rerun bundle preview."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_JSON = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RERUN_BUNDLE.json"
BUNDLE_DOC = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RERUN_BUNDLE.md"
BUNDLE_SCRIPT = ROOT / "scripts" / "commercial_release_grade_rerun_bundle.py"
RECEIPTS_JSON = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
CONTRACT_ID = "commercial_release_grade_rerun_bundle_v1"
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


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_bundle(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUNDLE_SCRIPT), *args],
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
            {"name": "Agent Gateway CLI smoke", "ok": True, "detail": {"run_id": "run_gw_bundlefixture"}},
            {"name": "POST /api/integrations/openclaw/probe live", "ok": True, "detail": {"run_id": "run_api_integrations_openclaw_probe_20260625000000000000_bundlefx"}},
            {"name": "POST /api/integrations/hermes/run-task live", "ok": True, "detail": {"run_id": "run_api_integrations_hermes_run_task_20260625000000000000_bundlefx"}},
        ],
    }), encoding="utf-8")


def main() -> int:
    spec = read_json(BUNDLE_JSON)
    require(spec.get("contract_id") == CONTRACT_ID, "bundle contract mismatch")
    require(spec.get("status") == "blocked_rerun_bundle_preview", "bundle status mismatch")
    require(spec.get("ci_safe") is True and spec.get("read_only") is True, "bundle spec must be CI-safe/read-only")
    for needle in [
        CONTRACT_ID,
        "commercial_release_grade_receipt_plan_v1",
        "COMMERCIAL_EVIDENCE_RECEIPTS.json",
        "receipt_mutation_during_preview",
        "rerun_command_auto_execution",
        "local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api --openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720",
        "raw_prompts",
        "token_values",
    ]:
        require(needle in json.dumps(spec), f"bundle spec missing {needle}")
        require(needle in read_text(BUNDLE_DOC), f"bundle doc missing {needle}")
    script_text = read_text(BUNDLE_SCRIPT)
    for needle in [
        CONTRACT_ID,
        "phase_gate_rerun_bundles",
        "write_preview",
        "preview_only_no_write",
        "--include-external-ci-evidence",
        "--runtime-acceptance-json",
        "--require-bundle-ready",
    ]:
        require(needle in script_text, f"bundle script missing {needle}")

    before_hash = file_hash(RECEIPTS_JSON)
    default = run_bundle()
    after_hash = file_hash(RECEIPTS_JSON)
    require(before_hash == after_hash, "default bundle must not mutate commercial evidence receipts")
    require(default.returncode == 0, f"default bundle failed: {default.stdout}{default.stderr}")
    default_payload = json.loads(default.stdout)
    require(default_payload.get("contract") == CONTRACT_ID, "default payload contract mismatch")
    require(default_payload.get("status") == "blocked_rerun_bundle_preview", "default bundle must stay blocked")
    require((default_payload.get("safety") or {}).get("network_called") is False, "default bundle must not call network")
    require((default_payload.get("safety") or {}).get("mutates_receipts") is False, "bundle must not mutate receipts")
    require((default_payload.get("safety") or {}).get("executes_rerun_commands") is False, "bundle must not execute rerun commands")
    gate_ids = [item.get("gate_id") for item in default_payload.get("phase_gate_rerun_bundles") or []]
    require(gate_ids == REQUIRED_GATE_IDS, "rerun bundle gate coverage mismatch")
    require("receipt_rerun_required" in set(default_payload.get("blockers") or []), "receipt rerun blocker missing")
    summary = default_payload.get("bundle_summary") or {}
    require(summary.get("bundle_count") == len(REQUIRED_GATE_IDS), "bundle count mismatch")
    require(summary.get("write_preview_count") == len(REQUIRED_GATE_IDS), "write preview count mismatch")
    require(summary.get("mutating_write_count") == 0, "bundle must report zero mutating writes")
    for item in default_payload.get("phase_gate_rerun_bundles") or []:
        require(item.get("bundle_id") == f"rerun_{item.get('gate_id')}", f"{item.get('gate_id')} bundle id mismatch")
        require(item.get("rerun_commands"), f"{item.get('gate_id')} rerun commands missing")
        require(item.get("executes_rerun_commands") is False, f"{item.get('gate_id')} must not execute rerun commands")
        preview = item.get("write_preview") or {}
        require(preview.get("target") == "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", f"{item.get('gate_id')} write target mismatch")
        require(preview.get("operation") == "preview_only_no_write", f"{item.get('gate_id')} write operation mismatch")
        require(preview.get("mutates_receipts") is False, f"{item.get('gate_id')} preview must be read-only")
        require((preview.get("would_set") or {}).get("release_grade_update_allowed") is False, f"{item.get('gate_id')} must not allow release-grade write")

    with tempfile.TemporaryDirectory() as tmp:
        runtime_path = Path(tmp) / "runtime_acceptance.json"
        runtime_fixture(runtime_path)
        fixture = run_bundle("--runtime-acceptance-json", str(runtime_path), "--require-current-runtime-evidence")
        require(fixture.returncode == 0, f"runtime fixture bundle failed: {fixture.stdout}{fixture.stderr}")
        fixture_payload = json.loads(fixture.stdout)
        checks = fixture_payload.get("bundle_checks") or {}
        plan_summary = fixture_payload.get("plan_summary") or {}
        require(checks.get("real_runtime_acceptance_verified") is True, "runtime fixture must verify real runtime acceptance")
        require(plan_summary.get("current_runtime_evidence_supplied") is True, "runtime fixture must be current-session evidence")
        strict = run_bundle("--runtime-acceptance-json", str(runtime_path), "--require-current-runtime-evidence", "--require-bundle-ready")
        require(strict.returncode != 0, "strict rerun bundle must remain blocked")

    require(before_hash == file_hash(RECEIPTS_JSON), "rerun bundle smoke must leave receipts unchanged")
    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": default_payload.get("status"),
        "gate_count": len(default_payload.get("phase_gate_rerun_bundles") or []),
        "strict_bundle_still_blocked": True,
        "receipts_mutated": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
