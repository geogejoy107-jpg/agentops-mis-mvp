#!/usr/bin/env python3
"""CI-safe release-grade promotion preflight for commercial evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_release_promotion_preflight_v1"
PREFLIGHT_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json"
EXACT_HEAD_CI_SCRIPT = ROOT / "scripts" / "commercial_exact_head_ci_evidence.py"
REQUIRED_RELEASE_GRADE_GATES = [
    "gate_1_product_packaging_and_entitlement",
    "gate_2_production_safety_baseline",
    "gate_3_storage_boundary_before_postgres",
    "gate_4_ui_api_parity_before_nextjs",
    "gate_5_byoc_enterprise_deployment",
]


SOURCE_SPECS = [
    ("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", "commercial_evidence_receipts_v1"),
    ("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "commercial_current_evidence_status_v1"),
    ("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_handoff_status_v1"),
    ("docs/RELEASE_FREEZE_PROTOCOL.json", "release_freeze_protocol_v1"),
    ("docs/MERGE_READINESS_STATUS.json", "merge_readiness_status_v1"),
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(relative_path: str | Path) -> dict[str, Any]:
    path = relative_path if isinstance(relative_path, Path) else ROOT / relative_path
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def git_output(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return (proc.stdout or proc.stderr).strip()


def ahead_behind() -> tuple[int | None, int | None]:
    raw = git_output("rev-list", "--left-right", "--count", "@{u}...HEAD")
    parts = raw.split()
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None, None
    behind, ahead = (int(parts[0]), int(parts[1]))
    return ahead, behind


def source_payloads() -> list[dict[str, Any]]:
    sources = []
    for path, contract_id in SOURCE_SPECS:
        payload = read_json(path)
        require(payload.get("contract_id") == contract_id, f"{path} contract mismatch")
        sources.append({
            "path": path,
            "contract_id": contract_id,
            "status": payload.get("status"),
        })
    return sources


def external_exact_head_ci_evidence(include_external_ci: bool, require_external_ci: bool, run_id: str | None) -> dict[str, Any]:
    if not include_external_ci and not require_external_ci:
        return {
            "checked": False,
            "exact_head_ci_verified": False,
            "status": "external_ci_check_not_requested",
        }
    args = [sys.executable, str(EXACT_HEAD_CI_SCRIPT), "--from-gh"]
    if require_external_ci:
        args.append("--require-current-head")
    if run_id:
        args.extend(["--run-id", run_id])
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )
    if proc.returncode != 0:
        if require_external_ci:
            raise AssertionError(f"external exact-head CI evidence failed: {proc.stdout}{proc.stderr}")
        return {
            "checked": True,
            "exact_head_ci_verified": False,
            "status": "exact_head_ci_not_verified",
            "error": (proc.stderr or proc.stdout).strip(),
        }
    payload = json.loads(proc.stdout)
    payload["checked"] = True
    return payload


def build_payload(include_external_ci: bool = False, require_external_ci: bool = False, external_ci_run_id: str | None = None) -> dict[str, Any]:
    preflight = read_json(PREFLIGHT_PATH)
    require(preflight.get("contract_id") == CONTRACT_ID, "preflight contract mismatch")
    require(preflight.get("status") == "blocked_release_promotion_required", "preflight status mismatch")
    require(preflight.get("release_promotion_allowed") is False, "preflight must not allow promotion by default")
    require(preflight.get("release_grade_update_allowed") is False, "preflight must not allow release-grade updates by default")

    receipts = read_json("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json")
    current = read_json("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json")
    handoff = read_json("docs/COMMERCIAL_HANDOFF_STATUS.json")
    merge = read_json("docs/MERGE_READINESS_STATUS.json")

    receipt_summary = receipts.get("receipt_summary") or {}
    current_summary = current.get("evidence_summary") or {}
    local_receipt_gates = list(receipt_summary.get("gates_with_local_receipts") or [])
    release_grade_gates = list(receipt_summary.get("gates_with_release_grade_receipts") or [])
    all_local_receipts_complete = local_receipt_gates == REQUIRED_RELEASE_GRADE_GATES and receipt_summary.get("gates_missing_local_receipts") == []
    release_grade_receipts_complete = release_grade_gates == REQUIRED_RELEASE_GRADE_GATES

    status_lines = [line for line in git_output("status", "--porcelain=v1").splitlines() if line]
    untracked_lines = [line for line in status_lines if line.startswith("??")]
    tracked_dirty_lines = [line for line in status_lines if not line.startswith("??")]
    ahead, behind = ahead_behind()
    upstream = git_output("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    upstream_head = git_output("rev-parse", "--short", "@{u}") if upstream and "fatal:" not in upstream else ""
    current_head = git_output("rev-parse", "--short", "HEAD")

    clean_worktree_verified = not status_lines
    remote_sync_verified = bool(upstream and "fatal:" not in upstream and ahead == 0 and behind == 0 and current_head == upstream_head)
    external_ci = external_exact_head_ci_evidence(include_external_ci, require_external_ci, external_ci_run_id)
    exact_head_ci_verified = bool(receipt_summary.get("exact_head_ci_verified") is True or external_ci.get("exact_head_ci_verified") is True)
    release_complete = bool(handoff.get("release_complete")) and bool(merge.get("release_complete"))
    commercial_handoff_allowed = bool(handoff.get("commercial_handoff_allowed")) and bool(merge.get("commercial_handoff_allowed"))
    ready_to_merge = bool(handoff.get("ready_to_merge")) and bool(merge.get("ready_to_merge"))

    blockers: list[str] = []
    if not all_local_receipts_complete:
        blockers.append("local_receipts_incomplete")
    if not release_grade_receipts_complete:
        blockers.append("release_grade_receipts_empty")
    if not exact_head_ci_verified:
        blockers.append("exact_head_ci_not_verified")
    if not remote_sync_verified:
        blockers.append("remote_sync_not_verified")
    if ahead:
        blockers.append("branch_ahead_of_upstream")
    if behind:
        blockers.append("branch_behind_upstream")
    if not clean_worktree_verified:
        blockers.append("worktree_not_clean")
    if tracked_dirty_lines:
        blockers.append("tracked_dirty_files_present")
    if untracked_lines:
        blockers.append("untracked_files_present")
    if not release_complete:
        blockers.append("release_complete_false")
    if not commercial_handoff_allowed:
        blockers.append("commercial_handoff_not_allowed")
    if not ready_to_merge:
        blockers.append("ready_to_merge_false")

    promotion_ready = not blockers
    payload = {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": "promotion_ready" if promotion_ready else "blocked_release_promotion_required",
        "ci_safe": True,
        "source_packets": source_payloads(),
        "git_state": {
            "branch": git_output("branch", "--show-current"),
            "head": current_head,
            "upstream": upstream,
            "upstream_head": upstream_head,
            "ahead": ahead,
            "behind": behind,
            "worktree_clean": clean_worktree_verified,
            "tracked_dirty_count": len(tracked_dirty_lines),
            "untracked_count": len(untracked_lines),
            "dirty_count": len(status_lines),
        },
        "receipt_state": {
            "all_local_receipts_complete": all_local_receipts_complete,
            "gates_with_local_receipts": local_receipt_gates,
            "gates_missing_local_receipts": list(receipt_summary.get("gates_missing_local_receipts") or []),
            "gates_with_release_grade_receipts": release_grade_gates,
            "local_receipt_command_counts": dict(receipt_summary.get("local_receipt_command_counts") or {}),
            "gates_requiring_current_evidence": list(current_summary.get("gates_requiring_current_evidence") or []),
        },
        "promotion_checks": {
            "release_promotion_allowed": promotion_ready,
            "release_grade_update_allowed": promotion_ready,
            "release_grade_receipts_complete": release_grade_receipts_complete,
            "clean_worktree_verified": clean_worktree_verified,
            "remote_sync_verified": remote_sync_verified,
            "exact_head_ci_verified": exact_head_ci_verified,
            "exact_head_ci_source": "external_github_actions" if external_ci.get("exact_head_ci_verified") is True else "receipt_summary",
            "release_complete": release_complete,
            "commercial_handoff_allowed": commercial_handoff_allowed,
            "ready_to_merge": ready_to_merge,
        },
        "external_exact_head_ci_evidence": external_ci,
        "blockers": blockers,
        "required_commands": list(preflight.get("required_commands") or []),
        "must_not_use": list(preflight.get("must_not_use") or []),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Print commercial release promotion preflight.")
    parser.add_argument("--require-promotion-ready", action="store_true", help="Fail unless release-grade promotion is allowed.")
    parser.add_argument("--include-external-ci-evidence", action="store_true", help="Query GitHub Actions for current HEAD exact CI evidence.")
    parser.add_argument("--require-external-ci-evidence", action="store_true", help="Fail unless GitHub Actions verifies current HEAD exact CI evidence.")
    parser.add_argument("--external-ci-run-id", help="Specific GitHub Actions run id to verify as exact-head CI evidence.")
    args = parser.parse_args()

    payload = build_payload(
        include_external_ci=bool(args.include_external_ci_evidence or args.require_external_ci_evidence),
        require_external_ci=bool(args.require_external_ci_evidence),
        external_ci_run_id=args.external_ci_run_id,
    )
    if args.require_promotion_ready:
        require(payload["promotion_checks"]["release_promotion_allowed"] is True, f"promotion blockers remain: {payload['blockers']}")
        require(payload["promotion_checks"]["release_grade_update_allowed"] is True, "release-grade update is not allowed")
        require(payload["status"] == "promotion_ready", "promotion status is not ready")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
