"""Pure Approval Wall prepared-action helpers."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


REDACTION_RULES: tuple[tuple[str, str], ...] = (
    (r"(?i)(authorization\s*:\s*bearer\s+)[a-z0-9._~+/\-=]+", r"\1[REDACTED]"),
    (r"(?i)(bearer\s+)[a-z0-9._~+/\-=]+", r"\1[REDACTED]"),
    (r"(?i)([\"']?(?:token|secret|password|api[_-]?key)[\"']?\s*:\s*[\"'])[^\"']+([\"'])", r"\1[REDACTED]\2"),
    (r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;]+", r"\1=[REDACTED]"),
    (r"(?i)\b(?:sk-[a-z0-9._~+/\-=]+|ntn_[a-z0-9._~+/\-=]+)\b", "[SECRET_REDACTED]"),
    (r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b", "[SECRET_REDACTED]"),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "[SECRET_REDACTED]"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "[SECRET_REDACTED]"),
    (r"\b(?:agtok|agtsess)_[A-Za-z0-9_-]+\b", "[AGENT_TOKEN_REF_REDACTED]"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL_REDACTED]"),
    (r"(?<![\w])(?:\+\d{1,3}[\s.-]*)?(?:\(?\d{2,4}\)?[\s.-]+){2,4}\d{2,4}(?![\w])", "[PHONE_REDACTED]"),
)


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_workspace_id(value: Any) -> str:
    raw = str(value or "local-demo").strip()[:120]
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw).strip("_")
    return normalized or "local-demo"


def redact_text(text: Any, limit: int = 200) -> str:
    value = str(text or "")
    for pattern, replacement in REDACTION_RULES:
        value = re.sub(pattern, replacement, value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def safe_json_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key)[:80]: safe_json_metadata(item) for key, item in list(value.items())[:40]}
    if isinstance(value, list):
        return [safe_json_metadata(item) for item in value[:40]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(value, 240)


def _parse_json_metadata(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value or "{}")
        except Exception:
            return value
    return value


def prepared_action_id_from_request(body: dict[str, Any]) -> Any:
    return body.get("prepared_action_id") or body.get("action_id")


def prepared_action_stored_args(row: Any) -> dict[str, Any]:
    if not row:
        return {}
    data = dict(row)
    value = _parse_json_metadata(data.get("normalized_args_json") or "{}")
    return value if isinstance(value, dict) else {}


def prepared_action_checkpoint(row: Any) -> dict[str, Any]:
    if not row:
        return {}
    data = dict(row)
    value = _parse_json_metadata(data.get("checkpoint_json") or "{}")
    return value if isinstance(value, dict) else {}


def prepared_action_hash_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "workspace_id": normalize_workspace_id(row.get("workspace_id")),
        "task_id": row.get("task_id"),
        "run_id": row.get("run_id"),
        "tool_call_id": row.get("tool_call_id"),
        "requested_by_agent_id": row.get("requested_by_agent_id"),
        "action_type": row.get("action_type"),
        "normalized_args_json": row.get("normalized_args_json") or "{}",
        "target_resource": row.get("target_resource"),
        "risk_level": row.get("risk_level"),
        "policy_version": row.get("policy_version") or "approval-wall-v1",
        "checkpoint_json": row.get("checkpoint_json") or "{}",
        "idempotency_key": row.get("idempotency_key"),
    }


def prepared_action_hash(row: dict[str, Any]) -> str:
    return stable_hash(prepared_action_hash_payload(row))


def prepared_action_hash_verification(row: dict[str, Any]) -> dict[str, Any]:
    current_hash = prepared_action_hash(row)
    return {
        "stored_action_hash": row.get("action_hash"),
        "current_action_hash": current_hash,
        "match": current_hash == row.get("action_hash"),
    }


def prepared_action_public(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    normalized_args = _parse_json_metadata(data.get("normalized_args_json") or "{}")
    checkpoint = _parse_json_metadata(data.get("checkpoint_json") or "{}")
    data["normalized_args"] = safe_json_metadata(normalized_args)
    data["checkpoint"] = safe_json_metadata(checkpoint)
    data["normalized_args_json"] = json.dumps(data["normalized_args"], ensure_ascii=False, sort_keys=True)
    data["checkpoint_json"] = json.dumps(data["checkpoint"], ensure_ascii=False, sort_keys=True)
    data["raw_prompt_omitted"] = True
    data["raw_response_omitted"] = True
    data["token_omitted"] = True
    return data


def prepared_action_gate(row: Any) -> dict[str, Any]:
    if not row:
        return {
            "required_for_exact_resume": False,
            "action_hash": None,
            "hash_match": None,
            "status": None,
            "consumed_at": None,
        }
    data = dict(row)
    verification = prepared_action_hash_verification(data)
    return {
        "required_for_exact_resume": True,
        "action_hash": data.get("action_hash"),
        "hash_match": verification["match"],
        "status": data.get("status"),
        "consumed_at": data.get("consumed_at"),
    }


def prepared_action_resume_gate_error(
    *,
    action_id: Any,
    row: Any,
    approval: Any,
    expected_args: dict[str, Any],
    expected_action_type: str,
    comparable_fields: tuple[str, ...],
    missing_error: str,
    missing_message: str,
    approval_message: str,
    extra_mismatches: list[str] | None = None,
) -> dict[str, Any] | None:
    if not action_id:
        return {"error": missing_error, "message": missing_message, "token_omitted": True}
    if not row:
        return {"error": "prepared_action_not_found", "prepared_action_id": action_id, "token_omitted": True}

    data = dict(row)
    approval_data = dict(approval) if approval else None
    if not approval_data or approval_data.get("decision") != "approved":
        return {
            "error": "approval_required",
            "message": approval_message,
            "approval_id": data.get("approval_id"),
            "prepared_action_id": action_id,
            "decision": approval_data.get("decision") if approval_data else None,
            "token_omitted": True,
        }
    if data.get("consumed_at") or data.get("status") == "consumed":
        return {
            "error": "prepared_action_already_consumed",
            "prepared_action": prepared_action_public(data),
            "token_omitted": True,
        }

    verification = prepared_action_hash_verification(data)
    if not verification["match"]:
        return {
            "error": "action_hash_mismatch",
            "stored_action_hash": verification["stored_action_hash"],
            "current_action_hash": verification["current_action_hash"],
            "token_omitted": True,
        }

    stored_args = prepared_action_stored_args(data)
    mismatched = [
        field
        for field in comparable_fields
        if stored_args.get(field) != expected_args.get(field)
    ]
    mismatched.extend(item for item in (extra_mismatches or []) if item)
    if data.get("action_type") != expected_action_type or mismatched:
        return {
            "error": "prepared_action_request_mismatch",
            "prepared_action_id": action_id,
            "mismatched_fields": mismatched or ["action_type"],
            "token_omitted": True,
        }
    return None


def build_prepared_action_get_response(prepared_action: Any, approval: Any) -> dict[str, Any]:
    row = dict(prepared_action)
    verification = prepared_action_hash_verification(row)
    return {
        "provider": "agentops-approval-wall",
        "operation": "prepared_action_get",
        "status": "ready" if verification["match"] else "blocked",
        "prepared_action": prepared_action_public(row),
        "approval": dict(approval) if approval else None,
        "hash_verification": verification,
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
        "token_omitted": True,
    }


def approval_wall_recommended_actions(approval: dict[str, Any], prepared_action: Any, approval_id: str) -> list[str]:
    row = dict(prepared_action) if prepared_action else None
    if approval.get("decision") == "pending":
        return [
            action
            for action in (
                f"agentops approval prepared-action get --action-id {row['action_id']}" if row else f"agentops approval inspect --approval-id {approval_id}",
                f"agentops approval approve --approval-id {approval_id}",
                f"agentops approval reject --approval-id {approval_id}",
                f"agentops approval prepared-action resume --action-id {row['action_id']} --provider-side-effect-id <id>" if row else "",
            )
            if action
        ]
    if row and approval.get("decision") == "approved" and not row.get("consumed_at"):
        return [f"agentops approval prepared-action resume --action-id {row['action_id']} --provider-side-effect-id <id>"]
    return ["agentops approval list --decision pending"]
