#!/usr/bin/env python3
"""Verify redaction keeps safe operational IDs readable while hiding secrets."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server
from agentops_mis_cli.redaction import redact_text as shared_redact_text
from agent_worker import redact_text as worker_redact_text


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def smoke() -> dict:
    safe = "http://127.0.0.1:8642/v1/chat/completions tsk_worker_hermes_live_20260618065503 run_gw_6f995c9de929"
    redacted_safe = server.redact_text(safe, 500)
    require("127.0.0.1:8642" in redacted_safe, f"loopback URL was over-redacted: {redacted_safe}")
    require("tsk_worker_hermes_live_20260618065503" in redacted_safe, f"task id was over-redacted: {redacted_safe}")
    require("run_gw_6f995c9de929" in redacted_safe, f"run id was over-redacted: {redacted_safe}")
    require("[PHONE_REDACTED]" not in redacted_safe, f"safe operational text got phone redaction: {redacted_safe}")

    sensitive = (
        "email joy@example.com phone +1 (415) 555-0123 "
        "Authorization: Bearer sk-demo-secret token=ntn_demo_secret raw ntn_raw_secret "
        "Api_Key = sk-query-secret password: hunter2"
    )
    redacted_sensitive = server.redact_text(sensitive, 500)
    require("[EMAIL_REDACTED]" in redacted_sensitive, f"email was not redacted: {redacted_sensitive}")
    require("[PHONE_REDACTED]" in redacted_sensitive, f"phone was not redacted: {redacted_sensitive}")
    require("sk-demo-secret" not in redacted_sensitive, f"bearer secret leaked: {redacted_sensitive}")
    require("ntn_demo_secret" not in redacted_sensitive, f"token secret leaked: {redacted_sensitive}")
    require("ntn_raw_secret" not in redacted_sensitive, f"raw token secret leaked: {redacted_sensitive}")
    require("sk-query-secret" not in redacted_sensitive, f"api key secret leaked: {redacted_sensitive}")
    require("hunter2" not in redacted_sensitive, f"password leaked: {redacted_sensitive}")

    mixed_case = (
        "authorization: bearer sk-worker-secret TOKEN = ntn_worker_secret "
        "url=http://example.test/cb?api_key=sk-url-secret&session=agtsess_should_hide_123456789"
    )
    for label, redactor in [
        ("shared", shared_redact_text),
        ("server", server.redact_text),
        ("worker", worker_redact_text),
    ]:
        redacted = redactor(mixed_case, 500)
        for secret in ["sk-worker-secret", "ntn_worker_secret", "sk-url-secret", "agtsess_should_hide_123456789"]:
            require(secret not in redacted, f"{label} secret leaked: {secret} in {redacted}")

    extended = (
        "aws=AKIA1234567890ABCDEF "
        "google=AIza1234567890abcdefghijklmnopqrstuvwxyz "
        "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmaXh0dXJlIn0.signature12345 "
        "-----BEGIN " + "PRIVATE KEY-----"
    )
    extended_redacted = shared_redact_text(extended, 1000)
    for secret in ["AKIA1234567890ABCDEF", "AIza1234567890abcdefghijklmnopqrstuvwxyz", "eyJhbGciOiJIUzI1NiJ9", "BEGIN PRIVATE KEY"]:
        require(secret not in extended_redacted, f"extended secret leaked: {secret} in {extended_redacted}")

    return {
        "ok": True,
        "safe_preserved": ["127.0.0.1:8642", "tsk_worker_hermes_live_20260618065503", "run_gw_6f995c9de929"],
        "sensitive_redacted": ["email", "phone", "bearer", "token", "api_key", "password", "agent_session", "aws", "google", "jwt", "private_key"],
    }


def main() -> int:
    print(json.dumps(smoke(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
