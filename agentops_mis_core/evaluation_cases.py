"""Pure evaluation-case public projection helpers."""
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


def evaluation_case_candidate_public(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    data["rubric"] = _json_object(data.get("rubric_json"))
    data["token_omitted"] = True
    return data


def evaluation_case_run_public(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    data["checks"] = _json_object(data.get("checks_json"))
    data["token_omitted"] = True
    return data
