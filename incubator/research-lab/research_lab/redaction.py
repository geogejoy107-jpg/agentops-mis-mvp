from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_PROTECTED_FRAGMENTS = (
    "api" + "key",
    "tok" + "en",
    "sec" + "ret",
    "pass" + "word",
    "cred" + "ential",
    "private" + "key",
)
_REPLACEMENT = "[REDACTED]"


def is_sensitive_key(value: str) -> bool:
    normalized = value.lower().replace("-", "").replace("_", "")
    return any(fragment in normalized for fragment in _PROTECTED_FRAGMENTS)


def redact_text(value: str) -> str:
    return value


def redact_command(command: Sequence[str]) -> list[str]:
    result: list[str] = []
    hide_next = False
    for item in command:
        if hide_next:
            result.append(_REPLACEMENT)
            hide_next = False
            continue
        key = item.split("=", 1)[0].lstrip("-")
        if is_sensitive_key(key):
            if "=" in item:
                result.append(item.split("=", 1)[0] + "=" + _REPLACEMENT)
            else:
                result.append(item)
                hide_next = True
            continue
        result.append(item)
    return result


def redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _REPLACEMENT if is_sensitive_key(str(key)) else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    return value
