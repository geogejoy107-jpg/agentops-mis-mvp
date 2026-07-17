#!/usr/bin/env python3
"""Static smoke for external exact-head commercial CI evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "commercial_exact_head_ci_evidence.py"
CONTRACT_ID = "commercial_exact_head_ci_evidence_v1"
sys.path.insert(0, str(ROOT / "scripts"))

import commercial_exact_head_ci_evidence as evidence  # noqa: E402

REQUIRED_SCRIPT_STRINGS = {
    "commercial_exact_head_ci_evidence_v1",
    "Commercial Migration CI",
    "Commercial core gates",
    "Storage and Postgres parity",
    "UI parity and build evidence",
    "Independent Postgres and BYOC evidence",
    "Assemble immutable commercial CI receipt",
    "commercial-migration-ci-receipt",
    "commercial_migration_ci_receipt_v1",
    "receipt_head_mismatch",
    "workflow_matches_expected",
    "--from-gh",
    "--require-current-head",
    "in_progress_ci_as_exact_head_proof",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify external exact-head CI evidence reader.")
    parser.add_argument("--from-gh", action="store_true", help="Also exercise the live gh lookup.")
    parser.add_argument("--require-current-head", action="store_true", help="Fail unless live gh lookup verifies current HEAD.")
    args = parser.parse_args()

    script_text = read_text(SCRIPT)
    for needle in REQUIRED_SCRIPT_STRINGS:
        require(needle in script_text, f"script missing {needle!r}")

    default = run_script()
    require(default.returncode == 0, f"default evidence reader failed: {default.stdout}{default.stderr}")
    payload = json.loads(default.stdout)
    require(payload.get("ok") is True, "default payload must be ok")
    require(payload.get("contract") == CONTRACT_ID, "contract mismatch")
    require(payload.get("external_check_requested") is False, "default must not query external CI")
    require(payload.get("exact_head_ci_verified") is False, "default must not claim exact-head CI")
    require(payload.get("status") == "external_ci_check_not_requested", "default status mismatch")

    fixture_head = "a" * 40
    fixture_receipt = {
        "contract_id": "commercial_migration_ci_receipt_v1",
        "subject_sha": fixture_head,
        "builder_sha": fixture_head,
        "github_run": {"run_id": "123"},
        "required_scopes": [
            "gate_3_storage_boundary_before_postgres",
            "gate_5_byoc_enterprise_deployment_ci",
        ],
        "scope_evidence_complete": True,
        "ci_run_complete": True,
        "raw_output_stored": False,
        "credentials_stored": False,
        "release_complete": False,
        "commercial_handoff_allowed": False,
        "ready_to_merge": False,
    }
    receipt_ok, receipt_failures = evidence.validate_receipt_artifact(fixture_receipt, head=fixture_head, run_id="123")
    require(receipt_ok and not receipt_failures, f"valid aggregate receipt rejected: {receipt_failures}")
    fixture_receipt["release_complete"] = True
    receipt_ok, receipt_failures = evidence.validate_receipt_artifact(fixture_receipt, head=fixture_head, run_id="123")
    require(not receipt_ok and "receipt_release_state_invalid" in receipt_failures, "self-promoted receipt was accepted")

    if args.from_gh or args.require_current_head:
        live_args = ["--from-gh"]
        if args.require_current_head:
            live_args.append("--require-current-head")
        live = run_script(*live_args)
        require(live.returncode == 0, f"live exact-head CI evidence failed: {live.stdout}{live.stderr}")
        live_payload = json.loads(live.stdout)
        require(live_payload.get("external_check_requested") is True, "live payload must request external check")
        if args.require_current_head:
            require(live_payload.get("exact_head_ci_verified") is True, "live payload must verify current HEAD")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "live_check_requested": bool(args.from_gh or args.require_current_head),
        "strict_current_head_required": bool(args.require_current_head),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
