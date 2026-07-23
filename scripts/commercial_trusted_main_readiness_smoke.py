#!/usr/bin/env python3
"""Negative fixtures for the trusted-main real-runtime readiness contract."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
READINESS_PATH = ROOT / "scripts" / "commercial_migration_readiness.py"
WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "commercial-real-runtime-acceptance.yml"
)
BLOCKERS_PATH = ROOT / "docs" / "HUMAN_MEMORY_REVIEW_RELEASE_BLOCKERS.json"
CONTRACT = "commercial_trusted_main_readiness_negative_v1"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_readiness() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "commercial_migration_readiness",
        READINESS_PATH,
    )
    require(spec is not None and spec.loader is not None, "readiness module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_exactly_once(text: str, old: str, new: str) -> str:
    require(text.count(old) == 1, f"fixture source count changed for {old!r}")
    return text.replace(old, new, 1)


def verify_workflow_negative_fixtures(
    readiness: ModuleType,
    workflow_text: str,
) -> dict[str, list[str]]:
    push_trigger = replace_exactly_once(
        workflow_text,
        "\npermissions:\n",
        "\n  push:\n\npermissions:\n",
    )
    fixtures = {
        "push_trigger_added": (
            push_trigger,
            "trusted_runtime_trigger_not_workflow_dispatch_only",
        ),
        "dispatch_trigger_replaced": (
            replace_exactly_once(
                workflow_text,
                "on:\n  workflow_dispatch:",
                "on:\n  push:",
            ),
            "trusted_runtime_trigger_not_workflow_dispatch_only",
        ),
        "main_ref_guard_weakened": (
            replace_exactly_once(
                workflow_text,
                "if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'",
                "if: github.event_name == 'workflow_dispatch'",
            ),
            "trusted_runtime_exact_main_ref_guard_missing",
        ),
        "protected_environment_removed": (
            replace_exactly_once(
                workflow_text,
                "environment: commercial-real-runtime",
                "environment: commercial-real-runtime-unprotected",
            ),
            "trusted_runtime_protected_environment_missing",
        ),
        "contents_permission_escalated": (
            replace_exactly_once(
                workflow_text,
                "  contents: read",
                "  contents: write",
            ),
            "trusted_runtime_permissions_not_least_privilege",
        ),
        "trusted_checkout_candidate_controlled": (
            replace_exactly_once(
                workflow_text,
                "          ref: ${{ github.sha }}",
                "          ref: ${{ inputs.candidate_ref }}",
            ),
            "trusted_runtime_main_checkout_binding_missing",
        ),
        "candidate_install_path_weakened": (
            replace_exactly_once(
                workflow_text,
                "run: npm --prefix candidate/ui/next-app ci --ignore-scripts",
                "run: npm --prefix ui/next-app ci",
            ),
            "trusted_runtime_candidate_install_path_invalid",
        ),
        "expected_sha_subject_binding_removed": (
            replace_exactly_once(
                workflow_text,
                '--subject-sha "$EXPECTED_SHA"',
                '--subject-sha "$GITHUB_SHA"',
            ),
            "trusted_runtime_receipt_or_harness_contract_missing",
        ),
        "candidate_harness_executed": (
            replace_exactly_once(
                workflow_text,
                "$GITHUB_WORKSPACE/trusted/scripts/nextjs_postgres_real_worker_human_review_smoke.py",
                "$GITHUB_WORKSPACE/candidate/scripts/nextjs_postgres_real_worker_human_review_smoke.py",
            ),
            "trusted_runtime_candidate_controlled_harness_forbidden",
        ),
        "candidate_source_binding_removed": (
            replace_exactly_once(
                workflow_text,
                '--source-root "$GITHUB_WORKSPACE/candidate" \\\n            --timeout',
                '--source-root "$GITHUB_WORKSPACE/trusted" \\\n            --timeout',
            ),
            "trusted_runtime_candidate_build_source_binding_missing",
        ),
    }
    results: dict[str, list[str]] = {}
    for name, (fixture, expected_failure) in fixtures.items():
        failures = readiness.trusted_real_runtime_workflow_failures(fixture)
        require(
            expected_failure in failures,
            f"{name} did not fail closed with {expected_failure}: {failures}",
        )
        results[name] = failures
    return results


def verify_blocker_negative_fixtures(
    readiness: ModuleType,
    blockers: dict,
) -> dict[str, list[str]]:
    fixtures: dict[str, tuple[dict, str]] = {}
    independent_builder = copy.deepcopy(blockers)
    independent_builder["external_runtime_receipt_requirement"][
        "builder_must_differ_from_candidate_authority"
    ] = False
    fixtures["independent_builder_requirement_removed"] = (
        independent_builder,
        "trusted_runtime_independent_builder_requirement_missing",
    )

    for blocker_id in readiness.TRUSTED_RUNTIME_SUPPLY_CHAIN_BLOCKERS:
        missing = copy.deepcopy(blockers)
        missing["open_blockers"] = [
            item
            for item in missing["open_blockers"]
            if item.get("id") != blocker_id
        ]
        fixtures[f"open_blocker_removed:{blocker_id}"] = (
            missing,
            f"trusted_runtime_supply_chain_blocker_missing:{blocker_id}",
        )

    weakened = copy.deepcopy(blockers)
    weakened_row = next(
        item
        for item in weakened["open_blockers"]
        if item.get("id") == "trusted_real_runtime_builder_not_established"
    )
    weakened_row["status"] = "closed"
    fixtures["builder_blocker_closed_without_real_evidence"] = (
        weakened,
        "trusted_runtime_supply_chain_blocker_weakened:"
        "trusted_real_runtime_builder_not_established",
    )

    results: dict[str, list[str]] = {}
    for name, (fixture, expected_failure) in fixtures.items():
        failures = readiness.trusted_runtime_blocker_contract_failures(fixture)
        require(
            expected_failure in failures,
            f"{name} did not fail closed with {expected_failure}: {failures}",
        )
        results[name] = failures
    return results


def main() -> int:
    readiness = load_readiness()
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    blockers = json.loads(BLOCKERS_PATH.read_text(encoding="utf-8"))

    workflow_failures = readiness.trusted_real_runtime_workflow_failures(
        workflow_text
    )
    blocker_failures = readiness.trusted_runtime_blocker_contract_failures(
        blockers
    )
    require(
        workflow_failures == [],
        f"current trusted workflow failed its contract: {workflow_failures}",
    )
    require(
        blocker_failures == [],
        f"current trusted blocker contract failed: {blocker_failures}",
    )

    workflow_negative = verify_workflow_negative_fixtures(
        readiness,
        workflow_text,
    )
    blocker_negative = verify_blocker_negative_fixtures(readiness, blockers)
    print(
        json.dumps(
            {
                "ok": True,
                "contract": CONTRACT,
                "files_read": [
                    str(WORKFLOW_PATH.relative_to(ROOT)),
                    str(BLOCKERS_PATH.relative_to(ROOT)),
                ],
                "workflow_positive": True,
                "blocker_positive": True,
                "workflow_negative_fixture_count": len(workflow_negative),
                "blocker_negative_fixture_count": len(blocker_negative),
                "workflow_negative_failures": workflow_negative,
                "blocker_negative_failures": blocker_negative,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
