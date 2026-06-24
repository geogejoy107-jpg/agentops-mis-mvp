#!/usr/bin/env python3
"""Preview operator-safe release-grade receipt recording patches without writing receipts."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from commercial_release_grade_rerun_bundle import build_bundle
from commercial_release_grade_receipt_plan import REQUIRED_GATE_IDS


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_release_grade_receipt_recording_v1"
RECORDING_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.json"
RECEIPTS_PATH = ROOT / "docs" / "COMMERCIAL_EVIDENCE_RECEIPTS.json"
RECEIPTS_TARGET = "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json"
FORBIDDEN_PATCH_FIELDS = {"release_complete", "commercial_handoff_allowed", "ready_to_merge"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(path: Path) -> dict[str, Any]:
    display_path = str(path)
    try:
        display_path = str(path.relative_to(ROOT))
    except ValueError:
        pass
    require(path.exists(), f"missing file: {display_path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def receipt_indexes(path: Path = RECEIPTS_PATH) -> dict[str, int]:
    receipts = read_json(path)
    return {
        str(item.get("gate_id")): index
        for index, item in enumerate(receipts.get("phase_gate_receipts") or [])
        if isinstance(item, dict)
    }


def load_recording_payload(path_value: str) -> dict[str, Any]:
    if path_value == "-":
        return json.loads(sys.stdin.read())
    return read_json(Path(path_value))


def json_patch_preview(*, bundle: dict[str, Any], current_head: str, receipt_index: int | None = None) -> list[dict[str, Any]]:
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
    path_prefix = f"/phase_gate_receipts/{receipt_index}" if receipt_index is not None else f"/phase_gate_receipts[gate_id={gate_id}]"
    return [
        {
            "op": "replace",
            "path": f"{path_prefix}/{field}",
            "value": value,
        }
        for field, value in patch_values.items()
    ]


def recording_request(*, bundle: dict[str, Any], current_head: str, global_blockers: list[str], receipt_index: int | None = None) -> dict[str, Any]:
    gate_id = str(bundle.get("gate_id") or "")
    rerun_commands = list(bundle.get("rerun_commands") or [])
    missing_commands = list(bundle.get("missing_commands") or [])
    patch = json_patch_preview(bundle=bundle, current_head=current_head, receipt_index=receipt_index)
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
        "target_index": receipt_index,
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


def recording_apply_checks(*, recording_requests: list[dict[str, Any]], recording_checks: dict[str, Any]) -> dict[str, Any]:
    return {
        "operator_confirmation_required": True,
        "exact_head_ci_verified": bool(recording_checks.get("exact_head_ci_verified")),
        "real_runtime_acceptance_verified": bool(recording_checks.get("real_runtime_acceptance_verified")),
        "current_runtime_evidence_supplied": bool(recording_checks.get("current_runtime_evidence_supplied")),
        "all_selected_requests_have_patch_preview": all(bool(item.get("json_patch_preview")) for item in recording_requests),
        "all_selected_requests_preview_only": all(item.get("operation") == "preview_only_json_patch" for item in recording_requests),
        "all_selected_requests_no_missing_commands": all(not item.get("missing_commands") for item in recording_requests),
        "all_selected_requests_no_release_grade_write": all(item.get("writes_release_grade_receipt") is False for item in recording_requests),
    }


def recording_transaction_preview(*, recording_requests: list[dict[str, Any]], recording_checks: dict[str, Any], current_head: str) -> dict[str, Any]:
    apply_checks = recording_apply_checks(recording_requests=recording_requests, recording_checks=recording_checks)
    apply_ready = all(apply_checks.values())
    selected_gate_ids = [str(item.get("gate_id")) for item in recording_requests]
    return {
        "transaction_id": f"tx_receipt_recording_{current_head[:12] or 'unknown'}",
        "operation": "explicit_confirm_receipt_recording_transaction",
        "target": RECEIPTS_TARGET,
        "confirm_flag": "--confirm-recording",
        "recording_payload_flag": "--recording-payload-json",
        "receipts_path_flag": "--receipts-path",
        "selected_gate_ids": selected_gate_ids,
        "selected_gate_count": len(selected_gate_ids),
        "apply_ready": apply_ready,
        "apply_checks": apply_checks,
        "applies_by_default": False,
        "applied": False,
        "mutates_receipts_when_confirmed": True,
        "writes_release_grade_receipts": False,
        "allows_handoff_or_merge": False,
        "requires_operator_confirmation": True,
        "confirm_command_template": "python3 scripts/commercial_release_grade_receipt_recording.py --recording-payload-json /tmp/receipt-recording-payload.json --receipts-path docs/COMMERCIAL_EVIDENCE_RECEIPTS.json --confirm-recording",
        "blocked_reasons": [key for key, ok in apply_checks.items() if not ok],
    }


def selected_requests(payload: dict[str, Any], gate_ids: list[str] | None = None) -> list[dict[str, Any]]:
    requests = [item for item in payload.get("phase_gate_recording_requests") or [] if isinstance(item, dict)]
    if gate_ids:
        requested = set(gate_ids)
        requests = [item for item in requests if str(item.get("gate_id")) in requested]
        require({str(item.get("gate_id")) for item in requests} == requested, f"selected gate ids missing from recording payload: {sorted(requested)}")
    return requests


def validate_recording_request_for_apply(request: dict[str, Any], checks: dict[str, Any]) -> None:
    gate_id = str(request.get("gate_id") or "")
    require(request.get("operation") == "preview_only_json_patch", f"{gate_id} recording operation is not preview-only")
    require(request.get("mutates_receipts") is False, f"{gate_id} source preview must be non-mutating")
    require(request.get("writes_release_grade_receipt") is False, f"{gate_id} must not write release-grade receipt")
    require(request.get("requires_operator_confirmation") is True, f"{gate_id} must require operator confirmation")
    require(not request.get("missing_commands"), f"{gate_id} still has missing local receipt commands")
    require(checks.get("exact_head_ci_verified") is True, "confirmed receipt recording requires exact-head CI evidence")
    require(checks.get("real_runtime_acceptance_verified") is True, "confirmed receipt recording requires real runtime evidence")
    require(checks.get("current_runtime_evidence_supplied") is True, "confirmed receipt recording requires current runtime evidence")
    patch = request.get("json_patch_preview") or []
    require(patch, f"{gate_id} patch preview missing")
    for op in patch:
        require(isinstance(op, dict), f"{gate_id} patch item must be an object")
        require(op.get("op") in {"replace", "add"}, f"{gate_id} unsupported patch op: {op.get('op')}")
        field = str(op.get("path") or "").split("/")[-1]
        require(field and field not in FORBIDDEN_PATCH_FIELDS, f"{gate_id} forbidden receipt patch field: {field}")
        if field == "release_grade_current":
            require(op.get("value") is False, f"{gate_id} recording transaction must not set release-grade current")


def refresh_receipt_summary(receipts: dict[str, Any]) -> None:
    phase_receipts = [item for item in receipts.get("phase_gate_receipts") or [] if isinstance(item, dict)]
    summary = dict(receipts.get("receipt_summary") or {})
    local_gates = [str(item.get("gate_id")) for item in phase_receipts if item.get("local_receipt_current") is True]
    release_grade_gates = [str(item.get("gate_id")) for item in phase_receipts if item.get("release_grade_current") is True]
    summary["gates_with_local_receipts"] = local_gates
    summary["gates_with_release_grade_receipts"] = release_grade_gates
    summary["gates_missing_local_receipts"] = [
        gate_id for gate_id in REQUIRED_GATE_IDS if gate_id not in set(local_gates)
    ]
    summary["gate_5_release_grade_current"] = "gate_5_byoc_enterprise_deployment" in set(release_grade_gates)
    receipts["receipt_summary"] = summary


def apply_recording_transaction(
    *,
    payload: dict[str, Any],
    receipts_path: Path,
    gate_ids: list[str] | None = None,
    confirm_recording: bool = False,
) -> dict[str, Any]:
    requests = selected_requests(payload, gate_ids)
    checks = dict(payload.get("recording_checks") or {})
    transaction = recording_transaction_preview(
        recording_requests=requests,
        recording_checks=checks,
        current_head=str(payload.get("current_git_head") or ""),
    )
    result = {
        "ok": True,
        "contract": CONTRACT_ID,
        "transaction_id": transaction.get("transaction_id"),
        "applied": False,
        "target": str(receipts_path),
        "selected_gate_ids": [str(item.get("gate_id")) for item in requests],
        "requires_operator_confirmation": True,
        "confirmation_supplied": bool(confirm_recording),
        "mutates_receipts": False,
        "writes_release_grade_receipts": False,
        "allows_handoff_or_merge": False,
        "release_complete": False,
        "commercial_handoff_allowed": False,
        "ready_to_merge": False,
        "apply_checks": transaction.get("apply_checks") or {},
        "blocked_reasons": list(transaction.get("blocked_reasons") or []),
    }
    if not confirm_recording:
        return result

    require(requests, "no recording requests selected")
    for request in requests:
        validate_recording_request_for_apply(request, checks)

    receipts = read_json(receipts_path)
    receipt_map = {
        str(item.get("gate_id")): item
        for item in receipts.get("phase_gate_receipts") or []
        if isinstance(item, dict)
    }
    recorded_at = now_iso()
    changed_fields: dict[str, list[str]] = {}
    for request in requests:
        gate_id = str(request.get("gate_id") or "")
        receipt = receipt_map.get(gate_id)
        require(isinstance(receipt, dict), f"{gate_id} missing from receipt ledger")
        changed: list[str] = []
        for op in request.get("json_patch_preview") or []:
            field = str(op.get("path") or "").split("/")[-1]
            before = receipt.get(field)
            receipt[field] = op.get("value")
            if before != op.get("value"):
                changed.append(field)
        receipt["verified_at"] = recorded_at
        receipt["recording_transaction_id"] = transaction.get("transaction_id")
        changed_fields[gate_id] = sorted(dict.fromkeys(changed))

    transactions = [item for item in receipts.get("receipt_recording_transactions") or [] if isinstance(item, dict)]
    transactions.append({
        "transaction_id": transaction.get("transaction_id"),
        "recorded_at": recorded_at,
        "operation": "explicit_confirm_receipt_recording_transaction",
        "selected_gate_ids": result["selected_gate_ids"],
        "current_git_head": payload.get("current_git_head"),
        "exact_head_ci_verified": checks.get("exact_head_ci_verified") is True,
        "real_runtime_acceptance_verified": checks.get("real_runtime_acceptance_verified") is True,
        "current_runtime_evidence_supplied": checks.get("current_runtime_evidence_supplied") is True,
        "writes_release_grade_receipts": False,
        "allows_handoff_or_merge": False,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "token_values_omitted": True,
    })
    receipts["receipt_recording_transactions"] = transactions
    receipts["release_complete"] = False
    receipts["commercial_handoff_allowed"] = False
    receipts["ready_to_merge"] = False
    refresh_receipt_summary(receipts)
    write_json(receipts_path, receipts)
    result.update({
        "applied": True,
        "mutates_receipts": True,
        "changed_fields": changed_fields,
        "recorded_at": recorded_at,
        "blocked_reasons": [],
    })
    return result


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
    indexes = receipt_indexes()
    recording_requests = [
        recording_request(
            bundle=item,
            current_head=current_head,
            global_blockers=global_blockers,
            receipt_index=indexes.get(str(item.get("gate_id") or "")),
        )
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
    transaction = recording_transaction_preview(
        recording_requests=recording_requests,
        recording_checks=recording_checks,
        current_head=current_head,
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
            "transaction_apply_ready": bool(transaction.get("apply_ready")),
        },
        "phase_gate_recording_requests": recording_requests,
        "recording_transaction": transaction,
        "recording_apply_checks": dict(transaction.get("apply_checks") or {}),
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
    parser.add_argument("--recording-payload-json", help="Use a previously generated recording payload JSON instead of rebuilding it.")
    parser.add_argument("--receipts-path", default=str(RECEIPTS_PATH), help="Receipt ledger path to write when --confirm-recording is supplied.")
    parser.add_argument("--gate-id", action="append", help="Limit a confirmed recording transaction to a gate id; may be repeated.")
    parser.add_argument("--confirm-recording", action="store_true", help="Apply the recording transaction to --receipts-path. Default is preview only.")
    args = parser.parse_args()

    if args.recording_payload_json:
        payload = load_recording_payload(args.recording_payload_json)
        require(payload.get("contract") == CONTRACT_ID or payload.get("contract_id") == CONTRACT_ID, "recording payload contract mismatch")
    else:
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

    if args.confirm_recording or args.recording_payload_json or args.gate_id:
        result = apply_recording_transaction(
            payload=payload,
            receipts_path=Path(args.receipts_path),
            gate_ids=list(args.gate_id or []),
            confirm_recording=bool(args.confirm_recording),
        )
        payload["recording_transaction_result"] = result

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
