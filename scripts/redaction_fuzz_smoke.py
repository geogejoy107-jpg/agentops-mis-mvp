#!/usr/bin/env python3
"""Deterministic redaction fuzz/property checks for common secret shapes."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server
from agent_worker import redact_text as worker_redact_text
from agentops_mis_cli.redaction import redact_full_text as shared_redact_full_text
from agentops_mis_cli.redaction import redact_text as shared_redact_text


SECRET_VALUES = [
    "sk-fuzzOpenAISecret1234567890",
    "sk-proj-fuzzProjectSecret1234567890",
    "ntn_fuzzNotionSecret1234567890",
    "agtok_fuzzAgentToken1234567890",
    "agtsess_fuzzAgentSession1234567890",
    "ghp_fuzzGithubSecretToken1234567890",
    "github_pat_fuzzGithubFineGrainedSecretToken1234567890",
    "xoxb-fuzz-slack-secret-1234567890",
    "credential_canary_fuzzProtectedInput1234567890",
]

KEYED_ONLY_SECRET_VALUES = [
    "hunter2-fuzz-password",
]

SAFE_VALUES = [
    "http://127.0.0.1:8787/api/dashboard/metrics",
    "run_gw_6f995c9de929",
    "tsk_worker_hermes_live_20260618065503",
    "ap_prepared_action_run_123456",
    "pa_run_123456_external_write",
]

CONTEXT_TEMPLATES = [
    "Authorization: Bearer {secret}",
    "authorization: bearer {secret}",
    "TOKEN={secret}",
    "token : '{secret}'",
    "secret=\"{secret}\"",
    "password: {secret}",
    "api_key={secret}",
    "api-key: {secret}",
    "url=https://example.invalid/callback?api_key={secret}&mode=test",
    "{{\"token\":\"{secret}\",\"nested\":{{\"password\":\"{secret}\"}}}}",
    "stderr line before {secret} line after",
    "prefix " + ("x" * 80) + " {secret} suffix",
]

KEYED_CONTEXT_TEMPLATES = [
    "TOKEN={secret}",
    "token : '{secret}'",
    "secret=\"{secret}\"",
    "password: {secret}",
    "api_key={secret}",
    "api-key: {secret}",
    "url=https://example.invalid/callback?api_key={secret}&mode=test",
    "{{\"token\":\"{secret}\",\"nested\":{{\"password\":\"{secret}\"}}}}",
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def redactors():
    return [
        ("shared", lambda text, limit=500: shared_redact_text(text, limit)),
        ("shared_full", lambda text, _limit=500: shared_redact_full_text(text)),
        ("server", lambda text, limit=500: server.redact_text(text, limit)),
        ("worker", lambda text, limit=500: worker_redact_text(text, limit)),
    ]


def main() -> int:
    failures: list[str] = []
    cases = []
    for secret in SECRET_VALUES:
        for template in CONTEXT_TEMPLATES:
            cases.append(template.format(secret=secret))
    for secret in KEYED_ONLY_SECRET_VALUES:
        for template in KEYED_CONTEXT_TEMPLATES:
            cases.append(template.format(secret=secret))
    safe_bundle = " ".join(SAFE_VALUES)
    cases.append(f"{safe_bundle} no secret here")

    for label, redactor in redactors():
        for case in cases:
            redacted = redactor(case, 500)
            rerun = redactor(redacted, 500)
            require(redacted == rerun, f"{label} redaction is not idempotent: {redacted} -> {rerun}", failures)
            for secret in [*SECRET_VALUES, *KEYED_ONLY_SECRET_VALUES]:
                require(secret not in redacted, f"{label} leaked secret {secret} in {redacted}", failures)
            if safe_bundle in case:
                for safe in SAFE_VALUES:
                    require(safe in redacted, f"{label} over-redacted safe operational id {safe}: {redacted}", failures)

        short_case = "prefix sk-fuzzOpenAISecret1234567890 " + ("tail " * 80)
        short_redacted = redactor(short_case, 32)
        require("sk-fuzzOpenAISecret1234567890" not in short_redacted, f"{label} truncated before redacting secret: {short_redacted}", failures)

    output = {
        "ok": not failures,
        "operation": "redaction_fuzz_smoke",
        "redactors": [label for label, _ in redactors()],
        "case_count": len(cases),
        "secret_shapes": len(SECRET_VALUES) + len(KEYED_ONLY_SECRET_VALUES),
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
