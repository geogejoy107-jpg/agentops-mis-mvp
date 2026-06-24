#!/usr/bin/env python3
"""Smoke the commercial release-status API projection without external network."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    default_payload = server.commercial_release_status({}, {})
    require(default_payload.get("contract_id") == "commercial_release_status_api_v1", "contract mismatch")
    require((default_payload.get("safety") or {}).get("read_only") is True, "release status must be read-only")
    require((default_payload.get("safety") or {}).get("network_called") is False, "default release status must not call network")
    require((default_payload.get("external_exact_head_ci") or {}).get("checked") is False, "default external CI must not be checked")
    require(default_payload.get("release_complete") is False, "release status must not claim release completion")
    require(default_payload.get("commercial_handoff_allowed") is False, "release status must not allow handoff")
    require(default_payload.get("ready_to_merge") is False, "release status must not claim merge readiness")
    packet = default_payload.get("promotion_packet") or {}
    require(packet.get("contract_id") == "commercial_release_promotion_packet_v1", "promotion packet contract missing from release status")
    require(packet.get("read_only") is True, "promotion packet must be read-only")
    require("python3 scripts/commercial_release_promotion_packet.py --include-external-ci-evidence" in set(default_payload.get("commands", {}).values()), "promotion packet command missing")
    receipt_plan = default_payload.get("release_grade_receipt_plan") or {}
    require(receipt_plan.get("contract_id") == "commercial_release_grade_receipt_plan_v1", "release-grade receipt plan contract missing from release status")
    require(receipt_plan.get("read_only") is True, "release-grade receipt plan must be read-only")
    require("python3 scripts/commercial_release_grade_receipt_plan.py --include-external-ci-evidence" in set(default_payload.get("commands", {}).values()), "release-grade receipt plan command missing")
    rerun_bundle = default_payload.get("release_grade_rerun_bundle") or {}
    require(rerun_bundle.get("contract_id") == "commercial_release_grade_rerun_bundle_v1", "release-grade rerun bundle contract missing from release status")
    require(rerun_bundle.get("read_only") is True, "release-grade rerun bundle must be read-only")
    require("python3 scripts/commercial_release_grade_rerun_bundle.py --include-external-ci-evidence" in set(default_payload.get("commands", {}).values()), "release-grade rerun bundle command missing")

    original = server.commercial_release_external_ci_evidence

    def fake_external_ci(*, include_external_ci: bool, require_external_ci: bool = False, run_id: str | None = None) -> dict[str, Any]:
        require(include_external_ci is True, "explicit external CI request was not forwarded")
        return {
            "contract_id": "commercial_exact_head_ci_evidence_v1",
            "checked": True,
            "network_called": True,
            "external_check_requested": True,
            "exact_head_ci_verified": True,
            "status": "exact_head_ci_verified",
            "head": "test-head",
            "head_matches_current": True,
            "run_id": run_id or "test-run",
            "workflow": "Commercial Migration CI",
            "url": "https://example.invalid/actions/runs/test-run",
            "required_jobs_success": True,
            "job_gaps": [],
            "command": "python3 scripts/commercial_exact_head_ci_evidence.py --from-gh --require-current-head",
            "required_for_promotion": True,
        }

    try:
        server.commercial_release_external_ci_evidence = fake_external_ci
        explicit_payload = server.commercial_release_status({}, {"include_external_ci_evidence": ["1"], "external_ci_run_id": ["test-run"]})
    finally:
        server.commercial_release_external_ci_evidence = original

    exact = explicit_payload.get("external_exact_head_ci") or {}
    current = explicit_payload.get("current_evidence_status") or {}
    require(exact.get("checked") is True, "explicit external CI was not checked")
    require(exact.get("network_called") is True, "explicit external CI must mark network_called")
    require(exact.get("exact_head_ci_verified") is True, "explicit exact-head CI should verify")
    require(current.get("exact_head_ci_verified") is True, "effective current evidence should include explicit exact-head CI")
    require(current.get("exact_head_ci_source") == "external_github_actions", "external CI source mismatch")
    require((explicit_payload.get("safety") or {}).get("network_called") is True, "release status safety must reflect explicit network readback")
    require(explicit_payload.get("release_complete") is False, "external CI readback must not complete release")
    require(explicit_payload.get("commercial_handoff_allowed") is False, "external CI readback must not allow handoff")
    require(explicit_payload.get("ready_to_merge") is False, "external CI readback must not mark merge-ready")

    print(json.dumps({
        "ok": True,
        "contract": "commercial_release_status_api_v1",
        "default_network_called": (default_payload.get("safety") or {}).get("network_called"),
        "explicit_network_called": (explicit_payload.get("safety") or {}).get("network_called"),
        "explicit_exact_head_ci_verified": exact.get("exact_head_ci_verified"),
        "release_complete": explicit_payload.get("release_complete"),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
