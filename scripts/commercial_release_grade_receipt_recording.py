#!/usr/bin/env python3
"""Preview operator-safe release-grade receipt recording patches without writing receipts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from commercial_release_grade_rerun_bundle import build_bundle
from commercial_release_grade_receipt_plan import REQUIRED_GATE_IDS


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_release_grade_receipt_recording_v1"
RECORDING_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.json"
RECEIPTS_TARGET = "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(path: Path) -> dict[str, Any]:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def json_patch_preview(*, bundle: dict[str, Any], current_head: str) -> list[dict[str, Any]]:
    gate_id = str(bundle.get("gate_id") or "")
    write_preview = bundle.get("write_preview") or {}
    would_set = write_preview.get("would_set") if isinstance(write_preview.get("would_set"), dict) else {}
    patch_values = {
        "verified_head": current_head,
        "local_receipt_current": bool(would_set.get("local_receipt_current")),
        "release_grade_current": False,
        "receipt_state": "local_receipt_recording_preview_ready",
        "evidence_level": "local_current_not_release_grade",
        "release_grade_update_allowed": False,
    }
    return [
        {
            "op": "replace",
            "path": f"/phase_gate_receipts/{gate_id}/{field}",
            "value": value,
        }
        for field, value in patch_values.items()
    ]


def recording_request(*, bundle: dict[str, Any], current_head: str, global_blockers: list[str]) -> dict[str, Any]:
    gate_id = str(bundle.get("gate_id") or "")
    rerun_commands = list(bundle.get("rerun_commands") or [])
    missing_commands = list(bundle.get("missing_commands") or [])
    patch = json_patch_preview(bundle=bundle, current_head=current_head)
    blockers = list(bundle.get("blockers") or []) + list(global_blockers)
    if bundle.get("receipt_head_current") is not True:
        blockers.append("receipt_head_not_current")
    if missing_commands:
        blockers.append("local_receipt_commands_missing")
    blockers.append("operator_confirmation_required")
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "gate_id": gate_id,
        "recording_id": f"record_{gate_id}",
        "state": "blocked_recording_preview" if blockers else "recording_preview_ready",
        "target": RECEIPTS_TARGET,
        "target_path": f"phase_gate_receipts[gate_id={gate_id}]",
        "operation": "preview_only_json_patch",
        "mutates_receipts": False,
        "writes_release_grade_receipt": False,
        "current_head": current_head,
        "previous_verified_head": str(bundle.get("previous_verified_head") or ""),
        "receipt_head_current": bool(bundle.get("receipt_head_current")),
        "local_receipt_current": bool(bundle.get("local_receipt_current")),
        "release_grade_current": bool(bundle.get("release_grade_current")),
        "requires_operator_rerun": bool(not bundle.get("receipt_head_current") or missing_commands),
        "requires_operator_confirmation": True,
        "rerun_commands": rerun_commands,
        "command_count": len(rerun_commands),
        "missing_commands": missing_commands,
        "json_patch_preview": patch,
        "patch_preview_count": len(patch),
        "blockers": blockers,
    }


def build_recording(
    *,
    include_external_ci: bool = False,
    require_external_ci: bool = False,
    external_ci_run_id: str | None = None,
    runtime_acceptance_json: str | None = None,
    require_current_runtime: bool = False,
) -> dict[str, Any]:
    spec = read_json(RECORDING_PATH)
    require(spec.get("contract_id") == CONTRACT_ID, "recording contract mismatch")
    bundle_payload = build_bundle(
        include_external_ci=include_external_ci,
        require_external_ci=require_external_ci,
        external_ci_run_id=external_ci_run_id,
        runtime_acceptance_json=runtime_acceptance_json,
        require_current_runtime=require_current_runtime,
    )
    current_head = str(bundle_payload.get("current_git_head") or "")
    bundles = list(bundle_payload.get("phase_gate_rerun_bundles") or [])
    require([str(item.get("gate_id")) for item in bundles] == REQUIRED_GATE_IDS, "recording gate coverage mismatch")
    global_blockers = list(bundle_payload.get("blockers") or [])
    recording_requests = [
        recording_request(bundle=item, current_head=current_head, global_blockers=global_blockers)
        for item in bundles
    ]
    all_preview_only = all(item.get("operation") == "preview_only_json_patch" and item.get("mutates_receipts") is False for item in recording_requests)
    mutation_count = sum(1 for item in recording_requests if item.get("mutates_receipts") is not False)
    patch_count = sum(int(item.get("patch_preview_count") or 0) for item in recording_requests)
    bundle_checks = dict(bundle_payload.get("bundle_checks") or {})
    recording_checks = {
        "all_gate_recording_patches_materialized": len(recording_requests) == len(REQUIRED_GATE_IDS),
        "all_recording_patches_preview_only": all_preview_only,
        "all_receipt_mutation_disabled": mutation_count == 0,
        "all_gate_receipts_current_head": bool(bundle_checks.get("all_gate_receipts_current_head")),
        "exact_head_ci_verified": bool(bundle_checks.get("exact_head_ci_verified")),
        "real_runtime_acceptance_verified": bool(bundle_checks.get("real_runtime_acceptance_verified")),
        "current_runtime_evidence_supplied": bool((bundle_payload.get("plan_summary") or {}).get("current_runtime_evidence_supplied")),
        "clean_worktree_verified": bool(bundle_checks.get("clean_worktree_verified")),
        "remote_sync_verified": bool(bundle_checks.get("remote_sync_verified")),
        "release_complete": bool(bundle_checks.get("release_complete")),
        "commercial_handoff_allowed": bool(bundle_checks.get("commercial_handoff_allowed")),
        "ready_to_merge": bool(bundle_checks.get("ready_to_merge")),
    }
    blockers = list(global_blockers)
    if any(item.get("requires_operator_rerun") for item in recording_requests):
        blockers.append("receipt_rerun_required")
    if any(item.get("requires_operator_confirmation") for item in recording_requests):
        blockers.append("operator_confirmation_required")
    if mutation_count:
        blockers.append("receipt_recording_preview_not_read_only")
    blockers = sorted(dict.fromkeys(blockers))
    recording_ready = not blockers and all(
        recording_checks.get(key) is expected
        for key, expected in (spec.get("recording_requires") or {}).items()
    )
    return {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": "receipt_recording_ready" if recording_ready else "blocked_receipt_recording_preview",
        "ci_safe": True,
        "read_only": True,
        "current_git_head": current_head,
        "source_contracts": list(spec.get("source_contracts") or []),
        "release_grade_rerun_bundle": {
            "contract": bundle_payload.get("contract"),
            "status": bundle_payload.get("status"),
            "blockers": list(bundle_payload.get("blockers") or []),
            "bundle_summary": dict(bundle_payload.get("bundle_summary") or {}),
        },
        "recording_checks": recording_checks,
        "recording_requires": dict(spec.get("recording_requires") or {}),
        "recording_summary": {
            "gate_count": len(REQUIRED_GATE_IDS),
            "recording_request_count": len(recording_requests),
            "patch_preview_count": patch_count,
            "mutating_write_count": mutation_count,
            "requests_requiring_rerun": sum(1 for item in recording_requests if item.get("requires_operator_rerun")),
            "requests_requiring_confirmation": sum(1 for item in recording_requests if item.get("requires_operator_confirmation")),
        },
        "phase_gate_recording_requests": recording_requests,
        "blockers": blockers,
        "required_commands": list(spec.get("required_commands") or []),
        "must_not_use": list(spec.get("must_not_use") or []),
        "safety": {
            "read_only": True,
            "ci_safe": True,
            "network_called": bool((bundle_payload.get("safety") or {}).get("network_called")),
            "live_execution_performed": False,
            "executes_rerun_commands": False,
            "mutates_receipts": False,
            "writes_release_grade_receipts": False,
            "allows_handoff_or_merge": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "private_transcripts_omitted": True,
            "billing_call_performed": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview commercial release-grade receipt recording patches.")
    parser.add_argument("--include-external-ci-evidence", action="store_true", help="Query GitHub Actions for current HEAD exact CI evidence.")
    parser.add_argument("--require-external-ci-evidence", action="store_true", help="Fail unless GitHub Actions verifies current HEAD exact CI evidence.")
    parser.add_argument("--external-ci-run-id", help="Specific GitHub Actions run id to verify as exact-head CI evidence.")
    parser.add_argument("--runtime-acceptance-json", help="Path to local_runtime_acceptance.py JSON output, or '-' for stdin.")
    parser.add_argument("--require-current-runtime-evidence", action="store_true", help="Require operator-supplied runtime acceptance JSON.")
    parser.add_argument("--require-recording-ready", action="store_true", help="Fail unless every receipt recording requirement is ready.")
    args = parser.parse_args()

    payload = build_recording(
        include_external_ci=bool(args.include_external_ci_evidence or args.require_external_ci_evidence),
        require_external_ci=bool(args.require_external_ci_evidence),
        external_ci_run_id=args.external_ci_run_id,
        runtime_acceptance_json=args.runtime_acceptance_json,
        require_current_runtime=bool(args.require_current_runtime_evidence),
    )
    if args.require_recording_ready:
        require(payload["status"] == "receipt_recording_ready", f"receipt recording blockers remain: {payload['blockers']}")
        for key, expected in (payload.get("recording_requires") or {}).items():
            require((payload.get("recording_checks") or {}).get(key) is expected, f"recording requirement not met: {key}")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
