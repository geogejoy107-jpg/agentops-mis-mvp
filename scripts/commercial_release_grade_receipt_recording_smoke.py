#!/usr/bin/env python3
"""Smoke the commercial release-grade receipt recording preview."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECORDING_JSON = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.json"
RECORDING_DOC = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.md"
RECORDING_SCRIPT = ROOT / "scripts" / "commercial_release_grade_receipt_recording.py"
RECEIPTS_JSON = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
CONTRACT_ID = "commercial_release_grade_receipt_recording_v1"
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
    display_path = str(path)
    try:
        display_path = str(path.relative_to(ROOT))
    except ValueError:
        pass
    require(path.exists(), f"missing file: {display_path}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_recording(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RECORDING_SCRIPT), *args],
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
            {"name": "Agent Gateway CLI smoke", "ok": True, "detail": {"run_id": "run_gw_recordfixture"}},
            {"name": "POST /api/integrations/openclaw/probe live", "ok": True, "detail": {"run_id": "run_api_integrations_openclaw_probe_20260625000000000000_recordfx"}},
            {"name": "POST /api/integrations/hermes/run-task live", "ok": True, "detail": {"run_id": "run_api_integrations_hermes_run_task_20260625000000000000_recordfx"}},
        ],
    }), encoding="utf-8")


def transaction_fixture(payload: dict[str, Any], path: Path) -> None:
    clone = json.loads(json.dumps(payload))
    checks = clone.setdefault("recording_checks", {})
    checks["exact_head_ci_verified"] = True
    checks["real_runtime_acceptance_verified"] = True
    checks["current_runtime_evidence_supplied"] = True
    clone["blockers"] = ["operator_confirmation_required"]
    for item in clone.get("phase_gate_recording_requests") or []:
        item["missing_commands"] = []
        item["requires_operator_confirmation"] = True
        item["writes_release_grade_receipt"] = False
        item["mutates_receipts"] = False
        item["operation"] = "preview_only_json_patch"
        item["blockers"] = ["operator_confirmation_required", "receipt_head_not_current"]
    path.write_text(json.dumps(clone, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    spec = read_json(RECORDING_JSON)
    require(spec.get("contract_id") == CONTRACT_ID, "recording contract mismatch")
    require(spec.get("status") == "blocked_receipt_recording_preview", "recording status mismatch")
    require(spec.get("ci_safe") is True and spec.get("read_only") is True, "recording spec must be CI-safe/read-only")
    for needle in [
        CONTRACT_ID,
        "commercial_release_grade_rerun_bundle_v1",
        "COMMERCIAL_EVIDENCE_RECEIPTS.json",
        "preview_only_json_patch",
        "receipt_mutation_without_operator_confirmation",
        "release_grade_receipt_write_without_current_head_ci",
        "local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api",
        "raw_prompts",
        "token_values",
    ]:
        require(needle in json.dumps(spec), f"recording spec missing {needle}")
        require(needle in read_text(RECORDING_DOC), f"recording doc missing {needle}")
    script_text = read_text(RECORDING_SCRIPT)
    for needle in [
        CONTRACT_ID,
        "phase_gate_recording_requests",
        "preview_only_json_patch",
        "json_patch_preview",
        "--include-external-ci-evidence",
        "--runtime-acceptance-json",
        "--require-recording-ready",
        "--confirm-recording",
        "--recording-payload-json",
        "explicit_confirm_receipt_recording_transaction",
        "apply_recording_transaction",
    ]:
        require(needle in script_text, f"recording script missing {needle}")

    before_hash = file_hash(RECEIPTS_JSON)
    default = run_recording()
    after_hash = file_hash(RECEIPTS_JSON)
    require(before_hash == after_hash, "default recording preview must not mutate commercial evidence receipts")
    require(default.returncode == 0, f"default recording preview failed: {default.stdout}{default.stderr}")
    payload = json.loads(default.stdout)
    require(payload.get("contract") == CONTRACT_ID, "default payload contract mismatch")
    require(payload.get("status") == "blocked_receipt_recording_preview", "default recording preview must stay blocked")
    safety = payload.get("safety") or {}
    require(safety.get("network_called") is False, "default recording preview must not call network")
    require(safety.get("mutates_receipts") is False, "recording preview must not mutate receipts")
    require(safety.get("writes_release_grade_receipts") is False, "recording preview must not write release-grade receipts")
    require(safety.get("executes_rerun_commands") is False, "recording preview must not execute rerun commands")
    gate_ids = [item.get("gate_id") for item in payload.get("phase_gate_recording_requests") or []]
    require(gate_ids == REQUIRED_GATE_IDS, "recording gate coverage mismatch")
    summary = payload.get("recording_summary") or {}
    require(summary.get("recording_request_count") == len(REQUIRED_GATE_IDS), "recording request count mismatch")
    require(summary.get("mutating_write_count") == 0, "recording must report zero mutating writes")
    transaction = payload.get("recording_transaction") or {}
    require(transaction.get("operation") == "explicit_confirm_receipt_recording_transaction", "recording transaction preview missing")
    require(transaction.get("applies_by_default") is False, "recording transaction must not apply by default")
    require(transaction.get("applied") is False, "recording transaction preview must not apply")
    require(transaction.get("confirm_flag") == "--confirm-recording", "recording transaction confirm flag missing")
    require(transaction.get("writes_release_grade_receipts") is False, "recording transaction must not write release-grade receipts")
    require(transaction.get("allows_handoff_or_merge") is False, "recording transaction must not allow handoff/merge")
    require("operator_confirmation_required" in set(payload.get("blockers") or []), "operator confirmation blocker missing")
    for item in payload.get("phase_gate_recording_requests") or []:
        require(item.get("recording_id") == f"record_{item.get('gate_id')}", f"{item.get('gate_id')} recording id mismatch")
        require(item.get("operation") == "preview_only_json_patch", f"{item.get('gate_id')} operation mismatch")
        require(item.get("mutates_receipts") is False, f"{item.get('gate_id')} must be read-only")
        require(item.get("writes_release_grade_receipt") is False, f"{item.get('gate_id')} must not write release-grade receipt")
        require(item.get("requires_operator_confirmation") is True, f"{item.get('gate_id')} must require confirmation")
        require(item.get("rerun_commands"), f"{item.get('gate_id')} rerun commands missing")
        patch = item.get("json_patch_preview") or []
        require(patch, f"{item.get('gate_id')} patch preview missing")
        require(all(str(op.get("path", "")).startswith("/phase_gate_receipts/") for op in patch), f"{item.get('gate_id')} patch path mismatch")

    denied = run_recording("--confirm-recording")
    require(denied.returncode != 0, "confirmed recording must fail without exact-head/runtime evidence")
    require(before_hash == file_hash(RECEIPTS_JSON), "failed confirmed recording must not mutate receipts")

    with tempfile.TemporaryDirectory() as tmp:
        runtime_path = Path(tmp) / "runtime_acceptance.json"
        runtime_fixture(runtime_path)
        fixture = run_recording("--runtime-acceptance-json", str(runtime_path), "--require-current-runtime-evidence")
        require(fixture.returncode == 0, f"runtime fixture recording failed: {fixture.stdout}{fixture.stderr}")
        fixture_payload = json.loads(fixture.stdout)
        checks = fixture_payload.get("recording_checks") or {}
        require(checks.get("real_runtime_acceptance_verified") is True, "runtime fixture must verify real runtime acceptance")
        require(checks.get("current_runtime_evidence_supplied") is True, "runtime fixture must be current-session evidence")
        strict = run_recording("--runtime-acceptance-json", str(runtime_path), "--require-current-runtime-evidence", "--require-recording-ready")
        require(strict.returncode != 0, "strict receipt recording must remain blocked")

        synthetic_payload = Path(tmp) / "recording_payload.json"
        transaction_fixture(payload, synthetic_payload)
        temp_receipts = Path(tmp) / "receipts.json"
        temp_receipts.write_text(RECEIPTS_JSON.read_text(encoding="utf-8"), encoding="utf-8")
        temp_before = file_hash(temp_receipts)
        preview_only = run_recording("--recording-payload-json", str(synthetic_payload), "--receipts-path", str(temp_receipts))
        require(preview_only.returncode == 0, f"payload transaction preview failed: {preview_only.stdout}{preview_only.stderr}")
        require(file_hash(temp_receipts) == temp_before, "recording payload without confirmation must not mutate temp receipts")
        applied = run_recording("--recording-payload-json", str(synthetic_payload), "--receipts-path", str(temp_receipts), "--confirm-recording")
        require(applied.returncode == 0, f"confirmed temp recording failed: {applied.stdout}{applied.stderr}")
        applied_payload = json.loads(applied.stdout)
        result = applied_payload.get("recording_transaction_result") or {}
        require(result.get("applied") is True, "confirmed temp recording result must apply")
        require(result.get("mutates_receipts") is True, "confirmed temp recording must declare receipt mutation")
        require(result.get("writes_release_grade_receipts") is False, "confirmed temp recording must not write release-grade receipts")
        require(result.get("release_complete") is False and result.get("commercial_handoff_allowed") is False and result.get("ready_to_merge") is False, "confirmed temp recording must keep release/handoff/merge false")
        temp_after = read_json(temp_receipts)
        require(temp_after.get("release_complete") is False, "temp recording must keep release_complete false")
        require(temp_after.get("commercial_handoff_allowed") is False, "temp recording must keep handoff false")
        require(temp_after.get("ready_to_merge") is False, "temp recording must keep merge false")
        require(temp_after.get("receipt_recording_transactions"), "temp recording must append transaction audit metadata")
        receipt_heads = {item.get("verified_head") for item in temp_after.get("phase_gate_receipts") or []}
        require(payload.get("current_git_head") in receipt_heads, "confirmed temp recording must record current head")

    require(before_hash == file_hash(RECEIPTS_JSON), "recording smoke must leave receipts unchanged")
    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": payload.get("status"),
        "gate_count": len(payload.get("phase_gate_recording_requests") or []),
        "strict_recording_still_blocked": True,
        "receipts_mutated": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
