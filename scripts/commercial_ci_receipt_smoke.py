#!/usr/bin/env python3
"""Smoke test exact-head command, scope, and aggregate CI receipts."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "scripts" / "commercial_ci_receipt.py"


def run(args: list[str]) -> tuple[int, dict]:
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    try:
        payload = json.loads(proc.stdout)
    except Exception:
        payload = {}
    return proc.returncode, payload


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-ci-receipt-") as tmp:
        tmp_path = Path(tmp)
        receipts = tmp_path / "commands"
        good_path = receipts / "good.json"
        failed_path = receipts / "failed.json"
        skipped_path = receipts / "skipped.json"
        scope_path = tmp_path / "scope.json"
        aggregate_path = tmp_path / "aggregate.json"

        code, good = run([
            sys.executable,
            str(RECEIPT),
            "command",
            "--gate-id",
            "gate_test",
            "--command-id",
            "good",
            "--expected-contract",
            "fixture_v1",
            "--output",
            str(good_path),
            "--",
            sys.executable,
            "-c",
            'import json; print(json.dumps({"ok": True, "contract": "fixture_v1", "skipped": False}))',
        ])
        require(code == 0 and good.get("evidence_complete") is True, f"good command receipt failed: {good}", failures)
        require(good.get("raw_output_stored") is False, f"raw output policy missing: {good}", failures)
        require(len(str(good.get("subject_sha") or "")) == 40, f"subject SHA missing: {good}", failures)

        sensitive_failure = "customer token agtok_should_not_escape"
        failure_fixture = tmp_path / "emit_failure.py"
        failure_fixture.write_text(
            "import json, sys\n"
            f"print(json.dumps({{'ok': False, 'error_type': 'RuntimeError', "
            f"'failure_count': 2, 'failures': ['fixture_failed', {sensitive_failure!r}]}}))\n"
            "sys.exit(1)\n",
            encoding="utf-8",
        )
        code, failed = run([
            sys.executable,
            str(RECEIPT),
            "command",
            "--gate-id",
            "gate_test",
            "--command-id",
            "failed",
            "--output",
            str(failed_path),
            "--",
            sys.executable,
            str(failure_fixture),
        ])
        diagnostics = failed.get("payload_diagnostics") or {}
        require(code == 1 and failed.get("evidence_complete") is False, f"failed command receipt accepted: {failed}", failures)
        require(diagnostics.get("error_codes") == ["RuntimeError", "fixture_failed"], f"safe diagnostics missing: {failed}", failures)
        require(len(diagnostics.get("failure_hashes") or []) == 2, f"failure hashes missing: {failed}", failures)
        require(diagnostics.get("failure_text_stored") is False, f"failure text policy missing: {failed}", failures)
        require(sensitive_failure not in failed_path.read_text(encoding="utf-8"), "failure receipt stored raw sensitive text", failures)

        code, skipped = run([
            sys.executable,
            str(RECEIPT),
            "command",
            "--gate-id",
            "gate_test",
            "--command-id",
            "skipped",
            "--output",
            str(skipped_path),
            "--",
            sys.executable,
            "-c",
            'import json; print(json.dumps({"ok": True, "skipped": True}))',
        ])
        require(code == 1 and skipped.get("skipped_evidence") is True, f"skipped evidence accepted: {skipped}", failures)

        code, scope = run([
            sys.executable,
            str(RECEIPT),
            "scope",
            "--gate-id",
            "gate_test",
            "--receipts-dir",
            str(receipts),
            "--required-command-id",
            "good",
            "--output",
            str(scope_path),
        ])
        require(code == 0 and scope.get("scope_evidence_complete") is True, f"scope receipt failed: {scope}", failures)
        scope_commands = scope.get("command_receipts") or []
        require(scope_commands and scope_commands[0].get("expected_contracts") == ["fixture_v1"], f"scope contract evidence missing: {scope}", failures)
        require(bool((scope_commands[0].get("dependency_inputs") or {}).get("inputs_sha256")), f"scope dependency hash missing: {scope}", failures)

        code, aggregate = run([
            sys.executable,
            str(RECEIPT),
            "aggregate",
            "--scope-receipt",
            str(scope_path),
            "--required-scope",
            "gate_test",
            "--job-result",
            "gate_test=success",
            "--output",
            str(aggregate_path),
        ])
        require(code == 0 and aggregate.get("ci_run_complete") is True, f"aggregate receipt failed: {aggregate}", failures)
        require(aggregate.get("release_complete") is False, f"receipt self-promoted release: {aggregate}", failures)

    print(json.dumps({
        "ok": not failures,
        "contract_id": "commercial_ci_receipt_smoke_v1",
        "failure_count": len(failures),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
