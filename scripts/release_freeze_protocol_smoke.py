#!/usr/bin/env python3
"""Static release-freeze gate for the commercial migration branch."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FREEZE_PATH = ROOT / "docs" / "RELEASE_FREEZE_PROTOCOL.json"
FREEZE_DOC = ROOT / "docs" / "RELEASE_FREEZE_PROTOCOL.md"
RELEASE_SMOKE = ROOT / "scripts" / "release_evidence_packet_smoke.py"
CONTRACT_ID = "release_freeze_protocol_v1"

REQUIRED_COMMANDS = {
    "python3 scripts/commercial_exact_head_ci_evidence_smoke.py",
    "python3 scripts/commercial_exact_head_ci_evidence.py --from-gh --require-current-head",
    "python3 scripts/commercial_release_promotion_preflight.py",
    "python3 scripts/commercial_release_promotion_preflight.py --include-external-ci-evidence",
    "python3 scripts/commercial_release_promotion_preflight_smoke.py",
    "python3 scripts/commercial_evidence_receipts_smoke.py",
    "python3 scripts/commercial_current_evidence_status_smoke.py",
    "python3 scripts/commercial_handoff_status_smoke.py",
    "python3 scripts/release_evidence_packet_smoke.py",
    "python3 scripts/commercial_release_evidence_packet_smoke.py",
    "python3 scripts/commercial_migration_readiness.py",
    "python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture",
    "python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
    "python3 scripts/nextjs_postgres_control_plane_tasks_smoke.py",
    "python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    "HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api --openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720",
}

REQUIRED_CONTRACTS = {
    "commercial_exact_head_ci_evidence_v1",
    "commercial_release_promotion_preflight_v1",
    "commercial_evidence_receipts_v1",
    "commercial_current_evidence_status_v1",
    "commercial_handoff_status_v1",
    "release_evidence_packet_v1",
    "commercial_release_evidence_packet_v1",
    "deployment_readiness_postgres_runtime_write_fixture_v1",
    "nextjs_deployment_postgres_runtime_write_fixture_v1",
    "nextjs_postgres_control_plane_tasks_v1",
    "byoc_deployment_acceptance_v1",
    "real_hermes_openclaw_acceptance",
}

FORBIDDEN_EVIDENCE = {
    "manual_receipt_promotion_without_ci",
    "uncommitted_dirty_promotion",
    "local_only_release_grade_claim",
    "--skip-postgres-if-unavailable",
    "mock_only_product_claim",
    "release_complete_true",
    "raw_prompts",
    "raw_responses",
    "private_transcripts",
    "token_values",
    "sqlite_fallback_as_postgres_proof",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def git_status_short() -> str:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return proc.stdout.strip() or proc.stderr.strip()


def run_release_smoke() -> None:
    proc = subprocess.run(
        [sys.executable, str(RELEASE_SMOKE)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    require(proc.returncode == 0, f"release evidence packet smoke failed: {proc.stdout}{proc.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the commercial release freeze protocol.")
    parser.add_argument("--require-clean", action="store_true", help="Fail unless git status --short is clean.")
    args = parser.parse_args()

    freeze = read_json(FREEZE_PATH)
    require(freeze.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(freeze.get("status") == "freeze_active_not_release_complete", "freeze status mismatch")
    require(freeze.get("freeze_active") is True, "freeze must be active")
    require(freeze.get("release_complete") is False, "freeze protocol must not claim release completion")
    require(freeze.get("commercial_handoff_allowed") is False, "freeze protocol must not allow commercial handoff")
    require(freeze.get("release_evidence_packet") == "docs/RELEASE_EVIDENCE_PACKET.json", "release packet path mismatch")
    require(freeze.get("commercial_packet") == "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "commercial packet path mismatch")
    require(freeze.get("source_contract_id") == "commercial_release_evidence_packet_v1", "source contract mismatch")
    require(freeze.get("verification_command") == "python3 scripts/release_freeze_protocol_smoke.py", "verification command mismatch")
    require(REQUIRED_COMMANDS <= set(freeze.get("required_freeze_commands") or []), "freeze misses required commands")
    require(REQUIRED_CONTRACTS <= set(freeze.get("required_contracts") or []), "freeze misses required contracts")
    require(FORBIDDEN_EVIDENCE <= set(freeze.get("must_not_use") or []), "freeze forbidden evidence list is incomplete")

    policies = freeze.get("freeze_policies") or {}
    require(policies.get("feature_expansion_paused_until_gate_evidence") is True, "feature expansion pause missing")
    require(policies.get("agent_gateway_cli_api_mcp_unchanged") is True, "Agent Gateway contract policy missing")
    require(policies.get("postgres_proof_must_not_be_skipped") is True, "Postgres skip policy missing")
    require(policies.get("mock_only_product_claims_forbidden") is True, "mock-only policy missing")
    require(policies.get("raw_prompts_responses_tokens_forbidden") is True, "sensitive output policy missing")

    doc = read_text(FREEZE_DOC)
    require(CONTRACT_ID in doc, "freeze doc must name the contract")
    require("freeze_active_not_release_complete" in doc, "freeze doc must name the freeze status")
    for command in REQUIRED_COMMANDS:
        require(command in doc, f"freeze doc missing command: {command}")
    require("--skip-postgres-if-unavailable" in doc and "mock-only" in doc, "freeze doc must name invalid evidence")

    run_release_smoke()
    status = git_status_short()
    if args.require_clean:
        require(not status, f"working tree is not clean:\n{status}")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "freeze_active": True,
        "commercial_handoff_allowed": False,
        "release_complete": False,
        "strict_clean_required": bool(args.require_clean),
        "working_tree_clean": not bool(status),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
