"""Pure operator action receipt projection helpers."""
from __future__ import annotations

import json
from typing import Any


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _json_object(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except Exception:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def operator_control_readback_public(row: Any | None) -> dict[str, Any] | None:
    if not row:
        return None
    row_dict = _row_dict(row)
    metadata = _json_object(row_dict.get("metadata_json"))
    control_readback = metadata.get("control_readback") if isinstance(metadata.get("control_readback"), dict) else {}
    return {
        "readback_id": metadata.get("readback_id"),
        "receipt_id": metadata.get("receipt_id") or row_dict.get("entity_id"),
        "workspace_id": metadata.get("workspace_id") or "local-demo",
        "action_id": metadata.get("action_id"),
        "action_signature": metadata.get("action_signature"),
        "source": metadata.get("source") or "operator.action_queue_control_readback",
        "control_readback": control_readback,
        "created_at": row_dict.get("created_at"),
        "tamper_chain_hash": row_dict.get("tamper_chain_hash"),
        "token_omitted": True,
    }


def operator_action_evaluation_public(row: Any | None) -> dict[str, Any] | None:
    if not row:
        return None
    row_dict = _row_dict(row)
    rubric = _json_object(row_dict.get("rubric_json"))
    return {
        "evaluation_id": row_dict.get("evaluation_id"),
        "receipt_id": row_dict.get("receipt_id"),
        "workspace_id": row_dict.get("workspace_id") or "local-demo",
        "action_id": row_dict.get("action_id"),
        "action_signature": row_dict.get("action_signature"),
        "action_hash": row_dict.get("action_hash"),
        "verify_hash": row_dict.get("verify_hash"),
        "source": row_dict.get("source") or "operator_action_queue",
        "evaluator_type": row_dict.get("evaluator_type") or "rule",
        "score": float(row_dict.get("score") or 0),
        "pass_fail": row_dict.get("pass_fail"),
        "rubric": rubric,
        "notes": row_dict.get("notes"),
        "created_at": row_dict.get("created_at"),
        "token_omitted": True,
    }


def operator_action_receipt_public(row: Any) -> dict[str, Any]:
    row_dict = _row_dict(row)
    metadata = _json_object(row_dict.get("metadata_json"))
    return {
        "receipt_id": row_dict.get("entity_id"),
        "audit_id": row_dict.get("audit_id"),
        "actor_id": row_dict.get("actor_id"),
        "workspace_id": metadata.get("workspace_id") or "local-demo",
        "status": metadata.get("status") or "recorded",
        "source": metadata.get("source") or "operator_action_queue",
        "action_id": metadata.get("action_id"),
        "action_signature": metadata.get("action_signature"),
        "action_command": metadata.get("action_command"),
        "action_hash": metadata.get("action_hash"),
        "verify_command": metadata.get("verify_command"),
        "verify_hash": metadata.get("verify_hash"),
        "result_summary": metadata.get("result_summary"),
        "control_readback": metadata.get("control_readback") if isinstance(metadata.get("control_readback"), dict) else None,
        "created_at": row_dict.get("created_at"),
        "tamper_chain_hash": row_dict.get("tamper_chain_hash"),
        "token_omitted": True,
    }


def operator_receipt_requires_control_readback(receipt: dict[str, Any]) -> bool:
    source = str(receipt.get("source") or "")
    return (
        source.startswith("advance_loop:")
        or source == "handoff.evidence_remediation"
        or source.startswith("local_readiness.service_control_preview")
        or source.startswith("ui.local_run_path.service_control_preview")
    )
