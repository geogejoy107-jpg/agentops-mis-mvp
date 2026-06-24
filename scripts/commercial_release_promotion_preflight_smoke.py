#!/usr/bin/env python3
"""Static smoke for commercial release promotion preflight."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json"
PREFLIGHT_DOC = ROOT / "docs" / "COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.md"
PREFLIGHT_SCRIPT = ROOT / "scripts" / "commercial_release_promotion_preflight.py"
CONTRACT_ID = "commercial_release_promotion_preflight_v1"

REQUIRED_JSON_STRINGS = {
    "commercial_release_promotion_preflight_v1",
    "blocked_release_promotion_required",
    "release_promotion_allowed",
    "release_grade_update_allowed",
    "clean_worktree_verified",
    "remote_sync_verified",
    "exact_head_ci_verified",
    "gates_with_release_grade_receipts_complete",
    "manual_receipt_promotion_without_ci",
    "uncommitted_dirty_promotion",
    "local_only_release_grade_claim",
    "--require-promotion-ready",
}

REQUIRED_DOC_STRINGS = {
    "commercial_release_promotion_preflight_v1",
    "blocked_release_promotion_required",
    "release_promotion_allowed",
    "release_grade_update_allowed",
    "clean_worktree_verified",
    "remote_sync_verified",
    "exact_head_ci_verified",
    "--require-promotion-ready",
    "manual_receipt_promotion_without_ci",
    "uncommitted_dirty_promotion",
    "local_only_release_grade_claim",
}

REQUIRED_SCRIPT_STRINGS = {
    "commercial_release_promotion_preflight_v1",
    "blocked_release_promotion_required",
    "release_promotion_allowed",
    "release_grade_update_allowed",
    "clean_worktree_verified",
    "remote_sync_verified",
    "exact_head_ci_verified",
    "release_grade_receipts_empty",
    "--require-promotion-ready",
}

REQUIRED_LOCAL_RECEIPT_GATES = [
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def run_preflight(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PREFLIGHT_SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify commercial release promotion preflight.")
    parser.add_argument("--require-promotion-ready", action="store_true", help="Fail unless promotion is ready.")
    args = parser.parse_args()

    preflight = read_json(PREFLIGHT_PATH)
    require(preflight.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(preflight.get("status") == "blocked_release_promotion_required", "preflight status mismatch")
    require(preflight.get("ci_safe") is True, "preflight must be CI-safe")
    require(preflight.get("release_promotion_allowed") is False, "preflight must not allow promotion")
    require(preflight.get("release_grade_update_allowed") is False, "preflight must not allow release-grade updates")
    require(preflight.get("commercial_handoff_allowed") is False, "preflight must not allow handoff")
    require(preflight.get("ready_to_merge") is False, "preflight must not claim merge readiness")

    promotion_requires = preflight.get("promotion_requires") or {}
    for key in [
        "all_local_receipts_complete",
        "gates_with_release_grade_receipts_complete",
        "clean_worktree_verified",
        "remote_sync_verified",
        "exact_head_ci_verified",
        "release_complete",
        "commercial_handoff_allowed",
        "ready_to_merge",
    ]:
        require(promotion_requires.get(key) is True, f"promotion requirement missing: {key}")

    for relative, needles in {
        "docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json": REQUIRED_JSON_STRINGS,
        "docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.md": REQUIRED_DOC_STRINGS,
        "scripts/commercial_release_promotion_preflight.py": REQUIRED_SCRIPT_STRINGS,
    }.items():
        text = read_text(ROOT / relative)
        for needle in needles:
            require(needle in text, f"{relative} missing {needle!r}")

    proc = run_preflight()
    require(proc.returncode == 0, f"preflight failed: {proc.stdout}{proc.stderr}")
    payload = json.loads(proc.stdout)
    require(payload.get("ok") is True, "preflight payload must be internally consistent")
    require(payload.get("contract") == CONTRACT_ID, "preflight payload contract mismatch")
    require(payload.get("status") == "blocked_release_promotion_required", "preflight must remain blocked")
    checks = payload.get("promotion_checks") or {}
    require(checks.get("release_promotion_allowed") is False, "runtime preflight must not allow promotion")
    require(checks.get("release_grade_update_allowed") is False, "runtime preflight must not allow release-grade updates")
    require(checks.get("release_grade_receipts_complete") is False, "release-grade receipts should not be complete")
    require(checks.get("exact_head_ci_verified") is False, "exact-head CI must remain false")
    require("release_grade_receipts_empty" in set(payload.get("blockers") or []), "release-grade blocker missing")
    require("exact_head_ci_not_verified" in set(payload.get("blockers") or []), "exact-head CI blocker missing")
    receipt_state = payload.get("receipt_state") or {}
    require(receipt_state.get("all_local_receipts_complete") is True, "local receipts should now be complete")
    require(receipt_state.get("gates_with_local_receipts") == REQUIRED_LOCAL_RECEIPT_GATES, "local receipt gate summary mismatch")
    require(receipt_state.get("gates_with_release_grade_receipts") == [], "release-grade receipt gate summary mismatch")

    if args.require_promotion_ready:
        strict = run_preflight("--require-promotion-ready")
        require(strict.returncode == 0, f"promotion is not ready: {strict.stdout}{strict.stderr}")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": payload.get("status"),
        "blockers": payload.get("blockers"),
        "strict_promotion_required": bool(args.require_promotion_ready),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
