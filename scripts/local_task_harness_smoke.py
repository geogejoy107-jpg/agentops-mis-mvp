#!/usr/bin/env python3
"""Validate the local task harness plan-only contract."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "local_task_harness.py"


SECRET_RE = re.compile(
    r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,}|github_pat_[A-Za-z0-9_]+|gh[opsu]_[A-Za-z0-9_]+)",
    re.IGNORECASE,
)


def run(args: list[str]) -> dict:
    proc = subprocess.run(
        ["python3", str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(proc.stderr or proc.stdout)
    if SECRET_RE.search(proc.stdout + proc.stderr):
        raise AssertionError("secret-like value leaked from local task harness")
    return json.loads(proc.stdout)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    mock = run(["--adapter", "mock", "--title", "Local task harness smoke"])
    hermes = run(["--adapter", "hermes", "--title", "Hermes local task harness smoke"])
    openclaw = run(["--adapter", "openclaw", "--confirm-run", "--title", "OpenClaw local task harness smoke"])

    for payload, adapter in [(mock, "mock"), (hermes, "hermes"), (openclaw, "openclaw")]:
        packet = payload.get("work_packet") or {}
        safety = payload.get("safety") or {}
        require(payload.get("ok") is True, f"{adapter} harness should be ok: {payload}")
        require(payload.get("mode") == "plan", f"{adapter} harness must default to plan-only: {payload}")
        require(payload.get("adapter") == adapter, f"{adapter} payload adapter mismatch: {payload}")
        require(safety.get("plan_only") is True, f"{adapter} plan-only safety missing: {safety}")
        require(safety.get("live_execution_performed") is False, f"{adapter} must not run live in smoke: {safety}")
        require(safety.get("ledger_mutated") is False, f"{adapter} must not mutate ledger in smoke: {safety}")
        require(packet.get("packet_kind") == "local_task_harness_v1", f"{adapter} packet kind missing: {packet}")
        require("agent_id" in packet and packet["agent_id"], f"{adapter} packet missing agent id: {packet}")
        require("agentops workflow run-task" in " ".join(packet.get("allowed_commands") or []), f"{adapter} command missing: {packet}")
        require("READ task and authority refs" in (packet.get("required_gates") or []), f"{adapter} READ gate missing: {packet}")
        require("VERIFY run/tool/evaluation/artifact/audit evidence" in (packet.get("required_gates") or []), f"{adapter} VERIFY gate missing: {packet}")
        require((packet.get("redaction_rules") or {}).get("raw_prompt_stored") is False, f"{adapter} prompt redaction missing: {packet}")

    require(mock["work_packet"].get("confirm_required") is False, f"mock should not require live confirm: {mock}")
    require(hermes["work_packet"].get("confirm_required") is True, f"Hermes should require confirm: {hermes}")
    require("--confirm-run" not in " ".join(hermes["work_packet"].get("allowed_commands") or []), "Hermes unconfirmed plan must not include confirm-run")
    require(openclaw["confirm_run"] is True, "OpenClaw confirmed plan should reflect confirm_run")
    require("--confirm-run" in " ".join(openclaw["work_packet"].get("allowed_commands") or []), "OpenClaw confirmed plan should include confirm-run")

    print(json.dumps({
        "ok": True,
        "operation": "local_task_harness_smoke",
        "adapters_checked": ["mock", "hermes", "openclaw"],
        "live_execution_performed": False,
        "ledger_mutated": False,
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
