#!/usr/bin/env python3
"""Verify Worker adapter evidence without starting either control-plane API."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentops_mis_cli import worker  # noqa: E402


TASK = {
    "task_id": "tsk_provider_evidence",
    "title": "Provider evidence contract",
    "description": "Return a bounded visible result.",
    "acceptance_criteria": "Prove live adapter evidence flags.",
    "risk_level": "low",
}


class FakeHermesResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps({
            "choices": [{"message": {"content": "Hermes visible result"}}],
            "usage": {"completion_tokens": 4},
        }).encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def evidence(result: worker.AdapterResult) -> dict[str, object]:
    return {
        "ok": result.ok,
        "provider_call_performed": result.provider_call_performed,
        "dry_run": result.dry_run,
        "error_type": result.error_type,
        "target_resource": result.target_resource,
    }


def main() -> int:
    hermes_dry = worker.execute_hermes(TASK, "http://127.0.0.1:8642", "hermes-agent", 5, False)
    openclaw_dry = worker.execute_openclaw(TASK, "/missing/openclaw", "main", 5, False)

    with patch.object(worker, "urlopen", return_value=FakeHermesResponse()) as hermes_call:
        hermes_live = worker.execute_hermes(TASK, "http://127.0.0.1:8642", "hermes-agent", 5, True)
    openclaw_payload = {
        "result": {
            "meta": {"durationMs": 7, "finalAssistantVisibleText": "OpenClaw visible result"},
            "payloads": [],
        }
    }
    with patch.object(
        worker.subprocess,
        "run",
        return_value=subprocess.CompletedProcess(["openclaw"], 0, json.dumps(openclaw_payload), ""),
    ) as openclaw_call:
        openclaw_live = worker.execute_openclaw(TASK, "/opt/homebrew/bin/openclaw", "main", 5, True)

    for label, result in (("hermes_dry", hermes_dry), ("openclaw_dry", openclaw_dry)):
        require(not result.ok, f"{label} unexpectedly succeeded")
        require(result.dry_run is True, f"{label} did not mark dry_run")
        require(result.provider_call_performed is False, f"{label} called its provider")
        require(result.error_type == "ConfirmRunRequired", f"{label} lost the confirmation gate")
    for label, result in (("hermes_live", hermes_live), ("openclaw_live", openclaw_live)):
        require(result.ok, f"{label} did not complete")
        require(result.dry_run is False, f"{label} remained a dry run")
        require(result.provider_call_performed is True, f"{label} omitted provider-call evidence")
        require(bool(result.target_resource), f"{label} omitted its target")
    require(hermes_call.call_count == 1, "Hermes provider call count was not exactly one")
    require(openclaw_call.call_count == 1, "OpenClaw provider call count was not exactly one")

    print(json.dumps({
        "ok": True,
        "contract": "worker_provider_call_evidence_v1",
        "python_api_started": False,
        "cases": {
            "hermes_dry": evidence(hermes_dry),
            "openclaw_dry": evidence(openclaw_dry),
            "hermes_live": evidence(hermes_live),
            "openclaw_live": evidence(openclaw_live),
        },
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
